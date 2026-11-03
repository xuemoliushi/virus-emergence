-- 新玩法真实入口离屏验证。由引擎 validate-test 注入 V，不是游戏脚本。
-- 覆盖小鼠外观→解剖→点肺→动画稳定→选区→开始的真实UI回调、
-- 键盘 handler、重复事件、切群、观察暂停、独立视觉时间、R重开和布局。
-- UI回调验证不等于物理pointer投递；实际解剖叠肺画面仍由父任务截图验收。
-- 不修改 Core 配置，不伪造免疫模块，不声称已验证完整10～15分钟平衡。
-- surfaceless 环境可能无焦点：先记录并验证真实失焦暂停，再仅对同步操作段
-- 移除测试环境focus reason；不改input.focus，不绕过观察/transition/其他暂停。
-- 因此handler动作段不能证明真实窗口焦点获取或物理触摸事件投递。
local UI = require("urhox-libs/UI")
local Config = require("Core.Config")
local PlatformUtils = require("urhox-libs.Platform.PlatformUtils")

---@type GameScene?
local scene = nil
local diseaseStartTime, diseaseStartTick, diseaseNodeId = 0, 0, 0
local diseaseSegments = 0

---@param id string
---@return Widget
local function widget(id)
    local root = assert(UI.GetRoot(), "真实入口未建立UI根")
    return assert(root:FindById(id), "缺少UI控件：" .. id)
end

---@param id string
local function click(id)
    local button = widget(id)
    local onClick = assert(button.props.onClick, "控件缺少真实onClick：" .. id)
    onClick(button)
end

---@param key integer
---@param repeatKey? boolean
local function keyDown(key, repeatKey)
    HandleKeyDown("KeyDown", {
        GetInt = function() return key end,
        GetBool = function() return repeatKey or false end,
    })
end

