-- Explicit actor/contact geometry on the native 960-cell map. Full World/Sim
-- scripted-input stress runs separately; no native/player acceptance is implied.
local Config=require('Core.Config')
local H=require('ai_non_runtime_scenarios').Helpers
local Immune=require('Core.ImmuneSystem')
local Director=require('Core.ImmuneDirector')
local Suite={}
local dt=Config.Gameplay.movementStep
local function contact(w,im,c)
    for i=0,47 do
        local angle=i*math.pi/24;local r=im.radius+c.radius-.005
        local x,y=c.x+math.cos(angle)*r,c.y+math.sin(angle)*r
        if w.map:Contains(x,y,im.radius) and w:_DirectPathClear(x,y,c.x,c.y,0) then
            H.pose(w,im,x,y);return true
        end
    end
    return false
end
local function step(w,seconds)
    for _=1,math.floor(seconds/dt+.5)do
        w.time=w.time+dt;Immune.Update(w,dt)
    end
    H.invariants(w)
end
function Suite.Run(seed)
    local _,w=H.make(seed);local m,t=w.immunes[1],w.immunes[2]
    local far=w.map.regions[4];local remote=w.map.regions[5]
    H.pose(w,w.player,far.x,far.y);H.pose(w,m,remote.x,remote.y)
    local cell=nil
    for _,c in ipairs(w.cells)do
        if c.state=='HEALTHY' and (c.x-far.x)^2+(c.y-far.y)^2>144
            and (c.x-remote.x)^2+(c.y-remote.y)^2>144 and contact(w,t,c) then cell=c;break end
    end
    assert(cell,'native legal contact')
    w:SetDebugImmuneAlertLevel(4);Director.Update(w,Config.ImmuneAlert.alertActivationDelay)
    H.check(w.activeImmuneAlertLevel==4,'production_level_IV')
    w:_Infect(cell,'fixture')
    for _=1,600 do if t.state=='attack' then break end;step(w,dt)end
    H.check(t.state=='attack' and #w.immuneHotspots==1,'contact_confirmed_native_hotspot')
    local p=w.immuneHotspots[1]
    H.check(not p.targetId and not p.cellId,'report_has_no_target_identity')
    assert(contact(w,m,cell))
    step(w,dt)
    local duty=w.immuneCleanupAssignments[m.id]
    H.check(duty and m.hotspotCleanup and not m.targetId,'nearby_native_macro_accepts_location_only')
    -- Normal authority production creates real particles. Only their test poses
    -- are controlled; cleanup probability is unchanged and may fail naturally.
    w:_Release(cell,2)
    for _,v in ipairs(w.releasedViruses)do v.x,v.y=m.x,m.y end
    step(w,dt)
    H.check(m.targetType=='virus' and m.state=='locked' and m.warningTimer==Config.Gameplay.immuneBehavior.particleWarningSeconds,'self_discovery_fresh_warning')
    local killed=w.stats.totalKilled;step(w,.1)
    H.check(w.stats.totalKilled==killed,'no_early_or_remote_clear')
    local visited={}
    for _=1,math.floor(10/dt)do
        step(w,dt)
        local d=w.immuneCleanupAssignments[m.id]
        if d then visited[#visited+1]=string.format('%.12g,%.12g,%.12g,%s,%s',w.time,d.quiet,d.sweepClock,m.state,tostring(m.targetId or 0))end
    end
    H.check(w.stats.totalKilled>killed,'native_real_particle_cleanup')
    H.check((cell.immuneHits or 0)>0,'native_T_cell_keeps_node_role')
    -- Absolute expiry also works if actual clear failures kept the duty busy.
    if w.time<=p.untilTime then step(w,p.untilTime-w.time+dt)end
    H.check(not w.immuneCleanupAssignments[m.id] and not m.hotspotCleanup,'native_deadline_releases_duty')
    local state={time=w.time,rng=w._rng,killed=w.stats.totalKilled,nodeHits=cell.immuneHits,
        macroX=m.x,macroY=m.y,macroState=m.state,tX=t.x,tY=t.y,tState=t.state,
        hotspotSerial=w._nextImmuneHotspotId,alarms=w._nextImmuneAlarmId}
    return {checks=ACCEPTANCE_TRACE,state=state,decision_trace=table.concat(visited,';')}
end
return Suite
