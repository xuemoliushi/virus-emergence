-- Full-map presentation for the scaffold-2d Widget pipeline. No simulation writes.
local UI = require("urhox-libs/UI")
local Skin = require("UI.AssetTheme")
local Floor = require("Game.FlatMapVisual")

---@class MapOverview
---@field world SwarmWorld?
---@field amount number
---@field target number
---@field time number
---@field seedLabel Label?
local Map = {}
Map.__index = Map

---@return MapOverview
function Map.New()
    local self = setmetatable({}, Map)
    self:Reset()
    return self
end

function Map:Reset()
    self.amount, self.target, self.time = 0, 0, 0
    self.world = nil
    self.bins, self.healthy, self.immunes = {}, {}, {}
end

function Map:IsActive() return self.target == 1 or self.amount > 0 end
function Map:Blend()
    local t = self.amount
    return t*t*(3-2*t)
end

---@param dt number
function Map:Update(dt)
    local step = math.max(0, math.min(dt, .1))
    if self:IsActive() then self.time = self.time + step end
    if self.target == 1 then self.amount = math.min(1, self.amount + step/.4)
    else self.amount = math.max(0, self.amount - step/.4) end
end

---@param world SwarmWorld
---@param meters number
---@param exploration MapExploration?
function Map:Capture(world, meters, exploration)
    self.world = world
    if self.seedLabel then self.seedLabel:SetText("地图种子 "..tostring(world.map.seed or "—")) end
    self.bins, self.healthy, self.immunes = {}, {}, {}
    local byKey = {}
    local function add(v)
        if exploration and not exploration:IsExplored(v.x,v.y) then return end
        local gx, gy = math.floor(v.x/meters), math.floor(v.y/meters)
        local key = gx..":"..gy
        local bin = byKey[key]
        if not bin then
            bin = {x=0,y=0,count=0,phase=(gx*13+gy*7)%31,samples={}}
            byKey[key] = bin
            self.bins[#self.bins+1] = bin
        end
        bin.x,bin.y,bin.count = bin.x+v.x,bin.y+v.y,bin.count+1
        if #bin.samples<5 then bin.samples[#bin.samples+1]={x=v.x,y=v.y} end
    end
    -- These are separate populations with independent IDs; never count swarm.mass again.
    for _,v in ipairs(world.viruses) do add(v) end
    for _,v in ipairs(world.releasedViruses) do
        if v.state~="CLEARED" and v.state~="LOST" and v.state~="ABSORBED" and v.state~="CONVERTED" then add(v) end
    end
    for _,bin in ipairs(self.bins) do bin.x,bin.y=bin.x/bin.count,bin.y/bin.count end
    for _,cell in ipairs(world.cells) do
        if cell.state=="HEALTHY" and (not exploration or exploration:IsExplored(cell.x,cell.y)) then
            self.healthy[#self.healthy+1]={x=cell.x,y=cell.y,phase=cell.id%23}
        end
    end
    for _,immune in ipairs(world.immunes) do
        if not exploration or exploration:IsExplored(immune.x,immune.y) then
            self.immunes[#self.immunes+1]={x=immune.x,y=immune.y,phase=immune.id%19}
        end
    end
end

---@param l Rect4
---@return Rect4
function Map:Area(l)
    local safe = UI.GetSafeAreaInsets()
    ---@type number, number
    local left,right = math.max(12,safe.left or 0),math.max(12,safe.right or 0)
    ---@type number, number
    local top,bottom = math.max(12,safe.top or 0),math.max(48,safe.bottom or 0)
    top,bottom=math.min(top,l.h*.22),math.min(bottom,l.h*.25)
    left,right=math.min(left,l.w*.12),math.min(right,l.w*.12)
    return {x=l.x+left,y=l.y+top,w=math.max(1,l.w-left-right),h=math.max(1,l.h-top-bottom)}
end

---@param l Rect4
---@param world SwarmWorld
function Map:Fit(l,world)
    local area=self:Area(l)
    return math.min(area.w/world.width,area.h/world.height)*.98,area
end

-- Logarithmic scale interpolation keeps a 20x pullback perceptually continuous.
---@param l Rect4
---@param world SwarmWorld
---@param ppm number
---@param ox number
---@param oy number
function Map:Transform(l,world,ppm,ox,oy)
    local fit,area=self:Fit(l,world)
    local blend=self:Blend()
    local ax,ay=l.x+l.w*.5,l.y+l.h*.5
    local fx,fy=(ax-ox)/ppm,(ay-oy)/ppm
    local anchorX=ax+(area.x+area.w*.5-ax)*blend
    local anchorY=ay+(area.y+area.h*.5-ay)*blend
    local scale=ppm*(fit/ppm)^blend
    return scale,anchorX-(fx+(world.width*.5-fx)*blend)*scale,
        anchorY-(fy+(world.height*.5-fy)*blend)*scale
end

local function dot(vg,x,y,r,red,green,blue,alpha)
    nvgBeginPath(vg);nvgCircle(vg,x,y,r*3)
    nvgFillPaint(vg,nvgRadialGradient(vg,x,y,r*.3,r*3,
        nvgRGBA(red,green,blue,math.floor(alpha*.45)),nvgRGBA(red,green,blue,0)))
    nvgFill(vg)
    nvgBeginPath(vg);nvgCircle(vg,x,y,r)
    nvgFillColor(vg,nvgRGBA(red,green,blue,math.floor(alpha)));nvgFill(vg)
end

---@param vg NVGContextWrapper
---@param world SwarmWorld
---@param l Rect4
---@param ppm number
---@param ox number
---@param oy number
function Map:Draw(vg,world,l,ppm,ox,oy)
    nvgSave(vg)
    nvgIntersectScissor(vg,l.x,l.y,l.w,l.h)
    nvgBeginPath(vg);nvgRect(vg,l.x,l.y,l.w,l.h)
    nvgFillColor(vg,nvgRGBA(3,3,10,255));nvgFill(vg)
    if world.map.isFlatMap then
        Floor.Floor(vg,world.map,ppm,ox,oy,0,0,world.width,world.height)
    else
        for _,r in ipairs(world.map.regions) do
            nvgBeginPath(vg);nvgEllipse(vg,ox+r.x*ppm,oy+r.y*ppm,r.rx*ppm,r.ry*ppm)
            nvgFillColor(vg,nvgRGBA(25,15,38,255));nvgFill(vg)
        end
    end
    for _,channel in ipairs(world.map.channels or {}) do
        nvgBeginPath(vg)
        for i,p in ipairs(channel.points) do
            if i==1 then nvgMoveTo(vg,ox+p.x*ppm,oy+p.y*ppm)
            else nvgLineTo(vg,ox+p.x*ppm,oy+p.y*ppm) end
        end
        nvgStrokeWidth(vg,math.max(.6,(channel.width or 1)*ppm*.15))
        nvgStrokeColor(vg,nvgRGBA(90,110,145,65));nvgStroke(vg)
    end
    nvgBeginPath(vg);nvgRect(vg,ox,oy,world.width*ppm,world.height*ppm)
    nvgStrokeWidth(vg,1);nvgStrokeColor(vg,nvgRGBA(92,87,118,160));nvgStroke(vg)
    -- Red stays quieter and smaller than the two moving populations.
    for _,p in ipairs(self.healthy) do
        dot(vg,ox+p.x*ppm,oy+p.y*ppm,1.15,255,76,88,135+25*math.sin(self.time*2+p.phase))
    end
    for _,bin in ipairs(self.bins) do
        local density=math.min(1,math.log(1+bin.count)/math.log(65))
        local pulse=.87+.13*math.sin(self.time*3+bin.phase)
        dot(vg,ox+bin.x*ppm,oy+bin.y*ppm,1.5+3.3*density,255,212,63,(155+100*density)*pulse)
        for _,p in ipairs(bin.samples) do
            nvgBeginPath(vg);nvgCircle(vg,ox+p.x*ppm,oy+p.y*ppm,1.05)
            nvgFillColor(vg,nvgRGBA(255,232,113,math.floor(220*pulse)));nvgFill(vg)
        end
    end
    for _,p in ipairs(self.immunes) do
        dot(vg,ox+p.x*ppm,oy+p.y*ppm,2.5,72,165,255,215+35*math.sin(self.time*2.5+p.phase))
    end
    nvgRestore(vg)
end

-- Draw above fog so the player's circle remains legible on very small windows.
---@param vg NVGContextWrapper
---@param world SwarmWorld
---@param ppm number
---@param ox number
---@param oy number
function Map:DrawPlayer(vg,world,ppm,ox,oy)
    local player=world:SwarmById(world.currentControlledSwarmId)
    if player and player.mass>0 then
        local radius=math.max(10,(player.radius or .2)*ppm+5)+.8*math.sin(self.time*2.4)
        nvgBeginPath(vg);nvgCircle(vg,ox+player.x*ppm,oy+player.y*ppm,radius)
        nvgStrokeWidth(vg,1.6);nvgStrokeColor(vg,nvgRGBA(247,247,225,245));nvgStroke(vg)
    end
end

-- Text remains in UI components; the existing UI owns fonts, frame and DPI.
function Map:BuildLegend()
    local function label(text,color)
        return UI.Label{text=text,fontSize=12,fontColor=color,pointerEvents="none"}
    end
    self.seedLabel=UI.Label{id="overviewMapSeed",text="地图种子 —",fontSize=14,
        fontColor={210,202,226,255},textAlign="right",pointerEvents="none"}
    return UI.SafeAreaView {
        position="absolute",left=0,top=0,width="100%",height="100%",visible=false,
        nativeMenuInset=true,pointerEvents="box-none",children={
            UI.Panel{position="absolute",left=20,top=14,right=180,pointerEvents="none",children={
                UI.Label{text="全图观察",fontSize=19,fontColor={240,237,246,255}},
                label("模拟已暂停 · 黑色为未探索",{180,176,198,255})}},
            Skin.Button{id="overviewMapClose",text="返回游戏",position="absolute",right=16,top=12,
                width=144,height=48,fontSize=14,onClick=function() self.target=0 end},
            UI.Panel{position="absolute",right=20,top=70,width="44%",maxWidth=240,
                pointerEvents="none",children={self.seedLabel}},
            UI.Panel{position="absolute",left=16,right=16,bottom=16,flexDirection="row",
                flexWrap="wrap",justifyContent="center",gap=16,pointerEvents="none",children={
                    label("● 病毒 · 越密越亮",{255,216,72,255}),
                    label("● 免疫细胞",{80,170,255,255}),
                    label("● 健康细胞",{255,86,98,255}),
                    label("○ 当前病毒群",{247,247,225,255})}},
        }
    }
end

return Map
