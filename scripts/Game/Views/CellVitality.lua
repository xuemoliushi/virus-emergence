-- Bounded presentation-only drift and breathing. Collision shapes and gameplay
-- coordinates stay unchanged. Shared waves avoid per-entity per-frame trig/RNG.
---@class CellVitality
local Vitality = {}
Vitality.__index = Vitality

function Vitality.New()
    return setmetatable({poses={},time=0,serial=0},Vitality)
end

function Vitality:Reset()
    self.poses={}
    self.time,self.serial=0,0
end

function Vitality:Get(entity)
    return self.poses[entity]
end

local function visible(entity,view)
    return not view or (entity.x>=view.x-2 and entity.x<=view.x+view.w+2
        and entity.y>=view.y-2 and entity.y<=view.y+view.h+2)
end

function Vitality:Update(world,dt,active,view)
    if not world then return end
    if active and dt==dt and dt>0 and dt<math.huge then
        self.time=self.time+math.min(dt,1/15)
    end
    local t=self.time
    -- Broad, slow arcs (29 s), with a weaker 48 s variation. Quadrature axes
    -- carry the cell along a curve instead of independently shuttling in X/Y.
    local a,b=math.sin(t*.22),math.cos(t*.22)
    local c,d=math.sin(t*.13),math.cos(t*.13)
    local e,f=math.sin(t*.90),math.cos(t*.90)
    self.serial=self.serial+1
    local function update(items,immune)
        for _,entity in ipairs(items or {}) do
            if visible(entity,view) then
                local pose=self.poses[entity]
                if not pose then
                    local phase=(entity.phase or (entity.id or 1)*2.399963)+(immune and 1.17 or 0)
                    pose={dx=0,dy=0,sx=1,sy=1,
                        a=math.sin(phase),b=math.cos(phase),
                        c=math.sin(phase*1.731+2.1),d=math.cos(phase*1.731+2.1)}
                    self.poses[entity]=pose
                end
                pose.seen=self.serial
                -- A dead membrane keeps its last pose through its existing fade.
                if entity.state~="DEAD" then
                    local breath=e*pose.a+f*pose.b
                    local swell=(c*pose.c+d*pose.d)*.003
                    pose.sx=1+breath*.014+swell
                    pose.sy=1-breath*.010+swell
                    if not immune then
                        local radius=entity.radius or .4
                        local arcX=a*pose.a+b*pose.b
                        local arcY=b*pose.a-a*pose.b
                        local bendX=c*pose.c+d*pose.d
                        local bendY=d*pose.c-c*pose.d
                        pose.dx=(arcX*.85+bendX*.15)*radius*.075
                        pose.dy=(arcY*.85+bendY*.15)*radius*.060
                    end
                end
            end
        end
    end
    update(world.cells,false)
    update(world.immunes,true)
    for entity,pose in pairs(self.poses) do
        if pose.seen~=self.serial then self.poses[entity]=nil end
    end
end

return Vitality
