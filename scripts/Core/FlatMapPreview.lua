-- Pure candidate data, based on the scaffold-2d config -> initialize -> data split.
-- No game entry, combat, UI, or resource loading changes before layout approval.
local LoadJob = require("Core.LoadJob")
local Random = require("Core.MapRandom")
local Defaults = require("Core.FlatMapConfig")
local Layout = require("Core.FlatMapLayout")
local Mixed = require("Core.MixedTerrainLayout")
---@class FlatMapPreview
---@field spawn {x:number,y:number}
---@field outerBoundary table
---@field obstacles table[]
---@field flowSystems table[]
---@field crossFlows table[]
---@field bays {id:number,x:number,y:number,radius:number}[]
---@field majorRoutes table[]
---@field cells {id:number,x:number,y:number,radius:number,placement:string,regionId:integer?}[]
local Map = {}
Map.__index = Map
local TAU = math.pi * 2

local function squared(ax,ay,bx,by) return (ax-bx)^2+(ay-by)^2 end
local function integer(random,lo,hi) return lo+math.floor(random()*(hi-lo+1)) end

function Map.New(options)
    local instance=setmetatable({},Map)
    instance:Init(options or {})
    return instance
end

function Map:Init(options)
    local began=os.clock()
    self.config={}
    for key,value in pairs(Defaults) do self.config[key]=value end
    -- Copying config keys consumes no RNG and never controls generation order.
    for key,value in pairs(options) do self.config[key]=value end
    local cfg=self.config
    assert(cfg.mapKind=="flat_black_wall" and (cfg.mapGenerationVersion==4 or cfg.mapGenerationVersion==5),"Unsupported mixed map version")
    assert(cfg.gridSize==1 and cfg.width==120 and cfg.height==144,"Mixed v4 uses a 120x144m one-metre grid")
    assert(cfg.borderWidth==2 and cfg.islandCount==10 and cfg.ridgeCount==8,"Mixed v4 uses 10 islands and 8 ridges")
    assert(cfg.generationAttempts>=1 and cfg.generationAttempts<=8 and cfg.obstacleAttempts>=1 and cfg.obstacleAttempts<=160,"Invalid bounded generation attempts")
    assert(cfg.coverageRepairLimit>=0 and cfg.coverageRepairLimit<=64,"Coverage repair limit must be 0..64")
    assert(cfg.corridorWidth==6 and cfg.maxSwarmRadius>0 and cfg.maxSwarmRadius<=1.35,"Invalid navigation radius/width")
    assert(cfg.cellCount==cfg.coverageCellCount+cfg.supplementCellCount and cfg.coverageCellCount>=64 and cfg.supplementCellCount==120,"Cell stages require coverage plus 120 supplements")
    assert(cfg.cellCount<=(cfg.mapGenerationVersion==5 and 1200 or 768) and cfg.cellRadiusMin>0 and cfg.cellRadiusMax>=cfg.cellRadiusMin and cfg.cellRadiusMax<1,"Invalid cell budget/radii")
    assert(cfg.cellGap>=0 and cfg.spawnSafeRadius>=2 and cfg.playerRadius>0,"Invalid spawn/spacing settings")
    assert(cfg.bayCount==12 and cfg.bayCellCount==10 and cfg.bayCount*cfg.bayCellCount==cfg.supplementCellCount,"Invalid supplement patch budget")
    assert(cfg.bayRadius>=5.5 and cfg.bayMinDistance>=cfg.bayRadius*2 and cfg.supplementMinDistance>=2.4,"Invalid patch spacing")
    assert(cfg.densityRadius==4 and cfg.densityCap>=4 and cfg.densityCap<=9 and cfg.crossFlowCount==6,"Invalid density/flow coverage limits")
    assert(cfg.flowSystemCount==4 and cfg.vortexCount==3,"Mixed v4 uses four local systems and three vortices")
    assert(cfg.flowWidth==3 and cfg.vortexWidth==2 and cfg.spawnCalmRadius>=5,"Invalid flow widths/calm zone")
    assert(cfg.maxFlowSpeed>0 and cfg.maxFlowSpeed<=1.6,"Invalid flow speed cap")
    assert(cfg.jetSpeedMin>=.8 and cfg.jetSpeedMax>=cfg.jetSpeedMin and cfg.jetSpeedMax<=cfg.maxFlowSpeed,"Invalid jet speed")
    assert(cfg.counterSpeedMin>=.8 and cfg.counterSpeedMax>=cfg.counterSpeedMin and cfg.counterSpeedMax<=cfg.maxFlowSpeed,"Invalid counter speed")
    assert(cfg.vortexSpeed>=.8 and cfg.vortexSpeed<=cfg.maxFlowSpeed,"Invalid vortex speed")
    assert(cfg.coverageMaxDistance>0 and cfg.candidateCount>=cfg.cellCount and cfg.candidateAttemptLimit>=cfg.candidateCount,"Invalid candidate budget")
    self.width,self.height=cfg.width,cfg.height
    self.mapKind,self.generationVersion=cfg.mapKind,cfg.mapGenerationVersion
    local actualSeed=cfg.mapSeed
    if actualSeed==nil then actualSeed=Random.NewSeed() end
    self.seed=Random.Normalize(actualSeed)
    local success=false
    local reason=""
    LoadJob.Report(.04,"正在生成组织结构…")
    if cfg.mapGenerationVersion==5 then
        -- Anchor terrain to the approved v4 layout for this seed. Density changes
        -- must not select a different terrain retry or relocate the flow systems.
        local baseConfig={};for key,value in pairs(cfg) do baseConfig[key]=value end
        baseConfig.mapGenerationVersion=4;baseConfig.cellCount=480;baseConfig.coverageCellCount=360
        baseConfig.mapSeed=self.seed
        local base=Map.New(baseConfig)
        for _,key in ipairs({'rooms','connections','flows','floor','spawn','outerBoundary','obstacles',
            'flowSystems','crossFlows','bays','majorRoutes','navigationSamples','floorSamples'}) do self[key]=base[key] end
        self.cells={};self.fallbackCount,self.coverageRepairs=0,0
        local offset=(base.generationAttempt-1)*16
        self:_Populate(Random.New(self.seed,101+offset),Random.New(self.seed,102+offset))
        self.generationAttempt=base.generationAttempt;success=true
    else
    for attempt=1,cfg.generationAttempts do
        self.rooms,self.connections,self.flows,self.cells,self.floor,self.floorRows={},{},{},{},{},{}
        self.fallbackCount,self.coverageRepairs=0,0
        for y=1,self.height do self.floor[y]={} end
        local offset=(attempt-1)*16
        local ok,err=pcall(function()
            Mixed.Build(self,Random.New(self.seed,100+offset),Random.New(self.seed,103+offset))
            LoadJob.Report(.16,"正在铺设组织细胞…")
            self:_Populate(Random.New(self.seed,101+offset),Random.New(self.seed,102+offset))
        end)
        if ok then self.generationAttempt=attempt;success=true;break end
        reason=tostring(err)
    end
    end
    assert(success,"Mixed map rejected after bounded generation attempts: "..reason)
    LoadJob.Report(cfg.mapGenerationVersion==5 and .70 or .40,"正在整理组织分区…")
    self.floorRows={}
    local floorCount=0
    for y=1,self.height do
        local row={}
        for x=1,self.width do
            local open=self.floor[y][x]==true
            row[x]=open and "1" or "0"
            if open then floorCount=floorCount+1 end
        end
        self.floorRows[y]=table.concat(row)
    end
    self.floorArea=floorCount
    self.walkableRatio=floorCount/(self.width*self.height)
    self.generationMs=(os.clock()-began)*1000
