-- SplitVirusAI.lua -- 分裂体的局部自主行动；只改真实病毒的位置与意图。
-- 弹射 -> 避敌优先 -> 寻找健康细胞 -> 在真实感染范围内停留。
-- 活动圆固定在释放点，不读取玩家位置；免疫接触仍由 SwarmWorld 扫掠判定。
-- 圆与地图边界都是运动约束，不是无敌区；被包围或贴墙时仍可能死亡。

---@alias SwarmVirus table 旧版分裂体协议，仅供未接入当前玩法的历史模块标注。
---@alias SwarmCell RespiratoryCell
local SplitVirusAI = {}
local TAU = math.pi * 2

---@param world SwarmWorld
---@param virus SwarmVirus
---@param originX number
---@param originY number
---@param angle number
function SplitVirusAI.Release(world, virus, originX, originY, angle)
    virus.state, virus.splitState = "split", "launch"
    virus.originX, virus.originY = originX, originY
    virus.launchAge = 0
    virus.thinkClock = (virus.id % 7) / 7 * world.config.splitThinkInterval
    virus.reactionClock = (virus.id % 7 + 1) / 7 * world.config.splitReactionInterval
    virus.fleeX, virus.fleeY, virus.alerted = 0.0, 0.0, false
    virus.targetCellId, virus.targetCell = nil, nil
    virus.wanderX, virus.wanderY = virus.x, virus.y
    virus.vx = math.cos(angle) * world.config.splitLaunchSpeed
    virus.vy = math.sin(angle) * world.config.splitLaunchSpeed
end

---@param world SwarmWorld
---@param virus SwarmVirus
---@param x number
---@param y number
local function moveTo(world, virus, x, y)
    local ox, oy = virus.originX or virus.x, virus.originY or virus.y
    local dx, dy = x - ox, y - oy
    local length = math.sqrt(dx * dx + dy * dy)
    local scale = math.min(1, world.config.splitRoamRadius / math.max(0.000001, length))
    local tx, ty = ox + dx * scale, oy + dy * scale
    local oldDX, oldDY = virus.x - ox, virus.y - oy
    if oldDX * oldDX + oldDY * oldDY > world.config.splitRoamRadius ^ 2 then
        -- 膜外感染产出的子代或大主群可能在圈外出生，只能按本步路程连续回圈。
        local budget = math.sqrt((x - virus.x) ^ 2 + (y - virus.y) ^ 2)
        local ex, ey = tx - virus.x, ty - virus.y
        local ratio = math.min(1, budget / math.max(0.000001, math.sqrt(ex * ex + ey * ey)))
        tx, ty = virus.x + ex * ratio, virus.y + ey * ratio
    end
    virus.x = math.max(virus.radius, math.min(world.width - virus.radius, tx))
    virus.y = math.max(virus.radius, math.min(world.height - virus.radius, ty))
end

---@param world SwarmWorld
---@param virus SwarmVirus
---@param cell SwarmCell
---@return boolean
local function reachable(world, virus, cell)
    local ox, oy = virus.originX or virus.x, virus.originY or virus.y
    local dx, dy = cell.x - ox, cell.y - oy
    -- 与停留判定同口径：圆外细胞中心只要膜附近仍可接触，就能成为目标。
    local range = (cell.radius + world.config.infectionRadius + virus.radius) * 0.88
    return cell.state == "healthy" and dx * dx + dy * dy <= (world.config.splitRoamRadius + range) ^ 2
end

---@param world SwarmWorld
---@param virus SwarmVirus
---@param reservations table<number, integer>
---@return SwarmCell?
local function chooseCell(world, virus, reservations)
    ---@type SwarmCell?
    local bestCell = nil
    local bestScore = math.huge
    for _, cell in ipairs(world.cells) do
        if reachable(world, virus, cell) then
            local dx, dy = cell.x - virus.x, cell.y - virus.y
            local distanceSq = dx * dx + dy * dy
            local score = math.sqrt(distanceSq) - cell.exposure * 0.6
            local others = math.max(0, (reservations[cell.id] or 0)
                - (virus.targetCellId == cell.id and 1 or 0))
            score = score + others * 0.7
            if virus.targetCellId == cell.id then score = score - 0.45 end
            for _, immune in ipairs(world.immunes) do
                -- 检查前往细胞的整条路径，不能只看目标安全就迎头穿过免疫。
                local ix, iy = immune.x - virus.x, immune.y - virus.y
                local t = math.max(0, math.min(1, (ix * dx + iy * dy) / math.max(0.000001, distanceSq)))
                local ex, ey = ix - dx * t, iy - dy * t
                local clearance = math.sqrt(ex * ex + ey * ey) - immune.radius - virus.radius
                if clearance < world.config.splitAvoidRadius then
                    score = score + (world.config.splitAvoidRadius - clearance) * 6
                end
            end
            if score < bestScore or (score == bestScore and bestCell and cell.id < bestCell.id) then
                bestCell, bestScore = cell, score
            end
        end
    end
    return bestCell
