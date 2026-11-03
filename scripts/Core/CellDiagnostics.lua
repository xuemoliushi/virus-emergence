-- 可选真实模拟追踪：默认关闭，状态/位置仅只读，不向业务事件队列写调试事件。
local Debug = {}
local sessions = setmetatable({}, { __mode = "k" })

---@param world SwarmWorld
---@param options table? nil关闭；sink接收结构化行，frames限制连续帧数量
function Debug.Configure(world, options)
    if not options then sessions[world] = nil; return end
    sessions[world] = { options = options, frame = 0, before = {}, accepted = {}, rows = {} }
end

function Debug.IsEnabled(world) return sessions[world] ~= nil end

local function selected(options, cell)
    return not options.cellId or options.cellId == cell.id
end

---@param world SwarmWorld
---@param dt number
function Debug.BeginStep(world, dt)
    local session = sessions[world]
    if not session then return end
    session.frame = session.frame + 1
    session.dt = dt
    session.before, session.accepted = {}, {}
    for _, cell in ipairs(world.cells) do
        if selected(session.options, cell) then
            session.before[cell.id] = { exposure = cell.exposure, charge = cell._charge,
                state = cell.state, x = cell.x, y = cell.y, rotation = cell.rotation }
        end
    end
end

---@param world SwarmWorld
---@param cell RespiratoryCell
---@param accepted table<string,table>
function Debug.Accepted(world, cell, accepted)
    local session = sessions[world]
    if not session or not selected(session.options, cell) then return end
    session.accepted[cell.id] = accepted
end

local function emit(session, row)
    if session.options.sink then session.options.sink(row)
    elseif cjson then print("[CellTrace] " .. cjson.encode(row))
    else
        print(string.format("[CellTrace] frame=%d cellId=%d sourceType=%s sourceId=%d accepted=%s delta=%.9f exposure=%.6f state=%s",
            row.frame, row.cellId, row.sourceType, row.sourceId, tostring(row.acceptedContact),
            row.deltaExposure, row.exposure, row.stateAfterUpdate))
    end
end

---@param world SwarmWorld
function Debug.EndStep(world)
    local session = sessions[world]
    if not session then return end
    local options = session.options
    for _, cell in ipairs(world.cells) do
        local old = session.before[cell.id]
        if old then
            local inputs = session.accepted[cell.id] or {}
            -- 与权威结算一致：群体贡献不封顶，仅 Released 的总贡献封顶。
            -- 仅用于日志，不将诊断值写回感染模拟。
            local groupPower, releasedPower = 0, 0
            for _, input in pairs(inputs) do
                if input.sourceType == "RELEASED_VIRUS" then
                    releasedPower = releasedPower + input.strength
                else
                    groupPower = groupPower + input.strength
                end
            end
            local totalPower = groupPower + math.min(3, releasedPower)
            local acceptedDelta = 0
            if old.state == "HEALTHY" or old.state == "EXPOSED" then
                acceptedDelta = totalPower > 0 and session.dt * totalPower / world.config.infectionSeconds
                    or -session.dt * world.config.exposureDecay
            end
            local choices = {}
            for _, input in pairs(inputs) do choices[#choices + 1] = input end
            table.sort(choices, function(a, b) return a.key < b.key end)
            if #choices == 0 then
                local anchor = cell.contactVisualAnchor
                choices[1] = { sourceType = options.sourceType or (anchor and anchor.sourceType) or "NONE",
                    sourceId = options.sourceId or (anchor and anchor.sourceId) or 0,
                    sourceX = anchor and anchor.sourceX, sourceY = anchor and anchor.sourceY }
            end
            for _, input in ipairs(choices) do
                if (not options.sourceType or options.sourceType == input.sourceType)
                    and (not options.sourceId or options.sourceId == input.sourceId) then
                    local record
                    for _, contact in ipairs(cell.contactVisuals) do
                        if contact.sourceType == input.sourceType and contact.sourceId == input.sourceId then record = contact; break end
                    end
                    local row = { frame = session.frame, time = world.time, cellId = cell.id,
                        sourceType = input.sourceType, sourceId = input.sourceId,
                        cellPosition = { cell.x, cell.y }, sourcePosition = { input.sourceX, input.sourceY },
                        acceptedContact = input.strength ~= nil and input.strength > 0,
                        acceptedPower = input.strength or 0,
                        deltaExposure = cell.exposure - old.exposure, deltaAccruedCharge = acceptedDelta,
                        pendingCharge = cell._charge, exposure = cell.exposure,
                        infectionProgress = cell.exposure, progressField = "exposure",
                        oldState = old.state, newState = cell.state, stateAfterUpdate = cell.state,
                        cellRotation = cell.rotation }
                    if input.distance and input.distance >= 0.02 then
                        row.rawDirection = { input.dx / input.distance, input.dy / input.distance }
                        row.rawContactPosition = { cell.x + row.rawDirection[1] * cell.radius,
                            cell.y + row.rawDirection[2] * cell.radius }
                    end
                    if record then
                        row.stableDirection = { record.normalX, record.normalY }
                        row.stableContactPosition = { record.worldContactX, record.worldContactY }
                        row.stableAngle = record.stableAngle
                        row.key = record.key
                    end
                    if session.frame <= (options.frames or 120) then emit(session, row) end
                end
            end
            if old.state ~= cell.state then
                local source = choices[1]
                print(string.format("[CellState] frame=%d cellId=%d oldState=%s newState=%s progress=%.6f sourceType=%s sourceId=%d",
                    session.frame, cell.id, old.state, cell.state, cell.exposure, source.sourceType, source.sourceId))
            end
        end
    end
end

---@param world SwarmWorld
---@param cell RespiratoryCell
---@param x number
---@param y number
---@param scale number 每细胞源像素的屏幕长度
---@param pose CellSurfacePose? 仅传入本帧实际绘出的附着姿态
---@param drawnContact CellContactVisual? 多来源时记录实际绘制来源，不默认假定锚点被画出
function Debug.Draw(world, cell, x, y, scale, pose, drawnContact)
    local session = sessions[world]
    if not session or not session.options.drawSink or not selected(session.options, cell) then return end
    local rotation = cell.rotation or 0
    local co, si = math.cos(rotation), math.sin(rotation)
    local row = { frame = session.frame, cellId = cell.id, state = cell.state, progress = cell.exposure,
        cellPosition = { cell.x, cell.y }, cellRotation = rotation, drawCellPosition = { x, y },
        drawn = pose ~= nil }
    local contact = drawnContact or cell.contactVisualAnchor
    if contact then
        row.sourceType, row.sourceId, row.key = contact.sourceType, contact.sourceId, contact.key
        row.sourcePosition = { contact.sourceX, contact.sourceY }
        row.rawContactPosition = { contact.rawContactX, contact.rawContactY }
        row.rawDirection = { contact.rawNormalX, contact.rawNormalY }
        row.stableContactPosition = { contact.worldContactX, contact.worldContactY }
        row.stableDirection = { contact.normalX, contact.normalY }
        row.stableAngle = contact.stableAngle
    end
    if pose then
        row.drawPosition = { x + scale * (co * pose.spriteX - si * pose.spriteY),
            y + scale * (si * pose.spriteX + co * pose.spriteY) }
        row.drawAngle = pose.rotation + rotation
        row.drawContactPosition = { x + scale * (co * pose.x - si * pose.y),
            y + scale * (si * pose.x + co * pose.y) }
    end
    session.options.drawSink(row)
end
return Debug
