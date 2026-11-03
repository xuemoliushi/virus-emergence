-- ============================================================================
-- RespiratoryMap.lua - 第一优先级固定呼吸道地图，纯 Lua 5.4，无引擎依赖。
-- 从 scaffold-2d 的“配置 -> 初始化 -> 玩法数据”结构提取纯数据模块；不创建 UI/Scene。
-- 健康肺图仅作“气管 -> 左右支气管 -> 深肺”的结构参考，不加载/复制图片。
-- 所有长度单位为米；原点左上，x 向右，二维 y 向下；phase/rotation 单位为弧度。
-- 手工锚点提供可玩性骨架；每局使用独立确定性 PRNG 做有界抖动与补点。
-- ============================================================================
-- 碰撞设计（先设计后实现，图不按比例）：
--
--                   (1 上呼吸道 13,3.9)
--                         ||  c1 主干
--                   (2 气管 13.1,10.5)
--                    /                 \
--              c2 低流                  c3 高流
--              /                           \
--       (3 左肺 7.1,18)     XXXX     (4 右肺 19.2,17.7)
--             |             XXXX             |
--         c4 宽缓绕路       XXXX         c5 较窄捷径
--              \                           /
--                   (5 深肺 13.4,27.55)
--
-- 区域：5 个椭圆；通道：折线的圆头/圆角胶囊并集，width 是完整宽度。
-- XXXX 为不可玩空隙，左右支路只能经气管或深肺绕行，不能直穿中央。
-- 检测目的：约束病毒群/游离病毒/免疫圆体；普通细胞是感染目标，不是墙体。
-- margin >= 0：胶囊半宽减 margin；椭圆采用安全的同心等比内缩。
-- 椭圆内缩系数 1-margin/min(rx,ry) 保证整个圆体在椭圆内；不能简单 rx-r,ry-r，
-- 后者在斜角可能穿墙。并集交界处此法略保守，布局有充分重叠避免接缝卡住。
-- Move 对每个凸形状解析求线段区间，合并从起点开始的连续覆盖，再投影墙面切线。
-- 不以“目标点合法”替代扫掠；任意步长都不能跳过中间空隙/狭缝。
-- 边界推演：擦边/端帽/折线拐角/椭圆尖端/上下边界/大步长/非法起点/半径过大。
-- 非法起点保持原位，修复出生点应由调用方负责；本模块不把对象传送到另一侧。
-- ============================================================================

---@alias RespiratoryRegionType 'UPPER_AIRWAY'|'TRACHEA'|'BRONCHUS_LEFT'|'BRONCHUS_RIGHT'|'DEEP_LUNG'

---@class RespiratoryMapConfig
---@field width? number
---@field height? number
---@field cellCount? integer v1 最多72；v2/v3 最多216，v3须容纳出生、通道、八向边缘保留点。
---@field cellRadiusMin? number 米
---@field cellRadiusMax? number 米
---@field seed? number 仅用于外观，不改变布局或全局 math.random 状态。
---@field mapSeed? number|string
---@field mapGenerationVersion? integer
---@field mapRegionCount? integer
---@field mapRegionSpacing? number
---@field mapChannelWidth? number
---@field mapDensity? number
---@field mapEdgeCoverage? number
---@field mapCoverageSampleSpacing? number
---@field mapCellGap? number
---@field mapRouteTargetSpacing? number
---@field mapSpawnSafeRadius? number
---@field groupRadius? number

---@class RespiratoryPoint
---@field x number
---@field y number

---@class RespiratoryRegion
---@field id integer
---@field type RespiratoryRegionType
---@field name string
---@field depth number
---@field x number
---@field y number
---@field rx number
---@field ry number
---@field neighbors integer[]
---@field baseImmunePressure number 0..1 的基础压力，病程系统自行使用。
---@field inflammation number
---@field damage number

---@class RespiratoryChannel
---@field id integer
---@field points RespiratoryPoint[] 有序折线点，方向为浅部到深部，不是贝塞尔控制点。
---@field width number 完整可玩走廊/流带宽度（米），绘制时使用圆头圆角。
---@field strength number 无量纲，乘 speed 得中心流速。
---@field speed number 米/秒
---@field channelType 'normal'|'fast'
---@field connectedRegions integer[]

---@class RespiratoryCellSpawn
---@field id integer
---@field x number
---@field y number
---@field radius number
---@field variant integer 普通细胞美术变体 1..4，不是特殊细胞类型。
---@field phase number 弧度
---@field rotation number 弧度
---@field regionId integer

---@class RespiratoryImmuneSpawn: RespiratoryPoint
---@field regionId integer

---@class RespiratorySegment
---@field ax number
---@field ay number
---@field bx number
---@field by number
---@field minX number
---@field maxX number
---@field minY number
---@field maxY number
---@field ux number 单位切向量 x
---@field uy number 单位切向量 y
---@field length number
---@field along number 此段起点在整条通道上的累计弧长。
---@field halfWidth number
---@field channelId integer

---@class RespiratorySweepInterval
---@field enter number
---@field leave number
---@field kind 'ellipse'|'capsule'
---@field index number

---@class RespiratoryMap
---@field width number
---@field height number
---@field regions RespiratoryRegion[]
---@field channels RespiratoryChannel[]
---@field cells RespiratoryCellSpawn[]
---@field startPoints table<string, RespiratoryPoint>
---@field immuneSpawns RespiratoryImmuneSpawn[]
---@field startType RespiratoryRegionType
---@field seed integer
---@field generationVersion integer
---@field generationMs number?
---@field fallbackCount integer?
---@field cellGap number?
---@field spawnSafeRadius number?
---@field _scale number
---@field _segments RespiratorySegment[]
---@field _channelLengths table<number, number>
---@field flowOverride {x:number,y:number,ux:number,uy:number,radius:number,expiresAt:number}?
local Map = {}
Map.__index = Map

