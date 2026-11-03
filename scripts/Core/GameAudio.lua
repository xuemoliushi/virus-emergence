-- 菜单/剧情共享底乐，追逐层使用固定声源，不重启常态音乐或改设置音量。
local Config = require("Core.Config")
local ChaseMusic = require("Core.ChaseMusic")
local TutorialVoice = require("Core.TutorialVoice")
local GameplaySounds = require("Core.GameplaySounds")
local BirdAmbience = require("Core.BirdAmbience")

---@class CardChoicePlayback
---@field duration number
---@field position fun():number

---@class GameAudio
---@field scene Scene?
---@field music SoundSource?
---@field musicSound Sound?
---@field musicPath string?
---@field musicRetryIn number
---@field click SoundSource?
---@field clickSound Sound?
---@field cardChoice SoundSource?
---@field cardChoiceSound Sound?
---@field entryWhoosh SoundSource?
---@field entryWhooshSound Sound?
---@field entryMusic Sound?
---@field entryMusicPrepared boolean
---@field menuMusic Sound?
---@field menuMusicPrepared boolean
---@field mode string?
---@field transition SoundSource?
---@field transitionSound Sound?
---@field heartbeat SoundSource[]
---@field heartbeatSound Sound?
---@field chase ChaseMusic
---@field world SwarmWorld?
---@field endingActive boolean
---@field endingStopped boolean
---@field endingElapsed number
---@field endingSources {source:SoundSource,gain:number,duration:number,score:boolean,stopped:boolean}[]
---@field endingMix number
---@field tutorialVoice TutorialVoice?
---@field effects GameplaySounds
---@field birds BirdAmbience
---@field heartbeatRetryIn number
local GameAudio = {}
GameAudio.__index = GameAudio

function GameAudio.New()
    local self = setmetatable({}, GameAudio)
    -- Scene 由对象强持有，不能仅作为初始化函数的局部变量。
    self.scene = Scene()
    self.effects = GameplaySounds.New(self.scene)
    self.birds = BirdAmbience.New(self.scene)
    self.tutorialVoice = TutorialVoice.New(self.scene)
    self.music = self.scene:CreateChild("MusicSource"):CreateComponent("SoundSource")
    self.music:SetSoundType(SOUND_MUSIC)
    self.musicRetryIn = 0
    self.click = self.scene:CreateChild("MenuClickSource"):CreateComponent("SoundSource")
    self.click:SetSoundType(SOUND_EFFECT)
    self.clickSound = cache:GetResource("Sound", "audio/menu_click.wav")
    if self.clickSound then self.clickSound:SetLooped(false)
    else print("[Audio] 按键音效加载失败 audio/menu_click.wav") end
    self.cardChoice = self.scene:CreateChild("CardChoiceSource"):CreateComponent("SoundSource")
    self.cardChoice:SetSoundType(SOUND_EFFECT)
    self.cardChoiceSound = cache:GetResource("Sound", "audio/card_choice.wav")
    if self.cardChoiceSound then self.cardChoiceSound:SetLooped(false)
    else print("[Audio] 选卡音效加载失败 audio/card_choice.wav") end
    self.entryWhoosh = self.scene:CreateChild("MenuEntryWhoosh"):CreateComponent("SoundSource")
    self.entryWhoosh:SetSoundType(SOUND_EFFECT)
    self.entryWhooshSound = cache:GetResource("Sound", "audio/menu_entry_membrane.wav")
    if self.entryWhooshSound then self.entryWhooshSound:SetLooped(false) end
    self.entryMusic,self.entryMusicPrepared=nil,false
    self.menuMusic,self.menuMusicPrepared=nil,false
    self.transition = self.scene:CreateChild("ChaseTransition"):CreateComponent("SoundSource")
    self.transition:SetSoundType(SOUND_MUSIC)
    local heartbeat = self.scene:CreateChild("Heartbeat1"):CreateComponent("SoundSource")
    heartbeat:SetSoundType(SOUND_MUSIC)
    self.heartbeat = { heartbeat }
    self.transitionSound = cache:GetResource("Sound", Config.DynamicMusic.introPath)
    self.heartbeatSound = cache:GetResource("Sound", Config.DynamicMusic.heartbeatPath)
    if self.transitionSound then self.transitionSound:SetLooped(false)
    else print("[Audio] 追逐过渡加载失败 " .. Config.DynamicMusic.introPath) end
    if self.heartbeatSound then self.heartbeatSound:SetLooped(true)
    else print("[Audio] 心跳素材加载失败 " .. Config.DynamicMusic.heartbeatPath) end
    self.chase = ChaseMusic.New(Config.DynamicMusic, self.transitionSound and self.transitionSound:GetLength() or 0)
    self.endingActive,self.endingStopped,self.endingElapsed=false,false,0
    self.endingMix=0
    ---@type {source:SoundSource,gain:number,duration:number,score:boolean,stopped:boolean}[]
    self.endingSources={}
    return self
end

