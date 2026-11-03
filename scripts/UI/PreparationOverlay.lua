local UI=require("urhox-libs/UI")
local Skin=require("UI.AssetTheme")

---@class PreparationOverlay
---@field root Panel
---@field bar ProgressBar
---@field status Label
---@field percent Label
---@field ornament Widget
---@field elapsed number
local Overlay={}
Overlay.__index=Overlay

---@return PreparationOverlay
function Overlay.New()
    local self=setmetatable({},Overlay)
    self.elapsed=0
    self.bar=Skin.Progress{id="entryLoadingProgress",width="100%",height=22,value=0,max=1,showLabel=false}
    self.status=UI.Label{id="entryLoadingStatus",text="正在准备组织…",fontSize=15,
        fontColor=Skin.colors.muted,width="100%",textAlign="center",whiteSpace="normal"}
    self.percent=UI.Label{id="entryLoadingPercent",text="0%",fontSize=13,
        fontColor=Skin.colors.gold,width="100%",textAlign="center"}
    self.ornament=Skin.Ornament{height=40,width="100%",pointerEvents="none"}
    self.root=UI.Panel{id="entryLoading",position="absolute",left=0,top=0,width="100%",height="100%",
        zIndex=10001,backgroundColor={8,5,15,255},pointerEvents="auto",children={
            UI.SafeAreaView{width="100%",height="100%",nativeMenuInset=true,padding=24,
                alignItems="center",justifyContent="center",children={
                    UI.Panel{width="90%",maxWidth=520,gap=16,pointerEvents="none",children={
                        UI.Label{text="病毒涌现",fontSize=30,fontColor=Skin.colors.text,width="100%",textAlign="center"},
                        self.ornament,self.status,self.bar,self.percent,
                    }},
                }},
        }}
    return self
end

function Overlay:Update(dt,progress,message)
    self.elapsed=self.elapsed+math.max(0,math.min(dt,.1))
    self.bar:SetValue(progress)
    self.percent:SetText(string.format("%d%%",math.floor(progress*100)))
    self.status:SetText(message..string.rep("·",math.floor(self.elapsed*3)%4))
    self.ornament:SetStyle{opacity=.55+.45*(.5+.5*math.sin(self.elapsed*3))}
end

function Overlay:Destroy()
    self.root:Destroy()
end

return Overlay
