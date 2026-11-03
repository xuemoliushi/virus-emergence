-- Small deterministic visibility graph over the actual tissue/channel geometry.
-- Detection and damage stay in ImmuneSystem; this only routes a locked target.
local Navigation = {}
local graphs = setmetatable({}, {__mode="k"})

local function distance(a,b)return math.sqrt((a.x-b.x)^2+(a.y-b.y)^2)end

function Navigation.Clear(map,a,b,radius)
    if map.isFlatMap then return map:_ConvexPathClear(a.x,a.y,b.x,b.y,radius) end
    if map._ConvexPathClear and map:_ConvexPathClear(a.x,a.y,b.x,b.y,radius) then
        local x,y=map:Move(a.x,a.y,b.x,b.y,radius)
        return (x-b.x)^2+(y-b.y)^2<1e-10
    end
    if not map:Contains(a.x,a.y,radius) or not map:Contains(b.x,b.y,radius) then return false end
    local samples=math.max(1,math.ceil(distance(a,b)/.15))
    for i=1,samples-1 do
        local t=i/samples
        if not map:Contains(a.x+(b.x-a.x)*t,a.y+(b.y-a.y)*t,radius) then return false end
    end
    -- Production Move continuously sweeps the full body; do not rely on point LOS.
    local x,y = map:Move(a.x,a.y,b.x,b.y,radius)
    return (x-b.x)^2+(y-b.y)^2 < 1e-10
end

local function graph(map,radius)
    local byRadius = graphs[map] or {}; graphs[map] = byRadius
    if byRadius[radius] then return byRadius[radius] end
    local points = {}
    local function add(x,y)
        if not map:Contains(x,y,radius) then return end
        for _,p in ipairs(points)do if (p.x-x)^2+(p.y-y)^2<.01 then return end end
        points[#points+1] = {x=x,y=y}
    end
    for _,region in ipairs(map.regions or {})do add(region.x,region.y) end
    for _,channel in ipairs(map.channels or {})do
        for _,p in ipairs(channel.points)do add(p.x,p.y) end
    end
    local edges = {}
    for i=1,#points do edges[i]={} end
    for i=1,#points do
        for j=i+1,#points do
            if Navigation.Clear(map,points[i],points[j],radius) then
                local d=distance(points[i],points[j])
                edges[i][j],edges[j][i]=d,d
            end
        end
    end
    local result={points=points,edges=edges}
    byRadius[radius]=result
    return result
end

function Navigation.Route(map,start,target,radius)
    if map.isFlatMap then return require('Core.FlatNavigation').Route(map,start,target,radius) end
    if Navigation.Clear(map,start,target,radius) then return {target} end
    local g=graph(map,radius)
    local points,edges={},{}
    for i,p in ipairs(g.points)do
        points[i]=p;edges[i]={}
        for j,d in pairs(g.edges[i])do edges[i][j]=d end
    end
    local origin,goal=#points+1,#points+2
    points[origin],points[goal]=start,target
    edges[origin],edges[goal]={},{}
    for i=1,origin-1 do
        for _,j in ipairs({origin,goal})do
            if Navigation.Clear(map,points[i],points[j],radius) then
                local d=distance(points[i],points[j]);edges[i][j],edges[j][i]=d,d
            end
        end
    end
    local cost,previous,visited={[origin]=0},{},{}
    for _=1,#points do
        local current,best=nil,math.huge
        for i=1,#points do if not visited[i] and (cost[i] or math.huge)<best then current,best=i,cost[i] end end
        if not current then return nil end
        if current==goal then
            local route={}
            while current~=origin do table.insert(route,1,points[current]);current=previous[current] end
            return route
        end
        visited[current]=true
        for nextId=1,#points do
            local length=edges[current][nextId]
            if length and not visited[nextId] and best+length<(cost[nextId] or math.huge) then
                cost[nextId],previous[nextId]=best+length,current
            end
        end
    end
    return nil
end

return Navigation
