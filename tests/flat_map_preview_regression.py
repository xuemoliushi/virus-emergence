"""Real candidate Lua data; independent geometry checks, no gameplay integration."""
from collections import deque
from pathlib import Path
import hashlib,json,math,sys,time
from lua_test_runtime import LuaRuntime

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'validation/flat-map-preview'
OUT.mkdir(parents=True,exist_ok=True)
lua=LuaRuntime(unpack_returned_tuples=True)
lua.globals().SCRIPT_PATH=str(ROOT/'scripts/?.lua').replace('\\','/')
lua.execute("package.path=SCRIPT_PATH..';'..package.path;Map=require('Core.FlatMapPreview');Config=require('Core.FlatMapConfig')")

def plain(t):
    if not hasattr(t,'items'):return t
    if set(t.keys())==set(range(1,len(t)+1)):
        return [plain(t[i])for i in range(1,len(t)+1)]
    return {k:plain(v) for k,v in t.items()}

def export(m):
    return dict(mapKind=m.mapKind,generationVersion=m.generationVersion,seed=m.seed,
        width=m.width,height=m.height,gridSize=1,wallEncoding='floorRows: 0=solid black wall, 1=open; row0 at y=0; metre cells',
        config=plain(m.config),floorRows=[m.floorRows[i]for i in range(1,len(m.floorRows)+1)],
        rooms=[plain(m.rooms[i])for i in range(1,len(m.rooms)+1)],
        connections=[dict(id=c.id,a=c.a,b=c.b,extra=c.extra,width=c.width,
            points=[dict(x=c.points[i].x,y=c.points[i].y)for i in range(1,len(c.points)+1)])for c in [m.connections[i]for i in range(1,len(m.connections)+1)]],
        flows=[plain(m.flows[i])for i in range(1,len(m.flows)+1)],
        spawn=plain(m.spawn),cells=[plain(m.cells[i])for i in range(1,len(m.cells)+1)],
        floorArea=m.floorArea,walkableRatio=m.walkableRatio,maxTargetDistance=m.maxTargetDistance,
        fallbackCount=m.fallbackCount,coverageRepairs=m.coverageRepairs,generationAttempt=m.generationAttempt,
        outerBoundary=plain(m.outerBoundary),obstacles=plain(m.obstacles),flowSystems=plain(m.flowSystems),
        bays=plain(m.bays),crossFlows=plain(m.crossFlows),majorRoutes=plain(m.majorRoutes),maxLocalDensity=m.maxLocalDensity)

