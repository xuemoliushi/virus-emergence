"""Exercise real gesture, ability and layout state; engine input/storage are boundaries."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.tmp/test-deps'))
from bird_ui_regression import runtime
from compact_ui_regression import SMALL

SETUP = SMALL + r'''
graphics.width=924;graphics.height=520
UI.GetWidth=function() return graphics.width end;UI.GetHeight=function() return graphics.height end
UI.Slider=UI.Panel
local L=require('UI.ControlLayout')
local stored
cjson={encode=function(t) stored=L.Clean(t);return 'layout' end,decode=function() return stored end}
fileSystem={FileExists=function() return stored~=nil end}
File=function(_,mode) return {IsOpen=function() return true end,Close=function() end,Dispose=function() end,
 ReadString=function() return 'layout' end,WriteString=function() return true end} end
local h,g,s=fixture();require('UI.MobileLayout').MarkTouch();h.layoutWidth_=0;h:ApplyLayout()
local t=h.touchControls_;assert(t)
local function acquire(id)
 for _,card in ipairs(Config.Cards.definitions) do if card.id==id then require('Core.AbilityRuntime').Acquire(s.world,card);return end end
 error(id)
end
local function e(id,x,y)
 return {pointerId=id,x=x,y=y,buttons=1,IsPrimaryAction=function() return true end,
 IsMouse=function() return false end,PreventDefault=function() end,StopPropagation=function() end}
end
local function down()
 UI.Input.pointers[2]={pointerType='touch'}
 t.wheel:OnPointerDown(e(2,754,320));assert(t.gesture);t:Update(.2)
end
local function select(index)
 local z=t.gesture;local a=-math.pi/2+(index-1)*2*math.pi/#z.entries
 return e(2,z.x+math.cos(a)*z.radius,z.y+math.sin(a)*z.radius)
end
'''

CASES = {
    'uniform size limits and legacy layouts preserve button diameters': r'''
local value=L.Clean(nil)
for _,size in ipairs({L.minScale,1.5,L.maxScale}) do
 local expected
 for _,id in ipairs(L.ids) do
  L.Put(value,id,300,300,size,924,520)
  local d=L.Bounds(value,id,924,520).d
  expected=expected or d;assert(d==expected,'equal size settings must produce equal diameters')
 end
end
local old=L.Clean({version=1,controls={joystick={x=.2,y=.7,scale=1},absorbBtn={x=.8,y=.8,scale=1}}})
assert(old.version==2 and L.Bounds(old,'joystick',924,520).d==132)
assert(L.Bounds(old,'absorbBtn',924,520).d==92)
assert(L.Clean(old).controls.joystick.scale==old.controls.joystick.scale,'migration must run once')
t:Edit();assert(t.sizeSlider.Render and t.sizeSlider.props.thumbSize==28)
assert(t.sizeSlider.props.min==L.minScale and t.sizeSlider.props.max==L.maxScale);t:Finish(false)
''',
    'tutorial movement remains available while skills are locked': r'''
local Tutorial=require('Core.Tutorial')
s.tutorial=Tutorial.New(s);s.tutorial:StartIfNeeded()
t:Refresh();assert(not t.zone:IsVisible(),'explanation must still pause movement')
for _=1,2 do
 for _=1,8 do s.tutorial:Update(.1) end
 s.tutorial:Continue();s.tutorial:Update(.05)
end
assert(s.tutorial.step=='infect' and s:CanUseAction('move') and not s:CanUseAction('skill'))
t:Update(.001);assert(t.zone:IsVisible(),'movement tutorial lost its touch surface because skills are locked')
UI.Input.pointers[1]={pointerType='touch'}
t.zone.props.onPointerDown(e(1,130,370));t.zone.props.onPointerMove(e(1,170,370))
assert(h.joystickPointer_==1 and h.joystick_:IsVisible() and s.touchMove.x>.9)
local x=s.world.player.x;local dx,dy=g:ReadMovement(g:GetAbsoluteLayout())
s.world:SetMovement(dx,dy);s:Update(.1);assert(s.world.player.x>x,'touch must move the real player')
t.zone.props.onPointerUp(e(1,170,370));assert(not s.touchMove.active)
s:SetPaused('settings',true);t:Refresh();assert(not t.zone:IsVisible())
''',
    'only acquired skills appear in play and editor; layout entry lives in settings': r'''
t:Refresh();assert(not h.root:FindById('controlLayoutButton'))
assert(not t.wheel:IsVisible())
for _,id in ipairs({'swarm_anchor','infection_trail','merge_seed'}) do assert(not t.buttons[id]:IsVisible()) end
acquire('debris_camouflage');t:Refresh();assert(not t.wheel:IsVisible())
t:Edit();assert(t.handles.joystick and t.handles.absorbBtn and not t.handles.skillWheel and not t.handles.swarm_anchor)
L.Put(t.draft,'swarm_anchor',859,452,1,t.w,t.h);t:Finish(true);assert(not t.editor,'invisible skills must not block save')
acquire('infection_trail');t:Refresh();assert(t.buttons.infection_trail:IsVisible() and not t.wheel:IsVisible())
acquire('discrete_recall');t:Refresh();assert(t.wheel:IsVisible())
t:Edit();assert(t.handles.skillWheel and t.handles.infection_trail and not t.handles.merge_seed)
assert(t.handles.skillWheel.assetIcon_ and t.handles.infection_trail.assetIcon_)
t:Finish(false);down();local slot=t.ring:FindById('radialSlot_1')
assert(slot.assetIcon_ and slot.touchCaption_.props.text=='离散回收')
t:Cancel();s.world.abilities.owned.discrete_recall=nil;t:Refresh();assert(not t.wheel:IsVisible())
''',
    'fresh tutorial completes through joystick, real infection, collection, split and switch': r'''
local Tutorial=require('Core.Tutorial');s.tutorial=Tutorial.New(s);s.tutorial:StartIfNeeded()
local lesson=s.tutorial
local O=require('UI.TutorialOverlay');g.viewport={x=0,y=0,w=924,h=520}
g.cellView.WorldToScreen=function(_,x,y) return 462+x*4,260+y*4 end
local overlay=O.New(s,g)
local frames,moving=0,0
local function release()
 if h.joystickPointer_ then t.zone.props.onPointerUp(e(41,130,370)) end
 UI.Input.pointers[41]=nil
end
local function frame(target)
 frames=frames+1
 if s.cards.pending then
  release();finishCardReveal(h)
  callback(h,'cardGet_'..s.cards.pending.cards[1].id);callback(h,'cardContinue')
 end
 t:Refresh()
 if target and s:CanUseAction('move') then
  assert(t.zone:IsVisible(),'touch surface missing in '..lesson.step)
  if not h.joystickPointer_ then UI.Input.pointers[41]={pointerType='touch'};t.zone.props.onPointerDown(e(41,130,370)) end
  local p=s.world.player;local dx,dy=target.x-p.x,target.y-p.y;local d=math.max(1e-6,math.sqrt(dx*dx+dy*dy))
  t.zone.props.onPointerMove(e(41,130+40*dx/d,370+40*dy/d));moving=moving+1
 else release() end
 local dx,dy=g:ReadMovement(g:GetAbsoluteLayout());s.world:SetMovement(dx,dy)
 s:Update(1/60);lesson:Update(1/60);h:Update(1/60);overlay:Update()
end
local function continueLesson()
 for _=1,30 do frame() end
 assert(overlay.continueButton:IsVisible());overlay.continueButton.props.onClick();frame()
end
continueLesson();assert(lesson.step=='target');continueLesson();assert(lesson.step=='infect')
assert(not s:CanUseAction('skill') and s:CanUseAction('move'))
for _=1,9000 do if lesson.step~='infect' then break end;frame(assert(lesson:Target())) end
assert(lesson.step=='wait','failed real touch infection at '..lesson.step)
local infected=lesson:Cell();assert(infected and infected.infectionSource=='player')
for _=1,2000 do if lesson.step~='wait' then break end;frame() end
assert(lesson.step=='collect' and infected.releaseCount>=1)
for _=1,900 do
 if lesson.step~='collect' then break end
 frame(lesson:Target());if s.world:GetAbsorptionCooldown()<1e-9 then callback(h,'absorbBtn') end
end
assert(lesson.step=='split' and s.world.stats.totalAbsorbed>0)
release();callback(h,'splitBtn');frame();assert(lesson.step=='switch' and s.world.stats.totalSplits==1)
callback(h,'switchBtn');frame();assert(lesson.step=='switch_done' and s.world.controlSwitchCount==1)
for _=1,200 do if lesson.step~='switch_done' then break end;frame() end
assert(lesson.step=='tcell');continueLesson();assert(lesson.step=='macrophage');continueLesson();assert(lesson.step=='escape')
local p=s.world.player;local exit={x=p.x+.9,y=p.y}
for _=1,240 do if lesson.step~='escape' then break end;frame(exit) end
assert(lesson.step=='task')
for _=1,600 do if not lesson.active then break end;frame() end
assert(not lesson.active and lesson.completed and moving>0 and not s.ending)
release();assert(not s.touchMove.active)
touchTutorialEvidence={frames=frames,movingFrames=moving,time=s.time,infected=s.world.stats.totalInfected,
 released=s.world.stats.totalReleased,absorbed=s.world.stats.totalAbsorbed,splits=s.world.stats.totalSplits,switches=s.world.controlSwitchCount}
''',
    'press origin stays fixed through long drags, independent fingers and pause cleanup': r'''
assert(not h.root:FindById('touchMoveGuide') and not h.root:FindById('joystickHint'):IsVisible())
UI.Input.pointers[1]={pointerType='touch'}
t.zone.props.onPointerDown(e(1,130,370));assert(h.joystickPointer_==1 and h.joystick_:IsVisible())
assert(t.center.x==130 and t.center.y==370 and s.touchMove.x==0 and s.touchMove.y==0)
t.zone.props.onPointerUp(e(1,130,370))
t.zone.props.onPointerDown(e(1,10,510));assert(t.center.x==10 and t.center.y==510 and s.touchMove.x==0 and s.touchMove.y==0)
t.zone.props.onPointerUp(e(1,10,510));t.zone.props.onPointerDown(e(1,130,370))
t.zone.props.onPointerMove(e(9,180,380));assert(s.touchMove.x==0)
t.zone.props.onPointerMove(e(1,200,370));assert(s.touchMove.x>.9 and s.touchMove.active)
local baseX,baseY=h.joystick_.props.left,h.joystick_.props.top
t.zone.props.onPointerMove(e(1,470,90))
assert(t.center.x==130 and t.center.y==370,'long drag must not move the press origin')
assert(h.joystick_.props.left==baseX and h.joystick_.props.top==baseY,'joystick base drifted')
assert(s.touchMove.x>0 and s.touchMove.y<0 and s.touchMove.x^2+s.touchMove.y^2<=1.000001)
t.zone.props.onPointerMove(e(1,130,370));assert(s.touchMove.x==0 and s.touchMove.y==0,'return to original center must stop movement')
t.zone.props.onPointerMove(e(1,200,370))
acquire('discrete_recall');down();assert(t.gesture.pointer==2 and h.joystickPointer_==1)
t.zone.props.onPointerUp(e(1,200,370));assert(not s.touchMove.active and not h.joystick_:IsVisible() and t.gesture)
t:Up(e(1,754,320));assert(t.gesture)
s:SetPaused('test',true);t:Update(.1);assert(not t.gesture)
h:Update(.2);assert(not s.touchMove.active)
''',
    'hold, slide and release execute once; tap, center and outer cancel are free': r'''
acquire('discrete_recall');local serial=s.skillRequestSerial
t:Down(e(2,754,320));t:Up(e(2,754,204));assert(s.skillRequestSerial==serial)
down();t:Up(e(2,754,320));assert(s.skillRequestSerial==serial)
down();t:Up(e(2,754,20));assert(s.skillRequestSerial==serial)
local w=s.world;w:_Release(w.cells[1],1)
local v=w.releasedViruses[#w.releasedViruses];v.x,v.y=w.player.x,w.player.y
down();local release=select(1);t:Drag(release);assert(s.skillRequestSerial==serial and t.ring:IsVisible())
t.wheel:OnPointerUp(release);assert(s.skillRequestSerial==serial+1 and s:GetSkillState('discrete_recall').cooldown>0)
t:Up(release);assert(s.skillRequestSerial==serial+1 and not t.ring:IsVisible())
''',
    'cancel and stale run, control, focus or missing pointer never cast': r'''
acquire('discrete_recall');local serial=s.skillRequestSerial
down();t.wheel.props.onPointerCancel(e(2,754,204));assert(not t.gesture)
down();s.cards.runId=s.cards.runId+1;t:Up(select(1));assert(s.skillRequestSerial==serial)
down();local id=s.world.currentControlledSwarmId;s.world.currentControlledSwarmId=-1;t:Up(select(1));s.world.currentControlledSwarmId=id
assert(s.skillRequestSerial==serial)
down();input.focus=false;t:Update(.1);input.focus=true;assert(not t.gesture)
down();UI.Input.pointers[2]=nil;t:Update(.1);assert(not t.gesture and s.skillRequestSerial==serial)
''',
    'toggles are separate and targeted skill still requires a legal target': r'''
for _,id in ipairs({'swarm_anchor','infection_trail','merge_seed','node_cover'}) do acquire(id) end
local entries=t:Entries();assert(#entries==1 and entries[1].id=='node_cover')
t:Refresh();local b=t.buttons.swarm_anchor
b.props.onClick();assert(s:GetSkillState('swarm_anchor').active)
b.props.onClick();assert(not s:GetSkillState('swarm_anchor').active)
down();t:Up(select(1));assert(s.skillSelection and s.skillSelection.id=='node_cover')
assert(s:GetSkillState('node_cover').cooldown==0)
require('UI.SkillControls').Pick(s,-10000,-10000)
assert(s.skillSelection and s:GetSkillState('node_cover').cooldown==0)
''',
    'all active skills fit pages and hidden swarms retain their exit command': r'''
for _,card in ipairs(Config.Cards.definitions) do acquire(card.id) end
local swarm=s.world:SwarmById(s.world.currentControlledSwarmId);swarm.isHidden=true
local found=false
for _,entry in ipairs(t:Entries()) do if entry.id=='node_hide' and entry.target and entry.target.exit then found=true end end
assert(found);swarm.isHidden=false
down();assert(#t.gesture.entries<=8 and t.gesture.entries[#t.gesture.entries].page)
local serial=s.skillRequestSerial;t:Up(select(#t.gesture.entries));assert(t.page==2 and s.skillRequestSerial==serial)
down();assert(#t.gesture.entries<=8);t:Cancel()
''',
    'editor drag, resize, cancel, save, load and reset preserve other pause reasons': r'''
s:SetPaused('other',true);t:Edit();assert(t.editor and s.pauseReasons['control-layout'])
local old=L.Bounds(t.saved,'joystick',t.w,t.h);local handle=t.handles.joystick
handle.props.onPointerDown(e(7,old.x,old.y));handle.props.onPointerMove(e(7,old.x+25,old.y-20));handle.props.onPointerUp(e(7,old.x+25,old.y-20))
t.sizeSlider.props.onChange(nil,1.25);assert(t.draft.controls.joystick.scale==1.25)
t:Finish(false);assert(not t.saved.controls.joystick and not s.pauseReasons['control-layout'] and s.pauseReasons.other)
t:Edit();L.Put(t.draft,'joystick',180,380,1.2,t.w,t.h);t:Finish(true)
assert(not t.editor and L.Load().controls.joystick.scale==1.2 and s.pauseReasons.other)
local restored=L.Bounds(L.Load(),'joystick',1147,530);assert(restored.left>=0 and restored.top+restored.d<=530)
t:Edit();t.editor:FindById('layoutReset').props.onClick();t:Finish(true);assert(not L.Load().controls.joystick)
''',
    'overlap and storage failure keep the editor open, invalid saves fall back safely': r'''
t:Edit();L.Put(t.draft,'splitBtn',859,452,1,t.w,t.h);t:Finish(true);assert(t.editor)
t.draft=L.Clean(nil);File=function() error('unwritable') end;t:Finish(true);assert(t.editor and t.editorStatus.props.text:find('保存失败'))
t:Finish(false);assert(not s.pauseReasons['control-layout'])
local clean=L.Clean({version=1,controls={joystick={x=0/0,y=.5,scale=1},splitBtn={x=2,y=-1,scale=999}}})
assert(not clean.controls.joystick and clean.controls.splitBtn.x==1 and clean.controls.splitBtn.y==0 and clean.controls.splitBtn.scale==L.maxScale)
assert(next(L.Clean({version=99,controls={}}).controls)==nil)
''',
    'web save uses player cloud values and reports failure or timeout without late overwrite': r'''
testPlatform='Web';local get,put
clientCloud={userId='player',Get=function(_,key,events) get=events end,
 Set=function(_,key,value,events) assert(key=='touch_controls_v1' and value.version==2);put=events end}
assert(L.CloudAvailable())
local loaded;L.LoadCloud(function(value) loaded=value end)
get.ok({touch_controls_v1={version=1,controls={joystick={x=.2,y=.7,scale=1.1}}}})
assert(math.abs(loaded.controls.joystick.scale-132*1.1/L.baseSize)<1e-8)
t:Edit();t:Finish(true);assert(t.cloudPending~=nil and put)
put.error();assert(not t.cloudPending and h.noticeText_:find('云保存失败'))
t:Edit();t:Finish(true);local old=put;t:Update(13);assert(h.noticeText_:find('云保存超时'))
t:Edit();t:Finish(true);old.ok();assert(t.cloudPending~=nil);put.ok();assert(not t.cloudPending and h.noticeText_:find('保存到云端'))
clientCloud.userId=0;t:Edit();t:Finish(true);assert(h.noticeText_:find('本次游戏'))
''',
    'settings entry releases settings pause then opens layout; escape cancellation preserves run': r'''
UI.Dropdown=UI.Panel;UI.Toggle=UI.Panel
graphics.GetWidth=function(self) return self.width end;graphics.GetHeight=function(self) return self.height end
local menu;local actions={}
local settings={values={master=100,music=80,effects=100,ambient=80,voice=100,uiScale=1,maxFps=60,menuMotion=true}}
menu=require('UI.MainMenu').New(settings,function(action)
 actions[#actions+1]=action;if action=='resume' then s:SetPaused('settings',false);menu:DestroyPause() end
end)
s:SetPaused('settings',true);menu:ShowSettings(h.root)
local serial=s.cards.runId;local time=s.time
menu.pauseRoot:FindById('editTouchControls').props.onClick()
assert(actions[1]=='resume' and t.editor and not s.pauseReasons.settings and s.pauseReasons['control-layout'])
t:Finish(false);assert(s.cards.runId==serial and s.time==time and not s.paused)
''',
    'viewport or run changes cancel editing and clear captured gestures': r'''
t:Edit();L.Put(t.draft,'joystick',180,380,1.2,t.w,t.h)
graphics.width=1147;graphics.height=530;t:Update(.1)
assert(not t.editor and not t.saved.controls.joystick and not s.pauseReasons['control-layout'])
t:Edit();s.cards.runId=s.cards.runId+1;t:Update(.1)
assert(not t.editor and not s.pauseReasons['control-layout'])
''',
}

if __name__ == '__main__':
    for name, code in CASES.items():
        lua=runtime();lua.globals().print=lambda *args: None
        lua.execute(SETUP+code)
        print('PASS:',name)
    print(f'{len(CASES)} touch-control checks passed')
