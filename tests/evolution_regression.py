"""真实 Lua 六阶段、卡牌效果与正式选卡回归。"""
import argparse
from swarm_regression import ROOT, SETUP, LuaRuntime
from swarm_growth_regression import GROWTH_SETUP

EXTRA = r'''
Tracker=require('Core.EvolutionTracker')
Effects=require('Core.CardEffects')
Cards=require('Core.CardSystem')
function apply(w,id)
 local card
 for _,c in ipairs(Config.Cards.definitions) do if c.id==id then card=c end end
 assert(card);Effects.Apply(w,card)
end
function observe(s,seconds)
 local dt=cfg.movementStep
 for _=1,math.floor(seconds/dt+.5) do s.evolution:Observe(s.world,dt,s.victoryQualified) end
end
function choose(s)
 local p=assert(s.cards.pending);local id=p.cards[1].id
 assert(s:CommitCardChoice(p.id,id));assert(not s:CommitCardChoice(p.id,id))
 assert(s.cardNotice and s.paused);assert(s:ContinueAfterCard());assert(not s:ContinueAfterCard())
end
function infectRegion(w,regionId,count)
 local result={}
 for _,cell in ipairs(w.cells) do
  if cell.regionId==regionId and (cell.state=='HEALTHY' or cell.state=='EXPOSED') and #result<count then
   w:_Infect(cell,'fixture');result[#result+1]=cell
  end
 end
 assert(#result==count,'insufficient fixture cells in region '..regionId)
 return result
end
function fullNetwork(s)
 local a=infectRegion(s.world,1,4);local b=infectRegion(s.world,5,4)
 age(s.world,cfg.latentSeconds);s:ConsumeEvents()
 return a,b
end
function addThirdRegion(s)
 local added=infectRegion(s.world,3,4)
 age(s.world,cfg.latentSeconds);s:ConsumeEvents()
 return added
end
function finalFixture()
 local s=newSim('UPPER_AIRWAY',true)
 fullNetwork(s);addThirdRegion(s)
 s.evolution:Enter(6,0,s.world);s.evolution:BeginFinal(s.world);s.formalFinished=true
 return s,s.world
end
function diseaseLevel(w,fraction,damage)
 for _,region in ipairs(w.map.regions) do region.inflammation=0;region.damage=0 end
 w.globalInflammation,w.globalTissueDamage=0,0
 local inflammation=damage and 2*cfg.hotspotThreshold or cfg.irreversibleInflammation*fraction
 local tissue=damage and cfg.irreversibleDamage*fraction or 0
 w:AddInflammation(1,inflammation/2,tissue/2);w:AddInflammation(5,inflammation/2,tissue/2)
end
'''

