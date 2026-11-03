"""Pursuit/continuous-clear causal tests. Core Lua, no native gameplay claim."""
import json
import sys
from pathlib import Path
from immune_adaptation_regression import ROOT, SETUP, GROWTH_SETUP, COMMON, LuaRuntime

FOLDER = ROOT / 'validation/immune-pressure-20261017'
HELPERS = r'''
function particles(n)
 local w,m=immuneFixture('macrophage');local c=unitCell(w);w.cells={c}
 place(w,w.player,13,3.1);m.x,m.y=13,27.5;m._patrolX,m._patrolY=m.x,m.y
 w:_Release(c,n)
 for _,v in ipairs(w.releasedViruses)do v.x,v.y=m.x,m.y end
 return w,m
end
function untilClear(w,m)
 for _=1,900 do
  tick(w,cfg.movementStep)
  if w.stats.totalKilled>0 then return end
 end
 error('no real clear')
end
'''
TESTS = {
 'visible groups outrank ordinary particles; live decoys retain attention': r'''
for _,decoy in ipairs({false,true})do
 local w,m=particles(3);place(w,w.player,14.8,27.5)
 local v=w.releasedViruses[1];if decoy then v.decoyUntil=w.time+8 end
 tick(w,cfg.movementStep)
 assert(m.targetType==(decoy and 'virus' or 'swarm'))
end
''',
 'decoy diverts a macrophage already attacking the swarm and keeps its cooldown': r'''
for _,phase in ipairs({'attack','cooldown'})do
 local w,m=particles(1);w.releasedViruses={};place(w,w.player,14.1,27.5)
 untilState(w,m,phase);assert(m.targetType=='swarm')
 local cooldown=m.cooldown
 local v=w.releasedViruses;local A=require('Core.AbilityRuntime')
 local d=A.SpawnReleased(w,A.TakeMass(w,w.player,2,'fixture'),w.player.x,w.player.y,'decoy')
 for _,x in ipairs(d) do x.decoyUntil=w.time+8 end
 m._retargetTimer=0;tick(w,cfg.movementStep)
 assert(m.targetType=='virus' and (m.targetId==d[1].id or m.targetId==d[2].id),phase..' did not divert')
 if phase=='cooldown' then assert(m.state=='cooldown' and m.cooldown>0 and m.cooldown<=cooldown) end
end
''',
 'decoy outside the macrophage patrol area still diverts the chase': r'''
local w,m=particles(1);w.releasedViruses={}
m.patrolHome={regionId=m.regionId,x=m.x-40,y=m.y}
w.config.immuneCoverage=w.config.immuneCoverage or {patrolRadius=14,workAreaRadius=4,workAreaSlots=2}
local flat=w.map.isFlatMap;w.map.isFlatMap=true
place(w,w.player,14.8,27.5);untilState(w,m,'chase');assert(m.targetType=='swarm')
local A=require('Core.AbilityRuntime')
local d=A.SpawnReleased(w,A.TakeMass(w,w.player,2,'fixture'),w.player.x,w.player.y,'decoy')
for _,x in ipairs(d) do x.decoyUntil=w.time+8 end
m._retargetTimer=0;tick(w,cfg.movementStep);w.map.isFlatMap=flat
assert(m.targetType=='virus','patrol area must not block decoys')
''',
 'one decoy cluster can divert two chasing macrophages': r'''
local w,m=particles(1);w.releasedViruses={}
local m2=extra(w,'macrophage',13,26.9)
place(w,w.player,14.8,27.3);tick(w,.3)
assert(m.targetType=='swarm' and m2.targetType=='swarm')
local A=require('Core.AbilityRuntime')
local d=A.SpawnReleased(w,A.TakeMass(w,w.player,4,'fixture'),w.player.x,w.player.y,'decoy')
for _,x in ipairs(d) do x.decoyUntil=w.time+8 end
m._retargetTimer,m2._retargetTimer=0,0;tick(w,cfg.movementStep)
assert(m.targetType=='virus' and m2.targetType=='virus','both pursuers must follow the decoy')
''',
 'expired decoys no longer interrupt an attack on the swarm': r'''
local w,m=particles(1);w.releasedViruses={};place(w,w.player,14.1,27.5)
untilState(w,m,'attack')
local A=require('Core.AbilityRuntime')
A.SpawnReleased(w,A.TakeMass(w,w.player,2,'fixture'),w.player.x,w.player.y,'decoy')
m._retargetTimer=0;tick(w,cfg.movementStep);assert(m.targetType=='swarm')
''',
 'a nearby group interrupts particle windup without inheriting charge': r'''
local w,m=particles(3);untilState(w,m,'attack');local killed=w.stats.totalKilled
place(w,w.player,14.8,27.5);m._retargetTimer=0;tick(w,cfg.movementStep)
assert(m.targetType=='swarm' and m.state=='locked' and m.attackTimer==0)
assert(m.warningTimer==m.warningTime and w.stats.totalKilled==killed)
''',
 'warning approaches but never deals damage; all six levels react promptly': r'''
for level=0,5 do
 local w,m=clearFixture('macrophage',level);place(w,w.player,15.5,27.5)
 tick(w,2*cfg.movementStep);assert(m.state=='warning');local x=m.x;local mass=w.player.mass
 tick(w,.1);assert(m.x>x and w.player.mass==mass and m.warningTime<=.65)
end
''',
 'continuous clear skips a second warning but preserves cooldown and contact': r'''
local w,m=particles(4);untilClear(w,m)
assert(w.stats.totalKilled==1 and m.state=='cooldown' and m.targetType=='virus')
assert(m.warningTime==0 and m.warningTimer==0 and eventCount(w,'immune_clear_chain')==1)
local killed=w.stats.totalKilled;local remaining=m.cooldown
tick(w,remaining-cfg.movementStep);assert(w.stats.totalKilled==killed)
untilState(w,m,'attack');assert(w.stats.totalKilled==killed)
tick(w,m.attackWindup);assert(w.stats.totalKilled==killed+1)
assert(eventCount(w,'immune_warning')==1,'chain must not re-enter warning')
checkConservation(w)
''',
 'leaving detection ends chain; later reacquisition needs first warning': r'''
for _,far in ipairs({false,true})do
 local w,m=particles(2);untilClear(w,m);local v=w.releasedViruses[2]
 v.x,v.y=m.x+m.detectionRange+v.radius+.05,m.y
 if far then v.x,v.y=13,3.1 end
 assert(w.map:Contains(v.x,v.y,v.radius))
 local killed=w.stats.totalKilled;tick(w,.1)
 assert(not m.targetId and w.stats.totalKilled==killed)
 v.x,v.y=m.x,m.y;untilState(w,m,'locked')
 assert(m.targetId==v.id and m.warningTime>0,'fresh work cannot retain chain exemption')
end
''',
 'a chained target behind real tissue cannot be cleared': r'''
local w,m=particles(2);untilClear(w,m);local v=w.releasedViruses[2];local found=false
for y=1,31 do
 if found then break end
 for x=1,25 do
  if w.map:Contains(x,y,v.radius) and not Navigation.Clear(w.map,m,{x=x,y=y},0) then
   v.x,v.y=x,y;found=true;break
  end
 end
end
assert(found);local killed=w.stats.totalKilled;tick(w,.1)
assert(not m.targetId and w.stats.totalKilled==killed)
''',
 'full load ends continuous work and recovery does not preserve free warning': r'''
local w,m=particles(16);untilState(w,m,'processing')
assert(not m.targetId and m.processingLoad<=cfg.immuneBehavior.loadCapacity)
local killed=w.stats.totalKilled;tick(w,1)
assert(m.state=='processing' and w.stats.totalKilled==killed)
untilState(w,m,'locked');assert(m.warningTimer>0)
checkConservation(w)
''',
 'failed clear consumes a complete cycle instead of rerolling each frame': r'''
local w,m=particles(3);cfg.immuneClearChance=0;untilState(w,m,'attack')
tick(w,m.attackWindup);assert(m.state=='cooldown' and w.stats.totalKilled==0)
assert(eventCount(w,'immune_clear_chain')==0 and eventCount(w,'immune_warning')==1)
tick(w,m.cooldown-cfg.movementStep);assert(m.state=='cooldown')
checkConservation(w)
''',
 'escape cancels a moving contact attack and hidden groups remain safe': r'''
local w,m=immuneFixture('macrophage');untilState(w,m,'attack');local mass=w.player.mass
place(w,w.player,m.x+1.5,m.y);tick(w,cfg.movementStep)
assert(m.state=='chase' and w.player.mass==mass)
w.player.isHidden=true;tick(w,3)
assert(not m.targetId and w.player.mass==mass)
''',
 'T cells use stage-specific warning and contact recognition': r'''
local w,t,c=nodeFixture(3);w:_Infect(c,'fixture');tick(w,cfg.movementStep)
assert(t.warningTime==2.2 and t.attackWindup==1.1)
untilState(w,t,'investigate');tick(w,1)
assert(t.state=='investigate' and c.immuneHits==0)
''',
}

