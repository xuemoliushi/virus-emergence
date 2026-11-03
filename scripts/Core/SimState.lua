-- SimState.lua - 开局、暂停、六阶段任务和不可逆胜负的权威入口。
-- 基于 scaffold-2d.lua 的固定步组织；观察层暂停，不在视图中推进模拟。

local Config = require("Core.Config")
local EventBus = require("Core.EventBus")
local SwarmWorld = require("Core.SwarmWorld")
local CardSystem = require("Core.CardSystem")
local EvolutionTracker = require("Core.EvolutionTracker")
local Abilities = require("Core.AbilityRuntime")
local PerformanceStats = require("Core.PerformanceStats")

---@class MouseState
---@field health number
---@field symptom number
---@field activity number
---@field respiration number
---@field temperature number
---@field weight number

---@class PhaseTask
---@field stage integer
---@field name string
---@field text string
---@field progress number
---@field target number
---@field hint string
---@field detail string
---@field complete boolean
---@field reward string?

---@class SimState
---@field skillSelection table?
---@field skillMenu table?
---@field world SwarmWorld
---@field tutorial Tutorial?
---@field mouse MouseState
---@field task PhaseTask
---@field ending string?
---@field pauseReasons table<string, boolean>
---@field nodeAttacks table<number, table>
local SimState = {}
SimState.__index = SimState


function SimState.New()
    local self=setmetatable({},SimState)
    self:init()
    return self
end

function SimState:init()
    self.tutorial = nil
    PerformanceStats.Reset()
    self.world=SwarmWorld.New("UPPER_AIRWAY")
    self.started=false
    self.selectedStartRegion="UPPER_AIRWAY"
    self.time,self.tickAccum,self.tickCount,self.timeScale=0,0,0,1
    self.droppedSimulationSeconds=0
    self.touchMove={x=0,y=0,active=false}
    self.pauseReasons={selection=true}
    self.paused=true
    self.ending=nil
    self.irreversible=false
    self.globalInflammation,self.globalTissueDamage,self.victoryProgress=0,0,0
    self.peakVirus,self.peakInflammation=0,0
    self.mouse={health=100,symptom=0,activity=1,respiration=1,temperature=37,weight=100}
    self.stats=self.world.stats
    self.regions=self.world.map.regions
    self.stage,self.stageProgress,self.deepTarget=1,0,2
    self.independentDone,self.nodeEscapeDone,self.deepReached=false,false,false
    self.respirationLowSeconds=0
    self.nodeAttacks={}
    self.cards = CardSystem.New()
    self.world.abilityRunId=self.cards.runId
    self.skillRequestSerial=0
    self.skillSelection=nil
    self.skillMenu=nil
    self.skillMessage=""
    self.evolution = EvolutionTracker.New()
    self.victoryQualified, self.debugRun, self.formalFinished = false, false, false
    ---@type string?
    self.cardChoiceError = nil
    self.cardTimeline = {}
    self.flowTimeline={}
    self.experience={active=0,choice=0,tutorial=0,pause=0}
    self.lastFlowProgress=""
    self.obtainedCards = self.cards.acquired
    ---@type table?
    self.cardNotice = nil
    self.triggeredCardEvents={}
    self.task=self.evolution:Status(self.world,false)
    print("[SimState] 等待选择起始区域；六阶段完成后自动三选一")
end

