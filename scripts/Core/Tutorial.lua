-- 连续剧情开场教学；读取真实世界事件，不改感染与产毒时长。
-- 展示/暂停遵循 scaffold-2d.lua，界面由 UI.TutorialOverlay 负责。
local SWITCH_SETTLE_SECONDS = 3
local OUTRO_SECONDS = 6
local SKIP_HOLD_SECONDS = 1.2

---@class TutorialLesson
---@field title string
---@field text string
---@field keys string
---@field pause boolean?
---@field camera string?
---@field chapter integer

---@class Tutorial
---@field sim SimState
---@field active boolean
---@field completed boolean
---@field started boolean
---@field skipTime number
---@field step string
---@field stepTime number
---@field visualTime number
---@field continueRequested boolean
---@field cellId integer?
---@field targetId integer?
---@field immuneId integer?
---@field absorbedBaseline integer
---@field splitBaseline integer
---@field switchBaseline integer
---@field childId integer?
---@field travel number
---@field observedRelease boolean
---@field lesson TutorialLesson
local Tutorial = {}
Tutorial.__index = Tutorial

---@type table<string, TutorialLesson>
local LESSONS = {
    intro = { title = "你，现在是一个流感病毒", text = "这簇温暖的微光，就是你控制的病毒群。\n在这片组织中，寻找细胞，建立感染据点。", keys = "点击屏幕或按 Enter 继续", pause = true, camera = "player", chapter = 1 },
    target = { title = "找到第一枚健康细胞", text = "绿色的膜包围着健康细胞。\n靠近并保持接触，感染进度就会逐渐积累。", keys = "WASD / ↑↓←→ 移动 · 触摸设备使用摇杆", pause = true, camera = "cell", chapter = 2 },
    infect = { title = "靠近，让感染发生", text = "移动到标记细胞的膜边，保持接触。\n感染完成前离开，进度会逐渐消退。", keys = "WASD / 方向键 / 摇杆移动", chapter = 2 },
    wait = { title = "感染据点正在酝酿", text = "感染已经完成，你可以离开这枚细胞。\n潜伏结束后，它会释放新的病毒；这段时间可以探索或感染其他细胞。", keys = "保持正常病程 · 潜伏结束后自动进入下一步", chapter = 3 },
    collect = { title = "把新的病毒聚集起来", text = "跟随边缘的琥珀色三角，找到细胞释放的病毒。\n靠近可以收集，也可以按 E 吸附附近病毒。", keys = "E 吸附 · 触摸设备点击「吸附」", chapter = 4 },
    split = { title = "把一群变成两群", text = "分裂可以让病毒群接触不同细胞。\n先朝希望分出的方向移动，再按 Space。", keys = "Space 分裂 · 需要至少 12 病毒 · 成功一次", chapter = 5 },
    switch = { title = "接管另一群病毒", text = "按 Tab 切换控制，观察哪一群亮起控制标记。\n分群还不会自行寻找目标，需要你分别带到细胞附近。", keys = "Tab 切群 · 触摸设备点击「切群」· 成功一次", chapter = 5 },
    switch_done = { title = "切群成功", text = "你已经接管了另一群病毒。\n可以继续移动，观察这群病毒的控制标记。", keys = "稍作观察 · 即将介绍免疫细胞", chapter = 5 },
    tcell = { title = "这是细胞毒性 T 细胞", text = "它会识别并攻击感染细胞，威胁已经建立的据点。\n感染完成后及时转移，继续寻找其他细胞。", keys = "点击屏幕或按 Enter 继续", pause = true, camera = "immune", chapter = 6 },
    macrophage = { title = "留意巨噬细胞", text = "它会吞噬游离病毒，也会攻击病毒群。\n注意它的警戒和攻击提示，避免贴近。", keys = "点击屏幕或按 Enter 继续", pause = true, camera = "immune", chapter = 6 },
    escape = { title = "把感染带向下一枚细胞", text = "免疫细胞开始行动了。\n带着你控制的病毒群离开原位，寻找新的感染机会。", keys = "镜头已交还给你 · 移动继续", chapter = 7 },
    task = { title = "让感染网络继续发展", text = "左上角记录当前阶段的任务与进度。\n完成条件后，可以选择一张进化卡获得增益；免疫警戒也会随之提升。", keys = "已开放全部操作 · 提示将在几秒后自动收起", chapter = 8 },
}

---@param sim SimState
---@return Tutorial
function Tutorial.New(sim)
    local self = setmetatable({}, Tutorial)
    self.sim = sim
    self.active, self.step = false, "intro"
    self.completed=false
    self.started,self.skipTime=false,0
    self.stepTime, self.visualTime, self.travel = 0, 0, 0
    self.continueRequested, self.observedRelease = false, false
    self.absorbedBaseline, self.splitBaseline, self.switchBaseline = 0, 0, 0
    self.cellId, self.targetId, self.immuneId, self.childId = nil, nil, nil, nil
    self.lesson = LESSONS.intro
    return self
