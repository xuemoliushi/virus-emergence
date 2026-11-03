-- 基于 scaffold-2d.lua 的声明式 UI；仅使用组件，不创建独立 NanoVG 帧。
local UI = require("urhox-libs/UI")
local Skin = require("UI.AssetTheme")
---@type { groups: { role: string, names: string[] }[], closingMessage: string }
local Credits = require("UI.CreditsData")
local MenuBackdrop = require("UI.MenuBackdrop")
local Mobile = require("UI.MobileLayout")
local CreditsSkip = require("UI.CreditsSkip")

local function ReadyText()
    return Mobile.IsTouch() and Mobile.Text.menuReady or "场景已就绪 · Enter 开始"
end

local function CompactMenu()
    -- Web phones may not report touch until their first tap. Fit the first frame too.
    return Mobile.IsTouch() or UI.GetHeight()<600
end

local COLOR = { text=Skin.colors.text, muted=Skin.colors.muted, warm=Skin.colors.gold,
    surface=Skin.colors.surface, border=Skin.colors.border }

---@param text string
---@param size number?
local function label(text, size)
    return UI.Label { text = text, fontSize = size or 12, fontColor = COLOR.text,
        width = "100%", textAlign = "center" }
end

---@param text string
---@param action function
---@param primary boolean?
local function button(text, action, primary, kind, icon)
    return Skin.Button({text=text,height=primary and 84 or 56,width="100%",fontSize=16,
        onClick=action},kind or (primary and "primary" or "secondary"),icon)
end

---@class MainMenu
---@field settings UserSettings
---@field onAction fun(action: string)
---@field onClickSound fun()
---@field root Widget?
---@field creditsContent Widget?
---@field creditsSkip_ CreditsSkip?
---@field preparationProgress_ number
---@field preparationMessage_ string
---@field preparationTime_ number
---@field resolutionLabel Label?
---@field statusLabel Label?
---@field buttons Button[]
---@field backgroundCamera_ Panel?
---@field entering boolean
---@field backgroundLayers_ {widget:Panel,depth:number}[]
---@field pauseRoot Widget?
local Menu = {}
Menu.__index = Menu

function Menu.New(settings, onAction, onClickSound)
    local self = setmetatable({}, Menu)
    self:init(settings, onAction, onClickSound)
    return self
end

function Menu:init(settings, onAction, onClickSound)
    self.settings, self.onAction = settings, onAction
    self.onClickSound = onClickSound or function() end
    self.root, self.creditsContent, self.resolutionLabel, self.statusLabel = nil, nil, nil, nil
    self.screen, self.selected, self.creditsTime, self.resolutionTime = "menu", 1, 0, 0
    self.preparationProgress_,self.preparationMessage_,self.preparationTime_=0,"正在准备组织…",0
    self.creditsSkip_=nil
    self.buttons = {}
    self.hasRun = false
    self.prepared=false
    self.backgroundCamera_, self.entering = nil, false
    self.backgroundLayers_ = {}
    self.pauseRoot=nil
end

---@param action string
function Menu:Activate(action)
    if self.entering then return end
    self.onClickSound()
    self.onAction(action)
end

function Menu:DestroyRoot()
    self:DestroyPause()
    UI.ClearFocus()
    if self.root then self.root:Destroy(); self.root = nil end
    self.buttons = {}
    self.creditsContent, self.resolutionLabel, self.statusLabel = nil, nil, nil
    self.creditsSkip_=nil
    self.backgroundCamera_, self.entering = nil, false
    self.backgroundLayers_ = {}
end

function Menu:DestroyPause()
    UI.ClearFocus()
    if self.pauseRoot then self.pauseRoot:Destroy();self.pauseRoot=nil end
end

---@param root Widget
---@param screen string
function Menu:Mount(root, screen)
    local oldRoot = self.root
    UI.ClearFocus()
    UI.SetRoot(root)
    self.root, self.screen = root, screen
    self.creditsSkip_=nil
    if oldRoot then oldRoot:Destroy() end
    print("[Menu] " .. screen)
end

