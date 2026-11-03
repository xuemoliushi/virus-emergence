local UI=require("urhox-libs/UI")
local Skin=require("UI.AssetTheme")
local Mobile=require("UI.MobileLayout")
local Layout=require("UI.ControlLayout")
local A=require("Core.AbilityRuntime")
local Controls=require("UI.SkillControls")
local T={};T.__index=T
local toggles={"swarm_anchor","infection_trail","merge_seed"}
local isToggle={swarm_anchor=true,infection_trail=true,merge_seed=true}
local icons={absorbBtn="absorb",splitBtn="split",switchBtn="switch_swarm",skillWheel="ability_menu"}
local function consume(e) e:PreventDefault();e:StopPropagation() end
local function moveTo(widget,parent)
    if widget.parent~=parent then widget.parent:RemoveChild(widget);parent:AddChild(widget) end
end
local function circle(widget,b)
    widget:SetStyle{position="absolute",left=b.left,top=b.top,right="auto",bottom="auto",width=b.d,height=b.d,
        minWidth=b.d,maxWidth=b.d,minHeight=b.d,flexBasis="auto",flexGrow=0,flexShrink=0,
        shape="circle",borderRadius=b.d/2,padding=2,paddingLeft=2,paddingRight=2,paddingTop=0,paddingBottom=0,
        backgroundImage="",backgroundColor={28,17,26,225},borderWidth=2,borderColor={183,139,82,230},fontSize=14}
end
local function artwork(widget,id,text)
    Skin.SetIcon(widget,icons[id] or id)
    local label=UI.Label{text=text,position="absolute",textAlign="center",verticalAlign="middle",
        whiteSpace="normal",pointerEvents="none",fontColor=Skin.colors.text}
    widget:AddChild(label);widget.touchCaption_=label
end
local function placeArtwork(widget,b,id)
    local toggle=isToggle[id]
    widget:SetStyle{shape=toggle and "rect" or "circle",borderRadius=toggle and 10 or b.d/2,
        backgroundImage=toggle and "image/ui/scaled/ui_square_button_normal.png" or "",
        backgroundFit="sliced",backgroundSlice={6,6,6,6}}
    if widget.assetIcon_ then
        local size=b.d*(toggle and .70 or .62)
        widget.assetIcon_:SetStyle{width=size,height=size,left=(b.d-size)/2,top=b.d*.03,translateY=0}
        widget:SetStyle{paddingTop=size+b.d*.12}
    end
    if widget.touchCaption_ then widget.touchCaption_:SetStyle{left=2,top=b.d*.73,width=b.d-4,height=b.d*.23,
        fontSize=id=="skillWheel" and 13 or 11} end
