"""Real UI control handlers with native layout/draw dependencies replaced at the boundary.

Checks the new image skin against Slider/Toggle/Checkbox/ProgressBar interactions,
dynamic ability UI and imported file integrity. This is not native visual acceptance.
"""
from pathlib import Path
import hashlib
import json
import sys
from main_menu_regression import runtime as menu_runtime
from bird_ui_regression import runtime as hud_runtime

ROOT = Path(__file__).resolve().parents[1]
SETUP = r'''
Skin=require('UI.AssetTheme')
local Widget=UI.Widget
package.loaded['urhox-libs/UI/Core/Widget']=Widget
package.loaded['urhox-libs/UI/Core/Theme']={ComponentStyle=function() return {} end}
package.loaded['urhox-libs/UI/Core/Style']={ApplyDefaults=function(props,defaults)
 for k,v in pairs(defaults) do if props[k]==nil then props[k]=v end end
end}
function Widget:SetState(values) for k,v in pairs(values) do self.state[k]=v end end
function Widget:DispatchEvent() end
function Widget:GetRenderProp(name) return self.props[name] end
function Widget:OnPointerDown() end
function Widget:OnPointerMove() end
function Widget:OnPointerUp() end
function Widget:GetAbsoluteLayout() return self.rect or {x=8,y=10,w=400,h=40} end
Widget.GetAbsoluteLayoutForHitTest=Widget.GetAbsoluteLayout
draws={};clips={}
function Widget:RenderBackgroundImage(_,path,rect,fit,slice,radius,tint,opacity)
 assert(rect.w>=0 and rect.h>=0)
 for _,v in pairs(rect) do assert(v==v and math.abs(v)<1e6) end
 if fit=='sliced' then
  assert(slice[1] and slice[2] and slice[3] and slice[4],'numeric slice order: top right bottom left')
  assert(slice[1]+slice[3]<=rect.h and slice[2]+slice[4]<=rect.w,'corners must fit target')
 end
 draws[#draws+1]={path=path,rect=rect,fit=fit,opacity=opacity}
end
function nvgSave() end
function nvgRestore() end
function nvgIntersectScissor(_,x,y,w,h) assert(w>=0 and h>=0);clips[#clips+1]={x=x,y=y,w=w,h=h} end
for _,kind in ipairs({'Slider','Toggle','Checkbox','ProgressBar'}) do
 UI[kind]=require('urhox-libs/UI/Widgets/'..kind)
end
function near(a,b) assert(math.abs(a-b)<1e-6,tostring(a)..' != '..tostring(b)) end
'''

CONTROL_TESTS = {
    'slider thumb follows actual drag, snaps values and saves on release': r'''
local changes,ends=0,0
local s=Skin.Slider{min=0,max=100,value=0,step=1,
 onChange=function(_,v) changes=changes+1 end,onChangeEnd=function(_,v) ends=ends+1;near(v,65) end}
s.rect={x=20,y=50,w=400,h=40}
local event={x=20+14,IsPrimaryAction=function() return true end}
s:OnPointerDown(event);event.x=34+(400-28)*.65;s:OnPointerMove(event);s:OnPointerUp(event)
near(s:GetValue(),65);assert(changes==1 and ends==1 and not s.state.dragging)
s:Render(nil);near(draws[#draws].rect.x+14,event.x);near(clips[1].w,(400-28)*.65)
''',
    'disabled slider ignores input and narrow rendering keeps legal rectangles': r'''
local s=Skin.Slider{min=0,max=100,value=40,disabled=true};s.rect={x=0,y=0,w=20,h=40}
s:OnPointerDown{x=100,IsPrimaryAction=function() return true end};assert(s:GetValue()==40)
s:Render(nil);assert(draws[#draws].opacity==.35)
''',
    'toggle uses native value and callback and both thumb positions match': r'''
local changed=0;local s=Skin.Toggle{value=false,label='动态背景',onChange=function(_,v) changed=changed+1;assert(v) end}
s:Render(nil);near(draws[2].rect.x,11)
s:OnClick();assert(s:GetValue() and changed==1);draws={};s:Render(nil);near(draws[2].rect.x,43)
s:SetDisabled(true);s:OnClick();assert(changed==1 and s:GetValue())
assert(s.children[1].props.pointerEvents=='none')
''',
    'tutorial checkbox keeps native checked state and callback': r'''
local values={};local s=Skin.Checkbox{checked=false,label='跳过新手教程',onChange=function(_,v) values[#values+1]=v end}
s:OnClick();assert(s:IsChecked() and values[1]);s:OnClick();assert(not s:IsChecked() and not values[2])
s:SetDisabled(true);s:OnClick();assert(#values==2)
''',
    'progress clips original texture at zero, partial and maximum actual values': r'''
local s=Skin.Progress{value=0,max=10};s.rect={x=10,y=20,w=300,h=14}
s:Render(nil);assert(#draws==1)
s:SetValue(4);s:Render(nil);near(clips[#clips].w,290*.4)
s:SetValue(40);s:Render(nil);assert(s:GetValue()==10);near(clips[#clips].w,290)
''',
}

