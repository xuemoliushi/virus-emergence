-- 声明式教学面板 + 世界坐标指引；使用现有 UI 的字体、DPR 与 NanoVG 帧。
local UI = require("urhox-libs/UI")
local Skin = require("UI.AssetTheme")
local Mobile = require("UI.MobileLayout")

---@class TutorialArt : Widget
---@field sim SimState
---@field scene GameScene
local Art = UI.Widget:Extend("TutorialArt")

---@param props table
function Art:Init(props)
    self.sim, self.scene = props.sim, props.scene
    props.sim, props.scene = nil, nil
    props.pointerEvents = "none"
    UI.Widget.Init(self, props)
end

---@param nvg NVGContextWrapper
function Art:Render(nvg)
    local t = self.sim.tutorial
    if not t or not t.active then return end
    local l = self.scene:GetAbsoluteLayout() --[[@as Rect4]]
    local target = t:Target()
    local area = self.scene.viewport
    nvgSave(nvg)
    nvgIntersectScissor(nvg, l.x, l.y, l.w, l.h)
    if target then
        local x, y = self.scene.cellView:WorldToScreen(target.x, target.y, l, self.scene:CurrentZoom())
        local ppm = self.scene.cellView:CameraTransform(l, self.scene:CurrentZoom())
        local radius = math.min(math.max(22, (target.radius or 0.05)*ppm+12), math.min(area.w,area.h)*0.38)
        local pulse = 0.5+0.5*math.sin(t.visualTime*2.8)
        if t.lesson.pause then
            nvgBeginPath(nvg); nvgRect(nvg,l.x,l.y,l.w,l.h)
            nvgFillPaint(nvg,nvgRadialGradient(nvg,x,y,radius,radius+190,nvgRGBA(9,6,19,0),nvgRGBA(9,6,19,176)))
            nvgFill(nvg)
        end
        if x>=area.x and x<=area.x+area.w and y>=area.y and y<=area.y+area.h then
            nvgBeginPath(nvg);nvgCircle(nvg,x,y,radius+10)
            nvgFillPaint(nvg,nvgRadialGradient(nvg,x,y,radius-3,radius+20,nvgRGBA(255,184,95,0),nvgRGBA(255,184,95,24)))
            nvgFill(nvg)
            nvgBeginPath(nvg);nvgCircle(nvg,x,y,radius+3*pulse)
            nvgStrokeWidth(nvg,1.4);nvgStrokeColor(nvg,nvgRGBA(255,202,135,math.floor(160+70*pulse)));nvgStroke(nvg)
            for i=0,3 do
                local a=math.pi*0.5*i
                local dx,dy=math.cos(a),math.sin(a)
                nvgBeginPath(nvg);nvgMoveTo(nvg,x+dx*(radius+7),y+dy*(radius+7))
                nvgLineTo(nvg,x+dx*(radius+14),y+dy*(radius+14))
                nvgStrokeWidth(nvg,2);nvgStrokeColor(nvg,nvgRGBA(255,204,142,210));nvgStroke(nvg)
            end
        end
        if t.step == "collect" then
            local cue = self.scene.tutorialCue
            if cue then
                local a = cue.angle
                local dx,dy=math.cos(a),math.sin(a)
                local px,py=-dy,dx
                local cx,cy=cue.x-dx*(2+3*pulse),cue.y-dy*(2+3*pulse)
                nvgBeginPath(nvg);nvgCircle(nvg,cx,cy,23)
                nvgFillPaint(nvg,nvgRadialGradient(nvg,cx,cy,1,25,nvgRGBA(255,182,87,58),nvgRGBA(255,182,87,0)))
                nvgFill(nvg)
                nvgBeginPath(nvg)
                nvgMoveTo(nvg,cx+dx*12,cy+dy*12)
                nvgLineTo(nvg,cx-dx*8+px*8,cy-dy*8+py*8)
                nvgLineTo(nvg,cx-dx*8-px*8,cy-dy*8-py*8)
                nvgClosePath(nvg);nvgFillColor(nvg,nvgRGBA(255,197,113,245));nvgFill(nvg)
                nvgStrokeWidth(nvg,1);nvgStrokeColor(nvg,nvgRGBA(255,232,185,245));nvgStroke(nvg)
            end
        end
    end
    -- 控件几何由真实 UI 布局提供，标签文字仍由 Label 绘制。
    local id = ({split="splitBtn",switch="switchBtn",task="stagePanel"})[t.step]
    local root = self.scene.hudRoot
    local widget = id and root and root:FindById(id)
    if widget and widget:IsVisible() then
        local r = widget:GetAbsoluteLayoutForHitTest() --[[@as Rect4]]
        nvgBeginPath(nvg);nvgRoundedRect(nvg,r.x-4,r.y-4,r.w+8,r.h+8,10)
        nvgStrokeWidth(nvg,1.7);nvgStrokeColor(nvg,nvgRGBA(255,194,112,210));nvgStroke(nvg)
    end
    nvgRestore(nvg)