# Quantified before/after assays use legal poses on production v5 geometry, the
# real World movement and default Core parameters. Initial actors are arranged;
# this is not a natural player route or a win-rate measurement.
METRICS = r'''
local H=require('ai_non_runtime_scenarios').Helpers
local Director=require('Core.ImmuneDirector')
local Immune=require('Core.ImmuneSystem')
local Config=require('Core.Config')
local function fresh()
 local _,w=H.make(314159);local m=w.immunes[1];w.immunes={m}
 local anchor=w.map.regions[3]
 -- Find a body-clear straight corridor rather than ignoring actual map shape.
 for _,c in ipairs(w.cells)do
  if w.map:Contains(c.x,c.y,m.radius) and w.map:Contains(c.x+10,c.y,m.radius)
   and w:_DirectPathClear(c.x,c.y,c.x+10,c.y,m.radius) then anchor=c;break end
 end
 H.pose(w,m,anchor.x,anchor.y);H.pose(w,w.player,anchor.x+1.5,anchor.y)
 return w,m,anchor
end
local function ticks(w,seconds)
 for _=1,math.floor(seconds*60+.5)do w.time=w.time+1/60;Immune.Update(w,1/60)end
end
local w,m,anchor=fresh()
local c=w.cells[1];w:_Release(c,12)
for _,v in ipairs(w.releasedViruses)do v.x,v.y=m.x,m.y end
ticks(w,1/60)
local chosen=m.targetType
w,m,anchor=fresh();H.pose(w,w.player,w.map.regions[5].x,w.map.regions[5].y)
c=w.cells[1];w:_Release(c,30)
for _,v in ipairs(w.releasedViruses)do v.x,v.y=m.x,m.y end
local first,chainGap,previous,clears=nil,nil,nil,0
for _=1,30*60 do
 ticks(w,1/60)
 if w.stats.totalKilled>clears then
  clears=w.stats.totalKilled;first=first or w.time
  if previous and not chainGap then chainGap=w.time-previous end
  previous=w.time
 end
end
local cleared=clears
local pursues={}
for level=0,5 do
 w,m,anchor=fresh();w.activeImmuneAlertLevel=level
 local start=w.player.mass;w:SetMovement(1,0)
 for _=1,4*60 do w:Update(1/60)end
 H.invariants(w)
 pursues[#pursues+1]={level=level,killed=start-w.player.mass,gap=math.sqrt((w.player.x-m.x)^2+(w.player.y-m.y)^2),
  stillTracking=m.targetType=='swarm',state=m.state}
end
return {chosenWithParticles=chosen,firstClear=first,firstGap=chainGap,cleared30Seconds=cleared,pursuits=pursues}
'''


