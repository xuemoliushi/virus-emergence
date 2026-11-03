-- ============================================================================
-- VisualUtils.lua - 占位矢量绘制工具（正式美术到位前的所有程序化图形）
--
-- 依据美术风格规范:
--   §3 组织背景: 近黑深紫基底 + 微弱分支纤维 + 半透明斑块 + 稀疏颗粒
--   §4 细胞造型: 不规则扁平有机形态，红色颗粒膜 + 暗内部 + 原色液泡
--   §7 发光克制: 荧光只用于轮廓和正在发生的事件
--
-- 🎨 美术挂载位: 本模块所有 Draw* 函数在正式素材到位后可替换为贴图绘制
--    （贴图路径登记在 Config.ArtSlots，替换时保持函数签名不变）
-- ============================================================================

local Config = require("Core.Config")
local ImageCache = require("urhox-libs/UI/Core/ImageCache")

---@class VisualUtils
local VU = {}

-- ============================================================================
-- 贴图绘制（美术挂载位: 有素材用贴图，无素材/加载失败返回 false 由调用方回退矢量）
-- ============================================================================

--- 以中心点绘制一张透明底贴图
---@param nvg NVGContextWrapper
---@param path string Config.ArtSlots 中登记的路径（相对资源根）
---@param cx number 中心 x
---@param cy number 中心 y
---@param size number 绘制边长（正方形）
---@param alpha number? 透明度 0..1
---@param rot number? 旋转弧度
---@return boolean 是否成功绘制（false = 调用方应回退矢量绘制）
function VU.DrawSprite(nvg, path, cx, cy, size, alpha, rot)
    if not path then return false end
    local handle = ImageCache.Get(path)
    if not handle or handle == 0 then return false end

    local half = size / 2
    nvgSave(nvg)
    nvgTranslate(nvg, cx, cy)
    if rot and rot ~= 0 then nvgRotate(nvg, rot) end
    local paint = nvgImagePattern(nvg, -half, -half, size, size, 0, handle, alpha or 1.0)
    nvgBeginPath(nvg)
    nvgRect(nvg, -half, -half, size, size)
    nvgFillPaint(nvg, paint)
    nvgFill(nvg)
    nvgRestore(nvg)
    return true
end

--- Draw a region of a centred source canvas using the parent's full transform.
--- The path clips in cell coordinates; intersecting screen scissors would expand
--- a rotated region and expose the neighbouring atlas/base pixels.
---@param nvg NVGContextWrapper
---@param path string
---@param canvasSize number
---@param rect number[]
---@param alpha number
---@return boolean
function VU.DrawSpriteRegion(nvg, path, canvasSize, rect, alpha)
    local handle = ImageCache.Get(path)
    if not handle or handle == 0 then return false end
    nvgBeginPath(nvg)
    nvgRect(nvg, rect[1], rect[2], rect[3], rect[4])
    local paint = nvgImagePattern(nvg, -canvasSize/2, -canvasSize/2,
        canvasSize, canvasSize, 0, handle, alpha)
    nvgFillPaint(nvg, paint)
    nvgFill(nvg)
    return true
end

--- 以中心点在给定矩形内等比适配绘制贴图（不拉伸变形）
---@param nvg NVGContextWrapper
---@param path string
---@param cx number 中心 x
---@param cy number 中心 y
---@param maxW number 可用宽
---@param maxH number 可用高
---@param alpha number?
---@param scaleX number? 额外缩放（呼吸等）
---@param scaleY number?
---@param tint integer[]? 乘法叠色 {r,g,b}（nil = 原色）
---@return boolean
function VU.DrawSpriteFit(nvg, path, cx, cy, maxW, maxH, alpha, scaleX, scaleY, tint)
    if not path then return false end
    local handle = ImageCache.Get(path)
    if not handle or handle == 0 then return false end
    local iw, ih = ImageCache.GetSize(path)
    if not iw or iw <= 0 or not ih or ih <= 0 then return false end

    local s = math.min(maxW / iw, maxH / ih)
    local dw = iw * s * (scaleX or 1)
    local dh = ih * s * (scaleY or 1)
    nvgSave(nvg)
    local paint
    if tint then
        paint = nvgImagePatternTinted(nvg, cx - dw / 2, cy - dh / 2, dw, dh, 0,
            handle, nvgRGBA(tint[1], tint[2], tint[3], math.floor(255 * (alpha or 1.0))))
    else
        paint = nvgImagePattern(nvg, cx - dw / 2, cy - dh / 2, dw, dh, 0,
            handle, alpha or 1.0)
    end
    nvgBeginPath(nvg)
    nvgRect(nvg, cx - dw / 2, cy - dh / 2, dw, dh)
    nvgFillPaint(nvg, paint)
    nvgFill(nvg)
    nvgRestore(nvg)
    return true
