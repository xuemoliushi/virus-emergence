-- 已被权威感染分支接受的接触，统一提交为纯视觉快照。
-- 不读取或写入感染进度、细胞状态/位置；没有额外感染判定。
local Contacts = {}
local TAU = math.pi * 2
local EPSILON = 0.02 -- 米；穿过中心附近时保留历史方向，避免归一化放大噪声。
local DEAD_BAND = math.rad(12)
local CANDIDATE_TOLERANCE = math.rad(3)
local CANDIDATE_FRAMES = 3
local MAX_TURN = math.rad(0.25) -- 每步至多一个细分姿态，避免跨多个真实膜边界点。
local FADE_SECONDS = 0.75

local function finite(value)
    return type(value) == "number" and value == value and math.abs(value) < math.huge
end

local function delta(a, b) return (a - b + math.pi) % TAU - math.pi end

local function stronger(a, b)
    if a.strength ~= b.strength then return a.strength > b.strength end
    if a.distance ~= b.distance then return a.distance < b.distance end
    if a.sourceType ~= b.sourceType then return a.sourceType < b.sourceType end
    return a.sourceId < b.sourceId
end

---@param cell RespiratoryCell
---@param source SwarmRecord|ReleasedVirusRecord
---@param sourceType CellContactSourceType
---@param power number
---@param accepted table<string,table>
function Contacts.Collect(cell, source, sourceType, power, accepted)
    if not finite(power) or power <= 0 then return end
    if not finite(source.x) or not finite(source.y) then return end
    local dx, dy = source.x - cell.x, source.y - cell.y
    local distance = math.sqrt(dx * dx + dy * dy)
    local key = cell.id .. ":" .. sourceType .. ":" .. source.id
    local candidate = { key = key, cellId = cell.id, sourceType = sourceType, sourceId = source.id,
        sourceX = source.x, sourceY = source.y, sourceRadius = source.radius,
        strength = power, distance = distance, dx = dx, dy = dy }
    -- 同步周期中同一来源只有一份候选，重复收集不叠加视觉贡献。
    local previous = accepted[key]
    if not previous or stronger(candidate, previous) then accepted[key] = candidate end
end

local function advance(record, candidate, cell, now)
    local rotation = cell.rotation or 0
    local valid = candidate.distance >= EPSILON
    local localAngle
    if valid then
        localAngle = math.atan(candidate.dy, candidate.dx) - rotation
    elseif not record then
        return nil -- 没有历史有效方向，速度也不替代实际接触侧。
    end
    if not record then
        record = { key = candidate.key, cellId = cell.id, sourceType = candidate.sourceType,
            sourceId = candidate.sourceId, firstSeen = now, stableLocalAngle = localAngle,
            targetLocalAngle = localAngle, candidateFrames = 0, candidateLocalAngle = nil }
    end
    -- Capture each entry before applying diagnostic direction smoothing.
    if not record.active then
        record.contactSequence = (record.contactSequence or 0) + 1
        record.enteredAt = now
        record.entryLocalAngle = (localAngle or record.entryLocalAngle or record.stableLocalAngle) % TAU
    end
    if valid then
        record.rawNormalX, record.rawNormalY = candidate.dx / candidate.distance, candidate.dy / candidate.distance
        record.lastValidDirectionX, record.lastValidDirectionY = record.rawNormalX, record.rawNormalY
        local change = math.abs(delta(localAngle, record.targetLocalAngle))
        if change > DEAD_BAND then
            if record.candidateLocalAngle
                and math.abs(delta(localAngle, record.candidateLocalAngle)) <= CANDIDATE_TOLERANCE then
                record.candidateFrames = record.candidateFrames + 1
            else
                record.candidateFrames, record.candidateLocalAngle = 1, localAngle
            end
            if record.candidateFrames >= CANDIDATE_FRAMES then
                record.targetLocalAngle = localAngle
                record.candidateFrames, record.candidateLocalAngle = 0, nil
            end
        else
            record.candidateFrames, record.candidateLocalAngle = 0, nil
        end
    else
        record.rawNormalX, record.rawNormalY = nil, nil
        record.candidateFrames, record.candidateLocalAngle = 0, nil
        record.targetLocalAngle = record.stableLocalAngle -- 中心附近停在上一有效显示方向。
    end
    local turn = delta(record.targetLocalAngle, record.stableLocalAngle)
    record.stableLocalAngle = (record.stableLocalAngle + math.max(-MAX_TURN, math.min(MAX_TURN, turn))) % TAU
    local worldAngle = record.stableLocalAngle + rotation
    record.normalX, record.normalY = math.cos(worldAngle), math.sin(worldAngle)
    record.stableDirectionX, record.stableDirectionY = record.normalX, record.normalY
    record.stableAngle, record.visualCellRotation = record.stableLocalAngle, rotation
    record.sourceX, record.sourceY, record.sourceRadius = candidate.sourceX, candidate.sourceY, candidate.sourceRadius
    record.distance, record.strength, record.lastSeen = candidate.distance, candidate.strength, now
    record.worldContactX, record.worldContactY = cell.x + record.normalX * cell.radius, cell.y + record.normalY * cell.radius
    record.rawContactX = valid and (cell.x + candidate.dx / candidate.distance * cell.radius) or nil
    record.rawContactY = valid and (cell.y + candidate.dy / candidate.distance * cell.radius) or nil
    record.fade, record.active, record.lostTime, record._accepted = 1, true, 0, true
    return record