def runtime(baseline=False):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('package.path=' + repr((ROOT/'scripts/?.lua').as_posix()+';'+(ROOT/'tests/?.lua').as_posix()) + "..';'..package.path")
    lua.globals().print = lambda *args: None
    if baseline:
        for name in ['Core.Config', 'Core.ImmuneSystem']:
            path = FOLDER/'baseline/scripts'/Path(name.replace('.', '/')+'.lua')
            lua.execute('package.loaded['+repr(name)+']=assert(loadfile('+repr(path.as_posix())+'))()')
    return lua


def main():
    from ai_non_runtime_acceptance import plain
    rows=[]
    for name, code in TESTS.items():
        try:
            runtime().execute(SETUP+GROWTH_SETUP+COMMON+HELPERS+code)
            row=dict(name=name,passed=True)
        except Exception as exc:
            row=dict(name=name,passed=False,error=str(exc))
        rows.append(row)
        print(('PASS: ' if row['passed'] else 'FAIL: ')+name,flush=True)
        if not row['passed']: print(row['error'],flush=True)
    metrics={}
    for label in ['baseline','current']:
        try: metrics[label]=plain(runtime(label=='baseline').execute(METRICS))
        except Exception as exc: metrics[label]=dict(error=str(exc))
    valid='error' not in metrics['current'] and 'error' not in metrics['baseline']
    if valid:
        a,b=metrics['baseline'],metrics['current']
        valid=b['chosenWithParticles']=='swarm' and b['cleared30Seconds']>a['cleared30Seconds'] and b['firstGap']<a['firstGap']
        valid=valid and all(r['stillTracking'] and r['killed']>0 for r in b['pursuits'])
    print(json.dumps(metrics,ensure_ascii=False,indent=2),flush=True)
    passed=all(r['passed'] for r in rows) and valid
    FOLDER.mkdir(parents=True,exist_ok=True)
    (FOLDER/'targeted.json').write_text(json.dumps(dict(passed=passed,results=rows,metrics=metrics,
        scope='Explicit actors and particles; real Core Lua and production-map movement. No native or player balance acceptance.'),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return int(not passed)


if __name__=='__main__': raise SystemExit(main())
