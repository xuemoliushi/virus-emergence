-- 只读的潜伏期内部活动，在调用方已有的 NanoVG 帧中绘制。
-- 父层负责平移到细胞中心、旋转 cell.rotation、缩放 layerSize/1254。
-- 在原色液泡之后、感染色斑及附着亮点和病毒之前绘制。
-- 保留已核准的元数据点位，包括已认可的 54.8px 最小间距。

---@class LatentParticlePulse
---@field period_s number
---@field phase number
---@field alpha_min number
---@class LatentParticleMetaEntry
---@field tier string
---@field centre number[]
---@field sprite string
---@field pulse LatentParticlePulse
---@class LatentParticlesMeta
---@field canvas number[]
---@field sprite_canvas_px number
---@field count number
---@field tiers table<string,number>
---@field sprites table<string,string>
---@field pulse {period_s:number[],alpha_range:number[]}
---@field particles LatentParticleMetaEntry[]
---@class LatentParticleDrawEntry
---@field path string
---@field x number 矩形左边界，相对于 1254 画布中心
---@field y number 矩形上边界，相对于 1254 画布中心
---@field period number
---@field phase number
---@field alphaMin number
---@field alphaMax number
---@class LatentParticlesOptions
---@field meta LatentParticlesMeta? 测试可注入已核准元数据，不依赖引擎文件读取。
---@class LatentParticles
---@field meta LatentParticlesMeta?
---@field options LatentParticlesOptions
---@field particles LatentParticleDrawEntry[] 仅绘制描述，不是模拟实体。
---@field spritePaths table<string,string>
---@field images table<string,integer> 自持的 NEAREST 图片句柄；0 表示已缓存的加载失败。
---@field failures table<string,boolean>
---@field nvg NVGContextWrapper?
---@field size number
---@field metaAttempted boolean
---@field valid boolean
---@field destroyed boolean
---@field Draw fun(self:LatentParticles, nvg:NVGContextWrapper, cell:table, time:number, alpha:number?):boolean
---@field Destroy fun(self:LatentParticles)
local LatentParticles = {}
LatentParticles.__index = LatentParticles
local META_PATH = "image/latent_particles_meta.json"
local TIERS = { "dim", "normal", "bright" }
local TAU = math.pi * 2

---@param value any
---@return boolean
local function Finite(value)
    return type(value) == "number" and value == value and value > -math.huge and value < math.huge
end

