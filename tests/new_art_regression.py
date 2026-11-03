"""Current art integration protocols, real pixels and complete birth trajectories."""
from pathlib import Path
import hashlib
import json
import os
import sys

import numpy as np
from PIL import Image

from lua_test_runtime import LuaRuntime
import cell_render_regression as render

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT/'assets/image/bioluminescent/budding_manifest.json').read_text(encoding='utf-8'))

SETUP = r'''
Art=require('Game.Views.ArtResources');Budding=require('Game.Views.BuddingVisual')
nvgCreateImage=function(_,path,flags)
 calls[#calls+1]={'create',path,flags}
 if missingImages then return -1 end
 return 1000+#calls
end
nvgImageSize=function()return 1024,1024 end
nvgDeleteImage=function(_,id)calls[#calls+1]={'delete',id}end
nvgPathWinding=function(...)calls[#calls+1]={'winding',...}end
NVG_SOLID=1;NVG_IMAGE_NEAREST=32;NVG_IMAGE_REPEATX=2;NVG_IMAGE_REPEATY=4
function fixture()
 local w=require('Core.SwarmWorld').New('UPPER_AIRWAY')
 local c=w.cells[55];c.state='PRODUCTIVE';c.rotation=.3;w.time=10;w:_Release(c,6)
 local b=Budding.New({manifest=ART_META});b:Prepare(w)
 return w,c,b
end
function quietView(b)
 local v=View.New();v.budding=b
 v.DrawEnvironment=function()end;v.DrawImmuneWarning=function()end;v.DrawSwarm=function()end
 v.DrawImmune=function()end;v.DrawEffect=function()end
 return v
end
function freeze(value)
 if type(value)~='table' then return tostring(value) end
 local keys={};for k,v in pairs(value)do if type(v)~='function'then keys[#keys+1]=k end end
 table.sort(keys,function(a,b)return tostring(a)<tostring(b)end)
 local fields={};for _,k in ipairs(keys)do fields[#fields+1]=tostring(k)..'='..freeze(value[k])end
 return '{'..table.concat(fields,',')..'}'
end
'''

