-- Shared timing for the menu push-in and the covered game-root handoff.
local Shot = { hide = 0.25, push = 0.85, blackout = 0.10, hold = 0.10,
    reveal = 1.0, soundAt = 0.60, arrival = 0.78, hudAt = 0.72 }
Shot.duration = Shot.hide + Shot.push

---@param value number
---@return number
local function smooth(value)
    local t = math.max(0, math.min(1, value))
    return t * t * (3 - 2 * t)
end

---@param elapsed number
---@param motion boolean
---@return number foregroundOpacity
---@return number backgroundScale
---@return number blackOpacity
function Shot.Pose(elapsed, motion)
    local p = math.max(0, math.min(1, elapsed / Shot.duration))
    local menu = 1 - smooth(elapsed / Shot.hide)
    -- Nonzero gentle advance during title fade, followed by a smooth acceleration.
    local zoom = motion and (1 + 1.8 * p * p * p) or 1
    local black = smooth((elapsed - (Shot.duration - Shot.blackout)) / Shot.blackout)
    return menu, zoom, black
end

---@param elapsed number
---@param motion boolean
---@return number gameZoom
---@return number hudOpacity
---@return number blackOpacity
function Shot.Arrival(elapsed, motion)
    local t = math.max(0, math.min(1, elapsed / Shot.arrival))
    -- The real world continues forward from a slightly wider view; velocity settles to zero.
    local ease = 1 - (1 - t) ^ 3
    local zoom = motion and (0.82 + 0.18 * ease) or 1
    return zoom, smooth((elapsed - Shot.hudAt) / (Shot.reveal - Shot.hudAt)),
        1 - smooth(elapsed / 0.18)
end

return Shot
