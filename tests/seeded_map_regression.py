"""Production version-3 map: canonical snapshots, swept connectivity, RNG isolation.

No mocks for world/update/map. Host timings are CPU Lua 5.4, not GPU/device FPS.
"""
from pathlib import Path
import hashlib
import json
import sys
import time
from lua_test_runtime import LuaRuntime

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'validation/seeded-map'
OUT.mkdir(exist_ok=True,parents=True)

def runtime():
    lua=LuaRuntime(unpack_returned_tuples=True)
    lua.globals().SOURCE_PATH=str(ROOT/'scripts/?.lua').replace('\\','/')
    lua.execute("package.path=SOURCE_PATH..';'..package.path;print=function()end")
    lua.execute("Config=require('Core.Config');Map=require('Core.RespiratoryMap');World=require('Core.SwarmWorld');cfg=Config.Gameplay")
    return lua

lua=runtime()
lua.execute('''
function verify(seed)
 cfg.mapSeed=seed
 local a,b=Map.New(cfg),Map.New(cfg)
 assert(a:Snapshot()==b:Snapshot(),'full canonical snapshot differs')
 local ok,errors=a:Verify();assert(ok,table.concat(errors,';'))
 -- Actual circular swept movement, both routes and every infection target.
 local nav=require('Core.ImmuneNavigation')
 local start=a.startPoints.UPPER_AIRWAY
 for _,r in ipairs(a.regions)do
  local route=assert(nav.Route(a,start,r,1.35),'largest swarm cannot reach region '..r.id)
  local p=start
  for _,q in ipairs(route)do
   local x,y=a:Move(p.x,p.y,q.x,q.y,1.35)
   assert(math.abs(x-q.x)+math.abs(y-q.y)<1e-6,'route segment blocked')
   p=q
  end
 end
 for _,c in ipairs(a.cells)do
  local route=assert(nav.Route(a,start,c,.48),'cell unreachable '..c.id)
  local p=start
  for _,q in ipairs(route)do
   local x,y=a:Move(p.x,p.y,q.x,q.y,.48)
   assert(math.abs(x-q.x)+math.abs(y-q.y)<1e-6,'cell route blocked '..c.id)
   p=q
  end
 end
 return a:Snapshot(),a.generationMs,a.fallbackCount
end
''')
rows=[]
for seed in [314159,1,2,3,17,73,999,20261012,2147483646,'组织探索']:
    start=time.perf_counter()
    snapshot,ms,fallbacks=lua.globals().verify(seed)
    digest=hashlib.sha256(snapshot.encode()).hexdigest()
    rows.append(dict(seed=seed,sha256=digest,generation_ms=ms,fallbacks=fallbacks,
                     verification_ms=(time.perf_counter()-start)*1000))
assert len({x['sha256'] for x in rows})==len(rows)
(OUT/'seed-314159.snapshot.txt').write_text(lua.globals().verify(314159)[0],encoding='utf-8')
lua.execute('''
-- Map generation must consume neither global random nor a running world's RNG.
math.randomseed(73);local expected=math.random()
math.randomseed(73);Map.New(cfg);assert(math.random()==expected)
local w=World.New();local saved=w._rng;local nextValue=w:_Random();w._rng=saved
cfg.mapSeed='isolated';Map.New(cfg);assert(w._rng==saved);assert(w:_Random()==nextValue)
-- Initial player/immune properties stable across full world constructions.
cfg.mapSeed=314159
local a,b=World.New(),World.New()
assert(a._rng==b._rng and #a.immunes==#b.immunes)
for i,p in ipairs(a.viruses)do local q=b.viruses[i]
 assert(p.id==q.id and p.variant==q.variant and p.phase==q.phase and p.x==q.x and p.y==q.y) end
for i,p in ipairs(a.immunes)do local q=b.immunes[i]
 for _,key in ipairs({'id','kind','x','y','radius','variant','phase','regionId'})do assert(p[key]==q[key],key)end end
-- nil chooses exactly once per world; time/update/camera do not change it.
cfg.mapSeed=nil;local automatic=World.New();local seed=automatic.mapSeed
local snapshot=automatic.map:Snapshot()
for _=1,120 do automatic:Update(1/60)end
assert(automatic.mapSeed==seed and automatic.map:Snapshot()==snapshot)
cfg.mapSeed=seed;assert(Map.New(cfg):Snapshot()==snapshot)
-- Direct snapshot must remain immutable while offscreen nodes naturally age/release.
cfg.mapSeed=314159;cfg.immuneMax=0
for _,def in ipairs(Config.StartRegions)do def.immuneCount=0 end
w=World.New();local c=w.cells[9];w:_Infect(c,'player')
local before=w.map:Snapshot()
for _=1,60*50 do w:Update(1/60)end
assert(c.state=='PRODUCTIVE' and w.stats.totalReleased>0)
assert(w.map:Snapshot()==before,'updates regenerated the map')
-- Real player first infection and split/switch/merge, without changing infection formulas.
w=World.New();c=w.cells[1]
local dx,dy=c.x-w.player.x,c.y-w.player.y
local d=math.sqrt(dx*dx+dy*dy)
w:SetMovement(dx/d,dy/d)
for _=1,60*4 do
 w:Update(1/60)
 local dist=math.sqrt((c.x-w.player.x)^2+(c.y-w.player.y)^2)
 if dist<.3 then break end
end
for _=1,60*28 do
 local fx,fy=w.map:FlowAt(w.player.x,w.player.y,w.time)
 local dx,dy=c.x-w.player.x,c.y-w.player.y
 local d=math.sqrt(dx*dx+dy*dy)
 w:SetMovement(dx*4-fx*cfg.playerFlowInfluence,dy*4-fy*cfg.playerFlowInfluence)
 w:Update(1/60)
 if c.state=='LATENT' then break end
end
assert(c.state=='LATENT' and c.infectionSource=='player','normal movement failed to infect')
w:SetMovement(1,0);assert(w:Split());assert(#w.swarms==2);assert(w:SwitchControl())
-- Merge by real movement toward the other group after grace, never teleport.
for i=1,60*30 do
 local p=w.player;local other=w.swarms[1]==p and w.swarms[2] or w.swarms[1]
 if not other then break end
 local dx,dy=other.x-p.x,other.y-p.y;local d=math.sqrt(dx*dx+dy*dy)
 w:SetMovement(dx/math.max(1,d),dy/math.max(1,d));w:Update(1/60)
 if #w.swarms==1 then break end
end
assert(#w.swarms==1 and w.stats.totalMerges>=1,'real groups failed to merge')
''')

result=dict(environment='Windows x64 / Lupa Lua 5.4 / CPU, no rendering',
            map_width=78,map_height=96,regions=5,channels=5,cells=216,seeds=rows,
            checks=['canonical full snapshots','actual swept routes for largest swarm and all cells',
                    'spawn/spacing/bounds','global and simulation RNG isolation','initial world entities',
                    'automatic seed replay','offscreen natural release','natural first infection and split/switch/merge'])
(OUT/'generation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
