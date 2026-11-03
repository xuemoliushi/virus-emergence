"""Tutorial integration with real Lua simulation and menu/UI boundary fixtures.

Assertions cover real contact/latency/release/absorption/split/control changes,
persistent first-entry settings, pause ownership and directional cue geometry.
The UI dependency fixture does not establish native Yoga/GPU/device acceptance.
"""
from pathlib import Path
import argparse
import json
import sys
import time
from main_menu_regression import runtime as menu_runtime

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'validation/tutorial-20261014'

SETUP=r'''
autoSkipTutorial=false
Tutorial=require('Core.Tutorial')
Settings=require('Core.UserSettings')
Sim=require('Core.SimState')
Overlay=require('UI.TutorialOverlay')
function tutorialFixture()
 disk=nil
 local settings=Settings.New()
 local s=Sim.New();assert(s:StartRun('UPPER_AIRWAY',true))
 s.tutorial=Tutorial.New(s,settings);assert(s.tutorial:StartIfNeeded())
 return s,s.tutorial,settings
end
function frame(s,dt,dx,dy)
 s.world:SetMovement(s:CanUseAction('move') and (dx or 0) or 0,s:CanUseAction('move') and (dy or 0) or 0)
 s:Update(dt);s.tutorial:Update(dt)
end
function nextExplanation(s)
 for _=1,8 do s.tutorial:Update(.1) end
 s.tutorial:Continue();s.tutorial:Update(.05)
end
function prepareInfect(s)
 nextExplanation(s);nextExplanation(s);assert(s.tutorial.step=='infect')
end
function realInfection(s)
 local t,w=s.tutorial,s.world
 for _=1,9000 do
  if t.step~='infect' then break end
  local c=assert(t:Target());local p=w.player
  local dx,dy=c.x-p.x,c.y-p.y;local d=math.sqrt(dx*dx+dy*dy)
  frame(s,1/60,dx/math.max(1e-6,d),dy/math.max(1e-6,d))
 end
 assert(t.step=='wait','physical contact failed at '..t.step)
 return assert(t:Cell())
end
function realRelease(s)
 local t=s.tutorial;local c=assert(t:Cell());local start=s.time
 local latency=s.world.config.latentSeconds
 for _=1,math.ceil((latency+2)*60) do
  if t.step=='collect' then break end
  frame(s,1/60,0,0)
 end
 assert(t.step=='collect' and c.releaseCount==1)
 assert(s.time-start>=latency-s.world.config.diseaseStep-1e-6)
 assert(s.time-start<=latency+s.world.config.diseaseStep+1e-6)
 return c,start,s.time
end
function collectReal(s)
 local t=s.tutorial
 assert(s.world.stats.totalAbsorbed==t.absorbedBaseline)
 local target=assert(t:Target());local p=s.world.player
 -- Real movement/E, never inject a virus or advance a lifecycle timer.
 for _=1,600 do
  if t.step~='collect' then break end
  target=t:Target()
  if target then
   local dx,dy=target.x-p.x,target.y-p.y;local d=math.sqrt(dx*dx+dy*dy)
   frame(s,1/60,dx/math.max(1e-6,d),dy/math.max(1e-6,d))
   if s.world:GetAbsorptionCooldown()<1e-9 then s:AbsorbNearby() end
  else frame(s,1/60,0,0) end
 end
 assert(t.step=='split' and s.world.stats.totalAbsorbed>t.absorbedBaseline)
end
function sceneFixture(s)
 local scene=make('scene',{id='gameScene'})
 scene.sim=s;scene.viewport={x=16,y=70,w=graphics.width-32,h=graphics.height-170}
 function scene:CurrentZoom() return 1 end
 scene.cellView={WorldToScreen=function(_,x,y) return graphics.width/2+x*4,graphics.height/2+y*4 end,
  CameraTransform=function() return 4,0,0 end}
 return scene
end
'''

