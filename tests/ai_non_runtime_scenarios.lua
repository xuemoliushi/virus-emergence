-- Non-native acceptance: production v5 map, unchanged Core modules and config.
-- Local scenarios explicitly reposition existing actors; cells/AI are not replaced.
-- Card grants use SimState's test acquisition API, not formal pool acceptance.
local Config=require('Core.Config')
local Sim=require('Core.SimState')
local A=require('Core.AbilityRuntime')
local AI=require('Core.SplitVirusAI')
local Suite={}
local dt=Config.Gameplay.movementStep
local function dist(a,b) return math.sqrt((a.x-b.x)^2+(a.y-b.y)^2) end
local function live(v) return v.state~='CLEARED' and v.state~='LOST' and v.state~='ABSORBED' and v.state~='CONVERTED' end
local function check(ok,name,data)
    ACCEPTANCE_TRACE[#ACCEPTANCE_TRACE+1]={name=name,passed=not not ok,data=data or {}}
    assert(ok,name)
end
local function make(seed)
    ACCEPTANCE_TRACE={}
    Config.Gameplay.mapSeed=seed -- Test seed selection only; no AI/balance overrides.
    local sim=Sim.New();assert(sim:StartRun('UPPER_AIRWAY',true))
    local w=sim.world
    check(w.map.isFlatMap and w.mapGenerationVersion==5 and w.width==120 and w.height==144
        and #w.cells==960 and w.mapSeed==seed,'production_map',
        {seed=seed,version=w.mapGenerationVersion,cells=#w.cells,initial_immunes=#w.immunes})
    return sim,w
end
local function grant(sim,id)
    local ok,reason=sim:AcquireTestCard(id);assert(ok,tostring(reason));sim:ContinueAfterCard()
end
local function pose(w,s,x,y)
    assert(w.map:Contains(x,y,s.radius),'fixture pose outside production geometry')
    s.x,s.y,s.vx,s.vy=x,y,0,0
    if s.mass then s.currentRegionId=w.map:RegionAt(x,y);s.launchTimer=0;w:_UpdateParticles()
    else
        s.regionId=w.map:RegionAt(x,y);s._patrolX,s._patrolY=x,y
        -- Explicit fixture relocation includes its patrol posting. Natural
        -- gameplay never calls this helper or teleports an existing resident.
        if s.patrolHome then s.patrolHome={x=x,y=y,regionId=s.regionId} end
    end
end
local function invariants(w)
    local c=w:Counts();local stats=w.stats;local particles={}
    assert(stats.initialMass+stats.totalReleased-stats.totalKilled-stats.totalLost-stats.splitCost
        -(stats.abilityConsumed or 0)-(stats.abilityLoss or 0)==c.virus,'mass conservation')
    assert(c.groups==#w.swarms and #w.viruses==c.controlled,'group count/particles')
    assert(c.healthy+c.exposed+c.latent+c.productive+c.exhausted+c.dead==960,'cell state partition')
    for _,v in ipairs(w.viruses) do
        assert(w:SwarmById(v.swarmId),'orphan particle')
        particles[v.swarmId]=(particles[v.swarmId] or 0)+1
    end
    for _,n in ipairs(w.ecology and w.ecology.nodes or {}) do
        for _,channel in ipairs({'activity','damage','debris'}) do
            assert(n[channel]==n[channel] and n[channel]>=0 and n[channel]<=w.config.ecology.maxSignal,'bounded signal field')
        end
    end
    for _,c in ipairs(w.cells) do assert((c.antiviralStrength or 0)>=0 and (c.antiviralStrength or 0)<=1,'bounded defense') end
    for _,im in ipairs(w.immunes) do
        assert((im.processingLoad or 0)>=0 and (im.processingLoad or 0)<=w.config.immuneBehavior.loadCapacity,'bounded load')
        assert(not im.recognized or im.kind=='tcell' and im.targetType=='cell' and im.targetId,'recognition ownership')
    end
    assert(#w.immuneHotspots<=Config.ImmuneAlert.hotspotMaxActive,'bounded hotspot count')
    for id,duty in pairs(w.immuneCleanupAssignments) do
        assert(not w.immuneAlarmAssignments[id] and not w.channelPatrolAssignments[id],'conflicting immune jobs')
        assert(duty.quiet>=0 and duty.quiet<=Config.ImmuneAlert.hotspotQuietSeconds+dt,'bounded quiet timer')
    end
    local controlled=0
    for _,s in ipairs(w.swarms) do
        assert(s.mass>0 and particles[s.id]==s.mass and w.map:Contains(s.x,s.y,s.radius),'invalid swarm')
        if s.isPlayerControlled then controlled=controlled+1;assert(s.id==w.currentControlledSwarmId) end
    end
    assert(controlled==(#w.swarms>0 and 1 or 0),'control ownership')
    for _,im in ipairs(w.immunes) do assert(w.map:Contains(im.x,im.y,im.radius),'immune crossed wall') end
    for _,v in ipairs(w.releasedViruses) do if live(v) then assert(w.map:Contains(v.x,v.y,v.radius),'released crossed wall') end end
    for _,cell in ipairs(w.cells) do assert(cell.exposure==cell.exposure and cell.exposure>=0 and cell.exposure<=1,'invalid exposure') end
    for _,owners in pairs(w.brainReservations or {}) do
        for id in pairs(owners) do local s=w:SwarmById(id);assert(s and AI.IsAutonomous(w,s),'stale brain reservation') end
    end
    assert(stats.totalAutoSplits==0,'unexpected auto split')
end
local function steps(w,count)
    for i=1,count do w:Update(dt);if i%60==0 then invariants(w) end end
end
local function macro(w)
    for _,im in ipairs(w.immunes) do if im.kind=='macrophage' then return im end end
    error('production macro missing')
end
local function countEvent(w,name,id)
    local n=0
    for _,e in ipairs(w.events) do
        if e.name==name and (not id or e.payload.cellId==id or e.payload.swarmId==id) then n=n+1 end
    end
    return n
end
local function clearImmune(w,im,x,y)
    require('Core.ImmuneDirector').Release(w,im)
    pose(w,im,x,y);im.state='patrol';im.targetId=nil;im.targetType=nil;im.targetX=nil;im.targetY=nil
    im.cooldown=0;im._route=nil;im._lastSeen=nil;im._searchUntil=0
end
local function stateSignature(w,evolution)
    local parts={}
    local function add(...)
        local values={...}
        for i=1,#values do
            local v=values[i];parts[#parts+1]=type(v)=='number' and string.format('%.17g',v) or tostring(v)
        end
        parts[#parts+1]=';'
    end
    add(w.time,w._rng,w.globalInflammation,w.globalTissueDamage,w.currentControlledSwarmId)
    for _,c in ipairs(w.cells) do add(c.id,c.state,c.exposure,c.latencyTimer,c.productiveTimer,c.releaseCount,c.immuneHits) end
    for _,s in ipairs(w.swarms) do add(s.id,s.x,s.y,s.vx,s.vy,s.mass,s.radius,s.aiState,s.aiTargetCellId or 0,
        s.groupCommand and s.groupCommand.kind or 'none',s.camouflaged==true) end
    for _,im in ipairs(w.immunes) do add(im.id,im.kind,im.x,im.y,im.state,im.targetType or 'none',im.targetId or 0,
        im.warningTimer,im.warningTime,im.attackTimer,im.attackWindup,im.cooldown,
        im.processingLoad,im.recognitionTimer,im.recognized,im.signalInvestigation,im.screenRequiredSeconds or 0) end
    for _,im in ipairs(w.immunes) do
        local home=im.patrolHome
        add(im.dutyRole or 'none',home and home.x or 0,home and home.y or 0,home and home.regionId or 0,im.returningHome==true,im._homeRouteClock or 0)
        for _,p in ipairs(im._homeRoute or {}) do add(p.x,p.y) end
        add(im.id,im.hotspotCleanup==true,im._cleanupCancelled==true,im._hotspotReadyAt or 0)
        add(im._activityObservationClock or 0,im._activityAlarmTimer or 0,im._activityLastLevel or 0)
        local order=w.immuneWorkOrders[im.id]
        if order then add(order.kind,order.x,order.y) end
        local d=w.immuneCleanupAssignments[im.id]
        if d then add(d.hotspotId,d.x,d.y,d.radius,d.untilTime,d.quiet,d.sweepClock,d.sweepIndex,
            d.arrived==true,d.sweepX or 0,d.sweepY or 0) end
    end
    add(w.immuneStartingCount or 0,w._nextImmuneHotspotId)
    for _,p in ipairs(w.immuneHotspots) do add(p.id,p.x,p.y,p.sourceId,p.untilTime,p.assignedId or 0,p.closed==true) end
    local hotspotKeys={};for key in pairs(w.immuneHotspotCooldowns)do hotspotKeys[#hotspotKeys+1]=key end;table.sort(hotspotKeys)
    for _,key in ipairs(hotspotKeys)do add(key,w.immuneHotspotCooldowns[key])end
    for _,v in ipairs(w.releasedViruses) do add(v.id,v.state,v.x,v.y,v.vx,v.vy,v.age) end
    for _,c in ipairs(w.cells) do add(c.id,c.antiviralStimulus,c.antiviralRemaining,c.antiviralStrength) end
    for _,s in ipairs(w.swarms) do add(s.id,s._aiSupplyId,s._aiExploreX,s._aiExploreY,s._aiMoveX,s._aiMoveY) end
    for _,s in ipairs(w.swarms) do
        add(s._aiThinkClock,s._aiWanderClock,s._aiTargetHold,s._aiReservationTimer,s._aiDangerMemory)
        for _,p in ipairs(s._aiVisits or {}) do add(p.x,p.y) end
    end
    add(w.ecology and w.ecology.clock or 0)
    for id,n in ipairs(w.ecology and w.ecology.nodes or {}) do
        local p=w.ecology.pending[id] or {};add(id,n.activity,n.damage,n.debris,p.activity or 0,p.damage or 0,p.debris or 0)
    end
    local keys={};for k in pairs(w.stats) do keys[#keys+1]=k end;table.sort(keys)
    for _,k in ipairs(keys) do add(k,w.stats[k]) end
    if evolution then
        add(evolution.stage,evolution.completed,evolution.latched,evolution.recoveryDone,evolution.recoveryCount)
        local ids={};for id in pairs(evolution.recoveredViruses)do ids[#ids+1]=id end;table.sort(ids)
        for _,id in ipairs(ids)do add(id,evolution.recoveredViruses[id])end
        add(evolution.finalActive,evolution.stageStartInfections,evolution.stageStartEvent,
            evolution.recoveryStartInfections,evolution.finalStartInfections)
    end
    return table.concat(parts,'|')
end
local function openRay(w,origin,length,radius)
    for i=1,48 do
        local angle=i*math.pi*2/48;local x,y=origin.x+math.cos(angle)*length,origin.y+math.sin(angle)*length
        if w.map:Contains(x,y,radius) and w:_DirectPathClear(origin.x,origin.y,x,y,0) then
            return math.cos(angle),math.sin(angle)
        end
    end
    error('production geometry has no legal ray for this fixture')
end

function Suite.Base(seed)
    local sim,w=make(seed);local s=w.player;local im=macro(w)
    local x,y=w.map.spawn.x,w.map.spawn.y;clearImmune(w,im,x,y)
    local ux,uy=openRay(w,im,im.detectionRange+Config.Gameplay.immuneForgetExtra+s.radius+.4,s.radius)
    local cold=im.detectionRange+s.radius+.7
    pose(w,s,x+ux*cold,y+uy*cold);steps(w,1)
    check(not im.targetId and not next(w.abilities.owned),'base_cold_discovery_not_expanded')
    pose(w,s,im.x+ux*(im.detectionRange+s.radius-.3),im.y+uy*(im.detectionRange+s.radius-.3));steps(w,1)
    check(im.targetId==s.id and im.state=='locked','base_real_lock')
    local mass=s.mass
    pose(w,s,im.x+ux*cold,im.y+uy*cold);steps(w,2)
    check(im.targetId==s.id and im.warningTimer>0 and s.mass==mass,'base_retained_without_remote_damage',
        {gap=dist(im,s)-s.radius,warning_remaining=im.warningTimer})
    local far=im.detectionRange+Config.Gameplay.immuneForgetExtra+s.radius+.4
    pose(w,s,im.x+ux*far,im.y+uy*far);steps(w,1)
    check(not im.targetId and not im.targetX and im.state=='patrol','base_forget_limit')
    -- Legal blocked pair found in the current map, not an authored fake wall.
    local found=false;local bx,by=0,0
    for oy=3,w.height-3,2 do
        if found then break end
        for ox=3,w.width-3,2 do
            if found then break end
            if w.map:Contains(ox,oy,math.max(s.radius,im.radius)) then
                for i=1,24 do
                    local a=i*math.pi*2/24;local tx,ty=ox+math.cos(a)*(far-.6),oy+math.sin(a)*(far-.6)
                    if w.map:Contains(tx,ty,s.radius) and not w:_DirectPathClear(ox,oy,tx,ty,0) then
                        clearImmune(w,im,ox,oy);pose(w,s,ox,oy);bx,by=tx,ty;found=true;break
                    end
                end
            end
        end
    end
    assert(found,'no real wall fixture found')
    w.activeImmuneAlertLevel=6 -- Explicit high-alert boundary fixture, no extra entities.
    steps(w,1);assert(im.targetId==s.id)
    local seen=im._lastSeen;pose(w,s,bx,by);steps(w,1)
    check(im.state=='search' and not im.targetId and not im.targetX and im._lastSeen==seen
        and im._searchX==seen.x and im._searchY==seen.y,'VI_search_snapshot_only',
        {last_x=seen.x,last_y=seen.y,blocked_x=bx,blocked_y=by})
    invariants(w)
    return {checks=ACCEPTANCE_TRACE,simulated_seconds=w.time,arrangement='Existing actors repositioned; VI level explicitly selected for blocked-LOS case.'}
end

local function calmContact(w,s,minimumGap)
    local ordered={};for _,c in ipairs(w.cells) do ordered[#ordered+1]=c end
    table.sort(ordered,function(a,b)return dist(a,w.map.spawn)<dist(b,w.map.spawn) end)
    for _,c in ipairs(ordered) do
        if dist(c,w.map.spawn)>5 then break end
        for i=1,36 do
            local a=i*math.pi*2/36;local r=c.radius+s.radius+minimumGap
            local x,y=c.x+math.cos(a)*r,c.y+math.sin(a)*r
            local fx,fy=w.map:FlowAt(x,y,w.time)
            local safe=w.map:Contains(x,y,s.radius) and fx==0 and fy==0
                and w:_DirectPathClear(x,y,c.x,c.y,0)
            for _,other in ipairs(w.cells) do
                if other.id~=c.id and (other.x-x)^2+(other.y-y)^2<(other.radius+s.radius+.025)^2 then safe=false;break end
            end
            if safe then return c,x,y end
        end
    end
    error('no calm legal contact fixture')
end

function Suite.Camouflage(seed)
    local sim,w=make(seed);local s=w.player;local im=macro(w)
    local c,x,y=calmContact(w,s,.8)
    pose(w,s,x,y);w:KillCell(c,'acceptance_fixture')
    -- Existing actors kept alive and active but put beyond local detection until masked.
    local far=w.map.regions[5];pose(w,im,far.x,far.y)
    steps(w,math.ceil(3.1/dt));check(not s.camouflaged,'no_card_has_no_camouflage')
    grant(sim,'debris_camouflage');steps(w,math.ceil(3.1/dt))
    check(s.camouflaged and not w._immuneClearedDebris[c.id],'card_uncleaned_cover_active',{cell_id=c.id})
    clearImmune(w,im,c.x,c.y)
    local completed=false
    for _=1,math.ceil(8/dt) do
        w:Update(dt)
        if w._immuneClearedDebris[c.id] then
            check(not s.camouflaged and s.camouflageTime==0,'card_cleanup_same_step_unmasks',
                {cell_id=c.id,time=w.time,cleanup_events=countEvent(w,'immune_cleanup',c.id)})
            completed=true;break
        end
    end
    check(completed,'real_warning_windup_cleanup_completed')
    steps(w,math.ceil(1/dt))
    check(c.state=='DEAD' and countEvent(w,'immune_cleanup',c.id)==1 and not s.camouflaged,'cleanup_once_without_changing_cell_terminal')
    invariants(w)
    return {checks=ACCEPTANCE_TRACE,simulated_seconds=w.time,arrangement='One real cell killed through KillCell fixture; existing macro repositioned. No AI state or damage timer forced for cleanup.'}
end

function Suite.Commands(seed)
    local sim,w=make(seed);assert(sim:Split());local s=w.swarms[2];local im=macro(w)
    local c,x,y=calmContact(w,s,.12);pose(w,s,x,y)
    local far=w.map.regions[5];pose(w,w.player,far.x,far.y)
    local immuneFar=w.map.regions[4];pose(w,im,immuneFar.x,immuneFar.y)
    for _,other in ipairs(w.immunes) do
        if other.id~=im.id then pose(w,other,immuneFar.x+.8,immuneFar.y) end
    end
    grant(sim,'cluster_dispatch')
    assert(sim:UseSkill('cluster_dispatch',w.player.id,{command='hold'}))
    steps(w,2);check(s.groupCommand and s.groupCommand.kind=='hold' and not AI.IsAutonomous(w,s),'safe_no_brain_hold_waits')
    -- Actual macro decides its warning; only its legal starting position is arranged.
    local ux,uy=openRay(w,s,.8,im.radius);clearImmune(w,im,s.x+ux*.8,s.y+uy*.8)
    local mass=w:ControlledCount();steps(w,1)
    check(not s.groupCommand and not AI.IsAutonomous(w,s) and not s.aiTargetCellId
        and w:ControlledCount()==mass,'danger_release_does_not_grant_brain')
    clearImmune(w,im,immuneFar.x,immuneFar.y);grant(sim,'swarm_local_brain')
    pose(w,s,x,y);steps(w,1)
    check(s.aiTargetCellId~=nil and AI.IsAutonomous(w,s),'brain_real_target_selected')
    local target=assert(A.CellById(w,s.aiTargetCellId))
    assert(sim:UseSkill('cluster_dispatch',w.player.id,{command='hold'}))
    assert(s.groupCommand and s.groupCommand.cellId==target.id)
    local held={x=s.groupCommand.point.x,y=s.groupCommand.point.y,start_x=s.x,start_y=s.y}
    local converted=false
    for i=1,math.ceil(120/dt) do
        w:Update(dt)
        if i%60==0 then invariants(w) end
        if target.state~='HEALTHY' and target.state~='EXPOSED' then converted=true;break end
        assert(s.groupCommand,'calm infection fixture interrupted by another local threat')
    end
    check(converted,'hold_target_converts_by_real_contact',{cell_id=target.id,state=target.state,time=w.time,
        exposure=target.exposure,swarm_x=s.x,swarm_y=s.y,target_x=target.x,target_y=target.y,
        held=held,remaining_command=s.groupCommand and s.groupCommand.kind or 'none',
        releases=countEvent(w,'group_command_released',s.id)})
    steps(w,1)
    check(not s.groupCommand and AI.IsAutonomous(w,s) and countEvent(w,'group_command_released',s.id)==2,
        'target_invalid_releases_whole_command')
    assert(sim:UseSkill('cluster_dispatch',w.player.id,{command='hold'}))
    ux,uy=openRay(w,s,.8,im.radius);clearImmune(w,im,s.x+ux*.8,s.y+uy*.8)
    steps(w,1)
    check(not s.groupCommand and AI.IsAutonomous(w,s) and s.aiState=='flee','brain_hold_resumes_flee')
    clearImmune(w,im,immuneFar.x,immuneFar.y)
    assert(sim:UseSkill('cluster_dispatch',w.player.id,{command='gather'}));steps(w,1)
    check(s.groupCommand and s.groupCommand.kind=='gather','gather_keeps_explicit_intent')
    assert(sim:SwitchControl(s.id));check(not s.groupCommand and s.isPlayerControlled,'player_takeover_clears_command')
    invariants(w)
    return {checks=ACCEPTANCE_TRACE,simulated_seconds=w.time,
        arrangement='Real Split/UseSkill/test card acquisition; actors positioned in calm contact geometry. Infection completed by World.Update; no cell state or AI target forced.'}
end

function Suite.Stress(seed,seconds,withCards,active)
    local sim,w=make(seed)
    if active then seconds=math.max(120,seconds) end
    if withCards then
        grant(sim,'cluster_dispatch');grant(sim,'swarm_local_brain');grant(sim,'debris_camouflage')
    end
    assert(sim:Split())
    local rows={};local autoChoices=0
    local target=nil
    local frames=math.ceil(seconds/dt)
    for i=1,frames do
        -- Public input APIs and unchanged production frame scheduler, one fixed step/frame.
        if sim.cards.pending then
            local p=sim.cards.pending;assert(sim:CommitCardChoice(p.id,p.cards[1].id));sim:ContinueAfterCard();autoChoices=autoChoices+1
        end
        if sim.ending then break end
        if active then
            local player=w.player
            if target and (target.state~='HEALTHY' and target.state~='EXPOSED') then target=nil end
            if not target then
                local best=math.huge
                for _,c in ipairs(w.cells) do
                    local d=dist(player,c)
                    if (c.state=='HEALTHY' or c.state=='EXPOSED') and d<=Config.Gameplay.autonomy.searchRadius
                        and d<best and w:_DirectPathClear(player.x,player.y,c.x,c.y,player.radius) then target,best=c,d end
                end
            end
            if target then
                local dx,dy=target.x-player.x,target.y-player.y;local d=math.sqrt(dx*dx+dy*dy)
                if d>.08 then w:SetMovement(dx/d,dy/d) else w:SetMovement(0,0) end
            else
                local angle=math.floor((i-1)/180)*math.pi*.75;w:SetMovement(math.cos(angle),math.sin(angle))
            end
        else
            local angle=math.floor((i-1)/180)*math.pi*.75
            w:SetMovement(math.cos(angle),math.sin(angle))
        end
        if i%600==1 and i>1 then sim:SwitchControl() end
        sim:Update(dt)
        if i%60==0 then
            invariants(w)
            local c=w:Counts()
            rows[#rows+1]={time=w.time,mass=c.virus,groups=c.groups,nodes=c.infected,killed=w.stats.totalKilled,
                rng=w._rng,immunes=#w.immunes,brain=w.swarmBrainEnabled,alert=w.activeImmuneAlertLevel,
                defense=w.tissueDefenseCount or 0,
                px=w.player and w.player.x or 0,py=w.player and w.player.y or 0}
        end
    end
    invariants(w)
    check(sim.tickCount>0 and (sim.ending~=nil or math.abs(sim.time-seconds)<dt*1.1),'stress_progress_or_natural_end',
        {seconds=sim.time,ending=sim.ending or 'running',ticks=sim.tickCount,dropped=sim.droppedSimulationSeconds})
    if not withCards then check(not w.swarmBrainEnabled or autoChoices>0,'baseline_brain_gate') end
    check(sim.droppedSimulationSeconds==0,'stress_no_fixed_steps_dropped')
    if active then
        check(w.stats.totalInfected>0,'active_real_infection',{infected=w.stats.totalInfected})
        check(w.stats.totalReleased>0,'active_real_release',{released=w.stats.totalReleased})
    end
    return {checks=ACCEPTANCE_TRACE,simulated_seconds=sim.time,ending=sim.ending or 'running',
        stats={infected=w.stats.totalInfected,released=w.stats.totalReleased,killed=w.stats.totalKilled,
            initial_immunes=Config.StartRegions[1].flatImmuneCount,final_immunes=#w.immunes},
        samples=rows,auto_choices=autoChoices,state_signature=stateSignature(w,sim.evolution),
        arrangement=active and 'No actor/cell repositioning or AI overrides. Scripted player pursues locally reachable healthy cells using movement inputs; immunity and infection resolve naturally. Not a player strategy or win-rate evaluation.'
            or 'No actor/cell repositioning, no AI disabling; scripted movement/switching and first-option card response. This is idle stability, not player success.'}
end
Suite.Helpers={make=make,grant=grant,pose=pose,invariants=invariants,check=check}
return Suite
