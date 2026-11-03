-- 稀疏的宿主鸟叫线索；独立声源和随机流，不改底乐或模拟随机序列。
local Config=require("Core.Config")
local Random=require("Core.MapRandom")

---@class BirdHintProfile
---@field lastStage integer
---@field gainMin number
---@field gainMax number
---@field intervalMin number
---@field intervalMax number
---@class BirdHintClip
---@field path string
---@field sound Sound?
---@class BirdAmbience
---@field source SoundSource
---@field clips BirdHintClip[]
---@field random fun():number
---@field remaining number
---@field quietFor number
---@field gain number
---@field playGain number
---@field lastIndex integer
---@field retryIn number
---@field gainMin number
---@field gainMax number
---@field volumeRoll number
---@field waitingForEnd boolean
---@field Reset fun(self:BirdAmbience)
---@field Preload fun(self:BirdAmbience)
---@field BindRun fun(self:BirdAmbience,world:SwarmWorld)
---@field Update fun(self:BirdAmbience,dt:number,mode:string,sim:SimState?,blocked:boolean?)
local Birds={}
Birds.__index=Birds

---@param sim SimState?
---@return BirdHintProfile
local function profile(sim)
    local stage=sim and sim.evolution and sim.evolution.stage or 1
    local profiles=Config.BirdHints.profiles --[[@as BirdHintProfile[] ]]
    for _,entry in ipairs(profiles) do
        if stage<=entry.lastStage then return entry end
    end
    return profiles[#profiles]
end

local function approach(value,target,step)
    return value+math.max(-step,math.min(step,target-value))
end

---@param scene Scene
---@return BirdAmbience
function Birds.New(scene)
    local self=setmetatable({},Birds)
    self.source=scene:CreateChild("HostBirdHints"):CreateComponent("SoundSource")
    -- 鸟叫作为配乐的线索层，遵循音乐音量／静音设置。
    self.source:SetSoundType(SOUND_MUSIC)
    self.clips={}
    for _,path in ipairs(Config.BirdHints.clips) do self.clips[#self.clips+1]={path=path} end
    self.random=Random.New("host-bird-hints",53)
    self:Reset()
    return self
end

function Birds:Reset()
    self.source:StopImmediate();self.source:SetGain(0)
    self.remaining,self.quietFor,self.gain,self.playGain=Config.BirdHints.firstMin,0,0,0
    self.lastIndex,self.retryIn=0,0
    local first=Config.BirdHints.profiles[1]
    self.gainMin,self.gainMax=first.gainMin,first.gainMax
    self.volumeRoll,self.waitingForEnd=.5,false
end

function Birds:Preload()
    if not Config.BirdHints.enabled then return end
    for _,clip in ipairs(self.clips) do
        if not clip.sound then
            clip.sound=cache:GetResource("Sound",clip.path)
            if clip.sound then clip.sound:SetLooped(false) end
        end
    end
    self.retryIn=10
end

---@param world SwarmWorld
function Birds:BindRun(world)
    local seed=world.map and world.map.seed or Config.Gameplay.seed
    self.random=Random.New(tostring(seed)..":host-bird:"..tostring(world.abilityRunId or 0),53)
    self:Reset();self:Preload()
    local cfg=Config.BirdHints
    self.remaining=cfg.firstMin+self.random()*(cfg.firstMax-cfg.firstMin)
end

---@param dt number
---@param mode string
---@param sim SimState?
---@param blocked boolean?
function Birds:Update(dt,mode,sim,blocked)
    if dt<=0 or dt~=dt or dt==math.huge then return end
    -- 切回后台后的长帧不补发错过的鸟叫。
    dt=math.min(.25,dt)
    local cfg=Config.BirdHints
    local playing=self.source:IsPlaying()
    local allowed=cfg.enabled and mode=="game" and sim and sim.started and not sim.paused
        and not sim.ending and not blocked and not (sim.tutorial and sim.tutorial.active)
    if not allowed then
        self.quietFor=0
        self.gain=math.max(0,self.gain-self.playGain*dt/cfg.fadeOut)
        self.source:SetGain(self.gain)
        if playing and self.gain==0 then self.source:StopImmediate() end
        return
    end
    local current=profile(sim)
    -- 阶段只改变目标，不重置当前等待；正在鸣叫时也平滑过渡。
    local rise=cfg.gainRisePerSecond*dt
    self.gainMin=approach(self.gainMin,current.gainMin,rise)
    self.gainMax=approach(self.gainMax,current.gainMax,rise)
    self.retryIn=math.max(0,self.retryIn-dt)
    if self.retryIn==0 then
        for _,clip in ipairs(self.clips) do
            if not clip.sound then self:Preload();break end
        end
    end
    self.quietFor=self.quietFor+dt
    if playing then
        self.playGain=self.gainMin+(self.gainMax-self.gainMin)*self.volumeRoll
        self.gain=approach(self.gain,self.playGain,self.playGain*dt/cfg.fadeIn)
        self.source:SetGain(self.gain)
        return
    end
    if self.waitingForEnd then
        self.waitingForEnd=false
        -- 播放结束才按当时阶段抽取下一段间隔，暂停／转阶段都不补播。
        self.remaining=current.intervalMin+self.random()*(current.intervalMax-current.intervalMin)
    end
    self.gain=0;self.source:SetGain(0)
    if self.quietFor<cfg.quietGrace then return end
    self.remaining=self.remaining-dt
    if self.remaining>0 then return end
    local eligible={}
    for i,clip in ipairs(self.clips) do
        if clip.sound and i~=self.lastIndex then eligible[#eligible+1]=i end
    end
    if #eligible==0 then
        for i,clip in ipairs(self.clips) do if clip.sound then eligible[#eligible+1]=i end end
    end
    if #eligible==0 then
        return
    end
    local index=eligible[math.floor(self.random()*#eligible)+1]
    local sound=self.clips[index].sound
    if not sound then return end
    self.lastIndex=index
    self.volumeRoll=self.random()
    self.playGain=self.gainMin+(self.gainMax-self.gainMin)*self.volumeRoll
    self.gain=0
    self.waitingForEnd=true
    self.source:Play(sound,0,0)
end

return Birds