end

---@param world SwarmWorld
---@param virus SwarmVirus
---@return number, number, boolean
local function escapeDirection(world, virus)
    local fx, fy, nearestDistance = 0.0, 0.0, math.huge
    local nearestX, nearestY = 0.0, 0.0
    local nearestId = math.huge
    for _, immune in ipairs(world.immunes) do
        local dx, dy = virus.x - immune.x, virus.y - immune.y
        local distance = math.sqrt(dx * dx + dy * dy)
        local danger = immune.radius + virus.radius + world.config.splitAvoidRadius
        if distance < danger then
            local nx, ny = math.cos(virus.phase), math.sin(virus.phase)
            if distance > 0.000001 then nx, ny = dx / distance, dy / distance end
            local weight = (danger - distance) / danger
            fx, fy = fx + nx * weight, fy + ny * weight
            if distance < nearestDistance or (distance == nearestDistance and immune.id < nearestId) then
                nearestDistance, nearestX, nearestY, nearestId = distance, nx, ny, immune.id
            end
        end
    end
    if nearestDistance == math.huge then return 0, 0, false end
    -- 对称围堵时不除以零；少量侧向偏置使同批病毒不沿同一条线逃跑。
    if fx * fx + fy * fy < 0.000001 then fx, fy = nearestX, nearestY end
    local side = virus.id % 2 == 0 and 0.25 or -0.25
    local sx, sy = fx - nearestY * side, fy + nearestX * side
    local length = math.sqrt(sx * sx + sy * sy)
    return sx / length, sy / length, true
end

---@param world SwarmWorld
---@param virus SwarmVirus
local function chooseWander(world, virus)
    local angle = world:_Random() * TAU
    local radius = math.sqrt(world:_Random()) * world.config.splitRoamRadius * 0.85
    -- 目标必须在真实地图内，否则贴墙后永远到不了原目标，无法重新游荡。
    virus.wanderX = math.max(virus.radius, math.min(world.width - virus.radius,
        (virus.originX or virus.x) + math.cos(angle) * radius))
    virus.wanderY = math.max(virus.radius, math.min(world.height - virus.radius,
        (virus.originY or virus.y) + math.sin(angle) * radius))
end

---@param world SwarmWorld
---@param virus SwarmVirus
---@param dt number
---@param reservations table<number, integer>
function SplitVirusAI.Update(world, virus, dt, reservations)
    local cfg = world.config
    virus.reactionClock = virus.reactionClock - dt
    if virus.reactionClock <= 0 then
        -- 只在感知节拍更新方向，节拍之间沿旧方向行动，不每步完美闪避。
        virus.fleeX, virus.fleeY, virus.alerted = escapeDirection(world, virus)
        virus.reactionClock = math.max(0.01, cfg.splitReactionInterval)
    end
    local fx, fy, danger = virus.fleeX, virus.fleeY, virus.alerted
    if virus.splitState == "launch" then
        if not danger and virus.launchAge < cfg.splitLaunchSeconds then
            local active = math.min(dt, cfg.splitLaunchSeconds - virus.launchAge)
            local decay = math.exp(-cfg.splitLaunchDrag * active)
            local travel = cfg.splitLaunchDrag > 0 and (1 - decay) / cfg.splitLaunchDrag or active
            moveTo(world, virus, virus.x + virus.vx * travel, virus.y + virus.vy * travel)
            virus.vx, virus.vy = virus.vx * decay, virus.vy * decay
            virus.launchAge = virus.launchAge + dt
            return
        end
        virus.splitState = "wander"
    end
    virus.thinkClock = virus.thinkClock - dt
    if danger then
        virus.splitState = "flee"
        moveTo(world, virus, virus.x + fx * cfg.splitFleeSpeed * dt, virus.y + fy * cfg.splitFleeSpeed * dt)
        return
    end

    ---@type SwarmCell?
    local target = virus.targetCell
    if target and not reachable(world, virus, target) then target = nil end
    if virus.thinkClock <= 0 or (virus.targetCellId and not target) then
        local previous = virus.targetCellId
        target = chooseCell(world, virus, reservations)
        if previous then reservations[previous] = math.max(0, (reservations[previous] or 0) - 1) end
        virus.targetCell = target
        virus.targetCellId = target and target.id or nil
        if target then reservations[target.id] = (reservations[target.id] or 0) + 1 end
        virus.thinkClock = cfg.splitThinkInterval
        if not target and (virus.wanderX - virus.x)^2 + (virus.wanderY - virus.y)^2 < 0.1^2 then
            chooseWander(world, virus)
        end
    end

    local tx, ty = virus.wanderX, virus.wanderY
    if target then
        local dx, dy = target.x - virus.x, target.y - virus.y
        local range = target.radius + cfg.infectionRadius + virus.radius
        if dx * dx + dy * dy <= (range * 0.88) ^ 2 then
            virus.splitState = "infect"
            virus.vx, virus.vy = 0, 0
            return -- 停留由 SwarmWorld 的真实 covered 计时，不在 AI 里直接感染。
        end
        virus.splitState = "seek"
        tx, ty = target.x, target.y
    else
        virus.splitState = "wander"
    end
    local dx, dy = tx - virus.x, ty - virus.y
    local length = math.sqrt(dx * dx + dy * dy)
    local ratio = math.min(1, cfg.splitMoveSpeed * dt / math.max(0.000001, length))
    moveTo(world, virus, virus.x + dx * ratio, virus.y + dy * ratio)
