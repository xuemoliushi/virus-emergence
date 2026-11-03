"""Approved candidate vs runtime geometry, exact walls, routing and real simulation.
Native entry/input/rendering require separate Maker window evidence.
"""
from pathlib import Path
import hashlib,json,platform,time
from lua_test_runtime import LuaRuntime

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'validation/flat-map-live'
OUT.mkdir(parents=True,exist_ok=True)
lua=LuaRuntime(unpack_returned_tuples=True)
lua.globals().SCRIPT_PATH=str(ROOT/'scripts/?.lua').replace('\\','/')
lua.execute("package.path=SCRIPT_PATH..';'..package.path;Config=require('Core.Config');Map=require('Core.RespiratoryMap');World=require('Core.SwarmWorld');Nav=require('Core.ImmuneNavigation');print=function()end")
checks=[]
# Approved-geometry comparisons intentionally pin their reference seed.
lua.execute('Config.Gameplay.mapSeed=314159')
def check(name,code):
    began=time.perf_counter();lua.execute(code)
    checks.append(dict(name=name,passed=True,ms=(time.perf_counter()-began)*1000))
    print('PASS',name,flush=True)

check('Normal world factory uses dense v5 without disturbing global RNG',r'''
math.randomseed(456);local expected={math.random(),math.random(),math.random()}
math.randomseed(456);local first=math.random()
w=World.New('UPPER_AIRWAY');m=w.map
assert(first==expected[1] and math.random()==expected[2] and math.random()==expected[3])
assert(m.isFlatMap and m.generationVersion==5 and m.width==120 and m.height==144 and #w.cells==960 and m.seed==314159)
assert(#w.immunes==Config.StartRegions[1].flatImmuneCount)
for _,v in ipairs(w.immunes) do assert(m:Contains(v.x,v.y,v.radius));assert((v.x-w.player.x)^2+(v.y-w.player.y)^2>25) end
for _,c in ipairs(w.cells) do assert(c.regionId>0 and m:Contains(c.x,c.y,c.radius)) end
''')
# Compare all approved data, not pictures. Runtime only adds statistics regionId.
data=json.loads((ROOT/'validation/flat-map-preview/map-314159-v4.json').read_text(encoding='utf-8'))
m=lua.globals().m
assert list(m.floorRows.values())==data['floorRows']
legacy=lua.execute("local cfg={};for k,v in pairs(Config.Gameplay) do cfg[k]=v end;cfg.mapGenerationVersion=4;cfg.cellCount=480;return Map.New(cfg)")
for old in data['cells']:
    now=legacy.cells[old['id']]
    for key,value in old.items():assert now[key]==value,(old['id'],key)
def plain(t):
    if not hasattr(t,'items'):return t
    if len(t)>0 and set(t.keys())==set(range(1,len(t)+1)):return [plain(t[i]) for i in range(1,len(t)+1)]
    return {k:plain(v) for k,v in t.items()}
for key in ('spawn','flows','outerBoundary','obstacles','majorRoutes','crossFlows'):
    assert plain(m[key])==data[key],key
