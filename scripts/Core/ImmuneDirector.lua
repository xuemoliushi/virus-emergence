-- 免疫协调数据：局部目标的预约、密度、支路巡逻与最后观察位置搜索。
-- 不拥有第二份实体表，也不将全局实体坐标提供给感知/追击。
local Config = require("Core.Config")
local Navigation = require("Core.ImmuneNavigation")
local Ecology = require("Core.LocalEcology")
local Director = {}
local TAU = math.pi*2

function Director.Init(w)
    w.immuneReservations, w.patrolAssignments = {}, {}
    w.immuneWorkOrders={}
    w.virusDensityGroups, w.lastSeenTargets = {}, {}
    w.channelPatrolAssignments = {}
    w.immuneAlarms, w.immuneAlarmAssignments, w.immuneAlarmCooldowns = {}, {}, {}
    w._nextImmuneAlarmId = 1
    w.immuneHotspots,w.immuneCleanupAssignments,w.immuneHotspotCooldowns={},{},{}
    w._nextImmuneHotspotId=1
    w._densityClock, w._channelClock, w._channelCursor = 0, 0, 0
end

function Director.Level(w) return w.activeImmuneAlertLevel or 0 end

-- 选卡后的五秒缓冲结束才提高本阶段兵力；其他起点保留 +2/+4 压力。
function Director.PopulationLimit(w)
    local limit=math.max(0,math.floor(math.min(w.config.immuneMax or 8,Config.ImmuneAlert.maxImmuneUnits)))
    local coverage=w.map.isFlatMap and w.config.immuneCoverage
    if not coverage then return limit end
    local curve=coverage.stagePopulation
    local base=w.immuneStartingCount or curve[1]
    return math.min(limit,curve[math.min(5,math.max(0,math.floor(Director.Level(w))))+1]+math.max(0,base-curve[1]))
end

-- 数值只读取缓冲结束后真正生效的警戒，不提前使用选卡等级。
---@param w SwarmWorld
---@param key string
---@return number?
function Director.BehaviorValue(w,key)
    local behavior=w.config.immuneBehavior
    if not behavior then return nil end
    local curve=behavior.growth and behavior.growth[key]
    if curve then return curve[math.min(5,math.max(0,math.floor(Director.Level(w))))+1] end
    local value=behavior[key]
    return type(value)=="number" and value or nil
end

-- 驻巡范围约束无目标的调查，不限制已经通过本地感知锁定的真实追击。
function Director.InPatrolArea(w,immune,x,y)
    local home=immune.patrolHome
    if not home then return true end
    local radius=w.config.immuneCoverage.patrolRadius
    return w.map:RegionAt(x,y)==home.regionId and (x-home.x)^2+(y-home.y)^2<=radius^2
end

local function areaKey(w,x,y)
    local size = Config.ImmuneAlert.densityGridSize
    return math.floor(x/size)..":"..math.floor(y/size)
end

function Director.TargetKey(w,target)
    if target.targetType=="virus" then return "virus-area:"..areaKey(w,target.x,target.y) end
    return target.targetType..":"..target.id
end

local function slots(target)
    local cfg = Config.ImmuneAlert
    -- 诱饵要能引开所有追群的巨噬，名额与群攻击名额一致。
    if target.targetType=="virus" and target.decoy then return math.max(cfg.virusAreaSlots,cfg.swarmAttackSlots) end
    if target.targetType=="virus" then return cfg.virusAreaSlots end
    if target.targetType=="swarm" then return cfg.swarmAttackSlots end
    return cfg.nodeAttackSlots
end

