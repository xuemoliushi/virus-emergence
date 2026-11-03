local UI=require("urhox-libs/UI")
local Skin=require("UI.AssetTheme")
local Config=require("Core.Config")
local A=require("Core.AbilityRuntime")
local Controls=require("UI.SkillControls")
---@class SkillPanelMobileAPI
---@field IsTouch fun(hud:table?):boolean
---@field Text table<string,string>
local Mobile=require("UI.MobileLayout") --[[@as SkillPanelMobileAPI]]
---@class SkillPanelAPI
---@field Build fun(hud:table):Widget
---@field BuildQuick fun(hud:table):Widget
---@field BuildTarget fun(hud:table):Widget
---@field BuildMenu fun(hud:table):Widget
---@field Refresh fun(hud:table,fast:boolean?)
local Panel={}
local function skillButton(props)
    local icons={quickDash="emergency_dash",quickDecoy="shed_decoy",quickMenu="ability_menu",
        skillMenuToggle="ability_menu",skillCancel="close",skillMenuClose="close",skillMenuBack="back"}
    local id=props.id or ""
    local kind=(id=="skillCancel" or id=="skillMenuClose" or id=="skillMenuBack") and "secondary" or "action"
    local button=Skin.Button(props,kind,icons[id])
    if id=="quickDash" or id=="quickDecoy" or id=="quickMenu" then
        button:SetStyle{paddingLeft=38,paddingRight=6}
        if button.assetIcon_ then button.assetIcon_:SetStyle{left=6} end
    end
    return button
end

local QUICK={{id="emergency_dash",button="quickDash",key="Shift"},{id="shed_decoy",button="quickDecoy",key="F"}}
Panel.Begin=Controls.Activate
Panel.Pick=Controls.Pick

local function click(fn)
    return function(_,event) if not event or event:IsPrimaryAction() then fn() end end
end

-- Composite rows let Yoga measure both lines. Button's own text renderer is
-- single-line; a fixed absolute detail label clips wrapped cooldown/cost text.
local function menuRow(hud,index)
    local id="skillMenu_"..index
    local button=skillButton{id=id,width="100%",height="auto",minHeight=80,flexShrink=0,visible=false,
        onClick=click(function() Controls.Select(hud,index) end)}
    local title=UI.Label{id=id.."_title",text="",width="100%",fontSize=14,minFontSize=14,
        whiteSpace="normal",wordBreak="break-word",lineHeight=1.3,textAlign="left",flexShrink=0,
        fontColor=Skin.colors.text,pointerEvents="none"}
    local detail=UI.Label{id=id.."_detail",text="",width="100%",fontSize=12,minFontSize=12,
        whiteSpace="normal",wordBreak="break-word",lineHeight=1.35,textAlign="left",flexShrink=0,
        fontColor=Skin.colors.muted,pointerEvents="none"}
    button.assetIcon_=Skin.Icon("ability_menu",36)
    button.assetDetail_=detail
    button:SetStyle{paddingLeft=12,paddingRight=12,paddingTop=12,paddingBottom=12,
        flexDirection="row",alignItems="center",gap=12,minWidth=0}
    button:AddChild(button.assetIcon_)
    button:AddChild(UI.Panel{id=id.."_copy",flexGrow=1,flexBasis=0,minWidth=0,gap=4,
        pointerEvents="none",children={title,detail}})
    -- Keep the existing caption API for keyboard/menu callers; render the child label.
    button.SetText=function(_,text) if title:GetText()~=text then title:SetText(text) end end
    button.GetText=function() return title:GetText() end
    return button
end

