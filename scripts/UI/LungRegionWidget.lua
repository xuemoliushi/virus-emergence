-- 不规则肺部选区控件；继承现有UI.Widget，不另建NanoVG帧或字体。
local UI = require("urhox-libs/UI")
local Masks = require("Game.Views.LungRegionMasks")

---@class LungRegionWidget : Widget
---@field regionType_ string
---@field color_ RGBAColor
---@field selected_ boolean
---@overload fun(props:table): LungRegionWidget
local LungRegionWidget = UI.Widget:Extend("LungRegionWidget")

function LungRegionWidget:Init(props)
    local regionType, color = props.regionType, props.regionColor
    props.regionType, props.regionColor = nil, nil
    UI.Widget.Init(self, props)
    self.regionType_, self.color_, self.selected_, self.hovered_ = regionType, color, false, false
end

---@param visible boolean
---@return Widget
function LungRegionWidget:SetVisible(visible)
    if not visible then self.hovered_ = false end
    return UI.Widget.SetVisible(self, visible)
end

---@param value boolean
function LungRegionWidget:SetSelected(value)
    self.selected_ = value
end

---@param x number
---@param y number
---@return boolean
function LungRegionWidget:HitTest(x, y)
    local rect = self:GetAbsoluteLayoutForHitTest() --[[@as {x:number,y:number,w:number,h:number}]]
    return Masks.Contains(self.regionType_, rect, x, y)
end

---@param event PointerEvent
function LungRegionWidget:OnPointerEnter(event)
    self.hovered_ = event.pointerType == "mouse"
    UI.Widget.OnPointerEnter(self, event)
end

---@param event PointerEvent
function LungRegionWidget:OnPointerLeave(event)
    self.hovered_ = false
    UI.Widget.OnPointerLeave(self, event)
end

---@param nvg NVGContextWrapper
function LungRegionWidget:Render(nvg)
    local rect = self:GetAbsoluteLayout() --[[@as {x:number,y:number,w:number,h:number}]]
    Masks.Draw(nvg, self.regionType_, rect, self.color_, self.selected_, self.hovered_)
end

return LungRegionWidget
