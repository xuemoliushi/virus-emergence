"""Real Lua map/camera/simulation checks; native UI/rendering use fixtures."""
from pathlib import Path
import json
from observation_regression import runtime as ui_runtime, ROOT
from cell_render_regression import SETUP as CELL_SETUP

def runtime():
    lua=ui_runtime()
    lua.globals().SCRIPT_PATH=str(ROOT/'scripts/?.lua').replace('\\','/')
    lua.execute("package.loaded['Game.Views.CellView']=nil")
    lua.execute(CELL_SETUP)
    lua.execute('''
graphics.GetDPR=function() return 1 end
-- Keep production camera math; native visual physics is outside this suite.
View.Update=function() end
package.loaded['Game.GameScene']=nil;GameScene=require('Game.GameScene')
''')
    return lua

CASES = {
    'full map fits wide, portrait and small screens and restores the exact transform': r'''
local Map=require('Game.MapOverview')
local map=Map.New();local world={width=120,height=144}
for _,size in ipairs({{1920,1080},{960,540},{390,844},{240,180}}) do
 local l={x=17,y=31,w=size[1],h=size[2]}
 map.amount=0
 local scale,x,y=map:Transform(l,world,123,-281,-910)
 near(scale,123);near(x,-281);near(y,-910)
 map.amount=1
 local area=map:Area(l)
 scale,x,y=map:Transform(l,world,123,-281,-910)
 local oldFit=math.min((l.w-36)/world.width,(l.h-math.min(64,l.h*.22)-math.min(80,l.h*.25))/world.height)*.94
 assert(scale>oldFit,'map should occupy more of the screen than the original overview')
 assert(x>=area.x and y>=area.y)
 assert(x+120*scale<=area.x+area.w and y+144*scale<=area.y+area.h)
 near(x+60*scale,area.x+area.w/2);near(y+72*scale,area.y+area.h/2)
end
''',
    'real simulation freezes while map animation and density snapshot remain live': r'''
local game,sim,scale=sceneFixture(true)
game:Update(.016)
local time,ticks,mass=sim.time,sim.tickCount,sim.world.player.mass
local zoom=scale:CurrentZoom()
assert(game:ToggleMap() and sim.pauseReasons.map and sim.paused)
local count=0;for _,b in ipairs(game.mapView.bins)do count=count+b.count end
assert(count==sim:TotalVirus(),'must count both populations once, excluding terminal records')
for _=1,60 do game:Update(1/60) end
assert(game.mapView.amount==1 and game.mapView.time>.9)
near(sim.time,time);assert(sim.tickCount==ticks and sim.world.player.mass==mass)
local l=game:GetAbsoluteLayout();local area=game.mapView:Area(l)
local x,y=game.cellView:WorldToScreen(0,0,l,1)
local right,bottom=game.cellView:WorldToScreen(sim.world.width,sim.world.height,l,1)
assert(x>=area.x and y>=area.y and right<=area.x+area.w and bottom<=area.y+area.h)
for _,p in ipairs({{0,0},{20,80},{120,144}})do
 local sx,sy=game.cellView:WorldToScreen(p[1],p[2],l,1)
 local wx,wy=game.cellView:ScreenToWorld(sx,sy,l,1);near(wx,p[1]);near(wy,p[2])
end
sim:SetPaused('settings',true);game:CloseMap()
for _=1,30 do game:Update(1/60) end
assert(not game:IsMapActive() and not sim.pauseReasons.map and sim.pauseReasons.settings and sim.paused)
assert(game.cellView.overviewFrame==nil and not game.mapLegend:IsVisible())
near(scale:CurrentZoom(),zoom)
sim:SetPaused('settings',false);assert(sim:CanAct())
game:Update(.1);assert(sim.time>time,'simulation must resume without catch-up')
game:Destroy()
''',
    'midflight M reversal is continuous, movement and wheel stay blocked': r'''
local game,sim,scale=sceneFixture(true)
game:Update(.016);assert(game:ToggleMap())
for _=1,8 do game:Update(.016) end
local value=game.mapView.amount;local l=game:GetAbsoluteLayout()
local beforeX,beforeY=game.cellView:WorldToScreen(20,30,l,1)
assert(game:ToggleMap());near(game.mapView.amount,value)
local afterX,afterY=game.cellView:WorldToScreen(20,30,l,1)
near(beforeX,afterX);near(beforeY,afterY)
local target=scale.zoomTarget[1];game:OnWheel(0,100);near(scale.zoomTarget[1],target)
keys.W=true;local dx,dy=game:ReadMovement(l);near(dx,0);near(dy,0)
game:Update(.016);assert(game.mapView.amount<value and sim.pauseReasons.map)
assert(game:ToggleMap());game:Update(.016);near(game.mapView.amount,value)
game:CancelMap();assert(sim:CanAct());game:Destroy()
''',
    'snapshot counts independent IDs once and red includes only healthy cells': r'''
local Map=require('Game.MapOverview');local map=Map.New()
local world={viruses={{id=1,x=1,y=1},{id=2,x=1,y=1}},releasedViruses={
 {id=1,x=1,y=1,state='RELEASED'},{id=2,x=2,y=2,state='CLEARED'},
 {id=3,x=2,y=2,state='LOST'},{id=4,x=2,y=2,state='ABSORBED'},{id=5,x=2,y=2,state='CONVERTED'}},
 cells={{id=1,x=3,y=4,state='HEALTHY'},{id=2,x=0,y=0,state='EXPOSED'},
 {id=3,x=0,y=0,state='LATENT'},{id=4,x=0,y=0,state='DEAD'}},
 immunes={{id=1,x=8,y=9}}}
map:Capture(world,1);assert(#map.bins==1 and map.bins[1].count==3)
assert(#map.healthy==1 and map.healthy[1].x==3 and #map.immunes==1)
map.target=1;map:Update(.1);local t=map.time;map:Update(.1);assert(map.time>t)
assert(world.viruses[1].x==1 and world.cells[1].state=='HEALTHY')
''',
    'bottom map button opens the same scene and seed text follows the current map': r'''
local game,sim,scale=sceneFixture(true)
local hud=HUD.New{sim=sim,scaleMgr=scale,onMap=function()game:ToggleMap()end}
local root=hud:Build();game.hudRoot=root;hud:Update(.2)
local btn=assert(root:FindById('mapBtn'))
assert(btn.parent==root:FindById('baseActionRow') and btn.props.text=='地图 M')
assert(btn.assetIcon_.props.backgroundImage=='image/ui/icons/icon_cluster_dispatch.png')
assert(not btn:IsDisabled())
btn.props.onClick(btn)
assert(game:IsMapActive() and sim.pauseReasons.map)
assert(game.mapLegend:FindById('overviewMapSeed'):GetText()=='地图种子 '..sim.world.map.seed)
game:CancelMap();sim.world.map.seed=987654;btn.props.onClick(btn)
assert(game.mapLegend:FindById('overviewMapSeed'):GetText()=='地图种子 987654')
game:CancelMap();sim:SetPaused('settings',true);hud:RefreshStrategyHighlight()
assert(btn:IsDisabled());btn.props.onClick(btn);assert(not game:IsMapActive())
sim:SetPaused('settings',false);sim.tutorial={active=true,Allows=function()return true end};hud:RefreshStrategyHighlight()
assert(btn:IsDisabled());sim.tutorial=nil
hud:Destroy();game:Destroy()
''',
    'tutorial, paused, entry and ending gates; reset releases map state': r'''
local game,sim=sceneFixture(true)
sim.tutorial={active=true};assert(not game:ToggleMap());sim.tutorial=nil
sim:SetPaused('card-info',true);assert(not game:ToggleMap());sim:SetPaused('card-info',false)
game.entryActive=true;assert(not game:ToggleMap());game.entryActive=false
sim.ending='victory';assert(not game:ToggleMap());sim.ending=nil
assert(game:ToggleMap());game:Update(.1)
Bus.Emit(Bus.Events.SIM_RESET,{})
assert(not game:IsMapActive() and not sim.pauseReasons.map and game.cellView.overviewFrame==nil)
assert(#game.mapView.bins==0 and not game.mapLegend:IsVisible());game:Destroy()
''',
    'map rendering uses red yellow blue and white and pulses while simulation is frozen': r'''
local game,sim=sceneFixture(true);game:Update(.016)
-- Colour/animation fixture deliberately explores everything; fog is tested separately.
game.exploration.radius=250;game.exploration:Reset(sim.world);game.exploration:Observe(sim.world)
assert(game:ToggleMap())
for _=1,30 do game:Update(1/60) end
local colors={}
function nvgRGBA(r,g,b,a) return {r,g,b,a} end
function nvgFillColor(vg,c)colors[#colors+1]=c end
local strokes={};function nvgStrokeColor(vg,c)strokes[#strokes+1]=c end
game:Render({})
local red,yellow,blue=false,false,false
local firstAlpha
for _,c in ipairs(colors)do
 if c[1]==255 and c[2]==76 and c[3]==88 then red=true;firstAlpha=firstAlpha or c[4] end
 if c[1]==255 and c[2]==212 and c[3]==63 then yellow=true end
 if c[1]==72 and c[2]==165 and c[3]==255 then blue=true end
end
assert(red and yellow and blue)
local ring=strokes[#strokes];assert(ring[1]==247 and ring[2]==247 and ring[3]==225)
local before=sim.time;colors={};game:Update(.1);game:Render({})
near(sim.time,before)
local changed=false
for _,c in ipairs(colors)do
 if c[1]==255 and c[2]==76 and c[3]==88 then changed=c[4]~=firstAlpha;break end
end
assert(changed,'pulsing must use presentation time, not frozen world.time')
game:Destroy()
''',
}

