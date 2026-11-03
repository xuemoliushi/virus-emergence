"""真实CellSurface Lua及离线atlas回归；无原生GPU/时长验收声明。

注入Node/cache/Image验证生命周期；真实PNG/JSON独立验证三层几何和逐像素alpha。
只读取生产资源，报告stdout，不构建、不改写职责外validation文件。
"""
from pathlib import Path
import hashlib, json, sys
sys.path.insert(0, '/home/Maker/.local/swarm-test')
from lua_test_runtime import LuaRuntime
ROOT=Path(__file__).resolve().parents[1]
PRODUCTION=ROOT/'scripts/Game/Views/CellSurface.lua'
SETUP=r'''
package.path=SCRIPT_PATH..';'..package.path
package.loaded['Game.VisualUtils']={}
package.loaded['urhox-libs/UI/Core/ImageCache']={GetContext=function()return nil end}
state={nodes={},images={},jobs={},starts=0,forceReleases=0,submitFails={},submitThrows={},cloneThrows=false,cloneNil=false,callback=nil,callbackNode=nil}
function Node()
 local node={disposed=false}
 state.nodes[#state.nodes+1]=node
 function node:CreateScriptObject(name)
  return {SubscribeToEvent=function(_,event,callback)state.callback=callback;state.callbackNode=node end}
 end
 function node:Dispose()
  assert(not self.disposed,'node double Dispose');self.disposed=true
  if state.callbackNode==self then state.callback=nil;state.callbackNode=nil end
 end
 return node
end
function IntRect(a,b,c,d)return {a,b,c,d}end
function makeImage(width,height)
 local image={width=width or 1024,height=height or 1024,components=4,disposed=false,disposeCount=0}
 state.images[#state.images+1]=image
 function image:GetSubimage(rect)
  assert(not self.disposed,'clone of disposed Image')
  if state.cloneThrows then error('injected clone throw')end
  if state.cloneNil then return nil end
  if rect[1]<0 or rect[2]<0 or rect[3]>self.width or rect[4]>self.height then return nil end
  return makeImage(rect[3]-rect[1],rect[4]-rect[2])
 end
 function image:Dispose()
  self.disposeCount=self.disposeCount+1
  assert(not self.disposed,'image double Dispose');self.disposed=true
 end
 return image
end
Image=makeImage
cache={}
function cache:BackgroundLoadResource(kind,path,fail)
 state.starts=state.starts+1
 if state.submitThrows[path] then error('injected submit throw')end
 if state.submitFails[path] then return false end
 state.jobs[path]=true;return true
end
function cache:GetExistingResource(kind,path)return state.currentImage end
function cache:ReleaseResource(kind,path,force)
 assert(force==true,'must transfer private cache Image with force');state.forceReleases=state.forceReleases+1
end
function emit(path,success,width,height)
 state.currentImage=success and makeImage(width,height)or nil
 state.jobs[path]=nil
 local cb=assert(state.callback,'event subscription unavailable')
 cb(nil,nil,{GetString=function(_,key)assert(key=='ResourceName');return path end,
   GetBool=function(_,key)assert(key=='Success');return success end})
 return state.currentImage
end
function liveNodes()local n=0;for _,v in ipairs(state.nodes)do if not v.disposed then n=n+1 end end;return n end
function liveImages()local n=0;for _,v in ipairs(state.images)do if not v.disposed then n=n+1 end end;return n end
function count(t)local n=0;for _ in pairs(t)do n=n+1 end;return n end
local module=require('Game.Views.CellSurface')
local patch={geometry_version=2,path='image/infection_block_flat.png',canvas=300,anchor={150,150},
 bounds={97,104,203,245},visible_width=106,grown_fraction=.45,cell_foreground_width=807,max_scale=807*.45/106,
 crop={75,100,149},output_pixels=149,source_sha256='test',stack={{scale=.55,rot=0},{scale=.78,rot=25},{scale=1,rot=-20}}}
local data={version=5,canvas=1254,center={627,627},angle_bins=1,placements={{1,0,1,0}},
 union={rows={},width=807},patch=patch}
local meta={canvas=192,center={96,96},outward={1,0},contact={96,96},r_rim=47.5}
local stackMeta={canvas=300,center={150,150},stack=patch.stack}
function deepCopy(t)
 if type(t)~='table'then return t end
 local out={};for k,v in pairs(t)do out[k]=deepCopy(v)end;return out
end
function fixtureOptions()
 local pages={};for i=1,32 do pages[i]='private/page_'..i end
 return {data=deepCopy(data),meta=deepCopy(meta),stackMeta=deepCopy(stackMeta),
 atlas={version=2,encoding='straight-rgba-cropped',page_size=1024,sub_bins=1,
 tile_sizes={glint=192,patch=149},patch=deepCopy(patch),pages=pages,scale=1.6625,glints={{}},patches={{{},{},{}}}}}
end
function newSurface()
 local surface=module.New(fixtureOptions())
 assert(surface.data,'injected production Init failed');return surface
end
function rejectedOptions(options)
 local surface=module.New(options)
 assert(not surface.data and surface.failures.data,'stale/inconsistent atlas must be rejected')
 surface:Destroy();assert(liveImages()==0 and liveNodes()==0)
end
function realSurface(useAtlas)
 local surface=module.New({data=deepCopy(REAL_DATA),meta=deepCopy(REAL_META),patchMeta=deepCopy(REAL_BLOCK_META),
 stackMeta=deepCopy(REAL_STACK_META),atlas=useAtlas and deepCopy(REAL_ATLAS)or nil})
 assert(surface.data,'real resource Init failed');return surface
end
function near(a,b,e)assert(math.abs(a-b)<=(e or 1e-9),tostring(a)..' != '..tostring(b))end
function prepareDraw(surface)
 state.draws={};state.fills=0
 function surface:Texture(nvg,key,width,height,fill,x,y,size,rotation)
  local existing=self.entries[key];if existing then return existing end
  local image={width=width,height=height,pixels={}}
  function image:SetPixelInt(px,py,packed)
   assert(px>=0 and py>=0 and px<self.width and py<self.height,'pixel outside declared output')
   self.pixels[1+py*self.width+px]=packed
  end
  fill(image);state.fills=state.fills+1
  local entry={handle=state.fills,x=x,y=y,size=size,rotation=rotation,pixels=width*height,image=image,key=key}
  self.entries[key]=entry;return entry
 end
 surface.sources.patch={width=300,height=300,pixels=PATCH_PIXELS,nonzero={}}
 function nvgSave()end;function nvgRestore()end;function nvgBeginPath()end;function nvgRect()end
 function nvgTranslate(_,x,y)state.drawX,state.drawY=x,y end
 function nvgRotate(_,r)state.drawRot=r end
 function nvgImagePattern(_,x,y,w,h,rotation,handle,alpha)return {handle=handle,alpha=alpha,w=w,h=h}end
 function nvgFillPaint(_,paint)
  state.draws[#state.draws+1]={handle=paint.handle,alpha=paint.alpha,x=state.drawX,y=state.drawY,rot=state.drawRot,size=paint.w,
   rect=state.drawRect}
 end
 function nvgFill()end
 function nvgRect(_,x,y,w,h)state.drawRect={x=x,y=y,w=w,h=h}end
end
'''
TESTS={
 '旧atlas版本、stack、分辨率、锚点和源指纹必须拒绝':r'''
 for _,mutate in ipairs({
  function(o)o.atlas.version=1 end,
  function(o)o.atlas.patch.stack[2].rot=-25 end,
  function(o)o.atlas.tile_sizes.patch=192 end,
  function(o)o.atlas.patch.crop[1]=75.5 end,
  function(o)o.atlas.patch.anchor[2]=151 end,
  function(o)o.atlas.patch.source_sha256='old-source' end,
  function(o)o.atlas.patches[1]={{}} end,
  function(o)o.data.version=4 end,
  function(o)o.data.patch.max_scale=760*.45/106 end,
  function(o)o.data.patch.stack[3].scale=.99 end,
  function(o)o.stackMeta.stack[2].rot=0 end,
 })do local o=fixtureOptions();mutate(o);rejectedOptions(o)end
 ''',
 '三层任意正progress淡入及回落对称，无CPU重建':r'''
 local s=realSurface(false);prepareDraw(s)
 local pose=assert(s:GetPlacement({rotation=.6},{localAngle=1.1}))
 for _,p in ipairs({0,.00001,.02,1/3-1e-8,1/3,1/3+1e-8,.5,2/3-1e-8,2/3,2/3+1e-8,.8,1,2})do
  state.draws={};local drew=s:DrawPatch({},pose,p,.8,.6)
  local q=math.max(0,math.min(1,p))*3;local j=0
  for i=1,3 do
   local a=math.max(0,math.min(1,q-i+1))
   if a>0 then
    j=j+1;near(state.draws[j].alpha,.8*.6*math.sqrt(a));assert(state.draws[j].handle==i)
    local patch=s.data.patch;local scale=patch.max_scale*patch.stack[i].scale
    local cy=patch.crop[2]+patch.crop[3]*.5
    local front=patch.anchor[2]+(patch.bounds[4]-patch.anchor[2])*math.sqrt(a)
    local height=a<1 and math.max(0,math.min(state.draws[j].size,(front-cy)*scale+state.draws[j].size*.5))
      or state.draws[j].size
    near(state.draws[j].rect.h,height)
    assert(state.draws[j].rect.h<=state.draws[j].size and state.draws[j].rect.h>0)
   end
  end
  assert(#state.draws==j and drew==(j>0))
 end
 assert(state.fills==3 and count(s.entries)==3)
 local established=state.fills
 for k=1,300 do
  for _,p in ipairs({k/300,1-k/300})do
   state.draws={};s:DrawPatch({},pose,p,1,1)
   for _,draw in ipairs(state.draws)do
    local entry=s.entries['p2:'..pose.key..':'..draw.handle]
    near(draw.x,entry.x);near(draw.y,entry.y);near(draw.rot,entry.rotation);near(draw.size,entry.size)
   end
  end
 end
 assert(state.fills==established,'progress must never trigger mask rebuilding')
 state.draws={};assert(not s:DrawPatch({},pose,-1));assert(not s:DrawPatch({},pose,.8,0))
 assert(not s:DrawPatch({},pose,.8,1,0));assert(#state.draws==0)
 s.entries={};s:Destroy()
 ''',
 '1440真实膜点三层crop锚点零偏移和+Y转向':r'''
 local s=realSurface(false);prepareDraw(s)
 -- 只捕获几何，pixel逐点乘union由独立蒙版测试负责。
 function s:Texture(_,key,width,height,fill,x,y,size,rotation)return {x=x,y=y,size=size,rotation=rotation}end
 local patch=s.data.patch;local crop=patch.crop
 for index=1,#s.data.fine_placements do
  local angle=(index-1)*math.pi*2/#s.data.fine_placements
  local pose=assert(s:GetPlacement({rotation=.37},{localAngle=angle}))
  assert(pose.subBin==index)
  for i,layer in ipairs(patch.stack)do
   local entry=assert(s:PatchEntry({},pose,s.sources.patch,i));local scale=patch.max_scale*layer.scale
   local dx,dy=patch.anchor[1]-(crop[1]+crop[3]/2),patch.anchor[2]-(crop[2]+crop[3]/2)
   local co,si=math.cos(entry.rotation),math.sin(entry.rotation)
   near(entry.x+scale*(co*dx-si*dy),pose.membraneX,1e-9)
   near(entry.y+scale*(si*dx+co*dy),pose.membraneY,1e-9)
   local base=entry.rotation-math.rad(layer.rot)
   near(-math.sin(base),-pose.normalX,1e-9);near(math.cos(base),-pose.normalY,1e-9)
   near(entry.size,149*scale);near(106*scale,807*.45*layer.scale)
  end
 end
 s.entries={};s:Destroy()
 ''',
 '真实Lua三层逐像素RGBA精确等于离线atlas':r'''
 local s=realSurface(false);prepareDraw(s)
 for _,index in ipairs({1,181,361,541,721,901,1081,1261,264,568,1224,1440})do
  local pose=assert(s:GetPlacement({},{localAngle=(index-1)*math.pi*2/1440}))
  for i=1,3 do
   local entry=assert(s:PatchEntry({},pose,s.sources.patch,i));local expected=EXPECTED_MASKS[index][i]
   assert(entry.image.width==149 and entry.image.height==149)
   for j=1,149*149 do assert((entry.image.pixels[j]or 0)==expected[j],
     'mask differs from atlas at pose '..index..' layer '..i..' pixel '..j)end
  end
 end
 s.entries={};s:Destroy()
 ''',
 '默认DrawPatch走三层atlas，后台等待后热帧只复用纹理':r'''
 local s=realSurface(true);prepareDraw(s)
 local pose=assert(s:GetPlacement({},{localAngle=0}));assert(s:HasAtlas(pose))
 function s:LoadSource()error('default atlas must not load/scan source image')end
 function s:SampleUnion()error('default atlas must not recompute CPU mask')end
 function s:Bind()return true end
 local page=nil
 function s:AtlasPage()return page end
 --首次页未到齐时只等待，不走CPU重算，也不绘制未经union裁剪的原图。
 state.draws={};assert(not s:DrawPatch({},pose,1));assert(state.fills==0 and #state.draws==0)
 page=makeImage()
 local crops=0
 function s:Texture(_,key,width,height,fill,x,y,size,rotation)
  local entry=self.entries[key];if entry then return entry end
  assert(width==149 and height==149)
  local target={}
  function target:SetSubimage(image,rect)
   assert(not image.disposed and rect[3]<=149 and rect[4]<=149);crops=crops+1;return true
  end
  fill(target);state.fills=state.fills+1
  entry={handle=state.fills,x=x,y=y,size=size,rotation=rotation,pixels=width*height}
  self.entries[key]=entry;return entry
 end
 state.draws={};assert(s:DrawPatch({},pose,1));assert(crops==3 and state.fills==3 and #state.draws==3)
 for k=1,500 do state.draws={};s:DrawPatch({},pose,k/500)end
 assert(crops==3 and state.fills==3 and s.sourceLoads==0 and s.generatedPixels==0)
 page:Dispose();s.entries={};s:Destroy();assert(liveImages()==0)
 ''',
 'BakedTexture按149或300尺寸复原tile，不再硬写192':r'''
 for _,resolution in ipairs({149,300})do
  local s=newSurface();local completed=false
  function s:AtlasPage()return makeImage()end
  function s:Texture(_,key,width,height,fill,x,y,size,rotation)
   assert(width==resolution and height==resolution)
   local target={}
   function target:SetSubimage(crop,rect)
    assert(crop.width==106 and crop.height==141)
    assert(rect[1]==22 and rect[2]==4 and rect[3]==128 and rect[4]==145);return true
   end
   fill(target);completed=true;return {handle=1}
  end
  function s:Bind()return true end
  assert(s:BakedTexture({},'size-test',{1,10,20,106,141,22,4},0,0,10,0,resolution));assert(completed)
  --测试桩AtlasPage的Image不归s持有，显式回收，生命周期仍然要核验。
  for _,image in ipairs(state.images)do if not image.disposed then image:Dispose()end end
  s:Destroy();assert(liveImages()==0)
 end
 ''',
 'submission false cleans event node/pending':r'''
 local s=newSurface();state.submitFails['private/page_1']=true;s:AtlasPage(1)
 assert(state.starts==1 and count(s.atlasPending)==0 and s.failures['atlas:1'])
 assert(liveNodes()==0);s:Destroy();assert(liveImages()==0)
 ''',
 'submission throw cleans phantom pending and event subscription':r'''
 local s=newSurface();state.submitThrows['private/page_1']=true
 local ok=pcall(function()s:AtlasPage(1)end)
 assert(ok,'submit exception escapes original AtlasPage')
 assert(count(s.atlasPending)==0 and s.failures['atlas:1'] and liveNodes()==0,'submit exception leaves phantom job/pending/node')
 s:Destroy()
 ''',
 'duplicate same instance page coalesces one job':r'''
 local s=newSurface();s:AtlasPage(1);s:AtlasPage(1);assert(state.starts==1 and count(s.atlasPending)==1)
 local image=emit('private/page_1',true);assert(s.atlasPages[1].image==image and count(s.atlasPending)==0)
 assert(liveNodes()==0 and state.forceReleases==1);s:Destroy();assert(liveImages()==0)
 ''',
 'two instances same page get independently disposable images':r'''
 local a,b=newSurface(),newSurface();a:AtlasPage(1);b:AtlasPage(1);assert(state.starts==1)
 emit('private/page_1',true);assert(a.atlasPages[1].image~=b.atlasPages[1].image)
 a:Destroy();assert(not b.atlasPages[1].image.disposed);b:Destroy();assert(liveImages()==0 and liveNodes()==0)
 ''',
 'clone throw fails first recipient and transfers original to second':r'''
 local a,b=newSurface(),newSurface();a:AtlasPage(1);b:AtlasPage(1);state.cloneThrows=true
 emit('private/page_1',true);assert(a.failures['atlas:1'] and not a.atlasPages[1] and b.atlasPages[1])
 a:Destroy();b:Destroy();assert(liveImages()==0 and liveNodes()==0)
 ''',
 'clone nil has failure marker and preserves remaining recipient':r'''
 local a,b=newSurface(),newSurface();a:AtlasPage(1);b:AtlasPage(1);state.cloneNil=true
 emit('private/page_1',true);assert(a.failures['atlas:1'] and b.atlasPages[1]);a:Destroy();b:Destroy();assert(liveImages()==0)
 ''',
 'Accept throw disposes untransferred Image and event node':r'''
 local s=newSurface();s:AtlasPage(1);s.AcceptAtlasPage=function()error('injected accept throw')end
 emit('private/page_1',true);assert(s.failures['atlas:1'] and not s.atlasPages[1]);s:Destroy();assert(liveImages()==0 and liveNodes()==0)
 ''',
 'wrong dimensions multiinstance cleanup does not double Dispose':r'''
 local a,b=newSurface(),newSurface();a:AtlasPage(1);b:AtlasPage(1)
 emit('private/page_1',true,512,512)
 assert(a.failures['atlas:1'] and b.failures['atlas:1']);a:Destroy();b:Destroy();assert(liveImages()==0 and liveNodes()==0)
 ''',
 'failure event clears all live pending and event subscription':r'''
 local a,b=newSurface(),newSurface();a:AtlasPage(1);b:AtlasPage(1)
 emit('private/page_1',false);assert(a.failures['atlas:1'] and b.failures['atlas:1'])
 assert(count(a.atlasPending)==0 and count(b.atlasPending)==0 and liveNodes()==0);a:Destroy();b:Destroy()
 ''',
 'Destroy detaches old generation and orphan event disposes result':r'''
 local s=newSurface();s:AtlasPage(1);local generation=s.atlasGeneration;s:Destroy();assert(s.atlasGeneration>generation)
 s:Init(s.options);local newgeneration=s.atlasGeneration
 emit('private/page_1',true);assert(count(s.atlasPages)==0 and s.atlasGeneration==newgeneration)
 assert(liveImages()==0 and liveNodes()==0);s:Destroy()
 ''',
 'same path after reset adopts existing job only for new generation':r'''
 local s=newSurface();s:AtlasPage(1);s:Destroy();s:Init(s.options);s:AtlasPage(1)
 assert(state.starts==1);emit('private/page_1',true);assert(s.atlasPages[1] and count(s.atlasPending)==0)
 s:Destroy();assert(liveImages()==0)
 ''',
 'global orphan outstanding jobs remain capped across resets':r'''
 local s=newSurface();for i=1,8 do s:AtlasPage(i)end;assert(state.starts==8)
 s:Destroy();s:Init(s.options);s:AtlasPage(9);assert(state.starts==8 and not s.atlasPending[9])
 emit('private/page_1',true);s:AtlasPage(9);assert(state.starts==9)
 s:Destroy();for i=2,9 do emit('private/page_'..i,true)end
 assert(liveImages()==0 and liveNodes()==0)
 ''',
 'global jobs shared across multiple instances and local page LRU':r'''
 local a,b=newSurface(),newSurface();for i=1,8 do a:AtlasPage(i)end;b:AtlasPage(9);assert(state.starts==8)
 for i=1,8 do emit('private/page_'..i,true)end;assert(count(a.atlasPages)==8)
 a:AtlasPage(9);assert(count(a.atlasPages)==7 and liveImages()==7);emit('private/page_9',true)
 assert(count(a.atlasPages)==8 and liveImages()==8);a:Destroy();b:Destroy();assert(liveImages()==0 and liveNodes()==0)
 ''',
 'Dispose recipient immediately after page event cannot affect another':r'''
 local a,b=newSurface(),newSurface();a:AtlasPage(1);b:AtlasPage(1);emit('private/page_1',true)
 a:Destroy();assert(b:AtlasPage(1)==b.atlasPages[1].image);b:Destroy();assert(liveImages()==0)
 ''',
}
def resource_regression():
    """独立于生成脚本逐姿态重算，防止生成脚本和Lua共同写错仍误通过。"""
    import math
    import numpy as np
    from PIL import Image as PILImage
    image_dir = ROOT/'assets/image'
    data = json.loads((image_dir/'cell_surface_data.json').read_text(encoding='utf-8'))
    meta = json.loads((image_dir/'virus_attached_meta.json').read_text(encoding='utf-8'))
    block_meta = json.loads((image_dir/'infection_block_meta.json').read_text(encoding='utf-8'))
    stack_meta = json.loads((image_dir/'infection_patch_meta.json').read_text(encoding='utf-8'))
    atlas = json.loads((image_dir/'cell_surface_atlas/manifest.json').read_text(encoding='utf-8'))
    assert (image_dir/'infection_patch_meta.json').read_bytes() == (ROOT/'docs/infection_patch_meta.json').read_bytes()
    patch = data['patch']
    layers = [np.asarray(PILImage.open(image_dir/'bioluminescent'/name).convert('RGBA'))
              for name in ('cell_body.png','cell_vacuole.png','cell_membrane.png')]
    union = 1-np.prod([1-im[:,:,3].astype(np.float64)/255 for im in layers],axis=0)
    union_exact = 255**3-np.prod([255-im[:,:,3].astype(np.int64) for im in layers],axis=0)
    decoded = np.zeros_like(union_exact)
    u = data['union']
    for iy,row in enumerate(u['rows']):
        x = u['x']
        for off in range(0,len(row),10):
            count,value = int(row[off:off+4],16),int(row[off+4:off+10],16)
            decoded[u['y']+iy,x:x+count] = value
            x += count
        assert x == u['x']+u['width']
    assert np.array_equal(decoded,union_exact)
    union = decoded/float(255**3)
    source = np.asarray(PILImage.open(image_dir/'infection_block_flat.png').convert('RGBA'))
    bounds = PILImage.fromarray(source[:,:,3]).getbbox()
    cell_bounds = PILImage.fromarray((union_exact>0).astype(np.uint8)).getbbox()
    cell_width = cell_bounds[2]-cell_bounds[0]
    assert cell_width == patch['cell_foreground_width'] == 807
    assert patch['max_scale'] == cell_width*.45/(bounds[2]-bounds[0])
    assert patch['stack'] == stack_meta['stack'] == [{'scale':.55,'rot':0},{'scale':.78,'rot':25},{'scale':1.,'rot':-20}]
    assert atlas['version']==2 and atlas['patch']=={k:patch[k] for k in atlas['patch']}
    assert atlas['tile_sizes']=={'glint':192,'patch':149} and atlas['sub_bins']==1440
    assert all(name.startswith('image/cell_surface_atlas/stack_v2_page_') for name in atlas['pages'])
    assert all(len(tiles)==3 for tiles in atlas['patches'])
    for item in data['sources']:
        assert hashlib.sha256((ROOT/'assets'/item['path']).read_bytes()).hexdigest()==item['sha256']
    assert hashlib.sha256((image_dir/'infection_block_flat.png').read_bytes()).hexdigest()==patch['source_sha256']
    y,x = np.mgrid[0:149,0:149].astype(np.float64)
    sx,sy = x+patch['crop'][0]+.5,y+patch['crop'][1]+.5
    cropped = source[np.floor(sy).astype(int),np.floor(sx).astype(int)]
    assert np.count_nonzero(cropped[:,:,3])==np.count_nonzero(source[:,:,3])==9618
    assert np.array_equal(np.unique(source[source[:,:,3]>0,:3],axis=0),[[227,104,4]])
    glint = np.asarray(PILImage.open(image_dir/'attachment_glint.png').convert('RGBA'))
    gy,gx = np.mgrid[0:192,0:192].astype(np.float64)

    def sample(px,py):
        px,py = px-.5,py-.5
        ix,iy = np.floor(px).astype(int),np.floor(py).astype(int)
        fx,fy = px-ix,py-iy
        def at(a,b):
            valid=(a>=0)&(b>=0)&(a<1254)&(b<1254)
            return np.where(valid,union[np.clip(b,0,1253),np.clip(a,0,1253)],0)
        return ((at(ix,iy)*(1-fx)+at(ix+1,iy)*fx)*(1-fy)
                +(at(ix,iy+1)*(1-fx)+at(ix+1,iy+1)*fx)*fy)

    pages = {}
    def tile_image(tile,side):
        out=np.zeros((side,side,4),dtype=np.uint8)
        if not tile:return out
        page,px,py,w,h,ox,oy=tile
        assert ox>=0 and oy>=0 and ox+w<=side and oy+h<=side
        assert px>=1 and py>=1 and px+w<1024 and py+h<1024
        if page not in pages:
            # 页LRU只用于测试内存，不改变生产资源。
            if len(pages)>=8:pages.pop(next(iter(pages)))
            pages[page]=np.asarray(PILImage.open(ROOT/'assets'/atlas['pages'][page-1]).convert('RGBA'))
        out[oy:oy+h,ox:ox+w]=pages[page][py:py+h,px:px+w]
        return out

    expected_masks={}
    selected={1,181,361,541,721,901,1081,1261,264,568,1224,1440}
    checked_pixels=outside=partial=0
    for index,(px,py,nx,ny) in enumerate(data['fine_placements'],1):
        if index in selected:expected_masks[index]=[]
        for layer_index,layer in enumerate(patch['stack']):
            rotation=math.atan2(nx,-ny)+math.radians(layer['rot'])
            co,si=math.cos(rotation),math.sin(rotation)
            scale=patch['max_scale']*layer['scale']
            ux=627+px+scale*(co*(sx-150)-si*(sy-150))
            uy=627+py+scale*(si*(sx-150)+co*(sy-150))
            mask=sample(ux,uy)
            expected=cropped.copy()
            expected[:,:,3]=np.floor(cropped[:,:,3]*mask+.5).astype(np.uint8)
            expected[expected[:,:,3]==0]=0
            actual=tile_image(atlas['patches'][index-1][layer_index],149)
            assert np.array_equal(actual,expected),f'pose {index} layer {layer_index+1} RGBA mismatch'
            outside+=int(np.count_nonzero((actual[:,:,3]>0)&(mask==0)))
            partial+=int(np.count_nonzero((mask>0)&(mask<1)&(cropped[:,:,3]>0)))
            checked_pixels+=149*149
            assert np.all(actual[:,:,3]<=cropped[:,:,3])
            if index in selected:
                packed=(actual[:,:,0].astype(np.uint32)|(actual[:,:,1].astype(np.uint32)<<8)
                        |(actual[:,:,2].astype(np.uint32)<<16)|(actual[:,:,3].astype(np.uint32)<<24))
                expected_masks[index].append(packed.ravel().tolist())
        # glint旧公式逐像素保持，粒子变换公式不随patch改动。
        dx,dy=meta['outward'];rotation=math.atan2(dx*(-ny)-dy*(-nx),dx*(-nx)+dy*(-ny))
        co,si=math.cos(rotation),math.sin(rotation)
        distance=(meta['r_rim']-8)*atlas['scale']
        cx,cy=px+nx*distance,py+ny*distance
        ux=627+cx+atlas['scale']*(co*(gx+.5-96)-si*(gy+.5-96))
        uy=627+cy+atlas['scale']*(si*(gx+.5-96)+co*(gy+.5-96))
        expected=glint.copy();expected[:,:,3]=np.floor(glint[:,:,3]*sample(ux,uy)+.5).astype(np.uint8)
        expected[expected[:,:,3]==0]=0
        assert np.array_equal(tile_image(atlas['glints'][index-1],192),expected),f'glint pose {index} changed'
    assert outside==0 and partial>0
    print(f'PASS 4320 patch masks / {checked_pixels} RGBA pixels, 1440 unchanged glints, exact union, outside=0')
    packed_source=(source[:,:,0].astype(np.uint32)|(source[:,:,1].astype(np.uint32)<<8)
                   |(source[:,:,2].astype(np.uint32)<<16)|(source[:,:,3].astype(np.uint32)<<24))
    return {'REAL_DATA':data,'REAL_META':meta,'REAL_BLOCK_META':block_meta,'REAL_STACK_META':stack_meta,
            'REAL_ATLAS':atlas,'PATCH_PIXELS':packed_source.ravel().tolist(),'EXPECTED_MASKS':expected_masks}