end

---@return RespiratoryCell?
function Tutorial:Cell()
    for _, cell in ipairs(self.sim.world.cells) do
        if cell.id == self.cellId then return cell end
    end
    return nil
end

---@return RespiratoryCell?
function Tutorial:HealthyTarget()
    local w = self.sim.world
    local p = w.player
    ---@type RespiratoryCell?
    local best = nil
    local gap = math.huge
    for _, cell in ipairs(w.cells) do
        if cell.state == "HEALTHY" or cell.state == "EXPOSED" then
            local d = (cell.x-p.x)^2 + (cell.y-p.y)^2
            if d < gap then best, gap = cell, d end
        end
    end
    return best
end

---@param kind string
function Tutorial:SelectImmune(kind)
    local w, nearest = self.sim.world, math.huge
    self.immuneId = nil
    for _, immune in ipairs(w.immunes) do
        if immune.kind == kind then
            local d = (immune.x-w.player.x)^2 + (immune.y-w.player.y)^2
            if d < nearest then self.immuneId, nearest = immune.id, d end
        end
    end
end

---@param step string
function Tutorial:Enter(step)
    self.step, self.stepTime, self.travel = step, 0, 0
    self.lesson = LESSONS[step]
    self.continueRequested = false
    if step == "target" or step == "infect" then
        local cell = self:HealthyTarget()
        self.targetId = cell and cell.id or nil
    elseif step == "collect" then
        -- Baseline was captured before the real release, so same-step absorption
        -- is not lost and never mistaken for collecting an earlier batch.
        self.observedRelease = true
    elseif step == "split" then self.splitBaseline = self.sim.world.stats.totalSplits
    elseif step == "switch" then self.switchBaseline = self.sim.world.controlSwitchCount
    elseif step == "tcell" then self:SelectImmune("tcell")
    elseif step == "macrophage" then self:SelectImmune("macrophage") end
    self.sim:SetPaused("tutorial", self.lesson.pause == true)
    print("[Tutorial] " .. step)
end

---@return boolean
function Tutorial:StartIfNeeded()
    -- Per-run lifecycle only: continuing the same run does not replay its opening.
    if self.started then return false end
    if self.sim.ending then return false end
    self.started=true
    self.active = true
    self.completed=false
    self.sim.world.tutorial = self
    self:Enter("intro")
    return true
end

---@param completed boolean
function Tutorial:Stop(completed)
    if not self.active then return end
    self.active, self.continueRequested = false, false
    self.skipTime=0
    self.completed=completed==true
    self.sim.world.tutorial = nil
    self.sim:SetPaused("tutorial", false)
    if completed then print("[Tutorial] completed") end
end

function Tutorial:Skip()
    if not self.active then return false end
    self:Stop(false)
    print("[Tutorial] skipped for current run")
    return true
end

---@param dt number
---@param held boolean
function Tutorial:UpdateSkip(dt,held)
    if not self.active then self.skipTime=0;return end
    for reason in pairs(self.sim.pauseReasons) do
        if reason~="tutorial" then held=false;break end
    end
    if not held then self.skipTime=0;return end
    if dt~=dt or dt==math.huge or dt==-math.huge then return end
    self.skipTime=self.skipTime+math.max(0,math.min(dt,0.1))
    if self.skipTime+1e-9>=SKIP_HOLD_SECONDS then self:Skip() end
end

function Tutorial:SkipProgress()
    return math.min(1,self.skipTime/SKIP_HOLD_SECONDS)
end

---@param action string
---@return boolean
function Tutorial:Allows(action)
    if not self.active then return true end
    if self.step=="task" then return true end
    if self.lesson.pause then return false end
    if action == "move" then return true end
    if action == "absorb" then return self.step ~= "infect" and self.step ~= "wait" end
    if action == "split" then return self.step == "split" or self.step == "switch" or self.step == "switch_done" or self.step == "escape" end
    if action == "switch" then return self.step == "switch" or self.step == "switch_done" or self.step == "escape" end
    return false
end

---@return boolean
function Tutorial:DeferImmune()
    return self.active and self.step ~= "escape" and self.step ~= "task"
end

---@return boolean
function Tutorial:AllowPassiveCollection()
    if not self.active then return true end
    if self.step == "collect" then return self.stepTime >= 0.6 and self.travel >= 0.04 end
    return self.step == "split" or self.step == "switch" or self.step == "switch_done" or self.step == "escape" or self.step == "task"
end

function Tutorial:Continue()
    if self.active and self.lesson.pause and self.stepTime >= 0.35 then self.continueRequested = true end
end

