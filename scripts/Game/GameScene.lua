-- ============================================================================
-- GameScene.lua - 连续细胞世界画布（宿主鸟仅在结局展示）
-- 基于 scaffold-2d.lua：UI 自动驱动 Widget.Update / Render，无独立 NanoVG 帧。
-- 唯一模拟驱动：输入 → world:SetMovement → sim:Update → 镜头 / 缩放。
-- HUD 是兄弟组件；鼠标避让 HUD，移动键不受 UI 焦点 / 悬停影响。
-- ============================================================================

local UI = require("urhox-libs/UI")
local Config = require("Core.Config")
local EventBus = require("Core.EventBus")
local VU = require("Game.VisualUtils")
local CellView = require("Game.Views.CellView")
local PerformanceStats = require("Core.PerformanceStats")
local RenderMotion = require("Game.RenderMotion")
local CameraBounds = require("Game.CameraBounds")
local MapOverview = require("Game.MapOverview")
local MapExploration = require("Game.MapExploration")

---@class Rect4
---@field x number
---@field y number
---@field w number
---@field h number

---@param l Rect4
---@param x number
---@param y number
---@return boolean
local function contains(l, x, y)
    return l.w > 0 and l.h > 0
        and x >= l.x and x <= l.x + l.w and y >= l.y and y <= l.y + l.h
end

---@param widget Widget
---@return boolean
local function visible(widget)
    return widget:IsVisible() and widget.props.visibility ~= "hidden"
        and (widget.props.opacity or 1) > 0
end

local TOP_PANELS={"hudLeftScroll","hudStatsScroll","scalePanel","entityPanel"}
local BOTTOM_PANELS={"strategyBar","joystickPanel"}

---@param a Rect4
---@param b Rect4
---@return Rect4
local function intersect(a,b)
    local x,y=math.max(a.x,b.x),math.max(a.y,b.y)
    return {x=x,y=y,w=math.max(0,math.min(a.x+a.w,b.x+b.w)-x),
        h=math.max(0,math.min(a.y+a.h,b.y+b.h)-y)}
end

---@class GameScene : Widget
---@field tutorialZoom number
---@field entryZoom number
---@field entryActive boolean
---@field entryWarmFrames integer
---@field tutorialCue {x:number,y:number,angle:number}?
---@overload fun(props?: WidgetProps): GameScene
local GameScene = UI.Widget:Extend("GameScene")

---@param props table
function GameScene:Init(props)
    props = props or {}
    props.width = props.width or "100%"
    props.height = props.height or "100%"
    props.pointerEvents = props.pointerEvents or "auto"
    props.backgroundColor = props.backgroundColor or Config.Palette.bgDeep
    ---@type SimState
    local sim = props.sim
    ---@type ScaleManager
    local scaleMgr = props.scaleMgr
    props.sim, props.scaleMgr = nil, nil
    UI.Widget.Init(self, props)

    self.sim, self.scaleMgr = sim, scaleMgr
    self.cellView = CellView.New()
    self.renderMotion = RenderMotion.New()
    self.mapView = MapOverview.New()
    self.exploration = MapExploration.New()
    self.mapLegend = self.mapView:BuildLegend()
    self:AddChild(self.mapLegend)
    self.mapHUDActive = false
    ---@type table?
    self.cameraPlayer_ = nil
    self.beforeStep_ = function(world)
        self.renderMotion:Capture(world)
        self.exploration:Observe(world)
    end
    self.camera = { x = 0.0, y = 0.0 }
    self.tutorialZoom = 1
    self.endingZoom = 1
    ---@type {x:number,y:number,targetX:number,targetY:number,width:number,height:number}?
    self.endingFraming = nil
    self.entryZoom,self.entryActive = 1,false
    self.entryWarmFrames = 0
    self.tutorialCue = nil
    self.cellView:SetCamera(self.camera)
    self.pointer = { x = 0.0, y = 0.0, active = false, known = false }
    ---@type Rect4
    self.viewport = { x = 0, y = 0, w = 0, h = 0 }
    ---@type Rect4[]
    self.hudRects = {}
    ---@type table<string, Rect4>
    self.hudPanels = {}
    ---@type Widget?
    self.hudRoot = nil
    ---@type SwarmWorld?
    self.cameraWorld = nil
    ---@type string?
    self.outScale_ = nil
    self.outZoom_ = 1.0
    self.lastScale_ = self.scaleMgr:CurrentScale()
    self.lastZoom_ = self.scaleMgr:CurrentZoom()
    self.missingWorldWarned_ = false

    -- 按尺度名称记过渡，不假设 cell 是第几个尺度，也不订阅区域选择。
    self.scaleToken = EventBus.On(EventBus.Events.SCALE_CHANGED, function(payload)
        self.outScale_ = payload and payload.prevScale or self.lastScale_
        self.outZoom_ = self.lastZoom_
        self.pointer.active = false
    end)
    self.resetToken = EventBus.On(EventBus.Events.SIM_RESET, function()
        self:CancelMap()
        self.exploration:Reset(self.sim.world)
        self.exploration:Observe(self.sim.world)
        -- 重开直接进入细胞玩法，立即释放旧世界表现，不等下一次细胞绘制。
        self.cellView:Destroy()
        self.pointer.active, self.pointer.known = false, false
        self.cameraWorld = nil
        self.renderMotion:Reset()
        self.cameraPlayer_ = nil
        self.outScale_ = nil
        self.endingZoom = 1
        self.endingFraming = nil
        self.entryZoom,self.entryActive = 1,false
        self:SetVisible(true)
        self.lastScale_ = self.scaleMgr:CurrentScale()
        self.lastZoom_ = self.scaleMgr:CurrentZoom()
        self:UpdateCamera(0)
    end)
    self.exploration:Observe(self.sim.world)
    self:UpdateCamera(0)
    print("[GameScene] 感染网络：WASD / 方向键 / 手机摇杆；鸟仅在结局展示")
