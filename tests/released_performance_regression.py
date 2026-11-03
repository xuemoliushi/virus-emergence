"""Exact flow/movement equivalence and large released-virus Lua CPU benchmark.

Uses production v5 geometry, default gameplay and the final-stage immune budget. Setup,
map generation and state serialization are excluded from frame timings. Does
not measure native rendering, GPU, touch input or device FPS.
"""
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'validation/released-performance-20261017'
sys.path[:0] = [str(ROOT / '.tmp/test-deps'), str(ROOT / 'tests')]
from lua_test_runtime import LuaRuntime
from performance_regression import FIXTURE as SERIALIZER
from ai_non_runtime_acceptance import plain

GEOMETRY = r'''
local Config=require('Core.Config')
Config.Gameplay.mapSeed=SEED
local Map=require('Core.RespiratoryMap');local Layout=require('Core.FlatMapLayout')
local OldLayout=assert(loadfile(BASELINE..'/Core/FlatMapLayout.lua'))()
local OldMap=assert(loadfile(BASELINE..'/Core/FlatWorldMap.lua'))()
local m=Map.New(Config.Gameplay,'UPPER_AIRWAY')
local rng=SEED
local function random() rng=(rng*48271)%2147483647;return rng/2147483647 end
local flowCount,moveCount=0,0
local function flow(x,y)
 local a,b=OldLayout.FlowAt(m,x,y);local c,d=Layout.FlowAt(m,x,y)
 assert(a==c and b==d,string.format('flow mismatch (%.17g,%.17g): %.17g %.17g / %.17g %.17g',x,y,a,b,c,d))
 flowCount=flowCount+1
end
local function move(x,y,tx,ty,r)
 local a,b=OldMap.Move(m,x,y,tx,ty,r);local c,d=m:Move(x,y,tx,ty,r)
 assert(a==c and b==d,'movement mismatch');moveCount=moveCount+1
end
for y=0,m.height-1 do for x=0,m.width-1 do flow(x+.5,y+.5) end end
for i=1,6000 do
 local x,y=random()*m.width,random()*m.height
 flow(x,y)
 local span=i%2==0 and .025 or 12
 move(x,y,x+(random()-.5)*span,y+(random()-.5)*span,({0,.045,.48,1.35})[i%4+1])
end
-- Flow sides, endpoints, overlaps and exact bucket boundaries, including turns.
for _,f in ipairs(m.flows) do
 if f.points then
  local stride=math.max(1,math.floor(#f.points/25))
  for i=1,#f.points-1,stride do
   local a,b=f.points[i],f.points[i+1];local dx,dy=b.x-a.x,b.y-a.y
   local length=math.sqrt(dx*dx+dy*dy)
   for _,fraction in ipairs({0,.5,1}) do for _,side in ipairs({-1,-.999999,0,.999999,1}) do
    flow(a.x+dx*fraction-dy/length*f.width*.5*side,a.y+dy*fraction+dx/length*f.width*.5*side)
   end end
  end
 else
  for i=0,31 do
   local angle=i*math.pi/16
   for _,r in ipairs({f.ringRadius-f.width/2,f.ringRadius,f.ringRadius+f.width/2}) do
    flow(f.cx+math.cos(angle)*r,f.cy+math.sin(angle)*r)
   end
  end
 end
end
for y=0,m.height,4 do for x=0,m.width,4 do flow(x,y);flow(x-1e-10,y+1e-10) end end
for _,r in ipairs({0,.045,.48,1.35}) do
 for i=1,1500 do
  local x,y=random()*m.width,random()*m.height
  move(x,y,x+(random()-.5)*1e-6,y+(random()-.5)*1e-6,r)
 end
end
-- Runtime edits of geometry use explicit invalidation; speed stays live.
local f=m.flows[1];local speed=f.speed
f.speed=speed*.75;flow(m.spawn.x+8,m.spawn.y);f.speed=speed
local width=f.width;f.width=width*1.2;Layout.InvalidateFlowIndex(m)
for i=1,300 do flow(random()*m.width,random()*m.height) end
f.width=width;Layout.InvalidateFlowIndex(m)
local flows=m.flows;m.flows={};flow(60,60);m.flows=flows;flow(60,60)
return {seed=SEED,flows=flowCount,moves=moveCount,exact=true}
'''