end

-- 当前群级协议。以下接口只产生意图，绝不移动、感染、扣质量或调用历史 Update。
-- 地图实际位移仍唯一走 SwarmWorld -> RespiratoryMap:Move。
-- 感知/选靶/逃逸探测只有局部直线 Sweep，不是全局导航。

---@class SwarmAutonomyContext
---@field cells table<number, RespiratoryCell>
---@field reservations table<number, integer>
---@field supplies table<number,integer>

---@param world SwarmWorld
---@return boolean
function SplitVirusAI.Enabled(world)
    return world.swarmBrainEnabled == true and world.config.autonomy ~= nil and world.config.autonomy.enabled == true
end

---@param world SwarmWorld
---@param swarm SwarmRecord
---@return boolean
function SplitVirusAI.IsAutonomous(world, swarm)
    return SplitVirusAI.Enabled(world) and swarm.mass > 0 and not swarm.isHidden
        and not swarm.relayCellId and not swarm.anchored and not swarm.glideCellId and not swarm.dashUntil and not swarm.rescueUntil and not swarm.groupCommand
        and not swarm.isPlayerControlled
end

---@param world SwarmWorld
---@param swarm SwarmRecord
---@param resetCooldown? boolean
function SplitVirusAI.ResetSwarm(world, swarm, resetCooldown)
    if world.brainReservations and swarm.aiTargetCellId then
        local owners = world.brainReservations[swarm.aiTargetCellId]
        if owners then owners[swarm.id] = nil end
    end
    swarm.aiTargetCellId = nil
    swarm._aiSupplyId,swarm._aiExploreX,swarm._aiExploreY = nil,nil,nil
    swarm._aiVisits = {}
    swarm._aiSensedCells=nil
    swarm.aiState = swarm.isHidden and "hidden" or swarm.isPlayerControlled and "controlled"
        or SplitVirusAI.Enabled(world) and "idle" or "disabled"
    swarm._aiThinkClock, swarm._aiTargetHold, swarm._aiWanderClock = 0, 0, 0
    swarm._aiDirectionX, swarm._aiDirectionY = 0, 0
    swarm._aiMoveX, swarm._aiMoveY = swarm.x, swarm.y
    swarm._aiDangerMemory, swarm._aiReservationTimer = 0, 0
    if resetCooldown then
        swarm.autoSplitCooldown = world.config.autonomy and world.config.autonomy.splitCooldown or 8
    end
end