HUD_TESTS = {
    'six passive icons unlock as indicators and do not become skill buttons': r'''
local h,g,s=fixture();local A=require('Core.AbilityRuntime');local Skills=require('UI.SkillPanel')
local ids={'debris_camouflage','rupture_spread','swarm_capacity_4','swarm_capacity_6','swarm_local_brain','tail_preserve'}
 for _,id in ipairs(ids) do
 local node=h.root:FindById('passiveIcon_'..id);assert(not node:IsVisible() and not node.props.onClick)
 for _,card in ipairs(Config.Cards.definitions) do if card.id==id then A.Acquire(s.world,card) end end
end
Skills.Refresh(h)
for _,id in ipairs(ids) do assert(h.root:FindById('passiveIcon_'..id):IsVisible()) end
assert(#require('UI.SkillControls').Entries(s)==0)
''',
    'statistics remain discoverable by an actual toggle without pausing play': r'''
local h,g,s=fixture();assert(not h.root:FindById('entityDetails'):IsVisible())
callback(h,'statsToggle');assert(h.root:FindById('entityDetails'):IsVisible() and not s.paused)
assert(h.root:FindById('totalReleasedCount'))
callback(h,'statsToggle');h.motions_.stats:Update(.3);assert(not h.root:FindById('entityDetails'):IsVisible())
''',
    'skill icons follow acquisition order and submenus and cost text remains visible': r'''
local h,g,s=fixture();local A=require('Core.AbilityRuntime');local Skills=require('UI.SkillPanel');local C=require('UI.SkillControls')
for _,id in ipairs({'node_cover','cluster_dispatch','shed_decoy'}) do
 for _,card in ipairs(Config.Cards.definitions) do if card.id==id then A.Acquire(s.world,card) end end
end
C.Toggle(h);Skills.Refresh(h)
assert(h.root:FindById('skillMenu_1').assetIcon_.props.backgroundImage:find('icon_node_cover'))
assert(h.root:FindById('skillMenu_2').assetIcon_.props.backgroundImage:find('icon_cluster_dispatch'))
assert(h.root:FindById('quickDecoy_detail'):GetText():find('投入4'))
assert(h.root:FindById('skillMenu_1').props.paddingLeft==12)
assert(h.root:FindById('skillMenu_1').assetDetail_.props.position==nil)
assert(h.root:FindById('skillMenuClose').parent~=h.root:FindById('skillMenuScroll'))
assert(not h.root:FindById('skillMenuToggle'):IsVisible() and h.root:FindById('quickMenu'):IsVisible())
''',
}


def run():
    mapping = json.loads((ROOT/'assets/image/ui/mapping.json').read_text(encoding='utf-8'))
    assert mapping['imported'] == 51 and len(mapping['entries']) == 51
    for entry in mapping['entries']+mapping['displayDerivatives']:
        path=ROOT/'assets/image/ui'/entry['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
    print('PASS 51 original images imported with exact hashes')
    for name, code in CONTROL_TESTS.items():
        lua=menu_runtime()
        lua.execute("package.path="+repr((ROOT/'?.lua').as_posix())+"..';'..package.path")
        lua.execute(SETUP+code)
        print('PASS',name)
    lua=menu_runtime()
    source=(ROOT/'urhox-libs/UI/Core/Widget.lua').read_text(encoding='utf-8-sig')
    function=source[source.index('function Widget:RenderSlicedImage'):source.index('--- Render complete background')]
    lua.execute("local Widget=UI.Widget\n"+function)
    lua.execute(r'''local Skin=require('UI.AssetTheme')
function near(a,b) assert(math.abs(a-b)<1e-6) end
rectangles={}
function nvgRGBA(...) return {...} end
function nvgImagePattern(...) return {...} end
function nvgImagePatternTinted(...) return {...} end
function nvgBeginPath() end
function nvgFillPaint() end
function nvgFill() end
function nvgRect(_,x,y,w,h) rectangles[#rectangles+1]={x=x,y=y,w=w,h=h} end
for _,spec in ipairs({{'action',138,48,192,64},{'menu',432,72,432,72},{'primary',260,52,320,64},
 {'secondary',200,44,320,64},{'square',44,44,44,44},{'hud',280,240,384,256},{'dialog',420,240,512,640},
 {'tooltip',338,260,256,128},{'minimap',156,208,192,256},{'skill',388,104,192,64}}) do
 local widget=Skin.Frame({},spec[1]);rectangles={}
 widget:RenderSlicedImage(nil,1,spec[4],spec[5],{x=0,y=0,w=spec[2],h=spec[3]},widget.props.backgroundSlice,0,nil,1)
 assert(#rectangles==9,'all nine slices drawn for '..spec[1])
 local area=0
 for _,r in ipairs(rectangles) do assert(r.x>=0 and r.y>=0 and r.x+r.w<=spec[2] and r.y+r.h<=spec[3]);area=area+r.w*r.h end
 near(area,spec[2]*spec[3])
end
''')
    print('PASS actual engine nine-slice renderer covers 10 target sizes without overlapping corners')
    for name, code in HUD_TESTS.items():
        lua=hud_runtime()
        lua.execute('Config.Gameplay.mapSeed=314159')
        lua.execute(code)
        print('PASS',name)
    print(f'{2+len(CONTROL_TESTS)+len(HUD_TESTS)} image UI checks passed; native renderer and input devices unverified.')


if __name__=='__main__':
    run()
