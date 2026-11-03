-- 基于 scaffold-2d 的组件皮肤。交互仍由原 UI 控件处理，图片复用其缓存与 DPR。
local UI = require("urhox-libs/UI")

---@class SkinnedButton: Button
---@field assetIcon_ Panel?
---@field assetDetail_ Label?

---@class AssetThemeAPI
---@field colors table
---@field Frame fun(props:table,kind:string?):Panel
---@field Button fun(props:table,kind:string?,icon:string?):SkinnedButton
---@field Icon fun(id:string,size:number?):Panel
---@field SetIcon fun(button:table,id:string?)
---@field SetDetail fun(button:table,text:string)
---@field Keycap fun(key:string):Panel
---@field Slider fun(props:table):Slider
---@field Progress fun(props:table):ProgressBar
---@field Toggle fun(props:table):Toggle
---@field Checkbox fun(props:table):Checkbox
---@field Dropdown fun(props:table):Dropdown
---@field Scroll fun(props:table):ScrollView
---@field Ornament fun(props:table?):Panel
---@field ApplyColors fun()
local Skin = {}
Skin.colors = { text={241,224,193,255}, muted={178,151,126,255}, gold={234,177,87,255},
    border={139,87,53,200}, surface={28,16,16,245}, selected={250,193,106,255} }
local ROOT = "image/ui/"
local FRAMES = {
    action="ui_action_button_normal", menu="ui_menu_button_normal", primary="ui_primary_button_normal",
    secondary="ui_secondary_button_normal", swarm="ui_swarm_button_normal", square="ui_square_button_normal",
    skill="ui_skill_row_gold_192x64", hud="ui_hud_panel_normal", dialog="ui_dialog_panel_normal",
    tooltip="ui_tooltip_panel_normal", minimap="ui_minimap_frame_normal",
}
local SLICE = {
    action={12,14,12,14}, menu={10,12,10,12},
    primary={9,12,9,12}, secondary={9,11,9,11},
    swarm={9,10,9,10}, square={6,6,6,6},
    skill={8,9,8,9}, hud={14,14,14,14},
    dialog={14,14,14,14}, tooltip={10,10,10,10},
    minimap={21,18,16,18},
}

---@param props table
---@param kind string?
---@return Panel
function Skin.Frame(props,kind)
    kind=kind or props.frameKind or "hud"
    props.frameKind=nil
    props.backgroundImage=ROOT.."scaled/"..FRAMES[kind]..".png"
    props.backgroundFit,props.backgroundSlice="sliced",SLICE[kind]
    props.backgroundColor,props.borderWidth,props.borderRadius=false,0,0
    return UI.Panel(props)
end

---@param id string
---@param size number?
---@return Panel
function Skin.Icon(id,size)
    return UI.Panel {width=size or 40,height=size or 40,flexShrink=0,backgroundImage=ROOT.."icons/icon_"..id..".png",
        backgroundFit="contain",pointerEvents="none"}
end

---@param button table
---@param id string?
function Skin.SetIcon(button,id)
    if not id then return end
    local path=ROOT.."icons/icon_"..id..".png"
    if button.assetIcon_ then
        if button.assetIcon_.props.backgroundImage~=path then button.assetIcon_:SetStyle {backgroundImage=path} end
        return
    end
    local icon=Skin.Icon(id,button.props.assetIconSize or 40)
    icon:SetStyle {position="absolute",left=12,top="50%",translateY=-(button.props.assetIconSize or 40)/2}
    button.assetIcon_=icon
    button:SetStyle {paddingLeft=60,paddingRight=16}
    button:AddChild(icon)
end

---@param button table
---@param text string
function Skin.SetDetail(button,text)
    if not button.assetDetail_ then
        button.assetDetail_=UI.Label {id=button.props.id and (button.props.id.."_detail"),text=text,position="absolute",left=button.assetIcon_ and 64 or 14,
            right=12,bottom=4,height=26,whiteSpace="normal",fontSize=11,fontColor=Skin.colors.muted,
            verticalAlign="middle",pointerEvents="none"}
        button:AddChild(button.assetDetail_)
        button:SetStyle {paddingBottom=28}
    elseif button.assetDetail_.props.text~=text then button.assetDetail_:SetText(text) end
end

