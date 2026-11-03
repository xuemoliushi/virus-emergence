"""Phone HUD actions and foreground ownership; native pixels are checked separately."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.tmp/test-deps'))
from bird_ui_regression import runtime
from compact_ui_regression import SMALL

CASES = {
    'native exit capsule leaves utility buttons and stats tab in separate rows': r'''
local h,g,s=fixture();local M=require('UI.MobileLayout');M.MarkTouch()
sdk={GetNativeExitMenuRect=function() return {bottom=.1} end}
h.layoutWidth_=0;h:ApplyLayout()
local insets=M.SafeInsets();assert(insets.top==UI.GetHeight()*.1)
local tab=h.root:FindById('statsEdgeTab').props
local utilities=h.root:FindById('mobileUtilities').props
assert(tab.top>=insets.top+8+utilities.top+utilities.height+8)
assert(h.root:FindById('stageSummary').props.top==tab.top)
sdk=nil
''',
    'thumb controls stay separated, keep their callbacks and reserve the skill-menu area': r'''
local h,g,s=fixture();require('UI.MobileLayout').MarkTouch()
local M=require('UI.MobileLayout')
local ids={'absorbBtn','splitBtn','skillWheel','switchBtn','touchToggle_swarm_anchor','touchToggle_infection_trail','touchToggle_merge_seed'}
local function overlap(a,b)
 return a.left<b.left+b.width and b.left<a.left+a.width
    and a.top<b.top+b.height and b.top<a.top+a.height
end
local time=s.time;local controlled=s.world.currentControlledSwarmId
-- UI.Scale.DEFAULT maps the tested 667x375 / 844x390 phones to these UI-space sizes.
for _,size in ipairs({{924,520},{1147,530},{1280,720}}) do
 graphics.width,graphics.height=size[1],size[2]
 h:ApplyMobileLayout({w=size[1],h=size[2]},M.Metrics(size[1],size[2]))
 local dock=h.root:FindById('touchControlLayer').props
 local bounds={}
 for _,id in ipairs(ids) do
  local btn=h.root:FindById(id);local p=btn.props
  assert((btn.props.onClick or btn.props.onPointerDown) and p.width>=44 and p.height>=44,id.." touch size/callback")
  assert(p.left>=0 and p.top>=0 and p.left+p.width<=size[1] and p.top+p.height<=size[2]+.001,id.." safe bounds")
  for _,other in ipairs(bounds) do assert(not overlap(p,other),id.." overlaps") end
  bounds[#bounds+1]=p
 end
 local main=h.root:FindById('absorbBtn').props
 assert(main.width>h.root:FindById('splitBtn').props.width*1.4)
 assert(not h.root:FindById('quickDash'):IsVisible() and not h.root:FindById('quickMenu'):IsVisible())
 assert(not h.root:FindById('moveJoystick'):IsVisible(),"floating joystick starts hidden")
end
assert(s.time==time and s.world.currentControlledSwarmId==controlled)
''',

    'task disclosure preserves simulation and feedback expires on a phone': r'''
local h,g,s=fixture()
require('UI.MobileLayout').MarkTouch()
local content=h.root:FindById('hudContent');content.rect={x=0,y=0,w=844,h=390}
h.layoutWidth_=nil;h:ApplyLayout()
local task=h.root:FindById('stagePanel')
assert(task.parent==h.root and task.props.left==8 and task.props.top==8)
assert(not h.root:FindById('hudLeftScroll'):IsVisible())
local elapsed=s.time
assert(h.root:FindById('taskText'):IsVisible())
assert(not h.root:FindById('taskHint'):IsVisible())
h.root:FindById('taskToggle').props.onClick()
assert(h.root:FindById('taskText'):IsVisible() and s.time==elapsed)
assert(h.motions_.task.target==1)
h:ToggleDrawer('groups');assert(h.motions_.groups.target==1 and h.motions_.task.target==0)
h:ToggleDrawer('task');assert(h.motions_.task.target==1 and h.motions_.groups.target==0)
h:ToggleDrawer('stats');assert(h.motions_.stats.target==1 and h.motions_.task.target==0)
assert(h:CloseDrawers() and h.motions_.stats.target==0)
h:ToggleDrawer('task')
s.skillMenu={page='main',runId=s.cards.runId,controlId=s.world.currentControlledSwarmId}
require('UI.SkillPanel').Refresh(h)
assert(s.skillMenu and h.motions_.task.target==0)
h:ToggleDrawer('groups');assert(not s.skillMenu)
h:CloseDrawers();h:ToggleDrawer('task')
h.root:FindById('taskToggle').props.onClick()
assert(h.root:FindById('taskText'):IsVisible())
assert(not h.root:FindById('taskHint'):IsVisible())
h:Notify('操作失败');assert(h.root:FindById('statusTicker'):IsVisible())
h:UpdateTicker(4);assert(not h.root:FindById('statusTicker'):IsVisible())
assert(h.root:FindById('mapBtn').parent.id=='mobileUtilities' or h.root:FindById('mapBtn').parent.props.id=='mobileUtilities')
assert(h.root:FindById('splitBtn').props.onClick and h.root:FindById('switchBtn').props.onClick)
''',
    'tutorial yields to cards and abilities and returns without losing the lesson': r'''
local h,g,s=fixture()
local Tutorial=require('Core.Tutorial')
local Overlay=require('UI.TutorialOverlay')
s.tutorial=Tutorial.New(s);assert(s.tutorial:StartIfNeeded())
local overlay=Overlay.New(s,g)
s.skillMenu={page='main'};overlay.touchSkipHeld=true;overlay:Update()
assert(not overlay.root:IsVisible() and not overlay.touchSkipHeld and s.tutorial.active)
s.skillMenu=nil;s.cards.pending={mode='formal'};overlay:Update()
assert(not overlay.root:IsVisible() and s.tutorial.step=='intro')
s.cards.pending=nil;s.cardNotice={formal=true};overlay:Update()
assert(not overlay.root:IsVisible() and s.tutorial.active)
s.cardNotice=nil;s.pauseReasons.settings=true;overlay:Update()
assert(not overlay.root:IsVisible() and s.tutorial.active)
s.pauseReasons.settings=nil;overlay:Update()
assert(overlay.root:IsVisible() and s.tutorial.step=='intro')
''',
}

if __name__ == '__main__':
    for name, code in CASES.items():
        lua = runtime()
        lua.globals().print = lambda *args: None
        lua.execute('graphics.width=844;graphics.height=390;UI.GetHeight=function() return graphics.height end;UI.GetWidth=function() return graphics.width end')
        lua.execute(SMALL + code)
        print('PASS:', name)
    print(f'{len(CASES)} mobile interaction checks passed; OS touch and GPU layout checked separately.')
