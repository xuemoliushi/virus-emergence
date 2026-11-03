-- LocalEcology: identity-free local traces and reversible tissue response.
-- Pure Lua fixed-step module; no new cell states, damage or virus creation.
local Ecology={}
local CHANNELS={"activity","damage","debris"}
---@class EcologyNode
---@field x number
---@field y number
---@field links integer[]
---@field activity number
---@field damage number
---@field debris number
---@class EcologyField
---@field nodes EcologyNode[]
---@field lookup table<string,integer>
---@field pending table<integer,table<string,number>>
---@field clock number
---@field cellSamples table<integer,{x:number,y:number,node:integer?}>
---@field active table<integer,boolean>
---@class RespiratoryCell
---@field antiviralStimulus number?
---@field antiviralRemaining number?
---@field antiviralStrength number?
---@class SwarmWorld
---@field ecology EcologyField?
---@field tissueDefenseCount integer?
local function key(x,y) return x..":"..y end
local function clear(w,x,y,tx,ty)
    return w:_DirectPathClear(x,y,tx,ty,0)
end
-- A trace can enter only a nearby visible lattice node; no jumping across walls.
local function nearest(w,x,y)
    local f=w.ecology;local spacing=w.config.ecology.spacing
    local ix,iy=math.floor(x/spacing+.5),math.floor(y/spacing+.5)
    local best,d=nil,math.huge
    for ox=-1,1 do for oy=-1,1 do
        local id=f.lookup[key(ix+ox,iy+oy)]
        if id then
            local n=f.nodes[id];local d2=(n.x-x)^2+(n.y-y)^2
            if d2<d and clear(w,x,y,n.x,n.y) then best,d=id,d2 end
        end
    end end
    return best
end
-- Native cell geometry is fixed; invalidate this cache when a fixture moves it
-- or Init changes topology. Cached lattice IDs carry no target decision.
local function cellNode(w,c)
    local cached=w.ecology.cellSamples[c.id]
    if not cached or cached.x~=c.x or cached.y~=c.y then
        cached={x=c.x,y=c.y,node=nearest(w,c.x,c.y)}
        w.ecology.cellSamples[c.id]=cached
    end
    return cached.node