end
function T.New(hud)
    local self=setmetatable({hud=hud,saved=Layout.Load(),buttons={},age=0},T)
    self.layer=UI.Panel{id="touchControlLayer",position="absolute",left=0,top=0,width="100%",height="100%",pointerEvents="box-none"}
    self.zone=UI.Panel{id="floatingJoystickZone",position="absolute",pointerEvents="box-only",
        onPointerDown=function(e) self:MoveDown(e) end,
        onPointerMove=function(e) self:MoveDrag(e) end,
        onPointerUp=function(e) if e.pointerId==hud.joystickPointer_ then hud:ClearTouchMove();consume(e) end end,
        onPointerCancel=function(e) if e.pointerId==hud.joystickPointer_ then hud:ClearTouchMove();consume(e) end end}
    -- Activation surface is behind all HUD buttons and disclosures.
    hud.root:AddChild(self.layer)
    self.layer:AddChild(self.zone)
    moveTo(hud.joystick_,self.layer);hud.joystick_:SetStyle{position="absolute",pointerEvents="none"};hud.joystick_:SetVisible(false)
    self.wheel=Skin.Button{id="skillWheel",text="技能\n按住展开",onPointerDown=function(e) self:Down(e) end,
        onPointerMove=function(e) self:Drag(e) end,onPointerUp=function(e) self:Up(e) end,
        onPointerCancel=function(e) if self.gesture and self.gesture.pointer==e.pointerId then self:Cancel();consume(e) end end,
        onClick=function() end}
    -- Button overrides the base pointer down/up methods without forwarding props.
    local down,up=self.wheel.OnPointerDown,self.wheel.OnPointerUp
    self.wheel.OnPointerDown=function(widget,e)
        if down then down(widget,e) end
        self:Down(e)
    end
    self.wheel.OnPointerUp=function(widget,e)
        if up then up(widget,e) end
        self:Up(e)
    end
    self.wheel:SetText("");artwork(self.wheel,"skillWheel","技能")
    self.layer:AddChild(self.wheel);self.buttons.skillWheel=self.wheel
    for _,id in ipairs(toggles) do
        local key=id
        local btn=Skin.Button{id="touchToggle_"..id,text=Layout.names[id],onClick=function(_,e)
            if not e or e:IsPrimaryAction() then
                Controls.Activate(hud,key,key=="swarm_anchor" and {swarmId=hud.sim.world.currentControlledSwarmId} or nil)
            end
        end}
        btn:SetText("");artwork(btn,id,Layout.names[id])
        btn.touchState_=UI.Label{text="关",position="absolute",right=1,top=1,width=18,height=18,fontSize=10,
            textAlign="center",verticalAlign="middle",borderRadius=9,pointerEvents="none"}
        btn:AddChild(btn.touchState_)
        self.buttons[id]=btn;self.layer:AddChild(btn)
    end
    self.ring=UI.Panel{id="skillRadial",position="absolute",left=0,top=0,width="100%",height="100%",visible=false,
        pointerEvents="none",zIndex=100,children={}}
    self.caption=UI.Label{position="absolute",width=150,height=76,fontSize=13,textAlign="center",whiteSpace="normal",
        backgroundColor={14,10,21,245},borderRadius=8,padding=6,pointerEvents="none"}
    self.ring:AddChild(self.caption);hud.root:AddChild(self.ring)
    self.revision=0
    Layout.LoadCloud(function(value)
        if self.destroyed or hud.destroyed_ or self.revision~=0 or self.editor then return end
        self.saved=value;hud.layoutWidth_=0
    end)
    return self
end
function T:Viewport()
    local s=Mobile.SafeInsets()
    return UI.GetWidth()-s.left-s.right,UI.GetHeight()-s.top-s.bottom,s
end
function T:Apply()
    local h=self.hud;local w,ht,s=self:Viewport();self.w,self.h,self.safe=w,ht,s
    self:Cancel();h:ClearTouchMove()
    local value=self.draft or self.saved
    if not self.draft and Layout.Conflict(value,w,ht,function(id) return self:Available(id) end) then value=Layout.Clean(nil) end
    for _,id in ipairs({"absorbBtn","splitBtn","switchBtn"}) do
        local btn=h.root:FindById(id);moveTo(btn,self.layer);self.buttons[id]=btn
    end
    for id,btn in pairs(self.buttons) do
        local b=Layout.Bounds(value,id,w,ht);b.left,b.top=b.left+s.left,b.top+s.top
        circle(btn,b)
        placeArtwork(btn,b,id)
    end
    local joy=Layout.Bounds(value,"joystick",w,ht)
    h:ResizeJoystick(joy.d,joy.d*.375,joy.d,false)
    self.zone:SetStyle{left=s.left,top=s.top,width=w*.48,height=ht}
    h.root:FindById("joystickPanel"):SetVisible(false)
    h.root:FindById("quickDash"):SetVisible(false);h.root:FindById("quickDecoy"):SetVisible(false)
    h.root:FindById("quickMenu"):SetVisible(false)
    self:Refresh()
end
function T:MoveDown(e)
    local h=self.hud
    if h.joystickPointer_ or not e:IsPrimaryAction() or not self:CanMove() or h.sim.skillSelection then return end
    local pad=h.padSize_
    -- The initial origin is the finger itself, including presses near an edge.
    -- Clamping the base inward here would create movement before the first drag.
    self.center={x=e.x,y=e.y}
    h.joystick_:SetStyle{left=self.center.x-pad/2,top=self.center.y-pad/2};h.joystick_:SetVisible(true)
    -- A stable absolute center avoids a one-frame Yoga delay on the initial press.
    self.proxy={GetAbsoluteLayout=function() return {x=self.center.x-pad/2,y=self.center.y-pad/2,w=pad,h=pad} end}
    h:JoystickDown(e,self.proxy)