end

---@class TutorialOverlay
---@field sim SimState
---@field scene GameScene
---@field root Widget
---@field blocker Widget
---@field card Widget
---@field chapter Label
---@field title Label
---@field body Label
---@field hint Label
---@field continueButton Button
---@field cue Label
---@field progress Widget[]
---@field lastStep string
---@field skipArea Widget
---@field skipMask Widget
---@field skipHint Label
---@field skipFill Widget
local Overlay = {}
Overlay.__index = Overlay
local WARM={255,198,124,255}
local MUTED=Skin.colors.muted

---@param text string
---@param size number
---@param color table?
---@return Label
local function label(text,size,color)
    return UI.Label {text=text,fontSize=size,fontColor=color or {244,233,222,255},width="100%",flexShrink=1}
end

---@param sim SimState
---@param scene GameScene
---@return TutorialOverlay
function Overlay.New(sim,scene)
    local self=setmetatable({},Overlay)
    self:init(sim,scene)
    return self
end

---@param sim SimState
---@param scene GameScene
function Overlay:init(sim,scene)
    self.sim,self.scene,self.lastStep=sim,scene,""
    self.chapter=label("首次感染 · 01 / 08",10,WARM)
    self.title=label("",20)
    self.body=label("",14)
    self.hint=label("",10,MUTED)
    self.progress={}
    for i=1,8 do self.progress[i]=UI.Panel {height=3,flexGrow=1,flexBasis=0,borderRadius=2,backgroundColor={68,48,70,255},pointerEvents="none"} end
    self.continueButton=Skin.Button {buttonKind="primary",id="tutorialContinue",text="继续",height=56,width="100%",fontSize=12,
        backgroundColor={211,148,72,255},textColor=Skin.colors.text,borderRadius=7,
        hoverBackgroundColor={242,183,102,255},pressedBackgroundColor={174,108,48,255},
        onClick=function() if self.sim.tutorial then self.sim.tutorial:Continue() end end}
    -- 触屏专用：按住此按钮等同长按 Esc（由 main.lua 读取 touchSkipHeld），桌面隐藏。
    self.touchSkipButton=Skin.Button {buttonKind="secondary",id="tutorialSkipTouch",text="长按跳过",height=44,
        width="100%",fontSize=12,visible=false}
    self.touchSkipHeld=false
    self.mobileExpanded_=false
    self.expandButton=Skin.Button{id="tutorialExpand",text="详情",width=64,height=44,fontSize=11,visible=false,
        onClick=function() self.mobileExpanded_=not self.mobileExpanded_ end}
    self.title:SetStyle{width=0,flexGrow=1,flexBasis=0}
    self.titleRow=UI.Panel{width="100%",flexDirection="row",alignItems="center",gap=6,
        children={self.title,self.expandButton}}
    self.progressRow=UI.Panel{width="100%",height=3,gap=5,flexDirection="row",children=self.progress}
    self.card=Skin.Frame {frameKind="tooltip",id="tutorialCard",position="absolute",right=18,bottom=110,width=430,
        padding=18,gap=9,borderRadius=12,borderWidth=1,borderColor={171,119,72,190},
        backgroundColor={19,12,29,245},boxShadow={{x=0,y=8,blur=24,spread=0,color={0,0,0,100}}},
        zIndex=2,pointerEvents="auto",children={self.chapter,self.titleRow,self.body,self.progressRow,
            self.hint,UI.Panel{id="tutorialActions",width="100%",gap=6,children={self.continueButton,self.touchSkipButton}}}}
    self.blocker=UI.Panel {id="tutorialBlocker",position="absolute",left=0,top=0,width="100%",height="100%",
        pointerEvents="auto",onClick=function() if self.sim.tutorial then self.sim.tutorial:Continue() end end}
    self.cue=UI.Label {backgroundImage="image/ui/scaled/ui_tooltip_panel_normal.png",
        backgroundFit="sliced",backgroundSlice={10,10,10,10},id="tutorialCollectionCue",position="absolute",left=0,top=0,width=176,
        text="收集病毒",textAlign="center",fontSize=11,fontColor=WARM,
        padding=9,borderWidth=0,
        pointerEvents="none",visible=false}
    self.skipHint=UI.Label {id="tutorialSkipHint",text="长按 Esc 跳过教程",width="100%",height=20,
        textAlign="right",fontSize=11,fontColor=WARM,pointerEvents="none"}
    self.skipFill=UI.Panel {id="tutorialSkipProgress",width="0%",height="100%",
        backgroundColor=WARM,pointerEvents="none"}
    local skip=Skin.Frame {frameKind="tooltip",id="tutorialSkipHold",width=222,maxWidth="100%",
        height=52,flexShrink=0,padding=10,gap=5,pointerEvents="none",children={self.skipHint,
            UI.Panel {width="100%",height=4,backgroundColor={68,48,70,255},pointerEvents="none",
                children={self.skipFill}}}}
    self.skipMask=UI.Panel {id="tutorialSkipMask",position="absolute",left=0,top=0,
        width="100%",height="100%",zIndex=1,backgroundColor={9,6,19,0},
        backgroundImage="",boxShadow=false,borderWidth=0,pointerEvents="none",visible=false}
    self.skipArea=UI.SafeAreaView {id="tutorialSkipSafeArea",position="absolute",left=0,top=0,
        width="100%",height="100%",nativeMenuInset=true,padding=12,alignItems="flex-end",
        justifyContent="flex-start",zIndex=10,pointerEvents="none",visible=false,
        backgroundColor=false,backgroundImage="",boxShadow=false,borderWidth=0,children={skip}}
    self.root=UI.Panel {id="tutorialOverlay",position="absolute",left=0,top=0,width="100%",height="100%",
        zIndex=700,pointerEvents="box-none",visible=false,
        children={self.blocker,Art {width="100%",height="100%",sim=sim,scene=scene},self.cue,
            self.skipMask,self.card,self.skipArea}}
