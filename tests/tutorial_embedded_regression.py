"""Per-run tutorial and real Esc polling; native input delivery is a boundary."""
from pathlib import Path
import json
from main_menu_regression import runtime

CASES={
    'every fresh run includes text and voice regardless of old save flags':r'''
autoSkipTutorial=false
for _,save in ipairs({{}, {tutorialSeen=true,tutorialCompletedVersion=2},
 {skipTutorial=true,tutorialSeen=true,tutorialCompletedVersion=99}}) do
 disk=save;Start()
 assert(not UI.root:FindById('tutorialMode'))
 click('openSettings');flush()
 assert(not UI.root:FindById('skipTutorial') and not UI.root:FindById('resetTutorial'))
 key(KEY_ESCAPE);flush();openStory()
 assert(lastSim.tutorial.active and lastSim.pauseReasons.tutorial)
 assert(UI.root:FindById('tutorialSkipHint').props.text=='长按 Esc 跳过教程')
 assert(not UI.root:FindById('tutorialSkipSafeArea'):IsVisible())
 assert(not UI.root:FindById('tutorialSkipMask'):IsVisible())
 assert(UI.root:FindById('tutorialCard').children[2].children[1].props.text==lastSim.tutorial.lesson.title)
 assert(sources.TutorialVoiceSource.sound.path=='audio/tutorial/intro.wav')
 Stop();assert(disk.skipTutorial==nil and disk.tutorialSeen==nil and disk.tutorialCompletedVersion==nil)
end
''',
    'short taps and separated holds do not skip or open settings':r'''
autoSkipTutorial=false;Start();openStory()
for _=1,4 do
 key(KEY_ESCAPE);flush(.1)
 holdEscape(.5)
 assert(lastSim.tutorial.active and lastSim.tutorial.skipTime==0)
 assert(not UI.root:FindById('pauseOverlay'))
end
Stop()
''',
    'one sustained hold exits teaching without rebuilding or losing authoritative state':r'''
autoSkipTutorial=false;Start();openStory()
local sim,world,t=lastSim,lastSim.world,lastSim.tutorial
local player,cells,mass,time=world.player,#world.cells,world.player.mass,sim.time
heldKeys[KEY_ESCAPE]=true;key(KEY_ESCAPE)
for _=1,23 do flush(.05) end
assert(t.active and t:SkipProgress()>.9)
assert(UI.root:FindById('tutorialSkipHint').props.text:find('正在跳过'))
flush(.05)
assert(not t.active and sim:CanAct() and not sim.pauseReasons.tutorial)
assert(sim.world==world and world.player==player and #world.cells==cells and player.mass==mass and sim.time==time)
assert(not world.tutorial and not UI.root:FindById('tutorialOverlay'):IsVisible())
assert(not sources.TutorialVoiceSource:IsPlaying())
key(KEY_ESCAPE,true);key(KEY_ESCAPE);flush(.1)
assert(not UI.root:FindById('pauseOverlay'),'same held key must not open settings after skip')
heldKeys[KEY_ESCAPE]=nil;flush(.001);key(KEY_ESCAPE);flush()
assert(UI.root:FindById('pauseOverlay'))
click('settingsBack');flush();assert(not t.active and sim.world==world and sim:CanAct())
uiTick(.25);assert(sim.time>time)
RestartRun();flush()
assert(sim.world~=world and sim.tutorial~=t and sim.tutorial.active)
Stop()
''',
    'focus loss resets hold progress and a long stalled frame cannot instantly skip':r'''
autoSkipTutorial=false;Start();openStory()
heldKeys[KEY_ESCAPE]=true;key(KEY_ESCAPE)
for _=1,10 do flush(.05) end
assert(lastSim.tutorial.skipTime>.4)
input.focus=false;flush(4);assert(lastSim.tutorial.skipTime==0)
input.focus=true;flush(100);assert(lastSim.tutorial.active and lastSim.tutorial.skipTime<=.1)
heldKeys[KEY_ESCAPE]=nil;flush(.001)
holdEscape(1.25);assert(lastSim:CanAct())
Stop()
''',
    'skip hint and progressive mask appear only during a hold without covering lesson text':r'''
autoSkipTutorial=false;Start();openStory()
local t=lastSim.tutorial
local area=UI.root:FindById('tutorialSkipSafeArea')
local mask=UI.root:FindById('tutorialSkipMask')
local card=UI.root:FindById('tutorialCard')
assert(area.props.id=='tutorialSkipSafeArea' and area.props.nativeMenuInset and area.props.alignItems=='flex-end')
assert(area.props.backgroundColor==false and area.props.backgroundImage=='')
assert(area.props.pointerEvents=='none' and mask.props.pointerEvents=='none')
assert(not area:IsVisible() and not mask:IsVisible() and card:IsVisible())
assert(mask.props.zIndex<card.props.zIndex and card.props.zIndex<area.props.zIndex)
heldKeys[KEY_ESCAPE]=true;key(KEY_ESCAPE)
local previous=0
for _=1,12 do
 flush(.05)
 assert(area:IsVisible() and mask:IsVisible() and card:IsVisible())
 local alpha=mask.props.backgroundColor[4]
 assert(alpha>previous and alpha<190);previous=alpha
end
heldKeys[KEY_ESCAPE]=nil;flush(.001)
assert(t.skipTime==0 and t.active and not area:IsVisible() and not mask:IsVisible())
heldKeys[KEY_ESCAPE]=true;key(KEY_ESCAPE);flush(.1)
input.focus=false;flush(.05)
assert(not area:IsVisible() and not mask:IsVisible())
input.focus=true;heldKeys[KEY_ESCAPE]=nil;flush(.001)
holdEscape(1.25)
assert(not t.active and lastSim:CanAct() and not UI.root:FindById('tutorialOverlay'):IsVisible())
assert(not area:IsVisible() and not mask:IsVisible())
Stop()
''',
    'holding Esc before the opening cannot silently skip its tutorial':r'''
autoSkipTutorial=false;Start();heldKeys[KEY_ESCAPE]=true;key(KEY_ESCAPE);openStory()
for _=1,30 do flush(.1) end
assert(lastSim.tutorial.active and lastSim.tutorial.skipTime==0)
heldKeys[KEY_ESCAPE]=nil;flush(.001);holdEscape(1.25);assert(lastSim:CanAct())
Stop()
''',
    'natural completion and skipped completion do not replay on continue but recur next run':r'''
autoSkipTutorial=false;Start();openStory()
local t=lastSim.tutorial;t:Enter('task')
for _=1,60 do flush(.1) end
assert(not t.active and t.completed and lastSim:CanAct())
key(KEY_ESCAPE);flush();click('pauseMenu');flush();openStory()
assert(lastSim.tutorial==t and not t.active)
Stop();Start();openStory();assert(lastSim.tutorial.active and lastSim.tutorial.step=='intro')
Stop()
''',
}

def run():
    passed=[]
    for name,code in CASES.items():
        lua=runtime();lua.globals().print=lambda *args:None;lua.execute(code)
        passed.append(name);print('PASS:',name,flush=True)
    out=Path(__file__).resolve().parents[1]/'validation/embedded-tutorial-20261018'
    out.mkdir(parents=True,exist_ok=True)
    (out/'regression.json').write_text(json.dumps({'passed':passed,
        'scope':'Production Lua lifecycle, keyboard state polling, overlay state and audio dispatch; native Yoga/device input and hearing excluded'},ensure_ascii=False,indent=2),encoding='utf8')

if __name__=='__main__':
    run()