---@param props table
---@param kind string?
---@param icon string?
---@return SkinnedButton
function Skin.Button(props,kind,icon)
    kind=kind or props.buttonKind or "action"
    props.buttonKind=nil
    props.backgroundImage=ROOT.."scaled/"..FRAMES[kind]..".png"
    props.backgroundFit,props.backgroundSlice="sliced",SLICE[kind]
    props.backgroundColor,props.hoverBackgroundColor,props.pressedBackgroundColor=false,false,false
    props.disabledBackgroundColor=false
    props.backgroundImageOpacity,props.hoverBackgroundImageOpacity=0.92,1
    props.pressedBackgroundImageOpacity,props.disabledBackgroundImageOpacity=0.72,0.34
    props.textColor=props.textColor or Skin.colors.text
    props.disabledTextColor={133,110,96,255}
    props.borderWidth,props.hoverBorderWidth,props.pressedBorderWidth=0,1,1
    props.borderColor,props.hoverBorderColor,props.pressedBorderColor=Skin.colors.border,Skin.colors.gold,Skin.colors.gold
    props.borderRadius=3
    props.boxShadow,props.hoverBoxShadow,props.pressedBoxShadow,props.disabledBoxShadow=false,false,false,false
    props.height,props.fontSize=props.height or 56,props.fontSize or 14
    props.minFontSize=props.minFontSize or 11
    props.paddingLeft,props.paddingRight=icon and 60 or 16,16
    local b=UI.Button(props)
    Skin.SetIcon(b,icon)
    local update=b.Update
    b.Update=function(self,dt)
        if update then update(self,dt) end
        if self.assetIcon_ then
            local opacity=self.props.disabled and 0.35 or 1
            if self.assetIcon_.props.opacity~=opacity then self.assetIcon_:SetStyle {opacity=opacity} end
        end
    end
    return b
end

---@param key string
---@return Panel
function Skin.Keycap(key)
    return UI.Panel {width=key=="空格" and 46 or 36,height=27,flexShrink=0,pointerEvents="none",
        backgroundImage=ROOT.."scaled/ui_keycap_normal.png",backgroundFit="sliced",
        backgroundSlice={4,4,4,4},alignItems="center",justifyContent="center",
        children={UI.Label{text=key,fontSize=11,fontColor=Skin.colors.text,pointerEvents="none"}}}
end

-- These controls retain the library's pointer capture, values, callbacks and keyboard behavior.
---@param props table
---@return Slider
function Skin.Slider(props)
    props.thumbSize,props.trackHeight,props.height=28,10,40
    local widget=UI.Slider(props)
    widget.Render=function(_,nvg)
        local self=widget
        local l,p=self:GetAbsoluteLayout(),self.props
        local thumb=p.thumbSize
        local width=math.max(0,l.w-thumb)
        local value=math.max(0,math.min(1,(p.value-p.min)/math.max(0.000001,p.max-p.min)))
        local track={x=l.x+thumb/2,y=l.y+(l.h-10)/2,w=width,h=10}
        if width>=8 then
            self:RenderBackgroundImage(nvg,ROOT.."scaled/ui_slider_track_normal.png",track,"sliced",
                {3,4,3,4},0,nil,1)
            nvgSave(nvg);nvgIntersectScissor(nvg,track.x,track.y,width*value,10)
            self:RenderBackgroundImage(nvg,ROOT.."frames/ui_progress_fill_normal.png",track,"fill",nil,0,nil,p.disabled and 0.3 or 0.65)
            nvgRestore(nvg)
        end
        self:RenderBackgroundImage(nvg,ROOT.."frames/ui_slider_thumb_normal.png",
            {x=track.x+width*value-thumb/2,y=l.y+(l.h-thumb)/2,w=thumb,h=thumb},"contain",nil,0,nil,p.disabled and 0.35 or 1)
    end
    return widget
end

---@param props table
---@return ProgressBar
function Skin.Progress(props)
    props.height=props.height or 14
    local widget=UI.ProgressBar(props)
    widget.Render=function(_,nvg)
        local self=widget
        local l,p=self:GetAbsoluteLayout(),self.props
        local value=self:GetRenderProp("value") or p.value or 0
        local percent=math.max(0,math.min(1,value/math.max(0.000001,p.max or 1)))
        self:RenderBackgroundImage(nvg,ROOT.."scaled/ui_progress_track_normal.png",l,"sliced",
            {4,6,4,6},0,nil,1)
        local r={x=l.x+5,y=l.y+l.h*0.27,w=math.max(0,l.w-10),h=l.h*0.46}
        if percent>0 then
            nvgSave(nvg);nvgIntersectScissor(nvg,r.x,r.y,r.w*percent,r.h)
            self:RenderBackgroundImage(nvg,ROOT.."frames/ui_progress_fill_normal.png",r,"fill",nil,0,p.fillColor --[[@as RGBAColor?]],1)
            nvgRestore(nvg)
        end
    end
    return widget
end

---@param props table
---@return Toggle
function Skin.Toggle(props)
    props.trackWidth,props.trackHeight,props.thumbSize=64,32,26
    props.height=44
    local widget=UI.Toggle(props)
    widget:AddChild(UI.Label {text=props.label,position="absolute",left=78,right=0,height="100%",
        verticalAlign="middle",fontSize=14,fontColor=Skin.colors.text,pointerEvents="none"})
    widget.Render=function(_,nvg)
        local self=widget
        local l,p=self:GetAbsoluteLayout(),self.props
        local y=l.y+(l.h-32)/2
        self:RenderBackgroundImage(nvg,ROOT.."frames/ui_toggle_track_normal.png",{x=l.x,y=y,w=64,h=32},"contain",nil,0,
            p.value and nil or {145,125,115,255},p.disabled and 0.35 or 1)
        self:RenderBackgroundImage(nvg,ROOT.."frames/ui_toggle_thumb_normal.png",
            {x=l.x+(p.value and 35 or 3),y=y+3,w=26,h=26},"contain",nil,0,nil,p.disabled and 0.35 or 1)
    end
    return widget
