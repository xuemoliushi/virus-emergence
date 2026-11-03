-- ============================================================================
-- MouseView.lua - 外观、全身解剖叠肺及肺部详情（仅表现，不推进模拟）
-- Draw 在现有 Widget:Render 的 NanoVG frame 内调用，不创建自己的 frame。
-- GetLayout 的绝对 UI base px 同时供绘图和 HUD 命中测试使用。
-- ============================================================================

local Config = require("Core.Config")
local VU = require("Game.VisualUtils")
local ImageCache = require("urhox-libs/UI/Core/ImageCache")
local LungMasks = require("Game.Views.LungRegionMasks")

---@class MouseViewRect
---@field x number
---@field y number
---@field w number
---@field h number

---@class MouseViewLayout
---@field body MouseViewRect 全身可见内容矩形（透明留白已扣除）
---@field chest MouseViewRect 解剖图胸腔叠肺及点击矩形
---@field lung MouseViewRect 当前肺矩形，随 lungProgress 从 chest 放大到详情
---@field regions table<string, MouseViewRect> 像素蒙版外接矩形，仅供文字定位；命中必须查询LungMasks.Contains

---@class MouseViewInflammationMarker
---@field id integer 权威 map.regions 的索引；双下肺共享 id=5
---@field value number 仅来自该区域 inflammation
---@field severity number 0..1 的单调视觉强度
---@field x number
---@field y number
---@field radius number
---@field alpha number
---@field red integer 纯红色深浅，绿色和蓝色始终为0
---@field phase number 本次向外扩散周期进度0..1

---@class MouseViewCrop
---@field width number 原始图片宽
---@field height number 原始图片高
---@field x number alpha>40 bbox 左上角
---@field y number
---@field w number bbox 宽
---@field h number

---@class MouseView
local MouseView = {}

-- 已测量的素材元数据；纯布局函数绝不向引擎加载素材或查询尺寸。
-- bbox 右/下边为排除端点。原图保留，使用 image pattern 的源偏移裁透明空白。
local BODY_CROP = { width = 1920, height = 1080, x = 754, y = 25, w = 415, h = 1032 }
local ANATOMY_CROP = { width = 1920, height = 1080, x = 744, y = 39, w = 437, h = 1005 }
---@type MouseViewCrop
local HEALTHY_LUNG_CROP = { width = 1671, height = 941, x = 448, y = 39, w = 777, h = 849 }
---@type MouseViewCrop[]
local LUNG_CROPS = {
    HEALTHY_LUNG_CROP,
    { width = 1672, height = 941, x = 461, y = 49, w = 745, h = 827 },
    { width = 1671, height = 941, x = 451, y = 41, w = 777, h = 845 },
    { width = 1671, height = 941, x = 442, y = 37, w = 798, h = 855 },
    { width = 1670, height = 941, x = 428, y = 21, w = 823, h = 893 },
}
local LUNG_ASPECT = HEALTHY_LUNG_CROP.w / HEALTHY_LUNG_CROP.h

-- 旧调用的兼容占位；Draw/GetLayout 不读取这个全局，状态唯一来源是 ctx.observation。
MouseView.anatomyMode = false
---@param mode boolean
function MouseView.SetAnatomyMode(mode)
    MouseView.anatomyMode = mode and true or false
end

---@param value number
---@return number
local function Clamp01(value)
    return math.max(0, math.min(1, value))
end

---@param x number
---@param y number
---@param w number
---@param h number
---@param aspect number
---@return MouseViewRect
local function FitRect(x, y, w, h, aspect)
    local fitW = math.min(w, h * aspect)
    local fitH = fitW / aspect
    return { x = x + (w - fitW) * 0.5, y = y + (h - fitH) * 0.5, w = fitW, h = fitH }
end