function Director.Available(w,immune,target)
    local owners = w.immuneReservations[Director.TargetKey(w,target)] or {}
    local count = 0
    for id in pairs(owners) do if id~=immune.id then count=count+1 end end
    if count>=slots(target) then return false end
    local coverage=w.map.isFlatMap and w.config.immuneCoverage
    -- 诱饵与群一样不受驻巡范围和工作区名额限制：追击离开巡区后仍能被引开。
    if coverage and immune.patrolHome and target.targetType~="swarm" and not target.decoy then
        if not Director.InPatrolArea(w,immune,target.x,target.y) then return false end
        local workers=0
        for id,order in pairs(w.immuneWorkOrders) do
            if id~=immune.id and order.kind==immune.kind
                and (order.x-target.x)^2+(order.y-target.y)^2<coverage.workAreaRadius^2 then
                workers=workers+1
                if workers>=coverage.workAreaSlots then return false end
            end
        end
    end
    return true
end

function Director.ScreenAvailable(w,immune,cellId)
    for _,other in ipairs(w.immunes) do
        if other.id~=immune.id and other.kind=="tcell" and other._screenCellId==cellId then return false end
    end
    return true
end

function Director.Release(w,immune)
    for key,owners in pairs(w.immuneReservations or {}) do
        owners[immune.id]=nil
        if not next(owners) then w.immuneReservations[key]=nil end
    end
    w.patrolAssignments[immune.id]=nil
    w.immuneWorkOrders[immune.id]=nil
    w.immuneAlarmAssignments[immune.id]=nil
    immune.respondingToAlarm=false
end

function Director.Reserve(w,immune,target)
    if not Director.Available(w,immune,target) then return false end
    Director.Release(w,immune)
    local key = Director.TargetKey(w,target)
    local owners = w.immuneReservations[key] or {}
    w.immuneReservations[key]=owners
    owners[immune.id]=w.time+Config.ImmuneAlert.reservationTimeout
    w.patrolAssignments[immune.id]=w.map:RegionAt(target.x,target.y)
    if target.targetType~="swarm" then
        w.immuneWorkOrders[immune.id]={kind=immune.kind,x=target.x,y=target.y}
    end
    return true
end

function Director.Remember(w,immune,target)
    local point = { x=target.x,y=target.y,seenAt=w.time,regionId=w.map:RegionAt(target.x,target.y) }
    immune._lastSeen = point
    w.lastSeenTargets[immune.id]=point
end

function Director.Search(w,immune)
    local cfg,point=Config.ImmuneAlert,immune._lastSeen
    if Director.Level(w)<cfg.searchLevel or not point or w.time-point.seenAt>=cfg.searchMemoryDuration then return false end
    -- 同一区短时只有一个搜索者，其余恢复正常巡逻，保留搜索间隙。
    for _,other in ipairs(w.immunes) do
        if other.id~=immune.id and other.state=="search" and other.regionId==point.regionId then return false end
    end
    immune._searchUntil=point.seenAt+cfg.searchMemoryDuration
    immune._searchX,immune._searchY=point.x,point.y
    immune._patrolTimer=0
    return true
end

