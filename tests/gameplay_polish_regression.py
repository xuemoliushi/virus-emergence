"""Real Lua role/navigation and read-only rendering regression; no native GPU claim."""
from pathlib import Path
import json
import os
import sys

from lua_test_runtime import LuaRuntime
import cell_render_regression as render
import swarm_regression as swarm

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get('ART_VALIDATION_DIR', str(ROOT/'validation/gameplay-polish-20261010')))

SETUP = r'''
Attachments=require('Game.Views.AttachmentVisual')
Contacts=require('Core.CellContacts')
Navigation=require('Core.ImmuneNavigation')
function attachmentFixture()
 local v=View.New();local c=cell();c.contactVisuals={};c.contactVisualAnchor=nil
 c.state='HEALTHY';c.exposure=.3
 local s={id=1,x=.3,y=0,radius=.25}
 return v,c,s
end
function accept(c,s,t)
 local pending={};Contacts.Collect(c,s,'PLAYER_SWARM',1,pending);Contacts.Commit(c,pending,t)
end
function draw(v,c,t,r,ppm)
 calls={};v:DrawCell({},0,0,r or 50,c,t,nil,nil,ppm)
 return recorded('attached')[1],recorded('patch')[1]
end
function bendMap()
 local map={regions={},channels={{points={{x=1,y=1},{x=5,y=1},{x=5,y=4}}}}}
 function map:Contains(x,y,r)
  r=r or 0
  return (x>=r and x<=6-r and y>=r and y<=2-r)
      or (x>=4+r and x<=6-r and y>=r and y<=6-r)
 end
 function map:RegionAt()return 1 end
 function map:Move(x,y,tx,ty,r)
  for i=0,100 do local t=i/100;if not self:Contains(x+(tx-x)*t,y+(ty-y)*t,r) then return x,y end end
  return tx,ty
 end
 return map
end
'''