end

-- ============================================================================
-- 输入：源码核实 UI 只逆变换、不减布局原点；本画布无视觉 transform，
-- event.xy 已是绝对 base px（不能再加 l.x/y）。
-- ============================================================================

---@param dx number
---@param dy number
function GameScene:OnWheel(dx, dy)
    if self.mapView:IsActive() then return end
    -- 滚轮仅缩放细胞场景，不切换到宿主或器官视图。
    if self.sim.started and self.sim:CanUseAction("move") and self.scaleMgr:CurrentScale() == "cell" then self.scaleMgr:OnWheel(dy) end
end

-- 双指缩放（手机）：与滚轮同条件，仅缩放细胞层；每累计约 ×1.1 消费一格。
-- 只在本层缩放范围内调整，不累计跨尺度溢出，避免捏合误切到宿主/器官视图。
local PINCH_NOTCH = math.log(1.1)

---@return boolean
function GameScene:CanPinchZoom()
    return self.sim.started and self.sim:CanUseAction("move") and self.scaleMgr:CurrentScale() == "cell"
        and self.scaleMgr.transition >= 1.0
end

---@param event GestureEvent
function GameScene:OnPinchStart(event)
    if UI.Widget.OnPinchStart then UI.Widget.OnPinchStart(self, event) end
    self.pinchLast_ = (event and event.scale and event.scale > 0) and event.scale or 1
end

---@param event GestureEvent
function GameScene:OnPinchMove(event)
    if UI.Widget.OnPinchMove then UI.Widget.OnPinchMove(self, event) end
    local scale = event and event.scale
    if not scale or scale <= 0 then return end
    local last = self.pinchLast_ or 1
    if not self:CanPinchZoom() then self.pinchLast_ = scale; return end
    local diff = math.log(scale / last)
    local sm = self.scaleMgr
    local zoomMax, zoomStep = sm:ZoomParams()
    local idx = sm.scaleIndex
    while math.abs(diff) >= PINCH_NOTCH do
        local step = diff > 0 and 1 or -1
        diff = diff - step * PINCH_NOTCH
        last = last * math.exp(step * PINCH_NOTCH)
        local cur = sm.zoomTarget[idx]
        local target = math.max(Config.ZoomMin, math.min(cur + zoomStep * step, zoomMax))
        if target ~= cur then
            sm.zoomTarget[idx] = target
            sm.wheelAccum = 0.0
            sm:RetargetZoom(idx, target)
        end
    end
    self.pinchLast_ = last
