"""No added lighting regression. Draw-call checks do not certify GPU visuals."""
from pathlib import Path

from lua_test_runtime import LuaRuntime
import cell_render_regression as render

ROOT = Path(__file__).resolve().parents[1]
SETUP = render.SETUP + r'''
VU=require('Game.VisualUtils')
function forbidden()error('removed lighting path must never run')end
nvgSetBloomEnabled=forbidden
nvgRGBAf=forbidden
nvgRadialGradient=forbidden
'''

TESTS = {
    '普通精灵与出芽分区保留原尺寸锚点透明度': r'''
 calls={};assert(VU.DrawSprite({},'membrane.png',10,20,1254,.96,.3))
 local p=recorded('nvgImagePattern')[1]
 assert(p[3]==-627 and p[4]==-627 and p[5]==1254 and p[6]==1254 and p[9]==.96)
 assert(#recorded('nvgImagePatternTinted')==0)
 calls={};assert(VU.DrawSpriteRegion({},'membrane.png',1254,{-500,-200,100,80},.5))
 p=recorded('nvgImagePattern')[1];local rect=recorded('nvgRect')[1]
 assert(p[3]==-627 and p[4]==-627 and p[5]==1254 and p[9]==.5)
 assert(rect[3]==-500 and rect[4]==-200 and rect[5]==100 and rect[6]==80)
 ''',
    '六态细胞不调用BloomHDR或渐变并保留膜内接触亮斑': r'''
 local v=View.New();local c=cell()
 for _,state in ipairs({'HEALTHY','EXPOSED','LATENT','PRODUCTIVE','EXHAUSTED','DEAD'})do
  c.state=state;c.infectedVisualAt=9;c.exhaustionTimer=1;c.deathVisualAt=9
  c.lastReleaseVisualAt=10;c.releaseVisualDirections={{normalX=1,normalY=0,visualCellRotation=.3}}
  calls={};v:DrawCell({},100,100,50,c,10)
  if state=='HEALTHY' or state=='EXPOSED' then
   assert(#recorded('glint')>0 and #recorded('attached')>0)
  end
 end
 assert(Config.LightEffects==nil and v.lightEffects==nil and v.SetLightEffectsEnabled==nil)
 ''',
    '事件继续保留既有线条而无新增渐变光晕': r'''
 local v=View.New()
 for _,kind in ipairs({'infect','release','rupture','engulf','absorb','join','split'})do
  calls={};v:DrawEffect({},10,20,30,{kind=kind,age=.1,duration=.8})
  assert(#recorded('nvgStroke')>0,kind..' feedback must survive')
 end
 ''',
    '游离病毒与免疫细胞使用常规原图绘制': r'''
 local v=View.New()
 calls={};v:DrawVirus({},10,20,6,{id=1,x=0,y=0,state='RELEASED',phase=.1},10,128,true,false)
 assert(#recorded('nvgImagePattern')==1 and #recorded('nvgImagePatternTinted')==0)
 calls={};v:DrawImmune({},10,20,30,{id=1,kind='macrophage',state='patrol',phase=0},10)
 local tint=recorded('nvgRGBA')[1];assert(tint[2]==255 and tint[3]==255 and tint[4]==255)
 ''',
    '真实世界穿插绘制600步实体计时及RNG逐步一致': r'''
 local World=require('Core.SwarmWorld')
 local a=World.New('DEEP_LUNG');local b=World.New('DEEP_LUNG')
 for _,w in ipairs({a,b})do w.cells[1].state='LATENT';w.cells[1].latencyTimer=.01 end
 local function equal(x,y,seen)
  assert(type(x)==type(y))
  if type(x)=='function' then return end
  if type(x)~='table' then assert(x==y,tostring(x)..' ~= '..tostring(y));return end
  if x==y or seen[x]==y then return end;seen[x]=y
  for k,v in pairs(x)do equal(v,y[k],seen)end
  for k in pairs(y)do assert(x[k]~=nil)end
 end
 local v=View.New();v.visualWorld=a
 for i=1,600 do
  a:Update(1/60);b:Update(1/60);calls={}
  local c=a.cells[1];v:DrawCell({},100,100,c.radius*128,c,a.time)
  assert(a._rng==b._rng)
  -- Spatial caches have entity tables as keys, whose identities differ across
  -- independently initialized worlds. Compare every other world field.
  for key,value in pairs(a)do
   if key~='cellGrid' and key~='releasedGrid' then equal(value,b[key],{}) end
  end
 end
 ''',
    '启动重开切换观察层与退出不启用Bloom且B键无效果': r'''
 local resets=0;local current='cell';local shutdown=false;local observed=false
 local sim={started=true,init=function()resets=resets+1 end}
 local mgr={init=function()end,CurrentScale=function()return current end,
  JumpTo=function(_,scale)current=scale end}
 local hud={Build=function()return {}end,RefreshStrategyHighlight=function()end,
  ResetEnding=function()end,Destroy=function()end}
 package.loaded['Core.SimState']={New=function()return sim end}
 package.loaded['Core.ScaleManager']={New=function()return mgr end}
 package.loaded['Core.ObservationState']={New=function()return {
  Reset=function()end,ShowBody=function()observed=true end}end}
 package.loaded['UI.HUD']={New=function()return hud end}
 package.loaded['Game.GameScene']=function(props)return props end
 package.loaded['urhox-libs/UI']={Scale={DEFAULT=1},Init=function()end,
  Panel=function(props)return props end,SetRoot=function()end,
  Shutdown=function()shutdown=true end}
 graphics={};SubscribeToEvent=function()end
 KEY_B=66;KEY_R=82;KEY_E=69;KEY_SPACE=32;KEY_2=50;KEY_TAB=9;KEY_M=77
 dofile(MAIN_PATH);StartBgm=function()end
 local function key(k)
  HandleKeyDown('KeyDown',{GetInt=function()return k end,GetBool=function()return false end})
 end
 Start();key(KEY_B);assert(resets==0 and current=='cell')
 key(KEY_R);assert(resets==1)
 key(KEY_M);assert(current=='mouse' and observed)
 key(KEY_M);assert(current=='cell')
 Stop();assert(shutdown)
 ''',
}


def main():
    failed = []
    for name, code in TESTS.items():
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().SCRIPT_PATH = str(ROOT / 'scripts/?.lua')
        lua.globals().MAIN_PATH = str(ROOT / 'scripts/main.lua')
        try:
            lua.execute(SETUP)
            lua.execute(code)
            print('PASS', name)
        except Exception as error:
            failed.append((name, str(error)))
            print('FAIL', name, error)
    print(f'{len(TESTS)-len(failed)}/{len(TESTS)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
