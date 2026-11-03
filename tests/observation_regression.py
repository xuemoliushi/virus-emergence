"""Observation/input regression using real Lua modules in isolated Lua 5.4 runtimes.

Run: python3 /workspace/tests/observation_regression.py [--only substring]
Core/ObservationState, MouseView, GameScene and HUD are not rewritten or bypassed.
Only engine/UI rendering dependencies are stubbed; fake focus belongs to this process,
not the real surfaceless engine. PNG alpha is independently decoded with Pillow and
compared at every source pixel against real RLE/Contains/Widget:HitTest results.
Recorded draw calls verify texture use, not rendered pixels. This does not verify
Yoga layout, OS focus or physical pointer delivery. Real UI entry callbacks and layout
are separately asserted by redesign_validation.lua; composition needs screenshots.
权威模拟由 swarm 与 autonomy 回归单独覆盖；本文件聚焦观察、输入门控和动态群选择，
不以依赖桩代替真实引擎计时或布局验收。
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, '/home/Maker/.local/swarm-test')
from lua_test_runtime import LuaRuntime
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MASK_TYPES = ('UPPER_AIRWAY', 'TRACHEA', 'DEEP_LUNG')
MASK_SIZE = (777, 849)
# Independently measured healthy image crop, not read from generated RLE/metadata.
SOURCE_CROP = (448, 39, 1225, 888)
SETUP = r"""
Config = require('Core.Config')
Observation = require('Core.ObservationState')
Scale = require('Core.ScaleManager')
Sim = require('Core.SimState')
World = require('Core.SwarmWorld')
Bus = require('Core.EventBus')
function near(a,b,e) assert(math.abs(a-b)<=(e or 1e-7), tostring(a)..' ~= '..tostring(b)) end
function finite(v) return v==v and v~=math.huge and v~=-math.huge end
function settle(obs)
 for _=1,180 do if not obs:IsTransitioning() then break end; obs:Update(1/60) end
 assert(not obs:IsTransitioning(), 'Observation transition did not finish via Update')
end
function settleScale(scale)
 for _=1,240 do if not scale:IsTransitioning() then break end; scale:Update(1/60) end
 assert(not scale:IsTransitioning(), 'Scale transition did not finish via Update')
end

