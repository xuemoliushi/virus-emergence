"""真实Lua技能键盘/按钮回调；不代表引擎布局、物理输入验收。"""
import sys
from bird_ui_regression import SETUP,ROOT,LuaRuntime

EXTRA=r'''
-- Keep UI regressions reproducible; random map creation has its own suite.
Config.Gameplay.mapSeed=314159
Skills=require('UI.SkillPanel')
Controls=require('UI.SkillControls')
A=require('Core.AbilityRuntime')
function abilityFixture()
 local h,g,s,scale,obs=hudFixture()
 guidedStart(h,s,scale,obs,'DEEP_LUNG')
 s.world._skillSource=s.world.cells[1]
 s.world.immunes={};s.world.cells={}
 return h,g,s
end
function unlock(s,id)
 for _,c in ipairs(Config.Cards.definitions) do if c.id==id then A.Acquire(s.world,c) end end
end
function node(s)
 local p=s.world.player
 local c={id=999,x=p.x+.7,y=p.y,radius=.4,state='LATENT',regionId=s.world.map:RegionAt(p.x,p.y)}
 s.world.cells={c};return c
end
function recallTarget(s)
 local w=s.world;local p=w.player
 w:_Release(w._skillSource or w.cells[1],1)
 local v=w.releasedViruses[#w.releasedViruses];v.x,v.y=p.x,p.y;v.requiresActiveRecovery=true
end
'''
TESTS={
 '技能释放提示分成标题正文和取消行且宽度不依赖快捷按钮数':r'''
local h,g,s=abilityFixture();unlock(s,'membrane_glide');unlock(s,'node_cover');unlock(s,'local_flow')
local content=h.root:FindById('hudContent')
for _,id in ipairs({'membrane_glide','node_cover','local_flow'}) do
 assert(Controls.Activate(h,id));Skills.Refresh(h)
 assert(h.root:FindById('skillTargetTitle'):GetText():find(s.cards:Definition(id).name,1,true))
 for _,size in ipairs({{1920,1080},{1280,720},{960,540},{640,360}}) do
  content.rect={x=0,y=0,w=size[1],h=size[2]};h.layoutWidth_=0;h:ApplyLayout()
  local prompt=h.root:FindById('skillTargetPrompt');local body=h.root:FindById('skillTargetText')
  local cancel=h.root:FindById('skillCancel')
  assert(prompt.parent==h.root and prompt.props.flexDirection=='column' and prompt.props.height=='auto')
  assert(prompt.props.width>=300 and prompt.props.width+prompt.props.right<=size[1])
  assert(body.props.width=='100%' and body.props.flexShrink==0 and body.props.flexBasis=='auto')
  assert(body.props.whiteSpace=='normal' and body.props.minFontSize==12)
  assert(cancel.props.width==120 and cancel.props.height==36 and not cancel.assetIcon_:IsVisible())
 end
 callback(h,'skillCancel');assert(not s.skillSelection)
end
''',
 '桌面技能名称和说明分开排版且窗口变小时仍可滚动选择':r'''
local h,g,s=abilityFixture()
unlock(s,'node_cover');unlock(s,'discrete_recall');unlock(s,'cluster_dispatch')
Controls.Toggle(h);Skills.Refresh(h)
local row=h.root:FindById('skillMenu_1')
local title=h.root:FindById('skillMenu_1_title');local detail=row.assetDetail_
assert(row.props.text==nil and title:GetText()==row:GetText() and row:GetText():find(s.cards:Definition('node_cover').name,1,true))
assert(detail:GetText():find('投入') and detail.props.height==nil and detail.props.position==nil)
assert(title.parent==detail.parent and title.parent.props.minWidth==0)
local childCount=#row.children
for i=1,20 do Skills.Refresh(h) end
assert(#row.children==childCount,'refresh must reuse the text widgets')
local content=h.root:FindById('hudContent')
for _,size in ipairs({{1920,1080},{1280,720},{960,540},{640,360}}) do
 content.rect={x=0,y=0,w=size[1],h=size[2]};h.layoutWidth_=0;h:ApplyLayout()
 local popup=h.root:FindById('skillMenuPopup').props
 assert(popup.height+popup.bottom<=size[2] and popup.width<=size[1])
 assert(row.props.height=='auto' and row.props.flexShrink==0)
 assert(h.root:FindById('skillMenuFooter').parent==h.root:FindById('skillMenuPopup'))
end
local dispatch=h.root:FindById('skillMenu_3');dispatch:OnClick();Skills.Refresh(h)
assert(s.skillMenu.page=='dispatch' and row:GetText():find('集合'))
assert(row.assetIcon_.props.backgroundImage:find('cluster_dispatch'))
h.root:FindById('skillMenuClose'):OnClick();assert(not s.skillMenu)
''',
 '感染接力从V菜单选择目标并通过E主动回收':r'''
local h,g,s=abilityFixture();unlock(s,'membrane_glide')
local w=s.world;local c=w._skillSource;local p=w.player;local before=p.mass
c.x,c.y=p.x+.8,p.y;c.regionId=w.map:RegionAt(c.x,c.y)
c.state='HEALTHY';c.exposure=0;c._charge=0;c._groupCharge=0;c._releasedCharge=0
c.everPlayerContact=false;w.cells={c}
w:_AccumulateExposure(.5);w:_InfectCells()
assert(s.cards:Definition('membrane_glide').name=='感染接力')
assert(Controls.Activate(h,'membrane_glide') and s.skillSelection)
assert(Skills.Pick(s,c.x,c.y));assert(not s.skillSelection and #w.swarms==2)
local t=w.swarms[2];assert(t.relayCellId==c.id and p.mass==before-3)
assert(Controls.Hint('membrane_glide'):find('E',1,true))
assert(s:AbsorbNearby()==3 and #w.swarms==1 and p.mass==before)
''',
 'E基础吸附3秒全群冷却、暂停冻结、切群不可绕过':r'''
local h,g,s=abilityFixture();local w=s.world;local source=w._skillSource
assert(s:Split());local first=w.player
w:_Release(source,1);local v=w.releasedViruses[#w.releasedViruses];v.x,v.y=first.x,first.y
assert(s:AbsorbNearby()==1);near(w:GetAbsorptionCooldown(),3)
assert(s:SwitchControl());local second=w.player
w:_Release(source,1);local nextVirus=w.releasedViruses[#w.releasedViruses]
nextVirus.x,nextVirus.y=second.x,second.y
local mass=second.mass;local count,reason=s:AbsorbNearby()
assert(count==0 and reason:find('冷却') and second.mass==mass)
s:SetPaused('test',true);for _=1,300 do s:Update(.1) end;near(w:GetAbsorptionCooldown(),3)
s:SetPaused('test',false)
-- 冷却期间自动近距吸收仍执行，不被E的冷却阻断。
w:_MoveReleased(Config.Gameplay.movementStep);assert(nextVirus.state=='ABSORBED')
for _=1,181 do s:Update(1/60) end;near(w:GetAbsorptionCooldown(),0)
Skills.Refresh(h);assert(h.root:FindById('skillKeyHint'):GetText():find('就绪'))
''',
 'E空放计冷却，拒绝请求无脉冲；重开清理且回收冷却独立':r'''
local h,g,s=abilityFixture();unlock(s,'discrete_recall');local w=s.world
local count,reason=s:AbsorbNearby();assert(count==0 and reason==nil)
near(w:GetAbsorptionCooldown(),3);local events=#w.events
count,reason=s:AbsorbNearby();assert(count==0 and reason and #w.events==events)
recallTarget(s);Controls.Toggle(h);assert(Controls.Select(h,1));near(w.abilities.cooldowns.discrete_recall-w.time,18)
near(w:GetAbsorptionCooldown(),3);assert(w.player.recallUntil)
assert(s:StartRun('DEEP_LUNG'));near(s.world:GetAbsorptionCooldown(),0)
''',
 'main键盘路由2仅用于菜单，空格分裂且选卡屏蔽技能':r'''
require('main');BuildGame();local root=UI.GetRoot();local game=root:FindById('gameScene')
local s,scale=game.sim,game.scaleMgr
local function click(id) root:FindById(id):OnClick() end
local function key(k,repeatKey) HandleKeyDown('KeyDown',{GetInt=function() return k end,GetBool=function() return repeatKey or false end}) end
assert(s.started and not root:FindById('anatomyToggleBtn') and not root:FindById('startRunBtn'))
settleScale(scale);HandleUpdate('Update',{GetFloat=function() return .2 end});s.world.immunes={}
unlock(s,'infection_trail');unlock(s,'discrete_recall');unlock(s,'emergency_dash');unlock(s,'shed_decoy')
key(KEY_2);assert(#s.world.swarms==1 and not s.world.player.recallUntil)
key(KEY_V,true);assert(not s.skillMenu);key(KEY_V);assert(s.skillMenu)
recallTarget(s)
key(KEY_2);assert(s.world.player.recallUntil and not s.skillMenu)
key(KEY_SPACE);assert(#s.world.swarms==2)
s.world:SetMovement(1,0);s.world:SetMovement(0,0);key(KEY_LSHIFT)
assert(s.world.player.dashUntil)
assert(s:GrantCardChoice('input-test'));local mass=s.world.player.mass
key(KEY_F);key(KEY_V);key(KEY_SPACE);key(KEY_E)
assert(not s.skillMenu and s.world.player.mass==mass and s.world:GetAbsorptionCooldown()==0)
''',
 'Shift立即冲刺，方向失败保留点选，重复与冷却不重复执行':r'''
local h,g,s=abilityFixture();unlock(s,'emergency_dash');unlock(s,'node_cover')
Controls.Activate(h,'node_cover');local selected=s.skillSelection
assert(not Controls.HandleKey(h,KEY_LSHIFT,false));assert(s.skillSelection==selected)
assert(s.skillMessage:find('移动方向') and not s.world.abilities.cooldowns.emergency_dash)
s.world:SetMovement(1,0);s.world:SetMovement(0,0)
assert(not Controls.HandleKey(h,KEY_LSHIFT,true));assert(not s.world.player.dashUntil)
assert(Controls.HandleKey(h,KEY_LSHIFT,false));assert(not s.skillSelection and s.world.player.dashUntil)
local cd=s.world.abilities.cooldowns.emergency_dash
Controls.HandleKey(h,KEY_RSHIFT,false);assert(s.world.abilities.cooldowns.emergency_dash==cd)
Skills.Refresh(h);assert(h.root:FindById('quickDash'):GetText():find('Shift'))
''',
 'F按钮与键盘共用真实诱饵投入与失败提示':r'''
local h,g,s=abilityFixture();unlock(s,'shed_decoy');local w=s.world;local mass=w.player.mass
callback(h,'quickDecoy');assert(w.player.mass==mass-4 and #w.releasedViruses==4)
assert(w.massLedger.totals.decoy_investment==4)
Controls.HandleKey(h,KEY_F,false);assert(w.player.mass==mass-4 and #w.releasedViruses==4)
Skills.Refresh(h);assert(h.root:FindById('quickDecoy'):IsDisabled())
assert(h.root:FindById('quickDecoy_detail'):GetText():find('投入4'))
''',
 'V数字启动离散回收，无Q绑定且菜单期间不暂停':r'''
local h,g,s=abilityFixture();unlock(s,'swarm_capacity_4');unlock(s,'discrete_recall');unlock(s,'emergency_dash')
assert(Controls.HandleKey(h,KEY_V,false));Skills.Refresh(h)
assert(s.skillMenu and not s.paused and #Controls.Entries(s)==1)
assert(h.root:FindById('skillMenu_1'):GetText():find('离散回收'))
assert(not Controls.HandleKey(h,'Q',false));assert(not s.world.player.recallUntil)
local time=s.time;s:Update(.1);assert(s.time>time and s.skillMenu)
recallTarget(s)
assert(Controls.HandleKey(h,KEY_1,false));assert(not s.skillMenu and not s.skillSelection)
near(s.world.player.recallUntil,s.world.time+6)
assert(not Controls.HandleKey(h,KEY_1,false),'关闭菜单后数字键无玩法动作')
Controls.Toggle(h);assert(not Controls.Select(h,1));assert(s.skillMenu and s.skillMessage:find('冷却'))
''',
 '获取顺序编号稳定，被动与专属快捷技能不占数字':r'''
local h,g,s=abilityFixture()
for _,id in ipairs({'node_cover','emergency_dash','swarm_capacity_4','discrete_recall','shed_decoy','infection_trail'}) do unlock(s,id) end
unlock(s,'node_cover');Controls.Toggle(h)
recallTarget(s)
local entries=Controls.Entries(s);assert(#entries==3 and entries[1].id=='node_cover' and entries[2].id=='discrete_recall')
Controls.Select(h,2);Controls.Toggle(h);assert(Controls.Entries(s)[2].id=='discrete_recall')
Skills.Refresh(h);assert(h.root:FindById('passiveSkills'):GetText():find('分裂扩容'))
assert(h.root:FindById('skillKeyHint'):GetText():find('Shift') and h.root:FindById('skillKeyHint'):GetText():find('F'))
''',
 '目标点击立即执行，非法目标无成本且可重试':r'''
local h,g,s=abilityFixture();unlock(s,'node_cover');local c=node(s);local mass=s.world.player.mass
Controls.Activate(h,'node_cover');c.x=c.x+5
assert(Skills.Pick(s,c.x,c.y));assert(s.skillSelection and s.world.player.mass==mass and not c.shieldHits)
c.x=c.x-5;assert(Skills.Pick(s,c.x,c.y));assert(not s.skillSelection and c.shieldHits==1)
assert(s.world.player.mass==mass-4 and not s.paused)
assert(not Skills.Pick(s,c.x,c.y));assert(s.world.player.mass==mass-4)
''',
 '独存藏身群可从V子菜单独立退出':r'''
local h,g,s=abilityFixture();unlock(s,'node_hide');local c=node(s);local p=s.world.player;local x,y=p.x,p.y
assert(s:UseSkill('node_hide',p.id,{cellId=c.id}));assert(s.world.currentControlledSwarmId==0)
s.world.time=s.world.time+3;Controls.Toggle(h);assert(Controls.Select(h,1))
assert(s.skillMenu.page=='hide');Skills.Refresh(h)
assert(#Controls.Entries(s)==1 and h.root:FindById('skillMenu_1'):GetText():find('离开节点'))
assert(Controls.Select(h,1));assert(not p.isHidden and s.world.currentControlledSwarmId==p.id)
near(p.x,x);near(p.y,y)
''',
 '指定锚定分群与调度子菜单':r'''
local h,g,s=abilityFixture();unlock(s,'swarm_anchor');unlock(s,'cluster_dispatch')
assert(s:Split());local child=s.world.swarms[2];child.mergeGrace=100;child.x=s.world.player.x+2
Controls.Activate(h,'swarm_anchor');assert(Skills.Pick(s,child.x,child.y))
assert(child.anchored and not s.world.player.anchored)
Controls.Activate(h,'cluster_dispatch');assert(s.skillMenu.page=='dispatch')
assert(not Controls.Select(h,1));assert(not child.groupCommand and s.skillMessage:find('可调度'),'锚定群不参与集合')
assert(not h.root:FindById('cardInfoBtn'):IsVisible())
''',
 'Tab分裂暂停失焦菜单重开和死亡清除菜单及目标':r'''
local h,g,s=abilityFixture();unlock(s,'node_cover');unlock(s,'discrete_recall')
Controls.Toggle(h);assert(s:Split());assert(not s.skillMenu)
Controls.Activate(h,'node_cover');assert(s:SwitchControl());assert(not s.skillSelection)
Controls.Toggle(h);s:SetPaused('test',true);assert(not s.skillMenu)
s:SetPaused('test',false);Controls.Toggle(h);input.focus=false;Skills.Refresh(h);assert(not s.skillMenu)
assert(not Controls.HandleKey(h,KEY_V,false));input.focus=true
Controls.Activate(h,'node_cover');s:SetPaused('mainMenu',true);assert(not s.skillSelection)
s:SetPaused('mainMenu',false);h:Update(.2)
Controls.Toggle(h);local old=s.cards.runId;assert(s:StartRun('DEEP_LUNG'))
assert(s.cards.runId~=old and not s.skillMenu and not s.skillSelection and #s.world.abilities.order==0)
unlock(s,'node_cover');Controls.Activate(h,'node_cover');s.world:DamageSwarm(s.world.player.id,s.world.player.mass)
Skills.Refresh(h);assert(not s.skillSelection)
''',
 'Esc和V取消不扣质量，不重复创建请求结算':r'''
local h,g,s=abilityFixture();unlock(s,'node_cover');local c=node(s);local mass=s.world.player.mass
Controls.Activate(h,'node_cover');local old=s.skillSelection
Controls.HandleKey(h,KEY_ESCAPE,false);assert(not s.skillSelection and s.world.player.mass==mass)
Controls.Toggle(h);Controls.HandleKey(h,KEY_V,false);assert(not s.skillMenu)
Controls.Activate(h,'node_cover');Skills.Pick(s,c.x,c.y)
local newMass=s.world.player.mass;old.target={cellId=c.id}
assert(not Controls.Execute(s,old));assert(s.world.player.mass==newMass)
''',
 '正式选卡弹窗与主菜单暂停屏蔽技能和菜单':r'''
local h,g,s=abilityFixture();unlock(s,'discrete_recall');unlock(s,'shed_decoy')
h.cardInfoShown_=true;local mass=s.world.player.mass
assert(not Controls.HandleKey(h,KEY_F,false) and not Controls.HandleKey(h,KEY_V,false))
assert(s.world.player.mass==mass and not s.skillMenu)
h.cardInfoShown_=false;s:SetPaused('mainMenu',true);assert(not Controls.HandleKey(h,KEY_V,false))
''',
}
if __name__=='__main__':
 failed=[]
 for name,code in TESTS.items():
  lua=LuaRuntime(unpack_returned_tuples=True)
  lua.execute('package.path='+repr(str(ROOT/'scripts/?.lua').replace('\\','/'))+"..';'..package.path")
  lua.globals().print=lambda *a:None
  try:lua.execute(SETUP+EXTRA+code);print('PASS',name)
  except Exception as error:failed.append(name);print('FAIL',name,error)
 print(f'Mechanism UI: {len(TESTS)-len(failed)}/{len(TESTS)}')
 sys.exit(bool(failed))
