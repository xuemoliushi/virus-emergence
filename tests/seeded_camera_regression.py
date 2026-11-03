"""Shared real CellView transforms and bounds, with only native rendering mocked."""
from pathlib import Path
import json
from lua_test_runtime import LuaRuntime
from cell_render_regression import SETUP
ROOT=Path(__file__).resolve().parents[1]
lua=LuaRuntime(unpack_returned_tuples=True)
lua.globals().SCRIPT_PATH=str(ROOT/'scripts/?.lua').replace('\\','/')
lua.execute(SETUP)
lua.execute('''
local Config=require('Core.Config')
local Bounds=require('Game.CameraBounds')
local view=View.New()
local camera={x=0,y=0};view:SetCamera(camera)
local world={width=120,height=144}
local cases=0
for _,size in ipairs({{1920,1080},{960,540},{640,360},{390,844},{240,180}})do
 local l={x=17,y=31,w=size[1],h=size[2]}
 local area={x=l.x+8,y=l.y+l.h*.2,w=l.w-16,h=l.h*.6}
 view:SetViewport(area)
 for _,zoom in ipairs({.01,.2,1,2,3})do
  for _,target in ipairs({{-100,-100},{0,0},{39,48},{78,96},{200,200}})do
   camera.x,camera.y=target[1],target[2]
   local ppm,cx,cy=view:CameraTransform(l,zoom)
   Bounds.Clamp(camera,world,area,ppm,cx,cy)
   local rect=Bounds.View(camera,area,ppm,cx,cy)
   if rect.w<world.width then assert(rect.x>=-1e-8 and rect.x+rect.w<=world.width+1e-8)
   else assert(math.abs(rect.x+rect.w*.5-world.width*.5)<1e-8)end
   if rect.h<world.height then assert(rect.y>=-1e-8 and rect.y+rect.h<=world.height+1e-8)
   else assert(math.abs(rect.y+rect.h*.5-world.height*.5)<1e-8)end
   for _,p in ipairs({{0,0},{39,48},{78,96},{camera.x,camera.y}})do
    local x,y=view:WorldToScreen(p[1],p[2],l,zoom)
    local wx,wy=view:ScreenToWorld(x,y,l,zoom)
    assert(math.abs(wx-p[1])+math.abs(wy-p[2])<1e-8,'inverse input differs')
   end
   cases=cases+1
  end
 end
end
CAMERA_CASES=cases
''')
out=ROOT/'validation/seeded-map/camera.json'
out.write_text(json.dumps(dict(passed=True,cases=lua.globals().CAMERA_CASES,
    scope='Real camera bounds and CellView round-trip; excludes native input/Yoga'),indent=2),encoding='utf-8')
print(out.read_text())
