local LoadJob = require("Core.LoadJob")
-- Candidate v4: continuous ground, through-flows and bounded cell density.
local M={}
local TAU=math.pi*2
local function inside(x,y,points)
    local result=false
    local j=#points
    for i,p in ipairs(points) do
        local q=points[j]
        if (p.y>y)~=(q.y>y) and x<(q.x-p.x)*(y-p.y)/(q.y-p.y)+p.x then result=not result end
        j=i
    end
    return result
end
local function dist(a,b) return math.sqrt((a.x-b.x)^2+(a.y-b.y)^2) end
local function near(x,y,a,b)
    local dx,dy=b.x-a.x,b.y-a.y
    local t=math.max(0,math.min(1,((x-a.x)*dx+(y-a.y)*dy)/(dx*dx+dy*dy)))
    return (x-a.x-dx*t)^2+(y-a.y-dy*t)^2
end
local function length(points)
    local n=0
    for i=1,#points-1 do n=n+dist(points[i],points[i+1]) end
    return n
end
local function reverse(points)
    local result={}
    for i=#points,1,-1 do result[#result+1]=points[i] end
    return result
end
local function legalPath(map,points,radius)
    for i=1,#points-1 do
        local a,b=points[i],points[i+1]
        local n=math.ceil(dist(a,b)*4)
        for step=0,n do
            LoadJob.Checkpoint()
            local t=step/n
            if not map:Contains(a.x+(b.x-a.x)*t,a.y+(b.y-a.y)*t,radius) then return false end
        end
    end
    return true