end

--- 将贴图按 cover 比例铺满矩形；裁切超出部分，不拉伸图像。
---@param nvg NVGContextWrapper
---@param path string 贴图资源路径（相对资源根目录）
---@param x number 目标矩形左上角 x
---@param y number 目标矩形左上角 y
---@param width number 目标矩形宽度
---@param height number 目标矩形高度
---@param alpha number? 透明度 0..1
---@return boolean
function VU.DrawSpriteCover(nvg, path, x, y, width, height, alpha)
    if not path or width <= 0 or height <= 0 then return false end
    local handle = ImageCache.Get(path)
    if not handle or handle == 0 then return false end
    local imageW, imageH = ImageCache.GetSize(path)
    if not imageW or imageW <= 0 or not imageH or imageH <= 0 then return false end

    local scale = math.max(width / imageW, height / imageH)
    local drawW, drawH = imageW * scale, imageH * scale
    local drawX, drawY = x + (width - drawW) * 0.5, y + (height - drawH) * 0.5
    nvgSave(nvg)
    nvgIntersectScissor(nvg, x, y, width, height)
    local paint = nvgImagePattern(nvg, drawX, drawY, drawW, drawH, 0, handle, alpha or 1.0)
    nvgBeginPath(nvg)
    nvgRect(nvg, drawX, drawY, drawW, drawH)
    nvgFillPaint(nvg, paint)
    nvgFill(nvg)
    nvgRestore(nvg)
    return true
end

--- 查询贴图原始尺寸（用于在绘制外定位叠加特效）
---@param path string
---@return number iw
---@return number ih
function VU.GetSpriteSize(path)
    if not path then return 0, 0 end
    return ImageCache.GetSize(path)
end

--- 以中心点绘制贴图并做乘法叠色（变异后感染细胞整体变色用）
---@param nvg NVGContextWrapper
---@param path string
---@param cx number
---@param cy number
---@param size number
---@param tint integer[] {r,g,b} 0..255 乘法叠色（255,255,255 = 原色）
---@param alpha number?
---@return boolean
function VU.DrawSpriteTinted(nvg, path, cx, cy, size, tint, alpha)
    if not path then return false end
    local handle = ImageCache.Get(path)
    if not handle or handle == 0 then return false end

    local half = size / 2
    nvgSave(nvg)
    nvgTranslate(nvg, cx, cy)
    local paint = nvgImagePatternTinted(nvg, -half, -half, size, size, 0, handle,
        nvgRGBA(tint[1], tint[2], tint[3], math.floor(255 * (alpha or 1.0))))
    nvgBeginPath(nvg)
    nvgRect(nvg, -half, -half, size, size)
    nvgFillPaint(nvg, paint)
    nvgFill(nvg)
    nvgRestore(nvg)
    return true
end

-- ============================================================================
-- 确定性伪随机（不污染全局 math.random，模拟与纹理各自独立）
-- ============================================================================

--- 创建独立随机数生成器
---@param seed integer
---@return fun(): number 返回 [0,1) 的随机数
function VU.MakeRng(seed)
    local s = seed % 2147483647
    if s <= 0 then s = s + 2147483646 end
    return function()
        s = (s * 48271) % 2147483647
        return (s - 1) / 2147483646
    end
end

-- ============================================================================
-- 颜色辅助
-- ============================================================================

