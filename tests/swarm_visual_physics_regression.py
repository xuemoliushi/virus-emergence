"""Real Lua presentation solver: geometry, lifecycle, gameplay purity and CPU cost.

Uses the existing Unicode-safe Lua 5.4 harness. Timings exclude rendering/GPU;
controlled-state plots are evidence of trajectories, not native acceptance.
"""
from pathlib import Path
import json
import math
import time
from performance_regression import runtime, ROOT, percentile

OUT = ROOT / 'validation/swarm-visual-physics-20261017'
SETUP = r'''
Physics=require('Game.SwarmVisualPhysics')
function visualWorld(count)
 local w={cells={},swarms={{id=1,x=-.9,y=0,radius=.48,mass=count}},viruses={},releasedViruses={},immunes={}}
 for i=1,count do
  local a=i*2.399963;local r=.48*math.sqrt((i-.5)/count)
  w.viruses[i]={id=i,swarmId=1,x=w.swarms[1].x+math.cos(a)*r,y=math.sin(a)*r,radius=.045,phase=a}
 end
 return w,Physics.New()
end
function advance(w,p,n)
 for _=1,n do p:Update(w,nil,1/60,true,SURFACE) end
end
function separation(p)
 local ratio=math.huge
 for i,a in ipairs(p.bodies) do for j=i+1,#p.bodies do
  local b=p.bodies[j]
  local d=math.sqrt((a.x-b.x)^2+(a.y-b.y)^2)
  ratio=math.min(ratio,d/(a.radius+b.radius+a.padding+b.padding))
 end end
 return ratio
end
function outside(w,p)
 for _,b in ipairs(p.bodies) do for _,c in ipairs(w.cells) do if c.state~='DEAD' then
  local dx,dy=b.x-c.x,b.y-c.y
  assert(math.sqrt(dx*dx+dy*dy)+1e-6>=p:CellRadius(c,math.atan(dy,dx))+b.radius,
   'body visibly penetrated membrane')
 end end end
end
'''

