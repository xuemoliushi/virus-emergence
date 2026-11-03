-- 只读验收采样；不改变模拟步长、胜负、质量或调度。
local Metrics = {}
---@type SwarmWorld?
local lastWorld = nil
local nextTime, frames, frameTime, peakFrame = 0,0,0,0

---@param sim SimState
---@param dt number 引擎 TimeStep，帧间隔而非 CPU/GPU 独占耗时。
function Metrics.Update(sim,dt)
    local w=sim.world
    if lastWorld~=w then lastWorld=w;nextTime=0;frames,frameTime,peakFrame=0,0,0 end
    if not sim:CanAct() then return end
    frames,frameTime,peakFrame=frames+1,frameTime+dt,math.max(peakFrame,dt)
    if w.time<nextTime then return end
    nextTime=w.time+5
    sim:RecordFlow("sample")
    local c=w:GetCountsSnapshot()
    print(string.format("[EvolutionMetrics] t=%.2f stage=%d completed=%d formal_cards=%d qualified=%s debug_run=%s task=%s",
        w.time,sim.stage,sim.evolution.completed,sim.cards.formalCount,tostring(sim.victoryQualified),tostring(sim.debugRun),sim.task.detail or ""))
    local branches,searches=0,0
    for _ in pairs(w.channelPatrolAssignments) do branches=branches+1 end
    for _,im in ipairs(w.immunes) do if im.state=="search" then searches=searches+1 end end
    print(string.format("[CardMetrics] t=%.2f groups=%d/%d current=%d mass=%d brain=%s brain_assisted=%d brain_loss=%d immunes=%d nodes=%d inflammation=%.3f damage=%.3f splits=%d switches=%d alert=%d active=%d debug=%s frame_mean_ms=%.2f frame_peak_ms=%.2f branches=%d searches=%d",
        w.time,c.groups,w.maxPlayerSwarms,w.currentControlledSwarmId,w.player.mass,tostring(w.swarmBrainEnabled),
        w.stats.brainAssistedInfections,w.stats.brainMassLost,c.immune,c.infected,sim.globalInflammation,
        sim.globalTissueDamage,w.stats.totalSplits,w.controlSwitchCount or 0,w.immuneAlertLevel,
        w.activeImmuneAlertLevel,tostring(w.debugImmuneAlertLevel),frameTime/math.max(1,frames)*1000,peakFrame*1000,branches,searches))
    frames,frameTime,peakFrame=0,0,0
end
return Metrics
