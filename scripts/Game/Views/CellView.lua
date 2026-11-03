-- ============================================================================
-- CellView.lua - 感染网络的只读真实实体渲染（米制世界 -> Widget base px）
-- Widget.Render 拥有 NanoVG 帧、DPR 缩放和字体；这里不创建上下文 / 帧 / 字体。
-- 不推进世界、不改实体、不按 mass / 统计补粒子；环境微粒和残膜不是病毒。
-- ============================================================================

local Config = require("Core.Config")
local VU = require("Game.VisualUtils")
local Theme = require("urhox-libs/UI/Core/Theme")
local CellSurface = require("Game.Views.CellSurface")
local LatentParticles = require("Game.Views.LatentParticles")
local CellDiagnostics = require("Core.CellDiagnostics")
local BuddingVisual = require("Game.Views.BuddingVisual")
local TissueArt = require("Game.Views.TissueArt")
local AttachmentVisual = require("Game.Views.AttachmentVisual")
local PerformanceStats = require("Core.PerformanceStats")
local Bioluminescence = require("Game.Views.Bioluminescence")
local SwarmVisualPhysics = require("Game.SwarmVisualPhysics")
local CellVitality = require("Game.Views.CellVitality")

local TAU = math.pi * 2
local EMPTY = {}
local AI_LABELS = { relay = "接力感染", flee = "避敌", seek = "移动", infect = "感染", collect = "移动", wander = "等待", idle = "等待", disabled = "等待" }
-- 三层统一以原1254画布绘制；760是膜主体参考直径，不独立补偿任何图层留白。
local CELL_CANVAS = 1254
local CELL_DIAMETER = 760
-- 组织流使用青蓝薄带；低于冷色免疫轮廓亮度，且始终在实体/警戒范围下面绘制。
local FLOW_COLOR = { 48, 155, 181, 255 }
local FLOW_MARK = { 174, 222, 233, 255 }
local TIRED_TINT = { 126, 96, 158 }
local WHITE_TINT = { 255, 255, 255, 255 }

---@param slots string|string[]|nil
---@param variant number?
---@return string? path
---@return integer index
local function artSlot(slots, variant)
    if type(slots) == "table" then
        if #slots == 0 then return nil, 1 end
        local index = (math.floor(variant or 1) - 1) % #slots + 1
        return slots[index], index
    end
    return slots, 1
end

---@param value number
---@return number
local function unit(value)
    return math.max(0, math.min(1, value))
end

---@param value number
---@return number
local function smoothstep(value)
    local t = unit(value)
    return t * t * (3 - 2 * t)
end

---@param x number
---@param y number
---@param radius number
---@param l Rect4
---@return boolean
local function onScreen(x, y, radius, l)
    return x + radius >= l.x and x - radius <= l.x + l.w
        and y + radius >= l.y and y - radius <= l.y + l.h
end

---@param x number
---@param y number
---@param rx number
---@param ry number
---@param l Rect4
---@return boolean
local function ellipseOnScreen(x, y, rx, ry, l)
    return x + rx >= l.x and x - rx <= l.x + l.w
        and y + ry >= l.y and y - ry <= l.y + l.h
end

---@param virus table
---@return boolean
local function liveReleased(virus)
    return virus.state ~= "CLEARED" and virus.state ~= "LOST" and virus.state ~= "ABSORBED" and virus.state ~= "CONVERTED"
end

--- 世界 map 的实际包含测试只用于裁剪装饰，不用于碰撞或生成实体。
---@param map table
---@param x number
---@param y number
---@return boolean
local function inTissue(map, x, y)
    if map.Contains then return map:Contains(x, y, 0) end
    return true
end

--- 图内锚点标注，不创建 UI 树 / 字体，不乘 DPR 或镜头 zoom。
---@param nvg NVGContextWrapper
---@param x number
---@param y number
---@param text string
---@param color integer[]
---@param alpha number
---@param size number?
local function mapText(nvg, x, y, text, color, alpha, size)
    nvgSave(nvg)
    nvgFontFace(nvg, Theme.FontFace(nil, "normal"))
    nvgFontSize(nvg, Theme.FontSize(size or 9))
    nvgTextAlign(nvg, NVG_ALIGN_CENTER + NVG_ALIGN_MIDDLE)
    -- 小幅暗色阴影保证暖色粒子 / 绿色膜上的可读性，不遮住大块地图。
    nvgFillColor(nvg, VU.RGBA(Config.Palette.bgDeep, alpha * 0.85))
    nvgText(nvg, x + 1, y + 1, text, nil)
    nvgFillColor(nvg, VU.RGBA(color, alpha))
    nvgText(nvg, x, y, text, nil)
    nvgRestore(nvg)
end

---@param nvg NVGContextWrapper
---@param x number
---@param y number
---@param r number
---@param phase number
---@param alpha number
---@param tired boolean?
local function drawCellFallback(nvg, x, y, r, phase, alpha, tired)
    local P = Config.Palette
    nvgBeginPath(nvg)
    nvgCircle(nvg, x, y, r)
    local interior = tired and P.bgViolet or P.cellInterior
    nvgFillColor(nvg, VU.RGBA(interior, alpha))
    nvgFill(nvg)
    local membrane = tired and P.damaged or P.cellMembrane
    nvgStrokeColor(nvg, VU.RGBA(membrane, alpha * 0.88))
    nvgStrokeWidth(nvg, 1.8)
    nvgStroke(nvg)
    nvgBeginPath(nvg)
    nvgEllipse(nvg, x + math.cos(phase) * r * 0.28, y + math.sin(phase) * r * 0.28,
        r * 0.24, r * 0.19)
    nvgFillColor(nvg, VU.RGBA(P.cellVacuole, alpha * 0.55))
    nvgFill(nvg)
end

--- 包含旋转的乘法压暗；VU.DrawSpriteTinted 自身没有旋转参数。
---@param nvg NVGContextWrapper
---@param path string?
---@param x number
---@param y number
---@param size number
---@param alpha number
---@param rotation number
---@param tint integer[]?
---@return boolean
local function cellSprite(nvg, path, x, y, size, alpha, rotation, tint)
    if not path then return false end
    if not tint then return VU.DrawSprite(nvg, path, x, y, size, alpha, rotation) end
    nvgSave(nvg)
    nvgTranslate(nvg, x, y)
    nvgRotate(nvg, rotation)
    local drew = VU.DrawSpriteTinted(nvg, path, 0, 0, size, tint, alpha)
    nvgRestore(nvg)
    return drew
end

