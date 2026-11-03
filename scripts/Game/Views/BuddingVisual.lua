-- Read-only replacement of at most three real births per release batch.
local Config = require("Core.Config")
local Art = require("Game.Views.ArtResources")
local VU = require("Game.VisualUtils")
local TAU = math.pi * 2
local EMPTY = {}
---@class BuddingVisual
local Budding = {}
Budding.__index = Budding

function Budding.New(options)
    local self = setmetatable({}, Budding)
    self:init(options or {})
    return self
end

function Budding:init(options)
    self.options = options
    self.art = Art.New(8)
    self.records = {}
    self.batches = {}
    self.viruses = {}
    ---@type table?
    self.manifest = options.manifest
    self.metaAttempted = self.manifest ~= nil
    ---@type SwarmWorld?
    self.world = nil
end

function Budding:Destroy()
    self.art:Destroy()
    self.records = {}
    self.batches = {}
    self.viruses = {}
    self.world = nil
    self.metaAttempted = self.manifest ~= nil
end

function Budding:Prepare(world,sharedViruses)
    if self.world ~= world then self:Destroy(); self.world = world end
    self.art:BeginFrame()
    self.records = {}
    self.viruses = sharedViruses or {}
    if not world then return end
    if not self.metaAttempted then
        self.manifest = Art.ReadJSON(Config.ArtSlots.buddingManifest)
        self.metaAttempted = true
    end
    if not self.manifest then return end
    if not sharedViruses then
        for _, virus in ipairs(world.releasedViruses or EMPTY) do self.viruses[virus.id] = virus end
    end
    local time = world.time or 0
    local duration = Config.CellVisual.buddingSeconds
    local handoff = Config.CellVisual.buddingHandoffSeconds
    for _, cell in ipairs(world.cells or EMPTY) do
        local age = cell.lastReleaseVisualAt and time-cell.lastReleaseVisualAt or math.huge
        if cell.state ~= "DEAD" and age >= 0 and age < duration+handoff then
            local batch = self.batches[cell.id]
            if not batch or batch.sequence ~= cell.releaseVisualSequence then
              batch = {sequence=cell.releaseVisualSequence,selected={}}
              self.batches[cell.id] = batch
              for _, direction in ipairs(cell.releaseVisualDirections or EMPTY) do
                local virus = self.viruses[direction.sourceId]
                if virus and virus.sourceCellId == cell.id
                    and (virus.state == "RELEASED" or virus.state == "DRIFTING") then
                    local angle = (math.atan(direction.normalY, direction.normalX)
                        -(direction.visualCellRotation or cell.rotation or 0)) % TAU
                    local count = #self.manifest.poses
                    local index = 1+math.floor(angle / TAU*count+.5)%count
                    local pose = self.manifest.poses[index]
                    local overlaps = false
                    for _, prior in ipairs(batch.selected) do
                        local a,b = prior.pose.rect,pose.rect
                        if a[1] < b[1]+b[3] and b[1] < a[1]+a[3]
                            and a[2] < b[2]+b[4] and b[2] < a[2]+a[4] then overlaps = true end
                    end
                    -- Nearby patches cannot replace the same base rectangle twice.
                    -- Unselected births remain drawn at their real simulation positions.
                    if not overlaps and #batch.selected < 3 then
                        batch.selected[#batch.selected+1] = { pose=pose, virus=virus, age=age,
                            frame=math.min(#pose.frames,1+math.floor(age/duration*#pose.frames)),
                            key=tostring(world)..":"..tostring(cell.id)..":"..tostring(cell.releaseVisualSequence)..":"..tostring(virus.id) }
                    end
                end
              end
            end
            local selected = {}
            for _, record in ipairs(batch.selected) do
                local virus = self.viruses[record.virus.id]
                if not virus or (virus.state ~= "RELEASED" and virus.state ~= "DRIFTING") then record.cancelled=true end
                if not record.cancelled then
                    record.virus,record.age = virus,age
                    local count = #record.pose.frames
                    record.frame = math.min(count,1+math.floor(age/duration*count))
                    selected[#selected+1] = record
                end
            end
            self.records[cell.id] = selected
        else
            self.batches[cell.id] = nil
        end
    end
end

-- Legacy patches wait for their atlas. New births keep the intact registered
-- membrane and draw the shared new virus along the same authored trajectory.
function Budding:Ready(nvg, cell)
    local ready = {}
    for _, record in ipairs(self.records[cell.id] or EMPTY) do
        if record.age < Config.CellVisual.buddingSeconds then
          if self.manifest.material_mode == "bioluminescent-sprites" then
            local path = Config.ArtSlots.virusParticle[3]
            if self.art:Get(nvg,path,0) then
                record.fluorescent = true
                ready[#ready+1] = record
            end
          else
            local tile = record.pose.frames[record.frame]
            local path = self.manifest.pages[tile[1]]
            local entry = self.art:Get(nvg, path, NVG_IMAGE_NEAREST or 0)
            if entry and entry.width == self.manifest.page_size and entry.height == self.manifest.page_size then
                ready[#ready+1] = record
            end
          end
        end
    end
    return ready
end

function Budding:DrawPatches(nvg, records, alpha, handled)
    for _, record in ipairs(records) do
      if record.fluorescent then
        local point = record.pose.centres[record.frame]
        local diameter = record.pose.diameters[record.frame]
        local progress = (record.frame-1)/math.max(1,#record.pose.frames-1)
        local neck = math.sin(progress*math.pi)
        if neck > .01 then
            local anchor = record.pose.centres[1]
            nvgBeginPath(nvg)
            nvgMoveTo(nvg,anchor[1],anchor[2])
            nvgLineTo(nvg,point[1],point[2])
            if nvgLineCap then nvgLineCap(nvg,NVG_ROUND or 1) end
            nvgStrokeWidth(nvg,math.max(1,diameter*.20*neck))
            nvgStrokeColor(nvg,nvgRGBA(205,65,90,math.floor(alpha*170*neck)))
            nvgStroke(nvg)
        end
        if VU.DrawSprite(nvg,Config.ArtSlots.virusParticle[3],point[1],point[2],
            diameter/Config.CellVisual.virusFill,alpha) then
            handled[record.virus.id] = true
            record.shown = true
        end
      else
        local tile = record.pose.frames[record.frame]
        if self.art:DrawTile(nvg, self.manifest.pages[tile[1]], tile, record.pose.rect,
            self.manifest.tile_size, self.manifest.page_size, alpha) then
            handled[record.virus.id] = true
            record.shown = true
        end
      end
    end
end

function Budding:DrawHandoffs(nvg, cell, x, y, scale, time, ppm, drawVirus, handled, vitality)
    for _, record in ipairs(self.records[cell.id] or EMPTY) do
        if record.shown and record.age >= Config.CellVisual.buddingSeconds then
            local t = math.min(1,(record.age-Config.CellVisual.buddingSeconds)/Config.CellVisual.buddingHandoffSeconds)
            t = t*t*(3-2*t)
            local last = #record.pose.frames
            local point = record.pose.centres[last]
            local co,si = math.cos(cell.rotation or 0),math.sin(cell.rotation or 0)
            local lx,ly=point[1]*(vitality and vitality.sx or 1),point[2]*(vitality and vitality.sy or 1)
            local bx,by = x+(co*lx-si*ly)*scale,y+(si*lx+co*ly)*scale
            -- Remove display drift at the handoff target, which is in world space.
            local tx = x+(record.virus.x-cell.x-(vitality and vitality.dx or 0))*ppm
            local ty = y+(record.virus.y-cell.y-(vitality and vitality.dy or 0))*ppm
            local diameter = record.pose.diameters and record.pose.diameters[last] or 121
            local radius = (diameter*scale*.5)*(1-t) + record.virus.radius*ppm*t
            drawVirus(nvg,bx+(tx-bx)*t,by+(ty-by)*t,radius,record.virus,time,ppm,true,false)
            handled[record.virus.id] = true
        end
    end
end

return Budding