if __name__=='__main__':
    before=hashlib.sha256(PRODUCTION.read_bytes()).hexdigest();results=[]
    resources=resource_regression()
    for name,code in TESTS.items():
        lua=LuaRuntime(unpack_returned_tuples=True);lua.globals().SCRIPT_PATH=str(ROOT/'scripts/?.lua')
        try:
            # 只有用到真实资源的case注入大表，生命周期case仍保持小型独立夹具。
            if 'realSurface(' in code:
                for key,value in resources.items():lua.globals()[key]=lua.table_from(value,recursive=True)
            lua.execute(SETUP);lua.execute(code);results.append({'name':name,'passed':True});print('PASS',name)
        except Exception as e:results.append({'name':name,'passed':False,'error':str(e)});print('FAIL',name,str(e))
    after=hashlib.sha256(PRODUCTION.read_bytes()).hexdigest()
    result={'scope':'real source/atlas pixel math and Lua mocks; not native GPU/speed evidence','tests':results,
            'productionBefore':before,'productionAfter':after,'productionUnchanged':before==after,
            'passed':all(r['passed'] for r in results)}
    print(json.dumps(result,ensure_ascii=False))
    print(f"{sum(r['passed'] for r in results)}/{len(results)} passed; production unchanged={before==after}")
    raise SystemExit(0 if result['passed'] and before==after else 1)
