-- Read-only membrane anchors: fixed within a contact episode, reset on re-entry.
local Config = require("Core.Config")
local TAU = math.pi * 2
---@class AttachmentVisual
local Attachments = {}
Attachments.__index = Attachments

function Attachments.New()
    return setmetatable({cells={},patches={}},Attachments)
end

function Attachments:Destroy()
    self.cells = {}
    self.patches = {}
    self.viruses = nil
    self.swarmRadii = nil
end

function Attachments:Prepare(world,sharedViruses,sharedRadii)
    local liveCells,patchCells,viruses,radii = {},{},sharedViruses or {},sharedRadii or {}
    for _,cell in ipairs(world.cells or {})do
        if cell.state=="HEALTHY" or cell.state=="EXPOSED" or cell.state=="LATENT" then liveCells[cell.id]=true end
        if cell.state~="DEAD" then patchCells[cell.id]=true end
    end
    if not sharedViruses then
        for _,virus in ipairs(world.releasedViruses or {})do viruses[virus.id]=virus end
    end
    if not sharedRadii then
        for _,virus in ipairs(world.viruses or {})do
            if not radii[virus.swarmId] then radii[virus.swarmId]=virus.radius end
        end
    end
    self.viruses = viruses
    self.swarmRadii = radii
    for id in pairs(self.patches)do if not patchCells[id] then self.patches[id]=nil end end
    for id,entries in pairs(self.cells)do
        if not liveCells[id] then self.cells[id]=nil
        else
            for key,entry in pairs(entries)do
                if entry.sourceType=="RELEASED_VIRUS" then
                    local virus=viruses[entry.sourceId]
                    if not virus or virus.state=="ABSORBED" or virus.state=="CLEARED" or virus.state=="LOST" or virus.state=="CONVERTED" then entries[key]=nil end
                end
            end
        end
    end
end

local function entryAngle(cell,contact)
    if contact.entryLocalAngle then return contact.entryLocalAngle % TAU end
    if contact.stableLocalAngle then return contact.stableLocalAngle % TAU end
    if contact.normalX and contact.normalY then
        return (math.atan(contact.normalY,contact.normalX)
            -(contact.visualCellRotation or cell.rotation or 0)) % TAU
    end
end

function Attachments:RememberPatch(cell,key,angle,enteredAt,sequence)
    local previous = self.patches[cell.id]
    if not previous or enteredAt > previous.enteredAt
        or (enteredAt == previous.enteredAt and (key < previous.key
            or (key == previous.key and sequence > previous.sequence))) then
        self.patches[cell.id] = {angle=angle,key=key,enteredAt=enteredAt,sequence=sequence}
    end
end

function Attachments:GetPatchAngle(cell)
    local patch = self.patches[cell.id]
    return patch and patch.angle
end

function Attachments:VirusRadius(contact)
    local virus = contact.sourceType=="RELEASED_VIRUS" and self.viruses and self.viruses[contact.sourceId]
    local radius = virus and virus.radius
        or (contact.sourceType=="PLAYER_SWARM" and self.swarmRadii and self.swarmRadii[contact.sourceId])
        or Config.Gameplay.virusRadius
    return radius
end

function Attachments:Get(cell,time)
    if cell.state == "DEAD" then
        self.cells[cell.id] = nil
        self.patches[cell.id] = nil
        return {}
    end
    local entries = self.cells[cell.id] or {}
    self.cells[cell.id] = entries
    local count = 0
    local activeKeys = {}
    for index,contact in ipairs(cell.contactVisuals or {})do
        local key = contact.key or tostring(contact.sourceType)..":"..tostring(contact.sourceId or index)
        if contact.active~=false then activeKeys[key]=true end
    end
    for key,entry in pairs(entries) do
        if time-entry.lastSeen >= Config.CellVisual.attachmentGraceSeconds+Config.CellVisual.attachmentFadeSeconds then
            entries[key]=nil
        else count=count+1 end
    end
    for index, contact in ipairs(cell.contactVisuals or {}) do
        local key = contact.key or tostring(contact.sourceType)..":"..tostring(contact.sourceId or index)
        local entry = entries[key]
        local valid = true
        if contact.sourceType=="RELEASED_VIRUS" and self.viruses then
            local virus=self.viruses[contact.sourceId]
            valid=virus and virus.state~="ABSORBED" and virus.state~="CONVERTED" and virus.state~="CLEARED" and virus.state~="LOST"
        end
        local angle = entryAngle(cell,contact)
        if valid and not entry and angle and contact.active~=false and count>=3 then
            local oldest
            for oldKey,old in pairs(entries)do
                if not activeKeys[oldKey] and (not oldest or old.lastSeen<entries[oldest].lastSeen
                    or (old.lastSeen==entries[oldest].lastSeen and oldKey<oldest)) then oldest=oldKey end
            end
            if oldest then entries[oldest]=nil;count=count-1 end
        end
        if valid and not entry and angle and count < 3 then
            entry = {angle=angle%TAU,sourceType=contact.sourceType,sourceId=contact.sourceId,
                lastSeen=contact.lastSeen or time,contact=contact,
                enteredAt=contact.enteredAt or contact.firstSeen or contact.lastSeen or time,
                sequence=contact.contactSequence or 0,radius=self:VirusRadius(contact)}
            entries[key] = entry
            count = count+1
        elseif valid and entry then
            local enteredAt=contact.enteredAt or contact.firstSeen or entry.enteredAt
            local sequence=contact.contactSequence or 0
            if angle and (entry.enteredAt~=enteredAt or entry.sequence~=sequence) then
                entry.angle,entry.enteredAt,entry.sequence = angle,enteredAt,sequence
                entry.radius=self:VirusRadius(contact)
            end
            entry.lastSeen = math.max(entry.lastSeen,contact.lastSeen or time)
            entry.contact = contact
        end
        if valid and entry then
            self:RememberPatch(cell,key,entry.angle,entry.enteredAt,entry.sequence)
        end
    end
    -- Retain the latest accepted entry through infection and attachment fade-out.
    local anchor=cell.contactVisualAnchor
    if anchor and (not self.patches[cell.id] or #(cell.contactVisuals or {})==0) then
        local angle=entryAngle(cell,anchor)
        if angle then self:RememberPatch(cell,anchor.key or "anchor",angle,
            anchor.enteredAt or anchor.firstSeen or anchor.lastSeen or time,anchor.contactSequence or 0) end
    end
    if cell.state == "PRODUCTIVE" or cell.state == "EXHAUSTED" then
        self.cells[cell.id]=nil
        return {}
    end
    local visible = {}
    for key, entry in pairs(entries) do
        local age = math.max(0,time-entry.lastSeen-Config.CellVisual.attachmentGraceSeconds)
        local t = math.min(1,age/Config.CellVisual.attachmentFadeSeconds)
        local alpha = 1-t*t*(3-2*t)
        if cell.state == "LATENT" then
            local infectedAge = math.max(0,time-(cell.infectedVisualAt or time))
            local u = math.min(1,infectedAge/.8)
            alpha = alpha*(1-u*u*(3-2*u))
        end
        if alpha <= 0 then entries[key] = nil
        else
            visible[#visible+1] = {angle=entry.angle,alpha=alpha*.90,
                sourceType=entry.sourceType,sourceId=entry.sourceId,contact=entry.contact,key=key,radius=entry.radius}
        end
    end
    -- Stable order prevents overlapping source-over layers swapping each frame.
    table.sort(visible,function(a,b)return a.key<b.key end)
    return visible
end

return Attachments
