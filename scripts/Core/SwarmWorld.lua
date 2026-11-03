-- SwarmWorld.lua - 呼吸道感染网络的单机权威模拟（Lua 5.4，米制坐标）。
-- 基于 scaffold-2d.lua 的固定步更新，不依赖绘制、UI 或全局随机数。
--
-- 接触设计：
--  群粒子 v v      细胞 (C)          释放病毒 v -> (C)
--    [群半径] + infectionReach       仅真实位置附近累积感染，不用统计补感染。
--  两群 (A)......(B)  近距吸引 -> 接触合并；分裂后的短暂保护避免立刻合并。
--  免疫 (I) -> 警告 -> 接触 -> 蓄力 -> 少量清除；不远程扣群质量。
--  地图：上呼吸道 -> 气管 -> 左右支气管 -> 深肺；枝间暗区不可穿越。
--  活群清零即失败（SimState 判定），感染节点和 ReleasedVirus 不充当玩家复活。

local Config = require("Core.Config")
local WorldAudioEvents = require("Core.WorldAudioEvents")
local SpatialGrid = require("Core.SpatialGrid")
local SwarmParticles = require("Core.SwarmParticles")
---@class SwarmCardEffectsAPI
---@field Init fun(world:SwarmWorld)
local CardEffects = require("Core.CardEffects") --[[@as SwarmCardEffectsAPI]]
local Abilities = require("Core.AbilityRuntime")
local RespiratoryMap = require("Core.RespiratoryMap")
---@class SwarmImmuneAPI
---@field Init fun(world:SwarmWorld,startDef:table)
---@field InvalidateCell fun(world:SwarmWorld,cellId:integer)
---@field Update fun(world:SwarmWorld,dt:number)
---@field Recruit fun(world:SwarmWorld,dt:number)
local ImmuneSystem = require("Core.ImmuneSystem") --[[@as SwarmImmuneAPI]]
local SplitVirusAI = require("Core.SplitVirusAI")
local Ecology = require("Core.LocalEcology")
---@class SwarmContactAPI
---@field Collect fun(cell:RespiratoryCell,source:table,kind:string,power:number,accepted:table)
---@field CommitWorld fun(world:SwarmWorld,inputs:table)
local CellContacts = require("Core.CellContacts") --[[@as SwarmContactAPI]]
---@class SwarmDiagnosticsAPI
---@field BeginStep fun(world:SwarmWorld,dt:number)
---@field Accepted fun(world:SwarmWorld,cell:RespiratoryCell,accepted:table)
---@field EndStep fun(world:SwarmWorld)
local CellDiagnostics = require("Core.CellDiagnostics") --[[@as SwarmDiagnosticsAPI]]

---@class SwarmRecord
---@field id integer
---@field x number
---@field y number
---@field vx number
---@field vy number
---@field mass integer
---@field radius number
---@field visibility number
---@field isMainSwarm boolean
---@field isPlayerControlled boolean
---@field isHidden boolean
---@field activeMoveDistanceStep number
---@field currentRegionId integer
---@field launchTimer number
---@field launchX number
---@field launchY number
---@field mergeGrace number
---@field exposedCells table<number, boolean>
---@field aiState 'controlled'|'hidden'|'disabled'|'idle'|'flee'|'seek'|'infect'|'collect'|'wander'
---@field controllable boolean?
---@field _aiDangerMemory number
---@field _aiReservationTimer number
---@field aiTargetCellId integer?
---@field _aiSupplyId integer?
---@field _aiExploreX number?
---@field _aiExploreY number?
---@field _aiVisits {x:number,y:number}[]?
---@field _aiSensedCells RespiratoryCell[]?
---@field autoSplitCooldown number 自主活跃成熟/分离冷却；与玩家 splitCooldown 独立。
---@field _aiThinkClock number
---@field _aiTargetHold number
---@field _aiWanderClock number
---@field _aiDirectionX number
---@field _aiDirectionY number
---@field _aiMoveX number
---@field _aiMoveY number
---@field anchored boolean?
---@field relayCellId integer?
---@field glideCellId integer?
---@field glideInputX number?
---@field glideInputY number?
---@field glideDirection number?
---@field dashUntil number?
---@field dashX number?
---@field dashY number?
---@field rescueUntil number?
---@field rescueX number?
---@field rescueY number?
---@field groupCommand table?
---@field recallUntil number?
---@field hasMoveDirection boolean?
---@field lastMoveX number?
---@field lastMoveY number?
---@field hiddenCellId integer?
---@field trailEnabled boolean?
---@field trailDistance number?
---@field camouflaged boolean?
---@field camouflageTime number?
---@field camouflageX number?
---@field camouflageY number?

---@alias CellContactSourceType "PLAYER_SWARM"|"RELEASED_VIRUS"

-- 纯表现快照：法线为 cell -> source，沿本模拟的 Y 向下坐标；不参与感染判定。
---@class CellContactVisual
---@field key string cellId:sourceType:sourceId
---@field cellId integer
---@field distance number
---@field stableLocalAngle number
---@field targetLocalAngle number
---@field stableAngle number 经过滞回/最短弧过滤的cell-local角
---@field candidateLocalAngle number?
---@field candidateFrames integer
---@field rawNormalX number?
---@field rawNormalY number?
---@field rawContactX number?
---@field rawContactY number?
---@field lastValidDirectionX number
---@field lastValidDirectionY number
---@field stableDirectionX number
---@field stableDirectionY number
---@field active boolean
---@field lostTime number
---@field sourceType CellContactSourceType
---@field sourceId integer
---@field sourceX number
---@field sourceY number
---@field sourceRadius number
---@field strength number 接受分支的正 contactPower；绘制强度为 strength * fade
---@field lastSeen number 最后一次真实接受接触的 world.time
---@field firstSeen number 此稳定记录首次接受接触的 world.time
---@field contactSequence integer 同来源重新进入接触时递增，仅用于表现
---@field enteredAt number 本次连续接触开始时间
---@field entryLocalAngle number 本次进入接触的真实局部方向，连续接触期间固定
---@field normalX number
---@field normalY number
---@field visualCellRotation number 采样时 cell.rotation，渲染局部 patch 随后续细胞旋转修正
---@field worldContactX number 按权威 cell.radius 初投影，渲染再按 alpha 膜边缘修正
---@field worldContactY number
---@field fade number 接触结束后 0.75 秒内由 1 淡至 0
---@field _accepted boolean 仅本次 _AccumulateExposure 的视觉暂存标记

---@class CellReleaseVisualDirection
---@field sourceId integer 真实 ReleasedVirusRecord.id
---@field x number 真实出生位置（已经过地图合法性回退）
---@field y number
---@field normalX number
---@field normalY number
---@field visualCellRotation number 出生时的细胞旋转，仅用于保持局部膜锚点

---@class RespiratoryCell
---@field id integer
---@field x number
---@field y number
---@field radius number
---@field variant integer
---@field phase number
---@field rotation number
---@field regionId integer
---@field state string
---@field exposure number
---@field infectedAge number
---@field latencyTimer number
---@field productiveTimer number
---@field pendingProduction integer?
---@field pendingProductionElapsed number?
---@field takeoverReservation table?
---@field shieldHits integer?
---@field coverUsed boolean?
---@field ruptureSpreadUsed boolean?
---@field releaseCount integer
---@field infectionSerial integer? Permanent successful infection order, including initial nodes.
---@field hasReleasedVirus boolean? Permanent first real node release fact.
---@field exhaustionTimer number
---@field exhaustedReleaseTimer number
---@field immuneHits integer
---@field immuneSignalValue number
---@field covered boolean
---@field everPlayerContact boolean
---@field infectionSource string
---@field groupContribution number
---@field releasedContribution number
---@field _charge number
---@field _groupCharge number
---@field _releasedCharge number
---@field contactVisuals CellContactVisual[]
---@field contactVisualAnchor CellContactVisual? 最后真实接触的局部 patch 锚点；不随 fade 删除
---@field infectedVisualAt number? 真实进入 LATENT 的 world.time（含初始预感染，无伪造锚点）
---@field lastReleaseVisualAt number? 最新真实释放批次的 world.time
---@field releaseVisualSequence integer 纯视觉批次序号；不复用业务 releaseCount
---@field releaseVisualDirections CellReleaseVisualDirection[] 最新批次最多 3 个真实非中心出生方向
---@field deathVisualAt number? 真实死亡的 world.time

---@class CellContactVisualStep
---@field pending CellContactVisual[] 最强的最多 3 个尚未占 slot 的真实接受来源
---@field strongest CellContactVisual?
---@field incumbent CellContactVisual?