end

---@param props table
---@return Checkbox
function Skin.Checkbox(props)
    props.fontSize,props.size,props.height=14,24,40
    props.checkedBgColor,props.checkedHoverBgColor,props.checkedPressedBgColor=Skin.colors.gold,{255,207,135,255},{190,121,56,255}
    props.uncheckedBgColor,props.uncheckedBorderColor={27,16,14,255},Skin.colors.border
    props.checkmarkColor={27,16,14,255}
    return UI.Checkbox(props)
end

---@param props table
---@return Dropdown
function Skin.Dropdown(props)
    props.triggerBgColor={0,0,0,0}
    props.borderWidth,props.hoverBorderWidth,props.openBorderWidth=0,0,0
    props.arrowColor={0,0,0,0}
    props.itemHoverBgColor,props.itemSelectedColor={83,48,25,255},{64,36,23,255}
    props.popupBgColor,props.boxShadow={0,0,0,0},false
    local widget=UI.Dropdown(props)
    local render=widget.Render
    widget.Render=function(_,nvg)
        local self=widget
        self:RenderBackgroundImage(nvg,ROOT.."scaled/ui_dropdown_field_normal.png",self:GetAbsoluteLayout(),"sliced",
            {10,25,10,10},0,nil,self.props.disabled and 0.35 or 1)
        render(self,nvg)
    end
    local renderPanel=widget.RenderDropdownPanel
    if renderPanel then
        widget.RenderDropdownPanel=function(_,nvg)
            local l=UI.GetVisualRect(widget)
            local metrics=widget:GetPanelMetrics(l)
            widget:RenderBackgroundImage(nvg,ROOT.."scaled/ui_hud_panel_normal.png",
                {x=l.x,y=metrics.y,w=l.w,h=metrics.height},"sliced",{14,14,14,14},0,nil,1)
            renderPanel(widget,nvg)
        end
    end
    return widget
end

---@param props table
---@return ScrollView
function Skin.Scroll(props)
    props.bounces=false
    local widget=UI.ScrollView(props)
    local render=widget.RenderScrollbars
    if render then
        widget.RenderScrollbars=function(self,nvg)
            render(self,nvg) -- Keep the exact native hit bounds and drag ratios.
            local r=self.vScrollbarBounds_
            if r then
                local l=self:GetAbsoluteLayout()
                local hit=self:GetAbsoluteLayoutForHitTest()
                local x,y=r.x-(hit.x-l.x),r.y-(hit.y-l.y)
                nvgBeginPath(nvg);nvgRect(nvg,x,l.y,r.w,l.h)
                nvgFillColor(nvg,nvgRGBA(27,16,14,255));nvgFill(nvg)
                self:RenderBackgroundImage(nvg,ROOT.."scaled/ui_scroll_thumb_normal.png",{x=x,y=y,w=r.w,h=r.h},
                    "sliced",{6,3,6,3},0,nil,math.max(0.5,self.scrollbarOpacity_ or 0))
            end
            r=self.hScrollbarBounds_
            if r then
                local l=self:GetAbsoluteLayout()
                local hit=self:GetAbsoluteLayoutForHitTest()
                local x,y=r.x-(hit.x-l.x),r.y-(hit.y-l.y)
                nvgBeginPath(nvg);nvgRect(nvg,l.x,y,l.w,r.h)
                nvgFillColor(nvg,nvgRGBA(27,16,14,255));nvgFill(nvg)
                nvgSave(nvg);nvgTranslate(nvg,x,y+r.h);nvgRotate(nvg,-math.pi/2)
                self:RenderBackgroundImage(nvg,ROOT.."scaled/ui_scroll_thumb_normal.png",{x=0,y=0,w=r.h,h=r.w},
                    "sliced",{6,3,6,3},0,nil,math.max(0.5,self.scrollbarOpacity_ or 0))
                nvgRestore(nvg)
            end
        end
    end
    return widget
end

---@param props table?
---@return Panel
function Skin.Ornament(props)
    props=props or {}
    props.width,props.height=props.width or "100%",props.height or 42
    props.backgroundImage,props.backgroundFit=ROOT.."frames/ui_title_ornament_normal.png","contain"
    props.pointerEvents="none"
    return UI.Panel(props)
end

function Skin.ApplyColors()
    if not UI.Theme then return end
    UI.Theme.SetTheme(UI.Theme.ExtendTheme(UI.Theme.GetTheme(),{colors={
        primary=Skin.colors.gold,primaryHover={255,205,123,255},primaryPressed={187,117,54,255},
        surface=Skin.colors.surface,surfaceHover={49,29,23,255},text=Skin.colors.text,textSecondary=Skin.colors.muted,
        border=Skin.colors.border,disabled={30,22,20,255},disabledText={127,103,91,255},
    }}))
end

return Skin