local PASSIVES={"debris_camouflage","rupture_spread","swarm_capacity_4","swarm_capacity_6","swarm_local_brain","tail_preserve"}
function Panel.Build(hud)
    local icons={}
    for _,id in ipairs(PASSIVES) do
        icons[#icons+1]=Skin.Frame({id="passiveIcon_"..id,width=30,height=30,padding=3,visible=false,
            pointerEvents="none",children={Skin.Icon(id,24)}},"square")
    end
    return UI.Panel{id="skillBar",width="100%",gap=6,children={
        UI.Label{id="skillMessage",visible=false,text="完成阶段后自动选卡",fontSize=12,width="100%",whiteSpace="normal"},
        UI.Panel{id="passiveIconStrip",visible=false,width="100%",gap=6,flexDirection="row",flexWrap="wrap",children=icons},
        UI.Label{id="passiveSkills",text="",fontSize=11,width="100%",whiteSpace="normal"},
        skillButton{id="skillMenuToggle",text="V · 功能菜单",height=48,visible=false,
            onClick=click(function() Controls.Toggle(hud) end)},
    }}
end

function Panel.BuildTarget(hud)
    -- [HUD_BUTTON:skillCancel] 取消技能目标选择；独占一行，不能挤窄提示正文。
    local cancel=skillButton{id="skillCancel",text="取消 · Esc",height=36,width=120,maxWidth="100%",
        flexShrink=0,alignSelf="flex-end",onClick=click(function() Controls.Cancel(hud.sim) end)}
    if cancel.assetIcon_ then cancel.assetIcon_:SetVisible(false) end
    cancel:SetStyle{paddingLeft=12,paddingRight=12,minWidth=0}
    return Skin.Frame{frameKind="tooltip",padding=12,id="skillTargetPrompt",position="absolute",right=16,bottom=124,
            visible=false,width=360,height="auto",minWidth=0,flexDirection="column",gap=8,children={
            UI.Label{id="skillTargetTitle",text="",fontSize=14,minFontSize=14,fontColor=Skin.colors.gold,
                width="100%",whiteSpace="normal",wordBreak="break-word",flexShrink=0},
            UI.Label{id="skillTargetText",text="",fontSize=12,minFontSize=12,lineHeight=1.4,
                whiteSpace="normal",wordBreak="break-word",width="100%",minWidth=0,flexShrink=0},
            cancel,
        }}
end

function Panel.BuildQuick(hud)
    return UI.Panel{id="skillQuickBar",width="auto",flexBasis=360,flexGrow=1,maxWidth=480,alignSelf="flex-start",gap=5,flexShrink=0,pointerEvents="box-none",children={
        UI.Label{id="skillKeyHint",visible=false,text="E 基础吸附（冷却3秒） · 空格 分裂 · Tab 切群 · V 功能菜单",fontSize=11,
            whiteSpace="normal",width="100%",pointerEvents="none"},
        UI.Panel{id="quickButtonRow",width="100%",flexDirection="row",flexWrap="wrap",justifyContent="flex-start",gap=8,pointerEvents="box-none",children={
            -- [HUD_BUTTON:quickDash] 紧急冲刺快捷按钮
            skillButton{id="quickDash",text="Shift · 紧急冲刺",visible=false,height=48,width=112,minWidth=96,maxWidth=160,flexGrow=1,flexShrink=1,flexBasis=112,assetIconSize=26,fontSize=11,
                onClick=click(function() Controls.Activate(hud,"emergency_dash") end)},
            -- [HUD_BUTTON:quickDecoy] 脱落诱饵快捷按钮
            skillButton{id="quickDecoy",text="F · 脱落诱饵",visible=false,height=48,width=112,minWidth=96,maxWidth=160,flexGrow=1,flexShrink=1,flexBasis=112,assetIconSize=26,fontSize=11,
                onClick=click(function() Controls.Activate(hud,"shed_decoy") end)},
            -- [HUD_BUTTON:quickMenu] 快捷栏功能菜单入口
            skillButton{id="quickMenu",text="V · 技能",height=48,width=112,minWidth=96,maxWidth=160,flexGrow=1,flexShrink=1,flexBasis=112,assetIconSize=26,fontSize=11,
                onClick=click(function() Controls.Toggle(hud) end)},
        }},
    }}
