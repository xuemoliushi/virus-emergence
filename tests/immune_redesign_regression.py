"""Natural conflict progression, warning speed, staged deployment and work slots."""
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.tmp/test-deps'),str(ROOT/'tests')]
from immune_adaptation_regression import SETUP,GROWTH_SETUP,COMMON,LuaRuntime
from ai_non_runtime_acceptance import plain

TESTS={
 'warning uses a quarter of pursuit speed for both immune kinds without damage':r'''
for _,kind in ipairs({'macrophage','tcell'}) do
 local w,m,c
 if kind=='macrophage' then w,m=clearFixture(kind,0);place(w,w.player,16,27.5)
 else
  w,m,c=nodeFixture(0);m.x,m.y=13,27.5;c.x,c.y=16,27.5
  m._patrolX,m._patrolY=m.x,m.y;w:_Infect(c,'fixture')
 end
 untilState(w,m,'warning')
 local mass=w.player.mass;local x,y=m.x,m.y;tick(w,.1)
 local warned=distance({x=x,y=y},m)
 assert(warned>0 and w.player.mass==mass and (not c or c.immuneHits==0))
 m.state='chase';x,y=m.x,m.y;tick(w,.1)
 near(warned/distance({x=x,y=y},m),cfg.immuneWarningSpeedFactor,1e-7)
end
''',
 'pursuers chase visible groups while cleaners clear particles and defend close contact':r'''
for _,role in ipairs({'pursuit','cleanup'}) do
 local w,m=immuneFixture('macrophage');m.dutyRole=role
 local c=unitCell(w);m.x,m.y=13,27.5;m._patrolX,m._patrolY=m.x,m.y
 w:_Release(c,1);w.cells={}
 local v=w.releasedViruses[1];v.x,v.y=m.x,m.y
 place(w,w.player,m.x+2.5,m.y);tick(w,cfg.movementStep)
 assert(m.targetType==(role=='pursuit' and 'swarm' or 'virus'))
 reset(w,m);place(w,w.player,m.x+1,m.y);tick(w,cfg.movementStep)
 assert(m.targetType=='swarm','cleanup still defends itself at close range')
end
''',
 'immune presentation crosses ordinary tissue without any projection jump':r'''
local Physics=require('Game.SwarmVisualPhysics')
local p,q=Physics.New(),Physics.New()
local a={id=1,x=-.8,y=0,radius=.48,state='patrol',phase=0}
local b={id=1,x=-.8,y=0,radius=.48,state='patrol',phase=0}
local tissue={cells={{id=1,x=0,y=0,radius=.5,state='HEALTHY'}},swarms={},viruses={},releasedViruses={},immunes={a}}
local empty={cells={},swarms={},viruses={},releasedViruses={},immunes={b}}
for i=1,180 do
 a.x,b.x=-.8+i*.01,-.8+i*.01
 p:Update(tissue,nil,1/60,true);q:Update(empty,nil,1/60,true)
 local x,y=p:Position(a);local ex,ey=q:Position(b)
 near(x,ex);near(y,ey);assert(p.cellChecks==0)
end
''',
}