end

---@param cell RespiratoryCell
---@param accepted table<string,table>
---@param now number
function Contacts.Commit(cell, accepted, now)
    local records = cell.contactVisuals
    local anchor = cell.contactVisualAnchor
    if #records==0 and not anchor and not next(accepted) then return end
    local existing = {}
    for _, record in ipairs(records) do
        record._accepted = false
        existing[record.key or (cell.id .. ":" .. record.sourceType .. ":" .. record.sourceId)] = record
    end
    if anchor then
        anchor._accepted = false
        existing[anchor.key or (cell.id .. ":" .. anchor.sourceType .. ":" .. anchor.sourceId)] = anchor
    end
    -- All accepted sources have already contributed to infection. Presentation
    -- retains at most three slots plus its historical anchor: update those
    -- incumbents and only the three strongest valid new arrivals. Advancing
    -- thousands of discarded records/sorting the whole crowd cannot change
    -- which slots or anchor survive, but costs many trig calls and allocations.
    local candidates,newcomers = {},{}
    for _, candidate in pairs(accepted) do
        if existing[candidate.key] then candidates[#candidates+1]=candidate
        elseif candidate.distance>=EPSILON then
            local index=#newcomers+1
            for i,previous in ipairs(newcomers) do
                if stronger(candidate,previous) then index=i;break end
            end
            if index<=3 then
                table.insert(newcomers,index,candidate)
                newcomers[4]=nil
            end
        end
    end
    for _,candidate in ipairs(newcomers) do candidates[#candidates+1]=candidate end
    table.sort(candidates, stronger)
    local acceptedRecords, strongest = {}, nil
    for _, candidate in ipairs(candidates) do
        local record = advance(existing[candidate.key], candidate, cell, now)
        if record then
            acceptedRecords[#acceptedRecords + 1] = record
            if not strongest then strongest = record end
        end
    end
    for index = #records, 1, -1 do
        local record = records[index]
        if not record._accepted then
            record.lostTime = math.max(0, now - record.lastSeen)
            record.active = false
            record.fade = math.max(0, 1 - record.lostTime / FADE_SECONDS)
            if record.fade <= 0 then table.remove(records, index) end
        end
    end
    for _, record in ipairs(acceptedRecords) do
        local present = false
        for _, previous in ipairs(records) do if previous == record then present = true; break end end
        if not present then
            if #records < 3 then records[#records + 1] = record
            else
                local oldest
                for index, previous in ipairs(records) do
                    if not previous._accepted and (not oldest or previous.lastSeen < records[oldest].lastSeen
                        or (previous.lastSeen == records[oldest].lastSeen and previous.key < records[oldest].key)) then
                        oldest = index
                    end
                end
                if oldest then records[oldest] = record end
            end
        end
    end
    if anchor and not anchor._accepted then
        anchor.active = false
        anchor.lostTime = math.max(0, now - anchor.lastSeen)
        anchor.fade = math.max(0, 1 - anchor.lostTime / FADE_SECONDS)
    end
    -- 仍接受的原锚点优先；失去该来源后才选择排序后的最强真实来源。
    if not anchor or not anchor._accepted then
        if strongest then cell.contactVisualAnchor = strongest end
    end
end

---@param world SwarmWorld
---@param inputs table<number,table<string,table>>
function Contacts.CommitWorld(world, inputs)
    for _, cell in ipairs(world.cells) do Contacts.Commit(cell, inputs[cell.id] or {}, world.time) end
end

Contacts.Settings = { epsilon = EPSILON, deadBand = DEAD_BAND, candidateFrames = CANDIDATE_FRAMES,
    candidateTolerance = CANDIDATE_TOLERANCE, maxTurn = MAX_TURN, fadeSeconds = FADE_SECONDS }
return Contacts
