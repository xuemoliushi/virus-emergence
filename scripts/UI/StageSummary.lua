-- Stage-triggered summary: five readable seconds, then ease back beyond the right edge.
---@class StageSummary
---@field widget Widget
---@field tab Widget
local Summary={}
Summary.__index=Summary

---@param widget Widget
---@param tab Widget
---@return StageSummary
function Summary.New(widget,tab)
    local self=setmetatable({},Summary)
    self:init(widget,tab)
    return self
end

function Summary:init(widget,tab)
    self.widget,self.tab=widget,tab
    self.width=336
    self:Reset()
end

function Summary:Reset()
    self.seenStage=0
    self.value,self.from,self.target,self.elapsed,self.remaining=0,0,0,0,0
    self.widget:SetVisible(false)
    self.widget:SetStyle{translateX=self.width+16,pointerEvents="none"}
    self.tab:SetVisible(false)
end

function Summary:Move(open)
    local target=open and 1 or 0
    if target==self.target then return end
    self.from,self.target,self.elapsed=self.value,target,0
    self.widget:SetVisible(true)
    self.widget:SetStyle{pointerEvents=open and "box-none" or "none"}
    if target==self.value then self.widget:SetVisible(open) end
end

function Summary:Reveal()
    self.remaining=5
    self:Move(true)
end

---@param dt number
---@param stage number
---@param active boolean Reading time stops during tutorial, pause, cards and ending.
---@param pinned boolean Keep an explicitly opened details drawer available to read.
function Summary:Update(dt,stage,active,pinned)
    if active and stage>0 and stage~=self.seenStage then
        self.seenStage=stage
        self:Reveal()
    end
    if self.value~=self.target then
        self.elapsed=self.elapsed+math.max(0,dt)
        local t=math.min(1,self.elapsed/0.32)
        self.value=self.from+(self.target-self.from)*t*t*(3-2*t)
        if t==1 then self.value=self.target end
        self.widget:SetStyle{translateX=(1-self.value)*(self.width+16)}
        if self.value==0 then self.widget:SetVisible(false) end
    elseif active and not pinned and self.target==1 then
        self.remaining=math.max(0,self.remaining-math.max(0,dt))
        if self.remaining==0 then self:Move(false) end
    end
    self.tab:SetVisible(self.seenStage>0 and self.value==0)
end

return Summary