TESTS={
 'completion belongs only to the current run and a fresh tutorial starts again':r'''
local s,t,settings=tutorialFixture()
assert(t.active and t.started)
t:Stop(true);assert(t.completed and not t:StartIfNeeded())
settings:Save();assert(disk.tutorialSeen==nil and disk.skipTutorial==nil)
local nextTutorial=Tutorial.New(s);assert(nextTutorial:StartIfNeeded())
''',
 'old tutorial preference fields are ignored and no longer saved':r'''
disk={skipTutorial=true,tutorialSeen=true,tutorialCompletedVersion=2,music=43}
local settings=Settings.New();settings:Save()
assert(settings.values.music==43 and disk.skipTutorial==nil and disk.tutorialSeen==nil)
local s,t=tutorialFixture();assert(t.active);t:Skip();assert(s:CanAct() and not t:StartIfNeeded())
''',
 'intro freezes simulation and all gameplay actions; menu pause owns its own reason':r'''
local s,t=tutorialFixture();local age=s.time;local mass=s.world.player.mass
assert(s.pauseReasons.tutorial and not s:CanAct())
assert(not s:Split() and not s:SwitchControl() and s:AbsorbNearby()==0)
for _=1,120 do frame(s,1/60,1,1) end
assert(s.time==age and s.world.player.mass==mass)
s:SetPaused('mainMenu',true);local clock=t.stepTime;t:Update(.1);assert(t.stepTime==clock)
t:Stop(false);assert(s.pauseReasons.mainMenu and not s:CanAct())
s:SetPaused('mainMenu',false);assert(s:CanAct() and not s.world.tutorial)
''',
 'real player contact, original 28s latency and real first release':r'''
local s,t=tutorialFixture();prepareInfect(s)
assert(not s:Split() and not s:SwitchControl())
local positions={};for _,im in ipairs(s.world.immunes) do positions[im.id]={im.x,im.y} end
local c=realInfection(s);assert(c.infectionSource=='player' and c.latencyTimer<.51)
local _,start,finish=realRelease(s)
assert(s.world.config.latentSeconds==28 and s.world.config.releaseInterval==18)
assert(s.world.stats.totalAbsorbed==0 and #s.world.releasedViruses>0)
for _,im in ipairs(s.world.immunes) do assert(im.x==positions[im.id][1] and im.y==positions[im.id][2]) end
pathEvidence={infectedAt=start,firstReleaseAt=finish,latentSeconds=finish-start}
''',
 'full physical path: collect, split once, switch once, immune introduction, movement and tasks':r'''
local s,t,settings=tutorialFixture();prepareInfect(s);realInfection(s);realRelease(s);collectReal(s)
assert(s.world.stats.totalSplits==0 and s:Split())
frame(s,1/60,0,0);assert(t.step=='switch' and not s.paused)
local child=assert(t.childId);assert(s.world:LiveSwarmCount()==2)
-- Negative/no-op selection is not credited as successful switching.
assert(not s:SwitchControl(s.world.currentControlledSwarmId));t:Update(.1);assert(t.step=='switch')
assert(s:SwitchControl(child));t:Update(.1);assert(t.step=='switch_done' and not s.paused)
for _=1,29 do t:Update(.1) end
assert(t.step=='switch_done' and t:DeferImmune())
t:Update(.1);assert(t.step=='tcell' and s.paused)
local cell=t:Cell();assert(cell and cell.state~='DEAD')
nextExplanation(s);assert(t.step=='macrophage');nextExplanation(s);assert(t.step=='escape' and s:CanAct())
assert(not t:DeferImmune())
for _=1,240 do if t.step=='task' then break end;frame(s,1/60,1,0) end
assert(t.step=='task' and s:CanAct())
assert(cell.state~='DEAD','tutorial must not require scripted node death')
for _=1,60 do t:Update(.1) end
assert(not t.active and t.completed and not s.world.tutorial and s:CanAct())
assert(s.world.stats.totalSplits==1 and s.world.controlSwitchCount==1)
assert(s.world.stats.totalInfected>=1 and s.world.stats.totalReleased>0 and s.world.stats.totalAbsorbed>0)
''',
 'failed split never progresses; only a real successful split event advances':r'''
local s,t=tutorialFixture();t:Enter('split');s.world.player.mass=11
assert(not s:Split());frame(s,1/60,0,0);assert(t.step=='split')
assert(t:Detail():find('12'));t:Stop(false)
''',
 'task facts count during tutorial; card offer waits until tutorial ends':r'''
local s,t=tutorialFixture();t:Enter('infect')
-- Explicit authority fixture establishes completed facts; it is not natural play evidence.
local first,second=s.world.cells[1],s.world.cells[2]
s.world:_Infect(first,'fixture');s.world:_Infect(second,'fixture')
first.state='PRODUCTIVE';first.releaseCount=1
s:UpdateTasks();assert(s.task.complete and not s.cards.pending)
assert(not s:GrantCardChoice('stage:1'))
t:Stop(true);s:UpdateTasks();assert(s.cards.pending and s.paused)
''',
 'escaping/finishing releases only tutorial restrictions and preserves real entities':r'''
local s,t=tutorialFixture();local world=s.world;local first=world.player;local count=#world.cells
t:Enter('task');s:SetPaused('focus',true);t:Stop(true)
assert(s.world==world and world.player==first and #world.cells==count and s.pauseReasons.focus)
s:SetPaused('focus',false);assert(s:CanAct())
''',
 'settings has no tutorial preference and Esc taps cannot open pause during teaching':r'''
Start();click('openSettings');flush()
assert(not UI.root:FindById('skipTutorial') and not UI.root:FindById('resetTutorial'))
key(KEY_ESCAPE);flush();openStory()
local s=lastSim;assert(s.tutorial.active and s.tutorial.step=='intro')
key(KEY_ESCAPE);flush();assert(not UI.root:FindById('pauseOverlay') and s.tutorial.active)
holdEscape(1.25);assert(s:CanAct());Stop()
''',
 'hold skip resumes the same world and returning from settings does not replay':r'''
Start();openStory();local s=lastSim;local world=s.world
holdEscape(1.25);assert(not s.tutorial.active and s:CanAct())
key(KEY_ESCAPE);flush();click('settingsBack');flush()
assert(s.world==world and not s.tutorial.active and s:CanAct());Stop()
''',
 'mouse continue and key repeats retain teaching while a sustained hold skips':r'''
Start();openStory();local s=lastSim
key(KEY_RETURN,true);flush();assert(s.tutorial.step=='intro')
for _=1,5 do flush(.1) end;click('tutorialContinue');flush();assert(s.tutorial.step=='target')
key(KEY_ESCAPE);flush();assert(s.tutorial.step=='target' and not UI.root:FindById('pauseOverlay'))
holdEscape(.5);assert(s.tutorial.active);holdEscape(1.25);assert(not s.tutorial.active);Stop()
''',
 'collection pointer projects to all four edges and uses words and real target coordinates':r'''
local s,t=tutorialFixture();t:Enter('collect');local scene=sceneFixture(s);local view=Overlay.New(s,scene)
local p=s.world.player
for _,delta in ipairs({{1000,0},{-1000,0},{0,1000},{0,-1000},{1000,1000}}) do
 s.world.releasedViruses={{id=1,x=p.x+delta[1],y=p.y+delta[2],radius=.045,state='DRIFTING'}}
 t.stepTime=1;view:Update();local cue=assert(scene.tutorialCue);local area=scene.viewport
 assert(cue.x>=area.x and cue.x<=area.x+area.w and cue.y>=area.y and cue.y<=area.y+area.h)
 assert(view.cue.props.visible and view.cue.props.text:find('收集病毒'))
 assert(view.cue.props.left>=0 and view.cue.props.left+176<=graphics.width)
end
''',
 'collection marker does not target absorbed/lost/cleared particles; pause freezes animation':r'''
local s,t=tutorialFixture();t:Enter('collect')
s.world.releasedViruses={{id=1,x=1,y=1,state='ABSORBED'},{id=2,x=1,y=1,state='LOST'},{id=3,x=1,y=1,state='CLEARED'}}
assert(t:Target()==nil);assert(t:Detail():find('等待'))
local clock=t.visualTime;s:SetPaused('mainMenu',true);t:Update(.1);assert(t.visualTime==clock)
''',
 'tutorial vectors render through the existing widget frame; dimensions stay finite':r'''
local s,t=tutorialFixture();local scene=sceneFixture(s);local view=Overlay.New(s,scene)
local calls=0
for _,name in ipairs({'nvgSave','nvgRestore','nvgIntersectScissor','nvgBeginPath','nvgRect','nvgFillPaint','nvgFill',
 'nvgCircle','nvgStrokeWidth','nvgStrokeColor','nvgStroke','nvgMoveTo','nvgLineTo','nvgClosePath','nvgRoundedRect'}) do
 _G[name]=function(...) calls=calls+1;for _,v in ipairs({...}) do if type(v)=='number' then assert(v==v and v~=math.huge and v~=-math.huge) end end end
end
function nvgRGBA(...) return {...} end;function nvgRadialGradient(...) return {...} end
for _,size in ipairs({{1920,1080},{844,390},{390,844}}) do
 graphics.width,graphics.height=size[1],size[2];scene.viewport={x=16,y=70,w=size[1]-32,h=size[2]-170}
 view:Update();assert(view.card.props.width<=graphics.width-28)
 view.root.children[2]:Render({})
end
assert(calls>40)
''',
 'restart creates a fresh opening tutorial and clears old world bindings':r'''
Start();openStory();local old=lastSim.tutorial;local oldWorld=lastSim.world
RestartRun();assert(not old.active and not oldWorld.tutorial and lastSim.tutorial.active and lastSim.world~=oldWorld)
holdEscape(1.25);assert(lastSim:CanAct());Stop()
''',
}
TESTS['production v5 map 960 cells completes physical tutorial without lifecycle injection']=r'''
local cfg=require('Core.Config').Gameplay
cfg.mapGenerationVersion=5;cfg.width=120;cfg.height=144;cfg.cellCount=960
'''+TESTS['full physical path: collect, split once, switch once, immune introduction, movement and tasks']
TESTS['invalid start requests keep the active tutorial intact']=r'''
local s,t=tutorialFixture();assert(not s:StartRun('UNKNOWN'))
assert(s.tutorial==t and t.active and s.pauseReasons.tutorial)
'''
TESTS['merge before Tab returns to split instruction instead of blocking forever']=r'''
local s,t=tutorialFixture();t:Enter('split');assert(s:Split());frame(s,1/60,0,0)
assert(t.step=='switch')
-- Boundary fixture places the real pair in contact; merge is the real authority method.
local a,b=s.world.swarms[1],s.world.swarms[2];b.x,b.y=a.x,a.y;a.mergeGrace,b.mergeGrace=0,0
assert(s.world:_Merge(a,b));t:Update(.1);assert(t.step=='split')
'''

