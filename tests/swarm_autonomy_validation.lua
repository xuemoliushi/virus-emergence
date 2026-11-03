-- 独立原生自主行为验收：真实 main.lua 创建世界/控件，V 仅注入断言。
-- ONLY tests；不替换 SwarmWorld/SimState、不关默认 AI、不改 production / input.focus。
-- 局部夹具明确限定：合法群/免疫坐标布置；由真实感染节点 _Release 出生并置近供给。
-- 不手造细胞病程、免疫状态、群质量或 AI 计时；不宣称自然全局路线/局长平衡。
-- 感染、免疫锁定/预警/趋近/逃逸、被动吸附、成熟与分离均走真实 Sim.Update -> world.Update。
-- UI 指针由真实命中树与物理坐标适配器投递；离屏 focus 先验证，仅同步段隔离。
-- 软件渲染 spike 阈10000仅环境容忍，非性能验收；desktop1280x720/small854x384。
local UI = require("urhox-libs/UI")
local Config = require("Core.Config")
local LungMasks = require("Game.Views.LungRegionMasks")
local PlatformUtils = require("urhox-libs.Platform.PlatformUtils")

---@type GameScene?
local scene = nil
---@type SwarmWorld?
local testedWorld = nil
local initialFocus = ""
local initialMinimized = ""
local finished = false
local slotHighWater = 0
local autoCycles = 0
local naturalInfectedCellId = 0
local fleeVerified = false
local peakGroups = 0
local originalConfig = {}
local originalAutonomy = {}
for k, v in pairs(Config.Gameplay) do originalConfig[k] = v end
for k, v in pairs(Config.Gameplay.autonomy) do originalAutonomy[k] = v end

---@param id string
---@return Widget
local function widget(id)
    return assert(assert(UI.GetRoot()):FindById(id), "缺真实控件：" .. id)
end

---@param id string
---@return Button
local function button(id) return widget(id) --[[@as Button]] end

---@param id string
---@return string
local function text(id) return tostring(widget(id).props.text or "") end

local function refreshHUD()
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

---@param item Widget
local function reveal(item)
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
        elseif target.y + target.h > area.y + area.h then adjustment = target.y + target.h - area.y - area.h end
        container:SetScroll(0, sy + adjustment)
        UI.Layout()
    end
end

---@param id string
local function pointerClick(id)
    local item = widget(id)
    reveal(item)
    local r = item:GetAbsoluteLayoutForHitTest()
    local x, y = r.x + r.w * 0.5, r.y + r.h * 0.5
    local maskType = id == "lungHotspot" and "ALL" or (id == "start_DEEP_LUNG" and "DEEP_LUNG" or nil)
    if maskType then
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
        V.assert(found and LungMasks.Contains(maskType, r, x, y), "已知肺缝隙：真实指针寻找蒙版内部 " .. id)
    end
    V.assert(item:IsVisible() and r.w > 0 and r.h > 0, "实际指针目标可见且布局有效：" .. id)
    V.assert(UI.FindWidgetAt(x, y) == item, "实际指针命中真实目标而非裁剪外包装器：" .. id)
    assert(UI.FindWidgetAt(x, y) == item, "指针无法命中 " .. id)
    local scale, which = UI.GetScale(), UI.PointerEvent.Button.Left
    UI.HandleMouseMove(x * scale, y * scale)
    UI.HandleMouseDown(x * scale, y * scale, which)
    UI.HandleMouseUp(x * scale, y * scale, which)
end

---@param key integer
---@param repeated? boolean
local function keyDown(key, repeated)
    HandleKeyDown("KeyDown", {
        GetInt = function() return key end,
        GetBool = function() return repeated == true end,
    })
end

---@param game GameScene
---@param label string
local function verifyFocus(game, label)
    game:Update(0)
    local unfocused = input ~= nil and (input.focus == false or input.minimized == true)
    V.assert((game.sim.pauseReasons.focus == true) == unfocused, label .. "：真实窗口失焦与暂停一致")
    if unfocused then V.assert(game.sim.paused, label .. "：离屏失焦确实暂停") end
end

---@param game GameScene
---@param label string
local function beginSegment(game, label)
    verifyFocus(game, label)
    game.sim:SetPaused("autonomy-validation-hold", false)
    if game.sim.pauseReasons.focus then
        print("[swarm_autonomy_validation] 仅同步段隔离已验证focus reason；不写input.focus：" .. label)
        game.sim:SetPaused("focus", false)
    end
    V.assert(game.sim:CanAct(), label .. "：真实 CanAct 允许行动")
    V.assert(Config.Gameplay.autonomy.enabled == true, label .. "：默认真实自主 AI 一直启用")
    refreshHUD()
end

---@param game GameScene
local function endSegment(game)
    game.sim:SetPaused("autonomy-validation-hold", true)
    verifyFocus(game, "同步段结束恢复真实focus")
    refreshHUD()
end

