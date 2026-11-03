"""Contact/geometry/stage assays against real Lua modules; no native acceptance."""
from pathlib import Path
import json
import hashlib
import sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.tmp/test-deps'))
from swarm_regression import ROOT, SETUP, LuaRuntime
from swarm_growth_regression import GROWTH_SETUP

COMMON = r'''
Director=require('Core.ImmuneDirector')
Navigation=require('Core.ImmuneNavigation')
function tick(w,seconds)
 for _=1,math.floor(seconds/cfg.movementStep+.5) do
  w.time=w.time+cfg.movementStep;Immune.Update(w,cfg.movementStep)
 end
end
function extra(w,kind,x,y)
 local base=w.immunes[1];local im={}
 for k,v in pairs(base) do if type(v)~='table' then im[k]=v end end
 im.id=100+#w.immunes;im.kind=kind;im.x,im.y=x,y
 im.state,im.stateTimer='patrol',0;im.targetId,im.targetType=nil,nil
 im._patrolX,im._patrolY=x,y;im._patrolTimer=0;im.processingLoad=0
 im.regionId=w.map:RegionAt(x,y);w.immunes[#w.immunes+1]=im
 return im
end
function clearFixture(kind,level)
 local w,im=immuneFixture(kind);w.activeImmuneAlertLevel=level or 0
 w.cells={};place(w,w.player,13,3.1)
 im.x,im.y=13,27.5;im._patrolX,im._patrolY=im.x,im.y
 im.regionId=w.map:RegionAt(im.x,im.y)
 return w,im
end
function nodeFixture(level)
 local w,t=immuneFixture('tcell');w.activeImmuneAlertLevel=level or 3
 local c=unitCell(w,1,13,27.5);w.cells={c}
 place(w,w.player,13,3.1)
 t.x,t.y=c.x-c.radius-t.radius+.01,c.y
 t._patrolX,t._patrolY=t.x,t.y;t.regionId=c.regionId
 return w,t,c
end
function untilState(w,im,state)
 for _=1,1200 do if im.state==state then return end;tick(w,cfg.movementStep) end
 error('missing state '..state..': '..im.state)
end
function reset(w,im)
 Director.Release(w,im);im.targetId,im.targetType,im.targetX,im.targetY=nil,nil,nil,nil
 im.state,im.cooldown,im.stateTimer='patrol',0,0;im.recognized=false;im._patrolTimer=0
end
'''

