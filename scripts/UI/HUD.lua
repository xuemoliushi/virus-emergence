-- ============================================================================
-- HUD.lua - 感染网络：直接开局 / 六阶段任务 / 吸附与多群操作 / 病程阈值 / 结算
-- 基于现有 2D HUD 生命周期；UI.Init / UI.SetRoot 仍由 main 管理。
-- sim / world 是唯一权威状态。HUD 只调用公开操作，除 touchMove 外不写模拟字段。
-- 保留 GameScene 的 HUD 避让 id；所有重要文本换行，长内容在受约束视窗内滚动。
-- 风格已查阅 ui-astroon / ui-brawlforge / ui-pixelforge；继续项目原有生物组织配色，
-- 不注册主题、不换字体、不创建额外 NanoVG 上下文或渲染帧。
-- ============================================================================

local UI = require("urhox-libs/UI")
local Skin = require("UI.AssetTheme")
local Motion = require("UI.Disclosure")
local StageSummary = require("UI.StageSummary")
local Ability = require("Core.AbilityRuntime")
local EndingScreen = require("UI.EndingScreen")
local CardPanel = require("UI.CardPanel") --[[@as CardPanelAPI]]
local Config = require("Core.Config")
local SkillPanel=require("UI.SkillPanel") --[[@as SkillPanelAPI]]
local EventBus = require("Core.EventBus")
local PlatformUtils = require("urhox-libs.Platform.PlatformUtils")
local Mobile = require("UI.MobileLayout")

---@class HUDDependencies
---@field sim SimState
---@field scaleMgr ScaleManager
---@field onRestart fun()?
---@field onMenu fun()?
---@field onCredits fun()?
---@field onMap fun()?
---@field onCardChoiceShown (fun():CardChoicePlayback?)?
---@field videoVolume (fun():number)?
---@field onEndingPose (fun(zoom:number, covered:boolean, progress:number?))?
---@field onEndingMix (fun(progress:number))?

local CLEAR_BORDER = { 0, 0, 0, 0 }
local AI_LABELS = {
    controlled = "手动", hidden = "隐藏", disabled = "等待", idle = "等待", flee = "避敌",
    seek = "移动", infect = "感染", collect = "寻找供给", wander = "探索",
}
local PAD_SIZE, KNOB_SIZE = 120, 45
local PAD_CENTER = PAD_SIZE / 2
local PAD_TRAVEL = (PAD_SIZE - KNOB_SIZE) / 2 - 2

---@param value number?
---@return string
local function countText(value)
    if value == nil then return "—" end
    return string.format("%d", math.max(0, math.floor(value)))
end

---@param value number?
---@return string
local function numberText(value)
    if value == nil then return "—" end
    if value == math.floor(value) then return countText(value) end
    return string.format("%.1f", value)
end

