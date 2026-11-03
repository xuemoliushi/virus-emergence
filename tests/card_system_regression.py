"""卡牌、群体容量、小脑和警戒的真实 Lua 5.4 回归。"""
import argparse
import time
from swarm_regression import ROOT, SETUP, LuaRuntime
from swarm_growth_regression import GROWTH_SETUP

EXTRA = r'''
Cards=require('Core.CardSystem')
Director=require('Core.ImmuneDirector')
AI=require('Core.SplitVirusAI')
function getCard(s,id)
 local ok,reason=s:AcquireTestCard(id);assert(ok,tostring(reason));s:ContinueAfterCard()
end
function immuneAt(w,kind,x,y)
 local base=assert(w.immunes[1]);local im={}
 for key,value in pairs(base)do im[key]=value end
 im.id=#w.immunes+100;im.kind=kind;im.x,im.y=x,y
 im._patrolX,im._patrolY,im._oldX,im._oldY=x,y,x,y
 im.regionId=w.map:RegionAt(x,y)
 im.targetType,im.targetId=nil,nil;im.state='patrol';im.cooldown=0
 w.immunes[#w.immunes+1]=im
 return im
end
'''

TESTS={
'跨局旧请求失效，关闭卡牌只解除自身暂停':r'''
local s=newSim();local ok,old=s.cards:BeginTestChoice('swarm_capacity_4');assert(ok)
assert(s:StartRun('UPPER_AIRWAY'))
local ok,new=s.cards:BeginTestChoice('swarm_capacity_4');assert(ok and old.id~=new.id)
assert(not s:CommitCardChoice(old.id,'swarm_capacity_4'))
assert(s:CommitCardChoice(new.id,'swarm_capacity_4'))
s:SetPaused('observation',true);s:ContinueAfterCard()
assert(s.paused and s.pauseReasons.observation and not s.pauseReasons['card-alert'])
''',
'III活跃信号仅局部可见，攻击仍须完整预警':r'''
local w,im=immuneFixture('tcell');local c=unitCell(w)
c.state='PRODUCTIVE';c.releaseCount=2;w.cells={c};w.immunes={im}
c.x,c.y=im.x+im.detectionRange*1.1+c.radius,im.y
assert(w.map:Contains(c.x,c.y,c.radius))
Immune.Update(w,cfg.movementStep);assert(not im.targetId)
w.activeImmuneAlertLevel=3;Immune.Update(w,cfg.movementStep)
assert(im.targetId==c.id and im.state=='locked' and im.warningTimer==2.2)
assert(c.immuneHits==0)
w:KillCell(c,'test');assert(not im.targetId and next(w.immuneReservations)==nil)
local released=w.stats.totalReleased;w:_Release(c,6);assert(w.stats.totalReleased==released)
''',
'小脑预约分散、危险滞回、隐藏威胁无全图感知':r'''
local w=quietWorld();w.maxPlayerSwarms=4;w.swarmBrainEnabled=true
growByAbsorption(w,160);assert(w:Split());w.splitCooldown=0;assert(w:Split())
local a,b,c=w.swarms[1],w.swarms[2],w.swarms[3]
place(w,a,13,3.1);place(w,b,12.5,27.4);place(w,c,13.3,27.4)
local ca=unitCell(w,1,12.4,29.4);local cb=unitCell(w,2,13.4,29.4);w.cells={ca,cb}
AI.ThinkWorld(w,.02);assert(b.aiTargetCellId and c.aiTargetCellId and b.aiTargetCellId~=c.aiTargetCellId)
local im={id=1,x=b.x+.8,y=b.y,radius=.48,state='patrol',kind='macrophage'};w.immunes={im}
b._aiThinkClock=0;AI.ThinkWorld(w,.02);assert(b.aiState=='flee' and not b.aiTargetCellId)
im.x=b.x+7
b._aiThinkClock=0;AI.ThinkWorld(w,.25);assert(b.aiState=='flee','危险记忆不能立即退出')
AI.ThinkWorld(w,2);assert(b.aiState~='flee','局部不可见的远敌不能持续驱动撤退')
w:KillCell(ca,'test');w:KillCell(cb,'test');AI.ThinkWorld(w,.3)
assert(b.aiState=='wander' and c.aiState=='wander','无目标且可通行时应有限探索')
assert(not b.aiTargetCellId and not c.aiTargetCellId)
assert(w.map:Contains(b._aiMoveX,b._aiMoveY,b.radius) and w.map:Contains(c._aiMoveX,c._aiMoveY,c.radius))
for _,owners in pairs(w.brainReservations)do assert(not next(owners)) end
''',
'预约到期回收，所有合法入口被占时延期而不空降':r'''
local w,im=immuneFixture('tcell');local c=unitCell(w);w:_Infect(c,'player')
local t={targetType='cell',id=c.id,x=c.x,y=c.y,radius=c.radius}
assert(Director.Reserve(w,im,t));w.time=Config.ImmuneAlert.reservationTimeout+.1
Director.Update(w,.1);assert(next(w.immuneReservations)==nil)
w.immunes={};w.map.immuneSpawns={{x=w.player.x,y=w.player.y}}
Immune.Recruit(w,cfg.immuneRecruitInterval);assert(#w.immunes==0)
assert(w._immuneRecruitClock==cfg.immuneRecruitInterval)
w.map.immuneSpawns={};Immune.Recruit(w,1);assert(#w.immunes==0)
''',
'默认两群与12门槛，所有分裂入口禁止超限和自动分裂':r'''
local w=quietWorld();assert(w.maxPlayerSwarms==2 and not w.swarmBrainEnabled)
w:DamageSwarm(w.player.id,19);assert(w.player.mass==11 and not w:CanSplit())
growByAbsorption(w,1);assert(w:CanSplit());local before=w:ControlledCount()
assert(w:Split());assert(w:ControlledCount()==before-1 and #w.swarms==2)
w.splitCooldown=0;growByAbsorption(w,50)
assert(not w:Split() and w:SplitUnavailableReason()=='群体数量已达上限')
assert(not w:_SplitSwarm(w.player,1,0,false) and not w:_SplitSwarm(w.player,1,0,true))
w.swarmBrainEnabled=true;assert(w:_AutoSplitGroups()==0)
checkConservation(w)
''',
'三张卡前置即时生效，不增质量与重复结算':r'''
local s=newSim();local w=s.world;local before=w:ControlledCount()
assert(not s:AcquireTestCard('swarm_capacity_6'))
assert(s:AcquireTestCard('swarm_capacity_4'))
assert(w.maxPlayerSwarms==4 and w:ControlledCount()==before and #w.swarms==1)
assert(w.immuneAlertLevel==1 and s.paused and s.cardNotice)
assert(not s:AcquireTestCard('swarm_capacity_4'));s:ContinueAfterCard()
assert(not s:AcquireTestCard('swarm_capacity_4'))
getCard(s,'swarm_capacity_6');getCard(s,'swarm_local_brain')
assert(w.maxPlayerSwarms==6 and w.swarmBrainEnabled and w.immuneAlertLevel==3)
assert(s.cards.acquisitionCount==3 and w:ControlledCount()==before)
assert(not s:CommitCardChoice(1,'swarm_capacity_4'))
''',
'六群循环稳定，隐藏占名额但不可切入，合并死亡可复用名额':r'''
local s=newSim();getCard(s,'swarm_capacity_4');getCard(s,'swarm_capacity_6')
local w=s.world;growByAbsorption(w,800)
for _=1,5 do w.splitCooldown=0;assert(w:Split()) end
assert(#w.swarms==6)
local ids={};for _,group in ipairs(w.swarms)do ids[#ids+1]=group.id end
for i=2,6 do assert(w:SwitchControl() and w.currentControlledSwarmId==ids[i]) end
assert(w:SwitchControl() and w.currentControlledSwarmId==ids[1])
local hidden=w.swarms[2];hidden.isHidden=true
assert(w:LiveSwarmCount()==6 and not w:SwitchControl(hidden.id))
assert(w:SwitchControl() and w.currentControlledSwarmId==ids[3])
w:DamageSwarm(w.player.id,w.player.mass);assert(w.currentControlledSwarmId~=ids[3])
assert(w:LiveSwarmCount()==5);growByAbsorption(w,50);w.splitCooldown=0;assert(w:Split())
hidden.isHidden=false;local a,b=w.swarms[1],w.swarms[2]
place(w,a,13,3.1);place(w,b,13,3.1);assert(w:_Merge(a,b))
assert(w:LiveSwarmCount()==5);w.splitCooldown=0;assert(w:Split())
checkConservation(w)
''',
'卡池不足不推进，测试入口独立于正式轮次':r'''
local s=newSim();s.cards=Cards.New({Config.Cards.definitions[7]});assert(#s:GetEligibleCards(1)==1)
local ok,reason=s:GrantCardChoice('debug');assert(not ok and string.find(reason,'不足'))
assert(s.cards.round==0 and next(s.cards.lastOfferedRound)==nil and not s.paused)
getCard(s,'swarm_capacity_4');assert(s.cards.round==0 and next(s.cards.lastOfferedRound)==nil)
''',
'测试定义验证六轮B3前置权重补位及重复提交':r'''
local w=quietWorld();local defs={}
for i=1,24 do defs[i]={id='test_'..i,rarity=i%2==0 and 'RARE' or 'EPIC',implemented=true} end
defs[24].prerequisites={'test_1'}
local c=Cards.New(defs);c.weightOverride={COMMON=100,RARE=0,EPIC=0}
local n=0;local function random() n=n+1;return (n%7)/7 end
local unselected=nil
for round=1,6 do
 local ok,choice=c:GrantCardChoice('fixture',random);assert(ok,tostring(choice))
 assert(#choice.cards==3 and choice.round==round)
 local seen={};for _,card in ipairs(choice.cards)do assert(not seen[card.id]);seen[card.id]=true end
 if round==1 then unselected=choice.cards[2].id end
 if round==2 or round==3 then assert(not seen[unselected]) end
 local selected=choice.cards[1].id
 assert(c:CommitCardChoice(choice.id,selected,w));assert(not c:CommitCardChoice(choice.id,selected,w))
 assert(c.acquired[selected])
 if round==3 then
  local pool=c:GetEligibleCards(4);local found=false
  for _,card in ipairs(pool)do if card.id==unselected then found=true end end
  assert(found,'第4轮应回池')
 end
end
assert(c.acquisitionCount==6 and w.immuneAlertLevel==6 and not c:GrantCardChoice('seventh',random))
''',
'小脑必须解锁，外围真实感染与接管释放预约':r'''
-- Isolate autonomous infection/control handoff from the now faster pursuers.
local s=newSim('UPPER_AIRWAY',true);local w=s.world;assert(w:Split());local a,b=w.swarms[1],w.swarms[2]
place(w,a,13,3.1);place(w,b,12.9,27.4)
local cell=unitCell(w,1,b.x+2,b.y);w.cells={cell}
cfg.playerFlowInfluence,cfg.splitFlowInfluence,cfg.inactiveDrift=0,0,0
step(w,1);assert(not AI.IsAutonomous(w,b) and b.aiTargetCellId==nil)
getCard(s,'swarm_local_brain');assert(w.maxPlayerSwarms==2)
step(w,1);assert(b.aiTargetCellId==cell.id and b.x>12.9 and w.brainReservations[cell.id][b.id])
local before=cell.exposure;assert(w:SwitchControl(b.id))
assert(b.aiTargetCellId==nil and b.vx==0 and b.vy==0 and not w.brainReservations[cell.id][b.id])
assert(cell.exposure==before)
assert(w:SwitchControl(a.id))
for _=1,math.floor(140/cfg.movementStep) do
 w:Update(cfg.movementStep)
 if cell.state=='LATENT' then break end
end
assert(cell.state=='LATENT','必须通过原接触感染实现')
assert(b.aiTargetCellId==nil and b.aiState=='idle')
assert(#w.swarms==2 and w.stats.totalAutoSplits==0)
checkConservation(w,true)
''',
'小脑连续避让细胞，流场不把意图推穿细胞':r'''
local w=quietWorld();w.swarmBrainEnabled=true;assert(w:Split());local b=w.swarms[2]
place(w,w.player,13,3.1);place(w,b,12.9,27.4)
local cell=unitCell(w,1,b.x+1.5,b.y);w.cells={cell}
local nx,ny=AI.RestrictCellMotion(w,b,b.x+5,b.y)
assert(nx<cell.x-cell.radius-b.radius and ny==b.y)
step(w,12)
assert(distance(b,cell)>=b.radius+cell.radius-.001,'自主运动必须停在膜外围')
assert(w.map:Contains(b.x,b.y,b.radius))
''',
'暂停警戒缓冲不推进，调试0到6不增加获得记录':r'''
local s=newSim();getCard(s,'swarm_capacity_4')
local w=s.world;assert(w.activeImmuneAlertLevel==0)
s:SetPaused('observation',true);simStep(s,10);near(w.pendingAlertActivation.remaining,5)
s:SetPaused('observation',false);simStep(s,4);assert(w.activeImmuneAlertLevel==0)
simStep(s,1.1);assert(w.activeImmuneAlertLevel==1 and not w.pendingAlertActivation)
for level=0,6 do
 assert(s:SetDebugImmuneAlertLevel(level));simStep(s,5.1)
 assert(w.activeImmuneAlertLevel==level and w.immuneAlertLevel==1 and s.cards.acquisitionCount==1)
end
assert(s:SetDebugImmuneAlertLevel(nil));simStep(s,5.1);assert(w.activeImmuneAlertLevel==1)
''',
'T不追群清游离，巨噬优先可见群且无群时清理病毒与残骸':r'''
local w,im=immuneFixture('tcell');w.cells={}
w:_Release(w._fixtureSource or World.New('UPPER_AIRWAY').cells[1],1)
for _,v in ipairs(w.releasedViruses)do v.x,v.y=im.x,im.y end
Immune.Update(w,cfg.movementStep);assert(not im.targetId)
im.kind='macrophage';Immune.Update(w,cfg.movementStep);assert(im.targetType=='swarm')
w.player.isHidden=true;Immune.Update(w,cfg.movementStep);Immune.Update(w,cfg.movementStep)
assert(im.targetType=='virus')
for _,v in ipairs(w.releasedViruses)do w:KillReleased(v)end
Immune.Update(w,cfg.movementStep);im.cooldown=0;im.state='patrol'
local c=World.New('UPPER_AIRWAY').cells[1];c.x,c.y,c.state,c.regionId=im.x,im.y,'DEAD',im.regionId
w.cells={c};Immune.Update(w,cfg.movementStep);assert(im.targetType=='cell')
advanceImmune(w,6);assert(w._immuneClearedDebris[c.id])
w.player.isHidden=false;advanceImmune(w,4);assert(im.targetType=='swarm')
''',
'节点单预约与一次破坏，免疫合法站位分离':r'''
local w,im=immuneFixture('tcell');local c=unitCell(w);w:_Infect(c,'player');w.cells={c}
im.x,im.y=c.x-1,c.y;im._oldX,im._oldY=im.x,im.y
local other=immuneAt(w,'tcell',im.x,im.y)
cfg.immuneNodeHits=1;local before=w.map.regions[c.regionId].inflammation
advanceImmune(w,12)
assert(c.state=='DEAD' and c.immuneHits==1 and eventCount(w,'cell_dead')==1 and eventCount(w,'node_attack')==1)
near(w.map.regions[c.regionId].inflammation-before,cfg.nodeAttackInflammation+cfg.deadInflammation)
assert(next(w.immuneReservations)==nil and not im.targetId and not other.targetId)
local p={targetType='swarm',id=w.player.id,x=w.player.x,y=w.player.y,radius=w.player.radius}
local point=assert(Director.AttackPoint(w,im,p));assert(w.map:Contains(point.x,point.y,im.radius))
im.state,other.state='patrol','patrol';other.x,other.y=im.x,im.y
Director.Separate(w,.5);assert(distance(im,other)>0)
''',
'局部失去感知停止坐标追踪，VI搜索旧位置且超时回巡逻':r'''
local w,im=immuneFixture('macrophage');w.cells={};w.activeImmuneAlertLevel=6
Immune.Update(w,cfg.movementStep);assert(im.targetType=='swarm')
local x,y=im.targetX,im.targetY
place(w,w.player,im.x+im.detectionRange+cfg.immuneForgetExtra+w.player.radius+.2,im.y)
Immune.Update(w,cfg.movementStep)
assert(im.state=='search' and im.targetId==nil and im.targetX==nil)
assert(im._searchX==x and im._searchY==y)
for _=1,600 do w.time=w.time+cfg.movementStep;Immune.Update(w,cfg.movementStep) end
assert(im.state~='search' and not im.targetId)
''',
'II局部密度，III节点响应，IV多点分工，V支路预警及数量预算':r'''
local w,im=immuneFixture('macrophage');w.activeImmuneAlertLevel=2
local c=unitCell(w);w:_Release(c,6)
for _,v in ipairs(w.releasedViruses)do v.x,v.y=im.x,im.y end
Director.Update(w,.5)
local target={targetType='virus',id=w.releasedViruses[1].id,x=im.x,y=im.y,radius=.045}
assert(Director.VisibleDensity(w,im,target,function()return true end)>0)
assert(Director.VisibleDensity(w,im,target,function()return false end)==0)
w.activeImmuneAlertLevel=4;w.patrolAssignments[999]=im.regionId
assert(Director.RegionPenalty(w,im,target)>0)
w.activeImmuneAlertLevel=5;im.state='patrol';im.targetId=nil;w._channelClock=0
Director.Update(w,.1);local assignment=assert(w.channelPatrolAssignments[im.id])
assert(assignment.startsAt>w.time and eventCount(w,'channel_patrol_warning')==1)
assert(Config.ImmuneAlert.channelMode=='branch_patrol')
w.time=assignment.untilTime+.1;Director.Update(w,.1);assert(not w.channelPatrolAssignments[im.id])
for _=1,30 do Immune.Recruit(w,cfg.immuneRecruitInterval) end
assert(#w.immunes<=math.min(cfg.immuneMax,Config.ImmuneAlert.maxImmuneUnits))
local t,m=0,0;for _,unit in ipairs(w.immunes)do
 if unit.kind=='tcell' then t=t+1 else m=m+1 end
 assert(w.map:Contains(unit.x,unit.y,unit.radius))
end
assert(t<=Config.ImmuneAlert.maxTCells and m<=Config.ImmuneAlert.maxMacrophages)
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
            for line in logs[-8:]:print(' LOG',line)
    print(f'{total-failed}/{total} passed')
    return int(failed>0)

if __name__=='__main__':raise SystemExit(main())
