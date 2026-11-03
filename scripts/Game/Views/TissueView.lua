-- ============================================================================
-- TissueView.lua - 组织层视图（占位矢量绘制）
--
-- 依据玩法文档 §4 组织层:
--   展示一小片呼吸道组织中的感染分布、局部损伤和免疫响应
--   玩家在这一层点击选择策略作用区域，观察感染点形成与扩展
--   首版只模拟有限的几个相邻区域（Config.Sim.regionCount = 3）
-- 依据美术规范: 深色基底 + 冷暖状态色，区域间用微结构自然分隔
--
-- 🎨 美术挂载位: Config.ArtSlots.tissueBg 有值时替换背景为贴图
-- ============================================================================

local Config = require("Core.Config")
local VU = require("Game.VisualUtils")

-- This retained view consumes the legacy tissue summary, not map geometry.
---@class LegacyTissueRegion
---@field index integer
---@field infected number
---@field dead number
---@field damage number
---@field immune number
---@field virus number
---@field fluidSpeed number?
---@field strains table
---@field recognition number

---@class TissueView
local TissueView = {}

-- 模块级纹理缓存（Start 时生成一次，避免每帧重建）
---@type TissueTexture?
local texture_ = nil

--- 区域几何（画布内归一化布局）
--- 玩法新 §6: 2×2 相邻四区 [A 起始]-[B 通道] / [C 易感]-[D 高监视]，
--- 同一片连续组织中的四个计算区域（不是四个独立房间）
---@param x number
---@param y number
---@param w number
---@param h number
---@return { cx:number, cy:number, rx:number, ry:number }[]
function TissueView.RegionLayout(x, y, w, h)
    local regions = {}
    -- A 左上 / B 右上 / C 左下 / D 右下
    local positions = { { 0.30, 0.32 }, { 0.70, 0.30 }, { 0.30, 0.70 }, { 0.70, 0.70 } }
    local radii     = { { 0.17, 0.24 }, { 0.17, 0.24 }, { 0.17, 0.24 }, { 0.17, 0.24 } }
    for i = 1, Config.Sim.regionCount do
        local pos = positions[i] or { 0.5, 0.5 }
        local rad = radii[i] or { 0.17, 0.24 }
        regions[i] = {
            cx = x + pos[1] * w,
            cy = y + pos[2] * h,
            rx = rad[1] * w,
            ry = rad[2] * h,
        }
    end
    return regions
end

--- 画布坐标 → 区域序号（点击命中用）
---@param px number 画布内 x
---@param py number 画布内 y
---@param x number 画布区域
---@param y number
---@param w number
---@param h number
---@return integer? 命中的区域序号，未命中返回 nil
function TissueView.HitTestRegion(px, py, x, y, w, h)
    ---@type {cx:number,cy:number,rx:number,ry:number}[]
    local layout = TissueView.RegionLayout(x, y, w, h)
    for i, reg in ipairs(layout) do
        local dx = (px - reg.cx) / reg.rx
        local dy = (py - reg.cy) / reg.ry
        if dx * dx + dy * dy <= 1.0 then
            return i
        end
    end
    return nil
end

