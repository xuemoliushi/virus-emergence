-- 键盘、按钮与地图点选共用的意图层；结算仍由 SimState / AbilityRuntime 校验。
---@class SkillIntentAbilityAPI
---@field Config fun(id:string):table
---@field Owned fun(world:table,id:string):boolean
local A=require("Core.AbilityRuntime") --[[@as SkillIntentAbilityAPI]]
local Controls={}

function Controls.CanUse(hud)
    return hud.sim:CanUseAction("skill") and not hud.cardInfoShown_ and hud.scaleMgr:CurrentScale()=="cell"
        and not (input and (input.focus==false or input.minimized==true))
end

function Controls.Cancel(sim)
    sim.skillSelection=nil;sim.skillMenu=nil
end

function Controls.Refresh(hud)
    local sim=hud.sim
    local context=sim.skillSelection or sim.skillMenu
    if context and (not Controls.CanUse(hud) or context.runId~=sim.cards.runId
        or context.controlId~=sim.world.currentControlledSwarmId
        or (context.swarmId and not sim.world:SwarmById(context.swarmId))) then
        Controls.Cancel(sim)
    end
end

local function menu(sim,page)
    sim.skillSelection=nil
    sim.skillMenu={page=page,runId=sim.cards.runId,controlId=sim.world.currentControlledSwarmId}
end

function Controls.Toggle(hud)
    if not Controls.CanUse(hud) then return end
    if hud.sim.skillMenu then Controls.Cancel(hud.sim) else menu(hud.sim,"main") end
end

