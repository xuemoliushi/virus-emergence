-- ============================================================================
-- ScaleManager.lua - 细胞玩法镜头管理（缓动缩放 + 尺度切换）
--
-- 依据玩法文档 §5:
--   - 滚轮向上: 逐步放大（本级缓动缩放）；到达放大极限后继续滚 → 进入更微观视图
--   - 滚轮向下: 逐步缩小；到达缩小极限后继续滚 → 返回上一尺度
--   - 跨尺度时保留当前选中的组织区域（SimState 是单一数据源，天然满足）
--   - 使用短暂镜头过渡连接视图（淡入淡出 + 缩放入场，不做物理连续无限放大）
--
-- 缩放手感（本文件核心）:
--   滚轮只修改 zoomTarget（目标值），实际 innerZoom 每帧按 easeInOutCubic
--   曲线追赶目标 → 起步加速、到位前减速，永远不会突变。
--   连续滚动时曲线不断重定向（始终处于加速段），停止滚动后减速归位。
--
-- 跨尺度切换手感（"放大到 300% → 慢慢渐变到下一层次"）:
--   1. 每格固定 +5% 目标缩放，实际缩放按 easeInOutCubic 加减速追赶
--   2. 到达 300% 极限后继续同向滚动 ZoomWheelThreshold 格 → 触发切换
--   3. 切换用 TransitionDuration 秒的 easeInOutCubic 交叉淡化 + 缩放入场，
--      旧层级继续放大淡出、新层级从大缩放到 1.0 缓缓落定 → "渐渐变成下一个层次"
--
-- 尺度顺序（宏观 → 微观）: 仅 cell(1)，不提供宿主/器官层入口
-- ============================================================================

local Config = require("Core.Config")
local EventBus = require("Core.EventBus")

--- easeInOutCubic: 前半段加速、后半段减速（"加速再缓慢归位"的曲线手感）
---@param t number 0..1
---@return number
local function easeInOutCubic(t)
    if t < 0.5 then
        return 4 * t * t * t
    end
    local f = -2 * t + 2
    return 1 - (f * f * f) / 2
end

---@class ScaleManager
local ScaleManager = {}
ScaleManager.__index = ScaleManager

---@return ScaleManager
function ScaleManager.New()
    local self = setmetatable({}, ScaleManager)
    self:init()
    return self
end

function ScaleManager:init()
    self.scaleIndex = 1          -- 开局直接进入细胞玩法
    self.wheelAccum = 0.0        -- 极限处的滚轮溢出累计（格数，触发跨尺度切换）
    self.notchAccum_ = 0.0       -- 平台 delta 归一化后的半格累加器
    ---@type number 跨尺度过渡进度 0..1（1 = 完全静止）
    self.transition = 1.0
    self.transitionFrom = 1      -- 过渡起点尺度序号
    self.transitionDir = 0       -- 1 放大 / -1 缩小 / 0 无

    -- 本级缩放: 目标值（滚轮直接设定）与动画当前值（每帧缓动追赶）
    ---@type number[]
    self.zoomTarget = { 1.0, 1.0 }
    ---@type number[]
    self.innerZoom = { 1.0, 1.0 }

    -- 缩放缓动动画状态（作用于当前尺度）
    self.zoomFrom_ = 1.0
    self.zoomTo_ = 1.0
    self.zoomT_ = 1.0            -- 1 = 动画完成
    self.zoomEaseDur_ = Config.ZoomEaseDuration  -- 当前缓动时长（入场时=过渡时长）
end

--- 当前尺度 id
---@return string "cell"
function ScaleManager:CurrentScale()
    return Config.Scales[self.scaleIndex]
end

--- 处理滚轮输入: 修改目标缩放，实际缩放由 Update 按缓动曲线追赶
---@param wheelDelta number 引擎 MouseWheel 值（正=向上=放大）
function ScaleManager:OnWheel(wheelDelta)
    if wheelDelta == 0 or self.transition < 1.0 then return end

    -- ⚠️ 平台归一化: 桌面滚轮每格 ±1；Web/WASM 上报像素 delta（约 ±100/格，
    --    见 urhox-libs ScrollView 的平台适配注释）。不归一化会把一格当成
    --    上百格 → 直接越过跨尺度阈值"一滚就切层"。
    local delta = wheelDelta
    if math.abs(delta) > 3 then
        delta = delta / 100
    end

    -- 小数格累加、按整格消费（触控板小 delta 也能平滑累积成格）
    self.notchAccum_ = (self.notchAccum_ or 0) + delta
    while math.abs(self.notchAccum_) >= 1.0 do
        local step = self.notchAccum_ > 0 and 1 or -1
        self.notchAccum_ = self.notchAccum_ - step
        self:ApplyNotch(step)
    end
end

--- 当前层的缩放参数（细胞 300% 每格+5%）
---@return number max
---@return number step
function ScaleManager:ZoomParams()
    local p = Config.ZoomPerScale[self:CurrentScale()]
    if p then return p.max, p.step end
    return 1.5, 0.10
end