CASES = {
    'one-sided pack refills the disk after losses with unchanged entities': r'''
local w,p=visualWorld(60);advance(w,p,1)
for _,b in ipairs(p.bodies) do b.x=-1.3;b.y=b.y*.2 end
-- Simulate losses without updating cached swarm.mass.
for i=60,31,-1 do table.remove(w.viruses,i) end
advance(w,p,360)
local sectors={0,0,0,0};local inner,outer=0,0
for _,b in ipairs(p.bodies) do
 local dx,dy=b.x-w.swarms[1].x,b.y-w.swarms[1].y
 local sector=math.floor((math.atan(dy,dx) % (2*math.pi))/(math.pi/2))+1
 sectors[sector]=sectors[sector]+1
 local r=math.sqrt(dx*dx+dy*dy)
 if r<.25 then inner=inner+1 end
 if r>.3 then outer=outer+1 end
 assert(r<.65,'refill escaped disk')
end
for _,count in ipairs(sectors) do assert(count>=4,'empty sector remained') end
assert(inner>=4 and outer>=4,'disk interior or outer rim remained empty')
assert(#w.viruses==30 and #p.bodies==30,'refill created viruses')
assert(separation(p)>.97,'refill caused overlap')
''',
    'irregular spacing and gentle continuous drift at rest': r'''
local w,p=visualWorld(30);advance(w,p,300)
local low,high=math.huge,0
local prior={}
for i,a in ipairs(p.bodies) do
 local nearest=math.huge
 for _,b in ipairs(p.bodies) do if a~=b then
  nearest=math.min(nearest,math.sqrt((a.x-b.x)^2+(a.y-b.y)^2)-a.radius-b.radius)
 end end
 low,high=math.min(low,nearest),math.max(high,nearest)
 prior[i]={a.x,a.y}
end
assert(high-low>.008,'pack spacing still resembles a uniform lattice')
advance(w,p,60)
local moved=0
for i,b in ipairs(p.bodies) do
 local d=math.sqrt((b.x-prior[i][1])^2+(b.y-prior[i][2])^2)
 if d>.001 then moved=moved+1 end
 assert(d<.3,'drift is too violent')
end
assert(moved>10,'stationary pack has no visible local drift')
local t=p.visualTime;p:Update(w,nil,1,false,SURFACE);assert(p.visualTime==t)
''',
    'short-range spacing and gentle bounded central cohesion': r'''
local w,p=visualWorld(30);advance(w,p,240)
assert(separation(p)>.97,'particles overlap at rest: '..separation(p))
for _,b in ipairs(p.bodies) do
 assert(math.sqrt((b.x+.9)^2+b.y*b.y)<.65,'cohesion lost')
 assert(math.abs(b.spin)<5)
end
local b=p.poses[w.viruses[1]];b.x=b.x+2
advance(w,p,300);assert(math.abs(b.x+.9)<.65,'stray did not return')
''',
    'membrane pile-up, outer layers and recovery after moving away': r'''
local w,p=visualWorld(30)
w.cells={{id=1,x=0,y=0,radius=.4,state='HEALTHY',rotation=.37}}
advance(w,p,60)
for _=1,80 do w.swarms[1].x=w.swarms[1].x+.006;p:Update(w,nil,1/60,true,SURFACE) end
advance(w,p,120);outside(w,p)
local front,back=0,0
for _,b in ipairs(p.bodies) do
 local angle=math.atan(b.y,b.x)
 local surface=p:CellRadius(w.cells[1],angle)+b.radius
 local d=math.sqrt(b.x*b.x+b.y*b.y)-surface
 if d<.03 then front=front+1 end
 if d>.10 then back=back+1 end
end
assert(front>=3 and back>=3,'expected attached front and compressed outer layer')
assert(separation(p)>.85,'excessive pile-up overlap: '..separation(p))
for _=1,140 do w.swarms[1].x=w.swarms[1].x-.008;p:Update(w,nil,1/60,true,SURFACE) end
advance(w,p,180)
for _,b in ipairs(p.bodies) do
 assert(math.sqrt((b.x-w.swarms[1].x)^2+b.y*b.y)<.7,'pack failed to recover')
end
''',
    'virus/cell and immune pairs collide; immunity passes through tissue': r'''
local w,p=visualWorld(20)
w.cells={{id=1,x=0,y=0,radius=.4,state='HEALTHY'}}
w.immunes={{id=1,x=-.35,y=0,radius=.3,state='patrol'},
 {id=2,x=-.35,y=.25,radius=.3,state='patrol'}}
advance(w,p,180)
for _,b in ipairs(p.bodies) do if not b.immune then
 for _,c in ipairs(w.cells) do
  local dx,dy=b.x-c.x,b.y-c.y
  assert(math.sqrt(dx*dx+dy*dy)+1e-6>=p:CellRadius(c,math.atan(dy,dx))+b.radius)
 end
end end
for _,a in ipairs(p.bodies) do for _,b in ipairs(p.bodies) do
 if a~=b and (a.immune or b.immune) then
  assert(math.sqrt((a.x-b.x)^2+(a.y-b.y)^2)>a.radius+b.radius-.025,'immune overlap')
 end
end end
''',
    'collision-induced rotation decays without runaway spin': r'''
local w,p=visualWorld(1);advance(w,p,1)
local b=p.poses[w.viruses[1]]
w.cells={{id=1,x=0,y=0,radius=.4,state='HEALTHY'}}
b.x,b.y,b.vx,b.vy=-.43,0,1,1
local angle=b.angle;advance(w,p,12)
assert(math.abs(b.angle-angle)>.01,'tangential contact produced no rotation')
advance(w,p,480);assert(math.abs(b.spin)<.02,'spin failed to damp')
''',
    'pause, bad delta, hidden/dead/absorbed entities, split, world reset': r'''
local w,p=visualWorld(30);advance(w,p,2)
local virus=w.viruses[1];local b=p.poses[virus]
local x,y,a=b.x,b.y,b.angle
for _,dt in ipairs({0,-1,0/0,math.huge}) do p:Update(w,nil,dt,true,SURFACE) end
p:Update(w,nil,.25,false,SURFACE)
assert(b.x==x and b.y==y and b.angle==a,'pause advanced particles')
w.swarms[2]={id=2,x=-.4,y=.2,radius=.3,mass=1};virus.swarmId=2
advance(w,p,1);assert(p.poses[virus]==b,'split discarded individual identity')
w.swarms[2].isHidden=true;advance(w,p,1);assert(p.poses[virus]==nil)
table.remove(w.viruses,2);advance(w,p,1);assert(#p.bodies==28)
w.releasedViruses={{id=1,x=-1,y=0,radius=.045,state='DRIFTING'}}
advance(w,p,1);assert(p.poses[w.releasedViruses[1]])
w.releasedViruses[1].state='ABSORBED';advance(w,p,1);assert(not p.poses[w.releasedViruses[1]])
local replacement=visualWorld(1);p:Update(replacement,nil,1/60,true,SURFACE)
assert(not p.poses[virus] and #p.bodies==1)
p:Reset();assert(not next(p.poses) and #p.bodies==0)
''',
    'offscreen sleeping and large frame bounded work': r'''
local w,p=visualWorld(30)
p:Update(w,nil,.25,true,SURFACE,{x=30,y=30,w=3,h=3})
assert(#p.bodies==0 and not next(p.poses),'offscreen body did not sleep')
p:Update(w,nil,.25,true,SURFACE,{x=-3,y=-3,w=6,h=6})
assert(#p.bodies==30 and p.steps<=4)
for _,b in ipairs(p.bodies) do assert(b.x==b.x and b.y==b.y) end
''',
    'coincident births have a linear neighbour-check ceiling': r'''
local w,p=visualWorld(1000)
for _,v in ipairs(w.viruses) do v.x,v.y=-.9,0 end
advance(w,p,1)
assert(p.pairChecks<=1000*48*2 and #p.bodies==1000,'unbounded all-pairs workload')
for _,b in ipairs(p.bodies) do assert(b.x==b.x and math.abs(b.x)<4) end
''',
    '600 real simulation steps exactly match with/without presentation': r'''
local a,b=quietWorld(),quietWorld();local p=Physics.New()
a:SetMovement(1,0);b:SetMovement(1,0)
for i=1,600 do
 if i==40 then a:Split();b:Split() end
 if i==100 then a:SetMovement(0,1);b:SetMovement(0,1) end
 if i==200 then a:AbsorbNearby();b:AbsorbNearby() end
 a:Update(1/60);b:Update(1/60)
 local before=snapshot(a)
 p:Update(a,nil,(i%2==0 and 1/30 or 1/120),true,SURFACE)
 assert(before==snapshot(a) and before==snapshot(b),'gameplay changed at step '..i)
end
''',
}


