-- ============================================================================
-- main.lua - 主菜单后台预加载 → 开场镜头 → 病毒控制／暂停设定浮层
--
-- 基于 scaffold-2d.lua：初始化 UI → 组装游戏 → 事件循环 → 释放资源。
-- GameScene 统一驱动 SimState / SwarmWorld，HUD 和两个视图只读真实实体状态。
-- Core.Config 保存可调数值，组织分区保留在后台，不再提供组织层入口。
-- ============================================================================

local UI = require("urhox-libs/UI")
local Config = require("Core.Config")
local SimState = require("Core.SimState")
local ScaleManager = require("Core.ScaleManager")
local GameScene = require("Game.GameScene")
local HUD = require("UI.HUD")
local CardMetrics = require("Core.CardMetrics")
local SkillControls = require("UI.SkillControls")
local UserSettings = require("Core.UserSettings")
local MainMenu = require("UI.MainMenu")
local GameAudio = require("Core.GameAudio")
local Tutorial = require("Core.Tutorial")
local TutorialOverlay = require("UI.TutorialOverlay")
local AssetTheme = require("UI.AssetTheme")
local LoadJob = require("Core.LoadJob")
local EntryShot = require("UI.EntryShot")
local PreparationOverlay = require("UI.PreparationOverlay")

---@type GameAudio?
local gameAudio_ = nil

---@type UserSettings?
local settings_ = nil
---@type MainMenu?
local menu_ = nil
---@type string?
local pendingAction_ = nil
local screen_ = "menu"

local function QueueMenuAction(action)
    -- 下一帧切根，避免在指针事件派发中销毁当前控件树。
    if not pendingAction_ then pendingAction_ = action end
end

---@type SimState?
local sim_ = nil
---@type ScaleManager?
local scaleMgr_ = nil
---@type HUD?
local hud_ = nil
---@type Widget?
local uiRoot_ = nil
---@type TutorialOverlay?
local tutorialOverlay_ = nil
---@type Widget?
local entryFade_ = nil
---@type string?
local entryPhase_ = nil
local entryTime_ = 0
local entryPrepared_ = false
---@type LoadJob?
local entryJob_ = nil
---@type PreparationOverlay?
local entryLoading_ = nil
---@type string?
local preloadPhase_ = nil
local worldReady_, runEntered_ = false, false
local escapeConsumed_=false
local preparationProgress_=0
local preparationMessage_="正在准备组织…"

local function SetPreparationProgress(progress,message)
    preparationProgress_,preparationMessage_=math.max(preparationProgress_,progress),message
    if menu_ then menu_:SetPreparationProgress(preparationProgress_,message) end
end

local function BeginPreparation()
    worldReady_, preloadPhase_ = false, "prepare"
    preparationProgress_=0
    SetPreparationProgress(0,"正在准备组织…")
    if menu_ then menu_:SetPreparationReady(false) end
    entryJob_=LoadJob.New(function()
        if sim_ and sim_.ending then RestartRun() else BuildGame(true) end
        if sim_ then sim_:SetPaused("mainMenu",true) end
        LoadJob.Checkpoint()
        if gameAudio_ then gameAudio_:PrepareEntryMusic(true) end
        LoadJob.Report(.86,"正在预热组织画面…")
    end)
end

local function DetachWarmup()
    if uiRoot_ and uiRoot_.parent then uiRoot_.parent:RemoveChild(uiRoot_) end
    local shield=menu_ and menu_.root and menu_.root:FindById("entryWarmShield")
    if shield then shield:Destroy() end
    if preloadPhase_=="warm" then preloadPhase_="mount" end
end

local function ApplyGameEntryPose(zoom,opacity,active)
    local scene=uiRoot_ and uiRoot_:FindById("gameScene") --[[@as GameScene?]]
    if scene then scene:SetEntryPose(zoom,active) end
    if hud_ and hud_.root then hud_.root:SetStyle {opacity=opacity} end
end