---@param world SwarmWorld
---@param swarm SwarmRecord
---@return ImmuneCellRecord[]
local function visibleThreats(world, swarm)
    ---@type ImmuneCellRecord[]
    local result = {}
    local cfg = world.config.autonomy
    for _, immune in ipairs(world.immunes) do
        local dx, dy = immune.x-swarm.x, immune.y-swarm.y
        local range = cfg.searchRadius+swarm.radius+immune.radius
        -- 仅近距、真实合法、无墙遮挡对象。绝不读取远端 targetX/玩家位置来透视。
        if dx*dx+dy*dy <= range*range and world.map:Contains(immune.x,immune.y,immune.radius)
            and world:_DirectPathClear(swarm.x,swarm.y,immune.x,immune.y,0) then
            result[#result+1] = immune
        end
    end
    return result
end

---@param world SwarmWorld
---@param swarm SwarmRecord
---@param threats ImmuneCellRecord[]
---@return boolean
local function dangerous(world, swarm, threats)
    for _, immune in ipairs(threats) do
        local cfg = world.config.autonomy
        local radius = swarm.radius+immune.radius+(swarm.aiState=="flee" and cfg.dangerExitExtra or cfg.dangerExtra)
        if (immune.x-swarm.x)^2+(immune.y-swarm.y)^2 < radius*radius
            or (immune.targetType=="swarm" and immune.targetId==swarm.id
                and (immune.state=="warning" or immune.state=="attack" or immune.state=="locked")) then return true end
    end
    return swarm.aiState=="flee" and (swarm._aiDangerMemory or 0)>0
end

---@param world SwarmWorld
---@param swarm SwarmRecord
---@return boolean
function SplitVirusAI.HasDanger(world, swarm)
    return dangerous(world,swarm,visibleThreats(world,swarm))
end

-- 逃逸碰撞推演（米）：
--   墙 || (群 S) <- I1      I2
--      ||   \ 有限24方向探测，截在第一道墙前，比较所有可见威胁的最小净距。
--   对称包围不能除零；全部受阻则停下，不穿墙、不远程削弱免疫。
--   探测只算意图；实际惯性/组织流/免疫追踪照常，不能保证逃脱成功。
---@param world SwarmWorld
---@param swarm SwarmRecord
---@param threats ImmuneCellRecord[]
---@return number, number
local function fleeDirection(world, swarm, threats)
    local cfg = world.config.autonomy
    local probe = math.max(0.1,cfg.escapeProbe)
    local preferredX, preferredY = swarm._aiDirectionX, swarm._aiDirectionY
    if swarm.aiState ~= "flee" then
        preferredX,preferredY = 0,0
        for _, immune in ipairs(threats) do
            local dx,dy = swarm.x-immune.x,swarm.y-immune.y
            local d = math.max(0.001,math.sqrt(dx*dx+dy*dy))
            preferredX,preferredY = preferredX+dx/(d*d),preferredY+dy/(d*d)
        end
    end
    local baselineWorst,baselineSum = math.huge,0
    for _, immune in ipairs(threats) do
        local gap = math.sqrt((swarm.x-immune.x)^2+(swarm.y-immune.y)^2)-swarm.radius-immune.radius
        baselineWorst = math.min(baselineWorst,gap)
        baselineSum = baselineSum+math.min(cfg.dangerExtra,gap)
    end
    local bestX,bestY,bestScore = 0,0,baselineWorst+baselineSum*0.04
    ---@param dx number
    ---@param dy number
    local function consider(dx,dy)
        local fraction = world.map:_Sweep(swarm.x,swarm.y,dx*probe,dy*probe,swarm.radius)
        local travel = math.max(0,math.min(1,fraction)-0.00001)*probe
        if travel < probe*0.12 then return end
        local x,y = swarm.x+dx*travel,swarm.y+dy*travel
        if not world.map:Contains(x,y,swarm.radius) then return end
        local worst,sum,pathWorst = math.huge,0,math.huge
        for _, immune in ipairs(threats) do
            local gap = math.sqrt((x-immune.x)^2+(y-immune.y)^2)-swarm.radius-immune.radius
            worst = math.min(worst,gap)
            sum = sum+math.min(cfg.dangerExtra,gap)
            local ix,iy = immune.x-swarm.x,immune.y-swarm.y
            local along = math.max(0,math.min(travel,ix*dx+iy*dy))
            pathWorst = math.min(pathWorst,math.sqrt((ix-dx*along)^2+(iy-dy*along)^2)
                -swarm.radius-immune.radius)
        end
        -- 静止是合法候选；不能为“有位移”选更危险终点，或穿过近威胁再算终点安全。
        if worst <= baselineWorst+0.00001 or pathWorst < baselineWorst-0.0001 then return end
        local score = worst+sum*0.04+travel*0.025+(dx*preferredX+dy*preferredY)*0.015
        if score > bestScore+1e-9 then bestX,bestY,bestScore=dx,dy,score end
    end
    local length = math.sqrt(preferredX*preferredX+preferredY*preferredY)
    if length > 0.00001 then consider(preferredX/length,preferredY/length) end
    local samples = math.max(8,math.floor(cfg.directionSamples))
    local phase = swarm.id*2.399963229728653
    for index=1,samples do
        local angle = phase+index*TAU/samples
        consider(math.cos(angle),math.sin(angle))
    end
    return bestX,bestY
end

---@param world SwarmWorld
---@param swarm SwarmRecord
---@param x number
---@param y number
---@param threats ImmuneCellRecord[]
---@return boolean
local function safePath(world,swarm,x,y,threats)
    if not world:_DirectPathClear(swarm.x,swarm.y,x,y,swarm.radius) then return false end
    local dx,dy = x-swarm.x,y-swarm.y
    local lengthSq = math.max(0.000001,dx*dx+dy*dy)
    for _, cell in ipairs(swarm._aiSensedCells or world.cells) do
        if cell.state ~= "DEAD" then
            local cx,cy = cell.x-swarm.x,cell.y-swarm.y
            local t = math.max(0,math.min(1,(cx*dx+cy*dy)/lengthSq))
            local clearance = cell.radius+swarm.radius+world.config.autonomy.cellClearance
            local initial = cx*cx+cy*cy
            local closest = (cx-dx*t)^2+(cy-dy*t)^2
            if closest < clearance*clearance-1e-9 and (initial>=clearance*clearance or closest<initial-1e-9) then return false end
        end
    end
    for _, immune in ipairs(threats) do
        local ix,iy = immune.x-swarm.x,immune.y-swarm.y
        local t = math.max(0,math.min(1,(ix*dx+iy*dy)/lengthSq))
        local clearance = swarm.radius+immune.radius+world.config.autonomy.dangerExtra
        if (ix-dx*t)^2+(iy-dy*t)^2 < clearance*clearance then return false end
    end
    return true
end

-- Bounded two-leg detours around currently visible nearby cell bodies only.
-- No full-map navigation, hidden target reads or movement overrides.
---@param world SwarmWorld
---@param swarm SwarmRecord
---@param x number
---@param y number
---@param threats ImmuneCellRecord[]
---@return boolean,number,number
local function localPath(world,swarm,x,y,threats)
    if safePath(world,swarm,x,y,threats) then return true,x,y end
    local cfg=world.config.autonomy
    local best,bx,by=math.huge,x,y
    for _,obstacle in ipairs(swarm._aiSensedCells or world.cells) do
        if obstacle.state~="DEAD" and (obstacle.x-swarm.x)^2+(obstacle.y-swarm.y)^2<=cfg.searchRadius^2
            and world:_DirectPathClear(swarm.x,swarm.y,obstacle.x,obstacle.y,0) then
            local dx,dy=x-swarm.x,y-swarm.y;local len=math.max(1e-9,dx*dx+dy*dy)
            local t=math.max(0,math.min(1,((obstacle.x-swarm.x)*dx+(obstacle.y-swarm.y)*dy)/len))
            local r=obstacle.radius+swarm.radius+cfg.cellClearance
            if (obstacle.x-swarm.x-dx*t)^2+(obstacle.y-swarm.y-dy*t)^2<(r+cfg.detourExtra)^2 then
                for ring=1,2 do for i=0,15 do
                    local angle=i*TAU/16;local radius=r*(ring==1 and 1.5 or 2)+cfg.detourExtra
                    local tx,ty=obstacle.x+math.cos(angle)*radius,obstacle.y+math.sin(angle)*radius
                    local travel=math.sqrt((tx-swarm.x)^2+(ty-swarm.y)^2)+math.sqrt((tx-x)^2+(ty-y)^2)
                    if travel<best and (tx-swarm.x)^2+(ty-swarm.y)^2<=cfg.searchRadius^2
                        and safePath(world,swarm,tx,ty,threats) then
                        ---@type SwarmRecord
                        local ghost=setmetatable({x=tx,y=ty},{__index=swarm})
                        if safePath(world,ghost,x,y,threats) then best,bx,by=travel,tx,ty end
                    end
                end end
            end
        end
    end
    return best<math.huge,bx,by
end
---@param world SwarmWorld
---@param swarm SwarmRecord
---@param cell RespiratoryCell
---@param threats ImmuneCellRecord[]
---@return boolean, number, number, number
local function cellApproach(world,swarm,cell,threats)
    local dx,dy = cell.x-swarm.x,cell.y-swarm.y
    local d = math.sqrt(dx*dx+dy*dy)
    if (cell.state ~= "HEALTHY" and cell.state ~= "EXPOSED")
        or d > world.config.autonomy.searchRadius
        or not world:_DirectPathClear(swarm.x,swarm.y,cell.x,cell.y,0) then return false,0,0,d end
    local radius = cell.radius+swarm.radius+math.max(world.config.autonomy.cellClearance, world.config.infectionReach*0.35)
    local x,y = swarm.x,swarm.y
    if d > radius then
        local best = math.huge
        local phase = math.atan(-dy,-dx)
        for i=0,12 do
            local angle = phase+i*TAU/12
            local tx,ty = cell.x+math.cos(angle)*radius,cell.y+math.sin(angle)*radius
            local travel = (tx-swarm.x)^2+(ty-swarm.y)^2
            if travel < best and safePath(world,swarm,tx,ty,threats) then x,y,best=tx,ty,travel end
        end
        if best==math.huge then
            local tx,ty=cell.x-dx/math.max(d,.001)*radius,cell.y-dy/math.max(d,.001)*radius
            local ok;ok,x,y=localPath(world,swarm,tx,ty,threats)
            if not ok then return false,x,y,d end
        end
    elseif not safePath(world,swarm,x,y,threats) then return false,x,y,d end
    for _, immune in ipairs(threats) do
        local danger = immune.radius+cell.radius+world.config.autonomy.dangerExtra
        if (cell.x-immune.x)^2+(cell.y-immune.y)^2 < danger*danger then return false,x,y,d end
    end
    return true,x,y,d
end

-- 意图与组织流合并后的连续圆体避让；只约束小脑，绝不挪动其他实体。
function SplitVirusAI.RestrictCellMotion(world,swarm,tx,ty)
    local dx,dy = tx-swarm.x,ty-swarm.y
    local a = dx*dx+dy*dy
    if a < 1e-12 then return tx,ty end
    local fraction = 1
    for _,cell in ipairs(world:NearbyCells(swarm.x,swarm.y,
        swarm.radius+world.config.autonomy.cellClearance+math.sqrt(a))) do
        if cell.state ~= "DEAD" then
            local px,py = swarm.x-cell.x,swarm.y-cell.y
            local r = swarm.radius+cell.radius+world.config.autonomy.cellClearance
            local c = px*px+py*py-r*r
            local b = 2*(px*dx+py*dy)
            if c<0 then
                if b<0 then fraction=0 end -- 已有重叠只能向外移动。
            else
                local discriminant = b*b-4*a*c
                if discriminant >= 0 then
                    local enter = (-b-math.sqrt(discriminant))/(2*a)
                    if enter>=0 and enter<=fraction then fraction=math.max(0,enter-1e-5) end
                end
            end
        end
    end
    return swarm.x+dx*fraction,swarm.y+dy*fraction
end

local function targetScore(world,swarm,cell,d,context,threats,x,y)
    local cfg = world.config.autonomy
    local risk = 0
    for _,immune in ipairs(threats) do
        local gap=math.sqrt((cell.x-immune.x)^2+(cell.y-immune.y)^2)-immune.radius-cell.radius
        risk=risk+1/math.max(.2,gap)
    end
    local fx,fy=world.map:FlowAt(swarm.x,swarm.y,world.time)
    local dx,dy=x-swarm.x,y-swarm.y
    local length=math.max(.001,math.sqrt(dx*dx+dy*dy))
    local reverse=math.max(0,-(dx*fx+dy*fy)/length)
    local defense=(cell.antiviralStrength or 0)*cfg.riskWeight
    return defense+d*cfg.distanceWeight-cell.exposure*cfg.exposureWeight
        +(context.reservations[cell.id] or 0)*cfg.reservationPenalty
        +risk*cfg.riskWeight+reverse*cfg.flowWeight
end

local function supply(world,swarm,context,threats)
    local cfg=world.config.autonomy
    local best,chosen,x,y=math.huge,nil,swarm.x,swarm.y
    for _,v in ipairs(world:NearbyReleased(swarm.x,swarm.y,cfg.collectRadius)) do
        if (v.state=="RELEASED" or v.state=="DRIFTING" or v.state=="ATTRACTED" or v.state=="INFECTING")
            and v.age<v.lifetime and not context.supplies[v.id]
            and world:_CanPassivelyAbsorbReleased(swarm,v)
            and (v.x-swarm.x)^2+(v.y-swarm.y)^2<=cfg.collectRadius^2
            and world:_DirectPathClear(swarm.x,swarm.y,v.x,v.y,0) then
            local d=(v.x-swarm.x)^2+(v.y-swarm.y)^2
            if d<best then
                local ok,tx,ty=localPath(world,swarm,v.x,v.y,threats)
                if ok then chosen,best,x,y=v,d,tx,ty end
            end
        end
    end
    if not chosen then return false end
    swarm.aiTargetCellId,swarm._aiTargetHold,swarm._aiReservationTimer=nil,0,0
    swarm.aiState,swarm._aiSupplyId="collect",chosen.id
    swarm._aiMoveX,swarm._aiMoveY=x,y
    swarm._aiExploreX,swarm._aiExploreY=nil,nil
    context.supplies[chosen.id]=swarm.id
    return true
end
local function explore(world,swarm,threats)
    local cfg=world.config.autonomy
    swarm._aiExploreX,swarm._aiExploreY=swarm._aiExploreX or swarm.x,swarm._aiExploreY or swarm.y
    if swarm.aiState=="wander" and swarm._aiWanderClock>0
        and (swarm._aiMoveX-swarm.x)^2+(swarm._aiMoveY-swarm.y)^2>.12^2
        and safePath(world,swarm,swarm._aiMoveX,swarm._aiMoveY,threats) then return end
    swarm._aiVisits=swarm._aiVisits or {}
    local best,bx,by=-math.huge,swarm.x,swarm.y
    for i=0,15 do
        local angle=i*TAU/16
        local dx,dy=math.cos(angle),math.sin(angle)
        local tx,ty=swarm.x+dx*1.2,swarm.y+dy*1.2
        if (tx-swarm._aiExploreX)^2+(ty-swarm._aiExploreY)^2<=cfg.wanderRadius^2
            and safePath(world,swarm,tx,ty,threats) then
            local score=dx*(swarm._aiDirectionX or 0)+dy*(swarm._aiDirectionY or 0)
            for _,p in ipairs(swarm._aiVisits) do score=score-1/math.max(.2,(tx-p.x)^2+(ty-p.y)^2) end
            if score>best then best,bx,by=score,tx,ty end
        end
    end
    if best==-math.huge then
        swarm.aiState="idle";swarm._aiMoveX,swarm._aiMoveY=swarm.x,swarm.y;return
    end
    swarm._aiVisits[#swarm._aiVisits+1]={x=swarm.x,y=swarm.y}
    if #swarm._aiVisits>6 then table.remove(swarm._aiVisits,1) end
    local length=math.max(.001,math.sqrt((bx-swarm.x)^2+(by-swarm.y)^2))
    swarm._aiDirectionX,swarm._aiDirectionY=(bx-swarm.x)/length,(by-swarm.y)/length
    swarm.aiState,swarm._aiMoveX,swarm._aiMoveY="wander",bx,by
    swarm._aiWanderClock=cfg.wanderSeconds
end
---@param world SwarmWorld
---@param swarm SwarmRecord
---@param context SwarmAutonomyContext
---@param threats ImmuneCellRecord[]
local function thinkSwarm(world,swarm,context,threats)
    local cfg = world.config.autonomy
    swarm._aiSensedCells={}
    for _,cell in ipairs(world:NearbyCells(swarm.x,swarm.y,cfg.searchRadius)) do
        if (cell.x-swarm.x)^2+(cell.y-swarm.y)^2<=cfg.searchRadius^2
            and world:_DirectPathClear(swarm.x,swarm.y,cell.x,cell.y,0) then
            swarm._aiSensedCells[#swarm._aiSensedCells+1]=cell
        end
    end
    if swarm._aiSupplyId then context.supplies[swarm._aiSupplyId]=nil;swarm._aiSupplyId=nil end
    if swarm.aiTargetCellId then
        local old = swarm.aiTargetCellId
        context.reservations[old] = math.max(0,(context.reservations[old] or 0)-1)
    end
    if dangerous(world,swarm,threats) then
        -- 只有实际局部威胁刷新记忆；解除期间不会自己无限延长。
        for _,immune in ipairs(threats) do
            local gap=math.sqrt((immune.x-swarm.x)^2+(immune.y-swarm.y)^2)-swarm.radius-immune.radius
            if gap<cfg.dangerExtra then swarm._aiDangerMemory=cfg.dangerMemorySeconds end
        end
        swarm._aiDirectionX,swarm._aiDirectionY = fleeDirection(world,swarm,threats)
        swarm.aiState,swarm.aiTargetCellId = "flee",nil
        swarm._aiTargetHold = 0
        return
    end
    ---@type RespiratoryCell?
    local chosen = nil
    local best,moveX,moveY = math.huge,swarm.x,swarm.y
    local incumbent = swarm.aiTargetCellId and context.cells[swarm.aiTargetCellId] or nil
    -- Near completion only wins while safe; danger was resolved before this branch.
    local finishing=incumbent and incumbent.exposure>=cfg.completionExposure
        and (incumbent.x-swarm.x)^2+(incumbent.y-swarm.y)^2<=(incumbent.radius+swarm.radius+world.config.infectionReach)^2
    swarm._aiSupplyId=nil
    if swarm.mass<cfg.collectBelowMass and not finishing and supply(world,swarm,context,threats) then return end
    if incumbent and (swarm._aiTargetHold > 0 or finishing) then
        local ok,x,y = cellApproach(world,swarm,incumbent,threats)
        if ok then chosen,moveX,moveY,best=incumbent,x,y,targetScore(world,swarm,incumbent,math.sqrt((incumbent.x-swarm.x)^2+(incumbent.y-swarm.y)^2),context,threats,x,y) end
    end
    if not chosen then
        for _, cell in ipairs(swarm._aiSensedCells) do
            local dx,dy = cell.x-swarm.x,cell.y-swarm.y
            if dx*dx+dy*dy <= cfg.searchRadius*cfg.searchRadius then
                local ok,x,y,d = cellApproach(world,swarm,cell,threats)
                if ok then
                    local score = targetScore(world,swarm,cell,d,context,threats,x,y)
                    if score < best-1e-9 or (math.abs(score-best)<1e-9 and chosen and cell.id<chosen.id) then
                        chosen,best,moveX,moveY = cell,score,x,y
                    end
                end
            end
        end
    end
    if chosen then
        -- 过了最短保留时间也必须明显优于旧目标，不每帧抖靶。
        if incumbent and chosen.id~=incumbent.id then
            local ok,x,y,d=cellApproach(world,swarm,incumbent,threats)
            if ok and targetScore(world,swarm,incumbent,d,context,threats,x,y)-best<cfg.switchImprovement then
                chosen,moveX,moveY=incumbent,x,y
            end
        end
        if chosen.id ~= swarm.aiTargetCellId then
            swarm._aiTargetHold=cfg.targetHoldSeconds
            swarm._aiReservationTimer=cfg.reservationTimeout
        end
        swarm._aiExploreX,swarm._aiExploreY=nil,nil
        swarm.aiTargetCellId = chosen.id
        ---@type table<number, integer>
        local reservations = context.reservations
        local previousCount = rawget(reservations,chosen.id) or 0
        reservations[chosen.id] = previousCount+1
        swarm._aiMoveX,swarm._aiMoveY = moveX,moveY
        swarm.aiState = (moveX-swarm.x)^2+(moveY-swarm.y)^2 < 0.02^2 and "infect" or "seek"
        return
    end
    swarm.aiTargetCellId,swarm._aiTargetHold = nil,0
    swarm._aiReservationTimer = 0
    explore(world,swarm,threats)
end

---@param world SwarmWorld
---@param dt number
function SplitVirusAI.ThinkWorld(world,dt)
    ---@type SwarmAutonomyContext
    local context = {cells={},reservations={},supplies={}}
    ---@type SwarmRecord[]
    local ordered = {}
    for _, cell in ipairs(world.cells) do context.cells[cell.id]=cell end
    for _, swarm in ipairs(world.swarms) do
        if SplitVirusAI.IsAutonomous(world,swarm) then
            ordered[#ordered+1] = swarm
            if swarm._aiSupplyId then context.supplies[swarm._aiSupplyId]=swarm.id end
            local cell = swarm.aiTargetCellId and context.cells[swarm.aiTargetCellId] or nil
            if cell and (cell.state=="HEALTHY" or cell.state=="EXPOSED") then
                context.reservations[cell.id] = (context.reservations[cell.id] or 0)+1
            elseif swarm.aiTargetCellId then
                swarm.aiTargetCellId = nil
                swarm._aiThinkClock = 0
            end
        else SplitVirusAI.ResetSwarm(world,swarm,false) end
    end
    world.brainReservations = {}
    -- ID顺序稳定；每步重建预约，没有永久悬挂的所有者。
    table.sort(ordered,function(a,b) return a.id<b.id end)
    for _, swarm in ipairs(ordered) do
        swarm._aiDangerMemory = math.max(0,(swarm._aiDangerMemory or 0)-dt)
        swarm._aiReservationTimer = math.max(0,(swarm._aiReservationTimer or 0)-dt)
        if swarm.aiTargetCellId and swarm._aiReservationTimer<=0 then
            local old = swarm.aiTargetCellId
            local cell=context.cells[old]
            local finishing=cell and cell.exposure>=world.config.autonomy.completionExposure
                and (cell.x-swarm.x)^2+(cell.y-swarm.y)^2<=(cell.radius+swarm.radius+world.config.infectionReach)^2
                and world:_DirectPathClear(swarm.x,swarm.y,cell.x,cell.y,0)
            if finishing then swarm._aiReservationTimer=world.config.autonomy.reservationTimeout
            else
                context.reservations[old] = math.max(0,(context.reservations[old] or 0)-1)
                swarm.aiTargetCellId = nil
                swarm._aiThinkClock,swarm._aiTargetHold = 0,0
            end
        end
        swarm._aiThinkClock = swarm._aiThinkClock-dt
        swarm._aiTargetHold = math.max(0,swarm._aiTargetHold-dt)
        swarm._aiWanderClock = math.max(0,swarm._aiWanderClock-dt)
        if swarm._aiThinkClock <= 1e-9 then
            thinkSwarm(world,swarm,context,visibleThreats(world,swarm))
            swarm._aiThinkClock = math.max(0.01,world.config.autonomy.thinkInterval)
        end
        if swarm.aiTargetCellId then
            local owners = world.brainReservations[swarm.aiTargetCellId] or {}
            world.brainReservations[swarm.aiTargetCellId] = owners
            owners[swarm.id] = true
        end
    end
end

---@param world SwarmWorld
function SplitVirusAI.CleanTargets(world)
    ---@type table<number, boolean>
    local valid = {}
    for _, cell in ipairs(world.cells) do
        if cell.state=="HEALTHY" or cell.state=="EXPOSED" then valid[cell.id]=true end
    end
    for _, swarm in ipairs(world.swarms) do
        if swarm.aiTargetCellId and not valid[swarm.aiTargetCellId] then
            SplitVirusAI.ResetSwarm(world,swarm,false)
            swarm._aiThinkClock,swarm._aiTargetHold,swarm._aiWanderClock = 0,0,0
        end
    end
end

---@param world SwarmWorld
---@param swarm SwarmRecord
---@param speed number
---@param dt number
---@return number, number
function SplitVirusAI.DesiredVelocity(world,swarm,speed,dt)
    if not SplitVirusAI.IsAutonomous(world,swarm) then return 0,0 end
    local cfg = world.config.autonomy
    if swarm.aiState=="flee" then
        return swarm._aiDirectionX*speed*cfg.fleeSpeedMultiplier,swarm._aiDirectionY*speed*cfg.fleeSpeedMultiplier
    end
    local dx,dy = swarm._aiMoveX-swarm.x,swarm._aiMoveY-swarm.y
    local d = math.sqrt(dx*dx+dy*dy)
    local velocity = math.min(speed*cfg.speedMultiplier,d/math.max(dt,0.000001))
    return dx/math.max(d,0.000001)*velocity,dy/math.max(d,0.000001)*velocity
end

return SplitVirusAI
