"""Execute real menu/settings/main and SimState with a small engine/UI boundary fixture.

This verifies routing, pause/resume, storage and credits; it does not verify GPU rendering.
Run with Lua 5.4 Lupa available (or project-local .tmp/test-deps).
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.tmp/test-deps'))
from lua_test_runtime import LuaRuntime

FIXTURE = r'''
local Widget = {}; Widget.__index = Widget
function make(kind, props)
 local w=setmetatable({kind=kind,props=props or {},children={},destroyed=false},Widget)
 for _,c in ipairs(w.props.children or {}) do w:AddChild(c) end
 return w
end
function Widget:AddChild(child) self.children[#self.children+1]=child; child.parent=self end
function Widget:InsertChild(child,index)
 if child.parent then child.parent:RemoveChild(child) end
 table.insert(self.children,index,child);child.parent=self
end
function Widget:RemoveChild(child)
 for i,c in ipairs(self.children) do if c==child then table.remove(self.children,i);child.parent=nil;return end end
end
function Widget:FindById(id)
 if self.props.id==id then return self end
 for _,c in ipairs(self.children) do local r=c:FindById(id); if r then return r end end
end
function Widget:SetStyle(p) for k,v in pairs(p) do self.props[k]=v end end
function Widget:SetText(text) self.props.text=text end
function Widget:SetValue(value) self.props.value=value end
function Widget:SetDisabled(value) self.props.disabled=value end
function Widget:Animate(p) self.animation=p end
function Widget:GetLayout() return {h=800} end
function Widget:SetVisible(value) self.props.visible=value end
function Widget:IsVisible() return self.props.visible~=false end
function Widget:GetAbsoluteLayout()
 return {x=0,y=0,w=graphics.width/(UI.scale and UI.scale() or 1),h=graphics.height/(UI.scale and UI.scale() or 1)}
end
Widget.GetAbsoluteLayoutForHitTest=Widget.GetAbsoluteLayout
function Widget:Init(props)
 self.props,self.children,self.destroyed=props,{},false
 for _,c in ipairs(props.children or {}) do self:AddChild(c) end
end
function Widget:Extend(name)
 local class={};class.__index=class
 return setmetatable(class,{__index=self,__call=function(_,props)
  local w=setmetatable({kind=name},class);w:Init(props);return w
 end})
end
function Widget:Destroy()
 if self.destroyed then return end
 self.destroyed=true; self.animation=nil
 for i=#self.children,1,-1 do self.children[i]:Destroy() end
 if self.parent then self.parent:RemoveChild(self) end
end
UI={Scale={DEFAULT=function() return graphics.dpr or 1 end}}
for _,kind in ipairs({'Panel','Label','Button','Slider','Dropdown','Toggle','Checkbox','Divider','SafeAreaView','ScrollView','ProgressBar'}) do
 UI[kind]=function(props) return make(kind,props) end
end
UI.Widget=Widget
function UI.Init() end
function UI.SetRoot(root) UI.root=root end
function UI.GetRoot() return UI.root end
function UI.SetScale(fn) UI.scale=fn end
function UI.GetHeight() return graphics.height/UI.scale() end
function UI.ClearFocus() end
function UI.Shutdown() if UI.root then UI.root:Destroy() end; UI.root=nil end
package.loaded['urhox-libs/UI']=UI
function clone(v)
 if type(v)~='table' then return v end
 local r={}; for k,x in pairs(v) do r[k]=clone(x) end; return r
end
disk={}; writeAllowed=true
-- Non-tutorial suites explicitly exercise the public hold-to-skip path after entry.
autoSkipTutorial=true
fileSystem={FileExists=function() return disk~=nil end}
FILE_READ=0;FILE_WRITE=1
function File(path,mode)
 local f={}; function f:IsOpen() return mode==FILE_READ or writeAllowed end
 function f:ReadString() return disk end
 function f:WriteString(value) disk=value;return true end
 function f:Dispose() self.disposed=true end
 return f
end
cjson={encode=function(v) return clone(v) end,decode=function(v)
 if v=='corrupt' then error('bad json') end; return clone(v)
end}
SOUND_MASTER='Master'; SOUND_MUSIC='Music'; SOUND_EFFECT='Effect'; SOUND_AMBIENT='Ambient'; SOUND_VOICE='Voice'
audio={gains={}};function audio:SetMasterGain(kind,gain) self.gains[kind]=gain end
engine={exiting=false};function engine:SetAutoExit(value) self.autoExit=value end
function engine:SetMaxFps(value) self.maxFps=value end
function engine:Exit() self.exiting=true end
graphics={width=1280,height=720,dpr=1}
function graphics:GetWidth() return self.width end;function graphics:GetHeight() return self.height end
input={};MM_ABSOLUTE=0;heldKeys={}
function input:GetKeyDown(key) return heldKeys[key]==true end
KEY_V=86;KEY_1=49;KEY_ESCAPE=27;KEY_UP=38;KEY_DOWN=40;KEY_RETURN=13;KEY_SPACE=32;KEY_R=82;KEY_E=69;KEY_TAB=9;KEY_M=77;KEY_2=50
sounds={};missingSounds={};sources={};audioScenes={}
cache={GetResource=function(_,kind,path)
 if missingSounds[path] then return nil end
 if not sounds[path] then
  sounds[path]={path=path,SetLooped=function(self,value) self.looped=value end,GetLength=function() return 4 end}
 end
 return sounds[path]
end}
function Scene()
 local scene={disposed=false};audioScenes[#audioScenes+1]=scene
 function scene:CreateChild(name)
  return {CreateComponent=function(_,kind)
   local source={name=name,plays=0,stops=0,playing=false}
   function source:SetSoundType(value) self.soundType=value end
   function source:SetGain(value) self.gain=value end
   function source:GetGain() return self.gain or 1 end
   function source:GetTimePosition() return self.timePosition or 0 end
   function source:Seek(value) self.timePosition=value end
   function source:IsPlaying() return self.playing end
   function source:Play(sound,frequency,gain)
    self.sound=sound;self.frequency=frequency;self.gain=gain;self.plays=self.plays+1;self.playing=true
   end
   function source:StopImmediate() self.stops=self.stops+1;self.playing=false end
   sources[name]=source;return source
  end}
 end
 function scene:Dispose() self.disposed=true end
 return scene
end
function SubscribeToEvent() end
gameCreates=0; hudUpdates=0; gameDestroys=0; metricsUpdates=0
package.loaded['Game.GameScene']=function(props)
 gameCreates=gameCreates+1; lastSim=props.sim
 local w=make('GameScene',props)
 w.viewport={x=0,y=90,w=1280,h=490};w.hudRoot=nil
 function w:CurrentZoom() return 1 end
 function w:IsMapActive() return false end
 function w:ToggleMap() return false end
 function w:SetEntryPose(zoom,active) self.entryZoom,self.entryActive=zoom,active end
 function w:SetEndingPose(zoom,covered,progress) self.endingPose={zoom,covered,progress} end
 function w:BeginEntryWarmup() self.warmFrames=0 end
 function w:IsEntryReady() return (self.warmFrames or 0)>=3 end
 function w:Render() self.warmFrames=(self.warmFrames or 0)+1 end
 w.cellView={WorldToScreen=function(_,x,y) return 640+x*8,335+y*8 end,
  CameraTransform=function() return 8,640,335 end}
 function w:Update(dt) props.sim:Update(dt) end
 function w:Destroy() if not self.destroyed then gameDestroys=gameDestroys+1 end;Widget.Destroy(self) end
 return w
end
package.loaded['UI.HUD']={New=function(props)
 local h={cardInfoShown_=false,sim=props.sim,scaleMgr=props.scaleMgr};function h:Build() self.root=make('HUD');return self.root end
 function h:Update() hudUpdates=hudUpdates+1 end
 function h:RefreshStrategyHighlight() end;function h:ResetEnding() end
 function h:CloseDrawers() return false end
 function h:RefreshScale()
  props.sim:SetPaused('observation',props.scaleMgr:CurrentScale()=='mouse')
  props.sim:SetPaused('transition',props.scaleMgr:IsTransitioning())
 end
 function h:ClearTouchMove() props.sim.touchMove={x=0,y=0,active=false} end
 function h:Destroy() self.root:Destroy() end
 return h
end}
package.loaded['Core.CardMetrics']={Update=function() metricsUpdates=metricsUpdates+1 end}
function event(values)
 return {GetInt=function(_,k) return values[k] or 0 end,
  GetBool=function(_,k) return values[k] or false end,GetFloat=function(_,k) return values[k] or 0 end}
end
function key(value,repeatKey) HandleKeyDown('',event({Key=value,Repeat=repeatKey or false})) end
function flush(dt) HandleUpdate('',event({TimeStep=dt or .1})) end
function uiTick(dt)
 local function update(w)
  if w.Update then w:Update(dt) end;for _,c in ipairs(w.children) do update(c) end
 end
 update(UI.root)
 local function render(w)
  if w.kind=='GameScene' and w.Render then w:Render() end
  for _,c in ipairs(w.children) do render(c) end
 end
 render(UI.root)
end
function click(id)
 local w=assert(UI.root:FindById(id),id)
 if not w.props.disabled and w.props.onClick then w.props.onClick(w) end
end
function holdEscape(seconds)
 heldKeys[KEY_ESCAPE]=true;key(KEY_ESCAPE)
 for _=1,math.floor(seconds/.05+.5) do flush(.05) end
 heldKeys[KEY_ESCAPE]=nil;flush(.001)
end
function finishEntry()
 for _=1,3000 do
  if not UI.root:FindById('entryFade') then
   if autoSkipTutorial and lastSim and lastSim.tutorial and lastSim.tutorial.active then holdEscape(1.25) end
   return
  end
  uiTick(.1);flush(.1)
 end
 error('Entry fade did not finish')
end
function prepareEntry()
 for _=1,3000 do
  if not UI.root:FindById('entryLoading') then return end
  uiTick(.016);flush(.016)
 end
 error('Preparation did not finish')
end
function openStory() click('storyMode');flush();finishEntry() end
function skipCredits()
 heldKeys[KEY_ESCAPE]=nil;flush(.01)
 heldKeys[KEY_ESCAPE]=true;key(KEY_ESCAPE)
 for _=1,13 do flush(.1) end
 heldKeys[KEY_ESCAPE]=nil;flush(.01)
end
function finishPreload()
 for _=1,3000 do
  local label=UI.root:FindById('menuPreparation')
  if label and label.props.text:find('已就绪') then return end
  uiTick(.016);flush(.016)
 end
 error('Idle preload did not finish')
end
'''

TESTS = {
    'phone menu places its entire action group in the upper part of the screen': r'''
require('UI.MobileLayout').MarkTouch();Start()
local content=UI.root:FindById('menuContent').props
assert(content.justifyContent=='flex-start' and content.paddingTop<=44)
assert(UI.root:FindById('storyMode').props.height>=44)
''',
    'entry whoosh follows camera onset, uses effect gain and plays once per entry': r'''
Start();local whoosh=assert(sources.MenuEntryWhoosh)
assert(whoosh.soundType==SOUND_EFFECT and whoosh.plays==0)
click('storyMode');flush(.1);prepareEntry();flush(.1);assert(whoosh.plays==0)
click('storyMode');for _=1,4 do flush(.1) end;assert(whoosh.plays==0);flush(.1)
assert(whoosh.plays==1 and whoosh.sound.path=='audio/menu_entry_membrane.wav')
assert(whoosh.frequency==0 and whoosh.gain==.8 and not whoosh.sound.looped)
finishEntry();assert(whoosh.plays==1)
key(KEY_ESCAPE);flush();click('pauseMenu');flush();click('storyMode');flush(.1);finishEntry()
assert(whoosh.plays==2);Stop();assert(not whoosh.playing)
''',
    'missing entry whoosh does not block the entry transition': r'''
missingSounds['audio/menu_entry_membrane.wav']=true;Start();openStory()
assert(gameCreates==1 and lastSim:CanAct() and sources.MenuEntryWhoosh.plays==0)
''',
    'merged skill shortcuts cancel selection before opening paused settings': r'''
Start();openStory();assert(lastSim.started)
local A=require('Core.AbilityRuntime');local C=require('Core.Config')
for _,card in ipairs(C.Cards.definitions) do
 if card.id=='node_cover' then A.Acquire(lastSim.world,card) end
end
key(KEY_V);assert(lastSim.skillMenu and not lastSim.pauseReasons.mainMenu)
key(KEY_ESCAPE);flush();assert(UI.root.props.id=='uiRoot' and not lastSim.skillMenu)
key(KEY_V);key(KEY_1);assert(lastSim.skillSelection)
key(KEY_ESCAPE);flush();assert(UI.root.props.id=='uiRoot' and not lastSim.skillSelection)
key(KEY_ESCAPE);flush();assert(UI.root.props.id=='uiRoot' and UI.root:FindById('pauseOverlay') and lastSim.pauseReasons.settings)
key(KEY_ESCAPE);flush();assert(UI.root.props.id=='uiRoot' and not lastSim.pauseReasons.settings)
''',

    'menu music switches without overlap/restart, clicks use effects and cleanup stops audio': r'''
Start();finishPreload();local music=sources.MusicSource;local effect=sources.MenuClickSource
assert(music.sound.path=='audio/menu_theme.wav' and music.sound.looped)
assert(music.soundType==SOUND_MUSIC and music.frequency==0)
assert(effect.soundType==SOUND_EFFECT and not sounds['audio/menu_click.wav'].looped)
local menuPlays=music.plays;local clickPlays=effect.plays
click('endlessMode');key(KEY_R);key(KEY_DOWN,true);flush()
assert(effect.plays==clickPlays and music.plays==menuPlays)
click('openSettings');flush();assert(effect.plays==clickPlays+1 and music.plays==menuPlays)
local slider=UI.root:FindById('volume_effects');slider.props.onChange(slider,0)
assert(audio.gains[SOUND_EFFECT]==0 and audio.gains[SOUND_MUSIC]==.8)
slider.props.onChangeEnd(slider,0);assert(effect.plays==clickPlays+2)
key(KEY_ESCAPE);flush();click('openCredits');flush();skipCredits()
assert(music.plays==menuPlays)
local stops=music.stops;openStory()
assert(music.sound.path=='audio/bgm.mp3' and music.sound.looped and music.stops==stops+2)
key(KEY_ESCAPE);flush();assert(UI.root:FindById('pauseOverlay'));click('pauseMenu');flush();assert(music.sound.path=='audio/menu_theme.wav')
local afterReturn=music.plays;click('openSettings');flush();assert(music.plays==afterReturn)
Stop();assert(not music.playing and not effect.playing and audioScenes[1].disposed)
''',
    'missing audio is silent and safe, failed track switch stops previous music': r'''
missingSounds['audio/menu_click.wav']=true
Start();key(KEY_DOWN);key(KEY_RETURN);flush();assert(UI.root.props.id=='settingsScreen')
assert(sources.MenuClickSource.plays==0)
missingSounds['audio/bgm.mp3']=true;key(KEY_ESCAPE);flush();openStory()
assert(not sources.MusicSource.playing)
key(KEY_ESCAPE);flush();click('pauseMenu');flush();assert(sources.MusicSource.playing)
Stop();assert(audioScenes[1].disposed)
''',
    'startup preloads while menu remains usable and keyboard starts gameplay': r'''
Start(); assert(engine.autoExit==false and gameCreates==0)
local rows=UI.root:FindById('menuOptions').children
assert(#rows==6 and rows[1]:FindById('gameTitle').props.text=='病毒涌现')
for i,title in ipairs({'开始','无尽模式','设定','制作名单','退出'}) do assert(rows[i+1].props.text==title) end
assert(rows[3].props.disabled);click('endlessMode');flush();assert(gameCreates==0)
key(KEY_DOWN);key(KEY_RETURN);flush();assert(UI.root.props.id=='settingsScreen')
assert(gameCreates==1 and lastSim.paused);key(KEY_ESCAPE);flush();assert(UI.root.props.id=='mainMenu')
key(KEY_RETURN);flush();assert(gameCreates==1 and UI.root.props.id=='mainMenu')
finishEntry();assert(gameCreates==1 and UI.root.props.id=='uiRoot')
assert(lastSim.started and lastSim.selectedStartRegion=='UPPER_AIRWAY' and lastSim:CanAct())
assert(UI.root:FindById('gameScene').props.scaleMgr:CurrentScale()=='cell')
''',
    'world prepares before camera movement, then handoff blocks input until revealed': r'''
Start();click('storyMode');flush(.05)
local fade=assert(UI.root:FindById('entryFade'))
assert(fade.props.opacity==0 and gameCreates==0)
assert(UI.root:FindById('menuForeground').props.opacity==nil)
prepareEntry()
flush(.05)
assert(UI.root:FindById('menuForeground').props.opacity<1)
assert(UI.root:FindById('menuCamera').props.scale==1)
key(KEY_ESCAPE);key(KEY_RETURN);flush(.05);assert(UI.root.props.id=='mainMenu')
for _=1,30 do
 uiTick(.05);flush(.05)
 if UI.root.props.id=='uiRoot' then break end
end
assert(gameCreates==1 and UI.root.props.id=='uiRoot')
assert(UI.root:FindById('entryFade')==fade and fade.props.opacity==1)
assert(lastSim.started and lastSim.paused and lastSim.time==0)
local mgr=UI.root:FindById('gameScene').props.scaleMgr
assert(mgr:CurrentScale()=='cell' and not mgr:IsTransitioning())
key(KEY_R);key(KEY_M);key(KEY_ESCAPE);uiTick(.05);flush(.05)
assert(lastSim.time==0 and mgr:CurrentScale()=='cell')
finishEntry();assert(lastSim:CanAct() and fade.destroyed and not UI.root:FindById('entryFade'))
uiTick(.25);assert(lastSim.time>0)
RestartRun();assert(lastSim.started and lastSim.tutorial.active and lastSim.paused and lastSim.time==0)
assert(mgr:CurrentScale()=='cell' and not mgr:IsTransitioning())
''',
    'entry hides controls before pushing the background, blocks repeat clicks and restores a fresh menu': r'''
Start();click('storyMode');flush(.1);prepareEntry();flush(.1)
local foreground=assert(UI.root:FindById('menuForeground'))
local camera=assert(UI.root:FindById('menuCamera'))
local fade=assert(UI.root:FindById('entryFade'))
assert(foreground.props.opacity>0 and foreground.props.opacity<1 and camera.props.scale==1)
assert(camera.children[2].props.scale>camera.children[1].props.scale)
click('openSettings');click('storyMode');flush(.1)
flush(.1)
assert(UI.root.props.id=='mainMenu' and foreground.props.opacity==0)
assert(fade.props.opacity==0 and gameCreates==1 and lastSim.paused)
for _=1,3 do flush(.1) end
assert(camera.children[2].props.scale>camera.children[1].props.scale and fade.props.opacity==0)
finishEntry();assert(gameCreates==1 and UI.root.props.id=='uiRoot' and camera.destroyed)
key(KEY_ESCAPE);flush();click('pauseMenu');flush()
assert(UI.root:FindById('menuCamera').props.scale==1)
assert(UI.root:FindById('menuForeground').props.opacity==nil)
click('storyMode');flush(.1);HandleExitRequested();flush(.1);assert(engine.exiting)
''',
    'arrival slows the real camera before revealing HUD and releasing simulation': r'''
Start();click('storyMode');flush(.1);prepareEntry()
for _=1,20 do
 if UI.root.props.id=='uiRoot' then break end
 flush(.1)
end
local scene=assert(UI.root:FindById('gameScene'))
local hud=assert(UI.root:FindById('entryFade')).parent.children[2]
assert(scene.entryActive and scene.entryZoom==.82 and hud.props.opacity==0)
assert(lastSim.paused and lastSim.time==0)
for _=1,4 do flush(.1) end
local first=scene.entryZoom
assert(first>.82 and first<1 and hud.props.opacity==0)
flush(.1);local middle=scene.entryZoom
assert(middle>first and lastSim.time==0)
for _=1,3 do flush(.1) end
assert(scene.entryZoom>=middle and scene.entryZoom<=1)
finishEntry();assert(scene.entryZoom==1 and not scene.entryActive and hud.props.opacity==1)
assert(lastSim:CanAct())
''',
    'motion-disabled entry keeps a stationary camera and still completes safely': r'''
disk={skipTutorial=true,menuMotion=false};Start();click('storyMode');flush(.1)
local camera=assert(UI.root:FindById('menuCamera'))
for _=1,5 do flush(.1);assert(camera.props.scale==1) end
finishEntry();assert(gameCreates==1 and lastSim:CanAct())
''',
    'paused settings resumes the same authoritative run without entry transition': r'''
Start();openStory();assert(lastSim.started)
uiTick(.25);flush(.25);local sim=lastSim;local world=sim.world;local time=sim.time
assert(time>0);sim.touchMove={x=1,y=1,active=true}
key(KEY_ESCAPE);flush();assert(sim.pauseReasons.settings and not sim.touchMove.active)
local hudCount,metricCount=hudUpdates,metricsUpdates
for _=1,60 do uiTick(.1);flush(.1) end
assert(sim.time==time and hudUpdates==hudCount and metricsUpdates==metricCount)
key(KEY_ESCAPE);flush();finishEntry();assert(gameCreates==1 and lastSim==sim and sim.world==world)
assert(not sim.pauseReasons.settings and sim:CanAct() and not UI.root:FindById('entryFade'));uiTick(.25);assert(sim.time>time)
Stop();assert(gameDestroys==1)
''',
    'audio/display controls persist, defaults reset, invalid storage recovers': r'''
Start();click('openSettings');flush()
local music=UI.root:FindById('volume_music');music.props.onChange(music,35);music.props.onChangeEnd(music,35)
assert(audio.gains[SOUND_MUSIC]==.35)
local master=UI.root:FindById('volume_master');master.props.onChange(master,0)
assert(audio.gains[SOUND_MASTER]==0)
local scale=UI.root:FindById('uiScale');scale.props.onChange(scale,1.15)
assert(UI.scale()==1.15)
local fps=UI.root:FindById('frameLimit');fps.props.onChange(fps,120);assert(engine.maxFps==120)
local toggle=UI.root:FindById('menuMotion');toggle.props.onChange(toggle,false)
local S=require('Core.UserSettings');local loaded=S.New()
assert(loaded.values.music==35 and loaded.values.master==0 and loaded.values.uiScale==1.15)
assert(loaded.values.maxFps==120 and loaded.values.menuMotion==false)
loaded:Reset();assert(audio.gains[SOUND_MASTER]==1 and audio.gains[SOUND_MUSIC]==.8)
assert(engine.maxFps==60 and UI.scale()==1)
disk={music=500,master=-10,effects=35.7,uiScale=99,maxFps=99,menuMotion='bad'}
local checked=S.New();assert(checked.values.music==100 and checked.values.master==0 and checked.values.effects==36)
assert(checked.values.uiScale==1 and checked.values.maxFps==60 and checked.values.menuMotion==true)
disk='corrupt';local recovered=S.New();assert(recovered.values.music==80)
writeAllowed=false;recovered.values.music=20;recovered:ApplyAudio()
assert(recovered:Save()==false and audio.gains[SOUND_MUSIC]==.2)
''',
    'credits scroll in black, require a held skip and finish automatically': r'''
Start();click('openCredits');flush();assert(UI.root.props.id=='creditsScreen')
assert(UI.root.props.backgroundColor[1]==0 and UI.root.props.backgroundColor[2]==0)
local roll=UI.root:FindById('creditsRoll');local old=roll.props.top;flush(1)
assert(roll.props.top<old);key(KEY_R,true);flush();assert(UI.root.props.id=='creditsScreen')
key(KEY_R);flush();key(KEY_RETURN);flush();key(KEY_ESCAPE);flush()
assert(UI.root.props.id=='creditsScreen' and not UI.root.props.onClick)
skipCredits();assert(UI.root.props.id=='mainMenu' and gameCreates==1 and lastSim.paused and roll.destroyed)
click('openCredits');flush();flush(90);flush();assert(UI.root.props.id=='mainMenu')
click('exitGame');assert(not engine.exiting);flush();assert(engine.exiting)
''',
    'stop releases detached gameplay while in menu': r'''
Start();openStory();key(KEY_ESCAPE);flush();Stop();assert(gameDestroys==1 and UI.root==nil)
''',
    'window close takes priority over queued menu navigation': r'''
Start();click('openSettings');HandleExitRequested();flush();assert(engine.exiting)
''',
}

def runtime():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute("package.path=" + repr((ROOT / 'scripts/?.lua').as_posix()) + "..';'..package.path")
    lua.execute(FIXTURE)
    lua.execute("local c=require('Core.Config').Gameplay;c.mapGenerationVersion=1;c.width=26;c.height=32;c.cellCount=72")
    lua.execute((ROOT / 'scripts/main.lua').read_text(encoding='utf-8-sig'))
    return lua

if __name__ == '__main__':
    for name, code in TESTS.items():
        runtime().execute(code)
        print('PASS:', name)
    print(f'{len(TESTS)} menu integration checks passed; GPU/UI layout unverified.')