TESTS = {
 '旋转细胞保留完整膜且用新病毒沿出芽轨迹绘制': r'''
  local w,c,b=fixture();local v=quietView(b);v.visualWorld=w
  local nvg={};b:Prepare(w);calls={}
  v:DrawCell(nvg,200,200,60,c,10,nil,{},128)
  assert(#recorded('nvgIntersectScissor')==0,'局部替换不能使用会扩张旋转矩形的scissor')
  assert(#recorded('nvgShapeAntiAlias')>0,'分块边缘不应额外叠加抗锯齿透明缝')
  local births=0
  for _,call in ipairs(recorded('image'))do
   assert(not call[2]:find('image/integrated/',1,true))
   if call[2]==Config.ArtSlots.virusParticle[3] then births=births+1 end
  end
  assert(births>0 and #recorded('image')>3)
 ''',
 '真实释放六阶段随世界时间播放且暂停不推进': r'''
  local w,c,b=fixture();assert(#b.records[c.id]>0 and #b.records[c.id]<=3)
  local count=#b.records[c.id][1].pose.frames
  for frame=1,count do
   w.time=10+(frame-.5)*.8/count;b:Prepare(w)
   assert(b.records[c.id][1].frame==frame)
   b:Prepare(w);assert(b.records[c.id][1].frame==frame)
  end
  w.time=10.921;b:Prepare(w);assert(not b.records[c.id] and not b.batches[c.id])
 ''',
 '代绘只隐藏成功绘出的真实出生其余实体正常绘制': r'''
  local w,c,b=fixture();local v=quietView(b);v.visualWorld=w;v:SetCamera(c)
  local ids={};v.DrawVirus=function(_,_,_,_,_,virus)ids[virus.id]=(ids[virus.id]or 0)+1 end
  v:DrawWorld({},0,0,900,700,{sim={world=w}})
  local selected=#b.records[c.id];assert(selected>0)
  for _,rec in ipairs(b.records[c.id])do assert(rec.shown and not ids[rec.virus.id])end
  assert(#w.releasedViruses==6 and w.stats.totalReleased==6)
 ''',
 '缺图不挖空细胞也不隐藏实际病毒': r'''
  local w,c,b=fixture();missingImages=true;local ready=b:Ready({},c)
  assert(#ready==0)
  local handled={};b:DrawPatches({},ready,.96,handled);assert(not next(handled))
  w.time=10.85;b:Prepare(w);local draws=0
  b:DrawHandoffs({},c,0,0,.1,w.time,100,function()draws=draws+1 end,handled)
  assert(draws==0 and not next(handled),'没有成功显示的动画不能突然开始衔接')
 ''',
 '吸收清除丢失感染吸附全部立即结束且不会重新加入': r'''
  for _,state in ipairs({'ABSORBED','CLEARED','LOST','INFECTING','ATTRACTED'})do
   local w,c,b=fixture();local rec=b.records[c.id][1];local id=rec.virus.id
   rec.virus.state=state;b:Prepare(w)
   for _,r in ipairs(b.records[c.id])do assert(r.virus.id~=id)end
   rec.virus.state='RELEASED';b:Prepare(w)
   for _,r in ipairs(b.records[c.id])do assert(r.virus.id~=id)end
  end
 ''',
 '死亡重开和新批次不会复用旧出生标记': r'''
  local w,c,b=fixture();local first=b.records[c.id][1].key
  w:_Release(c,6);b:Prepare(w);assert(b.records[c.id][1].key~=first)
  c.state='DEAD';b:Prepare(w);assert(not b.records[c.id])
  b:Destroy();assert(not b.world and not next(b.records) and not next(b.batches))
  local replacement=require('Core.SwarmWorld').New('UPPER_AIRWAY');b:Prepare(replacement)
  assert(b.world==replacement and not next(b.records))
 ''',
 '衔接保持真实位置并在0.12秒内逼近当前位置': r'''
  local w,c,b=fixture();local rec=b.records[c.id][1];rec.shown=true
  w.time=10.919;b:Prepare(w);local out={}
  b:DrawHandoffs({},c,200,300,.2,w.time,160,function(_,x,y,r,virus)out[virus.id]={x,y,r}end,{})
  local result=out[rec.virus.id];assert(result)
  assert(math.abs(result[1]-(200+(rec.virus.x-c.x)*160))<.03)
  assert(math.abs(result[2]-(300+(rec.virus.y-c.y)*160))<.03)
  assert(math.abs(result[3]-rec.virus.radius*160)<.01)
 ''',
 '绘制全病程和出芽不会写模拟数据或RNG': r'''
  local w,c,b=fixture();local v=quietView(b);v.visualWorld=w
  local nvg={};local before=freeze(w)
  v:DrawWorld(nvg,0,0,900,700,{sim={world=w}});assert(freeze(w)==before)
  for _,state in ipairs({'HEALTHY','EXPOSED','LATENT','PRODUCTIVE','EXHAUSTED','DEAD'})do
   c.state=state;c.deathVisualAt=10;c.exhaustionTimer=20
   before=freeze(w);v:DrawCell(nvg,200,200,60,c,10.2,nil,{},128);assert(freeze(w)==before)
  end
 ''',
 '耗竭不整体染色且死亡采用新覆盖层': r'''
  local v=View.New();local c=cell();c.state='EXHAUSTED';c.exhaustionTimer=20
  v:DrawCell({},0,0,50,c,10)
  local exhaustion=false
  for _,call in ipairs(recorded('image'))do if call[2]==Config.ArtSlots.cellExhaustion then exhaustion=true end end
  assert(exhaustion)
  for _,paint in ipairs(recorded('nvgImagePatternTinted'))do
   assert(imagePaths[paint[8]]==Config.ArtSlots.cellVacuole,'旧整体染色应移除')
  end
  calls={};c.state='DEAD';c.deathVisualAt=10;v:DrawCell({},0,0,50,c,10.35)
  local death=false
  for _,call in ipairs(recorded('image'))do
   assert(call[2]~=Config.ArtSlots.cellDamaged)
   if call[2]==Config.ArtSlots.cellDeath then death=true end
  end
  assert(death and #recorded('latent')==0 and #recorded('attached')==0)
 ''',
 '病毒尺寸选档与白色免疫母版有效范围匹配': r'''
  local v=View.New();local virus={phase=0,variant=4,radius=.045,state='DRIFTING'}
  for _,pair in ipairs({{5,1},{20,2},{60,3},{130,4}})do
   calls={};v:DrawVirus({},0,0,pair[1],virus,10,128,false,false)
   assert(recorded('image')[1][2]==Config.ArtSlots.virusParticle[pair[2]])
  end
  calls={};v:DrawImmune({},0,0,40,{kind='macrophage'},10)
  assert(recorded('image')[1][2]==Config.ArtSlots.macrophage[1])
  local color=recorded('nvgImagePatternTinted')[1][9]
  assert(color[2]==255 and color[3]==255 and color[4]==255)
  calls={};v:DrawImmune({},0,0,40,{kind='tcell'},10)
  assert(recorded('image')[1][2]==Config.ArtSlots.tCell[1])
 ''',
 '纹理缓存有界并释放所有自持句柄': r'''
  local art=Art.New(3);local nvg={}
  for i=1,9 do assert(art:Get(nvg,'test-'..i))end
  local count=0;for _ in pairs(art.images)do count=count+1 end;assert(count==3)
  assert(#recorded('delete')==6);art:Destroy();assert(#recorded('delete')==9)
 ''',
 '免疫外观覆盖所有新图且不同状态缩放时间不会换形': r'''
  local v=View.New()
  for _,kind in ipairs({'macrophage','tcell'})do
   local slots=kind=='macrophage' and Config.ArtSlots.macrophage or Config.ArtSlots.tCell
   assert(#slots==(kind=='macrophage' and 1 or 2))
   for i,path in ipairs(slots)do
    local immune={id=7,kind=kind,phase=(i-.5)*math.pi*2/#slots,variant=1,state='patrol'}
    local before=freeze(immune)
    for _,state in ipairs({'patrol','warning','chase','attack','cooldown'})do
     immune.state=state
     for _,radius in ipairs({20,40,80})do
      calls={};v:DrawImmune({},123,234,radius,immune,100*radius)
      assert(recorded('image')[1][2]==path,'不能随状态、镜头或时间换形')
     end
    end
    immune.state='patrol';assert(freeze(immune)==before)
   end
  end
 ''',
 '免疫新图有效前景尺寸读取逐图比例并保留原色': r'''
  local v=View.New()
  local cache=package.loaded['urhox-libs/UI/Core/ImageCache']
  for path,meta in pairs(IMMUNE_META)do
   cache.GetSize=function()return meta.canvas[1],meta.canvas[2]end
   assert(math.abs(Config.CellVisual.immuneFillByPath[path]-meta.fill)<1e-12)
   local macro=path:find('macrophage',1,true)~=nil
   local slots=macro and Config.ArtSlots.macrophage or Config.ArtSlots.tCell
   local index;for i,p in ipairs(slots)do if p==path then index=i end end
   local immune={kind=macro and 'macrophage' or 'tcell',phase=(index-.5)*math.pi*2/#slots}
   for _,radius in ipairs({20,40,80})do
    calls={};v:DrawImmune({},0,0,radius,immune,10)
    local paint=recorded(macro and 'nvgImagePatternTinted' or 'nvgImagePattern')[1]
    assert(math.abs(paint[5]*meta.fill-2*radius)<1e-9,'有效前景必须匹配原有直径')
    if macro then
     local color=paint[9];assert(color[2]==255 and color[3]==255 and color[4]==255)
    else assert(#recorded('nvgImagePatternTinted')==0,'T细胞显示原色')end
   end
  end
 ''',
 '真实出生免疫随机外观只读实体且不消耗模拟或全局RNG': r'''
  local w=require('Core.SwarmWorld').New('UPPER_AIRWAY');local v=View.New()
  local before=freeze(w);local seen={};local rng=math.random
  math.random=function()error('禁止使用全局随机数')end
  for frame=1,20 do
   for _,immune in ipairs(w.immunes)do
    assert(immune.phase~=nil)
    calls={};v:DrawImmune({},immune.x,immune.y,40*frame,immune,frame)
    local path=recorded('image')[1][2]
    assert(not seen[immune.id] or seen[immune.id]==path);seen[immune.id]=path
   end
  end
  math.random=rng;assert(next(seen) and freeze(w)==before)
 ''',
 '新免疫图片加载失败时可见矢量回退且不请求旧图': r'''
  local v=View.New();local cache=package.loaded['urhox-libs/UI/Core/ImageCache']
  cache.Get=function(path)calls[#calls+1]={'image',path};return 0 end
  for _,kind in ipairs({'macrophage','tcell'})do
   calls={};v:DrawImmune({},100,200,40,{kind=kind,phase=1},10)
   assert(#recorded('nvgCircle')>=3 and #recorded('nvgFill')>=2)
   assert(#recorded('nvgImagePattern')==0 and #recorded('nvgImagePatternTinted')==0)
   for _,call in ipairs(recorded('image'))do
    assert(call[2]:find('image/bioluminescent/',1,true)==1)
   end
  end
 ''',
 '环境素材来自真实地图且装饰生成不消耗模拟RNG': r'''
  local w=require('Core.SwarmWorld').New('UPPER_AIRWAY')
  local tissue=require('Game.Views.TissueArt').New();local before=freeze(w)
  assert(tissue:Draw({},w.map,128,10,20));assert(freeze(w)==before)
  local created={};for _,call in ipairs(recorded('create'))do created[call[2]]=true end
  assert(created[Config.ArtSlots.tissueBg] and created[Config.ArtSlots.flowBed])
  assert(created[Config.ArtSlots.tissueFibers[1]] and created[Config.ArtSlots.tissueFibers[2]])
  assert(not Config.EnvironmentVisual.debugFlowBands)
  local fibers=freeze(tissue.fibers);tissue:Prepare(w.map);assert(freeze(tissue.fibers)==fibers)
  tissue:Destroy();assert(not tissue.map and not next(tissue.fibers))
 ''',
 '同帧已提交纹理不被LRU删除且容量不足回退下一帧重试': r'''
  local art=Art.New(2);local nvg={};art:BeginFrame()
  assert(art:Get(nvg,'page-a') and art:Get(nvg,'page-b'))
  assert(not art:Get(nvg,'page-c') and #recorded('delete')==0)
  assert(not next(art.failures),'缓存饱和不是文件加载失败')
  art:BeginFrame();assert(art:Get(nvg,'page-b'))
  assert(art:Get(nvg,'page-c') and #recorded('delete')==1)
  assert(art:Get(nvg,'page-b') and not art:Get(nvg,'page-a'))
  art:Destroy();assert(#recorded('delete')==3)
 ''',
}