def validate(data):
    w,h=data['width'],data['height'];rows=data['floorRows'];cfg=data['config']
    def open_at(x,y):return 0<=x<w and 0<=y<h and rows[y][x]=='1'
    def circle(x,y,r):
        if x-r<0 or y-r<0 or x+r>=w or y+r>=h:return False
        for gy in range(math.floor(y-r),math.floor(y+r)+1):
            for gx in range(math.floor(x-r),math.floor(x+r)+1):
                if not open_at(gx,gy):
                    nx=max(gx,min(gx+1,x));ny=max(gy,min(gy+1,y))
                    if (nx-x)**2+(ny-y)**2<=r*r+1e-12:return False
        return True
    def flood(allowed,origin):
        visited={origin};queue=deque([origin])
        while queue:
            x,y=queue.popleft()
            for p in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                if p in allowed and p not in visited:visited.add(p);queue.append(p)
        return visited
    assert data['generationVersion']==cfg['mapGenerationVersion'] and (w,h)==(120,144)
    assert data['rooms']==[] and data['connections']==[], 'candidate still uses a room graph'
    assert len(data['cells'])==cfg['cellCount'] and len(data['obstacles'])==18
    assert [sum(o['kind']==kind for o in data['obstacles'])for kind in ('island','ridge')]==[10,8]
    assert [f['kind']for f in data['flowSystems']]==['fork','fork','merge','counter_loop']
    assert len(data['flows'])==20 and sum(f['kind']=='vortex'for f in data['flows'])==3
    assert len(data['bays'])==12 and 1<=data['generationAttempt']<=8
    assert sum(c['placement']=='coverage'for c in data['cells'])==cfg['coverageCellCount']
    assert sum(c['placement']=='supplement'for c in data['cells'])==120
    for bay in data['bays']:
        supplements=[c for c in data['cells']if c['bayId']==bay['id']]
        assert len(supplements)==10
        assert all(math.hypot(c['x']-bay['x'],c['y']-bay['y'])<=bay['radius']+1e-9 for c in supplements)
        assert circle(bay['x'],bay['y'],bay['radius']+.2)
        for other in data['bays'][:bay['id']-1]:
            assert math.hypot(bay['x']-other['x'],bay['y']-other['y'])>=cfg['bayMinDistance']
    # Verify square-to-square >=6m separation, independently of the generator's
    # reserve grid, including the exterior. Tile ownership also prevents overlap.
    owner={}
    for obstacle in data['obstacles']:
        assert obstacle['tiles']
        for tile in obstacle['tiles']:
            p=(tile['x'],tile['y']);assert p not in owner and not open_at(*p)
            owner[p]=obstacle['id']
    for (x,y),identity in owner.items():
        for dy in range(-7,8):
            for dx in range(-7,8):
                if max(0,abs(dx)-1)**2+max(0,abs(dy)-1)**2<=36:
                    q=(x+dx,y+dy)
                    assert open_at(*q)or owner.get(q)==identity,'less than 6m wall separation'
    # Flow graph semantics: branches share an inlet/outlet; loop route endpoints
    # form a real return route, rather than just an illustrative pair of arrows.
    def point_equal(a,b):return math.hypot(a['x']-b['x'],a['y']-b['y'])<1e-8
    for system in data['flowSystems']:
        fields=[data['flows'][i-1]for i in system['flowIds']]
        if system['kind']=='fork':
            assert point_equal(fields[0]['points'][-1],fields[1]['points'][0])
            assert point_equal(fields[1]['points'][0],fields[2]['points'][0])
        elif system['kind']=='merge':
            assert point_equal(fields[0]['points'][0],fields[1]['points'][-1])
            assert point_equal(fields[1]['points'][-1],fields[2]['points'][-1])
        else:
            assert point_equal(fields[0]['points'][-1],fields[1]['points'][0])
            assert point_equal(fields[0]['points'][0],fields[1]['points'][-1])
    cross=[data['flows'][r['flowId']-1]for r in data['crossFlows']]
    assert len(cross)==6 and all(f['scope']=='open_ground'and f['length']>=18 for f in cross)
    assert point_equal(cross[0]['points'][-1],cross[1]['points'][0])
    assert point_equal(cross[2]['points'][-1],cross[3]['points'][0])
    assert point_equal(cross[0]['points'][-1],cross[2]['points'][-1])
    # Through-flows must actually traverse quiet ground away from island rings.
    outside=total=0
    islands=[o for o in data['obstacles']if o['kind']=='island']
    for f in cross:
        for a,b in zip(f['points'],f['points'][1:]):
            n=math.ceil(math.hypot(b['x']-a['x'],b['y']-a['y'])*2)
            for i in range(n):
                t=(i+.5)/n;x=a['x']+(b['x']-a['x'])*t;y=a['y']+(b['y']-a['y'])*t
                total+=1
                outside+=all(math.hypot(x-o['cx'],y-o['cy'])>o['boundRadius']+7 for o in islands)
    assert outside/total>=.4,'through-flows remain concentrated around islands'
    all_floor={(x,y)for y in range(h)for x in range(w)if open_at(x,y)}
    assert len(flood(all_floor,next(iter(all_floor))))==len(all_floor),'isolated floor'
    for y in range(h):
        for x in range(w):
            if x<2 or y<2 or x>=w-2 or y>=h-2:assert not open_at(x,y),'outer wall breach'
    start=data['spawn'];assert circle(start['x'],start['y'],cfg['spawnCalmRadius'])
    # Half-metre navigation graph, independently eroded by the exact body radius.
    safe={(x,y)for y in range(h*2)for x in range(w*2)if circle(x*.5+.25,y*.5+.25,cfg['maxSwarmRadius'])}
    origin=min(safe,key=lambda p:(p[0]*.5+.25-start['x'])**2+(p[1]*.5+.25-start['y'])**2)
    reachable=flood(safe,origin)
    assert reachable==safe,'largest swarm navigation has a disconnected pocket'
    for c in data['cells']:
        assert circle(c['x'],c['y'],c['radius']) and circle(c['x'],c['y'],cfg['playerRadius'])
        d=math.hypot(c['x']-start['x'],c['y']-start['y'])
        assert d>=cfg['playerRadius']+c['radius']+cfg['cellGap']
        if c['id']>3:assert d>cfg['spawnSafeRadius']
        for q in data['cells'][:c['id']-1]:
            assert math.hypot(c['x']-q['x'],c['y']-q['y'])>=c['radius']+q['radius']+cfg['cellGap']-1e-9
            if c['placement']=='supplement'or q['placement']=='supplement':
                assert math.hypot(c['x']-q['x'],c['y']-q['y'])>=cfg['supplementMinDistance']-1e-9
    assert sum(math.hypot(c['x']-start['x'],c['y']-start['y'])<=2 for c in data['cells'])==3
    for ch in data['majorRoutes']:
        assert ch['width']==6
        for a,b in zip(ch['points'],ch['points'][1:]):
            n=math.ceil(math.hypot(a['x']-b['x'],a['y']-b['y'])*4)
            for i in range(n+1):
                t=i/n;assert circle(a['x']+(b['x']-a['x'])*t,a['y']+(b['y']-a['y'])*t,3),'less than 6m corridor clearance'
    for f in data['flows']:
        if f['kind']=='vortex':
            assert 7<=f['ringRadius']<=11 and f['direction']in(-1,1)
            for i in range(128):
                a=math.tau*i/128
                assert circle(f['cx']+math.cos(a)*f['ringRadius'],f['cy']+math.sin(a)*f['ringRadius'],f['width']/2+.05)
        else:
            assert f['length']>=6-1e-8 and f['width']==3
            assert abs(sum(math.hypot(a['x']-b['x'],a['y']-b['y'])for a,b in zip(f['points'],f['points'][1:]))-f['length'])<1e-8
            for a,b in zip(f['points'],f['points'][1:]):
                n=math.ceil(math.hypot(a['x']-b['x'],a['y']-b['y'])*4)
                for i in range(n+1):
                    t=i/n;x=a['x']+(b['x']-a['x'])*t;y=a['y']+(b['y']-a['y'])*t
                    assert circle(x,y,f['width']/2+.05),'flow band crosses a wall'
    max_gap=max(min(math.hypot(x+.5-c['x'],y+.5-c['y'])for c in data['cells'])for x,y in all_floor)
    assert max_gap<=6 and abs(max_gap-data['maxTargetDistance'])<1e-8
    max_density=max(sum((x+.5-c['x'])**2+(y+.5-c['y'])**2<=cfg['densityRadius']**2 for c in data['cells'])for y in range(h)for x in range(w))
    assert max_density<=cfg['densityCap']and max_density==data['maxLocalDensity']
    return dict(maxTargetDistance=max_gap,floorArea=len(all_floor),walkableRatio=data['walkableRatio'],
        largestSwarmSafeSamples=len(safe),coverageRepairs=data['coverageRepairs'],fallbackCount=data['fallbackCount'],
        generationAttempt=data['generationAttempt'],maxLocalDensity=max_density,openGroundFlowFraction=outside/total)

