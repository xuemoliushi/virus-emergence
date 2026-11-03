-- 在实体移除/切群前保存纯数值表现快照；不消费玩法事件，不使用模拟随机数。
local Bridge = {}
local names = {}
for _, name in ipairs({"absorb_pulse","absorb","infection_complete","split","auto_split","merge",
    "immune_attack","node_attack","swarm_cleared","release_batch","cell_dead","node_attack_start",
    "immune_alert_changed","skill_used","ability_released","tail_preserved","node_takeover",
    "switch_control","anchor_changed","hide_enter","hide_exit","glide_start","relay_started","camouflage_on","skill_failed"}) do
    names[name] = true
end

function Bridge.Capture(world, name, payload)
    if not names[name] then return nil end
    local copy = {}
    for key, value in pairs(payload) do
        if type(value) ~= "table" and type(value) ~= "userdata" then copy[key] = value end
    end
    local listener = world:SwarmById(world.currentControlledSwarmId)
    local entity = payload.swarmId and world:SwarmById(payload.swarmId)
    if payload.cellId then
        for _, cell in ipairs(world.cells) do if cell.id == payload.cellId then entity = cell; break end end
    end
    copy.x, copy.y = copy.x or (entity and entity.x), copy.y or (entity and entity.y)
    copy.listenerX, copy.listenerY = payload.listenerX or (listener and listener.x), payload.listenerY or (listener and listener.y)
    copy.controlId = payload.controlId or world.currentControlledSwarmId
    world.audioSequence = (world.audioSequence or 0) + 1
    return {name=name, payload=copy, runId=world.abilityRunId, sequence=world.audioSequence}
end

return Bridge
