-- 纯 Lua 权威能力运行时。UI 只提出请求，不拥有质量、实体或移动计时。
local Config = require("Core.Config")
---@class SwarmAbilityAI
---@field ResetSwarm fun(world:SwarmWorld,swarm:SwarmRecord,resetCooldown:boolean?)
---@field HasDanger fun(world:SwarmWorld,swarm:SwarmRecord):boolean
---@field RestrictCellMotion fun(world:SwarmWorld,swarm:SwarmRecord,tx:number,ty:number):number,number
local AI = require("Core.SplitVirusAI") --[[@as SwarmAbilityAI]]
local Navigation = require("Core.ImmuneNavigation")
local Relay=require("Core.InfectionRelay")
local Particles=require("Core.SwarmParticles")
local A = {}
local function distance(a,b) return math.sqrt((a.x-b.x)^2+(a.y-b.y)^2) end
local function alive(v) return v.state~="ABSORBED" and v.state~="CLEARED" and v.state~="LOST" and v.state~="CONVERTED" end
local function cellById(w,id)
    -- Production IDs match dense array slots. Keep authored/sparse fixtures valid.
    local direct=w.cells[id]
    if direct and direct.id==id then return direct end
    for _,c in ipairs(w.cells) do if c.id==id then return c end end
end
local function unit(x,y)
    local d=math.sqrt(x*x+y*y)
    if d<1e-6 then return nil end
    return x/d,y/d
end

-- 与牵引和指令执行共用条件，校验本身不改变实体、旧意图或冷却。
local function recallable(w,s,v,range)
    return alive(v) and (not v.lifetime or (v.age or 0)<v.lifetime)
        and distance(s,v)<=range and w:_DirectPathClear(v.x,v.y,s.x,s.y,v.radius)
end
local function dispatchable(w,s,other)
    return other.id~=s.id and other.mass>0 and not other.anchored and not other.isHidden
        and not other.relayCellId and (other.rescueUntil or 0)<=w.time
end

function A.Init(w)
    w.abilities={owned={},order={},cooldowns={},requests={},mergeSeedEnabled=false,tailSaved=false}
    w.massLedger={totals={},events={}}
end