-- Request the menu resource early so DWP can download it during map preparation,
-- but leave the playback source stopped until that busy period has ended.
function GameAudio:PrepareMenuMusic()
    if self.menuMusicPrepared then return end
    self.menuMusic=cache:GetResource("Sound","audio/menu_theme.wav")
    self.menuMusicPrepared=true
end

function GameAudio:ResetChase()
    self.heartbeatRetryIn = 0
    self.endingActive,self.endingStopped,self.endingElapsed=false,false,0
    self.endingMix=0
    self.endingSources={}
    self.chase:Reset()
    self.birds:Reset()
    self.world = nil
    if self.transition then self.transition:StopImmediate() end
    for _, source in ipairs(self.heartbeat) do source:StopImmediate() end
    if self.music then self.music:SetGain(Config.DynamicMusic.normalGain) end
end

-- Driven by decoded film time, so slow loading cannot leave a silent gap.
function GameAudio:SetEndingMix(progress)
    self.endingMix=math.max(0,math.min(1,progress))
end

-- 显式绑定放在开局后、玩家操作前；Update保留世界更换兜底。
function GameAudio:BindSim(sim)
    if self.world==sim.world and self.effects.runId==sim.world.abilityRunId then return end
    self:ResetChase()
    self.world=sim.world
    self.effects:BindRun(sim.world.abilityRunId,sim.world.immuneAlertLevel)
    self.birds:BindRun(sim.world)
end

-- Decode/cache the destination track during preparation, never at the black handoff.
---@param withTutorial boolean?
function GameAudio:PrepareEntryMusic(withTutorial)
    self.birds:Preload()
    self.entryMusic = cache:GetResource("Sound", "audio/bgm.mp3")
    if self.entryMusic then self.entryMusic:SetLooped(true) end
    self.entryMusicPrepared = true
    if withTutorial then self:PrepareTutorial() end
end

function GameAudio:PrepareTutorial()
    if self.tutorialVoice then self.tutorialVoice:Preload() end
end

---@param dt number
---@return boolean
function GameAudio:IsEntryAudioReady(dt)
    return not self.tutorialVoice or self.tutorialVoice:PreloadReady(dt)
end

---@param mode string
function GameAudio:SetMode(mode)
    if self.mode == mode or not self.music then return end
    if mode ~= "game" and self.tutorialVoice then self.tutorialVoice:Suspend() end
    self:ResetChase()
    self.effects.enabled=mode=="game"
    self.effects:ClearEffects()
    self.music:StopImmediate()
    self.mode, self.musicSound, self.musicPath = nil, nil, nil
    self.musicRetryIn = 1
    if mode == "loading" then
        self.mode = mode
        self.effects.ambience:StopImmediate()
        if self.click then self.click:StopImmediate() end
        if self.entryWhoosh then self.entryWhoosh:StopImmediate() end
        return
    end
    local path = mode == "menu" and "audio/menu_theme.wav" or "audio/bgm.mp3"
    ---@type Sound?
    local sound = nil
    if mode=="menu" and self.menuMusicPrepared then sound=self.menuMusic
    elseif mode=="game" and self.entryMusicPrepared then sound=self.entryMusic
    else sound=cache:GetResource("Sound",path) end
    if not sound then print("[Audio] 音乐加载失败 " .. path); return end
    self.musicSound, self.musicPath = sound, path
    sound:SetLooped(true)
    self.music:Play(sound, 0, Config.DynamicMusic.normalGain)
    self.mode = mode
end

-- 底乐通常由引擎循环；声源意外结束时恢复同一曲目，不重置追逐状态。
-- 若设备拒绝播放，最多每秒重试一次，避免逐帧 Play/日志风暴。
---@param dt number
---@param gain number
function GameAudio:UpdateMusic(dt, gain)
    if not self.mode or not self.music or not self.musicSound then return end
    self.music:SetGain(gain)
    if self.music:IsPlaying() then
        self.musicRetryIn = 0
        return
    end
    self.musicRetryIn = math.max(0, self.musicRetryIn - dt)
    if self.musicRetryIn > 0 then return end
    self.musicRetryIn = 1
    self.musicSound:SetLooped(true)
    self.music:Play(self.musicSound, 0, gain)
    print("[Audio] 底乐停播，恢复播放 " .. tostring(self.musicPath))
end

