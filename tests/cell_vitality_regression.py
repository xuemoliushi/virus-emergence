"""Presentation-only cell vitality: bounds, wiring, unchanged collisions and cost."""
from pathlib import Path
import json
import sys
import time
import statistics

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tests'))
from swarm_visual_physics_regression import make_runtime
from cell_render_regression import SETUP as DRAW_SETUP
OUT = ROOT/'validation/cell-vitality-20261017'

CASES = {
    'bounded irregular drift, asynchronous breathing and no immune drift': r'''
local Vitality=require('Game.Views.CellVitality');local v=Vitality.New()
local w={cells={},immunes={}}
for i=1,40 do
 w.cells[i]={id=i,x=i,y=2,radius=.4,phase=i*.31,state='HEALTHY'}
 w.immunes[i]={id=i,x=i,y=4,radius=.5,phase=i*.73,state='patrol'}
end
local before=snapshot(w);local minX,maxX=1e9,-1e9;local different=false
local previous,velocities={},{}
for _=1,1200 do
 v:Update(w,1/60,true)
 for _,c in ipairs(w.cells) do
  local p=v:Get(c)
  assert(math.abs(p.dx)<=.4*.075+1e-10 and math.abs(p.dy)<=.4*.060+1e-10)
  assert(p.sx>=.983 and p.sx<=1.017 and p.sy>=.987 and p.sy<=1.013)
  if previous[c] then
   local vx,vy=(p.dx-previous[c][1])*60,(p.dy-previous[c][2])*60
   assert(math.sqrt(vx*vx+vy*vy)<=c.radius*.017,'drift moves too fast')
   local velocity=velocities[c]
   if velocity then
    local ax,ay=(vx-velocity[1])*60,(vy-velocity[2])*60
    assert(math.sqrt(ax*ax+ay*ay)<=c.radius*.004,'drift direction changes abruptly')
   end
   velocities[c]={vx,vy}
  end
  previous[c]={p.dx,p.dy}
 end
 for _,c in ipairs(w.immunes) do local p=v:Get(c);assert(p.dx==0 and p.dy==0) end
 local p=v:Get(w.cells[1]);minX=math.min(minX,p.dx);maxX=math.max(maxX,p.dx)
 if math.abs(p.sx-v:Get(w.cells[2]).sx)>.003 then different=true end
end
assert(maxX-minX>.02 and different,'drift/breathing missing or synchronized')
assert(before==snapshot(w),'presentation mutated entities')
''',
    'paused/invalid delta, dead membrane freeze, culling and cleanup': r'''
local v=require('Game.Views.CellVitality').New()
local c={id=1,x=0,y=0,radius=.4,state='HEALTHY'}
local w={cells={c},immunes={}}
v:Update(w,1/60,true);local t=v.time
local p=v:Get(c);local dx,dy,sx,sy=p.dx,p.dy,p.sx,p.sy
for _,dt in ipairs({0,-1,0/0,math.huge}) do v:Update(w,dt,true) end
v:Update(w,1,false)
assert(v.time==t and p.dx==dx and p.dy==dy and p.sx==sx and p.sy==sy)
c.state='DEAD';v:Update(w,1/60,true)
assert(p.dx==dx and p.dy==dy and p.sx==sx and p.sy==sy)
v:Update(w,1/60,true,{x=100,y=100,w=5,h=5});assert(not next(v.poses))
v:Update(w,1/60,true);assert(v:Get(c));w.cells={};v:Update(w,1/60,true);assert(not next(v.poses))
v:Reset();assert(v.time==0 and not next(v.poses))
''',
    '600 real simulation steps retain identical world and collision poses': r'''
local a,b=quietWorld(),quietWorld();local pa,pb=Physics.New(),Physics.New()
local v=require('Game.Views.CellVitality').New()
a:SetMovement(1,0);b:SetMovement(1,0)
for i=1,600 do
 if i==40 then a:Split();b:Split() end
 if i==100 then a:SetMovement(0,1);b:SetMovement(0,1) end
 if i==200 then a:AbsorbNearby();b:AbsorbNearby() end
 a:Update(1/60);b:Update(1/60)
 pa:Update(a,nil,1/60,true,SURFACE);pb:Update(b,nil,1/60,true,SURFACE)
 v:Update(a,1/60,true)
 assert(snapshot(a)==snapshot(b),'gameplay changed at '..i)
 for j,pose in ipairs(pa.bodies) do
  local other=pb.bodies[j]
  assert(pose.x==other.x and pose.y==other.y and pose.radius==other.radius,'collision changed')
 end
end
''',
    'actual renderer uses drift/scales, restores before immune indicators, destroys cache': r'''
local w=quietWorld();w.immunes={{id=999,x=2,y=2,radius=.3,phase=.9,state='patrol',kind='tcell'}}
local view=View.New();for _=1,60 do view:Update(1/60,w,nil,true) end
nvgLineCap=function()end;nvgLineJoin=function()end;nvgPathWinding=function()end
nvgRadialGradient=function()return {}end;NVG_ROUND=1;NVG_HOLE=2
local c=w.cells[1];local pose=view.vitality:Get(c);local drawn
local original=view.DrawCell
view.DrawCell=function(self,nvg,x,y,r,entity,...)
 if entity==c then drawn={x,y} end
 return original(self,nvg,x,y,r,entity,...)
end
view:SetCamera(c);local before=snapshot(w)
view:DrawWorld({},0,0,1000,800,{sim={world=w},zoom=1})
local x,y=view:WorldToScreen(c.x+pose.dx,c.y+pose.dy,{x=0,y=0,w=1000,h=800},1)
assert(drawn and math.abs(drawn[1]-x)<1e-8 and math.abs(drawn[2]-y)<1e-8)
local found=false
local sc=60*2/760
calls={};view:DrawCell({},250,320,60,c,w.time)
for _,call in ipairs(calls) do
 if call[1]=='nvgScale' and math.abs(call[3]-sc*pose.sx)<1e-9 and math.abs(call[4]-sc*pose.sy)<1e-9 then found=true end
end
assert(found,'cell layers ignore breath')
calls={};view:DrawImmune({},200,300,40,w.immunes[1],w.time)
local ip=view.vitality:Get(w.immunes[1]);local depth=0;local scaled=false;local ring=false
for _,call in ipairs(calls) do
 if call[1]=='nvgSave' then depth=depth+1 elseif call[1]=='nvgRestore' then depth=depth-1 end
 if call[1]=='nvgScale' and call[3]==ip.sx and call[4]==ip.sy then scaled=true end
 if call[1]=='nvgCircle' and call[5]==42 then assert(depth==0,'warning ring stretched');ring=true end
end
assert(scaled and ring and depth==0 and before==snapshot(w))
view:Destroy();assert(not next(view.vitality.poses) and view.vitality.time==0)
''',
    'budding handoff follows scaled membrane and ends at original world position': r'''
local b=require('Game.Views.BuddingVisual').New()
local c={id=1,x=3,y=4,rotation=0}
local virus={id=8,x=3.8,y=4.5,radius=.045}
local cfg=Config.CellVisual
local record={shown=true,age=cfg.buddingSeconds,virus=virus,
 pose={frames={1},centres={{10,20}},diameters={12}}}
b.records[1]={record}
local pose={dx=.01,dy=-.02,sx=1.02,sy=.99};local got
local function draw(_,x,y)got={x,y}end
b:DrawHandoffs({},c,101,198,2,0,100,draw,{},pose)
assert(math.abs(got[1]-(101+10*1.02*2))<1e-8 and math.abs(got[2]-(198+20*.99*2))<1e-8)
record.age=cfg.buddingSeconds+cfg.buddingHandoffSeconds
b:DrawHandoffs({},c,101,198,2,0,100,draw,{},pose)
assert(math.abs(got[1]-180)<1e-8 and math.abs(got[2]-250)<1e-8,'handoff target inherited drift')
''',
}