-- Layered HD artwork remains separate from menu controls so only the scene pushes forward.
function Menu:Background()
    local backdrop, camera, layers = MenuBackdrop.Build(self.settings.values.menuMotion)
    self.backgroundCamera_ = camera
    self.backgroundLayers_ = layers
    return backdrop
end

function Menu:BeginEntry()
    self.entering = true
    UI.ClearFocus()
end

---@param opacity number
---@param scale number
function Menu:SetEntryPose(opacity, scale)
    local foreground = self.root and self.root:FindById("menuForeground")
    if foreground then foreground:SetStyle { opacity=opacity, pointerEvents="none" } end
    -- Parallax is applied per depth plane; breathing remains on the child sprites.
    for _,layer in ipairs(self.backgroundLayers_) do
        layer.widget:SetStyle {scale=1+(scale-1)*layer.depth}
    end
end

function Menu:Show(hasRun)
    self.menuTouch_=nil
    self.hasRun = hasRun == true
    self.buttons = {}
    local title = UI.Panel { id="menuTitleGroup", width = "100%", marginBottom = 20, gap = 10, pointerEvents = "none",
        children = {
            UI.Label { id = "gameTitle", text = "病毒涌现", width = "100%", fontSize = 44,
                letterSpacing = 5, textAlign = "center", fontColor = COLOR.text,
                textShadow = { offsetX = 0, offsetY = 2, blur = 5, color = { 0, 0, 0, 220 } } },
            UI.Label { text = "微观之下，生存涌现", width = "100%", fontSize = 10,
                letterSpacing = 3, textAlign = "center", fontColor = COLOR.muted },
            Skin.Ornament { id="menuOrnament", height=32 },
        } }
    -- [UI_BUTTON:storyMode] 开始／继续游戏
    local story = button(self.hasRun and "继续游戏" or "开始", function() self:Activate("story") end, true)
    story.id,story.props.id = "storyMode","storyMode"
    -- [UI_BUTTON:endlessMode] 无尽模式，暂未开放
    local endless = button("无尽模式", function() end, false, "menu")
    endless.id,endless.props.id = "endlessMode","endlessMode"
    endless:SetDisabled(true)
    endless:SetStyle { disabledBackgroundColor = { 16, 13, 25, 220 },
        disabledTextColor = { 105, 99, 119, 255 }, borderColor = { 53, 43, 63, 160 } }
    endless:AddChild(UI.Label { text = "暂未开放", fontSize = 8, fontColor = { 120, 109, 133, 255 },
        position = "absolute", right = 12, top = 29, pointerEvents = "none" })
    -- [UI_BUTTON:openSettings] 打开设定
    local settings = button("设定", function() self:Activate("settings") end, false, "menu", "settings")
    settings.id,settings.props.id = "openSettings","openSettings"
    -- [UI_BUTTON:openCredits] 制作名单
    local credits = button("制作名单", function() self:Activate("credits") end, false, "menu")
    credits.id,credits.props.id = "openCredits","openCredits"
    -- [UI_BUTTON:exitGame] 退出游戏
    local exit = button("退出", function() self:Activate("exit") end, false, "menu")
    exit.id,exit.props.id = "exitGame","exitGame"
    for _,item in ipairs({endless,settings,credits,exit}) do item:SetStyle {height=72} end
    self.buttons = { story, settings, credits, exit }
    self.selected = 1
    ---@type Widget[]
    local options={title,story,endless,settings,credits,exit}
    if CompactMenu() then
        options={title,story,endless,UI.Panel{id="menuSecondary",width="100%",gap=12,
            children={settings,credits,exit}}}
    end
    local root = UI.Panel {
        id = "mainMenu", width = "100%", height = "100%", backgroundColor = { 8, 5, 15, 255 },
        children = { self:Background(), UI.SafeAreaView { id = "menuForeground",
            width = "100%", height = "100%", nativeMenuInset = true,
            children = { Skin.Scroll { width = "100%", flexGrow = 1, flexBasis = 0,
                showScrollbar = false, children = { UI.Panel {
                    id="menuContent", width = "100%", minHeight = "100%", paddingVertical = 28, gap = 22,
                    alignItems = "center", justifyContent = "center", pointerEvents = "box-none",
                    children = { UI.Panel {
                        id = "menuOptions", width = "86%", maxWidth = 432, gap = 12,
                        children = options,
                    }, UI.Panel {width="86%",maxWidth=432,gap=8,pointerEvents="none",children={
                        UI.Label { id="menuPreparation",text = self.prepared and
                        (self.hasRun and "游戏已暂停 · 选择继续游戏返回" or ReadyText()) or "正在预加载组织场景…",
                        width = "100%", fontSize = 11, textAlign = "center", fontColor = COLOR.muted },
                        Skin.Progress{id="menuPreparationProgress",width="100%",height=16,max=1,
                            value=self.preparationProgress_,showLabel=false,visible=not self.prepared},
                    }} },
                } } } },
        } },
    }
    self:Mount(root, "menu")
    self:ApplyMobileLayout()
