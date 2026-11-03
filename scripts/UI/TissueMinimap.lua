-- UI owns the frame/DPR/font lifecycle. Only simple paths, never cell textures.
local UI = require("urhox-libs/UI")
local Minimap = UI.Widget:Extend("TissueMinimap")

function Minimap:Init(props)
    self.sim=props.sim
    props.sim=nil
    props.pointerEvents="none"
    UI.Widget.Init(self,props)
end

function Minimap:Render(nvg)
    local world=self.sim.world
    if not self.sim.started or not world then return end
    local rect=self:GetAbsoluteLayout()
    if rect.w<=0 or rect.h<=0 then return end
    local scale=math.min((rect.w-8)/world.width,(rect.h-8)/world.height)
    if scale<=0 then return end
    local ox=rect.x+(rect.w-world.width*scale)*.5
    local oy=rect.y+(rect.h-world.height*scale)*.5
    nvgSave(nvg)
    nvgIntersectScissor(nvg,rect.x,rect.y,rect.w,rect.h)
    nvgBeginPath(nvg);nvgRect(nvg,ox,oy,world.width*scale,world.height*scale)
    nvgFillColor(nvg,nvgRGBA(8,6,16,240));nvgFill(nvg)
    nvgStrokeColor(nvg,nvgRGBA(100,95,140,180));nvgStrokeWidth(nvg,1);nvgStroke(nvg)
    if world.map.isFlatMap then
        require('Game.FlatMapVisual').Floor(nvg,world.map,scale,ox,oy,0,0,world.width,world.height)
        -- Statistics partitions are small landmarks, not fictitious ellipse rooms.
        for _,r in ipairs(world.map.regions) do
            nvgBeginPath(nvg);nvgCircle(nvg,ox+r.x*scale,oy+r.y*scale,1.5)
            nvgFillColor(nvg,nvgRGBA(130,90,150,180));nvgFill(nvg)
        end
    else
    for _,ch in ipairs(world.map.channels) do
        nvgBeginPath(nvg)
        for i,p in ipairs(ch.points) do
            if i==1 then nvgMoveTo(nvg,ox+p.x*scale,oy+p.y*scale)
            else nvgLineTo(nvg,ox+p.x*scale,oy+p.y*scale) end
        end
        nvgStrokeWidth(nvg,math.max(1,ch.width*scale))
        nvgStrokeColor(nvg,nvgRGBA(48,100,125,145));nvgStroke(nvg)
    end
    for _,r in ipairs(world.map.regions) do
        nvgBeginPath(nvg);nvgEllipse(nvg,ox+r.x*scale,oy+r.y*scale,r.rx*scale,r.ry*scale)
        nvgFillColor(nvg,nvgRGBA(70+r.id*8,35,85,210));nvgFill(nvg)
    end
    end
    -- Camera rectangle comes from the same transform that inverses pointer input.
    local root=UI.GetRoot()
    local scene=root and root:FindById("gameScene") --[[@as GameScene?]]
    local view=scene and scene.cellView.worldView
    if view then
        local x,y=math.max(0,view.x),math.max(0,view.y)
        local right,bottom=math.min(world.width,view.x+view.w),math.min(world.height,view.y+view.h)
        nvgBeginPath(nvg);nvgRect(nvg,ox+x*scale,oy+y*scale,math.max(0,right-x)*scale,math.max(0,bottom-y)*scale)
        nvgStrokeWidth(nvg,1);nvgStrokeColor(nvg,nvgRGBA(220,230,240,200));nvgStroke(nvg)
    end
    for _,swarm in ipairs(world.swarms) do
        local x,y=swarm.x,swarm.y
        if scene then x,y=scene.renderMotion:Position(swarm) end
        local selected=swarm.id==world.currentControlledSwarmId
        nvgBeginPath(nvg);nvgCircle(nvg,ox+x*scale,oy+y*scale,selected and 3 or 2)
        nvgFillColor(nvg,selected and nvgRGBA(255,210,95,255) or nvgRGBA(245,135,70,255));nvgFill(nvg)
        if selected then nvgStrokeColor(nvg,nvgRGBA(255,255,255,230));nvgStrokeWidth(nvg,1);nvgStroke(nvg) end
    end
    local selection=self.sim.skillSelection
    local target=selection and selection.target
    if target and target.x and target.y then
        nvgBeginPath(nvg);nvgCircle(nvg,ox+target.x*scale,oy+target.y*scale,3)
        nvgStrokeColor(nvg,nvgRGBA(90,210,230,220));nvgStrokeWidth(nvg,1);nvgStroke(nvg)
    end
    nvgRestore(nvg)
end

return Minimap
