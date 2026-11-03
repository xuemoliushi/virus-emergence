-- Reversible ease-in/out motion, driven by real frame time (also while paused).
---@class DisclosureMotion
---@field widget Widget
---@field height number?
local Motion = {}
Motion.__index = Motion

---@param widget Widget
---@param height number?
---@return DisclosureMotion
function Motion.New(widget, height)
    local self = setmetatable({}, Motion)
    self:init(widget,height)
    return self
end

function Motion:init(widget,height)
    self.widget, self.height = widget, height
    self.value, self.from, self.target, self.elapsed = 0, 0, 0, 0
    self.duration = 0.28
    self:Reset()
end

function Motion:Reset()
    self.value, self.from, self.target, self.elapsed = 0, 0, 0, 0
    self.widget:SetVisible(false)
    self.widget:SetStyle {opacity=0, translateY=10, pointerEvents="none"}
    if self.height then self.widget:SetStyle {height=0} end
end

function Motion:SetOpen(open)
    local target = open and 1 or 0
    if self.target == target then return end
    self.from, self.target, self.elapsed = self.value, target, 0
    self.widget:SetVisible(true)
    self.widget:SetStyle {pointerEvents=open and "auto" or "none"}
    -- An open/close pair within one frame has no distance left to animate.
    if target==self.value then self.widget:SetVisible(open) end
end

function Motion:Toggle() self:SetOpen(self.target==0) end

function Motion:Update(dt)
    if self.value == self.target then return end
    self.elapsed = self.elapsed + math.max(0, dt)
    local t = math.min(1, self.elapsed / self.duration)
    -- Cubic smoothstep: zero velocity at both ends, no overshoot.
    local eased = t*t*(3-2*t)
    self.value = self.from + (self.target-self.from)*eased
    local style = {opacity=self.value, translateY=(1-self.value)*10}
    if self.height then style.height=self.height*self.value end
    self.widget:SetStyle(style)
    if t==1 then
        self.value=self.target
        if self.target==0 then self.widget:SetVisible(false) end
    end
end

return Motion
