-- Local controlled renderer; never the published entry. Exercises the real main lifecycle.
local Mobile=require("UI.MobileLayout")
Mobile.MarkTouch()
require("main")
local gameStart=Start
local gameUpdate=HandleUpdate
local frame=0
local activated=false
local prepared=false
local CASE="__CASE__"
function Start()
    input.touchEmulation=true
    gameStart()
    UnsubscribeFromEvent("Update")
    SubscribeToEvent("Update",function(eventType,eventData)
        gameUpdate(eventType,eventData)
        MobilePreviewUpdate(eventType,eventData)
    end)
end
function MobilePreviewUpdate(eventType,eventData)
    frame=frame+1
    local UI=require("urhox-libs/UI")
    local root=UI.GetRoot()
    if not root then return end
    local start=root:FindById("storyMode")
    if CASE~="menu" and CASE~="interactive" and start and not activated and frame>180 and not start.props.disabled then
        activated=true
        start.props.onClick(start)
        print("[MobilePreview] start via real menu callback")
    end
    local scene=root:FindById("gameScene")
    if CASE~="interactive" and scene and root.id=="uiRoot" and not prepared and scene.sim.tutorial.active then
        prepared=true
        -- Controlled screenshot windows may be unfocused. Exempt only this test instance;
        -- interactive mode and the published main keep all OS focus safeguards.
        local setPaused=scene.sim.SetPaused
        scene.sim.SetPaused=function(self,reason,value)
            if reason=="focus" then value=false end
            return setPaused(self,reason,value)
        end
        scene.sim:SetPaused("focus",false)
        if CASE=="skills" then
            local Controls=require("UI.SkillControls")
            Controls.CanUse=function(hud)
                return hud.sim:CanUseAction("skill") and not hud.cardInfoShown_
                    and hud.scaleMgr:CurrentScale()=="cell"
            end
        end
        if CASE=="hud" or CASE=="skills" or CASE=="cards" then
            scene.sim.tutorial:Stop(true)
            local A=require("Core.AbilityRuntime")
            for _,card in ipairs(require("Core.Config").Cards.definitions) do
                local menuSkill=CASE=="skills" and (card.id=="swarm_anchor" or card.id=="discrete_recall"
                    or card.id=="node_hide" or card.id=="cluster_dispatch")
                if card.id=="emergency_dash" or card.id=="shed_decoy" or menuSkill then A.Acquire(scene.sim.world,card) end
            end
        end
        if CASE=="skills" then root:FindById("quickMenu").props.onClick() end
        if CASE=="cards" then
            assert(scene.sim:GrantCardChoice("stage:1"))
            -- Deliberately retain an active lesson to reproduce the reported foreground conflict.
            scene.sim.tutorial.active=true
        end
        print("[MobilePreview] controlled case="..CASE.." after natural menu entry")
    end
    if CASE~="interactive" and scene and root.id=="uiRoot" and frame==2100 then
        local buttons={}
        for _,id in ipairs({"stagePanel","strategyBar","absorbBtn","splitBtn","switchBtn","quickMenu","quickDash","quickDecoy","joystickPanel"}) do
            local w=root:FindById(id)
            if w then local l=w:GetAbsoluteLayout();print(string.format("[MobilePreview] %s %.1f %.1f %.1f %.1f",id,l.x,l.y,l.w,l.h)) end
            if w and w:IsVisible() and (id:find("Btn") or id:find("quick")) then buttons[#buttons+1]=w end
        end
        for i,a in ipairs(buttons) do
            local r=a:GetAbsoluteLayout()
            assert(r.x>=0 and r.y>=0 and r.x+r.w<=UI.GetWidth()+2 and r.y+r.h<=UI.GetHeight()+2,"button outside viewport: "..a.id)
            for j=i+1,#buttons do
                local b=buttons[j]:GetAbsoluteLayout()
                assert(r.x+r.w<=b.x+1 or b.x+b.w<=r.x+1 or r.y+r.h<=b.y+1 or b.y+b.h<=r.y+1,"overlap: "..a.id.." / "..buttons[j].id)
            end
        end
        print("[MobilePreview] real Yoga button bounds and non-overlap checked")
        if CASE=="skills" or CASE=="cards" then
            assert(not root:FindById("tutorialOverlay"):IsVisible(),"tutorial covers foreground")
            local panel=root:FindById(CASE=="skills" and "skillMenuPopup" or "cardPanelFrame")
            assert(panel and panel:IsVisible() and panel:GetLayout().h>100,"foreground panel was not displayed")
            assert(CASE~="skills" or scene.sim.skillMenu~=nil,"skills menu state was cancelled")
            assert(CASE~="cards" or scene.sim.cards.pending~=nil,"card choice missing")
            print("[MobilePreview] tutorial yields to foreground")
        end
    end
end