--- 纯确定性布局；不依赖 sim、time、素材缓存、DPR 或可变全局视图状态。
--- x/y/w/h 已是 Widget:GetAbsoluteLayout 的 base px，不再转换坐标。
--- body/anatomy 的透明 bbox 等比适配，肺详情完整适配可用视窗，不拉伸/裁肺。
---@param x number
---@param y number
---@param w number
---@param h number
---@param observation ObservationState?
---@return MouseViewLayout
function MouseView.GetLayout(x, y, w, h, observation)
    local width, height = math.max(0, w), math.max(0, h)
    -- 常规屏幕留上方 88 / 下方 150 给 HUD；矮屏按比例压缩而非挤掉主体。
    local top = math.min(88, height * 0.15)
    local bottom = math.min(150, height * 0.22)
    local side = math.min(24, width * 0.035)
    local availX, availY = x + side, y + top
    local availW, availH = math.max(0, width - side * 2), math.max(0, height - top - bottom)
    local mode = observation and observation.mode or "body"
    local bodyCrop = mode == "body" and BODY_CROP or ANATOMY_CROP
    local body = FitRect(availX, availY, availW, availH, bodyCrop.w / bodyCrop.h)

    -- 校准全身解剖图：bbox 内的胸腔中心约 (.50, .255)，肺宽为身体 .43。
    -- 叠图保留自身比例，包含顶部气道；不把肺铺成整只小鼠。
    local chestW = body.w * 0.43
    local chestH = chestW / LUNG_ASPECT
    local chest = {
        x = body.x + body.w * 0.50 - chestW * 0.5,
        y = body.y + body.h * 0.255 - chestH * 0.5,
        w = chestW, h = chestH,
    }
    local detail = FitRect(availX, availY, availW, availH, LUNG_ASPECT)
    local progress = mode ~= "body" and Clamp01(observation and observation.lungProgress or 0) or 0
    -- smoothstep 两端零速度；退出详情时也用同一插值反向回到原叠图。
    local eased = progress * progress * (3 - 2 * progress)
    local lung = {
        x = chest.x + (detail.x - chest.x) * eased,
        y = chest.y + (detail.y - chest.y) * eased,
        w = chest.w + (detail.w - chest.w) * eased,
        h = chest.h + (detail.h - chest.h) * eased,
    }
    return {
        body = body, chest = chest, lung = lung,
        regions = {
            UPPER_AIRWAY = LungMasks.Bounds("UPPER_AIRWAY", lung),
            TRACHEA = LungMasks.Bounds("TRACHEA", lung),
            DEEP_LUNG = LungMasks.Bounds("DEEP_LUNG", lung),
        },
    }
end

-- 五个真实区域的固定观察锚点，不是随机病灶，也不使用组织损伤代替炎症。
--   1 上气道顶       2 气管
--   3 左肺中         4 右肺中
--        5 双下肺（两个标记来自同一个区域值）
---@class MouseViewMarkerAnchor
---@field id integer
---@field x number
---@field y number
---@field radiusScale number
---@type MouseViewMarkerAnchor[]
local MARKER_ANCHORS = {
    { id = 1, x = 0.50, y = 0.055, radiusScale = 0.45 },
    { id = 2, x = 0.50, y = 0.24, radiusScale = 0.50 },
    { id = 3, x = 0.25, y = 0.49, radiusScale = 1.00 },
    { id = 4, x = 0.75, y = 0.49, radiusScale = 1.00 },
    { id = 5, x = 0.27, y = 0.79, radiusScale = 0.90 },
    { id = 5, x = 0.73, y = 0.79, radiusScale = 0.90 },
}