checks.append(dict(name='Exact approved v4 geometry retained; legacy cells reproduced; v5 density configured',passed=True))
check('Repeated runtime generation and nil seed stored once',r'''
local again=Map.New(Config.Gameplay)
assert(m:Snapshot()==again:Snapshot())
local cfg={};for k,v in pairs(Config.Gameplay) do cfg[k]=v end
local random=require('Core.MapRandom');local makeSeed=random.NewSeed
local actual=makeSeed();assert(actual>=1 and actual<=2147483646)
local calls=0;random.NewSeed=function() calls=calls+1;return 1 end
cfg.mapSeed=nil;local fresh=Map.New(cfg);random.NewSeed=makeSeed
assert(calls==1)
local seed=fresh.seed;local snapshot=fresh:Snapshot()
for i=1,5 do fresh:FlowAt(20,30,i);fresh:Move(fresh.spawn.x,fresh.spawn.y,fresh.spawn.x+1,fresh.spawn.y,.48) end
assert(fresh.seed==seed and fresh:Snapshot()==snapshot)
cfg.mapSeed=seed;assert(Map.New(cfg):Snapshot()==snapshot)
''')
check('Exact sweep blocks long jumps and slides; rounded corners and tangents',r'''
local fake={width=20,height=20,floor={}}
setmetatable(fake,getmetatable(m))
for y=1,20 do fake.floor[y]={};for x=1,20 do fake.floor[y][x]=x>1 and x<20 and y>1 and y<20 end end
fake.floor[10][10]=false
for _,radius in ipairs({0,.05,.48,1.35}) do
 local hit=fake:_Sweep(3,9.5,13,0,radius);assert(hit>0 and hit<1)
 local x,y=fake:Move(3,9.5,16,9.5,radius);assert(x<9-radius and fake:Contains(x,y,radius))
 assert(not Nav.Clear(fake,{x=3,y=9.5},{x=16,y=9.5},radius))
 x,y=fake:Move(3,8,16,11,radius);assert(fake:Contains(x,y,radius))
end
local t=fake:_Sweep(8,8,2,2,.5)
assert(math.abs(t-(1-.5/math.sqrt(2))/2)<1e-9)
local x,y=fake:Move(3,9.5,8.5,9.5,.5);assert(fake:Contains(x,y,.5) and x<8.5)
x,y=fake:Move(8.5-1e-6,9.5,8.5-1e-6,14,.5);assert(y>13.9)
fake.isFlatMap=true;fake.navigationCache={}
local route=assert(Nav.Route(fake,{x=3,y=9.5},{x=16,y=9.5},.5));assert(#route>=2)
local from={x=3,y=9.5};for _,p in ipairs(route) do assert(Nav.Clear(fake,from,p,.5));from=p end
''')
check('Real large-map routes for immune and maximum swarm body',r'''
ROUTE_TIMES={}
for _,radius in ipairs({.3,.5,1.35}) do
 local from={x=m.spawn.x,y=m.spawn.y}
 for _,region in ipairs(m.regions) do
  local began=os.clock();local route=assert(Nav.Route(m,from,region,radius),'No route to region')
  ROUTE_TIMES[#ROUTE_TIMES+1]=(os.clock()-began)*1000
  for _,p in ipairs(route) do assert(Nav.Clear(m,from,p,radius),'Unsafe route edge');from=p end
 end
end
''')
check('First target reached with production movement, infection and stable contact',r'''
-- Quiet controlled fixture; same world methods, only initial immune pressure removed.
w.immunes={};local oldMax=w.config.immuneMax;w.config.immuneMax=0
local best=math.huge
for _,cell in ipairs(w.cells) do
 local d=(cell.x-w.player.x)^2+(cell.y-w.player.y)^2
 if d<best and Nav.Clear(m,w.player,cell,w.player.radius) then firstCell=cell;best=d end
end
assert(firstCell and best<36)
for i=1,1500 do
 local dx,dy=firstCell.x-w.player.x,firstCell.y-w.player.y
 local d=math.sqrt(dx*dx+dy*dy)
 if d>.15 then w:SetMovement(dx/d,dy/d) else w:SetMovement(0,0) end
 w:Update(1/60)
 if firstCell.state=='LATENT' or firstCell.state=='PRODUCTIVE' then break end
end
assert(firstCell.state=='LATENT' or firstCell.state=='PRODUCTIVE','first infection never converted')
assert(firstCell.contactVisualAnchor and firstCell.everPlayerContact)
''')
check('Split/switch/merge and current controlled death fallback',r'''
local original=w.player;w:SetAim(1,0)
assert(w:Split());assert(#w.swarms==2)
local other=w.swarms[2];assert(w:SwitchControl(other.id));assert(w.player.id==other.id)
original.launchTimer,other.launchTimer,original.mergeGrace,other.mergeGrace=0,0,0,0
local x,y=m.spawn.x,m.spawn.y
original.x,original.y=x,y;other.x,other.y=x+.05,y
assert(w:_Merge(original,other));assert(#w.swarms==1 and w.player==w.swarms[1])
w.splitCooldown=0;w.player.splitCooldown=0
assert(w:Split());local selected=w.player;local survivor=w.swarms[2]
w:DamageSwarm(selected.id,selected.mass)
assert(#w.swarms==1 and w.player.id==survivor.id and w.currentControlledSwarmId==survivor.id)
''')
check('Offscreen node continues latency/release; legal particles and boundaries',r'''
local far=m.regions[5];w.player.x,w.player.y=far.x,far.y;w:SetMovement(0,0)
local before=firstCell.releaseCount
for i=1,3600 do w:Update(1/60) end
assert(firstCell.releaseCount>before,'offscreen release stopped')
for _,s in ipairs(w.swarms) do assert(m:Contains(s.x,s.y,s.radius)) end
for _,v in ipairs(w.releasedViruses) do if v.state=='FREE' then assert(m:Contains(v.x,v.y,v.radius)) end end
w.config.immuneMax=8
''')
check('Flow calm zone, wall clipping, cap and ability override',r'''
for y=0,m.height-1 do for x=0,m.width-1 do
 local vx,vy=m:FlowAt(x+.5,y+.5,0)
 assert(vx*vx+vy*vy<=1.6^2+1e-10)
 if not m.floor[y+1][x+1] or (x+.5-m.spawn.x)^2+(y+.5-m.spawn.y)^2<25 then assert(vx==0 and vy==0) end
end end
local p=m.flowMarks[1];local vx,vy=m:FlowAt(p.x,p.y,0)
m.flowOverride={x=p.x,y=p.y,radius=4,ux=-1,uy=0,expiresAt=10}
local ax,ay=m:FlowAt(p.x,p.y,1);assert(math.abs(ax*ax+ay*ay-vx*vx-vy*vy)<1e-9)
m.flowOverride=nil
''')
check('Animated arrows follow seeded paths; production flow changes realised speed',r'''
local Visual=require('Game.FlatMapVisual')
local moving=false
for _,mark in ipairs(m.flowMarks) do
 local x,y=Visual.MarkPosition(m,mark,0);local nx,ny=Visual.MarkPosition(m,mark,.4)
 if (nx-x)^2+(ny-y)^2>.01 then moving=true end
end
assert(moving,'arrows are static')
local sx,sy
for _,mark in ipairs(m.flowMarks) do
 local vx,vy=m:FlowAt(mark.x,mark.y,0)
 if vx*vx+vy*vy>1.2^2 and m:Contains(mark.x,mark.y,2) then sx,sy=mark.x,mark.y;break end
end
assert(sx,'No legal strong flow sample')
local vx,vy=m:FlowAt(sx,sy,0);local flow=math.sqrt(vx*vx+vy*vy);local ux,uy=vx/flow,vy/flow
local p=w.player;p.x,p.y=sx,sy;p.launchTimer=0;p.mass=30
local speed=math.max(w.config.minSpeed,w.config.baseSpeed/math.sqrt(p.mass/w.config.initialMass))
local function displacement(sign)
 p.x,p.y,p.vx,p.vy=sx,sy,ux*speed*sign,uy*speed*sign
 w:SetMovement(ux*sign,uy*sign);w:_MoveGroups(1/60)
 return ((p.x-sx)*ux+(p.y-sy)*uy)*60*sign
end
FLOW_FORWARD=displacement(1);FLOW_AGAINST=displacement(-1);FLOW_STILL=speed
assert(FLOW_FORWARD>FLOW_STILL*1.35 and FLOW_AGAINST<FLOW_STILL*.65 and FLOW_AGAINST>0,'Flow speed effect too weak or traps player')
''')
# Measure normal updates separately from generation and screenshot capture.
lua.execute('bench=World.New("UPPER_AIRWAY");function benchFrame() bench:Update(1/60) end')
times=[]
for _ in range(600):
    began=time.perf_counter();lua.globals().benchFrame();times.append((time.perf_counter()-began)*1000)
times.sort()
report=dict(passed=True,environment=dict(os=platform.platform(),python=platform.python_version(),lua='Lupa Lua5.4'),
    seed=m.seed,version=m.generationVersion,width=m.width,height=m.height,cells=len(m.cells),
    generation_ms=m.generationMs,route_ms=list(lua.globals().ROUTE_TIMES.values()),checks=checks,
    flow_speed_mps=dict(forward=lua.globals().FLOW_FORWARD,against=lua.globals().FLOW_AGAINST,still=lua.globals().FLOW_STILL),
    simulation=dict(frames=600,p50_ms=times[300],p95_ms=times[570],max_ms=times[-1],over50ms=sum(t>50 for t in times),
        scope='Real Lua world Update, 960 cells/initial immunes; excludes engine rendering, UI and screenshot cost'),
    runtime_snapshot_sha256=hashlib.sha256(m.Snapshot(m).encode()).hexdigest())
(OUT/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