end

function Overlay:Update()
    local t=self.sim.tutorial
    local active=t and t.active or false
    -- Card choice, abilities and pause menus own the foreground exclusively.
    local reasons=self.sim.pauseReasons or {}
    local covered=self.sim.cards.pending~=nil or self.sim.cardNotice~=nil or self.sim.skillMenu~=nil
        or reasons.mainMenu or reasons.settings or reasons.ending
    if covered then
        self.root:SetVisible(false);self.touchSkipHeld=false;self.scene.tutorialCue=nil
        return
    end
    self.root:SetVisible(active)
    local progress=active and t and t:SkipProgress() or 0
    self.skipArea:SetVisible(progress>0)
    self.skipMask:SetVisible(progress>0)
    local touch=Mobile.IsTouch()
    if self.touchSkipButton:IsVisible()~=(active and touch) then self.touchSkipButton:SetVisible(active and touch) end
    local pressed=self.touchSkipButton.state and self.touchSkipButton.state.pressed
    self.touchSkipHeld=(active and touch and pressed) and true or false
    if not active or not t then self.scene.tutorialCue=nil;return end
    local alpha=math.floor(190*progress)
    if self.skipMask.props.backgroundColor[4]~=alpha then
        self.skipMask:SetStyle {backgroundColor={9,6,19,alpha}}
    end
    local width=string.format("%.1f%%",progress*100)
    if self.skipFill.props.width~=width then self.skipFill:SetStyle {width=width} end
    local skipText=progress>0 and string.format("正在跳过 · %.0f%%",progress*100)
        or (touch and Mobile.Text.tutorialSkip or "长按 Esc 跳过教程")
    if self.skipHint.props.text~=skipText then self.skipHint:SetText(skipText) end
    self.blocker:SetVisible(t.lesson.pause==true)
    self.continueButton:SetVisible(t.lesson.pause==true)
    self.continueButton:SetDisabled(t.stepTime<0.35)
    local override=touch and Mobile.Tutorial[t.step] or nil
    local detail=t:Detail()
    if override then
        if t.step=="split" and detail=="准备就绪 · 按 Space 分裂" then detail=Mobile.Tutorial.splitReady
        elseif override.keys and detail==t.lesson.keys then detail=override.keys end
    end
    self.hint:SetText(detail)
    if self.lastStep~=t.step or self.lastTouch_~=touch then
        self.mobileExpanded_=false
        self.lastStep,self.lastTouch_=t.step,touch
        self.chapter:SetText(string.format("首次感染 · %02d / 08",t.lesson.chapter))
        self.title:SetText(t.lesson.title);self.body:SetText(override and override.text or t.lesson.text)
        self.continueButton:SetText("继续")
        for i,bar in ipairs(self.progress) do bar:SetStyle {backgroundColor=i<=t.lesson.chapter and WARM or {68,48,70,255}} end
    end
    local l=self.scene:GetAbsoluteLayout() --[[@as Rect4]]
    local area=self.scene.viewport
    local compact=l.w<760 or l.h<600
    local width=math.max(180,math.min(touch and 300 or (compact and 338 or 430),l.w-28))
    self.card:SetStyle {width=width,right=14,bottom=math.max(12,l.y+l.h-area.y-area.h+12),
        padding=compact and 12 or 18,gap=compact and 6 or 9,
        opacity=t.step=="task" and math.min(1,math.max(0,(6-t.stepTime)/0.4)) or 1,
        pointerEvents=t.lesson.pause and "auto" or (touch and "box-none" or "none")}
    self.title:SetStyle {fontSize=compact and 15 or 20}
    self.body:SetStyle {fontSize=compact and 12 or 14}
    local actions=self.card:FindById("tutorialActions")
    if actions then actions:SetStyle{flexDirection=touch and "row" or "column",flexShrink=0} end
    self.continueButton:SetStyle{width=touch and 0 or "100%",flexGrow=touch and 1 or 0,
        flexBasis=touch and 0 or "auto",height=touch and 44 or 56}
    self.touchSkipButton:SetStyle{width=touch and 0 or "100%",flexGrow=touch and 1 or 0,flexBasis=touch and 0 or "auto"}
    if touch then
        local safe=UI.GetSafeAreaInsets()
        local collapsed=not t.lesson.pause and not self.mobileExpanded_
        width=math.min(360,l.w-(safe.left or 0)-(safe.right or 0)-32)
        local left=(l.w-width)/2
        if collapsed then
            -- Fit the reminder between the task panel and the upper-right utility buttons.
            local start=(safe.left or 0)+math.min(276,l.w*.32)+24
            local finish=l.w-(safe.right or 0)-172
            width=math.max(160,math.min(340,finish-start))
            left=math.max((safe.left or 0)+8,start+(finish-start-width)/2)
        end
        -- Position setters accept Yoga's undefined value, not the dimension string "auto".
        -- Clear the lower anchor so automatic height ends immediately below the actions.
        local unset=YGUndefined or (0/0)
        self.card:SetStyle{width=width,left=left,right=unset,top=(safe.top or 0)+8,bottom=unset,
            height=collapsed and 60 or "auto",maxHeight=l.h-(safe.top or 0)-(safe.bottom or 0)-24,padding=8,gap=4}
        self.chapter:SetVisible(not collapsed);self.body:SetVisible(not collapsed)
        self.progressRow:SetVisible(not collapsed);self.hint:SetVisible(not collapsed)
        if actions then actions:SetVisible(not collapsed) end
        self.touchSkipButton:SetVisible(not collapsed)
        self.expandButton:SetVisible(not t.lesson.pause)
        self.expandButton:SetText(collapsed and "详情" or "收起")
        self.titleRow:SetStyle{minHeight=44,flexShrink=0}
        self.card:SetStyle{pointerEvents="auto"}
        self.title:SetStyle{fontSize=14};self.body:SetStyle{fontSize=11}
    else
        self.chapter:SetVisible(true);self.body:SetVisible(true);self.progressRow:SetVisible(true)
        self.hint:SetVisible(true);if actions then actions:SetVisible(true) end
        self.expandButton:SetVisible(false);self.titleRow:SetStyle{minHeight=0}
        self.card:SetStyle{height="auto"}
    end
    self.touchSkipHeld=touch and self.touchSkipButton:IsVisible()
        and self.touchSkipButton.state and self.touchSkipButton.state.pressed==true or false
    self.scene.tutorialCue=nil
    ---@type {x: number, y: number}?
    local target=t.step=="collect" and t:Target() or nil
    self.cue:SetVisible(target~=nil)
    if target then
        local x,y=self.scene.cellView:WorldToScreen(target.x,target.y,l,self.scene:CurrentZoom())
        local cx,cy=area.x+area.w*0.5,area.y+area.h*0.5
        local dx,dy=x-cx,y-cy
        if math.abs(dx)+math.abs(dy)<1 then dx,dy=0,-1 end
        local length=math.sqrt(dx*dx+dy*dy)
        dx,dy=dx/length,dy/length
        local halfW,halfH=math.max(1,area.w*0.5-28),math.max(1,area.h*0.5-30)
        local scale=math.min(halfW/math.max(0.0001,math.abs(dx)),halfH/math.max(0.0001,math.abs(dy)))
        local px,py=cx+dx*scale,cy+dy*scale
        self.scene.tutorialCue={x=px,y=py,angle=math.atan(dy,dx)}
        -- Keep the lesson card on the opposite side of the directional cue.
        local cardHeight=self.card:GetLayout().h
        if not cardHeight or cardHeight<=0 then cardHeight=compact and 218 or 260 end
        local cardBottom=py>cy and math.max(12,l.h-(area.y-l.y+12)-math.min(cardHeight,area.h-24))
            or math.max(12,l.y+l.h-area.y-area.h+12)
        if not touch then self.card:SetStyle {right=px>cx and math.max(14,l.w-width-14) or 14,bottom=cardBottom} end
        local left=math.max(l.x+10,math.min(px-88-dx*34,l.x+l.w-186))
        local top=math.max(area.y+4,math.min(py+14-dy*35,area.y+area.h-34))
        self.cue:SetStyle {left=left-l.x,top=top-l.y}
        ---@type SwarmWorld
        local w=self.sim.world
        local distance=math.sqrt((target.x-w.player.x)^2+(target.y-w.player.y)^2)
        self.cue:SetText(string.format("收集病毒 · %.1f m",distance))
    end
end

return Overlay