---@class GroupVirusParticle
---@field id integer
---@field swarmId integer
---@field x number
---@field y number
---@field radius number
---@field variant integer
---@field phase number

---@class ReleasedVirusRecord
---@field nodeProduced boolean? True only for a real infected-node release, never swarm investments.
---@field id integer
---@field x number
---@field y number
---@field vx number
---@field vy number
---@field radius number
---@field variant integer
---@field phase number
---@field sourceCellId integer
---@field sourceRegionId integer
---@field state string
---@field age number
---@field lifetime number
---@field _oldX number
---@field _oldY number
---@field releaseBatchId integer?
---@field sourceSwarmId integer?
---@field tractionOwnerId integer?
---@field decoyUntil number?
---@field origin string?
---@field requiresActiveRecovery boolean? 主动播散单位只接受 E 或已开启的离散回收。

---@class SwarmCounts
---@field virus integer
---@field controlled integer
---@field mainMass integer
---@field splitMass integer
---@field released integer
---@field infected integer
---@field latent integer
---@field productive integer
---@field exhausted integer
---@field healthy integer
---@field exposed integer
---@field dead integer
---@field immune integer
---@field groups integer

---@class SwarmMergePair
---@field aId integer
---@field bId integer

---@class SwarmWorld
---@field tutorial Tutorial?
---@field mergePairs SwarmMergePair[] 存活、无保护、非隐藏且近距可达的群对快照。
---@field swarms SwarmRecord[]
---@field player SwarmRecord
---@field cells RespiratoryCell[]
---@field viruses GroupVirusParticle[]
---@field releasedViruses ReleasedVirusRecord[]
---@field immunes ImmuneCellRecord[]
---@field events table[]
---@field cardEffects table<string, number>
---@field playerTouchedCells table<number, boolean> 本局阶段用永久接触历史。
---@field abilities table
---@field abilityRunId integer?
---@field massLedger table
---@field effects table[]
---@field brainReservations table<number, table<number, boolean>>?
local SwarmWorld = {}
SwarmWorld.__index = SwarmWorld
local TAU = math.pi * 2
local GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))

local function distance(a, b)
    return math.sqrt((a.x - b.x)^2 + (a.y - b.y)^2)
end

local function liveReleased(v)
    return v.state ~= "CLEARED" and v.state ~= "LOST" and v.state ~= "ABSORBED" and v.state ~= "CONVERTED"
end

function SwarmWorld.New(startType)
    local self = setmetatable({}, SwarmWorld)
    self:init(startType)
    return self
end

