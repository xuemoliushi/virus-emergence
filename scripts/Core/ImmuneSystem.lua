-- ImmuneSystem.lua -- 简单、可预读的免疫追踪；纯 Lua 5.4，不依赖引擎。
-- 参考 scaffold-2d.lua 的初始化/固定步更新分离，碰撞事件示例的一次性结算原则。
-- Update 只负责移动/攻击；病程步另外调用 Recruit，勿在两处重复招募。
--
-- 接触设计（所有坐标/半径为米）：
--       detection + target.r           contact = immune.r + target.r
--     .--------------------.              ( I )|( target )
--     | I -> LOCK -> WARN  |                    ^ 相切也算接触
--     '--------------------'              接触 -> 短动作 -> 再核对距离 -> 少量损失
--   巨噬预警时接近但不攻击；T 细胞保留原组织预警与识别。
--   首次发现圈与追踪失忆圈分离；后者 = detection + forgetExtra + target.r。
--   已锁定目标仍须直线可见；隐藏、遮挡或超过失忆圈立即停止实时坐标追踪。
--   节点事件的 dangerRadius 围绕节点中心，供阶段系统判定受击后分群存活；不是伤害范围。
--   群用真实紧凑群半径，不用感染影响圈；远处、隐藏、失效目标绝不扣量。
--   蓄力中离开接触圈则取消攻击；必须再次接触并重新蓄满。
--   地图边缘/枝间暗区：只通过 map:Move 移动，短路标也必须 Contains。
--   高 dt 每次最多推进一个状态，丢弃跨状态余量，不能把预警/蓄力压成瞬杀。
--   CLEARED/LOST/ABSORBED 不可重杀；DEAD 残骸只标记处理一次，不再次 KillCell。

---@alias ImmuneTargetType 'swarm'|'cell'|'virus'
---@alias ImmuneState 'patrol'|'search'|'locked'|'warning'|'chase'|'attack'|'cooldown'|'investigate'|'processing'

---@class ImmuneCellRecord
---@field id integer
---@field kind 'macrophage'|'tcell'
---@field x number
---@field y number
---@field radius number
---@field variant integer
---@field phase number
---@field state ImmuneState
---@field targetType ImmuneTargetType?
---@field targetId integer?
---@field targetX number?
---@field targetY number?
---@field detectionRange number
---@field dangerRadius number
---@field warningTime number 总预警时长。
---@field warningTimer number 剩余预警秒数。
---@field attackWindup number 总蓄力时长。
---@field attackTimer number 剩余蓄力秒数。
---@field cooldown number 剩余冷却秒数。
---@field stateTimer number 当前状态经过秒数。
---@field processingLoad number?
---@field recognitionTimer number?
---@field recognized boolean?
---@field signalInvestigation boolean?
---@field respondingToAlarm boolean?
---@field alarmVisibleUntil number?
---@field _alarmReadyAt number?
---@field _encounterTimer number?
---@field _screenCellId integer?
---@field screenTimer number?
---@field screenRequiredSeconds number?
---@field _cellChecks table<integer, ImmuneCellCheck>?
---@field recognitionRequiredSeconds number?
---@field hotspotCleanup boolean?
---@field _cleanupCancelled boolean?
---@field _hotspotReadyAt number?
---@field _activityObservationClock number?
---@field _activityAlarmTimer number?
---@field _activityLastLevel number?
---@field regionId integer
---@field patrolHome ImmunePoint? 固定驻巡入口，追击结束后沿真实路径返回。
---@field dutyRole 'pursuit'|'cleanup'|'node'?
---@field returningHome boolean?
---@field _homeRoute ImmunePoint[]?
---@field _homeRouteClock number?
---@field _oldX number
---@field _oldY number
---@field _patrolX number
---@field _patrolY number
---@field _patrolTimer number
---@field _stuckTimer number
---@field _retargetTimer number? 重新检查职责目标的间隔。
---@field _route ImmunePoint[]? 当前真实通道路径。
---@field _routeTarget ImmunePoint? 路径终点的最近快照。
---@field _searchUntil number
---@field _searchX number
---@field _searchY number
---@field _lastSeen ImmuneObservation?

---@class ImmunePoint
---@field x number
---@field y number
---@field regionId integer?

---@class ImmuneCellCheck: ImmunePoint
---@field checkedAt number
---@field infected boolean

---@class ImmuneObservation: ImmunePoint
---@field seenAt number

---@class ImmuneBranchAssignment: ImmunePoint
---@field startsAt number
---@field untilTime number

-- 类型源由 SwarmWorld/RespiratoryMap 定义；这里只给新增的世界字段补标注。
-- 无 require SwarmWorld，故不形成循环依赖。
---@class RespiratoryMap
---@field isFlatMap boolean? 当前平面地图适配器的路径检测标记。

---@class SwarmWorld
---@field _nextImmuneId integer?
---@field _immuneRecruitClock number?
---@field immuneStartingCount number?
---@field immuneWorkOrders table<number,{kind:string,x:number,y:number}>
---@field _immuneClearedDebris table<number, boolean>?
---@field immuneReservations table<string, table<number, number>>
---@field patrolAssignments table<number, integer>
---@field channelPatrolAssignments table<number, ImmuneBranchAssignment>
---@field immuneAlarms table[]
---@field immuneAlarmAssignments table<integer, table>
---@field immuneAlarmCooldowns table<string, number>
---@field _nextImmuneAlarmId integer
---@field immuneHotspots table[]
---@field immuneCleanupAssignments table<integer, table>
---@field immuneHotspotCooldowns table<string, number>
---@field _nextImmuneHotspotId integer

---@class ImmuneTargetView
---@field targetType ImmuneTargetType
---@field id integer
---@field x number
---@field y number
---@field radius number
---@field signal number
---@field priority number

local ImmuneSystem = {}
local Navigation = require("Core.ImmuneNavigation")
local PatrolNavigation = require("Core.PatrolNavigation")
local Director = require("Core.ImmuneDirector")
local Config = require("Core.Config")
local Ecology = require("Core.LocalEcology")
local Abilities = require("Core.AbilityRuntime")
local TAU = math.pi * 2
local EPSILON = 1e-9

---@param dt number
---@return boolean
local function validStep(dt)
    return dt > 0 and dt == dt and dt < math.huge
end

---@param value number
---@param lo number
---@param hi number
---@return number
local function clamp(value, lo, hi)
    return math.max(lo, math.min(hi, value))
end

---@param x number
---@param y number
---@param tx number
---@param ty number
---@return number
local function distance(x, y, tx, ty)
    return math.sqrt((tx - x)^2 + (ty - y)^2)
end

---@param w SwarmWorld
---@return number
local function random(w)
    return clamp(w:_Random(), 0, 1)
end

---@param cell RespiratoryCell
---@return number
local function nodeSignal(cell)
    local activity = cell.state == "PRODUCTIVE" and 1
        or cell.state == "EXHAUSTED" and 1.2
        or cell.state == "LATENT" and 0.4 or 0
    return activity * math.max(0, cell.immuneSignalValue or 1)
end