end

-- Keep all menu actions visible on a short landscape phone, without scaling the art.
function Menu:ApplyMobileLayout()
    if not self.root or self.screen~="menu" then return end
    local touch=CompactMenu()
    if self.menuTouch_==touch then return end
    self.menuTouch_=touch
    local options=self.root:FindById("menuOptions")
    local secondary=self.root:FindById("menuSecondary")
    if options and touch and not secondary then
        secondary=UI.Panel{id="menuSecondary",width="100%",gap=6}
        for _,id in ipairs({"openSettings","openCredits","exitGame"}) do
            local btn=options:FindById(id)
            if btn then options:RemoveChild(btn);secondary:AddChild(btn) end
        end
        options:AddChild(secondary)
    elseif options and not touch and secondary then
        for _,id in ipairs({"openSettings","openCredits","exitGame"}) do
            local btn=secondary:FindById(id)
            if btn then secondary:RemoveChild(btn);options:AddChild(btn) end
        end
        secondary:Destroy()
    end
    local function style(id,props)
        local w=self.root:FindById(id);if w then w:SetStyle(props) end
    end
    style("menuContent",{paddingTop=touch and math.max(12,math.min(44,UI.GetHeight()*.065)) or 28,
        paddingBottom=touch and 12 or 28,justifyContent=touch and "flex-start" or "center",gap=touch and 8 or 22})
    style("menuOptions",{maxWidth=touch and 300 or 432,gap=touch and 8 or 12})
    style("menuTitleGroup",{marginBottom=touch and 4 or 20,gap=touch and 4 or 10})
    style("gameTitle",{fontSize=touch and 30 or 44,letterSpacing=touch and 3 or 5})
    style("menuOrnament",{height=touch and 16 or 32})
    style("storyMode",{height=touch and 52 or 84,fontSize=16})
    style("endlessMode",{height=touch and 44 or 72,fontSize=touch and 12 or 16})
    style("menuSecondary",{flexDirection=touch and "row" or "column",gap=touch and 6 or 12})
    for _,id in ipairs({"openSettings","openCredits","exitGame"}) do
        local btn=self.root:FindById(id)
        if btn then
            btn:SetStyle{width=touch and 0 or "100%",flexGrow=touch and 1 or 0,
                flexBasis=touch and 0 or "auto",height=touch and 44 or 72,fontSize=touch and 12 or 16,
                paddingLeft=touch and 6 or (btn.assetIcon_ and 60 or 16),paddingRight=touch and 6 or 16}
            if btn.assetIcon_ then btn.assetIcon_:SetVisible(not touch) end
        end
    end
end

function Menu:SetPreparationReady(ready)
    self.prepared=ready
    local status=self.root and self.root:FindById("menuPreparation") --[[@as Label?]]
    if status then status:SetText(ready and
        (self.hasRun and "游戏已暂停 · 选择继续游戏返回" or ReadyText()) or "正在预加载组织场景…") end
    local bar=self.root and self.root:FindById("menuPreparationProgress")
    if bar then bar:SetVisible(not ready) end
end