end

function Panel.BuildMenu(hud)
    ---@type Widget[]
    local children={UI.Label{id="skillMenuTitle",text="V · 功能菜单",fontSize=18,width="100%",whiteSpace="normal",flexShrink=0},
        UI.Panel {id="skillMenuKeycaps",width="100%",flexDirection="row",flexWrap="wrap",gap=6,pointerEvents="none",children={
            Skin.Keycap("1"),Skin.Keycap("2"),Skin.Keycap("3"),Skin.Keycap("4"),Skin.Keycap("5"),Skin.Keycap("6")}},
        UI.Label{id="skillMenuHint",text="1—6选择 · V / Esc关闭 · 模拟继续运行",fontSize=11,whiteSpace="normal",width="100%"},
        UI.Label{id="skillMenuMessage",text="",fontSize=11,whiteSpace="normal",width="100%"}}
    for i=1,6 do
        local index=i
        -- [HUD_BUTTON:skillMenu_] 1—6动态功能槽，共用藏身/调度子菜单
        children[#children+1]=menuRow(hud,index)
    end
    -- [HUD_BUTTON:skillMenuBack] 子菜单返回主功能菜单
    children[#children+1]=skillButton{id="skillMenuBack",text="返回",height=44,width=0,flexGrow=1,flexBasis=0,assetIconSize=28,visible=false,
        onClick=click(function() Controls.Cancel(hud.sim);Controls.Toggle(hud) end)}
    -- [HUD_BUTTON:skillMenuClose] 关闭功能菜单
    children[#children+1]=skillButton{id="skillMenuClose",text="关闭",height=44,width=0,flexGrow=1,flexBasis=0,assetIconSize=28,onClick=click(function() Controls.Cancel(hud.sim) end)}
    for _,child in ipairs(children) do
        if child.props.id=="skillMenuBack" then Skin.SetIcon(child,"back")
        elseif child.props.id=="skillMenuClose" then Skin.SetIcon(child,"close") end
        if child.props.id=="skillMenuBack" or child.props.id=="skillMenuClose" then
            local footer=child --[[@as SkinnedButton]]
            if footer.assetIcon_ then footer.assetIcon_:SetVisible(false) end
            footer:SetStyle{paddingLeft=12,paddingRight=12,minWidth=0}
        end
    end
    local rows={}
    for i=5,#children-2 do rows[#rows+1]=children[i] end
    return Skin.Frame {frameKind="dialog",id="skillMenuPopup",position="absolute",right=8,bottom="25%",
        width="80%",maxWidth=420,height="56%",visible=false,padding=16,gap=6,minHeight=0,
        children={UI.Panel {width="100%",gap=4,flexShrink=0,children={children[1],children[2],children[3],children[4]}},
            Skin.Scroll {id="skillMenuScroll",width="100%",height=0,flexGrow=1,flexBasis=0,minHeight=0,
                children={UI.Panel {id="skillMenuRows",width="100%",height="auto",gap=6,flexShrink=0,children=rows}}},
            UI.Panel {id="skillMenuFooter",width="100%",height=44,flexDirection="row",gap=8,flexShrink=0,
                children={children[#children-1],children[#children]}}}}

end

local function status(sim,id,swarmId)
    local state=sim:GetSkillState(id,swarmId)
    local suffix=state.cooldown>0 and string.format(" · 冷却%.1f秒",state.cooldown) or " · 就绪"
    if state.massCost>0 then suffix=suffix.." · 投入"..state.massCost.."颗，留3颗" end
    if state.remaining>0 then suffix=suffix..string.format(" · 剩余%.1f秒",state.remaining) end
    if id=="discrete_recall" and state.remaining==0 then suffix=suffix.." · 牵引6秒" end
    if id=="swarm_anchor" or id=="infection_trail" or id=="merge_seed" then suffix=suffix..(state.active and " · 开启" or " · 关闭") end
    return suffix
end

function Panel.Refresh(hud,fast)
    Controls.Refresh(hud)
    local sim,w=hud.sim,hud.sim.world
    local canUse=Controls.CanUse(hud)
    local show=sim.started and hud.scaleMgr:CurrentScale()=="cell" and not sim.ending
    if show and Mobile.IsTouch(hud) and (sim.skillMenu or sim.skillSelection) then hud:CloseDrawers() end
    local quick=hud.root:FindById("skillQuickBar");if quick then quick:SetVisible(show) end
    local popup=hud.root:FindById("skillMenuPopup")
    if hud.motions_.skills then hud.motions_.skills:SetOpen(show and sim.skillMenu~=nil) end
    local prompt=hud.root:FindById("skillTargetPrompt")
    if hud.motions_.target then hud.motions_.target:SetOpen(show and sim.skillSelection~=nil) end
    local menuChanged=hud.renderedSkillMenu_~=sim.skillMenu
    hud.renderedSkillMenu_=sim.skillMenu
    -- 触屏去掉键名；桌面文案保持原样（测试与键盘提示依赖）。
    local touch=Mobile.IsTouch(hud)
    local T=Mobile.Text
    for _,entry in ipairs(QUICK) do
        local btn=hud.root:FindById(entry.button) --[[@as SkinnedButton?]]
        if btn then
            btn:SetVisible(not touch and A.Owned(w,entry.id))
            local legal,reason=sim:ValidateSkill(entry.id,w.currentControlledSwarmId)
            local disabled=not canUse or not legal
            if btn:IsDisabled()~=disabled then btn:SetDisabled(disabled) end
            if not fast then
                local def=sim.cards:Definition(entry.id)
                local suffix=status(sim,entry.id)
                if not legal then suffix=suffix.." · "..tostring(reason) end
                Skin.SetIcon(btn,entry.id)
                local remaining=sim:GetSkillState(entry.id).cooldown
                local caption=remaining>0 and string.format("%.1fs",remaining) or ""
                Skin.SetDetail(btn,suffix:gsub("^ · ",""))
                if btn.assetDetail_ then btn.assetDetail_:SetVisible(false) end
                btn:SetStyle{paddingBottom=0}
                local text=touch and (remaining>0 and string.format("%.0fs",remaining) or (entry.id=="emergency_dash" and "冲刺" or "诱饵"))
                    or entry.key.." · "..(entry.id=="emergency_dash" and "冲刺" or "诱饵")..(caption~="" and " "..caption or "")
                if btn.props.text~=text then btn:SetText(text) end
            end
        end
    end
    if sim.skillMenu and (not fast or menuChanged) then
        local entries=Controls.Entries(sim)
        if not fast then
            hud:SetText("skillMenuTitle",sim.skillMenu.page=="hide" and "寄居藏身 · 各群独立进出"
                or sim.skillMenu.page=="dispatch" and "集群调度" or (touch and T.skillMenuTitle or "V · 功能菜单"))
            if touch then
                hud:SetText("skillMenuHint",#entries==0 and T.skillMenuHintEmpty or T.skillMenuHint)
            else
                hud:SetText("skillMenuHint",#entries==0 and "尚未获得可操作的功能卡 · V / Esc关闭"
                    or "1—6选择 · V / Esc关闭 · 模拟继续运行")
            end
            local keycaps=hud.root:FindById("skillMenuKeycaps")
            if keycaps and keycaps:IsVisible()==touch then keycaps:SetVisible(not touch) end
            hud:SetText("skillMenuMessage",sim.skillMessage or "")
            local message=hud.root:FindById("skillMenuMessage")
            if message then message:SetVisible(sim.skillMessage~=nil and sim.skillMessage~="") end
        end
        for i=1,6 do
            local btn=hud.root:FindById("skillMenu_"..i) --[[@as SkinnedButton?]]
            local e=entries[i]
            if btn then
                btn:SetVisible(e~=nil)
                if btn:IsDisabled()~=not canUse then btn:SetDisabled(not canUse) end
                if e and not fast then
                    Skin.SetIcon(btn,e.id)
                    Skin.SetDetail(btn,status(sim,e.id,e.target and e.target.swarmId):gsub("^ · ",""))
                    btn:SetStyle {backgroundImage="image/ui/scaled/ui_skill_row_gold_192x64.png",
                        backgroundSlice={8,9,8,9}}
                    local text=i.." · "..e.name
                    if btn:GetText()~=text then btn:SetText(text) end
                end
            end
        end
        local back=hud.root:FindById("skillMenuBack");if back then back:SetVisible(sim.skillMenu.page~="main") end
    end
    if fast then return end
    local text=sim.skillMessage or ""
    if text~=hud.lastSkillMessage_ then
        hud.lastSkillMessage_=text
        if text~="" then hud:Notify(text) end
    end
    if sim.skillSelection then
        local selected=sim.skillSelection
        local def=sim.cards:Definition(selected.id)
        hud:SetText("skillTargetTitle",def.name.." · 群"..selected.swarmId)
        hud:SetText("skillTargetText",text)
    end
    hud:SetText("skillMessage",text)
    for _,id in ipairs(PASSIVES) do
        local icon=hud.root:FindById("passiveIcon_"..id)
        if icon then
            local owned=A.Owned(w,id);icon:SetVisible(owned)
            if owned then local state=sim:GetSkillState(id);icon:SetStyle {opacity=state.used and 0.45 or 1,
                borderWidth=state.active and 1 or 0,borderColor=Skin.colors.gold} end
        end
    end
    local strip=hud.root:FindById("passiveIconStrip")
    if strip then
        local any=false;for _,id in ipairs(PASSIVES) do if A.Owned(w,id) then any=true end end
        strip:SetVisible(any)
    end
    local passives={}
    for _,id in ipairs(w.abilities.order) do
        if not A.Config(id).targetType then
            local def=sim.cards:Definition(id);local state=sim:GetSkillState(id)
            passives[#passives+1]=def.name..(state.used and "（已使用）" or state.active and "（生效中）" or "（被动）")
        end
    end
    for _,s in ipairs(w.swarms) do
        if s.groupCommand then passives[#passives+1]="群"..s.id..(s.groupCommand.kind=="gather" and "：集合" or "：留守") end
    end
    hud:SetText("passiveSkills",table.concat(passives," · "))
    local cd=w:GetAbsorptionCooldown()
    local absorb=hud.root:FindById("absorbBtn") --[[@as SkinnedButton?]]
    if absorb then
        local text
        if touch then text=cd>1e-9 and string.format(T.absorbCooldown,cd) or T.absorbReady
        else text=cd>1e-9 and string.format("E 吸附 %.1fs",cd) or "E 基础吸附" end
        if absorb.props.text~=text then absorb:SetText(text) end
    end
    if touch then
        hud:SetText("skillKeyHint",(cd>1e-9 and string.format(T.skillKeyHintCooldown,cd) or T.skillKeyHintReady)
            ..(A.Owned(w,"emergency_dash") and " · 冲刺" or "")..(A.Owned(w,"shed_decoy") and " · 诱饵" or "")
            ..T.skillKeyHintTail)
        return
    end
    hud:SetText("skillKeyHint",(cd>1e-9 and string.format("E 吸附：冷却%.1f秒",cd) or "E 基础吸附：就绪（冷却3秒）")
        ..(A.Owned(w,"emergency_dash") and " · Shift 冲刺" or "")..(A.Owned(w,"shed_decoy") and " · F 诱饵" or "")
        .." · V 功能菜单 · 空格 分裂 · Tab 切群")
end

return Panel
