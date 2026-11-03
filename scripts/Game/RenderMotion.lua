-- Presentation poses only. No extrapolation, RNG, events or entity writes.
local Config=require("Core.Config")
---@class RenderMotion
---@field previous table<table,{x:number,y:number,state:string?,swarmId:number?,hidden:boolean?}>
---@field alpha number
local Motion={}
Motion.__index=Motion

---@return RenderMotion
function Motion.New()
    local self=setmetatable({},Motion)
    self:Reset()
    return self
end

function Motion:Reset()
    -- Removed entities are not retained across deaths, absorption or a restart.
    self.previous=setmetatable({},{__mode="k"})
    self.alpha=1
end

---@param world SwarmWorld
function Motion:Capture(world)
    for _,list in ipairs({world.swarms,world.viruses,world.releasedViruses,world.immunes}) do
        for _,entity in ipairs(list) do
            local pose=self.previous[entity]
            if not pose then pose={x=entity.x,y=entity.y};self.previous[entity]=pose end
            pose.x,pose.y=entity.x,entity.y
            pose.state,pose.swarmId,pose.hidden=entity.state,entity.swarmId,entity.isHidden
        end
    end
end

---@param entity table
---@return number x
---@return number y
function Motion:Position(entity)
    local pose=self.previous[entity]
    if not pose or self.alpha>=1 or pose.state~=entity.state
        or pose.swarmId~=entity.swarmId or pose.hidden~=entity.isHidden then return entity.x,entity.y end
    local dx,dy=entity.x-pose.x,entity.y-pose.y
    local snap=Config.Performance.renderSnapDistance
    if dx*dx+dy*dy>snap*snap then return entity.x,entity.y end
    return pose.x+dx*self.alpha,pose.y+dy*self.alpha
end

return Motion
