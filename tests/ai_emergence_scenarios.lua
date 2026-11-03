-- Default production-map assays. Explicit actor poses/contact exposure and
-- authority-based infection/aging fixtures isolate causes; Core functions intact.
local Base=require('ai_non_runtime_scenarios')
local H=Base.Helpers
local E=require('Core.LocalEcology')
local AI=require('Core.SplitVirusAI')
local Immune=require('Core.ImmuneSystem')
local Suite={}
local dt=1/60
local function dist(a,b) return math.sqrt((a.x-b.x)^2+(a.y-b.y)^2) end
local function away(w,actor,region)
    local r=w.map.regions[region or 5]
    H.pose(w,actor,r.x,r.y)
end
local function fresh(seed)
    local sim,w=H.make(seed)
    for _,im in ipairs(w.immunes) do away(w,im,5) end
    return sim,w
end
local function immuneSteps(w,seconds,callback)
    for i=1,math.floor(seconds/dt+.5) do
        w.time=w.time+dt;Immune.Update(w,dt)
        if callback and callback(i) then return end
    end
end
local function closestCell(w,predicate)
    local best,chosen=math.huge,nil
    for _,c in ipairs(w.cells) do
        local d=dist(c,w.player)
        if d<best and (not predicate or predicate(c)) then best,chosen=d,c end
    end
    assert(chosen,'no suitable cell in default map');return chosen
end
local function bodyContact(w,actor,cell,gap)
    for i=0,31 do
        local a=i*math.pi/16;local r=actor.radius+cell.radius+(gap or 0)
        local x,y=cell.x+math.cos(a)*r,cell.y+math.sin(a)*r
        if w.map:Contains(x,y,actor.radius) and w:_DirectPathClear(x,y,cell.x,cell.y,0) then
            H.pose(w,actor,x,y);return
        end
    end
    error('no valid contact')
