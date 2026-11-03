"""Real Lua simulation equivalence and timings; no GPU/mobile FPS claims.

Run with -B. --baseline points at a pre-edit scripts copy, or an exported Git
revision. Timing excludes fixture setup and state serialization.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import time

from lua_test_runtime import LuaRuntime
from swarm_regression import SETUP

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = r'''
print=function()end
function fixture(count,dense,immune)
 local w
 if immune then w=World.New('DEEP_LUNG');w.activeImmuneAlertLevel=2
 else w=quietWorld() end
 local c=w.cells[1]
 w:_Release(c,count)
 for _,v in ipairs(w.releasedViruses) do
  local x,y=c.x,c.y
  if not dense then
   repeat x=w:_Random()*w.width;y=w:_Random()*w.height until w.map:Contains(x,y,v.radius)
  end
  v.x,v.y,v._oldX,v._oldY=x,y,x,y
 end
 w.events={}
 return w
end
function dump(value)
 if type(value)=='number' then return string.format('%.17g',value) end
 if type(value)~='table' then return type(value)..':'..tostring(value) end
 local keys={}
 for key in pairs(value) do keys[#keys+1]=key end
 table.sort(keys,function(a,b)return type(a)..tostring(a)<type(b)..tostring(b)end)
 local parts={}
 for _,key in ipairs(keys)do parts[#parts+1]=dump(key)..'='..dump(value[key]) end
 return '{'..table.concat(parts,',')..'}'
end
function snapshot(w)
 local result={}
 for _,key in ipairs({'time','_rng','cells','swarms','viruses','releasedViruses','immunes',
 'stats','events','effects','massLedger','immuneReservations','globalInflammation','globalTissueDamage'})do
  result[key]=w[key]
 end
 return dump(result)
end
'''

def runtime(scripts):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.globals().SOURCE_PATH = str(scripts / '?.lua').replace('\\', '/')
    lua.execute("package.path=SOURCE_PATH..';'..package.path")
    lua.execute(SETUP + FIXTURE)
    return lua

def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]

def measure(scripts, count, dense, immune, steps):
    lua = runtime(scripts)
    world = lua.globals().fixture(count, dense, immune)
    update = world.Update
    timings = []
    for _ in range(steps):
        start = time.perf_counter()
        update(world, 1/60)
        timings.append((time.perf_counter() - start) * 1000)
    transient_memory=lua.eval('collectgarbage("count")')
    lua.execute('collectgarbage("collect")')
    memory = lua.eval('collectgarbage("count")')
    state = lua.globals().snapshot(world)
    result = dict(count=count, distribution='dense' if dense else 'uniform', immune=immune,
                  steps=steps, median_ms=percentile(timings, .5), p95_ms=percentile(timings, .95),
                  p99_ms=percentile(timings, .99), max_ms=max(timings),
                  over_50ms=sum(v>50 for v in timings), over_100ms=sum(v>100 for v in timings),
                  lua_heap_kib=memory, lua_heap_before_gc_kib=transient_memory,
                  state_sha256=hashlib.sha256(state.encode()).hexdigest())
    return result, state


def draw_measure(scripts, count, dense, immune, frames):
    # Actual CellView/attachment/budding code, mocked engine and surface bridge.
    # This measures Lua draw preparation, not atlas decode/upload, GPU or FPS.
    from cell_render_regression import SETUP as DRAW_SETUP
    lua = runtime(scripts)
    lua.globals().SCRIPT_PATH = str(scripts/'?.lua').replace('\\', '/')
    lua.execute(DRAW_SETUP)
    lua.execute("nvgLineCap=function()end;nvgLineJoin=function()end;nvgPathWinding=function()end;"
                "nvgRadialGradient=function()return {}end;nvgLinearGradient=function()return {}end;NVG_ROUND=1;NVG_HOLE=2")
    world = lua.globals().fixture(count, dense, immune)
    world.Update(world, 1/60)
    before = lua.globals().snapshot(world)
    lua.globals().DRAW_WORLD = world
    lua.globals().DRAW_DENSE = dense
    lua.execute("drawView=View.New();drawView:SetCamera(DRAW_DENSE and DRAW_WORLD.cells[1] or "
                "{x=DRAW_WORLD.width*.5,y=DRAW_WORLD.height*.5});"
                "drawContext={sim={world=DRAW_WORLD},zoom=DRAW_DENSE and 1 or .2};drawNvg={};"
                "function drawFrame()calls={};drawView:DrawWorld(drawNvg,0,0,1920,1080,drawContext)end")
    draw = lua.globals().drawFrame
    draw()  # warm view caches, excludes initial preparation
    timings = []
    for _ in range(frames):
        start = time.perf_counter()
        draw()
        timings.append((time.perf_counter()-start)*1000)
    assert before == lua.globals().snapshot(world), 'draw mutated authoritative/visual state'
    transient_memory=lua.eval('collectgarbage("count")')
    lua.execute('collectgarbage("collect")')
    return dict(scope='warm Lua drawing with native/surface mocks; excludes GPU/upload',
                viewport='dense: cell centre at zoom 1; uniform: full map at zoom .2',
                frames=frames, median_ms=percentile(timings,.5),p95_ms=percentile(timings,.95),
                p99_ms=percentile(timings,.99),max_ms=max(timings),
                over_50ms=sum(v>50 for v in timings),over_100ms=sum(v>100 for v in timings),
                lua_heap_kib=lua.eval('collectgarbage("count")'),lua_heap_before_gc_kib=transient_memory)


def equivalence_cases(baseline):
    scenarios = {
        'same-step immune rupture, later detection and exposure': r'''
local w=World.New('DEEP_LUNG');local A=require('Core.AbilityRuntime')
for _,card in ipairs(Config.Cards.definitions)do if card.id=='rupture_spread' then A.Acquire(w,card)end end
local c=unitCell(w,1,w.player.x-1,w.player.y)
c.state='PRODUCTIVE';c.releaseCount=2;c.productiveTimer=cfg.releaseInterval*.9
c.pendingProductionElapsed=c.productiveTimer;c.immuneHits=cfg.immuneNodeHits-1
local neighbour=unitCell(w,2,c.x-.35,c.y);w.cells={c,neighbour}
local killer=w.immunes[2];local follower=w.immunes[1];w.immunes={killer,follower}
killer.x,killer.y=c.x,c.y;killer.state='attack';killer.targetType='cell';killer.targetId=c.id
killer.attackTimer=1/60;killer.cooldown=0
follower.x,follower.y=c.x,c.y;follower.state='patrol';follower.cooldown=0
follower.targetId=nil;follower.targetType=nil;follower.regionId=c.regionId
w:Update(1/60)
assert(c.state=='DEAD' and #w.releasedViruses>0,c.state..'/'..#w.releasedViruses..' killer='..killer.state..' hits='..c.immuneHits)
assert(follower.targetType=='virus','later immune sees newly born rupture viruses')
assert(neighbour._releasedCharge>0,'same-step contact sees rupture viruses')
for _=1,180 do w:Update(1/60)end
return snapshot(w)
''',
        '600-step releases, absorption, split and merge': r'''
local w=quietWorld();local c=unitCell(w)
c.state='LATENT';c.latencyTimer=cfg.latentSeconds-.5
w:SetMovement(1,0)
for i=1,600 do
 if i==2 then w:Split() end
 if i==60 then w:SetMovement(0,0) end
 if i==180 then w:AbsorbNearby() end
 w:Update(1/60)
end
return snapshot(w)
''',
        'map boundaries and convex paths (4000 samples)': r'''
local w=quietWorld();local result={}
for i=1,4000 do
 local x,y=w:_Random()*w.width,w:_Random()*w.height
 local tx,ty=x+(w:_Random()-.5)*10,y+(w:_Random()-.5)*10
 local radius=(i%4)*.1
 local nx,ny=w.map:Move(x,y,tx,ty,radius)
 result[#result+1]={w.map:Contains(x,y,radius),nx,ny,w:_DirectPathClear(x,y,tx,ty,radius)}
end
return dump(result)
''',
    }
    for name, code in scenarios.items():
        new=runtime(ROOT/'scripts').execute(code)
        if baseline:
            assert runtime(baseline).execute(code)==new, 'baseline mismatch: '+name
        print('PASS '+('baseline equivalence: ' if baseline else '')+name, flush=True)

def regressions():
    lua = runtime(ROOT / 'scripts')
    lua.execute(r'''
local Grid=require('Core.SpatialGrid')
local g=Grid.New(1.5)
local items={{id=7,x=-.01,y=0,radius=.1},{id=2,x=1.5,y=1.5,radius=.3},
 {id=9,x=1.49,y=1.49,radius=.2},{id=1,x=9,y=9,radius=.1}}
g:Build(items)
local q=g:Query(1.5,1.5,1.51)
assert(#q==3 and q[1]==items[1] and q[2]==items[2] and q[3]==items[3])
items[2].x=9;items[2].y=9;g:Build(items)
assert(#g:Query(1.5,1.5,.01)==1,'rebuild removes old bucket membership')
g:Build({});assert(#g:Query(0,0,100)==0)

local s=newSim('UPPER_AIRWAY',true)
for _,dt in ipairs({.1,.25,.101,.249})do
 local before=s.tickCount;s:Update(dt)
 assert(s.tickCount-before==2 and s.tickAccum<cfg.movementStep)
end
local before=s.tickCount;s:Update(1/60);assert(s.tickCount-before==1)
assert(s.droppedSimulationSeconds>0)
s:SetPaused('focus',true);assert(s.tickAccum==0)
s:Update(.25);assert(s.tickCount==before+1)
s:SetPaused('observation',true);s:SetPaused('focus',false);assert(s.paused)
s:SetPaused('observation',false);s:Update(1/60);assert(s.tickCount==before+2)
s:init();assert(s.tickAccum==0 and s.droppedSimulationSeconds==0)
assert(s:StartRun('DEEP_LUNG'));assert(s.tickAccum==0 and s.droppedSimulationSeconds==0)
local w=s.world;local a=w:GetCountsSnapshot();assert(a==w:GetCountsSnapshot())
w:_Release(w.cells[1],3);local b=w:GetCountsSnapshot();assert(b~=a and b.released==a.released+3)
w:KillReleased(w.releasedViruses[1]);assert(w:GetCountsSnapshot().released==b.released-1)
local keep=w.releasedViruses[2];w.releasedViruses[3].age=w.releasedViruses[3].lifetime
w:Update(1/60);assert(#w.releasedViruses==1 and w.releasedViruses[1]==keep)

local Director=require('Core.ImmuneDirector')
w.activeImmuneAlertLevel=2;w.virusDensityGroups['0:0']={}
for i=1,100 do w.virusDensityGroups['0:0'][i]={state='DRIFTING'} end
local checks=0;local memo={};local target={x=0,y=0}
local function visible() checks=checks+1;return true end
assert(Director.VisibleDensity(w,{},target,visible,memo)==8*Config.ImmuneAlert.densityWeight)
assert(checks==8);Director.VisibleDensity(w,{},target,visible,memo);assert(checks==8)

local Perf=require('Core.PerformanceStats')
assert(not Perf.Snapshot().enabled and Perf.Begin()==nil)
Perf.SetEnabled(true);Config.Performance.timingWindow=3
for _,ms in ipairs({10,60,110,20})do Perf.Sample('frame',ms)end
local stat=Perf.Snapshot().metrics.frame
assert(stat.sampleCount==3 and stat.totalCount==4 and stat.p99Ms==110 and stat.over50ms==2 and stat.over100ms==1)
Perf.Sample('frame',0/0);assert(Perf.Snapshot().metrics.frame.totalCount==4)
Perf.Reset();assert(not next(Perf.Snapshot().metrics));Perf.SetEnabled(false)
''')
    print('PASS spatial boundaries, stable order, bounded catch-up, pause/restart, snapshots, compaction, density memo')
    from cell_atlas_async_regression import SETUP as SURFACE_SETUP
    surface_lua = LuaRuntime(unpack_returned_tuples=True)
    surface_lua.globals().SCRIPT_PATH = str(ROOT/'scripts'/'?.lua').replace('\\', '/')
    surface_lua.execute(SURFACE_SETUP)
    surface_lua.execute(r'''
local s=newSurface();local ctx={};s.Bind=function(self,nvg)self.nvg=nvg;return true end
local nextHandle=0;local deleted={}
function Image()return {SetSize=function()return true end,ClearInt=function()end,Dispose=function()end}end
function Texture2D()return {SetNumLevels=function()end,SetFilterMode=function()end,
 SetData=function()return true end,Dispose=function(self)self.disposed=true end}end
function nvgCreateVideo()nextHandle=nextHandle+1;return nextHandle end
function nvgDeleteVideo(_,handle)deleted[handle]=true end
local function get(key)return s:Texture(ctx,key,16,16,function()end,0,0,16,0)end
s:BeginFrame();assert(get('a') and get('b'));assert(not get('c') and not get('d'))
assert(nextHandle==2)
s:BeginFrame();assert(get('a'));assert(not get('d'),'queued c goes first')
assert(get('c') and get('d') and nextHandle==4)
-- Full cache, a is pinned this frame; eviction must skip it.
s.maxResources=4;s:BeginFrame();local a=get('a');assert(get('e'))
assert(not deleted[a.handle] and s.entries.a==a)
-- When every resident is pinned, wait for a later frame rather than delete one.
s:BeginFrame();for key in pairs(s.entries)do assert(get(key))end
local before=nextHandle;assert(not get('f') and nextHandle==before)
s:BeginFrame();assert(get('f') and nextHandle==before+1)
s:Destroy();assert(not next(s.pendingTextures) and #s.textureQueue==0 and s.framePins==nil)
s:BeginFrame();assert(not s.destroyed and s.frameCreated==0)
s:Destroy()
''')
    print('PASS texture creation budget, fair retry, in-frame pins, full-cache wait, reset lifecycle')
    from bird_ui_regression import runtime as hud_runtime
    hud_lua = hud_runtime()
    hud_lua.execute(r'''
local h,game,s,manager,observation=hudFixture()
guidedStart(h,s,manager,observation,'DEEP_LUNG')
if package.loaded['UI.SkillControls'] then
 s.skillMenu={page='main',runId=s.cards.runId,controlId=s.world.currentControlledSwarmId}
 h:Update(.12)
end
local texts,full,fast=0,0,0
local set=h.SetText;h.SetText=function(self,...)texts=texts+1;return set(self,...)end
local refresh=h.RefreshStrategyHighlight
h.RefreshStrategyHighlight=function(self,quick)
 if quick then fast=fast+1 else full=full+1 end;return refresh(self,quick)
end
h.refreshAccum_=0
for _=1,6 do h:Update(1/60)end
assert(full==0 and fast==6 and texts==0,'text updates wait for .12-second cadence')
h:Update(1/60);h:Update(1/60);assert(full==1 and texts>0)
s:SetPaused('focus',true);h:Update(1/60)
assert(not s:CanAct() and h.strategyButtons_.split:IsDisabled()
 and h.strategyButtons_.absorb:IsDisabled() and h.strategyButtons_.switch:IsDisabled())
''')
    print('PASS HUD text cadence and immediate pause availability')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--steps', type=int, default=60)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    regressions()
    equivalence_cases(args.baseline)
    results = []
    if args.baseline:
        for immune in (False, True):
            for count in (30, 300, 1000, 3000):
                for dense in (False, True):
                    old, old_state = measure(args.baseline, count, dense, immune, args.steps)
                    new, new_state = measure(ROOT/'scripts', count, dense, immune, args.steps)
                    assert old_state == new_state, f'business/visual state mismatch: {count}, {dense}, {immune}'
                    old['draw_mock']=draw_measure(args.baseline,count,dense,immune,args.steps)
                    new['draw_mock']=draw_measure(ROOT/'scripts',count,dense,immune,args.steps)
                    result = dict(baseline=old, optimized=new, state_equivalent=True,
                                  median_reduction_pct=100*(1-new['median_ms']/old['median_ms']))
                    results.append(result)
                    print(json.dumps(result, ensure_ascii=False), flush=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(dict(kind='Lua CPU simulation; excludes native drawing/GPU',
            results=results), ensure_ascii=False, indent=2), encoding='utf-8')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