local function ClearEntryFade()
    -- Warmup temporarily parents the game below the menu. Detach before menu disposal.
    if uiRoot_ and uiRoot_.parent then uiRoot_.parent:RemoveChild(uiRoot_) end
    if uiRoot_ then uiRoot_:SetStyle {position="relative",zIndex=0,pointerEvents="box-none"} end
    ApplyGameEntryPose(1,1,false)
    if entryFade_ then entryFade_:Destroy(); entryFade_ = nil end
    if entryLoading_ then entryLoading_:Destroy(); entryLoading_ = nil end
    entryPrepared_ = false
    entryJob_ = nil
    entryPhase_, entryTime_ = nil, 0
end

local function BeginEntryFade()
    if entryPhase_ then return end
    local root = UI.GetRoot()
    if not root then return end
    UI.ClearFocus()
    if menu_ then menu_:BeginEntry() end
    entryPrepared_ = worldReady_ and not (sim_ and sim_.ending)
    if gameAudio_ then
        gameAudio_:PrepareTutorial()
        -- Reuse the cached map if real voice preparation still needs to settle.
        if entryPrepared_ and not gameAudio_:IsEntryAudioReady(0) then
            entryPrepared_,worldReady_,preloadPhase_=false,false,"mount"
            preparationProgress_=.88
            SetPreparationProgress(.88,"正在准备场景音频…")
            if menu_ then menu_:SetPreparationReady(false) end
        end
    end
    -- 先显示准备提示并停止音频，再分帧准备世界，完成后启动镜头。
    -- Web 主线程繁忙时不让旧音频缓冲持续发出短促重复声。
    if gameAudio_ then gameAudio_:SetMode("loading") end
    entryFade_ = UI.Panel {
        id = "entryFade", position = "absolute", top = 0, left = 0,
        width = "100%", height = "100%", zIndex = 10000,
        backgroundColor = { 0, 0, 0, 255 }, opacity = 0,
        pointerEvents = "auto",
    }
    root:AddChild(entryFade_)
    if not entryPrepared_ then
        entryLoading_=PreparationOverlay.New()
        entryLoading_:Update(0,preparationProgress_,preparationMessage_)
        root:AddChild(entryLoading_.root)
    end
    entryPhase_, entryTime_ = entryPrepared_ and "out" or "wait", 0
    if not entryPrepared_ and not preloadPhase_ then BeginPreparation() end
    if sim_ then sim_:SetPaused("entryFade",true) end
end

function Start()
    graphics.windowTitle = Config.Title
    engine:SetAutoExit(false) -- Esc 用于暂停设定/返回，不由引擎直接退出。
    input.mouseMode = MM_ABSOLUTE
    UI.Init({
        theme = "default-dark",
        fonts = {
            { family = "sans", weights = { normal = "Fonts/MiSans-Regular.ttf" } },
        },
        scale = UI.Scale.DEFAULT,
    })
    AssetTheme.ApplyColors()
    settings_ = UserSettings.New()
    settings_:Apply()
    gameAudio_ = GameAudio.New()
    menu_ = MainMenu.New(settings_, QueueMenuAction, function()
        if gameAudio_ then gameAudio_:PlayClick() end
    end)
    menu_:Show(false)
    screen_, pendingAction_ = "menu", nil
    -- Web mixes audio on the same busy startup path. Keep it silent until the
    -- world and first renders are warm, rather than repeating an underrun buffer.
    gameAudio_:SetMode("loading")
    gameAudio_:PrepareMenuMusic()
    runEntered_=false
    escapeConsumed_=false
    BeginPreparation()
    SubscribeToEvent("KeyDown", "HandleKeyDown")
    SubscribeToEvent("Update", "HandleUpdate")
    SubscribeToEvent("ExitRequested", "HandleExitRequested")
    print("=== Game Started: " .. Config.Title .. " ===")
    print("[main] WASD / 方向键 / 手机摇杆 | E基础吸附(3秒冷却) | Shift冲刺 | F诱饵 | V功能菜单、1—6选择 | 空格分离 | Tab切群")
end

-- 关闭窗口仍然退出；显式接管 ExitRequested 与菜单键盘处理分开。
function HandleExitRequested()
    pendingAction_ = "exit"