end
function T:CanMove()
    local h=self.hud
    return not self.editor and not h.cardInfoShown_ and h.scaleMgr:CurrentScale()=="cell"
        and h.sim:CanUseAction("move") and not (input and (input.focus==false or input.minimized==true))
end
function T:MoveDrag(e)
    if self.proxy and e.pointerId==self.hud.joystickPointer_ then
        -- Keep this press origin fixed; HUD clamps only the inner knob's travel.
        self.hud:JoystickMove(e,self.proxy)
    end
end
function T:Entries()
    local sim=self.hud.sim;local entries={}
    for _,id in ipairs(sim.world.abilities.order) do
        if A.Owned(sim.world,id) and A.Config(id).targetType and not isToggle[id] then
            local def=sim.cards:Definition(id)
            if id=="cluster_dispatch" then
                entries[#entries+1]={id=id,name="集合",target={command="gather"}}
                entries[#entries+1]={id=id,name="留守",target={command="hold"}}
            elseif id=="node_hide" then
                local swarm=sim.world:SwarmById(sim.world.currentControlledSwarmId)
                if swarm and not swarm.isHidden then entries[#entries+1]={id=id,name="寄居藏身",enter=true} end
                for _,hidden in ipairs(sim.world.swarms) do
                    if hidden.isHidden then entries[#entries+1]={id=id,name="群"..hidden.id.."出藏",target={swarmId=hidden.id,exit=true}} end
                end
            else entries[#entries+1]={id=id,name=def and def.name or id} end
        end
    end
    return entries
end
function T:Available(id)
    if isToggle[id] then return A.Owned(self.hud.sim.world,id) end
    if id=="skillWheel" then return #self:Entries()>0 end
    return true
end
function T:Down(e)
    if self.editor or self.gesture or not e:IsPrimaryAction() or not Controls.CanUse(self.hud) then return end
    local entries=self:Entries()
    if #entries==0 then self.hud:Notify("获得主动技能卡后，按住展开技能盘");consume(e);return end
    if #entries>8 then
        local pages=math.ceil(#entries/7);self.page=((self.page or 1)-1)%pages+1
        local page={}
        for i=(self.page-1)*7+1,math.min(#entries,self.page*7) do page[#page+1]=entries[i] end
        page[#page+1]={page=true,name="下一页\n"..self.page.."/"..pages};entries=page
    end
    Controls.Cancel(self.hud.sim);self.hud:CloseDrawers()
    local radius=math.min(116,self.h*.26);local margin=radius+35
    local x=math.max(self.safe.left+margin,math.min(self.safe.left+self.w-margin,e.x))
    local y=math.max(self.safe.top+margin,math.min(self.safe.top+self.h-margin,e.y))
    self.gesture={pointer=e.pointerId,run=self.hud.sim.cards.runId,control=self.hud.sim.world.currentControlledSwarmId,
        entries=entries,age=0,x=x,y=y,startX=e.x,startY=e.y,px=e.x,py=e.y,radius=radius}
    consume(e)
end
function T:DrawRing()
    local g=self.gesture;if not g then return end
    local stamp=tostring(g.selected)..":"..math.floor(self.hud.sim.world.time*10)
    if g.drawStamp==stamp then return end
    g.drawStamp=stamp
    self.ring:SetVisible(true)
    for _,btn in pairs(self.buttons) do btn:SetStyle{opacity=.12} end
    for i,entry in ipairs(g.entries) do
        local slot=self.ring:FindById("radialSlot_"..i)
        if not slot then
            slot=UI.Panel{id="radialSlot_"..i,position="absolute",borderRadius=12,borderWidth=2,pointerEvents="none"}
            artwork(slot,entry.page and "skillWheel" or entry.id,entry.name)
            slot.cooldownLabel_=UI.Label{position="absolute",right=1,top=0,width=40,height=16,fontSize=10,
                textAlign="center",verticalAlign="middle",backgroundColor={14,9,20,245},borderRadius=5,pointerEvents="none"}
            slot:AddChild(slot.cooldownLabel_);self.ring:AddChild(slot)
        end
        local angle=-math.pi/2+(i-1)*2*math.pi/#g.entries
        local cd=entry.page and 0 or self.hud.sim:GetSkillState(entry.id).cooldown
        local selected=g.selected==i
        Skin.SetIcon(slot,entry.page and "ability_menu" or entry.id)
        slot:SetVisible(true);slot.touchCaption_:SetText(entry.name:gsub("\n"," "))
        slot.cooldownLabel_:SetVisible(cd>0);slot.cooldownLabel_:SetText(string.format("%.1fs",cd))
        slot.assetIcon_:SetStyle{left=11,top=2,width=42,height=42,translateY=0}
        slot.touchCaption_:SetStyle{left=1,top=45,width=62,height=17,fontSize=11}
        slot:SetStyle{left=g.x+math.cos(angle)*g.radius-32,top=g.y+math.sin(angle)*g.radius-32,width=64,height=64,
            padding=0,paddingLeft=0,paddingRight=0,paddingTop=0,paddingBottom=0,
            backgroundColor=selected and {126,78,31,250} or {28,18,30,245},
            borderColor=selected and {255,212,121,255} or {159,116,76,230},opacity=cd>0 and .65 or 1}
    end
    for i=#g.entries+1,12 do local slot=self.ring:FindById("radialSlot_"..i);if slot then slot:SetVisible(false) end end
    local entry=g.selected and g.entries[g.selected]
    local text="滑向技能后松手\n回到中心或滑出圆盘取消"
    if entry then
        local kind=entry.page and "page" or A.Config(entry.id).targetType
        text=entry.name..((kind=="cell" or kind=="node" or kind=="direction") and not entry.target
            and "\n松手选定，再点高亮目标" or "\n松手释放 · 回中取消")
        if entry.page then text="下一页\n松手切页，再按住展开" end
    end
    self.caption:SetText(text);self.caption:SetStyle{left=g.x-75,top=g.y-38}
end
function T:Drag(e)
    local g=self.gesture;if not g or e.pointerId~=g.pointer then return end
    if e:IsMouse() and (e.buttons & UI.PointerEvent.Buttons.Primary)==0 then self:Cancel();consume(e);return end
    g.px,g.py=e.x,e.y;self:Choose();consume(e)
end
function T:Choose()
    local g=self.gesture;if not g then return end
    local dx,dy=g.px-g.x,g.py-g.y;local d=math.sqrt(dx*dx+dy*dy)
    local fromStart=math.sqrt((g.px-g.startX)^2+(g.py-g.startY)^2)
    g.selected=nil
    if g.age>=.18 and d>=45 and d<=g.radius+66 and fromStart>=24 then
        local angle=(math.atan(dy,dx)+math.pi/2)%(2*math.pi)
        g.selected=(math.floor(angle/(2*math.pi/#g.entries)+.5)%#g.entries)+1
    end
    if g.age>=.18 then self:DrawRing() end
end
function T:Valid()
    local g=self.gesture;local h=self.hud
    return g and Controls.CanUse(h) and g.run==h.sim.cards.runId and g.control==h.sim.world.currentControlledSwarmId
end
function T:Up(e)
    local g=self.gesture;if not g or e.pointerId~=g.pointer then return end
    if not e:IsPrimaryAction() then self:Cancel();consume(e);return end
    g.px,g.py=e.x,e.y;self:Choose()
    local entry=self:Valid() and g.selected and g.entries[g.selected]
    self:Cancel();consume(e)
    if entry and entry.page then self.page=(self.page or 1)+1;self.hud:Notify("已切换技能页，再按住展开")
    elseif entry then Controls.Activate(self.hud,entry.id,entry.target,entry.enter) end
end
function T:Cancel()
    self.gesture=nil;self.ring:SetVisible(false)
    for _,btn in pairs(self.buttons) do btn:SetStyle{opacity=1} end
end
function T:RefreshMovement()
    local h=self.hud
    local canMove=self:CanMove() and not h.sim.skillSelection
    self.zone:SetVisible(canMove)
end
function T:Refresh()
    local h=self.hud;local active=Mobile.IsTouch(h) and h.sim.started and h.scaleMgr:CurrentScale()=="cell" and not h.sim.ending
    self.layer:SetVisible(active and not self.editor and not h.cardInfoShown_)
    self:RefreshMovement()
    for _,id in ipairs(toggles) do
        local btn=self.buttons[id];btn:SetVisible(A.Owned(h.sim.world,id))
        btn:SetDisabled(not Controls.CanUse(h))
        if A.Owned(h.sim.world,id) then
            local on=h.sim:GetSkillState(id).active
            btn.touchState_:SetText(on and "开" or "关")
            btn.touchState_:SetStyle{backgroundColor=on and {39,105,69,255} or {46,33,42,255},
                fontColor=on and {170,255,190,255} or {205,185,165,255}}
            btn:SetStyle{borderColor=on and {126,230,170,255} or {159,116,76,230},backgroundColor=on and {23,65,48,235} or {28,17,26,225}}
        end
    end
    self.wheel:SetVisible(self:Available("skillWheel"));self.wheel:SetDisabled(not Controls.CanUse(h))
    for _,id in ipairs({"quickDash","quickDecoy","quickMenu"}) do h.root:FindById(id):SetVisible(false) end
end
function T:Update(dt)
    if self.gesture then
        if not self:Valid() or not UI.Input.GetPointer(self.gesture.pointer) then self:Cancel()
        else self.gesture.age=self.gesture.age+math.max(0,dt);self:Choose() end
    end
    if self.editor and (self.hud.sim.ending or not self.hud.sim.started or self.editRun~=self.hud.sim.cards.runId) then self:Finish(false) end
    if self.cloudPending then
        self.cloudPending=self.cloudPending+dt
        if self.cloudPending>12 then self.cloudPending=nil;self.cloudAttempt=(self.cloudAttempt or 0)+1
            self.hud:Notify("布局已应用，云保存超时；请进入布局重试保存") end
    end
    local w,h,safe=self:Viewport()
    if self.w~=w or self.h~=h or self.safe.left~=safe.left or self.safe.top~=safe.top then
        if self.editor then self:Finish(false);self.hud:Notify("屏幕尺寸改变，未保存的布局已取消") end
        self:Apply()
    end
    -- Tutorial permission changes must reach hit testing in the same frame.
    self:RefreshMovement()
    self.age=self.age+dt;if self.age>=.12 then self.age=0;self:Refresh() end
end
function T:Edit()
    if self.editor or not Mobile.IsTouch(self.hud) or not self.hud.sim.started or self.hud.sim.ending or self.hud.cardInfoShown_ then return end
    local h=self.hud;self:Cancel();Controls.Cancel(h.sim);h:ClearTouchMove();h:CloseDrawers()
    self.draft=Layout.Clean(self.saved);self.selected=self:Available("skillWheel") and "skillWheel" or "absorbBtn";self.editRun=h.sim.cards.runId
    h.sim:SetPaused("control-layout",true)
    self.editor=UI.Panel{id="controlLayoutEditor",position="absolute",left=0,top=0,width="100%",height="100%",
        zIndex=30000,backgroundColor={7,5,15,180},pointerEvents="auto"}
    self.handles={}
    for _,id in ipairs(Layout.ids) do
        if self:Available(id) then
        local key=id
        local handle=UI.Panel{id="layoutHandle_"..id,position="absolute",borderRadius=40,borderWidth=2,
            backgroundColor={48,31,40,230},pointerEvents="box-only",
            onPointerDown=function(e)
                if self.editPointer or not e:IsPrimaryAction() then return end
                self.editPointer=e.pointerId;self.selected=key
                local b=Layout.Bounds(self.draft,key,self.w,self.h);self.dragOffset={x=e.x-self.safe.left-b.x,y=e.y-self.safe.top-b.y}
                self:DrawEditor();consume(e)
            end,
            onPointerMove=function(e)
                if e.pointerId~=self.editPointer or self.selected~=key then return end
                Layout.Put(self.draft,key,e.x-self.safe.left-self.dragOffset.x,e.y-self.safe.top-self.dragOffset.y,nil,self.w,self.h)
                self:DrawEditor();consume(e)
            end,
            onPointerUp=function(e) if e.pointerId==self.editPointer then self.editPointer=nil;consume(e) end end,
            onPointerCancel=function(e) if e.pointerId==self.editPointer then self.editPointer=nil;consume(e) end end}
        if id=="joystick" then
            handle:AddChild(UI.Panel{position="absolute",left="50%",top="50%",translateX=-20,translateY=-20,
                width=40,height=40,backgroundImage="image/ui/frames/ui_joystick_knob_normal.png",backgroundFit="contain",pointerEvents="none"})
        else artwork(handle,id,Layout.names[id]) end
        self.handles[id]=handle;self.editor:AddChild(handle)
        end
    end
    self.editorStatus=UI.Label{text="",width="100%",fontSize=12,textAlign="center",whiteSpace="normal"}
    self.sizeSlider=Skin.Slider{id="controlSizeSlider",width=220,min=Layout.minScale,max=Layout.maxScale,step=.05,value=1,
        onChange=function(_,v)
            local b=Layout.Bounds(self.draft,self.selected,self.w,self.h)
            Layout.Put(self.draft,self.selected,b.x,b.y,v,self.w,self.h);self:DrawEditor()
        end}
    local header=UI.Panel{position="absolute",left=self.safe.left,top=self.safe.top,width=self.w,height=118,
        padding=8,gap=4,backgroundColor={19,13,25,250},children={
        UI.Panel{width="100%",height=44,flexDirection="row",gap=8,children={
            UI.Label{text="按键布局 · 拖动按键",fontSize=18,flexGrow=1,justifyContent="center"},
            Skin.Button{id="layoutReset",text="恢复默认",height=44,width=100,onClick=function() self.draft=Layout.Clean(nil);self:DrawEditor() end},
            Skin.Button{id="layoutCancel",text="取消",height=44,width=72,onClick=function() self:Finish(false) end},
            Skin.Button{id="layoutSave",text="保存",height=44,width=72,onClick=function() self:Finish(true) end}}},
        UI.Panel{width="100%",height=44,flexDirection="row",alignItems="center",justifyContent="center",gap=12,children={
            UI.Label{text="选中按键大小",fontSize=13},self.sizeSlider}},self.editorStatus}}
    self.editor:AddChild(header);(UI.GetRoot() or h.root):AddChild(self.editor)
    self:DrawEditor();self:Refresh()
end
function T:DrawEditor()
    for id,handle in pairs(self.handles) do
        local b=Layout.Bounds(self.draft,id,self.w,self.h);b.left,b.top=b.left+self.safe.left,b.top+self.safe.top
        circle(handle,b);handle:SetStyle{borderColor=id==self.selected and {255,215,125,255} or {133,122,135,255}}
        if id=="joystick" then handle:SetStyle{backgroundImage="image/ui/frames/ui_joystick_base_normal.png",backgroundFit="contain"}
        else placeArtwork(handle,b,id) end
    end
    local p=self.draft.controls[self.selected];local size=p and p.scale or Layout.defaultScales[self.selected]
    -- SetValue emits onChange; assign props to avoid recursive callbacks.
    self.sizeSlider.props.value=size
    self.editorStatus:SetText(Layout.names[self.selected]..string.format(" · %.0f%%（统一基准）",size*100).." · 摇杆按下定位、底座固定；仅显示已获得的技能")
end
function T:Finish(save)
    if not self.editor then return end
    if save then
        local conflict=Layout.Conflict(self.draft,self.w,self.h,function(id) return self:Available(id) end)
        if conflict then self.editorStatus:SetText(conflict);return end
        if not Layout.Save(self.draft) then self.editorStatus:SetText("保存失败，请重试；取消可返回原布局");return end
        self.saved=Layout.Clean(self.draft)
    end
    local editor=self.editor;self.editor=nil;self.editPointer=nil;self.draft=nil
    editor.parent:RemoveChild(editor);editor:Destroy();self.hud.sim:SetPaused("control-layout",false)
    self:Apply();self.hud:Notify(save and "按键布局已保存" or "已取消布局修改")
    if save then
        self.revision=self.revision+1
        if GetPlatform and GetPlatform()=="Web" then
            if Layout.CloudAvailable() then
                self.cloudAttempt=(self.cloudAttempt or 0)+1;local attempt=self.cloudAttempt
                self.cloudPending=0;self.hud:Notify("布局已应用，正在保存到云端")
                Layout.SaveCloud(self.saved,function(ok)
                    if self.destroyed or self.hud.destroyed_ or self.cloudAttempt~=attempt then return end
                    self.cloudPending=nil;self.hud:Notify(ok and "按键布局已保存到云端" or "布局已应用，云保存失败；请进入布局重试保存")
                end)
            else self.hud:Notify("布局已应用到本次游戏；登录后保存可保留到下次") end
        end
    end
end
function T:Destroy()
    self.destroyed=true;self:Cancel();if self.editor then self:Finish(false) end
end
return T
