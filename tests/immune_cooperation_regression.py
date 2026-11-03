"""Role cooperation and bounded hotspot cleanup; real Lua, explicit fixtures."""
import json
import sys
import hashlib
from pathlib import Path
from immune_adaptation_regression import ROOT, SETUP, GROWTH_SETUP, COMMON, LuaRuntime

TESTS = {
    'independent hotspots keep separate workers and obey the global budget': r'''
local w,t,c=nodeFixture(4);w:_Infect(c,'fixture');untilState(w,t,'attack')
-- Direct director calls isolate the report/assignment budget; actual contact
-- publication is exercised separately above and in the production-map assay.
local r=w.map.regions[1];local t2=extra(w,'tcell',r.x,r.y);t2.recognized=true;t2._hotspotReadyAt=0
assert(Director.ConfirmHotspot(w,t2,{targetType='cell',x=r.x,y=r.y}))
local t3=extra(w,'tcell',13,27.5);t3.recognized=true
assert(not Director.ConfirmHotspot(w,t3,{targetType='cell',x=21.75,y=20.5}))
local a=extra(w,'macrophage',13.4,27.5);local b=extra(w,'macrophage',r.x,r.y)
Director.Update(w,.01)
local da,db=w.immuneCleanupAssignments[a.id],w.immuneCleanupAssignments[b.id]
assert(da and db and da.hotspotId~=db.hotspotId and #w.immuneHotspots==2)
''',
    'stage IV hotspot requires completed contact recognition': r'''
for _,level in ipairs({3,4}) do
 local w,t,c=nodeFixture(level);w:_Infect(c,'fixture')
 untilState(w,t,'investigate');assert(#w.immuneHotspots==0)
 tick(w,1);assert(#w.immuneHotspots==0 and c.immuneHits==0)
 untilState(w,t,'attack');assert((#w.immuneHotspots==1)==(level>=4))
 if level>=4 then
  local p=w.immuneHotspots[1];assert(p.sourceId==t.id and p.x==c.x and not p.targetId and not p.cellId)
  assert(not Director.ConfirmHotspot(w,t,{targetType='cell',x=c.x,y=c.y}),'same source/location cooldown')
 end
end
''',
    'one idle macrophage per hotspot; role and workload exclusion': r'''
local w,t,c=nodeFixture(4);w:_Infect(c,'fixture');untilState(w,t,'attack')
local a=extra(w,'macrophage',12,27.5);local b=extra(w,'macrophage',14,27.5)
local busy=extra(w,'macrophage',13,27.7);busy.processingLoad=6;busy.state='processing'
local spare=extra(w,'tcell',13,28);local count=#w.immunes
Director.Update(w,.01)
local n=0;for _ in pairs(w.immuneCleanupAssignments)do n=n+1 end
assert(n==1 and not w.immuneCleanupAssignments[t.id] and not w.immuneCleanupAssignments[spare.id])
assert(not w.immuneCleanupAssignments[busy.id] and busy.state=='processing' and #w.immunes==count)
local duty=w.immuneCleanupAssignments[a.id] or w.immuneCleanupAssignments[b.id]
assert(duty and not duty.targetId and not duty.cellId and duty.untilTime==w.immuneHotspots[1].untilTime)
''',
    'hotspot recipient finds and physically clears real released viruses': r'''
local w,t,c=nodeFixture(4);w:_Infect(c,'fixture');untilState(w,t,'attack')
local m=extra(w,'macrophage',13.4,27.5);w:_Release(c,1)
local v=w.releasedViruses[1];v.x,v.y=m.x,m.y;cfg.immuneClearChance=1
local killed=w.stats.totalKilled;local mass=w:ControlledCount()
tick(w,cfg.movementStep);assert(m.targetType=='virus' and m.state=='locked' and m.hotspotCleanup)
tick(w,.1);assert(v.state~='CLEARED' and w.stats.totalKilled==killed)
tick(w,4.4);assert(v.state=='CLEARED' and w.stats.totalKilled==killed+1 and w:ControlledCount()==mass)
assert(c.immuneHits==2,'stage IV attack cadence allows two T-cell hits in this window')
for _,event in ipairs(w.events)do
 if event.name=='node_attack' then assert(event.payload.immuneId==t.id,'macro must not add node attacks')end
end
''',
    'cleanup ignores outside lure and releases escaped particles without search': r'''
local w,t,c=nodeFixture(5);w:_Infect(c,'fixture');untilState(w,t,'attack')
local m=extra(w,'macrophage',13.4,27.5);w:_Release(c,1)
local v=w.releasedViruses[1];v.x,v.y=m.x,m.y
tick(w,cfg.movementStep);assert(m.targetType=='virus')
local duty=w.immuneCleanupAssignments[m.id];v.x,v.y=c.x+duty.radius+.2,c.y
local killed=w.stats.totalKilled;tick(w,cfg.movementStep)
assert(not m.targetId and m.state=='patrol' and w.immuneCleanupAssignments[m.id])
tick(w,.1);assert(not m.targetId and v.state~='CLEARED' and w.stats.totalKilled==killed)
''',
    'empty hotspot ends early and does not continually replace workers': r'''
local w,t,c=nodeFixture(4);w:_Infect(c,'fixture');untilState(w,t,'attack')
local m=extra(w,'macrophage',13.4,27.5);Director.Update(w,.01)
assert(w.immuneCleanupAssignments[m.id]);tick(w,4.2)
assert(not w.immuneCleanupAssignments[m.id] and not m.hotspotCleanup)
local b=extra(w,'macrophage',13.6,27.5);Director.Update(w,.01)
assert(not w.immuneCleanupAssignments[b.id],'used slot is not endlessly refilled')
''',
    'workload ends duty and preserves attack cooldown': r'''
local w,t,c=nodeFixture(4);w:_Infect(c,'fixture');untilState(w,t,'attack')
local m=extra(w,'macrophage',13.4,27.5);Director.Update(w,.01)
assert(w.immuneCleanupAssignments[m.id]);m.processingLoad=4;m.cooldown=2;m.state='cooldown'
tick(w,cfg.movementStep)
assert(not w.immuneCleanupAssignments[m.id] and m.cooldown>1.9 and m.state=='cooldown')
m.state='processing';m.processingLoad=6;tick(w,.1)
assert(m.state=='processing','ending cleanup must not cancel load processing')
''',
    'deadline cancels attack without damage and keeps already-started cooldown': r'''
local w,t,c=nodeFixture(4);w:_Infect(c,'fixture');untilState(w,t,'attack')
local m=extra(w,'macrophage',13.4,27.5);w:_Release(c,1)
local v=w.releasedViruses[1];v.x,v.y=m.x,m.y;cfg.immuneClearChance=1
untilState(w,m,'attack');local duty=w.immuneCleanupAssignments[m.id];assert(duty)
w.time=duty.untilTime;local killed=w.stats.totalKilled;tick(w,cfg.movementStep)
assert(not m.hotspotCleanup and m.state~='attack' and v.state~='CLEARED' and w.stats.totalKilled==killed)
assert(not m.targetId or m.state=='locked' and m.warningTimer==cfg.immuneBehavior.particleWarningSeconds,'ordinary reacquisition starts a fresh warning')
''',
    'debug downgrade revokes cleanup immediately after its normal buffer': r'''
local w,t,c=nodeFixture(4);w:_Infect(c,'fixture');untilState(w,t,'attack')
local m=extra(w,'macrophage',13.4,27.5);Director.Update(w,.01);assert(m.hotspotCleanup)
w:SetDebugImmuneAlertLevel(3);Director.Update(w,4.9);assert(w.immuneCleanupAssignments[m.id])
Director.Update(w,.1);Immune.Update(w,cfg.movementStep)
assert(#w.immuneHotspots==0 and not m.hotspotCleanup and not w.immuneCleanupAssignments[m.id])
''',
    'hotspot and alarm do not assign conflicting jobs to the same worker': r'''
local w,t,c=nodeFixture(4);w:_Infect(c,'fixture');untilState(w,t,'attack')
local a=extra(w,'macrophage',12,27.5);local b=extra(w,'macrophage',14,27.5)
assert(Director.Alarm(w,b,b.x,b.y));Director.Update(w,.01)
assert(w.immuneCleanupAssignments[a.id] or w.immuneCleanupAssignments[b.id])
for _,im in ipairs(w.immunes)do assert(not (w.immuneCleanupAssignments[im.id] and w.immuneAlarmAssignments[im.id]))end
''',
    'actual wall blocks recruitment and nearby duplicate hotspots': r'''
local w,t,c=nodeFixture(4);local found=false;local mx,my
for y=1,w.height-1 do
 if found then break end
 for x=1,w.width-1 do
  if found then break end
  if w.map:Contains(x,y,c.radius) then
   for i=1,48 do
    local angle=i*math.pi/24;local bx,by=x+math.cos(angle)*5,y+math.sin(angle)*5
    if w.map:Contains(bx,by,t.radius) and not Navigation.Clear(w.map,{x=bx,y=by},{x=x,y=y},t.radius) then
     c.x,c.y=x,y;c.regionId=w.map:RegionAt(x,y);t.x,t.y=x,y;t._patrolX,t._patrolY=x,y
     mx,my=bx,by;found=true;break
    end
   end
  end
 end
end
assert(found,'authored tissue has a real blocked pair');w:_Infect(c,'fixture');untilState(w,t,'attack')
local m=extra(w,'macrophage',mx,my);Director.Update(w,.01)
assert(not w.immuneCleanupAssignments[m.id])
local other=extra(w,'tcell',t.x,t.y);other.recognized=true
assert(not Director.ConfirmHotspot(w,other,{targetType='cell',x=c.x+.1,y=c.y}),'overlapping hotspots are merged by exclusion')
''',
}


