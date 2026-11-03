local Config = require("Core.Config")
local Tracker = {}
Tracker.__index = Tracker
local NAMES = {"首次产出","回收与感染","多点产毒","继续扩张","扩大感染","最后进化"}

-- 硬性阶段计数：细胞必须在本阶段边界之后才“开始接触”(contactSerial)，
-- 并在之后完成感染，才计入当前阶段。上一阶段已起步的接触、已潜伏或已在产毒的
-- 旧节点都不能把新阶段直接推满，避免选卡后连续完成。
local function snapshot(world,contactBaseline,infectionBaseline)
    local result={infections=0,released=0,carried=0,productive=0,running=0,available=0,supplyNodes=0,healthy=0,pendingRelease=0}
    for _,cell in ipairs(world.cells) do
        -- Infection and first release are permanent facts, independent of current state.
        if (cell.infectionSerial or 0)>(infectionBaseline or 0) and cell.infectionSource~="initial" then
            if (cell.contactSerial or 0)>contactBaseline then
                result.infections=result.infections+1
                if cell.hasReleasedVirus then result.released=result.released+1 end
                if not cell.hasReleasedVirus and (cell.state=="LATENT" or cell.state=="PRODUCTIVE" or cell.state=="EXHAUSTED") then
                    result.pendingRelease=result.pendingRelease+1
                end
            elseif cell.stageCarried then
                result.carried=result.carried+1
            end
        end
        -- 跨阶段接触中的细胞完成后也不计入，不能算作剩余可完成目标；接触中断后重新起步即恢复。
        local carriedContact=cell.stageCarried and cell.contactSerial and cell.contactSerial<=contactBaseline
        if (cell.state=="HEALTHY" or cell.state=="EXPOSED") and not carriedContact then result.healthy=result.healthy+1 end
        if cell.state=="PRODUCTIVE" then result.productive=result.productive+1 end
        if cell.state=="LATENT" or cell.state=="PRODUCTIVE" then result.running=result.running+1 end
        if cell.state=="LATENT" or cell.state=="PRODUCTIVE" or cell.state=="EXHAUSTED" then
            result.supplyNodes=result.supplyNodes+1
        end
    end
    for _,virus in ipairs(world.releasedViruses) do
        if virus.nodeProduced and virus.state~="ABSORBED" and virus.state~="CONVERTED"
            and virus.state~="CLEARED" and virus.state~="LOST" then result.available=1;break end
    end
    return result
end

-- Infection/death is irreversible: never request more new cells than can exist.
local function reachable(desired,earned,remaining)
    return math.min(desired,earned+remaining)
end

local function actionHint(world,counts,fallback)
    local swarm=world:SwarmById(world.currentControlledSwarmId)
    if not swarm then return fallback end
    for _,immune in ipairs(world.immunes) do
        if (immune.x-swarm.x)^2+(immune.y-swarm.y)^2<=world.config.immuneDetectRange^2 then
            return "附近有免疫细胞，先绕开威胁，再寻找健康细胞。"
        end
    end
    if swarm.mass<world.config.densityReference and counts.available>0 then
        return "群内病毒较少，靠近产毒节点，按E吸附病毒后继续感染。"
    end
    for _,cell in ipairs(world.cells) do
        if cell.state=="EXPOSED" and (cell.x-swarm.x)^2+(cell.y-swarm.y)^2
            <=(cell.radius+swarm.radius+world.config.infectionReach)^2 then
            return "正在感染这个细胞，请保持接触，直到感染完成。"
        end
    end
    return fallback
end

function Tracker.New()
    local self=setmetatable({},Tracker)
    self:init()
    return self
end
function Tracker:init()
    self.stage,self.completed=1,0
    self.timeline={}
    self.stageStartInfections,self.stageStartEvent,self.stageStartContact=0,0,0
    self.recoveryDone,self.recoveryCount=false,0
    self.recoveryFallback=false
    self.recoveryStartInfections=0
    self.recoveredViruses={}
    self.latched=false
    self.goalTarget=nil
    self.finalActive,self.finalStartInfections,self.finalStartContact=false,0,0
end

-- 进入阶段时，正在接触中的细胞标记为“跨阶段”：完成后不计本阶段，只用于提示。
local function markCarried(world)
    for _,cell in ipairs(world.cells) do
        cell.stageCarried=(cell.state=="HEALTHY" or cell.state=="EXPOSED") and cell.contactSerial~=nil or nil
    end
end