---@param virus ReleasedVirusRecord
---@return boolean
local function liveVirus(virus)
    return virus.state == "RELEASED" or virus.state == "DRIFTING"
        or virus.state == "ATTRACTED" or virus.state == "INFECTING"
end

local function priority(kind,targetType,state)
    if targetType=="cell" then
        if state=="DEAD" then return kind=="macrophage" and 50 or 0 end
        if kind=="tcell" then return state=="PRODUCTIVE" and 100 or state=="EXHAUSTED" and 90 or 70 end
        return 0
    end
    if targetType=="virus" then return kind=="macrophage" and 60 or 0 end
    return kind=="macrophage" and 40 or 0
end

local function isDecoy(w,virus)
    return virus~=nil and (virus.decoyUntil or 0)>w.time
end

-- 同一套优先级供新发现、已有目标和中途换靶使用，不偏爱当前受控群。
local function macrophagePriority(w,targetType,virus,immune,swarm)
    local behavior=w.config.immuneBehavior
    if behavior and targetType=="swarm" then
        if immune and immune.dutyRole=="cleanup" and swarm
            and distance(immune.x,immune.y,swarm.x,swarm.y)>immune.radius+swarm.radius+1 then
            return behavior.swarmPriority*.5
        end
        return behavior.swarmPriority
    end
    if behavior and virus and (virus.decoyUntil or 0)>w.time then return behavior.decoyPriority end
    return priority("macrophage",targetType)
end

local function swarmVisibility(immune,swarm)
    local visibility=swarm.visibility or 1
    if swarm.camouflaged and distance(immune.x,immune.y,swarm.x,swarm.y)-swarm.radius>Config.CardAbilities.debris_camouflage.nearRange then
        visibility=visibility*Config.CardAbilities.debris_camouflage.visibility
    end
    return visibility
end

local function reaction(w,immune,targetType)
    local b=w.config.immuneBehavior
    if not b then
        return w.config.immuneWarningSeconds,w.config.immuneAttackWindup,w.config.immuneAttackInterval
    end
    if immune.kind=="tcell" then
        return Director.BehaviorValue(w,"tcellWarningSeconds") or w.config.immuneWarningSeconds,
            w.config.immuneAttackWindup,Director.BehaviorValue(w,"tcellAttackInterval") or w.config.immuneAttackInterval
    end
    if targetType=="swarm" then
        local warning=b.growth and Director.BehaviorValue(w,"swarmWarningSeconds")
            or b.swarmWarningSeconds-math.min(5,Director.Level(w))*b.swarmWarningReductionPerLevel
        return warning,b.swarmWindup,Director.BehaviorValue(w,"swarmAttackInterval")
    elseif targetType=="virus" then
        return b.particleWarningSeconds,Director.BehaviorValue(w,"particleWindup"),Director.BehaviorValue(w,"particleAttackInterval")
    end
    return b.debrisWarningSeconds,b.debrisWindup,b.debrisAttackInterval
end

---@param w SwarmWorld
---@param id integer
---@return SwarmRecord?
local function swarmById(w, id)
    for _, swarm in ipairs(w.swarms) do
        if swarm.id == id then return swarm end
    end
    return nil
end

---@param w SwarmWorld
---@param id integer
---@return RespiratoryCell?
local function cellById(w, id)
    for _, cell in ipairs(w.cells) do
        if cell.id == id then return cell end
    end
    return nil
end

---@param w SwarmWorld
---@param id integer
---@return ReleasedVirusRecord?
local function virusById(w, id)
    for _, virus in ipairs(w.releasedViruses) do
        if virus.id == id then return virus end
    end
    return nil
end

---@param w SwarmWorld
---@param immune ImmuneCellRecord
---@return ImmuneTargetView?
local function resolveTarget(w, immune)
    local id, targetType = immune.targetId, immune.targetType
    if not id or not targetType then return nil end
    if immune.kind=="tcell" and targetType~="cell" then return nil end
    if targetType == "swarm" then
        local swarm = swarmById(w, id)
        if swarm and swarm.mass > 0 and not swarm.isHidden and (swarm.visibility or 1) > 0 then
            local visibility=swarmVisibility(immune,swarm)
            return { targetType = "swarm", id = id, x = swarm.x, y = swarm.y,
                radius = swarm.radius, priority = macrophagePriority(w,"swarm",nil,immune,swarm)*clamp(visibility,0,1), signal = visibility }
        end
    elseif targetType == "cell" then
        local cell = cellById(w, id)
        local debris = w._immuneClearedDebris or {}
        if cell and ((immune.kind=="tcell" and nodeSignal(cell) > 0)
            or (immune.kind == "macrophage" and cell.state == "DEAD" and not debris[id])) then
            return { targetType = "cell", id = id, x = cell.x, y = cell.y,
                radius = cell.radius, priority = priority(immune.kind,"cell",cell.state), signal = nodeSignal(cell) }
        end
    else
        local virus = virusById(w, id)
        if virus and liveVirus(virus) then
            return { targetType = "virus", id = id, x = virus.x, y = virus.y,
                radius = virus.radius, priority = macrophagePriority(w,"virus",virus), signal = 1,
                decoy = isDecoy(w,virus) }
        end
    end
    return nil
end

---@param immune ImmuneCellRecord
---@param state ImmuneState
local function setState(immune, state)
    immune.state, immune.stateTimer = state, 0
end

local function memoryEnabled(w,immune)
    return immune.kind=="tcell" and w.config.immuneBehavior
        and Director.Level(w)>=Config.ImmuneAlert.cellMemoryLevel
end

local function checkedCell(w,immune,id)
    local record=immune._cellChecks and immune._cellChecks[id]
    if record and w.time-record.checkedAt<w.config.immuneBehavior.checkMemorySeconds then return record end
    return nil
end

local function rememberCheck(w,immune,cell,infected)
    if not memoryEnabled(w,immune) then return end
    local checks=immune._cellChecks or {};immune._cellChecks=checks
    checks[cell.id]={x=cell.x,y=cell.y,checkedAt=w.time,infected=infected}
    local count,oldestId,oldestTime=0,nil,math.huge
    for id,record in pairs(checks) do
        count=count+1
        if record.checkedAt<oldestTime or record.checkedAt==oldestTime and (not oldestId or id<oldestId) then
            oldestId,oldestTime=id,record.checkedAt
        end
    end
    if count>w.config.immuneBehavior.checkMemoryLimit then checks[oldestId]=nil end
end

---@param w SwarmWorld
---@param immune ImmuneCellRecord
---@param escaped boolean
local function releaseTarget(w, immune, escaped)
    local known=immune.targetType=="cell" and memoryEnabled(w,immune) and checkedCell(w,immune,immune.targetId)
    local search = escaped and (immune.targetType=="swarm" or known and known.infected) and Director.Search(w,immune)
    Director.Release(w,immune)
    if escaped and immune.targetType == "swarm" and immune.targetId then
        local swarm = swarmById(w, immune.targetId)
        if swarm and swarm.mass > 0 then
            w:Emit("immune_escape", { swarmId = swarm.id })
            print(string.format("[ImmuneSystem] 逃脱 immune=%d swarm=%d", immune.id, swarm.id))
        end
    end
    immune.targetType, immune.targetId = nil, nil
    immune.targetX, immune.targetY = nil, nil
    immune.warningTimer, immune.attackTimer = 0, 0
    immune.recognitionTimer,immune.recognized,immune.signalInvestigation = 0,false,false
    immune.recognitionRequiredSeconds=nil
    immune._encounterTimer,immune._screenCellId,immune.screenTimer=0,nil,0
    immune.screenRequiredSeconds=nil
    immune._patrolTimer, immune._stuckTimer = 0, 0
    immune._route,immune._routeTarget,immune._retargetTimer = nil,nil,0
    -- 自己清除/外部移除目标都不能免除已经开始的攻击冷却。
    if not escaped and immune.cooldown > 0 then setState(immune, "cooldown")
    else immune.cooldown = 0; setState(immune, search and "search" or "patrol") end
