-- Per-run exploration for the overview. Reads real controlled-swarm positions only.
-- Coordinates are metres; the small grid also permits a cached, batched black mask.
---@class MapExploration
---@field world SwarmWorld?
---@field lastX number?
---@field lastY number?
---@field coverage table<number, number>
---@field maskRuns table<number, Rect4[]>
local Exploration = {}
Exploration.__index = Exploration

---@return MapExploration
function Exploration.New()
    local self=setmetatable({},Exploration)
    self.cellSize,self.radius,self.feather=.75,5,1.25
    self:Reset()
    return self
end

---@param world SwarmWorld?
function Exploration:Reset(world)
    self.world=world
    self.lastX,self.lastY=nil,nil
    self.coverage,self.maskRuns={},{}
    self.cols=world and math.ceil(world.width/self.cellSize) or 0
    self.rows=world and math.ceil(world.height/self.cellSize) or 0
    self.dirty=true
end

---@param x number
---@param y number
---@return boolean
function Exploration:IsExplored(x,y)
    local world=self.world
    if not world or x<0 or y<0 or x>=world.width or y>=world.height then return false end
    local col,row=math.floor(x/self.cellSize),math.floor(y/self.cellSize)
    return (self.coverage[row*self.cols+col+1] or 0)>0
end

---@param world SwarmWorld
function Exploration:Observe(world)
    if self.world~=world then self:Reset(world) end
    local player=world.player
    if not player or player.mass<=0 then return end
    local x,y=player.x,player.y
    if self.lastX and self.lastY and (x-self.lastX)^2+(y-self.lastY)^2<(self.cellSize*.25)^2 then return end
    self.lastX,self.lastY=x,y
    local size,radius=self.cellSize,self.radius
    local firstCol,lastCol=math.max(0,math.floor((x-radius)/size)),math.min(self.cols-1,math.floor((x+radius)/size))
    local firstRow,lastRow=math.max(0,math.floor((y-radius)/size)),math.min(self.rows-1,math.floor((y+radius)/size))
    for row=firstRow,lastRow do
        for col=firstCol,lastCol do
            local distance=math.sqrt(((col+.5)*size-x)^2+((row+.5)*size-y)^2)
            local level=math.max(0,math.min(8,math.floor((radius-distance)/self.feather*8+.5)))
            local key=row*self.cols+col+1
            if level>(self.coverage[key] or 0) then
                self.coverage[key]=level
                self.dirty=true
            end
        end
    end
end

-- Only regenerate rows after exploration changes, never every paused animation frame.
function Exploration:BuildMask()
    local world=self.world
    if not world then return end
    self.maskRuns={}
    local size=self.cellSize
    for row=0,self.rows-1 do
        local col=0
        while col<self.cols do
            local start=col
            local level=self.coverage[row*self.cols+col+1] or 0
            repeat col=col+1 until col>=self.cols or (self.coverage[row*self.cols+col+1] or 0)~=level
            if level<8 then
                local runs=self.maskRuns[level] or {}
                self.maskRuns[level]=runs
                local right=math.min(world.width,col*size)
                runs[#runs+1]={x=start*size,y=row*size,w=right-start*size,h=math.min(size,world.height-row*size)}
            end
        end
    end
    self.dirty=false
end

---@param vg NVGContextWrapper
---@param l Rect4
---@param ppm number
---@param ox number
---@param oy number
function Exploration:Draw(vg,l,ppm,ox,oy)
    if not self.world then return end
    if self.dirty then self:BuildMask() end
    nvgSave(vg)
    nvgIntersectScissor(vg,l.x,l.y,l.w,l.h)
    nvgIntersectScissor(vg,ox,oy,self.world.width*ppm,self.world.height*ppm)
    nvgShapeAntiAlias(vg,0) -- Adjacent tiles must not leave bright hairline seams.
    for level=0,7 do
        local runs=self.maskRuns[level]
        if runs then
            nvgBeginPath(vg)
            for _,r in ipairs(runs) do nvgRect(vg,ox+r.x*ppm,oy+r.y*ppm,r.w*ppm,r.h*ppm) end
            nvgFillColor(vg,nvgRGBA(0,0,0,math.floor(255*(1-level/8))))
            nvgFill(vg)
        end
    end
    nvgRestore(vg)
end

return Exploration
