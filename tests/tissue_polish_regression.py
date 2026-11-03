"""Production Lua equivalence and CPU evidence. No native/GPU FPS claims.

Run using Python 3.12 with .tmp/test-deps and tests on PYTHONPATH.
Baseline is the working tree captured before this change, including prior edits.
"""
from pathlib import Path
import hashlib
import json
import math
import time
from lua_test_runtime import LuaRuntime
from released_performance_regression import BENCH_SETUP, SERIALIZER, GEOMETRY
from ai_non_runtime_acceptance import plain

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'validation/tissue-polish-20261018'
BASE=OUT/'baseline/scripts'

def runtime(path=ROOT/'scripts'):
    lua=LuaRuntime(unpack_returned_tuples=True)
    lua.globals().SOURCE_PATH=(path/'?.lua').as_posix()
    lua.execute("package.path=SOURCE_PATH..';'..package.path;print=function()end")
    return lua

def percentile(values,q):
    return sorted(values)[max(0,math.ceil(len(values)*q)-1)]

def timing(values):
    return dict(median_ms=percentile(values,.5),p95_ms=percentile(values,.95),
                max_ms=max(values),over50=sum(v>50 for v in values))

def geometry():
    results=[]
    for seed in (314159,271828,161803):
        lua=runtime();lua.globals().SEED=seed;lua.globals().BASELINE=BASE.as_posix()
        result=plain(lua.execute(GEOMETRY));results.append(result)
        print('PASS exact flow and swept movement',result,flush=True)
    lua=runtime();lua.globals().BASELINE=BASE.as_posix()
    lua.execute(r'''
local Grid=require('Core.SpatialGrid');local g=Grid.New(1.5)
local items={}
for i=1,800 do items[i]={id=i,x=(i%31)*.25,y=(i%17)*.4,radius=.34+i%7*.02,
 state=i%3==0 and 'DEAD' or i%2==0 and 'HEALTHY' or 'EXPOSED'} end
g:Build(items)
local function compare(x,y,body)
 local padding=.24;local expected=false
 for _,c in ipairs(items) do
  if c.state=='HEALTHY' or c.state=='EXPOSED' then
   local d=math.sqrt((x-c.x)^2+(y-c.y)^2)
   if d<=c.radius+padding+body then expected=true end
  end
 end
 assert(expected==g:AnyInRange(x,y,padding,body,'HEALTHY','EXPOSED'))
end
for i=1,10000 do compare((i%317)*.033,(i%271)*.027,(i%6)*.045) end
-- Boundary arithmetic, including exact tangency and one-ulp offsets.
items={{id=1,x=0,y=0,radius=.34,state='HEALTHY'}};g:Build(items)
for _,body in ipairs({0,.045,.1,.3}) do
 local r=items[1].radius+.24+body
 for _,offset in ipairs({-1e-14,0,1e-14}) do compare(r+offset,0,body) end
end
g:Build({});items={};compare(0,0,.045)
local Config=require('Core.Config');local Map=require('Core.RespiratoryMap')
local m=Map.New(Config.Gameplay);local G=require('Game.FlatMapGeometry')
local before=m:Snapshot();local a=G.Get(m)
assert(a==G.Get(m) and before==m:Snapshot(),'geometry cache mutates map')
local runs=0
for y=1,m.height do for _,r in ipairs(a.wallRows[y]) do
 runs=runs+1;for x=r.x,r.x+r.w-1 do assert(not m.floor[y][x+1]) end
end end
for y=1,m.height do for x=0,m.width-1 do
 local covered=false;for _,r in ipairs(a.wallRows[y]) do if x>=r.x and x<r.x+r.w then covered=true end end
 assert(covered==not m.floor[y][x+1],'wall mask differs from collision')
end end
assert(runs>0 and next(a.chunks))
G.Invalidate(m);assert(G.Get(m)~=a,'explicit edit invalidation')
local old=m.flows;m.flows={};assert(G.Get(m).flows==m.flows);m.flows=old
assert(G.Get(m).flows==old)
''')
    return results

def simulation():
    runtimes={label:runtime(path) for label,path in [('before',BASE),('after',ROOT/'scripts')]}
    for lua in runtimes.values():lua.execute(SERIALIZER+BENCH_SETUP)
    results=[]
    for index,(count,dense) in enumerate([(300,False),(1000,False),(3000,False),(6000,False),(3000,True)]):
        row=dict(count=count,distribution='dense' if dense else '30_sources',steps=120)
        worlds={label:lua.globals().burst(count,dense) for label,lua in runtimes.items()}
        samples={label:[] for label in runtimes}
        # Alternate the order every frame to reduce host-load ordering bias.
        for frame in range(124):
            order=['before','after'] if (frame+index)%2 else ['after','before']
            for label in order:
                w=worlds[label];start=time.perf_counter();w.Update(w,1/60)
                if frame>=4:samples[label].append((time.perf_counter()-start)*1000)
        states={label:lua.globals().snapshot(worlds[label]) for label,lua in runtimes.items()}
        row['exact_state_equal']=states['before']==states['after']
        assert row['exact_state_equal'],'world state/RNG drift'
        for label in runtimes:
            row[label]=timing(samples[label]);row[label]['sha256']=hashlib.sha256(states[label].encode()).hexdigest()
        results.append(row);print('PASS simulation',json.dumps(row),flush=True)
    return results

