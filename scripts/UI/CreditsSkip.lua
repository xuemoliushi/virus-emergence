-- Matches the film's 1.2-second hold, dimming and framed progress feedback.
local UI=require("urhox-libs/UI")
local Skin=require("UI.AssetTheme")
local Mobile=require("UI.MobileLayout")
local HOLD_SECONDS=1.2
local WARM={255,198,124,255}

---@class CreditsSkip
---@field root Panel
---@field button Button
---@field touchArea SafeAreaView
---@field mask Panel
---@field area SafeAreaView
---@field hint Label
---@field fill Panel
---@field elapsed number
---@field armed boolean
---@field keyReady boolean
---@field done boolean
local Skip={}
Skip.__index=Skip

---@return CreditsSkip
function Skip.New()
    local self=setmetatable({},Skip)
    self.elapsed,self.armed,self.done=0,false,false
    self.keyReady=not (input and input.GetKeyDown and input:GetKeyDown(KEY_ESCAPE))
    self.hint=UI.Label{id="creditsSkipHint",text="长按 Esc 跳过制作名单",width="100%",height=20,
        textAlign="right",fontSize=11,fontColor=WARM,pointerEvents="none"}
    self.fill=UI.Panel{id="creditsSkipProgress",width="0%",height="100%",backgroundColor=WARM,pointerEvents="none"}
    self.mask=UI.Panel{id="creditsSkipMask",position="absolute",left=0,top=0,width="100%",height="100%",
        visible=false,backgroundColor={9,6,19,0},pointerEvents="none"}
    self.area=UI.SafeAreaView{id="creditsSkipArea",position="absolute",left=0,top=0,width="100%",height="100%",
        nativeMenuInset=true,padding=12,alignItems="flex-end",justifyContent="flex-start",pointerEvents="none",visible=false,
        children={Skin.Frame{frameKind="tooltip",width=222,maxWidth="100%",height=52,padding=10,gap=5,
            pointerEvents="none",children={self.hint,UI.Panel{width="100%",height=4,
                backgroundColor={68,48,70,255},pointerEvents="none",children={self.fill}}}}}}
    self.button=Skin.Button{id="creditsTouchSkip",text="长按跳过名单",width=168,height=48,
        fontSize=13,buttonKind="secondary"}
    self.touchArea=UI.SafeAreaView{position="absolute",left=0,top=0,width="100%",height="100%",
        nativeMenuInset=true,padding=12,alignItems="flex-end",justifyContent="flex-start",
        pointerEvents="box-none",visible=Mobile.IsTouch(),children={self.button}}
    self.root=UI.Panel{position="absolute",left=0,top=0,width="100%",height="100%",pointerEvents="box-none",
        children={self.mask,self.touchArea,self.area}}
    return self
end

function Skip:HandleKey(key)
    if key==KEY_ESCAPE and self.keyReady then self.armed=true end
end

---@return boolean
function Skip:Update(dt)
    if self.done then return false end
    local touch=Mobile.IsTouch()
    self.touchArea:SetVisible(touch)
    self.area:SetStyle{paddingTop=touch and 72 or 12}
    local focused=not input or (input.focus~=false and input.minimized~=true)
    local keyHeld=input and input.GetKeyDown and input:GetKeyDown(KEY_ESCAPE) or false
    if not keyHeld then self.keyReady=true end
    local touchHeld=touch and self.button.state and self.button.state.pressed==true
    if touchHeld and focused then self.armed=true end
    if not focused or not self.armed or not (touchHeld or keyHeld) then
        self.elapsed,self.armed=0,false
        if not focused then self.keyReady=false end
        self.area:SetVisible(false);self.mask:SetVisible(false)
        self.fill:SetStyle{width="0%"}
        return false
    end
    if dt~=dt or math.abs(dt)==math.huge then return false end
    self.elapsed=math.min(HOLD_SECONDS,self.elapsed+math.max(0,math.min(dt,.1)))
    local progress=self.elapsed/HOLD_SECONDS
    self.area:SetVisible(true);self.mask:SetVisible(true)
    self.fill:SetStyle{width=string.format("%.1f%%",progress*100)}
    self.hint:SetText(string.format("正在跳过 · %.0f%%",progress*100))
    self.mask:SetStyle{backgroundColor={9,6,19,math.floor(190*progress)}}
    if self.elapsed+1e-9>=HOLD_SECONDS then self.done=true;return true end
    return false
end

return Skip