end

-- 防止隔着枝间暗区看到/攻击对象；这里只验直线可通，不做全图寻路。
---@param w SwarmWorld
---@param x number
---@param y number
---@param tx number
---@param ty number
---@param radius number
---@return boolean
local function clearLine(w, x, y, tx, ty, radius)
    if w.map.isFlatMap then return w.map:_ConvexPathClear(x,y,tx,ty,radius) end
    local steps = math.max(1, math.ceil(distance(x, y, tx, ty) / 0.2))
    for index = 1, steps do
        local t = index / steps
        if not w.map:Contains(x + (tx - x)*t, y + (ty - y)*t, radius) then return false end
    end
    return true
end

---@param w SwarmWorld
---@param immune ImmuneCellRecord
---@param target ImmuneTargetView
---@return boolean
local function inContact(w, immune, target)
    local contact = immune.radius + math.max(0, target.radius)
    return distance(immune.x, immune.y, target.x, target.y) <= contact + EPSILON
        and clearLine(w, immune.x, immune.y, target.x, target.y, 0)
end

---@param w SwarmWorld
---@param immune ImmuneCellRecord
---@return ImmuneTargetView?
local function detect(w, immune, patrolRange)
    ---@type ImmuneTargetView?
    local best = nil
    local bestScore = -math.huge
    local densityMemo={}
    local duty=w.immuneCleanupAssignments[immune.id]
    local function visibleVirus(virus)
        return distance(immune.x,immune.y,virus.x,virus.y)<=immune.detectionRange+virus.radius
            and clearLine(w,immune.x,immune.y,virus.x,virus.y,0)
    end
    ---@param target ImmuneTargetView
    ---@param range number
    local function consider(target, range)
        if target.priority<=0 or not Director.Available(w,immune,target) then return end
        if duty and (target.targetType=="swarm" or (target.x-duty.x)^2+(target.y-duty.y)^2>duty.radius^2) then return end
        local gap = math.max(0, distance(immune.x, immune.y, target.x, target.y) - target.radius)
        if gap > (patrolRange or range) or not clearLine(w, immune.x, immune.y, target.x, target.y, 0) then return end
        if patrolRange and w.map:RegionAt(target.x,target.y)~=immune.regionId then return end
        -- 职责优先：巨噬应对可见群，真实诱饵可分散注意；T 优先节点。
        local score = target.priority + clamp(target.signal, 0, 4)/(1 + gap)
            - Director.RegionPenalty(w,immune,target)
        local behavior=w.config.immuneBehavior
        local selective=immune.kind=="macrophage" and behavior
            and (immune.processingLoad or 0)>=behavior.loadCapacity*behavior.selectiveLoadFraction
        if immune.kind=="macrophage" and behavior then
            local cost=target.targetType=="cell" and behavior.debrisLoad
                or target.targetType=="virus" and 1 or math.min(w.config.immuneKillsPerAttack,swarmById(w,target.id).mass)
            if behavior.loadCapacity-(immune.processingLoad or 0)+EPSILON<cost then return end
        end
        if selective then score=score-gap*behavior.loadedDistanceWeight end
        if target.targetType=="virus" then
            local density=Director.VisibleDensity(w,immune,target,visibleVirus,densityMemo)
            score=score+density*(selective and -behavior.loadedCrowdWeight or 1)
        elseif target.targetType=="cell" and Director.Level(w)>=3 then
            local cell=cellById(w,target.id)
            if cell and cell.state=="PRODUCTIVE" then score=score+cell.releaseCount*Config.ImmuneAlert.activeSignalMultiplier end
        end
        if score > bestScore then best, bestScore = target, score end
    end
    local cellRange=patrolRange or immune.detectionRange*math.max(1,Config.ImmuneAlert.activeSignalMultiplier)
    for _, cell in ipairs(w:NearbyCells(immune.x,immune.y,cellRange)) do
        local signal = nodeSignal(cell)
        local debris = w._immuneClearedDebris or {}
        if signal > 0 and immune.kind=="tcell" then
            local range=immune.detectionRange
            if Director.Level(w)>=3 and cell.state=="PRODUCTIVE" and cell.releaseCount>0 then range=range*Config.ImmuneAlert.activeSignalMultiplier end
            consider({ targetType = "cell", id = cell.id, x = cell.x, y = cell.y,
                radius = cell.radius, signal = signal, priority = priority(immune.kind,"cell",cell.state) }, range)
        elseif immune.kind == "macrophage" and cell.state == "DEAD" and not debris[cell.id] then
            consider({ targetType = "cell", id = cell.id, x = cell.x, y = cell.y,
                radius = cell.radius, signal = 0.5, priority = 50 }, immune.detectionRange)
        end
    end
    for _, swarm in ipairs(w.swarms) do
        local visibility = swarmVisibility(immune,swarm)
        if immune.kind=="macrophage" and swarm.mass > 0 and not swarm.isHidden and visibility > 0 then
            consider({ targetType = "swarm", id = swarm.id, x = swarm.x, y = swarm.y,
                radius = swarm.radius, signal = visibility,
                priority = macrophagePriority(w,"swarm",nil,immune,swarm)*clamp(visibility,0,1) },
                immune.detectionRange * clamp(visibility, 0.25, 1.5))
        end
    end
    for _, virus in ipairs(w:NearbyReleased(immune.x,immune.y,patrolRange or immune.detectionRange)) do
        if immune.kind=="macrophage" and liveVirus(virus) then
            consider({ targetType = "virus", id = virus.id, x = virus.x, y = virus.y,
                radius = virus.radius, signal = 1+math.max(0,(virus.decoyUntil or 0)-w.time)/Config.CardAbilities.shed_decoy.signalSeconds,
                priority = macrophagePriority(w,"virus",virus), decoy = isDecoy(w,virus) }, immune.detectionRange)
        end
    end
    return best
end