---@param seconds number
---@return string
local function elapsedText(seconds)
    local whole = math.floor(math.max(0, seconds))
    return string.format("%02d:%02d", whole // 60, whole % 60)
end

---@param value number?
---@return number
local function unitProgress(value)
    return math.max(0, math.min(1, value or 0))
end

---@param props LabelProps
---@return Label
local function label(props)
    props.fontSize = props.fontSize or 12
    props.fontColor = props.fontColor or Config.Palette.textDim
    props.width = props.width or "100%"
    props.minWidth, props.maxWidth = 0, "100%"
    props.whiteSpace, props.wordBreak = "normal", "break-word"
    props.lineHeight = props.lineHeight or 1.35
    props.verticalAlign = "top"
    -- 不固定 height / maxLines：重要任务和提示完整换行，不压扁滚动内容。
    props.flexShrink = 0
    props.pointerEvents = "none"
    return UI.Label(props)
end

-- [HUD_BUTTON_STYLE] 基础玩法和结算按钮共用的外观入口；保留点击回调及动态状态更新。
local ACTION_ICONS={absorbBtn="absorb",splitBtn="split",switchBtn="switch_swarm",mapBtn="cluster_dispatch",menuBtn="menu",
    endingMenuBtn="back",restartBtn="restart"}
---@param props ButtonProps
---@return Button
local function button(props)
    props.maxWidth,props.minWidth,props.flexShrink=props.maxWidth or "100%",props.minWidth or 0,1
    local id=props.id or ""
    local kind=id=="restartBtn" and "primary" or id=="endingMenuBtn" and "secondary"
        or id:find("selectSwarm_",1,true) and "swarm" or "action"
    local onClick=props.onClick
    if onClick then props.onClick=function(widget,event)
        if not event or event:IsPrimaryAction() then onClick(widget,event) end
    end end
    return Skin.Button(props,kind,ACTION_ICONS[id])
end

---@class HUDTouchMove
---@field x number
---@field y number
---@field active boolean

---@class HUD
---@field taskExpanded_ boolean?
---@field endingShown_ boolean
---@field destroyed_ boolean
---@field cardInfoShown_ boolean
---@field refreshAccum_ number
---@field layoutWidth_ number
---@field layoutHeight_ number
---@field touchControls_ table?
---@field touchMove_ HUDTouchMove
---@field cardRevealElapsed_ number?
---@field cardRevealPlayback_ CardChoicePlayback?
---@field cardRevealChoice_ string?
---@field cardArtwork_ CardArtworkBatch?
---@field cardRevealStarted_ boolean
---@field cardSelectedId_ string?
---@field cardHoveredId_ string?
---@field cardSelectionChoice_ string?
---@field cardConfirming_ boolean?
---@field cardBriefText_ boolean?
---@field cardDescriptionViews_ table<string, CardDescriptionView>?
local HUD = {}
HUD.__index = HUD

---@param deps HUDDependencies
---@return HUD
function HUD.New(deps)
    local self = setmetatable({}, HUD)
    self:init(deps)
    return self
end

---@param deps HUDDependencies
function HUD:init(deps)
    self.sim, self.scaleMgr, self.onRestart = deps.sim, deps.scaleMgr, deps.onRestart
    self.onMenu = deps.onMenu
    self.onCredits = deps.onCredits
    self.onMap = deps.onMap
    self.videoVolume = deps.videoVolume
    self.onEndingPose = deps.onEndingPose
    self.onEndingMix = deps.onEndingMix
    ---@type table<string, DisclosureMotion>
    self.motions_ = {}
    self.noticeText_, self.noticeElapsed_ = "", 0
    self.tickerElapsed_=0
    self.onCardChoiceShown = deps.onCardChoiceShown
    self.cardRevealElapsed_, self.cardRevealPlayback_, self.cardRevealChoice_ = nil, nil, nil
    self.cardArtwork_=nil
    self.cardRevealStarted_=false
    self.touchSeen_ = false
    -- 摇杆尺寸默认沿用桌面常量；触屏布局在 ApplyLayout 中按屏幕高度放大。
    self.padSize_, self.knobSize_ = PAD_SIZE, KNOB_SIZE
    ---@type boolean?
    self.layoutTouch_ = nil
    ---@type number?
    self.touchListener_ = nil
    ---@type Widget?
    self.root = nil
    ---@type Panel?
    self.joystick_ = nil
    ---@type Panel?
    self.joystickKnob_ = nil
    ---@type number?
    self.joystickPointer_ = nil
    ---@type string?
    self.lastScale_ = nil
    ---@type boolean?
    self.lastStarted_ = nil
    ---@type table<string, SkinnedButton>
    self.strategyButtons_ = {}
    ---@type Button[]
    self.groupButtons_ = {}
    ---@type Panel?
    self.swarmSelector_ = nil
    self.actionNotice_, self.actionNoticeUntil_ = "", 0
    self.lastControlledSwarmId_ = self.sim.world.currentControlledSwarmId
    ---@type table<string, string>
    self.textCache_ = {}
    self.endingShown_, self.destroyed_, self.cardInfoShown_ = false, false, false
    self.refreshAccum_, self.layoutWidth_, self.layoutHeight_ = 0, 0, 0
    self.touchMove_ = self.sim.touchMove
    self:ClearTouchMove()

    -- New 只订阅一次；Build / ResetEnding 不重复注册，也不重启模拟。
    self.tokens_ = {
        EventBus.On(EventBus.Events.SIM_ENDING, function()
            self:CloseCardInfo()
            self:RefreshStrategyHighlight()
            self:ShowEnding()
        end),
        EventBus.On(EventBus.Events.SCALE_CHANGED, function()
            self:RefreshScale() -- 同步清理暂停时的输入。
            self:RefreshStrategyHighlight()
        end),
        EventBus.On(EventBus.Events.SIM_RESET, function()
            self:ResetEnding()
        end),
        EventBus.On("cards:acquired", function()
            self:OpenCardInfo()
            CardPanel.Refresh(self)
        end),
        EventBus.On("cards:choice", function()
            self:OpenCardInfo()
            CardPanel.Refresh(self)
        end),
        EventBus.On("controls:edit", function()
            if self.touchControls_ then self.touchControls_:Edit() end
        end),
    }
    -- PlatformUtils 不把桌面 Web 当移动端；首次真实触摸后保留触摸入口。
    self.touchListener_ = UI.Input.On("PointerDown", function(event)
        if event:IsTouch() and not self.destroyed_ then
            self.touchSeen_ = true
            Mobile.MarkTouch()
            self:RefreshJoystickVisibility()
        end
    end)
end

---@return Widget
function HUD:Build()
    if self.root then return self.root end
    local P = Config.Palette
    self.root = UI.Panel {
        id = "hudRoot", position = "absolute", left = 0, top = 0,
        width = "100%", height = "100%", pointerEvents = "box-none", flexShrink = 1,
        children = {
            UI.SafeAreaView {
                id = "hudSafeArea", position = "absolute", left = 0, top = 0,
                width = "100%", height = "100%", nativeMenuInset = true,
                pointerEvents = "box-none", flexShrink = 1,
                paddingLeft = 8, paddingRight = 8, paddingTop = 8, paddingBottom = 8,
                children = {
                    UI.Panel {
                        id = "hudContent", width = "100%", height = "100%",
                        minHeight = 0, gap = 6, flexShrink = 1, pointerEvents = "box-none",
                        children = {
                            UI.Panel {
                                id="mobileUtilities",position="absolute",right=0,top=0,
                                width=148,height=44,flexDirection="row",gap=8,
                                pointerEvents="box-none",visible=false,
                            },
                            UI.Panel {
                                id = "hudTopRow", width = "100%", height = 210,
                                flexDirection = "row", justifyContent = "space-between",
                                gap = 8, flexShrink = 1, minHeight = 0, pointerEvents = "box-none",
                                children = {
                                    Skin.Scroll {
                                        id = "hudLeftScroll", width = "48%", maxWidth = 384,
                                        height = "100%", flexBasis = "48%", flexShrink = 1,
                                        minWidth = 0, minHeight = 0, scrollY = true, scrollX = false,
                                        bounces = false, showScrollbar = true, backgroundColor = false,
                                        children = {
                                            UI.Panel {
                                                id = "taskPanelHost", width = "100%", gap = 5, flexShrink = 0,
                                                pointerEvents = "box-none", children = {
                                                    self:BuildTaskPanel(P),

                                                },
                                            },
                                        },
                                    },

                                },
                            },
                            UI.Panel {
                                -- 独立锚定安全区左下角，内容增减不再依赖上方弹性留白。
                                id = "hudBottomRow", position = "absolute", left = 0, bottom = 0,
                                width = "100%", height = "auto",
                                flexDirection = "row", justifyContent = "flex-start",
                                alignItems = "flex-end", gap = 8, flexShrink = 0,
                                pointerEvents = "box-none", children = {
                                    self:BuildJoystick(P), self:BuildStrategyBar(P),
                                },
                            },
                        },
                    },
                },
            },
            UI.Panel{id="stageSummary",position="absolute",right=8,top=8,width=336,maxWidth="46%",
                pointerEvents="box-none",children={Skin.Scroll{id="hudStatsScroll",width="100%",height=152,
                minHeight=0,children={self:BuildEntityPanel(P)}},
                Skin.Button{id="statsToggle",text="详细统计 ▾",width="100%",height=28,fontSize=11,flexShrink=0,
                    onClick=function() self:ToggleDrawer("stats") end}}},
            Skin.Button{id="statsEdgeTab",text="‹",position="absolute",right=0,top=30,width=28,height=54,
                visible=false,fontSize=20,onClick=function() self.stageSummary:Reveal() end},
            self:BuildStatsDrawer(P),
            Skin.Frame{id="taskDrawer",position="absolute",visible=false,zIndex=6,
                width=400,height=300,minHeight=0,padding=12,gap=8,children={
                    label{text="当前任务",fontSize=18},
                    Skin.Scroll{width="100%",height=0,flexGrow=1,flexBasis=0,minHeight=0,children={
                        UI.Panel{width="100%",gap=12,children={
                            label{id="taskDetailText",text="",fontSize=15},
                            label{id="taskDetailHint",text="",fontSize=14},
                            label{id="taskDetailReward",text="",fontSize=14},
                        }}}},
                    Skin.Button{text="关闭任务详情",height=48,flexShrink=0,
                        onClick=function() self:CloseDrawers() end},
                }},
            SkillPanel.BuildMenu(self),
            SkillPanel.BuildTarget(self),
            self:BuildEndingOverlay(P),
            self:BuildCardInfoOverlay(P),
        },
    }
    self.stageSummary=StageSummary.New(self.root:FindById("stageSummary"),self.root:FindById("statsEdgeTab"))
    self.root:FindById("statsEdgeTab"):SetStyle{paddingLeft=0,paddingRight=0}
    self.motions_.task=Motion.New(self.root:FindById("taskDrawer"))
    self.motions_.stats=Motion.New(self.root:FindById("entityDetails"),300)
    self.motions_.groups=Motion.New(self.root:FindById("groupDrawer"),156)
    self.motions_.skills=Motion.New(self.root:FindById("skillMenuPopup"))
    self.motions_.target=Motion.New(self.root:FindById("skillTargetPrompt"))
    self:RefreshScale()
    self:RefreshStrategyHighlight()
    self:Update(0.12)
    print("[HUD] 病毒操控 / 六阶段 / 鸟结局；搜索 HUD_BUTTON 定位按钮换皮入口")
    return self.root
end

function HUD:BuildTaskPanel(P)
    return Skin.Frame {
        id = "stagePanel", width = "100%", padding = 12, gap = 5, flexShrink = 0,
        backgroundColor = P.panelBg, borderRadius = 10, borderWidth = 1,
        borderColor = P.panelBorder, pointerEvents = "box-none",
        children = {
            UI.Panel{width="100%",flexDirection="row",alignItems="center",gap=4,pointerEvents="box-none",children={
                label { id = "stageName", text = "阶段 — / 6", fontSize = 12, fontColor = P.virus,flexGrow=1,flexBasis=0 },
                Skin.Button{id="taskToggle",text="详情",width=44,height=44,fontSize=10,visible=false,
                    onClick=function()
                        self:ToggleDrawer("task")
                    end},
            }},
            label { id = "taskText", text = "主要任务：开始游戏" , fontColor = P.textMain },
            label { id = "taskProgress", text = "进度：— / —" },
            Skin.Progress {
                id = "taskProgressBar", width = "100%", height = 14,
                value = 0, max = 1, showLabel = false, fillColor = P.virus,
                borderWidth = 0, borderRadius = 4, flexShrink = 0, pointerEvents = "none",
            },
            label { id = "taskHint", text = "", width = "100%", fontSize = 11 },
            label { id = "taskReward", text = "", width = "100%", fontSize = 10 },
        },
    }
end

function HUD:BuildScaleIndicator(P)
    return Skin.Frame {
        id = "scalePanel", width = "100%", padding = 14, gap = 5, flexShrink = 0,
        backgroundColor = P.panelBg, borderRadius = 10, borderWidth = 1,
        borderColor = P.panelBorder, pointerEvents = "none",
        children = {
            label { id = "timeLabel", text = "已进行 00:00", fontColor = P.textMain },
            label { id = "mapSeedInfo", text = "", fontSize = 11 },
            label { id = "scaleHint", text = "WASD / 方向键 / 摇杆移动 · M 全图", fontSize = 11 },
        },
    }
end

function HUD:ToggleDrawer(name)
    local motion=self.motions_[name]
    if not motion then return end
    motion:Toggle()
    if name=="stats" and motion.target==1 then self.stageSummary:Reveal() end
    -- One supplementary drawer at a time keeps the world readable.
    if motion.target==1 then
        if Mobile.IsTouch(self) then require("UI.SkillControls").Cancel(self.sim) end
        for _,other in ipairs({"task","stats","groups"}) do
            if other~=name and self.motions_[other] then self.motions_[other]:SetOpen(false) end
        end
    end
    self:SetText("statsToggle",self.motions_.stats.target==1 and "收起统计 ▴" or "详细统计 ▾")
    self:SetText("groupsToggle",Mobile.IsTouch(self) and "群组" or (self.motions_.groups.target==1 and "收起群列表" or "群列表"))
end

function HUD:CloseDrawers()
    local closed=false
    for _,name in ipairs({"task","stats","groups"}) do
        local motion=self.motions_[name]
        if motion and motion.target==1 then motion:SetOpen(false);closed=true end
    end
    if closed then
        self:SetText("statsToggle","详细统计 ▾")
        self:SetText("groupsToggle",Mobile.IsTouch(self) and "群组" or "群列表")
    end
    return closed
end

function HUD:BuildStatsDrawer(P)
    return Skin.Frame {id="entityDetails",position="absolute",right=8,top=184,width="46%",maxWidth=336,zIndex=5,
        height=0,minHeight=0,visible=false,overflow="hidden",padding=12,
        children={Skin.Scroll{width="100%",height=0,flexGrow=1,flexBasis=0,minHeight=0,children={
            UI.Panel{width="100%",gap=7,children={
            label { id = "splitCount", text = "群体规模 —", fontSize = 11 },

            label { id = "releasedCount", text = "释放病毒 —（活病毒内）", fontSize = 11 },
            label { id = "infectedCount", text = "感染节点 —", fontColor = P.infectWarm },
            label { id = "nodeStates", text = "潜伏 — / 释放 — / 耗竭 —", fontSize = 11 },
            label { id = "healthyCount", text = "健康 — · 接触中 —", fontColor = P.cellMembrane },
            label { id = "deadImmuneCount", text = "死亡细胞 — · 免疫细胞 —", fontColor = P.immuneCool, fontSize = 11 },
            UI.Divider { color = P.panelBorder, spacing = 3 },
            label { id = "totalInfectedCount", text = "累计感染 —" },
            label { id = "totalReleasedCount", text = "累计释放 — · 吸收 —", fontSize = 11 },
            label { id = "totalKilledCount", text = "被清除 — · 离区 / 失活 —", fontColor = P.immuneCool, fontSize = 11 },
            label { id = "independentCount", text = "独立感染 —", fontSize = 11 },

                label{id="mapSeedInfo",text="",fontSize=10},
                label{id="timeLabel",text="",fontSize=11},
                label{id="immuneAlertHud",text="免疫警戒 0",fontSize=11},
                SkillPanel.Build(self),
            }}
        }},Skin.Button{id="statsClose",text="收起统计",width="100%",height=44,flexShrink=0,
            onClick=function() self:ToggleDrawer("stats") end}}}
end

function HUD:BuildEntityPanel(P)
    return Skin.Frame {id="entityPanel",width="100%",padding=10,gap=3,flexShrink=0,
        pointerEvents="box-none",children={
            label{id="inflammationLabel",text="炎症 —",fontColor=P.infectWarm},
            Skin.Progress{id="inflammationBar",width="100%",height=12,value=0,max=1,showLabel=false,fillColor=P.infectWarm},
            label{id="damageLabel",text="损伤 —",fontColor=P.virusHot},
            Skin.Progress{id="damageBar",width="100%",height=12,value=0,max=1,showLabel=false,fillColor=P.virusHot},
            label{id="virusCount",text="活病毒 —",fontColor=P.virus},

            label{id="victoryStatus",text="",visible=false},
        }}
end

function HUD:BuildStrategyBar(P)
    -- [HUD_BUTTON:absorbBtn] 基础吸附；含共享冷却文字
    self.strategyButtons_.absorb = button {
        id = "absorbBtn", height=60, assetIconSize=36, text = "吸附 E", width = 180, flexGrow = 1, flexBasis = 180,
        textColor = P.virus, onClick = function() self:AbsorbNearby() end,
    }
    -- [HUD_BUTTON:splitBtn] 病毒群分离
    self.strategyButtons_.split = button {
        id = "splitBtn", height=60, assetIconSize=36, text = "分离 空格", width = 180, flexGrow = 1, flexBasis = 180,
        textColor = P.virus, onClick = function() self:Split() end,
    }
    -- [HUD_BUTTON:switchBtn] 循环切群
    self.strategyButtons_.switch = button {
        id = "switchBtn", height=60, assetIconSize=36, text = "切群 Tab", width = 180, flexGrow = 1, flexBasis = 180,
        onClick = function() self:SwitchControl() end,
    }
    self.strategyButtons_.map = button {
        id="mapBtn",height=60,assetIconSize=36,text="地图 M",width=180,flexGrow=1,flexBasis=180,
        onClick=function() self:OpenMap() end,
    }
    -- [HUD_BUTTON:menuBtn] 在游戏画面上暂停并打开设定。
    self.strategyButtons_.menu = button {
        id = "menuBtn", height=60, assetIconSize=36, text = "菜单 Esc", width = 180, flexGrow = 1, flexBasis = 180,
        onClick = function()
            self:ClearTouchMove()
            if self.onMenu then self.onMenu() end
        end,
    }
    -- 按实时群数动态增槽，不预设数量上限；旧槽仅隐藏，避免持续创建/销毁控件。
    self.swarmSelector_ = UI.Panel {
        id = "swarmSelector", width = "100%", flexDirection = "row",
        flexWrap = "wrap", gap = 6, flexShrink = 0, pointerEvents = "box-none",
    }
    return UI.Panel {
        id="strategyBar",width=0,flexGrow=1,flexBasis=0,minWidth=0,maxWidth=980,
        gap=6,pointerEvents="box-none",alignSelf="flex-end",children={
            Skin.Frame{id="groupDrawer",position="absolute",bottom="100%",left=0,marginBottom=6,
                visible=false,width="100%",height=0,minHeight=0,
                overflow="hidden",padding=12,children={Skin.Scroll{
                    id="strategyScroll",width="100%",height=0,flexGrow=1,flexBasis=0,minHeight=0,children={
                        UI.Panel{width="100%",gap=7,children={
                            label{id="swarmListTitle",text="存活群体 —",fontSize=11},
                            self.swarmSelector_,
                            label{id="autonomyStatus",text="",fontSize=11},
                        }}
                    }},Skin.Button{id="groupsClose",text="关闭群组列表",height=48,flexShrink=0,
                        onClick=function() self:CloseDrawers() end}}},
            UI.Panel{id="actionDock",width="100%",padding=0,gap=6,pointerEvents="box-none",children={
                UI.Panel{id="statusTicker",width="100%",height=36,minHeight=36,maxHeight=36,
                    flexShrink=0,overflow="hidden",pointerEvents="none",children={
                        UI.Label{id="actionNotice",text="",position="absolute",left=0,top=0,
                            width="100%",height=36,fontSize=11,fontColor=P.infectWarm,
                            whiteSpace="normal",wordBreak="break-word",maxLines=2,pointerEvents="none"},
                        UI.Label{id="actionNoticeNext",text="",position="absolute",left=0,top=36,
                            width="100%",height=36,fontSize=11,fontColor=P.infectWarm,
                            whiteSpace="normal",wordBreak="break-word",maxLines=2,pointerEvents="none"},
                    }},
                UI.Panel{id="dockActions",width="100%",flexDirection="row",flexWrap="wrap",gap=6,
                    pointerEvents="box-none",children={
                        UI.Panel{id="baseActionRow",width="auto",flexGrow=1,flexBasis=490,
                            flexDirection="row",flexWrap="wrap",gap=6,pointerEvents="box-none",children={
                                self.strategyButtons_.absorb,self.strategyButtons_.split,self.strategyButtons_.switch,
                                self.strategyButtons_.map,self.strategyButtons_.menu,
                                Skin.Button{id="groupsToggle",text="群列表",width=76,height=48,fontSize=11,
                                    onClick=function() self:ToggleDrawer("groups") end}}},
                        SkillPanel.BuildQuick(self),
                    }},
                label{id="absorptionStatus",text="",visible=false},
                label{id="swarmStatusDetail",text="",visible=false},
                button{id="cardInfoBtn",text="开发调试",visible=Config.Debug.cardTools==true,
                    onClick=function() self:OpenCardInfo() end},
            }},
        }}
end

-- 复用原摇杆：pressedWidgets_[pointerId] 自动捕获移出后的 move / up / cancel。
-- 不发明 SetPointerCapture，不直接写 world 的移动或鼠标目标。
-- [HUD_CONTROL:joystickPanel] 拖动控件，可换底盘/摇杆美术，不能替换为点击按钮。
function HUD:BuildJoystick(P)
    self.joystickKnob_ = UI.Panel {
        position = "absolute", left = PAD_CENTER - KNOB_SIZE / 2,
        top = PAD_CENTER - KNOB_SIZE / 2, width = KNOB_SIZE, height = KNOB_SIZE,
        backgroundImage="image/ui/frames/ui_joystick_knob_normal.png",backgroundFit="contain",
        pointerEvents = "none", flexShrink = 1,
    }
    self.joystick_ = UI.Panel {
        id = "moveJoystick", width = PAD_SIZE, height = PAD_SIZE,
        minWidth = PAD_SIZE, minHeight = PAD_SIZE, flexShrink = 1,
        shape = "circle", backgroundImage="image/ui/frames/ui_joystick_base_normal.png",backgroundFit="contain", pointerEvents = "box-only",
        children = {
            self.joystickKnob_,
        },
        onPointerDown = function(event, widget) self:JoystickDown(event, widget) end,
        onPointerMove = function(event, widget) self:JoystickMove(event, widget) end,
        onPointerUp = function(event)
            if event.pointerId == self.joystickPointer_ and event:IsPrimaryAction() then
                self:ClearTouchMove()
                event:StopPropagation()
            end
        end,
        onPointerCancel = function(event)
            if event.pointerId == self.joystickPointer_ then
                self:ClearTouchMove()
                event:StopPropagation()
            end
        end,
        onClick = function() end, onTap = function() end,
    }
    return UI.Panel {
        id = "joystickPanel", width = 128, minWidth = 128, gap = 4,
        alignItems = "center", flexShrink = 0, pointerEvents = "box-none",
        children = { self.joystick_, label { id = "joystickHint", text = "拖动移动", textAlign = "center" } },
    }
end

-- 触屏布局放大摇杆；只改尺寸，不改拖动捕获 / 死区 / 取消逻辑。
---@param pad number
---@param knob number
---@param panelWidth number
---@param showHint boolean
function HUD:ResizeJoystick(pad, knob, panelWidth, showHint)
    local root = self.root
    if not root or not self.joystick_ or not self.joystickKnob_ then return end
    local changed = pad ~= self.padSize_ or knob ~= self.knobSize_
    self.padSize_, self.knobSize_ = pad, knob
    if changed then
        self.joystick_:SetStyle {width=pad,height=pad,minWidth=pad,minHeight=pad}
        self.joystickKnob_:SetStyle {width=knob,height=knob,left=pad/2-knob/2,top=pad/2-knob/2}
    end
    local panel = root:FindById("joystickPanel")
    if panel and panel.props.width ~= panelWidth then panel:SetStyle {width=panelWidth,minWidth=panelWidth} end
    local hint = root:FindById("joystickHint")
    if hint and hint:IsVisible() ~= showHint then hint:SetVisible(showHint) end
end

---@param event PointerEvent
---@param widget Widget
function HUD:JoystickDown(event, widget)
    if self.sim.world.currentControlledSwarmId ~= self.lastControlledSwarmId_ then
        self:ClearTouchMove()
        self.lastControlledSwarmId_ = self.sim.world.currentControlledSwarmId
    end
    if self.joystickPointer_ ~= nil or not event:IsPrimaryAction() then return end
    if self.scaleMgr:CurrentScale() ~= "cell" or not self.sim:CanAct() then return end
    self.joystickPointer_ = event.pointerId
    self.touchMove_ = self.sim.touchMove
    event:PreventDefault()
    event:StopPropagation()
    self:SetJoystickPosition(event, widget)
end

---@param event PointerEvent
---@param widget Widget
function HUD:JoystickMove(event, widget)
    if self.sim.world.currentControlledSwarmId ~= self.lastControlledSwarmId_ then
        self:ClearTouchMove()
        self.lastControlledSwarmId_ = self.sim.world.currentControlledSwarmId
        return
    end
    if event.pointerId ~= self.joystickPointer_ then return end
    if self.scaleMgr:CurrentScale() ~= "cell" or not self.sim:CanAct()
        or (event:IsMouse() and (event.buttons & UI.PointerEvent.Buttons.Primary) == 0) then
        self:ClearTouchMove()
        return
    end
    event:PreventDefault()
    event:StopPropagation()
    self:SetJoystickPosition(event, widget)
end

---@param event PointerEvent
---@param widget Widget
function HUD:SetJoystickPosition(event, widget)
    -- event.xy 是绝对基准像素；减绝对布局原点，不受 DPR / 转屏影响。
    local rect = widget:GetAbsoluteLayout()
    local pad, knob = self.padSize_ or PAD_SIZE, self.knobSize_ or KNOB_SIZE
    local travel = pad == PAD_SIZE and knob == KNOB_SIZE and PAD_TRAVEL or (pad - knob) / 2 - 2
    local center = pad / 2
    local dx = (event.x - rect.x - rect.w / 2) / travel
    local dy = (event.y - rect.y - rect.h / 2) / travel
    local distance = math.sqrt(dx * dx + dy * dy)
    local divisor = math.max(1, distance)
    local x, y = dx / divisor, dy / divisor
    local moving = distance > 0.12
    self.touchMove_.x, self.touchMove_.y = moving and x or 0, moving and y or 0
    self.touchMove_.active = true -- 中心死区输出零方向，仍保持摇杆输入优先级。
    if self.joystickKnob_ then
        self.joystickKnob_:SetStyle {
            left = center - knob / 2 + x * travel,
            top = center - knob / 2 + y * travel,
        }
    end
end

function HUD:ClearTouchMove()
    if self.touchControls_ and self.joystick_ then self.joystick_:SetVisible(false) end
    local hadInput = self.joystickPointer_ ~= nil or self.touchMove_.active
        or self.touchMove_.x ~= 0 or self.touchMove_.y ~= 0
    self.joystickPointer_ = nil
    self.touchMove_.x, self.touchMove_.y, self.touchMove_.active = 0, 0, false
    -- 模拟重置可能换表；旧引用和新输入一并清零，随后由 Update 重新绑定。
    local move = self.sim.touchMove
    if move then move.x, move.y, move.active = 0, 0, false end
    if hadInput and self.joystickKnob_ then
        local pad, knob = self.padSize_ or PAD_SIZE, self.knobSize_ or KNOB_SIZE
        self.joystickKnob_:SetStyle {
            left = pad / 2 - knob / 2, top = pad / 2 - knob / 2,
        }
    end
end

---@return Widget
function HUD:BuildCardInfoOverlay(P)
    return CardPanel.Build(self)
end

function HUD:OpenCardInfo()
    if not self.root or self.sim.ending then return end
    local wasShown = self.cardInfoShown_
    self:ClearTouchMove()
    self.cardTestError_ = nil
    self.cardInfoShown_ = true
    CardPanel.Refresh(self)
    self.sim:SetPaused("card-info", true)
    local overlay = self.root:FindById("cardInfoOverlay")
    if overlay then
        overlay:Show()
        local pending = self.sim.cards.pending
        if not wasShown and pending and pending.mode == "formal" then
            CardPanel.BeginReveal(self)
        end
    end
    self:RefreshStrategyHighlight()
end

function HUD:CloseCardInfo()
    if not self.cardInfoShown_ then return end
    if self.sim.cards.pending and self.sim.cards.pending.mode=="formal" then return end
    self:ClearTouchMove()
    self.cardInfoShown_ = false
    CardPanel.ResetReveal(self)
    CardPanel.ResetSelection(self)
    self.sim:ContinueAfterCard()
    self.sim:SetPaused("card-info", false) -- 不清除其他暂停原因。
    local overlay = self.root and self.root:FindById("cardInfoOverlay")
    if overlay then overlay:Hide() end
    self:RefreshStrategyHighlight()
end

function HUD:BuildEndingOverlay(P)
    self.endingScreen=EndingScreen.New(self)
    return self.endingScreen.root
end

---@return SwarmCounts?
function HUD:ReadCounts()
    local world = self.sim.world
    return world and world:GetCountsSnapshot() or nil
end

---@param id string
---@return number?
function HUD:ReadStat(id)
    local world = self.sim.world
    return world and world.stats[id] or nil
end

---@param id string
---@param text string
function HUD:SetText(id, text)
    if not self.root or self.textCache_[id] == text then return end
    local widget = self.root:FindById(id) --[[@as Label?]]
    if widget then
        widget:SetText(text)
        self.textCache_[id] = text
    end
end

---@param id string
---@param value number
function HUD:SetProgress(id, value)
    local bar = self.root and self.root:FindById(id) --[[@as ProgressBar?]]
    local bounded = unitProgress(value)
    if bar and bar:GetValue() ~= bounded then bar:SetValue(bounded) end
end

---@param dt number
function HUD:Update(dt)
    if self.destroyed_ or not self.root then return end
    for _,motion in pairs(self.motions_) do motion:Update(dt) end
    if self.endingScreen then self.endingScreen:Update(dt) end
    local canRead=self.sim.started and not self.sim.paused and not self.sim.ending and not self.cardInfoShown_
    local summaryStage=self.sim.formalFinished and 7 or (self.sim.task and self.sim.task.stage or 0)
    self.stageSummary:Update(dt,summaryStage,canRead,self.motions_.stats.target==1)
    self:UpdateTicker(dt)
    -- 自然清群/合并也会改控制对象：旧指针捕获必须释放，不能由旧拖拽带动新群。
    local controlledId = self.sim.world.currentControlledSwarmId
    if controlledId ~= self.lastControlledSwarmId_ then
        self:ClearTouchMove()
        self.lastControlledSwarmId_ = controlledId
    end
    -- 输入与暂停生命周期不走 8Hz 文本节流：切层 / 暂停 / 重开立即清除。
    if self.sim.touchMove ~= self.touchMove_ then
        self:ClearTouchMove()
        self.touchMove_ = self.sim.touchMove
    end
    self:RefreshScale()
    self:RefreshJoystickVisibility()
    if not self.sim:CanAct() or (self.joystickPointer_ ~= nil and not UI.Input.GetPointer(self.joystickPointer_)) then
        self:ClearTouchMove()
    end
    self:RefreshStrategyHighlight(true)
    SkillPanel.Refresh(self,true)
    self:ApplyLayout()
    if self.touchControls_ then self.touchControls_:Update(dt) end
    if self.sim.ending == "victory" or self.sim.ending == "extinct" then self:ShowEnding() end
    self.refreshAccum_ = self.refreshAccum_ + math.max(0, dt)
    if self.refreshAccum_ < Config.Performance.hudRefreshSeconds then return end
    self.refreshAccum_ = 0
    self:RefreshStrategyHighlight()
    SkillPanel.Refresh(self)

    local sim, counts = self.sim, self:ReadCounts()
    self:SetText("timeLabel", "已进行 " .. elapsedText(sim.time) .. (sim.paused and " · 已暂停" or ""))
    local task = sim.task
    local world=sim.world
    if world then
        self:SetText("mapSeedInfo",string.format("种子 %d · v%d · %.0f×%.0fm · %d细胞",
            world.map.seed,world.map.generationVersion,world.width,world.height,#world.cells))
    end
    if sim.started and task then
        local stageName=sim.formalFinished and not sim.ending and "终局："..task.name
            or "阶段 " .. countText(task.stage) .. " / 6：" .. task.name
        self:SetText("stageName",stageName)
        self:SetText("taskText",task.text)
        self:SetText("taskProgress", task.detail or ("进度：" .. numberText(task.progress) .. " / " .. numberText(task.target)))
        local hint=Mobile.IsTouch(self) and task.hint:gsub("按E","点吸附") or task.hint
        self:SetText("taskHint", "提示：" .. hint)
        self:SetText("taskReward",task.reward or "")
        local infections=world.stats.totalInfected
        if self.taskFeedbackWorld_==world and self.taskFeedbackInfections_ and infections>self.taskFeedbackInfections_
            and sim:CanAct() then
            self:Notify(string.format("新感染细胞 +%d",infections-self.taskFeedbackInfections_))
        end
        self.taskFeedbackWorld_,self.taskFeedbackInfections_=world,infections
        self:SetProgress("taskProgressBar", task.target > 0 and task.progress / task.target or task.complete and 1 or 0)
    else
        self:SetText("stageName", "阶段 — / 6")
        self:SetText("taskText", "主要任务：开始游戏")
        self:SetText("taskProgress", "进度：— / —")
        self:SetText("taskHint", "提示：开始后直接操控病毒群。")
        self:SetText("taskReward","")
        self:SetProgress("taskProgressBar", 0)
    end
    local taskHint=self.root:FindById("taskHint")
    if taskHint then taskHint:SetVisible(sim.started and task~=nil and not Mobile.IsTouch(self)) end
    if Mobile.IsTouch(self) then
        for _,suffix in ipairs({"Text","Hint","Reward"}) do
            local original=self.root:FindById("task"..suffix)
            if original then self:SetText("taskDetail"..suffix,original.props.text or "") end
        end
    end
    self:RefreshDiseaseProgress()
    self:SetText("virusCount", "活病毒 " .. countText(counts and counts.virus))
    self:SetText("splitCount", "群体病毒 " .. countText(counts and ((counts.mainMass or 0)+(counts.splitMass or 0))))
    self:SetText("releasedCount", "释放病毒 " .. countText(counts and counts.released) .. "（活病毒内）")
    self:SetText("infectedCount", "感染节点 " .. countText(counts and counts.infected))
    self:SetText("nodeStates", "潜伏 " .. countText(counts and counts.latent) .. " / 释放 " .. countText(counts and counts.productive) .. " / 耗竭 " .. countText(counts and counts.exhausted))
    self:SetText("healthyCount", "健康 " .. countText(counts and counts.healthy) .. " · 接触中 " .. countText(counts and counts.exposed))
    local investigating,processing=0,0
    for _,immune in ipairs(self.sim.world.immunes) do
        if immune.state=="investigate" or immune.signalInvestigation or immune.respondingToAlarm
            or immune._screenCellId or immune.state=="search" or immune.hotspotCleanup then investigating=investigating+1 end
        if immune.state=="processing" then processing=processing+1 end
    end
    self:SetText("deadImmuneCount",string.format("死亡 %d · 免疫 %d · 调查 %d / 处理 %d · 抗病毒 %d",
        counts and counts.dead or 0,counts and counts.immune or 0,investigating,processing,self.sim.world.tissueDefenseCount or 0))
    self:SetText("totalInfectedCount", "累计感染 " .. countText(self:ReadStat("totalInfected")))
    self:SetText("totalReleasedCount", "累计释放 " .. countText(self:ReadStat("totalReleased")) .. " · 吸收 " .. countText(self:ReadStat("totalAbsorbed")))
    self:SetText("totalKilledCount", "被清除 " .. countText(self:ReadStat("totalKilled")) .. " · 离区 / 失活 " .. countText(self:ReadStat("totalLost")))
    self:SetText("independentCount", "独立感染 " .. countText(self:ReadStat("independentInfections")))
    self:RefreshStatus(counts)
end

function HUD:RefreshDiseaseProgress()
    local G = Config.Gameplay
    local inflammation = self.sim.globalInflammation
    local damage = self.sim.globalTissueDamage
    local ip = G.irreversibleInflammation > 0 and inflammation / G.irreversibleInflammation or 0
    local dp = G.irreversibleDamage > 0 and damage / G.irreversibleDamage or 0
    self:SetText("inflammationLabel", string.format("炎症 %.0f%%", unitProgress(ip) * 100))
    self:SetText("damageLabel", string.format("损伤 %.0f%%", unitProgress(dp) * 100))
    self:SetProgress("inflammationBar", ip)
    self:SetProgress("damageBar", dp)
    self:SetText("victoryStatus", self.sim.irreversible and "已进入不可逆阶段；群体被清除也不取消胜利。"
        or string.format("病程胜利进度 %.0f%% · 以实际模拟判定为准", unitProgress(self.sim.victoryProgress) * 100))
end

function HUD:ApplyLayout()
    local root = self.root
    if not root then return end
    local content = root:FindById("hudContent")
    if not content then return end
    local rect = content:GetLayout()
    local quickCount=1+(Ability.Owned(self.sim.world,"emergency_dash") and 1 or 0)
        +(Ability.Owned(self.sim.world,"shed_decoy") and 1 or 0)
    local touch=Mobile.IsTouch(self)
    if rect.w <= 0 or rect.h <= 0 or (rect.w == self.layoutWidth_ and rect.h == self.layoutHeight_
        and quickCount==self.layoutQuickCount_ and touch==self.layoutTouch_) then return end
    self.layoutQuickCount_=quickCount
    self:ClearTouchMove() -- 转屏 / 安全区改变时不能继续沿用旧摇杆中心。
    self.layoutWidth_, self.layoutHeight_ = rect.w, rect.h
    if touch~=self.layoutTouch_ then self.layoutTouch_=touch;self:ApplyInputTexts(touch) end
    -- 触屏：放大摇杆和按钮（≥44px 触控目标），矮横屏压缩上方面板；桌面沿用原尺寸。
    local m=touch and Mobile.Metrics(rect.w,rect.h) or nil
    if touch then self:ApplyMobileLayout(rect,m);return end
    local task=root:FindById("stagePanel")
    local taskHost=root:FindById("taskPanelHost")
    if task and taskHost and task.parent~=taskHost then
        task.parent:RemoveChild(task);taskHost:AddChild(task)
        local unset=YGUndefined or (0/0)
        task:SetStyle{position="relative",left=unset,top=unset,width="100%",padding=12,gap=5}
        root:FindById("hudLeftScroll"):SetVisible(true)
    end
    local topHeight=m and m.topHeight or math.min(190,rect.h*0.38)
    local top = root:FindById("hudTopRow")
    local bottom = root:FindById("hudBottomRow")
    if top then top:SetStyle {height=topHeight} end
    if bottom then bottom:SetStyle {height="auto",minHeight=0} end
    local small=rect.w<760
    local actionWidth=m and m.actionWidth or (small and 96 or 116)
    local menuWidth=m and m.menuWidth or 48
    local buttonHeight=m and m.buttonHeight or 48
    local iconSize=m and m.iconSize or 26
    for id,btn in pairs(self.strategyButtons_) do
        btn:SetStyle {flexBasis=id=="menu" and menuWidth or actionWidth,
            width=id=="menu" and menuWidth or actionWidth,flexGrow=0,flexShrink=0,
            height=buttonHeight,fontSize=m and 13 or (small and 11 or 12),
            paddingLeft=id=="menu" and 0 or (iconSize+17),paddingRight=id=="menu" and 0 or 8}
        if btn.assetIcon_ then btn.assetIcon_:SetStyle {width=iconSize,height=iconSize,
            left=id=="menu" and (menuWidth-iconSize)/2 or 8,translateY=-iconSize/2} end
        if id=="menu" then btn:SetText("") end
    end
    local groupsWidth=m and m.groupsWidth or 76
    if m then
        self:ResizeJoystick(m.pad,m.knob,m.joystickWidth,m.showJoystickHint)
    else
        self:ResizeJoystick(PAD_SIZE,KNOB_SIZE,128,true)
    end
    local statsToggle=root:FindById("statsToggle")
    if statsToggle then statsToggle:SetStyle{height=m and m.statsToggleHeight or 28} end
    local edgeTab=root:FindById("statsEdgeTab")
    if edgeTab then edgeTab:SetStyle{width=m and 40 or 28,height=m and 60 or 54} end
    for i=1,6 do
        local slot=root:FindById("skillMenu_"..i)
        if slot then slot:SetStyle{height="auto",minHeight=80,flexShrink=0} end
    end
    for _,id in ipairs({"quickDash","quickDecoy","quickMenu"}) do
        local q=root:FindById(id)
        if q then q:SetStyle{height=m and m.quickHeight or 48} end
    end
    local stats=root:FindById("entityDetails")
    if stats then stats:SetStyle{top=topHeight+16} end
    if self.motions_.stats then self.motions_.stats.height=math.max(100,math.min(300,rect.h-topHeight-140)) end
    if self.motions_.groups then self.motions_.groups.height=math.min(156,rect.h*0.24) end
    self.stageSummary.width=math.min(336,rect.w*0.46)
    local summaryScroll=root:FindById("hudStatsScroll")
    if summaryScroll then summaryScroll:SetStyle{height=m and m.summaryHeight or math.min(152,rect.h*0.42)} end
    local popup=root:FindById("skillMenuPopup")
    if popup then
        local bottomInset=math.min(124,math.max(24,rect.h*.2))
        popup:SetStyle {height=math.max(100,math.min(560,rect.h-bottomInset-16)),bottom=bottomInset,
            width=math.min(420,math.max(180,rect.w-16))}
    end
    local prompt=root:FindById("skillTargetPrompt")
    if prompt then
        local unset=YGUndefined or (0/0)
        prompt:SetStyle{left=unset,top=unset,right=16,bottom=math.min(124,math.max(64,rect.h*.2)),
            width=math.min(360,math.max(100,rect.w-32)),height="auto",padding=12,gap=8,zIndex=8,flexDirection="column"}
        root:FindById("skillTargetText"):SetStyle{fontSize=12,width="100%",flexBasis="auto",flexGrow=0}
        root:FindById("skillCancel"):SetStyle{height=36,width=120,alignSelf="flex-end"}
    end
    local quick=root:FindById("skillQuickBar")
    local baseWidth=4*actionWidth+menuWidth+groupsWidth+30
    local quickWidth=quickCount*112+(quickCount-1)*8
    local base=root:FindById("baseActionRow")
    local joystick=root:FindById("joystickPanel")
    local reserve=joystick and joystick:IsVisible() and (m and m.joystickWidth+8 or 136) or 0
    reserve=math.max(reserve,joystick and joystick:IsVisible() and 136 or 0)
    -- 同时受屏幕和操作区上限约束；窄屏快捷栏换行，不能撑出安全区。
    local available=math.max(0,math.min(980,rect.w-reserve))
    local rowWidth=math.min(available,baseWidth)
    if base then base:SetStyle{flexGrow=0,flexShrink=0,flexBasis=rowWidth,width=rowWidth,maxWidth="100%"} end
    local groups=root:FindById("groupsToggle")
    if groups then groups:SetStyle{width=groupsWidth,flexBasis=groupsWidth,flexGrow=0,flexShrink=0,height=buttonHeight} end
    if quick then quick:SetStyle {maxWidth="100%",width=math.min(available,quickWidth),
        flexBasis=math.min(available,quickWidth),flexGrow=0,flexShrink=0} end
    local bar=root:FindById("strategyBar")
    if bar then bar:SetStyle{width=math.min(available,baseWidth+quickWidth+6),
        flexGrow=0,flexShrink=0,flexBasis="auto"} end

end

-- Left thumb steers; the main action anchors a thumb arc, with utility keys in a separate strip.
function HUD:ApplyMobileLayout(rect,m)
    local root=self.root
    local function style(id,props)
        local w=root:FindById(id);if w then w:SetStyle(props) end
        return w
    end
    local safe=Mobile.SafeInsets()
    local dockScale=math.max(.96,math.min(1.12,UI.GetHeight()/540))
    local dockW,dockH=350*dockScale,244*dockScale
    local utilities=style("mobileUtilities",{visible=true,width=160,height=48,right=8,top=4})
    if utilities then utilities:SetVisible(true) end
    local base=root:FindById("baseActionRow")
    for _,id in ipairs({"mapBtn","menuBtn","groupsToggle"}) do
        local w=root:FindById(id)
        if w and utilities and w.parent~=utilities then w.parent:RemoveChild(w);utilities:AddChild(w) end
    end
    local function circle(id,size,right,bottom,utility)
        local btn=root:FindById(id)
        if not btn then return end
        btn:SetStyle{position=utility and "relative" or "absolute",right=0,bottom=0,
            left=utility and 0 or dockW-size-right,top=utility and 0 or dockH-size-bottom,translateX=0,translateY=0,
            width=size,height=size,minWidth=size,maxWidth=size,minHeight=size,flexBasis=size,
            flexGrow=0,flexShrink=0,borderRadius=size/2,backgroundImage="",
            backgroundColor={28,17,26,220},hoverBackgroundColor={62,37,37,240},
            pressedBackgroundColor={96,54,34,250},disabledBackgroundColor={21,16,26,170},
            borderWidth=1.5,hoverBorderWidth=2,pressedBorderWidth=2,borderColor={176,126,74,230},
            disabledBorderColor={95,72,64,180},fontSize=utility and 11 or 12,minFontSize=11,
            paddingLeft=2,paddingRight=2,paddingTop=btn.assetIcon_ and (utility and 18 or 24) or 0,paddingBottom=0}
        if btn.assetIcon_ then
            local icon=utility and 18 or 24
            btn.assetIcon_:SetStyle{width=icon,height=icon,left=(size-icon)/2,
                top=utility and 5 or 9,translateY=0}
        end
    end
    circle("mapBtn",48,0,0,true);circle("menuBtn",48,0,0,true);circle("groupsToggle",48,0,0,true)
    self:SetText("menuBtn","暂停");self:SetText("groupsToggle","群组")
    -- Combat keys follow a broad arc around the main action, never a rectangular grid.
    local function combat(id,cx,cy,diameter,primary)
        local d=diameter*dockScale
        circle(id,d,dockW-(cx+diameter/2)*dockScale,dockH-(cy+diameter/2)*dockScale)
        local btn=root:FindById(id)
        if not btn then return end
        local icon=(primary and 40 or 28)*dockScale
        btn:SetStyle{fontSize=primary and 16 or 13,minFontSize=primary and 14 or 12,
            paddingTop=(primary and 38 or 26)*dockScale,
            borderWidth=primary and 2.5 or 1.5,
            borderColor=primary and {245,190,98,255} or {176,126,74,230},
            backgroundColor=primary and {92,51,27,240} or {28,17,26,220}}
        if btn.assetIcon_ then btn.assetIcon_:SetStyle{width=icon,height=icon,
            left=(d-icon)/2,top=(primary and 14 or 9)*dockScale} end
    end
    combat("absorbBtn",288,176,100,true)
    combat("splitBtn",188,200,68,false)
    combat("quickDash",159,116,68,false)
    combat("quickDecoy",239,40,68,false)
    -- Management controls have distinct shapes and sit outside the combat arc.
    for _,entry in ipairs({{id="switchBtn",x=10},{id="quickMenu",x=80}}) do
        local d=52*dockScale
        circle(entry.id,d,0,0)
        local btn=root:FindById(entry.id)
        if btn then
            btn:SetStyle{left=entry.x*dockScale,top=177*dockScale,
                width=62*dockScale,minWidth=62*dockScale,maxWidth=62*dockScale,
                flexBasis=62*dockScale,borderRadius=12*dockScale,fontSize=12,minFontSize=11,
                paddingTop=18*dockScale,backgroundColor={25,20,30,220}}
            if btn.assetIcon_ then btn.assetIcon_:SetStyle{width=20*dockScale,height=20*dockScale,
                left=21*dockScale,top=5*dockScale} end
        end
    end
    style("hudBottomRow",{justifyContent="space-between",height=math.max(dockH,m.pad),alignItems="flex-end"})
    style("strategyBar",{position="absolute",right=20,bottom=20,width=dockW,height=dockH,
        flexBasis="auto",maxWidth="100%",flexGrow=0,flexShrink=0})
    style("actionDock",{width="100%",height="100%",gap=0})
    style("dockActions",{position="absolute",right=0,bottom=0,width="100%",height="100%"})
    if base then base:SetStyle{position="absolute",right=0,bottom=0,width="100%",height="100%",
        flexBasis="auto",flexGrow=0,flexShrink=0} end
    style("skillQuickBar",{position="absolute",right=0,bottom=0,width="100%",height="100%",
        minWidth=0,maxWidth="100%",flexBasis="auto",flexGrow=0,flexShrink=0})
    style("quickButtonRow",{width="100%",height="100%"})
    local ticker=style("statusTicker",{position="absolute",right=dockW+16,bottom=0,
        width=math.max(120,rect.w-dockW-m.joystickWidth-40),height=32,minHeight=0,maxHeight=32})
    -- Routine controls do not need a permanent instructional ticker on a phone.
    if ticker then ticker:SetVisible(self.noticeText_~="" and self.noticeElapsed_<3.5) end
    self:ResizeJoystick(m.pad,m.knob,m.joystickWidth,false)
    style("hudTopRow",{height=162})
    style("hudLeftScroll",{width=math.min(276,rect.w*.32),flexBasis=math.min(276,rect.w*.32),maxWidth=276})
    local task=style("stagePanel",{position="absolute",left=(safe.left or 0)+8,top=(safe.top or 0)+8,
        width=math.min(276,rect.w*.32),padding=8,gap=2})
    if task and task.parent~=root then task.parent:RemoveChild(task);root:AddChild(task) end
    root:FindById("hudLeftScroll"):SetVisible(false)
    local toggle=root:FindById("taskToggle");if toggle then toggle:SetVisible(true);toggle:SetText(self.taskExpanded_ and "收起" or "详情") end
    local detail=root:FindById("taskText");if detail then detail:SetVisible(true) end
    local hint=root:FindById("taskHint");if hint then hint:SetVisible(false) end
    local reward=root:FindById("taskReward");if reward then reward:SetVisible(false) end
    style("taskProgress",{fontSize=10,maxLines=2})
    style("taskProgressBar",{height=6})
    local summaryWidth=math.min(200,rect.w*.24)
    self.stageSummary.width=summaryWidth
    style("stageSummary",{width=summaryWidth,maxWidth=summaryWidth,right=(safe.right or 0)+8,top=(safe.top or 0)+72})
    style("hudStatsScroll",{height=96})
    style("entityPanel",{padding=7,gap=2})
    style("statsToggle",{height=44})
    style("statsEdgeTab",{width=44,height=44,top=(safe.top or 0)+72,right=(safe.right or 0)+8})
    style("entityDetails",{width=math.min(270,rect.w*.34),maxWidth=270,top=(safe.top or 0)+72,right=(safe.right or 0)+8})
    if self.motions_.stats then
        -- This overlay belongs to the full HUD, not the intrinsically sized top content row.
        self.motions_.stats.height=math.max(160,UI.GetHeight()-(safe.top or 0)-(safe.bottom or 0)-190)
    end
    local usableH=UI.GetHeight()-(safe.top or 0)-(safe.bottom or 0)
    style("taskDrawer",{left=(safe.left or 0)+16,top=(safe.top or 0)+64,
        width=math.min(440,rect.w*.48),height=math.max(180,usableH-100)})
    for _,id in ipairs({"groupDrawer","skillTargetPrompt"}) do
        local widget=root:FindById(id)
        if widget and widget.parent~=root then widget.parent:RemoveChild(widget);root:AddChild(widget) end
    end
    style("swarmSelector",{flexDirection="column",flexWrap="no-wrap",gap=8})
    for _,button in ipairs(self.groupButtons_) do
        button:SetStyle{width="100%",height=52,flexBasis=52,flexGrow=0,flexShrink=0}
    end
    style("groupDrawer",{left=UI.GetWidth()-(safe.right or 0)-16-math.min(360,rect.w*.4),bottom=0,right=(safe.right or 0)+16,
        top=(safe.top or 0)+64,width=math.min(360,rect.w*.4),zIndex=7,gap=8})
    if self.motions_.groups then self.motions_.groups.height=math.max(180,usableH-100) end
    style("skillMenuPopup",{width=math.min(380,math.max(240,rect.w-dockW-m.joystickWidth-64)),height=math.max(180,usableH-96),
        left=(safe.left or 0)+m.joystickWidth+24,right=0,
        bottom=(safe.bottom or 0)+48,padding=10,zIndex=8})
    style("skillTargetPrompt",{left=(safe.left or 0)+m.joystickWidth+24,right=YGUndefined or (0/0),
        bottom=(safe.bottom or 0)+24,width=math.max(200,rect.w-m.joystickWidth-dockW-64),
        padding=10,gap=8,zIndex=8,flexDirection="column"})
    style("skillTargetText",{fontSize=14,flexBasis="auto",flexGrow=0,width="100%"})
    style("skillCancel",{height=48,width="100%"})
    for i=1,6 do style("skillMenu_"..i,{height="auto",minHeight=72,flexShrink=0}) end
    if not self.touchControls_ then self.touchControls_=require("UI.TouchControls").New(self) end
    self.touchControls_:Apply()
end

-- 触屏 / 桌面切换时同步按钮上的操作名；动态文字（冷却、提示）由各自 Refresh 按同一判定生成。
---@param touch boolean
function HUD:ApplyInputTexts(touch)
    local T=Mobile.Text
    local texts=touch and {splitBtn=T.splitBtn,switchBtn=T.switchBtn,quickMenu=T.quickMenu,
        skillCancel=T.skillCancel,skillMenuClose=T.skillMenuClose,mapBtn="地图",scaleHint="摇杆移动 · 双指缩放 · 点「地图」查看全图"}
        or {splitBtn="分离 空格",switchBtn="切群 Tab",quickMenu="V · 技能",
        skillCancel="取消 · Esc",skillMenuClose="关闭",mapBtn="地图 M",scaleHint="WASD / 方向键 / 摇杆移动 · M 全图"}
    for id,text in pairs(texts) do self:SetText(id,text) end
end

-- 保留主入口的刷新接口；游戏只有细胞场景，不再切到宿主观察。
function HUD:RefreshScale()
    if not self.sim:CanAct() then self:ClearTouchMove() end
    self:RefreshJoystickVisibility()
end

function HUD:RefreshJoystickVisibility()
    if not self.touchSeen_ then
        for _, pointer in pairs(UI.Input.GetActivePointers()) do
            if pointer.pointerType == "touch" then self.touchSeen_ = true; break end
        end
    end
    local needsJoystick = PlatformUtils.NeedsVirtualJoystick() or self.touchSeen_ or Mobile.IsTouch(self)
    local panel = self.root and self.root:FindById("joystickPanel")
    if panel then
        local show=not self.touchControls_ and needsJoystick and self.sim.started and self.scaleMgr:CurrentScale()=="cell"
        if panel:IsVisible()~=show then panel:SetVisible(show);self.layoutWidth_=0 end
    end
end

-- 按钮与 main 快捷键共用这些操作入口，暂停门控、提示和摇杆清理一致。
function HUD:Notify(text)
    self.noticeText_,self.noticeElapsed_=text or "",0
    self.tickerElapsed_=0
    self:UpdateTicker(0)
end

-- 固定 36px 视窗内向上轮播；提示只改变文字与渲染位移，不参与按钮/地图布局。
function HUD:UpdateTicker(dt)
    if not self.root then return end
    local elapsed=math.max(0,dt)
    self.noticeElapsed_=self.noticeElapsed_+elapsed
    if Mobile.IsTouch(self) then
        local ticker=self.root:FindById("statusTicker")
        if ticker then ticker:SetVisible(self.noticeText_~="" and self.noticeElapsed_<3.5) end
    end
    local current=self.root:FindById("actionNotice")
    local nextLabel=self.root:FindById("actionNoticeNext")
    if not current or not nextLabel then return end
    if self.noticeText_~="" and self.noticeElapsed_<3.5 then
        self:SetText("actionNotice",self.noticeText_)
        if current.props.translateY~=0 then current:SetStyle {translateY=0} end
        if nextLabel.props.translateY~=0 then nextLabel:SetStyle {translateY=0} end
        return
    end
    self.tickerElapsed_=(self.tickerElapsed_+elapsed)%10
    local detail=self.root:FindById("swarmStatusDetail")
    local absorption=self.root:FindById("absorptionStatus")
    local a=detail and detail.props.text or ""
    local b=absorption and absorption.props.text or ""
    if a=="" then a=Mobile.IsTouch(self) and Mobile.Text.ticker or "E 吸附 · 空格分离 · Tab 切群 · Esc 暂停设定" end
    if b=="" then b=a end
    local second=self.tickerElapsed_>=5
    self:SetText("actionNotice",second and b or a)
    self:SetText("actionNoticeNext",second and a or b)
    local t=math.max(0,(self.tickerElapsed_%5-4.65)/0.35)
    local offset=-36*t*t*(3-2*t)
    if current.props.translateY~=offset then current:SetStyle {translateY=offset} end
    if nextLabel.props.translateY~=offset then nextLabel:SetStyle {translateY=offset} end
end

function HUD:AbsorbNearby()
    if self.scaleMgr:CurrentScale() ~= "cell" or not self.sim:CanAct() then return end
    local count, reason = self.sim:AbsorbNearby()
    self.actionNotice_ = reason or (count > 0 and string.format("已吸附 %d 个游离病毒到当前群。", count)
        or "附近没有可吸附的存活游离病毒；请靠近释放个体。")
    self.actionNoticeUntil_ = self.sim.time + 2.5
    self:Notify(self.actionNotice_)
    self:RefreshStrategyHighlight()
    self:RefreshStatus(self:ReadCounts())
    self.refreshAccum_ = 0.12
end

function HUD:Split()
    if self.scaleMgr:CurrentScale() ~= "cell" or not self.sim:CanAct() then return end
    self:ClearTouchMove()
    local success = self.sim:Split()
    self.actionNotice_ = success and (Mobile.IsTouch(self) and Mobile.Text.splitSuccess
        or "分离成功：新分群沿最近移动方向弹出；Tab 或点选切换。")
        or self.sim.world:SplitUnavailableReason() or "当前无法分裂"
    self.actionNoticeUntil_ = self.sim.time + 2.5
    self:Notify(self.actionNotice_)
    self:RefreshStrategyHighlight()
    self:RefreshStatus(self:ReadCounts())
    self.refreshAccum_ = 0.12
end

---@param swarmId integer?
function HUD:SwitchControl(swarmId)
    if self.scaleMgr:CurrentScale() ~= "cell" or not self.sim:CanAct() then return end
    self:ClearTouchMove()
    self.sim:SwitchControl(swarmId)
    self.actionNotice_, self.actionNoticeUntil_ = "", 0
    self:Notify("")
    self:RefreshStrategyHighlight()
    self:RefreshStatus(self:ReadCounts())
    self.refreshAccum_ = 0.12
end

-- 按存活群高水位扩容，回调只按实时槽位读 ID，不捕获已死亡群对象。
function HUD:EnsureGroupButtons()
    local world, selector = self.sim.world, self.swarmSelector_
    if not world or not selector then return end
    for index = #self.groupButtons_ + 1, #world.swarms do
        local slot = index
        -- [HUD_BUTTON:selectSwarm_] 动态群体点选；编号、规模、状态随模拟更新
        local btn = button {
            id = "selectSwarm_" .. slot, text = "—", visible = false,
            minWidth = 140, width=Mobile.IsTouch(self) and "100%" or "auto",
            flexGrow = Mobile.IsTouch(self) and 0 or 1, flexBasis = Mobile.IsTouch(self) and 52 or 160,
            fontSize = 13, height=Mobile.IsTouch(self) and 52 or 40,
            onClick = function()
                local activeWorld = self.sim.world
                local swarm = activeWorld and activeWorld.swarms[slot]
                if swarm then self:SwitchControl(swarm.id) end
            end,
        }
        self.groupButtons_[slot] = btn
        selector:AddChild(btn)
    end
end

function HUD:OpenMap()
    if not self.sim:CanAct() or (self.sim.tutorial and self.sim.tutorial.active) then return end
    self:ClearTouchMove()
    if self.onMap then self.onMap() end
end

-- 保留 main 的兼容接口名称；刷新的是新操作禁用，不再保留免费隐匿 / 三形态。
function HUD:RefreshStrategyHighlight(fast)
    self:EnsureGroupButtons()
    local sim = self.sim
    local world = sim.world
    local player = world and world.player
    local canAct = sim:CanAct() and self.scaleMgr:CurrentScale() == "cell"
    local splitDisabled = not canAct or not sim:CanUseAction("split") or not world or not world:CanSplit()
    local switchDisabled = not canAct or not sim:CanUseAction("switch") or not world or world:LiveSwarmCount() < 2
    local absorbDisabled = not canAct or not sim:CanUseAction("absorb") or not player or player.mass <= 0 or player.isHidden or world:GetAbsorptionCooldown()>1e-9
    local mapDisabled=not canAct or (sim.tutorial and sim.tutorial.active==true) or not self.onMap
    local disabled = { absorb = absorbDisabled, split = splitDisabled, switch = switchDisabled, map = mapDisabled }
    for id, btn in pairs(self.strategyButtons_) do
        local value = disabled[id] == true
        if btn:IsDisabled() ~= value then btn:SetDisabled(value) end
    end
    for index, btn in ipairs(self.groupButtons_) do
        local swarm = world and world.swarms[index]
        local visible = sim.started and swarm ~= nil
        if btn:IsVisible() ~= visible then btn:SetVisible(visible) end
        local disabledGroup = not canAct or not sim:CanUseAction("switch") or not world:CanControl(swarm) or swarm.isPlayerControlled
        if btn:IsDisabled() ~= disabledGroup then btn:SetDisabled(disabledGroup) end
        if swarm and not fast then
            local behavior = swarm.anchored and "留守" or swarm.isHidden and "藏身" or swarm.groupCommand and "指令" or swarm.isPlayerControlled and "手动" or (AI_LABELS[swarm.aiState] or "等待")
            local text = (swarm.isPlayerControlled and "当前 " or "")
                .. "群 #" .. swarm.id .. " · " .. swarm.mass .. " · " .. behavior
            if btn.props.text ~= text then btn:SetText(text) end
            local selected = swarm.isPlayerControlled and Config.Palette.virus or CLEAR_BORDER
            if btn.props.borderColor ~= selected then btn:SetStyle {borderColor=selected,
                borderWidth=swarm.isPlayerControlled and 1 or 0} end
        end
    end
end

---@param counts SwarmCounts?
function HUD:RefreshStatus(counts)
    local sim, world = self.sim, self.sim.world
    local player = world and world.player
    local touch = Mobile.IsTouch(self)
    local T = Mobile.Text
    self:SetText("swarmListTitle", string.format(touch and T.swarmListTitle or "存活群体 %d / %d · 点选控制（Tab 循环）",
        counts and counts.groups or 0, world.maxPlayerSwarms))
    local ai = Config.Gameplay.autonomy
    local autonomous, fleeing, infecting = 0, 0, 0
    if world then
        for _, swarm in ipairs(world.swarms) do
            if swarm.mass > 0 and not swarm.isPlayerControlled and not swarm.isHidden then
                autonomous = autonomous + 1
                if swarm.aiState == "flee" then fleeing = fleeing + 1 end
                if swarm.aiState == "infect" then infecting = infecting + 1 end
            end
        end
    end
    self:SetText("autonomyStatus", world.swarmBrainEnabled and string.format(
        "分群小脑 · 自主 %d 群 · 避敌 %d · 感染 %d · 不自动分裂",autonomous,fleeing,infecting)
        or "尚未获得分群小脑：未控制分群漂移与接触感染。")
    CardPanel.Refresh(self)
    if not sim.started then
        self:SetText("swarmStatus", "尚未开始")
        self:SetText("absorptionStatus", touch and T.absorptionIdle or "E 吸附附近游离病毒；规模越大，感染越快。")
        self:SetText("swarmStatusDetail", "请开始游戏。")
        return
    end
    if player and player.mass > 0 then
        local region = world.map.regions[player.currentRegionId]
        self:SetText("absorptionStatus", string.format(touch and T.absorption or "E 吸附：附近 %d 个 · 范围 %.2f米 · 接触感染倍率 ×%.2f",
            world:AbsorbableCount(), player.radius + Config.Gameplay.activeAbsorptionExtra,
            world:GroupInfectionMultiplier(player)))
    else
        self:SetText("swarmStatus", "当前无可控制病毒群")
        self:SetText("absorptionStatus", "无存活群体，不能吸附或复活。")
    end
    if sim.ending then
        self:SetText("swarmStatusDetail", "本局已结束，请重新开始。")
    elseif sim.paused then
        self:SetText("swarmStatusDetail", "模拟已暂停，关闭说明或返回游戏继续。")
    elseif not counts or not world then
        self:SetText("swarmStatusDetail", "等待权威世界状态。")
    elseif self.actionNotice_ ~= "" and sim.time < self.actionNoticeUntil_ then
        self:SetText("swarmStatusDetail", self.actionNotice_)
    elseif world:SplitUnavailableReason() then
        self:SetText("swarmStatusDetail",world:SplitUnavailableReason())
    elseif world.splitCooldown > 0 then
        self:SetText("swarmStatusDetail", string.format(touch and T.splitCooldown or "分离冷却 %.1f秒 · E 可继续吸附，Tab / 点选切换。", world.splitCooldown))
    elseif player and player.mass < Config.Gameplay.splitMinMass then
        self:SetText("swarmStatusDetail", string.format(touch and T.splitNeedMass or "当前群至少 %d 个才能分离；E 吸附游离个体壮大当前群。", Config.Gameplay.splitMinMass))
    elseif world.mergeReady then
        self:SetText("swarmStatusDetail", "附近群正在互相吸引，接触后自动合并；不影响其他远处分群。")
    else
        self:SetText("swarmStatusDetail", touch and T.splitReady or "空格可再次分离；Tab或点选切群；V打开功能菜单，数字键选择。")
    end
end

-- SIM_ENDING 仅通知；完全信任 sim.ending，不用感染节点 / 游离病毒数拦截失败。
---@param summary table?
function HUD:ShowEnding(summary)
    if not self.root then return end
    local outcome = self.sim.ending
    if outcome ~= "victory" and outcome ~= "extinct" then return end
    if self.endingShown_ then return end
    self:CloseCardInfo()
    self:ClearTouchMove()
    self.endingShown_ = true
    if self.sim.tutorial then self.sim.tutorial:Stop(false) end
    local victory = outcome == "victory"
    self:SetText("endingTitle", victory and "胜利 · 不可逆重症" or "失败 · 病毒群被清除")
    local title = self.root:FindById("endingTitle") --[[@as Label?]]
    if title then title:SetFontColor(victory and Config.Palette.virus or Config.Palette.immuneCool) end
    self:SetText("endingReason", victory
        and "鸟已进入不可逆阶段。即使病毒群随后被清除，也不取消本局胜利。"
        or "玩家控制的所有病毒群已被免疫系统清除，鸟尚未进入不可逆重症。剩余感染节点不改变本局失败结果。")
    self:SetText("endingTime", "总时间 " .. elapsedText(self.sim.time))
    self:SetText("endingDisease", string.format("炎症 %.1f · 组织损伤 %.1f", self.sim.globalInflammation, self.sim.globalTissueDamage))
    self:SetText("endingInfected", "累计感染 " .. countText(self:ReadStat("totalInfected")))
    self:SetText("endingReleased", "累计释放 " .. countText(self:ReadStat("totalReleased")) .. " · 吸收 " .. countText(self:ReadStat("totalAbsorbed")))
    self:SetText("endingIndependent", "独立感染 " .. countText(self:ReadStat("independentInfections")))
    self:SetText("endingLost", "被清除 " .. countText(self:ReadStat("totalKilled")) .. " · 离区 / 失活 " .. countText(self:ReadStat("totalLost")))
    self:SetText("endingGroups", "分裂 " .. countText(self:ReadStat("totalSplits")) .. " 次 · 合并 " .. countText(self:ReadStat("totalMerges")) .. " 次")
    self:SetText("endingPeak", "峰值活病毒 " .. countText(self:ReadStat("peakVirus")))
    for _,motion in pairs(self.motions_) do motion:Reset() end
    self.stageSummary:Reset()
    self.endingScreen:Show(outcome)
end

function HUD:ResetEnding()
    self:CloseCardInfo()
    self:ClearTouchMove()
    self.touchMove_ = self.sim.touchMove
    self.endingShown_ = false
    if self.stageSummary then self.stageSummary:Reset() end
    self:Notify("")
    if self.endingScreen then self.endingScreen:Reset() end
    for _,motion in pairs(self.motions_) do motion:Reset() end
    local area=self.root and self.root:FindById("hudSafeArea")
    if area then area:SetVisible(true) end
    self:SetText("statsToggle","详细统计 ▾");self:SetText("groupsToggle",Mobile.IsTouch(self) and "群组" or "群列表")
    self.actionNotice_, self.actionNoticeUntil_ = "", 0
    self.lastScale_, self.lastStarted_ = nil, nil
    self.refreshAccum_ = 0.12
    self.textCache_ = {}
    local overlay = self.root and self.root:FindById("endingOverlay")
    if overlay then overlay:Hide() end
    self:RefreshScale()
    self:RefreshStrategyHighlight()
end

function HUD:Destroy()
    if self.destroyed_ then return end
    self:CloseCardInfo()
    CardPanel.ResetReveal(self)
    self:ClearTouchMove()
    if self.touchControls_ then self.touchControls_:Destroy() end
    for _, token in ipairs(self.tokens_) do EventBus.Off(token) end
    self.tokens_ = {}
    if self.touchListener_ then UI.Input.Off("PointerDown", self.touchListener_) end
    self.touchListener_ = nil
    if self.endingScreen then self.endingScreen:Reset() end
    self.destroyed_ = true
    if self.root then self.root:Destroy() end
    self.root, self.joystick_, self.joystickKnob_ = nil, nil, nil
    self.strategyButtons_, self.textCache_ = {}, {}
end

return HUD