PRODUCTION=r'''
local C=require('Core.Config');C.Gameplay.mapSeed=SEED
local W=require('Core.SwarmWorld');local I=require('Core.ImmuneSystem');local D=require('Core.ImmuneDirector')
local w=W.New('UPPER_AIRWAY');local expected={10,16,24,32,40,50};local deployed={#w.immunes}
assert(#w.immunes==10)
for level=1,5 do
 local before=#w.immunes
 w:SetDebugImmuneAlertLevel(level);D.Update(w,4.9)
 assert(D.PopulationLimit(w)==expected[level] and #w.immunes==before)
 I.Recruit(w,100);assert(#w.immunes==before,'buffer must not deploy next stage')
 D.Update(w,.1);assert(D.PopulationLimit(w)==expected[level+1] and #w.immunes==before)
 I.Recruit(w,1.99);assert(#w.immunes==before)
 I.Recruit(w,.01);assert(#w.immunes==before+1,'first deployment after two seconds')
 local n=#w.immunes;I.Recruit(w,100);assert(#w.immunes==n+1,'large dt cannot create a wave instantly')
 for i=1,60 do I.Recruit(w,2) end
 assert(#w.immunes==expected[level+1],'stage budget not reached with safe entries')
 deployed[#deployed+1]=#w.immunes
end
local regions={}
for id=1,5 do regions[id]={pursuit=0,cleanup=0,node=0,total=0} end
for _,im in ipairs(w.immunes) do
 local r=regions[im.patrolHome.regionId];r[im.dutyRole]=r[im.dutyRole]+1;r.total=r.total+1
 assert(w.map:Contains(im.x,im.y,im.radius))
 for _,s in ipairs(w.swarms) do
  assert((im.x-s.x)^2+(im.y-s.y)^2>=(w.config.immuneSafeDistance+im.radius+s.radius)^2)
 end
end
for _,r in ipairs(regions) do assert(r.pursuit>=2 and r.cleanup>=2 and r.node>=4) end
-- Arrange three real workers and three separate particle buckets within one
-- local work area. Only two may take work; the third takes a released slot.
local macros,tcells={},{}
for _,im in ipairs(w.immunes) do
 local list=im.kind=='macrophage' and macros or tcells;list[#list+1]=im
end
local cell
for _,c in ipairs(w.cells) do
 local ok=c.regionId==3
 for _,offset in ipairs({-1.6,0,1.6}) do
  ok=ok and w.map:Contains(c.x+offset,c.y,.48)
   and w.map:RegionAt(c.x+offset,c.y)==c.regionId
   and w:_DirectPathClear(c.x,c.y,c.x+offset,c.y,.48)
 end
 if ok then cell=c;break end
end
assert(cell,'legal area fixture')
local function pose(im)
 D.Release(w,im);im.state='patrol';im.targetId,im.targetType=nil,nil
 im.x,im.y=cell.x,cell.y;im.regionId=cell.regionId
 im._patrolX,im._patrolY=im.x,im.y;im._patrolTimer=0;im.cooldown=0;im.processingLoad=0
 im.patrolHome={x=im.x,y=im.y,regionId=cell.regionId};im.returningHome=false
end
w.immunes={macros[1],macros[2],macros[3]};D.Init(w);w.player.isHidden=true
for _,im in ipairs(w.immunes) do pose(im) end
w:_Release(cell,3)
for i,v in ipairs(w.releasedViruses) do v.x,v.y=cell.x+(i-2)*1.6,cell.y end
I.Update(w,w.config.movementStep)
local busy=0;local idle
for _,im in ipairs(w.immunes) do if im.targetId then busy=busy+1 else idle=im end end
assert(busy==2 and idle,'work area must not absorb a third worker')
local first=w.immunes[1];D.Release(w,first);first.targetId,first.targetType=nil,nil
first.state='processing';first.processingLoad=6
I.Update(w,w.config.movementStep);assert(idle.targetType=='virus','freed work slot never reassigned')
-- Health screening also has a single owner for each cell.
w.immunes={tcells[1],tcells[2]};D.Init(w);w.cells={cell};w.releasedViruses={};w.activeImmuneAlertLevel=3
for _,im in ipairs(w.immunes) do pose(im);im._cellChecks={};im._screenCellId=nil end
I.Update(w,w.config.movementStep)
local screens=0;for _,im in ipairs(w.immunes) do if im._screenCellId==cell.id then screens=screens+1 end end
assert(screens==1,'T cells stacked on the same healthy screening cell')
return {seed=SEED,counts=deployed,regions=regions,areaWorkers=busy,screenWorkers=screens}
'''


def main():
 rows=[]
 for name,code in TESTS.items():
  lua=LuaRuntime(unpack_returned_tuples=True);lua.globals().print=lambda *a:None
  lua.execute("package.path='scripts/?.lua;'..package.path")
  try:lua.execute(SETUP+GROWTH_SETUP+COMMON+code);r=dict(name=name,passed=True)
  except Exception as e:r=dict(name=name,passed=False,error=str(e))
  rows.append(r);print(r,flush=True)
 for seed in [314159,271828,161803]:
  lua=LuaRuntime(unpack_returned_tuples=True);lua.globals().print=lambda *a:None;lua.globals().SEED=seed
  lua.execute("package.path='scripts/?.lua;'..package.path")
  try:r=dict(seed=seed,passed=True,metrics=plain(lua.execute(PRODUCTION)))
  except Exception as e:r=dict(seed=seed,passed=False,error=str(e))
  rows.append(r);print(json.dumps(r),flush=True)
 out=ROOT/'validation/immune-redesign-20261017';out.mkdir(parents=True,exist_ok=True)
 (out/'targeted.json').write_text(json.dumps(dict(passed=all(r['passed'] for r in rows),results=rows),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 return int(any(not r['passed'] for r in rows))


if __name__=='__main__':raise SystemExit(main())