local MapRandom = require("Core.MapRandom")
local Generation = require("Core.TissueGeneration")
local TAU = math.pi * 2
local BASE_WIDTH, BASE_HEIGHT = 26, 32
local SWEEP_EPSILON = 1e-12

---@param value number
---@return boolean
local function IsFinite(value)
    return type(value) == "number" and value == value and value > -math.huge and value < math.huge
end

---@param value number
---@param lo number
---@param hi number
---@return number
local function Clamp(value, lo, hi)
    return math.max(lo, math.min(hi, value))
end

---@param ax number
---@param ay number
---@param bx number
---@param by number
---@return number
local function Distance(ax, ay, bx, by)
    local dx, dy = bx - ax, by - ay
    return math.sqrt(dx * dx + dy * dy)
end

--- 局部 Park-Miller PRNG，不调用 math.randomseed，也不随机化任何锚点。
---@param seed integer
---@return fun():number
local function AppearanceRandom(seed)
    local state = seed % 2147483647
    if state <= 0 then state = 1 end
    return function()
        state = (state * 48271) % 2147483647
        return state / 2147483647
    end
end

--- 72 个手工有机锚点；间距刻意不相等，通道旁有目标，中央不铺细胞。
--- 上呼吸道/气管/深肺开局 2 米内分别有 4/4/3 个普通细胞。
---@type RespiratoryPoint[]
local CELL_ANCHORS = {
    -- 上呼吸道（10）
    { x = 11.7, y = 2.3 }, { x = 14.4, y = 2.5 },
    { x = 13.5, y = 4.7 }, { x = 12.8, y = 1.9 },
    { x = 10.6, y = 4.0 }, { x = 11.2, y = 5.2 },
    { x = 12.55, y = 5.75 }, { x = 14.15, y = 5.7 },
    { x = 15.6, y = 4.3 }, { x = 15.5, y = 3.0 },
    -- 气管与分叉两侧（12）
    { x = 12.85, y = 7.6 }, { x = 12.1, y = 8.6 },
    { x = 14.0, y = 8.35 }, { x = 11.95, y = 9.8 },
    { x = 14.25, y = 9.9 }, { x = 11.95, y = 11.2 },
    { x = 14.25, y = 11.25 }, { x = 12.15, y = 12.6 },
    { x = 14.05, y = 12.65 }, { x = 12.95, y = 13.75 },
    { x = 13.55, y = 6.8 }, { x = 14.9, y = 13.7 },
    -- 左支气管组织（16）：宽阔、低流、外侧绕行
    { x = 6.9, y = 13.65 }, { x = 8.2, y = 14.45 },
    { x = 5.2, y = 15.25 }, { x = 9.7, y = 15.6 },
    { x = 6.55, y = 15.55 }, { x = 4.0, y = 17.0 },
    { x = 8.0, y = 16.9 }, { x = 10.25, y = 17.8 },
    { x = 5.6, y = 18.0 }, { x = 3.75, y = 19.5 },
    { x = 7.0, y = 19.4 }, { x = 9.2, y = 20.0 },
    { x = 5.15, y = 20.6 }, { x = 7.6, y = 21.85 },
    { x = 4.95, y = 22.4 }, { x = 8.45, y = 22.85 },
    -- 右支气管组织（16）：高流带穿过内侧，带外仍可停留感染
    { x = 19.4, y = 13.1 }, { x = 17.8, y = 14.15 },
    { x = 21.2, y = 14.5 }, { x = 19.8, y = 15.0 },
    { x = 16.6, y = 16.0 }, { x = 22.4, y = 16.3 },
    { x = 18.3, y = 16.5 }, { x = 20.8, y = 17.4 },
    { x = 16.3, y = 18.2 }, { x = 23.05, y = 18.0 },
    { x = 18.3, y = 18.75 }, { x = 21.75, y = 19.7 },
    { x = 16.85, y = 20.55 }, { x = 19.9, y = 20.6 },
    { x = 18.1, y = 22.25 }, { x = 20.4, y = 22.7 },
    -- 深肺（18）：横向汇合的组织袋，开局留空而不在簇中心
    { x = 11.45, y = 27.55 }, { x = 14.45, y = 27.65 },
    { x = 12.65, y = 25.85 }, { x = 14.2, y = 25.7 },
    { x = 11.15, y = 25.7 }, { x = 12.05, y = 29.45 },
    { x = 13.9, y = 29.55 }, { x = 16.0, y = 28.9 },
    { x = 10.0, y = 28.6 }, { x = 9.4, y = 26.8 },
    { x = 7.4, y = 27.55 }, { x = 8.0, y = 28.8 },
    { x = 10.6, y = 29.5 }, { x = 16.3, y = 26.2 },
    { x = 17.6, y = 27.7 }, { x = 18.85, y = 26.5 },
    { x = 19.25, y = 28.2 }, { x = 17.8, y = 29.1 },
}

---@param segment RespiratorySegment
---@param x number
---@param y number
---@return number distance
---@return number nearestX
---@return number nearestY
---@return number alongOnSegment
local function NearestOnSegment(segment, x, y)
    local along = Clamp((x - segment.ax) * segment.ux + (y - segment.ay) * segment.uy, 0, segment.length)
    local px, py = segment.ax + segment.ux * along, segment.ay + segment.uy * along
    return Distance(x, y, px, py), px, py, along
end