--- 只读生成局部炎症标记；零炎症不返回标记，低值微弱，阈值 8 起清晰。
--- 相同 layout/time 下，严重度增大半径与不透明度；每周期仅向外扩散然后重启。
--- time 必须是 observation.visualTime，与 sim.paused、病程 time 无关。
---@param sim SimState
---@param layout MouseViewLayout
---@param time number?
---@return MouseViewInflammationMarker[]
function MouseView.GetInflammationMarkers(sim, layout, time)
    ---@type MouseViewInflammationMarker[]
    local markers = {}
    local lung = layout.lung
    if lung.w <= 0 or lung.h <= 0 then return markers end
    local world = sim.world
    local map = world and world.map
    if not map then return markers end
    local threshold = math.max(0.001, Config.Gameplay.hotspotThreshold)
    local phase = ((time or 0) / 2.2) % 1 -- 0..1，2.2秒一轮：从中心向外扩散，不往回收缩。
    local shortSide = math.min(lung.w, lung.h)
    for _, anchor in ipairs(MARKER_ANCHORS) do
        local region = map.regions[anchor.id] --[[@as RespiratoryRegion?]]
        local value = region and math.max(0, region.inflammation) or 0
        if value > 0 then
            local severity = value / (value + threshold)
            -- RGB只含红色；病灶越严重红值越低、覆盖越浓，始终保留半透明。
            markers[#markers + 1] = {
                id = anchor.id, value = value, severity = severity, phase = phase,
                x = lung.x + lung.w * anchor.x,
                y = lung.y + lung.h * anchor.y,
                radius = shortSide * (0.04 + 0.09 * severity) * anchor.radiusScale * (0.45 + phase * 1.15),
                alpha = severity * (0.30 + 0.40 * severity) * (1 - phase * 0.78),
                red = math.floor(255 - severity * 80),
            }
        end
    end
    return markers
end

--- 在目标 rect 内等比绘制 alpha bbox；图片 pattern 偏移实现 source crop。
---@param nvg NVGContextWrapper
---@param path string?
---@param crop MouseViewCrop
---@param rect MouseViewRect
---@param alpha number
---@return boolean
local function DrawCroppedSprite(nvg, path, crop, rect, alpha)
    if not path or rect.w <= 0 or rect.h <= 0 or alpha <= 0 then return false end
    local handle = math.floor(ImageCache.Get(path))
    if handle <= 0 then return false end
    local scale = math.min(rect.w / crop.w, rect.h / crop.h)
    local drawW, drawH = crop.w * scale, crop.h * scale
    local drawX, drawY = rect.x + (rect.w - drawW) * 0.5, rect.y + (rect.h - drawH) * 0.5
    local paint = nvgImagePattern(nvg,
        drawX - crop.x * scale, drawY - crop.y * scale,
        crop.width * scale, crop.height * scale, 0, handle, alpha)
    nvgBeginPath(nvg)
    nvgRect(nvg, drawX, drawY, drawW, drawH)
    nvgFillPaint(nvg, paint)
    nvgFill(nvg)
    return true
end

---@param nvg NVGContextWrapper
---@param x number
---@param y number
---@param w number
---@param h number
local function DrawBackground(nvg, x, y, w, h)
    local background = Config.ArtSlots.mouseBackground
    if background and VU.DrawSpriteCover(nvg, background, x, y, w, h, 1) then return end
    local grad = nvgLinearGradient(nvg, x, y, x, y + h,
        VU.RGBA(Config.Palette.bgDeep), nvgRGBA(14, 10, 26, 255))
    nvgBeginPath(nvg)
    nvgRect(nvg, x, y, w, h)
    nvgFillPaint(nvg, grad)
    nvgFill(nvg)
end

---@param nvg NVGContextWrapper
---@param markers MouseViewInflammationMarker[]
local function DrawInflammation(nvg, markers)
    for _, marker in ipairs(markers) do
        -- 半透明纯红圆面随周期向四周扩散并淡出，不描边、不加粉色柔光。
        nvgBeginPath(nvg)
        nvgCircle(nvg, marker.x, marker.y, marker.radius)
        nvgFillColor(nvg, nvgRGBA(marker.red, 0, 0, math.floor(marker.alpha * 255)))
        nvgFill(nvg)
    end
end

