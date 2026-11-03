-- Static branch assignments reuse their route. Target detection remains owned
-- by ImmuneSystem; every movement still uses the authoritative disk sweep.
local Navigation=require('Core.ImmuneNavigation')
local Patrol={}
local routes=setmetatable({},{__mode='k'})
local RETRY_SECONDS=.75

function Patrol.Point(map,immune,assignment,now)
    local radius=immune.radius
    if Navigation.Clear(map,immune,assignment,radius) then
        routes[immune]=nil
        return assignment.x,assignment.y
    end
    local entry=routes[immune]
    if not entry or entry.map~=map or entry.assignment~=assignment or entry.radius~=radius
        or entry.x~=assignment.x or entry.y~=assignment.y
        or (immune.x-entry.lastX)^2+(immune.y-entry.lastY)^2>1 then
        entry={map=map,assignment=assignment,radius=radius,x=assignment.x,y=assignment.y,
            lastX=immune.x,lastY=immune.y,index=1,nextPlan=now}
        routes[immune]=entry
    end
    entry.lastX,entry.lastY=immune.x,immune.y
    local route=entry.route
    if route then
        while entry.index<#route and (immune.x-route[entry.index].x)^2+(immune.y-route[entry.index].y)^2<.01 do
            entry.index=entry.index+1
        end
        local point=route[entry.index]
        if not point or not Navigation.Clear(map,immune,point,radius) then entry.route=nil
        elseif (immune._stuckTimer or 0)>.6 and now>=entry.nextPlan then entry.route=nil end
    end
    if not entry.route and now>=entry.nextPlan then
        entry.route=Navigation.Route(map,immune,assignment,radius)
        entry.index=1
        entry.nextPlan=now+RETRY_SECONDS
    end
    local point=entry.route and entry.route[entry.index]
    if point then return point.x,point.y end
    return nil,nil
end

return Patrol
