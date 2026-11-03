local UI = require("urhox-libs/UI")
local Skin = require("UI.AssetTheme")
local Motion = require("UI.Disclosure")
local Mobile = require("UI.MobileLayout")
---@type GameConfig
local Config = require("Core.Config")
---@type EndingTransitionShot
local Shot = require("UI.EndingTransition")
local EXIT_HOLD_SECONDS=1.2 -- same hold duration as the opening tutorial
local WARM={255,198,124,255}

---@class EndingScreen
local Screen = {}
Screen.__index = Screen

---@return EndingScreen
function Screen.New(hud)
    local self=setmetatable({},Screen)
    self:init(hud)
    return self
end

function Screen:init(hud)
    self.hud=hud
    self.phase,self.elapsed,self.playTime="idle",0,0
    self.finishRequested=false
    self.generation=0
    self.playRequested=false
    self.exitArmed,self.exitTime=false,0
    self.shotTime,self.blendClock,self.mix,self.videoGain,self.exitGain,self.exitMix=0,0,0,0,0,0
    self.menuRequested=false
    ---@type string?
    self.loadError=nil
    ---@type string?
    self.outcome=nil
    ---@type VideoPlayerWidget?
    self.player=nil
    ---@type Widget?
    self.blocker=nil
    local function text(id,size)
        return UI.Label{id=id,text="",width="100%",fontSize=size or 13,
            fontColor=Skin.colors.text,whiteSpace="normal",flexShrink=0,pointerEvents="none"}
    end
    local rows={}
    for _,id in ipairs({"endingDisease","endingInfected","endingReleased","endingIndependent",
        "endingLost","endingGroups","endingPeak"}) do
        local row=text(id)
        row:SetStyle{width="48%",flexBasis="48%",flexGrow=1,minWidth=0}
        rows[#rows+1]=row
    end
    self.details=UI.Panel{id="endingDetails",width="100%",flexShrink=0,
        children={UI.Panel{width="100%",flexDirection="row",flexWrap="wrap",gap=10,padding=12,children=rows}}}
    self.motion=Motion.New(self.details)
    self.result=UI.SafeAreaView{id="endingResult",width="100%",height="100%",visible=false,
        nativeMenuInset=true,alignItems="center",justifyContent="center",padding=24,
        children={Skin.Frame{width="96%",maxWidth=760,height="96%",minHeight=0,padding=12,gap=8,children={
            Skin.Scroll{id="endingBody",width="100%",height=0,flexGrow=1,flexBasis=0,minHeight=0,children={
                UI.Panel{width="100%",gap=10,padding=4,children={
                    text("endingTitle",26),text("endingReason",14),text("endingTime",13),
                    Skin.Button{id="endingStatsToggle",text="本局数据 ▾",height=48,
                        onClick=function(button)
                            self.motion:Toggle()
                            button:SetText(self.motion.target==1 and "收起数据 ▴" or "本局数据 ▾")
                        end},self.details,
                }}}},
            UI.Panel{id="endingActions",width="100%",flexDirection="row",gap=12,flexShrink=0,children={
                Skin.Button{id="restartBtn",buttonKind="primary",text="再来一局",height=52,width=0,flexGrow=1,flexBasis=0,
                    onClick=function() self:Reset();if hud.onRestart then hud.onRestart() end end},
                Skin.Button{id="endingMenuBtn",buttonKind="secondary",text="返回主菜单",height=52,width=0,flexGrow=1,flexBasis=0,
                    onClick=function() self:DisposePlayer();if hud.onMenu then hud.onMenu() end end},
            }},
        }}}}
    self.matteA=UI.Panel{position="absolute",backgroundColor={0,0,0,255},pointerEvents="none"}
    self.matteB=UI.Panel{position="absolute",backgroundColor={0,0,0,255},pointerEvents="none"}
    self.videoHost=UI.Panel{id="endingVideoHost",position="absolute",left=0,top=0,
        width="100%",height="100%",backgroundColor=false,visible=false,children={self.matteA,self.matteB}}
    self.play=Skin.Button{id="endingPlay",text="播放影片",width=160,height=48,visible=false,
        position="absolute",left="50%",top="50%",translateX=-80,translateY=-24,
        onClick=function()
            if self.phase=="error" then self:RetryVideo()
            elseif self.player then self.player:Play() end
        end}
    self.back=Skin.Button{id="endingVideoBack",buttonKind="secondary",text="跳过影片",width=160,height=48,
        position="absolute",left="50%",top="50%",translateX=-80,translateY=40,
        visible=false,onClick=function() self.finishRequested=true end}
    self.exitHint=UI.Label{id="endingExitHint",text="长按 Esc 退出影片",width="100%",height=20,
        textAlign="right",fontSize=11,fontColor=WARM,pointerEvents="none"}
    self.exitFill=UI.Panel{id="endingExitProgress",width="0%",height="100%",
        backgroundColor=WARM,pointerEvents="none"}
    local exitHold=Skin.Frame{frameKind="tooltip",id="endingExitHold",width=222,maxWidth="100%",
        height=52,flexShrink=0,padding=10,gap=5,pointerEvents="none",children={self.exitHint,
            UI.Panel{width="100%",height=4,backgroundColor={68,48,70,255},pointerEvents="none",
                children={self.exitFill}}}}
    self.exitMask=UI.Panel{id="endingExitMask",position="absolute",left=0,top=0,width="100%",height="100%",
        backgroundColor={9,6,19,0},backgroundImage="",boxShadow=false,borderWidth=0,pointerEvents="none",visible=false}
    self.exitArea=UI.SafeAreaView{id="endingExitSafeArea",position="absolute",left=0,top=0,
        width="100%",height="100%",nativeMenuInset=true,padding=12,alignItems="flex-end",
        justifyContent="flex-start",pointerEvents="none",visible=false,
        backgroundColor=false,backgroundImage="",boxShadow=false,borderWidth=0,children={exitHold}}
    self.touchSkipButton=Skin.Button{id="endingTouchSkip",text="长按跳过影片",width=168,height=48,
        fontSize=13,buttonKind="secondary"}
    self.touchControls=UI.SafeAreaView{id="endingTouchControls",position="absolute",left=0,top=0,
        width="100%",height="100%",nativeMenuInset=true,padding=12,alignItems="flex-end",
        justifyContent="flex-start",pointerEvents="box-none",visible=false,children={self.touchSkipButton}}
    self.fade=UI.Panel{id="endingFade",position="absolute",left=0,top=0,width="100%",height="100%",
        backgroundColor={0,0,0,255},opacity=0,pointerEvents="none"}
    self.status=text("endingVideoStatus",13)
    self.status:SetStyle{position="absolute",left=24,bottom=24,width="80%",visible=false}
    self.root=UI.Panel{id="endingOverlay",visible=false,zIndex=35,position="absolute",left=0,top=0,
        width="100%",height="100%",backgroundColor=false,pointerEvents="auto",
        children={self.videoHost,self.result,self.status,self.play,self.back,self.exitMask,self.touchControls,self.exitArea,self.fade}}
end

function Screen:CanHoldExit()
    return self.outcome=="victory" and (self.phase=="waiting" or self.phase=="videoIn"
        or self.phase=="video" or self.phase=="error")
end

function Screen:ResetExitHold()
    self.exitArmed,self.exitTime=false,0
    self.exitArea:SetVisible(false);self.exitMask:SetVisible(false)
    self.exitFill:SetStyle{width="0%"}
    self.exitHint:SetText("长按 Esc 退出影片")
end

function Screen:UpdateExitHold(dt)
    local touch=Mobile.IsTouch()
    self.touchControls:SetVisible(touch and self:CanHoldExit())
    self.exitArea:SetStyle{paddingTop=touch and 72 or 12}
    -- Retain the dimmed image until the exit fade covers it, without a bright flash.
    if self.phase=="videoOut" then self.exitArmed=false;return end
    local focused=not input or (input.focus~=false and input.minimized~=true)
    local touchHeld=touch and self.touchControls:IsVisible() and self.touchSkipButton.state
        and self.touchSkipButton.state.pressed==true
    local held=touchHeld or (input and input.GetKeyDown and input:GetKeyDown(KEY_ESCAPE)) or false
    if touchHeld and focused then self.exitArmed=true end
    if not self:CanHoldExit() or not self.exitArmed or not focused or not held then
        self:ResetExitHold();return
    end
    if dt~=dt or dt==math.huge or dt==-math.huge then return end
    self.exitTime=math.min(EXIT_HOLD_SECONDS,self.exitTime+math.max(0,math.min(dt,.1)))
    local progress=self.exitTime/EXIT_HOLD_SECONDS
    self.exitArea:SetVisible(progress>0);self.exitMask:SetVisible(progress>0)
    self.exitFill:SetStyle{width=string.format("%.1f%%",progress*100)}
    self.exitHint:SetText(string.format("正在退出 · %.0f%%",progress*100))
    self.exitMask:SetStyle{backgroundColor={9,6,19,math.floor(190*progress)}}
    if self.exitTime+1e-9>=EXIT_HOLD_SECONDS then self.finishRequested=true end
end

function Screen:DisposePlayer()
    local player=self.player
    self.player=nil
    if player then
        player:Stop()
        self.videoHost:RemoveChild(player)
        player:Destroy()
    end
    if self.blocker then self.videoHost:RemoveChild(self.blocker);self.blocker:Destroy();self.blocker=nil end
end

function Screen:Show(outcome)
    self:Reset()
    self.outcome=outcome
    self.root:SetVisible(true)
    self.phase,self.elapsed="out",0
    UI.ClearFocus()
    local area=self.hud.root:FindById("hudSafeArea")
    if area then area:SetStyle{opacity=1} end
    local nav=self.hud.root:FindById("tissueNavigation")
    if nav then nav:SetVisible(false) end
    if outcome=="victory" then
        if self.hud.onEndingPose then self.hud.onEndingPose(1,false,0) end
        self:PrepareVideo()
    end
end

-- Preload silently; skip only the film's opening fade when decoding is ready.
function Screen:PrepareVideo()
    self.generation=self.generation+1
    local ticket=self.generation
    self:DisposePlayer()
    self.playRequested,self.playTime,self.loadError=false,0,nil
    local cfg=Config.EndingVideo
    local src=cfg and cfg[self.outcome]
    local Video=require("urhox-libs/Video")
    if not src or not Video.isSupported then
        self.loadError="当前设备暂时无法播放影片。"
        return
    end
    self.videoHost:SetVisible(true)
    self.videoHost:SetStyle{opacity=0}
    self.player=Video.VideoPlayer{id="endingVideo",src=src,width="100%",height="100%",
        autoPlay=false,loop=false,objectFit="contain",textureWidth=1920,textureHeight=1080,
        volume=0,backgroundColor={0,0,0,0},
        onTimeUpdate=function(_,time)
            if self.generation==ticket then self.playTime=math.max(0,time-Config.EndingTransition.videoOffset) end
        end,
        onEnded=function() if self.generation==ticket then self.finishRequested=true end end,
        onLoadError=function(_,code,name)
            if self.generation~=ticket then return end
            print("[Ending] video load failed: "..tostring(code).." "..tostring(name))
            self.loadError="影片暂时无法播放，可以重试或跳过影片。"
        end}
    if self.player then
        self.videoHost:AddChild(self.player)
        -- Cinematic clicks do not toggle pause accidentally.
        self.blocker=UI.Panel{position="absolute",left=0,top=0,width="100%",height="100%",
            pointerEvents="auto",onPointerDown=function(event) event:StopPropagation() end,
            onPointerUp=function(event) event:StopPropagation() end,
            onClick=function() end,onTap=function() end}
        self.videoHost:AddChild(self.blocker)
    else self.loadError="影片暂时无法播放，可以重试或跳过影片。" end
end

-- Keep black bars outside the image. Stacking full-frame black backgrounds under
-- a translucent video would darken the dissolve twice instead of blending it.
function Screen:UpdateVideoMatte()
    local l=self.videoHost:GetAbsoluteLayout()
    if l.w<=0 or l.h<=0 then return end
    if l.w/l.h>16/9 then
        local margin=math.max(0,(1-l.h*16/9/l.w)*50)
        self.matteA:SetStyle{left=0,top=0,width=tostring(margin).."%",height="100%"}
        self.matteB:SetStyle{left=tostring(100-margin).."%",top=0,width=tostring(margin).."%",height="100%"}
    else
        local margin=math.max(0,(1-l.w*9/16/l.h)*50)
        self.matteA:SetStyle{left=0,top=0,width="100%",height=tostring(margin).."%"}
        self.matteB:SetStyle{left=0,top=tostring(100-margin).."%",width="100%",height=tostring(margin).."%"}
    end
end

function Screen:StartVideo()
    local area=self.hud.root:FindById("hudSafeArea")
    if area then area:SetVisible(false);area:SetStyle{opacity=1} end
    if self.outcome~="victory" then
        self.root:SetStyle{backgroundColor={0,0,0,255}}
        self:ShowResult();return
    end
    self.phase,self.elapsed="waiting",0
end

function Screen:SetMix(progress)
    self.mix=progress
    if self.hud.onEndingMix then self.hud.onEndingMix(progress) end
end

function Screen:BeginVideoOut()
    self.exitGain,self.exitMix=self.videoGain,self.mix
    self.phase,self.elapsed="videoOut",0
end

function Screen:RetryVideo()
    self:ResetExitHold()
    self.play:SetVisible(false);self.back:SetVisible(false);self.status:SetVisible(false)
    self.play:SetText("播放影片")
    self.fade:SetStyle{opacity=0}
    self.root:SetStyle{backgroundColor=false}
    if self.hud.onEndingPose then self.hud.onEndingPose(Config.EndingTransition.zoom,false,1) end
    self:SetMix(0);self.videoGain=0
    self.finishRequested=false
    self:PrepareVideo()
    self.phase,self.elapsed="waiting",0
end

function Screen:ShowVideoError()
    self:ResetExitHold()
    self:SetMix(1)
    self.root:SetStyle{backgroundColor={0,0,0,255}}
    if self.hud.onEndingPose then self.hud.onEndingPose(Config.EndingTransition.zoom,true,1) end
    self.phase,self.elapsed="error",0
    self:DisposePlayer()
    self.generation=self.generation+1
    self.videoHost:SetVisible(false)
    self.fade:SetStyle{opacity=0}
    self.status:SetText(self.loadError or "影片暂时无法播放。")
    self.status:SetVisible(true)
    self.play:SetText("重试播放");self.play:SetVisible(true)
    self.back:SetVisible(true)
end

function Screen:FinishCinematic()
    self:ResetExitHold()
    self.touchControls:SetVisible(false)
    self:DisposePlayer()
    self.generation=self.generation+1
    self.videoHost:SetVisible(false)
    self.fade:SetStyle{opacity=1}
    self.back:SetVisible(false);self.play:SetVisible(false);self.status:SetVisible(false)
    self.phase="complete"
    local onComplete=self.hud.onCredits or self.hud.onMenu
    if not self.menuRequested and onComplete then
        self.menuRequested=true
        onComplete() -- main.lua queues the credits root outside UI callbacks.
    end
end

function Screen:ShowResult()
    if self.outcome=="victory" then self:FinishCinematic();return end
    self:DisposePlayer()
    if self.blocker then self.videoHost:RemoveChild(self.blocker);self.blocker:Destroy();self.blocker=nil end
    self.videoHost:SetVisible(false)
    self:ResetExitHold()
    self.touchControls:SetVisible(false)
    self.back:SetVisible(false);self.play:SetVisible(false);self.status:SetVisible(false)
    self.result:SetVisible(true)
    self.fade:SetStyle{opacity=1}
    self.phase,self.elapsed="resultIn",0
end

function Screen:Update(dt)
    if dt~=dt or dt==math.huge or dt==-math.huge then dt=0 end
    self.motion:Update(dt)
    if self.phase=="idle" or self.phase=="result" or self.phase=="complete" then return end
    self:UpdateExitHold(dt)
    self.elapsed=self.elapsed+math.max(0,dt)
    local cfg=Config.EndingTransition
    if self.player then self:UpdateVideoMatte() end
    if self.outcome=="victory" and (self.phase=="out" or self.phase=="waiting" or self.phase=="videoIn") then
        self.shotTime=math.min(cfg.zoomEnd,self.shotTime+math.max(0,dt))
        local opacity,zoom=Shot.Pose(self.shotTime)
        local area=self.hud.root:FindById("hudSafeArea")
        if area then area:SetStyle{opacity=opacity} end
        if self.hud.onEndingPose then self.hud.onEndingPose(zoom,false,self.shotTime/cfg.zoomEnd) end
    end
    local t=math.min(1,self.elapsed/0.4)
    local eased=t*t*(3-2*t)
    if self.phase=="out" then
        local victory=self.outcome=="victory"
        local area=self.hud.root:FindById("hudSafeArea")
        if area and not victory then area:SetStyle{opacity=1-eased} end
        self.fade:SetStyle{opacity=victory and 0 or eased}
        if self.elapsed>=(victory and cfg.videoStart or .4) then self:StartVideo() end
    elseif self.phase=="waiting" then
        if self.finishRequested then self:BeginVideoOut();return end
        if self.loadError then self:ShowVideoError();return end
        if self.player and self.player:IsReady() then
            if not self.playRequested then
                self.playRequested=true
                self.player:SetVolume(0)
                self.player:Seek(cfg.videoOffset)
                self.player:Play()
            end
            -- onPlay is optimistic on browsers. Reveal only after its real clock advances.
            if self.player:IsPlaying() and self.player:GetCurrentTime()>cfg.videoOffset+.03 then
                self.phase,self.elapsed="videoIn",0
                self.blendClock=self.player:GetCurrentTime()
                self.fade:SetStyle{opacity=0}
                self.play:SetVisible(false);self.status:SetVisible(false)
            elseif self.elapsed>2 then
                self.fade:SetStyle{opacity=0}
                self.play:SetVisible(true)
                self.status:SetVisible(false)
            end
        elseif self.elapsed>20 then
            self.loadError="影片准备时间较长，可以重试或跳过影片。"
            self:ShowVideoError()
        elseif self.elapsed>1.5 then
            self.fade:SetStyle{opacity=0}
            self.status:SetText("正在准备影片…");self.status:SetVisible(true)
        end
    elseif self.phase=="videoIn" then
        local clock=self.player and self.player:GetCurrentTime() or self.blendClock
        self.playTime=math.max(0,clock-cfg.videoOffset)
        self.play:SetVisible(self.elapsed>2 and self.player~=nil and not self.player:IsPlaying())
        local progress,gain=Shot.Mix(math.max(0,clock-self.blendClock))
        self:SetMix(progress);self.videoGain=gain
        self.videoHost:SetStyle{opacity=progress}
        if self.player then self.player:SetVolume((self.hud.videoVolume and self.hud.videoVolume() or 1)*gain) end
        if self.loadError then self:ShowVideoError()
        elseif self.finishRequested then self:BeginVideoOut()
        elseif progress>=1 then
            self.root:SetStyle{backgroundColor={0,0,0,255}}
            if self.hud.onEndingPose then self.hud.onEndingPose(cfg.zoom,true,1) end
            self.phase,self.elapsed="video",0
        end
    elseif self.phase=="video" then
        if self.player then
            self.playTime=math.max(0,self.player:GetCurrentTime()-cfg.videoOffset)
            self.player:SetVolume(self.hud.videoVolume and self.hud.videoVolume() or 1)
        end
        if self.loadError then self:ShowVideoError()
        elseif self.finishRequested then self:BeginVideoOut() end
    elseif self.phase=="error" then
        if self.finishRequested then self:BeginVideoOut() end
    elseif self.phase=="videoOut" then
        self.fade:SetStyle{opacity=eased}
        self:SetMix(self.exitMix+(1-self.exitMix)*eased)
        if self.player then self.player:SetVolume((self.hud.videoVolume and self.hud.videoVolume() or 1)*self.exitGain*(1-eased)) end
        if t==1 then self:ShowResult() end
    elseif self.phase=="resultIn" then
        self.fade:SetStyle{opacity=1-eased}
        if t==1 then self.phase="result" end
    end
end

function Screen:HandleKey(key)
    if self.phase=="idle" then return false end
    if key==KEY_ESCAPE and self:CanHoldExit() then
        -- A fresh key-down arms the hold. Esc carried in from gameplay cannot exit.
        self.exitArmed=true
    elseif (self.phase=="waiting" or self.phase=="videoIn") and self.playRequested and self.player
        and (key==KEY_SPACE or key==KEY_RETURN) then
        self.player:Play()
    end
    return true
end

function Screen:Reset()
    self:ResetExitHold()
    self.touchControls:SetVisible(false)
    self.generation=self.generation+1
    self:DisposePlayer()
    if self.blocker then self.videoHost:RemoveChild(self.blocker);self.blocker:Destroy();self.blocker=nil end
    self.phase,self.elapsed,self.playTime="idle",0,0
    self.shotTime,self.blendClock,self.videoGain,self.exitGain,self.exitMix=0,0,0,0,0
    self:SetMix(0)
    self.finishRequested=false
    self.playRequested,self.menuRequested,self.loadError=false,false,nil
    self.motion:Reset()
    self.root:SetVisible(false);self.result:SetVisible(false);self.videoHost:SetVisible(false)
    self.back:SetVisible(false);self.play:SetVisible(false);self.status:SetVisible(false)
    self.play:SetText("播放影片")
    self.videoHost:SetStyle{opacity=1}
    self.fade:SetStyle{opacity=0}
    self.root:SetStyle{backgroundColor=false}
    local area=self.hud.root and self.hud.root:FindById("hudSafeArea")
    if area then area:SetStyle{opacity=1};area:SetVisible(true) end
    if self.hud.onEndingPose then self.hud.onEndingPose(1,false) end
    local toggle=self.root:FindById("endingStatsToggle") --[[@as Button?]]
    if toggle then toggle:SetText("本局数据 ▾") end
end

return Screen