function SwarmWorld:init(startType)
    self.config = Config.Gameplay
    self.startType = startType or "UPPER_AIRWAY"
    local def = Config.StartRegions[1]
    for _, item in ipairs(Config.StartRegions) do
        if item.type == self.startType then def = item end
    end
    self.map = RespiratoryMap.New(self.config, self.startType)
    self.mapSeed, self.mapGenerationVersion = self.map.seed, self.map.generationVersion
    self.width, self.height = self.map.width, self.map.height
    self._rng = math.max(1, self.config.seed % 2147483647)
    self.time, self.diseaseAccum, self.splitCooldown = 0, 0, 0
    self.activeAbsorptionReadyAt = 0
    self.maxPlayerSwarms = self.config.initialSwarmCapacity
    CardEffects.Init(self)
    self.swarmBrainEnabled = false
    self.tutorial = nil
    self.controlSwitchCount = 0
    self.immuneAlertLevel, self.activeImmuneAlertLevel = 0, 0
    ---@type number?
    self.debugImmuneAlertLevel = nil
    ---@type table?
    self.pendingAlertActivation = nil
    self._inputX, self._inputY, self._aimX, self._aimY = 0, 0, 0, 1
    self._nextGroupId, self._nextVirusId, self._nextReleasedId = 1, 1, 1
    self.swarms, self.viruses, self.releasedViruses, self.immunes = {}, {}, {}, {}
    self.cells, self.effects, self.events = {}, {}, {}
    self.eventSerial=0
    self.contactSerial=0
    self.cellGrid = SpatialGrid.New(Config.Performance.spatialGridSize)
    self.releasedGrid = SpatialGrid.New(Config.Performance.spatialGridSize)
    self._spatialActive = false
    self._cellSpatialActive = false
    ---@type SwarmCounts?
    self._countsSnapshot = nil
    self.stats = {
        totalInfected = 0, totalReleased = 0, totalKilled = 0, totalLost = 0,
        totalSplits = 0, totalAutoSplits = 0, totalMerges = 0, totalAbsorbed = 0,
        independentInfections = 0, peakVirus = def.mass, splitCost = 0, initialMass = def.mass,
        brainAssistedInfections = 0, brainMassLost = 0,
    }
    self.mergeReady, self.mergePairs = false, {}
    self.globalInflammation, self.globalTissueDamage = 0, 0
    for _, spawn in ipairs(self.map.cells) do
        self.cells[#self.cells + 1] = {
            id = spawn.id, x = spawn.x, y = spawn.y, radius = spawn.radius,
            variant = spawn.variant, phase = spawn.phase, rotation = spawn.rotation,
            regionId = spawn.regionId, state = "HEALTHY", exposure = 0,
            infectedAge = 0, latencyTimer = 0, productiveTimer = 0, releaseCount = 0,
            exhaustionTimer = 0, exhaustedReleaseTimer = 0, immuneHits = 0, immuneSignalValue = 1,
            covered = false, everPlayerContact = false, infectionSource = "none",
            groupContribution = 0, releasedContribution = 0,
            _charge = 0, _groupCharge = 0, _releasedCharge = 0,
            contactVisuals = {}, releaseVisualSequence = 0, releaseVisualDirections = {},
        }
    end
    local point = self.map.startPoints[self.startType]
    self.player = self:_CreateSwarm(point.x, point.y, def.mass, true)
    self.currentControlledSwarmId = self.player.id
    self:_UpdateParticles()
    if def.initialNodes > 0 then
        local nearest, best = self.cells[1], math.huge
        for _, cell in ipairs(self.cells) do
            local d = distance(cell, self.player)
            if d < best then nearest, best = cell, d end
        end
        self:_Infect(nearest, "initial")
    end
    Ecology.Init(self)
    ImmuneSystem.Init(self, def)
    self.events = {} -- 初始设置不作为玩家首次行为。
    self._logClock = 0
    print(string.format("[SwarmWorld] 呼吸道开局=%s 细胞=%d 主群=%d 免疫=%d", def.name,
        #self.cells, self.player.mass, #self.immunes))
end

function SwarmWorld:_Random()
    self._rng = (self._rng * 48271) % 2147483647
    return self._rng / 2147483647
end

function SwarmWorld:Emit(name, payload)
    self:InvalidateCounts()
    self.eventSerial=self.eventSerial+1
    self.events[#self.events + 1] = { name = name, payload = payload or {}, time = self.time, serial=self.eventSerial,
        audio = WorldAudioEvents.Capture(self, name, payload or {}) }
end

function SwarmWorld:InvalidateCounts()
    self._countsSnapshot = nil
end

-- Public Counts remains a fresh read for tools/fixtures which directly edit state.
-- Runtime readers explicitly share the post-step snapshot until an action changes it.
function SwarmWorld:GetCountsSnapshot()
    return self._countsSnapshot or self:Counts()
end

function SwarmWorld:NearbyCells(x,y,reach,result)
    if not self._cellSpatialActive and not self._spatialActive then return self.cells end
    return self.cellGrid:Query(x,y,reach+self.cellGrid.maxRadius,result)
end

function SwarmWorld:NearbyReleased(x,y,reach,result)
    if not self._spatialActive then return self.releasedViruses end
    -- Immune node destruction may append rupture-spread viruses mid-phase.
    -- Later immune actors and contact resolution must see them in this step.
    if self.releasedGrid.sourceCount~=#self.releasedViruses then
        self.releasedGrid:Build(self.releasedViruses)
    end
    return self.releasedGrid:Query(x,y,reach+self.releasedGrid.maxRadius,result)
end

function SwarmWorld:_Effect(kind, x, y, radius)
    self.effects[#self.effects + 1] = { kind = kind, x = x, y = y, radius = radius, age = 0, duration = 0.8 }
end

function SwarmWorld:SetMovement(x, y)
    if x ~= x or y ~= y then x, y = 0, 0 end
    local length = math.sqrt(x*x + y*y)
    local divisor = math.max(1, length)
    self._inputX, self._inputY = x/divisor, y/divisor
    if length > 0.05 then
        self:SetAim(x, y)
        local s=self:SwarmById(self.currentControlledSwarmId)
        if s then s.hasMoveDirection=true;s.lastMoveX,s.lastMoveY=x/length,y/length end
    end
end

function SwarmWorld:SetAim(x, y)
    local length = math.sqrt(x*x + y*y)
    if length > 0.0001 then self._aimX, self._aimY = x/length, y/length end
end

function SwarmWorld:_CreateSwarm(x, y, mass, main)
    self:InvalidateCounts()
    local id = self._nextGroupId
    self._nextGroupId = id + 1
    ---@type SwarmRecord
    local swarm = {
        id = id, x = x, y = y, vx = 0, vy = 0, mass = mass,
        radius = self.config.groupRadius, visibility = 1,
        isMainSwarm = main, isPlayerControlled = main, isHidden = false,
        currentRegionId = self.map:RegionAt(x, y), launchTimer = 0,
        launchX = 0, launchY = 0, mergeGrace = 0, exposedCells = {},
        aiState = main and "controlled" or "wander", aiTargetCellId = nil,
        autoSplitCooldown = self.config.autonomy and self.config.autonomy.splitCooldown or 8,
        _aiThinkClock = 0, _aiTargetHold = 0, _aiWanderClock = 0,
        _aiDirectionX = 0, _aiDirectionY = 0, _aiMoveX = x, _aiMoveY = y,
    }
    self.swarms[#self.swarms + 1] = swarm
    self:_AddParticles(swarm, mass)
    return swarm
end

---@param swarm SwarmRecord
---@param count integer
---@param source? ReleasedVirusRecord
function SwarmWorld:_AddParticles(swarm, count, source)
    for _ = 1, count do
        local id = self._nextVirusId
        self._nextVirusId = id + 1
        self.viruses[#self.viruses + 1] = {
            id = id, swarmId = swarm.id, x = swarm.x, y = swarm.y,
            radius = source and source.radius or self.config.virusRadius,
            variant = source and source.variant or math.floor(self:_Random()*4)+1,
            phase = source and source.phase or self:_Random()*TAU,
        }
    end
end

-- 吸附范围示意（米）：
--   游离 v -- 完整直线扫掠 --> [当前群半径 R] + activeAbsorptionExtra
--   枝间暗区 || / 地图矩形外均阻挡；细胞不阻挡，与地图 Move 的规则相同。
--   恰好在范围边缘可收；终态、寿命到期、无活群均不可收；一次按下只取原范围快照。
---@param x number
---@param y number
---@param tx number
---@param ty number
---@param radius number
---@return boolean
function SwarmWorld:_DirectPathClear(x, y, tx, ty, radius)
    if self.map:_ConvexPathClear(x,y,tx,ty,radius) then return true end
    if not self.map:Contains(x, y, radius) or not self.map:Contains(tx, ty, radius) then return false end
    -- Move 会沿墙滑移，不能仅以最终位置接近目标判断直线无阻挡。
    -- 复用其精确区间扫掠，不用离散采样跨过极细枝间空隙。
    local fraction = self.map:_Sweep(x, y, tx-x, ty-y, radius)
    return fraction >= 1
end

---@param swarm SwarmRecord
function SwarmWorld:_RefreshGroupShape(swarm)
    local desiredRadius = math.max(0.20, math.min(1.35,
        self.config.groupRadius * math.sqrt(math.max(1, swarm.mass)/30)))
    -- 只压缩阵型、不挪中心：吸附/合并后即时生效，贴墙也保留合法移动起点。
    if not self.map:Contains(swarm.x, swarm.y, desiredRadius) then
        local lo, hi = math.min(swarm.radius, desiredRadius), desiredRadius
        if not self.map:Contains(swarm.x, swarm.y, lo) then lo = 0 end
        for _ = 1, 14 do
            local middle = (lo+hi)*0.5
            if self.map:Contains(swarm.x, swarm.y, middle) then lo=middle else hi=middle end
        end
        desiredRadius = lo
    end
    swarm.radius = desiredRadius
    swarm.visibility = 0.7 + math.sqrt(math.max(0, swarm.mass)/30)*0.3
end

---@param swarm SwarmRecord
---@param virus ReleasedVirusRecord
---@return boolean
function SwarmWorld:_CanAbsorbReleased(swarm, virus)
    return swarm.mass > 0 and not swarm.isHidden and not swarm.relayCellId and liveReleased(virus) and virus.age < virus.lifetime
        and self:_DirectPathClear(virus.x, virus.y, swarm.x, swarm.y, virus.radius)
end

---@param swarm SwarmRecord
---@param virus ReleasedVirusRecord
---@return boolean
function SwarmWorld:_CanPassivelyAbsorbReleased(swarm, virus)
    return (not virus.requiresActiveRecovery or (swarm.recallUntil or 0)>self.time)
        and self:_CanAbsorbReleased(swarm,virus)
end

---@param swarm SwarmRecord
---@param virus ReleasedVirusRecord
---@return boolean
function SwarmWorld:_AbsorbReleased(swarm, virus, method)
    if self:SwarmById(swarm.id) ~= swarm or not self:_CanAbsorbReleased(swarm, virus) then return false end
    virus.state = "ABSORBED"
    swarm.mass = swarm.mass + 1
    self:_AddParticles(swarm, 1, virus)
    self:_RefreshGroupShape(swarm)
    Abilities.Record(self,"absorb_recovery",1,virus.id,swarm.id)
    self.stats.totalAbsorbed = self.stats.totalAbsorbed + 1
    self:_Effect("join", virus.x, virus.y, virus.radius*2)
    self:Emit("absorb", { swarmId=swarm.id, sourceCellId=virus.sourceCellId,virusId=virus.id,
        nodeProduced=virus.nodeProduced==true,method=method,infectionBaseline=self.stats.totalInfected })
    return true
end

---@return ReleasedVirusRecord[]
function SwarmWorld:_NearbyAbsorbable()
    local result = {}
    local swarm = self:SwarmById(self.currentControlledSwarmId)
    if not swarm or swarm.mass <= 0 or swarm.isHidden then return result end
    local range = swarm.radius + self.config.activeAbsorptionExtra
    for _, virus in ipairs(self.releasedViruses) do
        if distance(virus, swarm) <= range+1e-9 and self:_CanAbsorbReleased(swarm, virus) then
            result[#result+1] = virus
        end
    end
    return result
end

---@return integer
function SwarmWorld:AbsorbableCount()
    return #self:_NearbyAbsorbable()+Abilities.RelayRecoverableMass(self,self:SwarmById(self.currentControlledSwarmId))
end

function SwarmWorld:GetAbsorptionCooldown()
    return math.max(0, self.activeAbsorptionReadyAt - self.time)
end

---@return integer
---@return string? reason
function SwarmWorld:AbsorbNearby()
    local swarm = self:SwarmById(self.currentControlledSwarmId)
    if not swarm or swarm.mass <= 0 or swarm.isHidden then return 0 end
    local cooldown = self:GetAbsorptionCooldown()
    if cooldown > 1e-9 then return 0, string.format("基础吸附冷却 %.1f秒", cooldown) end
    Abilities.RecoverRelays(self,swarm)
    self.activeAbsorptionReadyAt = self.time + self.config.activeAbsorptionCooldown
    local radius = swarm.radius + self.config.activeAbsorptionExtra
    local count = 0
    for _, virus in ipairs(self:_NearbyAbsorbable()) do
        if self:_AbsorbReleased(swarm, virus,"basic") then count = count + 1 end
    end
    self:_UpdateParticles()
    self.stats.peakVirus = math.max(self.stats.peakVirus, self:Counts().virus)
    self:_Effect("absorb", swarm.x, swarm.y, radius)
    self:Emit("absorb_pulse", { count=count, swarmId=swarm.id })
    return count
end

---@param swarm SwarmRecord
---@return number
function SwarmWorld:GroupInfectionMultiplier(swarm)
    return math.sqrt(math.max(0, swarm.mass)/self.config.densityReference)
end

function SwarmWorld:SwarmById(id)
    for _, swarm in ipairs(self.swarms) do if swarm.id == id then return swarm end end
    return nil
end

function SwarmWorld:MainSwarm()
    for _, swarm in ipairs(self.swarms) do if swarm.isMainSwarm then return swarm end end
    return nil
end

function SwarmWorld:ControlledCount()
    local count = 0
    for _, swarm in ipairs(self.swarms) do count = count + swarm.mass end
    return count
end

function SwarmWorld:_RefreshGroups()
    self:InvalidateCounts()
    for i = #self.swarms, 1, -1 do
        local swarm = self.swarms[i]
        if swarm.mass <= 0 then
            if not swarm.isMainSwarm then self:Emit("split_lost", { swarmId = swarm.id }) end
            self:Emit("swarm_cleared", { swarmId = swarm.id })
            swarm.isMainSwarm, swarm.isPlayerControlled = false, false
            SplitVirusAI.ResetSwarm(self,swarm,false)
            table.remove(self.swarms, i)
        end
    end
    if #self.swarms > 0 then
        if not self:MainSwarm() then self.swarms[1].isMainSwarm = true end
        local active = self:SwarmById(self.currentControlledSwarmId)
        if not self:CanControl(active) then
            active = nil
            for _, candidate in ipairs(self.swarms) do
                if self:CanControl(candidate) then active = candidate; break end
            end
            self.currentControlledSwarmId = active and active.id or 0
            if active then active.vx, active.vy = 0, 0;active.relayCellId=nil end
            self:SetMovement(0, 0)
        end
        if active then self.player = active end
        for _, swarm in ipairs(self.swarms) do
            local controlled = swarm.id == self.currentControlledSwarmId
            if swarm.isPlayerControlled ~= controlled then
                swarm.isPlayerControlled = controlled
                SplitVirusAI.ResetSwarm(self,swarm,false)
            end
        end
    else
        self.currentControlledSwarmId = 0
        self:SetMovement(0, 0)
    end
    self:_RefreshMergePairs()
    -- 最后一个群的坐标仅供结算镜头使用，不作为复活/感染源。
end

function SwarmWorld:DamageSwarm(id, count)
    local swarm = self:SwarmById(id)
    if not swarm then return 0 end
    local remaining = math.min(swarm.mass, math.max(0, math.floor(count)))
    local killed = remaining
    if SplitVirusAI.IsAutonomous(self,swarm) then self.stats.brainMassLost=self.stats.brainMassLost+killed end
    for _,virus in ipairs(SwarmParticles.Take(self.viruses,id,killed)) do
        self:_Effect("engulf", virus.x, virus.y, virus.radius*2)
    end
    Abilities.Record(self,"immune_clear",killed,id)
    swarm.mass = swarm.mass - killed
    self:_RefreshGroupShape(swarm)
    self.stats.totalKilled = self.stats.totalKilled + killed
    self:_RefreshGroups()
    return killed
end

function SwarmWorld:KillReleased(virus)
    if not liveReleased(virus) then return false end
    virus.state = "CLEARED"
    Abilities.Record(self,"immune_clear",1,virus.id)
    self.stats.totalKilled = self.stats.totalKilled + 1
    self:_Effect("engulf", virus.x, virus.y, virus.radius*2)
    return true
end

---@return integer
function SwarmWorld:LiveSwarmCount()
    local count = 0
    for _, swarm in ipairs(self.swarms) do if swarm.mass > 0 then count = count+1 end end
    return count
end

function SwarmWorld:CanControl(swarm)
    return swarm ~= nil and swarm.mass > 0 and not swarm.isHidden and swarm.controllable ~= false
end

---@return string?
function SwarmWorld:SplitUnavailableReason()
    local swarm = self:SwarmById(self.currentControlledSwarmId)
    if not self:CanControl(swarm) then return "当前群不可控制" end
    if swarm.mass < self.config.splitMinMass then return "至少需要12病毒" end
    if self:LiveSwarmCount() >= self.maxPlayerSwarms then return "群体数量已达上限" end
    if self.splitCooldown > 1e-9 then return string.format("分裂冷却 %.1f秒", self.splitCooldown) end
    return nil
end

function SwarmWorld:CanSplit()
    local cfg, swarm = self.config, self:SwarmById(self.currentControlledSwarmId)
    if self:SplitUnavailableReason() then return false end
    local cost = math.max(1, math.floor(swarm.mass*cfg.splitCostFraction))
    local splitMass = math.floor((swarm.mass-cost)*cfg.splitFraction)
    return splitMass >= 1 and swarm.mass-cost-splitMass >= 1
end

function SwarmWorld:Split()
    if not self:CanSplit() then return false end
    local swarm = self:SwarmById(self.currentControlledSwarmId)
    if not swarm then return false end
    return self:_SplitSwarm(swarm,self._aimX,self._aimY,false)
end

-- 共用真实分离损耗/原粒子归属；自动分离不抢控制、不写玩家splitCooldown。
---@param swarm SwarmRecord
---@param aimX number
---@param aimY number
---@param automatic boolean
---@return boolean
function SwarmWorld:_SplitSwarm(swarm,aimX,aimY,automatic)
    if automatic or self:LiveSwarmCount() >= self.maxPlayerSwarms
        or self:SwarmById(swarm.id) ~= swarm or swarm.mass < self.config.splitMinMass
        or not self:CanControl(swarm) or self.splitCooldown > 1e-9 then return false end
    local cfg = self.config
    Abilities.BreakCamouflage(swarm)
    Abilities.SetAnchor(self,swarm,false);swarm.glideCellId=nil;swarm.groupCommand=nil
    local splitSourceMass = swarm.mass
    local launchScale = math.sqrt(math.max(1, splitSourceMass / math.max(1, cfg.initialMass)))
    local cost = math.max(1, math.floor(swarm.mass*cfg.splitCostFraction))
    local splitMass = math.floor((swarm.mass-cost)*cfg.splitFraction)
    if splitMass < 1 or swarm.mass-cost-splitMass < 1 then return false end
    -- 分裂损耗独立记账，不冒充免疫击杀；原有粒子转移，不凭空增加。
    SwarmParticles.Take(self.viruses,swarm.id,cost)
    swarm.mass = swarm.mass - cost
    local other = self:_CreateSwarm(swarm.x, swarm.y, 0, false)
    for id in pairs(swarm.exposedCells) do other.exposedCells[id]=true end
    other.mass = splitMass
    local moved = 0
    for i = #self.viruses, 1, -1 do
        local v = self.viruses[i]
        if v.swarmId == swarm.id and moved < splitMass then v.swarmId = other.id; moved = moved + 1 end
    end
    swarm.mass = swarm.mass - splitMass
    -- launchScale基于分裂前质量快照，避免扣除分裂质量后缩小弹射力。
    other.launchTimer, swarm.launchTimer = cfg.splitLaunchSeconds, cfg.splitLaunchSeconds
    other.launchX, other.launchY = aimX*cfg.splitLaunchSpeed*launchScale,
        aimY*cfg.splitLaunchSpeed*launchScale
    swarm.launchX, swarm.launchY = -aimX*cfg.splitRecoil*launchScale,
        -aimY*cfg.splitRecoil*launchScale
    other.mergeGrace, swarm.mergeGrace = cfg.mergeGraceSeconds, cfg.mergeGraceSeconds
    if not automatic then self.splitCooldown = cfg.splitCooldown end
    SplitVirusAI.ResetSwarm(self,swarm,true)
    SplitVirusAI.ResetSwarm(self,other,true)
    self:_RefreshGroupShape(swarm)
    self:_RefreshGroupShape(other)
    self:_RefreshMergePairs()
    Abilities.Record(self,"split_cost",cost,swarm.id)
    self.stats.splitCost = self.stats.splitCost + cost
    self.stats.totalSplits = self.stats.totalSplits + 1
    if automatic then self.stats.totalAutoSplits = self.stats.totalAutoSplits+1 end
    self:_Effect("split", swarm.x, swarm.y, swarm.radius)
    self:Emit(automatic and "auto_split" or "split", { sourceSwarmId=swarm.id, swarmId=other.id, cost=cost })
    print(string.format("[SwarmWorld] %s分离 source=%d child=%d 损耗%d 源群%d 子群%d",
        automatic and "自主" or "手动",swarm.id,other.id,cost,swarm.mass,splitMass))
    return true
end

---@return integer
function SwarmWorld:_AutoSplitGroups()
    return 0 -- 自动分裂不属于本次正式卡牌能力。
end

---@param swarmId? integer
---@return boolean
function SwarmWorld:SwitchControl(swarmId)
    ---@type SwarmRecord?
    local target = nil
    if swarmId then
        target = self:SwarmById(swarmId)
    else
        local activeIndex = 0
        for i, swarm in ipairs(self.swarms) do
            if swarm.id == self.currentControlledSwarmId then activeIndex = i; break end
        end
        for offset = 1, #self.swarms do
            local candidate = self.swarms[(activeIndex+offset-1)%#self.swarms+1]
            if self:CanControl(candidate) then target = candidate; break end
        end
    end
    if not self:CanControl(target) or target.id == self.currentControlledSwarmId then return false end
    -- 清除 AI 自身的驱动惯性；弹射和组织流仍由原移动管线处理。
    target.vx, target.vy = 0, 0
    target.groupCommand=nil;target.glideCellId=nil;target.relayCellId=nil
    self.currentControlledSwarmId = target.id
    self.controlSwitchCount = self.controlSwitchCount+1
    self:_RefreshGroups()
    self:SetMovement(0, 0)
    self:Emit("switch_control", { swarmId=target.id })
    return true
end

function SwarmWorld:_MoveGroups(dt)
    local cfg = self.config
    for _, swarm in ipairs(self.swarms) do self:_RefreshGroupShape(swarm) end
    SplitVirusAI.ThinkWorld(self,dt)
    for _, swarm in ipairs(self.swarms) do
        swarm.mergeGrace = math.max(0, swarm.mergeGrace-dt)
        swarm.activeMoveDistanceStep=0
        local speed = math.max(cfg.minSpeed, cfg.baseSpeed/math.sqrt(math.max(1, swarm.mass/30)))
        local desiredX, desiredY = 0, 0
        if swarm.isPlayerControlled then
            desiredX, desiredY = self._inputX*speed, self._inputY*speed
        elseif SplitVirusAI.IsAutonomous(self,swarm) then
            desiredX,desiredY = SplitVirusAI.DesiredVelocity(self,swarm,speed,dt)
        else
            desiredX = math.cos(self.time*0.32 + swarm.id)*cfg.inactiveDrift
            desiredY = math.sin(self.time*0.29 + swarm.id)*cfg.inactiveDrift
        end
        local special
        desiredX,desiredY,special=Abilities.Movement(self,swarm,desiredX,desiredY,speed,dt)
        local response = cfg.turnResponse/math.sqrt(math.max(1, swarm.mass/30))
        local blend = 1-math.exp(-response*dt)
        swarm.vx = swarm.vx+(desiredX-swarm.vx)*blend
        swarm.vy = swarm.vy+(desiredY-swarm.vy)*blend
        local flowX, flowY = self.map:FlowAt(swarm.x, swarm.y, self.time)
        local influence = swarm.isMainSwarm and cfg.playerFlowInfluence or cfg.splitFlowInfluence
        if self.map.isFlatMap then influence=cfg.flatMapFlowInfluence or influence end
        local vx, vy = swarm.vx+flowX*influence, swarm.vy+flowY*influence
        if special then vx,vy=desiredX,desiredY end
        local launching = swarm.launchTimer > 0
        if launching then
            local factor = (special or swarm.aiState=="flee") and 0 or swarm.launchTimer/cfg.splitLaunchSeconds
            vx, vy = vx+swarm.launchX*factor, vy+swarm.launchY*factor
            swarm.launchTimer = math.max(0, swarm.launchTimer-dt)
        end
        if not swarm.isHidden then
            local ox,oy=swarm.x,swarm.y
            local nx,ny = self.map:Move(swarm.x, swarm.y, swarm.x+vx*dt, swarm.y+vy*dt, swarm.radius)
            if SplitVirusAI.IsAutonomous(self,swarm) then
                nx,ny = SplitVirusAI.RestrictCellMotion(self,swarm,nx,ny)
            end
            swarm.x,swarm.y = self.map:Move(swarm.x,swarm.y,nx,ny,swarm.radius)
            if swarm.isPlayerControlled and not launching and (not special or swarm.glideCellId) and (self._inputX~=0 or self._inputY~=0) then
                -- Only count realised movement in the input direction, bounded
                -- by the smoothed active velocity with flow/launch removed.
                local activeX,activeY=swarm.vx,swarm.vy
                if special then activeX,activeY=desiredX,desiredY end
                local ax,ay=self.map:Move(ox,oy,ox+activeX*dt,oy+activeY*dt,swarm.radius)
                local inputLength=math.sqrt(self._inputX^2+self._inputY^2)
                local realised=0
                if swarm.glideCellId then
                    -- Glide input chooses orbit intent, not a fixed world-space direction.
                    -- This special movement excludes flow; count only its collision-limited path.
                    realised=math.sqrt((swarm.x-ox)^2+(swarm.y-oy)^2)
                else
                    realised=((swarm.x-ox)*self._inputX+(swarm.y-oy)*self._inputY)/inputLength
                end
                swarm.activeMoveDistanceStep=math.max(0,math.min(realised,math.sqrt((ax-ox)^2+(ay-oy)^2)))
            end
            Abilities.AfterMovement(self,swarm,ox,oy,swarm.activeMoveDistanceStep)
        end
        local region = self.map:RegionAt(swarm.x, swarm.y)
        if region ~= swarm.currentRegionId then
            self:Emit("region_enter", { swarmId=swarm.id, from=swarm.currentRegionId, regionId=region })
            swarm.currentRegionId = region
        end
    end
    self:_RefreshMergePairs()
    local pending, used = self.mergePairs, {}
    -- 使用 id 快照而不是可被删除的数组索引；每群每步最多参与一次，避免失效引用/重复合并。
    for _, pair in ipairs(pending) do
        local a, b = self:SwarmById(pair.aId), self:SwarmById(pair.bId)
        if a and b and not used[a.id] and not used[b.id] and self:_CanMergePair(a, b) then
            used[a.id], used[b.id] = true, true
            local d, contact = distance(a,b), a.radius+b.radius
            if d > 0.0001 then
                local amount = math.min((d-contact)*0.5, cfg.mergeSpeed*dt)
                if amount > 0 then
                    local dx, dy = (b.x-a.x)/d*amount, (b.y-a.y)/d*amount
                    a.x,a.y = self.map:Move(a.x,a.y,a.x+dx,a.y+dy,a.radius)
                    b.x,b.y = self.map:Move(b.x,b.y,b.x-dx,b.y-dy,b.radius)
                end
            end
            if distance(a,b) <= contact+0.015 then self:_Merge(a,b) end
        end
    end
    self:_RefreshMergePairs()
end

---@param a SwarmRecord
---@param b SwarmRecord
---@return boolean
function SwarmWorld:_CanMergePair(a, b)
    return a.id ~= b.id and a.mass > 0 and b.mass > 0 and a.mergeGrace <= 0 and b.mergeGrace <= 0
        and not a.isHidden and not b.isHidden and not a.relayCellId and not b.relayCellId and not a.anchored and not b.anchored and not a.glideCellId and not b.glideCellId and distance(a,b) <= a.radius+b.radius+self.config.mergeExtra
        and self:_DirectPathClear(a.x, a.y, b.x, b.y, math.min(a.radius,b.radius))
end

-- 近距合并是玩家附近的机会，不是自主群的目标。逃逸/感染/收集方向优先，
-- 两个自主群不会被隐式牵引归并；显式 _Merge 的几何/守恒核心保持独立。
---@param a SwarmRecord
---@param b SwarmRecord
---@return boolean
function SwarmWorld:_MergeIntentAllowed(a,b)
    if not SplitVirusAI.Enabled(self) then return true end
    if not a.isPlayerControlled and not b.isPlayerControlled then return false end
    if (SplitVirusAI.IsAutonomous(self,a) and a.aiState=="flee")
        or (SplitVirusAI.IsAutonomous(self,b) and b.aiState=="flee") then return false end
    -- 玩家真正靠近接触可回收忙于感染的群，但不能远距拉走其目标，也不能抢逃逸。
    if distance(a,b) <= a.radius+b.radius+0.015 then return true end
    for _, swarm in ipairs({a,b}) do
        if SplitVirusAI.IsAutonomous(self,swarm) and (swarm.aiState=="seek"
            or swarm.aiState=="infect" or swarm.aiState=="collect") then return false end
    end
    return true
end

function SwarmWorld:_RefreshMergePairs()
    self.mergePairs = {}
    ---@type table<string, number>
    local gaps = {}
    ---@type table<string, boolean>
    local touching = {}
    -- 无数量上限的空间候选，桶宽取本步最大可能接触范围；相邻9桶完整涵盖合法对。
    -- 不取前N、不丢拥挤桶；最坏同点仍需完整n²对，远距不再每步做全对Sweep。
    local maxRadius = 0
    for _, swarm in ipairs(self.swarms) do maxRadius=math.max(maxRadius,swarm.radius) end
    local bucketSize = math.max(0.1,maxRadius*2+self.config.mergeExtra)
    ---@type table<string, integer[]>
    local buckets = {}
    for i, swarm in ipairs(self.swarms) do
        local key = math.floor(swarm.x/bucketSize)..":"..math.floor(swarm.y/bucketSize)
        if not buckets[key] then buckets[key]={} end
        local bucket = buckets[key]
        bucket[#bucket+1] = i
    end
    for i, a in ipairs(self.swarms) do
        local bx,by = math.floor(a.x/bucketSize),math.floor(a.y/bucketSize)
        for dx=-1,1 do for dy=-1,1 do
            local bucket = buckets[(bx+dx)..":"..(by+dy)]
            if bucket then for _,j in ipairs(bucket) do
                local b = self.swarms[j]
                if j>i and self:_MergeIntentAllowed(a,b) and self:_CanMergePair(a,b) then
                    local aId,bId = math.min(a.id,b.id),math.max(a.id,b.id)
                    local key = aId..":"..bId
                    local contact,d = a.radius+b.radius,distance(a,b)
                    gaps[key] = (d-contact)/math.max(contact,0.0001)
                    touching[key] = d<=contact+0.015
                    self.mergePairs[#self.mergePairs+1] = {aId=aId,bId=bId}
                end
            end end
        end end
    end
    table.sort(self.mergePairs, function(a,b)
        local aKey, bKey = a.aId..":"..a.bId, b.aId..":"..b.bId
        if touching[aKey] ~= touching[bKey] then return touching[aKey] end
        if gaps[aKey] ~= gaps[bKey] then return gaps[aKey] < gaps[bKey] end
        if a.aId ~= b.aId then return a.aId < b.aId end
        return a.bId < b.bId
    end)
    self.mergeReady = #self.mergePairs > 0
end

---@param a SwarmRecord
---@param b SwarmRecord
---@return boolean
function SwarmWorld:_Merge(a,b)
    if self:SwarmById(a.id) ~= a or self:SwarmById(b.id) ~= b or not self:_CanMergePair(a,b) then return false end
    local keep = a
    if b.isMainSwarm or (not a.isMainSwarm and
        (b.id == self.currentControlledSwarmId or (a.id ~= self.currentControlledSwarmId and b.id < a.id))) then
        keep = b
    end
    local other = keep == a and b or a
    local total = keep.mass+other.mass
    local x = (keep.x*keep.mass+other.x*other.mass)/total
    local y = (keep.y*keep.mass+other.y*other.mass)/total
    keep.x,keep.y = self.map:Move(keep.x,keep.y,x,y,keep.radius)
    keep.mass = total
    Abilities.BreakCamouflage(keep)
    keep.groupCommand=nil
    for _, v in ipairs(self.viruses) do if v.swarmId == other.id then v.swarmId = keep.id end end
    for id in pairs(other.exposedCells) do keep.exposedCells[id] = true end
    -- 只删除本对败方，其他分群/主群/受控群及其粒子与感染任务不受影响。
    for i = #self.swarms, 1, -1 do
        if self.swarms[i].id == other.id then table.remove(self.swarms, i); break end
    end
    other.mass, other.isMainSwarm, other.isPlayerControlled = 0, false, false
    SplitVirusAI.ResetSwarm(self,other,false)
    SplitVirusAI.ResetSwarm(self,keep,false)
    if self.currentControlledSwarmId == other.id then
        self.currentControlledSwarmId = keep.id
        self:SetMovement(0, 0)
    end
    self:_RefreshGroupShape(keep)
    self:_RefreshGroups()
    Abilities.OnMerge(self,keep)
    self.stats.totalMerges = self.stats.totalMerges+1
    self:_Effect("join",keep.x,keep.y,keep.radius)
    self:Emit("merge", { swarmId=keep.id, absorbedSwarmId=other.id })
    return true
end

function SwarmWorld:_UpdateParticles()
    ---@type table<number, SwarmRecord>
    local groups = {}
    ---@type table<number, integer>
    local indices = {}
    for _, swarm in ipairs(self.swarms) do groups[swarm.id]=swarm end
    -- 单次遍历仍按原数组顺序保每群阵型索引，等价于旧n群*全粒子扫描。
    for _, v in ipairs(self.viruses) do
        local swarm = groups[v.swarmId]
        if swarm then
            local index = (indices[swarm.id] or 0)+1
            indices[swarm.id] = index
            local fraction = (index-0.5)/math.max(1,swarm.mass)
            local radius = swarm.radius*math.sqrt(fraction)
            local angle = v.id*GOLDEN_ANGLE + math.sin(self.time*0.3+v.phase)*0.08
            local x,y = swarm.x+math.cos(angle)*radius,swarm.y+math.sin(angle)*radius
            if self.map:Contains(x,y,v.radius) then v.x,v.y=x,y else v.x,v.y=swarm.x,swarm.y end
        end
    end
end

function SwarmWorld:AddInflammation(regionId, amount, damage)
    local r = self.map.regions[regionId]
    if not r then return end
    local oldInflammation,oldDamage=r.inflammation,r.damage
    r.inflammation = math.max(0,r.inflammation+amount)
    r.damage = math.max(0,r.damage+(damage or 0))
    -- 接触攻击和清群可能发生在同一移动步，阈值不能等下次病程步才汇总。
    self.globalInflammation=self.globalInflammation+r.inflammation-oldInflammation
    self.globalTissueDamage=self.globalTissueDamage+r.damage-oldDamage
end

function SwarmWorld:_StampContact(cell)
    self.contactSerial=(self.contactSerial or 0)+1
    cell.contactSerial=self.contactSerial
end

function SwarmWorld:_Infect(cell, source)
    if cell.state ~= "HEALTHY" and cell.state ~= "EXPOSED" then return end
    -- 没有经过接触累积的直接感染（夹具、开局节点）在感染瞬间起步。
    if not cell.contactSerial then self:_StampContact(cell) end
    Ecology.ClearDefense(self,cell)
    cell.state,cell.exposure,cell.infectedAge = "LATENT",1,0
    cell.infectedVisualAt = self.time -- 纯视觉时间戳，不发送额外事件，也不补接触锚点。
    cell.latencyTimer = 0
    cell.infectionSource = source
    self.stats.totalInfected = self.stats.totalInfected+1
    cell.infectionSerial=self.stats.totalInfected
    if source=="player" then
        for _, swarm in ipairs(self.swarms) do
            if SplitVirusAI.IsAutonomous(self,swarm) and swarm.exposedCells[cell.id] then
                self.stats.brainAssistedInfections=self.stats.brainAssistedInfections+1
                break -- 同一节点参与者再多也只计一次辅助完成。
            end
        end
    end
    self:AddInflammation(cell.regionId,self.config.infectionInflammation)
    self:_Effect("infect",cell.x,cell.y,cell.radius)
    self:Emit("infection_complete",{cellId=cell.id,source=source})
    Abilities.FinishRelays(self,cell.id)
    if source == "released" then
        self.stats.independentInfections = self.stats.independentInfections+1
        self:Emit("independent_infection",{cellId=cell.id})
    end
end

function SwarmWorld:KillCell(cell, reason)
    if cell.state == "DEAD" then return end
    local oldState=cell.state
    Ecology.ClearDefense(self,cell)
    cell.state,cell.covered,cell.exposure = "DEAD",false,0
    Abilities.NodeDeath(self,cell,oldState,reason)
    ImmuneSystem.InvalidateCell(self,cell.id)
    SplitVirusAI.CleanTargets(self)
    Ecology.Pulse(self,cell.x,cell.y,"damage",self.config.ecology and self.config.ecology.deathPulse or 0)
    cell.deathVisualAt = self.time
    self:AddInflammation(cell.regionId,self.config.deadInflammation,self.config.deadDamage)
    self:_Effect("rupture",cell.x,cell.y,cell.radius)
    self:Emit("cell_dead",{cellId=cell.id,reason=reason})
end

function SwarmWorld:_Release(cell,count)
    if cell.state=="DEAD" then return end
    local nodeProduced=cell.infectionSerial~=nil
    if count>0 and nodeProduced then cell.hasReleasedVirus=true end
    cell.lastReleaseVisualAt = self.time
    cell.releaseVisualSequence = cell.releaseVisualSequence + 1
    cell.releaseVisualDirections = {}
    for index = 1,count do
        local angle = self:_Random()*TAU
        local r = cell.radius+self.config.virusRadius+0.04
        local x,y=cell.x+math.cos(angle)*r,cell.y+math.sin(angle)*r
        if not self.map:Contains(x,y,self.config.virusRadius) then x,y=cell.x,cell.y end
        local id = self._nextReleasedId
        self._nextReleasedId=id+1
        self.releasedViruses[#self.releasedViruses+1]={
            id=id,x=x,y=y,vx=math.cos(angle)*0.24,vy=math.sin(angle)*0.24,
            radius=self.config.virusRadius,variant=math.floor(self:_Random()*4)+1,phase=angle,
            sourceCellId=cell.id,sourceRegionId=cell.regionId,nodeProduced=nodeProduced,
            releaseBatchId=cell.releaseVisualSequence,state="RELEASED",age=0,
            lifetime=self.config.releasedLifetime,_oldX=x,_oldY=y,
        }
        -- 只记录真实实体经过地图回退后的出生位置；中心回退没有方向，不能借 angle 伪造。
        if #cell.releaseVisualDirections < 3 then
            local dx,dy=x-cell.x,y-cell.y
            local d=math.sqrt(dx*dx+dy*dy)
            if d > 0.000001 then
                cell.releaseVisualDirections[#cell.releaseVisualDirections+1]={
                    sourceId=id,x=x,y=y,normalX=dx/d,normalY=dy/d,
                    visualCellRotation=cell.rotation or 0,
                }
            end
        end
    end
    Ecology.Pulse(self,cell.x,cell.y,"activity",(self.config.ecology and self.config.ecology.releasePulse or 0)*count)
    self.stats.totalReleased=self.stats.totalReleased+count
    Abilities.NormalRelease(self,cell,count)
    Abilities.AfterRelease(self,cell)
    self:AddInflammation(cell.regionId,self.config.releaseInflammation)
    self:_Effect("release",cell.x,cell.y,cell.radius)
    self:Emit("release_batch",{cellId=cell.id,count=count})
end

function SwarmWorld:_AgeCells(dt)
    self:InvalidateCounts()
    local cfg=self.config
    for _,cell in ipairs(self.cells) do
        if cell.state == "LATENT" then
            cell.infectedAge=cell.infectedAge+dt
            cell.latencyTimer=cell.latencyTimer+dt
            if cell.latencyTimer >= cfg.latentSeconds then
                cell.state,cell.productiveTimer="PRODUCTIVE",0
                self:Emit("latency_complete",{cellId=cell.id,productiveCount=self:Counts().productive})
                self:_Release(cell,cfg.releaseBatches[1])
                cell.releaseCount=1
            end
        elseif cell.state == "PRODUCTIVE" then
            cell.infectedAge=cell.infectedAge+dt
            cell.productiveTimer=cell.productiveTimer+dt
            local interval=cfg.releaseInterval
            if cell.productiveTimer >= interval then
                cell.productiveTimer=cell.productiveTimer-interval
                if cell.releaseCount < #cfg.releaseBatches then
                    cell.releaseCount=cell.releaseCount+1
                    self:_Release(cell,cfg.releaseBatches[cell.releaseCount])
                else cell.state,cell.exhaustionTimer="EXHAUSTED",0 end
            end
        elseif cell.state == "EXHAUSTED" then
            cell.infectedAge=cell.infectedAge+dt
            cell.exhaustionTimer=cell.exhaustionTimer+dt
            cell.exhaustedReleaseTimer=cell.exhaustedReleaseTimer+dt
            if cell.exhaustionTimer >= cfg.exhaustedSeconds then self:KillCell(cell,"exhausted")
            elseif cell.exhaustedReleaseTimer >= cfg.exhaustedReleaseInterval then
                cell.exhaustedReleaseTimer=0
                self:_Release(cell,cfg.exhaustedReleaseCount)
            end
        end
    end
end

function SwarmWorld:_MoveReleased(dt)
    local cfg=self.config
    self:InvalidateCounts()
    -- Rebuild even for standalone calls: development fixtures may move cells.
    if not self._cellSpatialActive then self.cellGrid:Build(self.cells) end
    local drag=math.exp(-2*dt)
    for _,v in ipairs(self.releasedViruses) do
        if liveReleased(v) then
            v._oldX,v._oldY=v.x,v.y
            v.age=v.age+dt
            if v.age >= v.lifetime then
                v.state="LOST"; self.stats.totalLost=self.stats.totalLost+1
                Abilities.Record(self,"inactivation",1,v.id)
            else
                local recall,recallDistance=Abilities.RecallOwner(self,v)
                if recall then
                    local step=math.min(recallDistance,Config.CardAbilities.discrete_recall.speed*dt)
                    v.x,v.y=self.map:Move(v.x,v.y,v.x+(recall.x-v.x)/math.max(1e-6,recallDistance)*step,v.y+(recall.y-v.y)/math.max(1e-6,recallDistance)*step,v.radius)
                end
                local absorber,best=nil,math.huge
                for _,s in ipairs(self.swarms) do
                    local d=distance(v,s)
                    if d <= s.radius+cfg.absorptionExtra then v.everSwarmContact=true end
                    if d <= s.radius+cfg.absorptionExtra and d < best and self:_CanPassivelyAbsorbReleased(s,v)
                        and (not self.tutorial or self.tutorial:AllowPassiveCollection()) then
                        absorber,best=s,d
                    end
                end
                if absorber then
                    v.state="ATTRACTED"
                    local d=math.max(0.0001,best)
                    local move=math.min(d,cfg.absorptionSpeed*dt)
                    v.x,v.y=self.map:Move(v.x,v.y,v.x+(absorber.x-v.x)/d*move,
                        v.y+(absorber.y-v.y)/d*move,v.radius)
                    if distance(v,absorber) <= absorber.radius*0.75 then
                        self:_AbsorbReleased(absorber,v,recall==absorber and "recall" or nil)
                    end
                else
                    local near=self.cellGrid:AnyInRange(v.x,v.y,cfg.infectionReach,v.radius,"HEALTHY","EXPOSED")
                    local flowX,flowY=self.map:FlowAt(v.x,v.y,self.time)
                    v.vx,v.vy=v.vx*drag,v.vy*drag
                    local slow=near and 0.12 or 1
                    v.state=near and "INFECTING" or (v.age<1 and "RELEASED" or "DRIFTING")
                    local vx=(v.vx+flowX*cfg.releasedFlowInfluence+
                        math.cos(self.time*0.5+v.phase)*cfg.releasedDrift)*slow
                    local vy=(v.vy+flowY*cfg.releasedFlowInfluence+
                        math.sin(self.time*0.4+v.phase)*cfg.releasedDrift)*slow
                    v.x,v.y=self.map:Move(v.x,v.y,v.x+vx*dt,v.y+vy*dt,v.radius)
                end
            end
        end
    end
end

-- 视觉接触设计（不扩大上方业务的接受条件）：
--                 source S
--                   | normal (cell -> S，Y 向下)
--       cell C ---- P = C + normal * cell.radius
--  P 仅初投影，实际膜 alpha 由渲染修正；多个 S 各有独立 P，绝不平均成全胞 mask。
--  同中心：沿旧方向；无历史有效方向则不造视觉方向，业务贡献保持原式。
--  最多 3 个稳定 slot；先更新所有 incumbent，再用本步最强新来源填空/替换 gone 最旧。
--  脱离/隐藏/吸收/清除/LATENT 都停止续期，0.75s 淡出；最后 patch anchor 永久保留。
-- 逐移动步记录真实接触，再按0.5秒病程步结算；不把瞬间停留扩成半秒。
function SwarmWorld:_AccumulateExposure(dt, deferVisualCommit)
    local cfg=self.config
    local inputs={}
    local nearby={}
    for _,cell in ipairs(self.cells) do
        cell.covered=false
        local accepted={}
        inputs[cell.id]=accepted
        if cell.state == "HEALTHY" or cell.state == "EXPOSED" then
            local groupPower,releasedPower=0,0
            for _,s in ipairs(self.swarms) do
                local range=cell.radius+s.radius+cfg.infectionReach
                local d=distance(cell,s)
                if s.mass > 0 and not s.isHidden and (not s.relayCellId or s.relayCellId==cell.id) and d <= range
                    and self:_DirectPathClear(s.x,s.y,cell.x,cell.y,0) then
                    local proximity=math.max(0.22,1-d/range)
                    local density=self:GroupInfectionMultiplier(s)
                    local power=s.relayCellId and Abilities.RelayPower(self,s) or proximity*density
                    groupPower=groupPower+power
                    Abilities.BreakCamouflage(s)
                    s.exposedCells[cell.id]=true
                    cell.everPlayerContact=true
                    self.playerTouchedCells[cell.id]=true -- 阶段永久事实，感染来源仍使用原字段。
                    CellContacts.Collect(cell,s,"PLAYER_SWARM",power,accepted)
                end
            end
            for _,v in ipairs(self:NearbyReleased(cell.x,cell.y,cell.radius+cfg.infectionReach,nearby)) do
                if liveReleased(v) then
                    local range=cell.radius+cfg.infectionReach+v.radius
                    local d=distance(cell,v)
                    if d <= range and self:_DirectPathClear(v.x,v.y,cell.x,cell.y,0) then
                        local power=cfg.releasedInfectionPower*math.max(0.3,1-d/range)
                        releasedPower=releasedPower+power
                        CellContacts.Collect(cell,v,"RELEASED_VIRUS",
                            power,accepted)
                    end
                end
            end
            -- 群规模持续生效；只有游离病毒自己的功率封顶，不挤掉群的真实贡献。
            local countedReleasedPower=math.min(3,releasedPower)
            local total=groupPower+countedReleasedPower
            if total>0 then
                cell.covered=true
                local charge=dt*total/cfg.infectionSeconds*Ecology.InfectionMultiplier(self,cell)
                cell._charge=cell._charge+charge
                cell._groupCharge=cell._groupCharge+charge*groupPower/total
                cell._releasedCharge=cell._releasedCharge+charge*countedReleasedPower/total
            else cell._charge=cell._charge-dt*cfg.exposureDecay end
        end
        CellDiagnostics.Accepted(self,cell,accepted)
    end
    if not deferVisualCommit then CellContacts.CommitWorld(self,inputs) end
    return inputs
end

function SwarmWorld:_InfectCells()
    self:InvalidateCounts()
    for _,cell in ipairs(self.cells) do
        if cell.state == "HEALTHY" or cell.state == "EXPOSED" then
            local before=cell.exposure
            cell.exposure=math.max(0,math.min(1,cell.exposure+cell._charge))
            cell.groupContribution=cell.groupContribution+cell._groupCharge
            cell.releasedContribution=cell.releasedContribution+cell._releasedCharge
            cell.state=cell.exposure>0 and "EXPOSED" or "HEALTHY"
            -- 本轮接触从零开始时取新序号；阶段任务只认阶段开始后才起步的感染。
            if before<=0 and cell.exposure>0 then self:_StampContact(cell) end
            if cell.exposure >= 1-1e-9 then
                local source=not cell.everPlayerContact and cell.releasedContribution>0 and "released" or "player"
                self:_Infect(cell,source)
            elseif cell.exposure==0 then
                cell.contactSerial=nil
                cell.groupContribution,cell.releasedContribution=0,0
                cell.everPlayerContact=false
                for _,s in ipairs(self.swarms) do s.exposedCells[cell.id]=nil end
            end
        end
        cell._charge,cell._groupCharge,cell._releasedCharge=0,0,0
    end
end

function SwarmWorld:_Inflammation(dt)
    local cfg=self.config
    for _,r in ipairs(self.map.regions) do
        r.inflammation=r.inflammation*math.exp(-cfg.inflammationDecayRate*dt)
    end
    for _,cell in ipairs(self.cells) do
        local inflammation,damage=0,0
        if cell.state=="LATENT" then inflammation=cfg.latentInflammationRate
        elseif cell.state=="PRODUCTIVE" then inflammation,damage=cfg.productiveInflammationRate,cfg.productiveDamageRate
        elseif cell.state=="EXHAUSTED" then inflammation,damage=cfg.exhaustedInflammationRate,cfg.exhaustedDamageRate
        elseif cell.state=="DEAD" then inflammation,damage=cfg.deadInflammationRate,cfg.deadDamageRate end
        self:AddInflammation(cell.regionId,inflammation*dt,damage*dt)
    end
    self.globalInflammation,self.globalTissueDamage=0,0
    for _,r in ipairs(self.map.regions) do
        self.globalInflammation=self.globalInflammation+r.inflammation
        self.globalTissueDamage=self.globalTissueDamage+r.damage
    end
end

function SwarmWorld:Counts()
    local c={virus=0,controlled=0,mainMass=0,splitMass=0,released=0,infected=0,
        latent=0,productive=0,exhausted=0,healthy=0,exposed=0,dead=0,immune=#self.immunes,groups=self:LiveSwarmCount()}
    for _,s in ipairs(self.swarms) do
        c.controlled=c.controlled+s.mass
        if s.isMainSwarm then c.mainMass=s.mass else c.splitMass=c.splitMass+s.mass end
    end
    for _,v in ipairs(self.releasedViruses) do if liveReleased(v) then c.released=c.released+1 end end
    for _,cell in ipairs(self.cells) do
        if cell.state=="HEALTHY" then c.healthy=c.healthy+1
        elseif cell.state=="EXPOSED" then c.exposed=c.exposed+1
        elseif cell.state=="LATENT" then c.latent=c.latent+1
        elseif cell.state=="PRODUCTIVE" then c.productive=c.productive+1
        elseif cell.state=="EXHAUSTED" then c.exhausted=c.exhausted+1
        elseif cell.state=="DEAD" then c.dead=c.dead+1 end
    end
    c.virus=c.controlled+c.released
    c.infected=c.latent+c.productive+c.exhausted
    self._countsSnapshot=c
    return c
end

function SwarmWorld:RegionAt(x,y) return self.map:RegionAt(x,y) end
function SwarmWorld:GetFormationRadius() return self.player.radius end

function SwarmWorld:AcquireImmuneAlert()
    self.immuneAlertLevel = math.min(Config.ImmuneAlert.maxLevel, self.immuneAlertLevel+1)
    local level = self.debugImmuneAlertLevel or self.immuneAlertLevel
    self.pendingAlertActivation = { level = level, remaining = Config.ImmuneAlert.alertActivationDelay }
    self:Emit("immune_alert_changed", { level = self.immuneAlertLevel })
end

function SwarmWorld:SetDebugImmuneAlertLevel(level)
    if level ~= nil and (type(level) ~= "number" or level ~= math.floor(level) or level < 0 or level > 6) then return false end
    self.debugImmuneAlertLevel = level
    self.pendingAlertActivation = { level = level or self.immuneAlertLevel, remaining = Config.ImmuneAlert.alertActivationDelay }
    return true
end

function SwarmWorld:Update(dt)
    if dt<=0 or dt~=dt or dt==math.huge then return end
    self:InvalidateCounts()
    -- BeginStep在真实移动/感染前取样；仅显式Debug开启时工作。
    CellDiagnostics.BeginStep(self,dt)
    self.time=self.time+dt
    -- Cells keep their positions during a step. Share one current index with
    -- abilities, AI, released particles and immune queries; never reuse it outside.
    self.cellGrid:Build(self.cells)
    self._cellSpatialActive=true
    Ecology.Update(self,dt)
    Abilities.Update(self,dt)
    self.splitCooldown=math.max(0,self.splitCooldown-dt)
    self:_MoveGroups(dt)
    self:_UpdateParticles()
    self:_MoveReleased(dt)
    self.releasedGrid:Build(self.releasedViruses)
    self._spatialActive=true
    if not self.tutorial or not self.tutorial:DeferImmune() then ImmuneSystem.Update(self,dt) end
    self:_RefreshGroups()
    local acceptedContacts=self:_AccumulateExposure(dt,true)
    self.diseaseAccum=self.diseaseAccum+dt
    if self.diseaseAccum+1e-9>=self.config.diseaseStep then
        self.diseaseAccum=math.max(0,self.diseaseAccum-self.config.diseaseStep)
        self:_AgeCells(self.config.diseaseStep)
        self:_InfectCells()
        self:_Inflammation(self.config.diseaseStep)
        if not self.tutorial or not self.tutorial:DeferImmune() then ImmuneSystem.Recruit(self,self.config.diseaseStep) end
    end
    -- 原感染结算/状态迁移完成后统一提交，绘制只读这一帧的新状态与稳定方向。
    CellContacts.CommitWorld(self,acceptedContacts)
    SplitVirusAI.CleanTargets(self)
    self:_AutoSplitGroups()
    CellDiagnostics.EndStep(self)
    self._spatialActive=false -- callers outside the step never read a stale index.
    self._cellSpatialActive=false
    local write=1
    local releasedCount=#self.releasedViruses
    for read=1,releasedCount do
        local virus=self.releasedViruses[read]
        if liveReleased(virus) then self.releasedViruses[write]=virus;write=write+1 end
    end
    for i=releasedCount,write,-1 do self.releasedViruses[i]=nil end
    write=1
    local effectCount=#self.effects
    for read=1,effectCount do
        local effect=self.effects[read]
        effect.age=effect.age+dt
        if effect.age<effect.duration then self.effects[write]=effect;write=write+1 end
    end
    for i=effectCount,write,-1 do self.effects[i]=nil end
    local counts=self:Counts()
    self.stats.peakVirus=math.max(self.stats.peakVirus,counts.virus)
    self._logClock=self._logClock+dt
    if self._logClock>=30 then
        self._logClock=0
        print(string.format("[SwarmWorld] %.0fs 群=%d 活节点=%d 游离=%d 炎症=%.1f 损伤=%.1f",
            self.time,counts.controlled,counts.infected,counts.released,self.globalInflammation,self.globalTissueDamage))
    end
end

return SwarmWorld