-- 主菜单编号由本局获得顺序决定，不随冷却、开关或群切换重排。
function Controls.Entries(sim)
    local entries={}
    local page=sim.skillMenu and sim.skillMenu.page or "main"
    if page=="dispatch" then
        return {{id="cluster_dispatch",name="集合",target={command="gather"}},
            {id="cluster_dispatch",name="留守",target={command="hold"}}}
    elseif page=="hide" then
        local s=sim.world:SwarmById(sim.world.currentControlledSwarmId)
        if s and not s.isHidden then entries[#entries+1]={id="node_hide",name="当前群：进入节点",enter=true} end
        for _,hidden in ipairs(sim.world.swarms) do
            if hidden.isHidden then entries[#entries+1]={id="node_hide",name="群"..hidden.id.."：离开节点",
                target={swarmId=hidden.id,exit=true}} end
        end
    else
        for _,id in ipairs(sim.world.abilities.order) do
            local mobileToggle=require("UI.MobileLayout").IsTouch() and (id=="swarm_anchor" or id=="infection_trail" or id=="merge_seed")
            if A.Config(id).targetType and id~="emergency_dash" and id~="shed_decoy" and not mobileToggle then
                local def=sim.cards:Definition(id)
                entries[#entries+1]={id=id,name=def and def.name or id}
            end
        end
    end
    return entries
end

function Controls.Hint(id)
    ---@class SkillMobileHintAPI
    ---@field IsTouch fun(hud:table?):boolean
    ---@field SkillHint table<string,string>
    local Mobile=require("UI.MobileLayout") --[[@as SkillMobileHintAPI]]
    if Mobile.IsTouch() then
        local hints=Mobile.SkillHint
        if hints[id] then return hints[id] end
        if not A.Config(id).targetType then return "被动能力，获得后自动生效。" end
        return hints.default
    end
    if id=="emergency_dash" then return "Shift：沿最近主动移动方向立即冲刺，冷却"..A.Config(id).cooldown.."秒；方向被完全阻挡时不进入冷却。"
    elseif id=="shed_decoy" then return "F：脱落4颗诱饵，保留至少3颗，冷却18秒；E或离散回收可收回。"
    elseif not A.Config(id).targetType then return "被动能力，获得后自动生效。"
    elseif id=="discrete_recall" then return "V → 对应数字：附近有可牵引病毒时启动6秒远距牵引，冷却18秒；E仍是基础瞬时吸附。"
    elseif id=="local_flow" then return "进入组织流区域后指定方向，转流持续10秒；无水流时不进入冷却。"
    elseif id=="membrane_glide" then return "选择当前群正在感染的细胞，留下3颗继续感染，占1个名额；E回收附近小队，Tab接管。"
    else return "V → 对应数字：操作此能力；目标技能点击合法目标立即执行，Esc取消。" end
end

function Controls.Execute(sim,selection)
    if selection.runId~=sim.cards.runId or selection.controlId~=sim.world.currentControlledSwarmId then
        Controls.Cancel(sim);return false
    end
    local ok,reason=sim:UseSkill(selection.id,selection.swarmId,selection.target,selection.requestId,selection.runId)
    if ok then Controls.Cancel(sim) end
    return ok,reason
end

function Controls.Activate(hud,id,target,enter)
    local sim=hud.sim
    if not Controls.CanUse(hud) then return false end
    if not A.Owned(sim.world,id) then sim.skillMessage="尚未获得此卡";sim:ReportActionDenied(sim.skillMessage);return false end
    local cfg=A.Config(id)
    if not cfg.targetType then sim.skillMessage="此卡为被动能力";sim:ReportActionDenied(sim.skillMessage);return false end
    if id=="cluster_dispatch" and not target then menu(sim,"dispatch");return true end
    if id=="node_hide" and not target and not enter then menu(sim,"hide");return true end
    local s=sim.world:SwarmById(target and target.swarmId or sim.world.currentControlledSwarmId)
    if not s then sim.skillMessage="请选择可行动群；藏身群可从V菜单退出";sim:ReportActionDenied(sim.skillMessage);return false end
    sim.skillRequestSerial=sim.skillRequestSerial+1
    local selection={id=id,swarmId=s.id,target=target,runId=sim.cards.runId,
        controlId=sim.world.currentControlledSwarmId,requestId="skill:"..sim.skillRequestSerial}
    if cfg.targetType=="self" or cfg.targetType=="global" or target then
        -- 立即技能失败不覆盖旧点选，也不消耗资源或启动冷却。
        return Controls.Execute(sim,selection)
    end
    sim.skillMenu=nil;sim.skillSelection=selection
    sim.skillMessage=require("UI.MobileLayout").IsTouch(hud) and require("UI.MobileLayout").Text.targetSelect
        or "点击高亮合法目标立即执行；Esc取消，模拟继续运行"
    return true
end

function Controls.Select(hud,index)
    Controls.Refresh(hud)
    if not hud.sim.skillMenu or not Controls.CanUse(hud) then return false end
    local entry=Controls.Entries(hud.sim)[index]
    if not entry then return false end
    return Controls.Activate(hud,entry.id,entry.target,entry.enter)
end

function Controls.HandleKey(hud,key,repeated)
    if repeated then return false end
    local keys={KEY_1,KEY_2,KEY_3,KEY_4,KEY_5,KEY_6}
    local recognized=key==KEY_LSHIFT or key==KEY_RSHIFT or key==KEY_F or key==KEY_V or key==KEY_ESCAPE
    for index=1,6 do if keys[index]~=nil and key==keys[index] then recognized=true end end
    if not recognized or not Controls.CanUse(hud) then return false end
    Controls.Refresh(hud)
    if key==KEY_LSHIFT or key==KEY_RSHIFT then return Controls.Activate(hud,"emergency_dash")
    elseif key==KEY_F then return Controls.Activate(hud,"shed_decoy")
    elseif key==KEY_V then Controls.Toggle(hud);return true
    elseif key==KEY_ESCAPE then Controls.Cancel(hud.sim);return true end
    for index=1,6 do if keys[index]~=nil and key==keys[index] then return Controls.Select(hud,index) end end
    return false
end

function Controls.Pick(sim,x,y)
    local selection=sim.skillSelection
    if not selection or not sim:CanAct() then return false end
    local w=sim.world
    if selection.runId~=sim.cards.runId or selection.controlId~=w.currentControlledSwarmId
        or not w:SwarmById(selection.swarmId) then Controls.Cancel(sim);return false end
    local kind=A.Config(selection.id).targetType
    if kind=="direction" then selection.target={x=x,y=y}
    else
        local list=kind=="swarm" and w.swarms or w.cells
        local best,d=nil,math.huge
        local failure="未点中合法目标，请选择高亮目标"
        for _,c in ipairs(list) do
            local gap=math.sqrt((c.x-x)^2+(c.y-y)^2)
            if gap<=c.radius*(kind=="swarm" and 1 or 1.5) then
                local target=kind=="swarm" and {swarmId=c.id} or {cellId=c.id}
                local legal,reason=sim:ValidateSkill(selection.id,kind=="swarm" and c.id or selection.swarmId,target)
                if legal and gap<d then best,d=c,gap elseif not legal then failure=tostring(reason) end
            end
        end
        if not best then sim.skillMessage=failure;sim:ReportActionDenied(failure);return true end
        if kind=="swarm" then selection.swarmId=best.id;selection.target={swarmId=best.id}
        else selection.target={cellId=best.id} end
    end
    Controls.Execute(sim,selection)
    return true
end

return Controls