NVG=r'''
calls=0
for _,name in ipairs({'nvgBeginPath','nvgMoveTo','nvgLineTo','nvgQuadTo','nvgClosePath',
 'nvgRect','nvgFillColor','nvgFill','nvgFillPaint','nvgStrokeWidth','nvgStrokeColor',
 'nvgStroke','nvgCircle','nvgLineCap','nvgLineJoin'})do _G[name]=function()calls=calls+1 end end
nvgRGBA=function()return 1 end;NVG_ROUND=1
Visual=require('Game.FlatMapVisual');Config=require('Core.Config')
map=require('Core.RespiratoryMap').New(Config.Gameplay)
art={BeginFrame=function()end,Paint=function()calls=calls+3;return true end}
function draw()calls=0;Visual.Draw({},map,{x=0,y=0,w=1280,h=720},SCALE,OX,OY,TIME,art)end
'''

def rendering():
    results=[]
    for name,x,y,scale in [('spawn',24,16,55),('walls_and_flows',40,66,55),('overview',60,72,9)]:
        row=dict(scene=name,frames=120)
        for label,path in [('before',BASE),('after',ROOT/'scripts')]:
            lua=runtime(path);lua.execute(NVG)
            lua.globals().SCALE=scale;lua.globals().OX=640-x*scale;lua.globals().OY=360-y*scale
            lua.globals().TIME=12;lua.globals().draw()
            before=lua.eval('map:Snapshot()');values=[]
            for frame in range(120):
                lua.globals().TIME=12+frame/60
                start=time.perf_counter();lua.globals().draw();values.append((time.perf_counter()-start)*1000)
            assert before==lua.eval('map:Snapshot()'),'drawing changed authoritative map'
            row[label]=dict(**timing(values),native_calls=lua.globals().calls)
        results.append(row);print('PASS environment rendering',json.dumps(row),flush=True)
    return results

def physics():
    from swarm_visual_physics_regression import SETUP
    surface=json.loads((ROOT/'assets/image/cell_surface_data.json').read_text())
    results=[]
    for count in (30,300,1000):
        row=dict(count=count,frames=120);states={}
        for label,path in [('before',BASE),('after',ROOT/'scripts')]:
            lua=runtime(path);lua.globals().SURFACE=lua.table_from(surface,recursive=True)
            lua.execute(SETUP);lua.execute(f'w,p=visualWorld({count});advance(w,p,30)')
            values=[]
            update=lua.eval('function()p:Update(w,nil,1/60,true,SURFACE)end')
            for _ in range(120):
                start=time.perf_counter();update();values.append((time.perf_counter()-start)*1000)
            states[label]=lua.execute('''local out={};for _,b in ipairs(p.bodies)do
             out[#out+1]=string.format('%.17g/%.17g/%.17g/%.17g/%.17g',b.x,b.y,b.vx,b.vy,b.angle) end
             return table.concat(out,';')''')
            row[label]=timing(values)
        assert states['before']==states['after'],'presentation trajectory drift'
        row['exact_poses_equal']=True;results.append(row)
        print('PASS visual physics',json.dumps(row),flush=True)
    return results

def long_run():
    states={};result={'steps':3600,'simulated_seconds':60,'burst_every_steps':900}
    for label,path in [('before',BASE),('after',ROOT/'scripts')]:
        lua=runtime(path);lua.execute(SERIALIZER+BENCH_SETUP)
        lua.execute(r'''
longWorld=burst(1000,false)
for frame=1,3600 do
 if frame%300==1 then longWorld:SetMovement(frame%600<300 and 1 or -1,0) end
 if frame%900==0 then
  longWorld:_Release(longWorld.cells[501],300)
  longWorld:Split()
 end
 longWorld:Update(1/60)
end
''')
        state=lua.globals().snapshot(lua.globals().longWorld);states[label]=state
        result[label+'_sha256']=hashlib.sha256(state.encode()).hexdigest()
        print('PASS sustained update completed',label,flush=True)
    assert states['before']==states['after'],'long-run gameplay/RNG drift'
    result['exact_state_equal']=True
    lua=runtime()
    lua.execute(r'''
local p=require('Game.SwarmVisualPhysics').New()
for frame=1,2000 do
 p:BuildParticles({{x=frame*100,y=frame*100},{x=frame*100+1,y=frame*100+1}},.1)
 local rows=0;for _ in pairs(p.rows) do rows=rows+1 end
 assert(rows==2 and #p.rowPool==2 and #p.bucketPool==2,'spatial pool retains visited coordinates')
 assert(not p.rows[(frame-1)*1000],'old coordinate remains active')
end
p:BuildParticles({},.1);assert(not next(p.rows))
for _,bucket in ipairs(p.bucketPool) do assert(#bucket==0,'dead entities retained') end
p:Reset();assert(#p.rowPool==0 and #p.bucketPool==0 and not next(p.slotDirections))
''')
    result['pool_lifecycle_passed']=True
    return result

if __name__=='__main__':
    OUT.mkdir(exist_ok=True,parents=True)
    result={'scope':'Lua 5.4 CPU and native call counts; excludes GPU/upload/device FPS',
            'geometry':geometry(),'simulation':simulation(),'environment':rendering(),'visual_physics':physics(),
            'long_run':long_run()}
    (OUT/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('PASS complete; report:',OUT/'report.json')