--- 绘制仅外观模式的克制症状；鼻部表现绝不贴到肺详情上。
---@param nvg NVGContextWrapper
---@param body MouseViewRect
---@param sim SimState
---@param time number
local function DrawBodySymptoms(nvg, body, sim, time)
    local symptom = Clamp01(sim.mouse.symptom)
    local noseX, noseY = body.x + body.w * 0.5, body.y + body.h * 0.025
    if symptom > 0.35 then
        for i = 1, 3 do
            local phase = (time * 0.4 + i * 0.33) % 1
            nvgBeginPath(nvg)
            nvgCircle(nvg, noseX + 3 + phase * 6, noseY + 2 + phase * 5, 1.5 * symptom)
            nvgFillColor(nvg, VU.RGBA(Config.Palette.infectWarm, symptom * (1 - phase)))
            nvgFill(nvg)
        end
    end
    if symptom > 0.2 then
        local phase = time * (1 + symptom * 2.2) * 2
        local alpha = (0.3 + math.sin(phase) * 0.3) * symptom
        nvgBeginPath(nvg)
        nvgArc(nvg, body.x + body.w * 0.5, body.y + body.h * 0.28,
            body.w * 0.18, math.pi * 1.15, math.pi * 1.85, NVG_CW)
        nvgStrokeColor(nvg, VU.RGBA(Config.Palette.textDim, alpha))
        nvgStrokeWidth(nvg, 1.5)
        nvgStroke(nvg)
    end
end

--- 保持现有绘图签名；权威 ctx.sim 只读，所有视图状态由 observation 提供。
---@param nvg NVGContextWrapper
---@param x number
---@param y number
---@param w number
---@param h number
---@param ctx {sim: SimState, observation: ObservationState?, scaleMgr: ScaleManager, time: number, rng: fun():number}
function MouseView.Draw(nvg, x, y, w, h, ctx)
    if w <= 0 or h <= 0 then return end
    local sim = ctx.sim
    local observation = ctx.observation
    local mode = observation and observation.mode or "body"
    -- 无 observation 的旧调用只回退外观与旧计时，不读取全局 anatomyMode。
    local visualTime = observation and observation.visualTime or ctx.time or 0
    local progress = mode ~= "body" and Clamp01(observation and observation.lungProgress or 0) or 0
    local eased = progress * progress * (3 - 2 * progress)
    local layout = MouseView.GetLayout(x, y, w, h, observation)

    nvgSave(nvg)
    nvgIntersectScissor(nvg, x, y, w, h)
    DrawBackground(nvg, x, y, w, h)
    if mode == "body" then
        if DrawCroppedSprite(nvg, Config.ArtSlots.mouseSprite, BODY_CROP, layout.body, 1) then
            DrawBodySymptoms(nvg, layout.body, sim, visualTime)
        end
    else
        -- 全身解剖在放大过程中逐渐淡出；初始肺与胸腔叠图完全是同一矩形。
        DrawCroppedSprite(nvg, Config.ArtSlots.mouseAnatomy, ANATOMY_CROP, layout.body, 1 - eased)
        -- 0..4 原素材只表示整体病程底图；红圈始终取局部 map.regions 炎症。
        local stage = 1 + math.floor(Clamp01(sim.victoryProgress or 0) * 4.999)
        if sim.ending == "victory" then stage = 5 end
        local path = Config.ArtSlots.lungStages[stage]
        local crop = LUNG_CROPS[stage] or HEALTHY_LUNG_CROP
        local drew = DrawCroppedSprite(nvg, path, crop, layout.lung, 1)
        if drew and mode == "lung" then
            DrawInflammation(nvg, MouseView.GetInflammationMarkers(sim, layout, visualTime))
        end
    end

    -- 保留胜利锁定后的死亡暗化，不借由视图改变结局或 world。
    if sim.ending == "victory" then
        nvgBeginPath(nvg)
        nvgRect(nvg, x, y, w, h)
        nvgFillColor(nvg, nvgRGBA(0, 0, 0, 115))
        nvgFill(nvg)
    end
    nvgRestore(nvg)
end

return MouseView
