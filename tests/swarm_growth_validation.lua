-- 本轮旧机制的独立原生回归：由真实 main.lua 建树，validate-test 注入 V。
-- ONLY 此旧夹具及 swarm_autonomy_validation.lua；不改生产、入口、HUD 或 input.focus。
-- 动态选择槽按真实活群数增长并保留高水位对象，不再假定六群上限。
-- 键盘通过真实 HandleKeyDown；按钮通过真实鼠标适配器及控件树命中分发。
-- 状态夹具只安排合法位置、调用真实 _Release / DamageSwarm / 固定步生命周期。
-- _Release 使用真实初始潜伏节点和配置批量，但不等待其自然释放时刻；这不是玩家自然全局路线。
-- 群的位置布置用于隔离局部操作、冷却和截图，不证明玩家自然行走能建立这些布局。
-- 离屏失焦先验证；只在同步动作段清 focus reason，结束由真实 GameScene.Update 恢复。
-- 建议原生验收帧数 160，截图帧 140；分别用桌面与小屏分辨率运行同一文件。
-- 当前验收环境为 Linux 原生离屏运行；Windows233 是项目文档目录名，不要求 Windows 系统验收。
local UI = require("urhox-libs/UI")
local Config = require("Core.Config")
local PlatformUtils = require("urhox-libs.Platform.PlatformUtils")
local LungMasks = require("Game.Views.LungRegionMasks")

---@type GameScene?
local scene = nil
---@type SwarmWorld?
local screenshotWorld = nil
---@type integer[]
local screenshotIds = {}
local completedCooldownSeconds = 0
local cooldownStartTime = 0
local cooldownExpectedGroups = 0
local screenshotPrepared = false
local originalFocus = ""
local originalMinimized = ""
local originalConfig = {}
local originalAutonomy = {}
local slotHighWater = 0
for key, value in pairs(Config.Gameplay) do originalConfig[key] = value end
for key, value in pairs(Config.Gameplay.autonomy) do originalAutonomy[key] = value end

---@param id string
---@return Widget
local function widget(id)
    return assert(assert(UI.GetRoot(), "真实 main 未建立 UI 根"):FindById(id), "缺少真实控件：" .. id)
end

---@param id string
---@return Button
local function button(id)
    return widget(id) --[[@as Button]]
end

---@param id string
---@return string
local function text(id)
    return tostring(widget(id).props.text or "")
end

---@param id string
---@return ScrollView
local function scroll(id)
    return widget(id) --[[@as ScrollView]]
end

local function refreshHUD()
    -- 只调 main 的真实 HUD 节流入口，不调 UI.Update 以免额外推进整个游戏树。
    HandleUpdate("Update", { GetFloat = function() return 0.25 end })
    UI.Layout()
    for _, id in ipairs({ "strategyScroll", "hudLeftScroll", "hudStatsScroll", "startSummary" }) do
        local item = assert(UI.GetRoot()):FindById(id) --[[@as ScrollView?]]
        if item then item:Update(0) end
    end
    local index = 1
    while assert(UI.GetRoot()):FindById("selectSwarm_" .. index) do
        slotHighWater = math.max(slotHighWater, index)
        index = index + 1
    end
end

---@param key integer
---@param repeated? boolean
local function keyDown(key, repeated)
    HandleKeyDown("KeyDown", {
        GetInt = function() return key end,
        GetBool = function() return repeated == true end,
    })
end

---@param outer Rect4
---@param inner Rect4
---@return boolean
local function fullyInside(outer, inner)
    return inner.w > 0 and inner.h > 0 and inner.x >= outer.x - 1 and inner.y >= outer.y - 1
        and inner.x + inner.w <= outer.x + outer.w + 1
        and inner.y + inner.h <= outer.y + outer.h + 1
end

---@param item Widget
local function reveal(item)
    -- 从外到内滚动真正的祖先视窗；不用改控件位置/visible/disabled 来制造命中。
    ---@type ScrollView[]
    local ancestors = {}
    local parent = item.parent
    while parent do
        if parent.GetScroll then table.insert(ancestors, 1, parent --[[@as ScrollView]]) end
        parent = parent.parent
    end
    UI.Layout()
    for _, container in ipairs(ancestors) do
        container:Update(0)
        local area, target = container:GetAbsoluteLayoutForHitTest(), item:GetAbsoluteLayoutForHitTest()
        local _, sy = container:GetScroll()
        local adjustment = 0
        if target.y < area.y then adjustment = target.y - area.y
        elseif target.y + target.h > area.y + area.h then
            adjustment = target.y + target.h - area.y - area.h
        end
        container:SetScroll(0, sy + adjustment)
        UI.Layout()
    end
end

---@param item Widget
---@param mouseButton? number
local function pointerClickWidget(item, mouseButton)
    reveal(item)
    local r = item:GetAbsoluteLayoutForHitTest()
    local x, y = r.x + r.w * 0.5, r.y + r.h * 0.5
    local hit = UI.FindWidgetAt(x, y)
    local maskType = item.props.id == "lungHotspot" and "ALL"
        or (item.props.id == "start_DEEP_LUNG" and "DEEP_LUNG" or nil)
    if maskType then
        -- 肺蒙版中央为透明缝隙；逐点寻找原始蒙版内部且控件树实际命中的位置。
        -- 不扩张生产 mask，不改布局/控件属性，也不以业务回调取代指针投递。
        local found = false
        for row = 1, 79 do
            if found then break end
            for column = 1, 79 do
                local px, py = r.x + r.w * column / 80, r.y + r.h * row / 80
                if LungMasks.Contains(maskType, r, px, py) and UI.FindWidgetAt(px, py) == item then
                    x, y, found = px, py, true
                    break
                end
            end
        end
        V.assert(found and LungMasks.Contains(maskType, r, x, y), "指针位于真实肺蒙版内部而非透明中心：" .. tostring(item.props.id))
        hit = UI.FindWidgetAt(x, y)
    end
    V.assert(item:IsVisible() and r.w > 0 and r.h > 0, "实际指针目标具有可见有效布局：" .. tostring(item.props.id or item.props.text))
    V.assert(hit == item, "实际坐标命中目标而非包装器/裁剪外内容：" .. tostring(item.props.id or item.props.text))
    assert(hit == item, "真实指针无法命中目标")
    -- 适配器接受物理像素和 UI.PointerEvent 的按钮枚举，不混用引擎位掩码。
    local scale, which = UI.GetScale(), mouseButton or UI.PointerEvent.Button.Left
    UI.HandleMouseMove(x * scale, y * scale)
    UI.HandleMouseDown(x * scale, y * scale, which)
    UI.HandleMouseUp(x * scale, y * scale, which)
