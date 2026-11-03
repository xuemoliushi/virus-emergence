"""实际引擎画面与资源协议回归，不把draw-call测试冒充视觉验收。"""
from pathlib import Path
import sys
sys.path.insert(0, '/home/Maker/.local/swarm-test')
from lua_test_runtime import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
SETUP = r'''
package.path=SCRIPT_PATH..';'..package.path
calls={}; imagePaths={}; imageIds={}
local cache={}
function cache.Get(path)
 if not imageIds[path] then imagePaths[#imagePaths+1]=path;imageIds[path]=#imagePaths end
 calls[#calls+1]={'image',path};return imageIds[path]
end
function cache.GetSize() return 1254,1254 end
package.loaded['urhox-libs/UI/Core/ImageCache']=cache
package.loaded['urhox-libs/UI/Core/Theme']={FontFace=function() return 'sans' end,FontSize=function(v)return v end,
 GetScale=function()return uiScale or 1 end}
for _,name in ipairs({'nvgSave','nvgRestore','nvgTranslate','nvgRotate','nvgScale','nvgBeginPath','nvgCircle',
'nvgEllipse','nvgFill','nvgStroke','nvgStrokeColor','nvgStrokeWidth','nvgFillColor','nvgMoveTo',
'nvgLineTo','nvgQuadTo','nvgClosePath','nvgArc','nvgRect','nvgFillPaint','nvgImagePattern','nvgImagePatternTinted',
'nvgRGBA','nvgText','nvgFontSize','nvgTextAlign','nvgFontFace','nvgIntersectScissor','nvgShapeAntiAlias'}) do
 _G[name]=function(...) local a={name,...};calls[#calls+1]=a;return a end
end
NVG_CW=1;NVG_ALIGN_CENTER=1;NVG_ALIGN_MIDDLE=2
local surface={}
function surface.New()return setmetatable({},{__index=surface})end
function surface.Destroy()end
function surface.BeginFrame()end
function surface.GetData()return {visible_particle_pixels=96}end
function surface.GetPlacement(self,cell,contact,scale)return {x=10,y=10,spriteX=20,spriteY=20,rotation=0,
 normalX=math.cos(contact.angle),normalY=math.sin(contact.angle),angle=contact.angle,scale=scale,size=192*(scale or 1)}end
function surface.DrawGlint(self,nvg,pose,alpha)calls[#calls+1]={'glint',pose.angle,alpha};return true end
function surface.DrawParticle(self,nvg,pose,alpha)calls[#calls+1]={'attached',pose.angle,alpha,pose.scale};return true end
function surface.DrawPatch(self,nvg,pose,progress,alpha,activity)calls[#calls+1]={'patch',pose.angle,progress,alpha,activity}end
package.loaded['Game.Views.CellSurface']=surface
local latent={}
function latent.New()return setmetatable({},{__index=latent})end
function latent.Destroy()end
function latent.Draw(self,nvg,cell,time,alpha)
 if cell.state=='LATENT' or cell.state=='PRODUCTIVE' then calls[#calls+1]={'latent',time,alpha} end
end
package.loaded['Game.Views.LatentParticles']=latent
Config=require('Core.Config');View=require('Game.Views.CellView')
function cell()
 return {id=1,x=0,y=0,radius=.4,rotation=.3,phase=.1,state='EXPOSED',exposure=.7,infectedAge=0,
  contactVisuals={{normalX=-1,normalY=0,lastSeen=10,strength=1,visualCellRotation=.3},
   {normalX=0,normalY=1,lastSeen=10,strength=.3,visualCellRotation=.3}},
  contactVisualAnchor={normalX=-1,normalY=0,visualCellRotation=.3}}
end
function recorded(name)local out={};for _,c in ipairs(calls)do if c[1]==name then out[#out+1]=c end end;return out end
'''
TESTS = {
 '释放表现资源并清空旧世界和流动装饰': r'''
  local v=View.New();local old={cells={}}
  v.visualWorld=old;v.flowAnimation[1]={time=3,phase=.2}
  local surfaces,particles=0,0
  v.surface.Destroy=function()surfaces=surfaces+1 end
  v.latentParticles.Destroy=function()particles=particles+1 end
  v:Destroy()
  assert(surfaces==1 and particles==1 and v.visualWorld==nil and not next(v.flowAnimation))
  assert(old.cells and #old.cells==0,'释放表现不修改旧模拟世界')
 ''',
 '缺失世界地图或零尺寸也先释放旧世界': r'''
  local v=View.New();local count=0
  v.surface.Destroy=function()count=count+1 end
  v.latentParticles.Destroy=function()count=count+1 end
  v.visualWorld={map={}};v:DrawWorld({},0,0,700,500,{sim={}})
  assert(count==2 and v.visualWorld==nil)
  local replacement={};v.visualWorld={map={}}
  v:DrawWorld({},0,0,0,0,{sim={world=replacement}})
  assert(count==4 and v.visualWorld==replacement)
  v:DrawWorld({},0,0,700,500,{sim={world=replacement}})
  assert(count==4,'同一世界不重复释放')
 ''',
 '三层共享1254画布且不加载旧完整图': r'''
  local v=View.New();v:DrawCell({},250,320,60,cell(),10)
  local images=recorded('image')
  assert(images[1][2]==Config.ArtSlots.cellBody and images[2][2]==Config.ArtSlots.cellMembrane)
  assert(images[3][2]==Config.ArtSlots.cellVacuole)
  local bodyIndex,membraneIndex,patchIndex,vacuoleIndex
  for i,call in ipairs(calls)do
   if call[1]=='image' and call[2]==Config.ArtSlots.cellBody then bodyIndex=i
   elseif call[1]=='image' and call[2]==Config.ArtSlots.cellMembrane then membraneIndex=i
   elseif call[1]=='patch'then patchIndex=i
   elseif call[1]=='image' and call[2]==Config.ArtSlots.cellVacuole then vacuoleIndex=i end
  end
  assert(bodyIndex<membraneIndex and membraneIndex<vacuoleIndex and vacuoleIndex<patchIndex,
      '交付顺序为细胞本体、膜、原液泡、内部颗粒、局部色块')
  for _,c in ipairs(images)do assert(c[2]~=Config.ArtSlots.cellInfected)end
  assert(Config.Palette.cellMembrane[1]>Config.Palette.cellMembrane[2])
 ''',
 '多个接触先画全部glint再画本体': r'''
  View.New():DrawCell({},0,0,50,cell(),10)
  local lastGlint,firstParticle=0,math.huge
  for i,c in ipairs(calls)do if c[1]=='glint'then lastGlint=i elseif c[1]=='attached'then firstParticle=math.min(i,firstParticle)end end
  assert(lastGlint>0 and firstParticle>lastGlint)
 ''',
 '色斑服从权威进度回落且不写cell': r'''
  local v=View.New();local c=cell();v:DrawCell({},0,0,50,c,10);local high=recorded('patch')[1]
  local function assertPatchOverMembrane()
   local mi,pi
   for i,call in ipairs(calls)do
    if call[1]=='image' and call[2]==Config.ArtSlots.cellMembrane then mi=i
    elseif call[1]=='patch'then pi=i end
   end
   assert(pi and mi and pi>mi,'感染区域必须绘在膜上方')
  end
  assertPatchOverMembrane()
  assert(c.exposure==.7 and c.state=='EXPOSED')
  calls={};c.exposure=.2;v:DrawCell({},0,0,50,c,10);local low=recorded('patch')[1]
  assertPatchOverMembrane()
  assert(low[3]==.2 and low[4]==high[4], '进度由各层生长管理，不再重复压暗')
  calls={};c.exposure=0;c.state='HEALTHY';v:DrawCell({},0,0,50,c,10);assert(#recorded('patch')==0)
  calls={};c=cell();c.exposure=1;v:DrawCell({},0,0,50,c,10);local before=recorded('patch')[1]
  calls={};c.state='LATENT';c.infectedVisualAt=10;v:DrawCell({},0,0,50,c,10);local after=recorded('patch')[1]
  assert(math.abs(before[4]*before[5]-after[4]*after[5])<1e-8)
  c.state='LATENT';c.exposure=0;calls={};v:DrawCell({},0,0,50,c,10)
  assert(recorded('patch')[1][3]==1,'感染后不可因状态进度字段短暂清零而丢失色斑')
  c.state='PRODUCTIVE';calls={};v:DrawCell({},0,0,50,c,10)
  assert(recorded('patch')[1][3]==1,'潜伏进入产毒时继续保持完整色斑')
  c.state='EXHAUSTED';calls={};v:DrawCell({},0,0,50,c,10)
  assert(recorded('patch')[1][3]==1,'耗竭前仍保留感染斑')
 ''',
 '接触未结算贡献立即显示色斑但不改环或状态': r'''
  local v=View.New();local c=cell();c.state='HEALTHY';c.exposure=0;c._charge=.004
  v:DrawCell({},0,0,50,c,10)
  assert(recorded('patch')[1][3]==.004 and #recorded('nvgArc')==0)
  assert(c.exposure==0 and c._charge==.004 and c.state=='HEALTHY')
  calls={};c.exposure=.3;c._charge=-.005;v:DrawCell({},0,0,50,c,10)
  assert(recorded('patch')[1][3]==.295 and c.exposure==.3 and c._charge==-.005)
 ''',
 '潜伏首帧保留圈与局部色斑而后附着淡出': r'''
  local v=View.New();local c=cell();c.state='LATENT';c.exposure=1;c.infectedVisualAt=10
  v:DrawCell({},0,0,50,c,10);assert(#recorded('nvgArc')>0 and #recorded('patch')==1 and #recorded('attached')==2)
  calls={};v:DrawCell({},0,0,50,c,11);assert(#recorded('attached')==0 and #recorded('patch')==1)
 ''',
 '细胞旋转后保留接触局部锚点': r'''
  local v=View.New();local c=cell();c.rotation=1.1;v:DrawCell({},0,0,50,c,10)
  local p=recorded('patch')[1];assert(math.abs(p[2]-(math.pi+.8))<1e-8)
 ''',
 '产毒无真实释放不绘制膜芽': r'''
  local v=View.New();local c=cell();c.state='PRODUCTIVE';c.exposure=1;c.productiveTimer=17.9;c.releaseCount=3
  v:DrawCell({},0,0,50,c,10);assert(#recorded('attached')==0 and #recorded('nvgArc')==0)
  calls={};c.lastReleaseVisualAt=9.8;c.releaseVisualDirections={{normalX=1,normalY=0,visualCellRotation=.3}}
  v:DrawCell({},0,0,50,c,10);assert(#recorded('nvgArc')==0,'不能仅凭出生方向虚构不存在的实体')
 ''',
 '液泡始终使用白色调制且无感染状态染色': r'''
  local v=View.New()
  assert(Config.ArtSlots.cellVacuoleTint==nil)
  for _,state in ipairs({'HEALTHY','EXPOSED','LATENT','PRODUCTIVE','EXHAUSTED'})do
   calls={};local c=cell();c.state=state;c.exposure=state=='HEALTHY' and 0 or 1
   v:DrawCell({},0,0,50,c,10)
   local found=false
   for _,p in ipairs(recorded('nvgImagePatternTinted'))do
    if imagePaths[p[8]]==Config.ArtSlots.cellVacuole then
     local color=p[9];assert(color[1]=='nvgRGBA' and color[2]==255 and color[3]==255 and color[4]==255 and color[5]==255)
     found=true
    end
   end
   assert(found,state..'液泡未显式设置白色调制')
  end
 ''',
 '真实释放的膜芽随细胞旋转而保持局部锚点': r'''
  local World=require('Core.SwarmWorld')
  local world=World.New('UPPER_AIRWAY');local c=world.cells[55]
  c.rotation=.3;c.state='PRODUCTIVE';world.time=10;world:_Release(c,6)
  local manifest={pages={'atlas-test'},poses={{rect={-20,-20,40,40},frames={},centres={}}},tile_size=256,page_size=1024}
  for i=1,6 do manifest.poses[1].frames[i]={1,0,0};manifest.poses[1].centres[i]={20,0} end
  nvgCreateImage=function()return 900 end;nvgImageSize=function()return 1024,1024 end;nvgDeleteImage=function()end
  local v=View.New();v.budding=require('Game.Views.BuddingVisual').New({manifest=manifest})
  v.budding:Prepare(world);local handled={};v:DrawCell({},0,0,50,c,10,nil,handled)
  local before=recorded('nvgRotate');assert(next(handled) and #before>0)
  local x,y=world.releasedViruses[1].x,world.releasedViruses[1].y
  local count,rng=#world.releasedViruses,world._rng
  calls={};c.rotation=c.rotation+.8;v.budding:Prepare(world);v:DrawCell({},0,0,50,c,10,nil,{})
  local after=recorded('nvgRotate');assert(math.abs(after[1][3]-before[1][3]-.8)<1e-10)
  assert(world.releasedViruses[1].x==x and world.releasedViruses[1].y==y)
  assert(#world.releasedViruses==count and world._rng==rng)
 ''',
 'Released附着成功后不双画且失败时保留真实原位图': r'''
  local v=View.New();v:SetCamera({x=0,y=0});v:SetViewport({x=0,y=0,w=700,h=500})
  v.DrawEnvironment=function()end;v.DrawImmuneWarning=function()end;v.DrawSwarm=function()end
  local c=cell();c.contactVisuals={{normalX=1,normalY=0,lastSeen=10,strength=.1,
   visualCellRotation=.3,sourceType='RELEASED_VIRUS',sourceId=7}}
  local virus={id=7,x=.3,y=0,radius=.045,state='INFECTING'}
  local world={map={},time=10,cells={c},releasedViruses={virus},immunes={},swarms={},viruses={},effects={}}
  local raw=0;v.DrawVirus=function()raw=raw+1 end
  v:DrawWorld({},0,0,700,500,{sim={world=world},zoom=1})
  assert(raw==0 and #recorded('attached')==1 and world.releasedViruses[1]==virus)
  v.surface.DrawParticle=function()return false end
  v:DrawWorld({},0,0,700,500,{sim={world=world},zoom=1});assert(raw==1)
 ''',
 '全部病程保留红膜且只由真实锚点局部感染': r'''
  local v=View.New();local c=cell();c.exposure=1;c.infectedVisualAt=10
  for _,state in ipairs({'HEALTHY','EXPOSED','LATENT','PRODUCTIVE','EXHAUSTED'})do
   calls={};c.state=state
   local expectedExposure=(state=='HEALTHY' or state=='EXPOSED') and 1 or 0
   c.exposure=expectedExposure
   v:DrawCell({},0,0,50,c,12)
   local membrane=false
   for _,entry in ipairs(recorded('image'))do
    assert(entry[2]~=Config.ArtSlots.cellInfectedLayer,'禁止整胞感染黄层')
    if entry[2]==Config.ArtSlots.cellMembrane then membrane=true end
   end
   assert(membrane and #recorded('patch')==1)
   assert(#recorded('latent')==((state=='LATENT' or state=='PRODUCTIVE') and 1 or 0))
   assert(c.exposure==expectedExposure and c.state==state and c.infectedVisualAt==10)
  end
  c=cell();c.id=2;c.state='LATENT';c.contactVisuals={};c.contactVisualAnchor=nil
  calls={};v:DrawCell({},0,0,50,c,12)
  assert(#recorded('latent')==1 and #recorded('patch')==0,'初始潜伏节点不伪造附着点')
 ''',
 '潜伏颗粒处于液泡之上且色块亮点病毒之下': r'''
  local v=View.New();local c=cell();c.state='LATENT';c.exposure=1;c.infectedVisualAt=10
  v:DrawCell({},0,0,50,c,10)
  local vacuole,latent,patch,glint,particle
  for i,call in ipairs(calls)do
   if call[1]=='image' and call[2]==Config.ArtSlots.cellVacuole then vacuole=i
   elseif call[1]=='latent' then latent=i
   elseif call[1]=='patch' then patch=i
   elseif call[1]=='glint' then glint=i
   elseif call[1]=='attached' and not particle then particle=i end
  end
  assert(vacuole<latent and latent<patch and patch<glint and glint<particle)
  assert(#recorded('nvgClosePath')==0,'潜伏仅用交付内部颗粒，不加中央菱形活动')
 ''',
 '环形进度条增大并包围真实膜且仍只读进度': r'''
  local v=View.New();local c=cell()
  for _,r in ipairs({16,50,100})do
   calls={};v:DrawCell({},0,0,r,c,10)
   local arc=recorded('nvgArc')[1]
   local radius=arc[5]
   assert(radius==math.max(r*Config.CellVisual.infectionRingRadiusMul,r+Config.CellVisual.infectionRingPadding))
   assert(radius>r+3.5 and radius>r*1.271)
   assert(math.abs(arc[7]-arc[6]-.7*math.pi*2)<1e-12)
   local wide=false
   for _,call in ipairs(recorded('nvgStrokeWidth'))do if call[3]>=3.2 then wide=true end end
   assert(wide and c.exposure==.7 and c.radius==.4)
  end
 ''',
 '实际draw诊断仅在附着绘制成功后记录姿态': r'''
  local Diagnostics=require('Core.CellDiagnostics')
  local v=View.New();local c=cell()
  c.contactVisuals={c.contactVisuals[1]}
  c.contactVisuals[1].sourceType='PLAYER_SWARM';c.contactVisuals[1].sourceId=1
  c.contactVisuals[1].key='1:PLAYER_SWARM:1';c.contactVisualAnchor=c.contactVisuals[1]
  local world={cells={c}};local rows={};v.visualWorld=world
  Diagnostics.Configure(world,{drawSink=function(row)rows[#rows+1]=row end})
  v:DrawCell({},0,0,50,c,10)
  assert(#rows==1 and rows[1].drawn and rows[1].drawPosition and rows[1].sourceId==1)
  rows={};v.surface.DrawParticle=function()return false end
  v:DrawCell({},0,0,50,c,10)
  assert(#rows==1 and not rows[1].drawn and not rows[1].drawPosition and not rows[1].drawAngle)
 ''',
 '异步亮斑蒙版未就绪时仍保留固定病毒本体': r'''
  local v=View.New();local c=cell();local attached={}
  c.contactVisuals={c.contactVisuals[1]};c.contactVisuals[1].sourceType='RELEASED_VIRUS';c.contactVisuals[1].sourceId=7
  v.surface.DrawGlint=function()return false end
  v:DrawCell({},0,0,50,c,10,attached)
  assert(#recorded('attached')==1 and attached[7])
  assert(c.exposure==.7 and c.state=='EXPOSED')
 ''',
 '新多群编号与真实合并对绘制不写权威状态': r'''
  local v=View.New();v:SetCamera({x=0,y=0});v:SetViewport({x=0,y=0,w=700,h=500})
  v.DrawEnvironment=function()end;v.DrawImmuneWarning=function()end
  local a={id=11,x=-.5,y=0,radius=.2,mass=8,isMainSwarm=true,isPlayerControlled=false}
  local b={id=14,x=.5,y=0,radius=.2,mass=7,isMainSwarm=false,isPlayerControlled=true}
  local c={id=19,x=0,y=1,radius=.2,mass=6,isMainSwarm=false,isPlayerControlled=false}
  local world={map={},time=10,cells={},releasedViruses={},immunes={},swarms={a,b,c},viruses={},effects={},
   mergeReady=true,mergePairs={{aId=11,bId=14},{aId=14,bId=19},{aId=11,bId=999}}}
  v:DrawWorld({},0,0,700,500,{sim={world=world},zoom=1})
  local texts=recorded('nvgText');local labels,merges={},0
  for _,call in ipairs(texts)do
   labels[call[5]]=true
   if call[5]=='靠近合并'then merges=merges+1 end
  end
  assert(labels['主群 #11'] and labels['分群 #14'] and labels['分群 #19'])
  assert(merges==4,'两组真实合并对各绘阴影与正文，失效ID不得绘制')
  assert(#world.swarms==3 and #world.mergePairs==3 and a.mass==8 and b.mass==7 and c.mass==6)
 ''',
 '自主群状态标签只读且受控群不显示旧AI状态': r'''
  local v=View.New();local l={x=0,y=0,w=700,h=500}
  local s={id=12,x=2,y=2,radius=.2,mass=48,isMainSwarm=false,isPlayerControlled=false,aiState='flee'}
  v:DrawSwarm({},s,l,20,0,0)
  assert(recorded('nvgText')[1][5]=='分群 #12 · 避敌')
  calls={};s.aiState='infect';v:DrawSwarm({},s,l,20,0,0)
  assert(recorded('nvgText')[1][5]=='分群 #12 · 感染')
  calls={};s.isPlayerControlled=true;v:DrawSwarm({},s,l,20,0,0)
  assert(recorded('nvgText')[1][5]=='分群 #12')
  assert(s.aiState=='infect' and s.mass==48 and s.id==12,'视觉不可改AI或质量')
 ''',
 '新主动吸附反馈为向内收缩纯视觉脉冲': r'''
  local v=View.New();local e={kind='absorb',age=0,duration=.8,radius=2.3}
  v:DrawEffect({},100,200,80,e)
  local first=recorded('nvgCircle')[1];assert(first and first[5]==80)
  calls={};e.age=.4;v:DrawEffect({},100,200,80,e)
  local second=recorded('nvgCircle')[1];assert(second and second[5]>0 and second[5]<first[5])
  assert(e.age==.4 and e.radius==2.3 and e.kind=='absorb')
  calls={};e.age=.8;v:DrawEffect({},100,200,80,e);assert(#calls==0)
 ''',
 '默认视距颗粒不被缩成亚像素且缩放整体一致': r'''
  local v=View.New()
  for _,scale in ipairs({.66,1,2,3})do
   uiScale=scale
   graphics={GetDPR=function()return 2 end}
   for _,short in ipairs({360,390,720,1000})do
    local l={x=0,y=0,w=short*2,h=short}
    local ppm=v:CameraTransform(l,1)
    local logicalPPM=ppm*scale/2
    assert(logicalPPM>=128-1e-8 and 32*(2*.34*logicalPPM/760)>3.6)
    assert(v:CameraTransform(l,2)==ppm*2)
   end
  end
 ''',
 '摄像机移动缩放转换互逆': r'''
  local v=View.New();v:SetCamera({x=8,y=24});v:SetViewport({x=70,y=110,w=700,h=400})
  local l={x=10,y=20,w=900,h=700}
  for _,z in ipairs({1,1.7,3})do local x,y=v:WorldToScreen(8.4,23.7,l,z);local a,b=v:ScreenToWorld(x,y,l,z)
   assert(math.abs(a-8.4)<1e-8 and math.abs(b-23.7)<1e-8)end
 ''',
}
if __name__ == '__main__':
 failed=0
 for name,code in TESTS.items():
  lua=LuaRuntime(unpack_returned_tuples=True);lua.globals().SCRIPT_PATH=str(ROOT/'scripts'/'?.lua')
  try: lua.execute(SETUP);lua.execute(code);print('PASS',name)
  except Exception as e: failed+=1;print('FAIL',name,str(e))
 print(f'{len(TESTS)-failed}/{len(TESTS)} 通过；仅协议/draw-call回归，真实像素另行截图。')
 raise SystemExit(bool(failed))