function Tracker:Enter(stage,time,world)
    self.stage=math.max(1,math.min(6,stage))
    self.stageStartInfections=world and world.stats.totalInfected or 0
    self.stageStartEvent=world and world.eventSerial or 0
    self.stageStartContact=world and world.contactSerial or 0
    if world then markCarried(world) end
    self.recoveryDone,self.recoveryCount=false,0
    self.recoveryFallback=false
    self.recoveryStartInfections=self.stageStartInfections
    self.recoveredViruses={}
    self.latched=false
    self.goalTarget=nil
    self.timeline[#self.timeline+1]={kind="stage",stage=self.stage,time=time}
end
function Tracker:BeginFinal(world)
    self.finalActive=true
    self.finalStartInfections=world.stats.totalInfected
    self.finalStartContact=world.contactSerial or 0
    markCarried(world)
    self.timeline[#self.timeline+1]={kind="final",stage=6,time=world.time,
        infections=world.stats.totalInfected,target=Config.Evolution.victory.newInfections}
end
function Tracker:Consume(world,events)
    if self.finalActive then return end
    if self.stage~=2 or self.recoveryFallback then return end
    for _,event in ipairs(events) do
        local p=event.payload
        if event.name=="absorb" and (event.serial or 0)>self.stageStartEvent
            and p.nodeProduced and (p.method=="basic" or p.method=="recall")
            and p.virusId and not self.recoveredViruses[p.virusId] then
            self.recoveredViruses[p.virusId]=true
            self.recoveryCount=self.recoveryCount+1
            if not self.recoveryDone then
                self.recoveryDone=true
                -- Snapshot at absorption, before later infections in the same step.
                self.recoveryStartInfections=p.infectionBaseline
                self.timeline[#self.timeline+1]={kind="recovery",stage=2,time=event.time,
                    infections=p.infectionBaseline,virusId=p.virusId}
            end
        end
    end
end
function Tracker:Observe(world,dt)
    -- No artificial duration or minimum card interval.
end
local CARRIED_HINT="上一阶段已开始感染的细胞不计入本阶段，请感染新的健康细胞。"

function Tracker:Status(world)
    local cfg=Config.Evolution
    local counts=snapshot(world,self.stageStartContact,
        self.stage==2 and not self.recoveryFallback and self.recoveryStartInfections or self.stageStartInfections)
    local progress,target,text,detail,hint,ready
    if self.stage==1 then
        target=cfg.establish.released
        progress=math.min(target,counts.released)
        ready=counts.infections>=cfg.establish.nodes and progress>=target
        text="感染1个新细胞，等待它释放病毒。"
        detail=string.format("新感染细胞：%d / %d · 首次释放：%d / %d",counts.infections,cfg.establish.nodes,counts.released,target)
        hint=ready and "首次产出已完成，感染成果已保留。"
            or counts.pendingRelease>0 and "感染已完成，等待新节点释放病毒；成功感染的细胞就是感染节点。"
            or counts.infections>0 and "原节点已被清除，请重新感染健康细胞，等待新节点首次释放病毒。"
            or "靠近健康细胞进行感染，感染后的细胞会逐渐开始产毒。"
        if not ready and counts.infections>=cfg.establish.nodes and counts.healthy==0 and counts.pendingRelease==0 then
            -- Every possible new source was lost before release; preserve the real
            -- infection achievement without inventing a release or reviving cells.
            progress,target,ready=1,1,true
            text="可感染细胞已耗尽，结算已完成的感染。"
            detail=string.format("已完成新感染：%d · 剩余可感染细胞：0",counts.infections)
            hint="产毒来源已全部失去，保留真实感染成果并继续进化。"
        end
    elseif self.stage==2 then
        target=cfg.recovery.newInfections
        if not self.recoveryDone and not self.recoveryFallback and counts.supplyNodes==0 and counts.available==0 then
            self.recoveryFallback=true
            counts=snapshot(world,self.stageStartContact,self.stageStartInfections)
            self.timeline[#self.timeline+1]={kind="recovery_fallback",stage=2,time=world.time}
        end
        target=self.goalTarget or reachable(target,counts.infections,counts.healthy)
        progress=(self.recoveryDone or self.recoveryFallback) and math.min(target,counts.infections) or 0
        ready=(self.recoveryDone or self.recoveryFallback) and progress>=target
        text=self.recoveryDone and string.format("再感染%d个新细胞。",target) or "先吸附节点释放的病毒。"
        detail=string.format("回收病毒：%s · 回收后新感染：%d / %d",self.recoveryDone and "已完成" or "未完成",progress,target)
        hint="在产毒节点附近按E吸附病毒，补充群体后继续感染。"
        if self.recoveryFallback then
            text=string.format("感染%d个新细胞，重建感染网络。",target)
            detail=string.format("原产毒来源已失去 · 重建节点：%d / %d",progress,target)
            hint="已切换重建目标，无需等待原节点；感染健康细胞即可继续进化。"
        elseif not self.recoveryDone then
            if counts.available==0 then
                hint=counts.running>0 and "靠近仍在运行的感染节点，等待它释放病毒后按E吸附。"
                    or "先感染一个健康细胞，等待它释放病毒。"
            else hint="寻找节点释放的游离病毒，靠近后按E吸附；空按或被动吸收不计。" end
        end
        if target<cfg.recovery.newInfections then
            text=target==0 and (self.recoveryDone and "回收已完成，剩余感染目标已耗尽。" or self.recoveryFallback
                and "可感染细胞已耗尽，结算重建任务。" or "先吸附节点释放的病毒，感染目标已耗尽。")
                or (self.recoveryDone or self.recoveryFallback) and string.format("再感染%d个新细胞。",target)
                or "先吸附节点释放的病毒。"
            detail=detail.." · 已按剩余可感染细胞调整目标"
        end
    elseif self.stage==3 then
        -- 本阶段新感染的节点各完成首次释放；旧节点即使正在产毒也不计。
        local desired=cfg.production.released
        target=self.goalTarget or reachable(desired,counts.released+counts.pendingRelease,counts.healthy)
        progress=math.min(target,counts.released)
        ready=progress>=target
        text=target>0 and string.format("建立%d个新的产毒节点。",target) or "可产毒节点已耗尽，结算本阶段进化。"
        detail=string.format("本阶段新感染：%d / %d · 已释放病毒：%d / %d",
            math.min(target,counts.infections),target,counts.released,target)
        hint=counts.infections>=target and "新节点已建立，等待它们释放病毒；躲开免疫细胞保护节点。"
            or "感染新的健康细胞；之前的节点不计入，本阶段的新节点释放病毒后才算完成。"
        if target<desired then detail=detail.." · 已按剩余可产毒细胞调整目标" end
    else
        target=self.goalTarget or reachable(cfg.expansion[self.stage],counts.infections,counts.healthy)
        progress=math.min(target,counts.infections)
        ready=progress>=target
        text=self.stage==4 and string.format("再建立%d个感染节点。",target)
            or self.stage==5 and string.format("再感染%d个新细胞。",target)
            or string.format("再感染%d个新细胞，获得最后一张进化卡。",target)
        detail=string.format("本阶段新感染：%d / %d",counts.infections,target)
        hint=self.stage==4 and "绕开免疫细胞，寻找健康细胞继续感染；成功感染的细胞就是感染节点。"
            or self.stage==5 and "从产毒节点补充病毒，利用分群或已获得的能力加快感染。"
            or "运用已经获得的能力，持续扩大感染。"
        if target-progress==1 then hint="再感染1个细胞即可进化。" end
        if target<cfg.expansion[self.stage] then
            if target==0 then text="可感染细胞已耗尽，结算本阶段进化。" end
            detail=detail.." · 已按剩余可感染细胞调整目标"
        end
    end
    if ready and not self.latched then
        self.latched=true
        self.goalTarget=target
        self.timeline[#self.timeline+1]={kind="complete",stage=self.stage,time=world.time}
    end
    if self.latched then progress=target end
    if self.stage~=2 or self.recoveryDone then hint=actionHint(world,counts,hint) end
    if not self.latched and counts.carried>0 and counts.infections==0 and self.stage~=1 then hint=CARRIED_HINT end
    return {stage=self.stage,name=NAMES[self.stage],text=text,progress=progress,target=target,
        detail=detail,hint=hint,reward="完成奖励：进化卡三选一；获得后免疫警戒提升。",
        complete=self.latched and self.completed<self.stage}
end
function Tracker:FinalStatus(world,victoryQualified)
    local goal=Config.Evolution.victory
    local counts=snapshot(world,self.finalStartContact,self.finalStartInfections)
    local added=counts.infections
    local target=reachable(goal.newInfections,added,counts.healthy)
    local minimum=reachable(goal.infections,world.stats.totalInfected,counts.healthy)
    local ready=self.finalActive and added>=target and world.stats.totalInfected>=minimum and victoryQualified
    return {stage=6,name="最后扩张",text=victoryQualified
            and (target==0 and "扩张目标已耗尽，最后扩张已完成。" or string.format("再感染%d个新细胞，完成最后扩张。",target))
            or (target==0 and "扩张目标已耗尽，等待炎症或组织损伤达到失控。" or string.format("再感染%d个新细胞，让炎症或组织损伤达到失控。",target)),
        progress=math.min(target,added),target=target,
        detail=string.format("获卡后新感染：%d / %d · 病理资格：%s",added,target,victoryQualified and "已达到" or "未达到")
            ..(target<goal.newInfections and " · 已按剩余可感染细胞调整目标" or ""),
        hint=(counts.carried>0 and added==0) and CARRIED_HINT or actionHint(world,counts,victoryQualified
            and "病理资格已保留，继续感染完成最后扩张；仍需躲避免疫清除。"
            or "用最后获得的能力继续感染；炎症、损伤或连续呼吸衰竭任一路线达标均有效。"),
        reward="终局任务：完成后触发胜利，不再发放卡牌。",complete=ready}
end
return Tracker