def main():
    OUT.mkdir(exist_ok=True, parents=True)
    results=[]
    for name,code in CASES.items():
        try:
            lua=make_runtime()
            lua.globals().SCRIPT_PATH=str(ROOT/'scripts/?.lua').replace('\\','/')
            lua.execute(DRAW_SETUP)
            lua.execute(code)
            results.append({'name':name,'passed':True})
            print('PASS',name,flush=True)
        except Exception as e:
            results.append({'name':name,'passed':False,'error':str(e)})
            print('FAIL',name,str(e),flush=True)
    lua=make_runtime()
    lua.execute("v=require('Game.Views.CellVitality').New();w={cells={},immunes={}};for i=1,960 do w.cells[i]={id=i,x=i%40,y=math.floor(i/40),radius=.4,phase=i*.31,state='HEALTHY'} end;for i=1,30 do w.immunes[i]={id=i,x=i,y=4,radius=.5,phase=i*.73,state='patrol'} end;v:Update(w,1/60,true)")
    update=lua.eval('function()v:Update(w,1/60,true)end')
    for _ in range(100):update()
    timings=[]
    for _ in range(500):
        t=time.perf_counter();update();timings.append((time.perf_counter()-t)*1000)
    cost={'cells':960,'immunes':30,'samples':500,'median_ms':statistics.median(timings),
          'p95_ms':sorted(timings)[int(len(timings)*.95)],'scope':'Lua vitality update only, all visible, excludes render/GPU/FPS'}
    report={'tests':results,'passed':all(r['passed'] for r in results),'benchmark':cost}
    (OUT/'regression.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(cost,ensure_ascii=False),flush=True)
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