TESTS = {
    '阶段二节点被杀且无产物时改为重建不会死锁': r'''
local s=newSim('UPPER_AIRWAY',true);local w=s.world
local first=infectRegion(w,1,1)[1];s:ConsumeEvents()
s.evolution:Enter(2,w.time,w);w:KillCell(first,'tcell');s:ConsumeEvents();s:UpdateTasks()
assert(s.evolution.recoveryFallback and not s.task.complete and s.task.progress==0)
assert(s.task.text:find('重建感染网络'))
infectRegion(w,1,1);s:ConsumeEvents();s:UpdateTasks();assert(s.task.progress==1 and not s.cards.pending)
infectRegion(w,1,1);s:ConsumeEvents();s:UpdateTasks();assert(s.cards.pending)
local choice=s.cards.pending.id;s:UpdateTasks();assert(s.cards.pending.id==choice)
choose(s);assert(s.stage==3 and not s.evolution.recoveryFallback)
''',
    '阶段二死节点的存活产物以及耗竭节点仍支持正常回收': r'''
local s=newSim('UPPER_AIRWAY',true);local w=s.world
local first=infectRegion(w,1,1)[1];w:_Release(first,1);s:ConsumeEvents()
s.evolution:Enter(2,w.time,w);w:KillCell(first,'tcell');s:ConsumeEvents();s:UpdateTasks(false)
assert(not s.evolution.recoveryFallback)
local v=w.releasedViruses[1];v.x,v.y=w.player.x,w.player.y
assert(s:AbsorbNearby()>0);s:ConsumeEvents();s:UpdateTasks(false)
assert(s.evolution.recoveryDone and not s.evolution.recoveryFallback)
local s=newSim('UPPER_AIRWAY',true);local w=s.world
local first=infectRegion(w,1,1)[1];first.state='EXHAUSTED';s.evolution:Enter(2,w.time,w)
assert(not s.evolution:Status(w).complete and not s.evolution.recoveryFallback)
''',
    '真实正式卡池千局六轮与调试权重补位': r'''

for seed=1,1000 do
 local c=Cards.New();local w=quietWorld();local randomSeed=seed
 local function random() randomSeed=(randomSeed*48271)%2147483647;return randomSeed/2147483647 end
 if seed%3==0 then c.weightOverride={COMMON=0,RARE=0,EPIC=100} end
 for round=1,6 do
  local ok,p=c:GrantCardChoice('history',random);assert(ok,tostring(p))
  assert(#p.cards==3 and p.round==round)
  local seen={}
  for _,card in ipairs(p.cards)do
   assert(not seen[card.id] and not c.acquired[card.id]);seen[card.id]=true
   assert(round>=(card.minRound or 1))
   for _,id in ipairs(card.prerequisites or {})do assert(c.acquired[id]) end
  end
  local pick=p.cards[math.floor(random()*3)+1].id
  assert(c:CommitCardChoice(p.id,pick,w));assert(not c:CommitCardChoice(p.id,pick,w))
 end
 assert(c.formalCount==6 and w.immuneAlertLevel==6)
end

''',
    '小卡池失败无暂停无轮次历史，正式阶段开放': r'''

local s=newSim('UPPER_AIRWAY',true);s.cards=Cards.New({Config.Cards.definitions[1]})
infectRegion(s.world,1,2);age(s.world,cfg.latentSeconds);s:ConsumeEvents()
s:UpdateTasks();assert(s.cardChoiceError and not s.paused and s.cards.round==0)
assert(not next(s.cards.lastOfferedRound) and s.stage==1)
local c=Cards.New();assert(#c:GetEligibleCards(1)==17)
assert(c:Eligibility('swarm_local_brain',1,false));assert(c:Eligibility('swarm_local_brain',4,false))
assert(c:Eligibility('rupture_spread',1,false));assert(c:Eligibility('rupture_spread',6,false))
assert(not c:Eligibility('swarm_capacity_6',6,false));c.acquired.swarm_capacity_4=true
assert(c:Eligibility('swarm_capacity_6',6,false))

''',
    '机制卡不延迟潜伏生产，不增加免费产量': r'''

local w=quietWorld();local c=unitCell(w);w.cells={c};w:_Infect(c,'player')
for _,def in ipairs(Config.Cards.definitions) do Effects.Apply(w,def) end
age(w,28);assert(c.state=='PRODUCTIVE' and c.releaseCount==1 and w.stats.totalReleased==3)
age(w,18);assert(c.releaseCount==2 and w.stats.totalReleased==8)
assert(cfg.latentSeconds==28 and cfg.releaseInterval==18 and cfg.exhaustedSeconds==35)
local before=w.stats.totalReleased;w:KillCell(c,'exhausted');assert(w.stats.totalReleased==before)

''',
    '第一阶段只需一个新细胞真实首次产出且死亡不撤销': r'''

local s=newSim('UPPER_AIRWAY',true);local w=s.world
local c=infectRegion(w,1,1)[1];s:ConsumeEvents();s:UpdateTasks()
assert(not s.task.complete and not s.cards.pending)
age(w,cfg.latentSeconds-cfg.diseaseStep);s:ConsumeEvents();s:UpdateTasks();assert(not s.cards.pending)
age(w,cfg.diseaseStep);w:KillCell(c,'immune');s:ConsumeEvents();s:UpdateTasks()
assert(c.hasReleasedVirus and s.task.complete and s.cards.pending)
local before=w.time;s:Update(60);near(w.time,before)
choose(s);assert(s.stage==2 and not s.task.complete and not s.cards.pending)

''',
    '开局节点仅参与同时产毒不提供阶段一新感染': r'''

local s=newSim('DEEP_LUNG',true);local w=s.world
age(w,cfg.latentSeconds);s:ConsumeEvents();s:UpdateTasks(false)
assert(not s.task.complete)
local added=infectRegion(w,1,1);age(w,cfg.latentSeconds);s:ConsumeEvents();s:UpdateTasks(false)
assert(s.task.complete)
local nodes=infectRegion(w,1,2);age(w,cfg.latentSeconds);s:ConsumeEvents()
s.evolution:Enter(3,w.time,w);assert(w:Counts().productive>=3 and not s.evolution:Status(w).complete)

''',
    '进入EXPOSED和重放感染产出事件均不制造进度': r'''

local s=newSim('UPPER_AIRWAY',true);local w=s.world
local c=w.cells[1];c.state='EXPOSED';c.exposure=.99
s.evolution:Consume(w,{{name='infection_complete',payload={cellId=c.id,source='player'}},
 {name='release_batch',payload={cellId=c.id,count=3}}})
assert(not s.evolution:Status(w).complete and w.stats.totalInfected==0)
w:_Infect(c,'player');w:_Infect(c,'released');assert(w.stats.totalInfected==1)
s:ConsumeEvents();assert(not s.evolution:Status(w).complete)

''',
    '阶段二回收前感染不计而回收后两次感染有效': r'''

local s=newSim('UPPER_AIRWAY',true);local w=s.world
local c=infectRegion(w,1,1)[1];age(w,cfg.latentSeconds)
s.evolution:Enter(2,w.time,w);infectRegion(w,1,2)
local v=w.releasedViruses[1];v.x,v.y=w.player.x,w.player.y
assert(s:AbsorbNearby()>0)
local baseline=w.stats.totalInfected
infectRegion(w,1,1);s:ConsumeEvents();s:UpdateTasks()
assert(s.evolution.recoveryDone and s.evolution.recoveryStartInfections==baseline)
assert(s.task.progress==1 and not s.cards.pending)
infectRegion(w,1,1);s:ConsumeEvents();s:UpdateTasks();assert(s.cards.pending)

''',
    '阶段二排除空按被动吸收旧回收及诱饵拖尾合并播种': r'''

local s=newSim('UPPER_AIRWAY',true);local w=s.world
local c=infectRegion(w,1,1)[1];w:_Release(c,2)
local a,b=w.releasedViruses[1],w.releasedViruses[2]
assert(w:_AbsorbReleased(w.player,a,'basic'))
s.evolution:Enter(2,w.time,w);s:ConsumeEvents();assert(not s.evolution.recoveryDone)
assert(w:_AbsorbReleased(w.player,b));s:ConsumeEvents();assert(not s.evolution.recoveryDone)
assert(s:AbsorbNearby()==0);s:ConsumeEvents();assert(not s.evolution.recoveryDone)
local A=require('Core.AbilityRuntime')
for _,kind in ipairs({'decoy','trail','merge_seed','relay_return'}) do
 local particles=A.TakeMass(w,w.player,1,'fixture')
 local v=A.SpawnReleased(w,particles,w.player.x,w.player.y,kind)[1]
 assert(not v.nodeProduced and w:_AbsorbReleased(w.player,v,'basic'))
end
s:ConsumeEvents();assert(not s.evolution.recoveryDone)

''',
    '主动离散回收实际吸入节点产物才推进且事件去重': r'''

local s=newSim('UPPER_AIRWAY',true);local w=s.world
apply(w,'discrete_recall');s.evolution:Enter(2,0,w)
local c=infectRegion(w,1,1)[1];local vs=releaseAt(w,1,w.player.x,w.player.y)
assert(vs[1].nodeProduced);assert(s:UseSkill('discrete_recall',w.player.id))
assert(not s.evolution.recoveryDone)
w:_MoveReleased(cfg.movementStep)
local events=w.events;s.evolution:Consume(w,events);s.evolution:Consume(w,events)
assert(s.evolution.recoveryDone and s.evolution.recoveryCount==1 and vs[1].state=='ABSORBED')

''',
    '回收提示区分无节点等待释放和可回收产物': r'''

local s=newSim('UPPER_AIRWAY',true);local w=s.world;s.evolution:Enter(2,0,w)
assert(s.evolution:Status(w).hint:find('已切换重建目标'))
assert(s.evolution.recoveryFallback)
local s=newSim('UPPER_AIRWAY',true);local w=s.world;s.evolution:Enter(2,0,w)
local c=infectRegion(w,1,1)[1]
assert(s.evolution:Status(w).hint:find('等待它释放'))
w:_Release(c,1);assert(s.evolution:Status(w).hint:find('按E吸附'))

''',
    '阶段三只计本阶段新节点首次释放且已产毒旧节点不计': r'''

local s=newSim('UPPER_AIRWAY',true);local w=s.world
local old=infectRegion(w,1,3);age(w,cfg.latentSeconds);s:ConsumeEvents()
s.evolution:Enter(3,w.time,w);assert(w:Counts().productive>=3)
assert(s.evolution:Status(w).progress==0 and not s.evolution:Status(w).complete)
local c=infectRegion(w,1,3);assert(s.evolution:Status(w).progress==0)
age(w,cfg.latentSeconds);w:KillCell(c[1],'immune');s:ConsumeEvents()
assert(s.evolution:Status(w).complete)
s:UpdateTasks();local id=s.cards.pending.id
s:UpdateTasks();assert(s.cards.pending.id==id and s.cards.round==1)

''',
    '跨阶段已起步的接触完成后不计入新阶段': r'''
local s=newSim('UPPER_AIRWAY',true);local w=s.world
local a,b
for _,c in ipairs(w.cells) do if c.regionId==1 and c.state=='HEALTHY' then if not a then a=c elseif not b then b=c end end end
-- 真实病程步：a 在进入阶段前开始接触，进入后才完成感染。
a._charge=.6;w:_InfectCells();assert(a.state=='EXPOSED' and a.contactSerial)
s.evolution:Enter(4,w.time,w);s:UpdateTasks(false);assert(s.task.progress==0)
a._charge=.6;w:_InfectCells();assert(a.state=='LATENT')
s:UpdateTasks(false);assert(s.task.progress==0 and s.task.hint:find('上一阶段'))
-- b 在阶段开始后才起步，完成即计入。
b._charge=.6;w:_InfectCells();b._charge=.6;w:_InfectCells();assert(b.state=='LATENT')
s:UpdateTasks(false);assert(s.task.progress==1)
-- 接触中断（exposure 归零）后重新起步，算作本阶段新的接触。
local c
for _,x in ipairs(w.cells) do if x.regionId==1 and x.state=='HEALTHY' then c=x;break end end
c._charge=.3;w:_InfectCells();local stamp=c.contactSerial
s.evolution:Enter(5,w.time,w);c._charge=-1;w:_InfectCells();assert(c.state=='HEALTHY' and not c.contactSerial)
c._charge=.6;w:_InfectCells();assert(c.contactSerial>stamp);c._charge=.6;w:_InfectCells()
s:UpdateTasks(false);assert(s.task.progress==1)
''',
    '阶段四五六各自累计4_8_12且旧感染死亡和事件重放不误计': r'''

local s=newSim('UPPER_AIRWAY',true);local w=s.world
local old=infectRegion(w,1,4);s:ConsumeEvents()
for stage=4,6 do
 s.evolution:Enter(stage,w.time,w);s:UpdateTasks(false);assert(s.task.progress==0)
 local target=Config.Evolution.expansion[stage]
 local added={}
 for _,c in ipairs(w.cells) do if (c.state=='HEALTHY' or c.state=='EXPOSED') and #added<target then
   w:_Infect(c,#added%2==0 and 'released' or 'player');added[#added+1]=c
 end end
 assert(#added==target)
 for _,c in ipairs(added) do w:KillCell(c,'immune') end
 s:ConsumeEvents();assert(s.evolution:Status(w).complete)
 for _=1,3 do s.evolution:Consume(w,{{name='infection_complete',payload={cellId=old[1].id,source='player'}}}) end
 assert(w.stats.totalInfected==4+(stage==4 and 4 or stage==5 and 12 or 24))
 assert(s.evolution:Status(w).progress==target)
end

''',
    '关说明前的同一步感染不流入下一阶段': r'''

local s=newSim('UPPER_AIRWAY',true);local w=s.world
s.evolution:Enter(4,0,w);infectRegion(w,1,6);s:ConsumeEvents();s:UpdateTasks();assert(s.cards.pending)
local id=s.cards.pending.id;local card=s.cards.pending.cards[1].id
assert(s:CommitCardChoice(id,card));local before=w.time;s:Update(60);near(w.time,before)
assert(s:ContinueAfterCard());assert(s.stage==5 and s.task.progress==0 and not s.cards.pending)
s:ConsumeEvents();s:UpdateTasks();assert(s.task.progress==0)

''',
    '教程累计阶段一但教程结束前不发卡': r'''

local s=newSim('UPPER_AIRWAY',true);local w=s.world
s.tutorial={active=true,Allows=function() return false end,Observe=function() end}
infectRegion(w,1,1);age(w,cfg.latentSeconds);s:ConsumeEvents();s:UpdateTasks()
assert(s.task.complete and not s.cards.pending)
s.tutorial.active=false;s.tutorial.Allows=function() return true end
s:UpdateTasks();assert(s.cards.pending)

''',
    '第六阶段没有病理等待第六卡后再新增四个且没有第七卡': r'''

local s=newSim('UPPER_AIRWAY',true);local w=s.world
fullNetwork(s);addThirdRegion(s);s.evolution:Enter(6,0,w)
infectRegion(w,1,4);infectRegion(w,3,4);infectRegion(w,5,4);s:ConsumeEvents();s:UpdateTasks()
assert(s.cards.pending and s.task.complete and not s.victoryQualified)
choose(s);assert(s.formalFinished and s:CanAct() and not s.ending)
s:CheckOutcome(0);assert(not s.ending)
s.globalInflammation=cfg.irreversibleInflammation;s:CheckOutcome(0)
assert(s.victoryQualified and not s.ending)
infectRegion(w,5,3);s:ConsumeEvents();s:CheckOutcome(0);assert(not s.ending)
local c=infectRegion(w,5,1)[1];w:KillCell(c,'immune');s:ConsumeEvents();s:CheckOutcome(0)
assert(s.ending=='victory' and not s.cards.pending)

''',
    '终局保留连续呼吸衰竭资格并切换文案': r'''

local s,w=finalFixture();s.mouse.respiration=cfg.minRespiration
s:CheckOutcome(cfg.respirationFailureSeconds);assert(s.victoryQualified and not s.ending)
s:UpdateTasks(false);assert(s.task.text:find('完成最后扩张') and not s.task.text:find('损伤'))
s.mouse.respiration=1;s:CheckOutcome(0);assert(s.victoryQualified)
infectRegion(w,3,4);s:ConsumeEvents();s:CheckOutcome(0);assert(s.ending=='victory')

''',
    '提前病理资格仍需扩张且可能灭团失败': r'''

local s,w=finalFixture();s.globalTissueDamage=cfg.irreversibleDamage;s:CheckOutcome(0)
assert(s.victoryQualified and not s.ending)
w:DamageSwarm(w.player.id,w.player.mass);s:CheckOutcome(0)
assert(s.ending=='extinct' and not s.irreversible)

''',
    '终局基线排除待处理感染且全部死亡后保留新增': r'''

local s,w=finalFixture();infectRegion(w,3,4);s.evolution:BeginFinal(w);s:ConsumeEvents()
assert(not s.evolution:FinalStatus(w,true).complete)
local a=infectRegion(w,5,4)
for _,c in ipairs(a) do w:KillCell(c,'immune') end
s:ConsumeEvents();assert(s.evolution:FinalStatus(w,true).complete)
assert(not s.evolution:FinalStatus(w,false).complete)

''',
    '终局扩张同一步满足病理与清群仍胜利优先': r'''

local s,w=finalFixture();infectRegion(w,3,4);s:ConsumeEvents()
s.globalInflammation=cfg.irreversibleInflammation;w:DamageSwarm(w.player.id,w.player.mass);s:CheckOutcome(0)
assert(s.ending=='victory')

''',
    '体验计时包含选卡排除教程暂停且重开清空': r'''

local s=newSim('UPPER_AIRWAY',true)
s:TrackExperience(10);s:SetPaused('settings',true);s:TrackExperience(6);s:SetPaused('settings',false)
s.tutorial={active=true,Allows=function() return true end,Observe=function() end,Stop=function() end}
s:TrackExperience(7);s.tutorial.active=false
assert(s:GrantCardChoice('fixture'));s:TrackExperience(8)
local p=s.cards.pending;assert(s:CommitCardChoice(p.id,p.cards[1].id));s:TrackExperience(4)
assert(s:ContinueAfterCard());s:RecordFlow('sample')
local r=s.flowTimeline[#s.flowTimeline]
near(r.experience,22);near(r.choice,12);near(r.pause,6);near(r.tutorial,7)
assert(s:StartRun('UPPER_AIRWAY'));near(s.experience.active,0);near(s.experience.choice,0)
assert(Config.Gameplay.targetDurationMin==900 and Config.Gameplay.targetDurationMax==1200)

''',
    '六次选卡自然顺序无分群强制且各边界只发一次': r'''

local s=newSim('UPPER_AIRWAY',true);local w=s.world
infectRegion(w,1,1);age(w,cfg.latentSeconds);s:ConsumeEvents();s:UpdateTasks();choose(s)
local v=w.releasedViruses[1];v.x,v.y=w.player.x,w.player.y;assert(s:AbsorbNearby()>0)
infectRegion(w,1,2);s:ConsumeEvents();s:UpdateTasks();choose(s)
age(w,cfg.latentSeconds);s:ConsumeEvents();s:UpdateTasks();assert(not s.cards.pending)
infectRegion(w,1,3);age(w,cfg.latentSeconds);s:ConsumeEvents();s:UpdateTasks();choose(s)
for stage=4,6 do
 local count=Config.Evolution.expansion[stage];local added=0
 for _,c in ipairs(w.cells) do if c.state=='HEALTHY' and added<count then w:_Infect(c,'released');added=added+1 end end
 assert(added==count);s:ConsumeEvents();s:UpdateTasks();assert(s.cards.pending)
 choose(s);assert(s.cards.formalCount==stage and not s.cards.pending)
end
assert(s.formalFinished and w.immuneAlertLevel==6 and w.stats.totalSplits==0)
local offers,completes=0,0
for _,r in ipairs(s.flowTimeline) do if r.kind=='offer' then offers=offers+1 elseif r.kind=='complete' then completes=completes+1 end end
assert(offers==6 and completes==6)

''',
}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--only',default='');args=parser.parse_args()
    failed=0;total=0
    for name,code in TESTS.items():
        if args.only and args.only not in name: continue
        total+=1
        lua=LuaRuntime(unpack_returned_tuples=True)
        lua.execute("package.path="+repr(str(ROOT/'scripts/?.lua').replace('\\','/'))+"..';'..package.path")
        logs=[];lua.globals().print=lambda *a:logs.append(' '.join(map(str,a)))
        try:
            lua.execute(SETUP+GROWTH_SETUP+EXTRA+code);print('PASS',name)
        except Exception as error:
            failed+=1;print('FAIL',name,error)
            for line in logs[-6:]:print(' LOG',line)
    print(f'{total-failed}/{total} passed')
    return int(failed>0)

if __name__=='__main__':raise SystemExit(main())