BENCH_SETUP = r'''
Config=require('Core.Config');Config.Gameplay.mapSeed=314159
World=require('Core.SwarmWorld')
local Map=require('Core.RespiratoryMap')
local template=Map.New(Config.Gameplay,'UPPER_AIRWAY')
local function clone(value,memo)
 if type(value)~='table' then return value end
 if memo[value] then return memo[value] end
 local result={};memo[value]=result
 for k,v in pairs(value) do result[clone(k,memo)]=clone(v,memo) end
 return setmetatable(result,getmetatable(value))
end
-- Reuse only a pristine geometry template. Each trial has independent map,
-- world, actors, timers, navigation, ecology, RNG and contact histories.
Map.New=function()return clone(template,{})end
function burst(count,dense)
 local w=World.New('UPPER_AIRWAY');local sites={}
 for _,c in ipairs(w.cells) do if c.id%20==0 and #sites<30 then sites[#sites+1]=c end end
 for i,c in ipairs(sites) do
  w:_Infect(c,'fixture');w:_Release(c,math.floor(count/#sites)+(i<=count%#sites and 1 or 0))
 end
 if dense then
  local c=w.cells[501]
  for _,v in ipairs(w.releasedViruses) do
   v.x,v.y=c.x+c.radius+v.radius+.01,c.y;v._oldX,v._oldY=v.x,v.y
  end
 end
 w.activeImmuneAlertLevel=5
 local budget=require('Core.ImmuneDirector').PopulationLimit(w)
 for i=1,budget do require('Core.ImmuneSystem').Recruit(w,2) end
 assert(#w.immunes==budget and #w.releasedViruses==count)
 w.events={};return w
end
'''

CONTACTS = r'''
local New=require('Core.CellContacts')
local Old=assert(loadfile(BASELINE..'/Core/CellContacts.lua'))()
local function cell()return {id=1,x=0,y=0,radius=.4,rotation=.37,contactVisuals={}}end
local a,b=cell(),cell();local rng=1729;local stream={}
local function random()rng=(rng*48271)%2147483647;return rng/2147483647 end
for frame=1,360 do
 local acceptedA,acceptedB={},{}
 local count=frame%60<20 and 0 or (frame%7==0 and 7 or 1200)
 for id=1,count do
  if random()>.2 then
   local angle=id*2.399963+frame*.01;local radius=id%17==0 and 0 or (.2+random()*.5)
   local source={id=id,x=math.cos(angle)*radius,y=math.sin(angle)*radius,radius=.045}
   local strength=id%5==0 and 1 or random()
   local kind=id%3==0 and 'PLAYER_SWARM' or 'RELEASED_VIRUS'
   Old.Collect(a,source,kind,strength,acceptedA);New.Collect(b,source,kind,strength,acceptedB)
  end
 end
 Old.Commit(a,acceptedA,frame*.05);New.Commit(b,acceptedB,frame*.05)
 local old,new=dump(a),dump(b)
 assert(old==new,'contact record/anchor drift at frame '..frame)
 stream[#stream+1]=new
end
return table.concat(stream,'\n')
'''


def runtime(baseline=False):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.globals().print = lambda *a: None
    lua.execute("package.path='scripts/?.lua;'..package.path")
    if baseline:
        # Compare only the performance algorithms against old versions. Current
        # gameplay, staged population, roles and registered entries stay equal.
        for name, method in [('FlatMapLayout','FlowAt'), ('FlatWorldMap','Move'), ('CellContacts',None)]:
            lua.globals().oldSource=(FOLDER/'baseline/scripts/Core'/(name+'.lua')).as_posix()
            lua.globals().oldModule=lua.execute("return assert(loadfile(oldSource))()")
            if method:
                lua.execute("require('Core."+name+"')."+method+"=oldModule."+method)
            else:
                lua.execute("package.loaded['Core."+name+"']=oldModule")
    return lua