---@param w SwarmWorld
---@param immune ImmuneCellRecord
---@param target ImmuneTargetView
---@param continuedClear boolean? 成功吞噬后直接交接游离目标，仍保留冷却。
local function lock(w, immune, target, continuedClear)
    if not Director.Reserve(w,immune,target) then return false end
    Director.Remember(w,immune,target)
    immune.targetType, immune.targetId = target.targetType, target.id
    immune.targetX, immune.targetY = target.x, target.y
    immune.recognitionTimer,immune.recognized,immune.signalInvestigation = 0,false,false
    immune.recognitionRequiredSeconds=nil
    immune._screenCellId,immune.screenTimer,immune._encounterTimer=nil,0,0
    immune.screenRequiredSeconds=nil
    immune.warningTime,immune.attackWindup=reaction(w,immune,target.targetType)
    if continuedClear then immune.warningTime=0 end
    immune.warningTimer = immune.warningTime
    immune.attackTimer, immune.cooldown = 0, 0
    immune._route,immune._routeTarget,immune._retargetTimer = nil,nil,.25
    immune._homeRoute,immune._homeRouteClock=nil,0
    setState(immune, "locked")
    w:Emit("immune_lock", { immuneId = immune.id, targetType = target.targetType,
        targetId = target.id, x = immune.x, y = immune.y, warningSeconds = immune.warningTime,
        dangerRadius=immune.dangerRadius })
    print(string.format("[ImmuneSystem] 锁定 %s#%d -> %s#%d 预警=%.1f秒",
        immune.kind, immune.id, target.targetType, target.id, immune.warningTime))
    return true
end

---@param w SwarmWorld
---@param immune ImmuneCellRecord
local function choosePatrol(w, immune)
    -- 只向本区域/可直达近邻的感染信号缓慢靠近，不从另一枝全图透视追节点。
    ---@type ImmuneTargetView?
    local hotspot = detect(w,immune)
    if hotspot then
        local d = distance(immune.x, immune.y, hotspot.x, hotspot.y)
        local ratio = math.min(1, 2.2/math.max(0.01, d))
        local tx = immune.x + (hotspot.x - immune.x)*ratio
        local ty = immune.y + (hotspot.y - immune.y)*ratio
        if clearLine(w, immune.x, immune.y, tx, ty, immune.radius) then
            immune._patrolX, immune._patrolY, immune._patrolTimer = tx, ty, 4
            return
        end
    end
    local trace=Ecology.Investigate(w,immune)
    if trace and not Director.InPatrolArea(w,immune,trace.x,trace.y) then trace=nil end
    immune.signalInvestigation=trace~=nil
    if trace then
        immune._patrolX,immune._patrolY,immune._patrolTimer=trace.x,trace.y,2
        w:Emit("immune_investigate_trace",{immuneId=immune.id,x=trace.x,y=trace.y})
        return
    end
    if memoryEnabled(w,immune) then
        local best,bestDistance=nil,math.huge
        for _,cell in ipairs(w:NearbyCells(immune.x,immune.y,immune.detectionRange)) do
            local gap=distance(immune.x,immune.y,cell.x,cell.y)-cell.radius
            if (cell.state=="HEALTHY" or cell.state=="EXPOSED") and not checkedCell(w,immune,cell.id)
                and gap<=immune.detectionRange and gap<bestDistance
                and Director.InPatrolArea(w,immune,cell.x,cell.y)
                and Director.ScreenAvailable(w,immune,cell.id)
                and clearLine(w,immune.x,immune.y,cell.x,cell.y,0) then best,bestDistance=cell,gap end
        end
        if best then
            immune._screenCellId,immune.screenTimer=best.id,0
            immune.screenRequiredSeconds=Director.BehaviorValue(w,"recognitionSeconds")
            immune._patrolTimer=0
            w:Emit("immune_screen_start",{immuneId=immune.id,cellId=best.id})
            return
        end
    end
    local attempts=Director.Level(w)>=1 and 20 or 12
    for _ = 1, attempts do
        local radius=Director.Level(w)>=1 and Config.ImmuneAlert.patrolAlertRadius or Config.ImmuneAlert.patrolBaseRadius
        local angle, step = random(w)*TAU, 0.6 + random(w)*(radius-.6)
        local tx, ty = immune.x + math.cos(angle)*step, immune.y + math.sin(angle)*step
        if Director.InPatrolArea(w,immune,tx,ty) and clearLine(w, immune.x, immune.y, tx, ty, immune.radius) then
            immune._patrolX, immune._patrolY, immune._patrolTimer = tx, ty, 4
            return
        end
    end
    immune._patrolX, immune._patrolY, immune._patrolTimer = immune.x, immune.y, 1
end

---@param w SwarmWorld
---@param immune ImmuneCellRecord
---@param tx number
---@param ty number
---@param speed number
---@param dt number
local function move(w, immune, tx, ty, speed, dt)
    local d = distance(immune.x, immune.y, tx, ty)
    local behavior=w.config.immuneBehavior
    if immune.kind=="macrophage" and behavior then
        speed=speed*math.max(behavior.loadedSpeedMin,1-(immune.processingLoad or 0)/behavior.loadCapacity*(1-behavior.loadedSpeedMin))
    end
    local step = math.min(d, math.max(0, speed)*dt)
    local ratio = d > 0 and step/d or 0
    local nx, ny = w.map:Move(immune.x, immune.y,
        immune.x + (tx - immune.x)*ratio, immune.y + (ty - immune.y)*ratio, immune.radius)
    -- 若外部地图返回非法落点，保持当前位置，不修正为穿枝瞬移。
    if w.map:Contains(nx, ny, immune.radius) then immune.x, immune.y = nx, ny end
    local moved = distance(immune._oldX, immune._oldY, immune.x, immune.y)
    if step > 0.0001 and moved < step*0.1 then immune._stuckTimer = immune._stuckTimer + dt
    else immune._stuckTimer = 0 end
    immune.regionId = w.map:RegionAt(immune.x, immune.y)
end

-- 预警、追击和巨噬短接触动作共用真实移动与通道检查。
-- 蓄力时只允许补上本固定步内的位移；跳出接触仍会取消，不保留远程伤害。
local function approach(w,immune,target,dt)
    local b=w.config.immuneBehavior
    local speed=w.config.immuneChaseSpeed or 1.3
    if immune.kind=="macrophage" and b then
        local swarmSpeed=b.growth and Director.BehaviorValue(w,"swarmChaseSpeed")
            or b.swarmChaseSpeed+math.min(5,Director.Level(w))*b.swarmChaseSpeedPerLevel
        speed=target.targetType=="swarm" and swarmSpeed
            or b.particleChaseSpeed
    end
    if immune.state=="warning" then speed=speed*(w.config.immuneWarningSpeedFactor or .25) end
    local destination=Director.AttackPoint(w,immune,target)
    if not destination then return false end
    local start={x=immune.x,y=immune.y}
    if Navigation.Clear(w.map,start,destination,immune.radius) then
        immune._route=nil
        move(w,immune,destination.x,destination.y,speed,dt)
    else
        local previous=immune._routeTarget
        if not immune._route or not previous or distance(previous.x,previous.y,destination.x,destination.y)>.3 then
            immune._route=Navigation.Route(w.map,start,destination,immune.radius)
            immune._routeTarget=destination
        end
        local route=immune._route
        if not route then return false end
        while #route>1 and distance(immune.x,immune.y,route[1].x,route[1].y)<.10 do table.remove(route,1) end
        move(w,immune,route[1].x,route[1].y,speed,dt)
    end
    return true
end