function SimState:StartRun(startType,reuseInitialWorld)
    local valid=false
    for _,def in ipairs(Config.StartRegions) do if def.type==startType then valid=true end end
    if not valid then return false end
    if self.tutorial then self.tutorial:Stop(false); self.tutorial = nil end
    PerformanceStats.Reset()
    if not (reuseInitialWorld and not self.started and self.world and self.world.time==0 and self.world.startType==startType) then
        self.world=SwarmWorld.New(startType)
    end
    self.selectedStartRegion=startType
    self.started=true
    self.ending=nil
    self.pauseReasons={}
    self.paused=false
    self.irreversible=false
    self.time,self.tickAccum,self.tickCount,self.timeScale=0,0,0,1
    self.droppedSimulationSeconds=0
    self.cards = CardSystem.New()
    self.world.abilityRunId=self.cards.runId
    self.skillRequestSerial=0
    self.skillSelection=nil
    self.skillMenu=nil
    self.skillMessage=""
    self.evolution = EvolutionTracker.New()
    self.victoryQualified, self.debugRun, self.formalFinished = false, false, false
    ---@type string?
    self.cardChoiceError = nil
    self.cardTimeline = {}
    self.flowTimeline={}
    self.experience={active=0,choice=0,tutorial=0,pause=0}
    self.lastFlowProgress=""
    self.obtainedCards = self.cards.acquired
    self.cardNotice = nil
    self.touchMove.x,self.touchMove.y,self.touchMove.active=0,0,false
    self.mouse={health=100,symptom=0,activity=1,respiration=1,temperature=37,weight=100}
    self.globalInflammation,self.globalTissueDamage,self.victoryProgress=0,0,0
    self.stats,self.regions=self.world.stats,self.world.map.regions
    self.stage,self.stageProgress=1,0
    local depth=self.world.map:DepthAt(self.world.player.x,self.world.player.y)
    self.deepTarget=math.min(4,depth+1)
    self.deepReached=depth>=4
    self.independentDone,self.nodeEscapeDone=false,false
    self.respirationLowSeconds=0
    self.peakVirus,self.peakInflammation=self.world.player.mass,0
    self.nodeAttacks,self.triggeredCardEvents={},{}
    self.evolution:Enter(1,0,self.world)
    self:RecordFlow("start")
    self:UpdateTasks()
    EventBus.Emit(EventBus.Events.SIM_RESET,{startType=startType})
    print("[SimState] 开始呼吸道感染网络，目标局长15～20分钟（数值待实机调校）")
    return true
end

function SimState:SetPaused(reason,value)
    self.pauseReasons[reason]=value and true or nil
    self.paused=not self.started or next(self.pauseReasons)~=nil
    if self.paused then
        self.skillSelection=nil
        self.skillMenu=nil
        self.world:SetMovement(0,0)
        self.touchMove.x,self.touchMove.y,self.touchMove.active=0,0,false
        self.tickAccum=0 -- 不补跑观察期间的时间。
    end
end

-- Wall-clock frame deltas are kept separate from simulation time (including dropped steps).
function SimState:TrackExperience(dt)
    if not self.started or self.ending or dt~=dt or dt<=0 or dt==math.huge then return end
    local category
    if self.tutorial and self.tutorial.active then category="tutorial"
    elseif self.pauseReasons["settings"] or self.pauseReasons["focus"] then category="pause"
    elseif self.cards.pending or self.cardNotice then category="choice"
    elseif self.paused then category="pause"
    else category="active" end
    self.experience[category]=self.experience[category]+dt
end

