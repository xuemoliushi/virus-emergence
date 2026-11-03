-- Pure presentation state: real-time fades and one continuous heartbeat loop.
-- Reads a snapshot only; never consumes gameplay events or simulation RNG.
---@class ChaseMusic
---@field config table
---@field transitionLength number
---@field transitionRemaining number
---@field mix number
---@field state 'normal'|'transition'|'chase'|'release'
local Chase = {}
Chase.__index = Chase

function Chase.New(config, transitionLength)
    local self = setmetatable({}, Chase)
    self.config, self.transitionLength = config, math.max(0, transitionLength)
    self:Reset()
    return self
end

function Chase:Reset()
    self.mix, self.transitionRemaining = 0, 0
    self.state = 'normal'
end

---@param sim SimState?
---@return boolean
function Chase.IsChased(sim)
    if not sim or not sim.started or sim.ending then return false end
    local world = sim.world
    if not world then return false end
    local group = world:SwarmById(world.currentControlledSwarmId)
    if not group or group.mass <= 0 or group.isHidden then return false end
    for _, immune in ipairs(world.immunes) do
        -- Warning is still acquisition. Only formal pursuit and its attack /
        -- retained-target cooldown drive chase music.
        local state = immune.state
        if immune.targetType == 'swarm' and immune.targetId == group.id
            and (state == 'chase' or state == 'attack' or state == 'cooldown') then return true end
    end
    return false
end

-- introPlaying is actual engine playback, so heartbeat never overlaps the intro.
-- Repetition belongs to the audio engine, not the frame / simulation clock.
function Chase:Update(dt, chased, introPlaying)
    local cfg = self.config
    if dt <= 0 or dt ~= dt or dt == math.huge then
        return { intro = false, heartbeat = false, mix = self.mix }
    end
    local intro = false
    if chased and self.state == 'normal' then
        self.state, self.transitionRemaining = 'transition', self.transitionLength
        intro = true
    end
    if chased then self.mix = math.min(1, self.mix + dt / cfg.fadeInSeconds)
    else self.mix = math.max(0, self.mix - dt / cfg.fadeOutSeconds) end

    if not intro then self.transitionRemaining = math.max(0, self.transitionRemaining - dt) end
    local heartbeat = false
    if self.transitionRemaining <= 0 and not intro and not introPlaying then
        if self.mix > 0 then
            self.state = chased and 'chase' or 'release'
            heartbeat = true
        else self:Reset() end
    end
    return { intro = intro, heartbeat = heartbeat, mix = self.mix }
end

return Chase