---@param dt number
---@param sim SimState?
function GameAudio:Update(dt, sim)
    if not self.mode or not self.music then return end
    if self.mode == "loading" then return end
    if dt <= 0 or dt ~= dt or dt == math.huge then return end
    if self.mode=="game" and sim then self:BindSim(sim) end
    if self.tutorialVoice then self.tutorialVoice:Update(dt, sim, self.mode) end
    self.effects:Update(dt,self.mode,sim,self.mode=="game" and sim and sim.ending~=nil)
    if self.mode=="game" and sim and sim.ending then
        if not self.endingActive then
            self.endingActive=true
            self.effects:BeginEnding(sim.ending)
            self.chase:Reset()
            local cfg=Config.EndingTransition
            local function capture(source,duration,score)
                if source then self.endingSources[#self.endingSources+1]={source=source,
                    gain=source:GetGain(),duration=duration,score=score or false,stopped=false} end
            end
            capture(self.music,cfg.audioFade,true)
            capture(self.transition,cfg.pulseFade)
            capture(self.birds.source,cfg.effectsFade)
            capture(self.cardChoice,cfg.effectsFade);capture(self.entryWhoosh,cfg.effectsFade)
            for _,source in ipairs(self.heartbeat) do capture(source,cfg.pulseFade) end
            for _,source in ipairs(self.effects:BackgroundSources()) do
                capture(source,source==self.effects.ambience and cfg.audioFade or cfg.effectsFade)
            end
        end
        if not self.endingStopped then
            self.endingElapsed=self.endingElapsed+dt
            local stopped=true
            for _,item in ipairs(self.endingSources) do
                local t=math.min(1,self.endingElapsed/(sim.ending=="victory" and item.duration or .4))
                local gain=1-t*t*(3-2*t)
                if sim.ending=="victory" and item.score then
                    gain=self.endingMix>=1 and 0 or math.cos(self.endingMix*math.pi*.5)
                end
                if not item.stopped then
                    item.source:SetGain(item.gain*gain)
                    if gain<=0 then item.source:StopImmediate();item.stopped=true end
                end
                stopped=stopped and item.stopped
            end
            self.endingStopped=stopped
        end
        return
    end
    if self.mode ~= "game" then
        self.birds:Update(dt,self.mode,sim,true)
        self:UpdateMusic(dt, Config.DynamicMusic.normalGain)
        return
    end
    local cfg = Config.DynamicMusic
    local chased=ChaseMusic.IsChased(sim)
    ---@type {intro:boolean,heartbeat:boolean,mix:number}
    local frame = self.chase:Update(dt, chased, self.transition and self.transition:IsPlaying() or false)
    self.birds:Update(dt,self.mode,sim,chased or frame.mix>0 or (self.tutorialVoice and self.tutorialVoice:IsSpeaking()))
    if frame.intro and self.transition and self.transitionSound then
        self.transition:Play(self.transitionSound, 0, cfg.introGain)
    end
    self:UpdateMusic(dt, cfg.normalGain * (1 - (1 - cfg.duckMultiplier) * frame.mix))
    self.heartbeatRetryIn = math.max(0, self.heartbeatRetryIn - dt)
    for _, source in ipairs(self.heartbeat) do
        source:SetGain(cfg.heartbeatGain * frame.mix)
        if self.chase.state == "normal" then source:StopImmediate() end
        -- 过渡结束后的首帧启动，之后由引擎连续循环，不逐帧重播或补拍。
        if frame.heartbeat and self.heartbeatSound and not source:IsPlaying() and self.heartbeatRetryIn <= 0 then
            source:Play(self.heartbeatSound, 0, cfg.heartbeatGain * frame.mix)
            self.heartbeatRetryIn = math.max(1, self.heartbeatSound:GetLength())
        end
    end
end

function GameAudio:PlayClick()
    if self.mode=="loading" then return end
    if not self.click or not self.clickSound then return end
    -- 0 使用素材原始采样率；音效与音乐的类别音量由 UserSettings 统一控制。
    self.click:Play(self.clickSound, 0, 1)
end

function GameAudio:PlayEntryWhoosh()
    if self.entryWhoosh and self.entryWhooshSound then
        self.entryWhoosh:Play(self.entryWhooshSound, 0, 0.8)
    end
end

---@return CardChoicePlayback?
function GameAudio:PlayCardChoice()
    if not self.cardChoice or not self.cardChoiceSound then return end
    local duration = self.cardChoiceSound:GetLength()
    self.cardChoice:Play(self.cardChoiceSound, 0, 1)
    return {
        duration = duration,
        position = function()
            if not self.cardChoice or not self.cardChoice:IsPlaying() then return duration end
            return self.cardChoice:GetTimePosition()
        end,
    }
end

function GameAudio:Destroy()
    self.effects:Destroy()
    if self.tutorialVoice then self.tutorialVoice:Destroy(); self.tutorialVoice = nil end
    self:ResetChase()
    if self.music then self.music:StopImmediate() end
    if self.click then self.click:StopImmediate() end
    if self.cardChoice then self.cardChoice:StopImmediate() end
    if self.entryWhoosh then self.entryWhoosh:StopImmediate() end
    if self.scene then self.scene:Dispose() end
    self.scene, self.music, self.click, self.clickSound, self.mode = nil, nil, nil, nil, nil
    self.musicSound, self.musicPath = nil, nil
    self.cardChoice, self.cardChoiceSound = nil, nil
    self.entryWhoosh, self.entryWhooshSound = nil, nil
    self.entryMusic,self.entryMusicPrepared=nil,false
    self.menuMusic,self.menuMusicPrepared=nil,false
    self.musicRetryIn = 0
end

return GameAudio