TESTS['post-switch delay starts on success, allows observation and ignores continue']=r'''
local s,t=tutorialFixture();t:Enter('split');assert(s:Split());frame(s,1/60,0,0)
-- Waiting before Tab cannot consume the delay, and a no-op does not start it.
for _=1,40 do t:Update(.1) end
assert(not s:SwitchControl(s.world.currentControlledSwarmId));t:Update(.1)
assert(t.step=='switch')
assert(s:SwitchControl(assert(t.childId)));t:Update(.1)
assert(t.step=='switch_done' and t.stepTime==0 and not s.paused and t:DeferImmune())
assert(s:CanUseAction('move') and s:CanUseAction('switch') and t:AllowPassiveCollection())
assert(t:CameraFocus()==nil and t:Target()==nil)
for _=1,29 do t:Continue();t:Update(.1) end
assert(t.step=='switch_done' and s.world.controlSwitchCount==1)
t:Update(.1);assert(t.step=='tcell' and s.paused)
'''
TESTS['post-switch delay freezes for menu and focus, with skip and restart cleanup']=r'''
local s,t,settings=tutorialFixture();t:Enter('switch_done');t:Update(.1)
for _,reason in ipairs({'menu','focus'}) do
 s:SetPaused(reason,true)
 for _=1,50 do t:Update(.1) end
 assert(t.step=='switch_done' and t.stepTime==.1)
 s:SetPaused(reason,false)
end
for _=1,28 do t:Update(.1) end
assert(t.step=='switch_done');t:Update(.1);assert(t.step=='tcell')
t:Enter('switch_done');t:Skip()
assert(not t.active and not s.pauseReasons.tutorial and not t:StartIfNeeded())
local nextTutorial=Tutorial.New(s);assert(nextTutorial:StartIfNeeded() and nextTutorial.step=='intro')
'''