--- 绘制组织层
---@param nvg NVGContextWrapper
---@param x number
---@param y number
---@param w number
---@param h number
---@param ctx {sim:{regions:LegacyTissueRegion[],strategyRegion:number},scaleMgr:ScaleManager,time:number,hover:{x:number,y:number}?}
function TissueView.Draw(nvg, x, y, w, h, ctx)
    local P = Config.Palette
    local sim = ctx.sim

    -- 纹理只生成一次
    if not texture_ then
        texture_ = VU.MakeTissueTexture(20261002)
    end

    -- 组织背景（与细胞层同一套微结构语言，保证尺度间连续性）
    VU.DrawTissueBackground(nvg, x, y, w, h, texture_, ctx.time)

    ---@type {cx:number,cy:number,rx:number,ry:number}[]
    local layout = TissueView.RegionLayout(x, y, w, h)

    -- 流体通道（玩法新 §8.1: 低亮度流体路径，B 通道区更明显）
    for i, reg in ipairs(layout) do
        local def = Config.Regions[i]
        if def then
            local fd = def.fluidDir
            local alpha = 0.10 + def.fluidSpeed * 0.18
            for k = -1, 1 do
                local ox, oy = -fd[2] * k * reg.ry * 0.35, fd[1] * k * reg.rx * 0.35
                nvgBeginPath(nvg)
                nvgMoveTo(nvg, reg.cx - fd[1] * reg.rx * 0.9 + ox,
                    reg.cy - fd[2] * reg.ry * 0.9 + oy)
                nvgLineTo(nvg, reg.cx + fd[1] * reg.rx * 0.9 + ox,
                    reg.cy + fd[2] * reg.ry * 0.9 + oy)
                nvgStrokeColor(nvg, VU.RGBA(P.bgFiber, alpha))
                nvgStrokeWidth(nvg, 2.5)
                nvgStroke(nvg)
            end
        end
    end

    for i, reg in ipairs(layout) do
        local r = sim.regions[i]
        if r then
            local hovered = ctx.hover
                and TissueView.HitTestRegion(ctx.hover.x, ctx.hover.y, x, y, w, h) == i
            TissueView.DrawRegion(nvg, reg, r, ctx, i == sim.strategyRegion, hovered)
        end
    end

    -- 区域间连接通道（2×2 相邻: A-B, A-C, B-D, C-D，表现同一片连续组织）
    ---@type integer[][]
    local links = { { 1, 2 }, { 1, 3 }, { 2, 4 }, { 3, 4 } }
    for _, pair in ipairs(links) do
        local firstId = pair[1] --[[@as integer]]
        local lastId = pair[2] --[[@as integer]]
        local a, b = layout[firstId], layout[lastId]
        if a and b then
            nvgBeginPath(nvg)
            nvgMoveTo(nvg, a.cx, a.cy)
            nvgBezierTo(nvg,
                (a.cx + b.cx) / 2, a.cy - h * 0.04,
                (a.cx + b.cx) / 2, b.cy + h * 0.04,
                b.cx, b.cy)
            nvgStrokeColor(nvg, VU.RGBA(P.bgFiber, 0.6))
            nvgStrokeWidth(nvg, 2)
            nvgStroke(nvg)
        end
    end
end

--- 数值 → 低/中/高 等级（玩法新 §6.3 区域反馈）
---@param v number
---@param mid number
---@param high number
---@return string
local function Level(v, mid, high)
    if v >= high then return "高" end
    if v >= mid then return "中" end
    return "低"
end

