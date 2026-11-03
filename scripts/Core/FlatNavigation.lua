-- Deterministic A* over legal metre-centres. Every edge uses the exact disk sweep.
-- Cached topology belongs to this map and is discarded with it on scene rebuild.
local N={}
local offsets={{1,0},{0,1},{-1,0},{0,-1},{1,1},{-1,1},{-1,-1},{1,-1}}
local function push(heap,id,score)
    local i=#heap+1;local item={id=id,score=score}
    while i>1 do
        local parent=math.floor(i/2);local p=heap[parent]
        if p.score<score or (p.score==score and p.id<=id) then break end
        heap[i]=p;i=parent
    end
    heap[i]=item
end
local function pop(heap)
    local first,last=heap[1],table.remove(heap)
    if #heap>0 then
        local i=1
        while i*2<=#heap do
            local child=i*2
            local a,b=heap[child],heap[child+1]
            if b and (b.score<a.score or (b.score==a.score and b.id<a.id)) then child=child+1 end
            local c=heap[child]
            if last.score<c.score or (last.score==c.score and last.id<=c.id) then break end
            heap[i]=c;i=child
        end
        heap[i]=last
    end
    return first.id
end
function N.Route(map,start,target,radius)
    if not map:Contains(start.x,start.y,radius) or not map:Contains(target.x,target.y,radius) then return nil end
    if map:_ConvexPathClear(start.x,start.y,target.x,target.y,radius) then return {target} end
    local g=map.navigationCache[radius]
    if not g then g={legal={},edges={}};map.navigationCache[radius]=g end
    local w,h=map.width,map.height
    local function point(id) return {x=(id-1)%w+.5,y=math.floor((id-1)/w)+.5} end
    local function legal(id)
        if g.legal[id]==nil then local p=point(id);g.legal[id]=map:Contains(p.x,p.y,radius) end
        return g.legal[id]
    end
    local function anchors(p)
        local result={}
        for y=math.max(0,math.floor(p.y)-3),math.min(h-1,math.floor(p.y)+3) do
            for x=math.max(0,math.floor(p.x)-3),math.min(w-1,math.floor(p.x)+3) do
                local id=y*w+x+1;local q=point(id)
                if legal(id) and map:_ConvexPathClear(p.x,p.y,q.x,q.y,radius) then
                    result[#result+1]={id=id,cost=math.sqrt((p.x-q.x)^2+(p.y-q.y)^2)}
                end
            end
        end
        return result
    end
    local origins,ends=anchors(start),anchors(target)
    if #origins==0 or #ends==0 then return nil end
    local goals={};for _,v in ipairs(ends) do goals[v.id]=v.cost end
    local cost,previous,closed,heap={},{},{},{}
    local function estimate(id) local p=point(id);return math.sqrt((p.x-target.x)^2+(p.y-target.y)^2) end
    for _,v in ipairs(origins) do cost[v.id]=v.cost;previous[v.id]=0;push(heap,v.id,v.cost+estimate(v.id)) end
    local best,bestCost=nil,math.huge
    for _=1,w*h*8 do
        if #heap==0 then break end
        if best and heap[1].score>=bestCost then break end
        local id=pop(heap)
        if not closed[id] then
            closed[id]=true
            if goals[id] and cost[id]+goals[id]<bestCost then best,bestCost=id,cost[id]+goals[id] end
            local edges=g.edges[id]
            if not edges then
                edges={};local p=point(id);local x,y=(id-1)%w,math.floor((id-1)/w)
                for _,o in ipairs(offsets) do
                    local nx,ny=x+o[1],y+o[2];local nextId=ny*w+nx+1
                    if nx>=0 and ny>=0 and nx<w and ny<h and legal(nextId) then
                        local q=point(nextId)
                        if map:_ConvexPathClear(p.x,p.y,q.x,q.y,radius) then edges[#edges+1]={id=nextId,cost=math.sqrt(o[1]^2+o[2]^2)} end
                    end
                end
                g.edges[id]=edges
            end
            for _,v in ipairs(edges) do
                local nextCost=cost[id]+v.cost
                if not closed[v.id] and nextCost<(cost[v.id] or math.huge) then
                    cost[v.id],previous[v.id]=nextCost,id;push(heap,v.id,nextCost+estimate(v.id))
                end
            end
        end
    end
    if not best then return nil end
    local reverse={target};local id=best
    while id~=0 do reverse[#reverse+1]=point(id);id=previous[id] end
    -- Greedy short-cutting keeps the returned route small without crossing walls.
    local route={};local from=start;local i=#reverse
    while i>=1 do
        local chosen=i
        for j=i-1,1,-1 do
            local p=reverse[j]
            if map:_ConvexPathClear(from.x,from.y,p.x,p.y,radius) then chosen=j else break end
        end
        from=reverse[chosen];route[#route+1]=from;i=chosen-1
    end
    return route
end
return N
