"""Real Lua UI callbacks/state; native layout, input delivery and video decoder are boundaries."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from bird_ui_regression import runtime

SMALL='''
function UI.Widget:RemoveChild(child)
 for i,c in ipairs(self.children) do if c==child then table.remove(self.children,i);child.parent=nil;return self end end
end
Config.Gameplay.mapGenerationVersion=1
Config.Gameplay.width=26;Config.Gameplay.height=32;Config.Gameplay.cellCount=72
'''

CASES={
    'bottom actions retain their corner through resize, skill unlock and touch changes': '''
local h,g,s=fixture();local A=require('Core.AbilityRuntime');local Skills=require('UI.SkillPanel')
local content=h.root:FindById('hudContent')
local dock=h.root:FindById('hudBottomRow')
local joystick=h.root:FindById('joystickPanel')
local before=s.world.player.mass
for _,skill in ipairs({'none','emergency_dash','shed_decoy'}) do
 if skill~='none' then
  for _,card in ipairs(Config.Cards.definitions) do if card.id==skill then A.Acquire(s.world,card) end end
 end
 Skills.Refresh(h)
 for _,width in ipairs({1920,1280,760,640,390,320,1280}) do
  for _,touch in ipairs({false,true,false}) do
   joystick:SetVisible(touch);h.layoutWidth_=0
   content.rect={x=0,y=0,w=width,h=720};h:ApplyLayout()
   assert(dock.parent==content and dock.props.position=='absolute')
   assert(dock.props.left==0 and dock.props.bottom==0 and dock.props.justifyContent=='flex-start')
   local bar=h.root:FindById('strategyBar')
   local quick=h.root:FindById('skillQuickBar')
   local base=h.root:FindById('baseActionRow')
   local room=width-(touch and 136 or 0)
   assert(bar.props.width<=room and bar.props.width<=980)
   assert(quick.props.width<=bar.props.width and base.props.width<=bar.props.width)
   h:Notify('窗口变化后的操作提示');h:UpdateTicker(5)
   assert(dock.props.left==0 and dock.props.bottom==0)
  end
 end
end
assert(s.world.player.mass==before and h.root:FindById('absorbBtn').props.onClick)
''',
    'stage summary appears once per stage and slides away after five readable seconds': '''
local h,g,s=fixture();local summary=h.stageSummary
summary:Update(.4,1,true,false);assert(summary.value==1)
summary:Update(4.9,1,true,false);assert(summary.target==1)
summary:Update(.2,1,true,false);summary:Update(.4,1,true,false)
assert(not summary.widget:IsVisible() and summary.tab:IsVisible())
summary:Update(10,1,true,false);assert(summary.target==0)
summary:Update(.4,2,true,false);assert(summary.value==1 and summary.seenStage==2)
summary:Update(20,2,false,false);assert(summary.target==1)
summary:Update(20,2,true,true);assert(summary.target==1)
summary:Update(5,2,true,false);summary:Update(.4,2,true,false)
assert(not summary.widget:IsVisible())
callback(h,'statsEdgeTab');summary:Update(.4,2,true,false);assert(summary.value==1)
summary:Reset();assert(not summary.widget:IsVisible() and not summary.tab:IsVisible())
summary:Update(20,3,false,false);assert(summary.seenStage==0)
summary:Update(.4,3,true,false);assert(summary.value==1 and summary.seenStage==3)
''',
    'no minimap, current swarm label or empty dock header remains': '''
local h,g,s=fixture()
assert(not h.root:FindById('tissueNavigation') and not h.root:FindById('swarmStatus'))
local toggle=h.root:FindById('groupsToggle')
assert(toggle.parent==h.root:FindById('baseActionRow'))
''',
    'drawers default closed, animate through midpoint and reverse without a jump': '''
local h,g,s=fixture()
assert(not h.root:FindById('entityDetails'):IsVisible())
assert(not h.root:FindById('groupDrawer'):IsVisible())
callback(h,'statsToggle');callback(h,'statsToggle')
assert(not h.root:FindById('entityDetails'):IsVisible())
callback(h,'statsToggle');local m=h.motions_.stats
assert(m.target==1 and h.root:FindById('entityDetails'):IsVisible())
m:Update(.07);local first=m.value;m:Update(.07);near(m.value,.5)
assert(first>0 and first<.25)
callback(h,'statsToggle');near(m.value,.5)
m:Update(.14);assert(m.value>0 and m.value<.5)
m:Update(.14);assert(not m.widget:IsVisible() and m.widget.props.pointerEvents=='none')
callback(h,'statsToggle');m:Update(.3)
assert(h:CloseDrawers());m:Update(.3);assert(not m.widget:IsVisible())
assert(not h:CloseDrawers())
''',
    'drawer exclusivity, pause-safe animation and reset': '''
local h,g,s=fixture();callback(h,'statsToggle');h.motions_.stats:Update(.3)
s:SetPaused('test',true);callback(h,'groupsToggle');h:Update(.3)
assert(not h.motions_.stats.widget:IsVisible() and h.motions_.groups.value==1)
assert(s.paused and h.motions_.groups.widget:IsVisible())
h:ResetEnding();assert(not h.motions_.groups.widget:IsVisible())
''',
    'groups retain actual control callback while collapsed by default': '''
local h,g,s=fixture();assert(s:Split());h:RefreshStrategyHighlight()
callback(h,'groupsToggle');h.motions_.groups:Update(.3)
local id=s.world.swarms[2].id;callback(h,'selectSwarm_2')
assert(s.world.currentControlledSwarmId==id)
assert(h.root:FindById('absorbBtn').props.onClick and h.root:FindById('quickMenu').props.onClick)
''',
    'skill popup animates from keyboard and cancellation preserves state': '''
local h,g,s=fixture();local C=require('UI.SkillControls');local P=require('UI.SkillPanel')
C.Toggle(h);P.Refresh(h);h.motions_.skills:Update(.14)
near(h.motions_.skills.value,.5);C.Cancel(s);P.Refresh(h)
h.motions_.skills:Update(.28);assert(not h.root:FindById('skillMenuPopup'):IsVisible())
''',
    'defeat keeps result statistics disclosure and reset': '''
local h,g,s=fixture();s.ending='extinct';h:ShowEnding()
local e=h.endingScreen;e:Update(.4);e:Update(.4)
assert(e.phase=='result' and e.result:IsVisible() and not e.player)
assert(not h.root:FindById('hudSafeArea'):IsVisible())
assert(not h.root:FindById('endingFrame'))
callback(h,'endingStatsToggle');e:Update(.14);near(e.motion.value,.5)
callback(h,'endingStatsToggle');e:Update(.28);assert(not e.details:IsVisible())
s.ending=nil;h:ResetEnding();assert(e.phase=='idle' and not e.root:IsVisible())
assert(h.root:FindById('hudSafeArea'):IsVisible())
''',
    'full-screen video lifecycle: skip delay, key capture, audio volume and disposal': '''
local players={}
package.loaded['urhox-libs/Video']={isSupported=true,VideoPlayer=function(props)
 local p=UI.Panel(props);p.playing=false;p.ready=true;p.clock=0
 function p:Play() self.playing=true end
 function p:SetVolume(value) self.volume=value end
 function p:GetCurrentTime() return self.clock end
 function p:Stop() self.stopped=true end
 function p:IsPlaying() return self.playing end
 function p:IsReady() return self.ready end
 players[#players+1]=p;return p
end}
local h,g,s=fixture();h.videoVolume=function() return .32 end
local returns=0;h.onMenu=function() returns=returns+1 end
s.ending='victory';h:ShowEnding();local e=h.endingScreen
local p=e.player;assert(p and p.props.width=='100%' and p.props.height=='100%')
assert(p.props.objectFit=='contain' and p.props.volume==0 and not p.props.loop)
e:Update(2.2);assert(e.phase=='waiting');e:Update(.1)
assert(p.playing and p.volume==.32 and not e.result:IsVisible())
p.clock=.1;e:Update(.1);e:Update(.4);assert(e.phase=='video')
assert(not e.skip:IsVisible() and e:HandleKey(KEY_R))
e:HandleKey(KEY_ESCAPE);assert(not e.finishRequested)
p.props.onTimeUpdate(p,2.1);e:Update(.1)
assert(e.skip:IsVisible());e:HandleKey(KEY_ESCAPE);assert(e.finishRequested)
e:Update(.01);e:Update(.4);e:Update(.4)
assert(e.phase=='complete' and returns==1 and not e.result:IsVisible())
assert(p.stopped and p.destroyed and not e.player)
h:ResetEnding();assert(not e.root:IsVisible())
''',
    'load error, natural end and early reset never retain video widgets': '''
package.loaded['urhox-libs/Video']={isSupported=true,VideoPlayer=function(props)
 local p=UI.Panel(props);function p:Stop() self.stopped=true end
 function p:SetVolume(value) self.volume=value end
 function p:IsReady() return false end;function p:IsPlaying() return false end
 return p
end}
local h,g,s=fixture();local returns=0;h.onMenu=function() returns=returns+1 end
s.ending='victory';h:ShowEnding();local e=h.endingScreen;e:Update(2.2)
local p=e.player;p.props.onLoadError(p,1,'NO_DECODER');e:Update(.1)
assert(e.phase=='error' and not e.result:IsVisible() and p.destroyed)
h:ResetEnding();h:ShowEnding();e:Update(2.2);p=e.player
p.props.onEnded(p);e:Update(.1);e:Update(.4)
assert(p.destroyed and e.phase=='complete' and returns==1)
h:ResetEnding();h:ShowEnding();e:Update(.4);p=e.player
h:ResetEnding();assert(p.destroyed and p.stopped and e.phase=='idle')
''',
    'transient feedback returns to a fixed status ticker with frame time': '''
local h,g,s=fixture();h:Notify('操作失败');assert(h.root:FindById('actionNotice'):IsVisible())
s:SetPaused('test',true);h:Update(3.6)
assert(h.root:FindById('actionNotice'):IsVisible())
assert(h.root:FindById('actionNotice').props.text~='操作失败')
assert(h.root:FindById('statusTicker').props.height==36)
''',
}

if __name__=='__main__':
    failed=[]
    for name,code in CASES.items():
        try:
            lua=runtime();lua.globals().print=lambda *args:None
            lua.execute(SMALL+code)
            print('PASS',name,flush=True)
        except Exception as error:
            failed.append(name);print('FAIL',name,error,flush=True)
    print(f'Compact UI: {len(CASES)-len(failed)}/{len(CASES)}')
    sys.exit(bool(failed))