end

function Stop()
    if sim_ and sim_.tutorial then sim_.tutorial:Stop(false) end
    tutorialOverlay_ = nil
    ClearEntryFade()
    preloadPhase_,worldReady_,runEntered_=nil,false,false
    if settings_ then settings_:Save() end
    if menu_ then menu_:DestroyRoot(); menu_ = nil end
    if hud_ then hud_:Destroy(); hud_ = nil end
    -- 游戏树在菜单期间脱离 UI 根，仍需显式释放。
    if uiRoot_ and UI.GetRoot() ~= uiRoot_ then uiRoot_:Destroy() end
    UI.Shutdown()
    settings_, pendingAction_ = nil, nil
    sim_, scaleMgr_, uiRoot_ = nil, nil, nil
    if gameAudio_ then gameAudio_:Destroy(); gameAudio_ = nil end
end

local function ApplyMenuAction(action)
    if not menu_ or not settings_ then return end
    if entryPhase_ and action ~= "exit" then return end
    local scene=uiRoot_ and uiRoot_:FindById("gameScene") --[[@as GameScene?]]
    if scene and scene:IsMapActive() then scene:CancelMap() end
    if action == "story" then
        BeginEntryFade()
    elseif action == "exit" then
        settings_:Save()
        engine:Exit()
    elseif action == "resume" and screen_=="pause" then
        settings_:Save()
        menu_:DestroyPause()
        screen_="game"
        if sim_ then
            sim_:SetPaused("settings",false)
        end
    elseif (screen_=="game" or screen_=="pause") and
        (action=="settings" or action=="resetSettings") then
        if hud_ then hud_:ClearTouchMove() end
        if sim_ then sim_:SetPaused("settings",true) end
        if action=="resetSettings" then settings_:Reset() end
        screen_="pause"
        menu_:ShowSettings(uiRoot_)
    else
        menu_:DestroyPause()
        DetachWarmup()
        screen_ = "menu"
        if gameAudio_ then gameAudio_:SetMode(preloadPhase_ and "loading" or "menu") end
        if hud_ then hud_:ClearTouchMove() end
        if sim_ then sim_:SetPaused("mainMenu", true);sim_:SetPaused("settings",false) end
        if action == "settings" then menu_:ShowSettings()
        elseif action == "credits" then menu_:ShowCredits()
        elseif action == "resetSettings" then settings_:Reset(); menu_:ShowSettings()
        else settings_:Save(); menu_:Show(runEntered_ and sim_ ~= nil and not sim_.ending) end
    end
end

function BuildGame(detached)
    screen_ = detached and "menu" or "game"
    if sim_ then
        RestartRun()
        return
    end
    sim_ = SimState.New()
    scaleMgr_ = ScaleManager.New()
    scaleMgr_:JumpTo("cell", true)
    sim_:StartRun("UPPER_AIRWAY",true)
    if gameAudio_ then gameAudio_:BindSim(sim_) end
    sim_.tutorial = Tutorial.New(sim_)
    sim_:SetPaused("entryFade", entryPhase_ ~= nil)
    sim_:SetPaused("mainMenu",detached==true)
    hud_ = HUD.New({ sim = sim_, scaleMgr = scaleMgr_, onRestart = RestartRun,
        onMenu = function() QueueMenuAction(sim_ and sim_.ending and "menu" or "settings") end,
        onCredits = function() QueueMenuAction("credits") end,
        onMap = function()
            local scene=uiRoot_ and uiRoot_:FindById("gameScene") --[[@as GameScene?]]
            if scene then scene:ToggleMap() end
        end,
        videoVolume = function() return settings_ and settings_.values.master/100*settings_.values.music/100 or 1 end,
        onEndingMix = function(progress)
            if gameAudio_ then gameAudio_:SetEndingMix(progress) end
        end,
        onEndingPose = function(zoom, covered, progress)
            local scene = uiRoot_ and uiRoot_:FindById("gameScene") --[[@as GameScene?]]
            if scene then scene:SetEndingPose(zoom, covered, progress) end
        end,
        onCardChoiceShown = function()
            if gameAudio_ then return gameAudio_:PlayCardChoice() end
        end })
    local gameScene = GameScene {
        id = "gameScene", width = "100%", height = "100%",
        sim = sim_, scaleMgr = scaleMgr_,
    }
    tutorialOverlay_ = TutorialOverlay.New(sim_, gameScene)
    uiRoot_ = UI.Panel {
        id = "uiRoot", width = "100%", height = "100%",
        backgroundColor = { 0, 0, 0, 255 },
        children = { gameScene, hud_:Build(), tutorialOverlay_.root },
    }
    LoadJob.Report(.80,"正在准备场景音频…")
    if not detached then UI.SetRoot(uiRoot_) end
    hud_:RefreshStrategyHighlight()