--- 单格滚轮: 目标缩放 ±step，实际缩放由 Update 的 easeInOutCubic 加减速追赶
---@param step integer 1 放大 / -1 缩小
function ScaleManager:ApplyNotch(step)
    local idx = self.scaleIndex
    local cur = self.zoomTarget[idx]
    local zoomMax, zoomStep = self:ZoomParams()

    local raw = cur + zoomStep * step
    local newTarget = math.max(Config.ZoomMin, math.min(raw, zoomMax))

    -- 已到达缩放极限仍继续同向滚动 → 计入跨尺度切换；
    -- 本级还有缩放空间 → 清零累计（保证玩家能先充分缩放本级画面）
    local overflow = raw - newTarget
    local pushingPastLimit = (overflow > 0.0001 and step > 0)
                          or (overflow < -0.0001 and step < 0)
    if pushingPastLimit then
        self.wheelAccum = self.wheelAccum + step
    else
        self.wheelAccum = 0.0
    end

    self.zoomTarget[idx] = newTarget
    self:RetargetZoom(idx, newTarget)

    -- 极限溢出达到阈值: 跨尺度渐变切换
    if self.wheelAccum >= Config.ZoomWheelThreshold then
        self:TrySwitch(1)    -- 放大 → 更微观
    elseif self.wheelAccum <= -Config.ZoomWheelThreshold then
        self:TrySwitch(-1)   -- 缩小 → 更宏观
    end
end

--- 重启缩放缓动动画: 从当前动画值出发，easeInOutCubic 追向新目标
--- （滚轮触发 → 使用常规缓动时长；跨尺度入场单独用 TransitionDuration）
---@param idx integer
---@param target number
function ScaleManager:RetargetZoom(idx, target)
    self.zoomFrom_ = self.innerZoom[idx]
    self.zoomTo_ = target
    self.zoomT_ = 0.0
    self.zoomEaseDur_ = Config.ZoomEaseDuration
end

--- 尝试切换尺度
---@param dir integer 1 进入更微观 / -1 返回更宏观
function ScaleManager:TrySwitch(dir)
    ---@type integer
    local target = self.scaleIndex + dir
    if target < 1 or target > #Config.Scales then
        print("[ScaleManager] 已到达尺度边界，无法继续切换")
        return
    end

    local prevScale = self:CurrentScale()
    self.transitionFrom = self.scaleIndex
    self.scaleIndex = target
    self.transitionDir = dir
    self.transition = 0.0
    self.wheelAccum = 0.0

    -- 新尺度入场动画与交叉淡化同步（同用 TransitionDuration）→ "渐渐变成下一个层次"
    --   放大(更微观): 从放大态进入缓缓落定到 1.0 → "钻入内部"感
    --   缩小(更宏观): 从缩小态浮现缓缓升回 1.0 → "拉出全貌"感
    local entryZoom = dir > 0 and 1.5 or 0.75
    self.innerZoom[target] = entryZoom
    self.zoomTarget[target] = 1.0
    self.zoomFrom_ = entryZoom
    self.zoomTo_ = 1.0
    self.zoomT_ = 0.0
    self.zoomEaseDur_ = Config.TransitionDuration

    print(string.format("[ScaleManager] 尺度切换: %s → %s", prevScale, self:CurrentScale()))
    EventBus.Emit(EventBus.Events.SCALE_CHANGED,
        { scale = self:CurrentScale(), prevScale = prevScale })
end

--- 直接跳到指定尺度（调试/结局演示用）
---@param scaleId string
---@param immediate boolean? 黑屏遮挡下直接落定，省略跨尺度交叉淡化。
function ScaleManager:JumpTo(scaleId, immediate)
    for i, id in ipairs(Config.Scales) do
        if id == scaleId and (i ~= self.scaleIndex or (immediate and self:IsTransitioning())) then
            if immediate then
                local prevScale = self:CurrentScale()
                self.scaleIndex, self.transitionFrom = i, i
                self.transition, self.transitionDir = 1, 0
                self.wheelAccum, self.notchAccum_ = 0, 0
                self.innerZoom[i], self.zoomTarget[i] = 1, 1
                self.zoomFrom_, self.zoomTo_, self.zoomT_ = 1, 1, 1
                EventBus.Emit(EventBus.Events.SCALE_CHANGED, { scale = id, prevScale = prevScale })
                return
            end
            self:TrySwitch(i - self.scaleIndex)
            return
        end
    end
end

--- 每帧更新: 跨尺度过渡 + 本级缩放缓动动画
---@param dt number
function ScaleManager:Update(dt)
    if self.transition < 1.0 then
        self.transition = math.min(1.0, self.transition + dt / Config.TransitionDuration)
        if self.transition >= 1.0 then
            self.transitionDir = 0
        end
    end

    -- 本级缩放: easeInOutCubic 追赶目标（加速 → 减速，不突变）
    if self.zoomT_ < 1.0 then
        self.zoomT_ = math.min(1.0, self.zoomT_ + dt / self.zoomEaseDur_)
        local e = easeInOutCubic(self.zoomT_)
        self.innerZoom[self.scaleIndex] = self.zoomFrom_ + (self.zoomTo_ - self.zoomFrom_) * e
    end
end

-- ============================================================================
-- 渲染插值参数（场景读取）
-- ============================================================================

--- 过渡进度缓动值（0→1, easeInOutCubic: 缓起缓落，交叉淡化更"渐渐"）
---@return number
function ScaleManager:TransitionProgress()
    return easeInOutCubic(self.transition)
end

--- 当前应显示的缩放系数（已含每帧缓动动画，场景直接使用）
---@return number
function ScaleManager:CurrentZoom()
    return self.innerZoom[self.scaleIndex] or 1.0
end

--- 过渡淡入 alpha（0→1），场景用它做淡入
---@return number
function ScaleManager:FadeAlpha()
    return self:TransitionProgress()
end

--- 是否处于跨尺度过渡中
---@return boolean
function ScaleManager:IsTransitioning()
    return self.transition < 1.0
end

return ScaleManager