function Menu:SetPreparationProgress(progress,message)
    self.preparationProgress_,self.preparationMessage_=progress,message
    local bar=self.root and self.root:FindById("menuPreparationProgress") --[[@as ProgressBar?]]
    if bar then bar:SetValue(progress) end
end

function Menu:SaveSettings()
    local saved = self.settings:Save()
    if self.statusLabel then
        self.statusLabel:SetText(saved and "设定已保存" or "本次设定已生效，暂时无法保存")
    end
end

function Menu:VolumeRow(key, title)
    local valueLabel = UI.Label { text = string.format("%d%%", self.settings.values[key]),
        width = 48, textAlign = "right", fontSize = 11, fontColor = COLOR.warm }
    return UI.Panel { width = "100%", gap = 4, children = {
        UI.Panel { width = "100%", flexDirection = "row", justifyContent = "space-between", children = {
            UI.Label { text = title, fontSize = 12, fontColor = COLOR.text }, valueLabel,
        } },
        Skin.Slider { id = "volume_" .. key, width = "100%", height = 30, min = 0, max = 100, step = 1,
            value = self.settings.values[key], trackFillColor = COLOR.warm,
            onChange = function(_, value)
                self.settings.values[key] = value
                valueLabel:SetText(string.format("%d%%", math.floor(value + 0.5)))
                self.settings:ApplyAudio()
            end,
            onChangeEnd = function() self:SaveSettings(); self.onClickSound() end,
        },
    } }
end

