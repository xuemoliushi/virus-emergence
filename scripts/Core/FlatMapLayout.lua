-- Candidate v2 geometry: staggered faceted regions, oblique routes and local flow.
-- The one-metre solid/open raster stays authoritative for future live collision.
local Layout = {}
local TAU = math.pi*2
local function clamp(x,a,b) return math.max(a,math.min(b,x)) end
local function distance(a,b) return math.sqrt((a.x-b.x)^2+(a.y-b.y)^2) end
local function inside(x,y,points)
    local hit=false
    local j=#points
    for i,p in ipairs(points) do
        local q=points[j]
        if (p.y>y)~=(q.y>y) and x<(q.x-p.x)*(y-p.y)/(q.y-p.y)+p.x then hit=not hit end
        j=i
    end
    return hit
end
local function nearest(x,y,a,b)
    local dx,dy=b.x-a.x,b.y-a.y
    local t=clamp(((x-a.x)*dx+(y-a.y)*dy)/(dx*dx+dy*dy),0,1)
    return (x-a.x-dx*t)^2+(y-a.y-dy*t)^2,t
end
local function pathLength(points)
    local n=0
    for i=1,#points-1 do n=n+distance(points[i],points[i+1]) end
    return n
end
local function slice(points,start,finish)
    local result,total={},0
    for i=1,#points-1 do
        local a,b=points[i],points[i+1]
        local length=distance(a,b)
        local low,high=math.max(start,total),math.min(finish,total+length)
        if high>low then
            if #result==0 then
                local t=(low-total)/length
                result[1]={x=a.x+(b.x-a.x)*t,y=a.y+(b.y-a.y)*t}
            end
            local t=(high-total)/length
            result[#result+1]={x=a.x+(b.x-a.x)*t,y=a.y+(b.y-a.y)*t}
        end
        total=total+length
    end
    return result
end

function Layout.Build(map,random,flowRandom)
    local cfg=map.config
    local border=cfg.borderWidth
    local function scan(minX,minY,maxX,maxY,predicate)
        for y=math.max(border,math.floor(minY)),math.min(map.height-border-1,math.floor(maxY)) do
            for x=math.max(border,math.floor(minX)),math.min(map.width-border-1,math.floor(maxX)) do
                if predicate(x+.5,y+.5) then map.floor[y+1][x+1]=true end
            end
        end
    end
    -- Strata avoid unvisited edge deserts; all centers, facets, sizes and angles
    -- are seed-dependent. Three/two/three staggered strata replace rectangular BSP.
    local anchors={{.18,.19},{.51,.14},{.82,.23},{.27,.48},{.72,.49},{.17,.78},{.49,.84},{.83,.79}}
    for id,p in ipairs(anchors) do
        local cx=(p[1]+(random()-.5)*.07)*map.width
        local cy=(p[2]+(random()-.5)*.07)*map.height
        local rx=(id==4 or id==5) and 15+random()*2 or 10+random()*4
        local ry=10+random()*4
        local angle=random()*TAU
        local points={}
        local count=7+math.floor(random()*3)
        local minX,minY,maxX,maxY=map.width,map.height,0,0
        for i=1,count do
            local theta=angle+(i-1)*TAU/count+(random()-.5)*.15
            local scale=.82+random()*.28
            local x=clamp(cx+math.cos(theta)*rx*scale,border+1,map.width-border-1)
            local y=clamp(cy+math.sin(theta)*ry*scale,border+1,map.height-border-1)
            points[i]={x=x,y=y}
            minX,minY,maxX,maxY=math.min(minX,x),math.min(minY,y),math.max(maxX,x),math.max(maxY,y)
        end
        map.rooms[id]={id=id,cx=cx,cy=cy,x=minX,y=minY,w=maxX-minX,h=maxY-minY,points=points}
        scan(minX,minY,maxX,maxY,function(x,y) return inside(x,y,points) end)
    end

    local edges={}
    for i=1,#map.rooms do for j=i+1,#map.rooms do
        local a,b=map.rooms[i],map.rooms[j]
        edges[#edges+1]={a=i,b=j,weight=((a.cx-b.cx)^2+(a.cy-b.cy)^2)*(.85+random()*.3)}
    end end
    table.sort(edges,function(a,b)
        if a.weight~=b.weight then return a.weight<b.weight end
        return a.a==b.a and a.b<b.b or a.a<b.a
    end)
    local parent={}
    for i=1,#map.rooms do parent[i]=i end
    local function root(i) while parent[i]~=i do i=parent[i] end;return i end
    local function connect(edge,extra)
        edge.used=true
        local a,b=map.rooms[edge.a],map.rooms[edge.b]
        local dx,dy=b.cx-a.cx,b.cy-a.cy
        local length=math.sqrt(dx*dx+dy*dy)
        local offset=(random()-.5)*12
        local points={{x=a.cx,y=a.cy},
            {x=clamp((a.cx+b.cx)/2-dy/length*offset,7,map.width-7),
             y=clamp((a.cy+b.cy)/2+dx/length*offset,7,map.height-7)},
            {x=b.cx,y=b.cy}}
        -- Dilate by half a grid diagonal: every square touching the intended
        -- 6m capsule is open, so raster stair steps never narrow oblique routes.
        local radius=cfg.corridorWidth/2+math.sqrt(.5)
        for i=1,#points-1 do
            local p,q=points[i],points[i+1]
            scan(math.min(p.x,q.x)-radius,math.min(p.y,q.y)-radius,
                math.max(p.x,q.x)+radius,math.max(p.y,q.y)+radius,
                function(x,y) return nearest(x,y,p,q)<=radius*radius end)
        end
        map.connections[#map.connections+1]={id=#map.connections+1,a=edge.a,b=edge.b,
            extra=extra,width=cfg.corridorWidth,points=points}
    end
    for _,edge in ipairs(edges) do
        local a,b=root(edge.a),root(edge.b)
        if a~=b then parent[b]=a;connect(edge,false) end
    end
    -- Prefer loops that cover as-yet single-route tree edges. This prevents all
    -- shortcuts clustering in the upper map while leaving lower regions as a
    -- long dead-end chain. Stable adjacency order supplies deterministic ties.
    local adjacent,looped={},{ }
    for i=1,#map.rooms do adjacent[i]={} end
    for _,c in ipairs(map.connections) do
        adjacent[c.a][#adjacent[c.a]+1]={room=c.b,id=c.id}
        adjacent[c.b][#adjacent[c.b]+1]={room=c.a,id=c.id}
    end
    local function treePath(current,target,previous)
        if current==target then return {} end
        for _,link in ipairs(adjacent[current]) do
            if link.room~=previous then
                local result=treePath(link.room,target,current)
                if result then result[#result+1]=link.id;return result end
            end
        end
    end
    local extras=0
    for i=1,cfg.extraConnections do
        local selected,path,score=nil,nil,-math.huge
        for _,edge in ipairs(edges) do
            if not edge.used then
                local route=treePath(edge.a,edge.b,0)
                local uncovered=0
                for _,id in ipairs(route) do if not looped[id] then uncovered=uncovered+1 end end
                local candidate=uncovered*1000000-edge.weight
                if candidate>score then selected,path,score=edge,route,candidate end
            end
        end
        assert(selected,'No distinct edge remains for an alternate route')
        for _,id in ipairs(path) do looped[id]=true end
        connect(selected,true);extras=extras+1
    end
    assert(#map.connections==10 and extras==3,'Cannot establish all oblique connections')
    local spawnRoom=map.rooms[1]
    map.spawn={x=spawnRoom.cx,y=spawnRoom.cy,roomId=spawnRoom.id,radius=cfg.playerRadius}
    assert(map:Contains(spawnRoom.cx,spawnRoom.cy,cfg.spawnCalmRadius),'Spawn calm zone does not fit')

    for _,connection in ipairs(map.connections) do
        local points={}
        for _,p in ipairs(connection.points) do points[#points+1]={x=p.x,y=p.y} end
        -- Main flow travels towards the lower map; extra shortcuts flow back up,
        -- creating different travel costs in the two directions of each loop.
        local reverse=points[1].y>points[#points].y
        if connection.extra then reverse=not reverse end
        if reverse then
            local reordered={}
            for i=#points,1,-1 do reordered[#reordered+1]=points[i] end
            points=reordered
        end
        local total=pathLength(points)
        local length=math.min(total-4,cfg.flowLengthMin+flowRandom()*(cfg.flowLengthMax-cfg.flowLengthMin))
        assert(length>=cfg.flowLengthMin,'Flow route is too short')
        local start=2+flowRandom()*(total-4-length)
        local kind=connection.extra and 'counter' or 'jet'
        local lo=connection.extra and cfg.counterSpeedMin or cfg.jetSpeedMin
        local hi=connection.extra and cfg.counterSpeedMax or cfg.jetSpeedMax
        map.flows[#map.flows+1]={id=#map.flows+1,kind=kind,connectionId=connection.id,
            points=slice(points,start,start+length),length=length,width=cfg.flowWidth,speed=lo+flowRandom()*(hi-lo)}
    end
    -- Two local circulation fields in open regions, with a calm center and an
    -- outer calm route. No random calls are needed when sampling these fields.
    for _,roomId in ipairs({4,7}) do
        local room=map.rooms[roomId]
        local radius=cfg.vortexRadius
        local valid=false
        for attempt=0,6 do
            valid=true
            for i=1,64 do
                local a=TAU*i/64
                if not map:Contains(room.cx+math.cos(a)*radius,room.cy+math.sin(a)*radius,cfg.vortexWidth/2+.1) then valid=false end
            end
            if valid then break end
            radius=radius-.25
        end
        assert(valid,'Cannot fit a circulation band in the open region')
        map.flows[#map.flows+1]={id=#map.flows+1,kind='vortex',roomId=roomId,
            cx=room.cx,cy=room.cy,ringRadius=radius,width=cfg.vortexWidth,
            speed=cfg.vortexSpeed,direction=flowRandom()<.5 and -1 or 1}
    end
    assert(#map.flows==cfg.flowCount,'Flow count does not match candidate configuration')
end

-- Same FlowAt interface as the live map, ready for later approved integration.
-- Additive local vectors have smooth side/end falloff and a speed cap; quiet
-- spawn and wall samples return zero. The preview itself does not move entities.
-- Geometry is static after generation. Keep the derived index outside map data
-- so snapshots, RNG and the approved geometry remain unchanged.
local flowIndexes=setmetatable({},{__mode="k"})
local FLOW_BUCKET_SIZE=2
local function flowIndex(map)
    local cached=flowIndexes[map]
    if cached and cached.source==map.flows and cached.count==#map.flows then return cached end
    local rows={}
    local function add(flow,segment,l,t,r,b)
        for by=math.floor(t/FLOW_BUCKET_SIZE),math.floor(b/FLOW_BUCKET_SIZE) do
            local row=rows[by]
            if not row then row={};rows[by]=row end
            for bx=math.floor(l/FLOW_BUCKET_SIZE),math.floor(r/FLOW_BUCKET_SIZE) do
                local bucket=row[bx]
                if not bucket then bucket={};row[bx]=bucket end
                local entry=bucket[#bucket]
                if not entry or entry.flow~=flow then
                    entry={flow=flow,segments={}};bucket[#bucket+1]=entry
                end
                if segment then entry.segments[#entry.segments+1]=segment end
            end
        end
    end
    for _,f in ipairs(map.flows) do
        local half=f.width/2
        if f.kind=='vortex' then
            local reach=f.ringRadius+half
            add(f,nil,f.cx-reach,f.cy-reach,f.cx+reach,f.cy+reach)
        else
            local total=0
            for i=1,#f.points-1 do
                local a,b=f.points[i],f.points[i+1]
                local dx,dy=b.x-a.x,b.y-a.y
                local length=distance(a,b)
                local segment={x=a.x,y=a.y,dx=dx,dy=dy,length=length,
                    length2=dx*dx+dy*dy,along=total,ux=dx/length,uy=dy/length}
                -- Conservative AABB: every segment with distance < half is in
                -- this bucket. Original segment/flow order preserves ties/sums.
                add(f,segment,math.min(a.x,b.x)-half,math.min(a.y,b.y)-half,
                    math.max(a.x,b.x)+half,math.max(a.y,b.y)+half)
                total=total+length
            end
        end
    end
    cached={source=map.flows,count=#map.flows,rows=rows}
    flowIndexes[map]=cached
    return cached
end

-- Call after editing path points/widths in place. Replacing the flows array or
-- changing its count is detected automatically; speed/direction are read live.
function Layout.InvalidateFlowIndex(map) flowIndexes[map]=nil end

---@return number, number
function Layout.FlowAt(map,x,y)
    local cfg=map.config
    if not map:Contains(x,y,0) or (x-map.spawn.x)^2+(y-map.spawn.y)^2<=cfg.spawnCalmRadius^2 then return 0,0 end
    local vx,vy=0,0
    local index=flowIndex(map)
    local row=index.rows[math.floor(y/FLOW_BUCKET_SIZE)]
    local bucket=row and row[math.floor(x/FLOW_BUCKET_SIZE)]
    if not bucket then return 0,0 end
    for _,entry in ipairs(bucket) do
        local f=entry.flow
        local half=f.width/2
        if f.kind=='vortex' then
            local dx,dy=x-f.cx,y-f.cy
            local r=math.sqrt(dx*dx+dy*dy)
            local gap=math.abs(r-f.ringRadius)
            if gap<half and r>0 then
                local strength=f.speed*(1-(gap/half)^2)^2*f.direction
                vx,vy=vx-dy/r*strength,vy+dx/r*strength
            end
        else
            local best,along,ux,uy=math.huge,0,0,0
            for _,segment in ipairs(entry.segments) do
                local t=clamp(((x-segment.x)*segment.dx+(y-segment.y)*segment.dy)/segment.length2,0,1)
                local d=(x-segment.x-segment.dx*t)^2+(y-segment.y-segment.dy*t)^2
                if d<best then best,along,ux,uy=d,segment.along+t*segment.length,segment.ux,segment.uy end
            end
            if best<half*half then
                local strength=f.speed*(1-best/(half*half))^2*math.max(0,math.min(1,along/2,(f.length-along)/2))
                vx,vy=vx+ux*strength,vy+uy*strength
            end
        end
    end
    local speed=math.sqrt(vx*vx+vy*vy)
    if speed>cfg.maxFlowSpeed then vx,vy=vx/speed*cfg.maxFlowSpeed,vy/speed*cfg.maxFlowSpeed end
    return vx,vy
end

return Layout
