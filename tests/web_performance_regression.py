"""Presentation/scheduling checks. Engine calls are mocked; this is not browser FPS acceptance."""
from pathlib import Path
import json
import os
import time

from PIL import Image
from lua_test_runtime import LuaRuntime
import performance_regression as perf
import bird_ui_regression as observation
import cell_render_regression as render

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get('WEB_VALIDATION_DIR', ROOT/'validation/web-performance-20261012'))


def check(name, lua, source):
    lua.execute(source)
    print('PASS '+name, flush=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lua = perf.runtime(ROOT/'scripts')
    check('pose interpolation, discontinuities, weak lifetime and 600-step simulation purity', lua, r'''
local Motion=require('Game.RenderMotion');local m=Motion.New()
local w=quietWorld();m:Capture(w)
local p=w.player;local x,y=p.x,p.y;p.x=x+.1;p.y=y+.2;m.alpha=.25
local px,py=m:Position(p);near(px,x+.025);near(py,y+.05)
p.x=x+2;px=m:Position(p);near(px,p.x)
p.x=x+.1;p.isHidden=true;px=m:Position(p);near(px,p.x)
p.x,p.y,p.isHidden=x,y,false
local a=quietWorld();local b=quietWorld()
a:SetMovement(1,0);b:SetMovement(1,0)
for i=1,600 do
 if i==2 then a:Split();b:Split() end
 if i==60 then a:SetMovement(0,0);b:SetMovement(0,0) end
 if i==180 then a:AbsorbNearby();b:AbsorbNearby() end
 m:Capture(a);a:Update(1/60);b:Update(1/60);m.alpha=(i%10)/10
 local state=snapshot(a)
 for _,list in ipairs({a.swarms,a.viruses,a.releasedViruses,a.immunes}) do
  for _,e in ipairs(list) do m:Position(e) end
 end
 assert(snapshot(a)==state and state==snapshot(b),'presentation changes gameplay at step '..i)
end
m:Reset()
do local transient={x=0,y=0};local world={swarms={transient},viruses={},releasedViruses={},immunes={}}
 m:Capture(world) end
collectgarbage('collect');collectgarbage('collect')
assert(not next(m.previous),'presentation retained a removed entity')
m:Reset();assert(not next(m.previous) and m.alpha==1)
''')
    check('adaptive budget, observer per actual step, pause and no subsequent catch-up', lua, r'''
local s=newSim('UPPER_AIRWAY',true)
local clock=os.clock;local now,cost=0,.005
os.clock=function()return now end
s.Tick=function(self,dt) self.tickCount=self.tickCount+1;now=now+cost end
local captures=0;local function capture()captures=captures+1 end
s:Update(.25,capture);assert(s.tickCount==1 and captures==1 and s.tickAccum<cfg.movementStep)
s:Update(1/60,capture);assert(s.tickCount==2 and captures==2)
cost=.001;s:Update(.25,capture);assert(s.tickCount==4 and captures==4)
cost=.100;s:Update(.25,capture);assert(s.tickCount==5,'one complete step despite over budget')
s:SetPaused('focus',true);s:Update(.25,capture);assert(s.tickCount==5 and s.tickAccum==0)
s:SetPaused('focus',false);s:Update(1/60,capture);assert(s.tickCount==6)
os.clock=clock
''')
    check('randomized grid queries preserve full-array order including rebuild/empty buckets', lua, r'''
local Grid=require('Core.SpatialGrid');local g=Grid.New(1.5);local items={};local w=quietWorld()
for i=1,500 do items[i]={x=w:_Random()*20-10,y=w:_Random()*20-10} end
for pass=1,3 do
 g:Build(items)
 for query=1,400 do
  local x,y,r=w:_Random()*20-10,w:_Random()*20-10,w:_Random()*5
  local result=g:Query(x,y,r);local index=0
  for _,item in ipairs(items) do
   local bx,by=math.floor(item.x/g.size),math.floor(item.y/g.size)
   if bx>=math.floor((x-r)/g.size) and bx<=math.floor((x+r)/g.size)
    and by>=math.floor((y-r)/g.size) and by<=math.floor((y+r)/g.size) then
     index=index+1;assert(result[index]==item)
   end
  end
  assert(index==#result)
 end
 for _,item in ipairs(items) do item.x,item.y=w:_Random()*3,w:_Random()*3 end
end
''')
    hud = observation.runtime()
    check('120/144/30 Hz and irregular frames, input, camera alignment, focus and restart', hud, r'''
local game,s,scale,obs=sceneFixture(true)
keys.D=true
for _,dt in ipairs({1/120,1/120,1/144,1/144,1/30,.007,.020,.1,.25,1/60}) do
 local n=s.tickCount;game:Update(dt);assert(s.tickCount-n<=2)
 local px,py=game.renderMotion:Position(s.world.player)
 near(game.camera.x,px);near(game.camera.y,py)
 assert(game.renderMotion.alpha>=0 and game.renderMotion.alpha<=1)
end
assert(s.world._inputX==1,'input was applied before simulation')
keys.D=false;game:Update(1/60);assert(s.world._inputX==0)
local n=s.tickCount;input.focus=false;game:Update(.25)
assert(s.tickCount==n and game.renderMotion.alpha==1 and not next(game.renderMotion.previous))
input.focus=true;game:Update(1/60);assert(s.tickCount==n+1)
s:init();Bus.Emit(Bus.Events.SIM_RESET,{})
assert(not next(game.renderMotion.previous));near(game.camera.x,s.world.player.x)
''')
    check('live HUD panel geometry equals recursive collection, click guards remain current', hud, r'''
local game=sceneFixture(true);game.rect={x=0,y=0,w=1000,h=800}
local label=UI.Label{text='label'};label.rect={x=20,y=20,w=50,h=20}
local panel=UI.Panel{id='hudLeftScroll',overflow='hidden',children={label}}
panel.rect={x=10,y=10,w=250,h=120}
local bottom=UI.Panel{id='strategyBar'};bottom.rect={x=400,y=650,w=500,h=100}
local ancestor=UI.Panel{pointerEvents='box-none',overflow='hidden',children={panel}}
ancestor.rect={x=0,y=0,w=200,h=100}
local root=UI.Panel{id='hudRoot',pointerEvents='box-none',children={ancestor,bottom}}
root.rect=game.rect;game.hudRoot=root
for _,change in ipairs({'initial','resize','scroll','hidden','opacity','restore'}) do
 if change=='resize' then ancestor.rect.h=150;bottom.rect.y=600 end
 if change=='scroll' then panel.rect.y=-20;ancestor.GetScroll=function()return 0,30 end end
 if change=='hidden' then ancestor:Hide() end
 if change=='opacity' then ancestor:Show();ancestor.props.opacity=0 end
 if change=='restore' then ancestor.props.opacity=1;panel.rect.y=10 end
 game.hudRects={};game.hudPanels={};game:CollectHUDRects(root,game.rect)
 local expected=game.hudPanels;game:UpdateViewport(game.rect)
 for id,r in pairs(expected) do equalRect(r,assert(game.hudPanels[id])) end
 for id in pairs(game.hudPanels) do assert(expected[id]) end
end
assert(game:IsOverHUD(30,30));ancestor:Hide();assert(not game:IsOverHUD(30,30))
ancestor:Show();assert(game:IsOverHUD(30,30),'visibility changes between frames must apply immediately')
''')
    drawing = perf.runtime(ROOT/'scripts')
    drawing.globals().SCRIPT_PATH = str(ROOT/'scripts/?.lua').replace('\\','/')
    drawing.execute(render.SETUP)
    drawing.execute('nvgLineCap=function()end;nvgLineJoin=function()end;nvgPathWinding=function()end;'
                    'nvgRadialGradient=function()return {}end;NVG_ROUND=1;NVG_SOLID=1')
    check('decorative cache lifecycle, live flow and shared interpolated drawing coordinates', drawing, r'''
local w=quietWorld();local v=View.New();v.visualWorld=w
local geometry=v:EnvironmentGeometry(w.map)
local count=0;local contains=w.map.Contains
w.map.Contains=function(self,...)count=count+1;return contains(self,...)end
assert(v:EnvironmentGeometry(w.map)==geometry and count==0)
local flow=w.map.FlowAt;local callsToFlow=0
w.map.FlowAt=function(self,...)callsToFlow=callsToFlow+1;return flow(self,...)end
v:DrawTissueDrift({},w.map,{x=-10000,y=-10000,w=20000,h=20000},128,0,0,1)
assert(callsToFlow>0,'time-varying flow must not be cached')
local Motion=require('Game.RenderMotion');local m=Motion.New();m:Capture(w)
local p=w.player;p.x=p.x+.1;m.alpha=.5
local expected=m:Position(p);local got
v.DrawSwarm=function(self,_,s)if s==p then got=self:Position(s) end end
local before=snapshot(w)
v:DrawWorld({},0,0,1000,800,{sim={world=w},renderMotion=m})
near(got,expected);assert(snapshot(w)==before)
v:Destroy();assert(v.environmentGeometry==nil and v.renderMotion==nil and v.renderGroups==nil)
''')
    check('offscreen rotated decals only, visible decal parameters and order remain exact', drawing, r'''
local Tissue=require('Game.Views.TissueArt');local tissue=Tissue.New();local map=quietWorld().map
local all,culled={},{}
tissue.art.Paint=function(self,_,path,x,y,w,h,alpha,rot,flags)
 all[#all+1]={path,x,y,w,h,alpha,rot,flags};return true end
local l={x=0,y=0,w=1000,h=800}
tissue:Draw({},map,128,-1200,-2600)
local old=all;all=culled;tissue:Draw({},map,128,-1200,-2600,l)
local expected={old[1]}
for i=2,#old do
 local d=old[i];local minX,minY,maxX,maxY=math.huge,math.huge,-math.huge,-math.huge
 local co,si=math.cos(d[7]),math.sin(d[7])
 for _,corner in ipairs({{0,0},{d[4],0},{0,d[5]},{d[4],d[5]}}) do
  local x,y=d[2]+co*corner[1]-si*corner[2],d[3]+si*corner[1]+co*corner[2]
  minX,minY,maxX,maxY=math.min(minX,x),math.min(minY,y),math.max(maxX,x),math.max(maxY,y)
 end
 if maxX+2>=l.x and minX-2<=l.x+l.w and maxY+2>=l.y and minY-2<=l.y+l.h then expected[#expected+1]=d end
end
assert(#culled==#expected and #culled<#old)
for i,d in ipairs(expected) do for j=1,8 do assert(culled[i][j]==d[j]) end end
''')
    # NanoVG's non-repeating image patterns clamp edges. Footprint culling is
    # valid for these assets because every outer pixel is fully transparent.
    for path in ('tissue_fibers_01.png.png','tissue_fibers_02.png.png','flow_bed_decal.png.png'):
        with Image.open(ROOT/'assets/image'/path) as image:
            alpha = image.getchannel('A')
            for box in ((0,0,alpha.width,1),(0,alpha.height-1,alpha.width,alpha.height),
                        (0,0,1,alpha.height),(alpha.width-1,0,alpha.width,alpha.height)):
                assert alpha.crop(box).getextrema() == (0,0), path+' has opaque clamped edges'
    print('PASS decal source alpha proves skipped fills contribute no pixels', flush=True)
    # Isolate pose capture overhead from simulation and native draw work.
    overhead=[]
    for count in (30,300,1000,3000):
        rt=perf.runtime(ROOT/'scripts');rt.globals().W=rt.globals().fixture(count,False,True)
        rt.execute("M=require('Game.RenderMotion').New();function capture()M:Capture(W)end;capture()")
        values=[]
        for _ in range(180):
            start=time.perf_counter();rt.globals().capture();values.append((time.perf_counter()-start)*1000)
        overhead.append(dict(count=count,median_ms=perf.percentile(values,.5),p95_ms=perf.percentile(values,.95)))
    (OUT/'motion-overhead.json').write_text(json.dumps(overhead,indent=2),encoding='utf-8')
    print('PASS all web performance checks; pose capture overhead: '+json.dumps(overhead),flush=True)


if __name__ == '__main__':
    main()
