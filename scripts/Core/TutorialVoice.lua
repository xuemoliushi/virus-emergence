-- 单声源分句旁白；只读取教程状态，不推进模拟或改变操作条件。
local Cues = require("Core.TutorialVoiceCues")
local LoadJob = require("Core.LoadJob")

---@class TutorialVoice
---@field source SoundSource?
---@field sounds table<string, Sound|false>
---@field tutorial Tutorial?
---@field step string?
---@field queue string[]
---@field current string?
---@field sound Sound?
---@field suspended boolean
---@field position number
---@field elapsed number
---@field preload_ {pending:integer,elapsed:number,cancelled:boolean,timedOut:boolean}?
local Voice = {}
Voice.__index = Voice

---@param scene Scene
---@return TutorialVoice
function Voice.New(scene)
    local self = setmetatable({}, Voice)
    self.source = scene:CreateChild("TutorialVoiceSource"):CreateComponent("SoundSource")
    self.source:SetSoundType(SOUND_VOICE)
    self.sounds, self.queue = {}, {}
    self.tutorial, self.step, self.current, self.sound = nil, nil, nil, nil
    self.suspended, self.position, self.elapsed = false, 0, 0
    self.preload_=nil
    return self
end

function Voice:Clear()
    if self.source and self.current then self.source:StopImmediate() end
    self.tutorial, self.step, self.current, self.sound = nil, nil, nil, nil
    self.queue, self.position, self.elapsed, self.suspended = {}, 0, 0, false
end

function Voice:Suspend()
    if self.suspended or not self.current or not self.source then return end
    local start=Cues.clips[self.current].start or 0
    self.position = self.source:IsPlaying() and self.source:GetTimePosition() or start+self.elapsed
    self.source:StopImmediate()
    self.suspended = true
end

-- Decode while the main menu prepares the world, rather than at a lesson change.
function Voice:Preload()
    if self.preload_ then return end
    local batch={pending=0,elapsed=0,cancelled=false,timedOut=false}
    self.preload_=batch
    local ids={}
    for id in pairs(Cues.clips) do ids[#ids+1]=id end
    table.sort(ids)
    for _,id in ipairs(ids) do
        if self.sounds[id]==nil and cache.GetResourceAsync then
            batch.pending=batch.pending+1
            local resolved=false
            local function loaded(sound)
                if resolved or batch.cancelled then return end
                resolved=true
                if not batch.timedOut then batch.pending=batch.pending-1 end
                self.sounds[id]=sound or false
                if sound then sound:SetLooped(false) end
            end
            local ok=pcall(function() cache:GetResourceAsync("Sound",Cues.clips[id].path,loaded) end)
            if not ok then loaded(nil) end
        else self:Load(id);LoadJob.Checkpoint() end
    end
end

---@param dt number
---@return boolean
function Voice:PreloadReady(dt)
    local batch=self.preload_
    if not batch or batch.pending==0 then return true end
    batch.elapsed=batch.elapsed+math.max(0,math.min(dt,0.1))
    if batch.elapsed>=15 then
        batch.timedOut=true
        batch.pending=0
        -- Keep the tutorial usable without audio if a download never completes.
        for id in pairs(Cues.clips) do if self.sounds[id]==nil then self.sounds[id]=false end end
        return true
    end
    return false
end

---@return boolean
function Voice:IsSpeaking()
    return self.current ~= nil and not self.suspended and self.source ~= nil and self.source:IsPlaying()
end

---@param id string
---@return Sound?
function Voice:Load(id)
    local cached = self.sounds[id]
    if cached ~= nil then return cached or nil end
    local sound = cache:GetResource("Sound", Cues.clips[id].path)
    self.sounds[id] = sound or false
    if sound then sound:SetLooped(false)
    else print("[TutorialVoice] 配音加载失败，保留文字引导 " .. Cues.clips[id].path) end
    return sound
end

function Voice:Next()
    if not self.source then return end
    self.current, self.sound, self.position, self.elapsed, self.suspended = nil, nil, 0, 0, false
    while #self.queue > 0 do
        local id = table.remove(self.queue, 1)
        local sound = self:Load(id)
        if sound then
            self.current, self.sound = id, sound
            self.source:Play(sound, 0, 1) -- 0 = WAV 原采样率；音量由 SOUND_VOICE 分类控制。
            self.position=Cues.clips[id].start or 0
            if self.position>0 then self.source:Seek(self.position) end
            return
        end
    end
end

---@param dt number
---@param sim SimState?
---@param mode string?
function Voice:Update(dt, sim, mode)
    if dt <= 0 or dt ~= dt or dt == math.huge or not self.source then return end
    local tutorial = sim and sim.tutorial
    -- Final help disappears independently; let its already-started narration finish
    -- in normal play. Interruption, skip, reset and endings still stop it immediately.
    local outro=tutorial and tutorial==self.tutorial and self.step=="task" and tutorial.completed==true
    if not tutorial or (not tutorial.active and not outro) or sim.ending then
        self:Clear()
        return
    end
    if self.tutorial ~= tutorial then
        self:Clear()
        self.tutorial = tutorial
    end
    local changed = self.step ~= tutorial.step
    if changed then
        -- Text and narration belong to the same lesson, including natural transitions.
        if self.current then
            self.source:StopImmediate()
            self.current, self.sound, self.position, self.elapsed, self.suspended = nil, nil, 0, 0, false
        end
        self.queue = {}
        for _, id in ipairs(Cues.steps[tutorial.step] or {}) do self.queue[#self.queue+1] = id end
        self.step = tutorial.step
    end
    local blocked = mode ~= "game"
    for reason in pairs(sim.pauseReasons) do if reason ~= "tutorial" then blocked = true end end
    if blocked then self:Suspend(); return end
    if self.suspended and self.sound then
        local finish=Cues.clips[self.current].finish or self.sound:GetLength()
        if finish > 0 and self.position >= finish then
            self.current, self.sound = nil, nil
        else
            self.source:Play(self.sound, 0, 1)
            self.source:Seek(math.max(0, self.position))
        end
        self.suspended = false
    end
    if self.current then
        self.elapsed = self.elapsed + dt
        local cue=Cues.clips[self.current]
        local finish=cue.finish or cue.seconds
        local length=finish-(cue.start or 0)
        -- Give asynchronous starts a short grace period, and bound a stuck decoder.
        if self.source:GetTimePosition()>=finish or
            (self.elapsed >= 0.25 and not self.source:IsPlaying()) or self.elapsed > length + 0.5 then
            self.source:StopImmediate()
            self:Next()
        end
    else self:Next() end
end

function Voice:Destroy()
    if self.preload_ then self.preload_.cancelled=true;self.preload_=nil end
    self:Clear()
    self.source, self.sounds = nil, {}
end

return Voice