---@param sim SimState
---@param label string
---@return boolean unfocused
local function logPause(sim, label)
    local reasons = {}
    for reason in pairs(sim.pauseReasons) do reasons[#reasons + 1] = reason end
    table.sort(reasons)
    local focus = input and tostring(input.focus) or "no-input"
    local minimized = input and tostring(input.minimized) or "no-input"
    local unfocused = input ~= nil and (input.focus == false or input.minimized == true)
    print(string.format("[redesign_validation] %s focus=%s minimized=%s paused=%s reasons={%s}",
        label, focus, minimized, tostring(sim.paused), table.concat(reasons, ",")))
    return unfocused
end

---@param game GameScene
---@param label string
---@return boolean unfocused
local function verifyFocusPause(game, label)
    game:Update(0)
    local sim = game.sim
    local unfocused = logPause(sim, label)
    V.assert((sim.pauseReasons.focus == true) == unfocused,
        label .. "：GameScene按实际窗口状态保留失焦暂停")
    if unfocused then
        V.assert(sim.paused, label .. "：失焦时不能自行恢复病程")
    end
    return unfocused
end

---@param game GameScene
---@param label string
local function isolateSurfacelessFocus(game, label)
    local sim = game.sim
    local unfocused = logPause(sim, label .. "隔离前")
    if unfocused then
        V.assert(sim.pauseReasons.focus == true, label .. "：先证明focus暂停来源于真实离屏失焦")
        sim:SetPaused("focus", false)
        print("[redesign_validation] 仅此同步测试段清离屏focus reason；真实GameScene下一Update仍会重设失焦暂停")
    end
    logPause(sim, label .. "隔离后")
    V.assert(sim:CanAct(), label .. "：无观察/过渡/其他暂停残留时才允许handler动作")
end

---@param sim SimState
---@return string
local function diseaseFingerprint(sim)
    local fields = { tostring(sim.time), tostring(sim.world.time), tostring(sim.tickCount),
        tostring(sim.tickAccum), tostring(sim.world.diseaseAccum), tostring(sim.respirationLowSeconds),
        tostring(sim.globalInflammation), tostring(sim.globalTissueDamage), tostring(sim.ending) }
    for _, cell in ipairs(sim.world.cells) do
        fields[#fields + 1] = table.concat({ cell.id, cell.state, cell.exposure, cell.latencyTimer,
            cell.productiveTimer, cell.releaseCount, cell.exhaustionTimer, cell.immuneHits }, ",")
    end
    for _, swarm in ipairs(sim.world.swarms) do
        fields[#fields + 1] = table.concat({ swarm.id, swarm.mass, swarm.x, swarm.y, swarm.vx, swarm.vy }, ",")
    end
    for _, virus in ipairs(sim.world.releasedViruses) do
        fields[#fields + 1] = table.concat({ virus.id, virus.state, virus.x, virus.y, virus.age }, ",")
    end
    for _, immune in ipairs(sim.world.immunes) do
        fields[#fields + 1] = table.concat({ immune.id, immune.state, immune.x, immune.y,
            immune.warningTimer, immune.attackTimer, immune.cooldown }, ",")
    end
    local statNames = {}
    for name in pairs(sim.stats) do statNames[#statNames + 1] = name end
    table.sort(statNames)
    for _, name in ipairs(statNames) do fields[#fields + 1] = name .. "=" .. tostring(sim.stats[name]) end
    return table.concat(fields, ";")
end

---@param world SwarmWorld
local function conservation(world)
    local c, s = world:Counts(), world.stats
    V.assert(s.initialMass + s.totalReleased - s.totalKilled - s.totalLost - s.splitCost == c.virus,
        "真实实体守恒含分裂成本；吸收只转移不重复加出生")
    V.assert(#world.viruses == c.controlled and c.virus == c.controlled + c.released,
        "群particle实体数等于mass，Released独立记账")
    V.assert(c.groups <= 2, "同时最多两个群")
end

---@param dt number
local function refreshHUD(dt)
    HandleUpdate("Update", { GetFloat = function() return dt end })
end

---@param game GameScene
local function settleObservation(game)
    -- ObservationState会夹紧dt；逐帧推进真实动画，不能赋值lungProgress冒充稳定。
    for _ = 1, 180 do
        if not game.observation:IsTransitioning() then break end
        game.observation:Update(1 / 60)
        refreshHUD(1 / 60)
    end
    V.assert(not game.observation:IsTransitioning(), "肺部进退动画经逐帧Update确实稳定")
    refreshHUD(0.2)
end

---@param game GameScene
local function settleScale(game)
    -- 跨层也逐帧调用真实ScaleManager；不JumpTo/写transition绕过UI发起的过渡。
    for _ = 1, 240 do
        if not game.scaleMgr:IsTransitioning() then break end
        game.scaleMgr:Update(1 / 60)
        game.observation:Update(1 / 60)
        refreshHUD(1 / 60)
    end
    V.assert(not game.scaleMgr:IsTransitioning(), "UI发起的跨层镜头经逐帧Update确实稳定")
    game:Update(0) -- 同步真实暂停原因；仍保留surfaceless失焦，不推进病程。
    refreshHUD(0.2)
end

---@param game GameScene
---@param label string
local function rejectStartBypass(game, label)
    local sim, observation, previous = game.sim, game.observation, game.sim.world
    local t, mode = sim.time, observation.mode
    for _, def in ipairs(Config.StartRegions) do click("start_" .. def.type) end
    click("startRunBtn") -- 刻意直调禁用/隐藏控件回调，验证业务防线而非仅disabled样式。
    V.assert(not sim.started and sim.world == previous and sim.time == t,
        label .. "：真实onClick不能越过解剖/点肺/动画稳定启动")
    V.assert(observation.mode == mode and observation.selectedStartType == nil,
        label .. "：提前点击三区不偷偷留下起点")
end

---@param game GameScene
---@param startType string
local function guidedStart(game, startType)
    local observation, sim = game.observation, game.sim
    V.assert(not sim.started and game.scaleMgr:CurrentScale() == "mouse" and observation.mode == "body",
        "每次真实开局均从mouse外观引导开始")
    rejectStartBypass(game, "外观阶段")
    keyDown(KEY_M)
    game:OnWheel(0, 1000)
    V.assert(game.scaleMgr:CurrentScale() == "mouse" and not sim.started,
        "未开局M/滚轮不能跳过外观引导")
    click("lungHotspot")
    V.assert(observation.mode == "body", "外观不能直接点击肺热点进入肺部")
    click("anatomyToggleBtn")
    V.assert(observation.mode == "anatomy", "真实解剖按钮切换解剖叠肺状态")
    rejectStartBypass(game, "解剖未点肺阶段")
    click("lungHotspot")
    V.assert(observation.mode == "lung" and observation:IsTransitioning(), "点肺发起真实肺部放大动画")
    rejectStartBypass(game, "肺部放大未稳定阶段")
    settleObservation(game)
    local previous = sim.world
    click("start_" .. startType)
    V.assert(observation.selectedStartType == startType and sim.world == previous and not sim.started and sim.time == 0,
        "动画稳定后选区仅预览，不重建或启动世界")
    click("startRunBtn")
    V.assert(sim.started and sim.selectedStartRegion == startType and game.scaleMgr:CurrentScale() == "cell",
        "明确开始按钮启动所选区域并进入细胞跨层")
    V.assert(game.scaleMgr:IsTransitioning(), "开始后保留真实跨层过渡，不瞬切细胞")
    settleScale(game)
    V.assert(sim.time == 0 and not sim.pauseReasons.selection and not sim.pauseReasons.observation
        and not sim.pauseReasons.transition, "引导/动画只改变表现，病程从零等待后续真实步")
end

V.atFrame(5, function()
    scene = widget("gameScene") --[[@as GameScene]]
    local sim = scene.sim
    V.assert(not sim.started and sim.paused and sim.time == 0, "真实入口先等待引导，不后台跑病程")
    V.assert(scene.observation.mode == "body" and scene.scaleMgr:CurrentScale() == "mouse",
        "main注入ObservationState并默认mouse外观")
    V.assert(widget("observationOverlay"):IsVisible(), "开局透明观察交互层可见")
    guidedStart(scene, "TRACHEA")
    local ok, errors = sim.world.map:Verify()
    V.assert(ok, "真实入口固定地图Verify通过：" .. table.concat(errors, "; "))
    conservation(sim.world)

    keyDown(KEY_R)
    V.assert(not sim.started and sim.paused and sim.time == 0, "R返回选择并重置计时")
    V.assert(scene.observation.mode == "body" and scene.observation.selectedStartType == nil
        and scene.scaleMgr:CurrentScale() == "mouse", "R同时重置小鼠外观/选区/默认mouse尺度")
    guidedStart(scene, "DEEP_LUNG")
    V.assert(sim.world:Counts().mainMass == 42 and sim.world:Counts().latent == 1,
        "深肺开始使用42质量与1潜伏节点真实开局参数")
    V.assert(sim.stage == 1 and sim.deepReached, "深肺初始节点不计入首阶段新增感染节点")
    conservation(sim.world)

    for _, id in ipairs({ "stageName", "taskText", "taskProgress", "taskHint", "releasedCount",
        "nodeStates", "splitBtn", "switchBtn", "observeBtn" }) do
        V.assert(widget(id) ~= nil, "新协议HUD有" .. id)
    end
    V.assert(#Config.Cards.definitions == 16 and widget("cardInfoOverlay") ~= nil,
        "正式卡池有16张定义并使用统一线框弹窗")
    V.assert(not widget("cardInfoOverlay"):IsVisible() and #sim.obtainedCards == 0,
        "开局不显示正式弹窗，也未假授能力")
    -- 暂停保持开局截图和接下来的handler测试，不允许背景免疫打乱夹具。
    sim:SetPaused("validation-hold", true)
end)

V.atFrame(10, function()
    local game = assert(scene)
    local sim, world = game.sim, game.sim.world
    logPause(sim, "frame10移除validation-hold前")
    sim:SetPaused("validation-hold", false)
    verifyFocusPause(game, "frame10真实Update后")
    isolateSurfacelessFocus(game, "frame10分裂切群")
    world:SetAim(1, 0)
    local mass = world.player.mass
    keyDown(KEY_2)
    local counts = world:Counts()
    local cost = math.max(1, math.floor(mass * Config.Gameplay.splitCostFraction))
    V.assert(counts.groups == 2 and counts.controlled == mass - cost and world.stats.splitCost == cost,
        "真实按2分裂为两群并扣质量成本")
    local before = counts.controlled
    keyDown(KEY_2, true)
    keyDown(KEY_SPACE, true)
    V.assert(world:Counts().controlled == before and world.stats.totalSplits == 1,
        "忽略空格/2的Repeat事件，不重复消耗质量")
    local main = assert(world:MainSwarm())
    world:SetMovement(1, 0)
    sim.touchMove.x, sim.touchMove.y, sim.touchMove.active = 1, 0, true
    keyDown(KEY_TAB)
    V.assert(world.player.id ~= main.id and main.isMainSwarm and not main.isPlayerControlled,
        "真实Tab切分群，主群身份不混淆")
    V.assert(world._inputX == 0 and world._inputY == 0 and not sim.touchMove.active,
        "Tab清前一个群的移动及摇杆状态")
    local selected = world.currentControlledSwarmId
    keyDown(KEY_TAB, true)
    V.assert(world.currentControlledSwarmId == selected, "Tab Repeat不反复切群")
    conservation(world)

    -- 驱动真实观察切层，再完成镜头过渡；scene Update同步pauseReasons。
    keyDown(KEY_M)
    settleScale(game)
    verifyFocusPause(game, "frame10小鼠观察Update后")
    V.assert(game.scaleMgr:CurrentScale() == "mouse" and sim.pauseReasons.observation == true and sim.paused,
        "真实M切小鼠观察层并独立暂停病程")
    local t, wt = sim.time, world.time
    local beforeObservation = diseaseFingerprint(sim)
    if input and (input.focus == false or input.minimized == true) then
        sim:SetPaused("focus", false) -- 只隔离离屏focus，必须仍由observation暂停。
    end
    V.assert(sim.pauseReasons.observation == true and sim.paused, "移除环境focus后观察暂停仍独立有效")
    sim:Update(60)
    V.assert(diseaseFingerprint(sim) == beforeObservation, "观察暂停60秒真实细胞/免疫/Released/统计/计时全部不变")
    V.assert(sim.time == t and world.time == wt, "观察60秒不跑病程、不补跑")
    verifyFocusPause(game, "frame10观察60秒后恢复真实focus")
    keyDown(KEY_2)
    V.assert(world.stats.totalSplits == 1, "观察层分裂键不执行")

    V.assert(game.observation.mode == "body", "started观察也先回小鼠外观，不直接换成孤立肺图")
    click("anatomyToggleBtn")
    V.assert(game.observation.mode == "anatomy", "started观察同一解剖切换链路")
    click("lungHotspot")
    V.assert(game.observation.mode == "lung" and game.observation:IsTransitioning(), "started点肺也有真实放大动画")
    settleObservation(game)
    local selectedStart = sim.selectedStartRegion
    for _, def in ipairs(Config.StartRegions) do click("start_" .. def.type) end
    click("startRunBtn")
    V.assert(sim.world == world and sim.selectedStartRegion == selectedStart
        and game.observation.selectedStartType == nil, "started观察三区和开始回调不能选区/重开")
    local visualBefore = game.observation.visualTime
    for _ = 1, 60 do game:Update(1 / 60) end
    V.assert(game.observation.visualTime > visualBefore and sim.time == t and world.time == wt,
        "真实GameScene观察Update增长视觉时间，但病程保持原时间")
    V.assert(diseaseFingerprint(sim) == beforeObservation, "观察动画更新不写真实病程实体/统计")
    click("observationPlayBtn")
    settleScale(game)
    local unfocused = verifyFocusPause(game, "frame10返回细胞Update后")
    V.assert(game.scaleMgr:CurrentScale() == "cell" and not sim.pauseReasons.observation
        and not sim.pauseReasons.transition, "返回细胞只结束观察/过渡，不改合理失焦暂停")
    V.assert(unfocused and sim.paused or not unfocused and not sim.paused,
        "返回细胞是否暂停取决于真实失焦状态")
    isolateSurfacelessFocus(game, "frame10恢复固定步")
    sim:Update(Config.Gameplay.movementStep)
    V.assert(math.abs(sim.time - t - Config.Gameplay.movementStep) < 0.000001, "回细胞只推进下一固定步，无观察补跑")
    conservation(world)
    verifyFocusPause(game, "frame10同步动作结束恢复真实失焦判断")

    game.pointer.active, game.pointer.known = true, true
    sim.touchMove.x, sim.touchMove.y, sim.touchMove.active = 1, -1, true
    keyDown(KEY_R)
    V.assert(not sim.started and sim.paused and sim.time == 0 and sim.world:Counts().groups == 1,
        "真实R重开清群、计时和暂停状态，回选择")
    V.assert(not sim.touchMove.active and sim.touchMove.x == 0 and sim.touchMove.y == 0,
        "R重开清触摸输入")
    V.assert(not game.pointer.active and not game.pointer.known, "SIM_RESET清GameScene鼠标残留")
    V.assert(sim.world._inputX == 0 and sim.world._inputY == 0 and sim.world.splitCooldown == 0,
        "R重开清世界移动与分裂冷却")
    V.assert(game.scaleMgr:CurrentScale() == "mouse" and game.observation.mode == "body"
        and game.observation.selectedStartType == nil and game.observation.lungProgress == 0,
        "R重开回mouse/body，清肺部过渡和选区")
    guidedStart(game, "DEEP_LUNG")
    V.assert(sim.started and sim.world:Counts().mainMass == 42 and sim.world:Counts().latent == 1,
        "重新选择真实深肺开局，未人为改cells的60秒病程准备完成")
    diseaseStartTime, diseaseStartTick, diseaseNodeId = sim.time, sim.tickCount, 0
    for _, cell in ipairs(sim.world.cells) do
        if cell.state == "LATENT" then diseaseNodeId = cell.id end
    end
    V.assert(diseaseNodeId > 0, "60秒病程必须使用开局真实潜伏节点")
    sim:SetPaused("validation-hold", true)
    game:UpdateCamera(1)
end)

-- 分散到60个验证帧，每帧同步1秒Sim.Update。不是timeScale快进/大dt吞步，
-- 避免同步3600步塞进一帧人为制造多秒帧尖峰。正常引擎更新之间保持hold暂停。
for offset = 0, 59 do
    local segment = offset + 1
    V.atFrame(20 + offset, function()
        local game = assert(scene)
        local sim = game.sim
        verifyFocusPause(game, "60秒病程段" .. segment)
        sim:SetPaused("validation-hold", false)
        isolateSurfacelessFocus(game, "60秒病程段" .. segment)
        sim.world:SetMovement(0, 0)
        sim.touchMove.x, sim.touchMove.y, sim.touchMove.active = 0, 0, false
        for _ = 1, 60 do sim:Update(Config.Gameplay.movementStep) end
        diseaseSegments = diseaseSegments + 1
        V.assert(math.abs(sim.time - diseaseStartTime - diseaseSegments) < 0.000001,
            "真实病程段" .. segment .. "恰推进1秒，无观察/失焦补跑")
        V.assert(not sim.ending, "真实深肺60秒内仍有玩家活群，未提前终局")
        conservation(sim.world)
        sim:SetPaused("validation-hold", true)
        if input and (input.focus == false or input.minimized == true) then sim:SetPaused("focus", true) end
    end)
end

V.atFrame(80, function()
    local game = assert(scene)
    local sim, world = game.sim, game.sim.world
    V.assert(diseaseSegments == 60 and math.abs(sim.time - diseaseStartTime - 60) < 0.000001,
        "真实未改细胞病程推进完整60秒")
    V.assert(sim.tickCount - diseaseStartTick == 3600 and world.diseaseAccum < 0.000001,
        "60秒真实固定3600移动步与120病程步无积压")
    local node
    for _, cell in ipairs(world.cells) do if cell.id == diseaseNodeId then node = cell end end
    V.assert(node ~= nil and node.state == "PRODUCTIVE" and node.latencyTimer >= Config.Gameplay.latentSeconds,
        "真实开局潜伏节点自然转为PRODUCTIVE，不人为更改状态")
    V.assert(node ~= nil and node.releaseCount == 2 and world.stats.totalReleased >=
        Config.Gameplay.releaseBatches[1] + Config.Gameplay.releaseBatches[2], "60秒自然分批释放已完成前两批")
    V.assert(world:Counts().released > 0 and sim.globalInflammation > 0 and sim.globalTissueDamage > 0,
        "真实60秒有独立Released、炎症及损伤，不只是推进空计时")
    conservation(world)
    print(string.format("[redesign_validation] 真实60秒 cells=%d released=%d killed=%d inflammation=%.2f damage=%.2f",
        #world.cells, world.stats.totalReleased, world.stats.totalKilled, sim.globalInflammation, sim.globalTissueDamage))
    keyDown(KEY_R)
    guidedStart(game, "UPPER_AIRWAY")
    V.assert(sim.started and sim.time == 0 and sim.world:Counts().mainMass == 30 and sim.world:Counts().infected == 0,
        "60秒病程后重开健康上呼吸道，保留健康截图而非延续深肺状态")
    sim:SetPaused("validation-hold", true)
    game:UpdateCamera(1)
end)

---@param id string
---@param lastId string
local function verifyScroll(id, lastId)
    local scroll = widget(id) --[[@as ScrollView]]
    local rect = scroll:GetAbsoluteLayoutForHitTest()
    local cw, ch = scroll:GetContentSize()
    print(string.format("[redesign_validation] scroll=%s viewport=(%.1f,%.1f %.1fx%.1f) content=%.1fx%.1f",
        id, rect.x, rect.y, rect.w, rect.h, cw, ch))
    V.assert(rect.w > 0 and rect.h > 0 and ch > 0, id .. "：手机滚动视窗及内容不能是零高度")
    V.assert(scroll.props.scrollY == true and scroll.props.scrollX == false,
        id .. "：纵向内容可滚动且不水平溢出")
    V.assert(cw <= rect.w + 1, id .. "：内容宽度不溢出手机左右分栏")
    scroll:SetScroll(0, 0)
    local start = widget(lastId):GetAbsoluteLayoutForHitTest()
    scroll:ScrollToBottom()
    local sx, sy = scroll:GetScroll()
    local finish = widget(lastId):GetAbsoluteLayoutForHitTest()
    local maxScroll = math.max(0, ch - rect.h)
    V.assert(math.abs(sy - maxScroll) < 0.01 and sx == 0, id .. "：可滚到底部且位置按视窗夹紧")
    if maxScroll > 0.01 then
        V.assert(finish.y < start.y and math.abs(start.y - finish.y - sy) < 0.1,
            id .. "：真实滚动使底部内容移动，不是只改变计数")
    end
    local visibleHeight = math.max(0, math.min(finish.y + finish.h, rect.y + rect.h) - math.max(finish.y, rect.y))
    V.assert(finish.h > 0 and visibleHeight >= math.min(finish.h, rect.h) - 1,
        id .. "：末项" .. lastId .. "有有效可见高度，可通过滚动到达")
    scroll:SetScroll(0, 0)
end

V.atFrame(100, function()
    local joystick = widget("joystickPanel")
    local needsJoystick = PlatformUtils.NeedsVirtualJoystick()
    if PlatformUtils.IsDesktopPlatform() and not needsJoystick then
        V.assert(not joystick:IsVisible(), "桌面隐藏整个joystickPanel，不只隐藏旋钮或按窄屏判断")
    elseif PlatformUtils.IsMobilePlatform() then
        V.assert(joystick:IsVisible(), "原生移动端细胞玩法显示整个joystickPanel")
    end
    -- Web真实touch PointerDown锁存由独立Lua测试覆盖；离屏无真实触摸不冒充已投递。
    local top = widget("hudTopRow"):GetAbsoluteLayout()
    local bottom = widget("hudBottomRow"):GetAbsoluteLayout()
    local content = widget("hudContent"):GetAbsoluteLayout()
    V.assert(content.h > 0 and top.h > 0 and bottom.h > 0, "HUD主布局面积有效")
    V.assert(bottom.y >= top.y + top.h, "上下HUD分栏不重叠")
    local left = widget("hudLeftScroll") --[[@as ScrollView]]
    local right = widget("hudStatsScroll") --[[@as ScrollView]]
    left:SetScroll(0, 0)
    right:SetScroll(0, 0)
    local leftRect, rightRect = left:GetAbsoluteLayoutForHitTest(), right:GetAbsoluteLayoutForHitTest()
    V.assert(rightRect.x >= leftRect.x + leftRect.w - 1, "手机左右滚动分栏不重叠")
    local stage = widget("stagePanel"):GetAbsoluteLayoutForHitTest()
    local hint = widget("taskHint"):GetAbsoluteLayoutForHitTest()
    local hintVisible = math.max(0, math.min(hint.y + hint.h, leftRect.y + leftRect.h) - math.max(hint.y, leftRect.y))
    print(string.format("[redesign_validation] stage=(%.1f,%.1f %.1fx%.1f) hint=(%.1f,%.1f %.1fx%.1f) hintVisible=%.1f topBottom=%.1f",
        stage.x, stage.y, stage.w, stage.h, hint.x, hint.y, hint.w, hint.h, hintVisible, leftRect.y + leftRect.h))
    V.assert(stage.w > 0 and stage.h > 0 and hint.h > 0, "阶段任务面板及底部提示具有非零有效高度")
    V.assert(hint.y + hint.h <= stage.y + stage.h + 1, "阶段底部提示包含于stagePanel而非被零高度裁掉")
    V.assert(hintVisible >= hint.h - 1, "手机左栏初始视窗能完整看到阶段底部提示")
    verifyScroll("hudLeftScroll", "scaleHint")
    verifyScroll("hudStatsScroll", "independentCount")
    verifyScroll("strategyScroll", "cardInfoBtn")
    conservation(assert(scene).sim.world)
    print("[redesign_validation] handler仅隔离离屏focus reason；真实失焦暂停已保留并验证，窗口焦点/物理触摸及完整局长/平衡未验收")
end)
