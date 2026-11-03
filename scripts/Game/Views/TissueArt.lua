local Config = require("Core.Config")
local VU = require("Game.VisualUtils")
local Art = require("Game.Views.ArtResources")
local EMPTY = {}
---@class TissueArt
local Tissue = {}
Tissue.__index = Tissue

function Tissue.New()
    local self = setmetatable({}, Tissue)
    self:init()
    return self
end

function Tissue:init()
    self.art = Art.New(5)
    self.fibers = {}
    ---@type RespiratoryMap?
    self.map = nil
end

function Tissue:Destroy()
    self.art:Destroy()
    self.fibers = {}
    self.map = nil
end

local function capsule(nvg, ax, ay, bx, by, radius)
    local length = math.sqrt((bx-ax)^2+(by-ay)^2)
    if length < .00001 then return end
    local nx,ny = -(by-ay)/length*radius,(bx-ax)/length*radius
    nvgMoveTo(nvg,ax+nx,ay+ny)
    nvgLineTo(nvg,bx+nx,by+ny)
    nvgLineTo(nvg,bx-nx,by-ny)
    nvgLineTo(nvg,ax-nx,ay-ny)
    nvgClosePath(nvg)
    nvgPathWinding(nvg,NVG_SOLID)
    nvgCircle(nvg,ax,ay,radius)
    nvgCircle(nvg,bx,by,radius)
end

-- Same-winding subpaths fill the union once, including overlapping channels/regions.
local function path(nvg,map,ppm,ox,oy,onlyChannel)
    nvgBeginPath(nvg)
    if not onlyChannel then
        for _, region in ipairs(map.regions or EMPTY) do
            nvgEllipse(nvg,ox+region.x*ppm,oy+region.y*ppm,region.rx*ppm,region.ry*ppm)
        end
    end
    local channels = onlyChannel and {onlyChannel} or map.channels or EMPTY
    for _, channel in ipairs(channels) do
        for i=1,#channel.points-1 do
            local a,b = channel.points[i],channel.points[i+1]
            capsule(nvg,ox+a.x*ppm,oy+a.y*ppm,ox+b.x*ppm,oy+b.y*ppm,channel.width*ppm*.5)
        end
    end
end

function Tissue:Prepare(map)
    if self.map == map then return end
    self:Destroy()
    self.map = map
    local rng = VU.MakeRng((map.seed or 90210)+13007)
    for i=1,36 do
        local x,y = rng()*map.width,rng()*map.height
        if not map.Contains or map:Contains(x,y,0) then
            self.fibers[#self.fibers+1] = {x=x,y=y,size=3.8+rng()*1.4,angle=rng()*math.pi*2,
                variant=(i-1)%2+1}
        end
    end
end

-- Fully offscreen decals contribute no pixels but previously rebuilt the whole
-- tissue union and submitted a fill. Bound the rotated footprint before that work.
local function visible(l,x,y,w,h,co,si)
    if not l then return true end
    local cx,cy=x+(co*w-si*h)*.5,y+(si*w+co*h)*.5
    local rx,ry=(math.abs(co)*w+math.abs(si)*h)*.5+2,(math.abs(si)*w+math.abs(co)*h)*.5+2
    return cx+rx>=l.x and cx-rx<=l.x+l.w and cy+ry>=l.y and cy-ry<=l.y+l.h
end

function Tissue:Draw(nvg,map,ppm,ox,oy,l)
    if not nvgPathWinding then return false end
    self:Prepare(map)
    self.art:BeginFrame()
    local slots,settings = Config.ArtSlots,Config.EnvironmentVisual
    path(nvg,map,ppm,ox,oy)
    local drew = self.art:Paint(nvg,slots.tissueBg,ox,oy,settings.tileWidthMeters*ppm,
        settings.tileWidthMeters*9/16*ppm,settings.baseAlpha,0,(NVG_IMAGE_REPEATX or 2)|(NVG_IMAGE_REPEATY or 4))
    for _, fiber in ipairs(self.fibers) do
        local size = fiber.size*ppm
        local co,si = math.cos(fiber.angle),math.sin(fiber.angle)
        local x = ox+fiber.x*ppm-size*.5*(co-si)
        local y = oy+fiber.y*ppm-size*.5*(si+co)
        if visible(l,x,y,size,size,co,si) then
            path(nvg,map,ppm,ox,oy)
            self.art:Paint(nvg,slots.tissueFibers[fiber.variant],x,y,size,size,settings.fiberAlpha,fiber.angle)
        end
    end
    for _, channel in ipairs(map.channels or EMPTY) do
        for i=1,#channel.points-1 do
            local a,b = channel.points[i],channel.points[i+1]
            local dx,dy = b.x-a.x,b.y-a.y
            local length = math.sqrt(dx*dx+dy*dy)
            if length > .001 and channel.width > 0 then
                local angle = math.atan(dy,dx)
                local width,height = length*2*ppm,channel.width/0.461*ppm
                local co,si = math.cos(angle),math.sin(angle)
                local x = ox+(a.x+b.x)*.5*ppm-co*width*.5+si*height*.5
                local y = oy+(a.y+b.y)*.5*ppm-si*width*.5-co*height*.5
                if visible(l,x,y,width,height,co,si) then
                    path(nvg,map,ppm,ox,oy,channel)
                    self.art:Paint(nvg,slots.flowBed,x,y,width,height,settings.flowBedAlpha,angle)
                end
            end
        end
    end
    return drew
end

return Tissue
