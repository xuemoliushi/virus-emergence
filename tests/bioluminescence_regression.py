"""Runtime resource/anchor and bounded-emission checks; not native GPU certification."""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np
from PIL import Image
from lua_test_runtime import LuaRuntime
import cell_render_regression as render

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'validation/bioluminescence-integration-20261015'
TESTS = {
    'shared atlas is capped, small viruses add no draw and destroy releases it': r'''
      local Light=require('Game.Views.Bioluminescence')
      local loads,deletes=0,0
      nvgCreateImage=function(_,path,flags)loads=loads+1;assert(flags==0);return 99 end
      nvgImageSize=function()return 640,512 end
      nvgDeleteImage=function()deletes=deletes+1 end
      nvgGlobalCompositeOperation=function(_,op)assert(op==8)end;NVG_LIGHTER=8
      local v=Light.New();v:BeginFrame(100)
      local vg={}
      for i=1,100 do assert(not v:Draw(vg,1,0,0,16,1,i,0,12)) end
      assert(loads==0 and v.draws==0)
      for i=1,100 do v:Draw(vg,2,0,0,120,1,i,0,100) end
      assert(loads==1 and v.draws==24)
      v:BeginFrame(1200)
      for i=1,100 do v:Draw(vg,5,0,0,1254,.96,i,0,100) end
      assert(loads==1 and v.draws==8)
      v:Destroy();assert(deletes==1)
    ''',
    'missing additive API or texture leaves base art and render state alone': r'''
      local Light=require('Game.Views.Bioluminescence');local v=Light.New();v:BeginFrame(10)
      nvgGlobalCompositeOperation=nil
      calls={};assert(not v:Draw({},5,0,0,1254,1,0,0,100));assert(#calls==0)
      nvgGlobalCompositeOperation=function()error('failed image must not change blend')end;NVG_LIGHTER=8
      nvgCreateImage=function()return 0 end
      calls={};assert(not v:Draw({},5,0,0,1254,1,0,0,100));assert(#calls==0)
      Config.Bioluminescence.glowEnabled=false
      assert(not v:Draw({},5,0,0,1254,1,0,0,100))
      assert(Config.ArtSlots.cellBody:match('bioluminescent/cell_body'))
    ''',
    'new birth sprites retain centre/diameter and only handle successful births': r'''
      local Bud=require('Game.Views.BuddingVisual');local b=Bud.New({manifest={material_mode='bioluminescent-sprites'}})
      nvgCreateImage=function()return 20 end;nvgImageSize=function()return 256,256 end;nvgDeleteImage=function()end
      b.records[7]={{age=.3,frame=2,virus={id=19},pose={
        frames={{1,0,0},{1,0,0},{1,0,0}},
        centres={{0,-50},{30,-70},{44,-98}},diameters={2,24,32},rect={0,0,40,50}}}}
      local vg={};local ready=b:Ready(vg,{id=7});assert(#ready==1 and ready[1].fluorescent)
      local handled={};b:DrawPatches(vg,ready,.96,handled)
      assert(handled[19] and ready[1].shown)
      local translations=recorded('nvgTranslate');assert(translations[#translations][3]==30 and translations[#translations][4]==-70)
      local paints=recorded('nvgImagePattern');local expected=24/Config.CellVisual.virusFill
      assert(math.abs(paints[#paints][5]-expected)<1e-10)
      assert(#recorded('nvgStroke')==1,'Mid-birth neck must use the new warm membrane line')
      assert(ready[1].virus.id==19 and ready[1].age==.3)
    ''',
}


def main():
    results = []
    for name, code in TESTS.items():
        lua=LuaRuntime(unpack_returned_tuples=True)
        lua.globals().SCRIPT_PATH=str(ROOT/'scripts/?.lua')
        try:
            lua.execute(render.SETUP); lua.execute(code)
            results.append({'name':name,'passed':True}); print('PASS', name)
        except Exception as exc:
            results.append({'name':name,'passed':False,'error':str(exc)}); print('FAIL',name,str(exc))
    alpha={}
    # Captured from the old source layers before their verified retirement.
    baseline=json.loads((ROOT/'validation/actor-asset-cleanup-20261018/removed.json').read_text(encoding='utf8'))['original_alpha_sha256']
    for name in ['cell_body.png','cell_membrane.png','cell_vacuole.png']:
        new=np.asarray(Image.open(ROOT/'assets/image/bioluminescent'/name).convert('RGBA'))
        alpha[name]=hashlib.sha256(new[:,:,3].tobytes()).hexdigest()==baseline[name]
    new=np.asarray(Image.open(ROOT/'assets/image/bioluminescent/virus_attached.png').convert('RGBA'))
    alpha['attached_virus']=hashlib.sha256(new[:,:,3].tobytes()).hexdigest()==baseline['virus_attached.png']
    report={'scope':'Lua protocol and resource pixels only, not native engine or mobile FPS',
            'cases':results,'originalAlphaPreserved':alpha,
            'passed':all(x['passed'] for x in results) and all(alpha.values())}
    OUT.mkdir(exist_ok=True,parents=True)
    (OUT/'bioluminescence-regression.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print('ALPHA',alpha)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    sys.exit(main())