end

function RestartRun()
    if not sim_ or not scaleMgr_ or not hud_ then return end
    print("[main] 直接重开病毒控制场景")
    if sim_.tutorial then sim_.tutorial:Stop(false) end
    sim_:init()
    scaleMgr_:init()
    scaleMgr_:JumpTo("cell", true)
    sim_:StartRun("UPPER_AIRWAY",true)
    if gameAudio_ then gameAudio_:BindSim(sim_) end
    sim_.tutorial = Tutorial.New(sim_)
    escapeConsumed_=false
    if not entryPhase_ and sim_.tutorial then sim_.tutorial:StartIfNeeded() end
    hud_:RefreshStrategyHighlight()
end

local function UpdatePreparation(dt)
    if preloadPhase_ == "prepare" then
        -- Keep the menu breathing while bounded pure-Lua generation yields each frame.
        -- No camera/audio timeline starts until all startup work has completed.
        if entryJob_ then
            entryJob_:Step()
            if entryJob_.error then error("Entry preparation failed: "..entryJob_.error) end
            SetPreparationProgress(entryJob_.progress,entryJob_.message)
            if entryJob_.done then
                entryJob_=nil
                preloadPhase_="mount"
            end
        end
        return
    elseif preloadPhase_ == "mount" then
        assert(uiRoot_ and menu_ and menu_.root,"Entry world was not prepared")
        local scene=assert(uiRoot_:FindById("gameScene")) --[[@as GameScene]]
        if scaleMgr_ then scaleMgr_:JumpTo("cell",true) end
        if hud_ then hud_:RefreshScale();hud_:RefreshStrategyHighlight() end
        local zoom=EntryShot.Arrival(0,settings_ ~= nil and settings_.values.menuMotion)
        scene:SetEntryPose(zoom,true)
        scene:BeginEntryWarmup()
        -- Must remain visible: opacity=0/visibility=hidden would skip real rendering.
        uiRoot_:SetStyle {position="absolute",left=0,top=0,zIndex=-2,pointerEvents="none"}
        menu_.root:InsertChild(uiRoot_,1)
        menu_.root:InsertChild(UI.Panel {id="entryWarmShield",position="absolute",
            left=0,top=0,width="100%",height="100%",zIndex=-1,
            backgroundColor={8,5,15,255},pointerEvents="none"},2)
        preloadPhase_="warm"
        SetPreparationProgress(.88,"正在预热组织画面…")
    elseif preloadPhase_ == "warm" then
        -- Resolve responsive HUD geometry after the detached tree's first layout.
        -- Zero elapsed time keeps tutorials, notices and simulation frozen.
        if hud_ then hud_:Update(0) end
        local scene=uiRoot_ and uiRoot_:FindById("gameScene") --[[@as GameScene?]]
        local audioReady=not gameAudio_ or gameAudio_:IsEntryAudioReady(dt)
        SetPreparationProgress(scene and scene:IsEntryReady() and .97 or .92,
            scene and scene:IsEntryReady() and "正在准备场景音频…" or "正在预热组织画面…")
        if scene and scene:IsEntryReady() and audioReady then
            -- Retain the warmed tree without drawing it underneath the fast menu shot.
            DetachWarmup()
            preloadPhase_,worldReady_=nil,true
            SetPreparationProgress(1,"组织场景已就绪")
            if menu_ then menu_:SetPreparationReady(true) end
            -- An early Start click proceeds directly to the entry shot; menu
            -- navigation during preparation must never restart background music.
            if not entryPhase_ and gameAudio_ then gameAudio_:SetMode("menu") end
        end
    end