-- Alarm records contain a fixed location and expiry, never a moving target ID.
-- Only confirmed macrophage encounters/clears call this; old traces do not.
function Director.Alarm(w,immune,x,y)
    local cfg=Config.ImmuneAlert
    if immune.kind~="macrophage" or Director.Level(w)<cfg.alarmLevel then return false end
    local key=areaKey(w,x,y)
    if (immune._alarmReadyAt or 0)>w.time or (w.immuneAlarmCooldowns[key] or 0)>w.time
        or #w.immuneAlarms>=cfg.alarmMaxActive then return false end
    local alarm={id=w._nextImmuneAlarmId,x=x,y=y,untilTime=w.time+cfg.alarmDuration,
        sourceId=immune.id,responders={}}
    w._nextImmuneAlarmId=w._nextImmuneAlarmId+1
    w.immuneAlarms[#w.immuneAlarms+1]=alarm
    w.immuneAlarmCooldowns[key]=w.time+cfg.alarmCooldown
    immune._alarmReadyAt=w.time+cfg.alarmCooldown
    immune.alarmVisibleUntil=w.time+2
    w:Emit("immune_alarm",{immuneId=immune.id,alarmId=alarm.id,x=x,y=y,seconds=cfg.alarmDuration})
    return true
end

-- Sustained local production signal is evidence of activity, not a target lock.
-- Sample actual field updates; decaying old traces cannot accumulate confirmation.
function Director.ObserveActivity(w,immune,dt)
    local cfg=Config.ImmuneAlert
    if immune.kind~="macrophage" then return end
    if Director.Level(w)<cfg.alarmLevel or not w.ecology or immune.state=="processing" then
        immune._activityObservationClock,immune._activityAlarmTimer,immune._activityLastLevel=0,0,nil
        return
    end
    immune._activityObservationClock=(immune._activityObservationClock or 0)+dt
    if immune._activityObservationClock+1e-9<cfg.activityAlarmSampleInterval then return end
    immune._activityObservationClock=0
    local level=Ecology.Sample(w,immune.x,immune.y,"activity")
    local previous=immune._activityLastLevel
    immune._activityLastLevel=level
    if level<cfg.activityAlarmThreshold or previous and level+cfg.activityAlarmFallTolerance<previous then
        immune._activityAlarmTimer=0;return
    end
    immune._activityAlarmTimer=math.min(cfg.activityAlarmSeconds,
        (immune._activityAlarmTimer or 0)+cfg.activityAlarmSampleInterval)
    if immune._activityAlarmTimer+1e-9>=cfg.activityAlarmSeconds and Director.Alarm(w,immune,immune.x,immune.y) then
        immune._activityAlarmTimer=0
        w:Emit("immune_activity_alarm",{immuneId=immune.id,x=immune.x,y=immune.y,signal=level})
    end
end

local function updateAlarms(w)
    local cfg=Config.ImmuneAlert
    local liveAlarms={}
    for i=#w.immuneAlarms,1,-1 do
        local alarm=w.immuneAlarms[i]
        if w.time>=alarm.untilTime or Director.Level(w)<cfg.alarmLevel then table.remove(w.immuneAlarms,i)
        else liveAlarms[alarm.id]=alarm end
    end
    for key,expiry in pairs(w.immuneAlarmCooldowns) do
        if w.time>=expiry then w.immuneAlarmCooldowns[key]=nil end
    end
    for _,immune in ipairs(w.immunes) do
        local assignment=w.immuneAlarmAssignments[immune.id]
        if assignment and (not liveAlarms[assignment.alarmId] or immune.state~="patrol" or immune.targetId) then
            w.immuneAlarmAssignments[immune.id]=nil;assignment=nil
        end
        immune.respondingToAlarm=assignment~=nil
    end
    for _,alarm in ipairs(w.immuneAlarms) do
        local count=0;for _ in pairs(alarm.responders) do count=count+1 end
        local limit=Director.Level(w)>=cfg.alarmCooperationLevel and cfg.alarmCooperationResponders or cfg.alarmResponders
        while count<limit do
            local best,bestDistance=nil,math.huge
            for _,immune in ipairs(w.immunes) do
                local dx,dy=immune.x-alarm.x,immune.y-alarm.y
                local d=math.sqrt(dx*dx+dy*dy)
                local behavior=w.config.immuneBehavior
                local busy=immune.kind=="macrophage" and behavior
                    and (immune.processingLoad or 0)>=behavior.loadCapacity*behavior.selectiveLoadFraction
                if immune.id~=alarm.sourceId and immune.state=="patrol" and not immune.targetId and not busy
                    and not alarm.responders[immune.id] and not w.immuneAlarmAssignments[immune.id]
                    and not w.channelPatrolAssignments[immune.id] and not w.immuneCleanupAssignments[immune.id]
                    and d<=cfg.alarmRadius and d<bestDistance and Director.InPatrolArea(w,immune,alarm.x,alarm.y)
                    and w.map:Contains(alarm.x,alarm.y,immune.radius)
                    and Navigation.Clear(w.map,immune,alarm,immune.radius) then best,bestDistance=immune,d end
            end
            if not best then break end
            alarm.responders[best.id]=true;count=count+1
            w.immuneAlarmAssignments[best.id]={alarmId=alarm.id,x=alarm.x,y=alarm.y,untilTime=alarm.untilTime}
            best.respondingToAlarm=true
            best._screenCellId,best.screenTimer=nil,0
            best.signalInvestigation=false
            w:Emit("immune_alarm_response",{immuneId=best.id,alarmId=alarm.id,x=alarm.x,y=alarm.y})
        end
    end
end

-- A T cell calls this only after its own continuous contact identification.
-- The report carries a stationary area; recipients still discover every target.
function Director.ConfirmHotspot(w,immune,target)
    local cfg=Config.ImmuneAlert
    if Director.Level(w)<cfg.hotspotLevel or immune.kind~="tcell" or not immune.recognized
        or target.targetType~="cell" then return false end
    local key=areaKey(w,target.x,target.y)
    if (immune._hotspotReadyAt or 0)>w.time or (w.immuneHotspotCooldowns[key] or 0)>w.time
        or #w.immuneHotspots>=cfg.hotspotMaxActive then return false end
    for _,point in ipairs(w.immuneHotspots) do
        if (target.x-point.x)^2+(target.y-point.y)^2<(cfg.hotspotRadius*2)^2 then return false end
    end
    local point={id=w._nextImmuneHotspotId,x=target.x,y=target.y,sourceId=immune.id,
        untilTime=w.time+cfg.hotspotDuration}
    w._nextImmuneHotspotId=w._nextImmuneHotspotId+1
    w.immuneHotspots[#w.immuneHotspots+1]=point
    w.immuneHotspotCooldowns[key]=w.time+cfg.hotspotCooldown
    immune._hotspotReadyAt=w.time+cfg.hotspotCooldown
    w:Emit("immune_hotspot_confirmed",{immuneId=immune.id,hotspotId=point.id,x=point.x,y=point.y,seconds=cfg.hotspotDuration})
    return true
end

function Director.EndCleanup(w,immune,reason)
    local duty=w.immuneCleanupAssignments[immune.id]
    if not duty then return end
    for _,point in ipairs(w.immuneHotspots) do if point.id==duty.hotspotId then point.closed=true end end
    w.immuneCleanupAssignments[immune.id]=nil
    immune._cleanupCancelled=true
    w:Emit("immune_hotspot_finished",{immuneId=immune.id,hotspotId=duty.hotspotId,reason=reason})
end

local function updateHotspots(w)
    local cfg=Config.ImmuneAlert
    local active={}
    for i=#w.immuneHotspots,1,-1 do
        local point=w.immuneHotspots[i]
        if w.time>=point.untilTime or Director.Level(w)<cfg.hotspotLevel then table.remove(w.immuneHotspots,i)
        else active[point.id]=point end
    end
    for key,expiry in pairs(w.immuneHotspotCooldowns) do if w.time>=expiry then w.immuneHotspotCooldowns[key]=nil end end
    for _,immune in ipairs(w.immunes) do
        local duty=w.immuneCleanupAssignments[immune.id]
        local behavior=w.config.immuneBehavior
        if duty and (not active[duty.hotspotId] or immune.kind~="macrophage" or immune.state=="processing"
            or behavior and (immune.processingLoad or 0)>=behavior.loadCapacity*behavior.selectiveLoadFraction) then
            Director.EndCleanup(w,immune,not active[duty.hotspotId] and "expired" or "load")
        end
    end
    for _,point in ipairs(w.immuneHotspots) do
        if not point.assignedId and not point.closed then
            local best,bestDistance=nil,math.huge
            for _,immune in ipairs(w.immunes) do
                local d=(immune.x-point.x)^2+(immune.y-point.y)^2
                local behavior=w.config.immuneBehavior
                local available=not behavior or (immune.processingLoad or 0)<behavior.loadCapacity*behavior.selectiveLoadFraction
                if immune.kind=="macrophage" and immune.state=="patrol" and not immune.targetId and available
                    and not w.immuneAlarmAssignments[immune.id] and not w.channelPatrolAssignments[immune.id]
                    and not w.immuneCleanupAssignments[immune.id] and d<=cfg.hotspotRecruitRadius^2 and d<bestDistance
                    and Director.InPatrolArea(w,immune,point.x,point.y)
                    and Navigation.Clear(w.map,immune,point,immune.radius) then best,bestDistance=immune,d end
            end
            if best then
                point.assignedId=best.id
                w.immuneCleanupAssignments[best.id]={hotspotId=point.id,x=point.x,y=point.y,
                    radius=cfg.hotspotRadius,untilTime=point.untilTime,quiet=0,sweepClock=0,sweepIndex=0}
                best.hotspotCleanup=true;best.signalInvestigation=false
                w:Emit("immune_hotspot_assigned",{immuneId=best.id,hotspotId=point.id,x=point.x,y=point.y})
            end
        end
    end
end

function Director.VisibleDensity(w,immune,target,visible,memo)
    if Director.Level(w)<2 then return 0 end
    local key=areaKey(w,target.x,target.y)
    if memo and memo[key]~=nil then return memo[key] end
    local count=0
    for _,virus in ipairs(w.virusDensityGroups[key] or {}) do
        if virus.state~="CLEARED" and virus.state~="LOST" and virus.state~="ABSORBED" and virus.state~="CONVERTED" and visible(virus) then count=count+1 end
        if count>=8 then break end
    end
    local score=count*Config.ImmuneAlert.densityWeight
    if memo then memo[key]=score end
    return score
end

function Director.RegionPenalty(w,immune,target)
    if Director.Level(w)<4 then return 0 end
    local region=w.map:RegionAt(target.x,target.y)
    local count=0
    for id,assigned in pairs(w.patrolAssignments) do
        if id~=immune.id and assigned==region then count=count+1 end
    end
    return count*Config.ImmuneAlert.regionAssignmentPenalty
end

function Director.AttackPoint(w,immune,target)
    local radius=immune.radius+target.radius-0.002
    local base=math.atan(immune.y-target.y,immune.x-target.x)
    local best,bestScore=nil,math.huge
    for i=0,15 do
        local angle=base+i*TAU/16
        local x,y=target.x+math.cos(angle)*radius,target.y+math.sin(angle)*radius
        if w.map:Contains(x,y,immune.radius) and w:_DirectPathClear(x,y,target.x,target.y,0) then
            local score=(x-immune.x)^2+(y-immune.y)^2
            for _,other in ipairs(w.immunes) do
                if other.id~=immune.id then
                    local d=(x-other.x)^2+(y-other.y)^2
                    score=score+0.4/math.max(.01,d)
                end
            end
            if score<bestScore then best,bestScore={x=x,y=y},score end
        end
    end
    return best
end

function Director.Separate(w,dt)
    for _,immune in ipairs(w.immunes) do
        -- 不推动正在蓄力或原地预警的单位，移动者让出攻击站位。
        if immune.state=="patrol" or immune.state=="chase" or immune.state=="search" then
            local dx,dy=0,0
            for _,other in ipairs(w.immunes) do
                if immune.id~=other.id then
                    local x,y=immune.x-other.x,immune.y-other.y
                    local d=math.sqrt(x*x+y*y)
                    local r=immune.radius+other.radius+.12
                    if d<r then
                        if d<1e-6 then local a=immune.id*2.399963; x,y,d=math.cos(a),math.sin(a),1 end
                        dx,dy=dx+x/d,dy+y/d
                    end
                end
            end
            local length=math.sqrt(dx*dx+dy*dy)
            if length>0 then
                local speed=Config.ImmuneAlert.separationSpeed
                immune.x,immune.y=w.map:Move(immune.x,immune.y,immune.x+dx/length*speed*dt,immune.y+dy/length*speed*dt,immune.radius)
            end
        end
    end
end

function Director.Update(w,dt)
    local cfg=Config.ImmuneAlert
    local pending=w.pendingAlertActivation
    if pending then
        pending.remaining=math.max(0,pending.remaining-dt)
        if pending.remaining<=1e-9 then
            w.activeImmuneAlertLevel=pending.level
            w.pendingAlertActivation=nil
            w:Emit("immune_alert_active",{level=pending.level})
            -- 降级调试时及时撤销高等级任务。
            if pending.level<5 then w.channelPatrolAssignments={} end
            for _,immune in ipairs(w.immunes) do
                immune._patrolTimer=0
                if pending.level<cfg.searchLevel and immune.state=="search" then immune.state="patrol" end
                if pending.level<cfg.cellMemoryLevel then
                    immune._cellChecks={};immune._screenCellId=nil;immune.screenTimer=0
                end
            end
        end
    end
    local live={}
    for _,immune in ipairs(w.immunes) do live[immune.id]=true end
    for key,owners in pairs(w.immuneReservations) do
        for id,expiry in pairs(owners) do if not live[id] or expiry<w.time then owners[id]=nil end end
        if not next(owners) then w.immuneReservations[key]=nil end
    end
    for id,point in pairs(w.lastSeenTargets) do
        if not live[id] or w.time-point.seenAt>cfg.searchMemoryDuration then w.lastSeenTargets[id]=nil end
    end
    for id in pairs(w.patrolAssignments) do if not live[id] then w.patrolAssignments[id]=nil end end
    for id in pairs(w.immuneWorkOrders) do if not live[id] then w.immuneWorkOrders[id]=nil end end
    for id,assignment in pairs(w.channelPatrolAssignments) do
        if not live[id] or w.time>=assignment.untilTime then w.channelPatrolAssignments[id]=nil end
    end
    for id in pairs(w.immuneAlarmAssignments) do if not live[id] then w.immuneAlarmAssignments[id]=nil end end
    for id in pairs(w.immuneCleanupAssignments) do if not live[id] then w.immuneCleanupAssignments[id]=nil end end
    updateHotspots(w)
    updateAlarms(w)
    w._densityClock=w._densityClock-dt
    if w._densityClock<=0 then
        w._densityClock=.5
        w.virusDensityGroups={}
        if Director.Level(w)>=2 then
            for _,virus in ipairs(w.releasedViruses) do
                if virus.state~="CLEARED" and virus.state~="LOST" and virus.state~="ABSORBED" and virus.state~="CONVERTED" then
                    local key=areaKey(w,virus.x,virus.y)
                    local group=w.virusDensityGroups[key] or {}
                    w.virusDensityGroups[key]=group; group[#group+1]=virus
                end
            end
        end
    end
    w._channelClock=math.max(0,w._channelClock-dt)
    if Director.Level(w)>=5 and w._channelClock<=0 then
        -- 地图回退：最多派一个现有闲置单位走相邻支路，不堵必经通道，不新增单位。
        for _,immune in ipairs(w.immunes) do
            if immune.state=="patrol" and not immune.targetId and not w.immuneAlarmAssignments[immune.id]
                and not w.immuneCleanupAssignments[immune.id]
                and not w.channelPatrolAssignments[immune.id] then
                local options={}
                for _,channel in ipairs(w.map.channels) do
                    local a,b=channel.connectedRegions[1],channel.connectedRegions[2]
                    if a==immune.regionId or b==immune.regionId then options[#options+1]=a==immune.regionId and b or a end
                end
                if #options>0 then
                    w._channelCursor=w._channelCursor+1
                    local region=w.map.regions[options[(w._channelCursor-1)%#options+1]]
                    if w.map:Contains(region.x,region.y,immune.radius) then
                        w.channelPatrolAssignments[immune.id]={x=region.x,y=region.y,
                            startsAt=w.time+cfg.warningDuration,untilTime=w.time+cfg.warningDuration+cfg.channelPatrolDuration}
                        w:Emit("channel_patrol_warning",{immuneId=immune.id,regionId=region.id,warningSeconds=cfg.warningDuration})
                        break
                    end
                end
            end
        end
        w._channelClock=cfg.channelPatrolInterval
    end
end

return Director
