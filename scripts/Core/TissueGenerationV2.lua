-- Version 2 population of the existing RespiratoryMap; no new world or states.
local Random = require("Core.MapRandom")
local Generation = {}
local TAU = math.pi * 2
local STARTS = {"UPPER_AIRWAY", "TRACHEA", "DEEP_LUNG"}

local function distance(ax, ay, bx, by)
    return math.sqrt((ax - bx)^2 + (ay - by)^2)
end

function Generation.Populate(map, cfg)
    local began = os.clock()
    local layout = Random.New(map.seed, 20)
    local appearance = Random.New(map.seed, 21)
    local count = cfg.cellCount or 108
    local minR, maxR = cfg.cellRadiusMin or .34, cfg.cellRadiusMax or .48
    local gap = cfg.mapCellGap or .16
    local safety = cfg.mapSpawnSafeRadius or 2
    local groupRadius = cfg.groupRadius or .48
    map.spawnSafeRadius, map.cellGap = safety, gap
    map.fallbackCount = 0
    local candidates = {}
    -- Three guaranteed first targets at each supported spawn. These are generated
    -- before other cells and exempt only from the outer 2m target reservation.
    for _, key in ipairs(STARTS) do
        local start = map.startPoints[key]
        local base = layout() * TAU
        for i = 1, 3 do
            local angle = base + (i - 1) * TAU / 3
            local d = i == 1 and 1.35 or 1.8
            candidates[#candidates + 1] = {x=start.x + math.cos(angle)*d,
                y=start.y + math.sin(angle)*d, starter=true, jitter=0}
        end
    end
    -- Ordered arc-length sampling keeps targets along both routes, including bends.
    local spacing = cfg.mapRouteTargetSpacing or 4
    for _, channel in ipairs(map.channels) do
        local nextDistance, travelled, ordinal = spacing * .5, 0, 0
        for i = 1, #channel.points - 1 do
            local a, b = channel.points[i], channel.points[i+1]
            local length = distance(a.x,a.y,b.x,b.y)
            while nextDistance <= travelled + length do
                local t = (nextDistance - travelled) / length
                ordinal = ordinal + 1
                local offset = math.min(channel.width * .23, 1.8) * (ordinal % 2 == 0 and 1 or -1)
                candidates[#candidates + 1] = {
                    x=a.x+(b.x-a.x)*t-(b.y-a.y)/length*offset,
                    y=a.y+(b.y-a.y)*t+(b.x-a.x)/length*offset, jitter=.35}
                nextDistance = nextDistance + spacing
            end
            travelled = travelled + length
        end
    end
    -- Different physical density, using existing ordinary cell variants only.
    -- Dense pockets have short spacing, sparse tissue keeps longer gaps.
    local pitchByRegion = {2.2, 2.4, 1.35, 3.1, 1.7}
    local pools = {}
    for _, region in ipairs(map.regions) do
        local pitch = pitchByRegion[region.id] / math.sqrt(cfg.mapDensity or 1)
        local pool = {}
        for ring = 1, 7 do
            for i = 1, 8 * ring do
                local angle = i * TAU / (8*ring) + region.id * .71
                local d = ring * pitch
                local x, y = region.x + math.cos(angle)*d, region.y + math.sin(angle)*d
                if map:Contains(x,y,maxR) and map:RegionAt(x,y)==region.id then
                    pool[#pool+1] = {x=x,y=y,jitter=pitch*.2}
                end
            end
        end
        pools[region.id] = pool
    end
    -- Interleave so a configured prefix never starves the deeper areas.
    for index = 1, 196 do
        for id = 1, #map.regions do
            local candidate = pools[id][index]
            if candidate then candidates[#candidates+1] = candidate end
        end
    end

    local function clear(x,y,r,starter)
        if not map:Contains(x,y,r) then return false end
        for _, key in ipairs(STARTS) do
            local start = map.startPoints[key]
            local d = distance(x,y,start.x,start.y)
            if d < groupRadius + r + gap or (not starter and d <= safety) then return false end
        end
        for _, c in ipairs(map.cells) do
            if distance(x,y,c.x,c.y) < r+c.radius+gap then return false end
        end
        return true
    end

    for _, candidate in ipairs(candidates) do
        if #map.cells >= count then break end
        local radius = minR + appearance()*(maxR-minR)
        local x,y,placed = candidate.x,candidate.y,false
        -- Bounded six proposals, then the exact valid anchor. No retry RNG in combat.
        for attempt = 1, 6 do
            local angle, d = layout()*TAU, layout()*(candidate.jitter or .35)
            local tx,ty = candidate.x+math.cos(angle)*d,candidate.y+math.sin(angle)*d
            if clear(tx,ty,radius,candidate.starter) then x,y,placed=tx,ty,true;break end
        end
        if not placed and clear(x,y,radius,candidate.starter) then
            placed=true;map.fallbackCount=map.fallbackCount+1
        end
        if placed then
            local id = #map.cells+1
            map.cells[id] = {id=id,x=x,y=y,radius=radius,variant=math.floor(appearance()*4)+1,
                phase=appearance()*TAU,rotation=appearance()*TAU,regionId=map:RegionAt(x,y)}
        end
    end
    -- Finite lattice fallback still observes every real boundary and spawn constraint.
    if #map.cells < count then
        local step = 2*maxR+gap
        for y = step, map.height-step, step do
            for x = step, map.width-step, step do
                if #map.cells>=count then break end
                if clear(x,y,maxR,false) then
                    local id=#map.cells+1
                    map.cells[id]={id=id,x=x,y=y,radius=maxR,variant=(id-1)%4+1,
                        phase=id*.71%TAU,rotation=id*.37%TAU,regionId=map:RegionAt(x,y)}
                    map.fallbackCount=map.fallbackCount+1
                end
            end
            if #map.cells>=count then break end
        end
    end
    assert(#map.cells==count,"Configured tissue cannot fit cellCount with the required spacing")
    map.generationMs=(os.clock()-began)*1000
end

return Generation
