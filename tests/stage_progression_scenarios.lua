local H=require('ai_non_runtime_scenarios').Helpers
local Config=require('Core.Config')
local Suite={}
local dt=Config.Gameplay.movementStep

local function flee(world)
    local swarm=world.player
    local nearest=math.huge
    for _,immune in ipairs(world.immunes) do
        nearest=math.min(nearest,(immune.x-swarm.x)^2+(immune.y-swarm.y)^2)
    end
    if nearest>100 then world:SetMovement(0,0);return end
    local bestScore,bestX,bestY=-math.huge,0,0
    for index=0,23 do
        local angle=index*math.pi/12
        local directionX,directionY=math.cos(angle),math.sin(angle)
        local probeX,probeY=swarm.x+directionX*2,swarm.y+directionY*2
        if world.map:Contains(probeX,probeY,swarm.radius)
            and world:_DirectPathClear(swarm.x,swarm.y,probeX,probeY,swarm.radius) then
            local score=math.huge
            for _,immune in ipairs(world.immunes) do
                score=math.min(score,(immune.x-probeX)^2+(immune.y-probeY)^2)
            end
            if score>bestScore then bestScore,bestX,bestY=score,directionX,directionY end
        end
    end
    world:SetMovement(bestX,bestY)
end

local function infect(world,regionId,count)
    local added=0
    for _,cell in ipairs(world.cells) do
        if cell.regionId==regionId and cell.state=='HEALTHY' and added<count then
            world:_Infect(cell,'fixture')
            added=added+1
        end
    end
    assert(added==count,'missing production fixture cells')
end

local function waitChoice(sim,seconds)
    for _=1,math.ceil(seconds/dt) do
        if sim.cards.pending then return end
        assert(not sim.ending,'fixture lost before stage completion')
        flee(sim.world)
        sim:Update(dt)
    end
    assert(sim.cards.pending,'stage '..sim.stage..' did not complete: '..sim.task.detail)
end

local function choose(sim)
    local pending=assert(sim.cards.pending)
    assert(sim:CommitCardChoice(pending.id,pending.cards[1].id))
    assert(sim:ContinueAfterCard())
end

local function disease(world,fraction)
    local target=world.config.irreversibleInflammation*fraction
    local extra=math.max(0,target-world.globalInflammation)
    world:AddInflammation(3,extra/2)
    world:AddInflammation(4,extra/2)
end

function Suite.Run(seed)
    local sim,world=H.make(seed)
    local far=world.map.regions[5]
    for _,immune in ipairs(world.immunes) do H.pose(world,immune,far.x,far.y) end
    local timeline={}
    infect(world,3,1)
    waitChoice(sim,35);timeline[1]=world.time;choose(sim)
    assert(sim.stage==2 and not sim.cards.pending)
    -- Authored relocation of a real node product tests provenance, not player movement.
    local product
    for _,v in ipairs(world.releasedViruses) do
        if v.nodeProduced and v.state~='ABSORBED' and v.state~='CLEARED' and v.state~='LOST' then product=v;break end
    end
    assert(product,'first node must release recoverable products')
    product.x,product.y=world.player.x,world.player.y
    assert(sim:AbsorbNearby()>0)
    infect(world,3,2)
    waitChoice(sim,1);timeline[2]=world.time;choose(sim)
    assert(sim.stage==3 and not sim.cards.pending)
    infect(world,3,Config.Evolution.production.released)
    waitChoice(sim,35);timeline[3]=world.time;choose(sim)
    assert(sim.stage==4 and not sim.cards.pending)
    for stage=4,6 do
        assert(sim.task.progress==0,'stage entry must exclude old infections')
        infect(world,4,Config.Evolution.expansion[stage])
        waitChoice(sim,1);timeline[stage]=world.time;choose(sim)
    end
    assert(sim.formalFinished and sim.cards.formalCount==6 and not sim.ending)
    disease(world,1.2)
    flee(world);sim:Update(dt)
    assert(sim.victoryQualified and not sim.ending,'sixth card must leave time to expand')
    local finalTarget=Config.Evolution.victory.newInfections
    infect(world,4,4)
    flee(world);sim:Update(dt)
    assert(sim.ending=='victory','expanded infection and irreversible condition should win')
    H.invariants(world)
    return {seed=seed,timeline=timeline,stage=sim.stage,cards=sim.cards.formalCount,
        independent_infections=world.stats.independentInfections,groups=#world.swarms,
        inflammation=world.globalInflammation,damage=world.globalTissueDamage,
        final_target=finalTarget,final_time=world.time,ending=sim.ending}
end

return Suite