TESTS = {
    'load selects affordable work and preserves real capacity': r'''
local w,m=immuneFixture('macrophage');local c=unitCell(w,1,13,27.5)
w.cells={c};w:_Release(c,1);w:KillCell(c,'fixture');place(w,w.player,13,3.1)
m.x,m.y=12,27.5;m.processingLoad=6.1
local v=w.releasedViruses[1];v.x,v.y=12.5,27.5
tick(w,cfg.movementStep)
assert(m.targetType=='virus' and m.targetId==v.id,'unaffordable debris must be skipped')
assert(m.processingLoad<=cfg.immuneBehavior.loadCapacity)
''',
    'stage II density attracts empty macrophage; loaded one selects small cluster': r'''
for _,load in ipairs({0,4.5}) do
 local w,m=immuneFixture('macrophage');local c=unitCell(w);w.cells={c};place(w,w.player,13,3.1)
 m.x,m.y=13,27.5;m._patrolX,m._patrolY=m.x,m.y;m.processingLoad=load;w.activeImmuneAlertLevel=2
 w:_Release(c,6)
 for i,v in ipairs(w.releasedViruses) do v.x,v.y=i==6 and 12 or 14,27.5 end
 tick(w,cfg.movementStep)
 assert(m.targetType=='virus')
 assert((m.targetId==w.releasedViruses[6].id)==(load>0),'load must reverse dense-cluster preference')
end
''',
    'mere discovery and old traces do not publish alarms; real encounter does': r'''
local w,m=clearFixture('macrophage',1);place(w,w.player,13,27.5)
tick(w,cfg.movementStep);assert(m.state=='locked' and #w.immuneAlarms==0)
untilState(w,m,'chase');assert(#w.immuneAlarms==0)
tick(w,1.05);assert(#w.immuneAlarms==1 and m.alarmVisibleUntil>w.time)
local a=w.immuneAlarms[1];assert(not a.targetId and not a.targetType and not a.swarmId)
assert(not Director.Alarm(w,m,m.x,m.y),'per-source/location cooldown')
''',
    'successful physical virus clear publishes alarm without extra damage': r'''
local w,m=immuneFixture('macrophage');local c=unitCell(w);w.cells={c}
place(w,w.player,13,3.1);w.activeImmuneAlertLevel=1;cfg.immuneClearChance=1
m.x,m.y=13,27.5;w:_Release(c,1);local v=w.releasedViruses[1];v.x,v.y=m.x,m.y
local killed=w.stats.totalKilled;tick(w,6)
assert(v.state=='CLEARED' and #w.immuneAlarms==1 and w.stats.totalKilled==killed+1)
''',
    'alarm stages, responder budget, busy exclusion and fixed location': r'''
for _,level in ipairs({0,1,4}) do
 local w,m=clearFixture('macrophage',level)
 local a=extra(w,'tcell',12,27.5);local b=extra(w,'tcell',14,27.5)
 local busy=extra(w,'macrophage',13,27.8);busy.processingLoad=6;busy.state='processing'
 local count=#w.immunes;local mass=w:ControlledCount();local infl=w.globalInflammation
 local fired=Director.Alarm(w,m,13,27.5);assert(fired==(level>0))
 tick(w,cfg.movementStep)
 local n=0;for _ in pairs(w.immuneAlarmAssignments) do n=n+1 end
 assert(n==(level==0 and 0 or level==1 and 1 or 2))
 assert(not w.immuneAlarmAssignments[busy.id] and busy.state=='processing')
 assert(#w.immunes==count and w:ControlledCount()==mass and w.globalInflammation==infl)
 if level>0 then
  local p=w.immuneAlarmAssignments[a.id] or w.immuneAlarmAssignments[b.id];assert(p and not p.targetId)
  local x,y=p.x,p.y;m.x=m.x+.3;tick(w,.1);assert(p.x==x and p.y==y)
  w.time=w.time+Config.ImmuneAlert.alarmDuration;Director.Update(w,.01)
  assert(#w.immuneAlarms==0 and not next(w.immuneAlarmAssignments))
 end
end
''',
    'alarm cannot recruit through actual tissue barriers': r'''
local w,m=clearFixture('macrophage',4);local t=extra(w,'tcell',13,27.5)
local found=false
for y=1,w.height-1 do
 if found then break end
 for x=1,w.width-1 do
  if found then break end
  if w.map:Contains(x,y,t.radius) then
   for i=1,48 do
    local a=i*math.pi/24;local tx,ty=x+math.cos(a)*5,y+math.sin(a)*5
    if w.map:Contains(tx,ty,m.radius) and not Navigation.Clear(w.map,{x=x,y=y},{x=tx,y=ty},t.radius) then
     t.x,t.y=x,y;m.x,m.y=tx,ty;found=true;break
    end
   end
  end
 end
end
assert(found,'real barrier fixture');assert(Director.Alarm(w,m,m.x,m.y));Director.Update(w,.01)
assert(not w.immuneAlarmAssignments[t.id])
''',
    'alert activation buffer and downgrade cancel alarm, screening and search': r'''
local w,m=clearFixture('macrophage',0);w:AcquireImmuneAlert()
Director.Update(w,4.9);assert(w.activeImmuneAlertLevel==0 and not Director.Alarm(w,m,m.x,m.y))
Director.Update(w,.1);assert(w.activeImmuneAlertLevel==1 and Director.Alarm(w,m,m.x,m.y))
local t=extra(w,'tcell',12,27.5);Director.Update(w,.01);assert(t.respondingToAlarm)
w:SetDebugImmuneAlertLevel(0);Director.Update(w,5)
assert(#w.immuneAlarms==0 and not t.respondingToAlarm)
''',
    'T screening requires stage III and continuous real contact': r'''
for _,level in ipairs({2,3}) do
 local w,t,c=nodeFixture(level);local killed=w.stats.totalKilled
 tick(w,.1)
 if level==2 then assert(not t._screenCellId and not t._cellChecks)
 else
  assert(t._screenCellId==c.id)
  tick(w,.8);assert(t.screenTimer>.5 and not (t._cellChecks and t._cellChecks[c.id]))
  t.x=t.x-.5;tick(w,cfg.movementStep);assert(t.screenTimer==0)
  t.x=c.x-c.radius-t.radius+.01;tick(w,2.3)
  assert(t._cellChecks[c.id] and not t._cellChecks[c.id].infected and not t._screenCellId)
  assert(c.state=='HEALTHY' and c.immuneHits==0 and w.stats.totalKilled==killed)
  tick(w,.1);assert(not t._screenCellId,'recent safe check should avoid repeat scanning')
 end
end
''',
    'new infection overrides negative check without remote knowledge': r'''
local w,t,c=nodeFixture(3);tick(w,2.5);assert(t._cellChecks[c.id])
w:_Infect(c,'fixture');tick(w,cfg.movementStep)
assert(t.state=='locked' and t.targetId==c.id and t.warningTimer==Director.BehaviorValue(w,'tcellWarningSeconds'))
''',
    'confirmed T memory shortens recheck but preserves warning and windup': r'''
local w,t,c=nodeFixture(3);w:_Infect(c,'fixture')
untilState(w,t,'attack');assert(t._cellChecks[c.id].infected and c.immuneHits==0)
reset(w,t);tick(w,cfg.movementStep);assert(t.state=='locked' and t.warningTimer==Director.BehaviorValue(w,'tcellWarningSeconds'))
untilState(w,t,'investigate');near(t.recognitionRequiredSeconds,Director.BehaviorValue(w,'recheckSeconds'))
tick(w,.9);assert(c.immuneHits==0 and t.state=='investigate')
untilState(w,t,'attack');assert(c.immuneHits==0 and t.attackTimer>=1.1)
tick(w,1.2);assert(c.immuneHits==1)
''',
    'T memory expiry, ownership and target death clear retained evidence': r'''
local w,t,c=nodeFixture(3);w:_Infect(c,'fixture');untilState(w,t,'attack')
local other=extra(w,'tcell',t.x,t.y);assert(not other._cellChecks)
reset(w,t);w.time=w.time+cfg.immuneBehavior.checkMemorySeconds+.1
tick(w,cfg.movementStep);untilState(w,t,'investigate')
near(t.recognitionRequiredSeconds,Director.BehaviorValue(w,'recognitionSeconds'))
untilState(w,t,'attack');w:KillCell(c,'fixture')
assert(not t.targetId and not t.recognized and not t._cellChecks[c.id])
''',
    'T confirmed-node loss searches snapshot at V, expires without damage': r'''
local w,t,c=nodeFixture(5);w:_Infect(c,'fixture');untilState(w,t,'attack')
local x,y=t._lastSeen.x,t._lastSeen.y;local hits=c.immuneHits
t.x,t.y=13,3.1;tick(w,cfg.movementStep)
assert(t.state=='search' and not t.targetId and t._searchX==x and t._searchY==y)
assert(c.immuneHits==hits)
w.time=t._searchUntil+.01;tick(w,cfg.movementStep);assert(t.state=='patrol' and not t.targetId)
''',
    'macrophage search first appears at V and keeps last-seen expiry': r'''
for _,level in ipairs({4,5,6}) do
 local w,m=clearFixture('macrophage',level);place(w,w.player,13,27.5)
 tick(w,cfg.movementStep);local seen=m._lastSeen
 place(w,w.player,13,3.1);tick(w,cfg.movementStep)
 assert((m.state=='search')==(level>=5))
 if level>=5 then assert(m._searchUntil==seen.seenAt+Config.ImmuneAlert.searchMemoryDuration) end
end
''',
}