-- Engine dependency stubs. Image access is explicit and logged, never used for layout.
imageCalls, imageIds, imagePaths = {}, {}, {}
local imageCache = {}
function imageCache.Get(path)
 imageCalls[#imageCalls+1]=path
 if not imageIds[path] then local id=#imagePaths+1; imageIds[path]=id; imagePaths[id]=path end
 return imageIds[path]
end
function imageCache.GetSize(path) return 1920,1080 end
package.loaded['urhox-libs/UI/Core/ImageCache']=imageCache
renderCalls={}
local function record(name,...)
 local call={name=name,args={...}}
 renderCalls[#renderCalls+1]=call
 return call
end
for _,name in ipairs({'nvgSave','nvgRestore','nvgIntersectScissor','nvgBeginPath',
 'nvgRect','nvgFillPaint','nvgFill','nvgStrokeColor','nvgStrokeWidth','nvgStroke',
 'nvgCircle','nvgEllipse','nvgArc','nvgFillColor','nvgGlobalAlpha','nvgTranslate',
 'nvgRotate','nvgImagePattern','nvgImagePatternTinted','nvgLinearGradient','nvgRadialGradient','nvgBoxGradient'}) do
 _G[name]=function(...) return record(name,...) end
end
function nvgRGBA(r,g,b,a) return {r=r,g=g,b=b,a=a} end
function nvgRGBAf(r,g,b,a) return {r=r,g=g,b=b,a=a} end
NVG_CW=1

-- No Yoga emulation: these rectangles are test fixtures, not claimed real UI layout.
local Widget={}
Widget.__index=Widget
function Widget:Init(props)
 self.props=props or {}; self.children={}; self.rect={x=37,y=51,w=800,h=700}
 for _,child in ipairs(self.props.children or {}) do self.children[#self.children+1]=child; child.parent=self end
end
function Widget:Extend(name)
 local cls={}; cls.__index=cls
 return setmetatable(cls,{__index=self,__call=function(c,props)
  local value=setmetatable({},c); value:Init(props or {}); return value
 end})
end
function Widget:GetChildren() return self.children end
function Widget:AddChild(child)
 self.children[#self.children+1]=child; child.parent=self; return self
end
function Widget:FindById(id)
 if self.props.id==id then return self end
 for _,child in ipairs(self.children) do local found=child:FindById(id); if found then return found end end
end
function Widget:GetAbsoluteLayout() return self.rect end
function Widget:GetAbsoluteLayoutForHitTest() return self.absoluteLayout or self.rect end
-- Real Widget's rectangle/circle contract; no mask shortcut in the base stub.
function Widget:HitTest(x,y)
 local r=self:GetAbsoluteLayoutForHitTest()
 if r.w~=r.w or r.h~=r.h or r.x~=r.x or r.y~=r.y then return false end
 if self.props.shape=='circle' then
  local radius=math.min(r.w,r.h)/2
  local dx,dy=x-r.x-r.w/2,y-r.y-r.h/2
  return dx*dx+dy*dy<=radius*radius
 end
 return x>=r.x and x<=r.x+r.w and y>=r.y and y<=r.y+r.h
end
-- Match callback argument order and legacy hooks from UI/Core/Widget.lua.
function Widget:OnPointerEnter(event)
 if self.props.onPointerEnter then self.props.onPointerEnter(event,self) end
 self:OnMouseEnter()
end
function Widget:OnPointerLeave(event)
 if self.props.onPointerLeave then self.props.onPointerLeave(event,self) end
 self:OnMouseLeave()
end
function Widget:OnMouseEnter() end
function Widget:OnMouseLeave() end
function Widget:OnClick(event)
 if self.props.onClick then self.props.onClick(self,event)
 elseif self.parent then self.parent:OnClick(event) end
end
function Widget:GetLayout() return self.rect end
function Widget:IsVisible() return self.props.visible~=false end
function Widget:SetVisible(value) self.props.visible=value end
function Widget:Hide() self:SetVisible(false) end
function Widget:Show() self:SetVisible(true) end
function Widget:SetStyle(style) for k,v in pairs(style) do self.props[k]=v end end
function Widget:SetText(text) self.props.text=text end
function Widget:GetText() return self.props.text end
function Widget:IsDisabled() return self.props.disabled==true end
function Widget:SetDisabled(value) self.props.disabled=value end
function Widget:GetValue() return self.props.value or 0 end
function Widget:SetValue(value) self.props.value=value end
function Widget:Destroy() self.destroyed=true end
function Widget:SetScroll(x,y) self.scrollX,self.scrollY=x,y end
UI={Widget=Widget,Input={listeners={},pointers={}},PointerEvent={Buttons={Primary=1}}}
for _,name in ipairs({'Panel','Label','Button','ProgressBar','ScrollView','SafeAreaView','Divider'}) do
 UI[name]=function(props) local value=setmetatable({},Widget); value:Init(props); return value end
end
function UI.GetSafeAreaInsets() return {left=0,right=0,top=0,bottom=0} end
function UI.FindWidgetAt() return nil end
function UI.GetRoot() return UI.root end
function UI.SetRoot(root) UI.root=root end
function UI.Init() end
function UI.Shutdown() UI.root=nil end
graphics={windowTitle=''}
function SubscribeToEvent() end
function UI.Input.On(name,fn)
 UI.Input.listeners[name]=UI.Input.listeners[name] or {}
 local token={name=name,fn=fn}; table.insert(UI.Input.listeners[name],token); return fn
end
function UI.Input.Off(name,fn)
 local list=UI.Input.listeners[name] or {}
 for i=#list,1,-1 do if list[i].fn==fn then table.remove(list,i) end end
end
function UI.Input.GetPointer(id) return UI.Input.pointers[id] end
function UI.Input.GetActivePointers() return UI.Input.pointers end
package.loaded['urhox-libs/UI']=UI
package.loaded['Game.Views.CellView']={New=function()
 return {SetCamera=function(self,camera) self.camera=camera end,
  CameraTransform=function(self,l,zoom)
   local a=self.viewport or l
   return math.min(l.w,l.h)/9*(zoom or 1),a.x+a.w*.5,a.y+a.h*.57
  end,
  SetViewport=function(self,viewport) self.viewport=viewport end,
  Update=function(self,dt) self.visualTicks=(self.visualTicks or 0)+1 end,
  Destroy=function(self) self.destroyCount=(self.destroyCount or 0)+1 end,
  DrawWorld=function() record('cellDraw') end}
end}
-- Symbols stand in for engine enums only in this isolated process; no SDL numbers.
for _,name in ipairs({'W','A','S','D','E','UP','DOWN','LEFT','RIGHT','R','M','SPACE','1','2','3','4','5','6','TAB','V','F','LSHIFT','RSHIFT','ESCAPE'}) do _G['KEY_'..name]=name end
keys={}
testPlatform='Linux'
function GetPlatform() return testPlatform end
input={focus=true,minimized=false,touchEmulation=false,GetKeyDown=function(self,key) return keys[key]==true end}
MouseView=require('Game.Views.MouseView')
GameScene=require('Game.GameScene')
HUD=require('UI.HUD')
function finishCardReveal(hud)
 local overlay=assert(hud.root:FindById('cardInfoOverlay'))
 for _=1,60 do
  if overlay.Render then overlay:Render({}) end
  overlay:Update(1/60)
 end
end
function sceneFixture(started)
 local sim,scale,obs=Sim.New(),Scale.New(),Observation.New()
 if started then
  -- Core/input unit fixture only. UI cases below always use guidedStart callbacks.
  assert(sim:StartRun('UPPER_AIRWAY')); scale:JumpTo('cell'); settleScale(scale)
 end
 local game=GameScene{sim=sim,scaleMgr=scale,observation=obs,id='gameScene'}
 return game,sim,scale,obs
end
function hudFixture()
 local game,sim,scale,obs=sceneFixture(false)
 local hud=HUD.New{sim=sim,scaleMgr=scale,observation=obs}
 UI.root=hud:Build(); hud:Update(.2)
 return hud,game,sim,scale,obs
end
function callback(hud,id,event)
 local btn=assert(hud.root:FindById(id),'Missing widget '..id)
 assert(btn.props.onClick,'Missing true onClick '..id)(btn,event)
end
function guidedStart(hud,sim,scale,obs,region)
 assert(not sim.started and obs.mode=='body' and scale:CurrentScale()=='mouse')
 callback(hud,'anatomyToggleBtn'); assert(obs.mode=='anatomy')
 callback(hud,'lungHotspot'); assert(obs.mode=='lung' and obs:IsTransitioning())
 settle(obs); hud:Update(.2)
 callback(hud,'start_'..region); assert(obs.selectedStartType==region and not sim.started)
 callback(hud,'startRunBtn'); assert(sim.started and scale:CurrentScale()=='cell')
 assert(scale:IsTransitioning()); settleScale(scale); hud:Update(.2)
end
function markById(markers,id)
 local result={}; for _,m in ipairs(markers) do if m.id==id then result[#result+1]=m end end
 return result
end
function rectInside(outer,inner)
 assert(inner.w>=0 and inner.h>=0 and finite(inner.x) and finite(inner.y))
 assert(inner.x>=outer.x-1e-7 and inner.y>=outer.y-1e-7)
 assert(inner.x+inner.w<=outer.x+outer.w+1e-7 and inner.y+inner.h<=outer.y+outer.h+1e-7)
end
function equalRect(a,b) for _,k in ipairs({'x','y','w','h'}) do near(a[k],b[k]) end end
-- Assert the real MouseView draw consumes markers as single solid red circle paths.
-- Background image/gradient calls before these paths remain independent of disease.
function assertRedCircleDraw(markers)
 local circles,firstCircle={},nil
 for i,call in ipairs(renderCalls) do
  if call.name=='nvgCircle' then
   firstCircle=firstCircle or i
   assert(renderCalls[i-1].name=='nvgBeginPath','Each inflammation disk must start a fresh path')
   local color,fill=renderCalls[i+1],renderCalls[i+2]
   assert(color and color.name=='nvgFillColor' and fill and fill.name=='nvgFill',
    'Inflammation must use a solid fill, never an outline or gradient paint')
   local tint=color.args[2]
   assert(tint.r>0 and tint.r<=255 and tint.g==0 and tint.b==0,'Inflammation RGB must be pure red')
   assert(tint.a>=0 and tint.a<255,'Inflammation fill must remain translucent')
   circles[#circles+1]={call=call,tint=tint}
  end
 end
 assert(#circles==#markers,'Each local marker must draw exactly one filled disk')
 for i,m in ipairs(markers) do
  local circle,tint=circles[i].call,circles[i].tint
  near(circle.args[2],m.x); near(circle.args[3],m.y); near(circle.args[4],m.radius)
  assert(tint.r==m.red and tint.a==math.floor(m.alpha*255),
   'Rendered red and alpha must consume the same authoritative local marker')
 end
 for i=firstCircle or (#renderCalls+1),#renderCalls do
  local name=renderCalls[i].name
  assert(name~='nvgStroke' and name~='nvgStrokeColor' and name~='nvgStrokeWidth'
   and name~='nvgFillPaint' and name~='nvgLinearGradient' and name~='nvgRadialGradient'
   and name~='nvgBoxGradient','Inflammation paths must not add outlines/gradients/glow')
 end
 return circles
end
function assertWhiteUnionDraw(rect)
 local names={'UPPER_AIRWAY','TRACHEA','DEEP_LUNG'}
 assert(#renderCalls==17 and renderCalls[1].name=='nvgSave' and renderCalls[17].name=='nvgRestore',
  'Hovered organ must draw exactly three PNG fills, not an ellipse/outline/glow')
 assert(#imageCalls==3,'Hovered ALL must use existing region PNGs, not an extra ALL texture')
 for i,name in ipairs(names) do
  local offset=1+(i-1)*5
  assert(imageCalls[i]=='Sprites/LungMasks/'..name..'.png')
  assert(renderCalls[offset+1].name=='nvgBeginPath' and renderCalls[offset+2].name=='nvgRect')
  local box,paint=renderCalls[offset+2],renderCalls[offset+3]
  assert(paint.name=='nvgImagePatternTinted' and imagePaths[paint.args[7]]==imageCalls[i])
  for _,call in ipairs({box,paint}) do
   near(call.args[2],rect.x); near(call.args[3],rect.y)
   near(call.args[4],rect.w); near(call.args[5],rect.h)
  end
  local tint=paint.args[8]
  assert(paint.args[6]==0 and tint.r==255 and tint.g==255 and tint.b==255 and tint.a==255,
   'Hover must be pure white and fully opaque over the actual PNG alpha contour')
  assert(renderCalls[offset+4].name=='nvgFillPaint' and renderCalls[offset+4].args[2]==paint)
  assert(renderCalls[offset+5].name=='nvgFill')
 end
end
"""

TESTS = {
'Observation defaults and guarded three-step flow': r"""
local obs=Observation.New(); local other=Observation.New()
assert(obs.mode=='body' and obs.lungProgress==0 and obs.visualTime==0 and obs.selectedStartType==nil)
assert(not obs:IsTransitioning() and not obs:OpenLung() and not obs:SelectRegion('TRACHEA'))
obs:ShowAnatomy(); assert(obs.mode=='anatomy' and obs.selectedStartType==nil)
assert(obs:OpenLung() and obs.mode=='lung' and obs:IsTransitioning())
for _,region in ipairs(Config.StartRegions) do assert(not obs:SelectRegion(region.type)) end
obs:Update(1/60); assert(obs.lungProgress>0 and obs.lungProgress<1)
assert(not obs:OpenLung()); settle(obs); near(obs.lungProgress,1)
assert(not obs:SelectRegion('invalid') and obs.selectedStartType==nil)
for _,region in ipairs(Config.StartRegions) do assert(obs:SelectRegion(region.type)); assert(obs.selectedStartType==region.type) end
assert(other.mode=='body' and other.visualTime==0 and other.selectedStartType==nil)
""",
'Observation Back clears selection and reverses real animation': r"""
local obs=Observation.New(); obs:ShowAnatomy(); assert(obs:OpenLung()); settle(obs)
assert(obs:SelectRegion('DEEP_LUNG')); obs:Back()
assert(obs.mode=='anatomy' and obs.selectedStartType==nil and obs:IsTransitioning())
assert(not obs:OpenLung() and not obs:SelectRegion('UPPER_AIRWAY'))
local old=obs.lungProgress; obs:Update(1/60); assert(obs.lungProgress<old); settle(obs)
obs:Back(); assert(obs.mode=='body' and not obs:IsTransitioning())
obs:ShowAnatomy(); assert(obs:OpenLung()); obs:Update(.1); obs:ShowBody(); settle(obs)
assert(obs.mode=='body' and obs.lungProgress==0 and obs.selectedStartType==nil)
obs:Reset(); assert(obs.mode=='body' and obs.visualTime==0 and obs.lungProgress==0 and obs.selectedStartType==nil)
""",
'Observation time clamps dt without changing Sim time': r"""
local obs,sim=Observation.New(),Sim.New(); local world=sim.world
obs:Update(-4); near(obs.visualTime,0)
obs:Update(.05); near(obs.visualTime,.05)
obs:Update(9); assert(obs.visualTime>.05 and obs.visualTime<1)
for _=1,120 do obs:Update(1/60); sim:Update(1/60) end
assert(obs.visualTime>2 and sim.time==0 and world.time==0 and sim.world==world and not sim.started)
""",
'Layout absolute offset and three region rectangles are deterministic': r"""
local obs=Observation.New(); obs:ShowAnatomy()
for _,size in ipairs({{800,700},{390,844},{1920,1080},{600,200}}) do
 local w,h=size[1],size[2]; local origin={x=83,y=117,w=w,h=h}
 local layout=MouseView.GetLayout(origin.x,origin.y,w,h,obs)
 local zero=MouseView.GetLayout(0,0,w,h,obs)
 for _,name in ipairs({'body','chest','lung'}) do
  rectInside(origin,layout[name]); near(layout[name].x-zero[name].x,origin.x); near(layout[name].y-zero[name].y,origin.y)
  near(layout[name].w,zero[name].w); near(layout[name].h,zero[name].h)
 end
 rectInside(layout.body,layout.chest); equalRect(layout.chest,layout.lung)
 for _,region in ipairs(Config.StartRegions) do rectInside(layout.lung,layout.regions[region.type]) end
 obs.visualTime=obs.visualTime+.3
 local again=MouseView.GetLayout(origin.x,origin.y,w,h,obs)
 for _,name in ipairs({'body','chest','lung'}) do equalRect(layout[name],again[name]) end
end
assert(#imageCalls==0,'GetLayout must be pure, without ImageCache dependency')
""",
'Layout lung interpolates while chest remains anatomically anchored': r"""
local obs=Observation.New(); obs:ShowAnatomy()
local first=MouseView.GetLayout(31,67,900,800,obs)
assert(obs:OpenLung()); obs:Update(.2)
local mid=MouseView.GetLayout(31,67,900,800,obs)
settle(obs); local last=MouseView.GetLayout(31,67,900,800,obs)
equalRect(first.chest,mid.chest); equalRect(mid.chest,last.chest)
assert(mid.lung.w>first.lung.w and mid.lung.w<last.lung.w)
near(first.lung.w/first.lung.h,mid.lung.w/mid.lung.h); near(mid.lung.w/mid.lung.h,last.lung.w/last.lung.h)
rectInside({x=31,y=67,w=900,h=800},last.lung)
obs:Back(); settle(obs); equalRect(MouseView.GetLayout(31,67,900,800,obs).lung,first.chest)
for _,size in ipairs({{0,0},{-5,-1},{0,100}}) do
 local empty=MouseView.GetLayout(0,0,size[1],size[2],obs)
 assert(empty.lung.w==0 and empty.lung.h==0)
end
""",
'Local zero inflammation yields no red rings despite global damage': r"""
local sim,obs=Sim.New(),Observation.New(); obs:ShowAnatomy()
local layout=MouseView.GetLayout(91,123,800,700,obs)
sim.globalInflammation=999; sim.globalTissueDamage=999; sim.victoryProgress=1
for _,r in ipairs(sim.world.map.regions) do r.inflammation=0; r.tissueDamage=999 end
assert(#MouseView.GetInflammationMarkers(sim,layout,obs.visualTime)==0,
 'Global inflammation/damage must not invent local red rings')
""",
'Local low high zero intensity monotonic and left/right independent': r"""
local sim,obs=Sim.New(),Observation.New(); obs:ShowAnatomy(); obs:OpenLung(); settle(obs)
local layout=MouseView.GetLayout(91,123,800,700,obs); local regions=sim.world.map.regions
for _,r in ipairs(regions) do r.inflammation=0 end
local threshold=Config.Gameplay.hotspotThreshold
regions[3].inflammation=threshold*.02
local low=assert(markById(MouseView.GetInflammationMarkers(sim,layout,0),3)[1])
assert(low.severity<.1 and low.alpha<.1,'Low inflammation cannot be marked severe')
assert(#markById(MouseView.GetInflammationMarkers(sim,layout,0),4)==0)
regions[4].inflammation=threshold*4
local before=MouseView.GetInflammationMarkers(sim,layout,0)
local right=assert(markById(before,4)[1]); local left=assert(markById(before,3)[1])
near(left.value,low.value); near(left.radius,low.radius); near(left.alpha,low.alpha)
assert(right.severity>left.severity and right.alpha>left.alpha and right.radius>left.radius)
assert(left.x<layout.lung.x+layout.lung.w/2 and right.x>layout.lung.x+layout.lung.w/2)
regions[3].inflammation=threshold*8
local high=MouseView.GetInflammationMarkers(sim,layout,0)
local highLeft=assert(markById(high,3)[1]); local sameRight=assert(markById(high,4)[1])
assert(highLeft.radius>left.radius and highLeft.alpha>left.alpha and highLeft.severity>left.severity)
for _,k in ipairs({'value','severity','x','y','radius','alpha'}) do near(sameRight[k],right[k]) end
regions[3].inflammation=0
assert(#markById(MouseView.GetInflammationMarkers(sim,layout,0),3)==0)
near(assert(markById(MouseView.GetInflammationMarkers(sim,layout,0),4)[1]).value,right.value)
""",
'Markers coordinates track absolute lung rectangle and animation not disease time': r"""
local sim,obs=Sim.New(),Observation.New(); obs:ShowAnatomy(); obs:OpenLung(); settle(obs)
for i,r in ipairs(sim.world.map.regions) do r.inflammation=i*2 end
local layout=MouseView.GetLayout(73,119,850,740,obs)
local marks=MouseView.GetInflammationMarkers(sim,layout,0)
assert(#marks==6 and #markById(marks,5)==2)
local translated=MouseView.GetLayout(96,162,850,740,obs)
local moved=MouseView.GetInflammationMarkers(sim,translated,0)
for i,m in ipairs(marks) do
 assert(m.id>=1 and m.id<=5 and m.value==sim.world.map.regions[m.id].inflammation)
 assert(m.x>=layout.lung.x and m.x<=layout.lung.x+layout.lung.w)
 assert(m.y>=layout.lung.y and m.y<=layout.lung.y+layout.lung.h)
 assert(m.radius>0 and m.alpha>0 and m.alpha<=1 and m.severity>0 and m.severity<1)
 near(moved[i].x-m.x,23); near(moved[i].y-m.y,43)
end
local t=sim.time; local worldT=sim.world.time
obs:Update(.2); local animated=MouseView.GetInflammationMarkers(sim,layout,obs.visualTime)
local changed=false
for i,m in ipairs(animated) do
 near(m.value,marks[i].value); near(m.severity,marks[i].severity)
 near(m.x,marks[i].x); near(m.y,marks[i].y)
 if math.abs(m.alpha-marks[i].alpha)>1e-7 or math.abs(m.radius-marks[i].radius)>1e-7 then changed=true end
end
assert(changed and sim.time==t and sim.world.time==worldT)
""",
'Draw anatomy uses body and lung together and observation visual clock': r"""
local sim,obs=Sim.New(),Observation.New(); obs:ShowAnatomy()
sim.world.map.regions[3].inflammation=4; sim.time=0
MouseView.Draw({},83,117,800,700,{sim=sim,observation=obs,time=999})
assert(imageIds[Config.ArtSlots.mouseAnatomy] and imageIds[Config.ArtSlots.lungStages[1]],
 'Anatomy draw must retain full body and overlay actual lung')
local count=0; for _,call in ipairs(renderCalls) do if call.name=='nvgImagePattern' then count=count+1 end end
assert(count>=2,'Both images must reach drawing calls, not just be requested')
for _,call in ipairs(renderCalls) do
 assert(call.name~='nvgCircle' and call.name~='nvgEllipse' and call.name~='nvgStroke',
  'Anatomy must not show an always-on chest ring or inflammation disks')
end
-- Keep anatomy/body composition coverage, then enter actual lung mode for disks.
assert(obs:OpenLung()); obs:Update(.2); renderCalls={}
local marks=MouseView.GetInflammationMarkers(sim,MouseView.GetLayout(83,117,800,700,obs),obs.visualTime)
MouseView.Draw({},83,117,800,700,{sim=sim,observation=obs,time=999})
local m=assert(markById(marks,3)[1]); local matched=false
for _,call in ipairs(renderCalls) do
 if call.name=='nvgCircle' and math.abs(call.args[2]-m.x)<1e-7 and math.abs(call.args[3]-m.y)<1e-7
  and math.abs(call.args[4]-m.radius)<1e-7 then matched=true end
end
assert(matched,'Draw must consume same absolute markers and visualTime, not frozen sim.time or ctx.time')
assertRedCircleDraw(marks)
assert(sim.time==0 and sim.world.time==0 and not sim.started)
""",
'GameScene mouse pointer never moves or aims and zero input stays zero': r"""
local game,sim=sceneFixture(true); local world=sim.world
world:SetAim(0,1); local ax,ay=world._aimX,world._aimY
local px,py=world.player.x,world.player.y
for _,point in ipairs({{100,100},{600,300},{20,20}}) do
 game:OnPointerMove{pointerType='mouse',x=point[1],y=point[2],target=game}
 assert(game.pointer.known and game.pointer.x==point[1] and game.pointer.y==point[2])
 local x,y=game:ReadMovement(game:GetAbsoluteLayout()); near(x,0); near(y,0)
 game:Update(0); near(world._inputX,0); near(world._inputY,0)
 near(world._aimX,ax); near(world._aimY,ay); near(world.player.x,px); near(world.player.y,py)
end
local x,y=game.pointer.x,game.pointer.y
 game:OnPointerMove{pointerType='touch',x=700,y=600,target=game}
near(game.pointer.x,x); near(game.pointer.y,y)
game:OnPointerLeave{pointerType='mouse'}; assert(not game.pointer.active)
""",
'GameScene keyboard diagonal normalized opposing keys stationary arrows valid': r"""
local game=sceneFixture(true); local rect=game:GetAbsoluteLayout()
keys={[KEY_W]=true,[KEY_D]=true}
local x,y=game:ReadMovement(rect); near(x,1/math.sqrt(2)); near(y,-1/math.sqrt(2)); near(x*x+y*y,1)
keys={[KEY_UP]=true,[KEY_LEFT]=true}; x,y=game:ReadMovement(rect)
near(x,-1/math.sqrt(2)); near(y,-1/math.sqrt(2))
keys={[KEY_W]=true,[KEY_S]=true,[KEY_A]=true,[KEY_D]=true}
x,y=game:ReadMovement(rect); near(x,0); near(y,0)
keys={}; x,y=game:ReadMovement(rect); near(x,0); near(y,0)
""",
'World most recent movement direction persists for split after release': r"""
local game,sim=sceneFixture(true); local world=sim.world
keys={[KEY_W]=true,[KEY_D]=true}; game:Update(0)
near(world._inputX,1/math.sqrt(2)); near(world._inputY,-1/math.sqrt(2))
local ax,ay=world._aimX,world._aimY; near(ax,1/math.sqrt(2)); near(ay,-1/math.sqrt(2))
keys={}; game:OnPointerMove{pointerType='mouse',x=700,y=500,target=game}; game:Update(0)
near(world._inputX,0); near(world._inputY,0); near(world._aimX,ax); near(world._aimY,ay)
local main=world:MainSwarm()
local launchScale=math.sqrt(math.max(1,main.mass/Config.Gameplay.initialMass))
assert(sim:Split()); local split
for _,s in ipairs(world.swarms) do if not s.isMainSwarm then split=s end end
assert(split and split.launchX*ax+split.launchY*ay>0,'Split must launch along most recent keyboard movement')
near(split.launchX,ax*Config.Gameplay.splitLaunchSpeed*launchScale)
near(split.launchY,ay*Config.Gameplay.splitLaunchSpeed*launchScale)
near(main.launchX,-ax*Config.Gameplay.splitRecoil*launchScale)
near(main.launchY,-ay*Config.Gameplay.splitRecoil*launchScale)
""",
'GameScene joystick priority normalized and HUD center dead zone': r"""
local game,sim,scale,obs=sceneFixture(true)
local hud=HUD.New{sim=sim,scaleMgr=scale,observation=obs}; hud:Build()
keys={[KEY_D]=true}; sim.touchMove={x=0,y=0,active=true}; hud.touchMove_=sim.touchMove
local x,y=game:ReadMovement(game:GetAbsoluteLayout()); near(x,0); near(y,0)
sim.touchMove.x,sim.touchMove.y=2,-2; x,y=game:ReadMovement(game:GetAbsoluteLayout())
near(x,1/math.sqrt(2)); near(y,-1/math.sqrt(2))
local pad=assert(hud.root:FindById('moveJoystick')); pad.rect={x=137,y=251,w=88,h=88}
hud:SetJoystickPosition({x=181,y=295},pad)
assert(sim.touchMove.active); near(sim.touchMove.x,0); near(sim.touchMove.y,0)
hud:SetJoystickPosition({x=182,y=296},pad)
near(sim.touchMove.x,0); near(sim.touchMove.y,0)
x,y=game:ReadMovement(game:GetAbsoluteLayout()); near(x,0); near(y,0)
hud:SetJoystickPosition({x=281,y=195},pad)
x,y=game:ReadMovement(game:GetAbsoluteLayout()); near(x,1/math.sqrt(2)); near(y,-1/math.sqrt(2))
hud:ClearTouchMove(); assert(not sim.touchMove.active); near(sim.touchMove.x,0); near(sim.touchMove.y,0)
""",
'GameScene fake focus and observation pause preserve disease but advance visuals': r"""
local game,sim,scale,obs=sceneFixture(true)
local t,wt=sim.time,sim.world.time; input.focus=false; keys={[KEY_D]=true}
game:Update(.1); assert(sim.pauseReasons.focus and sim.paused and sim.time==t and sim.world.time==wt)
near(sim.world._inputX,0); assert(obs.visualTime>0)
input.focus=true; keys={}; game:Update(1/60); assert(not sim.pauseReasons.focus and sim.time>t)
scale:JumpTo('mouse'); settleScale(scale); game:Update(0)
t,wt=sim.time,sim.world.time; local visual=obs.visualTime
for _=1,120 do game:Update(1/60) end
assert(sim.pauseReasons.observation and sim.paused and sim.time==t and sim.world.time==wt and obs.visualTime>visual+1.9)
scale:JumpTo('cell'); settleScale(scale); game:Update(0); game:Update(1/60)
near(sim.time,t+Config.Gameplay.movementStep); assert(not sim.pauseReasons.observation)
""",
'HUD real callbacks reject skipped body anatomy and unfinished lung steps': r"""
local hud,game,sim,scale,obs=hudFixture(); local previous=sim.world
assert(hud.observation==obs and game.observation==obs)
local function reject()
 for _,region in ipairs(Config.StartRegions) do callback(hud,'start_'..region.type) end
 callback(hud,'startRunBtn')
 assert(not sim.started and sim.world==previous and sim.time==0 and obs.selectedStartType==nil)
end
reject(); callback(hud,'lungHotspot'); assert(obs.mode=='body')
callback(hud,'anatomyToggleBtn'); assert(obs.mode=='anatomy'); reject()
callback(hud,'lungHotspot'); assert(obs.mode=='lung' and obs:IsTransitioning()); reject()
settle(obs); hud:Update(.2); callback(hud,'start_TRACHEA')
assert(obs.selectedStartType=='TRACHEA' and sim.world==previous and not sim.started)
callback(hud,'startRunBtn'); assert(sim.started and sim.selectedStartRegion=='TRACHEA' and scale:IsTransitioning())
settleScale(scale); hud:Update(.2); game:Update(0); assert(scale:CurrentScale()=='cell' and sim.time==0)
""",
'HUD all three real guided starts use authoritative start quantities': r"""
for _,region in ipairs(Config.StartRegions) do
 local hud,game,sim,scale,obs=hudFixture()
 guidedStart(hud,sim,scale,obs,region.type)
 local counts=sim.world:Counts()
 assert(counts.mainMass==region.mass and counts.latent==region.initialNodes)
 assert(sim.selectedStartRegion==region.type and sim.time==0)
 hud:Destroy(); game:Destroy()
end
""",
'HUD started observation follows anatomy lung chain without reselection': r"""
local hud,game,sim,scale,obs=hudFixture(); guidedStart(hud,sim,scale,obs,'DEEP_LUNG')
local world,start,t=sim.world,sim.selectedStartRegion,sim.time
callback(hud,'observeBtn'); settleScale(scale); settle(obs); hud:Update(.2)
assert(scale:CurrentScale()=='mouse' and obs.mode=='body' and sim.paused)
callback(hud,'anatomyToggleBtn'); assert(obs.mode=='anatomy')
callback(hud,'lungHotspot'); settle(obs); hud:Update(.2); assert(obs.mode=='lung')
for _,region in ipairs(Config.StartRegions) do callback(hud,'start_'..region.type) end
callback(hud,'startRunBtn')
assert(sim.world==world and sim.selectedStartRegion==start and obs.selectedStartType==nil and sim.time==t)
callback(hud,'observationPlayBtn'); settleScale(scale); hud:Update(.2); game:Update(0)
assert(scale:CurrentScale()=='cell' and not sim.pauseReasons.observation and not sim.pauseReasons.transition)
""",
'HUD shared absolute hotspots reject outside pixel union wrong target and secondary action': r"""
local hud,game,sim,scale,obs=hudFixture()
callback(hud,'anatomyToggleBtn')
local layout,rect=hud:GetObservationLayout(); local hotspot=hud.root:FindById('lungHotspot')
near(hotspot.props.left+rect.x,layout.chest.x); near(hotspot.props.top+rect.y,layout.chest.y)
near(hotspot.props.width,layout.chest.w); near(hotspot.props.height,layout.chest.h)
local function event(r,target,primary,x,y)
 return {x=x or r.x+r.w*.50,y=y or r.y+r.h*.24,target=target,IsPrimaryAction=function() return primary end}
end
local Masks=require('Game.Views.LungRegionMasks')
local r=layout.chest
hotspot.rect=r -- Measured canvas fixture, not a Yoga emulation.
assert(hotspot.regionType_=='ALL' and hotspot:HitTest(r.x+r.w*.50,r.y+r.h*.24))
callback(hud,'lungHotspot',event(r,hotspot,false)); assert(obs.mode=='anatomy')
callback(hud,'lungHotspot',event(r,hud.root,true)); assert(obs.mode=='anatomy')
for _,point in ipairs({{0,0},{.50,.50},{.50,.79},{.50,.90}}) do
 local x,y=r.x+r.w*point[1],r.y+r.h*point[2]
 assert(not Masks.Contains('ALL',r,x,y) and not hotspot:HitTest(x,y),
  'Fixed corner/central gap must be outside true union, not moved onto tissue')
 assert(UI.Widget.HitTest(hotspot,x,y),'Negative fixture must lie inside rectangular canvas')
 callback(hud,'lungHotspot',event(r,hotspot,true,x,y))
 assert(obs.mode=='anatomy','Transparent corner/central gap must not open lung')
end
callback(hud,'lungHotspot',event(r,hotspot,true)); settle(obs); hud:Update(.2)
layout,rect=hud:GetObservationLayout()
local anchors={UPPER_AIRWAY={.50,.075},TRACHEA={.50,.24},DEEP_LUNG={.24,.67}}
for _,def in ipairs(Config.StartRegions) do
 local r=layout.lung; local target=hud.root:FindById('start_'..def.type)
 -- Full lungRect is the texture canvas; bbox is only for decoration, never hits.
 near(target.props.left+rect.x,r.x); near(target.props.top+rect.y,r.y)
 near(target.props.width,r.w); near(target.props.height,r.h)
 local anchor=anchors[def.type]; local x,y=r.x+r.w*anchor[1],r.y+r.h*anchor[2]
 assert(Masks.Contains(def.type,r,x,y),'Positive fixture must be inside actual mask')
 local previous=obs.selectedStartType
 callback(hud,'start_'..def.type,event(r,target,false,x,y)); assert(obs.selectedStartType==previous)
 callback(hud,'start_'..def.type,event(r,hud.root,true,x,y)); assert(obs.selectedStartType==previous)
 callback(hud,'start_'..def.type,event(r,target,true,r.x+r.w+1,r.y)); assert(obs.selectedStartType==previous)
 -- Keep the central gap fixed: never relocate a negative fixture onto lung tissue.
 local gapX,gapY=r.x+r.w*.50,r.y+r.h*.79
 assert(not Masks.Contains(def.type,r,gapX,gapY),'Central gap unexpectedly became selectable')
 callback(hud,'start_'..def.type,event(r,target,true,gapX,gapY)); assert(obs.selectedStartType==previous)
 callback(hud,'start_'..def.type,event(r,target,true,x,y)); assert(obs.selectedStartType==def.type)
end
local r=layout.lung
callback(hud,'start_UPPER_AIRWAY',event(r,hud.root:FindById('start_UPPER_AIRWAY'),true,r.x+r.w*.50,r.y+r.h*.075))
callback(hud,'startRunBtn',event(rect,hud.root:FindById('startRunBtn'),false)); assert(not sim.started)
callback(hud,'startRunBtn',event(rect,hud.root:FindById('startRunBtn'),true)); assert(sim.started)
""",
'HUD desktop hides whole joystick while native mobile and Web touch show': r"""
local function fixture(platform)
 testPlatform=platform; package.loaded['urhox-libs.Platform.PlatformUtils']=nil
 package.loaded['UI.HUD']=nil; HUD=require('UI.HUD')
 local hud,game,sim,scale,obs=hudFixture(); guidedStart(hud,sim,scale,obs,'UPPER_AIRWAY')
 return hud,sim,scale,obs
end
local desktop=fixture('Linux'); assert(not desktop.root:FindById('joystickPanel'):IsVisible())
desktop.root:FindById('hudContent').rect.w=250; desktop:ApplyLayout(); desktop:RefreshJoystickVisibility()
assert(not desktop.root:FindById('joystickPanel'):IsVisible(),'Narrow desktop cannot be treated as mobile')
desktop:Destroy()
for _,platform in ipairs({'Android','iOS','HarmonyOS'}) do
 local hud,sim,scale=fixture(platform); assert(hud.root:FindById('joystickPanel'):IsVisible())
 scale:JumpTo('mouse'); settleScale(scale); hud:Update(.2)
 assert(not hud.root:FindById('joystickPanel'):IsVisible(),'Observation must hide mobile joystick')
 hud:Destroy()
end
local web,sim,scale=fixture('Web'); assert(not web.root:FindById('joystickPanel'):IsVisible())
for _,token in ipairs(UI.Input.listeners.PointerDown or {}) do
 token.fn({pointerType='touch',IsTouch=function() return true end})
end
web:Update(.2); assert(web.root:FindById('joystickPanel'):IsVisible(),'Web touch event must enable entire joystick')
web:Destroy(); assert(#(UI.Input.listeners.PointerDown or {})==0,'Destroy removes touch visibility listener')
""",
'Main R restarts directly in cell control and clears shared observation through real key handler': r"""
require('main'); BuildGame()
local game=assert(UI.GetRoot():FindById('gameScene')); local sim,obs,scale=game.sim,game.observation,game.scaleMgr
local function uiClick(id)
 local w=assert(UI.GetRoot():FindById(id)); assert(w.props.onClick)(w)
end
assert(obs.mode=='body' and scale:CurrentScale()=='cell' and sim.started)
scale:JumpTo('mouse'); settleScale(scale)
uiClick('anatomyToggleBtn'); uiClick('lungHotspot'); settle(obs)
game.pointer.active,game.pointer.known=true,true
sim.touchMove.x,sim.touchMove.y,sim.touchMove.active=1,-1,true
HandleKeyDown('KeyDown',{GetInt=function() return KEY_R end,GetBool=function() return false end})
assert(sim.started and sim.time==0 and sim:CanAct() and sim.selectedStartRegion=='UPPER_AIRWAY')
assert(obs.mode=='body' and obs.lungProgress==0 and obs.visualTime==0 and obs.selectedStartType==nil)
assert(scale:CurrentScale()=='cell' and not scale:IsTransitioning())
assert(not game.pointer.active and not game.pointer.known and not sim.touchMove.active)
near(sim.touchMove.x,0); near(sim.touchMove.y,0); near(sim.world._inputX,0); near(sim.world._inputY,0)
""",
'新吸附按钮与E快捷键立即守恒转移并忽略重复事件': r"""
require('main'); BuildGame()
local game=assert(UI.GetRoot():FindById('gameScene'))
local sim,obs,scale=game.sim,game.observation,game.scaleMgr
local function click(id,event)
 local btn=assert(UI.GetRoot():FindById(id)); assert(btn.props.onClick)(btn,event)
end
local function key(k,repeatKey)
 HandleKeyDown('KeyDown',{GetInt=function() return k end,GetBool=function() return repeatKey or false end})
end
assert(sim.started and scale:CurrentScale()=='cell' and not scale:IsTransitioning())
HandleUpdate('Update',{GetFloat=function() return .2 end})
local w=sim.world; local s=w.player; local c=w.cells[1]
local function nearby(n)
 w:_Release(c,n)
 for _,v in ipairs(w.releasedViruses) do
  if v.state=='RELEASED' then v.x,v.y=s.x,s.y+1.2 end
 end
end
nearby(4)
local before=w:Counts(); local mass=s.mass; local t=sim.time
local absorbed=w.stats.totalAbsorbed
key(KEY_E,true); assert(s.mass==mass and w.stats.totalAbsorbed==absorbed)
key(KEY_E,false)
assert(s.mass==mass+4 and w:Counts().released==0 and w:Counts().virus==before.virus)
assert(w.stats.totalAbsorbed==absorbed+4 and sim.time==t and #w.viruses==w:Counts().controlled)
nearby(3); mass=s.mass; before=w:Counts()
click('absorbBtn',{IsPrimaryAction=function() return false end}); assert(s.mass==mass)
click('absorbBtn'); assert(s.mass==mass,'冷却期间按钮和键盘使用同一权威门控')
w.time=w.time+w:GetAbsorptionCooldown()
click('absorbBtn'); assert(s.mass==mass+3 and w:Counts().virus==before.virus)
key(KEY_E,false); assert(s.mass==mass+3,'重复主动吸附不能重复增加质量')
assert(UI.GetRoot():FindById('absorptionStatus'):GetText():find('×'))
assert(UI.GetRoot():FindById('swarmStatusDetail'):GetText():find('冷却'))
""",
'新多群点选与循环选择同步实时槽位及死亡升主': r"""
local hud,game,sim,scale,obs=hudFixture(); guidedStart(hud,sim,scale,obs,'DEEP_LUNG')
local w=sim.world
assert(sim:AcquireTestCard('swarm_capacity_4'));hud:CloseCardInfo()
callback(hud,'splitBtn'); assert(#w.swarms==2)
w.splitCooldown=0; hud:Update(.2)
assert(not hud.root:FindById('splitBtn'):IsDisabled(),'扩容后两群允许继续分离')
callback(hud,'splitBtn'); assert(#w.swarms==3)
local ids={}; for i,s in ipairs(w.swarms) do ids[i]=s.id end
hud:Update(.2)
for i=1,3 do
 local b=hud.root:FindById('selectSwarm_'..i)
 assert(b:IsVisible() and b:GetText():find('#'..ids[i]))
end
assert(hud.root:FindById('selectSwarm_4')==nil,'仅按实际群数动态增槽，不预创建六槽')
callback(hud,'selectSwarm_3'); assert(w.currentControlledSwarmId==ids[3])
assert(hud.root:FindById('selectSwarm_3'):IsDisabled())
for _,id in ipairs({ids[1],ids[2],ids[3]}) do callback(hud,'switchBtn'); assert(w.currentControlledSwarmId==id) end
local killed=w.swarms[2]; w:DamageSwarm(killed.id,killed.mass); hud:Update(.2)
assert(#w.swarms==2 and not hud.root:FindById('selectSwarm_3'):IsVisible())
callback(hud,'selectSwarm_2'); assert(w.currentControlledSwarmId==ids[3],'槽2须指向实时新群而非已清除ID')
local main=w:MainSwarm(); w:DamageSwarm(main.id,main.mass); hud:Update(.2)
assert(w:MainSwarm().id==ids[3] and w.currentControlledSwarmId==ids[3])
assert(hud.root:FindById('selectSwarm_1'):GetText():find('主群'))
assert(hud.root:FindById('switchBtn'):IsDisabled())
hud:Destroy(); game:Destroy()
""",
'六群动态列表逐槽可选并显示小脑状态': r"""
local hud,game,sim,scale,obs=hudFixture(); guidedStart(hud,sim,scale,obs,'DEEP_LUNG')
local w=sim.world
for _,id in ipairs({'swarm_capacity_4','swarm_capacity_6','swarm_local_brain'}) do
 assert(sim:AcquireTestCard(id));hud:CloseCardInfo()
end
-- 只隔离验证手动入口和动态列表，局部小脑另由真实模拟回归覆盖。
for index=2,6 do
 local s=w.player
 w:_Release(w.cells[1],30)
 for _,v in ipairs(w.releasedViruses) do
  if v.state~='ABSORBED' and v.state~='CLEARED' and v.state~='LOST' then v.x,v.y=s.x,s.y end
 end
 w.time=w.time+w:GetAbsorptionCooldown()
 hud:AbsorbNearby(); w.splitCooldown=0; hud:Split()
 assert(#w.swarms==index,'六群容量内允许新增群')
end
w.swarms[2].aiState='flee'; w.swarms[3].aiState='infect'
hud:Update(.2)
assert(#hud.groupButtons_==6 and #hud.swarmSelector_:GetChildren()==6)
assert(hud.root:FindById('swarmListTitle'):GetText():find('6 / 6'))
assert(hud.root:FindById('splitBtn'):IsDisabled(),'达到六群上限')
assert(hud.root:FindById('selectSwarm_2'):GetText():find('避敌'))
assert(hud.root:FindById('selectSwarm_3'):GetText():find('感染'))
assert(hud.root:FindById('autonomyStatus'):GetText():find('小脑'))
local last=w.swarms[6].id
callback(hud,'selectSwarm_6'); assert(w.currentControlledSwarmId==last)
assert(hud.root:FindById('selectSwarm_6'):GetText():find('手动'))
local existing=hud.groupButtons_[6]
for i=1,6 do
 local id=w.swarms[i].id
 callback(hud,'selectSwarm_'..i); assert(w.currentControlledSwarmId==id)
end
local gone=w.swarms[5]; w:DamageSwarm(gone.id,gone.mass); hud:Update(.2)
assert(#w.swarms==5 and not existing:IsVisible() and #hud.groupButtons_==6)
callback(hud,'selectSwarm_5'); assert(w.currentControlledSwarmId==last,'死亡重排不留下旧ID回调')
sim:init(); hud:ResetEnding(); hud:Update(.2)
for _,btn in ipairs(hud.groupButtons_) do assert(not btn:IsVisible()) end
assert(hud.groupButtons_[6]==existing,'重开复用已分配槽，不重复创建')
hud:Destroy(); game:Destroy()
""",
'新控制群自然消亡后旧摇杆拖拽不可继承': r"""
for _,beforeUpdate in ipairs({true,false}) do
 local hud,game,sim,scale,obs=hudFixture(); guidedStart(hud,sim,scale,obs,'DEEP_LUNG')
 local w=sim.world; callback(hud,'splitBtn')
 local dead=w.player
 local pad=hud.root:FindById('moveJoystick'); pad.rect={x=137,y=251,w=88,h=88}
 local function pointer(id)
  return {pointerId=id,x=211,y=295,buttons=1,IsPrimaryAction=function() return true end,
   IsMouse=function() return false end,PreventDefault=function()end,StopPropagation=function()end}
 end
 UI.Input.pointers[55]={pointerType='touch'}
 hud:JoystickDown(pointer(55),pad); assert(sim.touchMove.active and hud.joystickPointer_==55)
 w:DamageSwarm(dead.id,dead.mass)
 assert(w.player.id~=dead.id and w.player.isMainSwarm)
 if not beforeUpdate then hud:Update(.001) end
 hud:JoystickMove(pointer(55),pad)
 assert(hud.joystickPointer_==nil and not sim.touchMove.active)
 near(sim.touchMove.x,0); near(sim.touchMove.y,0)
 near(hud.joystickKnob_.props.left,30); near(hud.joystickKnob_.props.top,30)
 UI.Input.pointers[56]={pointerType='touch'}
 hud:JoystickDown(pointer(56),pad)
 assert(hud.joystickPointer_==56 and sim.touchMove.active and sim.touchMove.x>0)
 hud:Destroy(); game:Destroy()
end
""",
'新动作观察过渡说明及失焦暂停统一拒绝': r"""
require('main'); BuildGame()
local root=UI.GetRoot(); local game=root:FindById('gameScene')
local sim,obs,scale=game.sim,game.observation,game.scaleMgr
local function click(id) local b=root:FindById(id); assert(b.props.onClick)(b) end
local function keysAll()
 for _,k in ipairs({KEY_E,KEY_SPACE,KEY_2,KEY_TAB}) do
  HandleKeyDown('KeyDown',{GetInt=function() return k end,GetBool=function() return false end})
 end
end
click('anatomyToggleBtn'); click('lungHotspot'); settle(obs)
click('start_DEEP_LUNG'); click('startRunBtn'); settleScale(scale); HandleUpdate('Update',{GetFloat=function() return .2 end})
local w=sim.world; w:_Release(w.cells[1],4)
for _,v in ipairs(w.releasedViruses) do v.x,v.y=w.player.x,w.player.y end
local function reject()
 local t,groups,mass,total=sim.time,#w.swarms,w.player.mass,w.stats.totalAbsorbed
 keysAll(); click('absorbBtn'); click('splitBtn'); click('switchBtn')
 assert(sim.time==t and #w.swarms==groups and w.player.mass==mass and w.stats.totalAbsorbed==total)
end
click('cardInfoBtn'); reject()
-- 关闭说明通过原有实际控件回调，不直接解除HUD登记的暂停原因。
local function closeCard(node)
 if node.props.id=='cardContinue' then assert(node.props.onClick)(node); return true end
 for _,child in ipairs(node:GetChildren()) do if closeCard(child) then return true end end
 return false
end
assert(closeCard(root) and not sim.pauseReasons['card-info'])
-- 所有已登记暂停原因逐一测试；不声称模拟真实OS失焦。
for _,reason in ipairs({'focus','transition','observation'}) do
 sim:SetPaused(reason,true); reject(); sim:SetPaused(reason,false)
end
scale:JumpTo('mouse'); reject(); settleScale(scale); reject()
scale:JumpTo('cell'); settleScale(scale); HandleUpdate('Update',{GetFloat=function() return .2 end})
local mass=w.player.mass
HandleKeyDown('KeyDown',{GetInt=function() return KEY_E end,GetBool=function() return false end})
assert(w.player.mass==mass+4)
""",
'Masks boundary exclusions empty rectangles and invalid regions': r"""
local Masks=require('Game.Views.LungRegionMasks')
local rect={x=0,y=0,w=777,h=849}
-- Independent PNG evidence: upper's first row [362,366) and [411,414).
assert(Masks.Contains('UPPER_AIRWAY',rect,362,0),'Left/top included')
assert(Masks.Contains('UPPER_AIRWAY',rect,365.5,.5))
assert(not Masks.Contains('UPPER_AIRWAY',rect,366,.5),'Run end excluded')
assert(not Masks.Contains('UPPER_AIRWAY',rect,361.5,.5))
assert(not Masks.Contains('UPPER_AIRWAY',rect,400,.5),'Between first-row runs is a true gap')
for _,name in ipairs({'UPPER_AIRWAY','TRACHEA','DEEP_LUNG','ALL'}) do
 for _,point in ipairs({{-1,.5},{.5,-1},{777,.5},{.5,849},{778,850},{0/0,1},{1,0/0},
                       {math.huge,1},{1,-math.huge}}) do
  assert(not Masks.Contains(name,rect,point[1],point[2]),'Outside/nonfinite point must not hit')
 end
 for _,size in ipairs({{0,849},{777,0},{-1,849},{777,-1},{0/0,849},{777,0/0}}) do
  assert(not Masks.Contains(name,{x=0,y=0,w=size[1],h=size[2]},388.5,204.5))
 end
end
assert(not Masks.Contains('INVALID',rect,388.5,204.5))
equalRect(Masks.Bounds('INVALID',rect),{x=0,y=0,w=0,h=0})
assert(#imageCalls==0,'Hit queries must not load PNG textures')
""",
'Masks Draw uses only tinted full canvas PNG and contour outline': r"""
local Masks=require('Game.Views.LungRegionMasks')
local rect={x=83.25,y=117.5,w=291.375,h=530.625}; local color={93,196,150,255}
local states={{selected=false,hovered=false,fill=135,edge=225},
              {selected=false,hovered=true,fill=165,edge=245},
              {selected=true,hovered=false,fill=195,edge=255},
              {selected=true,hovered=true,fill=195,edge=255}}
for _,name in ipairs({'UPPER_AIRWAY','TRACHEA','DEEP_LUNG'}) do
 for _,state in ipairs(states) do
  renderCalls={}; imageCalls={}
  Masks.Draw({},name,rect,color,state.selected,state.hovered)
  assert(#renderCalls==12 and renderCalls[1].name=='nvgSave' and renderCalls[12].name=='nvgRestore')
  assert(#imageCalls==2 and imageCalls[1]=='Sprites/LungMasks/'..name..'.png'
         and imageCalls[2]=='Sprites/LungMasks/'..name..'_outline.png')
  for pass=1,2 do
   local offset=1+(pass-1)*5
   assert(renderCalls[offset+1].name=='nvgBeginPath')
   local box=renderCalls[offset+2]; assert(box.name=='nvgRect')
   near(box.args[2],rect.x); near(box.args[3],rect.y); near(box.args[4],rect.w); near(box.args[5],rect.h)
   local paint=renderCalls[offset+3]; assert(paint.name=='nvgImagePatternTinted')
   near(paint.args[2],rect.x); near(paint.args[3],rect.y); near(paint.args[4],rect.w); near(paint.args[5],rect.h)
   assert(paint.args[6]==0 and imagePaths[paint.args[7]]==imageCalls[pass])
   local tint=paint.args[8]
   assert(tint.r==color[1] and tint.g==color[2] and tint.b==color[3])
   assert(tint.a==(pass==1 and state.fill or state.edge))
   assert(renderCalls[offset+4].name=='nvgFillPaint' and renderCalls[offset+5].name=='nvgFill')
   assert(renderCalls[offset+4].args[2]==paint,'Canvas must be filled with PNG paint, not solid color')
  end
 end
end
for _,case in ipairs({{name='INVALID',rect=rect},
                     {name='TRACHEA',rect={x=0,y=0,w=0,h=849}},
                     {name='DEEP_LUNG',rect={x=0,y=0,w=777,h=-1}}}) do
 renderCalls={}; imageCalls={}; Masks.Draw({},case.name,case.rect,color,false,false)
 assert(#renderCalls==0 and #imageCalls==0,'Invalid/empty draw must be inert')
end
""",
'Mask Widget hover hooks selection Render and visual hit layout use real interface': r"""
local LungWidget=require('UI.LungRegionWidget')
local seen={}
local widget=LungWidget{
 regionType='TRACHEA',regionColor={80,196,255,255},
 onPointerEnter=function(event,self) assert(event.tag=='enter' and self.hovered_); seen.enter=self end,
 onPointerLeave=function(event,self) assert(event.tag=='leave' and not self.hovered_); seen.leave=self end,
}
assert(widget.props.regionType==nil and widget.props.regionColor==nil)
assert(widget.regionType_=='TRACHEA' and not widget.selected_ and not widget.hovered_)
widget.OnMouseEnter=function(self) seen.legacyEnter=self end
widget.OnMouseLeave=function(self) seen.legacyLeave=self end
widget:OnPointerEnter{tag='enter',pointerType='mouse'}
assert(seen.enter==widget and seen.legacyEnter==widget and widget.hovered_)
widget:OnPointerLeave{tag='leave'}
assert(seen.leave==widget and seen.legacyLeave==widget and not widget.hovered_)
widget.rect={x=37,y=51,w=777,h=849}
local visual={x=2000,y=1500,w=388.5,h=424.5}
widget.absoluteLayout=visual -- Real base interface permits separately measured visual hit layout.
assert(widget:HitTest(visual.x+visual.w*.5,visual.y+visual.h*.24))
assert(not widget:HitTest(widget.rect.x+widget.rect.w*.5,widget.rect.y+widget.rect.h*.24),
 'HitTest must use visual layout rather than unscrolled render layout')
widget:SetSelected(true); widget:OnPointerEnter{tag='enter',pointerType='mouse'}
renderCalls={}; widget:Render({})
assert(widget.selected_)
local paint=renderCalls[4]; assert(paint.name=='nvgImagePatternTinted')
near(paint.args[2],widget.rect.x); near(paint.args[3],widget.rect.y)
assert(paint.args[8].a==195,'Selected rendering must override hover alpha')
widget:SetSelected(false); renderCalls={}; widget:Render({})
assert(renderCalls[4].args[8].a==165)
""",
'Inflammation draws only translucent pure red filled disks in lung mode': r"""
local sim,obs=Sim.New(),Observation.New()
sim.mouse.symptom=0
for i,r in ipairs(sim.world.map.regions) do r.inflammation=Config.Gameplay.hotspotThreshold*i end
for _,mode in ipairs({'body','anatomy'}) do
 if mode=='anatomy' then obs:ShowAnatomy() end
 renderCalls={}; MouseView.Draw({},83,117,800,700,{sim=sim,observation=obs,time=999})
 for _,call in ipairs(renderCalls) do
  assert(call.name~='nvgCircle' and call.name~='nvgEllipse' and call.name~='nvgStroke',
   'Full-body/anatomy cannot display lung disks or the removed chest blue ring')
 end
end
assert(obs:OpenLung()); settle(obs)
for _,phase in ipairs({0,.25,.75,.99}) do
 obs.visualTime=2.2*phase
 local layout=MouseView.GetLayout(83,117,800,700,obs)
 local markers=MouseView.GetInflammationMarkers(sim,layout,obs.visualTime)
 assert(#markers==6)
 renderCalls={}; MouseView.Draw({},83,117,800,700,{sim=sim,observation=obs,time=999})
 local circles=assertRedCircleDraw(markers)
 for _,circle in ipairs(circles) do assert(circle.tint.a>0,'Nonzero fixture must actually paint') end
end
for _,r in ipairs(sim.world.map.regions) do r.inflammation=0 end
renderCalls={}; MouseView.Draw({},83,117,800,700,{sim=sim,observation=obs,time=999})
assertRedCircleDraw({})
""",
'Inflammation radius expands every cycle and resets instead of contracting': r"""
local sim,obs=Sim.New(),Observation.New(); obs:ShowAnatomy(); obs:OpenLung(); settle(obs)
for i,r in ipairs(sim.world.map.regions) do r.inflammation=Config.Gameplay.hotspotThreshold*i end
local layout=MouseView.GetLayout(83,117,800,700,obs)
local period=2.2
local origin=MouseView.GetInflammationMarkers(sim,layout,0)
assert(#origin==6)
for cycle=0,2 do
 local previous
 for _,phase in ipairs({0,.01,.10,.25,.50,.75,.90,.999}) do
  local markers=MouseView.GetInflammationMarkers(sim,layout,(cycle+phase)*period)
  assert(#markers==6)
  for i,m in ipairs(markers) do
   near(m.phase,phase); near(m.x,origin[i].x); near(m.y,origin[i].y)
   near(m.value,origin[i].value); near(m.severity,origin[i].severity); assert(m.red==origin[i].red)
   assert(m.alpha>0 and m.alpha<1 and m.radius>0)
   if previous then
    assert(m.radius>previous[i].radius,'Radius must increase at every same-cycle phase')
    assert(m.alpha<previous[i].alpha,'Outward disk must fade, never become opaque')
   end
  end
  previous=markers
 end
 local reset=MouseView.GetInflammationMarkers(sim,layout,(cycle+1)*period)
 for i,m in ipairs(reset) do
  near(m.phase,0); near(m.radius,origin[i].radius); near(m.alpha,origin[i].alpha)
  assert(m.radius<previous[i].radius and m.alpha>previous[i].alpha,
   'Next cycle must restart small, not run a breathing/sine contraction')
 end
end
""",
'Inflammation fixed phase severity darkens red and increases alpha and radius': r"""
local sim,obs=Sim.New(),Observation.New(); obs:ShowAnatomy(); obs:OpenLung(); settle(obs)
local layout=MouseView.GetLayout(83,117,800,700,obs)
local anchors={{.50,.055,.45},{.50,.24,.50},{.25,.49,1},{.75,.49,1},{.27,.79,.9},{.73,.79,.9}}
for _,phase in ipairs({0,.1,.5,.9,.999}) do
 local previous
 for _,multiple in ipairs({.02,.1,.5,1,2,4,8,32}) do
  for _,r in ipairs(sim.world.map.regions) do r.inflammation=Config.Gameplay.hotspotThreshold*multiple end
  local markers=MouseView.GetInflammationMarkers(sim,layout,phase*2.2)
  assert(#markers==6)
  for i,m in ipairs(markers) do
   local severity=multiple/(multiple+1); local anchor=anchors[i]
   near(m.phase,phase); near(m.severity,severity)
   near(m.x,layout.lung.x+layout.lung.w*anchor[1]); near(m.y,layout.lung.y+layout.lung.h*anchor[2])
   near(m.radius,math.min(layout.lung.w,layout.lung.h)*(.04+.09*severity)*anchor[3]*(.45+phase*1.15))
   near(m.alpha,severity*(.30+.40*severity)*(1-phase*.78))
   assert(math.type(m.red)=='integer' and m.red==math.floor(255-severity*80))
   if previous then
    assert(m.severity>previous[i].severity and m.alpha>previous[i].alpha and m.radius>previous[i].radius,
     'Higher local inflammation must be stronger at the same animation phase')
    assert(m.red<previous[i].red,'Higher severity must be deeper red, not a pink/orange gradient')
   end
  end
  previous=markers
 end
end
""",
'GameScene observation pause keeps sim time frozen while rendered red disks expand': r"""
local hud,game,sim,scale,obs=hudFixture(); guidedStart(hud,sim,scale,obs,'TRACHEA')
callback(hud,'observeBtn'); settleScale(scale); settle(obs); hud:Update(.2)
callback(hud,'anatomyToggleBtn'); callback(hud,'lungHotspot'); settle(obs); hud:Update(.2)
assert(obs.mode=='lung' and scale:CurrentScale()=='mouse' and sim.started and sim.paused)
for i,r in ipairs(sim.world.map.regions) do r.inflammation=Config.Gameplay.hotspotThreshold*i end
-- Set only a visual-phase fixture. Disease/world clocks remain their actual paused values.
obs.visualTime=2.2*.05
local t,wt,world=sim.time,sim.world.time,sim.world
local initial
for frame=0,30 do
 if frame>0 then game:Update(1/60); hud:Update(1/60) end
 assert(sim.time==t and sim.world.time==wt and sim.world==world and sim.pauseReasons.observation)
 local rect=game:GetAbsoluteLayout(); local layout=MouseView.GetLayout(rect.x,rect.y,rect.w,rect.h,obs)
 local markers=MouseView.GetInflammationMarkers(sim,layout,obs.visualTime)
 renderCalls={}; game:Render({}); assertRedCircleDraw(markers)
 if initial then
  for i,m in ipairs(markers) do
   near(m.value,initial[i].value); near(m.severity,initial[i].severity)
   assert(m.radius>initial[i].radius and m.alpha<initial[i].alpha,
    'Actual GameScene render must animate disks even while simulation is paused')
  end
 else initial=markers end
end
hud:Destroy(); game:Destroy()
""",
'Masks ALL Draw is hover-only pure white existing PNG union without outline': r"""
local Masks=require('Game.Views.LungRegionMasks')
local rect={x=83.25,y=117.5,w=291.375,h=530.625}
for _,selected in ipairs({false,true}) do
 renderCalls={}; imageCalls={}; Masks.Draw({},'ALL',rect,{1,2,3,4},selected,false)
 assert(#renderCalls==0 and #imageCalls==0,'ALL must not draw when mouse is not hovering')
 renderCalls={}; imageCalls={}; Masks.Draw({},'ALL',rect,{1,2,3,4},selected,true)
 assertWhiteUnionDraw(rect)
end
for _,r in ipairs({{x=0,y=0,w=0,h=849},{x=0,y=0,w=777,h=-1}}) do
 renderCalls={}; imageCalls={}; Masks.Draw({},'ALL',r,{255,255,255,255},false,true)
 assert(#renderCalls==0 and #imageCalls==0,'Empty ALL draw must be inert even while hovered')
end
""",
'HUD real lung hover enter leave touch and hide cannot stick white mask': r"""
local hud,game,sim,scale,obs=hudFixture(); callback(hud,'anatomyToggleBtn'); hud:Update(.2)
local hotspot=assert(hud.root:FindById('lungHotspot'))
assert(getmetatable(hotspot)==require('UI.LungRegionWidget') and hotspot.regionType_=='ALL')
local layout=hud:GetObservationLayout(); hotspot.rect=layout.chest
local x,y=layout.chest.x+layout.chest.w*.5,layout.chest.y+layout.chest.h*.24
assert(hotspot:IsVisible() and hotspot:HitTest(x,y) and not hotspot.hovered_)
renderCalls={}; imageCalls={}; hotspot:Render({})
assert(#renderCalls==0 and #imageCalls==0)
local entered,left=0,0
-- Wrap the real HUD widget's existing callback slots, preserving their argument order.
local oldEnter,oldLeave=hotspot.props.onPointerEnter,hotspot.props.onPointerLeave
hotspot.props.onPointerEnter=function(event,self)
 assert(self==hotspot and event.x==x and event.y==y)
 assert(self.hovered_==(event.pointerType=='mouse')); entered=entered+1
 if oldEnter then oldEnter(event,self) end
end
hotspot.props.onPointerLeave=function(event,self)
 assert(self==hotspot and not self.hovered_); left=left+1
 if oldLeave then oldLeave(event,self) end
end
local mouse={pointerType='mouse',x=x,y=y,target=hotspot}
local touch={pointerType='touch',x=x,y=y,target=hotspot,IsTouch=function() return true end}
hotspot:OnPointerEnter(mouse); assert(hotspot.hovered_ and entered==1)
renderCalls={}; imageCalls={}; hotspot:Render({}); assertWhiteUnionDraw(layout.chest)
hotspot:OnPointerLeave(mouse); assert(not hotspot.hovered_ and left==1)
renderCalls={}; imageCalls={}; hotspot:Render({}); assert(#renderCalls==0 and #imageCalls==0)
hotspot:OnPointerEnter(touch); assert(not hotspot.hovered_ and entered==2)
renderCalls={}; imageCalls={}; hotspot:Render({}); assert(#renderCalls==0 and #imageCalls==0)
hotspot:OnPointerLeave(touch); assert(not hotspot.hovered_ and left==2)
hotspot:OnPointerEnter(mouse); assert(hotspot.hovered_)
hotspot:OnPointerEnter(touch); assert(not hotspot.hovered_,'Touch entry must clear a previous mouse hover')
renderCalls={}; imageCalls={}; hotspot:Render({}); assert(#renderCalls==0 and #imageCalls==0)
hotspot:OnPointerEnter(mouse); hotspot:SetVisible(false)
assert(not hotspot.hovered_ and not hotspot:IsVisible(),'Hidden hotspot must clear hover without PointerLeave')
hotspot:SetVisible(true); renderCalls={}; imageCalls={}; hotspot:Render({})
assert(not hotspot.hovered_ and #renderCalls==0 and #imageCalls==0,'Showing it again cannot resurrect white hover')
-- Actual HUD transition hides this same widget without synthetic pointer leave.
hotspot:OnPointerEnter(mouse)
hotspot:OnClick{x=x,y=y,target=hotspot,IsPrimaryAction=function() return true end}
assert(obs.mode=='lung' and obs:IsTransitioning() and not hotspot:IsVisible() and not hotspot.hovered_)
settle(obs); hud:Update(.2); callback(hud,'observationBackBtn'); settle(obs); hud:Update(.2)
assert(obs.mode=='anatomy' and hotspot:IsVisible() and not hotspot.hovered_)
renderCalls={}; imageCalls={}; hotspot:Render({}); assert(#renderCalls==0 and #imageCalls==0)
hud:Destroy(); game:Destroy()
""",
}


def png_alpha(path: Path) -> bytes:
    """Decode actual PNGs independently; never use generation metadata as oracle."""
    with Image.open(path) as image:
        assert image.format == 'PNG', f'{path}: expected PNG'
        assert image.mode == 'RGBA', f'{path}: expected explicit RGBA alpha'
        assert image.size == MASK_SIZE, f'{path}: {image.size} != {MASK_SIZE}'
        pixels = image.tobytes()
    assert all(pixels[i:i+3] == b'\xff\xff\xff' for i in range(0, len(pixels), 4)), \
        f'{path}: masks must be white alpha textures, not painted color blocks'
    return pixels[3::4]


def mask_pngs() -> dict[str, bytes]:
    return {name: png_alpha(ROOT / 'assets' / 'Sprites' / 'LungMasks' / f'{name}.png')
            for name in MASK_TYPES}


def rle_pixels(lua: LuaRuntime, name: str) -> bytes:
    """Validate and expand real Lua RLE, without reproducing Contains's lookup."""
    mask = lua.eval("function(name) return require('Game.Views.LungMaskData')[name] end")(name)
    width, height = MASK_SIZE
    assert (mask.width, mask.height) == MASK_SIZE, f'{name}: RLE dimensions'
    assert len(mask.rows) == height, f'{name}: missing/excess RLE rows'
    pixels = bytearray(width * height)
    for y in range(height):
        row = mask.rows[y + 1]
        assert len(row) % 2 == 0, f'{name} row {y}: unpaired RLE endpoint'
        previous_end = -1
        for i in range(1, len(row) + 1, 2):
            start, end = row[i], row[i + 1]
            assert type(start) is int and type(end) is int, f'{name} row {y}: noninteger run'
            assert 0 <= start < end <= width, f'{name} row {y}: invalid [{start},{end})'
            assert start > previous_end, f'{name} row {y}: unordered/overlapping/adjacent runs'
            pixels[y * width + start:y * width + end] = b'\x01' * (end - start)
            previous_end = end
    return bytes(pixels)


def assert_pixel_plane(actual: bytes, expected: bytes, description: str) -> None:
    assert len(actual) == len(expected), f'{description}: dimension mismatch'
    if actual != expected:
        index = next(i for i, (a, b) in enumerate(zip(actual, expected)) if a != b)
        x, y = index % MASK_SIZE[0], index // MASK_SIZE[0]
        raise AssertionError(f'{description}: pixel ({x},{y}) actual={actual[index]} expected={expected[index]}')


def mask_consistency(lua: LuaRuntime, name: str) -> None:
    alpha = png_alpha(ROOT / 'assets' / 'Sprites' / 'LungMasks' / f'{name}.png')
    expected = bytes(value > 40 for value in alpha)
    assert any(expected) and 0 in expected, f'{name}: nontrivial contour required'
    assert_pixel_plane(rle_pixels(lua, name), expected, f'{name} RLE vs PNG')
    with Image.frombytes('L', MASK_SIZE, expected) as plane:
        bbox = plane.getbbox()
    assert bbox is not None
    x0, y0, x1, y1 = bbox
    mask = lua.eval("function(name) return require('Game.Views.LungMaskData')[name] end")(name)
    assert tuple(mask.bounds[key] for key in ('x', 'y', 'w', 'h')) == \
        (x0, y0, x1 - x0, y1 - y0), f'{name}: bounds must be tight PNG bbox'
    bounds = lua.eval("require('Game.Views.LungRegionMasks').Bounds")
    width, height = MASK_SIZE
    for rect in ({'x': 0, 'y': 0, 'w': width, 'h': height},
                 {'x': 83.25, 'y': -117.5, 'w': width * .375, 'h': height * .625}):
        actual = bounds(name, lua.table_from(rect))
        expected_bounds = (rect['x'] + x0 / width * rect['w'],
                           rect['y'] + y0 / height * rect['h'],
                           (x1 - x0) / width * rect['w'], (y1 - y0) / height * rect['h'])
        assert all(abs(actual[key] - value) <= 1e-7
                   for key, value in zip(('x', 'y', 'w', 'h'), expected_bounds)), \
            f'{name}: Bounds must transform actual PNG bbox, including absolute offset'
    # Pixel centers avoid roundoff at cell boundaries; all pixels, not samples.
    # Both 1:1 and translated/nonuniform scaling must use the same actual contour.
    lua.eval(r"""function(name, alpha, width, height)
        local Masks=require('Game.Views.LungRegionMasks')
        for _,rect in ipairs({{x=0,y=0,w=width,h=height},
                              {x=83.25,y=-117.5,w=width*.375,h=height*.625}}) do
            for y=0,height-1 do for x=0,width-1 do
                local a=string.byte(alpha,y*width+x+1)
                local hit=Masks.Contains(name,rect,rect.x+(x+.5)/width*rect.w,
                                         rect.y+(y+.5)/height*rect.h)
                if hit~=(a>40) then error(string.format(
                    '%s Contains/PNG mismatch pixel (%d,%d) alpha=%d hit=%s',
                    name,x,y,a,tostring(hit))) end
            end end
        end
        assert(#imageCalls==0,'Bounds/Contains must not request textures')
    end""")(name, alpha, *MASK_SIZE)


def masks_no_overlap(lua: LuaRuntime) -> None:
    pngs = mask_pngs()
    rles = [rle_pixels(lua, name) for name in MASK_TYPES]
    for index, values in enumerate(zip(*(pngs[name] for name in MASK_TYPES))):
        assert sum(value > 0 for value in values) <= 1, \
            f'PNG overlap at ({index % MASK_SIZE[0]},{index // MASK_SIZE[0]})'
    for index, values in enumerate(zip(*rles)):
        assert sum(values) <= 1, f'RLE overlap at pixel {index}'
    lua.eval(r"""function(width,height)
        local Masks=require('Game.Views.LungRegionMasks')
        local rect={x=37,y=51,w=width,h=height}
        for y=0,height-1 do for x=0,width-1 do
            local count=0
            for _,name in ipairs({'UPPER_AIRWAY','TRACHEA','DEEP_LUNG'}) do
                if Masks.Contains(name,rect,rect.x+x+.5,rect.y+y+.5) then count=count+1 end
            end
            if count>1 then error(string.format('Contains overlap at (%d,%d)',x,y)) end
        end end
    end""")(*MASK_SIZE)


def masks_source_transparency(lua: LuaRuntime) -> None:
    with Image.open(ROOT / 'assets' / 'Sprites' / 'lung_stage_0.png') as image:
        source = image.convert('RGBA').getchannel('A').crop(SOURCE_CROP)
        assert source.size == MASK_SIZE
        alpha = source.tobytes()
    assert 0 in alpha and any(0 < value <= 40 for value in alpha), \
        'Source fixtures must include alpha0 and low-alpha edge pixels'
    pngs = mask_pngs()
    for name in MASK_TYPES:
        rle = rle_pixels(lua, name)
        for index, (original, painted, hit) in enumerate(zip(alpha, pngs[name], rle)):
            if original <= 40:
                assert painted == 0 and hit == 0, f'{name}: transparent source hit/paint at pixel {index}'
            elif painted:
                assert painted == original, f'{name}: source edge alpha changed at pixel {index}'
    lua.eval(r"""function(alpha,width,height)
        local Masks=require('Game.Views.LungRegionMasks')
        local rect={x=-83,y=117,w=width*.5,h=height*.5}
        local zeros,edges=0,0
        for y=0,height-1 do for x=0,width-1 do
            local a=string.byte(alpha,y*width+x+1)
            if a<=40 then
                if a==0 then zeros=zeros+1 else edges=edges+1 end
                for _,name in ipairs({'UPPER_AIRWAY','TRACHEA','DEEP_LUNG'}) do
                    if Masks.Contains(name,rect,rect.x+(x+.5)*.5,rect.y+(y+.5)*.5) then
                        error(string.format('%s source alpha=%d hit at (%d,%d)',name,a,x,y))
                    end
                end
            end
        end end
        assert(zeros>0 and edges>0,'Transparent-source loops must not be vacuous')
    end""")(alpha, *MASK_SIZE)


def mask_widget_pixels(lua: LuaRuntime) -> None:
    lua.eval(r"""function(pngs,width,height)
        local Masks=require('Game.Views.LungRegionMasks')
        local LungWidget=require('UI.LungRegionWidget')
        local hud,game,sim,scale,obs=hudFixture()
        callback(hud,'anatomyToggleBtn'); callback(hud,'lungHotspot'); settle(obs); hud:Update(.2)
        local layout,parent=hud:GetObservationLayout()
        local rect=layout.lung
        for _,name in ipairs({'UPPER_AIRWAY','TRACHEA','DEEP_LUNG'}) do
            local widget=assert(hud.root:FindById('start_'..name))
            assert(getmetatable(widget)==LungWidget and widget.HitTest~=UI.Widget.HitTest,
                   'HUD must instantiate the real mask Widget, not a rectangular Panel')
            near(widget.props.left+parent.x,rect.x); near(widget.props.top+parent.y,rect.y)
            near(widget.props.width,rect.w); near(widget.props.height,rect.h)
            assert(widget.props.pointerEvents=='auto' and not widget.props.backgroundColor)
            assert(hud.root:FindById('startLabel_'..name).props.pointerEvents=='none')
            -- Inject a measured visual-layout fixture, not an emulated Yoga calculation.
            widget.rect=rect
            local alpha=pngs[name]
            for y=0,height-1 do for x=0,width-1 do
                local a=string.byte(alpha,y*width+x+1)
                local hit=widget:HitTest(rect.x+(x+.5)/width*rect.w,rect.y+(y+.5)/height*rect.h)
                if hit~=(a>40) then error(string.format(
                    '%s Widget:HitTest/PNG mismatch at (%d,%d) alpha=%d hit=%s',
                    name,x,y,a,tostring(hit))) end
            end end
        end
        local anchors={UPPER_AIRWAY={.5,.075},TRACHEA={.5,.24},DEEP_LUNG={.24,.67}}
        for name,anchor in pairs(anchors) do
            local widget=hud.root:FindById('start_'..name)
            local x,y=rect.x+rect.w*anchor[1],rect.y+rect.h*anchor[2]
            assert(widget:HitTest(x,y) and Masks.Contains(name,rect,x,y))
            widget:OnClick{x=x,y=y,target=widget,IsPrimaryAction=function() return true end}
            assert(obs.selectedStartType==name,'Real mask widget callback must select its own region')
            for _,other in ipairs({'UPPER_AIRWAY','TRACHEA','DEEP_LUNG'}) do
                if other~=name then assert(not hud.root:FindById('start_'..other):HitTest(x,y)) end
            end
        end
        -- Fixed central gaps must fail the UI override AND guarded callback.
        local before=obs.selectedStartType
        for _,v in ipairs({.50,.79,.90}) do
            local x,y=rect.x+rect.w*.50,rect.y+rect.h*v
            for _,name in ipairs({'UPPER_AIRWAY','TRACHEA','DEEP_LUNG'}) do
                local widget=hud.root:FindById('start_'..name)
                assert(UI.Widget.HitTest(widget,x,y),'Gap must be inside full rectangular canvas')
                assert(not widget:HitTest(x,y),'Gap must not be hit by any mask widget')
                widget:OnClick{x=x,y=y,target=widget,IsPrimaryAction=function() return true end}
                assert(obs.selectedStartType==before,'Gap callback must preserve selection')
            end
        end
        hud:Destroy(); game:Destroy()
    end""")(lua.table_from(mask_pngs()), *MASK_SIZE)


def all_mask_widget_pixels(lua: LuaRuntime) -> None:
    """Independent PNG union oracle for the real anatomy hotspot and HUD guard."""
    pngs = mask_pngs()
    expected = bytes(any(alpha > 40 for alpha in values)
                     for values in zip(*(pngs[name] for name in MASK_TYPES)))
    rles = [rle_pixels(lua, name) for name in MASK_TYPES]
    expanded = bytes(any(values) for values in zip(*rles))
    assert_pixel_plane(expanded, expected, 'ALL union RLE vs independently decoded PNGs')
    assert 0 in expected and 1 in expected, 'ALL must retain genuine tissue and transparent gaps'
    lua.eval(r"""function(union,width,height)
        local Masks=require('Game.Views.LungRegionMasks')
        local LungWidget=require('UI.LungRegionWidget')
        local hud,game,sim,scale,obs=hudFixture()
        callback(hud,'anatomyToggleBtn')
        local overlay=assert(hud.root:FindById('observationOverlay'))
        local widget=assert(hud.root:FindById('lungHotspot'))
        assert(getmetatable(widget)==LungWidget and widget.regionType_=='ALL'
               and widget.HitTest~=UI.Widget.HitTest,
               'Actual anatomy hotspot must be the same pixel mask widget, not an ellipse/rectangle')
        assert(widget.props.pointerEvents=='auto' and not widget.props.backgroundColor
               and not widget.props.shape and not widget.props.backgroundGradient)
        for _,canvas in ipairs({{x=37,y=51,w=800,h=700},{x=83.25,y=-117.5,w=390,h=844}}) do
            overlay.rect=canvas; hud:ApplyObservationLayout()
            local layout,parent=hud:GetObservationLayout()
            local rect=layout.chest
            near(widget.props.left+parent.x,rect.x); near(widget.props.top+parent.y,rect.y)
            near(widget.props.width,rect.w); near(widget.props.height,rect.h)
            -- A measured rect fixture only; no claim to emulate actual Yoga/OS routing.
            widget.rect=rect
            local event={target=widget,IsPrimaryAction=function() return true end}
            for y=0,height-1 do for x=0,width-1 do
                local expected=string.byte(union,y*width+x+1)==1
                event.x=rect.x+(x+.5)/width*rect.w
                event.y=rect.y+(y+.5)/height*rect.h
                local maskHit=Masks.Contains('ALL',rect,event.x,event.y)
                local widgetHit=widget:HitTest(event.x,event.y)
                local guardHit=hud:ObservationHit(nil,event)
                if maskHit~=expected or widgetHit~=expected or guardHit~=expected then
                    error(string.format('ALL PNG union pixel (%d,%d): expected=%s Contains=%s Widget=%s HUD=%s',
                          x,y,tostring(expected),tostring(maskHit),tostring(widgetHit),tostring(guardHit)))
                end
            end end
        end
        assert(#imageCalls==0,'Pixel hit tests cannot load or rewrite masks')
        hud:Destroy(); game:Destroy()
    end""")(expected, *MASK_SIZE)


TESTS['正式三选一自动打开仅三张，不能关闭，提交后继续与输入屏蔽'] = r"""
local hud,game,sim,scale,obs=hudFixture();guidedStart(hud,sim,scale,obs,'UPPER_AIRWAY')
local ok,pending=sim:GrantCardChoice('stage:1');assert(ok)
assert(hud.cardInfoShown_ and sim.paused and hud.root:FindById('cardInfoOverlay'):IsVisible())
local shown=0
for _,card in ipairs(Config.Cards.definitions) do
 if hud.root:FindById('cardBox_'..card.id):IsVisible() then shown=shown+1 end
end
assert(shown==3 and not hud.root:FindById('cardContinue'):IsVisible())
assert(not hud.root:FindById('cardDebugLevels'):IsVisible())
hud:CloseCardInfo();assert(hud.cardInfoShown_ and sim.cards.pending==pending)
local mass=sim.world.player.mass;callback(hud,'splitBtn');assert(sim.world.player.mass==mass and #sim.world.swarms==1)
callback(hud,'cardGet_'..pending.cards[1].id)
assert(sim.cardNotice and sim.paused and sim.world.immuneAlertLevel==1)
assert(hud.root:FindById('cardContinue'):IsVisible())
sim:SetPaused('observation-test',true);callback(hud,'cardContinue')
assert(not hud.cardInfoShown_ and sim.stage==2 and sim.paused and sim.pauseReasons['observation-test'])
assert(not sim.pauseReasons['card-choice'] and not sim.pauseReasons['card-alert'] and not sim.pauseReasons['card-info'])
hud:Destroy();game:Destroy()
"""

for _mask_name in MASK_TYPES:
    TESTS[f'Masks {_mask_name} RLE Bounds Contains match every PNG pixel'] = \
        lambda lua, name=_mask_name: mask_consistency(lua, name)
TESTS['Masks PNG RLE and Contains regions never overlap'] = masks_no_overlap
TESTS['Masks original source alpha0 and low-alpha edges never hit'] = masks_source_transparency
TESTS['Mask Widget HitTest matches every PNG pixel and HUD rejects fixed gaps'] = mask_widget_pixels
TESTS['Masks ALL union Contains Widget and HUD hit guard match every actual PNG pixel'] = all_mask_widget_pixels


def runtime() -> LuaRuntime:
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute("package.path = " + repr(str(ROOT / 'scripts' / '?.lua') + ';' +
                                       str(ROOT / 'scripts' / '?' / 'init.lua') + ';') + " .. package.path")
    lua.execute(SETUP)
    return lua


def main() -> int:
    # 2026-10-13: 宿主观察/器官选区已取消；旧用例保留作历史资料，当前入口验证鸟结局。
    from bird_ui_regression import TESTS as current_tests, runtime as current_runtime
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', default='')
    args = parser.parse_args()
    selected = [(name, code) for name, code in current_tests.items() if args.only.lower() in name.lower()]
    if not selected:
        parser.error('No matching tests')
    failures = []
    started = time.monotonic()
    for name, code in selected:
        try:
            lua = current_runtime()
            if callable(code):
                code(lua)
            else:
                lua.execute(code)
            print('PASS ' + name, flush=True)
        except Exception as exc:
            failures.append(name)
            print('FAIL ' + name + '\n' + str(exc), flush=True)
    print(f'{len(selected)-len(failures)}/{len(selected)} passed in {time.monotonic()-started:.2f}s', flush=True)
    print('LIMIT: dependency-stub Lua tests, not engine rendering/Yoga/OS focus/physical touch acceptance.', flush=True)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