end

-- Exact circle vs solid grid squares; the raster is the authoritative geometry.
-- Preview checks only: live movement/sweeps/navigation are intentionally not wired.
function Map:Contains(x,y,radius)
    local r=radius or 0
    if x~=x or y~=y or r<0 or x-r<0 or y-r<0 or x+r>=self.width or y+r>=self.height then return false end
    if r==0 then return self.floor[math.floor(y)+1][math.floor(x)+1]==true end
    for gy=math.floor(y-r),math.floor(y+r) do
        for gx=math.floor(x-r),math.floor(x+r) do
            if not self.floor[gy+1][gx+1] then
                local nx=math.max(gx,math.min(gx+1,x))
                local ny=math.max(gy,math.min(gy+1,y))
                if squared(x,y,nx,ny)<=r*r+1e-12 then return false end
            end
        end
    end
    return true
end

function Map:_Populate(layout,appearance)
    local cfg=self.config
    local density={}
    local function densityTiles(x,y,visit)
        for gy=math.max(0,math.floor(y-cfg.densityRadius)),math.min(self.height-1,math.floor(y+cfg.densityRadius)) do
            for gx=math.max(0,math.floor(x-cfg.densityRadius)),math.min(self.width-1,math.floor(x+cfg.densityRadius)) do
                if squared(x,y,gx+.5,gy+.5)<=cfg.densityRadius^2 then
                    if not visit(gy*self.width+gx+1) then return false end
                end
            end
        end
        return true
    end
    local function updateDensity(x,y,delta)
        densityTiles(x,y,function(id) density[id]=(density[id] or 0)+delta;return true end)
    end
    local function clear(x,y,r,starter,minDistance)
        if not self:Contains(x,y,r) then return false end
        local spawnDistance=math.sqrt(squared(x,y,self.spawn.x,self.spawn.y))
        if spawnDistance<cfg.playerRadius+r+cfg.cellGap or (not starter and spawnDistance<=cfg.spawnSafeRadius) then return false end
        for _,c in ipairs(self.cells) do
            local separation=math.max(c.radius+r+cfg.cellGap,minDistance or 0,
                c.placement=="supplement" and cfg.supplementMinDistance or 0)
            if squared(x,y,c.x,c.y)<separation^2 then return false end
        end
        return densityTiles(x,y,function(id) return (density[id] or 0)<cfg.densityCap end)
    end
    local function add(x,y,starter,bayId)
        if #self.cells>=cfg.cellCount or not clear(x,y,cfg.cellRadiusMax,starter,bayId and cfg.supplementMinDistance or 0) then return false end
        local id=#self.cells+1
        self.cells[id]={id=id,x=x,y=y,radius=cfg.cellRadiusMin+appearance()*(cfg.cellRadiusMax-cfg.cellRadiusMin),
            variant=integer(appearance,1,4),phase=appearance()*TAU,rotation=appearance()*TAU,state="HEALTHY",
            placement=id<=cfg.coverageCellCount and "coverage" or "supplement",bayId=bayId or 0}
        updateDensity(x,y,1)
        local start,span=cfg.mapGenerationVersion==5 and .40 or .16,cfg.mapGenerationVersion==5 and .23 or .17
        LoadJob.Report(start+span*id/cfg.cellCount,"正在铺设组织细胞…")
        return true
    end
    local phase=layout()*TAU
    for i=1,3 do
        local angle,d=phase+(i-1)*TAU/3,i==1 and 1.35 or 1.8
        assert(add(self.spawn.x+math.cos(angle)*d,self.spawn.y+math.sin(angle)*d,true),"Cannot reserve spawn targets")
    end
    local candidates={}
    -- Dense v5 reserves the supplement footprint before coverage placement.
    -- This retains loose patches instead of trying to squeeze them into a
    -- completed dense lattice. v4's approved initial data remain unchanged.
    local function coverageSpace(x,y)
        if cfg.mapGenerationVersion==4 then return true end
        for _,bay in ipairs(self.bays) do
            if squared(x,y,bay.x,bay.y)<(bay.radius+cfg.supplementMinDistance)^2 then return false end
        end
        return true
    end
    -- Fixed proposal count and attempts. Layout jitter never consumes appearances
    -- or simulation random numbers. Exact wall/spacing checks run before placement.
    for attempt=1,cfg.candidateAttemptLimit do
        LoadJob.Checkpoint()
        if #candidates>=cfg.candidateCount then break end
        local x=cfg.borderWidth+layout()*(self.width-2*cfg.borderWidth)
        local y=cfg.borderWidth+layout()*(self.height-2*cfg.borderWidth)
        if coverageSpace(x,y) and clear(x,y,cfg.cellRadiusMax,false) then candidates[#candidates+1]={x=x,y=y,priority=.8+layout()*.4} end
    end
    local function initialize(pool)
        for _,p in ipairs(pool) do
            LoadJob.Checkpoint()
            local nearest=math.huge
            for _,c in ipairs(self.cells) do nearest=math.min(nearest,squared(p.x,p.y,c.x,c.y)) end
            p.nearest=nearest
        end
    end
    local function choose(pool)
        LoadJob.Checkpoint()
        local selected,score=0,-1
        for i,p in ipairs(pool) do
            if not p.used then
                local candidate=p.nearest*p.priority
                if candidate>score then selected,score=i,candidate end
            end
        end
        if selected==0 then return false end
        local p=pool[selected];p.used=true
        if not add(p.x,p.y,false) then return false end
        local c=self.cells[#self.cells]
        for _,q in ipairs(pool) do
            local d=squared(q.x,q.y,c.x,c.y)
            q.nearest=math.min(q.nearest,d)
            if d<(cfg.cellRadiusMax+c.radius+cfg.cellGap)^2 then q.used=true end
        end
        return true
    end
    initialize(candidates)
    while #self.cells<cfg.coverageCellCount and choose(candidates) do end
    if #self.cells<cfg.coverageCellCount then
        -- Bounded fallback covers every legal half-metre lattice position.
        local pool={}
        for y=cfg.borderWidth+.5,self.height-cfg.borderWidth-.5,.5 do
            LoadJob.Checkpoint()
            for x=cfg.borderWidth+.5,self.width-cfg.borderWidth-.5,.5 do
                if coverageSpace(x,y) and clear(x,y,cfg.cellRadiusMax,false) then pool[#pool+1]={x=x,y=y,priority=1} end
            end
        end
        initialize(pool)
        while #self.cells<cfg.coverageCellCount and choose(pool) do self.fallbackCount=self.fallbackCount+1 end
    end
    assert(#self.cells==cfg.coverageCellCount,"Coverage cell budget cannot fit")
    for _,bay in ipairs(self.bays) do
        local placed=0
        for attempt=1,1600 do
            LoadJob.Checkpoint()
            if placed==cfg.bayCellCount then break end
            local a=layout()*TAU
            local r=math.sqrt(layout())*bay.radius
            if add(bay.x+math.cos(a)*r,bay.y+math.sin(a)*r,false,bay.id) then placed=placed+1 end
        end
        if placed<cfg.bayCellCount then
            for dy=-bay.radius,bay.radius,.5 do for dx=-bay.radius,bay.radius,.5 do
                if placed<cfg.bayCellCount and dx*dx+dy*dy<=bay.radius^2 and add(bay.x+dx,bay.y+dy,false,bay.id) then
                    placed=placed+1;self.fallbackCount=self.fallbackCount+1
                end
            end end
        end
        assert(placed==cfg.bayCellCount,"Cannot fit the loose supplement patch "..bay.id)
    end
    assert(#self.cells==cfg.cellCount,"Cell budget cannot fit the wall layout with required spacing")
    LoadJob.Report(cfg.mapGenerationVersion==5 and .65 or .35,"正在检查组织连通与覆盖…")
    -- Fixed-budget coverage repair. Reposition the most redundant non-starter
    -- cell into the worst sampled gap; keep identity/appearance unchanged.
    local samples={}
    for y=.5,self.height-.5,1 do LoadJob.Checkpoint(); for x=.5,self.width-.5,1 do
        if self:Contains(x,y,0) then samples[#samples+1]={x=x,y=y} end
    end end
    self.coverageRepairs=0
    for attempt=0,cfg.coverageRepairLimit do
        local worst,maxDistance=1,0
        for i,p in ipairs(samples) do
            LoadJob.Checkpoint()
            local best=math.huge
            for _,c in ipairs(self.cells) do best=math.min(best,squared(p.x,p.y,c.x,c.y)) end
            if best>maxDistance then worst,maxDistance=i,best end
        end
        self.maxTargetDistance=math.sqrt(maxDistance)
        if self.maxTargetDistance<=cfg.coverageMaxDistance then
            self.maxLocalDensity=0
            for _,count in pairs(density) do self.maxLocalDensity=math.max(self.maxLocalDensity,count) end
            return
        end
        assert(attempt<cfg.coverageRepairLimit,"Cell coverage exceeds the 6m limit after bounded repair")
        local target=samples[worst]
        local tx,ty,found=target.x,target.y,false
        for radius=0,3 do
            for dy=-radius,radius do for dx=-radius,radius do
                if not found and clear(target.x+dx*.5,target.y+dy*.5,cfg.cellRadiusMax,false) then
                    tx,ty,found=target.x+dx*.5,target.y+dy*.5,true
                end
            end end
            if found then break end
        end
        assert(found,"No safe repair location for uncovered floor")
        local selected,best=0,math.huge
        for i=4,cfg.coverageCellCount do
            LoadJob.Checkpoint()
            ---@type {x:number,y:number}
            local c=self.cells[i]
            local nearest=math.huge
            for j,q in ipairs(self.cells) do if i~=j then nearest=math.min(nearest,squared(c.x,c.y,q.x,q.y)) end end
            if nearest<best then selected,best=i,nearest end
        end
        updateDensity(self.cells[selected].x,self.cells[selected].y,-1)
        self.cells[selected].x,self.cells[selected].y=tx,ty
        updateDensity(tx,ty,1)
        self.cells[selected].coverageRepaired=true
        self.coverageRepairs=self.coverageRepairs+1
    end
end

-- Complete ordered data: gather keys without using their traversal order,
-- then sort numeric IDs and named properties before serializing recursively.
local function canonical(value)
    if type(value)=="number" then return string.format("%.17g",value) end
    if type(value)=="string" then return string.format("%q",value) end
    if type(value)~="table" then return tostring(value) end
    local keys,parts={},{}
    for key in pairs(value) do keys[#keys+1]=key end
    table.sort(keys,function(a,b)
        if type(a)~=type(b) then return type(a)<type(b) end
        return a<b
    end)
    for _,key in ipairs(keys) do parts[#parts+1]=canonical(key).."="..canonical(value[key]) end
    return "{"..table.concat(parts,",").."}"
end
function Map:Snapshot()
    return canonical({mapKind=self.mapKind,generationVersion=self.generationVersion,seed=self.seed,
        config=self.config,width=self.width,height=self.height,generationAttempt=self.generationAttempt,
        floorRows=self.floorRows,outerBoundary=self.outerBoundary,obstacles=self.obstacles,
        flowSystems=self.flowSystems,flows=self.flows,crossFlows=self.crossFlows,bays=self.bays,majorRoutes=self.majorRoutes,
        spawn=self.spawn,cells=self.cells})
end

---@return number, number
function Map:FlowAt(x,y,time)
    return Layout.FlowAt(self,x,y)
end

return Map
