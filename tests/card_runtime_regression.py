"""Card performance changes retain particle ownership, collision and route recovery."""
import json
from mechanism_cards_regression import ROOT,SETUP,GROWTH_SETUP,EXTRA,LuaRuntime

CASES={
 'bulk particle extraction preserves old reverse selection and every surviving formation index':r'''
local P=require('Core.SwarmParticles')
for n=0,300,13 do for _,count in ipairs({0,1,3,15,16,17,90,400}) do for swarm=1,7 do
 local actual,expected={},{}
 for i=1,n do local v={id=i,swarmId=(i*17)%6+1};actual[i]=v;expected[i]=v end
 local removed={}
 for i=#expected,1,-1 do
  if #removed>=count then break end
  if expected[i].swarmId==swarm then removed[#removed+1]=table.remove(expected,i) end
 end
 local taken=P.Take(actual,swarm,count)
 assert(#actual==#expected and #taken==#removed)
 for i,v in ipairs(expected) do assert(actual[i]==v) end
 for i,v in ipairs(removed) do assert(taken[i]==v) end
end end end
''',
 'large hidden-node casualty and lethal tail preservation retain real mass and other groups':r'''
local w=manyGroups(3);grant(w,'node_hide');grant(w,'tail_preserve')
local s=w.player
w:_AddParticles(s,3000-s.mass);s.mass=3000;w:_RefreshGroupShape(s)
local other=w.swarms[2];local otherMass=other.mass
local c=unitCell(w);c.state='PRODUCTIVE';w.cells={c}
s.hiddenCellId=c.id;s.isHidden=true
local before=w:ControlledCount();w:KillCell(c,'immune')
assert(s.mass==1500 and w:ControlledCount()==before-1500 and not s.isHidden)
local im={x=s.x+1,y=s.y}
local damage=A.ImmuneDamage(w,s,s.mass,im)
assert(damage==1498 and w.abilities.tailSaved)
w:DamageSwarm(s.id,damage)
assert(s.mass==2 and other.mass==otherMass and w:ControlledCount()==before-2998)
local actual=0;for _,p in ipairs(w.viruses) do if p.swarmId==s.id then actual=actual+1 end end
assert(actual==2 and w.massLedger.totals.hide_node_loss==1500)
''',
 'indexed cell avoidance exactly matches full scan for overlaps and long swept movements':r'''
local w=quietWorld();local AI=require('Core.SplitVirusAI')
local old=assert(loadfile(BASELINE..'/SplitVirusAI.lua'))()
w.cellGrid:Build(w.cells);w._cellSpatialActive=true
for i=1,500 do
 local c=w.cells[(i*37)%#w.cells+1]
 local s={x=c.x+(i%9-4)*.2,y=c.y+(i%7-3)*.2,radius=(i%6)*.1}
 local tx,ty=s.x+math.cos(i)*(i%5==0 and 10 or .06),s.y+math.sin(i)*(i%5==0 and 10 or .06)
 local ax,ay=AI.RestrictCellMotion(w,s,tx,ty)
 local bx,by=old.RestrictCellMotion(w,s,tx,ty)
 assert(ax==bx and ay==by,'indexed body sweep missed a cell')
end
w._cellSpatialActive=false
assert(w:NearbyCells(0,0,1)==w.cells)
w:Update(1/60);assert(not w._cellSpatialActive and not w._spatialActive)
assert(w:NearbyCells(0,0,1)==w.cells)
''',
 'camouflage loses cleared cover immediately and matches full scan while moving':r'''
local a,b=quietWorld(),quietWorld();grant(a,'debris_camouflage');grant(b,'debris_camouflage')
local old=assert(loadfile(BASELINE..'/AbilityRuntime.lua'))()
for _,w in ipairs({a,b}) do
 local c=unitCell(w);c.state='DEAD';w.cellGrid:Build(w.cells);w._cellSpatialActive=true
end
for step=1,200 do
 for _,w in ipairs({a,b}) do
  w.player.x=w.cells[1].x+((step%70)/20)
  if step==50 then w._immuneClearedDebris={[w.cells[1].id]=true} end
  if step==90 then w._immuneClearedDebris={} end
 end
 old.RefreshCamouflage(a,step%10==0 and 0 or 1/60)
 A.RefreshCamouflage(b,step%10==0 and 0 or 1/60)
 for _,key in ipairs({'camouflaged','camouflageTime','camouflageX','camouflageY'}) do assert(a.player[key]==b.player[key],key) end
 assert(#a.events==#b.events)
end
''',
 'dispatch reuses valid paths and replans for target movement growth blockage and failure':r'''
local w=manyGroups(2);local Nav=require('Core.ImmuneNavigation');local s=w.swarms[2];s.radius=.2
local c=unitCell(w);local destination
for _,r in ipairs(w.map.regions) do
 if not Nav.Clear(w.map,s,r,.2) and Nav.Route(w.map,s,r,.2) then destination=r;break end
end
assert(destination)
s.groupCommand={kind='hold',cellId=c.id,point={x=destination.x,y=destination.y},routeAt=0}
local original=Nav.Route;local calls=0;Nav.Route=function(...) calls=calls+1;return original(...) end
local function moveAt(time) w.time=time;return A.Movement(w,s,0,0,.5,1/60) end
moveAt(0);assert(calls==1 and s.groupCommand.route)
moveAt(.6);assert(calls==1)
s.radius=.21;moveAt(1.2);assert(calls==2)
local cmd=s.groupCommand
cmd.point.x=cmd.point.x+.4;moveAt(1.8);assert(calls==3)
cmd.route={{x=-10,y=-10}};moveAt(2.4);assert(calls==4)
cmd.point={x=-10,y=-10};moveAt(3);local before=calls
for i=1,180 do moveAt(3+i/60) end
assert(calls-before<=6 and not cmd.route,'unreachable point searches every frame')
c.state='DEAD';moveAt(7);assert(not s.groupCommand)
''',
}

def run():
    rows=[]
    for name,code in CASES.items():
        lua=LuaRuntime(unpack_returned_tuples=True)
        lua.execute('package.path='+repr((ROOT/'scripts/?.lua').as_posix())+"..';'..package.path")
        lua.globals().BASELINE=(ROOT/'validation/card-runtime-performance-20261018/baseline').as_posix()
        lua.globals().print=lambda *args:None
        lua.execute(SETUP+GROWTH_SETUP+EXTRA+code)
        rows.append({'name':name,'passed':True});print('PASS',name,flush=True)
    (ROOT/'validation/card-runtime-performance-20261018/contracts.json').write_text(json.dumps(rows,indent=2),encoding='utf8')

if __name__=='__main__':run()
