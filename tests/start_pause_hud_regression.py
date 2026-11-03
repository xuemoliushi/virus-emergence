"""Startup/pause/ticker regressions using production Lua; native UI is a boundary."""
from pathlib import Path
import json
from main_menu_regression import runtime as menu_runtime
from bird_ui_regression import runtime as hud_runtime

ROOT = Path(__file__).resolve().parents[1]

MENU_CASES = {
    'production 960-cell world finishes idle preload without advancing simulation': r'''
local cfg=require('Core.Config').Gameplay
cfg.mapGenerationVersion=5;cfg.width=120;cfg.height=144;cfg.cellCount=960
cfg.mapSeed=314159 -- deterministic readiness fixture, independent of wall-clock seeds
Start()
for _=1,10000 do
 uiTick(.016);flush(.016)
 if UI.root:FindById('menuPreparation').props.text:find('已就绪') then break end
end
assert(UI.root:FindById('menuPreparation').props.text:find('已就绪'))
assert(#lastSim.world.map.cells==960 and lastSim.time==0 and lastSim.paused)
assert(gameCreates==1 and UI.root.props.id=='mainMenu')
Stop();assert(gameDestroys==1)
''',
    'menu preloads and renders a paused world before any Start click': r'''
Start()
for _=1,300 do
 uiTick(.016);flush(.016)
 if UI.root:FindById('menuPreparation').props.text:find('已就绪') then break end
end
assert(UI.root.props.id=='mainMenu' and gameCreates==1)
local sim,world=lastSim,lastSim.world
assert(sim.time==0 and sim.paused and not sim.tutorial.active)
assert(not UI.root:FindById('gameScene') and not UI.root:FindById('entryWarmShield'))
require('Core.SimState').New=function() error('World rebuilt on click') end
local original=cache.GetResource
cache.GetResource=function(self,kind,path)
 assert(path~='audio/bgm.mp3','Music was not preloaded')
 return original(self,kind,path)
end
click('storyMode');flush(.016)
assert(UI.root:FindById('entryFade') and not UI.root:FindById('entryLoading'))
finishEntry();assert(lastSim==sim and sim.world==world and sim:CanAct())
assert(gameCreates==1)
Stop();assert(gameDestroys==1)
''',
    'settings and credits during warmup preserve the partially warmed world': r'''
Start()
for _=1,300 do flush(.016);if UI.root:FindById('gameScene') then break end end
local scene=assert(UI.root:FindById('gameScene'))
click('openSettings');flush();assert(UI.root.props.id=='settingsScreen' and not scene.destroyed)
uiTick(.016);flush(.016)
key(KEY_ESCAPE);flush();click('openCredits');flush();uiTick(.016);flush(.016)
skipCredits()
for _=1,20 do uiTick(.016);flush(.016) end
assert(UI.root:FindById('menuPreparation').props.text:find('已就绪'))
assert(not scene.destroyed and gameCreates==1 and lastSim.time==0)
openStory();assert(UI.root:FindById('gameScene')==scene and gameCreates==1)
Stop();assert(gameDestroys==1)
''',
    'pause settings keeps game root, music and authority; reset never replaces game': r'''
Start();openStory();uiTick(.25);flush(.25)
local root,scene,sim,world=UI.root,UI.root:FindById('gameScene'),lastSim,lastSim.world
local time,plays=sim.time,sources.MusicSource.plays
sim.touchMove={x=1,y=1,active=true}
key(KEY_ESCAPE);flush()
local overlay=assert(root:FindById('pauseOverlay'))
assert(UI.root==root and overlay.parent==root and overlay.props.position=='absolute')
assert(overlay.props.zIndex>10000 and overlay.props.backgroundColor[4]<255)
assert(not sim.touchMove.active and sim.pauseReasons.settings and not sim.pauseReasons.mainMenu)
for _=1,60 do uiTick(.016);flush(.016) end
assert(sim.time==time and sources.MusicSource.plays==plays)
local scale=root:FindById('uiScale');scale.props.onChange(scale,1.15)
assert(UI.root==root and root:FindById('gameScene')==scene)
click('resetSettings');flush();assert(overlay.destroyed and UI.root==root and sim.paused)
key(KEY_R);key(KEY_E);assert(sim.world==world and sim.time==time)
click('settingsBack');flush()
assert(not root:FindById('pauseOverlay') and not root:FindById('entryFade'))
assert(lastSim==sim and sim.world==world and sim:CanAct())
uiTick(.25);assert(sim.time>time)
key(KEY_ESCAPE);flush();click('pauseMenu');flush();assert(UI.root.props.id=='mainMenu')
assert(sim.pauseReasons.mainMenu and not sim.pauseReasons.settings)
Stop();assert(gameDestroys==1)
''',
    'closing settings releases only settings pause and keeps card/tutorial reasons': r'''
Start();openStory();lastSim:SetPaused('cardChoice',true)
key(KEY_ESCAPE);flush();key(KEY_ESCAPE);flush()
assert(lastSim.paused and lastSim.pauseReasons.cardChoice and not lastSim.pauseReasons.settings)
lastSim:SetPaused('cardChoice',false);assert(lastSim:CanAct())
lastSim:SetPaused('tutorial',true)
key(KEY_ESCAPE);flush();click('settingsBack');flush()
assert(lastSim.paused and lastSim.pauseReasons.tutorial)
Stop();assert(gameDestroys==1)
''',
    'shutdown while idle preload is suspended does not resume work': r'''
Start()
local Sim=require('Core.SimState');local original=Sim.New;local resumed=false
Sim.New=function() coroutine.yield();resumed=true;return original() end
flush();flush();Stop()
assert(not resumed and gameCreates==0 and UI.root==nil)
''',
}

