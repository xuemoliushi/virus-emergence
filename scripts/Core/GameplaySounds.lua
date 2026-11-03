-- 固定声源池与帧级裁决。只有不可变事件快照进入这里，不驱动模拟。
local Config = require("Core.Config")
local Bus = require("Core.EventBus")
---@class GameplaySounds
---@field sounds table<string, Sound>
---@field slots {source:SoundSource,priority:number}[]
---@field queue {id:string,payload:table,key:string,entityKey:string,gain:number,priority:number,score:number,at:number}[]
---@field ambience SoundSource
---@field ambienceSound Sound?
---@field defeat SoundSource
---@field runId integer?
local Sounds = {}
Sounds.__index = Sounds

function Sounds.New(scene)
    local self=setmetatable({},Sounds)
    self:Init(scene)
    return self
end

function Sounds:Init(scene)
    self.sounds,self.slots,self.queue,self.tokens={},{},{},{}
    self.clock,self.sequence,self.ambienceGain,self.ambienceRetry=0,0,0,0
    self.last,self.entityLast,self.seen,self.seenOrder={},{},{},{}
    self.alertLevel=0
    self.enabled=false
    for id,def in pairs(Config.SoundEffects) do
        local sound=cache:GetResource("Sound",def.path)
        if sound then sound:SetLooped(false);self.sounds[id]=sound
        else print("[Audio] 音效加载失败 "..def.path) end
    end
    for i=1,Config.SoundMix.normalSources+Config.SoundMix.importantSources do
        local source=scene:CreateChild("GameplaySFX"..i):CreateComponent("SoundSource")
        source:SetSoundType(SOUND_EFFECT)
        self.slots[i]={source=source,priority=0}
    end
    self.defeat=scene:CreateChild("DefeatSFX"):CreateComponent("SoundSource")
    self.defeat:SetSoundType(SOUND_EFFECT)
    self.ambience=scene:CreateChild("MicroAmbience"):CreateComponent("SoundSource")
    self.ambience:SetSoundType(SOUND_AMBIENT)
    self.ambienceSound=cache:GetResource("Sound",Config.SoundMix.ambiencePath)
    if self.ambienceSound then self.ambienceSound:SetLooped(true)
    else print("[Audio] 环境音加载失败 "..Config.SoundMix.ambiencePath) end
    self.tokens={
        Bus.On(Bus.Events.AUDIO_WORLD,function(batch)
            if not self.enabled or batch.runId~=self.runId then return end
            for _,event in ipairs(batch.events) do
                if event.sequence>self.sequence then
                    self.sequence=event.sequence
                    self:Event(event.name,event.payload)
                end
            end
        end),
        Bus.On(Bus.Events.AUDIO_DENIED,function(event)
            if self.enabled and event.runId==self.runId then self:Queue("action_denied",{}) end
        end),
        Bus.On("cards:acquired",function(event)
            if self.enabled and event.runId==self.runId then self:Queue("card_acquired",{},event.choiceId) end
        end),
    }
end

function Sounds:ClearEffects()
    self.queue={}
    for _,slot in ipairs(self.slots) do slot.source:StopImmediate();slot.priority=0 end
    self.defeat:StopImmediate()
end

function Sounds:BindRun(runId,level)
    if self.runId==runId then return end
    self:ClearEffects()
    self.ambience:StopImmediate()
    self.ambienceGain,self.ambienceRetry=0,0
    self.runId,self.alertLevel,self.sequence=runId,level or 0,0
    self.last,self.entityLast,self.seen,self.seenOrder={},{},{},{}
end