end

---@param dt number
local function UpdateEntryFade(dt)
    if not entryFade_ then return end
    local previousTime = entryTime_
    entryTime_ = entryTime_ + math.max(0, math.min(dt, 0.1))
    if entryPhase_=="wait" then
        UpdatePreparation(dt)
        if entryLoading_ then entryLoading_:Update(dt,preparationProgress_,preparationMessage_) end
        if worldReady_ then
            if entryLoading_ then entryLoading_:Destroy();entryLoading_=nil end
            entryPhase_,entryTime_="out",0
        end
        return
    elseif entryPhase_ == "out" then
        if previousTime < EntryShot.soundAt and entryTime_ >= EntryShot.soundAt and gameAudio_ then
            gameAudio_:PlayEntryWhoosh()
        end
        local foreground, zoom, black = EntryShot.Pose(entryTime_,
            settings_ ~= nil and settings_.values.menuMotion)
        if menu_ then menu_:SetEntryPose(foreground, zoom) end
        entryFade_:SetStyle { opacity = black }
        -- Covered frame handoff only; construction and first rendering are already complete.
        if entryTime_ >= EntryShot.duration then entryPhase_, entryTime_ = "switch", 0 end
    elseif entryPhase_ == "switch" then
        if entryFade_.parent then entryFade_.parent:RemoveChild(entryFade_) end
        assert(uiRoot_,"Entry world missing after warmup")
        if uiRoot_.parent then uiRoot_.parent:RemoveChild(uiRoot_) end
        uiRoot_:SetStyle {position="relative",zIndex=0,pointerEvents="box-none"}
        menu_:DestroyRoot()
        UI.SetRoot(uiRoot_)
        if uiRoot_ then uiRoot_:AddChild(entryFade_) end
        screen_ = "game"
        runEntered_=true
        if sim_ then
            sim_:SetPaused("entryFade", true)
            sim_:SetPaused("mainMenu", false)
        end
        -- Scale and HUD were already prepared and rendered before the shot.
        if gameAudio_ then gameAudio_:SetMode("game") end
        local zoom,opacity=EntryShot.Arrival(0,settings_ ~= nil and settings_.values.menuMotion)
        ApplyGameEntryPose(zoom,opacity,true)
        entryPhase_, entryTime_ = "hold", 0
    elseif entryPhase_ == "hold" then
        if entryTime_ >= EntryShot.hold then entryPhase_, entryTime_ = "in", 0 end
    else
        local zoom,opacity,black=EntryShot.Arrival(entryTime_,
            settings_ ~= nil and settings_.values.menuMotion)
        ApplyGameEntryPose(zoom,opacity,true)
        entryFade_:SetStyle {opacity=black}
        local t = math.min(1, entryTime_ / EntryShot.reveal)
        if t >= 1 then
            ClearEntryFade()
            if sim_ then
                sim_:SetPaused("entryFade", false)
                if sim_.tutorial then sim_.tutorial:StartIfNeeded() end
            end
            print("[main] 黑屏转场完成，进入病毒控制场景")
        end
    end
end

