"""真实 Lua 界面生命周期回归；引擎边界为桩，不代表画面和真机输入验收。"""
import sys
from observation_regression import SETUP as LEGACY_SETUP, ROOT, LuaRuntime

# Reuse only the existing native/UI boundary fixture; never load retired views.
SETUP = LEGACY_SETUP.split('function sceneFixture')[0]
SETUP = SETUP.replace("Observation = require('Core.ObservationState')", '')
SETUP = SETUP.replace("MouseView=require('Game.Views.MouseView')", '')
SETUP += r'''
function UI.ClearFocus() end
function UI.Widget:SetFontColor(color) self.props.fontColor=color end
function hudFixture()
 local sim,scale=Sim.New(),Scale.New()
 local game=GameScene{sim=sim,scaleMgr=scale,id='gameScene'}
 local hud=HUD.New{sim=sim,scaleMgr=scale}
 UI.root=hud:Build()
 return hud,game,sim,scale,nil
end
function guidedStart(hud,sim,scale,unused,region)
 assert(sim:StartRun(region or 'UPPER_AIRWAY'))
 hud:Update(.2)
 assert(scale:CurrentScale()=='cell' and not scale:IsTransitioning())
end
function callback(hud,id,event)
 local btn=assert(hud.root:FindById(id),'Missing widget '..id)
 assert(btn.props.onClick,'Missing callback '..id)(btn,event)
end
function fixture()
 local h,g,s,scale=hudFixture()
 guidedStart(h,s,scale)
 return h,g,s,scale
end
function effectivelyVisible(widget)
 if not widget then return false end
 while widget do
  if not widget:IsVisible() then return false end
  widget=widget.parent
 end
 return true
end
'''

TESTS = {
    'normal play has no host view or organ selection and bird stays hidden': r'''
local h,g,s,scale=fixture()
for _,id in ipairs({'observeBtn','scale_mouse','scale_cell','observationOverlay',
 'lungHotspot','anatomyToggleBtn','startRunBtn','start_DEEP_LUNG','endingObserveBtn'}) do
 assert(not h.root:FindById(id),'Retired UI still exists: '..id)
end
assert(not package.loaded['Game.Views.MouseView'] and not package.loaded['Core.ObservationState'])
assert(not effectivelyVisible(h.root:FindById('endingBird')))
local time=s.time;g:Update(.1);assert(s.time>time and not s.paused)
scale:JumpTo('mouse',true)
for _=1,100 do scale:OnWheel(-1);scale:Update(.1) end
assert(scale:CurrentScale()=='cell' and not s.pauseReasons.observation)
''',
    'both endings preserve statistics and reveal a clean result after fade': r'''
for _,outcome in ipairs({'victory','extinct'}) do
 local h,g,s=fixture();s.ending=outcome;h:ShowEnding()
 h.endingScreen:Update(.4);h.endingScreen:Update(.4)
 assert(effectivelyVisible(h.root:FindById('endingResult')))
 assert(not h.root:FindById('endingBird') and not h.root:FindById('endingFrame'))
 assert(h.root:FindById('endingReason'):GetText():find('鸟'))
 assert(h.root:FindById('endingTime'):GetText():find('总时间'))
 h.onRestart=function() assert(s:StartRun('UPPER_AIRWAY')) end
 callback(h,'restartBtn')
 assert(not s.ending and not h.root:FindById('endingOverlay'):IsVisible())
 h:Destroy();g:Destroy()
end
''',
    'failure never falls through to the victory film': r'''
local h,g,s=fixture();Config.EndingVideo.victory='video/victory.mp4';Config.EndingVideo.extinct=false
package.loaded['urhox-libs/Video']={isSupported=true,VideoPlayer=function() error('failure loaded victory film') end}
s.ending='extinct';h:ShowEnding();h.endingScreen:Update(.4)
assert(h.endingScreen.result:IsVisible() and not h.endingScreen.player)
h:Destroy();g:Destroy()
''',
    'HUD menu and ending menu dispatch callbacks and clear touch movement': r'''
local h,g,s=fixture();local calls=0
h.onMenu=function() calls=calls+1;s:SetPaused('mainMenu',true) end
s.touchMove.x,s.touchMove.active=1,true
callback(h,'menuBtn');assert(calls==1 and s.pauseReasons.mainMenu and not s.touchMove.active)
s:SetPaused('mainMenu',false);s.ending='extinct';h:ShowEnding()
callback(h,'endingMenuBtn');assert(calls==2)
''',
    'formal card offer still blocks play and resumes after selection': r'''
local h,g,s=fixture()
assert(s:GrantCardChoice('bird-ui-test'))
assert(h.cardInfoShown_ and s.paused and h.root:FindById('cardInfoOverlay'):IsVisible())
local pending=s.cards.pending
callback(h,'cardGet_'..pending.cards[1].id)
assert(s.cards.pending==pending and not s.cardNotice,'reveal blocks premature selection')
finishCardReveal(h)
callback(h,'cardGet_'..pending.cards[1].id)
assert(not s.cardNotice and s.cards.pending==pending and h.cardSelectedId_==pending.cards[1].id)
assert(h.root:FindById('cardContinue'):GetText()=='确定')
callback(h,'cardContinue')
assert(not h.cardInfoShown_ and not s.paused and not s.cardNotice)
assert(not effectivelyVisible(h.root:FindById('endingBird')))
''',
    'keyboard and touch share movement, pause clears input, focus gate persists': r'''
local h,g,s=fixture()
keys[KEY_D]=true
local kx,ky=g:ReadMovement(g:GetAbsoluteLayout());near(kx,1);near(ky,0)
g:Update(.1)
keys[KEY_D]=false
s.touchMove.x,s.touchMove.y,s.touchMove.active=0,1,true
local dx,dy=g:ReadMovement(g:GetAbsoluteLayout());near(dx,0);near(dy,1)
s:SetPaused('mainMenu',true);h:Update(.1);assert(not s.touchMove.active)
s:SetPaused('mainMenu',false);input.focus=false;g:Update(.1)
assert(s.pauseReasons.focus);input.focus=true;g:Update(.1);assert(not s.pauseReasons.focus)
''',
}

def runtime():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('package.path=' + repr(str(ROOT/'scripts/?.lua').replace('\\','/')) + "..';'..package.path")
    lua.execute(SETUP)
    return lua


if __name__ == '__main__':
    failures = []
    for name, code in TESTS.items():
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute('package.path=' + repr(str(ROOT/'scripts/?.lua').replace('\\','/')) + "..';'..package.path")
        lua.globals().print = lambda *args: None
        try:
            lua.execute(SETUP + code)
            print('PASS', name)
        except Exception as error:
            failures.append(name)
            print('FAIL', name, error)
    print(f'Bird UI: {len(TESTS)-len(failures)}/{len(TESTS)}')
    sys.exit(bool(failures))