end
function Suite.Autonomy(seed)
    local sim,w=fresh(seed)
    assert(w:Split());local main,b=w.swarms[1],w.swarms[2]
    local home=w.map.startPoints.UPPER_AIRWAY
    H.pose(w,b,home.x,home.y);away(w,main,4)
    w:DamageSwarm(b.id,b.mass-5)
    -- Remove local targets through the real death authority to isolate exploration.
    for _,c in ipairs(w.cells) do if dist(c,b)<w.config.autonomy.searchRadius+.2 then w:KillCell(c,'fixture') end end
    AI.ThinkWorld(w,dt)
    H.check(b.aiState=='disabled' and not b._aiSupplyId,'no_card_no_active_autonomy')
    H.grant(sim,'swarm_local_brain');AI.ThinkWorld(w,.3)
    H.check(b.aiState=='wander' and not b.aiTargetCellId,'brain_bounded_exploration')
    local radius=w.config.autonomy.wanderRadius
    H.check((b._aiMoveX-home.x)^2+(b._aiMoveY-home.y)^2<=radius^2
        and w:_DirectPathClear(b.x,b.y,b._aiMoveX,b._aiMoveY,b.radius),'exploration_body_clear_local')
    local producer=closestCell(w,function(c)return c.state=='HEALTHY' end)
    w:_Infect(producer,'fixture');w:_AgeCells(w.config.latentSeconds)
    local v=w.releasedViruses[1];assert(v)
    for _,other in ipairs(w.releasedViruses) do H.pose(w,other,w.map.regions[4].x,w.map.regions[4].y) end
    b._aiThinkClock=0;AI.ThinkWorld(w,.3)
    H.check(b.aiState~='collect' and not b._aiSupplyId,'far_supplies_do_not_leak_through_fallback_queries')
    -- A real released entity is placed within sensed range but outside absorption.
    local placed=false
    for i=0,15 do
        local x,y=b.x+math.cos(i*math.pi/8)*1.4,b.y+math.sin(i*math.pi/8)*1.4
        if w:_DirectPathClear(b.x,b.y,x,y,b.radius) then H.pose(w,v,x,y);placed=true;break end
    end
    assert(placed)
    b._aiThinkClock=0;AI.ThinkWorld(w,.3)
    H.check(b.aiState=='collect' and b._aiSupplyId==v.id,'low_mass_local_supply')
    local mass=b.mass
    for _=1,360 do w:Update(dt);if v.state=='ABSORBED' then break end end
    H.check(v.state=='ABSORBED' and b.mass==mass+1,'supply_actual_absorption_not_free_mass')
    H.invariants(w)
    -- Near-complete visible contact has priority over safe resupply.
    local target=closestCell(w,function(c)return c.state=='HEALTHY' end)
    bodyContact(w,b,target,.04);target.exposure=.85;target.state='EXPOSED'
    b.aiTargetCellId=target.id;b._aiTargetHold=0;b._aiThinkClock=0
    w:_Release(producer,1)
    local supply=w.releasedViruses[#w.releasedViruses]
    H.pose(w,supply,b.x,b.y) -- actual release; choice assay only
    AI.ThinkWorld(w,.3)
    H.check(b.aiTargetCellId==target.id and b.aiState~='collect','safe_near_completion_persists')
    local macro=w.immunes[1];bodyContact(w,macro,{x=b.x,y=b.y,radius=b.radius},.02)
    b._aiThinkClock=0;AI.ThinkWorld(w,.3)
    H.check(b.aiState=='flee' and not b.aiTargetCellId,'danger_overrides_completion')
    b.anchored=true;AI.ThinkWorld(w,.3);H.check(not AI.IsAutonomous(w,b),'anchor_keeps_priority')
    b.anchored=false;assert(w:SwitchControl(b.id));AI.ThinkWorld(w,.3)
    H.check(b.aiState=='controlled' and not b._aiSupplyId,'manual_takeover_clears_supply')
    H.invariants(w)
    return {checks=ACCEPTANCE_TRACE,simulated_seconds=w.time}
end
function Suite.Immunity(seed)
    local _,w=fresh(seed);local m=w.immunes[1]
    H.pose(w,m,w.player.x,w.player.y)
    local loadSeen,processingSeen=false,false
    immuneSteps(w,40,function()
        loadSeen=loadSeen or (m.processingLoad or 0)>0
        if m.state=='processing' then processingSeen=true;return true end
    end)
    H.check(loadSeen and w.stats.totalKilled>0,'actual_kills_create_load',{killed=w.stats.totalKilled})
    H.check(processingSeen and not m.targetId,'capacity_releases_target_and_processes',{load=m.processingLoad})
    local killed,load=w.stats.totalKilled,m.processingLoad
    immuneSteps(w,1)
    H.check(m.state=='processing' and w.stats.totalKilled==killed and m.processingLoad<load,'processing_recovers_without_damage')
    immuneSteps(w,30,function()return m.state~='processing' end)
    H.check(m.state~='processing' and m.processingLoad<=w.config.immuneBehavior.loadResume,'load_recovery_returns_to_work')
    H.invariants(w)
    -- Existing native T cell investigates a real infected node at body contact.
    local t=w.immunes[2];away(w,m,5);away(w,w.player,4)
    m.targetId,m.targetType=nil,nil;m.state='patrol'
    local cell=closestCell(w);w:_Infect(cell,'fixture');bodyContact(w,t,cell,-.01)
    local investigating=false
    immuneSteps(w,8,function()if t.state=='investigate' then investigating=true;return true end end)
    H.check(investigating and cell.immuneHits==0,'tcell_warning_precedes_identification')
    immuneSteps(w,.8)
    H.check((t.recognitionTimer or 0)>.5 and cell.immuneHits==0,'identification_accumulates_without_damage')
    bodyContact(w,t,cell,.5);immuneSteps(w,dt)
    H.check(t.recognitionTimer==0 and not t.recognized and t.state=='chase','contact_loss_resets_identification')
    bodyContact(w,t,cell,-.01)
    immuneSteps(w,10,function()return (cell.immuneHits or 0)>0 end)
    H.check(t.recognized and cell.immuneHits==1,'confirmed_target_then_real_windup_damage')
    w:KillCell(cell,'fixture')
    H.check(not t.targetId and not t.recognized and t.recognitionTimer==0,'dead_target_clears_recognition')
    H.invariants(w)
    return {checks=ACCEPTANCE_TRACE,simulated_seconds=w.time}
end
function Suite.Signals(seed)
    local _,w=fresh(seed)
    away(w,w.player,4)
    local c=w.cells[1];w:_Infect(c,'fixture');w:_AgeCells(w.config.latentSeconds)
    for _,v in ipairs(w.releasedViruses) do away(w,v,4) end
    local rng=w._rng;E.Update(w,.5)
    H.check(E.Sample(w,c.x,c.y,'activity')>0,'actual_production_emits_trace')
    local maxId,best=nil,-1
    for id,n in ipairs(w.ecology.nodes) do if n.activity>best then maxId,best=id,n.activity end end
    local linked=w.ecology.nodes[maxId].links[1];assert(linked)
    E.Update(w,.5)
    H.check(w.ecology.nodes[linked].activity>0,'trace_diffuses_over_open_edges')
    H.check(w._rng==rng,'signals_do_not_consume_simulation_randomness')
    for _,n in ipairs(w.ecology.nodes) do assert(not n.targetId and not n.sourceId) end
    H.check(true,'field_contains_no_entity_identity')
    for _=1,20 do E.Update(w,.5) end
    local t=w.immunes[2];local placed=false
    for i=0,31 do
        local a=i*math.pi/16;local x,y=c.x+math.cos(a)*4.1,c.y+math.sin(a)*4.1
        if w.map:Contains(x,y,t.radius) and w:_DirectPathClear(x,y,c.x,c.y,0) then
            H.pose(w,t,x,y)
            if E.Investigate(w,t) then placed=true;break end
        end
    end
    assert(placed,'no gradient investigation fixture')
    Immune.Update(w,dt)
    H.check(t.state=='patrol' and t.signalInvestigation and not t.targetId,'traces_investigate_without_remote_lock')
    H.check(dist(t,c)>t.detectionRange+c.radius,'investigation_outside_discovery_radius')
    w:KillCell(c,'fixture');E.Update(w,.5)
    H.check(E.Sample(w,c.x,c.y,'damage')>0 and E.Sample(w,c.x,c.y,'debris')>0,'death_has_distinct_damage_debris_channels')
    local m=w.immunes[1];bodyContact(w,m,c,-.01)
    immuneSteps(w,12,function()return w._immuneClearedDebris[c.id] end)
    H.check(w._immuneClearedDebris[c.id],'real_cleanup_ends_debris_source')
    local function total(channel)local sum=0;for _,n in ipairs(w.ecology.nodes) do sum=sum+n[channel] end;return sum end
    E.Update(w,.5);local before=total('debris');E.Update(w,3)
    H.check(total('debris')<before,'old_debris_trace_fades_after_cleanup')
    H.invariants(w)
    return {checks=ACCEPTANCE_TRACE,simulated_seconds=w.time,field_nodes=#w.ecology.nodes}
end
function Suite.Defense(seed)
    local _,w=fresh(seed)
    -- Positive topology control: two native cells whose actual sample nodes
    -- are directly connected. Euclidean closeness alone does not imply equal
    -- concentrations on a discretized field near ridges/grid boundaries.
    local a,b,best=nil,nil,math.huge
    for _,c in ipairs(w.cells) do
        local cn=w.ecology.cellSamples[c.id].node
        local adjacent={};if cn then adjacent[cn]=true;for _,id in ipairs(w.ecology.nodes[cn].links) do adjacent[id]=true end end
        for _,other in ipairs(w:NearbyCells(c.x,c.y,4.5)) do
            local d=dist(c,other);local on=w.ecology.cellSamples[other.id].node
            if c.id~=other.id and on and adjacent[on] and d<best
                and w:_DirectPathClear(c.x,c.y,other.x,other.y,0) then a,b,best=c,other,d end
        end
    end
    assert(a and b);w:_Infect(a,'fixture');w:_AgeCells(w.config.latentSeconds)
    for _,v in ipairs(w.releasedViruses) do away(w,v,4) end
    E.Update(w,.5);H.check((b.antiviralStrength or 0)==0,'no_instant_defense_on_production')
    local far=closestCell(w,function(c)return dist(c,a)>25 end)
    H.check((far.antiviralStrength or 0)==0,'remote_tissue_not_protected_by_global_state')
    local protectedAt=nil;local stimulated=0
    for i=1,160 do
        E.Update(w,.5)
        if E.Sample(w,b.x,b.y,'activity')>=w.config.ecology.defenseThreshold then stimulated=stimulated+.5 end
        if (b.antiviralStrength or 0)>=.99 then protectedAt=(i+1)*.5;break end
    end
    H.check(protectedAt and stimulated>=w.config.ecology.defenseDelay,'neighbor_delayed_reversible_defense',
        {distance=best,at=protectedAt,signal=E.Sample(w,b.x,b.y,'activity')})
    H.check((far.antiviralStrength or 0)==0,'defense_remains_local_during_production')
    bodyContact(w,w.player,b,.04)
    local charge=b._charge;w:_AccumulateExposure(.25);local reduced=b._charge-charge
    H.check(reduced>0 and E.InfectionMultiplier(w,b)<1,'defense_reduces_but_never_blocks_infection')
    local protectedStates=w:Counts()
    H.check(protectedStates.healthy+protectedStates.exposed==959,'defense_keeps_original_cell_state_partition')
    w:KillCell(a,'fixture')
    for _=1,240 do E.Update(w,.5);if (b.antiviralStrength or 0)==0 then break end end
    H.check((b.antiviralStrength or 0)==0 and E.InfectionMultiplier(w,b)==1,'quiet_period_reopens_infection_window')
    charge=b._charge;w:_AccumulateExposure(.25);local normal=b._charge-charge
    H.check(normal>reduced and math.abs(reduced/normal-(1-w.config.ecology.defenseSuppression))<1e-6,
        'same_contact_actual_charge_comparison',{protected=reduced,unprotected=normal})
    H.invariants(w)
    return {checks=ACCEPTANCE_TRACE,simulated_seconds=w.time,defense_onset=protectedAt}
end
function Suite.Navigation(seed)
    local sim,w=fresh(seed);assert(w:Split())
    local b,main=w.swarms[2],w.swarms[1]
    local home=w.map.startPoints.UPPER_AIRWAY
    H.pose(w,b,home.x,home.y);away(w,main,4)
    local candidates={}
    for _,c in ipairs(w.cells) do
        if dist(c,b)<7 then w:KillCell(c,'fixture') else candidates[#candidates+1]=c end
    end
    local obstacle,target=candidates[1],candidates[2]
    local placed=false
    for i=0,31 do
        local a=i*math.pi/16;local dx,dy=math.cos(a),math.sin(a)
        local tx,ty=b.x+dx*4,b.y+dy*4
        if w:_DirectPathClear(b.x,b.y,tx,ty,b.radius+.6) then
            H.pose(w,obstacle,b.x+dx*2,b.y+dy*2);H.pose(w,target,tx,ty)
            placed=true;break
        end
    end
    assert(placed,'no local navigation assay space')
    w:_Infect(obstacle,'fixture');H.grant(sim,'swarm_local_brain')
    b._aiThinkClock=0;AI.ThinkWorld(w,.3)
    local ox,oy=b.x,b.y
    H.check(b.aiTargetCellId==target.id and b.aiState=='seek','visible_target_plans_local_detour')
    local cross=(b._aiMoveX-b.x)*(target.y-b.y)-(b._aiMoveY-b.y)*(target.x-b.x)
    H.check(math.abs(cross)>.5,'detour_waypoint_is_not_blocked_center_line')
    for _=1,120 do w:Update(dt) end
    H.check((b.x-ox)^2+(b.y-oy)^2>.25,'detour_produces_real_movement')
    local gap=dist(b,obstacle)-b.radius-obstacle.radius
    H.check(gap>=w.config.autonomy.cellClearance-1e-5,'detour_preserves_body_collision',{gap=gap})
    H.invariants(w)
    -- Other small groups cannot claim the same locally sensed real supply.
    H.grant(sim,'swarm_capacity_4')
    while w.splitCooldown>1e-9 do w:Update(dt) end
    assert(w:Split())
    local c=w.swarms[#w.swarms]
    H.pose(w,b,home.x,home.y);H.pose(w,c,home.x+.2,home.y)
    w:DamageSwarm(b.id,math.max(0,b.mass-5));w:DamageSwarm(c.id,math.max(0,c.mass-5))
    w:_Release(obstacle,1);local v=w.releasedViruses[#w.releasedViruses]
    H.pose(w,v,home.x,home.y+1.4)
    b._aiThinkClock,c._aiThinkClock=0,0;AI.ThinkWorld(w,.3)
    local claims=(b._aiSupplyId==v.id and 1 or 0)+(c._aiSupplyId==v.id and 1 or 0)
    H.check(claims==1,'supply_intent_reservations_avoid_duplicate_assignment')
    H.invariants(w)
    return {checks=ACCEPTANCE_TRACE,simulated_seconds=w.time}
end
-- Synthetic sealed-domain negative control, explicitly not a production map.
function Suite.Barrier(seed)
    local _,w=fresh(seed)
    local realMap=w.map
    local synthetic={}
    function synthetic:Contains(x,y,r) return x>=r and x<=12-r and y>=r and y<=12-r and (x<5.8-r or x>6.2+r) end
    function synthetic:_ConvexPathClear(x,y,tx,ty,r) return self:Contains(x,y,r) and self:Contains(tx,ty,r) and (x<6)==(tx<6) end
    function synthetic:_Sweep(x,y,dx,dy,r) return self:_ConvexPathClear(x,y,x+dx,y+dy,r) and 1 or 0 end
    w.map=synthetic;w.width,w.height=12,12;E.Init(w)
    -- Authority-free pulse intentionally isolates the diffusion operator only.
    E.Pulse(w,3,6,'activity',1)
    for _=1,30 do E.Update(w,.5) end
    local left,right=0,0
    for _,n in ipairs(w.ecology.nodes) do if n.x<6 then left=left+n.activity else right=right+n.activity end end
    H.check(left>0 and right==0,'sealed_wall_blocks_diffusion',{left=left,right=right})
    w.map=realMap
    return {checks=ACCEPTANCE_TRACE,simulated_seconds=15,fixture='synthetic sealed domains'}
end
return Suite
