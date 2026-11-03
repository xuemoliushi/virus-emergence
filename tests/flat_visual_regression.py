"""Production flat rendering/resource protocol; native PNGs verify actual pixels."""
from pathlib import Path
from PIL import Image
from lua_test_runtime import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
lua = LuaRuntime(unpack_returned_tuples=True)
lua.globals().SCRIPT_PATH = str(ROOT/'scripts/?.lua').replace('\\', '/')
sizes = {}
for name in ('image/flow_bed_decal.png.png', 'image/integrated/tissue_base_seamless.png',
             'image/bioluminescent/background.png'):
    with Image.open(ROOT/'assets'/name) as im:
        sizes[name] = im.size
lua.globals().image_size = lambda path: sizes[path]
lua.execute(r'''
package.path=SCRIPT_PATH..';'..package.path
calls={};loads={};deleted={};handles={}
for _,name in ipairs({'nvgBeginPath','nvgMoveTo','nvgLineTo','nvgClosePath','nvgRect',
 'nvgFillColor','nvgFill','nvgFillPaint','nvgStrokeWidth','nvgStrokeColor','nvgStroke',
 'nvgCircle','nvgLineCap','nvgLineJoin','nvgQuadTo'}) do
 _G[name]=function(...) calls[#calls+1]={name,...} end
end
function nvgRGBA(r,g,b,a) return {r,g,b,a} end
function nvgCreateImage(vg,path,flags)
 loads[#loads+1]={path,flags};handles[#handles+1]=path;return #handles
end
function nvgImageSize(vg,id) return image_size(handles[id]) end
function nvgDeleteImage(vg,id) deleted[#deleted+1]=id end
function nvgImagePattern(vg,x,y,w,h,rotation,id,alpha)
 calls[#calls+1]={'pattern',handles[id],x,y,w,h,rotation,alpha}
 return id
end
NVG_ROUND=1;NVG_IMAGE_REPEATX=2;NVG_IMAGE_REPEATY=4
Config=require('Core.Config');Visual=require('Game.FlatMapVisual')
art=require('Game.Views.ArtResources').New(5);vg={}
map={width=20,height=20,renderRows={},floor={},spawn={x=-100,y=-100},flowMarks={},
 flows={{id=1,kind='cross',width=3,speed=1,length=14,
 points={{x=3,y=4},{x=10,y=4},{x=10,y=11}}},
 {id=2,kind='vortex',cx=14,cy=14,ringRadius=3,direction=1,width=3,speed=1}}}
for y=1,20 do
 map.renderRows[y]={{x=1,w=18}};map.floor[y]={}
 for x=1,20 do map.floor[y][x]=x>1 and x<20 and y>1 and y<20 end
end
function map:FlowAt()return 1,0 end
function map:Contains()return true end
''')
lua.execute(r'''
Visual.Draw(vg,map,{x=0,y=0,w=800,h=800},40,0,0,0,art)
assert(#loads==2 and loads[1][1]==Config.ArtSlots.tissueBg and loads[1][2]==6)
assert(loads[2][1]==Config.ArtSlots.flowBed)
local flowCount,diagonal,lastFlow,lastFill=0,false,0,0
for i,c in ipairs(calls) do
 if c[1]=='pattern' and c[2]==Config.ArtSlots.flowBed then
  flowCount=flowCount+1;lastFlow=i
  assert(c[5]>0 and c[6]>0 and c[8]==Config.EnvironmentVisual.flatFlowBedAlpha)
  if math.abs(c[7])>.1 then diagonal=true end
 elseif c[1]=='nvgFill' then lastFill=i end
end
assert(flowCount>=10 and diagonal,'Polyline turns and vortex must both paint the real decal')
assert(lastFill>lastFlow,'Solid walls mask the final flow decal')
Visual.Draw(vg,map,{x=0,y=0,w=800,h=800},40,0,0,1,art)
assert(#loads==2,'No per-frame texture creation')
art:Destroy();assert(#deleted==2,'Scene teardown releases both textures')
art=require('Game.Views.ArtResources').New(5);loads={}
Visual.Draw(vg,map,{x=0,y=0,w=400,h=400},40,-4000,-4000,2,art)
assert(#loads==1 and loads[1][1]==Config.ArtSlots.tissueBg,'Offscreen flow decals are culled')
''')
print('PASS: real flow/background image resources, oriented segments, wall masking, culling and teardown')
