"""Retired shortcuts must have no effect in the shipped main entry."""
from main_menu_regression import runtime

checks = {
    'retired shortcuts cannot start from menu or trigger a Windows ending': r'''
KEY_F8=119;KEY_F9=120;KEY_F10=121;GetPlatform=function() return 'Windows' end
Start();finishPreload()
local root,sim,world=UI.root,lastSim,lastSim.world
for _,k in ipairs({KEY_R,KEY_F8,KEY_F9,KEY_F10}) do key(k);flush(.1) end
assert(UI.root==root and not UI.root:FindById('entryFade') and sim.world==world)
openStory();local time=sim.time
for _,k in ipairs({KEY_R,KEY_F8,KEY_F9,KEY_F10}) do key(k);key(k,true);flush(.1) end
for _=1,40 do flush(.1) end
assert(UI.root.props.id=='uiRoot' and sim.world==world and sim.time==time)
assert(sim.ending==nil and not sim.debugRun and sim:CanAct());Stop()
''',
    'retired keys leave active teaching and paused state untouched': r'''
KEY_F8=119;KEY_F9=120;KEY_F10=121;GetPlatform=function() return 'Windows' end
autoSkipTutorial=false;Start();openStory()
local sim,world,t=lastSim,lastSim.world,lastSim.tutorial
for _,k in ipairs({KEY_R,KEY_F8,KEY_F9,KEY_F10}) do key(k);flush(.1) end
for _=1,40 do flush(.1) end
assert(sim.tutorial==t and t.active and sim.world==world and not sim.debugRun and not sim.ending)
holdEscape(1.25);key(KEY_ESCAPE);flush()
local pause=assert(UI.root:FindById('pauseOverlay'))
for _,k in ipairs({KEY_R,KEY_F8,KEY_F9,KEY_F10}) do key(k);flush(.1) end
assert(UI.root:FindById('pauseOverlay')==pause and sim.world==world and sim.pauseReasons.settings)
key(KEY_ESCAPE);flush();assert(sim:CanAct());Stop()
''',
    'Web shortcuts cannot enable performance collection or request debug reports': r'''
KEY_F8=119;KEY_F9=120;KEY_F10=121;GetPlatform=function() return 'Web' end
Start();openStory()
local Stats=require('Core.PerformanceStats');Stats.SetEnabled(false)
Stats.SetEnabled=function() error('retired F9 enabled diagnostics') end
Stats.Snapshot=function() error('retired F10 requested a debug report') end
local world=lastSim.world
for _,k in ipairs({KEY_R,KEY_F8,KEY_F9,KEY_F10}) do key(k);flush(.1) end
for _=1,40 do flush(.1) end
assert(lastSim.world==world and not lastSim.ending and not lastSim.debugRun);Stop()
''',
}
for name, code in checks.items():
    runtime().execute(code)
    print('PASS:', name)