--- 调色板颜色 → NanoVG 颜色（可乘透明度）
---@param c integer[] {r,g,b,a}
---@param alphaMul number? 透明度倍率 0..1
---@return NVGcolor
function VU.RGBA(c, alphaMul)
    local a = c[4] * (alphaMul or 1.0)
    return nvgRGBA(c[1], c[2], c[3], math.floor(math.max(0, math.min(255, a))))
end

--- 两个 RGBA 表插值（用于状态过渡色）
---@param a integer[]
---@param b integer[]
---@param t number 0..1
---@return integer[] {r,g,b,a}
function VU.LerpColor(a, b, t)
    t = math.max(0, math.min(1, t))
    return {
        math.floor(a[1] + (b[1] - a[1]) * t),
        math.floor(a[2] + (b[2] - a[2]) * t),
        math.floor(a[3] + (b[3] - a[3]) * t),
        math.floor(a[4] + (b[4] - a[4]) * t),
    }
end

-- ============================================================================
-- 发光（克制的局部荧光）
-- ============================================================================

--- 径向发光斑
---@param nvg NVGContextWrapper
---@param x number
---@param y number
---@param rInner number
---@param rOuter number
---@param c integer[] RGBA 表
---@param alpha number 0..1
function VU.DrawGlow(nvg, x, y, rInner, rOuter, c, alpha)
    if not nvgRadialGradient or rOuter <= 0 or alpha <= 0 then return false end
    local paint = nvgRadialGradient(nvg, x, y, rInner, rOuter,
        VU.RGBA(c, alpha), VU.RGBA(c, 0))
    nvgBeginPath(nvg)
    nvgCircle(nvg, x, y, rOuter)
    nvgFillPaint(nvg, paint)
    nvgFill(nvg)
    return true
end

-- ============================================================================
-- 组织纹理（背景微结构，细胞层与组织层共用）
-- ============================================================================

---@class TissueTexture
---@field fibers { pts: number[][], w: number, alpha: number }[]
---@field patches { x: number, y: number, rx: number, ry: number, rot: number, alpha: number }[]
---@field granules { x: number, y: number, r: number, alpha: number, phase: number }[]