---@param events table[]
---@param dt number
function Tutorial:Observe(events, dt)
    if not self.active then return end
    local p = self.sim.world.player
    self.travel = self.travel + math.max(0, p.activeMoveDistanceStep or 0)
    for _, event in ipairs(events) do
        local payload = event.payload or {}
        if event.name == "infection_complete" and payload.source == "player" and self.step == "infect" then
            self.cellId = payload.cellId
            self.absorbedBaseline = self.sim.world.stats.totalAbsorbed
            self:Enter("wait")
        elseif event.name == "release_batch" and self.step == "wait" and payload.cellId == self.cellId then
            self:Enter("collect")
        elseif event.name == "split" and self.step == "split" then
            self.childId = payload.swarmId
            self:Enter("switch")
        end
    end
end

---@param dt number
function Tutorial:Update(dt)
    if not self.active then return end
    if self.sim.ending then self:Stop(false); return end
    for reason in pairs(self.sim.pauseReasons) do if reason ~= "tutorial" then return end end
    self.stepTime = self.stepTime + math.max(0, math.min(dt, 0.1))
    self.visualTime = self.visualTime + math.max(0, math.min(dt, 0.1))
    if self.continueRequested then
        self.continueRequested = false
        if self.step == "intro" then self:Enter("target")
        elseif self.step == "target" then self:Enter("infect")
        elseif self.step == "tcell" then self:Enter("macrophage")
        elseif self.step == "macrophage" then self:Enter("escape") end
        return
    end
    if self.step == "collect" and self.stepTime >= 1.2 and self.sim.world.stats.totalAbsorbed > self.absorbedBaseline then
        self:Enter("split")
    elseif self.step == "switch" and self.sim.world.controlSwitchCount > self.switchBaseline then
        self:Enter("switch_done") -- Start the breathing room at the successful switch, not at the prompt.
    elseif self.step == "switch" and self.sim.world:LiveSwarmCount() < 2 then
        self:Enter("split") -- Re-merge is legal; never strand a learner at Tab.
    elseif self.step == "switch_done" and self.stepTime >= SWITCH_SETTLE_SECONDS then
        self:Enter("tcell")
    elseif self.step == "escape" and self.travel >= 0.7 then self:Enter("task")
    elseif self.step == "task" and self.stepTime+1e-9 >= OUTRO_SECONDS then self:Stop(true) end
end

---@return table?
function Tutorial:Target()
    if not self.active then return nil end
    local w = self.sim.world
    if self.step == "intro" then return w.player end
    if self.step == "target" or self.step == "infect" or self.step == "escape" then
        for _, cell in ipairs(w.cells) do
            if cell.id == self.targetId and (cell.state == "HEALTHY" or cell.state == "EXPOSED") then return cell end
        end
        local cell = self:HealthyTarget()
        self.targetId = cell and cell.id or nil
        return cell
    end
    if self.step == "wait" then return self:Cell() end
    if self.step == "collect" then
        ---@type ReleasedVirusRecord?
        local best = nil
        local gap = math.huge
        for _, virus in ipairs(w.releasedViruses) do
            if virus.state ~= "ABSORBED" and virus.state ~= "LOST" and virus.state ~= "CLEARED" then
                local d = (virus.x-w.player.x)^2 + (virus.y-w.player.y)^2
                if d < gap then best, gap = virus, d end
            end
        end
        return best
    end
    if self.step == "switch" then
        for _, swarm in ipairs(w.swarms) do if swarm.id == self.childId then return swarm end end
        return w.player
    end
    if self.step == "tcell" or self.step == "macrophage" then
        for _, immune in ipairs(w.immunes) do if immune.id == self.immuneId then return immune end end
    end
    return nil
end

---@return table?
function Tutorial:CameraFocus()
    if self.active and self.lesson.camera then return self:Target() or self.sim.world.player end
    return nil
end

---@return string
function Tutorial:Detail()
    if self.step == "wait" then
        local cell = self:Cell()
        if cell then
            return string.format("潜伏剩余 %.0f 秒 · 可以离开细胞", math.max(0, self.sim.world.config.latentSeconds-cell.latencyTimer))
        end
    elseif self.step == "split" then return self.sim.world:SplitUnavailableReason() or "准备就绪 · 按 Space 分裂"
    elseif self.step == "collect" and self.sim.world.stats.totalAbsorbed > self.absorbedBaseline then return "收集成功 · 病毒群正在壮大"
    elseif self.step == "collect" and not self:Target() then return "等待下一批释放 · 可以继续探索"
    elseif self.step == "tcell" and not self.immuneId then return "T 细胞尚未进入这片组织 · 留意后续出现的冷色细胞"
    elseif self.step == "macrophage" and not self.immuneId then return "巨噬细胞尚未进入这片组织 · 留意后续出现的免疫细胞" end
    return self.lesson.keys
end

return Tutorial