HUD_CASES = {
    'real absorption and expiry leave the ticker and action hierarchy fixed': r'''
local h,g,s=fixture()
local ticker=h.root:FindById('statusTicker')
local dock=h.root:FindById('actionDock')
local row=h.root:FindById('dockActions')
assert(dock.children[1]==ticker and dock.children[2]==row)
assert(ticker.props.height==36 and ticker.props.minHeight==36 and ticker.props.maxHeight==36)
assert(ticker.props.overflow=='hidden' and ticker.props.flexShrink==0)
local label=assert(h.root:FindById('actionNotice'))
assert(label.parent==ticker and label.props.position=='absolute')
local player=s.world.player
s.world:_Release(s.world.cells[1],2)
for _,v in ipairs(s.world.releasedViruses) do v.x,v.y=player.x,player.y end
local mass=player.mass
callback(h,'absorbBtn');assert(player.mass>mass and label.props.text:find('已吸附'))
for _=1,180 do
 h:Update(.1)
 assert(label:IsVisible() and ticker:IsVisible())
 assert(ticker.props.height==36 and ticker.props.minHeight==36 and ticker.props.maxHeight==36)
 assert(dock.children[1]==ticker and dock.children[2]==row)
end
assert(not h.root:FindById('absorptionStatus'):IsVisible())
assert(not h.root:FindById('swarmStatusDetail'):IsVisible())
''',
    'ticker scrolls current state, resets on an action and stays bounded across a stall': r'''
local h,g,s=fixture()
h:SetText('swarmStatusDetail','当前状态甲');h:SetText('absorptionStatus','当前状态乙')
h:Notify('')
h:UpdateTicker(4.8)
local a,b=h.root:FindById('actionNotice'),h.root:FindById('actionNoticeNext')
assert(a.props.text=='当前状态甲' and b.props.text=='当前状态乙')
assert(a.props.translateY<0 and a.props.translateY>-36)
h:UpdateTicker(.3);assert(a.props.text=='当前状态乙')
h:Notify('新的吸收提示');assert(a.props.text=='新的吸收提示' and a.props.translateY==0)
h:UpdateTicker(10000);assert(a.props.translateY>=-36 and a.props.translateY<=0)
''',
}

if __name__ == '__main__':
    results=[]
    for factory,cases in [(menu_runtime,MENU_CASES),(hud_runtime,HUD_CASES)]:
        for name,code in cases.items():
            lua=factory();lua.globals().print=lambda *args: None
            if factory==hud_runtime:
                lua.execute('Config.Gameplay.mapGenerationVersion=1;Config.Gameplay.width=26;Config.Gameplay.height=32;Config.Gameplay.cellCount=72')
            lua.execute(code)
            results.append(name);print('PASS:',name)
    out=ROOT/'validation/start-pause-hud-20261018'
    out.mkdir(parents=True,exist_ok=True)
    (out/'regression.json').write_text(json.dumps({'passed':results,
        'scope':'Production Lua startup, settings callbacks, pause reasons, real absorption and ticker; native Yoga/GPU are boundaries'},ensure_ascii=False,indent=2),encoding='utf8')