---@return LatentParticlesMeta
local function ReadMeta()
    assert(cache and cjson, "ResourceCache/cjson 不可用")
    local file = cache:GetFile(META_PATH)
    assert(file, "无法读取资源 " .. META_PATH)
    local ok, text = pcall(function()
        local lines = {}
        while not file:IsEof() do lines[#lines + 1] = file:ReadLine() end
        return table.concat(lines, "\n")
    end)
    file:Dispose() -- 仅释放自持文件，不释放共享缓存资源或上下文。
    assert(ok, text)
    local meta = cjson.decode(text)
    assert(type(meta) == "table", "潜伏颗粒 JSON 无效")
    return meta --[[@as LatentParticlesMeta]]
end

---@param options LatentParticlesOptions?
---@return LatentParticles
function LatentParticles.New(options)
    local self = setmetatable({}, LatentParticles)
    self:init(options or {})
    return self
end

---@param options LatentParticlesOptions
function LatentParticles:init(options)
    self.options = options
    self.meta = nil
    self.particles = {}
    self.spritePaths = {}
    self.images = {}
    self.failures = {}
    self.nvg = nil
    self.size = 50
    self.metaAttempted = false
    self.valid = false
    self.destroyed = false
    self:Init()
end

---@param key string
---@param reason string
function LatentParticles:Fail(key, reason)
    if self.failures[key] then return end
    self.failures[key] = true
    print("[LatentParticles] 错误 " .. key .. ": " .. reason)
end

--- 幂等初始化；重开时复用已解析元数据和仍有效的图片句柄。
--- Destroy 之后，Init 或下一次 LATENT Draw 仅按需重建图片句柄。
---@return boolean
function LatentParticles:Init()
    self.destroyed = false
    if self.metaAttempted then return self.valid end
    self.metaAttempted = true
    local ok, reason = pcall(function()
        local meta = self.options.meta or ReadMeta()
        assert(meta.canvas[1] == 1254 and meta.canvas[2] == 1254, "画布必须为 1254×1254")
        assert(meta.sprite_canvas_px == 50, "必须使用原始 50px 精灵画布")
        assert(meta.count == 14 and #meta.particles == meta.count, "必须保留已核准的 14 颗粒子")
        local range, periods = meta.pulse.alpha_range, meta.pulse.period_s
        assert(Finite(range[1]) and Finite(range[2]) and range[1] >= 0 and range[2] <= 1
            and range[1] <= range[2], "透明度范围无效")
        assert(Finite(periods[1]) and Finite(periods[2]) and periods[1] > 0
            and periods[1] <= periods[2], "脉冲周期范围无效")
        local counts = { dim = 0, normal = 0, bright = 0 }
        local alphaMax = range[2] --[[@as number]]
        ---@type table<string,string>
        local paths = {}
        for _, tier in ipairs(TIERS) do
            local sprite = meta.sprites[tier]
            assert(sprite == "latent_particle_" .. tier .. ".png", "档位精灵与约定不符")
            paths[tier] = "image/" .. sprite
        end
        ---@type LatentParticleDrawEntry[]
        local entries = {}
        local half = meta.sprite_canvas_px * 0.5
        for _, particle in ipairs(meta.particles) do
            assert(counts[particle.tier] and particle.sprite == meta.sprites[particle.tier], "颗粒档位无效")
            local centre, pulse = particle.centre, particle.pulse
            assert(Finite(centre[1]) and Finite(centre[2]) and centre[1] >= half and centre[2] >= half
                and centre[1] <= 1254 - half and centre[2] <= 1254 - half, "已核准中心点无效")
            assert(Finite(pulse.period_s) and pulse.period_s >= periods[1] and pulse.period_s <= periods[2]
                and Finite(pulse.phase) and Finite(pulse.alpha_min) and pulse.alpha_min >= range[1]
                and pulse.alpha_min <= range[2], "独立脉冲参数无效")
            counts[particle.tier] = counts[particle.tier] + 1
            entries[#entries + 1] = {
                path = paths[particle.tier],
                x = centre[1] - meta.canvas[1] * 0.5 - half,
                y = centre[2] - meta.canvas[2] * 0.5 - half,
                period = pulse.period_s, phase = pulse.phase,
                alphaMin = pulse.alpha_min, alphaMax = alphaMax,
            }
        end
        for _, tier in ipairs(TIERS) do
            assert(counts[tier] == meta.tiers[tier], "档位数量与元数据不符")
        end
        self.meta = meta
        self.size = meta.sprite_canvas_px
        self.spritePaths = paths
        self.particles = entries
        self.valid = true
    end)
    if not ok then self:Fail("meta", tostring(reason)) end
    return self.valid
end

function LatentParticles:ReleaseImages()
    if self.nvg then
        for path, handle in pairs(self.images) do
            if handle > 0 then
                local ok, reason = pcall(nvgDeleteImage, self.nvg, handle)
                if not ok then self:Fail("delete:" .. path, tostring(reason)) end
            end
        end
    end
    self.images = {}
    self.nvg = nil
end

---@param nvg NVGContextWrapper
function LatentParticles:LoadImages(nvg)
    if self.nvg ~= nvg then
        self:ReleaseImages()
        self.nvg = nvg
    end
    -- ImageCache.Get(path) 固定 flags=0，VU.DrawSprite 使用的也是该共享缓存。
    -- 本模块仅自持三张 NEAREST 图片，不修改共享采样方式或缓存。
    for _, tier in ipairs(TIERS) do
        local path = self.spritePaths[tier]
        if self.images[path] == nil then
            local handle = 0
            local ok, reason = pcall(function()
                handle = nvgCreateImage(nvg, path, NVG_IMAGE_NEAREST)
                assert(Finite(handle) and handle > 0, "无法加载精灵 " .. path)
                local width, height = nvgImageSize(nvg, handle)
                assert(width == self.size and height == self.size, "精灵必须为 50×50 " .. path)
            end)
            if ok then
                self.images[path] = handle
            else
                if Finite(handle) and handle > 0 then pcall(nvgDeleteImage, nvg, handle) end
                self.images[path] = 0
                self:Fail("sprite:" .. path, tostring(reason))
            end
        end
    end
end

--- 不累积时钟、不取随机数、不写细胞、不创建实体、不染色或添加发光层。
---@param nvg NVGContextWrapper
---@param cell {state:string?,infectedVisualAt:number?}
---@param time number 模拟世界时间，暂停时保持不变。
---@param alpha number? 可选父层透明度，限制在 0..1；默认为 1。
---@return boolean 是否至少绘制了一颗已核准精灵。
function LatentParticles:Draw(nvg, cell, time, alpha)
    if not nvg or not cell or (cell.state ~= "LATENT" and cell.state ~= "PRODUCTIVE") then return false end
    if not Finite(time) then return false end
    local started = cell.infectedVisualAt or 0
    if not Finite(started) then return false end
    local opacity = alpha == nil and 1 or alpha
    if not Finite(opacity) then return false end
    local parentAlpha = math.max(0.0, math.min(1.0, opacity))
    if parentAlpha == 0 then return false end
    if self.destroyed then self:Init() end
    if not self.valid then return false end
    self:LoadImages(nvg)
    local elapsed = math.max(0, time - started)
    local drawn = false
    nvgSave(nvg)
    nvgShapeAntiAlias(nvg, 0)
    nvgGlobalCompositeOperation(nvg, math.floor(NVG_SOURCE_OVER))
    for _, particle in ipairs(self.particles) do
        local handle = self.images[particle.path]
        if handle and handle > 0 then
            local wave = 0.5 + 0.5 * math.sin(elapsed * TAU / particle.period + particle.phase)
            local pulse = particle.alphaMin + (particle.alphaMax - particle.alphaMin) * wave
            local paint = nvgImagePattern(nvg, particle.x, particle.y, self.size, self.size, 0,
                handle, pulse * parentAlpha)
            nvgBeginPath(nvg)
            nvgRect(nvg, particle.x, particle.y, self.size, self.size)
            nvgFillPaint(nvg, paint)
            nvgFill(nvg)
            drawn = true
        end
    end
    nvgRestore(nvg)
    return drawn
end

--- 必须在调用方 NanoVG 上下文仍有效时调用；不销毁该上下文。
function LatentParticles:Destroy()
    if self.destroyed then return end
    self:ReleaseImages()
    self.destroyed = true
end

return LatentParticles