def pixels():
    source=ROOT/'assets/image/bioluminescent'
    for name,digest in MANIFEST['sources'].items():
        assert hashlib.sha256((source/name).read_bytes()).hexdigest()==digest,name
    exhaustion=np.asarray(Image.open(source/'cell_exhaustion.png').convert('RGBA'))
    vac=np.asarray(Image.open(source/'cell_vacuole.png').convert('RGBA'))[:,:,3]
    assert not (exhaustion[:,:,3][vac>0]>0).any()
    assert MANIFEST['material_mode']=='bioluminescent-sprites' and MANIFEST['pages']==[]
    assert len(MANIFEST['poses'])==180 and MANIFEST['patch_border_errors']==0
    assert MANIFEST['virus_fill']==466/512
    for pose in MANIFEST['poses']:
        assert len(pose['frames'])==len(pose['centres'])==len(pose['diameters'])==MANIFEST['animation_frames']
        centres=np.array(pose['centres']);diameters=np.array(pose['diameters'])
        assert np.isfinite(centres).all() and np.isfinite(diameters).all() and (diameters>=0).all()
        assert np.max(np.linalg.norm(np.diff(centres,axis=0),axis=1))<10
        assert np.max(abs(np.diff(diameters)))<=14
    art=json.loads((source/'manifest.json').read_text(encoding='utf8'))
    for name,item in art['files'].items():
        data=(source/name).read_bytes()
        assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256'],name
    return {'poses':180,'frames':180*MANIFEST['animation_frames'],'legacy_pages':0,
            'source_hashes_unchanged':len(MANIFEST['sources']),'current_files_verified':len(art['files']),
            'vacuole_overlap':0}


