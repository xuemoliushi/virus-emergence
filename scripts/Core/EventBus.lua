-- ============================================================================
-- EventBus.lua - 轻量事件总线（模块间解耦通信）
-- 用法:
--   local token = EventBus.On("sim:ending", function(payload) ... end)
--   EventBus.Emit("sim:ending", { outcome = "recovery" })
--   EventBus.Off(token)
-- ============================================================================

---@class EventBusModule
local EventBus = {}

---@type table<string, table<integer, fun(payload:any)>>
local handlers_ = {}
local nextId_ = 1

--- 订阅事件
---@param event string
---@param fn fun(payload:any)
---@return table token 传给 Off 取消订阅
function EventBus.On(event, fn)
    if not handlers_[event] then handlers_[event] = {} end
    local id = nextId_
    nextId_ = nextId_ + 1
    handlers_[event][id] = fn
    return { event = event, id = id }
end

--- 取消订阅
---@param token table On() 返回的令牌
function EventBus.Off(token)
    if token and handlers_[token.event] then
        handlers_[token.event][token.id] = nil
    end
end

--- 发射事件
---@param event string
---@param payload any
function EventBus.Emit(event, payload)
    local list = handlers_[event]
    if not list then return end
    for _, fn in pairs(list) do
        local ok, err = pcall(fn, payload)
        if not ok then
            print("[EventBus] handler error for '" .. event .. "': " .. tostring(err))
        end
    end
end

-- ============================================================================
-- 事件名常量（集中登记，避免散落字符串）
-- ============================================================================
EventBus.Events = {
    AUDIO_WORLD     = "audio:world_events", -- {runId,events}: immutable scalar snapshots
    AUDIO_DENIED    = "audio:action_denied", -- explicit rejected player intent only
    SIM_TICK        = "sim:tick",        -- payload: { time }
    SIM_STRATEGY    = "sim:strategy",    -- payload: { strategyId, regionIndex }
    SIM_ENDING      = "sim:ending",      -- payload: { outcome="extinct", summary }
    SCALE_CHANGED   = "scale:changed",   -- payload: { scale, prevScale }
    REGION_SELECTED = "region:selected", -- payload: { regionIndex }
    PHASE_CHANGED   = "sim:phase",       -- payload: { phase }（潜伏/急性/恢复窗口）
    MUTATION        = "sim:mutation",    -- payload: { mutationId, count }
    SIM_RESET       = "sim:reset",       -- 重开一局（表现层清缓存/重建）
}

return EventBus