def percentile(values, q):
    return sorted(values)[max(0, math.ceil(len(values)*q)-1)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--steps', type=int, default=30)
    parser.add_argument('--geometry-only', action='store_true')
    parser.add_argument('--benchmark-only', action='store_true')
    args = parser.parse_args()
    assert args.steps >= 10
    FOLDER.mkdir(parents=True, exist_ok=True)
    lua = runtime()
    lua.globals().BASELINE = (FOLDER/'baseline/scripts').as_posix()
    lua.execute(SERIALIZER)
    contact_state = lua.execute(CONTACTS)
    contact_result = dict(passed=True,frames=360,max_contacts=1200,
        state_sha256=hashlib.sha256(contact_state.encode()).hexdigest())
    (FOLDER/'contact-equivalence.json').write_text(json.dumps(contact_result,indent=2)+'\n',encoding='utf-8')
    print('PASS exact dense contact histories', contact_result,flush=True)
    geometry = []
    for seed in ([] if args.benchmark_only else [314159, 271828, 161803]):
        lua = runtime()
        lua.globals().SEED = seed
        lua.globals().BASELINE = (FOLDER/'baseline/scripts').as_posix()
        data = plain(lua.execute(GEOMETRY))
        geometry.append(data)
        print('PASS exact geometry', data, flush=True)
    if geometry:
        (FOLDER/'geometry.json').write_text(json.dumps(dict(passed=True, results=geometry), indent=2)+'\n', encoding='utf-8')
    if args.geometry_only:
        return 0
    # Alternate old/new per scenario; state bytes and RNG must agree exactly.
    runtimes = {label: runtime(label == 'baseline') for label in ['baseline', 'optimized']}
    for lua in runtimes.values():
        lua.execute(SERIALIZER+BENCH_SETUP)
    results = []
    for count, dense in [(300, False), (1000, False), (3000, False), (6000, False), (3000, True)]:
        row = dict(count=count, distribution='clustered' if dense else '30_sources')
        states = {}
        for label, lua in runtimes.items():
            world = lua.globals().burst(count, dense)
            row['immunes']=len(world.immunes)
            update = world.Update
            cold_start = time.perf_counter()
            update(world, 1/60)
            cold = (time.perf_counter()-cold_start)*1000
            for _ in range(3):
                update(world, 1/60)
            values = []
            cpu_start = time.process_time()
            for _ in range(args.steps):
                started = time.perf_counter()
                update(world, 1/60)
                values.append((time.perf_counter()-started)*1000)
            cpu_per_step = (time.process_time()-cpu_start)*1000/args.steps
            states[label] = lua.globals().snapshot(world)
            row[label] = dict(median_ms=percentile(values,.5),p95_ms=percentile(values,.95),
                max_ms=max(values),cold_step_ms=cold,steps=args.steps,
                cpu_mean_ms=cpu_per_step,
                state_sha256=hashlib.sha256(states[label].encode()).hexdigest(),
                final_released=len(world.releasedViruses))
        row['exact_state_equal'] = states['baseline'] == states['optimized']
        row['median_reduction_pct'] = 100*(1-row['optimized']['median_ms']/row['baseline']['median_ms'])
        results.append(row)
        (FOLDER/'benchmark.json').write_text(json.dumps(dict(passed=all(r['exact_state_equal'] for r in results),
            results=results,scope='Production v5 Lua World.Update with 20 immunes; explicit bursts; geometry setup excluded. No native/GPU FPS claim.'),indent=2)+'\n', encoding='utf-8')
        print(json.dumps(row), flush=True)
        assert row['exact_state_equal'], 'full world/visual snapshot drift'
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
