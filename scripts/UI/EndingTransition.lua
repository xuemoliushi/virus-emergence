-- A continuous pull-back and dissolve into the film's close-up of the bird.
---@type GameConfig
local Config = require("Core.Config")
---@class EndingTransitionShot
---@field Pose fun(time:number):number,number,number
---@field Mix fun(time:number):number,number
local Shot = {}
local function smooth(time, startTime, endTime)
    local t = math.max(0, math.min(1, (time-startTime)/(endTime-startTime)))
    return t*t*(3-2*t)
end
function Shot.Pose(time)
    local cfg = Config.EndingTransition
    return 1-smooth(time,0,cfg.hudHide),
        1+(cfg.zoom-1)*smooth(time,0,cfg.zoomEnd),
        0
end
-- Image opacity uses smoothstep; independent scores use an equal-power crossfade.
function Shot.Mix(time)
    local progress=smooth(time,0,Config.EndingTransition.blend)
    return progress,math.sin(progress*math.pi*.5)
end
return Shot