--- 绘制单个组织区域（感染分布 + 损伤 + 免疫 + 选中态 + 悬停信息）
---@param nvg NVGContextWrapper
---@param reg { cx:number, cy:number, rx:number, ry:number }
---@param r LegacyTissueRegion
---@param ctx table
---@param isSelected boolean
---@param hovered boolean?
function TissueView.DrawRegion(nvg, reg, r, ctx, isSelected, hovered)
    local P = Config.Palette
    local totalCells = Config.Sim.initSusceptible
    local infectRatio = math.min(1, r.infected / totalCells)
    local deadRatio = math.min(1, r.dead / totalCells)
    local damageRatio = math.min(1, r.damage / totalCells)

    -- 区域底色: 健康深绿 → 感染暖色（感染比例驱动）
    local baseColor = VU.LerpColor(
        { 20, 44, 32, 200 },        -- 健康组织底色
        { 70, 40, 22, 210 },        -- 感染底色
        infectRatio * 2)
    baseColor = VU.LerpColor(baseColor, { 46, 34, 58, 210 }, deadRatio)  -- 死亡 → 灰紫

    nvgBeginPath(nvg)
    nvgEllipse(nvg, reg.cx, reg.cy, reg.rx, reg.ry)
    nvgFillColor(nvg, VU.RGBA(baseColor))
    nvgFill(nvg)

    -- 感染热点: 区域中心偏移处的暖色光斑（规范: 感染是局部事件）
    if infectRatio > 0.01 then
        local hotX = reg.cx + reg.rx * 0.15
        local hotY = reg.cy - reg.ry * 0.1
        VU.DrawGlow(nvg, hotX, hotY,
            reg.rx * 0.1, reg.rx * (0.4 + infectRatio * 0.7),
            P.infectGlow, math.min(0.7, infectRatio * 2.5))
    end

    -- 免疫响应: 冷青色边缘脉冲（免疫压力高时出现）
    if r.immune > 0.15 then
        local pulse = 0.5 + math.sin(ctx.time * 3.0 + reg.cx) * 0.5
        local alpha = math.min(0.6, r.immune * 0.5) * (0.6 + pulse * 0.4)
        nvgBeginPath(nvg)
        nvgEllipse(nvg, reg.cx, reg.cy, reg.rx, reg.ry)
        nvgStrokeColor(nvg, VU.RGBA(P.immuneCool, alpha))
        nvgStrokeWidth(nvg, 2.5)
        nvgStroke(nvg)

        -- 少量免疫细胞小点
        local count = math.min(6, math.floor(r.immune * 5))
        for i = 1, count do
            local ang = (i / count) * math.pi * 2 + ctx.time * 0.3
            local px = reg.cx + math.cos(ang) * reg.rx * 0.7
            local py = reg.cy + math.sin(ang) * reg.ry * 0.7
            nvgBeginPath(nvg)
            nvgCircle(nvg, px, py, 2.5)
            nvgFillColor(nvg, VU.RGBA(P.immuneCool, 0.9))
            nvgFill(nvg)
        end
    end

    -- 损伤表现: 暗色破碎纹理（简单用几条暗色短线）
    if damageRatio > 0.15 then
        local rng = VU.MakeRng(reg.cx * 100 + 7)   -- 确定性，避免每帧跳变
        local cracks = math.floor(damageRatio * 8)
        for i = 1, cracks do
            local ang = rng() * math.pi * 2
            local dist = rng() * 0.8
            local px = reg.cx + math.cos(ang) * reg.rx * dist
            local py = reg.cy + math.sin(ang) * reg.ry * dist
            nvgBeginPath(nvg)
            nvgMoveTo(nvg, px, py)
            nvgLineTo(nvg, px + (rng() - 0.5) * 14, py + (rng() - 0.5) * 14)
            nvgStrokeColor(nvg, VU.RGBA(P.damaged, 0.7))
            nvgStrokeWidth(nvg, 1.5)
            nvgStroke(nvg)
        end
    end

    -- 选中态: 虚线感的双环（玩家策略作用区域）
    if isSelected then
        local pulse = 0.7 + math.sin(ctx.time * 2.5) * 0.3
        nvgBeginPath(nvg)
        nvgEllipse(nvg, reg.cx, reg.cy, reg.rx + 6, reg.ry + 6)
        nvgStrokeColor(nvg, VU.RGBA(P.textMain, 0.5 * pulse))
        nvgStrokeWidth(nvg, 1.5)
        nvgStroke(nvg)

        nvgBeginPath(nvg)
        nvgEllipse(nvg, reg.cx, reg.cy, reg.rx + 10, reg.ry + 10)
        nvgStrokeColor(nvg, VU.RGBA(P.textMain, 0.25 * pulse))
        nvgStrokeWidth(nvg, 1)
        nvgStroke(nvg)
    end

    -- 区域编号 + 名称（帮助玩家跨尺度识别"刚才观察的感染区域"）
    local def = Config.Regions[r.index] or {}
    nvgFontFace(nvg, "sans")
    nvgFontSize(nvg, 13)
    nvgTextAlign(nvg, NVG_ALIGN_CENTER + NVG_ALIGN_MIDDLE)
    nvgFillColor(nvg, VU.RGBA(P.textDim, 0.9))
    nvgText(nvg, reg.cx, reg.cy + reg.ry + 16, def.name or ("区域 " .. r.index))

    -- 表型三进度条（附着=绿 / 复制=橙 / 隐匿=紫）
    if ctx.sim and ctx.sim.DominantPhenotype then
        local att, rep, ste = ctx.sim:DominantPhenotype(r.index)
        local barW, barH = 48, 4
        local bx0 = reg.cx - barW / 2
        local by0 = reg.cy + reg.ry + 25
        local bars = {
            { v = att, c = { 80, 200, 100, 200 } },
            { v = rep, c = { 230, 140, 50,  200 } },
            { v = ste, c = { 160, 100, 230, 200 } },
        }
        for bi, bar in ipairs(bars) do
            local bx = bx0
            local by = by0 + (bi - 1) * (barH + 3)
            nvgBeginPath(nvg)
            nvgRect(nvg, bx, by, barW, barH)
            nvgFillColor(nvg, VU.RGBA({ 40, 40, 40, 140 }))
            nvgFill(nvg)
            nvgBeginPath(nvg)
            nvgRect(nvg, bx, by, barW * math.max(0, math.min(1, bar.v)), barH)
            nvgFillColor(nvg, VU.RGBA(bar.c))
            nvgFill(nvg)
        end
    end

    -- 悬停信息（玩法新 §18.1: 名称 + 四项等级 + 区域提示）
    if hovered then
        -- 基础行
        local lines = {
            def.name or ("区域 " .. r.index),
            "病毒活动: " .. Level(r.virus, 15, 50),
            "感染程度: " .. Level(r.infected, 10, 30),
            "免疫压力: " .. Level(r.immune, 0.4, 1.0),
            "组织损伤: " .. Level(r.damage, 25, 60),
            "流动: " .. Level(r.fluidSpeed or 0.5, 0.45, 0.8),
        }
        -- 表型 + 毒株信息（有 DominantPhenotype 时追加）
        if ctx.sim and ctx.sim.DominantPhenotype then
            local att, rep, ste = ctx.sim:DominantPhenotype(r.index)
            local sc  = #(r.strains or {})
            local rec = r.recognition or 1.0
            lines[#lines + 1] = string.format(
                "表型 附%.0f%% 复%.0f%% 隐%.0f%%  株%d",
                att * 100, rep * 100, ste * 100, sc)
            lines[#lines + 1] = string.format(
                "免疫识别率: %.0f%%%s",
                rec * 100, rec < 0.6 and " ⚠逃逸" or "")
        end
        if def.tip and def.tip ~= "" then
            lines[#lines + 1] = def.tip
        end
        local bw, bh = 200, 20 + #lines * 17
        local bx = math.min(reg.cx + reg.rx * 0.4, ctx.w - bw - 8)
        local by = math.max(8, reg.cy - bh / 2)
        nvgBeginPath(nvg)
        nvgRect(nvg, bx, by, bw, bh)
        nvgFillColor(nvg, VU.RGBA(P.panelBg, 0.95))
        nvgFill(nvg)
        nvgStrokeColor(nvg, VU.RGBA(P.panelBorder))
        nvgStrokeWidth(nvg, 1)
        nvgStroke(nvg)
        nvgTextAlign(nvg, NVG_ALIGN_LEFT + NVG_ALIGN_TOP)
        for i, line in ipairs(lines) do
            nvgFontSize(nvg, i == 1 and 13 or 11)
            -- 逃逸行高亮橙色
            local isEscapeLine = (line:find("逃逸") ~= nil)
            nvgFillColor(nvg, VU.RGBA(
                isEscapeLine and { 255, 160, 80, 255 } or
                (i == 1 and P.textMain or P.textDim)))
            nvgText(nvg, bx + 10, by + 8 + (i - 1) * 17, line)
        end
    end
end

return TissueView
