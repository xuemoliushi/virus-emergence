"""机制卡：真实 Lua 权威能力、质量、碰撞、暂停及卡池回归。"""
import argparse
from swarm_regression import ROOT, SETUP, LuaRuntime
from swarm_growth_regression import GROWTH_SETUP

EXTRA=r'''
A=require('Core.AbilityRuntime')
Cards=require('Core.CardSystem')
function grant(w,id)
 local def
 for _,c in ipairs(Config.Cards.definitions) do if c.id==id then def=c end end
 assert(def and def.implemented,id);A.Acquire(w,def);w.abilityRunId=w.abilityRunId or 1
end
function skill(w,id,target,request,s)
 return A.Execute(w,id,(s or w.player).id,target,request or id,w.abilityRunId or 1)
end
function liveMass(w)
 local count=w:ControlledCount()
 for _,v in ipairs(w.releasedViruses) do if A.Alive(v) then count=count+1 end end
 return count
end
'''
TESTS={
 '运动状态冲突优先、无效目标无成本和预约取消退冷却':r'''
local w=quietWorld();local c=unitCell(w);local s=w.player;w.cells={}
grant(w,'swarm_anchor');grant(w,'emergency_dash');grant(w,'membrane_glide')
assert(skill(w,'swarm_anchor'));w:SetMovement(1,0);w:SetMovement(0,0)
s.glideCellId=123;s.groupCommand={kind='hold'};s.launchTimer=1
assert(skill(w,'emergency_dash'));assert(not s.anchored and not s.glideCellId and not s.groupCommand and s.launchTimer==0)
local x=s.x;w:Update(cfg.movementStep);assert(s.x>x)
assert(skill(w,'swarm_anchor',nil,'anchor-again'));assert(s.anchored and not s.dashUntil)
assert(not skill(w,'membrane_glide','bad-target'));assert(s.anchored)
grant(w,'node_takeover');c.state='PRODUCTIVE';c.releaseCount=1;w.cells={c};place(w,s,c.x+.7,c.y)
assert(skill(w,'node_takeover',{cellId=c.id}));assert(c.takeoverReservation)
w:KillCell(c,'immune');assert(not c.takeoverReservation and not w.abilities.cooldowns.node_takeover)
assert(eventCount(w,'skill_failed')==1)
''',
 '回收最近群唯一归属和同距按ID打平':r'''
local w=manyGroups(2);w.cells={};grant(w,'discrete_recall')
local a,b=w.swarms[1],w.swarms[2];place(w,a,12,27.5);place(w,b,14,27.5)
a.recallUntil=10;b.recallUntil=10
local v={x=13,y=27.5,radius=cfg.virusRadius};local owner=A.RecallOwner(w,v)
assert(owner.id==math.min(a.id,b.id) and v.tractionOwnerId==owner.id)
v.x=13.5;owner=A.RecallOwner(w,v);assert(owner==b and v.tractionOwnerId==b.id)
b.isHidden=true;owner=A.RecallOwner(w,v);assert(owner==a)
''',
 '留守发现危险及时清安全目标，不借小脑权限漏检':r'''
local _,im=immuneFixture('macrophage')
local w=manyGroups(2);grant(w,'cluster_dispatch')
local s=w.swarms[2];s.launchTimer=0;local c=unitCell(w);w.cells={c}
s.groupCommand={kind='hold',cellId=c.id,point={x=c.x+.7,y=c.y}}
w.immunes={im};im.x,im.y=s.x+.2,s.y;im.state='warning';im.targetType='swarm';im.targetId=s.id
local x,y=A.Movement(w,s,1,0,1,cfg.movementStep)
assert(not s.groupCommand and not w.swarmBrainEnabled);near(x,0);near(y,0)
''',
 '免疫致命保全全局一次，先于灭团且真实脱离':r'''
local w,im=immuneFixture('macrophage');w.cells={};grant(w,'tail_preserve')
w:DamageSwarm(w.player.id,w.player.mass-2);local s=w.player
im.x,im.y=s.x,s.y;im.state='attack';im.targetType='swarm';im.targetId=s.id;im.attackTimer=cfg.movementStep
local x,y=s.x,s.y;Immune.Update(w,cfg.movementStep)
assert(w.abilities.tailSaved and s.mass==2 and #w.swarms==1)
local sim=Sim.New();sim.world=w;sim.started=true;sim.pauseReasons={};sim.paused=false
sim:CheckOutcome(0);assert(not sim.ending)
for _=1,20 do w.time=w.time+cfg.movementStep;A.Update(w,cfg.movementStep);w:_MoveGroups(cfg.movementStep) end
assert(distance(s,{x=x,y=y})>.6 and w.map:Contains(s.x,s.y,s.radius))
im.x,im.y=s.x,s.y;im.state='attack';im.attackTimer=cfg.movementStep;Immune.Update(w,cfg.movementStep)
sim:CheckOutcome(0);assert(sim.ending=='extinct' and #w.swarms==0)
local t=quietWorld();grant(t,'tail_preserve');t:DamageSwarm(t.player.id,t.player.mass)
assert(#t.swarms==0 and not t.abilities.tailSaved)
''',
 '合并播种默认开启守恒且冷却阻止刷量，关闭保留原合并':r'''
local w=manyGroups(3);grant(w,'merge_seed');local a,b,c=w.swarms[1],w.swarms[2],w.swarms[3]
place(w,a,13,27.5);place(w,b,13,27.5);place(w,c,13,27.5)
local before=liveMass(w);local released=w.stats.totalReleased
assert(w:_Merge(a,b));assert((w.massLedger.totals.merge_seed_investment or 0)>0)
assert(liveMass(w)==before and w.stats.totalReleased==released)
local invested=w.massLedger.totals.merge_seed_investment
assert(w:_Merge(a,c));assert(w.massLedger.totals.merge_seed_investment==invested and liveMass(w)==before)
assert(skill(w,'merge_seed'));assert(not w.abilities.mergeSeedEnabled)
w.time=30;w.splitCooldown=0;assert(w:Split())
local child=w.swarms[2];place(w,child,w.player.x,w.player.y);place(w,w.player,w.player.x,w.player.y)
local mass=liveMass(w);assert(w:_Merge(w.player,child));assert(liveMass(w)==mass and w.massLedger.totals.merge_seed_investment==invested)
''',
 '集群集合实际移动，留守无目标等待，Tab清命令':r'''
local w=manyGroups(3);w.cells={};grant(w,'cluster_dispatch')
local main=w.player;local child=w.swarms[2];local anchored=w.swarms[3]
for _,s in ipairs(w.swarms) do w:DamageSwarm(s.id,s.mass-20) end
place(w,main,12,27.5);place(w,child,15.5,27.5);place(w,anchored,13,30);anchored.anchored=true
assert(skill(w,'cluster_dispatch',{command='gather'}));assert(child.groupCommand and not anchored.groupCommand)
local d=distance(main,child);for _=1,120 do w:Update(cfg.movementStep) end
assert(distance(main,child)<d-.5 and not child.aiTargetCellId)
assert(w:SwitchControl(child.id));assert(not child.groupCommand and child.isPlayerControlled)
assert(skill(w,'cluster_dispatch',{command='hold'},'hold'));assert(main.groupCommand.kind=='hold' and not main.groupCommand.cellId)
local vx,vy=A.Movement(w,main,0,0,1,cfg.movementStep);near(vx,0);near(vy,0)
''',
 '破裂只散真实累积整数预算，不补未来且死亡一次':r'''
local w=quietWorld();grant(w,'rupture_spread');local c=unitCell(w);w.cells={c};w:_Infect(c,'player');age(w,28)
assert(c.releaseCount==1 and w.stats.totalReleased==3)
for _=1,600 do w.time=w.time+cfg.movementStep;A.Update(w,cfg.movementStep) end
assert(c.pendingProduction==2 and c.releaseCount==1)
local rng=w._rng;local produced=w.massLedger.totals.node_production
w:KillCell(c,'immune');assert(w.stats.totalReleased==4 and c.state=='DEAD' and c.pendingProduction==0)
assert(w.massLedger.totals.rupture_transfer==1 and w.massLedger.totals.node_budget_lost==1)
assert(w.massLedger.totals.node_production==produced and w._rng==rng)
local inflammation=w.globalInflammation;w:KillCell(c,'immune');assert(w.stats.totalReleased==4);near(w.globalInflammation,inflammation)
local t=quietWorld();grant(t,'rupture_spread');local latent=unitCell(t);t.cells={latent};t:_Infect(latent,'player')
t:KillCell(latent,'immune');assert(t.stats.totalReleased==0)
local q=quietWorld();local n=unitCell(q);n.state='PRODUCTIVE';n.pendingProduction=4;q.cells={n};q:KillCell(n,'immune');assert(q.stats.totalReleased==0)
''',
 '未选卡生产时间线和随机序列保持一致，预算不提前产出':r'''
local w=quietWorld();local c=unitCell(w);w.cells={c};w:_Infect(c,'player')
local t=quietWorld();local n=unitCell(t);t.cells={n};t:_Infect(n,'player');grant(t,'rupture_spread')
local expectedTimes={28,46,64,82,100,118};local batches={3,5,7,8,8,6};local total=0;local index=1
for step=1,7200 do
 local dt=cfg.movementStep
 for _,pair in ipairs({{w,c},{t,n}}) do
  local world=pair[1];world.time=world.time+dt;A.Update(world,dt)
  world.diseaseAccum=world.diseaseAccum+dt
  if world.diseaseAccum+1e-9>=cfg.diseaseStep then world.diseaseAccum=world.diseaseAccum-cfg.diseaseStep;world:_AgeCells(cfg.diseaseStep) end
 end
 if index<=6 and w.time+1e-8>=expectedTimes[index] then
  total=total+batches[index];assert(w.stats.totalReleased==total and c.releaseCount==index);index=index+1
 end
 assert(w._rng==t._rng and w.stats.totalReleased==t.stats.totalReleased and c.state==n.state)
 assert((c.pendingProduction or 0)<=(cfg.releaseBatches[c.releaseCount+1] or 0))
end
assert(total==37 and w.stats.totalReleased==37)
''',
 '伪装只改变新发现，已有锁定不擦除，近距仍识别':r'''
local w,im=immuneFixture('macrophage');w.cells={};grant(w,'debris_camouflage')
local s=w.player;place(w,s,im.x+im.detectionRange*.8+s.radius,im.y);s.camouflaged=true
Immune.Update(w,cfg.movementStep);assert(not im.targetId)
s.camouflaged=false;Immune.Update(w,cfg.movementStep);assert(im.targetId==s.id)
s.camouflaged=true;Immune.Update(w,cfg.movementStep);assert(im.targetId==s.id)
im.state='patrol';im.targetId=nil;im.targetType=nil;require('Core.ImmuneDirector').Release(w,im)
place(w,s,im.x+s.radius+.7,im.y);s.camouflaged=true;Immune.Update(w,cfg.movementStep);assert(im.targetId==s.id)
''',
 '锚定抵抗流并保留感染吸收，玩家输入解除':r'''
local w=quietWorld();w.cells={};grant(w,'swarm_anchor')
local s=w.player;local x,y=s.x,s.y
assert(skill(w,'swarm_anchor'));s.vx,s.vy=3,3
for _=1,60 do w:Update(cfg.movementStep) end
near(s.x,x);near(s.y,y);assert(s.anchored)
w:SetMovement(1,0);w:Update(cfg.movementStep);assert(not s.anchored and s.x>x)
assert(w:Split());local child=w.swarms[2];child.mergeGrace=100;child.launchTimer=0
assert(skill(w,'swarm_anchor',nil,'child-anchor',child));x,y=child.x,child.y
w.swarmBrainEnabled=true;for _=1,60 do w:Update(cfg.movementStep) end
near(child.x,x);near(child.y,y);assert(child.anchored and not child.aiTargetCellId)
''',
 '藏身唯一存活群可退出，节点死亡损失一次不误判':r'''
local s=newSim('DEEP_LUNG',true);local w=s.world;grant(w,'node_hide')
local c=unitCell(w);c.state='PRODUCTIVE';w.cells={c};place(w,w.player,c.x+.7,c.y)
local p=w.player;local mass=p.mass;local x,y=p.x,p.y
assert(skill(w,'node_hide',{cellId=c.id}));assert(p.isHidden and w:LiveSwarmCount()==1 and w.currentControlledSwarmId==0)
s:CheckOutcome(0);assert(not s.ending)
w.time=w.time+3;assert(skill(w,'node_hide',{exit=true},'exit',p))
assert(not p.isHidden and w.currentControlledSwarmId==p.id);near(p.x,x);near(p.y,y)
w.time=w.time+3;assert(skill(w,'node_hide',{cellId=c.id},'enter-again',p))
w:KillCell(c,'immune');assert(not p.isHidden and p.mass==mass-math.ceil(mass*.5))
local lost=w.massLedger.totals.hide_node_loss;w:KillCell(c,'immune');assert(w.massLedger.totals.hide_node_loss==lost)
''',
 '节点保护仅抵挡一次且合法接触事件不丢失':r'''
local w,im=immuneFixture('tcell');grant(w,'node_cover');local c=unitCell(w);w.cells={c};w:_Infect(c,'player')
place(w,w.player,c.x+.7,c.y);local mass=w.player.mass
assert(skill(w,'node_cover',{cellId=c.id}));assert(w.player.mass==mass-4 and c.shieldHits==1)
local damage,inflammation=w.globalTissueDamage,w.globalInflammation
im.state='attack';im.targetType='cell';im.targetId=c.id;im.attackTimer=cfg.movementStep
im.x,im.y=c.x,c.y;w.events={};Immune.Update(w,cfg.movementStep)
assert(c.shieldHits==0 and c.immuneHits==0);near(w.globalTissueDamage,damage);near(w.globalInflammation,inflammation)
assert(eventCount(w,'node_attack')==1)
w.time=20;assert(not skill(w,'node_cover',{cellId=c.id},'again'));assert(w.player.mass==mass-4)
im.state='attack';im.attackTimer=cfg.movementStep;Immune.Update(w,cfg.movementStep)
assert(c.immuneHits==1)
''',
 '节点接管产出转移守恒，预约满额取消不生成':r'''
local w=quietWorld();grant(w,'node_takeover');local c=unitCell(w);c.state='PRODUCTIVE';c.releaseCount=1;w.cells={c}
place(w,w.player,c.x+.7,c.y);w:_Release(c,5)
local before=liveMass(w);local rng=w._rng
assert(skill(w,'node_takeover',{cellId=c.id}));assert(w:LiveSwarmCount()==2 and w.swarms[2].mass==5)
assert(liveMass(w)==before and w._rng==rng);assert(not A.Alive(w.releasedViruses[1]))
assert(not w:_AbsorbReleased(w.player,w.releasedViruses[1]));assert(w.swarms[2].mass<12)
w:DamageSwarm(w.swarms[2].id,5);w.time=25
assert(skill(w,'node_takeover',{cellId=c.id},'reserve'));assert(c.takeoverReservation)
assert(w:Split());local mass=liveMass(w);w:_Release(c,5)
assert(w:LiveSwarmCount()==2 and liveMass(w)==mass+5 and not c.takeoverReservation)
assert(eventCount(w,'skill_failed')==1)
''',
 '拖尾按主动距离转移，不按帧流或冲刺生成':r'''
local w=quietWorld();w.cells={};grant(w,'infection_trail');grant(w,'emergency_dash')
assert(skill(w,'infection_trail'));local mass=w.player.mass
for _=1,120 do w:Update(cfg.movementStep) end
assert(not w.massLedger.totals.trail_investment)
w:SetMovement(1,0);for _=1,90 do w:Update(cfg.movementStep) end
assert((w.massLedger.totals.trail_investment or 0)>=1)
local invested=w.massLedger.totals.trail_investment;assert(skill(w,'emergency_dash'))
for _=1,20 do w:Update(cfg.movementStep) end
assert(w.massLedger.totals.trail_investment==invested)
assert(liveMass(w)==mass)
''',
 '局部转流同源保流速，到期准确还原且无质量变化':r'''
local w=quietWorld();grant(w,'local_flow');local s=w.player
local fx,fy=w.map:FlowAt(s.x,s.y,0);local mass=liveMass(w)
assert(skill(w,'local_flow',{x=s.x+1,y=s.y}))
local bx,by=w.map:FlowAt(s.x,s.y,0)
near(by,0);near(bx,math.sqrt(fx*fx+fy*fy));assert(liveMass(w)==mass)
local before=w.map.flowOverride;w.map.flowOverride=nil
local ex,ey=w.map:FlowAt(s.x,s.y,11);w.map.flowOverride=before
local ax,ay=w.map:FlowAt(s.x,s.y,11);near(ax,ex);near(ay,ey)
''',
 '感染接力留下真实三颗续感染，完成后转游离':r'''
local w=quietWorld();grant(w,'membrane_glide');local c=unitCell(w);w.cells={c}
local s=w.player;place(w,s,c.x+c.radius+s.radius*.75,c.y)
w:_AccumulateExposure(.5);w:_InfectCells();assert(skill(w,'membrane_glide',{cellId=c.id}))
local team=w.swarms[2];assert(team.mass==3 and s.mass==27 and team.relayCellId==c.id)
assert(w:LiveSwarmCount()==2 and not w:_CanMergePair(s,team))
place(w,s,13,30);progress(w,16)
assert(c.state=='LATENT' and not w:SwarmById(team.id) and liveMass(w)==30)
''',
 '残骸伪装停留生效，感染移动解除且不改速度':r'''
local w=quietWorld();grant(w,'debris_camouflage');local c=unitCell(w);c.state='DEAD';w.cells={c}
place(w,w.player,c.x+.7,c.y);local s=w.player;local speed=cfg.baseSpeed
for _=1,190 do w:Update(cfg.movementStep) end
assert(s.camouflaged and cfg.baseSpeed==speed)
w:SetMovement(1,0);for _=1,25 do w:Update(cfg.movementStep) end
assert(not s.camouflaged)
c.state='HEALTHY';w:SetMovement(0,0);place(w,s,c.x+.6,c.y);s.camouflaged=true
w:_AccumulateExposure(.01);assert(not s.camouflaged and c._charge>0)
''',
 '真实诱饵转移，失败和重复请求不扣量':r'''
local w=quietWorld();w.cells={};grant(w,'shed_decoy')
local before=liveMass(w);local mass=w.player.mass
assert(skill(w,'shed_decoy'));assert(w.player.mass==mass-4 and #w.viruses==mass-4)
assert(#w.releasedViruses==4 and liveMass(w)==before and w.stats.totalReleased==0)
assert(w.massLedger.totals.decoy_investment==4)
assert(not skill(w,'shed_decoy'));assert(liveMass(w)==before)
w.time=30;assert(not A.Execute(w,'shed_decoy',w.player.id,nil,'shed_decoy',999))
assert(not skill(w,'shed_decoy'));assert(w.player.mass==mass-4)
w:DamageSwarm(w.player.id,w.player.mass-6)
local cooldown=w.abilities.cooldowns.shed_decoy
assert(not skill(w,'shed_decoy',nil,'insufficient'))
assert(w.player.mass==6 and w.abilities.cooldowns.shed_decoy==cooldown)
''',
 '冲刺须真实方向、碰撞合法且不计主动阶段位移':r'''
local w=quietWorld();w.cells={};grant(w,'emergency_dash')
assert(not skill(w,'emergency_dash'));w:SetMovement(1,0);w:SetMovement(0,0)
assert(skill(w,'emergency_dash'));local x=w.player.x
for _=1,15 do w:Update(cfg.movementStep);assert(w.map:Contains(w.player.x,w.player.y,w.player.radius));near(w.player.activeMoveDistanceStep,0) end
assert(w.player.x>x+.8 and w.player.mass==30)
for _=1,30 do w:Update(cfg.movementStep) end
assert(not w.player.dashUntil and w.player.vx==0)
''',
 '回收实际移动后吸收，单颗牵引唯一且不越地图':r'''
local w=quietWorld();grant(w,'discrete_recall')
local list=releaseAt(w,1,w.player.x+2.5,w.player.y);local v=list[1]
w.cells={};local mass=w.player.mass;local x=v.x
assert(skill(w,'discrete_recall'));assert(w.player.mass==mass)
w:Update(cfg.movementStep);assert(v.x<x and v.tractionOwnerId==w.player.id and w.player.mass==mass)
for _=1,200 do w:Update(cfg.movementStep);assert(w.map:Contains(v.x,v.y,v.radius)) end
assert(w.player.mass==mass+1 and w.massLedger.totals.absorb_recovery==1)
''',
 '技能计时暂停，旧局请求失效且结束禁止使用':r'''
local s=newSim('DEEP_LUNG',true);grant(s.world,'discrete_recall')
releaseAt(s.world,1,s.world.player.x+2,s.world.player.y);s.world.cells={}
assert(s:UseSkill('discrete_recall',s.world.player.id,nil,'one',s.cards.runId))
local untilTime=s.world.player.recallUntil;local time=s.time
s:SetPaused('observation',true);s:Update(60)
assert(s.world.time==time and s.world.player.recallUntil==untilTime)
s:SetPaused('observation',false);s:Update(.1);assert(s.world.time>time)
local old=s.cards.runId;s:StartRun('DEEP_LUNG');grant(s.world,'discrete_recall')
assert(not s:UseSkill('discrete_recall',s.world.player.id,nil,'old',old))
s:FinishRun('extinct');assert(not s:UseSkill('discrete_recall',s.world.player.id))
''',
 '新卡名单无旧倍率，前置生效且全程共享':r'''
assert(#Config.Cards.definitions==18)
local cards=Cards.New();local eligible=cards:GetEligibleCards(1)
for _,c in ipairs(Config.Cards.definitions) do assert(not c.effect and not c.minRound) end
assert(not cards:Eligibility('swarm_capacity_6',1,false))
assert(cards:Eligibility('swarm_capacity_4',1,false))
cards.acquired.swarm_capacity_4=true;assert(cards:Eligibility('swarm_capacity_6',1,false))
local w=quietWorld();assert(require('Core.CardEffects').Value(w,'latencyExtra')==0)
''',
}

def run(only=''):
 results=[]
 for name,code in TESTS.items():
  if only and only not in name: continue
  lua=LuaRuntime(unpack_returned_tuples=True)
  lua.execute("package.path="+repr(str(ROOT/'scripts/?.lua').replace('\\','/'))+"..';'..package.path")
  try:
   lua.execute(SETUP+GROWTH_SETUP+EXTRA+code)
   print('PASS',name);results.append(True)
  except Exception as error:
   print('FAIL',name,str(error));results.append(False)
 print(f'Mechanism: {sum(results)}/{len(results)}')
 return all(results)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--only',default='')
 raise SystemExit(0 if run(p.parse_args().only) else 1)
