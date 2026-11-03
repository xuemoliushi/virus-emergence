-- Production-map causal assay. Explicit poses/authority infection isolate each
-- alert tier; this is separate from unchanged full World/Sim stress acceptance.
local Config=require('Core.Config')
local H=require('ai_non_runtime_scenarios').Helpers
local Immune=require('Core.ImmuneSystem')
local Director=require('Core.ImmuneDirector')
local Suite={}
local dt=Config.Gameplay.movementStep
local function dist(a,b)return math.sqrt((a.x-b.x)^2+(a.y-b.y)^2)end
local function contact(w,im,c)
    for i=0,47 do
        local a=i*math.pi/24;local r=im.radius+c.radius-.005
        local x,y=c.x+math.cos(a)*r,c.y+math.sin(a)*r
        if w.map:Contains(x,y,im.radius) and w:_DirectPathClear(x,y,c.x,c.y,0) then
            H.pose(w,im,x,y);return true
        end
    end
    return false
end
local function reset(w,im)
    Director.Release(w,im);im.state,im.stateTimer,im.cooldown='patrol',0,0
    im.targetId,im.targetType,im.targetX,im.targetY=nil,nil,nil,nil
    im._screenCellId,im.screenTimer,im.recognized,im.recognitionTimer=nil,0,false,0
    im._patrolTimer,im._stuckTimer=0,0
end
local function steps(w,seconds)
    for i=1,math.floor(seconds/dt+.5) do
        w.time=w.time+dt;Immune.Update(w,dt)
        if i%60==0 then H.invariants(w) end
    end
end
local function signature(w)
    local values={}
    local function add(...)
        for _,v in ipairs({...}) do values[#values+1]=type(v)=='number' and string.format('%.17g',v) or tostring(v) end
    end
    add(w.time,w._rng,w.activeImmuneAlertLevel,w.stats.totalKilled,w._nextImmuneAlarmId)
    for _,im in ipairs(w.immunes) do
        add(im.id,im.x,im.y,im.state,im.targetId or 0,im.processingLoad or 0,
            im.recognitionTimer or 0,im.recognized==true,im.recognitionRequiredSeconds or 0,
            im._searchUntil or 0,im._searchX or 0,im._searchY or 0,im._screenCellId or 0,
            im.screenTimer or 0,im._alarmReadyAt or 0,im._encounterTimer or 0,im.respondingToAlarm==true)
        local ids={};for id in pairs(im._cellChecks or {})do ids[#ids+1]=id end;table.sort(ids)
        for _,id in ipairs(ids)do local r=im._cellChecks[id];add(id,r.x,r.y,r.checkedAt,r.infected)end
        local p=w.immuneAlarmAssignments[im.id];if p then add(p.alarmId,p.x,p.y,p.untilTime)end
    end
    for _,a in ipairs(w.immuneAlarms)do
        add(a.id,a.x,a.y,a.untilTime,a.sourceId)
        local ids={};for id in pairs(a.responders)do ids[#ids+1]=id end;table.sort(ids)
        for _,id in ipairs(ids)do add(id)end
    end
    local keys={};for key in pairs(w.immuneAlarmCooldowns)do keys[#keys+1]=key end;table.sort(keys)
    for _,key in ipairs(keys)do add(key,w.immuneAlarmCooldowns[key])end
    return table.concat(values,'|')
end
function Suite.Run(seed)
    local rows={};local signatures={};local checks={}
    for level=0,5 do
        -- Isolate tier gates with living actors in each case. Faster real hits
        -- exhaust the same 30-particle swarm by IV when reused across all tiers.
        -- Full World/Sim stress separately covers uninterrupted actor lifetimes.
        local _,w=H.make(seed)
        local m,t=w.immunes[1],w.immunes[2]
        reset(w,m);reset(w,t)
        local far=w.map.regions[4];local remote=w.map.regions[5]
        H.pose(w,w.player,far.x,far.y);H.pose(w,m,remote.x,remote.y)
        -- Select an actual native healthy cell with a legal T-cell body contact.
        local cell=nil
        for _,c in ipairs(w.cells)do
            if c.state=='HEALTHY' and dist(c,far)>12 and dist(c,remote)>12 and contact(w,t,c)then cell=c;break end
        end
        assert(cell,'production contact fixture')
        w:SetDebugImmuneAlertLevel(level)
        steps(w,Config.ImmuneAlert.alertActivationDelay)
        H.check(w.activeImmuneAlertLevel==level,'stage_'..level..'_activated')
        reset(w,t);assert(contact(w,t,cell));steps(w,3)
        local record=t._cellChecks and t._cellChecks[cell.id]
        H.check(level<3 or record and not record.infected,'stage_'..level..'_screen_gate')
        H.check(level>=3 or not record,'stage_'..level..'_no_early_memory')
        w:_Infect(cell,'fixture')
        assert(contact(w,t,cell))
        steps(w,8)
        H.check((cell.immuneHits or 0)>0,'stage_'..level..'_real_contact_attack')
        -- Cooperation has its own production assay. Let the real duty expire
        -- with the T cell away before isolating the older swarm-alarm gate.
        if level>=Config.ImmuneAlert.hotspotLevel then
            reset(w,t);H.pose(w,t,far.x,far.y)
            steps(w,Config.ImmuneAlert.hotspotDuration+dt)
        end
        -- Create an actual swarm encounter after moving the T cell away.
        reset(w,t);H.pose(w,t,far.x,far.y);reset(w,m);m.processingLoad=0;assert(contact(w,m,cell))
        H.pose(w,w.player,m.x,m.y)
        local alarmCount=w._nextImmuneAlarmId
        steps(w,4.1)
        H.check((w._nextImmuneAlarmId>alarmCount)==(level>=1),'stage_'..level..'_alarm_gate')
        H.pose(w,w.player,far.x,far.y);steps(w,.1)
        H.check((m.state=='search')==(level>=5),'stage_'..level..'_search_gate')
        H.invariants(w)
        local memories=0;for _ in pairs(t._cellChecks or {})do memories=memories+1 end
        rows[#rows+1]={level=level,time=w.time,alarms=w._nextImmuneAlarmId-1,memories=memories,
            killed=w.stats.totalKilled,nodeHits=cell.immuneHits,search=m.state=='search'}
        signatures[#signatures+1]=signature(w)
        -- Remove this stage's known node through authority so the next stage's
        -- isolated contact target cannot compete with an older infected node.
        w:KillCell(cell,'fixture')
        reset(w,m);m.processingLoad=0;assert(contact(w,m,cell));steps(w,6)
        H.check(w._immuneClearedDebris[cell.id],'stage_'..level..'_real_cleanup')
        for _,check in ipairs(ACCEPTANCE_TRACE)do checks[#checks+1]=check end
    end
    return {checks=checks,stages=rows,state_signature=table.concat(signatures,'\n')}
end
return Suite