---@param host Widget? 游戏内设置附着在游戏树上，不切换根控件。
function Menu:ShowSettings(host)
    self:DestroyPause()
    local compact=CompactMenu()
    self.resolutionLabel = label("", 10)
    self.resolutionLabel:SetStyle { fontColor = COLOR.muted }
    self.statusLabel = label("调整即时生效", 10)
    self.statusLabel:SetStyle { fontColor = COLOR.muted }
    local scale = Skin.Dropdown { id = "uiScale", width = "100%", height = 40,
        value = self.settings.values.uiScale, options = {
            { value = 0.85, label = "紧凑 · 85%" }, { value = 1, label = "标准 · 100%" },
            { value = 1.15, label = "放大 · 115%" },
        }, onChange = function(_, value)
            self.settings.values.uiScale = value
            self.settings:Apply(); self:SaveSettings(); self.onClickSound()
        end }
    local fps = Skin.Dropdown { id = "frameLimit", width = "100%", height = 40,
        value = self.settings.values.maxFps, options = {
            { value = 30, label = "30 FPS" }, { value = 60, label = "60 FPS" },
            { value = 120, label = "120 FPS" },
        }, onChange = function(_, value)
            self.settings.values.maxFps = math.floor(value)
            self.settings:Apply(); self:SaveSettings(); self.onClickSound()
        end }
    local content = UI.Panel { width = "100%", padding = compact and 14 or 22, gap = compact and 10 or 16, children = {
        Skin.Button {id="editTouchControls",text="自定义按键布局",height=48,width="100%",visible=host~=nil and Mobile.IsTouch(),
            onClick=function()
                self:Activate("resume")
                require("Core.EventBus").Emit("controls:edit")
            end},
        label("音频", 15), self:VolumeRow("master", "主音量"), self:VolumeRow("music", "音乐音量"),
        self:VolumeRow("effects", "音效音量"), self:VolumeRow("ambient", "环境音量"),
        self:VolumeRow("voice", "语音音量"), UI.Divider { color = COLOR.border },
        label("显示", 15), self.resolutionLabel,
        UI.Label { text = "分辨率随游戏窗口调整", width = "100%", fontSize = 10,
            textAlign = "center", fontColor = COLOR.muted },
        label("界面缩放", 11), scale, label("帧率上限", 11), fps,
        Skin.Toggle { id = "menuMotion", width = "100%", height = 38, label = "开始界面动态背景",
            value = self.settings.values.menuMotion, onChange = function(_, value)
                self.settings.values.menuMotion = value; self:SaveSettings(); self.onClickSound()
            end }, UI.Divider { color = COLOR.border },
        UI.Label {text=Mobile.IsTouch() and Mobile.Text.menuTutorialNote or "每局开场包含引导，长按 Esc 可跳过当前教程。",width="100%",fontSize=10,fontColor=COLOR.muted}, self.statusLabel,
    } }
    -- [UI_BUTTON:resetSettings] 设定恢复默认。
    local reset = button("恢复默认", function() self:Activate("resetSettings") end)
    reset.id,reset.props.id = "resetSettings","resetSettings"
    -- [UI_BUTTON:settingsBack] 主菜单设定返回；游戏内设定原地继续。
    local back = button(host and "继续游戏" or "返回", function() self:Activate(host and "resume" or "menu") end, false, "secondary", "back")
    back.id,back.props.id = "settingsBack","settingsBack"
    reset:SetStyle { flexGrow = 1, flexBasis = 0, flexShrink = 1, width = "auto", fontSize = 12 }
    back:SetStyle { flexGrow = 1, flexBasis = 0, flexShrink = 1, width = "auto", fontSize = 12 }
    local actions={reset,back}
    if host then
        local main=button("主菜单",function() self:Activate("menu") end,false,"secondary","back")
        main.id,main.props.id="pauseMenu","pauseMenu"
        main:SetStyle {flexGrow=1,flexBasis=0,flexShrink=1,width="auto",fontSize=12}
        table.insert(actions,2,main)
    end
    local children={UI.SafeAreaView { id = "menuForeground",
            width = "100%", height = "100%", nativeMenuInset = true,
            alignItems = "center", justifyContent = "center", padding = compact and 8 or 16, children = {
                Skin.Frame { id="settingsFrame", frameKind="dialog", width = compact and "98%" or "94%", maxWidth = compact and 820 or 600, height = compact and "98%" or "92%", maxHeight = 760,
                    backgroundColor = COLOR.surface, borderRadius = 10, borderWidth = 1,
                    borderColor = COLOR.border, overflow = "hidden", children = {
                        UI.Panel { id="settingsHeader",width = "100%", height = compact and 52 or 92, flexShrink=0,justifyContent = "center", gap=4,
                            children = { label(host and "已暂停 · 设定" or "设定", compact and 22 or 28), Skin.Ornament {height=24,visible=not compact} } },
                        Skin.Scroll { id = "settingsScroll", width = "100%", flexGrow = 1,
                            flexBasis = 0, children = { content } },
                        UI.Panel { id="settingsActions",width = "100%", padding = compact and 8 or 16, gap = compact and 8 or 12, flexShrink=0,flexDirection = "row",
                            children = actions },
                    } },
            } }}
    if not host then table.insert(children,1,self:Background()) end
    local root=UI.Panel {id=host and "pauseOverlay" or "settingsScreen",width="100%",height="100%",
        position=host and "absolute" or "relative",left=0,top=0,zIndex=host and 20000 or 0,
        backgroundColor={8,5,15,host and 185 or 255},pointerEvents="auto",children=children}
    if host then
        UI.ClearFocus()
        self.pauseRoot,self.screen=root,"settings"
        host:AddChild(root)
    else self:Mount(root,"settings") end
    self:UpdateResolution()
    if compact then for _,action in ipairs(actions) do action:SetStyle{height=44} end end
end

function Menu:UpdateResolution()
    if self.resolutionLabel then
        self.resolutionLabel:SetText(string.format("当前分辨率  %d × %d", graphics:GetWidth(), graphics:GetHeight()))
    end
end

