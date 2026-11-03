-- Shared, bounded local emission. UI owns the NanoVG frame and DPR.
-- The approved material/highlights are in the base textures; this optional
-- additive atlas supplies gentle internal activity without full-screen Bloom.
---@type GameConfig
local Config = require("Core.Config")
local Art = require("Game.Views.ArtResources")
---@class Bioluminescence
local Light = {}
Light.__index = Light

function Light.New()
    local self = setmetatable({}, Light)
    self:init()
    return self
end

function Light:init()
    self.art = Art.New(1)
    self.draws = 0
    self.limit = 0
end

function Light:BeginFrame(entities)
    local c = Config.Bioluminescence or {}
    self.draws = 0
    self.limit = math.max(0, math.min(32, c.maxGlowDraws or 24))
    if (entities or 0) > (c.denseThreshold or 800) then
        self.limit = math.min(self.limit, c.denseGlowDraws or 8)
    end
    self.art:BeginFrame()
end

-- kind: virus=1, macrophage=2, tcell01=3, tcell02=4, healthy=5.
-- visiblePixels is in Widget base pixels, even inside the cell-local transform.
function Light:Draw(nvg, kind, x, y, size, alpha, time, phase, visiblePixels, rotation)
    local c = Config.Bioluminescence or {}
    if not c.enabled or not c.glowEnabled or self.draws >= self.limit
        or not nvgGlobalCompositeOperation or not NVG_LIGHTER
        or (visiblePixels or size) < (kind == 1 and (c.minVirusGlowPixels or 32) or (c.minGlowPixels or 28))
        or size <= 0 or alpha <= 0 then return false end
    local image = self.art:Get(nvg, c.emissionAtlas, 0)
    if not image then return false end
    local frame = math.floor(((time or 0)*.55+(phase or 0)/(math.pi*2))%4)
    local gain = math.max(0, math.min(.35, c.glowAlpha or .16))*alpha
    nvgSave(nvg)
    nvgTranslate(nvg, x, y)
    if rotation and rotation ~= 0 then nvgRotate(nvg, rotation) end
    nvgGlobalCompositeOperation(nvg, NVG_LIGHTER)
    nvgBeginPath(nvg)
    nvgRect(nvg, -size*.5, -size*.5, size, size)
    nvgFillPaint(nvg, nvgImagePattern(nvg, -size*.5-(kind-1)*size,
        -size*.5-frame*size, size*5, size*4, 0, image.handle, gain))
    nvgFill(nvg)
    nvgRestore(nvg)
    self.draws = self.draws+1
    return true
end

function Light:Destroy()
    self.art:Destroy()
    self.draws, self.limit = 0, 0
end

return Light