---@param w SwarmWorld
---@param immune ImmuneCellRecord
---@param target ImmuneTargetView
local function beginAttack(w, immune, target)
    immune.attackTimer = immune.attackWindup
    setState(immune, "attack")
    if immune.kind=="tcell" then Director.ConfirmHotspot(w,immune,target) end
    if target.targetType == "cell" then
        local cell = cellById(w, target.id)
        if cell and cell.state ~= "DEAD" then
            w:Emit("node_attack_start", { immuneId = immune.id, cellId = cell.id,
                x = cell.x, y = cell.y, dangerRadius = immune.dangerRadius })
        end
    end
    print(string.format("[ImmuneSystem] 接触蓄力 immune=%d target=%s#%d %.1f秒",
        immune.id, target.targetType, target.id, immune.attackWindup))
end

-- Investigation is at real contact, after the full warning. Interrupted contact
-- resets evidence; only this immune/target pair retains confirmed recognition.
local function prepareAttack(w,immune,target)
    local behavior=w.config.immuneBehavior
    if immune.kind=="tcell" and behavior and not immune.recognized then
        immune.recognitionTimer=0
        local record=memoryEnabled(w,immune) and checkedCell(w,immune,target.id)
        immune.recognitionRequiredSeconds=Director.BehaviorValue(w,record and record.infected and "recheckSeconds" or "recognitionSeconds")
        setState(immune,"investigate")
        w:Emit("immune_identify_start",{immuneId=immune.id,cellId=target.id,seconds=immune.recognitionRequiredSeconds})
    else beginAttack(w,immune,target) end
end
local function addLoad(w,immune,amount)
    if immune.kind~="macrophage" or amount<=0 or not w.config.immuneBehavior then return end
    immune.processingLoad=math.min(w.config.immuneBehavior.loadCapacity,(immune.processingLoad or 0)+amount)
    w:Emit("immune_load",{immuneId=immune.id,load=immune.processingLoad})
end
---@param w SwarmWorld
---@param immune ImmuneCellRecord
---@param target ImmuneTargetView
local function finishAttack(w, immune, target)
    -- 结算入口再验一次实际接触，不能沿用发现时的距离或缓存对象状态。
    if not inContact(w, immune, target) then return end
    local cfg = w.config
    local limit = math.max(0, math.floor(cfg.immuneKillsPerAttack or 2))
    if immune.kind=="macrophage" and cfg.immuneBehavior then
        limit=math.min(limit,math.max(0,math.floor(cfg.immuneBehavior.loadCapacity-(immune.processingLoad or 0))))
    end
    if target.targetType == "swarm" then
        local swarm = swarmById(w, target.id)
        if swarm and swarm.mass > 0 and not swarm.isHidden and limit > 0 then
            local damage=Abilities.ImmuneDamage(w,swarm,limit,immune)
            local controlId = w.currentControlledSwarmId
            local controlled = w:SwarmById(controlId)
            local listenerX,listenerY = controlled and controlled.x,controlled and controlled.y
            local killed = w:DamageSwarm(swarm.id, damage)
            if killed > 0 then
                addLoad(w,immune,killed)
                Director.Alarm(w,immune,immune.x,immune.y)
                w:Emit("immune_attack", { immuneId = immune.id, swarmId = swarm.id,
                    x = immune.x, y = immune.y, killed = killed, controlId = controlId,
                    listenerX = listenerX, listenerY = listenerY })
            end
        end
    elseif target.targetType == "virus" then
        local virus = virusById(w, target.id)
        -- 每轮最多一个游离实体，失败也进入冷却；不可每帧重投概率/重杀 CLEARED。
        if virus and liveVirus(virus) and limit > 0
            and random(w) < clamp(cfg.immuneClearChance or 0.65, 0, 1) then
            if w:KillReleased(virus) then
                addLoad(w,immune,1)
                Director.Alarm(w,immune,virus.x,virus.y)
                w:Emit("immune_clear", { immuneId = immune.id, virusId = virus.id,
                    x = virus.x, y = virus.y })
            end
        end
    else
        local cell = cellById(w, target.id)
        if cell and nodeSignal(cell) > 0 then
            local shielded=(cell.shieldHits or 0)>0
            if shielded then cell.shieldHits=cell.shieldHits-1 end
            if not shielded then
                cell.immuneHits = (cell.immuneHits or 0) + 1
                Ecology.Pulse(w,cell.x,cell.y,"damage",cfg.ecology and cfg.ecology.damagePulse or 0)
                w:AddInflammation(cell.regionId, cfg.nodeAttackInflammation or 2.3, cfg.nodeAttackDamage or 0.8)
            end
            w:Emit("node_attack", { immuneId = immune.id, cellId = cell.id,
                x = cell.x, y = cell.y, dangerRadius = immune.dangerRadius,shielded=shielded })
            print(string.format("[ImmuneSystem] 节点受击 cell=%d hits=%d", cell.id, cell.immuneHits))
            if cell.immuneHits >= math.max(1, math.floor(cfg.immuneNodeHits or 3)) then
                w:KillCell(cell, "immune")
            end
        elseif cell and cell.state == "DEAD" and immune.kind == "macrophage" then
            local debris = w._immuneClearedDebris or {}
            w._immuneClearedDebris = debris
            if not debris[cell.id] then
                debris[cell.id] = true
                addLoad(w,immune,cfg.immuneBehavior and cfg.immuneBehavior.debrisLoad or 0)
                -- 清理在本步立即移除掩护，后行动的免疫不能再被旧伪装蒙蔽。
                Abilities.RefreshCamouflage(w,0)
                w:Emit("immune_cleanup", { immuneId = immune.id, cellId = cell.id, x = cell.x, y = cell.y })
            end
        end
    end
    immune.attackTimer = 0
    local _,_,interval=reaction(w,immune,target.targetType)
    immune.cooldown = math.max(0.01, interval or 2.8)
    setState(immune, "cooldown")
    local behavior=cfg.immuneBehavior
    if immune.kind=="macrophage" and behavior
        and (immune.processingLoad or 0)>behavior.loadCapacity-math.max(limit,behavior.debrisLoad) then
        releaseTarget(w,immune,false)
        setState(immune,"processing")
        w:Emit("immune_processing_start",{immuneId=immune.id,load=immune.processingLoad})
    end
    -- 仅成功清除后的直接交接免预警。下一颗必须仍在本地发现圈、可见且可预约；
    -- 保留本次吞噬冷却与下一颗真实接触蓄力。切换为群/残骸或处理负载会中断链。
    if immune.state=="cooldown" and target.targetType=="virus" then
        local previous=virusById(w,target.id)
        if previous and previous.state=="CLEARED" then
            local nextTarget=detect(w,immune)
            if nextTarget and nextTarget.targetType=="virus" then
                local remaining=immune.cooldown
                if lock(w,immune,nextTarget,true) then
                    immune.cooldown=remaining
                    setState(immune,"cooldown")
                    w:Emit("immune_clear_chain",{immuneId=immune.id,virusId=nextTarget.id})
                end
            end
        end
    end
end