def main():
    immune_meta={}
    for name in ('macrophage.png','tcell-01.png','tcell-02.png'):
        img=Image.open(ROOT/'assets/image/bioluminescent'/name).convert('RGBA')
        bounds=img.getchannel('A').getbbox()
        low,high=img.getchannel('A').getextrema()
        assert bounds and low==0 and 250<=high<=255
        immune_meta['image/bioluminescent/'+name]={'canvas':list(img.size),
            'fill':max(bounds[2]-bounds[0],bounds[3]-bounds[1])/max(img.size)}
    results=[]
    for name,code in TESTS.items():
        lua=LuaRuntime(unpack_returned_tuples=True)
        lua.globals().SCRIPT_PATH=str(ROOT/'scripts/?.lua')
        lua.globals().ART_META=lua.table_from(MANIFEST,recursive=True)
        lua.globals().IMMUNE_META=lua.table_from(immune_meta,recursive=True)
        try:
            lua.execute(render.SETUP)
            lua.execute(SETUP)
            lua.execute(code)
            results.append({'name':name,'passed':True})
            print('PASS',name)
        except Exception as exc:
            results.append({'name':name,'passed':False,'error':str(exc)})
            print('FAIL',name,str(exc))
    audit=pixels()
    passed=sum(r['passed'] for r in results)
    report={'scope':'Current art in isolated Lua; mocked NanoVG protocols plus real resource pixels/trajectories, not native GPU gameplay',
            'passed':passed,'total':len(results),'cases':results,'pixels':audit}
    output=Path(os.environ.get('ART_VALIDATION_DIR',str(ROOT/'validation/new-art-integration')))
    output.mkdir(parents=True,exist_ok=True)
    (output/'regression.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'{passed}/{len(results)} passed; independent pixels:',audit)
    return 0 if passed==len(results) else 1


if __name__=='__main__':
    sys.exit(main())