---@param region RespiratoryRegion
---@param margin number
---@return number rx
---@return number ry
local function InnerEllipse(region, margin)
    local factor = math.max(0, 1 - margin / math.min(region.rx, region.ry))
    return region.rx * factor, region.ry * factor
end

---@param cfg? RespiratoryMapConfig
---@param startType? RespiratoryRegionType 仅接受 UPPER_AIRWAY/TRACHEA/DEEP_LUNG。
---@return RespiratoryMap
function Map.New(cfg, startType)
    if cfg and (cfg.mapGenerationVersion==4 or cfg.mapGenerationVersion==5) then
        return require('Core.FlatWorldMap').New(cfg,startType) --[[@as RespiratoryMap]]
    end
    local instance = setmetatable({}, Map)
    instance:Init(cfg or {}, startType or "UPPER_AIRWAY")
    return instance
end

---@param cfg RespiratoryMapConfig
---@param startType RespiratoryRegionType
function Map:Init(cfg, startType)
    self.width = cfg.width or BASE_WIDTH
    self.height = cfg.height or BASE_HEIGHT
    assert(IsFinite(self.width) and self.width > 0, "呼吸道地图：width 必须是正数（米）")
    assert(IsFinite(self.height) and self.height > 0, "呼吸道地图：height 必须是正数（米）")
    local count = cfg.cellCount or #CELL_ANCHORS
    local minRadius, maxRadius = cfg.cellRadiusMin or 0.34, cfg.cellRadiusMax or 0.48
    local version = cfg.mapGenerationVersion or 1
    assert(version == 1 or version == 2 or version == 3, "Unsupported mapGenerationVersion")
    local seed = version == 1 and (cfg.seed or 314159) or cfg.mapSeed
    if seed == nil then seed = MapRandom.NewSeed() end
    assert(IsFinite(count) and count == math.floor(count) and count >= 0 and count <= #CELL_ANCHORS * 3,
        "呼吸道地图：细胞数量必须在 0..216 之间")
    assert(IsFinite(minRadius) and IsFinite(maxRadius) and minRadius > 0 and maxRadius >= minRadius,
        "呼吸道地图：细胞半径范围无效")
    assert(type(seed) == "number" or type(seed) == "string", "呼吸道地图：mapSeed 必须是数字或文本")
    self.seed = MapRandom.Normalize(seed)
    self.generationVersion = version
    self.startType = startType
    self.regions = {}
    self.channels = {}
    self.cells = {}
    self.startPoints = {}
    self.immuneSpawns = {}
    self._segments = {}
    self._channelLengths = {}

    local sx, sy = self.width / BASE_WIDTH, self.height / BASE_HEIGHT
    self._scale = math.min(sx, sy)
    local topology = MapRandom.New(self.seed, 10)
    local warpX, warpY = {}, {}
    for i=1,5 do
        warpX[i]=(topology()-.5)*1.2*self._scale
        warpY[i]=(topology()-.5)*.6*self._scale
    end
    assert((cfg.mapRegionCount or 5)==5, "This generation version supports five connected regions")
    ---@param x number
    ---@param y number
    ---@return RespiratoryPoint
    local function Point(x, y)
        if version==1 then return {x=x*sx,y=y*sy} end
        local band=math.max(1,math.min(4,math.floor(y/8)+1))
        local t=math.max(0,math.min(1,y/8-(band-1)))
        local amplitude=cfg.mapRegionSpacing or 3
        local factor=amplitude/3
        return {x=x*sx+(warpX[band]*(1-t)+warpX[band+1]*t)*factor,
            y=y*sy+(warpY[band]*(1-t)+warpY[band+1]*t)*factor}
    end

    ---@param id integer
    ---@param regionType RespiratoryRegionType
    ---@param name string
    ---@param depth number
    ---@param x number
    ---@param y number
    ---@param rx number
    ---@param ry number
    ---@param neighbors integer[]
    ---@param pressure number
    local function Region(id, regionType, name, depth, x, y, rx, ry, neighbors, pressure)
        local center=Point(x,y)
        self.regions[id] = {
            id = id, type = regionType, name = name, depth = depth,
            x = center.x, y = center.y, rx = rx * sx, ry = ry * sy,
            neighbors = neighbors, baseImmunePressure = pressure, inflammation = 0, damage = 0,
        }
    end
    Region(1, "UPPER_AIRWAY", "上呼吸道", 1, 13.0, 3.9, 3.55, 2.65, { 2 }, 0.12)
    Region(2, "TRACHEA", "气管主干", 2, 13.1, 10.5, 1.85, 4.3, { 1, 3, 4 }, 0.24)
    Region(3, "BRONCHUS_LEFT", "左支气管", 3, 7.1, 18.0, 4.6, 6.0, { 2, 5 }, 0.40)
    Region(4, "BRONCHUS_RIGHT", "右支气管", 3, 19.2, 17.7, 4.5, 5.9, { 2, 5 }, 0.47)
    Region(5, "DEEP_LUNG", "肺部深区", 4, 13.4, 27.55, 7.7, 3.2, { 3, 4 }, 0.68)

    self.channels = {
        { id = 1, points = { Point(13.0, 3.9), Point(12.8, 6.8), Point(13.2, 9.0), Point(13.1, 12.5) },
          width = 2.7 * self._scale, strength = 0.62, speed = 1.15, channelType = "normal", connectedRegions = { 1, 2 } },
        { id = 2, points = { Point(13.1, 12.5), Point(11.0, 14.3), Point(8.2, 15.6), Point(6.0, 18.0) },
          width = 3.1 * self._scale, strength = 0.38, speed = 0.65, channelType = "normal", connectedRegions = { 2, 3 } },
        { id = 3, points = { Point(13.1, 12.5), Point(15.4, 13.6), Point(17.6, 15.0), Point(19.2, 17.7) },
          width = 2.5 * self._scale, strength = 0.78, speed = 1.60, channelType = "fast", connectedRegions = { 2, 4 } },
        { id = 4, points = { Point(6.0, 18.0), Point(5.8, 20.9), Point(7.0, 23.3), Point(9.2, 26.7), Point(12.3, 27.8) },
          width = 3.3 * self._scale, strength = 0.22, speed = 0.60, channelType = "normal", connectedRegions = { 3, 5 } },
        { id = 5, points = { Point(19.2, 17.7), Point(19.6, 20.5), Point(18.3, 23.4), Point(16.3, 25.8), Point(14.6, 27.4) },
          width = 2.7 * self._scale, strength = 0.88, speed = 1.60, channelType = "fast", connectedRegions = { 4, 5 } },
    }
    for _, channel in ipairs(self.channels) do
        if version>=2 then channel.width=channel.width*((cfg.mapChannelWidth or 3)/3) end
        local along = 0
        for i = 1, #channel.points - 1 do
            local a, b = channel.points[i], channel.points[i + 1]
            local length = Distance(a.x, a.y, b.x, b.y)
            assert(length > 0, "呼吸道地图：通道包含零长度线段")
            self._segments[#self._segments + 1] = {
                ax = a.x, ay = a.y, bx = b.x, by = b.y,
                ux = (b.x - a.x) / length, uy = (b.y - a.y) / length,
                length = length, along = along, halfWidth = channel.width * 0.5, channelId = channel.id,
                minX=math.min(a.x,b.x)-channel.width*.5, maxX=math.max(a.x,b.x)+channel.width*.5,
                minY=math.min(a.y,b.y)-channel.width*.5, maxY=math.max(a.y,b.y)+channel.width*.5,
            }
            along = along + length
        end
        self._channelLengths[channel.id] = along
    end

    self.startPoints = {
        UPPER_AIRWAY = Point(13.0, 3.1),
        TRACHEA = Point(13.1, 10.5),
        DEEP_LUNG = Point(12.9, 27.4),
    }
    assert(self.startPoints[startType], "呼吸道地图：startType 必须为 UPPER_AIRWAY、TRACHEA 或 DEEP_LUNG")
    local immuneAnchors = { Point(10.6, 4.9), Point(14.9, 13.5), Point(4.3, 16.0),
        Point(5.0, 21.75), Point(21.75, 20.5), Point(18.8, 28.9) }
    for _, point in ipairs(immuneAnchors) do
        self.immuneSpawns[#self.immuneSpawns + 1] = {
            x = point.x, y = point.y, regionId = self:RegionAt(point.x, point.y),
        }
    end

    if version==3 then
        Generation.Populate(self,cfg)
    elseif version==2 then
        require("Core.TissueGenerationV2").Populate(self,cfg)
    else
        local random=AppearanceRandom(self.seed)
        assert(count<=#CELL_ANCHORS,"Legacy map supports at most 72 cells")
        for i=1,count do
            local anchor=CELL_ANCHORS[i] --[[@as RespiratoryPoint]]
            local radius=minRadius+random()*(maxRadius-minRadius)
            self.cells[i]={id=i,x=anchor.x*sx,y=anchor.y*sy,radius=radius,
                variant=math.floor(random()*4)+1,phase=random()*TAU,rotation=random()*TAU,
                regionId=self:RegionAt(anchor.x*sx,anchor.y*sy)}
        end
    end
    print(string.format("[Map] seed=%d generation=%d %.1fx%.1fm regions=%d channels=%d cells=%d generationMs=%.2f fallback=%d",
        self.seed,version,self.width,self.height,#self.regions,#self.channels,#self.cells,
        self.generationMs or 0,self.fallbackCount or 0))
end

--- 安全的圆体中心检测：margin=0 为椭圆/走廊真实并集；margin>0 略保守。
---@param x number
---@param y number
---@param margin? number
---@return boolean
function Map:Contains(x, y, margin)
    local radius = margin or 0
    if not IsFinite(x) or not IsFinite(y) or not IsFinite(radius) or radius < 0 then return false end
    if x < radius or y < radius or x > self.width - radius or y > self.height - radius then return false end
    for _, region in ipairs(self.regions) do
        local rx, ry = InnerEllipse(region, radius)
        if rx > 0 and ry > 0 then
            local dx, dy = (x - region.x) / rx, (y - region.y) / ry
            if dx * dx + dy * dy <= 1 then return true end
        end
    end
    for _, segment in ipairs(self._segments) do
        local halfWidth = segment.halfWidth - radius
        if halfWidth > 0 and x>=segment.minX and x<=segment.maxX and y>=segment.minY and y<=segment.maxY then
            local distance = NearestOnSegment(segment, x, y)
            if distance <= halfWidth then return true end
        end
    end
    return false
end

--- 线段与凸圆/椭圆区间。B 是通常二次方程中一阶系数的一半。
---@param px number
---@param py number
---@param dx number
---@param dy number
---@return number? enter
---@return number? leave
local function UnitCircleInterval(px, py, dx, dy)
    local a = dx * dx + dy * dy
    local b = px * dx + py * dy
    local c = px * px + py * py - 1
    if a <= SWEEP_EPSILON * SWEEP_EPSILON then
        if c <= 0 then return 0, 1 end
        return nil, nil
    end
    local discriminant = b * b - a * c
    if discriminant < 0 then return nil, nil end
    local root = math.sqrt(discriminant)
    local enter, leave = (-b - root) / a, (-b + root) / a
    if c <= 0 then enter = 0 end -- 边界起点的浮点舍入不能阻止向内移动。
    if leave < 0 or enter > 1 then return nil, nil end
    return math.max(0, enter), math.min(1, leave)
end

---@param p number
---@param d number
---@param lo number
---@param hi number
---@param enter number
---@param leave number
---@return number? newEnter
---@return number? newLeave
local function ClipSlab(p, d, lo, hi, enter, leave)
    if math.abs(d) <= SWEEP_EPSILON then
        if p < lo or p > hi then return nil, nil end
        return enter, leave
    end
    local a, b = (lo - p) / d, (hi - p) / d
    local newEnter, newLeave = math.max(enter, math.min(a, b)), math.min(leave, math.max(a, b))
    if newEnter > newLeave then return nil, nil end
    return newEnter, newLeave
end

--- 胶囊 = 定向矩形 + 两个端圆；整体凸，所有命中区间的最小/最大值即完整区间。
---@param segment RespiratorySegment
---@param x number
---@param y number
---@param dx number
---@param dy number
---@param halfWidth number
---@return number? enter
---@return number? leave
local function CapsuleInterval(segment, x, y, dx, dy, halfWidth)
    local px, py = x - segment.ax, y - segment.ay
    local enter, leave = ClipSlab(px * segment.ux + py * segment.uy,
        dx * segment.ux + dy * segment.uy, 0, segment.length, 0, 1)
    if enter and leave then
        enter, leave = ClipSlab(-px * segment.uy + py * segment.ux,
            -dx * segment.uy + dy * segment.ux, -halfWidth, halfWidth, enter, leave)
    end
    local a, b = UnitCircleInterval(px / halfWidth, py / halfWidth, dx / halfWidth, dy / halfWidth)
    if a and b then
        enter = enter and math.min(enter, a) or a
        leave = leave and math.max(leave, b) or b
    end
    a, b = UnitCircleInterval((x - segment.bx) / halfWidth, (y - segment.by) / halfWidth, dx / halfWidth, dy / halfWidth)
    if a and b then
        enter = enter and math.min(enter, a) or a
        leave = leave and math.max(leave, b) or b
    end
    if enter and leave and NearestOnSegment(segment, x, y) <= halfWidth then enter = 0 end
    return enter, leave
end

--- 从起点合并线段覆盖，只到第一个空隙；不合并“相近”的间隔，避免穿极细空隙。
---@param x number
---@param y number
---@param dx number
---@param dy number
---@param radius number
---@return number fraction
---@return number normalX
---@return number normalY
---@return RespiratorySweepInterval? boundaryShape
function Map:_Sweep(x, y, dx, dy, radius)
    if self:_ConvexPathClear(x,y,x+dx,y+dy,radius) then return 1,0,0 end
    ---@type RespiratorySweepInterval[]
    local intervals = {}
    for i, region in ipairs(self.regions) do
        local rx, ry = InnerEllipse(region, radius)
        if rx > 0 and ry > 0 then
            local enter, leave = UnitCircleInterval((x - region.x) / rx, (y - region.y) / ry, dx / rx, dy / ry)
            if enter and leave then
                intervals[#intervals + 1] = { enter = enter, leave = leave, kind = "ellipse", index = i }
            end
        end
    end
    for i, segment in ipairs(self._segments) do
        local halfWidth = segment.halfWidth - radius
        if halfWidth > 0 then
            local enter, leave = CapsuleInterval(segment, x, y, dx, dy, halfWidth)
            if enter and leave then
                intervals[#intervals + 1] = { enter = enter, leave = leave, kind = "capsule", index = i }
            end
        end
    end
    table.sort(intervals, function(a, b)
        if a.enter == b.enter then return a.leave > b.leave end
        return a.enter < b.enter
    end)
    local frontier = 0
    ---@type RespiratorySweepInterval?
    local boundary = nil
    for _, interval in ipairs(intervals) do
        if interval.enter > frontier then break end
        if interval.leave > frontier then
            frontier = interval.leave
            boundary = interval
        end
        if frontier >= 1 then break end
    end

    -- 防止自定义长宽或后续几何数据把走廊延伸出地图矩形。
    local boundEnter, boundLeave = ClipSlab(x, dx, radius, self.width - radius, 0, 1)
    if boundEnter and boundLeave then
        boundEnter, boundLeave = ClipSlab(y, dy, radius, self.height - radius, boundEnter, boundLeave)
    end
    if not boundLeave then return 0, 0, 0 end
    if boundLeave < frontier then
        local hx, hy = x + dx * boundLeave, y + dy * boundLeave
        local nx, ny = 0, 0
        if hx <= radius + SWEEP_EPSILON then nx = -1
        elseif hx >= self.width - radius - SWEEP_EPSILON then nx = 1 end
        if hy <= radius + SWEEP_EPSILON then ny = -1
        elseif hy >= self.height - radius - SWEEP_EPSILON then ny = 1 end
        return boundLeave, nx, ny
    end
    if frontier >= 1 or not boundary then return frontier, 0, 0 end

    local hx, hy = x + dx * frontier, y + dy * frontier
    local nx, ny = 0, 0
    if boundary.kind == "ellipse" then
        local region = self.regions[boundary.index]
        local rx, ry = InnerEllipse(region, radius)
        nx, ny = (hx - region.x) / (rx * rx), (hy - region.y) / (ry * ry)
    else
        local segment = self._segments[boundary.index]
        local _, px, py = NearestOnSegment(segment, hx, hy)
        nx, ny = hx - px, hy - py
    end
    local length = math.sqrt(nx * nx + ny * ny)
    if length > 0 then return frontier, nx / length, ny / length, boundary end
    return frontier, 0, 0, boundary
end

--- 凸曲面上的切线一步会离开形状；把局部滑移目标映回接触形状内，再扫掠这条弦。
--- 不映回全地图“最近点”，也不跳到目标侧；映回的仍是起点可连续到达的同一凸形状。
---@param boundary RespiratorySweepInterval
---@param x number
---@param y number
---@param radius number
---@param skin number
---@return number x
---@return number y
function Map:_SlideTarget(boundary, x, y, radius, skin)
    if boundary.kind == "ellipse" then
        local region = self.regions[boundary.index]
        local rx, ry = InnerEllipse(region, radius + skin)
        if rx <= 0 or ry <= 0 then return x, y end
        local dx, dy = (x - region.x) / rx, (y - region.y) / ry
        local q = math.sqrt(dx * dx + dy * dy)
        if q > 1 then return region.x + (x - region.x) / q, region.y + (y - region.y) / q end
    else
        local segment = self._segments[boundary.index]
        local distance, px, py = NearestOnSegment(segment, x, y)
        local halfWidth = segment.halfWidth - radius - skin
        if distance > halfWidth and halfWidth > 0 then
            return px + (x - px) * halfWidth / distance, py + (y - py) * halfWidth / distance
        end
    end
    return x, y
end

---@param x number
---@param y number
---@param tx number
---@param ty number
---@param radius? number
---@return boolean
-- Fast proof, not endpoint-only collision: both endpoints must be strictly
-- inside the SAME eroded convex ellipse/capsule and the map rectangle.
-- Their complete connecting segment then lies inside that primitive.
function Map:_ConvexPathClear(x,y,tx,ty,radius)
    local r=radius or 0
    if not IsFinite(x) or not IsFinite(y) or not IsFinite(tx) or not IsFinite(ty)
        or not IsFinite(r) or r<0 then return false end
    if math.min(x,tx)<r or math.min(y,ty)<r
        or math.max(x,tx)>self.width-r or math.max(y,ty)>self.height-r then return false end
    for _,region in ipairs(self.regions) do
        local rx,ry=InnerEllipse(region,r)
        if rx>0 and ry>0 then
            local ax,ay=(x-region.x)/rx,(y-region.y)/ry
            if ax*ax+ay*ay<1-1e-10 then
                local bx,by=(tx-region.x)/rx,(ty-region.y)/ry
                if bx*bx+by*by<1-1e-10 then return true end
            end
        end
    end
    for _,segment in ipairs(self._segments) do
        local width=segment.halfWidth-r
        if width>0 and x>=segment.minX and x<=segment.maxX and y>=segment.minY and y<=segment.maxY then
            local a=NearestOnSegment(segment,x,y)
            if a<width-1e-10 then
                local b=NearestOnSegment(segment,tx,ty)
                if b<width-1e-10 then return true end
            end
        end
    end
    return false
end

--- tx,ty 是绝对目标坐标；返回两个数字，不返回向量/表，也不做寻路。
--- 连续扫掠后最多 8 次滑移，凸曲面使用内投影弦，每一段均被扫掠；细胞不阻挡。
---@param x number
---@param y number
---@param tx number
---@param ty number
---@param radius? number
---@return number x
---@return number y
function Map:Move(x, y, tx, ty, radius)
    local r = radius or 0
    local travelX,travelY=tx-x,ty-y
    local minTravel=1e-6*self._scale
    if travelX*travelX+travelY*travelY>minTravel*minTravel and self:_ConvexPathClear(x,y,tx,ty,r) then
        return x+travelX,y+travelY
    end
    if not IsFinite(tx) or not IsFinite(ty) or not self:Contains(x, y, r) then return x, y end
    local dx, dy = tx - x, ty - y
    local skin = 1e-6 * self._scale
    for _ = 1, 8 do
        local length = math.sqrt(dx * dx + dy * dy)
        if not IsFinite(length) or length <= skin then break end
        local fraction, nx, ny, boundary = self:_Sweep(x, y, dx, dy, r)
        if fraction >= 1 then return x + dx, y + dy end
        local safeFraction = math.max(0, fraction - skin / length)
        local px, py = x + dx * safeFraction, y + dy * safeFraction
        -- 浮点误差只可使本次运动缩短，不能触发向目标/最近区域的传送修正。
        if not self:Contains(px, py, r) then break end
        x, y = px, py
        local remainingX, remainingY = dx * (1 - fraction), dy * (1 - fraction)
        local outward = remainingX * nx + remainingY * ny
        if outward <= 0 then break end
        local slideX, slideY = remainingX - nx * outward, remainingY - ny * outward
        if boundary then
            local targetX, targetY = self:_SlideTarget(boundary, x + slideX, y + slideY, r, skin)
            dx, dy = targetX - x, targetY - y
        else
            dx, dy = slideX, slideY
        end
    end
    return x, y
end

--- 椭圆重叠处选归一化距离最小的区域，不把右肺 id=4 当作比左肺更深。
--- 纯走廊段按真实弧长选择相邻区域；域外 id/depth 均为 0。
---@param x number
---@param y number
---@return integer regionId
---@return number depth
function Map:_Locate(x, y)
    ---@type RespiratoryRegion[]
    local regions = self.regions
    if not IsFinite(x) or not IsFinite(y) or x < 0 or y < 0 or x > self.width or y > self.height then return 0, 0 end
    local id, best = 0, math.huge
    for _, region in ipairs(self.regions) do
        local dx, dy = (x - region.x) / region.rx, (y - region.y) / region.ry
        local q = dx * dx + dy * dy
        if q <= 1 and q < best then id, best = region.id, q end
    end
    if id ~= 0 then return id, self.regions[id].depth end
    local corridorId, depth, nearest = 0, 0, math.huge
    for _, segment in ipairs(self._segments) do
        local distance, _, _, along = NearestOnSegment(segment, x, y)
        if distance <= segment.halfWidth and distance < nearest then
            local channel = self.channels[segment.channelId]
            local fromId, toId = channel.connectedRegions[1], channel.connectedRegions[#channel.connectedRegions]
            ---@cast fromId integer
            ---@cast toId integer
            local t = (segment.along + along) / self._channelLengths[channel.id]
            corridorId = t < 0.5 and fromId or toId
            depth = regions[fromId].depth + (regions[toId].depth - regions[fromId].depth) * t
            nearest = distance
        end
    end
    return corridorId, depth
end

---@param x number
---@param y number
---@return integer
function Map:RegionAt(x, y)
    local id = self:_Locate(x, y)
    return id
end

---@param x number
---@param y number
---@return number
function Map:DepthAt(x, y)
    local _, depth = self:_Locate(x, y)
    return depth
end

--- 局部组织流（米/秒），调用方乘 dt 及不同对象的 flowInfluence 后再交给 Move。
--- 以折线距离/真实完整宽度衰减；带外只有微弱组织漂移，绝不全图向下强吹。
--- 同一通道每次只取最近段；交汇流权重归一，避免多段/多通道叠出异常强流。
---@param x number
---@param y number
---@param time? number 秒
---@return number vx
---@return number vy
function Map:FlowAt(x, y, time)
    if not self:Contains(x, y) then return 0, 0 end
    local t = time or 0
    if not IsFinite(t) then t = 0 end
    ---@type table<number, RespiratorySegment>
    local nearestSegments = {}
    ---@type table<number, number>
    local distances = {}
    ---@type table<number, number>
    local alongs = {}
    for _, segment in ipairs(self._segments) do
        if x>=segment.minX and x<=segment.maxX and y>=segment.minY and y<=segment.maxY then
            local distance, _, _, along = NearestOnSegment(segment, x, y)
            if distance < segment.halfWidth and (not distances[segment.channelId] or distance < distances[segment.channelId]) then
                nearestSegments[segment.channelId] = segment
                distances[segment.channelId] = distance
                alongs[segment.channelId] = segment.along + along
            end
        end
    end
    local vx, vy, weightSum = 0, 0, 0
    for _, channel in ipairs(self.channels) do
        local segment = nearestSegments[channel.id]
        if segment then
            local u = distances[channel.id] / segment.halfWidth
            local weight = (1 - u * u) ^ 2
            local pulse = 0.94 + 0.06 * math.sin(t * 0.8 - alongs[channel.id] * 0.35)
            local speed = channel.strength * channel.speed * pulse
            vx, vy = vx + segment.ux * speed * weight, vy + segment.uy * speed * weight
            weightSum = weightSum + weight
        end
    end
    local denominator = math.max(1, weightSum)
    local tissueWeight = 1 - math.min(1, weightSum)
    local tissueX = 0.025 * math.sin(x * 0.7 + y * 0.17 + t * 0.33)
    local tissueY = 0.018 * math.cos(y * 0.53 - x * 0.2 + t * 0.29)
    local fx,fy=vx/denominator+tissueX*tissueWeight,vy/denominator+tissueY*tissueWeight
    local override=self.flowOverride
    if override and t<override.expiresAt then
        local d=Distance(x,y,override.x,override.y)
        if d<override.radius then
            local u=1-d/override.radius
            local blend=u*u*(3-2*u)
            local speed=math.sqrt(fx*fx+fy*fy)
            local original=math.atan(fy,fx)
            local wanted=math.atan(override.uy,override.ux)
            local difference=(wanted-original+math.pi)%(2*math.pi)-math.pi
            local angle=original+difference*blend
            fx,fy=math.cos(angle)*speed,math.sin(angle)*speed
        end
    end
    return fx,fy
end

--- 可选开发验收，返回 bool 和错误列表；不会修图/重掷种子/修改实例。
--- 0.5 米圆体逐段通过每条走廊；检查实际扫掠、区域图、三处开局和免疫间距。
---@return boolean ok
---@return string[] errors
function Map:Verify()
    ---@type RespiratoryRegion[]
    local regions = self.regions
    ---@type string[]
    local errors = {}
    local radius = self.generationVersion >= 2 and .5 or 0.5 * self._scale
    local nearbyRadius = self.generationVersion >= 2 and (self.spawnSafeRadius or 2) or 2.0 * self._scale
    ---@param ok boolean
    ---@param message string
    local function Check(ok, message)
        if not ok then errors[#errors + 1] = message end
    end
    ---@type table<number, boolean>
    local visited = { [1] = true }
    ---@type integer[]
    local queue = { 1 }
    local cursor = 1
    while cursor <= #queue do
        local id = queue[cursor]
        for _, neighbor in ipairs(self.regions[id].neighbors) do
            local other = self.regions[neighbor]
            Check(other ~= nil, "区域邻居索引无效")
            if other then
                local reciprocal = false
                for _, value in ipairs(other.neighbors) do
                    if value == id then reciprocal = true end
                end
                Check(reciprocal, "区域连接不是双向连接")
                if not visited[neighbor] then
                    visited[neighbor] = true
                    queue[#queue + 1] = neighbor
                end
            end
        end
        cursor = cursor + 1
    end
    for _, region in ipairs(self.regions) do
        Check(visited[region.id] == true, "区域未连通：" .. region.type)
        Check(self:Contains(region.x, region.y, radius), "区域中心容不下圆体：" .. region.type)
    end
    for _, channel in ipairs(self.channels) do
        local a = channel.points[1]
        Check(self:Contains(a.x, a.y, radius), "通道起点容不下圆体")
        local firstId = channel.connectedRegions[1] --[[@as integer]]
        local lastId = channel.connectedRegions[#channel.connectedRegions] --[[@as integer]]
        local firstRegion = regions[firstId]
        local lastRegion = regions[lastId]
        local x, y = self:Move(firstRegion.x, firstRegion.y, a.x, a.y, radius)
        Check(Distance(x, y, a.x, a.y) < 0.001 * self._scale, "通道无法到达起始区域")
        for i = 2, #channel.points do
            local b = channel.points[i]
            x, y = self:Move(x, y, b.x, b.y, radius)
            Check(Distance(x, y, b.x, b.y) < 0.001 * self._scale, "通道线段受阻：" .. channel.id)
        end
        x, y = self:Move(x, y, lastRegion.x, lastRegion.y, radius)
        Check(Distance(x, y, lastRegion.x, lastRegion.y) < 0.001 * self._scale, "通道无法到达目标区域")
    end
    local startOrder = { "UPPER_AIRWAY", "TRACHEA", "DEEP_LUNG" }
    for _, key in ipairs(startOrder) do
        local start = self.startPoints[key]
        Check(self:Contains(start.x, start.y, radius), "出生点不合法：" .. key)
        local nearby = 0
        for _, cell in ipairs(self.cells) do
            local distance = Distance(start.x, start.y, cell.x, cell.y)
            if distance <= nearbyRadius then nearby = nearby + 1 end
            Check(distance > radius + cell.radius, "出生点与细胞重叠：" .. key)
        end
        Check(nearby >= 2 and nearby <= 4, "出生点 2 米内应有 2..4 个细胞：" .. key .. "，实际 " .. nearby)
        for _, spawn in ipairs(self.immuneSpawns) do
            Check(Distance(start.x, start.y, spawn.x, spawn.y) >= (self.generationVersion>=2 and 4.5 or 3.0*self._scale), "免疫出生点距离开局太近：" .. key)
        end
    end
    for _, cell in ipairs(self.cells) do
        Check(self:Contains(cell.x, cell.y, cell.radius), "细胞不合法：" .. cell.id)
        Check(cell.regionId == self:RegionAt(cell.x, cell.y), "细胞所属区域不正确：" .. cell.id)
        for i=1,cell.id-1 do
            local other=self.cells[i]
            Check(Distance(cell.x,cell.y,other.x,other.y)>=cell.radius+other.radius+(self.cellGap or 0)-1e-8,
                "细胞间距不足："..cell.id.."/"..other.id)
        end
    end
    for _, spawn in ipairs(self.immuneSpawns) do
        Check(self:Contains(spawn.x, spawn.y, radius), "免疫出生点容不下圆体")
        Check(spawn.regionId > 0, "免疫出生点不属于可玩区域")
    end
    if self.generationVersion >= 2 then return #errors == 0, errors end
    local sx, sy = self.width / BASE_WIDTH, self.height / BASE_HEIGHT
    Check(not self:Contains(13.0 * sx, 19.0 * sy), "肺部中央空隙必须不可穿越")
    local crossX, crossY = self:Move(10.5 * sx, 18.0 * sy, 16.0 * sx, 18.0 * sy, radius)
    Check(crossX < 13.0 * sx and self:Contains(crossX, crossY, radius), "移动穿过了肺部中央空隙")
    return #errors == 0, errors
end

-- Canonical full initial map data, ordered by ID and fixed keys, no pairs order.
-- Used for reproducibility evidence, not a rounded position-only fingerprint.
function Map:Snapshot()
    local parts={"version="..self.generationVersion,"seed="..self.seed,
        string.format("size=%.17g,%.17g",self.width,self.height)}
    for _, r in ipairs(self.regions) do
        parts[#parts+1]=string.format("r:%d:%s:%.17g:%.17g:%.17g:%.17g:%.17g:%.17g:%s",
            r.id,r.type,r.x,r.y,r.rx,r.ry,r.depth,r.baseImmunePressure,table.concat(r.neighbors,","))
    end
    for _, ch in ipairs(self.channels) do
        parts[#parts+1]=string.format("ch:%d:%.17g:%.17g:%.17g:%s:%s",ch.id,ch.width,ch.speed,
            ch.strength,ch.channelType,table.concat(ch.connectedRegions,","))
        for _, p in ipairs(ch.points) do parts[#parts+1]=string.format("p:%.17g:%.17g",p.x,p.y) end
    end
    for _, key in ipairs({"UPPER_AIRWAY","TRACHEA","DEEP_LUNG"}) do
        local p=self.startPoints[key]
        parts[#parts+1]=string.format("start:%s:%.17g:%.17g",key,p.x,p.y)
    end
    for _, c in ipairs(self.cells) do
        parts[#parts+1]=string.format("c:%d:%d:%.17g:%.17g:%.17g:%d:%.17g:%.17g:HEALTHY",
            c.id,c.regionId,c.x,c.y,c.radius,c.variant,c.phase,c.rotation)
    end
    for i,p in ipairs(self.immuneSpawns) do
        parts[#parts+1]=string.format("immune:%d:%d:%.17g:%.17g",i,p.regionId,p.x,p.y)
    end
    return table.concat(parts,"\n")
end

return Map