TESTS = {
 '真实连续接触期间色斑与吸附共用进入方向不沿膜滑动': r'''
  local v,c,s=attachmentFixture();accept(c,s,10)
  local a,p=draw(v,c,10);assert(a[2]==p[2]);local angle=a[2]
  for i=1,120 do
   s.x,s.y=.3*math.cos(i*.02),.3*math.sin(i*.02);accept(c,s,10+i/60)
   a,p=draw(v,c,10+i/60);assert(a[2]==angle and p[2]==angle)
  end
  c.rotation=c.rotation+.7;a,p=draw(v,c,12)
  assert(math.abs(a[2]-angle-.7)<1e-8 and a[2]==p[2])
  assert(c.contactVisuals[1].contactSequence==1 and c.contactVisuals[1].enteredAt==10)
 ''',
 '同来源在旧记录与淡出尚存时再次靠近重算真实方向': r'''
  local v,c,s=attachmentFixture();accept(c,s,10);local a=draw(v,c,10)
  local r=c.contactVisuals[1];Contacts.Commit(c,{},10.1)
  assert(not r.active)
  s.x,s.y=0,-.3;accept(c,s,10.2)
  local b,p=draw(v,c,10.2)
  assert(c.contactVisuals[1]==r and r.contactSequence==2 and r.enteredAt==10.2)
  assert(math.abs((b[2]+math.pi/2)%(2*math.pi))<1e-8)
  assert(b[2]~=a[2] and b[2]==p[2] and b[3]==.9)
  assert(math.abs(r.stableLocalAngle-r.entryLocalAngle)>1,'显示不能使用旧平滑方向')
 ''',
 '渲染漏过离开帧和旧记录删除后仍识别新接触段': r'''
  local v,c,s=attachmentFixture();accept(c,s,10);draw(v,c,10)
  Contacts.Commit(c,{},11);assert(#c.contactVisuals==0)
  s.x,s.y=-.3,0;accept(c,s,11.1)
  local b,p=draw(v,c,11.1)
  assert(math.abs(b[2]-math.pi)<1e-8 and b[2]==p[2])
  Contacts.Commit(c,{},12);calls={};v:DrawCell({},0,0,50,c,12)
  s.x,s.y=0,.3;accept(c,s,15)
  b,p=draw(v,c,15);assert(math.abs(b[2]-math.pi/2)<1e-8 and b[2]==p[2])
 ''',
 '色斑保存最新进入锚点直至产毒耗竭且暂停不改方向': r'''
  local v,c,s=attachmentFixture();accept(c,s,10);draw(v,c,10)
  Contacts.Commit(c,{},10.1);s.x,s.y=0,.3;accept(c,s,10.2)
  local _,p=draw(v,c,10.2);local angle=p[2]
  c.state='LATENT';c.infectedVisualAt=10.2;c.exposure=0
  Contacts.Commit(c,{},11);draw(v,c,11)
  for _,state in ipairs({'LATENT','PRODUCTIVE','EXHAUSTED'})do
   c.state=state
   local a,b=draw(v,c,14);assert(not a and b[2]==angle and b[3]==1)
   local _,again=draw(v,c,14);assert(again[2]==angle)
  end
  c.state='DEAD';draw(v,c,15);assert(not v.attachments.patches[c.id])
 ''',
 '渲染恢复时从真实病程锚点读取新进入方向不虚造接触': r'''
  local v,c,s=attachmentFixture();accept(c,s,10);draw(v,c,10)
  Contacts.Commit(c,{},11);s.x,s.y=0,-.3;accept(c,s,12)
  Contacts.Commit(c,{},13);c.state='PRODUCTIVE';c.exposure=0
  local a,p=draw(v,c,14);assert(not a and math.abs((p[2]+math.pi/2)%(2*math.pi))<1e-8)
  v.attachments:Prepare({cells={c}});assert(v.attachments.patches[c.id])
  v:Destroy();assert(not next(v.attachments.patches))
  local other=cell();other.id=3;other.state='LATENT';other.contactVisuals={};other.contactVisualAnchor=nil
  a,p=draw(v,other,14);assert(not a and not p)
 ''',
 '多来源新进入重置色斑旧淡出不能阻挡新来源': r'''
  local a=Attachments.New();local c=cell();c.contactVisuals={}
  for i=1,3 do c.contactVisuals[i]={key='old'..i,normalX=1,normalY=0,lastSeen=10,enteredAt=10,active=true}end
  assert(#a:Get(c,10)==3)
  for _,contact in ipairs(c.contactVisuals)do contact.active=false end
  c.contactVisuals[4]={key='new',normalX=0,normalY=-1,lastSeen=10.1,enteredAt=10.1,active=true}
  local list=a:Get(c,10.1);assert(#list==3 and a.cells[c.id].new)
  assert(a:GetPatchAngle(c)==a.cells[c.id].new.angle)
 ''',
 '吸附大小匹配单颗真实病毒不使用群半径且与细胞大小缩放无关': r'''
  for _,cellRadius in ipairs({.24,.4,.8})do
   for _,ppm in ipairs({40,120,260})do
    local v,c,s=attachmentFixture();c.radius=cellRadius;s.radius=2
    accept(c,s,10);v.attachments:Prepare({cells={c},viruses={{swarmId=1,radius=.045}}})
    local a,p=draw(v,c,10,cellRadius*ppm,ppm)
    local visible=a[4]*96*(cellRadius*ppm*2/760)
    near(visible,2*.045*ppm,1e-10)
    assert(a[2]==p[2])
    assert(v.surface:GetPlacement(c,{angle=p[2]}).scale==nil,'色斑保留原图集比例')
    s.radius=.1;accept(c,s,10.1);local b=draw(v,c,10.1,cellRadius*ppm,ppm)
    assert(b[4]==a[4])
   end
  end
 ''',
 '游离病毒不同真实尺寸与玩家单颗尺寸分别读取': r'''
  local v,c,s=attachmentFixture();s.id=7
  local pending={};Contacts.Collect(c,s,'RELEASED_VIRUS',1,pending);Contacts.Commit(c,pending,10)
  v.attachments:Prepare({cells={c},releasedViruses={{id=7,radius=.075,state='INFECTING'}},viruses={{swarmId=7,radius=.02}}})
  local a=draw(v,c,10,48,120);near(a[4]*96*96/760,.075*2*120,1e-10)
  local b=Attachments.New();near(b:VirusRadius({sourceType='RELEASED_VIRUS',sourceId=7}),cfg.virusRadius)
 ''',
 '吸附角度和亮度不随病毒群方向与接触强度抖动': r'''
  local v=View.New();local c=cell();c.state='HEALTHY';c.exposure=0;c.contactVisuals={c.contactVisuals[1]}
  v:DrawCell({},0,0,50,c,10);local initial=recorded('attached')[1]
  for i=1,120 do
   local record=c.contactVisuals[1];record.normalX,record.normalY=math.cos(i*.1),math.sin(i*.1)
   record.stableLocalAngle=i*.03;record.strength=(i%5)/5;record.lastSeen=10+i/60
   calls={};v:DrawCell({},0,0,50,c,10+i/60)
   local drawn=recorded('attached')[1];assert(drawn and drawn[2]==initial[2] and drawn[3]==initial[3])
  end
  c.rotation=c.rotation+.7;calls={};v:DrawCell({},0,0,50,c,12)
  assert(math.abs(recorded('attached')[1][2]-initial[2]-.7)<1e-8,'局部锚点随细胞旋转')
 ''',
 '离开健康细胞后淡出超过旧接触记录寿命且暂停不推进': r'''
  local v=View.New();local c=cell();c.state='HEALTHY';c.exposure=0;c.contactVisuals={c.contactVisuals[1]}
  v:DrawCell({},0,0,50,c,10);c.contactVisuals={}
  local previous=.9
  for _,t in ipairs({10.16,10.5,11,11.8,12.4})do
   calls={};v:DrawCell({},0,0,50,c,t);local p=recorded('attached')[1]
   assert(p and p[3]<previous);previous=p[3]
   calls={};v:DrawCell({},0,0,50,c,t);assert(recorded('attached')[1][3]==previous)
  end
  calls={};v:DrawCell({},0,0,50,c,12.56);assert(#recorded('attached')==0)
  assert(not next(v.attachments.cells[c.id]))
 ''',
 '三个真实来源限额去重死亡与退出清空视觉记录': r'''
  local a=Attachments.New();local c=cell();c.state='HEALTHY';c.contactVisuals={}
  for i=1,8 do c.contactVisuals[i]={key='k'..i,normalX=1,normalY=0,lastSeen=10,sourceId=i} end
  assert(#a:Get(c,10)==3 and #a:Get(c,10)==3)
  c.state='DEAD';assert(#a:Get(c,10)==0 and not a.cells[c.id])
  c.state='HEALTHY';assert(#a:Get(c,10)==3);a:Destroy();assert(not next(a.cells))
 ''',
 '已清除游离病毒立即取消附着并允许普通实体缺图回退': r'''
  local a=Attachments.New();local c=cell();c.state='HEALTHY'
  c.contactVisuals={{key='v:7',sourceType='RELEASED_VIRUS',sourceId=7,normalX=1,normalY=0,lastSeen=10}}
  assert(#a:Get(c,10)==1)
  a:Prepare({cells={c},releasedViruses={{id=7,state='CLEARED'}}})
  assert(not next(a.cells[c.id]))
  assert(#a:Get(c,10)==0,'旧接触记录不得复活已清除的实体')
 ''',
 'T细胞忽略游离病毒并对新发现节点完整预警': r'''
  local w,im=immuneFixture('tcell');local c=unitCell(w,1,im.x+1.8,im.y)
  w.swarms={};w.cells={c};w.releasedViruses={{id=99,x=im.x+1,y=im.y,radius=.045,state='DRIFTING'}}
  Immune.Update(w,cfg.movementStep);assert(im.targetId==nil)
  c.state='LATENT';c.immuneSignalValue=1
  Immune.Update(w,cfg.movementStep)
  assert(im.targetType=='cell' and im.targetId==c.id and im.state=='locked')
  near(im.warningTimer,im.warningTime);assert(im.attackTimer==0 and c.immuneHits==0)
 ''',
 '巨噬细胞忽略感染节点，游离病毒优先于群并重置预警': r'''
  local w,im=immuneFixture('macrophage');local c=unitCell(w,1,im.x+1.8,im.y)
  c.state='PRODUCTIVE';c.immuneSignalValue=1;w.cells={c}
  Immune.Update(w,cfg.movementStep);assert(im.targetType=='swarm')
  w.releasedViruses={{id=99,x=im.x+1,y=im.y,radius=.045,state='RELEASED'}}
  im.state='warning';im.warningTimer=.1;im._retargetTimer=0
  Immune.Update(w,cfg.movementStep)
  assert(im.targetType=='virus' and im.targetId==99 and im.state=='locked')
  near(im.warningTimer,im.warningTime)
  im.state='attack';im.x,im.y=im.targetX,im.targetY;im.attackTimer=.6
  w.releasedViruses[#w.releasedViruses+1]={id=100,x=im.x,y=im.y,radius=.045,state='RELEASED'}
  Immune.Update(w,cfg.movementStep)
  assert(im.targetId==99 and im.attackTimer>0)
 ''',
 '巡逻不读取感知范围外的节点或群坐标': r'''
  for _,kind in ipairs({'tcell','macrophage'})do
   local w,im=immuneFixture(kind);local x,y=im.x,im.y
   local c=unitCell(w,1,x-2,y);c.state='PRODUCTIVE';c.immuneSignalValue=1
   w.cells={c};w.releasedViruses={};w.player.x,w.player.y=x+2,y;w.player.visibility=1
   im.detectionRange=.1
   Immune.Update(w,cfg.movementStep)
   assert(im.state=='patrol' and im.targetId==nil)
   assert(w.map:Contains(im._patrolX,im._patrolY,im.radius))
  end
 ''',
 '按身体半径绕真实通道拐弯且拒绝跨暗区直线': r'''
  local map=bendMap();local a,b={x=1,y=1},{x=5,y=4}
  assert(not Navigation.Clear(map,a,b,.48))
  local route=assert(Navigation.Route(map,a,b,.48));assert(#route>=2)
  local previous=a
  for _,p in ipairs(route)do
   for i=0,100 do local t=i/100;assert(map:Contains(previous.x+(p.x-previous.x)*t,previous.y+(p.y-previous.y)*t,.48))end
   previous=p
  end
  assert(not Navigation.Route(map,a,{x=3,y=5},.48))
  local w,im=immuneFixture('macrophage');w.map=map;w.cells={};w.swarms={}
  im.x,im.y,im.radius=1,1,.48;im.targetType,im.targetId='virus',99;im.state='chase'
  w.releasedViruses={{id=99,x=5,y=4,radius=.045,state='DRIFTING'}}
  for i=1,450 do
   Immune.Update(w,cfg.movementStep);assert(map:Contains(im.x,im.y,im.radius))
   if im.state=='attack' then break end
   if im.targetId==nil then break end -- 丢失实际视线必须停止读取目标坐标。
  end
  assert(im.targetId==nil and im.state=='patrol','未能看见目标时停止追踪')
 ''',
 '真实地图通道图不会生成穿出组织的路段且尺寸隔离': r'''
  local w=World.New('UPPER_AIRWAY');local map=w.map
  for _,r in ipairs({.3,.48})do
   local a,b=map.startPoints.UPPER_AIRWAY,map.startPoints.DEEP_LUNG
   local route=assert(Navigation.Route(map,a,b,r));local previous=a
   assert(#route>1)
   for _,p in ipairs(route)do
    for i=0,100 do local t=i/100;assert(map:Contains(previous.x+(p.x-previous.x)*t,previous.y+(p.y-previous.y)*t,r))end
    previous=p
   end
  end
 ''',
 '组织流明亮箭头方向来自真实流场并且暂停相位固定': r'''
  nvgLineCap=function()end;nvgLineJoin=function()end;NVG_ROUND=1
  local v=View.New();local c={id=1,width=2.5,speed=1.6,strength=.88,points={{x=0,y=0},{x=10,y=0}}}
  local samples=0;local m={Contains=function()return true end,FlowAt=function()samples=samples+1;return 1,0 end}
  local l={x=-100,y=-100,w=1200,h=300}
  v:DrawFlow({},c,m,l,100,0,0,10)
  assert(samples>0 and #recorded('nvgLineTo')>30 and #recorded('nvgStrokeWidth')>20)
  local phase=v.flowAnimation[4].phase;calls={};v:DrawFlow({},c,m,l,100,0,0,10)
  assert(v.flowAnimation[4].phase==phase)
  calls={};v:DrawFlow({},c,m,l,100,0,0,10.1);assert(v.flowAnimation[4].phase>phase)
  assert(Config.EnvironmentVisual.debugFlowBands==false)
 ''',
}

def main():
    results=[]
    for name, code in TESTS.items():
        lua=LuaRuntime(unpack_returned_tuples=True)
        lua.globals().SCRIPT_PATH=str(ROOT/'scripts/?.lua')
        try:
            lua.execute(render.SETUP)
            lua.execute(swarm.SETUP)
            lua.execute(SETUP)
            lua.execute(code)
            results.append({'name':name,'passed':True})
            print('PASS',name)
        except Exception as error:
            results.append({'name':name,'passed':False,'error':str(error)})
            print('FAIL',name,str(error))
    OUT.mkdir(parents=True,exist_ok=True)
    passed=sum(item['passed'] for item in results)
    (OUT/'polish-regression.json').write_text(json.dumps({'passed':passed,'total':len(results),
        'scope':'real Lua plus draw-call mocks; not native GPU acceptance','cases':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'{passed}/{len(results)} passed')
    return 0 if passed==len(results) else 1

if __name__=='__main__':
    sys.exit(main())
