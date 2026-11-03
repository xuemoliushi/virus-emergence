-- Presentation-only particles. Never write entities, consume world RNG, emit events
-- or feed these poses back into targeting, infection, damage or movement.
local Grid = require("Core.SpatialGrid")
local TAU = math.pi * 2
local EMPTY = {}
local GAP = 0.012 -- metres between visible virus bodies
local STEP = 1 / 60

---@class SwarmVisualBody
---@field entity table
---@field x number
---@field y number
---@field vx number
---@field vy number
---@field angle number
---@field spin number
---@field radius number
---@field tx number
---@field ty number
---@field slotX number
---@field slotY number
---@field dx number
---@field dy number
---@field index integer
---@field immune boolean
---@field group table?
---@field swarmId number?
---@field state string?
---@field seen integer
---@field padding number
---@field noiseAX number
---@field noiseAY number
---@field noiseBX number
---@field noiseBY number

---@class SwarmVisualPhysics
local Physics = {}
Physics.__index = Physics

function Physics.New()
    local self = setmetatable({}, Physics)
    self:Reset()
    return self
end

function Physics:Reset()
    ---@type table<table,SwarmVisualBody>
    self.poses = {}
    ---@type SwarmVisualBody[]
    self.bodies = {}
    ---@type table?
    self.world = nil
    ---@type table?
    self.cellSource = nil
    ---@type table?
    self.surfaceData = nil
    self.cellGrid = Grid.New(1.2)
    self.immuneGrid = Grid.New(1.2)
    self.contour = {}
    self.contourBound = 1
    self.serial = 0
    self.steps = 0
    self.visualTime = 0
    self.pairChecks = 0
    self.cellChecks = 0
    self.rows = {}
    self.bucketPool = {}
    self.bucketCount = 0
    self.rowPool = {}
    self.rowCount = 0
    self.slotDirections = {}
end

