"""Real relay swarms: authority, resource transfer, contact, immunity, recovery and ownership."""
import json
from mechanism_cards_regression import ROOT,SETUP,GROWTH_SETUP,EXTRA,LuaRuntime

FIXTURE=r'''
function relayFixture()
 local w=quietWorld();grant(w,'membrane_glide');local c=unitCell(w);w.cells={c}
 local source=w.player;place(w,source,c.x+c.radius+source.radius*.75,c.y)
 w:_AccumulateExposure(.5);w:_InfectCells()
 assert(c.state=='EXPOSED' and source.exposedCells[c.id])
 assert(skill(w,'membrane_glide',{cellId=c.id}))
 local team=w.swarms[2];assert(team and team.relayCellId==c.id)
 return w,source,c,team
end
'''
CASES={
 'three production map seeds support legal deployment and infection after departure':r'''
cfg.width,cfg.height,cfg.cellCount,cfg.mapGenerationVersion=production.width,production.height,production.cellCount,production.version
for _,seed in ipairs({314159,271828,161803}) do
 cfg.mapSeed=seed;local w=quietWorld('UPPER_AIRWAY');grant(w,'membrane_glide')
 local source=w.player;local start={x=source.x,y=source.y};local chosen
 for _,c in ipairs(w.cells) do
  if distance(c,start)>3 then
   for i=0,15 do
    local angle=i*math.pi/8;local x=c.x+math.cos(angle)*(c.radius+source.radius*.75)
    local y=c.y+math.sin(angle)*(c.radius+source.radius*.75)
    if w.map:Contains(x,y,source.radius) then
     place(w,source,x,y);w:_AccumulateExposure(.5);w:_InfectCells()
     if skill(w,'membrane_glide',{cellId=c.id}) then chosen=c;break end
    end
   end
  end
  if chosen then break end
 end
 assert(chosen,'no legal production target found')
 local team=w.swarms[2];assert(team and team.relayCellId==chosen.id)
 place(w,source,start.x,start.y);source.anchored=true
 for i=1,2400 do
  w:Update(cfg.movementStep)
  if i%60==0 then checkConservation(w,true) end
  if not w:SwarmById(team.id) then break end
 end
 assert(chosen.state=='LATENT' and not w:SwarmById(team.id) and liveMass(w)==30)
 assert(w.stats.totalReleased==0 and w.massLedger.totals.relay_return==3)
 checkConservation(w,true)
end
''',
 'deployment transfers three real particles and consumes a group slot':r'''
local w,s,c,t=relayFixture()
assert(s.mass==27 and t.mass==3 and #w.viruses==30 and liveMass(w)==30)
assert(w:LiveSwarmCount()==2 and w.currentControlledSwarmId==s.id)
assert(w.massLedger.totals.relay_investment==3 and w.stats.totalReleased==0)
assert(w.map:Contains(t.x,t.y,t.radius));checkConservation(w,true)
assert(not w:_CanMergePair(s,t) and not w:_Merge(s,t))
''',
 'source can leave; dedicated power completes infection and converts only surviving squad':r'''
local w,s,c,t=relayFixture();place(w,s,13,30);s.anchored=true
local x,y=t.x,t.y;near(A.RelayPower(w,t),cfg.infectionSeconds/15)
for _=1,2400 do
 w:Update(cfg.movementStep)
 if not w:SwarmById(t.id) then break end
 near(t.x,x);near(t.y,y)
end
assert(c.state=='LATENT' and not w:SwarmById(t.id) and w:LiveSwarmCount()==1)
assert(#w.releasedViruses==3 and liveMass(w)==30 and w.stats.totalReleased==0)
assert(w.massLedger.totals.relay_return==3)
checkConservation(w,true)
''',
 'squad casualty proportionally reduces infection power without free replacement':r'''
local w,s,c,t=relayFixture();w:DamageSwarm(t.id,1)
assert(t.mass==2);near(A.RelayPower(w,t),cfg.infectionSeconds/15*2/3)
assert(liveMass(w)==29 and w.stats.totalKilled==1)
w:DamageSwarm(t.id,2);assert(not w:SwarmById(t.id) and w:LiveSwarmCount()==1)
assert(#w.releasedViruses==0 and liveMass(w)==27);checkConservation(w)
''',
 'E recovers nearby squad once and respects the normal shared cooldown':r'''
local w,s,c,t=relayFixture();assert(w:AbsorbableCount()==3)
assert(w:AbsorbNearby()==3 and s.mass==30 and w:LiveSwarmCount()==1)
assert(w.stats.totalAbsorbed==3 and w.stats.totalReleased==0 and liveMass(w)==30)
assert(w:AbsorbNearby()==0 and w:GetAbsorptionCooldown()>0)
assert(not w:SwarmById(t.id));checkConservation(w)
''',
 'target death returns remaining particles once without false swarm-death events':r'''
local w,s,c,t=relayFixture();w:DamageSwarm(t.id,1);w.events={}
w:KillCell(c,'immune');assert(not w:SwarmById(t.id) and #w.releasedViruses==2)
assert(eventCount(w,'swarm_cleared')==0 and eventCount(w,'split_lost')==0)
w:KillCell(c,'immune');assert(#w.releasedViruses==2 and liveMass(w)==29)
checkConservation(w)
''',
 'invalid contact mass capacity duplicate and repeated requests never charge twice':r'''
local w,s,c,t=relayFixture();local before=s.mass
assert(not skill(w,'membrane_glide',{cellId=c.id},'full'))
w.maxPlayerSwarms=4;assert(not skill(w,'membrane_glide',{cellId=c.id},'duplicate'))
assert(not skill(w,'membrane_glide',{cellId=c.id}));assert(s.mass==before)
local q=quietWorld();grant(q,'membrane_glide');local n=unitCell(q);q.cells={n}
assert(not skill(q,'membrane_glide',{cellId=n.id}));assert(q.player.mass==30)
q:_AccumulateExposure(.5);q:_InfectCells();q:DamageSwarm(q.player.id,25)
assert(not skill(q,'membrane_glide',{cellId=n.id},'low'));assert(q.player.mass==5)
assert(not q.abilities.cooldowns.membrane_glide)
''',
 'brain dispatch passive collection and flow cannot steal or move the squad':r'''
local w,s,c,t=relayFixture();grant(w,'swarm_local_brain');grant(w,'cluster_dispatch')
place(w,s,13,30);s.anchored=true;local x,y=t.x,t.y
assert(not require('Core.SplitVirusAI').IsAutonomous(w,t))
assert(not skill(w,'cluster_dispatch',{command='gather'}));assert(not t.groupCommand)
releaseAt(w,1,t.x,t.y);assert(not w:_CanAbsorbReleased(t,w.releasedViruses[1]))
for _=1,60 do w:Update(cfg.movementStep) end
assert(t.mass==3 and t.relayCellId==c.id);near(t.x,x);near(t.y,y);checkConservation(w)
''',
 'squad infects only its assigned target and can be manually taken over':r'''
local w,s,c,t=relayFixture();local other=unitCell(w,1,c.x,c.y)
-- Copy the cell record to a distinct neighboring target without adding a source.
local neighbor={};for k,v in pairs(other) do neighbor[k]=v end
neighbor.id=999;neighbor.x=c.x+.1;neighbor.exposure=0;neighbor._charge=0;neighbor._groupCharge=0
neighbor._releasedCharge=0;neighbor.everPlayerContact=false;neighbor.groupContribution=0
neighbor.releasedContribution=0;neighbor.contactVisuals={}
w.cells={c,neighbor};place(w,s,13,30);s.anchored=true
w:_AccumulateExposure(.5);assert(neighbor._charge<=0)
assert(w:SwitchControl(t.id));assert(w.player==t and not t.relayCellId and t.mass==3)
assert(w:LiveSwarmCount()==2);checkConservation(w)
''',
 'last surviving squad becomes an ordinary controllable group without creating mass':r'''
local w,s,c,t=relayFixture();w:DamageSwarm(s.id,s.mass)
assert(w.player==t and w.currentControlledSwarmId==t.id and not t.relayCellId)
assert(w:ControlledCount()==3 and #w.viruses==3 and w.stats.totalKilled==27)
checkConservation(w)
''',
 'real macrophage attack damages the stationary squad normally':r'''
local w,im=immuneFixture('macrophage');grant(w,'membrane_glide');local c=unitCell(w);w.cells={c}
local s=w.player;place(w,s,c.x+c.radius+s.radius*.75,c.y)
w:_AccumulateExposure(.5);w:_InfectCells();assert(skill(w,'membrane_glide',{cellId=c.id}))
local t=w.swarms[2];im.x,im.y=t.x,t.y;im.state='attack';im.targetType='swarm';im.targetId=t.id
im.attackTimer=cfg.movementStep;Immune.Update(w,cfg.movementStep)
assert(t.mass==1 and w.stats.totalKilled==2)
''',
}

def run():
    rows=[]
    for name,code in CASES.items():
        lua=LuaRuntime(unpack_returned_tuples=True)
        lua.execute('package.path='+repr((ROOT/'scripts/?.lua').as_posix())+"..';'..package.path")
        lua.execute("local c=require('Core.Config').Gameplay;production={width=c.width,height=c.height,cellCount=c.cellCount,version=c.mapGenerationVersion}")
        lua.globals().print=lambda *a:None
        try:
            lua.execute(SETUP+GROWTH_SETUP+EXTRA+FIXTURE+code)
            rows.append(dict(name=name,passed=True));print('PASS',name)
        except Exception as error:
            rows.append(dict(name=name,passed=False,error=str(error)));print('FAIL',name,str(error))
    out=ROOT/'validation/infection-relay-20261018';out.mkdir(exist_ok=True)
    (out/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    return all(r['passed'] for r in rows)
if __name__=='__main__':raise SystemExit(0 if run() else 1)
