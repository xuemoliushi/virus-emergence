"""Six-stage numerical curves through actual contact/state transitions."""
import json
from immune_pressure_regression import ROOT, SETUP, GROWTH_SETUP, COMMON, HELPERS, LuaRuntime

EXPECTED = r'''
WARN={.65,.60,.55,.50,.45,.40}
SPEED={1.90,1.96,2.02,2.08,2.14,2.20}
WINDUP={.15,.15,.14,.13,.12,.12}
CLEAR_INTERVAL={.35,.33,.31,.29,.27,.25}
DIGEST={.50,.55,.62,.70,.78,.85}
SWARM_INTERVAL={1.20,1.18,1.14,1.10,1.05,1.00}
T_WARN={2.8,2.6,2.4,2.2,2.0,1.8}
IDENTIFY={2.2,2.1,2.0,1.8,1.6,1.4}
RECHECK={1.1,1.1,1.1,1.1,.95,.80}
T_INTERVAL={2.8,2.7,2.6,2.4,2.2,2.0}
function completeAttack(w,im)
 tick(w,math.ceil(im.attackTimer/cfg.movementStep-1e-8)*cfg.movementStep)
end
'''
TESTS = {
 'each stage applies actual swarm warning, contact damage and cooldown': r'''
for level=0,6 do
 local w,m=immuneFixture('macrophage');w.activeImmuneAlertLevel=level
 local k=math.min(5,level)+1;local mass=w.player.mass
 tick(w,cfg.movementStep);near(m.warningTime,WARN[k]);near(m.attackWindup,.3)
 untilState(w,m,'attack');assert(w.player.mass==mass)
 tick(w,m.attackWindup);assert(w.player.mass==mass-2);near(m.cooldown,SWARM_INTERVAL[k])
 checkConservation(w)
end
''',
 'each stage applies real chase displacement without changing patrol speed': r'''
for level=0,5 do
 local w,m=clearFixture('macrophage',level);place(w,w.player,16,27.5)
 untilState(w,m,'chase');local x,y=m.x,m.y;tick(w,cfg.movementStep)
 near(math.sqrt((m.x-x)^2+(m.y-y)^2),SPEED[level+1]*cfg.movementStep)
 near(cfg.immuneSpeed,.9)
end
''',
 'all stages retain continuous clear and use approved action and cooldown': r'''
for level=0,5 do
 local w,m=particles(4);w.activeImmuneAlertLevel=level;cfg.immuneClearChance=1
 tick(w,cfg.movementStep);near(m.warningTime,.15);near(m.attackWindup,WINDUP[level+1])
 untilClear(w,m);near(m.cooldown,CLEAR_INTERVAL[level+1]);assert(m.warningTimer==0)
 local killed=w.stats.totalKilled;tick(w,m.cooldown-cfg.movementStep)
 assert(w.stats.totalKilled==killed)
 untilState(w,m,'attack');completeAttack(w,m)
 assert(w.stats.totalKilled==2 and eventCount(w,'immune_warning')==1)
 checkConservation(w)
end
''',
 'digestion actually accelerates at every tier while recovery threshold stays four': r'''
for level=0,5 do
 local w,m=clearFixture('macrophage',level);m.processingLoad=6;m.state='processing'
 tick(w,.5);near(m.processingLoad,6-DIGEST[level+1]*.5);assert(m.state=='processing')
 m.processingLoad=4+DIGEST[level+1]*cfg.movementStep/2;tick(w,cfg.movementStep)
 assert(m.state=='patrol' and m.processingLoad<=4 and not m.targetId)
 near(cfg.immuneBehavior.loadCapacity,8);near(cfg.immuneClearChance,.95)
end
''',
 'T warning recognition and node-hit cadence follow all six tiers': r'''
for level=0,5 do
 local w,t,c=nodeFixture(level);w:_Infect(c,'fixture');tick(w,cfg.movementStep)
 near(t.warningTime,T_WARN[level+1]);near(t.attackWindup,1.1)
 untilState(w,t,'investigate');near(t.recognitionRequiredSeconds,IDENTIFY[level+1])
 tick(w,t.recognitionRequiredSeconds-cfg.movementStep);assert(c.immuneHits==0 and t.state=='investigate')
 untilState(w,t,'attack');assert(c.immuneHits==0);tick(w,t.attackWindup)
 assert(c.immuneHits==1);near(t.cooldown,T_INTERVAL[level+1])
 for _=2,3 do untilState(w,t,'attack');tick(w,t.attackWindup)end
 assert(c.state=='DEAD' and c.immuneHits==3)
 assert(eventCount(w,'node_attack')==3 and cfg.nodeAttackInflammation==2.3 and cfg.nodeAttackDamage==.8)
end
''',
 'confirmed-node rechecks shorten only after memory unlock and retain windup': r'''
for level=0,5 do
 local w,t,c=nodeFixture(level);w:_Infect(c,'fixture');untilState(w,t,'attack')
 reset(w,t);tick(w,cfg.movementStep);untilState(w,t,'investigate')
 near(t.recognitionRequiredSeconds,level>=3 and RECHECK[level+1] or IDENTIFY[level+1])
 untilState(w,t,'attack');near(t.attackTimer,1.1);assert(c.immuneHits==0)
end
''',
 'healthy screening uses the same stage recognition duration': r'''
for level=3,5 do
 local w,t,c=nodeFixture(level);w._channelClock=math.huge -- isolate screening from branch duty
 tick(w,cfg.movementStep)
 near(t.screenRequiredSeconds,IDENTIFY[level+1]);assert(t._screenCellId==c.id)
 tick(w,IDENTIFY[level+1]-cfg.movementStep)
 assert(not t._cellChecks or not t._cellChecks[c.id])
 tick(w,2*cfg.movementStep);assert(t._cellChecks[c.id] and not t._cellChecks[c.id].infected)
end
''',
 'pending alert cannot accelerate work; existing warning retains its duration': r'''
local w,m=immuneFixture('macrophage');tick(w,cfg.movementStep);near(m.warningTime,.65)
w:SetDebugImmuneAlertLevel(5);Director.Update(w,4.9)
near(Director.BehaviorValue(w,'processingRate'),.5);near(Director.BehaviorValue(w,'tcellWarningSeconds'),2.8)
Director.Update(w,.1);near(Director.BehaviorValue(w,'processingRate'),.85)
near(Director.BehaviorValue(w,'tcellWarningSeconds'),1.8);near(m.warningTimer,.65)
untilState(w,m,'attack');tick(w,m.attackWindup);near(m.cooldown,1)
''',
 'upgrading during identification never completes an old contact early': r'''
local w,t,c=nodeFixture(0);w:_Infect(c,'fixture');untilState(w,t,'investigate');tick(w,1.5)
w:SetDebugImmuneAlertLevel(5);Director.Update(w,5);tick(w,.1)
assert(t.state=='investigate' and c.immuneHits==0);near(t.recognitionRequiredSeconds,2.2)
untilState(w,t,'attack');near(t.attackTimer,1.1)
''',
 'downgrade preserves cooldown and restores the earlier profile on next lock': r'''
local w,m=particles(4);w.activeImmuneAlertLevel=5;cfg.immuneClearChance=1;untilClear(w,m)
local remaining=m.cooldown;w:SetDebugImmuneAlertLevel(0);Director.Update(w,5)
near(m.cooldown,remaining);assert(m.warningTime==0 and m.targetId)
untilState(w,m,'attack');completeAttack(w,m);near(m.cooldown,.35)
reset(w,m);place(w,w.player,m.x,m.y);tick(w,cfg.movementStep);near(m.warningTime,.65)
''',
}


def main():
    rows=[]
    for name, code in TESTS.items():
        lua=LuaRuntime(unpack_returned_tuples=True)
        lua.execute("package.path='scripts/?.lua;'..package.path")
        lua.globals().print=lambda *args:None
        try:
            lua.execute(SETUP+GROWTH_SETUP+COMMON+HELPERS+EXPECTED+code)
            row=dict(name=name,passed=True)
        except Exception as exc:row=dict(name=name,passed=False,error=str(exc))
        rows.append(row);print(('PASS: ' if row['passed'] else 'FAIL: ')+name,flush=True)
        if not row['passed']: print(row['error'],flush=True)
    folder=ROOT/'validation/immune-growth-20261017';folder.mkdir(parents=True,exist_ok=True)
    (folder/'targeted.json').write_text(json.dumps(dict(passed=all(r['passed'] for r in rows),results=rows,
        scope='Actual Lua Core transitions on explicit contact fixtures, not native player acceptance.'),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return int(any(not r['passed'] for r in rows))


if __name__=='__main__':raise SystemExit(main())