-- The same authored membrane contour as CellSurface, in units of cell radius.
-- No image reads, alpha scanning or per-frame mesh/rigid-body creation.
function Physics:SetSurface(data)
    if data == self.surfaceData then return end
    self.surfaceData = data
    self.contour = {}
    self.contourBound = 1
    if not data or not data.placements or not data.foreground_diameter then return end
    local scale = 2 / data.foreground_diameter
    for _, point in ipairs(data.placements) do
        local radius = math.sqrt(point[1]^2 + point[2]^2) * scale
        self.contour[#self.contour + 1] = radius
        self.contourBound = math.max(self.contourBound, radius)
    end
end

local function position(motion, entity)
    if motion then return motion:Position(entity) end
    return entity.x, entity.y
end

local function finite(dt)
    return dt == dt and dt > 0 and dt < math.huge
end

-- A shared pose accessor also keeps warning lines aligned with immune bodies.
function Physics:Position(entity, motion)
    local body = self.poses[entity]
    if body then return body.x, body.y end
    return position(motion, entity)
end

function Physics:Rotation(entity)
    local body = self.poses[entity]
    return body and body.angle or nil
end

function Physics:CellRadius(cell, angle)
    local count = #self.contour
    if count == 0 then return cell.radius or .4 end
    local bin = ((angle - (cell.rotation or 0)) % TAU) / TAU * count
    local index = math.floor(bin)
    local a, b = self.contour[index + 1], self.contour[(index + 1) % count + 1]
    return (a + (b - a) * (bin - index)) * (cell.radius or .4)
end

-- Contact removes normal velocity, retaining a little tangential rolling.
local function contact(body, nx, ny, push)
    body.x, body.y = body.x + nx * push, body.y + ny * push
    local normal = body.vx * nx + body.vy * ny
    if normal < 0 then
        body.vx, body.vy = body.vx - normal * nx, body.vy - normal * ny
    end
    if not body.immune then
        local tangent = body.vy * nx - body.vx * ny
        body.spin = body.spin + (tangent / math.max(.02, body.radius) * .22 - body.spin) * .22
    end
end

function Physics:ProjectCells(body)
    -- 免疫寻路只避开真实地图墙体；表现也穿过组织，不将直线路径挤偏。
    if body.immune then return end
    local reach = body.radius + self.cellGrid.maxRadius * self.contourBound + .02
    local grid, size = self.cellGrid, self.cellGrid.size
    for by = math.floor((body.y-reach)/size), math.floor((body.y+reach)/size) do
        local row = grid.rows[by]
        if row then
            for bx = math.floor((body.x-reach)/size), math.floor((body.x+reach)/size) do
                for _, cell in ipairs(row[bx] or EMPTY) do
                    if cell.state ~= "DEAD" then
                        local dx, dy = body.x-cell.x, body.y-cell.y
                        local bound = body.radius + (cell.radius or .4) * self.contourBound + .004
                        local distance2 = dx*dx + dy*dy
                        if distance2 < bound*bound then
                            self.cellChecks = self.cellChecks + 1
                            local angle = distance2 > 1e-12 and math.atan(dy,dx)
                                or (body.entity.phase or body.index * 2.399963)
                            local radius = self:CellRadius(cell,angle) + body.radius + .004
                            local distance = math.sqrt(distance2)
                            if distance < radius then
                                contact(body,math.cos(angle),math.sin(angle),radius-distance)
                            end
                        end
                    end
                end
            end
        end
    end
end

-- Cell and immune bodies are large obstacles; virus pressure does not drag an
-- immune away from its authoritative target. Immune pairs share displacement.
function Physics:ProjectImmunes(body)
    local grid, size = self.immuneGrid, self.immuneGrid.size
    local reach = body.radius + grid.maxRadius + GAP
    for by = math.floor((body.y-reach)/size), math.floor((body.y+reach)/size) do
        local row = grid.rows[by]
        if row then
            for bx = math.floor((body.x-reach)/size), math.floor((body.x+reach)/size) do
                for _, other in ipairs(row[bx] or EMPTY) do
                    if body ~= other and (not body.immune or body.index < other.index) then
                        local dx,dy = body.x-other.x,body.y-other.y
                        local radius = body.radius+other.radius+GAP
                        local d2 = dx*dx+dy*dy
                        if d2 < radius*radius then
                            local distance = math.sqrt(d2)
                            local nx,ny = 1,0
                            if distance > 1e-6 then nx,ny=dx/distance,dy/distance end
                            local push = (radius-distance) * (body.immune and .5 or 1)
                            contact(body,nx,ny,push)
                            if body.immune then contact(other,-nx,-ny,push) end
                        end
                    end
                end
            end
        end
    end
end

-- Reuse bucket arrays and row maps. Clear coordinate keys between passes so
-- memory follows peak visible occupancy rather than all visited map positions.
function Physics:BuildParticles(particles, size)
    for i=1,self.bucketCount do
        local bucket = self.bucketPool[i]
        for j=#bucket,1,-1 do bucket[j]=nil end
    end
    for key in pairs(self.rows) do self.rows[key]=nil end
    for i=1,self.rowCount do
        for key in pairs(self.rowPool[i]) do self.rowPool[i][key]=nil end
    end
    self.rowCount = 0
    self.bucketCount = 0
    for _, body in ipairs(particles) do
        local bx,by = math.floor(body.x/size),math.floor(body.y/size)
        local row = self.rows[by]
        if not row then
            self.rowCount=self.rowCount+1
            row=self.rowPool[self.rowCount] or {}
            self.rowPool[self.rowCount]=row
            self.rows[by]=row
        end
        local bucket = row[bx]
        if not bucket then
            self.bucketCount = self.bucketCount+1
            bucket = self.bucketPool[self.bucketCount] or {}
            self.bucketPool[self.bucketCount] = bucket
            row[bx] = bucket
        end
        bucket[#bucket+1] = body
    end
end

function Physics:Separate(particles, size)
    self:BuildParticles(particles,size)
    for _, body in ipairs(particles) do
        local bx,by=math.floor(body.x/size),math.floor(body.y/size)
        local checks=0
        for y=by-1,by+1 do
            local row = self.rows[y]
            if row and checks<48 then
                for x=bx-1,bx+1 do
                    local bucket=row[x] or EMPTY
                    -- Even hundreds born at exactly the same point have bounded
                    -- cost. Rotate the sample so crowded particles all relax.
                    local start=(self.serial+body.index)%math.max(1,#bucket)
                    for offset=1,#bucket do
                        if checks>=48 then break end
                        checks=checks+1
                        local other=bucket[(start+offset-1)%#bucket+1]
                        if body.index < other.index then
                            self.pairChecks = self.pairChecks+1
                            local dx,dy=body.x-other.x,body.y-other.y
                            local radius=body.radius+other.radius+body.padding+other.padding
                            local d2=dx*dx+dy*dy
                            if d2 < radius*radius then
                                local distance=math.sqrt(d2)
                                local nx,ny=1,0
                                if distance>1e-6 then nx,ny=dx/distance,dy/distance
                                else
                                    local angle=(body.index*2.399963+other.index) % TAU
                                    nx,ny=math.cos(angle),math.sin(angle)
                                end
                                local push=(radius-distance)*.5
                                contact(body,nx,ny,push)
                                contact(other,-nx,-ny,push)
                            end
                        end
                    end
                end
            end
        end
    end
end

function Physics:Add(entity, group, immune, motion)
    local x,y=position(motion,entity)
    local tx,ty=x,y
    if group then tx,ty=group.x,group.y end
    local body=self.poses[entity]
    if not body then
        -- Stable per-individual variation belongs only to the view. No random()
        -- calls, per-frame random tables or changes to the simulation seed.
        local seed=(entity.id or #self.bodies+1)*12.9898+(entity.phase or 0)*78.233
        local variation=(math.sin(seed)*43758.5453)%1
        local a,b=variation*TAU,((math.sin(seed+9.7)*23421.631)%1)*TAU
        body={entity=entity,x=x,y=y,vx=0,vy=0,angle=entity.phase or 0,spin=0,
            radius=entity.radius or .045,tx=tx,ty=ty,slotX=tx,slotY=ty,dx=0,dy=0,index=0,
            immune=immune,group=group,swarmId=entity.swarmId,state=entity.state,seen=0,
            padding=.003+.018*variation,
            noiseAX=math.cos(a),noiseAY=math.sin(a),noiseBX=math.cos(b),noiseBY=math.sin(b)}
        self.poses[entity]=body
    end
    local dx,dy=tx-body.tx,ty-body.ty
    -- Teleports and re-entry reset presentation velocity, not the entity. A
    -- split/merge changes the centre but retains the individual's current pose.
    if dx*dx+dy*dy>9 or body.state~=entity.state then
        body.x,body.y,body.vx,body.vy=x,y,0,0
        body.spin=0
        dx,dy=0,0
    elseif body.swarmId~=entity.swarmId then dx,dy=0,0 end
    body.tx,body.ty,body.dx,body.dy=tx,ty,dx,dy
    body.state,body.swarmId=entity.state,entity.swarmId
    body.group,body.seen=group,self.serial
    body.radius=entity.radius or (immune and .48 or .045)
    body.index=#self.bodies+1
    self.bodies[body.index]=body
    return body
end

-- Called from Widget.Update, never DrawWorld. Frustum sleeping affects only
-- visual work; offscreen simulation and all entities remain untouched.
function Physics:Update(world, motion, dt, active, surfaceData, view)
    if self.world~=world then self:Reset();self.world=world end
    if not world then return end
    self:SetSurface(surfaceData)
    if self.cellSource~=world.cells then
        self.cellSource=world.cells
        self.cellGrid:Build(world.cells or EMPTY)
    end
    self.serial=self.serial+1
    self.bodies={}
    self.immuneGrid.rows={}
    self.pairChecks,self.cellChecks,self.steps=0,0,0
    local groups,particles,immunes={},{},{}
    for _, swarm in ipairs(world.swarms or EMPTY) do
        local x,y=position(motion,swarm)
        groups[swarm.id]={x=x,y=y,radius=swarm.radius or .48,hidden=swarm.isHidden}
    end
    local function visible(entity, padding)
        if not view then return true end
        return entity.x>=view.x-padding and entity.x<=view.x+view.w+padding
            and entity.y>=view.y-padding and entity.y<=view.y+view.h+padding
    end
    for _, immune in ipairs(world.immunes or EMPTY) do
        if visible(immune,3) then immunes[#immunes+1]=self:Add(immune,nil,true,motion) end
    end
    local maxRadius=.045
    local counts,indices={},{}
    for _,virus in ipairs(world.viruses or EMPTY) do
        counts[virus.swarmId]=(counts[virus.swarmId] or 0)+1
    end
    for _, virus in ipairs(world.viruses or EMPTY) do
        local group=groups[virus.swarmId]
        if group and not group.hidden and visible(group,3) then
            local body=self:Add(virus,group,false,motion)
            -- Equal-area disk slots refill missing sectors after contact, loss,
            -- split or merge. Use live membership, never stale swarm mass.
            local index=(indices[virus.swarmId] or 0)+1
            indices[virus.swarmId]=index
            local radius=math.max(0,group.radius-body.radius)
                *math.sqrt((index-.5)/counts[virus.swarmId])
            local direction=self.slotDirections[index]
            if not direction then
                local angle=index*2.3999632297287
                direction={x=math.cos(angle),y=math.sin(angle)}
                self.slotDirections[index]=direction
            end
            body.tx=group.x+direction.x*radius
            body.ty=group.y+direction.y*radius
            -- Add tracks centre translation, not slot changes on membership edits.
            -- Keep the stored target at the centre for the next frame's delta.
            body.slotX,body.slotY=body.tx,body.ty
            body.tx,body.ty=group.x,group.y
            particles[#particles+1]=body
            maxRadius=math.max(maxRadius,body.radius)
        end
    end
    for _, virus in ipairs(world.releasedViruses or EMPTY) do
        if virus.state~="CLEARED" and virus.state~="LOST" and virus.state~="ABSORBED"
            and virus.state~="CONVERTED" and visible(virus,2) then
            local body=self:Add(virus,nil,false,motion)
            particles[#particles+1]=body
            maxRadius=math.max(maxRadius,body.radius)
        end
    end
    for entity,body in pairs(self.poses) do
        if body.seen~=self.serial then self.poses[entity]=nil end
    end
    if not active or not finite(dt) then return end
    local elapsed=math.min(dt,1/15)
    local steps=math.ceil(elapsed/STEP)
    local h=elapsed/steps
    local passes=#particles>700 and 2 or (#particles>250 and 3 or 5)
    self.steps=steps
    for _=1,steps do
        self.visualTime=self.visualTime+h
        -- Four shared waves per substep, then only multiplies/adds per virus.
        -- Different coefficients yield gentle uncorrelated local wandering.
        local waveA,waveB=math.sin(self.visualTime*.91),math.cos(self.visualTime*.91)
        local waveC,waveD=math.sin(self.visualTime*1.37),math.cos(self.visualTime*1.37)
        local groupDrag,trackDrag,spinDrag=math.exp(-7*h),math.exp(-12*h),math.exp(-4*h)
        for _,body in ipairs(self.bodies) do
            local dx,dy=body.tx-body.x,body.ty-body.y
            if body.group then
                dx,dy=body.slotX-body.x,body.slotY-body.y
                -- Weak central spring; short-range constraints make the pack
                -- occupy space. Extra tension outside the ring prevents strays.
                local distance=math.sqrt(dx*dx+dy*dy)
                local stiffness=18+math.max(0,distance-body.group.radius)*24
                local noiseX=(body.noiseAX*waveA+body.noiseAY*waveB
                    +body.noiseBX*waveC+body.noiseBY*waveD)*.38
                local noiseY=(body.noiseAY*waveA-body.noiseAX*waveB
                    +body.noiseBY*waveC-body.noiseBX*waveD)*.38
                body.vx=(body.vx+(dx*stiffness+noiseX)*h)*groupDrag
                body.vy=(body.vy+(dy*stiffness+noiseY)*h)*groupDrag
            else
                body.vx=(body.vx+dx*55*h)*trackDrag
                body.vy=(body.vy+dy*55*h)*trackDrag
            end
            local speed=math.sqrt(body.vx*body.vx+body.vy*body.vy)
            if speed>3 then body.vx,body.vy=body.vx*3/speed,body.vy*3/speed end
            body.x=body.x+body.dx/steps+body.vx*h
            body.y=body.y+body.dy/steps+body.vy*h
            body.spin=body.spin*spinDrag
            body.angle=(body.angle+math.max(-5,math.min(5,body.spin))*h) % TAU
        end
        for _=1,passes do
            self.immuneGrid:Build(immunes)
            for _,body in ipairs(immunes) do self:ProjectImmunes(body) end
            self.immuneGrid:Build(immunes)
            self:Separate(particles,maxRadius*2+.052)
            for _,body in ipairs(particles) do self:ProjectImmunes(body);self:ProjectCells(body) end
        end
    end
end

return Physics
