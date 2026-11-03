"""Real Lua entry/settings/audio logic; engine, rendering and playback are fixtures."""
from main_menu_regression import runtime

CASES = {
    'real GameScene readiness requires three completed draws at a valid viewport': r'''
package.loaded['Game.GameScene']=nil
local Scene=require('Game.GameScene')
for _,name in ipairs({'nvgSave','nvgRestore','nvgIntersectScissor','nvgBeginPath',
 'nvgRect','nvgFillColor','nvgFill','nvgGlobalAlpha','nvgRGBA'}) do _G[name]=function() end end
local size=0
local scene=setmetatable({entryWarmFrames=0,sim={time=0},renderMotion={},mapView=require('Game.MapOverview').New(),
 entryZoom=1,tutorialZoom=1,endingZoom=1,
 scaleMgr={CurrentScale=function() return 'cell' end,FadeAlpha=function() return 1 end,
 IsTransitioning=function() return false end,CurrentZoom=function() return 1 end}},Scene)
function scene:GetAbsoluteLayout() return {x=0,y=0,w=size,h=size} end
function scene:DrawScale() end
scene:BeginEntryWarmup();scene:Render({});assert(not scene:IsEntryReady())
size=720
for _=1,2 do scene:Render({});assert(not scene:IsEntryReady()) end
scene:Render({});assert(scene:IsEntryReady())
scene:BeginEntryWarmup();assert(not scene:IsEntryReady())
function scene:DrawScale() error('Draw not completed') end
assert(not pcall(function() scene:Render({}) end))
assert(not scene:IsEntryReady())
''',
    'entry waits for rendered frames rather than timing out into a cold black screen': r'''
Start();click('storyMode');flush(.1)
for _=1,30 do
 flush(.1)
 if UI.root:FindById('entryWarmShield') then break end
end
local scene=assert(UI.root:FindById('gameScene'))
assert(scene.parent.parent==UI.root and scene.parent.props.zIndex==-2)
assert(scene.parent.props.pointerEvents=='none' and scene.parent.props.opacity==nil)
for _=1,60 do flush(.1) end
assert(UI.root.props.id=='mainMenu' and UI.root:FindById('entryLoading'))
assert(UI.root:FindById('entryFade').props.opacity==0)
assert(UI.root:FindById('menuForeground').props.opacity==nil)
assert(sources.MenuEntryWhoosh.plays==0 and lastSim.time==0 and lastSim.paused)
for i=1,2 do uiTick(.016);flush(.016);assert(UI.root:FindById('entryLoading')) end
uiTick(.016);flush(.016);assert(not UI.root:FindById('entryLoading'))
-- All construction and BGM reads must be finished before the push-in begins.
require('Core.SimState').New=function() error('Late world construction') end
local get=cache.GetResource
cache.GetResource=function(self,kind,path)
 assert(path~='audio/bgm.mp3','Late music load at covered handoff')
 return get(self,kind,path)
end
finishEntry()
assert(UI.root.props.id=='uiRoot' and UI.root.parent==nil and not scene.destroyed)
assert(UI.root.props.pointerEvents=='box-none' and UI.root.props.zIndex==0)
assert(scene.entryZoom==1 and lastSim:CanAct() and gameCreates==1)
''',
    'shutdown during render warmup never destroys the game as a menu child': r'''
Start();click('storyMode');flush(.1)
for _=1,30 do flush(.1);if UI.root:FindById('entryWarmShield') then break end end
assert(UI.root:FindById('gameScene'))
Stop();assert(gameDestroys==1 and UI.root==nil)
''',
    'slow preparation cannot advance the shot, repeat sound or start simulation': r'''
Start()
local Sim=require('Core.SimState');local original=Sim.New;local builds=0
Sim.New=function()
 builds=builds+1
 for _=1,12 do coroutine.yield() end
 return original()
end
click('storyMode');flush(.1)
for _=1,12 do
 uiTick(.1);flush(.1)
 assert(UI.root.props.id=='mainMenu' and UI.root:FindById('entryLoading'))
 assert(UI.root:FindById('menuForeground').props.opacity==nil)
 assert(UI.root:FindById('entryFade').props.opacity==0)
 assert(sources.MenuEntryWhoosh.plays==0 and gameCreates==0)
 key(KEY_RETURN,true);click('storyMode')
end
prepareEntry();assert(builds==1 and lastSim.paused and lastSim.time==0)
for _=1,5 do flush(.1) end;assert(sources.MenuEntryWhoosh.plays==0)
flush(.1);assert(sources.MenuEntryWhoosh.plays==1)
finishEntry();assert(lastSim:CanAct() and builds==1)
''',
    'stopping during suspended generation releases the queued work': r'''
Start()
local Sim=require('Core.SimState');local original=Sim.New;local resumed=false
Sim.New=function() coroutine.yield();resumed=true;return original() end
click('storyMode');flush(.1);flush(.1)
Stop();assert(not resumed and gameCreates==0 and UI.root==nil)
''',
    'world generation completes before the camera and audio timelines begin': r'''
Start()
local Sim=require('Core.SimState');local original=Sim.New;local builds=0
Sim.New=function()
 builds=builds+1
 assert(UI.root.props.id=='mainMenu')
 assert(UI.root:FindById('entryFade').props.opacity==0)
 assert(UI.root:FindById('menuForeground').props.opacity==nil)
 assert(UI.root:FindById('entryLoading'))
 for _,s in pairs(sources) do assert(not s.playing,'source active during preparation: '..s.name) end
 return original()
end
click('storyMode');flush(.1)
assert(builds==0 and UI.root:FindById('entryLoading'))
click('storyMode');key(KEY_RETURN,true)
prepareEntry()
assert(builds==1 and gameCreates==1 and UI.root.props.id=='mainMenu')
assert(lastSim.paused and lastSim.time==0 and not UI.root:FindById('entryLoading'))
finishEntry();assert(builds==1 and UI.root.props.id=='uiRoot')
assert(sources.MenuEntryWhoosh.plays==1)
''',
    'legacy tutorial flags never suppress a fresh opening': r'''
autoSkipTutorial=false
disk={tutorialSeen=true,skipTutorial=true,tutorialCompletedVersion=2};Start();openStory()
assert(lastSim.tutorial.active and UI.root:FindById('tutorialOverlay'):IsVisible())
holdEscape(1.25);assert(not lastSim.tutorial.active and lastSim:CanAct());Stop()
Start();openStory();assert(lastSim.tutorial.active);Stop()
''',
    'settings save excludes all retired tutorial preference fields': r'''
local Settings=require('Core.UserSettings');disk={tutorialSeen=true,skipTutorial=true,tutorialCompletedVersion=2,music=32}
local s=Settings.New();s:Save()
assert(disk.tutorialSeen==nil and disk.skipTutorial==nil and disk.tutorialCompletedVersion==nil and disk.music==32)
''',
    'loading mode never retries audio and rejected heartbeat starts are rate limited': r'''
local Audio=require('Core.GameAudio');local a=Audio.New();a:SetMode('menu');a:SetMode('loading')
local counts={};for name,s in pairs(sources) do counts[name]=s.plays end
for _=1,300 do a:Update(1/60,nil) end
for name,s in pairs(sources) do assert(s.plays==counts[name]) end
disk={skipTutorial=true};Start();openStory()
local w=lastSim.world;w.immunes={{targetType='swarm',targetId=w.player.id,state='chase'}}
local heartbeat=sources.Heartbeat1
function heartbeat:IsPlaying() return false end
function sources.ChaseTransition:IsPlaying() return false end
for _=1,600 do flush(1/60) end
assert(heartbeat.plays>0 and heartbeat.plays<=4,'heartbeat restarted each frame')
''',
}

if __name__ == '__main__':
    for name, code in CASES.items():
        lua=runtime();lua.globals().print=lambda *args: None
        lua.execute(code)
        print('PASS:', name)
    print(f'{len(CASES)} web entry boundary checks passed; browser rendering/audio unverified.')
