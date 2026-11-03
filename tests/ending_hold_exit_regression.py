"""Real ending logic with native UI, decoder and key-state polling at the boundary."""
from pathlib import Path
import json
from ending_cinematic_regression import runtime, menu_runtime

CASES = {
    'normal film has no skip button, and tapping Esc never exits': r'''
victory();readyFilm();tick(.3)
assert(not screen.root:FindById('endingSkip') and not screen.back:IsVisible())
assert(not screen.exitArea:IsVisible() and not screen.exitMask:IsVisible())
for _=1,4 do screen:HandleKey(KEY_ESCAPE);tick(.02) end
assert(not screen.finishRequested and screen.exitTime==0 and screen.phase=='video')
''',
    'hold shows tutorial-style progress and dimming; release cancels instead of accumulating': r'''
victory();local p=readyFilm()
for _=1,3 do
 holdExit(.5);assert(not screen.finishRequested and screen.exitTime==0)
 assert(not screen.exitArea:IsVisible() and not screen.exitMask:IsVisible())
end
heldKeys[KEY_ESCAPE]=true;screen:HandleKey(KEY_ESCAPE);tick(.6)
assert(screen.exitArea:IsVisible() and screen.exitMask:IsVisible())
assert(screen.exitHint.props.text=='正在退出 · 50%' and screen.exitFill.props.width=='50.0%')
assert(math.abs(screen.exitMask.props.backgroundColor[4]-95)<=1)
assert(screen.exitArea.props.pointerEvents=='none' and screen.exitArea.props.nativeMenuInset)
tick(.58);assert(not screen.finishRequested)
tick(.02);assert(screen.finishRequested and screen.phase=='videoOut' and screen.exitMask:IsVisible())
tick(.5);assert(menuCalls==1 and p.stopped and p.destroyed and not screen.exitArea:IsVisible())
''',
    'focus loss, minimize and frame stalls cannot accidentally complete the hold': r'''
victory();readyFilm();heldKeys[KEY_ESCAPE]=true;screen:HandleKey(KEY_ESCAPE)
screen:Update(10);assert(screen.exitTime==.1 and not screen.finishRequested)
screen:Update(0/0);screen:Update(math.huge);screen:Update(-math.huge)
assert(screen.exitTime==.1 and not screen.finishRequested)
tick(.4);input.focus=false;tick(.02)
assert(screen.exitTime==0 and not screen.exitArea:IsVisible() and not screen.exitArmed)
input.focus=true;tick(2);assert(not screen.finishRequested)
heldKeys[KEY_ESCAPE]=nil;tick(.02)
heldKeys[KEY_ESCAPE]=true;screen:HandleKey(KEY_ESCAPE);tick(.4)
input.minimized=true;tick(.02);assert(screen.exitTime==0 and not screen.exitMask:IsVisible())
input.minimized=false;heldKeys[KEY_ESCAPE]=nil;tick(.02);holdExit();tick(.5)
assert(menuCalls==1)
''',
    'Esc already held before the film cannot carry over, and reset clears progress': r'''
heldKeys[KEY_ESCAPE]=true;screen:Show('victory');screen:HandleKey(KEY_ESCAPE)
tick(.6);readyFilm();tick(2)
assert(screen.exitTime==0 and not screen.finishRequested)
heldKeys[KEY_ESCAPE]=nil;tick(.02)
heldKeys[KEY_ESCAPE]=true;screen:HandleKey(KEY_ESCAPE);tick(.5)
assert(screen.exitTime>.4);screen:Reset()
assert(screen.exitTime==0 and not screen.exitArmed and not screen.exitArea:IsVisible())
screen:Show('victory');tick(.6);readyFilm();tick(2)
assert(not screen.finishRequested and not screen.exitMask:IsVisible())
''',
    'loading and errors retain a hold exit, while the back button exists only for errors': r'''
local p=victory();assert(not screen.back:IsVisible());holdExit();tick(.5)
assert(menuCalls==1 and p.destroyed)
p=victory();p.props.onLoadError(p,2,'ERROR_SOURCE_NOT_FOUND');tick(.02)
assert(screen.back:IsVisible() and screen.play.props.text=='重试播放')
heldKeys[KEY_ESCAPE]=true;screen:HandleKey(KEY_ESCAPE);tick(.5)
screen.play.props.onClick()
assert(screen.phase=='waiting' and screen.exitTime==0 and not screen.back:IsVisible())
readyFilm();tick(2);assert(not screen.finishRequested)
heldKeys[KEY_ESCAPE]=nil;tick(.02);holdExit();tick(.5);assert(menuCalls==2)
''',
}


def main():
    passed=[]
    for name, code in CASES.items():
        runtime().execute(code)
        passed.append(name)
        print('PASS:', name)
    lua=menu_runtime()
    lua.execute(r'''
local oldNew=package.loaded['UI.HUD'].New
package.loaded['UI.HUD'].New=function(props)
 local h=oldNew(props);local build=h.Build;local update=h.Update
 function h:Build()
  build(self);self.onMenu=props.onMenu;self.onCredits=props.onCredits
  self.endingScreen=require('UI.EndingScreen').New(self);self.root:AddChild(self.endingScreen.root)
  return self.root
 end
 function h:Update(dt) update(self,dt);self.endingScreen:Update(dt) end
 reviewHUD=h;return h
end
Start();openStory();lastSim:FinishRun('victory');reviewHUD.endingScreen:Show('victory')
for _=1,7 do flush(.1) end
key(KEY_ESCAPE);flush(.1)
assert(not reviewHUD.endingScreen.finishRequested and not UI.root:FindById('pauseOverlay'))
heldKeys[KEY_ESCAPE]=true;key(KEY_ESCAPE)
for _=1,11 do flush(.1) end
assert(not reviewHUD.endingScreen.finishRequested)
flush(.1);assert(reviewHUD.endingScreen.finishRequested)
for _=1,7 do flush(.1) end
assert(UI.root.props.id=='creditsScreen' and not UI.root:FindById('pauseOverlay'))
for _=1,15 do flush(.1) end
assert(UI.root.props.id=='creditsScreen','film hold must not carry into credits')
heldKeys[KEY_ESCAPE]=nil;flush(.01);skipCredits()
assert(UI.root.props.id=='mainMenu');Stop()
''')
    passed.append('real main key routing transfers film to credits with a fresh hold required')
    out=Path(__file__).resolve().parents[1]/'validation/ending-handoff-20261019/hold-exit.json'
    out.write_text(json.dumps({'passed':len(passed),'checks':passed,'hold_seconds':1.2,
        'native_input_delivery_verified':False},ensure_ascii=False,indent=2),'utf-8')
    print(f'{len(passed)} hold-to-exit checks passed.')


if __name__=='__main__':
    main()