def main():
    if '--production' in sys.argv:
        from ai_non_runtime_acceptance import plain
        rows=[]
        seeds=[int(sys.argv[sys.argv.index('--seed')+1])] if '--seed' in sys.argv else [314159,271828,161803,314159]
        for seed in seeds:
            lua=LuaRuntime(unpack_returned_tuples=True)
            lua.execute('package.path='+repr((ROOT/'scripts/?.lua').as_posix()+';'+(ROOT/'tests/?.lua').as_posix())+"..';'..package.path")
            logs=[];lua.globals().print=lambda *v:logs.append(' '.join(map(str,v)))
            try:
                suite=lua.execute((ROOT/'tests/immune_cooperation_scenarios.lua').read_text(encoding='utf-8'))
                data=plain(suite.Run(seed));data['trace_sha256']=hashlib.sha256(data.pop('decision_trace').encode()).hexdigest()
                row=dict(seed=seed,passed=True,**data)
            except Exception as error:row=dict(seed=seed,passed=False,error=str(error),logs=logs[-6:])
            rows.append(row);print(f"{'PASS' if row['passed'] else 'FAIL'}: production cooperation {seed}",flush=True)
            if not row['passed']:print(row['error'],row['logs'],flush=True)
        replay=rows[0]['passed'] and rows[-1]['passed'] and rows[0].get('state')==rows[-1].get('state') and rows[0].get('trace_sha256')==rows[-1].get('trace_sha256')
        folder=ROOT/'validation/immune-cooperation-20261017';folder.mkdir(parents=True,exist_ok=True)
        (folder/'production.json').write_text(json.dumps(dict(passed=all(r['passed'] for r in rows) and replay,replay_passed=replay,
            results=rows,scope='Native production map with explicit actor/particle poses, authority infection and release. Immune-only causal steps; full World/Sim stress is separate.'),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return int(not all(r['passed'] for r in rows) or not replay)
    rows=[]
    for name,code in TESTS.items():
        lua=LuaRuntime(unpack_returned_tuples=True)
        lua.execute('package.path='+repr((ROOT/'scripts/?.lua').as_posix())+"..';'..package.path")
        logs=[];lua.globals().print=lambda *v:logs.append(' '.join(map(str,v)))
        try:
            lua.execute(SETUP+GROWTH_SETUP+COMMON+code)
            row=dict(name=name,passed=True)
        except Exception as error:
            row=dict(name=name,passed=False,error=str(error),logs=logs[-5:])
        rows.append(row);print(('PASS: ' if row['passed'] else 'FAIL: ')+name,flush=True)
        if not row['passed']:print(row['error'],row['logs'],flush=True)
    folder=ROOT/'validation/immune-cooperation-20261017';folder.mkdir(parents=True,exist_ok=True)
    (folder/'targeted.json').write_text(json.dumps(dict(passed=all(r['passed'] for r in rows),results=rows,
        scope='Real Lua Core modules on historical geometry; explicit poses and authority infection/clear. Not native/player acceptance.'),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"{sum(r['passed'] for r in rows)}/{len(rows)} cooperation checks passed.")
    return int(any(not r['passed'] for r in rows))

if __name__=='__main__':raise SystemExit(main())