def verify_field(m,data):
    """Independently evaluate local vectors, including overlap, taper and clipping."""
    def field(x,y):
        start=data['spawn'];cfg=data['config']
        if not m.Contains(m,x,y,0)or math.hypot(x-start['x'],y-start['y'])<=cfg['spawnCalmRadius']:return 0.,0.
        vx=vy=0.
        for f in data['flows']:
            half=f['width']/2
            if f['kind']=='vortex':
                dx=x-f['cx'];dy=y-f['cy'];r=math.hypot(dx,dy);gap=abs(r-f['ringRadius'])
                if gap<half and r>0:
                    force=f['speed']*(1-(gap/half)**2)**2*f['direction'];vx-=dy/r*force;vy+=dx/r*force
            else:
                best=float('inf');along=total=ux=uy=0.
                for a,b in zip(f['points'],f['points'][1:]):
                    dx=b['x']-a['x'];dy=b['y']-a['y'];length=math.hypot(dx,dy)
                    t=max(0,min(1,((x-a['x'])*dx+(y-a['y'])*dy)/(dx*dx+dy*dy)))
                    dist=(x-a['x']-dx*t)**2+(y-a['y']-dy*t)**2
                    if dist<best:best=dist;along=total+t*length;ux=dx/length;uy=dy/length
                    total+=length
                if best<half*half:
                    force=f['speed']*(1-best/(half*half))**2*max(0,min(1,along/2,(f['length']-along)/2))
                    vx+=ux*force;vy+=uy*force
        speed=math.hypot(vx,vy)
        if speed>cfg['maxFlowSpeed']:vx*=cfg['maxFlowSpeed']/speed;vy*=cfg['maxFlowSpeed']/speed
        return vx,vy
    active=0;peak=0
    for y in range(data['height']):
        for x in range(data['width']):
            a=m.FlowAt(m,x+.5,y+.5,0);b=field(x+.5,y+.5)
            assert math.hypot(a[0]-b[0],a[1]-b[1])<1e-8,(x,y,a,b)
            speed=math.hypot(*a);assert speed<=data['config']['maxFlowSpeed']+1e-9
            peak=max(peak,speed);active+=speed>.01
    assert active>200,'flow zones cover too little space'
    return dict(flowActiveSamples=active,peakFlowSpeed=peak)