end
local function flood(map,radius)
    local allowed,count={},0
    local w,h=map.width,map.height
    for y=0,h-1 do LoadJob.Checkpoint(); for x=0,w-1 do
        if map:Contains(x+.5,y+.5,radius) then allowed[y*w+x+1]=true;count=count+1 end
    end end
    local origin=math.floor(map.spawn.y)*w+math.floor(map.spawn.x)+1
    assert(allowed[origin],'Spawn does not fit navigation radius')
    local queue,seen,head={origin},{[origin]=true},1
    while head<=#queue do LoadJob.Checkpoint();
        local id=queue[head];head=head+1
        local x,y=(id-1)%w,math.floor((id-1)/w)
        for _,d in ipairs({{1,0},{0,1},{-1,0},{0,-1}}) do
            local nx,ny=x+d[1],y+d[2]
            local nextId=ny*w+nx+1
            if nx>=0 and nx<w and ny>=0 and ny<h and allowed[nextId] and not seen[nextId] then
                seen[nextId]=true;queue[#queue+1]=nextId
            end
        end
    end
    assert(#queue==count,'Continuous ground has an isolated navigation pocket')
    return count
end

function M.Build(map,random,flowRandom)
    local cfg,w,h=map.config,map.width,map.height
    map.obstacles,map.flowSystems,map.bays,map.majorRoutes,map.crossFlows={},{},{},{},{}
    -- A clipped, asymmetric outer polygon gives oblique shoulders, not an organ.
    local inset=cfg.borderWidth+2
    local cuts={}
    for i=1,8 do cuts[i]=5+random()*8 end
    map.outerBoundary={{x=inset+cuts[1],y=inset},{x=w-inset-cuts[2],y=inset},
        {x=w-inset,y=inset+cuts[3]},{x=w-inset,y=h-inset-cuts[4]},
        {x=w-inset-cuts[5],y=h-inset},{x=inset+cuts[6],y=h-inset},
        {x=inset,y=h-inset-cuts[7]},{x=inset,y=inset+cuts[8]}}
    for y=0,h-1 do LoadJob.Checkpoint(); for x=0,w-1 do map.floor[y+1][x+1]=inside(x+.5,y+.5,map.outerBoundary) end end
    map.spawn={x=14.5+random()*4,y=14.5+random()*4,roomId=0,radius=cfg.playerRadius}
    assert(map:Contains(map.spawn.x,map.spawn.y,cfg.spawnCalmRadius),'Outer boundary overlaps spawn calm area')
    local reserved={}
    for y=1,h do reserved[y]={} end
    local function reserve(cells,gap)
        local span=math.ceil(gap)+1
        for _,c in ipairs(cells) do LoadJob.Checkpoint();
            for dy=-span,span do for dx=-span,span do
                -- Exact distance between solid metre squares, conservatively
                -- reject tangency as well, preserving >=6m walkable passages.
                local gx,gy=math.max(0,math.abs(dx)-1),math.max(0,math.abs(dy)-1)
                local x,y=c.x+dx,c.y+dy
                if gx*gx+gy*gy<=gap*gap and x>=0 and x<w and y>=0 and y<h then reserved[y+1][x+1]=true end
            end end
        end
    end
    -- Only boundary-facing solid tiles need their margins reserved.
    local boundary={}
    for y=1,h-2 do LoadJob.Checkpoint(); for x=1,w-2 do
        if not map.floor[y+1][x+1] and (map.floor[y][x+1] or map.floor[y+2][x+1] or map.floor[y+1][x] or map.floor[y+1][x+2]) then
            boundary[#boundary+1]={x=x,y=y}
        end
    end end
    reserve(boundary,6)
    -- Distribute local flow systems across the whole ground without making
    -- these strata into rooms. Obstacle centers remain randomly jittered.
    local flowStrata={{.28,.25},{.72,.25},{.26,.68},{.74,.67},
        {.42,.49},{.78,.48},{.51,.86}}
    local function propose(kind,id)
        local cx=17+random()*(w-34)
        local cy=17+random()*(h-34)
        if kind=='island' and id<=7 then
            cx=(flowStrata[id][1]+(random()-.5)*.20)*w
            cy=(flowStrata[id][2]+(random()-.5)*.16)*h
        end
        local angle=random()*TAU
        -- All ridges are visibly oblique, without replacing stair steps in art.
        if kind=='ridge' then angle=(random()<.5 and 1 or -1)*(.35+random()*.8) end
        local item={id=id,kind=kind,cx=cx,cy=cy,angle=angle}
        local radius
        if kind=='island' then
            radius=(id<=4 and 5 or 3.5)+random()*2
            item.points={}
            local n=7+math.floor(random()*3)
            for i=1,n do
                local theta=angle+(i-1)*TAU/n
                local r=radius*(.78+random()*.22)
                item.points[i]={x=cx+math.cos(theta)*r,y=cy+math.sin(theta)*r}
            end
            item.boundRadius=radius
        else
            local size=12+random()*12
            local width=2.5+random()*2
            local dx,dy=math.cos(angle),math.sin(angle)
            item.width=width
            item.points={{x=cx-dx*size/2,y=cy-dy*size/2},
                {x=cx-dy*(random()-.5)*4,y=cy+dx*(random()-.5)*4},
                {x=cx+dx*size/2,y=cy+dy*size/2}}
            radius=size/2+width
            item.boundRadius=radius
        end
        local cells={}
        for y=math.max(0,math.floor(cy-radius-1)),math.min(h-1,math.ceil(cy+radius+1)) do
            for x=math.max(0,math.floor(cx-radius-1)),math.min(w-1,math.ceil(cx+radius+1)) do
                local occupied=kind=='island' and inside(x+.5,y+.5,item.points)
                if kind=='ridge' then
                    for i=1,#item.points-1 do if near(x+.5,y+.5,item.points[i],item.points[i+1])<=(item.width/2)^2 then occupied=true end end
                end
                if occupied then
                    if reserved[y+1][x+1] or not map.floor[y+1][x+1]
                        or (x+.5-map.spawn.x)^2+(y+.5-map.spawn.y)^2<12^2 then return nil end
                    cells[#cells+1]={x=x,y=y}
                end
            end
        end
        if #cells<10 then return nil end
        -- Flow-system islands need a complete legal 6m bypass ring and enough
        -- quiet space for the inlet/outlet. This is tested before committing.
        if kind=='island' and id<=7 then
            local ring=radius+4.6
            for i=1,96 do
                local a=TAU*i/96
                if not map:Contains(cx+math.cos(a)*ring,cy+math.sin(a)*ring,3.1) then return nil end
            end
        end
        item.tiles=cells
        return item
    end
    for id=1,cfg.islandCount+cfg.ridgeCount do
        local kind=id<=cfg.islandCount and 'island' or 'ridge'
        local placed=false
        for attempt=1,cfg.obstacleAttempts do LoadJob.Checkpoint();
            local item=propose(kind,id)
            if item then
                map.obstacles[id]=item
                for _,c in ipairs(item.tiles) do map.floor[c.y+1][c.x+1]=false end
                reserve(item.tiles,id<=4 and 10 or id<=7 and 9 or 6)
                placed=true;break
            end
        end
        assert(placed,'Obstacle placement exhausted at '..kind..'#'..id)
    end
    map.navigationSamples=flood(map,cfg.maxSwarmRadius)
    map.floorSamples=flood(map,0)
    M.Flows(map,flowRandom)
end

function M.Flows(map,random)
    local cfg=map.config
    local function add(kind,points,systemId)
        assert(legalPath(map,points,3.05),'Flow route lacks 6m continuous clearance')
        local f={id=#map.flows+1,kind=kind,points=points,width=cfg.flowWidth,
            length=length(points),speed=kind=='counter' and cfg.counterSpeedMin+random()*(cfg.counterSpeedMax-cfg.counterSpeedMin)
                or cfg.jetSpeedMin+random()*(cfg.jetSpeedMax-cfg.jetSpeedMin),systemId=systemId}
        map.flows[#map.flows+1]=f
        map.majorRoutes[#map.majorRoutes+1]={id=#map.majorRoutes+1,width=6,points=points,systemId=systemId}
        return f.id
    end
    local function arc(o,r,start,finish)
        local result={}
        local n=math.ceil(math.abs(finish-start)*r*.5)
        for i=0,n do
            local a=start+(finish-start)*i/n
            result[#result+1]={x=o.cx+math.cos(a)*r,y=o.cy+math.sin(a)*r}
        end
        return result
    end
    for id=1,4 do
        local o=map.obstacles[id]
        local r=o.boundRadius+4.6
        local kind=id<=2 and 'fork' or id==3 and 'merge' or 'counter_loop'
        local system={id=id,kind=kind,obstacleId=id,cx=o.cx,cy=o.cy,flowIds={}}
        local phase=random()*TAU
        local valid=false
        local upper,lower,trunk={},{},{}
        for attempt=0,11 do
            local a=phase+attempt*TAU/12
            upper=arc(o,r,a+math.pi,a+.35)
            lower=arc(o,r,a+math.pi,a+TAU-.35)
            local endPoint=upper[1]
            trunk={{x=endPoint.x+math.cos(a+math.pi)*6,y=endPoint.y+math.sin(a+math.pi)*6},endPoint}
            if legalPath(map,upper,3.05) and legalPath(map,lower,3.05) and (id==4 or legalPath(map,trunk,3.05)) then valid=true;break end
        end
        assert(valid,'Cannot fit the split/merge flow system')
        if kind=='merge' then
            upper,lower,trunk=reverse(upper),reverse(lower),reverse(trunk)
        end
        if kind=='counter_loop' then
            -- Complementary semicircles carry opposite travel directions on
            -- either side of the wall; joined endpoints form a return loop.
            local a=phase
            upper=arc(o,r,a+math.pi,a)
            lower=arc(o,r,a+TAU,a+math.pi)
            system.flowIds={add('jet',upper,id),add('counter',lower,id)}
        else
            system.flowIds={add('jet',trunk,id),add('jet',upper,id),add('jet',lower,id)}
        end
        map.flowSystems[id]=system
    end
    for i=1,cfg.vortexCount do
        local o=map.obstacles[i+4]
        local radius=o.boundRadius+4.6
        local points=arc(o,radius,0,TAU)
        assert(legalPath(map,points,3.05),'Vortex bypass does not fit')
        map.flows[#map.flows+1]={id=#map.flows+1,kind='vortex',cx=o.cx,cy=o.cy,obstacleId=o.id,
            ringRadius=radius,width=cfg.vortexWidth,speed=cfg.vortexSpeed,direction=random()<.5 and -1 or 1}
        map.majorRoutes[#map.majorRoutes+1]={id=#map.majorRoutes+1,width=6,points=points,systemId=0}
    end
    -- Route on the real eroded grid, then simplify and round only legal bends.
    -- This creates long open-ground streams without drawing through any wall.
    local w,h=map.width,map.height
    local safe,ordered={},{}
    for y=0,h-1 do LoadJob.Checkpoint(); for x=0,w-1 do
        if map:Contains(x+.5,y+.5,3.1) then
            local id=y*w+x+1;safe[id]=true;ordered[#ordered+1]=id
        end
    end end
    local function point(id) return {x=(id-1)%w+.5,y=math.floor((id-1)/w)+.5} end
    local function anchor(x,y)
        local best,score=0,math.huge
        for _,id in ipairs(ordered) do
            local p=point(id);local d=(p.x-x)^2+(p.y-y)^2
            if d<score then best,score=id,d end
        end
        assert(best>0,'No legal open-flow anchor');return best
    end
    local function routed(a,b)
        local queue,seen,parent,head={a},{[a]=true},{},1
        while head<=#queue and not seen[b] do LoadJob.Checkpoint();
            local id=queue[head];head=head+1
            local p=point(id)
            for _,delta in ipairs({{1,0},{0,1},{-1,0},{0,-1}}) do
                local x,y=p.x+delta[1],p.y+delta[2]
                local nextId=(y-.5)*w+x+.5
                if x>=.5 and x<w and y>=.5 and y<h and safe[nextId] and not seen[nextId]
                    and map:Contains((p.x+x)/2,(p.y+y)/2,3.1) then
                    seen[nextId]=true;parent[nextId]=id;queue[#queue+1]=nextId
                end
            end
        end
        assert(seen[b],'Open-flow routing exhausted the finite grid')
        ---@type table[]
        local raw={point(b)};local id=b
        while id~=a do id=parent[id];raw[#raw+1]=point(id) end
        raw=reverse(raw)
        local path,index={raw[1]},1
        while index<#raw do
            local nextIndex=#raw
            while nextIndex>index+1 and not legalPath(map,{raw[index],raw[nextIndex]},3.05) do nextIndex=nextIndex-1 end
            path[#path+1]=raw[nextIndex];index=nextIndex
        end
        local rounded={path[1]}
        for i=2,#path-1 do
            local prev,p,nextPoint=path[i-1],path[i],path[i+1]
            local entry={x=p.x+(prev.x-p.x)*.2,y=p.y+(prev.y-p.y)*.2}
            local exit={x=p.x+(nextPoint.x-p.x)*.2,y=p.y+(nextPoint.y-p.y)*.2}
            if legalPath(map,{rounded[#rounded],entry,exit,nextPoint},3.05) then
                rounded[#rounded+1]=entry;rounded[#rounded+1]=exit
            else rounded[#rounded+1]=p end
        end
        rounded[#rounded+1]=path[#path]
        assert(length(rounded)>=18,'Open flow too short');return rounded
    end
    local function seedAnchor(x,y) return anchor((x+(random()-.5)*.08)*w,(y+(random()-.5)*.08)*h) end
    local center=seedAnchor(.50,.50)
    local routes={{seedAnchor(.50,.12),center},{center,seedAnchor(.50,.88)},
        {seedAnchor(.12,.38),center},{center,seedAnchor(.88,.62)},
        {seedAnchor(.16,.24),seedAnchor(.84,.31)},
        {seedAnchor(.18,.77),seedAnchor(.84,.83)}}
    for i,pair in ipairs(routes) do
        local points=routed(pair[1],pair[2])
        local id=add(i==6 and 'counter' or 'jet',points,0)
        map.flows[id].scope='open_ground'
        map.crossFlows[i]={id=i,flowId=id,start=points[1],finish=points[#points],junction=i<=4 and point(center) or nil}
    end
    -- Twelve broad, separated patches spread the supplements across the map.
    -- They are not restricted to wall islands or flow ring centers.
    for i=1,cfg.bayCount do
        local selected,score=nil,-1
        for attempt=1,500 do LoadJob.Checkpoint();
            local x=8+random()*(w-16);local y=8+random()*(h-16)
            local nearest=(x-map.spawn.x)^2+(y-map.spawn.y)^2
            for _,bay in ipairs(map.bays) do nearest=math.min(nearest,(x-bay.x)^2+(y-bay.y)^2) end
            if nearest>=cfg.bayMinDistance^2 and map:Contains(x,y,cfg.bayRadius+.2) then
                local priority=nearest*(.8+random()*.4)
                if priority>score then selected,score={id=i,x=x,y=y,radius=cfg.bayRadius},priority end
            end
        end
        assert(selected,'Cannot reserve a separated loose cell patch')
        map.bays[i]=selected
    end
end

return M
