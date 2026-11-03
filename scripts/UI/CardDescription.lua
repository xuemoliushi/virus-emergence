-- Card copy stays separate from gameplay definitions; full text uses native wheel/touch scrolling.
local UI = require("urhox-libs/UI")
local Mobile = require("UI.MobileLayout")
local Art = require("UI.CardArt")
---@class CardDescriptionView
---@field scroll ScrollView
---@field short Label
---@field state table
local Description = {}
Description.brief = {
    swarm_anchor="原地固定，仍可感染和吸收；移动解除。",
    discrete_recall="牵引附近病毒6秒，吸收后增加数量。",
    emergency_dash="向前冲刺0.5秒，仍会撞墙和受伤。",
    shed_decoy="放出4颗诱饵引开巨噬；留3颗，可主动回收。",
    debris_camouflage="残骸旁静止3秒后隐蔽；移动或感染解除。",
    local_flow="改变附近水流方向，持续10秒。",
    swarm_capacity_4="群数上限增至4；满12颗才能分裂。",
    swarm_local_brain="未操控的群自动行动，可随时接管。",
    node_hide="藏入感染细胞；细胞毁灭时损失一半。",
    membrane_glide="留3颗接力感染，占1群名额；E回收。",
    node_cover="花4颗病毒抵挡一次攻击；每细胞限一次。",
    tail_preserve="致命攻击时保住最多2颗并逃开，每局一次。",
    node_takeover="新释放的5颗组成新群，可预约下一批。",
    infection_trail="每移动1.5米留1颗传播，数量不足即停。",
    swarm_capacity_6="群数上限4→6；需先获得分裂扩容。",
    cluster_dispatch="召集或留守其他群，固定及藏身群除外。",
    merge_seed="合并时散出10%（最多6颗），间隔20秒。",
    rupture_spread="产毒细胞被摧毁时，散出剩余病毒的一半。",
}

function Description.Build(hud, id, text)
    local state={phase=0,pause=1.5,automatic=false}
    local scroll=UI.ScrollView{
        id="cardDescriptionScroll_"..id,position="absolute",
        left=Art.description.left,top=Art.description.top,
        width=Art.description.width,height=Art.description.height,
        scrollX=false,scrollY=true,bounces=false,showScrollbar=false,pointerEvents="auto",
        onScroll=function()
            if not state.automatic then state.pause=4;state.resync=true end
        end,
        children={UI.Label{
            id="cardDescription_"..id,text=text,width="100%",flexShrink=0,
            textAlign="center",whiteSpace="normal",wordBreak="break-word",lineHeight=1.4,
            fontSize=20,minFontSize=20,fontColor={241,232,214,255},pointerEvents="none",
        }},
    }
    local short=UI.Label{
        id="cardBrief_"..id,text=assert(Description.brief[id]),position="absolute",
        left=Art.description.left,top=Art.description.top,
        width=Art.description.width,height=Art.description.height,
        textAlign="center",verticalAlign="middle",whiteSpace="normal",wordBreak="break-word",
        lineHeight=1.15,fontSize=15,minFontSize=8,fontColor={241,232,214,255},
        pointerEvents="none",visible=false,
    }
    hud.cardDescriptionViews_=hud.cardDescriptionViews_ or {}
    hud.cardDescriptionViews_[id]={scroll=scroll,short=short,state=state}
    return scroll,short
end

function Description.SetBrief(hud, brief)
    hud.cardBriefText_=brief
    for _,view in pairs(hud.cardDescriptionViews_ or {}) do
        view.scroll:SetVisible(not brief);view.short:SetVisible(brief)
        view.state.automatic=true;view.scroll:SetScroll(0,0);view.state.automatic=false
        view.state.phase,view.state.pause,view.state.resync=0,1.5,false
    end
    hud:SetText("cardBriefToggle",brief and "简略文本：开" or "简略文本：关")
end

function Description.Update(hud,dt)
    if Mobile.IsTouch(hud) or not hud.cardInfoShown_ or hud.cardBriefText_ or hud.cardRevealElapsed_~=nil then return end
    for id,view in pairs(hud.cardDescriptionViews_ or {}) do
        local box=hud.root:FindById("cardBox_"..id)
        if box and box:IsVisible() and view.scroll.GetContentSize then
            local _,height=view.scroll:GetContentSize()
            local extent=math.max(0,(height or 0)-view.scroll:GetLayout().h)
            local state=view.state
            if extent>1 then
                if state.resync then
                    local _,y=view.scroll:GetScroll()
                    state.phase=math.acos(1-2*math.max(0,math.min(1,y/extent)))
                    state.resync=false
                end
                if state.pause>0 then state.pause=math.max(0,state.pause-dt)
                elseif not (view.scroll.state and view.scroll.state.isDragging) then
                    -- Cosine motion naturally slows at both ends; cap dt after a stalled frame.
                    state.phase=state.phase+math.min(dt,.1)*24/extent
                    state.automatic=true
                    view.scroll:SetScroll(0,extent*(1-math.cos(state.phase))*.5)
                    state.automatic=false
                end
            end
        end
    end
end
return Description