---@param game GameScene
local function settleTransitions(game)
    for _ = 1, 300 do
        if not game.observation:IsTransitioning() and not game.scaleMgr:IsTransitioning() then break end
        game.observation:Update(1 / 60)
        game.scaleMgr:Update(1 / 60)
        refreshHUD()
    end
    V.assert(not game.observation:IsTransitioning() and not game.scaleMgr:IsTransitioning(), "观察/跨层动画逐帧稳定")
    game:Update(0)
    refreshHUD()
end

---@param game GameScene
local function guidedStart(game)
    V.assert(not game.sim.started and game.observation.mode == "body", "真实main从小鼠引导开局")
    pointerClick("anatomyToggleBtn")
    pointerClick("lungHotspot")
    settleTransitions(game)
    pointerClick("start_DEEP_LUNG")
    refreshHUD()
    pointerClick("startRunBtn")
    settleTransitions(game)
    V.assert(game.sim.started and game.sim.time == 0 and game.sim.selectedStartRegion == "DEEP_LUNG"
        and game.sim.world.player.mass == 42 and game.sim.world:Counts().latent == 1,
        "真实深肺开局保持42质量/一个潜伏节点，动画不偷跑病程")
end

---@param w SwarmWorld
local function conservation(w)
    local c, stats = w:Counts(), w.stats
    peakGroups = math.max(peakGroups, #w.swarms)
    V.assert(stats.initialMass + stats.totalReleased - stats.totalKilled - stats.totalLost - stats.splitCost == c.virus,
        "质量守恒：真实出生/释放扣清除/失活/分离，不手改质量")
    V.assert(#w.viruses == c.controlled and c.groups == #w.swarms, "实体归属数/群数与实时计数一致")
    local mainCount, controlledCount = 0, 0
    for _, s in ipairs(w.swarms) do
        local count = 0
        for _, v in ipairs(w.viruses) do if v.swarmId == s.id then count = count + 1 end end
        V.assert(s.mass > 0 and count == s.mass and not s.isHidden and w.map:Contains(s.x, s.y, s.radius),
            "每个真实群存活、粒子数匹配、圆体合法：#" .. s.id)
        local validAI = { controlled=true, hidden=true, disabled=true, flee=true, seek=true, infect=true, collect=true, wander=true }
        V.assert(validAI[s.aiState] and s.aiState ~= "disabled" and s.autoSplitCooldown >= 0
            and (s.isPlayerControlled == (s.aiState == "controlled")),
            "默认AI对每个存活未受控群启用，含自动子群和前主群，无数量截断：#" .. s.id)
        if s.isMainSwarm then mainCount = mainCount + 1 end
        if s.isPlayerControlled then controlledCount = controlledCount + 1 end
    end
    V.assert(mainCount == 1 and controlledCount == 1 and w.player == w:SwarmById(w.currentControlledSwarmId),
        "恰一个主群/控制群，player仍指向实时控制ID")
end

---@param w SwarmWorld
---@param s SwarmRecord
---@param x number
---@param y number
local function placeSwarm(w, s, x, y)
    assert(w:SwarmById(s.id) == s and w.map:Contains(x, y, s.radius), "局部群坐标必须合法")
    s.x, s.y, s.vx, s.vy = x, y, 0, 0
    s.currentRegionId = w.map:RegionAt(x, y)
    w:_UpdateParticles()
end

---@param w SwarmWorld
---@param immune ImmuneCellRecord
---@param x number
---@param y number
local function placeImmune(w, immune, x, y)
    assert(w.map:Contains(x, y, immune.radius), "局部免疫坐标必须容纳圆体")
    immune.x, immune.y, immune._oldX, immune._oldY = x, y, x, y
    immune.regionId = w.map:RegionAt(x, y)
    -- 不写 state/target/warning/patrol：下一步仍走真实免疫状态机。
end

---@param w SwarmWorld
local function moveImmunesFar(w)
    local points = { {11.5, 3.0}, {14.5, 3.0}, {12.0, 5.0}, {14.2, 5.0}, {13.1, 9.0}, {13.1, 11.0}, {7.0, 16.0}, {20.0, 16.0} }
    for i, immune in ipairs(w.immunes) do local p = assert(points[i]); placeImmune(w, immune, p[1], p[2]) end
end

-- 暂停比较包含整个权威模拟的所有递归字段（含AI意图/目标/计时/统计/RNG/接触历史）。
---@param value any
---@param seen table
---@return string
local function serialize(value, seen)
    if type(value) ~= "table" then return type(value) .. "=" .. tostring(value) end
    if seen[value] then return "ref=" .. seen[value] end
    seen[value] = tostring(value)
    local keys = {}
    for k in pairs(value) do keys[#keys + 1] = k end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    local parts = {}
    for _, k in ipairs(keys) do parts[#parts + 1] = tostring(k) .. ":" .. serialize(value[k], seen) end
    return "{" .. table.concat(parts, ";") .. "}"
end

---@param sim SimState
---@return string
local function fingerprint(sim) return serialize(sim, {}) end

---@param game GameScene
---@param steps integer
local function advance(game, steps)
    V.assert(Config.Gameplay.autonomy.enabled and game.sim:CanAct(), "真实默认AI固定步可运行")
    local start = game.sim.time
    for _ = 1, steps do game.sim:Update(Config.Gameplay.movementStep) end
    V.assert(not game.sim.ending and math.abs(game.sim.time - start - steps * Config.Gameplay.movementStep) < 1e-6,
        "只通过真实Sim.Update推进固定步/免疫/感染/成熟，未写计时")
end

---@param w SwarmWorld
---@return RespiratoryCell
local function sourceCell(w)
    for _, c in ipairs(w.cells) do
        if c.infectionSource == "initial" and c.state ~= "DEAD" then return c end
    end
    for _, c in ipairs(w.cells) do
        if c.state == "LATENT" or c.state == "PRODUCTIVE" or c.state == "EXHAUSTED" then return c end
    end
    error("真实感染节点已不存在，不能手造病程供给")
end

---@param game GameScene
---@param s SwarmRecord
---@param targetMass integer
local function passiveSupply(game, s, targetMass)
    local w = game.sim.world
    local beforeReleased, beforeAbsorbed, startMass = w.stats.totalReleased, w.stats.totalAbsorbed, s.mass
    while s.mass < targetMass do
        local count = math.min(Config.Gameplay.releaseBatches[2], targetMass - s.mass)
        local old = #w.releasedViruses
        local c = sourceCell(w)
        w:_Release(c, count)
        for index = old + 1, #w.releasedViruses do
            local v = w.releasedViruses[index]
            V.assert(v.state == "RELEASED" and v.age == 0 and v.sourceCellId == c.id
                and v.lifetime == Config.Gameplay.releasedLifetime, "真实_Release创建供给，不手造病毒/来源/寿命")
            assert(w.map:Contains(s.x, s.y, v.radius))
            v.x, v.y, v._oldX, v._oldY = s.x, s.y, s.x, s.y
        end
        local oldMass, oldSplits = s.mass, w.stats.totalAutoSplits
        advance(game, 1)
        assert(s.mass > oldMass or w.stats.totalAutoSplits > oldSplits, "被动吸附供给未增长，不能用写mass伪造")
        if w:SwarmById(s.id) ~= s then error("供给源群被生命周期移除") end
        if w.stats.totalAutoSplits > oldSplits then break end -- 真实成熟源可在达到48的同一步立即分离。
    end
    V.assert(w.stats.totalReleased > beforeReleased and w.stats.totalAbsorbed > beforeAbsorbed,
        "局部增长供给记真实释放与吸附账，未按E或调用主动吸附")
    print(string.format("[swarm_autonomy_validation] 局部供给真实_Release+被动吸附 swarm=%d mass=%d->%d released=%d absorbed=%d；非自然全局路线",
        s.id, startMass, s.mass, w.stats.totalReleased - beforeReleased, w.stats.totalAbsorbed - beforeAbsorbed))
    conservation(w)
end

---@param game GameScene
local function verifyAutonomousInfection(game)
    local w = game.sim.world
    w:SetAim(1, 0)
    keyDown(KEY_SPACE)
    V.assert(#w.swarms == 2 and w.stats.totalSplits == 1 and w.stats.totalAutoSplits == 0,
        "仅一次真实手动分离建立自主群，后续感染不输入移动/吸附/分离")
    local autonomous = w.swarms[2]
    local controlId, mainId = w.currentControlledSwarmId, assert(w:MainSwarm()).id
    -- 局部位置夹具：左支气管普通细胞，主群/开局节点/免疫在远处。
    placeSwarm(w, w.player, 18.0, 27.8)
    placeSwarm(w, autonomous, 7.8, 19.9)
    moveImmunesFar(w)
    local neverTouched = {}
    for _, c in ipairs(w.cells) do
        if c.regionId == 3 and c.state == "HEALTHY" and not c.everPlayerContact
            and not autonomous.exposedCells[c.id] then neverTouched[c.id] = true end
    end
    V.assert(next(neverTouched) ~= nil, "自主感染候选为真实健康/从未手动接触胞，不预填exposedCells")
    local x, y, infectedBefore = autonomous.x, autonomous.y, w.stats.totalInfected
    local sawIntent, completed = false, false
    for _ = 1, 5400 do
        game.sim:Update(Config.Gameplay.movementStep)
        if autonomous.aiState == "seek" or autonomous.aiState == "infect" then sawIntent = true end
        for _, c in ipairs(w.cells) do
            if neverTouched[c.id] and c.state == "LATENT" and autonomous.exposedCells[c.id] then
                V.assert(c.groupContribution > 0 and c.releasedContribution == 0 and c.infectedVisualAt ~= nil,
                    "新健康胞经真实群接触累计成为潜伏，不由游离或手造病程感染")
                naturalInfectedCellId, completed = c.id, true
                break
            end
        end
        if completed or game.sim.ending then break end
    end
    V.assert(game.sim:CanAct() and not game.sim.ending, "自主感染仍由存活未结束的真实Sim推进")
    refreshHUD()
    V.assert(completed and sawIntent and w.stats.totalInfected > infectedBefore,
        "无手动输入：默认自主群寻靶/停留并完成从未手动接触的新胞感染")
    V.assert(math.sqrt((autonomous.x - x)^2 + (autonomous.y - y)^2) > 0.08,
        "自主意图作用于真实位置而非只改状态文字")
    V.assert(w.currentControlledSwarmId == controlId and assert(w:MainSwarm()).id == mainId
        and w._inputX == 0 and w._inputY == 0 and not game.sim.touchMove.active,
        "自主感染不抢控制/主群/玩家输入")
    V.assert(w.stats.totalAutoSplits == 0, "未达48的小群不会偷做自动分离")
    print(string.format("[swarm_autonomy_validation] 默认AI局部无输入新目标感染 cell=%d time=%.3f swarm=%d pos=(%.3f,%.3f)",
        naturalInfectedCellId, w.time, autonomous.id, autonomous.x, autonomous.y))
    conservation(w)
end

---@param game GameScene
local function verifyRealImmuneApproachAndFlee(game)
    local w = game.sim.world
    -- 局部坐标布局；先受控不移动，让真实免疫自行锁定/预警/趋近，再真实指针放回自主。
    pointerClick("selectSwarm_2")
    local s = w.player
    placeSwarm(w, s, 7.2, 18.2)
    placeSwarm(w, w.swarms[1], 18.0, 27.8)
    moveImmunesFar(w)
    local immune = w.immunes[1]
    placeImmune(w, immune, 4.5, 18.2)
    local originalDistance = math.sqrt((immune.x - s.x)^2 + (immune.y - s.y)^2)
    local sawLock, sawWarning, sawChase, approached = false, false, false, false
    local mass = s.mass
    for _ = 1, 600 do
        game.sim:Update(Config.Gameplay.movementStep)
        if immune.targetType == "swarm" and immune.targetId == s.id then
            sawLock = sawLock or immune.state == "locked"
            sawWarning = sawWarning or immune.state == "warning"
            sawChase = sawChase or immune.state == "chase"
            local gap = math.sqrt((immune.x - s.x)^2 + (immune.y - s.y)^2)
            if sawChase and originalDistance - gap > 0.18 then approached = true; break end
        end
    end
    V.assert(sawLock and sawWarning and sawChase and approached and s.mass == mass,
        "真实免疫自行锁定→完整预警→chase实际趋近，非手写chase状态或远程扣质量")
    local closeDistance = math.sqrt((immune.x - s.x)^2 + (immune.y - s.y)^2)
    local oldControl = s.id
    refreshHUD()
    pointerClick("selectSwarm_1")
    V.assert(w.currentControlledSwarmId ~= oldControl and not s.isPlayerControlled,
        "真实指针交还前群自主，不用测试代码篡改控制身份")
    local sawFlee, separated, leftContact = false, false, false
    local legalTrajectory = true
    local escapeX, escapeY = s.x, s.y
    for _ = 1, 480 do
        game.sim:Update(Config.Gameplay.movementStep)
        sawFlee = sawFlee or s.aiState == "flee"
        local gap = math.sqrt((immune.x - s.x)^2 + (immune.y - s.y)^2)
        separated = separated or gap > closeDistance + 0.45
        leftContact = leftContact or gap > s.radius + immune.radius + 0.45
        legalTrajectory = legalTrajectory and w.map:Contains(s.x, s.y, s.radius)
        if sawFlee and separated and leftContact then break end
    end
    -- 危险额外2.2米小于免疫遗忘圈；局部逃逸不保证甩掉锁定，不能要求免疫作弊。
    V.assert(sawFlee and separated and leftContact and legalTrajectory and s.mass == mass
        and math.sqrt((s.x - escapeX)^2 + (s.y - escapeY)^2) > 0.45,
        "趋近的真实免疫导致默认AI flee/真实合法逃逸位移/脱离接触且无远程伤害，不保证解除追踪")
    V.assert(w.player == w.swarms[1] and w._inputX == 0 and w._inputY == 0, "逃逸不抢回玩家控制")
    refreshHUD()
    fleeVerified = sawFlee and separated and leftContact and legalTrajectory and s.mass == mass
    print(string.format("[swarm_autonomy_validation] 真实免疫趋近 %.3f->%.3f；AI逃逸 state=%s finalDistance=%.3f time=%.3f",
        originalDistance, closeDistance, s.aiState, math.sqrt((immune.x - s.x)^2 + (immune.y - s.y)^2), w.time))
    conservation(w)
end

-- 每轮起始只布合法位置，使独立分离数量边界可复现；段内群/免疫照常自由运动。
-- 不关AI、不写mergeGrace/launchTimer/autoSplitCooldown、不把局部布局冒充自然群分布。
---@param w SwarmWorld
---@param source SwarmRecord
local function arrangeAutoCycle(w, source)
    local points = { {18.0, 27.8}, {5.5, 16.0}, {6.5, 21.2}, {19.5, 16.5}, {20.5, 21.0},
        {12.9, 10.0}, {13.0, 3.2}, {8.0, 28.0}, {16.0, 28.0}, {9.5, 15.5}, {22.0, 18.3} }
    local index = 0
    for _, s in ipairs(w.swarms) do
        if s ~= source then
            index = index + 1
            local p = assert(points[index], "局部布局容量仅用于本测试十余群，不是生产群数上限")
            placeSwarm(w, s, p[1], p[2])
        end
    end
    placeSwarm(w, source, 7.0, 27.2)
    moveImmunesFar(w)
end

---@param game GameScene
---@param source SwarmRecord
local function autoCycle(game, source)
    local w = game.sim.world
    arrangeAutoCycle(w, source)
    local groups, splits, costs = #w.swarms, w.stats.totalAutoSplits, w.stats.splitCost
    local controlId, mainId = w.currentControlledSwarmId, assert(w:MainSwarm()).id
    V.assert(not source.isPlayerControlled and source.mass < Config.Gameplay.autonomy.splitMass,
        "真实未受控小群先低于默认48阈")
    passiveSupply(game, source, 47)
    V.assert(source.mass == 47 and #w.swarms == groups and w.stats.totalAutoSplits == splits,
        "成熟或未成熟的47质量群都不自动分离；不是无目标假通过")
    -- 以少量真实出生达到48；吸附在world.Update后半，不会在供给函数写mass。
    local matureAt = w.time + source.autoSplitCooldown
    local expectedCost = math.max(1, math.floor(48 * Config.Gameplay.splitCostFraction))
    local worldCooldown, clock = w.splitCooldown, w.time
    passiveSupply(game, source, 48)
    local reacted = w.stats.totalAutoSplits > splits
    if not reacted then
        V.assert(source.mass == 48, "未成熟源真实被动增长到默认阈48，等待自然成熟")
        for _ = 1, 600 do
            game.sim:Update(Config.Gameplay.movementStep)
            if w.stats.totalAutoSplits > splits then reacted = true; break end
        end
    end
    V.assert(reacted and w.stats.totalAutoSplits == splits + 1 and #w.swarms == groups + 1,
        "质量达到48后真实成熟/冷却自然结束，自动分离新增一个群（含第7及以后）")
    V.assert(w.time + Config.Gameplay.movementStep >= matureAt and w.stats.splitCost == costs + expectedCost,
        "自主分离遵守每群成熟/冷却并支付原10%真实成本")
    V.assert(w.currentControlledSwarmId == controlId and assert(w:MainSwarm()).id == mainId,
        "自动分离源/子群都不抢当前控制或主群身份")
    V.assert(math.abs(w.splitCooldown - math.max(0, worldCooldown - (w.time - clock))) < 1e-6,
        "自动分离不占用或重置玩家世界8秒冷却，只随正常时间自然递减")
    local child = w.swarms[#w.swarms]
    V.assert(not child.isPlayerControlled and not child.isMainSwarm
        and source.autoSplitCooldown > 7.9 and child.autoSplitCooldown > 7.9,
        "自主源/子分别重新成熟8秒，不共享玩家冷却")
    autoCycles = autoCycles + 1
    print(string.format("[swarm_autonomy_validation] 自主分离循环=%d groups=%d source=%d child=%d autoSplits=%d time=%.3f playerCD=%.3f sourceCD=%.3f",
        autoCycles, #w.swarms, source.id, child.id, w.stats.totalAutoSplits, w.time, w.splitCooldown, source.autoSplitCooldown))
    conservation(w)
end

---@param game GameScene
local function verifyDynamicListAndTakeover(game)
    local w = game.sim.world
    refreshHUD()
    V.assert(#w.swarms > 6 and slotHighWater == #w.swarms, "真实自动群数越过旧6cap后HUD即时建立第7+动态槽")
    V.assert(text("swarmListTitle") == "群体 " .. #w.swarms .. " · 无数量上限 · 点选控制（Tab 循环）",
        "标题实时无上限文案与群数完全匹配")
    local aiCount = #w.swarms - 1
    V.assert(text("autonomyStatus"):find("自主 " .. aiCount .. " 群", 1, true) ~= nil
        and text("autonomyStatus"):find("48", 1, true) ~= nil and text("autonomyStatus"):find("8", 1, true) ~= nil,
        "autonomyStatus明示实时自主运行数/阈48/每群8秒")
    local slot7 = button("selectSwarm_7")
    local seventh, oldControl = w.swarms[7], w.player
    local oldCooldown = seventh.autoSplitCooldown
    w:SetMovement(1, 0)
    game.sim.touchMove.x, game.sim.touchMove.y, game.sim.touchMove.active = 1, -1, true
    pointerClick("selectSwarm_7")
    V.assert(w.player == seventh and w._inputX == 0 and w._inputY == 0 and not game.sim.touchMove.active,
        "第7动态槽真实指针能接管并清前群运动/触控输入")
    advance(game, 18)
    V.assert(seventh.aiState == "controlled" and seventh.aiTargetCellId == nil
        and seventh.autoSplitCooldown == oldCooldown, "受控群停止自主意图/清目标，其成熟冷却不推进")
    V.assert(oldControl.aiState ~= "controlled" and oldControl.isPlayerControlled == false,
        "切群后前控制群真实恢复默认AI而非继续待机")
    refreshHUD()
    V.assert(button("selectSwarm_7") == slot7 and text("selectSwarm_7"):find("手动", 1, true) ~= nil,
        "第7槽复用原对象并显示实时手动状态后缀")
    local initial = w.currentControlledSwarmId
    local seen = { [initial] = true }
    for _ = 1, #w.swarms do keyDown(KEY_TAB); seen[w.currentControlledSwarmId] = true end
    V.assert(w.currentControlledSwarmId == initial, "Tab无限动态列表按全部活群完整环回")
    for _, s in ipairs(w.swarms) do V.assert(seen[s.id], "Tab遍历第7+的每个真实活群：#" .. s.id) end
    conservation(w)
end

---@param game GameScene
local function verifyPauseAI(game)
    local w = game.sim.world
    refreshHUD()
    pointerClick("observeBtn")
    settleTransitions(game)
    V.assert(game.sim.paused and game.sim.pauseReasons.observation and game.scaleMgr:CurrentScale() == "mouse",
        "真实观察按钮暂停有7+自主群的当前局")
    local before = fingerprint(game.sim)
    game.sim:Update(60)
    keyDown(KEY_TAB)
    for i = 1, slotHighWater do
        local b = button("selectSwarm_" .. i)
        assert(b.props.onClick)(b)
    end
    V.assert(fingerprint(game.sim) == before, "暂停60秒冻结全部AI目标/位置/成熟/冷却/感染/免疫/RNG且拒绝切群")
    pointerClick("observationPlayBtn")
    settleTransitions(game)
    beginSegment(game, "观察返回后默认AI继续")
    V.assert(game.sim.world == w, "返回玩法不替换验证中的真实世界")
    local beforeTime = w.time
    advance(game, 1)
    V.assert(w.time > beforeTime and Config.Gameplay.autonomy.enabled, "解除观察暂停后真实AI固定步恢复，不补跑60秒")
    conservation(w)
end

---@param game GameScene
local function verifyUnlimitedManual(game)
    local w = game.sim.world
    local count, splits, autos = #w.swarms, w.stats.totalSplits, w.stats.totalAutoSplits
    V.assert(count > 6 and w.splitCooldown == 0, "六群以后仍真实手动冷却归零，不因数量禁用")
    placeSwarm(w, w.player, 18.0, 27.8)
    if w.player.mass < Config.Gameplay.splitMinMass then passiveSupply(game, w.player, Config.Gameplay.splitMinMass) end
    V.assert(w:CanSplit(), "真实CanSplit无数量上限，仅质量与冷却门控")
    refreshHUD()
    pointerClick("splitBtn")
    V.assert(#w.swarms == count + 1 and w.stats.totalSplits == splits + 1 and w.stats.totalAutoSplits == autos
        and w.splitCooldown == 8, "真实手动按钮第7+以后照常分离并设置原玩家8秒冷却")
    -- 尚成熟的另一个自主群触发自动分离，验手动冷却正在运行时仍可独立行动。
    ---@type SwarmRecord?
    local ready = nil
    for _, s in ipairs(w.swarms) do
        if not s.isPlayerControlled and s.autoSplitCooldown == 0 and s.mass < 48 then ready = s; break end
    end
    local s = assert(ready, "应有自然成熟的既有自主群，不能清计时伪造")
    autoCycle(game, s)
    V.assert(w.splitCooldown > 0 and w.splitCooldown < 8, "玩家仍在真实手动冷却时，另群自主分离已独立发生")
    refreshHUD()
    conservation(w)
end

---@param game GameScene
local function verifyHighWaterRemoval(game)
    local w = game.sim.world
    refreshHUD()
    local high = slotHighWater
    local last = button("selectSwarm_" .. high)
    local oldCallback = assert(last.props.onClick)
    local doomed = w.swarms[high]
    local second = button("selectSwarm_2")
    local oldSecond = assert(second.props.onClick)
    local nextSecond = w.swarms[3]
    local deleted = w.swarms[2]
    V.assert(doomed ~= w.player and deleted ~= w.player, "移除夹具只伤害非当前群")
    V.assert(w:DamageSwarm(doomed.id, doomed.mass) > 0 and w:DamageSwarm(deleted.id, deleted.mass) > 0,
        "高水位/中间群使用真实伤害生命周期移除，不手删swarms数组")
    refreshHUD()
    V.assert(button("selectSwarm_" .. high) == last and not last:IsVisible() and last:IsDisabled(),
        "数量下降后保留第7+高水位对象但隐藏禁用无对应群槽")
    local before = fingerprint(game.sim)
    oldCallback(last)
    V.assert(fingerprint(game.sim) == before, "保存的末槽旧回调不得控制已移除群")
    oldSecond(second)
    V.assert(w.player == nextSecond and w.player ~= deleted, "旧第二槽回调读最新索引，不缓存已死对象")
    pointerClick("selectSwarm_7")
    V.assert(w.player == w.swarms[7], "真实消亡重排后第7槽仍可实际指针选中正确活群")
    conservation(w)
end

---@param outer Rect4
---@param inner Rect4
---@return boolean
local function fullyInside(outer, inner)
    return inner.w > 0 and inner.h > 0 and inner.x >= outer.x - 1 and inner.y >= outer.y - 1
        and inner.x + inner.w <= outer.x + outer.w + 1 and inner.y + inner.h <= outer.y + outer.h + 1
end

---@param game GameScene
local function screenshotLayout(game)
    refreshHUD()
    local strategy = widget("strategyScroll") --[[@as ScrollView]]
    strategy:SetScroll(0, 0)
    UI.Layout(); strategy:Update(0)
    local view, cw, ch = strategy:GetAbsoluteLayoutForHitTest(), strategy:GetContentSize()
    local screenRect = { x = 0, y = 0, w = UI.GetWidth(), h = UI.GetHeight() }
    V.assert(fullyInside(screenRect, view) and strategy.props.scrollY and not strategy.props.scrollX and cw <= view.w + 1,
        "两分辨率实际策略视窗在屏内，只纵向滚动不横向截断")
    for _, id in ipairs({ "absorbBtn", "splitBtn", "switchBtn", "observeBtn" }) do
        local r = widget(id):GetAbsoluteLayoutForHitTest()
        V.assert(fullyInside(view, r) and r.h >= 39 and r.w >= 82, "顶端真实双行按钮完整可见/尺寸未压扁：" .. id)
    end
    for i = 1, #game.sim.world.swarms do
        local b = button("selectSwarm_" .. i)
        reveal(b)
        V.assert(b:IsVisible() and fullyInside(view, b:GetAbsoluteLayoutForHitTest()), "动态任意第N槽真实可滚动到达：" .. i)
        V.assert(text("selectSwarm_" .. i):find("#" .. game.sim.world.swarms[i].id, 1, true) ~= nil,
            "实时槽文字匹配真实群编号：" .. i)
    end
    -- 各槽/第7+可达与真实指针选择上方已验；最终同图保留无上限标题+自主运行说明。
    reveal(widget("swarmListTitle"))
    local titleRect = widget("swarmListTitle"):GetAbsoluteLayoutForHitTest()
    local _, currentY = strategy:GetScroll()
    strategy:SetScroll(0, currentY + titleRect.y - view.y)
    UI.Layout()
    V.assert(fullyInside(view, widget("swarmListTitle"):GetAbsoluteLayoutForHitTest())
        and fullyInside(view, widget("autonomyStatus"):GetAbsoluteLayoutForHitTest()),
        "最终截图无上限标题与自主计数/阈值说明同在真实视窗内")
    for i = 1, math.min(6, #game.sim.world.swarms) do
        V.assert(fullyInside(view, button("selectSwarm_" .. i):GetAbsoluteLayoutForHitTest()),
            "最终截图前六个真实动态槽可见，不要求所有无限群同时铺满屏幕：" .. i)
    end
    if PlatformUtils.IsDesktopPlatform() and not PlatformUtils.NeedsVirtualJoystick() then
        V.assert(not widget("joystickPanel"):IsVisible(), "桌面小屏不因宽度误启摇杆")
    end
    game:UpdateViewport(game:GetAbsoluteLayout())
    game:UpdateCamera(2)
    print(string.format("[swarm_autonomy_validation] screenshot frame=140 physical=%dx%d DPR=%.2f scale=%.3f base=%.1fx%.1f groups=%d peak=%d controlled=%d content=%.1fx%.1f view=%.1fx%.1f scroll=%.1f autoCycles=%d newCell=%d flee=%s",
        graphics:GetWidth(), graphics:GetHeight(), graphics:GetDPR(), UI.GetScale(), UI.GetWidth(), UI.GetHeight(),
        #game.sim.world.swarms, peakGroups, game.sim.world.player.id, cw, ch, view.w, view.h,
        select(2, strategy:GetScroll()), autoCycles, naturalInfectedCellId, tostring(fleeVerified)))
end

V.atFrame(5, function()
    scene = widget("gameScene") --[[@as GameScene]]
    local game = assert(scene)
    initialFocus, initialMinimized = tostring(input and input.focus), tostring(input and input.minimized)
    V.assert(Config.Gameplay.maxSwarms == nil and Config.Gameplay.autonomy.enabled
        and Config.Gameplay.autonomy.splitMass == 48 and Config.Gameplay.autonomy.splitCooldown == 8
        and Config.Gameplay.autonomy.thinkInterval == 0.25 and Config.Gameplay.splitCooldown == 8,
        "无数量上限；默认真实AI阈48/每群8秒/think.25/玩家8秒不改")
    print("[swarm_autonomy_validation] Linux原生离屏；默认AI局部行为验收，局部位置/供给不等于自然全局路线；非性能验收")
    refreshHUD(); guidedStart(game)
    testedWorld = game.sim.world
    conservation(game.sim.world)
    endSegment(game)
end)

V.atFrame(10, function()
    local game = assert(scene)
    beginSegment(game, "默认AI自主新目标感染")
    verifyAutonomousInfection(game)
    endSegment(game)
end)

V.atFrame(20, function()
    local game = assert(scene)
    beginSegment(game, "真实免疫趋近与默认AI逃逸")
    verifyRealImmuneApproachAndFlee(game)
    endSegment(game)
end)

for cycle = 1, 6 do
    V.atFrame(29 + cycle, function()
        local game = assert(scene)
        beginSegment(game, "默认AI增长与自动无限群循环" .. cycle)
        autoCycle(game, game.sim.world.swarms[2])
        endSegment(game)
    end)
end

V.atFrame(50, function()
    local game = assert(scene)
    beginSegment(game, "无限动态列表第7+真实指针与接管")
    verifyDynamicListAndTakeover(game)
    verifyPauseAI(game)
    verifyUnlimitedManual(game)
    endSegment(game)
end)

V.atFrame(60, function()
    local game = assert(scene)
    beginSegment(game, "第7+高水位动态槽消亡重排")
    verifyHighWaterRemoval(game)
    -- 只为了确定截图镜头：真实存活群合法局部布置，不改半径/保护/群数。
    local w = game.sim.world
    local points = { {9.0,27.2}, {10.5,27.3}, {12.0,27.4}, {13.5,27.5}, {15.0,27.6}, {16.5,27.7}, {11.5,27.8}, {14.0,27.8} }
    for i, s in ipairs(w.swarms) do local p = assert(points[i]); placeSwarm(w, s, p[1], p[2]) end
    refreshHUD(); pointerClick("selectSwarm_7")
    game:UpdateCamera(2)
    endSegment(game)
end)

V.atFrame(100, function() screenshotLayout(assert(scene)) end)

V.atFrame(130, function()
    local game = assert(scene)
    verifyFocus(game, "截图前真实失焦")
    V.assert(game.sim.world == testedWorld and naturalInfectedCellId > 0 and fleeVerified and autoCycles == 7
        and #game.sim.world.swarms > 6 and peakGroups >= 9, "截图前完成默认AI感染/免疫逃逸/自动无限分群/手动>6并保持真实main世界")
    for k, v in pairs(originalConfig) do V.assert(Config.Gameplay[k] == v, "未修改顶层生产配置：" .. k) end
    for k, v in pairs(originalAutonomy) do V.assert(Config.Gameplay.autonomy[k] == v, "默认AI配置始终未修改：" .. k) end
    local w, layout = game.sim.world, game:GetAbsoluteLayout()
    game:UpdateViewport(layout)
    local visible = 0
    for _, s in ipairs(w.swarms) do
        local x, y = game.cellView:WorldToScreen(s.x, s.y, layout, game.scaleMgr:CurrentZoom())
        if x >= game.viewport.x and x <= game.viewport.x + game.viewport.w
            and y >= game.viewport.y and y <= game.viewport.y + game.viewport.h then visible = visible + 1 end
    end
    V.assert(visible >= 3 and widget("gameScene"):IsVisible(), "至少三个真实存活群中心在实际镜头内，不以后台存在或隐藏画布伪造截图")
    V.assert(w.player == w.swarms[7] and math.abs(game.camera.x - w.player.x) < 0.001
        and math.abs(game.camera.y - w.player.y) < 0.001, "真实镜头追踪实际指针选中的第7群")
    conservation(w)
    finished = true
end)

V.atFrame(150, function()
    V.assert(finished, "完成标记只能在完整默认AI验收与截图准备后产生")
    print("[swarm_autonomy_validation] 从未写input.focus，初始focus=" .. initialFocus .. " minimized=" .. initialMinimized
        .. "；范围：真实main/Sim/world/UI适配器，局部布局；非自然全局路线、物理设备事件或性能验收；以JSON及实际PNG判级")
    V.finish()
end)
