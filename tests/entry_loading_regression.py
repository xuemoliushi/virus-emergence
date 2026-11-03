"""Real 960-cell map equality and cooperative startup CPU slices (no engine)."""
from pathlib import Path
import json
import time
from lua_test_runtime import LuaRuntime

ROOT=Path(__file__).resolve().parents[1]
lua=LuaRuntime(unpack_returned_tuples=True)
lua.execute("package.path="+repr((ROOT/'scripts/?.lua').as_posix())+"..';'..package.path")
lua.execute('''
local Job=require('Core.LoadJob')
local Map=require('Core.FlatWorldMap')
local cfg=require('Core.FlatMapConfig')
local reference=Map.New(cfg,'UPPER_AIRWAY')
REFERENCE=reference:Snapshot()
job=Job.New(function() loaded=Map.New(cfg,'UPPER_AIRWAY') end)
''')
durations=[]
while not lua.globals().job.done:
    start=time.perf_counter()
    lua.execute('job:Step()')
    durations.append((time.perf_counter()-start)*1000)
    assert not lua.globals().job.error,lua.globals().job.error
    assert len(durations)<10000
lua.execute('''
assert(loaded:Snapshot()==REFERENCE,'yielding changed the seeded map')
assert(#loaded.cells==960)
-- A different coroutine cannot accidentally inherit a startup job's deadline.
local Job=require('Core.LoadJob')
local other=coroutine.create(function() for _=1,100 do Job.Checkpoint() end end)
assert(coroutine.resume(other) and coroutine.status(other)=='dead')
local failed=Job.New(function() error('expected failure') end)
failed:Step();failed:Step();assert(failed.done and failed.error:find('expected failure'))
''')
assert len(durations)>10, 'generation did not yield'
ordered=sorted(durations)
report={'passed':True,'cells':960,'slices':len(durations),
        'max_slice_ms':max(durations),'p95_slice_ms':ordered[int(.95*(len(ordered)-1))],
        'sum_cpu_ms':sum(durations),'seeded_map_identical':True,
        'scope':'Host Lua CPU slices, excludes engine asset upload, rendering and browser scheduling'}
out=ROOT/'validation/menu-entry-audio-20261018';out.mkdir(parents=True,exist_ok=True)
(out/'loading-checks.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