end
function Ecology.Init(w)
    local cfg=w.config.ecology
    w.tissueDefenseCount=0
    if not cfg or not cfg.enabled then w.ecology=nil;return end
    local f={nodes={},lookup={},pending={},clock=0,cellSamples={},active={}};w.ecology=f
    local s=cfg.spacing
    for ix=0,math.floor(w.width/s) do for iy=0,math.floor(w.height/s) do
        local x,y=ix*s,iy*s
        if w.map:Contains(x,y,0) then
            f.nodes[#f.nodes+1]={x=x,y=y,links={},activity=0,damage=0,debris=0}
            f.lookup[key(ix,iy)]=#f.nodes
        end
    end end
    for ix=0,math.floor(w.width/s) do for iy=0,math.floor(w.height/s) do
        local id=f.lookup[key(ix,iy)]
        if id then
            local n=f.nodes[id]
            for _,offset in ipairs({{1,0},{0,1}}) do
                local other=f.lookup[key(ix+offset[1],iy+offset[2])]
                if other then
                    local b=f.nodes[other]
                    if clear(w,n.x,n.y,b.x,b.y) then
                        n.links[#n.links+1]=other;b.links[#b.links+1]=id
                    end
                end
            end
        end
    end end
    -- Keep first simulation tick inexpensive; moved-cell fixtures invalidate caches.
    for _,c in ipairs(w.cells) do cellNode(w,c) end
end
-- Impulses come exclusively from actual release/death/unshielded node damage.
function Ecology.Pulse(w,x,y,channel,amount)
    if not w.ecology or amount<=0 then return end
    local id=nearest(w,x,y);if not id then return end
    local p=w.ecology.pending[id] or {};w.ecology.pending[id]=p
    p[channel]=(p[channel] or 0)+amount
end
function Ecology.Sample(w,x,y,channel)
    if not w.ecology then return 0 end
    local id=nearest(w,x,y)
    return id and w.ecology.nodes[id][channel] or 0
end
-- Only local samples and body-clear positions; no identity or remote source lookup.
function Ecology.Investigate(w,immune)
    if not w.ecology then return nil end
    local cfg=w.config.ecology
    local function strength(n)
        return immune.kind=="macrophage" and n.debris+n.damage*.6+n.activity*.25
            or n.activity+n.damage*.25
    end
    local origin=nearest(w,immune.x,immune.y)
    local baseline=origin and strength(w.ecology.nodes[origin]) or 0
    local best,score=nil,cfg.investigateThreshold
    local s=cfg.spacing
    local ix,iy=math.floor(immune.x/s+.5),math.floor(immune.y/s+.5)
    local count=math.ceil(cfg.senseRadius/s)
    for ox=-count,count do for oy=-count,count do
        local id=w.ecology.lookup[key(ix+ox,iy+oy)]
        if id then
            local n=w.ecology.nodes[id]
            local d2=(n.x-immune.x)^2+(n.y-immune.y)^2
            local value=strength(n)
            if d2>.04 and d2<=cfg.senseRadius^2 and value>baseline+.015
                and value/(1+math.sqrt(d2)*.12)>score
                and w.map:Contains(n.x,n.y,immune.radius)
                and w:_DirectPathClear(immune.x,immune.y,n.x,n.y,immune.radius) then
                best,score=n,value/(1+math.sqrt(d2)*.12)
            end
        end
    end end
    return best
end
local function tick(w,dt)
    local cfg,f=w.config.ecology,w.ecology
    local sources={}
    local function source(cell,channel,rate)
        local id=cellNode(w,cell);if not id then return end
        local p=sources[id] or {};sources[id]=p;p[channel]=(p[channel] or 0)+rate*dt
    end
    for _,c in ipairs(w.cells) do
        if c.state=="PRODUCTIVE" then source(c,"activity",cfg.productionRate)
        elseif c.state=="EXHAUSTED" then source(c,"damage",cfg.exhaustionRate)
        elseif c.state=="DEAD" and not (w._immuneClearedDebris or {})[c.id] then source(c,"debris",cfg.debrisRate) end
    end
    -- Double-buffer explicit diffusion. <= .2 per edge keeps coefficients positive.
    local alpha=math.min(.2,cfg.diffusion*dt)
    local decay=math.exp(-cfg.decay*dt)
    local touched={}
    for id in pairs(f.active) do
        touched[id]=true
        for _,other in ipairs(f.nodes[id].links) do touched[other]=true end
    end
    for id in pairs(sources) do touched[id]=true end
    for id in pairs(f.pending) do touched[id]=true end
    local ids={};for id in pairs(touched) do ids[#ids+1]=id end;table.sort(ids)
    local nextValues={}
    for _,id in ipairs(ids) do
        local n=f.nodes[id]
        local values={};nextValues[id]=values
        for _,channel in ipairs(CHANNELS) do
            local value=n[channel]*(1-alpha*#n.links)
            for _,other in ipairs(n.links) do value=value+f.nodes[other][channel]*alpha end
            values[channel]=math.min(cfg.maxSignal,math.max(0,value*decay
                +(sources[id] and sources[id][channel] or 0)
                +(f.pending[id] and f.pending[id][channel] or 0)))
        end
    end
    f.active={}
    for _,id in ipairs(ids) do
        local n=f.nodes[id]
        for _,channel in ipairs(CHANNELS) do
            local value=nextValues[id][channel]
            n[channel]=value>=cfg.signalEpsilon and value or 0
            if n[channel]>0 then f.active[id]=true end
        end
    end
    f.pending={}
    w.tissueDefenseCount=0
    for _,c in ipairs(w.cells) do
        if c.state=="HEALTHY" or c.state=="EXPOSED" then
            local id=cellNode(w,c)
            local level=id and f.nodes[id].activity or 0
            if level>=cfg.defenseThreshold then
                c.antiviralStimulus=math.min(cfg.defenseDelay,(c.antiviralStimulus or 0)+dt)
                if c.antiviralStimulus>=cfg.defenseDelay then
                    if (c.antiviralRemaining or 0)<=0 then w:Emit("tissue_defense_start",{cellId=c.id}) end
                    c.antiviralRemaining=cfg.defenseDuration
                end
            else c.antiviralStimulus=math.max(0,(c.antiviralStimulus or 0)-dt) end
            c.antiviralRemaining=math.max(0,(c.antiviralRemaining or 0)-dt)
            local before=c.antiviralStrength or 0
            local goal=c.antiviralRemaining>0 and 1 or 0
            c.antiviralStrength=math.max(0,math.min(1,goal>before and math.min(goal,before+dt/cfg.defenseRamp) or math.max(goal,before-dt/cfg.defenseFade)))
            if c.antiviralStrength>0 then w.tissueDefenseCount=w.tissueDefenseCount+1 end
            if before>0 and c.antiviralStrength==0 then w:Emit("tissue_defense_end",{cellId=c.id}) end
        else c.antiviralStimulus,c.antiviralRemaining,c.antiviralStrength=0,0,0 end
    end
end
function Ecology.Update(w,dt)
    if not w.ecology or dt<=0 or dt~=dt or dt==math.huge then return end
    local cfg=w.config.ecology
    w.ecology.clock=w.ecology.clock+dt
    while w.ecology.clock+1e-9>=cfg.step do
        w.ecology.clock=math.max(0,w.ecology.clock-cfg.step);tick(w,cfg.step)
    end
end
function Ecology.ClearDefense(w,cell)
    if (cell.antiviralStrength or 0)>0 then w.tissueDefenseCount=math.max(0,(w.tissueDefenseCount or 0)-1) end
    cell.antiviralStrength,cell.antiviralStimulus,cell.antiviralRemaining=0,0,0
end
function Ecology.InfectionMultiplier(w,cell)
    if not w.ecology then return 1 end
    return 1-w.config.ecology.defenseSuppression*(cell.antiviralStrength or 0)
end
return Ecology