---@param w SwarmWorld
---@param immune ImmuneCellRecord
---@param dt number
local function updateOne(w, immune, dt)
    immune._oldX, immune._oldY = immune.x, immune.y
    immune.stateTimer = immune.stateTimer + dt
    local behavior=w.config.immuneBehavior
    if immune._cleanupCancelled then
        if immune.targetId then releaseTarget(w,immune,false) end
        immune.hotspotCleanup,immune._cleanupCancelled=false,false
        immune._patrolTimer=0
    end
    Director.ObserveActivity(w,immune,dt)
    if immune._cellChecks then
        for id,record in pairs(immune._cellChecks) do
            if not memoryEnabled(w,immune) or w.time-record.checkedAt>=behavior.checkMemorySeconds then immune._cellChecks[id]=nil end
        end
    end
    if not memoryEnabled(w,immune) then immune._screenCellId,immune.screenTimer=nil,0 end
    if immune.kind=="macrophage" and behavior then
        immune.processingLoad=math.max(0,(immune.processingLoad or 0)-Director.BehaviorValue(w,"processingRate")*dt)
        if immune.state=="processing" then
            immune.cooldown=math.max(0,immune.cooldown-dt)
            if immune.processingLoad<=behavior.loadResume then
                setState(immune,immune.cooldown>EPSILON and "cooldown" or "patrol")
                w:Emit("immune_processing_end",{immuneId=immune.id,load=immune.processingLoad})
            end
            return
        end
    end
    if immune.state == "cooldown" and not immune.targetId then
        immune.cooldown = math.max(0, immune.cooldown - dt)
        if immune.cooldown <= EPSILON then setState(immune, "patrol") end
        return
    end
    if immune.state=="search" then
        local target=detect(w,immune)
        if target then lock(w,immune,target);return end
        if w.time>=immune._searchUntil then setState(immune,"patrol");immune._lastSeen=nil;return end
        immune._patrolTimer=math.max(0,immune._patrolTimer-dt)
        if immune._patrolTimer<=0 then
            local angle=random(w)*TAU
            local r=random(w)*Config.ImmuneAlert.searchRadius
            local x,y=immune._searchX+math.cos(angle)*r,immune._searchY+math.sin(angle)*r
            if clearLine(w,immune.x,immune.y,x,y,immune.radius) then immune._patrolX,immune._patrolY=x,y end
            immune._patrolTimer=1.5
        end
        move(w,immune,immune._patrolX,immune._patrolY,w.config.immuneSpeed,dt)
        return
    end
    if immune.state == "patrol" then
        local target = detect(w, immune)
        if target then
            local duty=w.immuneCleanupAssignments[immune.id];if duty then duty.quiet=0 end
            lock(w, immune, target); return
        end
        local duty=w.immuneCleanupAssignments[immune.id]
        if duty then
            local cfg=Config.ImmuneAlert
            local d=distance(immune.x,immune.y,duty.x,duty.y)
            if d<=1 then duty.arrived=true end
            if duty.arrived then
                duty.quiet=duty.quiet+dt
                if duty.quiet>=cfg.hotspotQuietSeconds then Director.EndCleanup(w,immune,"quiet");return end
                duty.sweepClock=math.max(0,duty.sweepClock-dt)
                if duty.sweepClock<=0 then
                    duty.sweepIndex=duty.sweepIndex+1
                    local angle=immune.id*2.399963+duty.sweepIndex*TAU/8
                    local x,y=duty.x+math.cos(angle)*duty.radius*.6,duty.y+math.sin(angle)*duty.radius*.6
                    if Navigation.Clear(w.map,immune,{x=x,y=y},immune.radius) then duty.sweepX,duty.sweepY=x,y end
                    duty.sweepClock=cfg.hotspotSweepInterval
                end
            end
            local x,y=duty.sweepX or duty.x,duty.sweepY or duty.y
            if Navigation.Clear(w.map,immune,{x=x,y=y},immune.radius) then move(w,immune,x,y,w.config.immuneSpeed,dt) end
            return
        end
        local alarm=w.immuneAlarmAssignments[immune.id]
        if alarm then
            immune.signalInvestigation=false
            move(w,immune,alarm.x,alarm.y,w.config.immuneSpeed,dt)
            return
        end
        local assignment=w.channelPatrolAssignments[immune.id]
        if assignment then
            if w.time<assignment.startsAt then return end
            local x,y=PatrolNavigation.Point(w.map,immune,assignment,w.time)
            if x and y then move(w,immune,x,y,w.config.immuneSpeed,dt) end
            return
        end
        local home=immune.patrolHome
        if home then
            if not Director.InPatrolArea(w,immune,immune.x,immune.y) then immune.returningHome=true end
            if immune.returningHome then
                immune._screenCellId,immune.screenTimer=nil,0
                immune.signalInvestigation=false
                if distance(immune.x,immune.y,home.x,home.y)<=1 then
                    immune.returningHome=false;immune._homeRoute=nil;immune._patrolTimer=0
                else
                    immune._homeRouteClock=math.max(0,(immune._homeRouteClock or 0)-dt)
                    if not immune._homeRoute or immune._stuckTimer>.6 then
                        if immune._homeRouteClock<=0 then
                            immune._homeRoute=Navigation.Route(w.map,immune,home,immune.radius)
                            immune._homeRouteClock=1
                            immune._stuckTimer=0
                        end
                    end
                    local route=immune._homeRoute
                    if route then
                        while #route>1 and distance(immune.x,immune.y,route[1].x,route[1].y)<.1 do table.remove(route,1) end
                        move(w,immune,route[1].x,route[1].y,w.config.immuneSpeed,dt)
                    end
                    return
                end
            end
        end
        if immune._screenCellId then
            local cell=cellById(w,immune._screenCellId)
            if not cell or (cell.state~="HEALTHY" and cell.state~="EXPOSED")
                or distance(immune.x,immune.y,cell.x,cell.y)>immune.detectionRange+cell.radius
                or not clearLine(w,immune.x,immune.y,cell.x,cell.y,0) then
                immune._screenCellId,immune.screenTimer=nil,0
                return
            end
            local view={targetType="cell",id=cell.id,x=cell.x,y=cell.y,radius=cell.radius,priority=0,signal=0}
            if inContact(w,immune,view) then
                immune.screenTimer=(immune.screenTimer or 0)+dt
                if immune.screenTimer+EPSILON>=(immune.screenRequiredSeconds or Director.BehaviorValue(w,"recognitionSeconds")) then
                    rememberCheck(w,immune,cell,false)
                    w:Emit("immune_screen_clear",{immuneId=immune.id,cellId=cell.id})
                    immune._screenCellId,immune.screenTimer=nil,0
                end
            else
                immune.screenTimer=0
                local point=Director.AttackPoint(w,immune,view)
                if point and Navigation.Clear(w.map,immune,point,immune.radius) then
                    move(w,immune,point.x,point.y,w.config.immuneSpeed,dt)
                else immune._screenCellId=nil end
            end
            return
        end
        immune._patrolTimer = math.max(0, immune._patrolTimer - dt)
        if immune._patrolTimer <= 0 or immune._stuckTimer > 0.6
            or distance(immune.x, immune.y, immune._patrolX, immune._patrolY) < 0.12 then
            choosePatrol(w, immune)
            immune._stuckTimer = 0
        end
        move(w, immune, immune._patrolX, immune._patrolY, w.config.immuneSpeed or 0.9, dt)
        return
    end
    local target = resolveTarget(w, immune)
    if not target then releaseTarget(w, immune, immune.state ~= "cooldown"); return end
    local duty=w.immuneCleanupAssignments[immune.id]
    if duty and (target.targetType=="swarm" or (target.x-duty.x)^2+(target.y-duty.y)^2>duty.radius^2) then
        releaseTarget(w,immune,false);return
    end
    if target.targetType=="virus" and immune.warningTime==0
        and distance(immune.x,immune.y,target.x,target.y)-target.radius>immune.detectionRange then
        releaseTarget(w,immune,false);return
    end
    -- 仅已锁定对象使用扩大的追踪圈；detect 的首次发现范围保持原样。
    local range=immune.detectionRange
    if target.targetType=="cell" and Director.Level(w)>=3 then
        local cell=cellById(w,target.id)
        if cell and cell.state=="PRODUCTIVE" and cell.releaseCount>0 then range=range*Config.ImmuneAlert.activeSignalMultiplier end
    end
    local forget=range+math.max(0,w.config.immuneForgetExtra or 1.8)+target.radius
    if distance(immune.x,immune.y,target.x,target.y)>forget
        or not clearLine(w,immune.x,immune.y,target.x,target.y,0) then
        releaseTarget(w,immune,true);return
    end
    if not Director.Reserve(w,immune,target) then releaseTarget(w,immune,false);return end
    Director.Remember(w,immune,target)
    if immune.kind=="macrophage" and target.targetType=="swarm"
        and (immune.state=="chase" or immune.state=="attack" or immune.state=="cooldown") and inContact(w,immune,target) then
        immune._encounterTimer=(immune._encounterTimer or 0)+dt
        if immune._encounterTimer>=Config.ImmuneAlert.alarmEncounterSeconds then Director.Alarm(w,immune,immune.x,immune.y) end
    else immune._encounterTimer=0 end
    -- Role changes restart warning and charge; continuous particle handoff is
    -- handled only after a successful clear, retaining its real cooldown.
    -- 正在打群的巨噬（蓄力或攻击冷却中）也要能被诱饵引开，否则贴身释放诱饵无效。
    local onSwarm=immune.kind=="macrophage" and target.targetType=="swarm"
        and (immune.state=="attack" or immune.state=="cooldown")
    if immune.state=="locked" or immune.state=="warning" or immune.state=="chase"
        or immune.kind=="macrophage" and immune.state=="attack" and target.targetType~="swarm"
        or onSwarm then
        immune._retargetTimer=math.max(0,(immune._retargetTimer or 0)-dt)
        if immune._retargetTimer<=0 then
            immune._retargetTimer=.25
            local preferred=detect(w,immune)
            if preferred and preferred.priority>target.priority and (not onSwarm or preferred.decoy) then
                local remaining=immune.state=="cooldown" and immune.cooldown or 0
                if lock(w,immune,preferred) then
                    -- 换靶不免除已开始的攻击冷却；冷却结束后直接追诱饵。
                    if remaining>EPSILON then immune.cooldown=remaining;setState(immune,"cooldown") end
                    w:Emit("immune_decoy_diverted",{immuneId=immune.id,virusId=preferred.id})
                    return
                end
            end
        end
    end
    immune.targetX, immune.targetY = target.x, target.y
    if immune.state == "locked" then
        setState(immune, "warning")
        w:Emit("immune_warning", { immuneId = immune.id, targetType = target.targetType,
            targetId = target.id, x = immune.x, y = immune.y, warningSeconds = immune.warningTime })
    elseif immune.state == "warning" then
        if not inContact(w,immune,target) then approach(w,immune,target,dt) end
        immune.warningTimer = math.max(0, immune.warningTimer - dt)
        if immune.warningTimer <= EPSILON then setState(immune, "chase") end
    elseif immune.state == "chase" then
        if inContact(w, immune, target) then prepareAttack(w, immune, target); return end
        if not approach(w,immune,target,dt) then releaseTarget(w,immune,false);return end
        if inContact(w, immune, target) then prepareAttack(w, immune, target)
        elseif immune._stuckTimer >= 1.5 then releaseTarget(w, immune, false) end
    elseif immune.state=="investigate" then
        if not inContact(w,immune,target) then
            immune.recognitionTimer,immune.recognized=0,false
            setState(immune,"chase");return
        end
        immune.recognitionTimer=(immune.recognitionTimer or 0)+dt
        if immune.recognitionTimer+EPSILON>=(immune.recognitionRequiredSeconds or (behavior and behavior.recognitionSeconds or 0)) then
            immune.recognized=true
            local cell=cellById(w,target.id)
            if cell then rememberCheck(w,immune,cell,true) end
            w:Emit("immune_identified",{immuneId=immune.id,cellId=target.id})
            beginAttack(w,immune,target)
        end
    elseif immune.state == "attack" then
        if immune.kind=="macrophage" and not inContact(w,immune,target) then
            approach(w,immune,target,math.min(dt,w.config.movementStep))
        end
        if not inContact(w, immune, target) then
            immune.attackTimer = 0
            setState(immune, "chase")
            w:Emit("immune_attack_cancel", { immuneId = immune.id, targetType = target.targetType,
                targetId = target.id, x = immune.x, y = immune.y })
            return
        end
        immune.attackTimer = math.max(0, immune.attackTimer - dt)
        if immune.attackTimer <= EPSILON then finishAttack(w, immune, target) end
    elseif immune.state == "cooldown" then
        immune.cooldown = math.max(0, immune.cooldown - dt)
        if immune.cooldown <= EPSILON then setState(immune, "chase") end
    end
