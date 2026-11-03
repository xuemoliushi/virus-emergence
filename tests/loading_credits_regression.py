"""Loading readiness and film -> credits routing with real Lua; GPU/input are boundaries."""
from pathlib import Path
import json
from main_menu_regression import runtime
from ending_cinematic_regression import VIDEO

CASES={
    'loading animates while generation is suspended and never completes before rendered warmup':r'''
Start()
local Sim=require('Core.SimState');local original=Sim.New
Sim.New=function() for _=1,12 do coroutine.yield() end;return original() end
click('storyMode');flush(.1)
local loader=assert(UI.root:FindById('entryLoading'))
local status=assert(loader:FindById('entryLoadingStatus'))
local before=status.props.text
for _=1,5 do flush(.1) end
assert(status.props.text~=before and loader:FindById('entryLoadingProgress').props.value<1)
assert(loader.props.pointerEvents=='auto' and loader.props.zIndex>10000)
assert(sources.MenuEntryWhoosh.plays==0 and gameCreates==0)
for _=1,100 do flush(.1);if UI.root:FindById('entryWarmShield') then break end end
local scene=assert(UI.root:FindById('gameScene'))
for _=1,30 do flush(.1) end
assert(UI.root:FindById('entryLoading') and loader:FindById('entryLoadingProgress').props.value<1)
assert(lastSim.time==0 and lastSim.paused)
for _=1,2 do uiTick(.016);flush(.016);assert(UI.root:FindById('entryLoading')) end
uiTick(.016);flush(.016)
assert(loader.destroyed and not UI.root:FindById('entryLoading'))
assert(UI.root:FindById('menuPreparationProgress').props.value==1)
assert(not UI.root:FindById('menuPreparationProgress'):IsVisible())
finishEntry();assert(lastSim:CanAct() and scene.entryZoom==1)
''',
    'audio readiness keeps the loader below 100 after the three real warmup draws':r'''
local Audio=require('Core.GameAudio');local ready=false
Audio.IsEntryAudioReady=function() return ready end
Start();click('storyMode');flush(.1)
for _=1,100 do uiTick(.016);flush(.016);if UI.root:FindById('gameScene') then break end end
for _=1,10 do uiTick(.016);flush(.016) end
local loader=assert(UI.root:FindById('entryLoading'))
assert(loader:FindById('entryLoadingProgress').props.value<1)
assert(loader:FindById('entryLoadingStatus').props.text:find('音频'))
assert(lastSim.paused and sources.MenuEntryWhoosh.plays==0)
ready=true;flush(.016)
assert(loader.destroyed);finishEntry();assert(lastSim:CanAct())
''',
    'short keys, repeated keys and clicks do not skip; release and focus loss reset the hold':r'''
Start();click('openCredits');flush(.01)
local root=UI.root
for _,k in ipairs({KEY_R,KEY_RETURN,KEY_SPACE,KEY_ESCAPE}) do key(k);flush(.01) end
assert(UI.root==root and not root.props.onClick)
heldKeys[KEY_ESCAPE]=true;key(KEY_ESCAPE)
for _=1,6 do flush(.1) end
assert(root:FindById('creditsSkipProgress').props.width=='50.0%')
heldKeys[KEY_ESCAPE]=nil;flush(.01)
assert(root:FindById('creditsSkipProgress').props.width=='0%')
heldKeys[KEY_ESCAPE]=true;key(KEY_ESCAPE);flush(10)
assert(UI.root==root and root:FindById('creditsSkipProgress').props.width~='100.0%')
input.focus=false;flush(.1);input.focus=true
for _=1,13 do flush(.1) end
assert(UI.root==root)
heldKeys[KEY_ESCAPE]=nil;flush(.01);skipCredits()
assert(UI.root.props.id=='mainMenu' and root.destroyed)
''',
    'phone players can hold the matching button and cancel on release':r'''
require('UI.MobileLayout').MarkTouch();Start();click('openCredits');flush(.01)
local button=assert(UI.root:FindById('creditsTouchSkip'))
button.state={pressed=true}
for _=1,6 do flush(.1) end
assert(UI.root:FindById('creditsSkipProgress').props.width=='50.0%')
button.state.pressed=false;flush(.01)
assert(not UI.root:FindById('creditsSkipMask'):IsVisible())
button.state.pressed=true
for _=1,11 do flush(.1) end
assert(UI.root.props.id=='creditsScreen')
flush(.1);flush(.01);assert(UI.root.props.id=='mainMenu')
''',
}

FILM=r'''
local previousNew=package.loaded['UI.HUD'].New
package.loaded['UI.HUD'].New=function(props)
 local h=previousNew(props);local build=h.Build;local update=h.Update
 function h:Build()
  build(self);self.onMenu=props.onMenu;self.onCredits=props.onCredits
  self.onEndingPose=props.onEndingPose;self.onEndingMix=props.onEndingMix
  self.endingScreen=require('UI.EndingScreen').New(self);self.root:AddChild(self.endingScreen.root)
  return self.root
 end
 function h:Update(dt) update(self,dt);self.endingScreen:Update(dt) end
 reviewHUD=h;return h
end
Start();openStory();lastSim:FinishRun('victory');reviewHUD.endingScreen:Show('victory')
for _=1,7 do flush(.1) end
local player=reviewHUD.endingScreen.player
player.ready=true;flush(.02);player.clock=5
for _=1,30 do player.clock=player.clock+.1;flush(.1) end
assert(reviewHUD.endingScreen.phase=='video')
player.props.onEnded(player)
for _=1,7 do flush(.1) end
assert(UI.root.props.id=='creditsScreen' and player.destroyed and player.stopped)
local credits=UI.root
player.props.onEnded(player);flush(.1);assert(UI.root==credits,'stale callback reopened credits')
skipCredits();assert(UI.root.props.id=='mainMenu')
assert(UI.root:FindById('storyMode').props.text=='开始')
Stop()
'''

def main():
    passed=[]
    for name,code in CASES.items():
        lua=runtime();lua.globals().print=lambda *args:None;lua.execute(code)
        passed.append(name);print('PASS:',name)
    lua=runtime();lua.globals().print=lambda *args:None
    lua.execute(VIDEO);lua.execute(FILM)
    passed.append('natural film end queues credits once, disposes decoder and returns to fresh menu')
    print('PASS:',passed[-1])
    out=Path(__file__).resolve().parents[1]/'validation/loading-credits-20261020'
    out.mkdir(parents=True,exist_ok=True)
    (out/'regression.json').write_text(json.dumps({'passed':passed,'native_visual_verified':False},ensure_ascii=False,indent=2),encoding='utf8')

if __name__=='__main__':main()