--- 生成组织纹理（归一化坐标 0..1）
---@param seed integer
---@return TissueTexture
function VU.MakeTissueTexture(seed)
    local rng = VU.MakeRng(seed)
    ---@type TissueTexture
    local tex = { fibers = {}, patches = {}, granules = {} }

    -- 分支纤维: 折线，有方向感
    for _ = 1, 14 do
        local x, y = rng(), rng()
        local ang = rng() * math.pi * 2
        ---@type number[][]
        local pts = { { x, y } }
        local segments = 3 + math.floor(rng() * 4)
        for _ = 1, segments do
            ang = ang + (rng() - 0.5) * 1.4
            local len = 0.04 + rng() * 0.08
            x = x + math.cos(ang) * len
            y = y + math.sin(ang) * len
            pts[#pts + 1] = { x, y }
        end
        tex.fibers[#tex.fibers + 1] =
            { pts = pts, w = 0.5 + rng() * 1.0, alpha = 0.25 + rng() * 0.3 }
    end

    -- 半透明流体斑块
    for _ = 1, 7 do
        tex.patches[#tex.patches + 1] = {
            x = rng(), y = rng(),
            rx = 0.05 + rng() * 0.12, ry = 0.03 + rng() * 0.08,
            rot = rng() * math.pi, alpha = 0.10 + rng() * 0.12,
        }
    end

    -- 稀疏颗粒（缓慢漂移，规范 §9）
    for _ = 1, 40 do
        tex.granules[#tex.granules + 1] = {
            x = rng(), y = rng(),
            r = 0.5 + rng() * 1.2,
            alpha = 0.15 + rng() * 0.3,
            phase = rng() * math.pi * 2,
        }
    end

    return tex
end

--- 绘制组织背景（基底 + 斑块 + 纤维 + 颗粒）
---@param nvg NVGContextWrapper
---@param x number 画布左上角 x（base px）
---@param y number 画布左上角 y
---@param w number 画布宽
---@param h number 画布高
---@param tex TissueTexture
---@param time number 用于颗粒缓慢漂移
function VU.DrawTissueBackground(nvg, x, y, w, h, tex, time)
    local P = Config.Palette

    -- 基底: 近黑 → 深紫渐变
    local grad = nvgLinearGradient(nvg, x, y, x + w * 0.4, y + h,
        VU.RGBA(P.bgDeep), VU.RGBA(P.bgViolet))
    nvgBeginPath(nvg)
    nvgRect(nvg, x, y, w, h)
    nvgFillPaint(nvg, grad)
    nvgFill(nvg)

    -- 半透明流体斑块
    for _, patch in ipairs(tex.patches) do
        nvgSave(nvg)
        nvgTranslate(nvg, x + patch.x * w, y + patch.y * h)
        nvgRotate(nvg, patch.rot)
        nvgBeginPath(nvg)
        nvgEllipse(nvg, 0, 0, patch.rx * w, patch.ry * h)
        nvgFillColor(nvg, VU.RGBA(P.bgViolet, patch.alpha * 2.2))
        nvgFill(nvg)
        nvgRestore(nvg)
    end

    -- 分支纤维（低对比度）
    for _, fiber in ipairs(tex.fibers) do
        nvgBeginPath(nvg)
        local p0 = fiber.pts[1]
        nvgMoveTo(nvg, x + p0[1] * w, y + p0[2] * h)
        for i = 2, #fiber.pts do
            local p = fiber.pts[i]
            nvgLineTo(nvg, x + p[1] * w, y + p[2] * h)
        end
        nvgStrokeColor(nvg, VU.RGBA(P.bgFiber, fiber.alpha))
        nvgStrokeWidth(nvg, fiber.w)
        nvgStroke(nvg)
    end

    -- 稀疏颗粒（缓慢漂移）
    for _, g in ipairs(tex.granules) do
        local drift = math.sin(time * 0.08 + g.phase) * 0.004
        nvgBeginPath(nvg)
        nvgCircle(nvg, x + (g.x + drift) * w, y + g.y * h, g.r)
        nvgFillColor(nvg, VU.RGBA(P.bgGranule, g.alpha))
        nvgFill(nvg)
    end
end

-- ============================================================================
-- 细胞形状（不规则有机轮廓）
-- ============================================================================

---@class CellShape 极坐标半径扰动谐波 { amp, freq, phase }[]

--- 生成细胞轮廓形状参数
---@param rng fun(): number
---@return CellShape
function VU.MakeCellShape(rng)
    ---@type CellShape
    local shape = {}
    for _ = 1, 5 do
        shape[#shape + 1] = {
            amp = 0.03 + rng() * 0.09,
            freq = 2 + math.floor(rng() * 4),
            phase = rng() * math.pi * 2,
        }
    end
    return shape
end

--- 计算轮廓半径
---@param shape CellShape
---@param theta number 极角
---@param baseR number 基础半径
---@param wobble number 流体波动幅度（随时间）
---@return number
function VU.CellRadius(shape, theta, baseR, wobble)
    local r = baseR
    for _, h in ipairs(shape) do
        r = r + baseR * h.amp * math.sin(h.freq * theta + h.phase + wobble)
    end
    return r
end

--- 生成细胞轮廓路径（调用后直接 fill/stroke）
---@param nvg NVGContextWrapper
---@param cx number
---@param cy number
---@param shape CellShape
---@param baseR number
---@param wobble number
function VU.CellPath(nvg, cx, cy, shape, baseR, wobble)
    local steps = 40
    nvgBeginPath(nvg)
    for i = 0, steps do
        local theta = (i / steps) * math.pi * 2
        local r = VU.CellRadius(shape, theta, baseR, wobble)
        local px = cx + math.cos(theta) * r
        local py = cy + math.sin(theta) * r
        if i == 0 then
            nvgMoveTo(nvg, px, py)
        else
            nvgLineTo(nvg, px, py)
        end
    end
    nvgClosePath(nvg)
end

return VU