end

---@param w SwarmWorld
---@param x number
---@param y number
---@param radius number
---@return boolean
local function safeSpawn(w, x, y, radius)
    if not w.map:Contains(x, y, radius) then return false end
    for _, swarm in ipairs(w.swarms) do
        -- 包括隐藏/非当前控制群：出生安全不能只检查 w.player alias。
        if swarm.mass > 0 then
            local safe = math.max(0, w.config.immuneSafeDistance or 4.5) + radius + swarm.radius
            if distance(x, y, swarm.x, swarm.y) < safe then return false end
        end
    end
    for _, immune in ipairs(w.immunes) do
        if distance(x, y, immune.x, immune.y) < radius + immune.radius + 0.15 then return false end
    end
    return true
end

---@param w SwarmWorld
---@return table<number, number>, number
local function infectionSignals(w)
    ---@type table<number, number>
    local signals = {}
    local total = 0
    for _, cell in ipairs(w.cells) do
        local signal = nodeSignal(cell)
        if signal > 0 then
            signals[cell.regionId] = (signals[cell.regionId] or 0) + signal
            total = total + signal
        end
    end
    return signals, total
end

---@param w SwarmWorld
---@param initial boolean
---@return boolean
local function spawn(w, initial)
    local cfg = w.config
    if #w.immunes>=Director.PopulationLimit(w) then return false end
    local radius = math.max(0.01, cfg.immuneRadius or 0.48)
    local counts={tcell=0,macrophage=0}
    for _,immune in ipairs(w.immunes) do counts[immune.kind]=counts[immune.kind]+1 end
    ---@type 'macrophage'|'tcell'
    local kind=counts.macrophage<=counts.tcell and "macrophage" or "tcell"
    local limits={tcell=Config.ImmuneAlert.maxTCells,macrophage=Config.ImmuneAlert.maxMacrophages}
    if counts[kind]>=limits[kind] then kind=kind=="tcell" and "macrophage" or "tcell" end
    if counts[kind]>=limits[kind] then return false end
    local signals = infectionSignals(w)
    local coverage=w.map.isFlatMap and cfg.immuneCoverage
    local residents={}
    if coverage then
        for _,unit in ipairs(w.immunes) do
            local region=unit.patrolHome and unit.patrolHome.regionId or unit.regionId
            local entry=residents[region] or {total=0,tcell=0,macrophage=0}
            residents[region]=entry;entry.total=entry.total+1;entry[unit.kind]=entry[unit.kind]+1
        end
    end
    ---@type ImmunePoint?
    local best = nil
    local bestScore = -math.huge
    ---@param x number
    ---@param y number
    local function consider(x, y)
        if not safeSpawn(w, x, y, radius) then return end
        local regionId = w.map:RegionAt(x, y)
        local proximity = math.huge
        for _, swarm in ipairs(w.swarms) do
            if swarm.mass > 0 then proximity = math.min(proximity, distance(x, y, swarm.x, swarm.y)) end
        end
        if proximity == math.huge then proximity = 20 end
        -- 同信号优先安全且靠近群的入口，避免所有实体远在另一个枝端。
        local score = (initial and 0 or (signals[regionId] or 0)*10) - proximity
        if coverage then
            -- 先补缺少该职责/驻巡人数的区域，再比较有限的感染压力与入口间距。
            -- 以固定辖区计数：追击中的单位不会导致原区被重复塞入增援。
            local entry=residents[regionId] or {total=0,tcell=0,macrophage=0}
            local spacing=coverage.spawnSpacing
            for _,unit in ipairs(w.immunes) do
                local home=unit.patrolHome or unit
                spacing=math.min(spacing,distance(x,y,home.x,home.y))
            end
            score=-entry[kind]*10000-entry.total*1000+spacing*2-proximity*.05
                +(initial and 0 or math.min(10,signals[regionId] or 0)*coverage.signalWeight)
        end
        if score > bestScore then best, bestScore = { x = x, y = y, regionId = regionId }, score end
    end
    for _, point in ipairs(w.map.immuneSpawns or {}) do consider(point.x, point.y) end
    -- 入口全部不安全时延期，绝不在组织外围任意空降。
    if not best then return false end
    local id = w._nextImmuneId or 1
    w._nextImmuneId = id + 1
    ---@type ImmuneCellRecord
    local immune = {
        id = id, kind = kind,
        x = best.x, y = best.y, radius = radius, variant = 1, phase = random(w)*TAU,
        state = "patrol", targetType = nil, targetId = nil, targetX = nil, targetY = nil,
        detectionRange = math.max(0.01, cfg.immuneDetectRange or 3.2),
        dangerRadius = math.max(0.01, cfg.immuneDetectRange or 3.2),
        warningTime = math.max(.01, cfg.immuneWarningSeconds or 2.8), warningTimer = 0,
        attackWindup = math.max(.01, cfg.immuneAttackWindup or 1.1), attackTimer = 0,
        cooldown = 0, stateTimer = 0, regionId = best.regionId or w.map:RegionAt(best.x, best.y),
        _oldX = best.x, _oldY = best.y, _patrolX = best.x, _patrolY = best.y,
        _patrolTimer = 0, _stuckTimer = 0,
        patrolHome = coverage and {x=best.x,y=best.y,regionId=best.regionId} or nil,
        dutyRole = coverage and (kind=="tcell" and "node"
            or ((residents[best.regionId] and residents[best.regionId].macrophage or 0)%2==0 and "pursuit" or "cleanup")) or nil,
    }
    w.immunes[#w.immunes + 1] = immune
    w:Emit("immune_spawn", { immuneId = id, kind = immune.kind, x = immune.x, y = immune.y,
        regionId = immune.regionId, role=immune.dutyRole })
    print(string.format("[ImmuneSystem] %s出生 %s#%d region=%d (%.2f,%.2f)",
        initial and "开局" or "招募", immune.kind, id, immune.regionId, immune.x, immune.y))
    return true
end

---@param w SwarmWorld
---@param startDef { immuneCount: number, flatImmuneCount: number? }
function ImmuneSystem.Init(w, startDef)
    w.immunes = {}
    w._nextImmuneId, w._immuneRecruitClock = 1, 0
    w._immuneClearedDebris = {}
    Director.Init(w)
    local requested=w.map.isFlatMap and startDef.flatImmuneCount or startDef.immuneCount
    w.immuneStartingCount=math.max(0,math.floor(requested or 0))
    local count = math.min(math.max(0, math.floor(requested or 0)),
        math.max(0, math.floor(math.min(w.config.immuneMax or 8,Config.ImmuneAlert.maxImmuneUnits))))
    for _ = 1, count do
        if not spawn(w, true) then
            print("[ImmuneSystem] 开局无安全免疫入口：保留玩家安全，不强行补满")
            break
        end
    end
end

---@param w SwarmWorld
---@param dt number
function ImmuneSystem.Update(w, dt)
    if not validStep(dt) then return end
    Director.Update(w,dt)
    for _, immune in ipairs(w.immunes) do updateOne(w, immune, dt) end
    Director.Separate(w,dt)
    -- 后行动者可能清除先行动者的目标，统一消除悬挂渲染目标。
    for _, immune in ipairs(w.immunes) do
        if immune.targetId and not resolveTarget(w, immune) then releaseTarget(w, immune, false) end
    end
end

---@param w SwarmWorld
---@param dt number
function ImmuneSystem.Recruit(w, dt)
    if not validStep(dt) then return end
    local _, total = infectionSignals(w)
    local coverage=w.map.isFlatMap and w.config.immuneCoverage
    local interval=math.max(.01,coverage and coverage.deploymentInterval or w.config.immuneRecruitInterval or 65)
    if (total<=0 and (not coverage or Director.Level(w)==0)) or #w.immunes>=Director.PopulationLimit(w) then
        w._immuneRecruitClock = 0
        return
    end
    local clock = math.min(interval, (w._immuneRecruitClock or 0) + dt)
    w._immuneRecruitClock = clock
    -- 正式地图按阶段目标分批入场；每次最多一名，安全入口不足则延期。
    if clock + EPSILON >= interval and spawn(w, false) then w._immuneRecruitClock = 0 end
end

-- 节点终态当步释放攻击预约；巨噬下一次局部发现后才能把它作为残骸处理。
function ImmuneSystem.InvalidateCell(w, cellId)
    w.immuneReservations["cell:"..cellId] = nil
    for _, immune in ipairs(w.immunes) do
        if immune._cellChecks then immune._cellChecks[cellId]=nil end
        if immune._screenCellId==cellId then immune._screenCellId,immune.screenTimer=nil,0 end
        if immune.targetType=="cell" and immune.targetId==cellId then
            releaseTarget(w,immune,false)
        end
    end
end

return ImmuneSystem
