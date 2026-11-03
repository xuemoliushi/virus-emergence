-- ObservationState.lua - 小鼠外观、解剖叠肺与肺部放大的表现状态。
-- 与病程计时分离；只影响观察和开局选择，不写感染/炎症/病毒数据。
local EventBus = require("Core.EventBus")

---@class ObservationState
---@field mode string
---@field lungProgress number
---@field visualTime number
---@field selectedStartType string?
local ObservationState = {}
ObservationState.__index = ObservationState

---@return ObservationState
function ObservationState.New()
    local self = setmetatable({}, ObservationState)
    self:init()
    return self
end

function ObservationState:init()
    self.mode, self.lungProgress, self.visualTime = "body", 0, 0
    self.selectedStartType = nil
end

function ObservationState:Notify()
    EventBus.Emit("observation:changed", { mode = self.mode })
end

function ObservationState:Reset()
    self:init()
    self:Notify()
end

function ObservationState:ShowAnatomy()
    self.mode = "anatomy"
    self.selectedStartType = nil
    self:Notify()
end

function ObservationState:ShowBody()
    self.mode = "body"
    self.selectedStartType = nil
    self:Notify()
end

---@return boolean
function ObservationState:OpenLung()
    if self.mode ~= "anatomy" or self.lungProgress > 0.01 then return false end
    self.mode = "lung"
    self:Notify()
    return true
end

function ObservationState:Back()
    if self.mode == "lung" then self:ShowAnatomy() else self:ShowBody() end
end

---@param regionType string
---@return boolean
function ObservationState:SelectRegion(regionType)
    if self.mode ~= "lung" or self:IsTransitioning() then return false end
    if regionType ~= "UPPER_AIRWAY" and regionType ~= "TRACHEA" and regionType ~= "DEEP_LUNG" then return false end
    self.selectedStartType = regionType
    self:Notify()
    return true
end

---@return boolean
function ObservationState:IsTransitioning()
    if self.mode == "lung" then return self.lungProgress < 1 end
    return self.lungProgress > 0
end

---@param dt number
function ObservationState:Update(dt)
    local step = math.max(0, math.min(dt, 0.25))
    self.visualTime = self.visualTime + step
    local target = self.mode == "lung" and 1 or 0
    local amount = step / 0.65
    if target > self.lungProgress then self.lungProgress = math.min(target, self.lungProgress + amount)
    else self.lungProgress = math.max(target, self.lungProgress - amount) end
end

return ObservationState