function A.Record(w,kind,count,source,target)
    if count<=0 then return end
    w:InvalidateCounts()
    local ledger=w.massLedger
    ledger.totals[kind]=(ledger.totals[kind] or 0)+count
    ledger.events[#ledger.events+1]={time=w.time,kind=kind,count=count,source=source,target=target}
    if #ledger.events>512 then table.remove(ledger.events,1) end
end

function A.Acquire(w,card)
    if not w.abilities.owned[card.id] then
        w.abilities.order[#w.abilities.order+1]=card.id
    end
    w.abilities.owned[card.id]=true
    if card.capacity then w.maxPlayerSwarms=card.capacity end
    if card.localBrain then w.swarmBrainEnabled=true end
    if card.id=="merge_seed" then w.abilities.mergeSeedEnabled=true end
end

function A.Owned(w,id) return w.abilities and w.abilities.owned[id]==true end
function A.Config(id) return Config.CardAbilities[id] or {} end

-- 投入与清除分别记账。返回真实移除的粒子，调用者只据此产生游离实体。
function A.TakeMass(w,s,count,kind)
    count=math.min(s.mass,math.max(0,math.floor(count)))
    local particles=Particles.Take(w.viruses,s.id,count)
    assert(#particles==count,"群质量与粒子数量不一致")
    s.mass=s.mass-count
    w:_RefreshGroupShape(s)
    A.Record(w,kind,count,s.id)
    return particles
end

function A.SpawnReleased(w,particles,x,y,kind,sourceCell,angles)
    local result={}
    for i,p in ipairs(particles) do
        local angle=angles and angles[i] or (i-1)*math.pi*2/math.max(1,#particles)
        local source=p.swarmId and w:SwarmById(p.swarmId)
        -- 投入型实体从真实吸收圈外沿各方向脱落，沿原地图碰撞出点。
        -- 主动投入的播散单位不被被动回收抵消；E 和离散回收仍可显式收回。
        local radius=sourceCell and sourceCell.radius+w.config.virusRadius+.04
            or source and source.radius+w.config.absorptionExtra+w.config.virusRadius+.04 or .1
        local nx,ny=w.map:Move(x,y,x+math.cos(angle)*radius,y+math.sin(angle)*radius,w.config.virusRadius)
        local v={id=w._nextReleasedId,x=nx,y=ny,vx=math.cos(angle)*.24,vy=math.sin(angle)*.24,
            radius=w.config.virusRadius,variant=p.variant or 1,phase=p.phase or angle,
            sourceCellId=sourceCell and sourceCell.id or 0,sourceRegionId=w.map:RegionAt(nx,ny),
            nodeProduced=sourceCell~=nil and sourceCell.infectionSerial~=nil,
            state="RELEASED",age=0,lifetime=w.config.releasedLifetime,_oldX=nx,_oldY=ny,origin=kind,
            sourceSwarmId=p.swarmId,
            requiresActiveRecovery=kind=="trail" or kind=="decoy" or kind=="merge_seed"}
        w._nextReleasedId=w._nextReleasedId+1
        w.releasedViruses[#w.releasedViruses+1]=v;result[#result+1]=v
    end
    w:Emit("ability_released",{kind=kind,count=#result,x=x,y=y})
    return result
end

function A.Validate(w,id,swarmId,target)
    if target~=nil and type(target)~="table" then return false,"目标格式无效" end
    if not A.Owned(w,id) then return false,"尚未获得此卡" end
    local cfg=A.Config(id)
    if not cfg.targetType then return false,"此卡为被动能力" end
    local s=w:SwarmById(swarmId)
    if not s or s.mass<=0 then return false,"群体已失效" end
    if s.relayCellId then return false,"请先用Tab接管或用E回收接力小队" end
    if s.isHidden and not (id=="node_hide" and target and target.exit) then return false,"藏身期间不能使用" end
    if id~="merge_seed" and (w.abilities.cooldowns[id] or 0)>w.time then return false,string.format("冷却 %.1f秒",w.abilities.cooldowns[id]-w.time) end
    if cfg.massCost and s.mass-cfg.massCost<(cfg.minimumRemainingMass or 0) then return false,"质量不足，需保留"..cfg.minimumRemainingMass.."颗" end
    if id=="emergency_dash" then
        if not s.hasMoveDirection then return false,"先确定移动方向" end
        local x,y=w.map:Move(s.x,s.y,s.x+s.lastMoveX*cfg.speed*w.config.movementStep,
            s.y+s.lastMoveY*cfg.speed*w.config.movementStep,s.radius)
        if (x-s.x)^2+(y-s.y)^2<=1e-10 then return false,"冲刺方向被阻挡" end
    elseif id=="local_flow" then
        local x,y=w.map:FlowAt(s.x,s.y,w.time)
        if x*x+y*y<=1e-10 then return false,"请先进入组织流区域" end
    elseif id=="discrete_recall" then
        local found=false
        for _,v in ipairs(w.releasedViruses) do
            if recallable(w,s,v,s.radius+cfg.range) then found=true;break end
        end
        if not found then return false,"附近没有可牵引的游离病毒" end
    elseif id=="infection_trail" and not s.trailEnabled and s.mass<=cfg.minimumRemainingMass then
        return false,"质量不足，无法留下拖尾病毒"
    end
    if cfg.targetType=="node" or cfg.targetType=="cell" then
        if id=="node_hide" and target and target.exit then
            if not s.isHidden or not s.hiddenCellId then return false,"此群未藏身" end
        else
            local c=cellById(w,target and target.cellId)
            if not c or c.state=="DEAD" then return false,"请选择存活细胞" end
            if cfg.targetType=="node" and c.state~="LATENT" and c.state~="PRODUCTIVE" and c.state~="EXHAUSTED" then return false,"请选择存活感染节点" end
            if distance(s,c)-s.radius-c.radius>cfg.range then return false,"请先靠近目标" end
            if not w:_DirectPathClear(s.x,s.y,c.x,c.y,0) then return false,"目标路径不合法" end
            if id=="membrane_glide" then
                local valid,reason=Relay.Validate(w,s,c)
                if not valid then return false,reason end
            end
            if id=="node_cover" and c.coverUsed then return false,"该节点本局已包覆" end
            if id=="node_takeover" then
                if w:LiveSwarmCount()>=w.maxPlayerSwarms then return false,"群体名额已满" end
                for _,node in ipairs(w.cells) do
                    if node.takeoverReservation then return false,"已有接管预约等待产出" end
                end
                local list=A.BatchViruses(w,c)
                if #list>0 and #list<cfg.minimumMass then return false,"本批病毒不足" end
                if #list==0 and (c.state~="PRODUCTIVE" or (w.config.releaseBatches[c.releaseCount+1] or 0)<cfg.minimumMass) then return false,"当前节点未释放，下一批病毒不足" end
            end
        end
    elseif cfg.targetType=="direction" then
        if not target or type(target.x)~="number" or type(target.y)~="number"
            or target.x~=target.x or target.y~=target.y or not w.map:Contains(target.x,target.y)
            or not unit(target.x-s.x,target.y-s.y) then return false,"请选择合法流向" end
    elseif cfg.targetType=="command" then
        if not target or (target.command~="gather" and target.command~="hold") then return false,"请选择集合或留守" end
        local found=false
        for _,other in ipairs(w.swarms) do
            if dispatchable(w,s,other) then found=true;break end
        end
        if not found then return false,"没有可调度的其他病毒群" end
    end
    if s.rescueUntil and s.rescueUntil>w.time then return false,"正在执行致命脱离" end
    return true,s
end

function A.SetAnchor(w,s,active)
    local before=s.anchored==true
    s.anchored=active
    if before~=active then w:Emit("anchor_changed",{swarmId=s.id,active=active}) end
end

function A.Execute(w,id,swarmId,target,requestId,runId)
    if runId~=w.abilityRunId then return false,"请求不属于本局" end
    if type(requestId)~="string" or w.abilities.requests[requestId] then return false,"请求已失效或已提交" end
    local ok,s=A.Validate(w,id,swarmId,target)
    if not ok then return false,s end
    local cfg=A.Config(id)
    if id=="discrete_recall" then s.recallUntil=w.time+cfg.duration
    elseif id=="emergency_dash" then
        A.SetAnchor(w,s,false);s.glideCellId=nil;s.groupCommand=nil;s.launchTimer=0;s.vx,s.vy=0,0
        s.dashUntil=w.time+cfg.duration;s.dashX,s.dashY=s.lastMoveX,s.lastMoveY
        AI.ResetSwarm(w,s,false)
    elseif id=="shed_decoy" then
        local particles=A.TakeMass(w,s,cfg.massCost,"decoy_investment")
        local released=A.SpawnReleased(w,particles,s.x,s.y,"decoy")
        for _,v in ipairs(released) do v.decoyUntil=w.time+cfg.signalSeconds end
    elseif id=="swarm_anchor" then
        A.SetAnchor(w,s,not s.anchored);s.vx,s.vy=0,0;s.launchTimer=0
        if s.anchored then s.dashUntil=nil;s.glideCellId=nil;s.groupCommand=nil end
        AI.ResetSwarm(w,s,false)
    elseif id=="node_hide" then
        if target.exit then A.ExitHide(w,s)
        else
            s.hiddenCellId=target.cellId;s.isHidden=true;s.vx,s.vy=0,0;s.launchTimer=0
            s.glideCellId=nil;s.trailEnabled=false;A.SetAnchor(w,s,false);s.dashUntil=nil
            s.groupCommand=nil
            w:Emit("hide_enter",{swarmId=s.id,cellId=target.cellId})
            AI.ResetSwarm(w,s,false);w:_RefreshGroups()
        end
    elseif id=="node_cover" then
        local c=cellById(w,target.cellId)
        A.TakeMass(w,s,cfg.massCost,"node_cover_investment")
        w.stats.abilityConsumed=(w.stats.abilityConsumed or 0)+cfg.massCost
        c.coverUsed=true;c.shieldHits=cfg.shieldHits
    elseif id=="node_takeover" then
        local c=cellById(w,target.cellId)
        local list=A.BatchViruses(w,c)
        if #list>=cfg.minimumMass then
            if not A.ConvertBatch(w,c,list) then return false,"当前批次无法接管" end
        else c.takeoverReservation={swarmId=s.id,requestId=requestId} end
    elseif id=="infection_trail" then
        s.trailEnabled=not s.trailEnabled;s.trailDistance=0
    elseif id=="local_flow" then
        local x,y=unit(target.x-s.x,target.y-s.y)
        w.map.flowOverride={x=s.x,y=s.y,ux=x,uy=y,radius=cfg.range,expiresAt=w.time+cfg.duration}
    elseif id=="membrane_glide" then
        Relay.Deploy(w,s,cellById(w,target.cellId),A)
    elseif id=="cluster_dispatch" then
        for _,other in ipairs(w.swarms) do
            if dispatchable(w,s,other) then
                local cellId=other.aiTargetCellId
                local point={x=other._aiMoveX or other.x,y=other._aiMoveY or other.y}
                AI.ResetSwarm(w,other,false)
                -- 显式调度替换旧运动意图；致命脱离仍由 Movement 的优先级保护。
                other.glideCellId=nil;other.dashUntil=nil;other.launchTimer=0
                other.groupCommand={kind=target.command,cellId=cellId,point=point,routeAt=0}
                other.vx,other.vy=0,0
            end
        end
    elseif id=="merge_seed" then w.abilities.mergeSeedEnabled=not w.abilities.mergeSeedEnabled
    else return false,"能力尚未实现" end
    if id~="swarm_anchor" and id~="node_hide" then A.BreakCamouflage(s) end
    w.abilities.requests[requestId]=true
    if id~="merge_seed" then w.abilities.cooldowns[id]=w.time+(cfg.cooldown or 0) end
    w:Emit("skill_used",{cardId=id,swarmId=s.id,requestId=requestId,
        command=target and target.command,cellId=target and target.cellId})
    return true
end

function A.State(w,id,s)
    local cfg=A.Config(id)
    return {owned=A.Owned(w,id),cooldown=math.max(0,(w.abilities.cooldowns[id] or 0)-w.time),
        active=s and ((id=="discrete_recall" and (s.recallUntil or 0)>w.time)
            or (id=="emergency_dash" and (s.dashUntil or 0)>w.time)
            or (id=="swarm_anchor" and s.anchored) or (id=="node_hide" and s.isHidden)
            or (id=="infection_trail" and s.trailEnabled) or (id=="membrane_glide" and s.relayCellId~=nil)
            or (id=="debris_camouflage" and s.camouflaged)) or id=="merge_seed" and w.abilities.mergeSeedEnabled or false,
        used=id=="tail_preserve" and w.abilities.tailSaved or false,
        progress=id=="debris_camouflage" and s and math.min(1,(s.camouflageTime or 0)/A.Config(id).duration) or 0,
        massCost=cfg.massCost or 0,targetType=cfg.targetType,
        remaining=s and id=="discrete_recall" and math.max(0,(s.recallUntil or 0)-w.time)
            or s and id=="emergency_dash" and math.max(0,(s.dashUntil or 0)-w.time) or 0}
end

function A.Update(w,dt)
    local finished={}
    for _,s in ipairs(w.swarms) do
        if s.relayCellId then
            local c=cellById(w,s.relayCellId)
            if not c or (c.state~="HEALTHY" and c.state~="EXPOSED") then finished[#finished+1]=s end
        end
    end
    for _,s in ipairs(finished) do Relay.Release(w,s,"target_invalid",A) end
    for _,c in ipairs(w.cells) do
        if c.state=="PRODUCTIVE" then
            c.pendingProductionElapsed=(c.pendingProductionElapsed or c.productiveTimer or 0)+dt
            local nextCount=w.config.releaseBatches[c.releaseCount+1] or 0
            local count=math.min(nextCount,math.floor(nextCount*c.pendingProductionElapsed/w.config.releaseInterval+1e-9))
            A.SetBudget(w,c,count)
        end
    end
    for _,s in ipairs(w.swarms) do
        if s.dashUntil and w.time>=s.dashUntil then s.dashUntil=nil;s.vx,s.vy=0,0 end
        if s.trailEnabled and s.mass<=A.Config("infection_trail").minimumRemainingMass then s.trailEnabled=false end
        if s.rescueUntil and w.time>=s.rescueUntil then s.rescueUntil=nil;s.vx,s.vy=0,0 end
        -- 在小脑 ThinkWorld 前释放失效留守，避免旧群指令持续禁用自主性。
        A.RefreshGroupCommand(w,s)
    end
    A.RefreshCamouflage(w,dt)
end

-- DEAD 仍是细胞终态；只有尚未被巨噬清理的残骸提供卡牌掩护。
-- dt=0 用于清理当步复核，不累积停留时间、不改写质量或节点病程。
function A.RefreshCamouflage(w,dt)
    if not A.Owned(w,"debris_camouflage") then return end
    local cleared=w._immuneClearedDebris or {}
    local nearby={}
    for _,s in ipairs(w.swarms) do
        if not s.isHidden then
            local cfg=A.Config("debris_camouflage")
            local near=false
            for _,c in ipairs(w:NearbyCells(s.x,s.y,s.radius+cfg.range,nearby)) do
                if c.state=="DEAD" and not cleared[c.id] and distance(s,c)-c.radius-s.radius<=cfg.range then
                    near=true;break
                end
            end
            if not near or (s.camouflageX and math.sqrt((s.x-s.camouflageX)^2+(s.y-s.camouflageY)^2)>cfg.moveThreshold) then
                A.BreakCamouflage(s)
            end
            if near then
                if not s.camouflageX then s.camouflageX,s.camouflageY=s.x,s.y end
                s.camouflageTime=(s.camouflageTime or 0)+dt
                local before=s.camouflaged
                s.camouflaged=s.camouflageTime>=cfg.duration
                if s.camouflaged and not before then w:Emit("camouflage_on",{swarmId=s.id}) end
            end
        end
    end
end

function A.BreakCamouflage(s)
    s.camouflaged=false;s.camouflageTime=0;s.camouflageX,s.camouflageY=nil,nil
end

-- 集合保持玩家指令优先；留守无目标时仍等待，危险或原感染目标失效时解除。
-- 解除后沿用小脑原解锁门槛，绝不为无卡群解锁自主感染或自动使用能力。
function A.RefreshGroupCommand(w,s)
    local command=s.groupCommand
    if not command or command.kind~="hold" or s.isPlayerControlled or s.anchored or s.isHidden then return false end
    ---@type string?
    local reason = nil
    if command.cellId then
        local c=cellById(w,command.cellId)
        if not c or (c.state~="HEALTHY" and c.state~="EXPOSED") or not command.point then reason="target_invalid" end
    end
    if not reason and AI.HasDanger(w,s) then reason="danger" end
    if not reason then return false end
    s.groupCommand=nil;s.vx,s.vy=0,0
    AI.ResetSwarm(w,s,false)
    w:Emit("group_command_released",{swarmId=s.id,command="hold",reason=reason})
    return true
end

function A.ExitHide(w,s)
    s.hiddenCellId=nil;s.isHidden=false;s.vx,s.vy=0,0
    AI.ResetSwarm(w,s,false);w:_RefreshGroups()
    w:Emit("hide_exit",{swarmId=s.id})
end

function A.NodeDeath(w,c,oldState,reason)
    Relay.FinishCell(w,c.id,A)
    local pending=c.pendingProduction or 0
    if oldState=="PRODUCTIVE" and reason=="immune" and A.Owned(w,"rupture_spread") and not c.ruptureSpreadUsed then
        c.ruptureSpreadUsed=true
        local count=math.floor(pending*A.Config("rupture_spread").fraction)
        local particles={}
        for _=1,count do particles[#particles+1]={} end
        A.SpawnReleased(w,particles,c.x,c.y,"rupture",c)
        w.stats.totalReleased=w.stats.totalReleased+count
        pending=pending-count
        A.Record(w,"rupture_transfer",count,c.id)
    end
    A.Record(w,"node_budget_lost",pending,c.id)
    c.pendingProduction,c.pendingProductionElapsed=0,0
    A.CancelTakeover(w,c,"接管预约取消：节点已死亡")
    local occupants={}
    for _,s in ipairs(w.swarms) do if s.hiddenCellId==c.id then occupants[#occupants+1]=s end end
    for _,s in ipairs(occupants) do
        local loss=math.ceil(s.mass*A.Config("node_hide").lossFraction)
        A.TakeMass(w,s,loss,"hide_node_loss")
        w.stats.abilityLoss=(w.stats.abilityLoss or 0)+loss
        A.ExitHide(w,s)
    end
end

function A.SetBudget(w,c,count)
    local old=c.pendingProduction or 0
    if count>old then A.Record(w,"node_production",count-old,c.id) end
    c.pendingProduction=count
end

function A.NormalRelease(w,c,count)
    local pending=c.pendingProduction or 0
    A.Record(w,"node_production",math.max(0,count-pending),c.id)
    c.pendingProduction,c.pendingProductionElapsed=0,0
end

function A.ImmuneDamage(w,s,count,immune)
    if count<s.mass or not A.Owned(w,"tail_preserve") or w.abilities.tailSaved then return count end
    w.abilities.tailSaved=true
    s.relayCellId=nil -- A saved squad becomes an ordinary escaping swarm.
    local keep=math.min(A.Config("tail_preserve").remaining,s.mass)
    local x,y=unit(s.x-immune.x,s.y-immune.y)
    if not x then x,y=-(s.lastMoveX or 0),-(s.lastMoveY or 1) end
    s.rescueX,s.rescueY=x,y
    s.rescueUntil=w.time+A.Config("tail_preserve").escapeDistance/A.Config("tail_preserve").escapeSpeed
    A.SetAnchor(w,s,false);s.glideCellId=nil;s.groupCommand=nil;s.dashUntil=nil
    AI.ResetSwarm(w,s,false)
    w:Emit("tail_preserved",{swarmId=s.id,remaining=keep})
    w.stats.tailPreservedSwarmId=s.id
    return s.mass-keep
end

function A.OnMerge(w,s)
    if not A.Owned(w,"merge_seed") or not w.abilities.mergeSeedEnabled
        or (w.abilities.cooldowns.merge_seed or 0)>w.time then return end
    local cfg=A.Config("merge_seed")
    local count=math.min(cfg.maxMass,math.floor(s.mass*cfg.fraction),math.max(0,s.mass-cfg.minimumRemainingMass))
    if count<1 then return end
    local particles=A.TakeMass(w,s,count,"merge_seed_investment")
    A.SpawnReleased(w,particles,s.x,s.y,"merge_seed")
    w.abilities.cooldowns.merge_seed=w.time+cfg.cooldown
end

function A.BatchViruses(w,c)
    local result={}
    for _,v in ipairs(w.releasedViruses) do
        if alive(v) and v.sourceCellId==c.id and v.releaseBatchId==c.releaseVisualSequence then result[#result+1]=v end
    end
    return result
end

function A.ConvertBatch(w,c,list)
    local count=A.Config("node_takeover").minimumMass
    if #list<count or w:LiveSwarmCount()>=w.maxPlayerSwarms or c.state=="DEAD" then return false end
    local first=list[1]
    local new=w:_CreateSwarm(first.x,first.y,0,false)
    for i=1,count do
        local v=list[i];v.state="CONVERTED";w:_AddParticles(new,1,v);new.mass=new.mass+1
    end
    new.mergeGrace=w.config.mergeGraceSeconds
    w:_RefreshGroupShape(new);w:_RefreshGroups()
    A.Record(w,"node_takeover_transfer",count,c.id,new.id)
    w:Emit("node_takeover",{cellId=c.id,swarmId=new.id,count=count})
    return true
end

function A.AfterRelease(w,c)
    local reservation=c.takeoverReservation
    if not reservation then return end
    local source=w:SwarmById(reservation.swarmId)
    if not source or source.isHidden or not A.ConvertBatch(w,c,A.BatchViruses(w,c)) then
        A.CancelTakeover(w,c,"接管预约取消：名额已满、来源失效或本批病毒不足")
    else c.takeoverReservation=nil end
end

function A.CancelTakeover(w,c,reason)
    if not c.takeoverReservation then return end
    c.takeoverReservation=nil
    w.abilities.cooldowns.node_takeover=nil
    w:Emit("skill_failed",{cardId="node_takeover",reason=reason})
end

function A.AfterMovement(w,s,ox,oy,activeDistance)
    if not s.trailEnabled or activeDistance<=0 then return end
    local cfg=A.Config("infection_trail")
    local previous=s.trailDistance or 0
    s.trailDistance=previous+activeDistance
    local nextAt=cfg.distancePerVirus-previous
    while s.trailDistance+1e-9>=cfg.distancePerVirus and s.mass>cfg.minimumRemainingMass do
        local t=math.min(1,nextAt/activeDistance)
        local particles=A.TakeMass(w,s,1,"trail_investment")
        local behind=math.atan(oy-s.y,ox-s.x)
        A.SpawnReleased(w,particles,ox+(s.x-ox)*t,oy+(s.y-oy)*t,"trail",nil,{behind})
        s.trailDistance=s.trailDistance-cfg.distancePerVirus;nextAt=nextAt+cfg.distancePerVirus
    end
    if s.mass<=cfg.minimumRemainingMass then s.trailEnabled=false end
end

function A.RecallOwner(w,v)
    local best,gap=nil,math.huge
    for _,s in ipairs(w.swarms) do
        if s.mass>0 and not s.isHidden and (s.recallUntil or 0)>w.time then
            local reach=s.radius+A.Config("discrete_recall").range
            local dx,dy=s.x-v.x,s.y-v.y
            if math.abs(dx)<=reach and math.abs(dy)<=reach then
                local d=math.sqrt(dx*dx+dy*dy)
                -- A farther candidate cannot win. Only sweep walls when it can
                -- replace the nearest legal owner found so far.
                if (d<gap or (d==gap and (not best or s.id<best.id)))
                    and recallable(w,s,v,reach) then best,gap=s,d end
            end
        end
    end
    v.tractionOwnerId=best and best.id or nil
    return best,gap
end

function A.Movement(w,s,dx,dy,speed,dt)
    if s.anchored then
        if s.isPlayerControlled and (w._inputX~=0 or w._inputY~=0) then A.SetAnchor(w,s,false);s.vx,s.vy=0,0
        else s.vx,s.vy=0,0;return 0,0,true end
    end
    if (s.rescueUntil or 0)>w.time then return s.rescueX*A.Config("tail_preserve").escapeSpeed,s.rescueY*A.Config("tail_preserve").escapeSpeed,true end
    if (s.dashUntil or 0)>w.time then return s.dashX*A.Config("emergency_dash").speed,s.dashY*A.Config("emergency_dash").speed,true end
    if s.relayCellId then s.vx,s.vy=0,0;return 0,0,true end
    if s.groupCommand and not s.isPlayerControlled then
        if A.RefreshGroupCommand(w,s) then return 0,0,false end
        local command=s.groupCommand
        local target
        if command.kind=="gather" then
            target=w:SwarmById(w.currentControlledSwarmId)
            if not target or target.isHidden then return 0,0,false end
            if distance(s,target)<=s.radius+target.radius+A.Config("cluster_dispatch").gatherGap then return 0,0,false end
        elseif command.cellId then
            target=command.point
        end
        if not target then return 0,0,false end
        local radius=math.ceil(s.radius*10)/10
        local route=command.route
        local changed=command.routeRadius~=radius or not command.routeX
            or (target.x-command.routeX)^2+(target.y-command.routeY)^2>.25^2
        local moved=not command.lastX or (s.x-command.lastX)^2+(s.y-command.lastY)^2>1e-8
        command.stuckFor=moved and 0 or (command.stuckFor or 0)+dt
        command.lastX,command.lastY=s.x,s.y
        if w.time>=(command.routeAt or 0) then
            local blocked=route and #route>0 and not Navigation.Clear(w.map,s,route[1],radius)
            if changed or not route or #route==0 or blocked or command.stuckFor>.6 then
                -- 仅复用地图导航，不查询未知细胞或免疫的全图目标。
                command.route=Navigation.Route(w.map,s,{x=target.x,y=target.y},radius)
                command.routeX,command.routeY,command.routeRadius=target.x,target.y,radius
                command.stuckFor=0
            end
            command.routeAt=w.time+.5
        end
        route=command.route
        if route and #route>0 then
            if distance(s,route[1])<.15 then table.remove(route,1) end
            if #route>0 then
                local x,y=unit(route[1].x-s.x,route[1].y-s.y)
                if x then
                    local tx,ty=AI.RestrictCellMotion(w,s,s.x+x*speed*dt,s.y+y*speed*dt)
                    return (tx-s.x)/dt,(ty-s.y)/dt,false
                end
            end
        end
        return 0,0,false
    end
    return dx,dy,false
end

function A.FinishRelays(w,cellId) Relay.FinishCell(w,cellId,A) end
function A.RecoverRelays(w,collector)
    for _,team in ipairs(Relay.Nearby(w,collector)) do Relay.Release(w,team,"active_recovery",A) end
end
function A.RelayRecoverableMass(w,collector)
    local mass=0;for _,team in ipairs(Relay.Nearby(w,collector)) do mass=mass+team.mass end;return mass
end
function A.RelayPower(w,s) return Relay.Power(w,s) end

A.CellById,A.Alive,A.Unit,A.Distance=cellById,alive,unit,distance
return A