function SimState:RecordFlow(kind,reason)
    local w=self.world
    local c=w:GetCountsSnapshot()
    local e=self.experience
    local row={kind=kind,reason=reason or "none",time=w.time,stage=self.evolution.stage,
        experience=e.active+e.choice,active=e.active,choice=e.choice,tutorial=e.tutorial,pause=e.pause,
        infections=w.stats.totalInfected,absorbed=w.stats.totalAbsorbed,productive=c.productive,
        killed=w.stats.totalKilled,lost=w.stats.totalLost,recovery=self.evolution.recoveryCount,
        cards=self.cards.formalCount,seed=w.map.seed,qualified=self.victoryQualified,
        debug=self.debugRun,final=self.formalFinished}
    self.flowTimeline[#self.flowTimeline+1]=row
    print(string.format("[FlowMetrics] kind=%s reason=%s t=%.3f stage=%d cards=%d seed=%d experience=%.3f active=%.3f choice=%.3f tutorial=%.3f pause=%.3f infected=%d absorbed=%d productive=%d killed=%d lost=%d recovery=%d qualified=%s debug=%s final=%s",
        row.kind,row.reason,row.time,row.stage,row.cards,row.seed,row.experience,row.active,row.choice,row.tutorial,row.pause,
        row.infections,row.absorbed,row.productive,row.killed,row.lost,row.recovery,tostring(row.qualified),tostring(row.debug),tostring(row.final)))
end

function SimState:CanAct()
    return self.started and not self.paused and self.ending==nil
end

---@param action string
---@return boolean
function SimState:CanUseAction(action)
    return self:CanAct() and (not self.tutorial or self.tutorial:Allows(action))
end

function SimState:ReportActionDenied(reason)
    EventBus.Emit(EventBus.Events.AUDIO_DENIED,{runId=self.world.abilityRunId,reason=reason})
end

function SimState:FlushAudioEvents()
    local batch={}
    for _,event in ipairs(self.world.events) do
        if event.audio and not event.audioForwarded then
            batch[#batch+1]=event.audio
            event.audioForwarded=true
        end
    end
    if #batch>0 then EventBus.Emit(EventBus.Events.AUDIO_WORLD,{runId=self.world.abilityRunId,events=batch}) end
end

function SimState:Split()
    if not self:CanUseAction("split") then self:ReportActionDenied("split");return false end
    local success=self.world:Split()
    if success then self.skillSelection=nil;self.skillMenu=nil end
    if not success then self:ReportActionDenied("split") end
    self:FlushAudioEvents()
    return success
end

---@return integer
---@return string? reason
function SimState:AbsorbNearby()
    if not self:CanUseAction("absorb") then self:ReportActionDenied("absorb");return 0, "按当前教程步骤操作" end
    local swarm=self.world:SwarmById(self.world.currentControlledSwarmId)
    if not swarm or swarm.mass<=0 or swarm.isHidden then
        self:ReportActionDenied("当前群无法吸附");return 0,"当前群无法吸附"
    end
    local count,reason=self.world:AbsorbNearby()
    if reason then self:ReportActionDenied(reason) end
    self:FlushAudioEvents()
    return count,reason
end

---@param swarmId? integer
---@return boolean
function SimState:SwitchControl(swarmId)
    if not self:CanUseAction("switch") then self:ReportActionDenied("switch");return false end
    local changed = self.world:SwitchControl(swarmId)
    if changed then self.skillSelection=nil;self.skillMenu=nil;self.touchMove.x,self.touchMove.y,self.touchMove.active=0,0,false end
    if not changed then self:ReportActionDenied("switch") end
    self:FlushAudioEvents()
    return changed
end

function SimState:TotalVirus() return self.world:GetCountsSnapshot().virus end

function SimState:GrantCardChoice(reason)
    if not self:CanUseAction("cards") then return false, "当前无法选卡" end
    local ok, result = self.cards:GrantCardChoice(reason, function() return self.world:_Random() end)
    if ok then
        self.cardTimeline[#self.cardTimeline+1]={kind="offer",round=result.round,reason=reason,time=self.time,cards=result.cards}
        local ids={}
        for _,card in ipairs(result.cards) do ids[#ids+1]=card.id end
        print(string.format("[EvolutionTimeline] t=%.3f kind=offer round=%d choice=%s cards=%s",
            self.time,result.round,result.id,table.concat(ids,",")))
        self:SetPaused("card-choice", true)
        self:RecordFlow("offer",result.id)
        EventBus.Emit("cards:choice",result)
    end
    return ok, result
end

function SimState:RequestCardChoice(reason) return self:GrantCardChoice(reason) end
function SimState:ValidateSkill(id,swarmId,target)
    if not self:CanUseAction("skill") then return false,"当前不能使用技能" end
    return Abilities.Validate(self.world,id,swarmId,target)
end
function SimState:UseSkill(id,swarmId,target,requestId,runId)
    if not self:CanUseAction("skill") then self:ReportActionDenied("skill");return false,"当前不能使用技能" end
    if not requestId then self.skillRequestSerial=self.skillRequestSerial+1;requestId="skill:"..self.skillRequestSerial end
    local ok,reason=Abilities.Execute(self.world,id,swarmId,target,requestId,runId or self.cards.runId)
    if not ok then self:ReportActionDenied(reason) end
    self:FlushAudioEvents()
    self.skillMessage=ok and "能力已执行" or tostring(reason)
    return ok,reason
end
function SimState:GetSkillState(id,swarmId)
    return Abilities.State(self.world,id,self.world:SwarmById(swarmId or self.world.currentControlledSwarmId))
end

function SimState:GetEligibleCards(round) return self.cards:GetEligibleCards(round) end

function SimState:CommitCardChoice(choiceId, cardId)
    if not self.started or self.ending or self.cardNotice then return false, "当前无法提交卡牌" end
    local ok, result = self.cards:CommitCardChoice(choiceId, cardId, self.world)
    if ok then
        self.cardNotice = { card = result, choiceId=choiceId, runId=self.world.abilityRunId, level = self.world.immuneAlertLevel,
            formal = self.cards.formalCount > self.evolution.completed and not self.debugRun }
        self.cardTimeline[#self.cardTimeline+1]={kind="acquired",cardId=cardId,level=self.world.immuneAlertLevel,time=self.time}
        print(string.format("[EvolutionTimeline] t=%.3f kind=acquired card=%s alert=%d formal=%s",
            self.time,cardId,self.world.immuneAlertLevel,tostring(self.cardNotice.formal)))
        self:SetPaused("card-alert", true)
        self:SetPaused("card-choice", false)
        self:RecordFlow("card",cardId)
        EventBus.Emit("cards:acquired", self.cardNotice)
    end
    return ok, result
end

function SimState:AcquireTestCard(cardId)
    if not self.started or self.ending or self.cardNotice then return false, "请开始游戏或先确认警戒说明" end
    local ok, choice = self.cards:BeginTestChoice(cardId)
    if not ok then return false, choice end
    self.debugRun = true
    return self:CommitCardChoice(choice.id, cardId)
end

function SimState:ContinueAfterCard()
    local notice=self.cardNotice
    if not notice then return false end
    self.cardNotice = nil
    self:SetPaused("card-alert", false)
    if notice.formal then
        self.evolution.completed=self.evolution.stage
        print(string.format("[EvolutionTimeline] t=%.3f kind=continue completed=%d qualified=%s",
            self.time,self.evolution.completed,tostring(self.victoryQualified)))
        if self.evolution.completed<6 then
            self.evolution:Enter(self.evolution.completed+1,self.time,self.world)
            self:RecordFlow("stage")
            self:UpdateTasks(false)
            EventBus.Emit(EventBus.Events.PHASE_CHANGED,{stage=self.stage,name=self.task.name})
        else
            self.formalFinished=true
            self.evolution:BeginFinal(self.world)
            self:RecordFlow("final")
            self:UpdateTasks(false)
        end
    end
    return true
end

function SimState:SetDebugImmuneAlertLevel(level)
    if not self.started or self.ending then return false end
    return self.world:SetDebugImmuneAlertLevel(level)
end

function SimState:TotalInfected() return self.world:GetCountsSnapshot().infected end
function SimState:TotalInflammation() return self.globalInflammation end
function SimState:TotalDamage() return self.globalTissueDamage end
function SimState:Phase() return self.task.name end
function SimState:CurrentMode() return "gather" end

-- Optional presentation observer; it reads the pose before each actual step.
-- Existing simulation/input callers need no observer.
---@param dt number
---@param beforeStep fun(world:SwarmWorld)?
function SimState:Update(dt, beforeStep)
    if not self:CanAct() then self.tickAccum=0;return end
    if dt~=dt or dt==math.huge or dt==-math.huge then return end
    local cfg=Config.Gameplay
    self.tickAccum=self.tickAccum+math.max(0,math.min(dt,cfg.maxFrameSeconds))*self.timeScale
    local guard=Config.Performance.maxStepsPerFrame
    local budget=(Config.Performance.simulationBudgetMs or 0)/1000
    local started=budget>0 and os.clock() or 0
    local lastCost=0
    while self.tickAccum+1e-9>=cfg.movementStep and guard>0 and self:CanAct() do
        -- Always permit one full step. Avoid spending another equally expensive
        -- step on catch-up when it would exceed this frame's simulation budget.
        if lastCost>0 and budget>0 and os.clock()-started+lastCost>budget then break end
        self.tickAccum=math.max(0,self.tickAccum-cfg.movementStep)
        local stepStarted=budget>0 and os.clock() or 0
        if beforeStep then beforeStep(self.world) end
        self:Tick(cfg.movementStep)
        if budget>0 then lastCost=math.max(0,os.clock()-stepStarted) end
        guard=guard-1
    end
    -- A slow frame cannot trigger another burst of catch-up on the next frame.
    -- Keep the sub-step remainder (including floating-point boundary tolerance).
    if self.tickAccum+1e-9>=cfg.movementStep then
        local dropped=math.floor((self.tickAccum+1e-9)/cfg.movementStep)
        self.tickAccum=math.max(0,self.tickAccum-dropped*cfg.movementStep)
        self.droppedSimulationSeconds=(self.droppedSimulationSeconds or 0)+dropped*cfg.movementStep
    end
    if not self:CanAct() then self.tickAccum=0 end
end

function SimState:Tick(dt)
    if not self:CanAct() then return end
    local previousControl = self.world.currentControlledSwarmId
    self.world:Update(dt)
    if self.world.currentControlledSwarmId ~= previousControl then
        self.skillSelection=nil;self.skillMenu=nil
        self.touchMove.x,self.touchMove.y,self.touchMove.active=0,0,false
    end
    self.time=self.world.time
    self.tickCount=self.tickCount+1
    self.stats=self.world.stats
    self.globalInflammation=self.world.globalInflammation
    self.globalTissueDamage=self.world.globalTissueDamage
    self.peakVirus=math.max(self.peakVirus,self:TotalVirus())
    self.peakInflammation=math.max(self.peakInflammation,self.globalInflammation)
    self:ConsumeEvents()
    self:UpdateMouseDisplay(dt)
    self:CheckOutcome(dt)
    if not self.ending then
        self.evolution:Observe(self.world,dt,self.victoryQualified)
        self:UpdateTasks()
    end
end

function SimState:ConsumeEvents()
    self:FlushAudioEvents()
    if self.tutorial then self.tutorial:Observe(self.world.events, Config.Gameplay.movementStep) end
    self.evolution:Consume(self.world,self.world.events)
    for _,event in ipairs(self.world.events) do
        self.triggeredCardEvents[event.name]=true
        if event.name=="skill_failed" then self.skillMessage=event.payload.reason
        elseif event.name=="tail_preserved" then self.skillMessage="断尾保全已触发：群"..event.payload.swarmId.."剩余"..event.payload.remaining.."颗，请救援" end
    end
    self.independentDone=self.world.stats.independentInfections>0
    self.world.events={}
end

function SimState:UpdateMouseDisplay(dt)
    local cfg=Config.Gameplay
    local inflammation=self.globalInflammation/cfg.irreversibleInflammation
    local damage=self.globalTissueDamage/cfg.irreversibleDamage
    local severity=math.max(inflammation,damage)
    local m=self.mouse
    local target=math.min(1,severity)
    m.symptom=m.symptom+(target-m.symptom)*(1-math.exp(-0.35*dt))
    m.health=math.max(0,100*(1-0.65*damage-0.35*inflammation))
    m.respiration=math.max(0,1-0.55*damage-0.55*inflammation)
    m.activity=math.max(0.05,1-m.symptom*0.9)
    m.temperature=37+m.symptom*2.6
    m.weight=math.max(60,100-m.symptom*28)
    self.victoryProgress=math.max(0,math.min(1,severity))
end

function SimState:UpdateTasks(allowGrant)
    self.task=self.formalFinished and self.evolution:FinalStatus(self.world,self.victoryQualified)
        or self.evolution:Status(self.world)
    self.stage,self.stageProgress=self.task.stage,self.task.progress
    local progressKey=string.format("%d:%s:%d:%d:%s",self.stage,tostring(self.formalFinished),
        self.world.stats.totalInfected,self.evolution.recoveryCount,tostring(self.task.complete))
    if progressKey~=self.lastFlowProgress then
        self.lastFlowProgress=progressKey
        self:RecordFlow(self.task.complete and "complete" or "progress")
    end
    if self.debugRun then self.task.hint="调试局：测试获取不计作正式六轮验收。"
    elseif not self.formalFinished and allowGrant~=false and self.task.complete and self:CanUseAction("cards") and Config.Cards.formalEnabled then
        local ok,reason=self:GrantCardChoice("stage:"..self.stage)
        if not ok then
            self.cardChoiceError=tostring(reason)
            self.task.hint=self.cardChoiceError
        else self.cardChoiceError=nil end
    end
end

function SimState:CheckOutcome(dt)
    local cfg=Config.Gameplay
    if self.mouse.respiration<=cfg.minRespiration then self.respirationLowSeconds=self.respirationLowSeconds+dt
    else self.respirationLowSeconds=0 end
    if self.globalInflammation>=cfg.irreversibleInflammation or self.globalTissueDamage>=cfg.irreversibleDamage
        or self.respirationLowSeconds>=cfg.respirationFailureSeconds then
        if not self.victoryQualified then
            self.victoryQualified=true
            self:RecordFlow("qualified",self.globalInflammation>=cfg.irreversibleInflammation and "inflammation"
                or self.globalTissueDamage>=cfg.irreversibleDamage and "damage" or "respiration")
        end
    end
    -- 正式局必须完成六次选卡；提前达到阈值仍有灭团风险。
    local finalReady=self.formalFinished and self.evolution:FinalStatus(self.world,self.victoryQualified).complete
    if self.victoryQualified and (finalReady or self.debugRun or not Config.Cards.formalEnabled) then
        self.irreversible=true
        self:FinishRun("victory")
    elseif #self.world.swarms==0 or self.world:ControlledCount()==0 then self:FinishRun("extinct") end
end

function SimState:FinishRun(outcome)
    if self.ending or not self.started then return end
    self.ending=outcome
    self:RecordFlow("ending",outcome)
    self.skillSelection=nil;self.skillMenu=nil
    self.world:SetMovement(0,0)
    self.touchMove.x,self.touchMove.y,self.touchMove.active=0,0,false
    if outcome=="victory" then
        self.irreversible=true
        self.victoryProgress=1
        self.stage=6
        self.task.stage,self.task.name,self.task.progress=6,"系统性失控",100
        self.task.text,self.task.target,self.task.hint="不可逆感染达成",100,"本局胜利已锁定。"
        self.mouse.health,self.mouse.respiration=0,0
    end
    print(string.format("[SimState] %s %.1fs 累计感染%d 独立感染%d 炎症%.1f 损伤%.1f",
        outcome,self.time,self.stats.totalInfected,self.stats.independentInfections,
        self.globalInflammation,self.globalTissueDamage))
    EventBus.Emit(EventBus.Events.SIM_ENDING,{outcome=outcome,durationSec=self.time})
end

return SimState