if __name__ == '__main__':
    passed=[]
    for name,code in CASES.items():
        runtime().execute(code)
        passed.append(name)
        print('PASS '+name)
    # Actual main.lua dispatch; the scene boundary records calls, not camera behaviour.
    from main_menu_regression import runtime as main_runtime
    main_runtime().execute(r'''
KEY_M='M'
local openMap
local makeHUD=package.loaded['UI.HUD'].New
package.loaded['UI.HUD'].New=function(props)openMap=props.onMap;return makeHUD(props)end
Start();openStory()
local scene=UI.root:FindById('gameScene');local toggles,closes,cancels=0,0,0
local active=false
function scene:IsMapActive()return active end
function scene:ToggleMap()toggles=toggles+1;active=true;return true end
function scene:CloseMap()closes=closes+1 end
function scene:CancelMap()cancels=cancels+1;active=false end
assert(openMap);openMap();assert(toggles==1 and active)
toggles,active=0,false
key(KEY_M,true);assert(toggles==0,'repeat must not toggle')
key(KEY_M);assert(toggles==1 and active)
key(KEY_M);assert(toggles==2)
local creates=gameCreates;key(KEY_R);assert(gameCreates==creates)
key(KEY_ESCAPE);assert(closes==1 and not UI.root:FindById('pauseOverlay'))
active=false;key(KEY_ESCAPE);flush();assert(UI.root:FindById('pauseOverlay'))
local old=toggles;key(KEY_M);assert(toggles==old,'settings must own keys')
Stop()
''')
    passed.append('real main M / Esc priority, repeat and settings gates')
    output=ROOT/'validation/map-overview';output.mkdir(parents=True,exist_ok=True)
    (output/'regression.json').write_text(json.dumps({'passed':passed,
        'scope':'Real Lua simulation, input gates and transforms; excludes native rendering/Yoga'},indent=2),encoding='utf8')
    print(f'{len(passed)} checks passed')