end

---@param event GestureEvent
function GameScene:OnPinchEnd(event)
    if UI.Widget.OnPinchEnd then UI.Widget.OnPinchEnd(self, event) end
    self.pinchLast_ = nil
end

---@param event PointerEvent
function GameScene:OnPointerMove(event)
    if event.pointerType ~= "mouse" then return end
    local l = self:GetAbsoluteLayout() --[[@as Rect4]]
    self.pointer.x, self.pointer.y = event.x, event.y
    self.pointer.known = true
    self.pointer.active = contains(l, self.pointer.x, self.pointer.y)
        and (not event.target or event.target == self)
end

---@param event PointerEvent
function GameScene:OnPointerLeave(event)
    if event.pointerType == "mouse" then self.pointer.active = false end
end

---@param event PointerEvent
function GameScene:OnPointerCancel(event)
    if event.pointerType == "mouse" then self.pointer.active = false end
end

-- 点击不选组织 / 不传送、不生产实体；手机只由 HUD 摇杆控制。
---@param event PointerEvent
function GameScene:OnPointerDown(event)
    if event.IsPrimaryAction and not event:IsPrimaryAction() then return end
    if not self.sim.skillSelection or not self.sim:CanAct() or self.scaleMgr:CurrentScale()~="cell" then return end
    if self:IsOverHUD(event.x,event.y) then return end
    local l=self:GetAbsoluteLayout() --[[@as Rect4]]
    local x,y=self.cellView:ScreenToWorld(event.x,event.y,l,self.scaleMgr:CurrentZoom())
    require("UI.SkillPanel").Pick(self.sim,x,y)
end