function Menu:ShowCredits()
    self.creditsTime = 0
    local lines = { label("病毒涌现", 36), Skin.Ornament {height=36}, label("制作名单", 20), UI.Panel { height = 64 } }
    for _, group in ipairs(Credits.groups) do
        local role = label(group.role, 15)
        role:SetStyle { fontColor = { 146, 146, 146, 255 }, marginBottom = 8 }
        lines[#lines + 1] = role
        for _, name in ipairs(group.names) do lines[#lines + 1] = label(name, 22) end
        lines[#lines + 1] = UI.Panel { height = 56, pointerEvents = "none" }
    end
    local closing=label(Credits.closingMessage or "感谢游玩",14)
    closing:SetStyle {maxWidth=640,alignSelf="center",minWidth=0,fontColor={150,150,150,255},
        whiteSpace="normal",wordBreak="break-word",lineHeight=1.6,flexShrink=0}
    -- Keep the Label's wrapping and measurement; only incline its rendered text.
    local renderClosing=closing.Render
    closing.Render=function(_,nvg)
        local layout=closing:GetAbsoluteLayout()
        local centerY=layout.y+layout.h/2
        nvgSave(nvg)
        nvgTranslate(nvg,0,centerY)
        nvgSkewX(nvg,-0.16)
        nvgTranslate(nvg,0,-centerY)
        renderClosing(closing,nvg)
        nvgRestore(nvg)
    end
    lines[#lines + 1] = closing
    local skip=CreditsSkip.New()
    self.creditsContent = UI.Panel { id = "creditsRoll", position = "absolute", top = "100%",
        width = "100%", paddingHorizontal = 20, gap = 12, pointerEvents = "none", children = lines }
    self:Mount(UI.Panel { id = "creditsScreen", width = "100%", height = "100%",
        backgroundColor = { 0, 0, 0, 255 }, overflow = "hidden", pointerEvents = "auto",
        children = { self.creditsContent,skip.root, UI.SafeAreaView {
            position = "absolute", left = 0, bottom = 0, width = "100%", pointerEvents = "none",
            children = { UI.Panel { width = "100%", padding = 14, backgroundColor = { 0, 0, 0, 235 },
                pointerEvents = "none", children = { label(Mobile.IsTouch() and "长按右上角按钮跳过制作名单" or "长按 Esc 跳过制作名单", 10) } } },
        } },
    }, "credits")
    self.creditsSkip_=skip
end

---@param key integer
function Menu:HandleKey(key)
    if self.screen == "credits" then
        if self.creditsSkip_ then self.creditsSkip_:HandleKey(key) end
        return
    end
    if self.screen == "settings" then
        if key == KEY_ESCAPE then self:Activate("menu") end
        return
    end
    if key == KEY_ESCAPE and self.hasRun then self:Activate("story"); return end
    if key == KEY_UP or key == KEY_DOWN then
        self.onClickSound()
        self.selected = (self.selected - 1 + (key == KEY_UP and -1 or 1)) % #self.buttons + 1
        for i, item in ipairs(self.buttons) do
            item:SetStyle { borderColor = i == self.selected and COLOR.warm or COLOR.border,
                borderWidth = i == self.selected and 2 or (i == 1 and 0 or 1) }
        end
    elseif key == KEY_RETURN or key == KEY_SPACE then
        local action = ({ "story", "settings", "credits", "exit" })[self.selected]
        self:Activate(action)
    end
end

---@param dt number
function Menu:Update(dt)
    self:ApplyMobileLayout()
    if not self.prepared then
        self.preparationTime_=self.preparationTime_+math.max(0,math.min(dt,.1))
        local status=self.root and self.root:FindById("menuPreparation") --[[@as Label?]]
        if status then status:SetText(string.format("%s %d%%%s",self.preparationMessage_,
            math.floor(self.preparationProgress_*100),string.rep("·",math.floor(self.preparationTime_*3)%4))) end
    end
    if self.screen == "credits" and self.creditsContent then
        if self.creditsSkip_ and self.creditsSkip_:Update(dt) then self:Activate("menu");return end
        self.creditsTime = self.creditsTime + dt
        local top = UI.GetHeight() - self.creditsTime * 57
        self.creditsContent:SetStyle { top = top }
        local height = self.creditsContent:GetLayout().h
        if height > 0 and top + height < -60 then self.onAction("menu") end
    elseif self.screen == "settings" then
        self.resolutionTime = self.resolutionTime + dt
        if self.resolutionTime > 0.5 then self.resolutionTime = 0; self:UpdateResolution() end
    end
end

return Menu

