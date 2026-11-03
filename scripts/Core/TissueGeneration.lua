-- Version 3: spawn/routes followed by independent full-region coverage quotas.
local Random = require("Core.MapRandom")
local Generation = {}
local TAU = math.pi * 2
local STARTS = {"UPPER_AIRWAY", "TRACHEA", "DEEP_LUNG"}
local function distance(ax,ay,bx,by) return math.sqrt((ax-bx)^2+(ay-by)^2) end

function Generation.Populate(map,cfg)
    local began=os.clock()
    local random,appearance=Random.New(map.seed,30),Random.New(map.seed,31)
    local count=cfg.cellCount or 216
    local minR,maxR=cfg.cellRadiusMin or .34,cfg.cellRadiusMax or .48
    local gap,safe=cfg.mapCellGap or .16,cfg.mapSpawnSafeRadius or 2
    local groupRadius=cfg.groupRadius or .48
    local sampleSpacing,edge=cfg.mapCoverageSampleSpacing or 2,cfg.mapEdgeCoverage or .87
    assert(sampleSpacing>=1 and sampleSpacing<=4,"Coverage sample spacing must be 1..4m")
    assert(edge>=.75 and edge<=.92,"Edge coverage must be .75.. .92")
    map.spawnSafeRadius,map.cellGap=safe,gap
    map.fallbackCount=0
    local function clear(x,y,r,starter)
        if not map:Contains(x,y,r) then return false end
        for _,key in ipairs(STARTS) do
            local p=map.startPoints[key]
            local d=distance(x,y,p.x,p.y)
            if d<groupRadius+r+gap or (not starter and d<=safe) then return false end
        end
        for _,c in ipairs(map.cells) do
            if distance(x,y,c.x,c.y)<r+c.radius+gap then return false end
        end
        return true
    end
    local function place(x,y,starter)
        if #map.cells>=count or not clear(x,y,maxR,starter) then return false end
        local id=#map.cells+1
        map.cells[id]={id=id,x=x,y=y,radius=minR+appearance()*(maxR-minR),
            variant=math.floor(appearance()*4)+1,phase=appearance()*TAU,
            rotation=appearance()*TAU,regionId=map:RegionAt(x,y)}
        return true
    end
    for _,key in ipairs(STARTS) do
        local p=map.startPoints[key]
        local angle=random()*TAU
        for i=1,3 do
            local a,d=angle+(i-1)*TAU/3,i==1 and 1.35 or 1.8
            assert(place(p.x+math.cos(a)*d,p.y+math.sin(a)*d,true),"Spawn target cannot fit")
        end
    end
    -- Route targets cannot consume the subsequent region coverage budget.
    local spacing=cfg.mapRouteTargetSpacing or 4
    for _,ch in ipairs(map.channels) do
        local nextDistance,travelled,ordinal=spacing*.5,0,0
        for i=1,#ch.points-1 do
            local a,b=ch.points[i],ch.points[i+1]
            local length=distance(a.x,a.y,b.x,b.y)
            while nextDistance<=travelled+length do
                local t=(nextDistance-travelled)/length
                ordinal=ordinal+1
                local offset=math.min(ch.width*.23,1.8)*(ordinal%2==0 and 1 or -1)
                place(a.x+(b.x-a.x)*t-(b.y-a.y)/length*offset,
                    a.y+(b.y-a.y)*t+(b.x-a.x)/length*offset,false)
                nextDistance=nextDistance+spacing
            end
            travelled=travelled+length
        end
    end
    local pools,weights,quotas={},{},{}
    local density={1.0,.9,1.3,.75,1.1}
    local totalWeight=0
    for _,r in ipairs(map.regions) do
        local pool={}
        -- Strata span the full ellipse. There is no seven-ring radius cap.
        -- Seeded phase, jitter and priority produce different tissue patches.
        local phase=random()*TAU
        local rings=math.ceil(math.max(r.rx,r.ry)/sampleSpacing)
        for ring=rings,1,-1 do
            local radial=edge*ring/rings
            local samples=math.max(8,math.ceil(TAU*math.sqrt(r.rx*r.ry)*radial/sampleSpacing))
            for i=1,samples do
                local angle=phase+i*TAU/samples+(random()-.5)*TAU/samples*.45
                local rad=math.min(.94,math.max(.05,radial+(random()-.5)*.035))
                local x,y=r.x+math.cos(angle)*r.rx*rad,r.y+math.sin(angle)*r.ry*rad
                if map:Contains(x,y,maxR) and map:RegionAt(x,y)==r.id then
                    pool[#pool+1]={x=x,y=y,priority=.88+random()*.24}
                end
            end
        end
        pools[r.id]=pool
        weights[r.id]=r.rx*r.ry*density[r.id]^(cfg.mapDensity or 1)
        totalWeight=totalWeight+weights[r.id]
    end
    -- Reserve all eight rim directions before distributing the remaining
    -- budget. Channels entering a region must not replace its side targets.
    for _,r in ipairs(map.regions) do
        for sector=1,8 do
            local covered=false
            for _,c in ipairs(map.cells) do
                if c.regionId==r.id then
                    local x,y=(c.x-r.x)/r.rx,(c.y-r.y)/r.ry
                    local s=math.floor((math.atan(y,x)+math.pi)/TAU*8)%8+1
                    if x*x+y*y>=.68^2 and s==sector then covered=true;break end
                end
            end
            if not covered then
                local best,score=nil,math.huge
                local angle=-math.pi+(sector-.5)*TAU/8
                local tx,ty=r.x+math.cos(angle)*r.rx*edge,r.y+math.sin(angle)*r.ry*edge
                for i,p in ipairs(pools[r.id]) do
                    local x,y=(p.x-r.x)/r.rx,(p.y-r.y)/r.ry
                    local s=math.floor((math.atan(y,x)+math.pi)/TAU*8)%8+1
                    local d=(p.x-tx)^2+(p.y-ty)^2
                    if x*x+y*y>=.68^2 and s==sector and d<score and clear(p.x,p.y,maxR,false) then
                        best,score=i,d
                    end
                end
                assert(best,"Configured tissue cannot cover all rim directions")
                local p=pools[r.id][best];p.used=true
                assert(place(p.x,p.y,false),"cellCount too small for spawn, route and rim coverage")
            end
        end
    end
    local remaining,assigned=count-#map.cells,0
    for id=1,#map.regions do
        quotas[id]=math.floor(remaining*weights[id]/totalWeight)
        assigned=assigned+quotas[id]
    end
    for i=1,remaining-assigned do quotas[(i-1)%#quotas+1]=quotas[(i-1)%#quotas+1]+1 end
    local function nearest(x,y)
        local best=math.huge
        for _,c in ipairs(map.cells) do best=math.min(best,(c.x-x)^2+(c.y-y)^2) end
        return best
    end
    local function choose(pool)
        local selected,score=nil,-1
        for i,p in ipairs(pool) do
            if p.nearest==nil then
                p.nearest=nearest(p.x,p.y)
                p.blocked=not clear(p.x,p.y,maxR,false)
            end
            if not p.used and not p.blocked then
                local candidate=p.nearest*p.priority
                if candidate>score then selected,score=i,candidate end
            end
        end
        if not selected then return false end
        local p=pool[selected];p.used=true
        if not place(p.x,p.y,false) then return false end
        local cell=map.cells[#map.cells]
        -- Update the distance field once per placed cell instead of repeating
        -- all pair queries for every proposal. Exact spacing checks retained.
        for _,otherPool in ipairs(pools) do
            for _,q in ipairs(otherPool) do
                if q.nearest~=nil and not q.used then
                    local d=(q.x-cell.x)^2+(q.y-cell.y)^2
                    q.nearest=math.min(q.nearest,d)
                    if d<(maxR+cell.radius+gap)^2 then q.blocked=true end
                end
            end
        end
        return true
    end
    -- Fill the farthest uncovered gaps per region; large sparse regions cannot
    -- be starved by a prefix of centre-out cells in the other regions.
    for turn=1,remaining do
        for id=1,#map.regions do
            if quotas[id]>0 then
                if choose(pools[id]) then quotas[id]=quotas[id]-1 else quotas[id]=0 end
            end
        end
        if #map.cells>=count then break end
    end
    -- Finite lattice fallback, still farthest-first and respecting true bounds.
    if #map.cells<count then
        local pool={}
        local step=2*maxR+gap
        for y=step,map.height-step,step do
            for x=step,map.width-step,step do
                if clear(x,y,maxR,false) then pool[#pool+1]={x=x,y=y,priority=1} end
            end
        end
        pools[#pools+1]=pool
        while #map.cells<count and choose(pool) do map.fallbackCount=map.fallbackCount+1 end
    end
    assert(#map.cells==count,"Configured tissue cannot fit cellCount with required spacing")
    map.generationMs=(os.clock()-began)*1000
end
return Generation