def run(selected=None):
 OUT.mkdir(parents=True,exist_ok=True)
 results=[]
 for name,code in TESTS.items():
  if selected and selected not in name: continue
  logs=[];started=time.perf_counter();lua=menu_runtime()
  lua.globals().test_log=lambda *parts: logs.append(' '.join(map(str,parts)))
  lua.execute('print=test_log');lua.execute(SETUP)
  try:
   lua.execute(code);result={'name':name,'passed':True,'seconds':round(time.perf_counter()-started,3)}
   evidence=lua.globals().pathEvidence
   if evidence: result['physicalPath']={k:v for k,v in evidence.items()}
  except Exception as exc:
   result={'name':name,'passed':False,'error':str(exc),'logs':logs[-12:]}
  results.append(result);print(('PASS ' if result['passed'] else 'FAIL ')+name)
  if not result['passed']: print(result['error'])
 report={'passed':sum(r['passed'] for r in results),'total':len(results),'tests':results,
  'evidenceBoundary':'Real Lua gameplay; UI/engine boundary fixture. Native Yoga/GPU, OS input and mobile hardware unverified.'}
 (OUT/'regression.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(f"{report['passed']}/{report['total']} passed")
 return 0 if report['passed']==report['total'] else 1

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--only');args=parser.parse_args()
 raise SystemExit(run(args.only))
