-- The old membrane_glide card slot now deploys a real, stationary three-virus swarm.
local Config=require("Core.Config")
local Relay={}
local function cfg() return Config.CardAbilities.membrane_glide end
local function distance(a,b) return math.sqrt((a.x-b.x)^2+(a.y-b.y)^2) end

function Relay.Position(w,s,c)
    local dx,dy=s.x-c.x,s.y-c.y
    local d=math.sqrt(dx*dx+dy*dy)
    if d<1e-6 then dx,dy,d=1,0,1 end
    local radius=.2
    local tx,ty=c.x+dx/d*(c.radius+radius),c.y+dy/d*(c.radius+radius)
    local x,y=w.map:Move(s.x,s.y,tx,ty,radius)
    if not w.map:Contains(x,y,radius) or distance({x=x,y=y},c)>c.radius+radius+w.config.infectionReach-.01 then
        return nil,nil
    end
    return x,y
end

function Relay.Validate(w,s,c)
    if c.state~="HEALTHY" and c.state~="EXPOSED" then return false,"请选择尚未感染完成的细胞" end
    if not s.exposedCells[c.id] or distance(s,c)>s.radius+c.radius+w.config.infectionReach then
        return false,"请先让当前群接触并开始感染目标"
    end
    if w:LiveSwarmCount()>=w.maxPlayerSwarms then return false,"群体名额已满" end
    for _,other in ipairs(w.swarms) do
        if other.relayCellId==c.id then return false,"目标已有接力小队" end
    end
    local x=Relay.Position(w,s,c)
    if not x then return false,"细胞边缘没有合法驻守位置" end
    return true
end

function Relay.Deploy(w,s,c,abilities)
    local x,y=Relay.Position(w,s,c)
    assert(x and y,"接力部署必须先验证合法位置")
    local particles=abilities.TakeMass(w,s,cfg().massCost,"relay_investment")
    local team=w:_CreateSwarm(x,y,0,false)
    team.mass=#particles;team.relayCellId=c.id;team.aiState="relay"
    team.launchTimer=0;team.mergeGrace=0
    for _,p in ipairs(particles) do p.swarmId=team.id;w.viruses[#w.viruses+1]=p end
    w:_RefreshGroupShape(team);w:_RefreshGroups();w:_UpdateParticles()
    w:Emit("relay_started",{swarmId=team.id,sourceSwarmId=s.id,cellId=c.id,count=team.mass,x=team.x,y=team.y})
end

function Relay.Release(w,team,reason,abilities)
    if not team.relayCellId or team.mass<=0 then return end
    local cellId=team.relayCellId
    local particles=abilities.TakeMass(w,team,team.mass,"relay_return")
    local released=abilities.SpawnReleased(w,particles,team.x,team.y,"relay_return")
    -- Convert in place so a single E pulse has the same range snapshot for the whole squad.
    for _,v in ipairs(released) do
        v.x,v.y,v._oldX,v._oldY=team.x,team.y,team.x,team.y
        v.vx,v.vy=0,0;v.sourceRegionId=w.map:RegionAt(v.x,v.y)
    end
    team.relayCellId=nil;team.isMainSwarm=false;team.isPlayerControlled=false
    -- Normal handoff is not a swarm death: avoid cleared/lost events and their audio.
    for i=#w.swarms,1,-1 do if w.swarms[i]==team then table.remove(w.swarms,i);break end end
    w:_RefreshGroups()
    w:Emit("relay_finished",{swarmId=team.id,cellId=cellId,count=#released,reason=reason})
end

function Relay.FinishCell(w,cellId,abilities)
    local teams={}
    for _,s in ipairs(w.swarms) do if s.relayCellId==cellId then teams[#teams+1]=s end end
    for _,s in ipairs(teams) do Relay.Release(w,s,"target_finished",abilities) end
end

function Relay.Nearby(w,collector)
    local result={}
    if not collector or collector.isHidden or collector.relayCellId then return result end
    for _,s in ipairs(w.swarms) do
        if s.relayCellId and s.mass>0 and distance(s,collector)<=collector.radius+w.config.activeAbsorptionExtra
            and w:_DirectPathClear(s.x,s.y,collector.x,collector.y,w.config.virusRadius) then result[#result+1]=s end
    end
    return result
end

function Relay.Power(w,s)
    return w.config.infectionSeconds/cfg().fullInfectionSeconds*math.min(1,s.mass/cfg().massCost)
end
return Relay