function Sounds:Queue(id,payload,key,scale)
    local def=Config.SoundEffects[id]
    if not def then return end
    local distanceGain=1
    if not def.global then
        if payload.x and payload.y and payload.listenerX and payload.listenerY then
            local d=math.sqrt((payload.x-payload.listenerX)^2+(payload.y-payload.listenerY)^2)
            local mix=Config.SoundMix
            distanceGain=math.max(def.distantFloor or 0,math.min(1,(mix.farDistance-d)/(mix.farDistance-mix.nearDistance)))
        else
            -- 缺失位置不假装发生在镜头中心；主动操作可由controlId识别。
            distanceGain=payload.swarmId and payload.swarmId==payload.controlId and 1 or (def.distantFloor or .25)
        end
    end
    if distanceGain<=0 then return end
    local entity=payload.cellId or payload.swarmId or "global"
    local dedupe=id..":"..tostring(key or entity)
    if id=="anchor_on" or id=="anchor_off" then
        -- 同一帧开关多次只保留最后有效方向，避免排序颠倒声音。
        for i=#self.queue,1,-1 do
            local old=self.queue[i]
            if (old.id=="anchor_on" or old.id=="anchor_off") and old.payload.swarmId==payload.swarmId then
                table.remove(self.queue,i)
            end
        end
    end
    if def.persistent and self.seen[dedupe] then return end
    local item={id=id,payload=payload,key=dedupe,entityKey=id..":"..tostring(entity),
        gain=def.gain*distanceGain*(scale or 1),priority=def.priority,
        score=def.priority+(payload.swarmId==payload.controlId and .4 or 0)+distanceGain*.1,at=self.clock}
    for i,old in ipairs(self.queue) do
        if old.key==dedupe then if item.score>=old.score then self.queue[i]=item end;return end
    end
    if #self.queue>=Config.SoundMix.maxQueue then
        local weakest=1
        for i=2,#self.queue do if self.queue[i].score<self.queue[weakest].score then weakest=i end end
        if item.score<=self.queue[weakest].score then return end
        self.queue[weakest]=item
    else self.queue[#self.queue+1]=item end
end

function Sounds:Event(name,p)
    local direct={absorb_pulse="absorb_pulse",absorb="virus_absorb",infection_complete="infection_complete",
        split="swarm_split",merge="swarm_merge",swarm_cleared="swarm_cleared",cell_dead="cell_dead",
        node_attack_start="node_warning",tail_preserved="tail_preserve",node_takeover="node_takeover",
        switch_control="switch_control",hide_enter="hide_enter",hide_exit="hide_exit",glide_start="glide_start",relay_started="glide_start",
        camouflage_on="camouflage_on",skill_failed="action_denied"}
    if direct[name] then
        local key=name=="merge" and (tostring(p.swarmId)..":"..tostring(p.absorbedSwarmId)) or p.swarmId or p.cellId
        self:Queue(direct[name],p,key)
    elseif name=="immune_attack" and (p.killed or 0)>0 then self:Queue("swarm_hit",p)
    elseif name=="node_attack" then self:Queue(p.shielded and "shield_block" or "node_hit",p)
    elseif name=="release_batch" and (p.count or 0)>0 then self:Queue("release_batch",p)
    elseif name=="anchor_changed" then self:Queue(p.active and "anchor_on" or "anchor_off",p)
    elseif name=="immune_alert_changed" then
        if p.level>self.alertLevel then self:Queue("alert_up",p) end
        self.alertLevel=p.level
    elseif name=="skill_used" then
        local skill={emergency_dash="skill_dash",discrete_recall="skill_recall",node_cover="node_cover",local_flow="flow_redirect"}
        if skill[p.cardId] then self:Queue(skill[p.cardId],p,p.requestId)
        elseif p.cardId=="cluster_dispatch" and (p.command=="gather" or p.command=="hold") then
            self:Queue(p.command=="gather" and "dispatch_gather" or "dispatch_hold",p,p.requestId)
        end
    elseif name=="ability_released" then
        if p.kind=="decoy" then self:Queue("skill_decoy",p)
        elseif p.kind=="merge_seed" then self:Queue("skill_decoy",p,nil,.35)
        elseif p.kind=="rupture" then self:Queue("release_batch",p,nil,.35) end
    end
end

function Sounds:Flush(sim)
    table.sort(self.queue,function(a,b) if a.score==b.score then return a.key<b.key end;return a.score>b.score end)
    local played={}
    for _,item in ipairs(self.queue) do
        local def=Config.SoundEffects[item.id]
        local sound=self.sounds[item.id]
        local last=self.last[item.id] or -math.huge
        local entityLast=self.entityLast[item.entityKey] or -math.huge
        local valid=true
        if item.id=="node_warning" then
            valid=false
            for _,immune in ipairs(sim and sim.world.immunes or {}) do
                if immune.id==item.payload.immuneId and immune.state=="attack"
                    and immune.targetType=="cell" and immune.targetId==item.payload.cellId then valid=true;break end
            end
        end
        if valid and sound and not played[item.id]
            and self.clock-last>=def.interval and self.clock-entityLast>=(def.entityInterval or 0) then
            local selected=nil
            for i,slot in ipairs(self.slots) do
                if item.priority>=4 or i<=Config.SoundMix.normalSources then
                    if not slot.source:IsPlaying() then selected=slot;break end
                    if slot.priority<item.priority and (not selected or slot.priority<selected.priority) then selected=slot end
                end
            end
            if selected then
                selected.source:Play(sound,0,item.gain);selected.priority=item.priority
                self.last[item.id],self.entityLast[item.entityKey],played[item.id]=self.clock,self.clock,true
                if def.persistent then
                    self.seen[item.key]=true;self.seenOrder[#self.seenOrder+1]=item.key
                    if #self.seenOrder>256 then self.seen[table.remove(self.seenOrder,1)]=nil end
                end
            end
        end
    end
    self.queue={}
    -- 按时间淘汰实体限频记录，避免长局残留每一个死亡节点。
    for key,at in pairs(self.entityLast) do if self.clock-at>2 then self.entityLast[key]=nil end end
end

function Sounds:BeginEnding(outcome)
    self.queue={}
    if outcome=="extinct" and self.sounds.ending_defeat then
        self.defeat:Play(self.sounds.ending_defeat,0,Config.SoundEffects.ending_defeat.gain)
    end
end

function Sounds:BackgroundSources()
    local sources={self.ambience}
    for _,slot in ipairs(self.slots) do sources[#sources+1]=slot.source end
    return sources -- 失败专用声源不能参与0.4秒背景淡出。
end

function Sounds:Update(dt,mode,sim,ending)
    self.clock=self.clock+dt
    if ending then self.queue={};return end
    local cfg=Config.SoundMix
    local target=mode=="game" and sim and sim.started and cfg.ambienceGain or 0
    if target>0 and sim.paused then target=target*cfg.pauseMultiplier end
    local duration=target>self.ambienceGain and cfg.ambienceFadeIn or cfg.menuFadeOut
    local step=cfg.ambienceGain*dt/duration
    self.ambienceGain=self.ambienceGain+math.max(-step,math.min(step,target-self.ambienceGain))
    self.ambience:SetGain(self.ambienceGain)
    self.ambienceRetry=math.max(0,self.ambienceRetry-dt)
    if self.ambienceGain<=0 then self.ambience:StopImmediate()
    elseif self.ambienceSound and not self.ambience:IsPlaying() and self.ambienceRetry<=0 then
        self.ambience:Play(self.ambienceSound,0,self.ambienceGain);self.ambienceRetry=1
    end
    if mode=="game" then self:Flush(sim) else self.queue={} end
end

function Sounds:Destroy()
    self:ClearEffects();self.ambience:StopImmediate()
    for _,token in ipairs(self.tokens) do Bus.Off(token) end
    self.tokens={}
end

return Sounds