---@param eventType string
---@param eventData KeyDownEventData
function HandleKeyDown(eventType, eventData)
    if eventData:GetBool("Repeat") then return end
    if input and (input.focus == false or input.minimized == true) then return end
    local key = eventData:GetInt("Key")
    if hud_ and hud_.touchControls_ and hud_.touchControls_.editor then
        if key==KEY_ESCAPE then hud_.touchControls_:Finish(false) end
        return
    end
    if entryPhase_ then return end
    if screen_=="pause" then
        if key==KEY_ESCAPE then QueueMenuAction("resume") end
        return
    end
    if screen_ ~= "game" then
        if menu_ then menu_:HandleKey(key) end
        return
    end
    if hud_ and hud_.endingScreen and hud_.endingScreen:HandleKey(key) then return end
    local scene=uiRoot_ and uiRoot_:FindById("gameScene") --[[@as GameScene?]]
    if scene and scene:IsMapActive() then
        if key==KEY_M then scene:ToggleMap()
        elseif key==KEY_ESCAPE then scene:CloseMap() end
        return
    end
    if key==KEY_M then
        if scene and scene:ToggleMap() and hud_ then hud_:ClearTouchMove() end
        return
    end
    if key == KEY_ESCAPE then
        if escapeConsumed_ then return end
        if sim_ and sim_.tutorial and sim_.tutorial.active then
            escapeConsumed_=true
            return -- Short taps do nothing during teaching; hold is polled each frame.
        end
        -- 技能选择先由原有操作取消；没有技能弹层时才打开暂停设定。
        if hud_ and sim_ and (sim_.skillSelection or sim_.skillMenu) then
            SkillControls.HandleKey(hud_, key, false)
        elseif hud_ and hud_:CloseDrawers() then
            return
        else QueueMenuAction("settings") end
        return
    end
    if not sim_ then return end
    local tutorial = sim_.tutorial
    if tutorial and tutorial.active and tutorial.lesson.pause then
        if key == KEY_RETURN or key == KEY_SPACE then tutorial:Continue() end
        return
    end
    if hud_ and hud_.cardInfoShown_ then return end
    if hud_ and SkillControls.HandleKey(hud_,key,false) then return end
    if key == KEY_E and not eventData:GetBool("Repeat") and hud_ then
        hud_:AbsorbNearby()
    elseif key == KEY_SPACE and not eventData:GetBool("Repeat") and hud_ then
        hud_:Split()
    elseif key == KEY_TAB and not eventData:GetBool("Repeat") and hud_ then
        hud_:SwitchControl()
    end
end

-- GameScene:Update 已由 UI autoEvents 调用；此处只节流刷新 HUD，不重复推进模拟。
---@param eventType string
---@param eventData UpdateEventData
function HandleUpdate(eventType, eventData)
    if pendingAction_ then
        local action = pendingAction_
        pendingAction_ = nil
        ApplyMenuAction(action)
    end
    local dt=eventData:GetFloat("TimeStep")
    local escapeHeld=input and input.GetKeyDown and input:GetKeyDown(KEY_ESCAPE) or false
    if not escapeHeld then escapeConsumed_=false end
    if entryPhase_ then
        UpdateEntryFade(eventData:GetFloat("TimeStep"))
        if screen_ == "game" and hud_ then hud_:Update(eventData:GetFloat("TimeStep")) end
        if screen_=="game" and tutorialOverlay_ then tutorialOverlay_:Update() end
        if gameAudio_ then gameAudio_:Update(dt,sim_) end
        return
    end
    if sim_ then sim_:TrackExperience(dt) end
    if screen_ ~= "game" then
        if sim_ and sim_.tutorial then sim_.tutorial:UpdateSkip(0,false) end
        if preloadPhase_ and screen_=="menu" then UpdatePreparation(dt) end
        if menu_ then menu_:Update(eventData:GetFloat("TimeStep")) end
        if gameAudio_ then gameAudio_:Update(dt,sim_) end
        return
    end
    if sim_ and sim_.tutorial then
        local focused=not input or (input.focus~=false and input.minimized~=true)
        local touchHeld=tutorialOverlay_ and tutorialOverlay_.touchSkipHeld or false
        local held=focused and ((escapeHeld and escapeConsumed_) or touchHeld) or false
        sim_.tutorial:UpdateSkip(dt,held)
        sim_.tutorial:Update(dt)
    end
    if tutorialOverlay_ then tutorialOverlay_:Update() end
    if hud_ then hud_:Update(eventData:GetFloat("TimeStep")) end
    if sim_ then CardMetrics.Update(sim_,eventData:GetFloat("TimeStep")) end
    -- Apply this frame's lesson/text before selecting its narration; never tick the sim here.
    if gameAudio_ then gameAudio_:Update(dt,sim_) end
end