-- Keep the original body intact; split only the membrane around replacement patches.
-- All regions retain the full 1254 canvas pattern and the parent's cell transform.
local function cellBase(nvg, slots, size, opacity, records)
    if #records == 0 then
        return cellSprite(nvg,slots.cellBody,0,0,size,opacity,0),
            cellSprite(nvg,slots.cellMembrane,0,0,size,opacity,0)
    end
    local parts = {{-627,-627,1254,1254}}
    for _, record in ipairs(records) do
      if not record.fluorescent then
        local cut = record.pose.rect
        local remaining = {}
        for _, rect in ipairs(parts) do
            local left,top = math.max(rect[1],cut[1]),math.max(rect[2],cut[2])
            local right,bottom = math.min(rect[1]+rect[3],cut[1]+cut[3]),math.min(rect[2]+rect[4],cut[2]+cut[4])
            if right <= left or bottom <= top then remaining[#remaining+1] = rect
            else
                if top > rect[2] then remaining[#remaining+1] = {rect[1],rect[2],rect[3],top-rect[2]} end
                if bottom < rect[2]+rect[4] then remaining[#remaining+1] = {rect[1],bottom,rect[3],rect[2]+rect[4]-bottom} end
                if left > rect[1] then remaining[#remaining+1] = {rect[1],top,left-rect[1],bottom-top} end
                if right < rect[1]+rect[3] then remaining[#remaining+1] = {right,top,rect[1]+rect[3]-right,bottom-top} end
            end
        end
        parts = remaining
      end
    end
    local body = cellSprite(nvg,slots.cellBody,0,0,size,opacity,0)
    local membrane = true
    nvgSave(nvg)
    nvgShapeAntiAlias(nvg, 0)
    for _, rect in ipairs(parts) do
        membrane = VU.DrawSpriteRegion(nvg,slots.cellMembrane,size,rect,opacity) and membrane
    end
    nvgRestore(nvg)
    return body,membrane
end

--- 只读真实折线胶囊测试，用于弱漂移和短线裁剪，不参与碰撞或移动。
---@param channel RespiratoryChannel
---@param x number
---@param y number
---@return boolean
local function inChannel(channel, x, y)
    local points = channel.points
    local halfWidth = channel.width * 0.5
    if halfWidth <= 0 then return false end
    for i = 1, #points - 1 do
        local a, b = points[i], points[i + 1]
        local dx, dy = b.x - a.x, b.y - a.y
        local lengthSquared = dx * dx + dy * dy
        if lengthSquared > 0 then
            local t = unit(((x - a.x) * dx + (y - a.y) * dy) / lengthSquared)
            local rx, ry = x - a.x - t * dx, y - a.y - t * dy
            if rx * rx + ry * ry < halfWidth * halfWidth then return true end
        end
    end
    return false
end

--- 米制流向短线，方向/长度来自当前 FlowAt；不使用病毒贴图或圆形微粒。
---@param nvg NVGContextWrapper
---@param map RespiratoryMap
---@param wx number
---@param wy number
---@param ppm number
---@param ox number
---@param oy number
---@param time number
---@param alpha number
---@param arrow boolean
---@param maxLength number 米
local function flowMark(nvg, map, wx, wy, ppm, ox, oy, time, alpha, arrow, maxLength, vx, vy)
    if vx==nil then vx,vy=map:FlowAt(wx,wy,time) end
    local speed = math.sqrt(vx * vx + vy * vy)
    if speed <= 0.0001 then return end
    local ux, uy = vx / speed, vy / speed
    local length = math.min(maxLength, speed * 0.32 + (arrow and 0.22 or 0.12))
    local ax, ay = wx - ux * length * 0.5, wy - uy * length * 0.5
    local bx, by = wx + ux * length * 0.5, wy + uy * length * 0.5
    if not inTissue(map, ax, ay) or not inTissue(map, bx, by) then return end
    nvgBeginPath(nvg)
    nvgMoveTo(nvg, ox + ax * ppm, oy + ay * ppm)
    nvgLineTo(nvg, ox + bx * ppm, oy + by * ppm)
    if arrow then
        local head = length * 0.28
        nvgMoveTo(nvg, ox + (bx - ux * head - uy * head * 0.55) * ppm,
            oy + (by - uy * head + ux * head * 0.55) * ppm)
        nvgLineTo(nvg, ox + bx * ppm, oy + by * ppm)
        nvgLineTo(nvg, ox + (bx - ux * head + uy * head * 0.55) * ppm,
            oy + (by - uy * head - ux * head * 0.55) * ppm)
    end
    -- Dark under-stroke separates the moving marks from textured tissue.
    local strokeWidth = Config.EnvironmentVisual.flowMarkWidth*(arrow and 1.15 or 1)
    nvgStrokeColor(nvg,VU.RGBA(Config.Palette.bgDeep,alpha*.8))
    nvgStrokeWidth(nvg,strokeWidth+2)
    nvgStroke(nvg)
    nvgStrokeColor(nvg, VU.RGBA(FLOW_MARK, alpha))
    nvgStrokeWidth(nvg,strokeWidth)
    nvgStroke(nvg)
end

---@param channel table
---@param l Rect4
---@param ppm number
---@param ox number
---@param oy number
---@return boolean
local function channelOnScreen(channel, l, ppm, ox, oy)
    local points = channel.points or EMPTY
    if #points < 2 or (channel.width or 0) <= 0 then return false end
    local minX, minY, maxX, maxY = math.huge, math.huge, -math.huge, -math.huge
    for _, point in ipairs(points) do
        minX, minY = math.min(minX, point.x), math.min(minY, point.y)
        maxX, maxY = math.max(maxX, point.x), math.max(maxY, point.y)
    end
    local width = channel.width
    return ellipseOnScreen(ox + (minX + maxX) * 0.5 * ppm, oy + (minY + maxY) * 0.5 * ppm,
        (maxX - minX + width) * ppm * 0.5, (maxY - minY + width) * ppm * 0.5, l)
end

---@class CellView
---@field overviewFrame {ppm:number,cx:number,cy:number}?
---@field worldView Rect4?
local CellView = {}
CellView.__index = CellView

---@return CellView
function CellView.New()
    local self = setmetatable({}, CellView)
    self:init()
    return self
end

function CellView:init()
    self.camera = { x = 0, y = 0 }
    ---@type Rect4?
    self.viewport = nil
    -- 只缓存纯装饰和资源诊断，不缓存世界的区域、实体或状态。
    self.texture = VU.MakeTissueTexture(90210)
    ---@type table<string, boolean>
    self.immuneArtStatus = {}
    -- 仅是绘制短线的归一化行程，不持有 map/channel/实体引用或权威状态。
    ---@type table<number, {time:number,phase:number}>
    self.flowAnimation = {}
    ---@type table?
    self.environmentGeometry = nil
    ---@type CellSurface
    self.surface = CellSurface.New()
    ---@type LatentParticles
    self.latentParticles = LatentParticles.New()
    self.budding = BuddingVisual.New()
    self.tissueArt = TissueArt.New()
    self.attachments = AttachmentVisual.New()
    self.fluorescence = Bioluminescence.New()
    self.swarmPhysics = SwarmVisualPhysics.New()
    self.vitality = CellVitality.New()
    self.cellAppearances = {}
    ---@type SwarmWorld?
    self.visualWorld = nil
end

function CellView:Destroy()
    self.surface:Destroy()
    self.latentParticles:Destroy()
    self.budding:Destroy()
    self.tissueArt:Destroy()
    self.attachments:Destroy()
    self.fluorescence:Destroy()
    self.swarmPhysics:Reset()
    self.vitality:Reset()
    self.cellAppearances = {}
    self.visualWorld = nil
    self.flowAnimation = {}
    self.environmentGeometry = nil
    self.renderMotion,self.renderGroups,self.renderReleased=nil,nil,nil
end

---@param camera {x:number,y:number}
function CellView:SetCamera(camera)
    self.camera = camera
end

---@param viewport Rect4
function CellView:SetViewport(viewport)
    self.viewport = viewport
end

-- Drawing and warnings consume the same read-only presentation pose.
function CellView:Position(entity)
    return self.swarmPhysics:Position(entity,self.renderMotion)
end

--- 仅更新表现副本；所有玩法模拟仍由 GameScene / SwarmWorld 拥有。
---@param dt number
---@param world SwarmWorld?
---@param motion RenderMotion?
---@param active boolean?
function CellView:Update(dt,world,motion,active)
    if self.visualWorld~=world then self:Destroy();self.visualWorld=world end
    self.renderMotion=motion
    local start=PerformanceStats.Begin()
    self.swarmPhysics:Update(world,motion,dt,active,self.surface:GetData(),self.worldView)
    self.vitality:Update(world,dt,active,self.worldView)
    PerformanceStats.Finish("visualPhysicsCPU",start)
end

---@param l Rect4
---@param zoom number?
---@return number pixelsPerMeter
---@return number screenX
---@return number screenY
function CellView:CameraTransform(l, zoom)
    if self.overviewFrame then
        return self.overviewFrame.ppm,self.overviewFrame.cx,self.overviewFrame.cy
    end
    local area = self.viewport
    if not area or area.w <= 0 or area.h <= 0 then area = l end
    -- 可读下限以屏幕逻辑像素计；换回Widget坐标后，仍由父层统一做UI/DPR缩放。
    -- 不单独放大颗粒，也不改变细胞、病毒与碰撞之间的比例。
    local dpr = graphics and graphics:GetDPR() or 1
    local minPPM = Config.CellVisual.minPixelsPerMeter * dpr / math.max(0.01, Theme.GetScale())
    local basePPM = math.max(minPPM, math.min(l.w, l.h) / 9)
    local ppm = basePPM * math.max(0.01, zoom or 1)
    return ppm, area.x + area.w * 0.5, area.y + area.h * 0.57
end

---@param x number 世界米制 x
---@param y number 世界米制 y（向屏幕下方增加，与摇杆一致）
---@param l Rect4
---@param zoom number?
---@return number px
---@return number py
function CellView:WorldToScreen(x, y, l, zoom)
    local ppm, cx, cy = self:CameraTransform(l, zoom)
    return cx + (x - self.camera.x) * ppm, cy + (y - self.camera.y) * ppm
end

---@param px number 绝对 base px
---@param py number 绝对 base px
---@param l Rect4
---@param zoom number?
---@return number x
---@return number y
function CellView:ScreenToWorld(px, py, l, zoom)
    local ppm, cx, cy = self:CameraTransform(l, zoom)
    return self.camera.x + (px - cx) / ppm, self.camera.y + (py - cy) / ppm
end

-- Map topology is immutable within a run. Cache only fixed decoration samples;
-- inflammation, time-varying flow, visibility and animation stay live.
function CellView:EnvironmentGeometry(map)
    local cached=self.environmentGeometry
    if cached and cached.map==map then return cached end
    cached={map=map,regions={},fibers={},grains={}}
    for _,region in pairs(map.regions or EMPTY) do
        local entry={edges={},drift={}}
        cached.regions[region]=entry
        for i=0,48 do
            local angle=i/48*TAU
            local co,si=math.cos(angle),math.sin(angle)
            entry.edges[#entry.edges+1]={x=region.x+co*region.rx,y=region.y+si*region.ry,
                visible=not inTissue(map,region.x+co*(region.rx+.035),region.y+si*(region.ry+.035))
                    and math.sin(angle*4+(region.id or 1))>-.15}
        end
        for index=1,8 do
            local angle=index*2.39996+(region.id or 1)
            local radius=math.sqrt(index/9)*.80
            local wx,wy=region.x+math.cos(angle)*region.rx*radius,region.y+math.sin(angle)*region.ry*radius
            local inBand=false
            for _,channel in ipairs(map.channels or EMPTY) do
                if inChannel(channel,wx,wy) then inBand=true;break end
            end
            entry.drift[index]={x=wx,y=wy,visible=not inBand and inTissue(map,wx,wy)}
        end
    end
    local width,height=map.width or 26,map.height or 32
    for _,fiber in ipairs(self.texture.fibers) do
        local points={};cached.fibers[fiber]=points
        for _,point in ipairs(fiber.pts) do
            local wx,wy=point[1]*width,point[2]*height
            points[#points+1]={x=wx,y=wy,visible=inTissue(map,wx,wy)}
        end
    end
    for _,grain in ipairs(self.texture.granules) do
        local wx,wy=grain.x*width,grain.y*height
        cached.grains[grain]={x=wx,y=wy,visible=inTissue(map,wx,wy)}
    end
    self.environmentGeometry=cached
    return cached
end

--- 同一张固定解剖地图：椭圆组织区域 + 实际通道全宽；枝间保留紫黑不可玩空隙。
---@param nvg NVGContextWrapper
---@param map table
---@param l Rect4
---@param ppm number
---@param ox number
---@param oy number
---@param time number
function CellView:DrawEnvironment(nvg, map, l, ppm, ox, oy, time)
    if map.isFlatMap then
        require('Game.FlatMapVisual').Draw(nvg,map,l,ppm,ox,oy,time,self.tissueArt.art)
        return
    end
    local P = Config.Palette
    local geometry=self:EnvironmentGeometry(map)
    nvgBeginPath(nvg)
    nvgRect(nvg, l.x, l.y, l.w, l.h)
    nvgFillColor(nvg, VU.RGBA(P.bgDeep))
    nvgFill(nvg)
    local regions, channels = map.regions or EMPTY, map.channels or EMPTY
    -- 同色铺底，无管壁 / 河岸 / 方格；主干与分支由数据连接，不猜四区矩形。
    for _, channel in ipairs(channels) do
        local points = channel.points or EMPTY
        local width = math.max(0, channel.width or 0) * ppm
        if channelOnScreen(channel, l, ppm, ox, oy) and width > 0 then
            nvgBeginPath(nvg)
            nvgMoveTo(nvg, ox + points[1].x * ppm, oy + points[1].y * ppm)
            for i = 2, #points do
                nvgLineTo(nvg, ox + points[i].x * ppm, oy + points[i].y * ppm)
            end
            nvgLineCap(nvg, NVG_ROUND)
            nvgLineJoin(nvg, NVG_ROUND)
            nvgStrokeWidth(nvg, width)
            nvgStrokeColor(nvg, VU.RGBA({ 21, 14, 33, 255 }))
            nvgStroke(nvg)
        end
    end
    for _, region in pairs(regions) do
        local px, py = ox + region.x * ppm, oy + region.y * ppm
        local rx, ry = math.max(0.001, region.rx) * ppm, math.max(0.001, region.ry) * ppm
        if ellipseOnScreen(px, py, rx, ry, l) then
            nvgSave(nvg)
            nvgTranslate(nvg, px, py)
            nvgScale(nvg, rx, ry)
            nvgBeginPath(nvg)
            nvgCircle(nvg, 0, 0, 1)
            nvgFillPaint(nvg, nvgRadialGradient(nvg, -0.12, -0.12, 0.12, 1.15,
                VU.RGBA(P.bgViolet), VU.RGBA({ 21, 14, 33, 255 })))
            nvgFill(nvg)
            nvgRestore(nvg)
            -- 部分薄纤维沿外缘，只画 union 的外界，避免椭圆相交处出现隔墙。
            nvgBeginPath(nvg)
            local connected = false
            for _,point in ipairs(geometry.regions[region].edges) do
                if point.visible then
                    if connected then nvgLineTo(nvg, ox + point.x * ppm, oy + point.y * ppm)
                    else nvgMoveTo(nvg, ox + point.x * ppm, oy + point.y * ppm) end
                end
                connected = point.visible
            end
            nvgStrokeColor(nvg, VU.RGBA(P.bgFiber, 0.52))
            nvgStrokeWidth(nvg, 0.75)
            nvgStroke(nvg)
            -- 热点来自真实炎症，不用感染节点数量或时间伪造热点。
            local inflammation = math.max(0, region.inflammation or 0)
            local threshold = math.max(0.01, (Config.Gameplay or EMPTY).hotspotThreshold or 8)
            local heat = unit(inflammation / (threshold * 3))
            if heat > 0 then
                nvgSave(nvg)
                nvgTranslate(nvg, px, py)
                nvgScale(nvg, rx, ry)
                nvgBeginPath(nvg)
                nvgCircle(nvg, 0, 0, 1)
                nvgFillPaint(nvg, nvgRadialGradient(nvg, 0, 0, 0.05, 1,
                    VU.RGBA(P.infectWarm, heat * 0.12), VU.RGBA(P.infectWarm, 0)))
                nvgFill(nvg)
                nvgRestore(nvg)
            end
            local labelY = py - ry * 0.76
            if region.name and onScreen(px, labelY, 45, l) then
                mapText(nvg, px, labelY, region.name, P.textDim, 0.46, 9)
            end
        end
    end

    local tissueDrew = self.tissueArt:Draw(nvg,map,ppm,ox,oy,l)
    -- 静态装饰锚在世界坐标；加载正式纤维时停用旧程序纤维。
    for _, fiber in ipairs(not tissueDrew and self.texture.fibers or EMPTY) do
        nvgBeginPath(nvg)
        local connected = false
        for _, point in ipairs(geometry.fibers[fiber]) do
            local px, py = ox + point.x * ppm, oy + point.y * ppm
            local visible = onScreen(px, py, 8, l) and point.visible
            if visible then
                if connected then nvgLineTo(nvg, px, py) else nvgMoveTo(nvg, px, py) end
            end
            connected = visible
        end
        nvgStrokeColor(nvg, VU.RGBA(P.bgFiber, fiber.alpha * 0.75))
        nvgStrokeWidth(nvg, 0.65)
        nvgStroke(nvg)
    end
    for _, grain in ipairs(self.texture.granules) do
        local point=geometry.grains[grain]
        local px, py = ox + point.x * ppm, oy + point.y * ppm
        if onScreen(px, py, 3, l) and point.visible then
            nvgBeginPath(nvg)
            nvgCircle(nvg, px, py, math.min(1.5, grain.r))
            nvgFillColor(nvg, VU.RGBA(P.bgGranule, grain.alpha * 0.65))
            nvgFill(nvg)
        end
    end
    -- 带外只有 FlowAt 定义的微弱组织漂移，不能把整个椭圆误画成强流带。
    self:DrawTissueDrift(nvg, map, l, ppm, ox, oy, time)
    for _, channel in ipairs(channels) do
        self:DrawFlow(nvg, channel, map, l, ppm, ox, oy, time)
    end
end

--- 椭圆内的弱流场采样，只画稀疏短线；无填充、无圆点、无额外世界对象。
---@param nvg NVGContextWrapper
---@param map RespiratoryMap
---@param l Rect4
---@param ppm number
---@param ox number
---@param oy number
---@param time number
function CellView:DrawTissueDrift(nvg, map, l, ppm, ox, oy, time)
    if not map.FlowAt then return end
    nvgSave(nvg)
    nvgLineCap(nvg, NVG_ROUND)
    for _, region in ipairs(map.regions or EMPTY) do
        if ellipseOnScreen(ox + region.x * ppm, oy + region.y * ppm, region.rx * ppm, region.ry * ppm, l) then
            for _,point in ipairs(self:EnvironmentGeometry(map).regions[region].drift) do
                local wx,wy=point.x,point.y
                if point.visible and onScreen(ox + wx * ppm, oy + wy * ppm, 4, l) then
                    local vx, vy = map:FlowAt(wx, wy, time)
                    local speed = math.sqrt(vx * vx + vy * vy)
                    flowMark(nvg, map, wx, wy, ppm, ox, oy, time, unit(speed / 0.032) * 0.30, false, 0.18,vx,vy)
                end
            end
        end
    end
    nvgRestore(nvg)
end

--- 实际折线/完整宽度的青蓝薄带；强度和短线密度由 strength * speed 决定。
--- 每条侧流线按 FlowAt 采样的顺流速度建立行程时间，不用默认速度或弯曲假路径。
---@param nvg NVGContextWrapper
---@param channel RespiratoryChannel
---@param map RespiratoryMap
---@param l Rect4
---@param ppm number
---@param ox number
---@param oy number
---@param time number
function CellView:DrawFlow(nvg, channel, map, l, ppm, ox, oy, time)
    local points = channel.points or EMPTY
    if #points < 2 or not map.FlowAt or not channelOnScreen(channel, l, ppm, ox, oy) then return end
    local width = math.max(0, channel.width or 0)
    local centerSpeed = math.max(0, channel.speed or 0) * math.max(0, channel.strength or 0)
    if width <= 0 or centerSpeed <= 0 then return end
    local flowStrength = unit(centerSpeed / 1.5)
    local totalLength = 0
    ---@type number[]
    local lengths = {}
    for i = 1, #points - 1 do
        local a, b = points[i], points[i + 1]
        local length = math.sqrt((b.x - a.x)^2 + (b.y - a.y)^2)
        lengths[i] = length
        totalLength = totalLength + length
    end
    if totalLength < 0.001 then return end

    nvgSave(nvg)
    nvgLineCap(nvg, NVG_ROUND)
    nvgLineJoin(nvg, NVG_ROUND)
    -- 青蓝影响域仅为调试显示；正式画面使用深紫贴花与真实方向短线。
    if Config.EnvironmentVisual.debugFlowBands then
    nvgBeginPath(nvg)
    nvgMoveTo(nvg, ox + points[1].x * ppm, oy + points[1].y * ppm)
    for i = 2, #points do
        nvgLineTo(nvg, ox + points[i].x * ppm, oy + points[i].y * ppm)
    end
    nvgStrokeWidth(nvg, width * ppm)
    nvgStrokeColor(nvg, VU.RGBA(FLOW_COLOR, 0.09 + flowStrength * 0.08))
    nvgStroke(nvg)
    nvgStrokeWidth(nvg, width * ppm * 0.56)
    nvgStrokeColor(nvg, VU.RGBA(FLOW_COLOR, 0.035 + flowStrength * 0.035))
    nvgStroke(nvg)
    end

    local count = math.max(4, math.min(22, math.floor(totalLength / (1.8 - flowStrength * 0.6))))
    for lane = 1, 3 do
        local offset = (lane-2)*.22*width
        ---@type number[]
        local travelTimes = {}
        local totalTime = 0
        for segment = 1, #points - 1 do
            local a, b = points[segment], points[segment + 1]
            local length = lengths[segment]
            if length > 0.001 then
                local ux, uy = (b.x - a.x) / length, (b.y - a.y) / length
                local vx, vy = map:FlowAt((a.x + b.x) * 0.5 - uy * offset,
                    (a.y + b.y) * 0.5 + ux * offset, time)
                -- 采用当前真实流场的切向分量，侧道衰减/交汇变化也影响动画速度。
                local speed = math.max(0, vx * ux + vy * uy)
                travelTimes[segment] = speed > 0.0001 and length / speed or 0
                totalTime = totalTime + travelTimes[segment]
            else travelTimes[segment] = 0 end
        end
        if totalTime > 0 then
            local key = channel.id * 3 + lane
            local animation = self.flowAnimation[key] or { time = time, phase = 0 }
            -- 对视觉相位积分，避免 FlowAt 脉动改变行程总时长后 time/totalTime 倒流。
            local dt = time - animation.time
            local phase = dt >= 0 and (animation.phase + dt / totalTime) % 1 or 0
            self.flowAnimation[key] = { time = time, phase = phase }
            for index = 1, count do
                local travel = ((phase + index / count + lane * 0.19 + channel.id * 0.13) % 1) * totalTime
                for segment = 1, #points - 1 do
                    local duration = travelTimes[segment]
                    if duration > 0 and travel <= duration then
                        local a, b = points[segment], points[segment + 1]
                        local length = lengths[segment]
                        local ux, uy = (b.x - a.x) / length, (b.y - a.y) / length
                        local t = unit(travel / duration)
                        local wx, wy = a.x + (b.x - a.x) * t - uy * offset,
                            a.y + (b.y - a.y) * t + ux * offset
                        local px, py = ox + wx * ppm, oy + wy * ppm
                        if onScreen(px, py, 12, l) and inChannel(channel, wx, wy) and inTissue(map, wx, wy) then
                            local vx, vy = map:FlowAt(wx, wy, time)
                            local localStrength = unit(math.sqrt(vx * vx + vy * vy) / 1.5)
                            local fade = smoothstep(t / 0.12) * smoothstep((1 - t) / 0.12)
                            flowMark(nvg, map, wx, wy, ppm, ox, oy, time,
                                Config.EnvironmentVisual.flowMarkAlpha*(.75+.25*localStrength)*fade,
                                index % 2 == 0, math.min(0.65, width * 0.28),vx,vy)
                        end
                        break
                    end
                    travel = travel - duration
                end
            end
        end
    end
    nvgRestore(nvg)
end

---@param nvg NVGContextWrapper
---@param sim SimState
---@param ppm number
---@param ox number
---@param oy number
-- 权威技能范围复用同一米制相机转换，不参与资源或状态结算。
function CellView:DrawSkillRange(nvg,sim,ppm,ox,oy)
    local selection=sim and sim.skillSelection
    if not selection then return end
    local world=sim.world
    local s=world:SwarmById(selection.swarmId)
    if not s then return end
    local cfg=Config.CardAbilities[selection.id] or {}
    local function ring(x,y,r)
        nvgBeginPath(nvg);nvgCircle(nvg,ox+x*ppm,oy+y*ppm,r*ppm)
        nvgStrokeColor(nvg,nvgRGBA(100,220,220,210));nvgStrokeWidth(nvg,2);nvgStroke(nvg)
    end
    ring(s.x,s.y,s.radius+(cfg.range or 0))
    if cfg.targetType=="node" or cfg.targetType=="cell" then
        for _,c in ipairs(world.cells) do
            -- Match authority's range rejection before allocating a target or
            -- doing contact/path/deployment checks; never validate distant cells.
            local dx,dy=c.x-s.x,c.y-s.y
            local reach=s.radius+c.radius+(cfg.range or 0)
            if dx*dx+dy*dy<=reach*reach+1e-9 then
                local legal=sim:ValidateSkill(selection.id,s.id,{cellId=c.id})
                if legal then ring(c.x,c.y,c.radius*1.45) end
            end
        end
    end
    if selection.target and selection.target.x then
        nvgBeginPath(nvg);nvgMoveTo(nvg,ox+s.x*ppm,oy+s.y*ppm)
        nvgLineTo(nvg,ox+selection.target.x*ppm,oy+selection.target.y*ppm)
        nvgStrokeColor(nvg,nvgRGBA(100,220,220,210));nvgStrokeWidth(nvg,2);nvgStroke(nvg)
    end
end

---@param nvg NVGContextWrapper
---@param x number
---@param y number
---@param w number
---@param h number
---@param ctx table
function CellView:DrawWorld(nvg, x, y, w, h, ctx)
    local world = (ctx.sim or EMPTY).world
    if self.visualWorld ~= world then
        self:Destroy()
        self.visualWorld = world
    end
    self.renderMotion=ctx.renderMotion
    if w <= 0 or h <= 0 then return end
    local drawStart=PerformanceStats.Begin()
    local l = { x = x, y = y, w = w, h = h }
    local zoom = ctx.zoom or 1
    local ppm = self:CameraTransform(l, zoom)
    local ox, oy = self:WorldToScreen(0, 0, l, zoom)
    local time = world and world.time or ctx.time or 0
    self.fluorescence:BeginFrame(world and (#(world.viruses or EMPTY)+#(world.releasedViruses or EMPTY)) or 0)
    nvgSave(nvg)
    nvgIntersectScissor(nvg, x, y, w, h)
    if not world or not world.map then
        nvgBeginPath(nvg)
        nvgRect(nvg, x, y, w, h)
        nvgFillColor(nvg, VU.RGBA(Config.Palette.bgDeep))
        nvgFill(nvg)
        nvgRestore(nvg)
        PerformanceStats.Finish("drawingCPU",drawStart)
        return
    end
    self:DrawEnvironment(nvg, world.map, l, ppm, ox, oy, time)
    self:DrawSkillRange(nvg,ctx.sim,ppm,ox,oy)
    self.surface:BeginFrame()
    local releasedById,swarmRadii={},{}
    for _,virus in ipairs(world.releasedViruses or EMPTY) do releasedById[virus.id]=virus end
    for _,virus in ipairs(world.viruses or EMPTY) do
        if not swarmRadii[virus.swarmId] then swarmRadii[virus.swarmId]=virus.radius end
    end
    self.budding:Prepare(world,releasedById)
    self.attachments:Prepare(world,releasedById,swarmRadii)
    local cells, effects = world.cells or EMPTY, world.effects or EMPTY
    -- 只对本帧确实画出附着本体的Released隐藏重复原位图，不删实体/感染能力。
    local attachedReleased = {}
    local buddingReleased = {}
    local swarms = world.swarms or EMPTY
    ---@type table<number, table>
    local groupsById = {}
    for _, swarm in ipairs(swarms) do groupsById[swarm.id] = swarm end
    self.renderGroups,self.renderReleased=groupsById,releasedById

    -- 冷色警戒范围与目标方向线先画在实体下面；免疫本体最后绘制。
    for _, immune in ipairs(world.immunes or EMPTY) do
        self:DrawImmuneWarning(nvg, immune, l, ppm, ox, oy, false)
    end
    for _, cell in ipairs(cells) do
        local pose = self.vitality:Get(cell)
        local px = ox + (cell.x + (pose and pose.dx or 0)) * ppm
        local py = oy + (cell.y + (pose and pose.dy or 0)) * ppm
        local radius = math.max(0, cell.radius or 0.5) * ppm
        if radius > 0 and onScreen(px, py, radius * 1.9 + 16, l) then
            self:DrawCell(nvg, px, py, radius, cell, time, attachedReleased,buddingReleased,ppm)
            if (cell.shieldHits or 0)>0 then
                nvgBeginPath(nvg);nvgCircle(nvg,px,py,radius*1.5)
                nvgStrokeColor(nvg,nvgRGBA(100,220,220,200));nvgStrokeWidth(nvg,1.5);nvgStroke(nvg)
                mapText(nvg,px,py+radius*1.7,"保护层 "..cell.shieldHits,Config.Palette.immuneCool,1,9)
            end
            local occupants=0
            for _,s in ipairs(swarms) do if s.hiddenCellId==cell.id then occupants=occupants+1 end end
            if occupants>0 then mapText(nvg,px,py-radius*1.6,"藏身群 "..occupants,Config.Palette.virus,1,9) end
        end
    end
    for _, effect in ipairs(effects) do
        local px, py = ox + (effect.x or 0) * ppm, oy + (effect.y or 0) * ppm
        local radius = math.max(0, effect.radius or 0.24) * ppm
        if onScreen(px, py, radius * 3 + 4, l) then self:DrawEffect(nvg, px, py, radius, effect) end
    end

    -- 两个集合是两种真实实体；ID 分别编号，不能跨集合按 ID 去重或补 mass。
    for _, virus in ipairs(world.viruses or EMPTY) do
        local swarm = groupsById[virus.swarmId]
        if not swarm or not swarm.isHidden then
            local vx,vy=self:Position(virus)
            local px, py = ox + vx * ppm, oy + vy * ppm
            local radius = math.max(0, virus.radius or 0.045) * ppm
            if radius > 0 and onScreen(px, py, radius * 1.8 + 4, l) then
                self:DrawVirus(nvg, px, py, radius, virus, time, ppm, false,
                    not swarm or swarm.isPlayerControlled)
            end
        end
    end
    for _, virus in ipairs(world.releasedViruses or EMPTY) do
        if liveReleased(virus) and not attachedReleased[virus.id] and not buddingReleased[virus.id] then
            local vx,vy=self:Position(virus)
            local px, py = ox + vx * ppm, oy + vy * ppm
            local radius = math.max(0, virus.radius or 0.045) * ppm
            if radius > 0 and onScreen(px, py, radius * 1.8 + ppm * 0.4, l) then
                self:DrawVirus(nvg, px, py, radius, virus, time, ppm, true, false)
            end
        end
    end
    for _, immune in ipairs(world.immunes or EMPTY) do
        local ix,iy=self:Position(immune)
        local px, py = ox + ix * ppm, oy + iy * ppm
        local radius = math.max(0, immune.radius or 0.48) * ppm
        if radius > 0 and onScreen(px, py, radius * 1.7 + 30, l) then
            self:DrawImmune(nvg, px, py, radius, immune, time)
        end
    end
    for _, swarm in ipairs(swarms) do
        if not swarm.isHidden and (swarm.mass or 0) > 0 then
            self:DrawSwarm(nvg, swarm, l, ppm, ox, oy)
        end
    end
    -- 目标标记 / 倒计时置于全部实体之上，尤其免疫本体屏外时不能被目标细胞盖住。
    for _, immune in ipairs(world.immunes or EMPTY) do
        self:DrawImmuneWarning(nvg, immune, l, ppm, ox, oy, true)
    end
    for _, pair in ipairs(world.mergePairs or EMPTY) do
        local a, b = groupsById[pair.aId], groupsById[pair.bId]
        if a and b and not a.isHidden and not b.isHidden then
            local ax,ay=self:Position(a)
            local bx,by=self:Position(b)
            ax,ay,bx,by=ox+ax*ppm,oy+ay*ppm,ox+bx*ppm,oy+by*ppm
            local px, py = (ax + bx) * 0.5, (ay + by) * 0.5
            if onScreen(px, py, 80, l) then
                nvgBeginPath(nvg)
                nvgMoveTo(nvg, ax, ay); nvgLineTo(nvg, bx, by)
                nvgStrokeColor(nvg, VU.RGBA(Config.Palette.infectWarm, 0.45))
                nvgStrokeWidth(nvg, 1.2)
                nvgStroke(nvg)
                mapText(nvg, px, math.min(ay, by) - math.max(a.radius, b.radius) * ppm - 25,
                    "靠近合并", Config.Palette.infectWarm, 0.86, 9)
            end
        end
    end
    nvgRestore(nvg)
    PerformanceStats.Finish("drawingCPU",drawStart)
end

---@param nvg NVGContextWrapper
---@param x number
---@param y number
---@param r number
---@param cell table
---@param time number
---@param attachedReleased table<number,boolean>? 本帧已绘制的Released标记，只用于避免同源双画
function CellView:DrawCell(nvg, x, y, r, cell, time, attachedReleased,buddingReleased,ppm)
    local P, slots = Config.Palette, Config.ArtSlots
    local cfg = Config.Gameplay or EMPTY
    local state = cell.state or "HEALTHY"
    local phase, rotation = cell.phase or 0, cell.rotation or 0
    local exposure = unit(cell.exposure or 0)
    local age = math.max(0, cell.infectedAge or 0)
    local latent = state == "LATENT"
    local productive = state == "PRODUCTIVE"
    local exhausted = state == "EXHAUSTED"
    buddingReleased = buddingReleased or {}
    local layerSize = r * 2 * CELL_CANVAS / CELL_DIAMETER
    local surfaceScale = layerSize / CELL_CANVAS
    local vitality = self.vitality:Get(cell)
    local sx,sy = vitality and vitality.sx or 1,vitality and vitality.sy or 1
    local attachments = self.attachments:Get(cell,time)
    -- 已感染病程的色斑视为完整；避免潜伏转产毒等状态迁移清除视觉进度。
    -- 暴露前则只读结算进度与本移动步真实累计值，不写回模拟状态。
    local patchProgress = (latent or productive or exhausted) and 1
        or unit(exposure + ((state == "HEALTHY" or state == "EXPOSED") and (cell._charge or 0) or 0))
    if state == "DEAD" then
        local fade = smoothstep((time-(cell.deathVisualAt or time))/Config.CellVisual.deathTransitionSeconds)
        local previous = self.cellAppearances[cell.id] or {opacity=.96,tired=0}
        nvgSave(nvg)
        nvgTranslate(nvg,x,y)
        nvgRotate(nvg,rotation)
        nvgScale(nvg,surfaceScale*sx,surfaceScale*sy)
        cellSprite(nvg,slots.cellBody,0,0,CELL_CANVAS,previous.opacity*(1-fade)+.32*fade,0)
        cellSprite(nvg,slots.cellMembrane,0,0,CELL_CANVAS,previous.opacity*(1-fade),0)
        if previous.tired > 0 then cellSprite(nvg,slots.cellExhaustion,0,0,CELL_CANVAS,previous.tired*(1-fade),0) end
        cellSprite(nvg,slots.cellVacuole,0,0,CELL_CANVAS,1-fade,0,WHITE_TINT)
        local deathDrew = cellSprite(nvg,slots.cellDeath,0,0,CELL_CANVAS,fade,0)
        nvgRestore(nvg)
        if not deathDrew then
            nvgSave(nvg);nvgTranslate(nvg,x,y);nvgRotate(nvg,rotation);nvgScale(nvg,sx,sy)
            drawCellFallback(nvg,0,0,r,phase,.32,true)
            nvgRestore(nvg)
        end
        return
    end

    local tiredProgress = exhausted and unit((cell.exhaustionTimer or 0)
        / math.max(0.001, cfg.exhaustedSeconds or 35)) or 0
    local opacity = exhausted and (0.96 - smoothstep(tiredProgress) * 0.56) or 0.96
    local infectedVisualAge = cell.infectedVisualAt and math.max(0, time - cell.infectedVisualAt) or age
    local ringFade = latent and (1 - smoothstep(infectedVisualAge / 0.9)) or 0
    -- 感染只从真实接触锚点局部洇开，不再用整张感染细胞替换红膜。
    self.cellAppearances[cell.id] = {opacity=opacity,tired=exhausted and smoothstep(tiredProgress) or 0}
    local buddingPatches = self.budding:Ready(nvg,cell)

    -- 一套cell-local变换：三层、mask、接触标记、局部色斑均共享原画布锚点。
    nvgSave(nvg)
    nvgTranslate(nvg, x, y)
    nvgRotate(nvg, rotation)
    nvgScale(nvg, surfaceScale*sx, surfaceScale*sy)
    local bodyDrew,membraneDrew = cellBase(nvg,slots,CELL_CANVAS,opacity,buddingPatches)
    self.budding:DrawPatches(nvg,buddingPatches,opacity,buddingReleased)

    local patchAngle = self.attachments:GetPatchAngle(cell)
    local diagnosticEnabled = self.visualWorld and CellDiagnostics.IsEnabled(self.visualWorld)
    local diagnosticDrew = false
    ---@type CellSurfacePose?
    local patchPose = nil
    local patchActivity = 1
    local patchAlpha = 0
    if patchAngle and patchProgress > 0 then
        local contact = { angle = patchAngle+rotation }
        patchPose = self.surface:GetPlacement(cell, contact)
        -- 真实进度只驱动各层生长，不再额外乘一次随进度变淡的总alpha。
        patchActivity = 1
        patchAlpha = Config.CellVisual.infectionPatchAlpha
            * (exhausted and (1 - smoothstep(tiredProgress) * 0.70) or 1)
    end
    if exhausted then cellSprite(nvg,slots.cellExhaustion,0,0,CELL_CANVAS,smoothstep(tiredProgress),0) end
    cellSprite(nvg, slots.cellVacuole, 0, 0, CELL_CANVAS, 1, 0, WHITE_TINT)
    -- 交付图层顺序：液泡之后的内部颗粒，再叠局部色块，最后亮点与病毒。
    -- 深肺初始潜伏节点没有真实接触点，只显示内部活动，不补造附着点。
    if bodyDrew and membraneDrew then self.latentParticles:Draw(nvg, cell, time, 1) end
    if bodyDrew and membraneDrew and not exhausted then
        self.fluorescence:Draw(nvg,5,0,0,CELL_CANVAS,opacity,time,phase,r*2)
    end
    if patchPose and patchProgress > 0 then
        self.surface:DrawPatch(nvg, patchPose, patchProgress, patchAlpha * opacity, patchActivity)
    end

    -- 先画全部glint，再统一画病毒本体，避免多来源光斑染亮先画的病毒。
    ---@type {pose:CellSurfacePose,alpha:number,sourceType:string?,sourceId:number?,contact:CellContactVisual}[]
    local attachmentDraws = {}
    -- 标记来源已由权威接触分支接受；本层只读，不消耗质量、不累积感染。
    if bodyDrew and membraneDrew and not exhausted then
        for _, attachment in ipairs(attachments) do
            local contact = attachment.contact
            if attachment.alpha > 0 then
                local data = self.surface:GetData()
                local scale = data and attachment.radius*CELL_DIAMETER
                    / (cell.radius*data.visible_particle_pixels)
                local pose = scale and self.surface:GetPlacement(cell, { angle = attachment.angle+rotation },scale)
                local contactAlpha = attachment.alpha
                if pose then
                    -- The sprite stays visible while its clipped glint is baking.
                    self.surface:DrawGlint(nvg, pose, contactAlpha)
                    attachmentDraws[#attachmentDraws + 1] = { pose = pose, alpha = contactAlpha,
                        sourceType = attachment.sourceType, sourceId = attachment.sourceId, contact = contact }
                end
            end
        end
    end
    for _, attachment in ipairs(attachmentDraws) do
        local drew = self.surface:DrawParticle(nvg, attachment.pose, attachment.alpha)
        if drew and diagnosticEnabled then
            CellDiagnostics.Draw(self.visualWorld, cell, x, y, surfaceScale, attachment.pose, attachment.contact)
            diagnosticDrew = true
        end
        if drew and attachedReleased and attachment.sourceType == "RELEASED_VIRUS" and attachment.sourceId then
            attachedReleased[attachment.sourceId] = true
        end
    end
    if diagnosticEnabled and not diagnosticDrew then
        CellDiagnostics.Draw(self.visualWorld, cell, x, y, surfaceScale, nil)
    end
    nvgRestore(nvg)
    if ppm then
        self.budding:DrawHandoffs(nvg,cell,x,y,surfaceScale,time,ppm,function(...)
            self:DrawVirus(...)
        end,buddingReleased,vitality)
    end
    if not bodyDrew or not membraneDrew then
        nvgSave(nvg);nvgTranslate(nvg,x,y);nvgRotate(nvg,rotation);nvgScale(nvg,sx,sy)
        drawCellFallback(nvg,0,0,r,phase,opacity,exhausted)
        nvgRestore(nvg)
    end

    if state == "EXPOSED" or (state == "HEALTHY" and exposure > 0) or (latent and ringFade > 0) then
        -- 只读exposure。进入潜伏后的短暂圈满淡出与局部色斑连续衔接。
        local ringAlpha = latent and ringFade or 1
        local color = VU.LerpColor({ 128, 53, 48, 255 }, P.infectWarm, smoothstep(exposure))
        local visual = Config.CellVisual
        -- 旧环落在不规则膜内；按真实膜最大径向距离留出外侧空隙，线宽随细胞缩放。
        local arcRadius = math.max(r * visual.infectionRingRadiusMul, r + visual.infectionRingPadding)
        local ringWidth = math.max(visual.infectionRingWidthMin,
            math.min(visual.infectionRingWidthMax, r * visual.infectionRingWidthMul))
        nvgSave(nvg)
        nvgBeginPath(nvg)
        nvgCircle(nvg, x, y, arcRadius)
        nvgStrokeColor(nvg, VU.RGBA(P.damaged, 0.38 * ringAlpha))
        nvgStrokeWidth(nvg, ringWidth * 0.8)
        nvgStroke(nvg)
        if exposure > 0 then
            nvgBeginPath(nvg)
            nvgArc(nvg, x, y, arcRadius, -math.pi * 0.5, -math.pi * 0.5 + exposure * TAU, NVG_CW)
            local pulse = exposure > 0.85 and (0.10 * (1 + math.sin(time * 4 + phase))) or 0
            nvgStrokeColor(nvg, VU.RGBA(color, (0.78 + pulse) * ringAlpha))
            nvgStrokeWidth(nvg, ringWidth)
            nvgStroke(nvg)
            local angle = -math.pi * 0.5 + exposure * TAU
            nvgBeginPath(nvg)
            nvgCircle(nvg, x + math.cos(angle) * arcRadius, y + math.sin(angle) * arcRadius, ringWidth * 0.65)
            nvgFillColor(nvg, VU.RGBA(color, 0.85 * ringAlpha))
            nvgFill(nvg)
        end
        nvgRestore(nvg)
    end
    if productive then
        -- 内部短线是状态活动，不是病毒；Released实体仍由DrawWorld原有集合绘制。
        local pulse = 0.80 + 0.20 * math.sin(time * 3.8 + phase)
        nvgBeginPath(nvg)
        nvgMoveTo(nvg, x - r * 0.12, y - r * 0.12)
        nvgLineTo(nvg, x + r * 0.08, y + r * 0.04)
        nvgMoveTo(nvg, x + r * 0.07, y - r * 0.16)
        nvgLineTo(nvg, x + r * 0.17, y - r * 0.06)
        nvgStrokeColor(nvg, VU.RGBA({ 180, 180, 180, 255 }, 0.42 * pulse))
        nvgStrokeWidth(nvg, 1)
        nvgStroke(nvg)
    end
    -- 标签只说明权威病程，不用整颗变色代替局部感染与潜伏活动。
    if latent or productive or exhausted then
        local label = latent and "潜伏" or (productive and "产毒" or "耗竭")
        mapText(nvg, x, y + r * 1.65 + 6, label, P.textDim, 0.85, 9)
    end
end

---@param nvg NVGContextWrapper
---@param x number
---@param y number
---@param r number
---@param virus table
---@param time number
---@param ppm number
---@param released boolean
---@param controlled boolean
function CellView:DrawVirus(nvg, x, y, r, virus, time, ppm, released, controlled)
    local phase = virus.phase or 0
    local state = released and virus.state or "GROUP"
    local color = state == "INFECTING" and Config.Palette.virusHot or Config.Palette.virus
    local alpha = released and 0.89 or (controlled and 0.96 or 0.78)
    if released then
        -- 尾迹仅用真实位移 / 速度，不制造自动归队行为。
        local dx = virus.x - (virus._oldX or virus.x)
        local dy = virus.y - (virus._oldY or virus.y)
        local length = math.sqrt(dx * dx + dy * dy)
        if length < 0.00001 then
            dx, dy = virus.vx or 0, virus.vy or 0
            length = math.sqrt(dx * dx + dy * dy)
        end
        if length > 0.00001 and state ~= "INFECTING" then
            local tail = math.min(0.26 * ppm, math.max(r * 2.5, 3))
            nvgBeginPath(nvg)
            nvgMoveTo(nvg, x - dx / length * tail, y - dy / length * tail)
            nvgLineTo(nvg, x, y)
            nvgStrokeColor(nvg, VU.RGBA(color, state == "ATTRACTED" and 0.56 or 0.24))
            nvgStrokeWidth(nvg, 0.7)
            nvgStroke(nvg)
        end
        if state == "RELEASED" or state == "INFECTING" then
            nvgBeginPath(nvg)
            nvgCircle(nvg, x, y, r * 1.2 + 0.5)
            nvgStrokeColor(nvg, VU.RGBA(color, state == "INFECTING" and 0.65 or 0.4))
            nvgStrokeWidth(nvg, 0.65)
            nvgStroke(nvg)
        end
    end
    local diameter = r*2
    local index = diameter <= 24 and 1 or (diameter <= 80 and 2 or (diameter <= 224 and 3 or 4))
    local path = artSlot(Config.ArtSlots.virusParticle,index)
    local rotation = self.swarmPhysics:Rotation(virus) or (phase + math.sin(time * 0.6 + phase) * 0.08)
    if not (path and VU.DrawSprite(nvg, path, x, y, diameter / Config.CellVisual.virusFill, alpha, rotation)) then
        nvgBeginPath(nvg)
        nvgCircle(nvg, x, y, r)
        nvgFillColor(nvg, VU.RGBA(color, alpha))
        nvgFill(nvg)
    else
        self.fluorescence:Draw(nvg,1,x,y,diameter/Config.CellVisual.virusFill,alpha,time,phase,diameter,
            rotation)
    end
end

--- 群轮廓和准星是控制标识，不是额外病毒或感染覆盖圈。
---@param nvg NVGContextWrapper
---@param swarm table
---@param l Rect4
---@param ppm number
---@param ox number
---@param oy number
function CellView:DrawSwarm(nvg, swarm, l, ppm, ox, oy)
    local sx,sy=self:Position(swarm)
    local x, y, r = ox + sx * ppm, oy + sy * ppm, math.max(0, swarm.radius or 0.48) * ppm
    if not onScreen(x, y, r + 40, l) then return end
    local controlled = swarm.isPlayerControlled
    local alpha = controlled and 0.88 or 0.42
    nvgBeginPath(nvg)
    nvgCircle(nvg, x, y, r + 3)
    nvgStrokeColor(nvg, VU.RGBA(Config.Palette.infectWarm, alpha))
    nvgStrokeWidth(nvg, controlled and 1.7 or 1.0)
    nvgStroke(nvg)
    if controlled then
        local marker = 4
        nvgBeginPath(nvg)
        nvgMoveTo(nvg, x - marker - 3, y); nvgLineTo(nvg, x - marker, y)
        nvgMoveTo(nvg, x + marker, y); nvgLineTo(nvg, x + marker + 3, y)
        nvgMoveTo(nvg, x, y - marker - 3); nvgLineTo(nvg, x, y - marker)
        nvgMoveTo(nvg, x, y + marker); nvgLineTo(nvg, x, y + marker + 3)
        nvgStrokeColor(nvg, VU.RGBA(Config.Palette.infectWarm, 0.98))
        nvgStrokeWidth(nvg, 1.2)
        nvgStroke(nvg)
    end
    local behavior = swarm.anchored and "等待" or swarm.groupCommand and (swarm.groupCommand.kind=="gather" and "移动" or "等待") or not controlled and AI_LABELS[swarm.aiState] or nil
    local title = (swarm.isMainSwarm and "主群 #" or "分群 #") .. tostring(swarm.id)
        .. (behavior and " · " .. behavior or "")
    if swarm.anchored then mapText(nvg,x,y+r+12,"留守",Config.Palette.immuneCool,alpha,9) end
    if swarm.camouflaged then mapText(nvg,x,y+r+12,"伪装",Config.Palette.immuneCool,alpha,9) end
    mapText(nvg, x, y - r - 13, title, Config.Palette.infectWarm, alpha, 9)
end

--- dangerRadius 是围绕 target 的逃脱提示域，不是瞬时伤害域；圆体接触才会攻击。
--- foreground=false 只画底层范围/方向；true 只画顶层目标/计时，nil 两者都画。
---@param nvg NVGContextWrapper
---@param immune table
---@param l Rect4
---@param ppm number
---@param ox number
---@param oy number
---@param foreground boolean?
function CellView:DrawImmuneWarning(nvg, immune, l, ppm, ox, oy, foreground)
    local state = immune.state or "patrol"
    local macro = immune.kind ~= "tcell"
    local color = macro and Config.Palette.immuneCool or Config.Palette.immuneTCell
    local ix,iy=self:Position(immune)
    local x, y = ox + ix * ppm, oy + iy * ppm
    local body = math.max(0.01, immune.radius or 0.48) * ppm
    local targeted = state == "locked" or state == "warning" or state == "chase" or state == "attack" or state == "investigate"
    local hasTarget = targeted and immune.targetX ~= nil and immune.targetY ~= nil
    local tx = hasTarget and ox + immune.targetX * ppm or x
    local ty = hasTarget and oy + immune.targetY * ppm or y
    if hasTarget and self.renderMotion then
        local target=immune.targetType=="swarm" and (self.renderGroups or EMPTY)[immune.targetId]
            or immune.targetType=="virus" and (self.renderReleased or EMPTY)[immune.targetId]
        if target then
            local px,py=self:Position(target)
            tx,ty=tx+(px-target.x)*ppm,ty+(py-target.y)*ppm
        end
    end
    local danger = targeted and math.max(body, math.max(0, immune.dangerRadius or 0) * ppm)
        or math.max(body + 7, math.max(0, immune.detectionRange or 0) * ppm)
    if foreground ~= true and onScreen(tx, ty, danger + 3, l) then
        nvgBeginPath(nvg)
        nvgCircle(nvg, tx, ty, danger)
        nvgFillColor(nvg, VU.RGBA(color, state == "attack" and 0.042 or (targeted and 0.024 or 0.009)))
        nvgFill(nvg)
        nvgStrokeColor(nvg, VU.RGBA(color, targeted and 0.42 or 0.18))
        nvgStrokeWidth(nvg, targeted and 1.05 or 0.75)
        nvgStroke(nvg)
    end
    if hasTarget then
        -- 线段包围盒裁剪，不只判断线段端点：免疫在屏外也能给出追踪方向。
        if foreground ~= true and ellipseOnScreen((x + tx) * 0.5, (y + ty) * 0.5,
            math.abs(tx - x) * 0.5 + 3, math.abs(ty - y) * 0.5 + 3, l) then
            nvgBeginPath(nvg)
            nvgMoveTo(nvg, x, y); nvgLineTo(nvg, tx, ty)
            nvgStrokeColor(nvg, VU.RGBA(color, (state == "warning" or state == "attack") and 0.5 or 0.31))
            nvgStrokeWidth(nvg, 0.9)
            nvgStroke(nvg)
            local dx, dy = tx - x, ty - y
            local distance = math.sqrt(dx * dx + dy * dy)
            if distance > 1 then
                local nx, ny = dx / distance, dy / distance
                local tipX, tipY = tx - nx * 8, ty - ny * 8
                nvgBeginPath(nvg)
                nvgMoveTo(nvg, tipX - nx * 5 - ny * 3, tipY - ny * 5 + nx * 3)
                nvgLineTo(nvg, tipX, tipY)
                nvgLineTo(nvg, tipX - nx * 5 + ny * 3, tipY - ny * 5 - nx * 3)
                nvgStroke(nvg)
            end
        end
        if foreground ~= false and onScreen(tx, ty, 32, l) then
            -- 这是免疫目标标识，不是病毒精灵。
            nvgBeginPath(nvg)
            nvgCircle(nvg, tx, ty, 8)
            nvgStrokeColor(nvg, VU.RGBA(color, 0.70))
            nvgStrokeWidth(nvg, 1.1)
            nvgStroke(nvg)
            local remaining = state == "investigate" and math.max(0,(immune.recognitionRequiredSeconds or Config.Gameplay.immuneBehavior.recognitionSeconds)-(immune.recognitionTimer or 0))
                or state == "attack" and immune.attackTimer or immune.warningTimer
            if (state == "warning" or state == "locked" or state == "attack" or state=="investigate") and remaining ~= nil then
                mapText(nvg, tx, ty - 20, string.format("%s %.1fs", state=="investigate" and "识别" or state == "attack" and "攻击" or "预警",
                    math.max(0, remaining)), color, 0.92, 9)
            end
        end
    end
end

---@param nvg NVGContextWrapper
---@param x number
---@param y number
---@param r number
---@param immune table
---@param time number
function CellView:DrawImmune(nvg, x, y, r, immune, time)
    local macro = immune.kind ~= "tcell"
    local color = macro and Config.Palette.immuneCool or Config.Palette.immuneTCell
    local phase = immune.phase or 0
    local state = immune.state or "patrol"
    local slots = macro and Config.ArtSlots.macrophage or Config.ArtSlots.tCell
    local variant = immune.variant or 1
    if type(slots) == "table" and #slots > 0 then
        -- Spawn already gives every immune a random, immutable phase. Reuse it
        -- instead of drawing random numbers or storing new state on the entity.
        local fraction = (phase % TAU) / TAU
        variant = math.floor(fraction * #slots) + 1
        -- Legacy records without a phase retain their explicit variant.
        if immune.phase == nil then variant = immune.variant or immune.id or 1 end
    end
    local path = artSlot(slots, variant)
    local fillByPath = Config.CellVisual.immuneFillByPath or EMPTY
    local fill = path and fillByPath[path] or nil
    local size = r * 2 / (fill or (macro and Config.CellVisual.macrophageFill or Config.CellVisual.tCellFill))
    local alpha = state == "cooldown" and 0.78 or 0.96
    -- Only the body/glow breathes; warning ranges and labels keep their size.
    local vitality = self.vitality:Get(immune)
    nvgSave(nvg)
    nvgTranslate(nvg,x,y)
    nvgScale(nvg,vitality and vitality.sx or 1,vitality and vitality.sy or 1)
    nvgTranslate(nvg,-x,-y)
    local drew = false
    if path and macro then
        drew = VU.DrawSpriteTinted(nvg, path, x, y, size, Config.ArtSlots.macrophageTint or WHITE_TINT, alpha)
    elseif path then drew = VU.DrawSpriteFit(nvg, path, x, y, size, size, alpha) end
    if drew then
        local kind = macro and 2 or (path == Config.ArtSlots.tCell[1] and 3 or 4)
        self.fluorescence:Draw(nvg,kind,x,y,size,alpha,time,phase,r*2)
    end
    if path and self.immuneArtStatus[path] ~= drew then
        self.immuneArtStatus[path] = drew
        print(string.format("[CellView] 免疫贴图 %s：%s", path, drew and "加载成功" or "失败，矢量回退"))
    end
    if not drew then
        nvgBeginPath(nvg)
        nvgCircle(nvg, x, y, r)
        nvgFillColor(nvg, VU.RGBA(macro and WHITE_TINT or color, alpha * 0.65))
        nvgFill(nvg)
        nvgBeginPath(nvg)
        nvgCircle(nvg, x, y, r * 0.40)
        nvgFillColor(nvg, VU.RGBA({ 26, 30, 62, 255 }, alpha))
        nvgFill(nvg)
    end
    nvgRestore(nvg)
    local active = state == "locked" or state == "warning" or state == "chase" or state == "attack" or state == "investigate"
    nvgBeginPath(nvg)
    nvgCircle(nvg, x, y, r + 2)
    nvgStrokeColor(nvg, VU.RGBA(color, active and 0.75 or 0.32))
    nvgStrokeWidth(nvg, state == "attack" and 1.8 or 1.0)
    nvgStroke(nvg)
    if state=="processing" then
        mapText(nvg,x,y-r-16,string.format("处理负载 %.1f",immune.processingLoad or 0),color,.95,9)
    elseif immune.hotspotCleanup and not active then mapText(nvg,x,y-r-16,"清理热点",color,.85,9)
    elseif immune.respondingToAlarm then mapText(nvg,x,y-r-16,"响应报警",color,.85,9)
    elseif immune._screenCellId then mapText(nvg,x,y-r-16,"检查组织",color,.85,9)
    elseif state=="search" then mapText(nvg,x,y-r-16,"搜索旧位置",color,.85,9)
    elseif immune.signalInvestigation then mapText(nvg,x,y-r-16,"调查痕迹",color,.85,9) end
    if (immune.alarmVisibleUntil or 0)>time then mapText(nvg,x,y+r+12,"局部报警",color,.95,9) end
    if active or state == "cooldown" then
        local cfg = Config.Gameplay or EMPTY
        local remaining, duration = 0, 1
        if state == "locked" or state == "warning" then
            remaining, duration = math.max(0, immune.warningTimer or 0),
                math.max(0.001, immune.warningTime or cfg.immuneWarningSeconds or 2.8)
        elseif state == "investigate" then
            duration=immune.recognitionRequiredSeconds or cfg.immuneBehavior.recognitionSeconds
            remaining=math.max(0,duration-(immune.recognitionTimer or 0))
        elseif state == "attack" then
            remaining, duration = math.max(0, immune.attackTimer or 0),
                math.max(0.001, immune.attackWindup or cfg.immuneAttackWindup or 1.1)
        elseif state == "cooldown" then
            remaining, duration = math.max(0, immune.cooldown or 0), math.max(0.001, cfg.immuneAttackInterval or 2.8)
        end
        local progress = state == "chase" and 0.35 or unit(remaining / duration)
        if progress > 0 then
            nvgBeginPath(nvg)
            local angle = state == "chase" and (phase + time * 0.6) or -math.pi * 0.5
            nvgArc(nvg, x, y, r + 5, angle, angle + TAU * progress, NVG_CW)
            nvgStrokeColor(nvg, VU.RGBA(color, state == "cooldown" and 0.30 or 0.85))
            nvgStrokeWidth(nvg, 1.5)
            nvgStroke(nvg)
        end
        if state == "warning" or state == "locked" or state == "attack" or state=="investigate" then
            mapText(nvg, x, y - r - 16, string.format("%s %.1fs", state=="investigate" and "识别" or state == "attack" and "攻击" or "预警", remaining),
                color, 0.95, 9)
        end
    end
end

---@param nvg NVGContextWrapper
---@param x number
---@param y number
---@param r number
---@param effect table
function CellView:DrawEffect(nvg, x, y, r, effect)
    local t = unit(math.max(0, effect.age or 0) / math.max(0.001, effect.duration or 0.8))
    if t >= 1 then return end
    local fade = 1 - t
    local P = Config.Palette
    if effect.kind == "infect" then
        nvgBeginPath(nvg)
        nvgCircle(nvg, x, y, r * (0.9 + t * 0.25))
        nvgStrokeColor(nvg, VU.RGBA(P.infectWarm, fade * 0.70))
        nvgStrokeWidth(nvg, 1.6)
        nvgStroke(nvg)
    elseif effect.kind == "release" or effect.kind == "rupture" then
        -- 批次释放 / 死亡由不同的膜弧表现，不额外造病毒或粒子阵列。
        local rupture = effect.kind == "rupture"
        for i = 1, 4 do
            local angle = (i - 1) * TAU / 4
            nvgBeginPath(nvg)
            nvgArc(nvg, x, y, r * (0.94 + t * (rupture and 0.48 or 0.19)),
                angle + 0.12, angle + (rupture and 0.88 or 1.12), NVG_CW)
            nvgStrokeColor(nvg, VU.RGBA(rupture and P.damaged or P.infectWarm, fade * 0.75))
            nvgStrokeWidth(nvg, 1 + fade * 1.2)
            nvgStroke(nvg)
        end
    elseif effect.kind == "engulf" then
        nvgBeginPath(nvg)
        nvgCircle(nvg, x, y, r * (1 - t * 0.72))
        nvgStrokeColor(nvg, VU.RGBA(P.immuneCool, fade * 0.85))
        nvgStrokeWidth(nvg, 1.7)
        nvgStroke(nvg)
    elseif effect.kind == "absorb" then
        -- 向内收缩的范围脉冲仅为主动吸附反馈，不扩大实际感染或碰撞区域。
        nvgBeginPath(nvg)
        nvgCircle(nvg, x, y, r * (1 - t * 0.82))
        nvgStrokeColor(nvg, VU.RGBA(P.virus, fade * 0.58))
        nvgStrokeWidth(nvg, 1.8)
        nvgStroke(nvg)
    elseif effect.kind == "join" then
        nvgBeginPath(nvg)
        nvgCircle(nvg, x, y, r * (1.25 - t * 0.50))
        nvgStrokeColor(nvg, VU.RGBA(P.infectWarm, fade * 0.75))
        nvgStrokeWidth(nvg, 1.1)
        nvgStroke(nvg)
    elseif effect.kind == "split" then
        for side = 1, 2 do
            local angle = (side - 1) * math.pi + 0.2
            nvgBeginPath(nvg)
            nvgArc(nvg, x, y, r * (0.75 + t * 1.1), angle, angle + math.pi * 0.7, NVG_CW)
            nvgStrokeColor(nvg, VU.RGBA(P.infectWarm, fade * 0.65))
            nvgStrokeWidth(nvg, 1.2)
            nvgStroke(nvg)
        end
    end
end

return CellView