def make_runtime():
    lua = runtime(ROOT / 'scripts')
    data = json.loads((ROOT / 'assets/image/cell_surface_data.json').read_text())
    lua.globals().SURFACE = lua.table_from(data, recursive=True)
    lua.execute(SETUP)
    return lua


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for name, source in CASES.items():
        try:
            make_runtime().execute(source)
            results.append({'name': name, 'passed': True})
            print('PASS', name, flush=True)
        except Exception as error:
            results.append({'name': name, 'passed': False, 'error': str(error)})
            print('FAIL', name, str(error), flush=True)
    # Exercise the actual CellView wiring after an update, then verify rendering
    # neither advances particles nor writes authoritative state.
    try:
        from cell_render_regression import SETUP as DRAW_SETUP
        lua = make_runtime()
        lua.globals().SCRIPT_PATH = str(ROOT / 'scripts/?.lua').replace('\\', '/')
        lua.execute(DRAW_SETUP)
        lua.execute(r'''
nvgLineCap=function()end;nvgLineJoin=function()end;nvgPathWinding=function()end
nvgRadialGradient=function()return {}end;NVG_ROUND=1;NVG_HOLE=2
local w=quietWorld();local v=View.New()
for _=1,20 do v:Update(1/60,w,nil,true) end
local virus=w.viruses[1];local body=v.swarmPhysics.poses[virus]
local x,y=body.x,body.y;local state=snapshot(w);local got
local original=v.DrawVirus
v.DrawVirus=function(self,nvg,px,py,r,entity,...)
 if entity==virus then got={px,py} end
 return original(self,nvg,px,py,r,entity,...)
end
v:SetCamera(w.player)
v:DrawWorld({},0,0,1000,800,{sim={world=w},zoom=1})
local px,py=v:WorldToScreen(x,y,{x=0,y=0,w=1000,h=800},1)
assert(got and math.abs(got[1]-px)<1e-6 and math.abs(got[2]-py)<1e-6,'draw ignored collision pose')
assert(state==snapshot(w) and body.x==x and body.y==y,'render advanced state')
v:Destroy();assert(not next(v.swarmPhysics.poses))
''')
        results.append({'name': 'actual CellView pose routing, read-only drawing and cleanup', 'passed': True})
        print('PASS actual CellView pose routing, read-only drawing and cleanup', flush=True)
    except Exception as error:
        results.append({'name': 'actual CellView pose routing, read-only drawing and cleanup',
                        'passed': False, 'error': str(error)})
        print('FAIL actual CellView pose routing', str(error), flush=True)
    timings = []
    for count in (30, 300, 1000):
        lua = make_runtime()
        lua.execute(f'w,p=visualWorld({count});advance(w,p,30)')
        update = lua.eval('function()p:Update(w,nil,1/60,true,SURFACE)end')
        values = []
        for _ in range(90):
            start = time.perf_counter()
            update()
            values.append((time.perf_counter()-start)*1000)
        timings.append(dict(count=count, distribution='dense pack',
                            median_ms=percentile(values, .5), p95_ms=percentile(values, .95),
                            pair_checks=lua.eval('p.pairChecks'), steps=lua.eval('p.steps')))
    report = dict(scope='Lua 5.4 CPU; excludes rendering, GPU, mobile FPS',
                  cases=results, timings=timings)
    (OUT / 'regression.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(timings), flush=True)
    raise SystemExit(any(not result['passed'] for result in results))


if __name__ == '__main__':
    main()
