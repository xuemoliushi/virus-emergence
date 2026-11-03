"""Real mobile UI control flow; native layout is checked separately in Runtime."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.tmp/test-deps'))
from ending_cinematic_regression import runtime as ending_runtime
from tutorial_regression import SETUP
from main_menu_regression import runtime as menu_runtime
from map_overview_regression import runtime as map_runtime


def check(name, runtime, source):
    lua = runtime()
    lua.globals().print = lambda *args: None
    lua.execute(source)
    print('PASS:', name)


if __name__ == '__main__':
    check('touch map return releases only map pause and restores the same camera', map_runtime, r'''
local game,sim,scale=sceneFixture(true)
game:Update(.016);local world=sim.world;local time=sim.time
assert(game:ToggleMap());for _=1,30 do game:Update(.02) end
sim:SetPaused('settings',true)
local back=assert(game.mapLegend:FindById('overviewMapClose'))
back.props.onClick();for _=1,30 do game:Update(.02) end
assert(not game:IsMapActive() and not sim.pauseReasons.map)
assert(sim.pauseReasons.settings and sim.world==world and sim.time==time)
game:Destroy()
''')
    check('touch film skip cancels on release and completes exactly once after a full hold', ending_runtime, r'''
require('UI.MobileLayout').MarkTouch()
victory();readyFilm();assert(screen.touchControls:IsVisible())
screen.touchSkipButton.state={pressed=true};tick(.6)
assert(screen.exitTime>.5 and not screen.finishRequested)
screen.touchSkipButton.state.pressed=false;tick(.04)
assert(screen.exitTime==0 and not screen.finishRequested)
screen.touchSkipButton.state.pressed=true;tick(1.24);tick(.5)
assert(menuCalls==1 and screen.phase=='complete' and not screen.touchControls:IsVisible())
tick(1);assert(menuCalls==1)
''')
    check('film hold is cancelled when focus is lost', ending_runtime, r'''
require('UI.MobileLayout').MarkTouch();victory();readyFilm()
screen.touchSkipButton.state={pressed=true};tick(.5)
input.focus=false;tick(.1);assert(screen.exitTime==0 and not screen.finishRequested)
screen.touchSkipButton.state.pressed=false;input.focus=true;tick(.1)
assert(screen.exitTime==0 and not screen.finishRequested)
''')
    check('tutorial disclosure preserves lesson and resets on the next lesson', menu_runtime, SETUP + r'''
require('UI.MobileLayout').MarkTouch()
UI.GetSafeAreaInsets=function() return {left=0,right=0,top=0,bottom=0} end
graphics.width,graphics.height=844,390
local s,t=tutorialFixture();local o=Overlay.New(s,sceneFixture(s))
t:Enter('infect');o:Update();local time=s.time
assert(o.card.props.height==60 and not o.body:IsVisible() and o.expandButton:IsVisible())
o.expandButton.props.onClick();o:Update()
assert(o.body:IsVisible() and o.touchSkipButton:IsVisible() and t.step=='infect' and s.time==time)
o.expandButton.props.onClick();o:Update();assert(not o.body:IsVisible())
o.expandButton.props.onClick();o:Update();t:Enter('wait');o:Update()
assert(not o.body:IsVisible() and o.card.props.height==60)
t:Enter('tcell');o:Update()
assert(o.body:IsVisible() and o.continueButton:IsVisible() and not o.expandButton:IsVisible())
''')
    print('4 mobile priority control-flow checks passed; native layout checked separately.')
