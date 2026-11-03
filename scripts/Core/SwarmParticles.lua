-- Stable extraction: preserve both formation order and the old reverse take order.
local Particles={}

---@param items GroupVirusParticle[]
---@param swarmId integer
---@param count integer
---@return GroupVirusParticle[]
function Particles.Take(items,swarmId,count)
    local taken={}
    if count<16 then
        for i=#items,1,-1 do
            if #taken>=count then break end
            if items[i].swarmId==swarmId then taken[#taken+1]=table.remove(items,i) end
        end
        return taken
    end
    local first=#items+1
    for i=#items,1,-1 do
        if #taken>=count then break end
        if items[i].swarmId==swarmId then taken[#taken+1]=items[i];first=i end
    end
    -- All particles of this swarm in the selected suffix were taken. Compact
    -- once instead of shifting every other swarm for each removed particle.
    local total,write=#items,first
    for read=first,total do
        local item=items[read]
        if item.swarmId~=swarmId then items[write]=item;write=write+1 end
    end
    for i=total,write,-1 do items[i]=nil end
    return taken
end

return Particles