def main():
    if '--production' in sys.argv:
        from ai_non_runtime_acceptance import plain
        rows = []
        seeds = [int(sys.argv[sys.argv.index('--seed') + 1])] if '--seed' in sys.argv else [314159, 271828, 161803, 314159]
        for seed in seeds:
            lua = LuaRuntime(unpack_returned_tuples=True)
            lua.execute('package.path=' + repr((ROOT / 'scripts/?.lua').as_posix() + ';' + (ROOT / 'tests/?.lua').as_posix()) + "..';'..package.path")
            logs = []
            lua.globals().print = lambda *v: logs.append(' '.join(map(str, v)))
            try:
                suite = lua.execute((ROOT / 'tests/immune_adaptation_scenarios.lua').read_text(encoding='utf-8'))
                result = plain(suite.Run(seed))
                result['state_sha256'] = hashlib.sha256(result.pop('state_signature').encode()).hexdigest()
                row = dict(seed=seed, passed=True, **result)
            except Exception as error:
                row = dict(seed=seed, passed=False, error=str(error), logs=logs[-5:])
            rows.append(row)
            print(f"{'PASS' if row['passed'] else 'FAIL'}: production {seed}", flush=True)
            if not row['passed']:
                print(row['error'], row['logs'], flush=True)
        replay = rows[0].get('state_sha256') == rows[-1].get('state_sha256') and rows[0]['passed'] and rows[-1]['passed']
        output = ROOT / 'validation/immune-ai-20261017'
        output.mkdir(parents=True, exist_ok=True)
        (output / 'stages.json').write_text(json.dumps(dict(passed=all(r['passed'] for r in rows) and replay,
            replay_passed=replay, results=rows,
            scope='Native production geometry and authority infection with explicit actor poses and debug alert transitions; immune-only causal steps. Full World/Sim stress and native player acceptance are separate.'
        ), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return int(not all(r['passed'] for r in rows) or not replay)
    rows = []
    for name, code in TESTS.items():
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute('package.path=' + repr((ROOT / 'scripts/?.lua').as_posix()) + "..';'..package.path")
        logs = []
        lua.globals().print = lambda *v: logs.append(' '.join(map(str, v)))
        try:
            lua.execute(SETUP + GROWTH_SETUP + COMMON + code)
            row = dict(name=name, passed=True)
        except Exception as error:
            row = dict(name=name, passed=False, error=str(error), logs=logs[-5:])
        rows.append(row)
        print(('PASS: ' if row['passed'] else 'FAIL: ') + name, flush=True)
        if not row['passed']:
            print(row['error'], row['logs'], flush=True)
    output = ROOT / 'validation/immune-ai-20261017'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'targeted.json').write_text(json.dumps(dict(
        passed=all(r['passed'] for r in rows), results=rows,
        generated_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
        scope='Explicit actor/contact/level fixtures on historical 26x32 geometry; real Lua Core modules. Native/player balance unverified.'
    ), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"{sum(r['passed'] for r in rows)}/{len(rows)} targeted checks passed.")
    return int(any(not r['passed'] for r in rows))


if __name__ == '__main__':
    raise SystemExit(main())