--- 读取实际可见 HUD 几何，包含 pointerEvents=none 的状态面板。
--- 不把 hudRoot / SafeArea / box-none 全屏布局包装器当成遮挡物。
---@param widget Widget
---@param clip Rect4?
function GameScene:CollectHUDRects(widget, clip)
    if not visible(widget) then return end
    local p = widget.props
    local source = widget:GetAbsoluteLayoutForHitTest() --[[@as Rect4]]
    -- HitTest 布局包含滚动偏移；子内容再与父视窗取交集。
    local l = source
    if clip then
        local x, y = math.max(source.x, clip.x), math.max(source.y, clip.y)
        l = {
            x = x, y = y,
            w = math.max(0, math.min(source.x + source.w, clip.x + clip.w) - x),
            h = math.max(0, math.min(source.y + source.h, clip.y + clip.h) - y),
        }
    end
    if l.w <= 0 or l.h <= 0 then return end
    local id = p.id
    if id == "scalePanel" or id == "entityPanel"
        or id == "hudLeftScroll" or id == "hudStatsScroll"
        or id == "strategyBar" or id == "joystickPanel" then
        self.hudPanels[id] = l
    end
    local hasSurface = p.backgroundColor or p.backgroundImage or p.backgroundGradient
        or (p.borderWidth or 0) > 0 or p.text
    local events = p.pointerEvents or "auto"
    local interactive = events == "auto" or events == "box-only"
    if widget ~= self.hudRoot and (hasSurface or interactive) then
        self.hudRects[#self.hudRects + 1] = l
    end
    local childClip = clip
    if p.overflow == "hidden" or widget.GetScroll then childClip = l end
    for _, child in ipairs(widget:GetChildren()) do self:CollectHUDRects(child, childClip) end
end

---@param l Rect4
function GameScene:UpdateViewport(l)
    -- HUD fading must not suddenly change the microscopic shot's composition.
    local frame=self.endingFraming
    if frame and frame.width==l.w and frame.height==l.h then return end
    if not self.hudRoot then
        local root = self.parent
        while root and root.parent do root = root.parent end
        if root then self.hudRoot = root:FindById("hudRoot") end
    end
    -- Camera avoidance needs only seven outer panels, not every HUD label and
    -- button. Read their live geometry each frame (resize/scroll/hide stay instant).
    self.hudPanels={}
    if self.hudRoot then
        if self.panelRoot_~=self.hudRoot then
            self.panelRoot_=self.hudRoot
            self.panelWidgets_={}
            for _,ids in ipairs({TOP_PANELS,BOTTOM_PANELS}) do
                for _,id in ipairs(ids) do self.panelWidgets_[id]=self.hudRoot:FindById(id) end
            end
        end
        for id,panel in pairs(self.panelWidgets_) do
            local rect=panel:GetAbsoluteLayoutForHitTest() --[[@as Rect4]]
            local ancestor=panel
            while ancestor do
                -- Reserve HUD space while its whole root fades in, so the camera never jumps.
                local reserved=ancestor==self.hudRoot and (self.entryActive or self.mapView:IsActive())
                if not visible(ancestor) and not reserved then rect=nil;break end
                local a=ancestor:GetAbsoluteLayoutForHitTest() --[[@as Rect4]]
                if a.w<=0 or a.h<=0 then rect=nil;break end
                if ancestor.props.overflow=="hidden" or ancestor.GetScroll then rect=intersect(rect,a) end
                if ancestor==self.hudRoot then break end
                ancestor=ancestor.parent
            end
            if rect then self.hudPanels[id]=intersect(rect,l) end
        end
    end

    local safe = UI.GetSafeAreaInsets()
    local top = math.max(0.0, (safe.top or 0) - l.y)
    local bottom = safe.bottom or 0.0
    for _, id in ipairs(TOP_PANELS) do
        local panel = self.hudPanels[id]
        if panel and panel.w > 0 and panel.h > 0 then
            top = math.max(top, panel.y + panel.h - l.y + 12)
        end
    end
    for _, id in ipairs(BOTTOM_PANELS) do
        local bar = self.hudPanels[id]
        if bar and bar.w > 0 and bar.h > 0 then
            bottom = math.max(bottom, l.y + l.h - bar.y + 12)
        end
    end
    -- 极小/正在布局的窗口也保持合法镜头；不会据此改世界尺寸或实体坐标。
    top = math.min(top, l.h * 0.40)
    bottom = math.min(bottom, l.h * 0.40)
    local left, right = safe.left or 0, safe.right or 0
    self.viewport.x,self.viewport.y=l.x+left,l.y+top
    self.viewport.w,self.viewport.h=math.max(1,l.w-left-right),math.max(1,l.h-top-bottom)
    self.cellView:SetViewport(self.viewport)
    if frame then frame.width,frame.height=l.w,l.h end
end

---@param x number
---@param y number
---@return boolean
function GameScene:IsOverHUD(x, y)
    -- Full hit geometry is needed only when pointing at a skill target. Collect
    -- it now so menus opened or scrolled since Update are correctly excluded.
    self.hudRects={}
    if self.hudRoot then
        local l=self:GetAbsoluteLayout() --[[@as Rect4]]
        self:CollectHUDRects(self.hudRoot,l)
    end
    for _, rect in ipairs(self.hudRects) do
        if contains(rect, x, y) then return true end
    end
    -- 自绘弹层 / 独立浮层也可阻挡鼠标；不能用 IsPointerOverUI，画布本身也是 UI。
    local hit = UI.FindWidgetAt(x, y)
    return hit ~= nil and hit ~= self
end

---@param l Rect4
---@return number dx
---@return number dy
function GameScene:ReadMovement(l)
    if not self.sim:CanUseAction("move") or self.scaleMgr:CurrentScale() ~= "cell" then return 0, 0 end
    if input and (input.focus == false or input.minimized == true) then
        self.pointer.active = false
        return 0, 0
    end

    -- active=true 的零向量仍优先，不让摇杆中心死区退回键盘输入。
    local touch = self.sim.touchMove
    if touch and touch.active then
        local x, y = touch.x or 0, touch.y or 0
        local length = math.sqrt(x * x + y * y)
        if length > 1 then return x / length, y / length end
        return x, y
    end
    if input then
        local w = input:GetKeyDown(KEY_W) or input:GetKeyDown(KEY_UP)
        local s = input:GetKeyDown(KEY_S) or input:GetKeyDown(KEY_DOWN)
        local a = input:GetKeyDown(KEY_A) or input:GetKeyDown(KEY_LEFT)
        local d = input:GetKeyDown(KEY_D) or input:GetKeyDown(KEY_RIGHT)
        if w or s or a or d then
            local dx = (d and 1.0 or 0.0) - (a and 1.0 or 0.0)
            local dy = (s and 1.0 or 0.0) - (w and 1.0 or 0.0)
            local length = math.sqrt(dx * dx + dy * dy)
            if length > 0 then return dx / length, dy / length end
            return 0, 0
        end
    end

    -- 鼠标仅负责点击与缩放；松开键盘且摇杆无输入时不产生移动方向。
    return 0, 0
end

-- ============================================================================
-- 唯一模拟推进。CellView 不拥有实体，不订阅事件、不再推进世界。
-- ============================================================================

---@param dt number
function GameScene:Update(dt)
    PerformanceStats.Sample("frameInterval",dt*1000)
    local l = self:GetAbsoluteLayout() --[[@as Rect4]]
    self:UpdateViewport(l)
    self.sim:SetPaused("transition", self.scaleMgr:IsTransitioning())
    local dx, dy = self:ReadMovement(l)
    local world = self.sim.world
    if world and world.SetMovement then
        -- SetMovement 仅在非零输入时更新最近朝向，松开按键后分裂仍沿该方向。
        world:SetMovement(dx, dy)
    elseif not self.missingWorldWarned_ then
        self.missingWorldWarned_ = true
        print("[GameScene] world/SetMovement 暂缺；禁用移动，不由表现层补造世界")
    end
    -- 失焦和镜头过渡不补跑病程。
    if input then
        self.sim:SetPaused("focus", input.focus == false or input.minimized == true)
    end
    local start=PerformanceStats.Begin()
    self.sim:Update(dt,self.beforeStep_)
    self.exploration:Observe(self.sim.world)
    if self.sim:CanAct() then
        self.renderMotion.alpha=math.min(1,self.sim.tickAccum/Config.Gameplay.movementStep)
    else
        self.renderMotion:Reset()
    end
    PerformanceStats.Finish("simulationCPU",start)
    self.mapView:Update(dt)
    if not self.mapView:IsActive() then
        if self.mapHUDActive then self:CancelMap() end
        self.scaleMgr:Update(dt)
    end
    self:UpdateCamera(dt)
    self:UpdateMapFrame(l)
    self.cellView:Update(dt*self.sim.timeScale,self.sim.world,self.renderMotion,self.sim:CanAct())
    self.lastScale_ = self.scaleMgr:CurrentScale()
    self.lastZoom_ = self.scaleMgr:CurrentZoom()
end

--- True through both transitions, so inputs stay blocked until the camera returns.
function GameScene:IsMapActive() return self.mapView:IsActive() end

function GameScene:ToggleMap()
    if self.mapView:IsActive() then
        self.mapView.target = 1-self.mapView.target
        return true
    end
    local tutorial=self.sim.tutorial
    if self.entryActive or not self.sim:CanAct() or (tutorial and tutorial.active) then return false end
    local l=self:GetAbsoluteLayout() --[[@as Rect4]]
    if l.w<=0 or l.h<=0 then return false end
    self.sim:SetPaused("map",true)
    self.pointer.active=false
    self.renderMotion:Reset()
    local fit=self.mapView:Fit(l,self.sim.world)
    self.exploration:Observe(self.sim.world)
    self.mapView:Capture(self.sim.world,math.max(.15,3.5/fit),self.exploration)
    self.mapView.target=1
    self.mapHUDActive=true
    self:UpdateMapFrame(l)
    return true
end

function GameScene:CloseMap()
    if self.mapView:IsActive() then self.mapView.target=0 end
end

function GameScene:CancelMap()
    self.mapView:Reset()
    self.cellView.overviewFrame=nil
    self.mapLegend:SetVisible(false)
    if self.mapHUDActive and self.hudRoot then
        self.hudRoot:SetStyle{opacity=1,pointerEvents="box-none"}
    end
    self.mapHUDActive=false
    self.sim:SetPaused("map",false)
end

---@param l Rect4
function GameScene:UpdateMapFrame(l)
    if not self.mapView:IsActive() then return end
    local ppm=self.cellView:CameraTransform(l,self:CurrentZoom())
    local ox,oy=self.cellView:WorldToScreen(0,0,l,self:CurrentZoom())
    local scale,x,y=self.mapView:Transform(l,self.sim.world,ppm,ox,oy)
    self.cellView.overviewFrame={ppm=scale,cx=x+self.camera.x*scale,cy=y+self.camera.y*scale}
    self.cellView.worldView={x=(l.x-x)/scale,y=(l.y-y)/scale,w=l.w/scale,h=l.h/scale}
    local blend=self.mapView:Blend()
    if self.hudRoot then self.hudRoot:SetStyle{opacity=1-blend,pointerEvents="none"} end
    self.mapLegend:SetVisible(true)
    self.mapLegend:SetStyle{opacity=blend}
end

---@return number
function GameScene:CurrentZoom()
    return self.scaleMgr:CurrentZoom() * self.tutorialZoom * self.endingZoom * self.entryZoom
end

---@param zoom number
---@param active boolean
function GameScene:SetEntryPose(zoom,active)
    self.entryZoom,self.entryActive=zoom,active
end

function GameScene:BeginEntryWarmup()
    self.entryWarmFrames = 0
end

function GameScene:IsEntryReady()
    return self.entryWarmFrames >= 3
end

-- Only presentation changes; the authoritative completed simulation is retained.
---@param zoom number
---@param covered boolean
---@param progress number?
function GameScene:SetEndingPose(zoom, covered, progress)
    self.endingZoom = zoom
    if progress==nil then
        self.endingFraming=nil
    else
        if not self.endingFraming then
            local x,y=self.camera.x,self.camera.y
            local targetX,targetY,nearest=x,y,9 -- only a nearby infection, never an off-screen pan
            local view=self.cellView.worldView
            for _,cell in ipairs(self.sim.world and self.sim.world.cells or {}) do
                if (cell.state=="LATENT" or cell.state=="PRODUCTIVE" or cell.state=="EXHAUSTED")
                    and (not view or contains(view,cell.x,cell.y)) then
                    local distance=(cell.x-x)^2+(cell.y-y)^2
                    if distance<nearest then targetX,targetY,nearest=cell.x,cell.y,distance end
                end
            end
            local l=self:GetAbsoluteLayout() --[[@as Rect4]]
            self.endingFraming={x=x,y=y,targetX=targetX,targetY=targetY,width=l.w,height=l.h}
        end
        local frame=self.endingFraming
        local p=math.max(0,math.min(1,progress))
        local eased=p*p*(3-2*p)
        self.camera.x=frame.x+(frame.targetX-frame.x)*eased
        self.camera.y=frame.y+(frame.targetY-frame.y)*eased
    end
    self:SetVisible(not covered)
end

---@param dt number
function GameScene:UpdateCamera(dt)
    if self.endingFraming then return end
    -- Calculate the normal return pose before applying the overview transform.
    self.cellView.overviewFrame=nil
    local world = self.sim.world
    local player = world and world.player
    if not player then return end
    local x, y = self.renderMotion:Position(player)
    local tutorial = self.sim.tutorial
    local focus = tutorial and tutorial:CameraFocus()
    local targetZoom = focus and (tutorial.step == "intro" and 1.5 or 1.15) or 1
    local ease = 1 - math.exp(-5 * math.max(0, dt))
    self.tutorialZoom = self.tutorialZoom + (targetZoom-self.tutorialZoom)*ease
    if focus then
        self.camera.x = self.camera.x + (focus.x-self.camera.x)*ease
        self.camera.y = self.camera.y + (focus.y-self.camera.y)*ease
        self.cameraWorld = world
        self.cameraPlayer_ = nil
    elseif self.cameraWorld ~= world then
        self.camera.x, self.camera.y = x, y
        self.cameraWorld = world
    else
        -- Track realised interpolated motion immediately. Ease only the offset
        -- after changing control, rather than introducing lag on every move.
        if self.cameraPlayer_==player then
            self.camera.x=self.camera.x+x-self.cameraPlayerX_
            self.camera.y=self.camera.y+y-self.cameraPlayerY_
        end
        local follow = 1 - math.exp(-Config.Performance.cameraFollowRate * math.max(0, dt))
        self.camera.x = self.camera.x + (x - self.camera.x) * follow
        self.camera.y = self.camera.y + (y - self.camera.y) * follow
    end
    if not focus then self.cameraPlayer_,self.cameraPlayerX_,self.cameraPlayerY_=player,x,y end
    local l=self:GetAbsoluteLayout() --[[@as Rect4]]
    if l.w>0 and l.h>0 then
        local ppm,cx,cy=self.cellView:CameraTransform(l,self:CurrentZoom())
        local area=self.viewport.w>0 and self.viewport or l
        CameraBounds.Clamp(self.camera,world,area,ppm,cx,cy)
        self.cellView.worldView=CameraBounds.View(self.camera,area,ppm,cx,cy)
    end
end

-- ============================================================================
-- 渲染：只在 Widget.Render 的帧内调用 raw NanoVG；不创建字体 / 上下文。
-- ============================================================================

---@param nvg NVGContextWrapper
function GameScene:Render(nvg)
    local l = self:GetAbsoluteLayout() --[[@as Rect4]]
    if l.w <= 0 or l.h <= 0 then return end
    local ctx = { sim = self.sim, scaleMgr = self.scaleMgr, time = self.sim.time or 0,
        renderMotion = self.renderMotion }
    nvgSave(nvg)
    nvgIntersectScissor(nvg, l.x, l.y, l.w, l.h)
    nvgBeginPath(nvg)
    nvgRect(nvg, l.x, l.y, l.w, l.h)
    nvgFillColor(nvg, VU.RGBA(Config.Palette.bgDeep))
    nvgFill(nvg)

    local current = self.scaleMgr:CurrentScale()
    local fade = self.scaleMgr:FadeAlpha()
    if self.scaleMgr:IsTransitioning() and self.outScale_ and self.outScale_ ~= current then
        nvgSave(nvg)
        nvgGlobalAlpha(nvg, 1 - fade)
        self:DrawScale(nvg, l, self.outScale_, self.outZoom_, ctx)
        nvgRestore(nvg)
    end
    local mapBlend=self.mapView:Blend()
    local mapFade=math.max(0,math.min(1,(mapBlend-.06)/.64))
    if mapFade<1 then
        nvgSave(nvg)
        nvgGlobalAlpha(nvg, fade*(1-mapFade))
        self:DrawScale(nvg, l, current, self:CurrentZoom(), ctx)
        nvgRestore(nvg)
    end
    if mapFade>0 then
        local ppm=self.cellView:CameraTransform(l,self:CurrentZoom())
        local ox,oy=self.cellView:WorldToScreen(0,0,l,self:CurrentZoom())
        nvgSave(nvg);nvgGlobalAlpha(nvg,mapFade)
        self.mapView:Draw(nvg,self.sim.world,l,ppm,ox,oy)
        nvgRestore(nvg)
    end
    if mapBlend>0 then
        local ppm=self.cellView:CameraTransform(l,self:CurrentZoom())
        local ox,oy=self.cellView:WorldToScreen(0,0,l,self:CurrentZoom())
        -- Apply after both render layers at full opacity, including the pullback.
        self.exploration:Draw(nvg,l,ppm,ox,oy)
        if mapFade>0 then
            nvgSave(nvg);nvgGlobalAlpha(nvg,mapFade)
            self.mapView:DrawPlayer(nvg,self.sim.world,ppm,ox,oy)
            nvgRestore(nvg)
        end
    end
    nvgRestore(nvg)
    self.entryWarmFrames = math.min(3,self.entryWarmFrames+1)
end

---@param nvg NVGContextWrapper
---@param l Rect4
---@param scaleId string
---@param zoom number
---@param ctx table
function GameScene:DrawScale(nvg, l, scaleId, zoom, ctx)
    if scaleId == "cell" then
        -- CellView 包含唯一镜头转换，禁止再套第二次中心缩放。
        ctx.zoom = zoom
        self.cellView:DrawWorld(nvg, l.x, l.y, l.w, l.h, ctx)
    end
end

function GameScene:Destroy()
    self:CancelMap()
    EventBus.Off(self.scaleToken)
    EventBus.Off(self.resetToken)
    if self.cellView.Destroy then self.cellView:Destroy() end
    self.renderMotion:Reset()
    self.cameraPlayer_ = nil
    local world = self.sim.world
    if world and world.SetMovement then world:SetMovement(0, 0) end
    UI.Widget.Destroy(self)
end

return GameScene
