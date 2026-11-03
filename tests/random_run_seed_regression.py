"""Default production runs randomize maps; explicit seeds remain reproducible."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.tmp/test-deps'))
from lua_test_runtime import LuaRuntime

lua = LuaRuntime(unpack_returned_tuples=True)
lua.globals().SCRIPT_PATH = (ROOT / 'scripts/?.lua').as_posix()
seeds = lua.execute(r'''
package.path=SCRIPT_PATH..';'..package.path
print=function() end
local Config=require('Core.Config')
local Sim=require('Core.SimState')
local Map=require('Core.RespiratoryMap')
local Random=require('Core.MapRandom')
assert(Config.Gameplay.mapSeed==nil,'normal play must not pin a debug map seed')

-- Two presses in the same clock tick must still produce different seeds.
local wall,cpu=os.time,os.clock
os.time=function() return 1792460000 end;os.clock=function() return 0 end
local a,b=Random.NewSeed(),Random.NewSeed()
os.time,os.clock=wall,cpu
assert(a~=b and a>=1 and b<=2147483646)

math.randomseed(456);local expected={math.random(),math.random()}
math.randomseed(456);assert(math.random()==expected[1])
local sim=Sim.New()
local prepared=sim.world
assert(sim:StartRun('UPPER_AIRWAY',true) and sim.world==prepared)
assert(math.random()==expected[2],'map creation must not consume global RNG')
local seed=sim.world.mapSeed
local snapshot=sim.world.map:Snapshot()
for _=1,10 do sim:Update(1/60) end
assert(sim.world.mapSeed==seed and sim.world.map.seed==seed and sim.world.map:Snapshot()==snapshot)

assert(sim:StartRun('UPPER_AIRWAY',true))
local second=sim.world.mapSeed
assert(second~=seed and sim.world.map:Snapshot()~=snapshot,'new run must change the actual map')
sim:init();local restarted=sim.world
assert(sim:StartRun('UPPER_AIRWAY',true) and sim.world==restarted)
local third=sim.world.mapSeed
assert(third~=seed and third~=second and Config.Gameplay.mapSeed==nil)

-- Copying the displayed seed back into an explicit config reproduces the map.
local cfg={};for k,v in pairs(Config.Gameplay) do cfg[k]=v end
cfg.mapSeed=seed
assert(Map.New(cfg):Snapshot()==snapshot)
cfg.mapSeed=314159
local fixed=Map.New(cfg)
assert(fixed.seed==314159 and Map.New(cfg):Snapshot()==fixed:Snapshot())
return {seed,second,third}
''')
print('PASS: default start, subsequent start and restart use distinct maps:', list(seeds.values()))
print('PASS: same-run seed stability, same-tick uniqueness, explicit seed replay and global RNG isolation')