results=[]
for seed in [314159,1,2,3,17,73,999,20261012,2147483646,'平面探索']:
    opts=lua.table_from(dict(mapSeed=seed))
    start=time.perf_counter();m=lua.globals().Map.New(opts);elapsed=(time.perf_counter()-start)*1000
    repeat=lua.globals().Map.New(opts)
    snapshot=m.Snapshot(m)
    assert snapshot==repeat.Snapshot(repeat),'same seed differs'
    data=export(m)
    assert data==export(repeat),'complete exported initial data differs'
    digest=hashlib.sha256(snapshot.encode()).hexdigest()
    result=dict(seed=seed,actualSeed=m.seed,sha256=digest,generationMs=elapsed,**validate(data),**verify_field(m,data))
    results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
    if seed==314159:
        (OUT/f'map-314159-v{m.generationVersion}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True),encoding='utf-8')
        (OUT/f'map-314159-v{m.generationVersion}.snapshot.txt').write_text(snapshot,encoding='utf-8')
assert len({r['sha256']for r in results})==10
lua.execute('''
math.randomseed(73);local expected=math.random()
math.randomseed(73);Map.New();assert(math.random()==expected)
local World=require('Core.SwarmWorld');local w=World.New();local saved=w._rng
local nextValue=w:_Random();w._rng=saved;Map.New();assert(w._rng==saved and w:_Random()==nextValue)
local explicit=Map.New({mapSeed='平面探索'});assert(explicit.seed==require('Core.MapRandom').Normalize('平面探索'))
local ok=pcall(Map.New,{coverageMaxDistance=.1,generationAttempts=1});assert(not ok,'impossible coverage silently accepted')
local bounded,why=pcall(Map.New,{obstacleAttempts=1,generationAttempts=1});assert(not bounded and tostring(why):find('bounded generation attempts'),'bounded rejection missing')
local baseline=Map.New();local altered=Map.New({vortexSpeed=.8})
for i,row in ipairs(baseline.floorRows) do assert(row==altered.floorRows[i]) end
for i,c in ipairs(baseline.cells) do local q=altered.cells[i];assert(c.x==q.x and c.y==q.y and c.radius==q.radius and c.rotation==q.rotation) end
assert(baseline:FlowAt(baseline.spawn.x,baseline.spawn.y)==0)
''')
(OUT/f'checks-v{m.generationVersion}.json').write_text(json.dumps(dict(passed=True,seeds=results,
    checks=['full canonical repeated snapshots','10 distinct seeds','2m perimeter wall','all floor connected',
        'largest 1.35m swarm safe space connected; all major routes fit a 3m radius','spawn and exact cell spacing',
        'continuous ground, 10 islands and 8 ridges, >=6m separation','two forks, one merge, one counter loop, three vortices and six open-ground streams','configured coverage cells + 120 supplements in 12 separated patches; >=2.4m supplement spacing; <=9 cells per 4m radius at metre samples',
        'independent local flow field, speed cap and calm spawn','flow settings do not change geometry or cells',
        '1m floor coverage <=6m','global and simulation RNG isolation','explicit invalid-config rejection']),ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS: 10 seeded flat maps; full data, connectivity, spacing, flow, coverage and RNG isolation')