end

---@param id string
---@param mouseButton? number
local function pointerClick(id, mouseButton)
    pointerClickWidget(widget(id), mouseButton)
end

---@param id string
local function callbackClick(id)
    -- 有意直调隐藏/禁用控件回调，单独检查业务门控，不能冒充指针验收。
    local item = widget(id)
    assert(item.props.onClick, "缺少真实回调：" .. id)(item)
end

---@param root Widget
---@param expected string
---@return Widget?
local function findText(root, expected)
    if root.props.text == expected then return root end
    for _, child in ipairs(root:GetChildren()) do
        local found = findText(child, expected)
        if found then return found end
    end
    return nil
end

---@param game GameScene
---@param label string
---@return boolean
local function verifyFocus(game, label)
    game:Update(0)
    local unfocused = input ~= nil and (input.focus == false or input.minimized == true)
    V.assert((game.sim.pauseReasons.focus == true) == unfocused, label .. "：真实窗口失焦与 focus 暂停一致")
    if unfocused then V.assert(game.sim.paused, label .. "：离屏失焦确实暂停") end
    local reasons = {}
    for reason in pairs(game.sim.pauseReasons) do reasons[#reasons + 1] = reason end
    table.sort(reasons)
    print(string.format("[swarm_growth_validation] %s focus=%s minimized=%s paused=%s reasons=%s",
        label, tostring(input and input.focus), tostring(input and input.minimized), tostring(game.sim.paused), table.concat(reasons, ",")))
    return unfocused
end

---@param game GameScene
---@param label string
---@param blocked? boolean
local function beginSegment(game, label, blocked)
    local unfocused = verifyFocus(game, label .. "真实失焦检查")
    game.sim:SetPaused("swarm-validation-hold", false)
    if unfocused then
        V.assert(game.sim.pauseReasons.focus == true, label .. "：先验证失焦来源再局部隔离")
        game.sim:SetPaused("focus", false)
        print("[swarm_growth_validation] 只在本同步段移除离屏 focus reason；不改 input.focus")
    end
    V.assert(game.sim:CanAct() == (blocked ~= true), label .. "：操作允许性只由真实 CanAct 决定")
end

---@param game GameScene
local function endSegment(game)
    game.sim:SetPaused("swarm-validation-hold", true)
    verifyFocus(game, "同步段结束恢复真实失焦")
    refreshHUD()
end

---@param world SwarmWorld
local function conservation(world)
    local c, stats = world:Counts(), world.stats
    V.assert(stats.initialMass + stats.totalReleased - stats.totalKilled - stats.totalLost - stats.splitCost == c.virus,
        "所有质量来自真实出生/释放，扣真实清除/失活/分离成本；主动吸附只是转账")
    V.assert(#world.viruses == c.controlled and c.virus == c.controlled + c.released,
        "群实体逐个对应质量，游离病毒单独记账")
    V.assert(c.groups == #world.swarms and Config.Gameplay.maxSwarms == nil, "活群数逐个计数，生产不设六群或其他数量上限")
    local controlled, mainCount = 0, 0
    for _, swarm in ipairs(world.swarms) do
        local particles = 0
        for _, virus in ipairs(world.viruses) do if virus.swarmId == swarm.id then particles = particles + 1 end end
        V.assert(swarm.mass > 0 and particles == swarm.mass, "每个活群的粒子归属和质量一致：#" .. swarm.id)
        V.assert(not swarm.isHidden and world.map:Contains(swarm.x, swarm.y, swarm.radius), "群未隐藏且实际圆体合法：#" .. swarm.id)
        if swarm.isPlayerControlled then controlled = controlled + 1 end
        if swarm.isMainSwarm then mainCount = mainCount + 1 end
    end
    V.assert(controlled == 1 and mainCount == 1 and world:SwarmById(world.currentControlledSwarmId) == world.player,
        "存活世界恰一主群/受控群，player 指向实时受控对象")
    for _, pair in ipairs(world.mergePairs) do
        V.assert(pair.aId ~= pair.bId and world:SwarmById(pair.aId) ~= nil and world:SwarmById(pair.bId) ~= nil,
            "合并对使用实时有效 aId/bId 而非失效数组下标")
    end
end

---@param sim SimState
---@return string
local function fingerprint(sim)
    local w = sim.world
    local fields = { tostring(sim.started), tostring(sim.time), tostring(sim.tickCount), tostring(sim.tickAccum),
        tostring(sim.ending), tostring(w.time), tostring(w.diseaseAccum), tostring(w.splitCooldown),
        tostring(w.currentControlledSwarmId), tostring(w._inputX), tostring(w._inputY), tostring(w._rng),
        tostring(sim.touchMove.x), tostring(sim.touchMove.y), tostring(sim.touchMove.active),
        tostring(w.globalInflammation), tostring(w.globalTissueDamage), tostring(w._nextGroupId), tostring(w._nextVirusId) }
    for _, s in ipairs(w.swarms) do fields[#fields + 1] = table.concat({ s.id, s.mass, s.x, s.y, s.vx, s.vy,
        tostring(s.isMainSwarm), tostring(s.isPlayerControlled), s.mergeGrace, s.launchTimer,
        tostring(s.aiState), tostring(s.aiTargetCellId), tostring(s.autoSplitCooldown),
        tostring(s._aiThinkClock), tostring(s._aiTargetHold), tostring(s._aiWanderClock),
        tostring(s._aiDirectionX), tostring(s._aiDirectionY), tostring(s._aiMoveX), tostring(s._aiMoveY) }, ",") end
    for _, v in ipairs(w.viruses) do fields[#fields + 1] = table.concat({ v.id, v.swarmId, v.x, v.y }, ",") end
    for _, v in ipairs(w.releasedViruses) do fields[#fields + 1] = table.concat({ v.id, v.state, v.x, v.y, v.age, v.lifetime }, ",") end
    for _, c in ipairs(w.cells) do fields[#fields + 1] = table.concat({ c.id, c.state, c.exposure, c.latencyTimer,
        c.productiveTimer, c.releaseCount, c.immuneHits, c._charge, c._groupCharge, c._releasedCharge }, ",") end
    for _, i in ipairs(w.immunes) do fields[#fields + 1] = table.concat({ i.id, i.state, i.x, i.y,
        i.warningTimer, i.attackTimer, i.cooldown, tostring(i.targetId) }, ",") end
    local names = {}
    for name in pairs(w.stats) do names[#names + 1] = name end
    table.sort(names)
    for _, name in ipairs(names) do fields[#fields + 1] = name .. "=" .. tostring(w.stats[name]) end
    for _, e in ipairs(w.events) do
        fields[#fields + 1] = e.name .. "=" .. tostring(e.time)
        local keys = {}
        for name in pairs(e.payload) do keys[#keys + 1] = name end
        table.sort(keys)
        for _, name in ipairs(keys) do fields[#fields + 1] = name .. "=" .. tostring(e.payload[name]) end
    end
    for _, e in ipairs(w.effects) do fields[#fields + 1] = table.concat({ e.kind, e.x, e.y, e.radius, e.age }, ",") end
    return table.concat(fields, ";")
end

---@param game GameScene
local function settleTransitions(game)
    -- 逐帧走真实动画，不写进度、transition、scale 或模拟时间。
    for _ = 1, 300 do
        if not game.observation:IsTransitioning() and not game.scaleMgr:IsTransitioning() then break end
        game.observation:Update(1 / 60)
        game.scaleMgr:Update(1 / 60)
        refreshHUD()
    end
    V.assert(not game.observation:IsTransitioning() and not game.scaleMgr:IsTransitioning(), "真实观察/跨层动画逐帧稳定")
    game:Update(0)
    refreshHUD()
end

---@param game GameScene
local function guidedStart(game)
    V.assert(not game.sim.started and game.observation.mode == "body" and game.scaleMgr:CurrentScale() == "mouse",
        "真实 main 从小鼠外观引导开局")
    pointerClick("anatomyToggleBtn")
    V.assert(game.observation.mode == "anatomy", "真实指针切换解剖")
    pointerClick("lungHotspot")
    V.assert(game.observation.mode == "lung" and game.observation:IsTransitioning(), "真实点肺启动放大动画")
    settleTransitions(game)
    pointerClick("start_DEEP_LUNG")
    V.assert(game.observation.selectedStartType == "DEEP_LUNG" and not game.sim.started, "真实点选深肺仅预览")
    refreshHUD()
    pointerClick("startRunBtn")
    V.assert(game.sim.started and game.sim.selectedStartRegion == "DEEP_LUNG" and game.scaleMgr:CurrentScale() == "cell",
        "真实开始按钮进入深肺细胞玩法")
    settleTransitions(game)
    V.assert(game.sim.time == 0 and game.sim.world:Counts().mainMass == 42 and game.sim.world:Counts().latent == 1,
        "深肺使用原生产开局质量/潜伏节点；动画不推进病程")
    conservation(game.sim.world)
end

---@param world SwarmWorld
---@param swarm SwarmRecord
---@param x number
---@param y number
local function placeSwarm(world, swarm, x, y)
    assert(world:SwarmById(swarm.id) == swarm and world.map:Contains(x, y, swarm.radius), "状态夹具群坐标必须容纳真实圆体")
    swarm.x, swarm.y, swarm.vx, swarm.vy = x, y, 0, 0
    swarm.currentRegionId = world.map:RegionAt(x, y)
    world:_UpdateParticles()
end

---@param world SwarmWorld
---@return RespiratoryCell
local function releaseSource(world)
    for _, cell in ipairs(world.cells) do
        if cell.infectionSource == "initial" and cell.state ~= "DEAD" then return cell end
    end
    error("状态夹具需要真实深肺初始感染节点；不伪造细胞生命周期")
end

---@param world SwarmWorld
---@param count integer
---@return ReleasedVirusRecord[]
local function releaseNear(world, count)
    local s, cfg = world.player, Config.Gameplay
    local oldReleased, oldTotal = #world.releasedViruses, world.stats.totalReleased
    world:_Release(releaseSource(world), count)
    V.assert(#world.releasedViruses == oldReleased + count and world.stats.totalReleased == oldTotal + count,
        "吸附夹具由真实 _Release 逐个创建并进入累计出生账")
    ---@type ReleasedVirusRecord[]
    local created = {}
    local distance = s.radius + (cfg.absorptionExtra + cfg.activeAbsorptionExtra) * 0.5
    for index = oldReleased + 1, #world.releasedViruses do
        local virus = world.releasedViruses[index]
        local found = false
        for step = 0, 71 do
            local angle = (step + index * 0.01) * math.pi / 36
            local x, y = s.x + math.cos(angle) * distance, s.y + math.sin(angle) * distance
            local sweep = world.map:_Sweep(x, y, s.x - x, s.y - y, virus.radius)
            if world.map:Contains(x, y, virus.radius) and world.map:Contains(s.x, s.y, virus.radius) and sweep >= 1 then
                virus.x, virus.y, virus._oldX, virus._oldY = x, y, x, y
                found = true
                break
            end
        end
        assert(found, "测试释放体必须找到合法且完整直线可达的主动吸附位置")
        V.assert(virus.age == 0 and virus.lifetime == cfg.releasedLifetime and virus.state == "RELEASED",
            "释放夹具保留真实状态、寿命与来源，不手造病毒表")
        local gap = math.sqrt((virus.x - s.x)^2 + (virus.y - s.y)^2)
        V.assert(gap > s.radius + cfg.absorptionExtra and gap < s.radius + cfg.activeAbsorptionExtra,
            "游离体在被动吸附圈外、主动圈内，E 的成功不能冒充被动吸附")
        created[#created + 1] = virus
    end
    conservation(world)
    return created
end

---@param game GameScene
---@param usePointer? boolean
local function absorbFixture(game, usePointer)
    local world = game.sim.world
    local batch = Config.Gameplay.releaseBatches[2]
    local created = releaseNear(world, batch)
    local before = world:Counts()
    local oldAbsorbed, oldReleased, mass = world.stats.totalAbsorbed, world.stats.totalReleased, world.player.mass
    local expected = world:AbsorbableCount()
    V.assert(math.type(expected) == "integer" and expected >= batch, "AbsorbableCount 是真实可吸附整数快照")
    refreshHUD()
    V.assert(text("absorptionStatus"):find("附近 " .. expected .. " 个", 1, true) ~= nil,
        "HUD 使用可吸附实体数而非仅总游离数")
    if usePointer then
        scroll("strategyScroll"):SetScroll(0, 0)
        UI.Layout()
        pointerClick("absorbBtn")
    else keyDown(KEY_E) end
    local after = world:Counts()
    V.assert(world.player.mass == mass + expected and after.released == before.released - expected,
        (usePointer and "真实吸附按钮" or "真实 E handler") .. "把附近游离病毒转入当前控制群")
    V.assert(world.stats.totalAbsorbed == oldAbsorbed + expected and world.stats.totalReleased == oldReleased
        and after.virus == before.virus, "主动吸附计吸收、不重计出生，活病毒总量守恒")
    for _, virus in ipairs(created) do V.assert(virus.state == "ABSORBED", "真实释放实体转为终态 ABSORBED：#" .. virus.id) end
    V.assert(text("swarmStatus"):find("质量 " .. world.player.mass, 1, true) ~= nil, "共用入口即时更新受控质量")
    conservation(world)
end

---@param game GameScene
local function verifyRepeats(game)
    local world = game.sim.world
    releaseNear(world, Config.Gameplay.releaseBatches[1])
    refreshHUD()
    local before = fingerprint(game.sim)
    for _, key in ipairs({ KEY_E, KEY_SPACE, KEY_2, KEY_TAB }) do keyDown(key, true) end
    V.assert(fingerprint(game.sim) == before and world:AbsorbableCount() > 0,
        "E/空格/2/Tab 的 Repeat 即使有可吸附体也无质量、控制、统计、事件或特效副作用")
    pointerClick("absorbBtn", UI.PointerEvent.Button.Right)
    V.assert(fingerprint(game.sim) == before, "实际右键分发不误触主动吸附")
    absorbFixture(game, true)
end

---@param game GameScene
local function infectionGrowth(game)
    local world, cfg = game.sim.world, Config.Gameplay
    ---@type RespiratoryCell?
    local target = nil
    for _, cell in ipairs(world.cells) do
        if cell.state == "HEALTHY" and world.map:Contains(cell.x, cell.y, world.player.radius) then target = cell; break end
    end
    local cell = assert(target, "实际地图必须有合法健康细胞用于规模接触夹具")
    local originalX, originalY = world.player.x, world.player.y
    placeSwarm(world, world.player, cell.x, cell.y)
    local mass1, charge1 = world.player.mass, cell._groupCharge
    world:_AccumulateExposure(cfg.movementStep)
    local first = cell._groupCharge - charge1
    V.assert(math.abs(first - cfg.movementStep * math.sqrt(mass1 / cfg.densityReference) / cfg.infectionSeconds) < 1e-10,
        "同中心真实接触累积遵守 sqrt(质量/密度基准)，不是只改 HUD 倍率")
    absorbFixture(game, false)
    local mass2, charge2 = world.player.mass, cell._groupCharge
    world:_AccumulateExposure(cfg.movementStep)
    local second = cell._groupCharge - charge2
    V.assert(mass2 > mass1 and second > first and math.abs(second / first - math.sqrt(mass2 / mass1)) < 1e-9,
        "真实吸附增大规模后，同位置同 dt 的群感染贡献按平方根比例加速")
    V.assert(math.abs(world:GroupInfectionMultiplier(world.player) - math.sqrt(mass2 / cfg.densityReference)) < 1e-10,
        "公开倍率与接触累计使用一致的真实规模")
    V.assert(text("absorptionStatus"):find(string.format("×%.2f", world:GroupInfectionMultiplier(world.player)), 1, true) ~= nil,
        "HUD 明示当前群实际感染倍率")
    placeSwarm(world, world.player, originalX, originalY)
    print(string.format("[swarm_growth_validation] 局部接触状态夹具 mass=%d->%d charge=%.9f->%.9f；不是自然全局路线",
        mass1, mass2, first, second))
    conservation(world)
end

---@param game GameScene
---@param key? integer
local function splitAction(game, key)
    local w, cfg = game.sim.world, Config.Gameplay
    if w.player.mass < cfg.splitMinMass then absorbFixture(game, true) end
    assert(w:CanSplit(), "必须在真实质量、冷却、上限均允许时验分离")
    local groups, mass, costTotal, splits = #w.swarms, w.player.mass, w.stats.splitCost, w.stats.totalSplits
    local total = w:Counts().controlled
    local cost = math.max(1, math.floor(mass * cfg.splitCostFraction))
    w:SetAim(1, 0)
    if key then keyDown(key)
    else
        refreshHUD()
        scroll("strategyScroll"):SetScroll(0, 0)
        pointerClick("splitBtn", UI.PointerEvent.Button.Right)
        V.assert(#w.swarms == groups and w.stats.splitCost == costTotal, "右键分发不分离或扣成本")
        pointerClick("splitBtn")
    end
    V.assert(#w.swarms == groups + 1 and w.stats.totalSplits == splits + 1 and w.stats.splitCost == costTotal + cost,
        (key == KEY_SPACE and "空格" or key == KEY_2 and "2" or "实际分离按钮") .. "通过共用入口新增一个分群并扣原10%成本")
    V.assert(w:Counts().controlled == total - cost and w.splitCooldown == cfg.splitCooldown,
        "分离保留八秒真实冷却，非免费生产质量")
    local before = fingerprint(game.sim)
    keyDown(KEY_SPACE, true); keyDown(KEY_2, true)
    V.assert(fingerprint(game.sim) == before, "分离后重复键无额外副作用")
    keyDown(KEY_SPACE); keyDown(KEY_2)
    V.assert(#w.swarms == groups + 1 and w.stats.splitCost == costTotal + cost,
        "冷却中的非重复分离事件也不能增加群或扣成本")
    conservation(w)
end

---@param game GameScene
local function cycleAll(game)
    local w = game.sim.world
    local initial = w.currentControlledSwarmId
    ---@type table<number, boolean>
    local seen = { [initial] = true }
    local mainId = assert(w:MainSwarm()).id
    for _ = 1, #w.swarms do
        local old = w.currentControlledSwarmId
        w:SetMovement(1, 0)
        game.sim.touchMove.x, game.sim.touchMove.y, game.sim.touchMove.active = 1, -1, true
        keyDown(KEY_TAB)
        V.assert(w.currentControlledSwarmId ~= old and w.player.id == w.currentControlledSwarmId,
            "真实 Tab 逐次换到另一活群并同步 player")
        V.assert(w._inputX == 0 and w._inputY == 0 and not game.sim.touchMove.active,
            "每次共用切群入口清前群移动及摇杆")
        seen[w.currentControlledSwarmId] = true
    end
    V.assert(w.currentControlledSwarmId == initial, "Tab 遍历全部活群后完整环回起群")
    for _, s in ipairs(w.swarms) do V.assert(seen[s.id] == true, "Tab 能触及每个活群，包括第三及以后：#" .. s.id) end
    V.assert(assert(w:MainSwarm()).id == mainId, "Tab 不篡改主群身份")
    local before = fingerprint(game.sim)
    keyDown(KEY_TAB, true)
    V.assert(fingerprint(game.sim) == before, "Tab Repeat 不反复切群")
    refreshHUD()
    V.assert(text("swarmListTitle") == "群体 " .. #w.swarms .. " · 无数量上限 · 点选控制（Tab 循环）", "群列表标题显示实时活群数、无上限和 Tab 引导")
end

---@param game GameScene
local function chooseAndClearSlot(game)
    local w = game.sim.world
    V.assert(#w.swarms >= 4, "动态槽消亡验收先有四个真实分离群")
    local slot2, slot4 = button("selectSwarm_2"), button("selectSwarm_4")
    local old2, old4 = assert(slot2.props.onClick), assert(slot4.props.onClick)
    local doomed, nextAt2, last = w.swarms[2], w.swarms[3], w.swarms[4]
    pointerClick("selectSwarm_4")
    V.assert(w.player == last and text("swarmStatus"):find("#" .. last.id, 1, true) ~= nil, "动态第四槽实际点选控制及编号立即更新")
    local oldKilled = w.stats.totalKilled
    local killed = w:DamageSwarm(doomed.id, doomed.mass)
    V.assert(killed > 0 and w.stats.totalKilled == oldKilled + killed and w:SwarmById(doomed.id) == nil,
        "使用真实伤害/移除生命周期消亡第二群，不手删数组或质量")
    refreshHUD()
    V.assert(button("selectSwarm_2") == slot2 and button("selectSwarm_4") == slot4, "动态选择槽保留高水位并复用原对象而非重复重建")
    old2(slot2)
    V.assert(w.player == nextAt2 and w.player ~= doomed, "消亡前保存的第二槽回调仍读取当前索引，不保留旧群对象")
    local before = fingerprint(game.sim)
    old4(slot4)
    V.assert(fingerprint(game.sim) == before and not slot4:IsVisible() and slot4:IsDisabled(),
        "消亡后空第四槽隐藏/禁用，旧回调无法控制旧群或执行动作")
    pointerClick("selectSwarm_3")
    V.assert(w.player == last, "第三槽已映射真实存活第四群，不残留旧编号对象")
    conservation(w)
end

---@param game GameScene
---@param reason string
local function rejectAllActions(game, reason)
    local sim, w = game.sim, game.sim.world
    V.assert(sim.pauseReasons[reason] == true and sim.paused and not sim:CanAct(), reason .. "：真实暂停原因独立门控")
    local before = fingerprint(sim)
    for _, key in ipairs({ KEY_E, KEY_SPACE, KEY_2, KEY_TAB }) do keyDown(key); keyDown(key, true) end
    for _, id in ipairs({ "absorbBtn", "splitBtn", "switchBtn" }) do callbackClick(id) end
    for i = 1, slotHighWater do callbackClick("selectSwarm_" .. i) end
    V.assert(sim:AbsorbNearby() == 0 and sim:Split() == false and sim:SwitchControl() == false
        and sim:SwitchControl(w.swarms[1].id) == false, reason .. "：Sim 公开操作也不能绕过 CanAct")
    sim:Update(60)
    V.assert(fingerprint(sim) == before, reason .. "：键盘/回调/公开操作/暂停60秒均无病程或动作副作用")
end

---@param game GameScene
local function verifyPauseAndReset(game)
    local w = game.sim.world
    -- 有可吸附体、多个群和真实可分离状态，使暂停拒绝不是无目标/冷却造成的假通过。
    for _ = 1, 3 do
        if w.player.mass >= Config.Gameplay.splitMinMass then break end
        absorbFixture(game, true)
    end
    releaseNear(w, Config.Gameplay.releaseBatches[1])
    V.assert(w:CanSplit() and w:AbsorbableCount() > 0 and #w.swarms >= 2,
        "暂停拒绝前存在真实可分离群/可吸附体/可切换群，不能靠无目标或冷却假通过")
    refreshHUD()
    pointerClick("observeBtn")
    settleTransitions(game)
    beginSegment(game, "观察层动作拒绝", true)
    V.assert(game.scaleMgr:CurrentScale() == "mouse", "真实观察按钮切小鼠层")
    rejectAllActions(game, "observation")
    verifyFocus(game, "观察拒绝后恢复失焦")
    pointerClick("observationPlayBtn")
    settleTransitions(game)
    beginSegment(game, "回细胞说明拒绝前")
    pointerClick("cardInfoBtn")
    V.assert(widget("cardInfoOverlay"):IsVisible(), "真实卡说明按钮打开模态说明")
    beginSegment(game, "机制卡说明动作拒绝", true)
    rejectAllActions(game, "card-info")
    local close = assert(findText(widget("cardInfoOverlay"), "关闭说明"), "真实说明关闭按钮必须存在")
    pointerClickWidget(close)
    V.assert(not game.sim.pauseReasons["card-info"] and not widget("cardInfoOverlay"):IsVisible(), "实际关闭说明只解除说明暂停")
    verifyFocus(game, "关闭说明恢复真实失焦")
    game.pointer.active, game.pointer.known = true, true
    game.sim.touchMove.x, game.sim.touchMove.y, game.sim.touchMove.active = 1, -1, true
    keyDown(KEY_R)
    V.assert(game.sim.world ~= w and not game.sim.started and game.sim.time == 0 and game.sim.world:Counts().groups == 1,
        "真实 R 替换世界、清多群/计时并返回引导")
    V.assert(not game.pointer.active and not game.pointer.known and not game.sim.touchMove.active
        and game.sim.touchMove.x == 0 and game.sim.touchMove.y == 0, "R 通过真实重置事件清鼠标及触控残留")
    V.assert(game.sim.world.splitCooldown == 0 and game.sim.world._inputX == 0 and game.sim.world._inputY == 0
        and game.sim.world.stats.totalSplits == 0 and game.sim.world.stats.totalAbsorbed == 0, "R 清冷却、质量操作统计和世界移动")
    V.assert(game.scaleMgr:CurrentScale() == "mouse" and game.observation.mode == "body"
        and game.observation.selectedStartType == nil, "R 回小鼠外观并清选区")
    refreshHUD()
    for i = 1, slotHighWater do V.assert(not button("selectSwarm_" .. i):IsVisible(), "R 后高水位槽不显示前局群：" .. i) end
end

---@param game GameScene
local function arrangeForCooldown(game)
    -- 三轮只布置已有群坐标，质量、免疫、冷却、保护计时均由真实生命周期继续。
    -- 深肺左侧布点避免分离后墙内重叠合并；各点在真实地图上先验证圆体合法。
    local points = { { x = 7.6, y = 27.5 }, { x = 10.2, y = 27.5 }, { x = 12.8, y = 27.5 } }
    for index, swarm in ipairs(game.sim.world.swarms) do
        local p = assert(points[index], "冷却夹具只服务二/三群")
        placeSwarm(game.sim.world, swarm, p.x, p.y)
    end
    completedCooldownSeconds, cooldownStartTime, cooldownExpectedGroups = 0, game.sim.time, #game.sim.world.swarms
end

---@param game GameScene
---@param second integer
local function advanceCooldown(game, second)
    beginSegment(game, "真实冷却秒段" .. second)
    -- 明确局部隔离旧八秒冷却机制：此段禁 AI，免疫/流动/病程/合并照常运行。
    -- 仅本同步秒段修改 enabled，结束立刻恢复；新自主夹具始终用默认真实 AI。
    local autonomyEnabled = Config.Gameplay.autonomy.enabled
    Config.Gameplay.autonomy.enabled = false
    print("[swarm_growth_validation] 旧冷却局部隔离 autonomy.enabled=false；非整体自主验收")
    game.sim.world:SetMovement(0, 0)
    for _ = 1, 60 do game.sim:Update(Config.Gameplay.movementStep) end
    completedCooldownSeconds = completedCooldownSeconds + 1
    V.assert(math.abs(game.sim.time - cooldownStartTime - completedCooldownSeconds) < 1e-6,
        "冷却秒段按真实固定步推进，不写时间或清 cooldown")
    if second == 8 then
        V.assert(game.sim.world.splitCooldown < 1e-6, "原配置八秒冷却自然结束至浮点容差")
        -- 连续减法可能余极小正值；真实再推进一移动步，不写冷却，也不放宽 CanSplit。
        game.sim:Update(Config.Gameplay.movementStep)
        V.assert(game.sim.world.splitCooldown == 0, "第八秒后一真实固定步让冷却归零")
    end
    V.assert(not game.sim.ending and #game.sim.world.swarms == cooldownExpectedGroups,
        "真实免疫/移动/合并生命周期运行，既有活群仍存活且没有被意外合并")
    Config.Gameplay.autonomy.enabled = autonomyEnabled
    conservation(game.sim.world)
    endSegment(game)
end

---@param game GameScene
local function verifyLayout(game)
    refreshHUD()
    local strategy = scroll("strategyScroll")
    strategy:SetScroll(0, 0)
    UI.Layout()
    strategy:Update(0)
    local view, cw, ch = strategy:GetAbsoluteLayoutForHitTest(), strategy:GetContentSize()
    local screenRect = { x = 0, y = 0, w = UI.GetWidth(), h = UI.GetHeight() }
    V.assert(view.w > 0 and view.h > 0 and cw > 0 and ch > 0 and fullyInside(screenRect, view), "策略滚动视窗有效且在实际屏幕内")
    V.assert(strategy.props.scrollY == true and strategy.props.scrollX == false and cw <= view.w + 1,
        "策略内容只纵向滚动，不横向截断")
    local ids = { "absorbBtn", "splitBtn", "switchBtn", "observeBtn" }
    ---@type Rect4[]
    local rows = {}
    for _, id in ipairs(ids) do
        local r = button(id):GetAbsoluteLayoutForHitTest()
        rows[#rows + 1] = r
        V.assert(fullyInside(view, r) and fullyInside(screenRect, r), "顶部两行按钮完整可见：" .. id)
        V.assert(r.h >= 39 and r.w >= 82, "两行按钮有足够基准尺寸，不被 flex 压扁：" .. id)
    end
    V.assert(math.abs(rows[1].y - rows[2].y) < 1 and math.abs(rows[3].y - rows[4].y) < 1
        and rows[3].y >= rows[1].y + rows[1].h - 1, "吸附/分离和切群/观察确实分两行且无重叠")
    V.assert(rows[2].x >= rows[1].x + rows[1].w - 1 and rows[4].x >= rows[3].x + rows[3].w - 1,
        "同行按钮完整分栏而非重叠")
    local initialLast = widget("cardInfoBtn"):GetAbsoluteLayoutForHitTest()
    strategy:ScrollToBottom()
    UI.Layout()
    local sx, sy = strategy:GetScroll()
    local finalLast = widget("cardInfoBtn"):GetAbsoluteLayoutForHitTest()
    V.assert(sx == 0 and math.abs(sy - math.max(0, ch - view.h)) < 0.1 and fullyInside(view, finalLast),
        "策略能滚到真实说明末项，滚动按内容与视窗夹紧")
    if ch > view.h + 1 then V.assert(finalLast.y < initialLast.y and math.abs(initialLast.y - finalLast.y - sy) < 0.1,
        "策略滚动真实移动内容而非仅修改滚动数字") end
    for i = 1, #game.sim.world.swarms do
        local item = button("selectSwarm_" .. i)
        reveal(item)
        V.assert(item:IsVisible() and fullyInside(view, item:GetAbsoluteLayoutForHitTest()), "各群选择槽可通过真实滚动到达：" .. i)
        V.assert(tostring(item.props.text):find("#" .. game.sim.world.swarms[i].id, 1, true) ~= nil, "选择槽明示实时群编号：" .. i)
    end
    local joystick = widget("joystickPanel")
    if PlatformUtils.IsDesktopPlatform() and not PlatformUtils.NeedsVirtualJoystick() then
        V.assert(not joystick:IsVisible(), "桌面及桌面小屏不按窄屏误开整个摇杆容器")
    end
    -- 最后把截图定位到群体列表；顶部按钮的完整可见性已单独在 scroll=0 验证。
    reveal(widget("swarmListTitle"))
    reveal(button("selectSwarm_" .. #game.sim.world.swarms))
    game:UpdateViewport(game:GetAbsoluteLayout())
    print(string.format("[swarm_growth_validation] 布局 platform=%s physical=%dx%d DPR=%.2f scale=%.3f base=%.1fx%.1f strategy=%.1fx%.1f content=%.1fx%.1f scroll=%.1f",
        GetPlatform(), graphics:GetWidth(), graphics:GetHeight(), graphics:GetDPR(), UI.GetScale(), UI.GetWidth(), UI.GetHeight(),
        view.w, view.h, cw, ch, select(2, strategy:GetScroll())))
end

---@param game GameScene
local function prepareScreenshot(game)
    local w = game.sim.world
    V.assert(#w.swarms >= 3 and game.scaleMgr:CurrentScale() == "cell", "截图明确选择至少三个真实活群的细胞场景")
    local points = { { x = 11.0, y = 27.1 }, { x = 13.0, y = 27.2 }, { x = 13.6, y = 27.3 } }
    for i, swarm in ipairs(w.swarms) do
        local p = assert(points[i])
        placeSwarm(w, swarm, p.x, p.y)
        screenshotIds[i] = swarm.id
    end
    refreshHUD()
    pointerClick("selectSwarm_3")
    V.assert(w.player == w.swarms[3] and not w.player.isMainSwarm, "截图实际点选第三群，不永远跟随主群")
    game:UpdateCamera(2)
    V.assert(math.abs(game.camera.x - w.player.x) < 0.001 and math.abs(game.camera.y - w.player.y) < 0.001,
        "真实镜头 UpdateCamera 正确追踪当前控制第三群")
    conservation(w)
    screenshotWorld, screenshotPrepared = w, true
end

V.atFrame(5, function()
    scene = widget("gameScene") --[[@as GameScene]]
    local game = assert(scene)
    originalFocus, originalMinimized = tostring(input and input.focus), tostring(input and input.minimized)
    V.assert(Config.Gameplay.maxSwarms == nil and Config.Gameplay.activeAbsorptionExtra == 1.8
        and Config.Gameplay.autonomy.enabled == true and Config.Gameplay.autonomy.splitMass == 48
        and Config.Gameplay.splitMinMass == 12 and Config.Gameplay.splitCooldown == 8
        and Config.Gameplay.splitCostFraction == 0.10, "生产无群数上限/默认自主阈48；主动1.8米/最少12/八秒/10%保持")
    print("[swarm_growth_validation] Linux 原生离屏验收；状态夹具不等于自然全局路线；Windows233 仅为项目文档目录名")
    refreshHUD()
    guidedStart(game)
    local ok, errors = game.sim.world.map:Verify()
    V.assert(ok, "原生产地图 Verify：" .. table.concat(errors, ";"))
    V.assert(button("selectSwarm_1"):IsVisible() and slotHighWater >= 1, "首个动态选择槽由实际活群建立")
    V.assert(not assert(UI.GetRoot()):FindById("selectSwarm_7"), "首局未达到七群，不预造固定七槽")
    endSegment(game)
end)

V.atFrame(10, function()
    local game = assert(scene)
    beginSegment(game, "E/指针吸附与首次空格分离")
    absorbFixture(game, false)
    verifyRepeats(game)
    infectionGrowth(game)
    splitAction(game, KEY_SPACE)
    arrangeForCooldown(game)
    endSegment(game)
end)

for offset = 0, 7 do
    local second = offset + 1
    V.atFrame(20 + offset, function() advanceCooldown(assert(scene), second) end)
end

V.atFrame(30, function()
    local game = assert(scene)
    beginSegment(game, "真实2键再次分离第三群")
    V.assert(completedCooldownSeconds == 8, "首次八秒生命周期完整执行")
    splitAction(game, KEY_2)
    V.assert(#game.sim.world.swarms >= 3, "再次分离突破旧双群限制，取得第三个真实活群")
    cycleAll(game)
    pointerClick("selectSwarm_3")
    V.assert(game.sim.world.player == game.sim.world.swarms[3], "实际第三槽点选切群")
    pointerClick("selectSwarm_1")
    arrangeForCooldown(game)
    endSegment(game)
end)

for offset = 0, 7 do
    local second = offset + 1
    V.atFrame(40 + offset, function() advanceCooldown(assert(scene), second) end)
end

V.atFrame(50, function()
    local game = assert(scene)
    beginSegment(game, "真实分离按钮与第四群/动态槽消亡")
    splitAction(game)
    cycleAll(game)
    chooseAndClearSlot(game)
    arrangeForCooldown(game)
    endSegment(game)
end)

for offset = 0, 7 do
    local second = offset + 1
    V.atFrame(55 + offset, function() advanceCooldown(assert(scene), second) end)
end

V.atFrame(65, function()
    local game = assert(scene)
    beginSegment(game, "冷却结束后的全部暂停动作拒绝")
    verifyPauseAndReset(game)
end)

V.atFrame(70, function()
    local game = assert(scene)
    guidedStart(game)
    beginSegment(game, "R后截图场景真实重建")
    absorbFixture(game, false)
    splitAction(game, KEY_SPACE)
    arrangeForCooldown(game)
    endSegment(game)
end)

for offset = 0, 7 do
    local second = offset + 1
    V.atFrame(80 + offset, function() advanceCooldown(assert(scene), second) end)
end

V.atFrame(90, function()
    local game = assert(scene)
    beginSegment(game, "截图三群第二次分离")
    splitAction(game, KEY_2)
    cycleAll(game)
    prepareScreenshot(game)
    endSegment(game)
end)

V.atFrame(100, function()
    local game = assert(scene)
    V.assert(screenshotPrepared and game.sim.world == screenshotWorld, "截图使用 R 后真实三群世界，不以自造替代世界冒充 main")
    verifyLayout(game)
    game:UpdateCamera(2)
end)

V.atFrame(130, function()
    local game = assert(scene)
    verifyFocus(game, "截图前真实失焦检查")
    V.assert(game.sim.world == screenshotWorld and #game.sim.world.swarms >= 3 and widget("gameScene"):IsVisible(),
        "截图前真实世界和至少三群持续存在，画布未隐藏")
    for i, id in ipairs(screenshotIds) do
        V.assert(game.sim.world.swarms[i].id == id and not game.sim.world.swarms[i].isHidden,
            "截图群全部真实、存活、未隐藏：#" .. id)
    end
    local l = game:GetAbsoluteLayout()
    game:UpdateViewport(l)
    local viewport, w = game.viewport, game.sim.world
    local visibleGroups = 0
    for _, s in ipairs(w.swarms) do
        local x, y = game.cellView:WorldToScreen(s.x, s.y, l, game.scaleMgr:CurrentZoom())
        if x >= viewport.x and x <= viewport.x + viewport.w and y >= viewport.y and y <= viewport.y + viewport.h then
            visibleGroups = visibleGroups + 1
        end
    end
    V.assert(visibleGroups >= 3, "截图至少三群中心落在真实可玩镜头视窗内，不只是后台存在")
    V.assert(math.abs(game.camera.x - w.player.x) < 0.001 and math.abs(game.camera.y - w.player.y) < 0.001,
        "截图镜头仍跟当前第三控制群")
    for key, value in pairs(originalConfig) do V.assert(Config.Gameplay[key] == value, "验收未篡改生产配置：" .. key) end
    for key, value in pairs(originalAutonomy) do V.assert(Config.Gameplay.autonomy[key] == value, "局部冷却后完整恢复默认自主配置：" .. key) end
    conservation(w)
    print(string.format("[swarm_growth_validation] 截图就绪 frame=140 groups=%d controlled=#%d mass=%d camera=(%.3f,%.3f) world=DEEP_LUNG",
        #w.swarms, w.player.id, w.player.mass, game.camera.x, game.camera.y))
    print("[swarm_growth_validation] 已设断言：真实指针和键盘handler、局部规模感染、冷却、三/四群、全活群Tab、动态槽、暂停及R；未证明自然全局路线/局长平衡/物理设备事件投递")
end)

V.atFrame(150, function()
    V.assert(screenshotPrepared, "最后完成标记只能在三群截图状态准备后产生")
    print("[swarm_growth_validation] 初始真实focus=" .. originalFocus .. " minimized=" .. originalMinimized
        .. "；从未写 input.focus；请按原生 JSON test_result/test_assertions 与截图文件判级，不以日志自称通过")
    V.finish()
end)
