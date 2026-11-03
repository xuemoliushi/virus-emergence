"""Real Lua cross-mechanism acceptance; no replacement of gameplay implementations."""
import argparse
import json
from pathlib import Path
from mechanism_cards_regression import ROOT, SETUP, GROWTH_SETUP, EXTRA, LuaRuntime

CASES = {
    'production map seeds support movement scatter flow and active recovery together': r'''
cfg.width,cfg.height,cfg.cellCount,cfg.mapGenerationVersion=production.width,production.height,production.cellCount,production.version
for _,seed in ipairs({314159,271828,161803}) do
 cfg.mapSeed=seed;local w=quietWorld('UPPER_AIRWAY');local s=w.player
 for _,id in ipairs({'infection_trail','shed_decoy','discrete_recall','local_flow','swarm_anchor','emergency_dash'}) do grant(w,id) end
 local dx,dy
 for i=0,15 do
  local angle=i*math.pi/8;local x,y=math.cos(angle),math.sin(angle)
  if w.map:Contains(s.x+x*4,s.y+y*4,s.radius) and w:_DirectPathClear(s.x,s.y,s.x+x*4,s.y+y*4,s.radius) then dx,dy=x,y;break end
 end
 assert(dx,'no legal test segment from production spawn')
 assert(not skill(w,'local_flow',{x=s.x+dx,y=s.y+dy}))
 assert(not w.abilities.cooldowns.local_flow,'calm spawn must not consume cooldown')
 assert(skill(w,'infection_trail'));assert(skill(w,'shed_decoy'))
 w:SetMovement(dx,dy);assert(skill(w,'emergency_dash'))
 for i=1,240 do w:Update(cfg.movementStep);if i%30==0 then checkConservation(w,true) end end
 assert((w.massLedger.totals.trail_investment or 0)>0)
 w:SetMovement(0,0);assert(skill(w,'swarm_anchor'));assert(skill(w,'discrete_recall'))
 for i=1,180 do w:Update(cfg.movementStep);if i%30==0 then checkConservation(w,true) end end
 assert(s.anchored and w.stats.totalAbsorbed>0 and w.stats.totalAutoSplits==0)
end
''',
    'trail is emitted behind actual movement in all four directions': r'''
for _,dir in ipairs({{1,0},{-1,0},{0,1},{0,-1}}) do
 local w=quietWorld();w.cells={};grant(w,'infection_trail');assert(skill(w,'infection_trail'))
 local s=w.player;local ox,oy=s.x,s.y
 s.x,s.y=ox+dir[1]*1.5,oy+dir[2]*1.5
 assert(w.map:Contains(s.x,s.y,s.radius))
 A.AfterMovement(w,s,ox,oy,1.5)
 local v=assert(w.releasedViruses[1]);assert(v.origin=='trail' and s.mass==29)
 assert((v.x-s.x)*dir[1]+(v.y-s.y)*dir[2]<0,'trail was emitted ahead of movement')
 assert(w.map:Contains(v.x,v.y,v.radius) and liveMass(w)==30)
end
''',
    'trail decoy and merge seeds resist passive recovery but allow explicit E': r'''
for _,kind in ipairs({'trail','decoy','merge_seed'}) do
 local w=quietWorld();local cell=unitCell(w);w.cells={};local s=w.player
 local p=A.TakeMass(w,s,1,kind..'_investment')
 local v=A.SpawnReleased(w,p,s.x,s.y,kind)[1]
 -- Backflow / wall fallback / another group approaching can place a seed inside the collection ring.
 v.x,v.y,v.vx,v.vy=s.x,s.y,0,0;s.anchored=true
 local mass=s.mass
 for _=1,30 do w:Update(cfg.movementStep) end
 assert(A.Alive(v) and s.mass==mass,'passive collection erased '..kind)
 assert(w:AbsorbableCount()==1 and w:AbsorbNearby()==1)
 assert(v.state=='ABSORBED' and s.mass==mass+1 and liveMass(w)==30)
 assert(w:AbsorbNearby()==0 and w.stats.totalAbsorbed==1)
end
''',
    'explicit recall recovers scattered seeds; ordinary node output still auto collects': r'''
local w=quietWorld();local s=w.player;local cell=unitCell(w)
local ordinary=releaseAt(w,1,s.x,s.y)[1];w.cells={};s.anchored=true
w:Update(cfg.movementStep);assert(ordinary.state=='ABSORBED' and s.mass==31)
grant(w,'discrete_recall')
local v=A.SpawnReleased(w,A.TakeMass(w,s,1,'trail_investment'),s.x,s.y,'trail')[1]
v.x,v.y,v.vx,v.vy=s.x+2,s.y,0,0
assert(skill(w,'discrete_recall'));assert(s.mass==30)
for _=1,300 do w:Update(cfg.movementStep) end
assert(v.state=='ABSORBED' and s.mass==31 and w.stats.totalAbsorbed==2)
''',
    'scattered seeds still infect independently, expire and can be cleared': r'''
local w=quietWorld();local s=w.player;local c=unitCell(w)
local v=A.SpawnReleased(w,A.TakeMass(w,s,1,'trail_investment'),s.x,s.y,'trail')[1]
place(w,s,13,30);c.x,c.y=12,27.5;c.regionId=w.map:RegionAt(c.x,c.y)
v.x,v.y,v.vx,v.vy=c.x+c.radius+.03,c.y,0,0
progress(w,25);assert(c.state=='EXPOSED' and c.releasedContribution>0 and not c.everPlayerContact)
assert(c.groupContribution==0)
assert(w:KillReleased(v) and not w:KillReleased(v))
local lost=A.SpawnReleased(w,A.TakeMass(w,s,1,'decoy_investment'),s.x,s.y,'decoy')[1]
lost.age=lost.lifetime-cfg.movementStep;w:_MoveReleased(cfg.movementStep)
assert(lost.state=='LOST' and w.stats.totalLost==1)
''',
    'brain skips intentional seeds but still collects normal node offspring': r'''
local w=manyGroups(2);w.cells={};grant(w,'swarm_local_brain')
local s=w.swarms[2];s.mergeGrace=100;w:DamageSwarm(s.id,s.mass-5)
w:DamageSwarm(w.player.id,w.player.mass-20)
place(w,w.player,13,30);place(w,s,13,27.5)
local v=A.SpawnReleased(w,A.TakeMass(w,w.player,1,'trail_investment'),s.x,s.y,'trail')[1]
v.x,v.y=s.x+.7,s.y
require('Core.SplitVirusAI').ThinkWorld(w,.1)
assert(s.aiState~='collect' and not s._aiSupplyId,'brain chased an intentional seed')
local ordinary=releaseAt(w,1,s.x+.7,s.y)[1]
s._aiThinkClock=0;require('Core.SplitVirusAI').ThinkWorld(w,.1)
assert(s.aiState=='collect' and s._aiSupplyId==ordinary.id)
''',
    'dispatch overrides old glide dash launch while leaving anchored and hidden groups alone': r'''
local w=manyGroups(4);assert(w:SwitchControl(w.swarms[1].id));grant(w,'cluster_dispatch')
local cell=unitCell(w);w.cells={cell}
local other=w.swarms[2]
local anchor,hidden=w.swarms[3],w.swarms[4];anchor.anchored=true;hidden.isHidden=true
for _,mode in ipairs({'glide','dash','launch'}) do
 other.glideCellId=mode=='glide' and cell.id or nil
 other.dashUntil=mode=='dash' and w.time+1 or nil
 other.launchTimer=mode=='launch' and 1 or 0
 assert(skill(w,'cluster_dispatch',{command='gather'},mode))
 assert(other.groupCommand and not other.glideCellId and not other.dashUntil and other.launchTimer==0)
 assert(not anchor.groupCommand and anchor.anchored and not hidden.groupCommand and hidden.isHidden)
end
''',
    'decoy genuinely attracts visible macrophages and remains vulnerable': r'''
local w,im=immuneFixture('macrophage');w.cells={};grant(w,'shed_decoy')
local s=w.player;place(w,s,im.x+2,im.y)
local mass=s.mass;assert(skill(w,'shed_decoy'));local v=w.releasedViruses[1]
v.x,v.y=im.x+.6,im.y
Immune.Update(w,cfg.movementStep)
assert(im.targetType=='virus' and im.targetId~=nil,'decoy did not attract macrophage')
local target;for _,x in ipairs(w.releasedViruses) do if x.id==im.targetId then target=x end end
im.x,im.y=target.x,target.y;im.state='attack';im.attackTimer=cfg.movementStep
cfg.immuneClearChance=1;Immune.Update(w,cfg.movementStep)
assert(target.state=='CLEARED','immune did not clear actual decoy');assert(s.mass==mass-4)
''',
    'all eighteen cards acquire through the authority and preserve mass': r'''
local seen=0
for _,card in ipairs(Config.Cards.definitions) do
 local sim=newSim('UPPER_AIRWAY',true);local w=sim.world;local mass=liveMass(w)
 for _,pre in ipairs(card.prerequisites or {}) do
  assert(sim:AcquireTestCard(pre));sim:ContinueAfterCard()
 end
 assert(sim:AcquireTestCard(card.id));assert(A.Owned(w,card.id) and liveMass(w)==mass)
 if card.capacity then assert(w.maxPlayerSwarms==card.capacity) end
 if card.localBrain then assert(w.swarmBrainEnabled) end
 if card.id=='merge_seed' then assert(w.abilities.mergeSeedEnabled) end
 assert(not sim:AcquireTestCard(card.id));sim:ContinueAfterCard()
 assert(not sim:AcquireTestCard(card.id));seen=seen+1
end
assert(seen==18)
''',
    'all 153 pairs acquire without overriding previous unlocks or breaking prerequisite': r'''
local pairs=0
for i,a in ipairs(Config.Cards.definitions) do for j=i+1,#Config.Cards.definitions do
 local b=Config.Cards.definitions[j];local sim=newSim('UPPER_AIRWAY',true);local w=sim.world
 local function acquire(card)
  for _,pre in ipairs(card.prerequisites or {}) do
   if not sim.cards.acquired[pre] then assert(sim:AcquireTestCard(pre));sim:ContinueAfterCard() end
  end
  if not sim.cards.acquired[card.id] then assert(sim:AcquireTestCard(card.id));sim:ContinueAfterCard() end
 end
 acquire(a);acquire(b)
 assert(A.Owned(w,a.id) and A.Owned(w,b.id) and liveMass(w)==30)
 assert(w.immuneAlertLevel==sim.cards.acquisitionCount and not sim.paused)
 if a.localBrain or b.localBrain then assert(w.swarmBrainEnabled) end
 if a.capacity or b.capacity then assert(w.maxPlayerSwarms==math.max(a.capacity or 2,b.capacity or 2)) end
 pairs=pairs+1
end end
assert(pairs==153)
''',
}

def run(only=''):
    results=[]
    for name,code in CASES.items():
        if only and only not in name:
            continue
        lua=LuaRuntime(unpack_returned_tuples=True)
        lua.execute('package.path='+repr(str(ROOT/'scripts/?.lua').replace('\\','/'))+"..';'..package.path")
        lua.execute("local c=require('Core.Config').Gameplay;production={width=c.width,height=c.height,cellCount=c.cellCount,version=c.mapGenerationVersion}")
        lua.globals().print=lambda *args: None
        try:
            lua.execute(SETUP+GROWTH_SETUP+EXTRA+code)
            results.append({'name':name,'passed':True})
            print('PASS',name)
        except Exception as error:
            results.append({'name':name,'passed':False,'error':str(error)})
            print('FAIL',name,str(error))
    out=ROOT/'validation/card-effects-20261018'
    out.mkdir(exist_ok=True)
    (out/'cross-mechanism-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Card effect acceptance:',sum(r['passed'] for r in results),'/',len(results))
    return all(r['passed'] for r in results)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--only',default='')
    raise SystemExit(0 if run(parser.parse_args().only) else 1)
