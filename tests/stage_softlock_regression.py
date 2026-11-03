"""Finite-target and lost-node boundaries through real Lua state and card commits.

Cells are deliberately infected/killed with the production methods to construct
late-game boundaries. This is logic acceptance, not a natural-play balance test.
"""
from evolution_regression import ROOT, SETUP, GROWTH_SETUP, EXTRA, LuaRuntime
import argparse
import json

PRODUCTION = r'''
cfg.mapGenerationVersion=5;cfg.width=120;cfg.height=144;cfg.cellCount=960;cfg.mapSeed=PRODUCTION_SEED
function newSim(start,quiet)
 if quiet then noImmune() end
 local s=Sim.New();assert(s:StartRun(start or 'UPPER_AIRWAY',true))
 assert(s.world.map.isFlatMap and #s.world.cells==960 and s.world.mapSeed==PRODUCTION_SEED)
 return s
end
'''

HELPERS = r'''
local function depleted(keep)
 local s=newSim('UPPER_AIRWAY',true);local w=s.world
 for i,c in ipairs(w.cells) do
  if i>keep then w:_Infect(c,'fixture');w:KillCell(c,'tcell') end
 end
 s:ConsumeEvents()
 return s,w
end
'''

CASES = {
    'stage 1 redirects after pre-release death and settles when no targets remain': r'''
local s=newSim('UPPER_AIRWAY',true);local w=s.world
local c=infectRegion(w,1,1)[1];w:KillCell(c,'tcell');s:ConsumeEvents();s:UpdateTasks(false)
assert(not s.task.complete and s.task.hint:find('重新感染'),'dead node must not remain a wait target')
for _,c in ipairs(w.cells) do if c.state=='HEALTHY' then w:_Infect(c,'fixture');w:KillCell(c,'tcell') end end
s:ConsumeEvents();s:UpdateTasks()
assert(s.task.complete and s.cards.pending and w.stats.totalReleased==0)
''',
    'stage 2 recovery with zero or one healthy cell left can still finish': r'''
for remaining=0,1 do
 local s,w=depleted(remaining+1)
 local c=w.cells[remaining+1];w:_Infect(c,'fixture');w:_Release(c,1)
 s:ConsumeEvents();s.evolution:Enter(2,w.time,w)
 local v=w.releasedViruses[1];v.x,v.y=w.player.x,w.player.y
 assert(s:AbsorbNearby()>0);s:ConsumeEvents();s:UpdateTasks()
 assert(s.evolution.recoveryDone and s.task.target==remaining)
 if remaining==1 then
  assert(not s.cards.pending);w:_Infect(w.cells[1],'fixture');s:ConsumeEvents();s:UpdateTasks()
 end
 assert(s.cards.pending)
end
''',
    'stage 3 does not demand three producers when only two cells can produce': r'''
local s,w=depleted(2)
s.evolution:Enter(3,w.time,w);s:UpdateTasks(false)
assert(s.task.target==2 and not s.task.complete)
for i=1,2 do w:_Infect(w.cells[i],'fixture') end
age(w,cfg.latentSeconds);s:ConsumeEvents();s:UpdateTasks()
assert(w:Counts().productive==2 and s.task.complete and s.cards.pending)
''',
    'stage 3 settles when old producers exist but no new cell remains': r'''
local s,w=depleted(2)
for i=1,2 do w:_Infect(w.cells[i],'fixture') end
age(w,cfg.latentSeconds);s:ConsumeEvents()
s.evolution:Enter(3,w.time,w);s:UpdateTasks()
assert(s.task.target==0 and s.task.complete and s.cards.pending)
''',
    'stages 4 5 6 keep earned infections and cap the goal to remaining cells': r'''
for stage=4,6 do
 local s,w=depleted(2);s.evolution:Enter(stage,w.time,w);s:UpdateTasks(false)
 assert(s.task.target==2 and not s.task.complete)
 for i=1,2 do w:_Infect(w.cells[i],'fixture');w:KillCell(w.cells[i],'tcell') end
 s:ConsumeEvents();s:UpdateTasks()
 assert(s.task.complete and s.task.progress==2 and s.cards.pending)
 local id=s.cards.pending.id;s:UpdateTasks();assert(s.cards.pending.id==id)
end
''',
    'final expansion uses remaining targets and still requires pathology': r'''
local s,w=depleted(2);s.evolution:Enter(6,w.time,w);s.evolution:BeginFinal(w);s.formalFinished=true
s:UpdateTasks(false);assert(s.task.target==2 and not s.task.complete)
for i=1,2 do w:_Infect(w.cells[i],'fixture');w:KillCell(w.cells[i],'tcell') end
s:ConsumeEvents();s:CheckOutcome(0);assert(not s.ending)
s.globalTissueDamage=cfg.irreversibleDamage;s:CheckOutcome(0)
assert(s.ending=='victory' and not s.cards.pending)
''',
    'fully depleted map advances exactly six card rounds without faking infections': r'''
local s,w=depleted(0);local total=w.stats.totalInfected
for stage=1,6 do
 s:UpdateTasks();assert(s.stage==stage and s.cards.pending,'stranded at stage '..stage)
 choose(s);assert(s.cards.formalCount==stage)
end
assert(s.formalFinished and not s.cards.pending and not s.ending and w.stats.totalInfected==total)
s:CheckOutcome(0);assert(not s.ending,'no auto victory before pathology')
s.globalTissueDamage=cfg.irreversibleDamage;s:CheckOutcome(0)
assert(s.ending=='victory' and s.cards.formalCount==6)
''',
}

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--production-seed',type=int)
    parser.add_argument('--output',type=str)
    args=parser.parse_args()
    failed = 0
    rows=[]
    for name, code in CASES.items():
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute('package.path=' + repr((ROOT/'scripts/?.lua').as_posix()) + "..';'..package.path")
        lua.globals().print = lambda *args: None
        lua.globals().PRODUCTION_SEED=args.production_seed
        try:
            lua.execute(SETUP+GROWTH_SETUP+EXTRA+(PRODUCTION if args.production_seed else '')+HELPERS+code)
            rows.append(dict(name=name,passed=True))
            print('PASS:', name,flush=True)
        except Exception as error:
            failed += 1
            rows.append(dict(name=name,passed=False,error=str(error)))
            print('FAIL:', name, error,flush=True)
    if args.output:
        from pathlib import Path
        p=Path(args.output);p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(dict(passed=not failed,production_seed=args.production_seed,cells=960 if args.production_seed else 72,
            results=rows,scope='Real Lua game modules; authored infection/death fixtures, not natural player or native-window acceptance.'),ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'{len(CASES)-failed}/{len(CASES)} softlock boundary checks passed')
    raise SystemExit(bool(failed))
