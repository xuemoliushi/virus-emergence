"""Real ending/menu/audio modules with explicit video-decoder boundary fixtures.

Verifies control flow and resource lifetime; does not claim native video rendering.
"""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.tmp/test-deps'))
from lua_test_runtime import LuaRuntime
from main_menu_regression import FIXTURE,runtime as menu_runtime

VIDEO=r'''
created={};menuCalls=0;poses={}
package.loaded['urhox-libs/Video']={isSupported=true,VideoPlayer=function(props)
 local p=make('Video',props);p.ready=false;p.playing=false;p.clock=0;p.plays=0;p.volume=props.volume
 function p:IsReady() return self.ready end
 function p:IsPlaying() return self.playing end
 function p:GetCurrentTime() return self.clock end
 function p:GetDuration() return 90 end
 function p:Seek(time) self.clock=time;self.seeks=(self.seeks or 0)+1 end
 function p:Play() self.plays=self.plays+1;self.playing=not self.blocked end
 function p:Stop() self.playing=false;self.stopped=true end
 function p:SetVolume(v) self.volume=v end
 created[#created+1]=p;return p
end}
local area=UI.Panel{id='hudSafeArea'}
hud={root=UI.Panel{children={area}},videoVolume=function() return .42 end,
 onMenu=function() menuCalls=menuCalls+1 end,onRestart=function() end,
 onEndingPose=function(z,covered,progress) poses[#poses+1]={z,covered,progress} end,
 onEndingMix=function(mix) lastMix=mix;if audioUnderTest then audioUnderTest:SetEndingMix(mix) end end}
screen=require('UI.EndingScreen').New(hud);hud.root:AddChild(screen.root)
function tick(seconds)
 for _=1,math.floor(seconds/.02+.5) do
  local p=screen.player
  if p and p.playing and p.advance then p.clock=p.clock+.02 end
  screen:Update(.02)
  if audioUnderTest then audioUnderTest:Update(.02,audioSim) end
  assert(not screen.result:IsVisible(),'victory panel flashed')
 end
end
function readyFilm()
 local p=screen.player;p.ready=true;screen:Update(.02)
 assert(p.plays==1 and screen.phase=='waiting','wait for actual playback clock')
 assert(p.clock==require('Core.Config').EndingTransition.videoOffset and p.volume==0)
 p.advance=true;tick(1.94);assert(screen.phase=='video');return p
end
function victory() screen:Show('victory');tick(.6);assert(screen.phase=='waiting');return screen.player end
function holdExit(seconds)
 heldKeys[KEY_ESCAPE]=true;screen:HandleKey(KEY_ESCAPE);tick(seconds or 1.2)
 heldKeys[KEY_ESCAPE]=nil;screen:Update(.02)
end
'''

CASES={
'preload is silent, microscopic pull-back remains visible until actual decoded motion':r'''
screen:Show('victory');local p=screen.player
assert(#created==1 and p.props.src==require('Core.Config').EndingVideo.victory)
assert(p.props.autoPlay==false and p.volume==0 and p.plays==0)
assert(screen.root.props.backgroundColor==false)
assert(not screen.root:FindById('endingSkip') and not screen.exitArea:IsVisible())
tick(.4);assert(screen.phase=='out' and screen.fade.props.opacity==0)
assert(hud.root:FindById('hudSafeArea').props.opacity<1)
tick(1);assert(poses[#poses][1]<1 and screen.fade.props.opacity==0)
tick(.84);assert(screen.phase=='waiting' and p.plays==0 and not poses[#poses][2])
p=readyFilm();assert(p.volume==.42 and screen.videoHost.props.width=='100%' and p.props.objectFit=='contain')
assert(screen.fade.props.opacity==0 and screen.videoHost.props.opacity==1 and poses[#poses][2])
''',
'normal end and skip return to menu once, never to victory result':r'''
victory();local p=readyFilm()
p.props.onTimeUpdate(p,89.9,90);p.props.onEnded(p)
tick(.5);assert(screen.phase=='complete' and menuCalls==1 and p.destroyed and p.stopped)
tick(2);assert(menuCalls==1)
screen:Show('victory');tick(.6);p=readyFilm()
screen:HandleKey(KEY_ESCAPE);assert(not screen.finishRequested)
tick(.2);assert(screen:HandleKey(KEY_R) and not screen.finishRequested)
holdExit();tick(.5);assert(menuCalls==2 and screen.phase=='complete')
''',
'blocked browser autoplay offers a direct gesture and retains the microscopic view':r'''
local p=victory();p.ready=true;p.blocked=true
tick(2.1);assert(p.plays==1 and screen.phase=='waiting' and screen.play:IsVisible())
assert(screen.videoHost.props.opacity==0 and screen.fade.props.opacity==0)
p.blocked=false;screen.play.props.onClick();assert(p.plays==2)
p.advance=true;tick(1.94);assert(screen.phase=='video' and not screen.play:IsVisible())
''',
'load failure, timeout and unsupported decoder never manufacture victory UI':r'''
local old=victory();old.props.onLoadError(old,2,'ERROR_SOURCE_NOT_FOUND')
tick(.02);assert(screen.phase=='error' and old.destroyed and screen.back:IsVisible())
screen.play.props.onClick();assert(screen.phase=='waiting' and #created==2)
old.props.onEnded(old);assert(not screen.finishRequested,'stale decoder callback must be ignored')
local p=readyFilm();p.props.onEnded(p);tick(.5);assert(menuCalls==1)
victory();tick(20.1);assert(screen.phase=='error');holdExit();tick(.5);assert(menuCalls==2)
package.loaded['urhox-libs/Video'].isSupported=false
screen:Show('victory');tick(.7);assert(screen.phase=='error' and not screen.player)
''',
'reset releases the player and restores the scene; defeat retains its existing result':r'''
local p=victory();screen:Reset();assert(p.destroyed and p.stopped and not screen.root:IsVisible())
assert(hud.root:FindById('hudSafeArea').props.opacity==1 and hud.root:FindById('hudSafeArea'):IsVisible())
p.props.onEnded(p);assert(not screen.finishRequested and poses[#poses][1]==1 and not poses[#poses][2])
local count=#created;screen:Show('extinct')
for _=1,50 do screen:Update(.02) end
assert(screen.phase=='result' and screen.result:IsVisible() and #created==count)
''',
'game score survives slow loading, overlaps movie audio, then stays stopped until menu':r'''
local a=require('Core.GameAudio').New();a:SetMode('game')
audioUnderTest=a;audioSim={ending='victory',world={abilityRunId=1,immuneAlertLevel=0}}
a:BindSim(audioSim)
local s=sources.MusicSource;local start=s.gain
local p=victory();tick(4)
assert(s.playing and s.gain==start and screen.fade.props.opacity==0,'slow decoder must not create dead air or black')
p.ready=true;screen:Update(.02);p.advance=true;tick(.94)
assert(screen.phase=='videoIn' and s.gain>0 and s.gain<start and p.volume>0 and p.volume<.42)
local scoreGain=s.gain/start;local filmGain=p.volume/.42
assert(math.abs(scoreGain^2+filmGain^2-1)<1e-8,'equal power overlap')
tick(1.1)
assert(not s.playing and s.gain==0);local plays,stops=s.plays,s.stops
for _=1,900 do a:Update(.1,audioSim) end
assert(s.plays==plays and s.stops==stops,'completed cinematic must not restart background score')
a:SetMode('menu');a:Update(.1,audioSim);assert(s.playing and s.gain>0)
''',
'a seek timestamp is not playback, and decoder stalls freeze both sides of the blend':r'''
local p=victory();p.ready=true;tick(.1)
assert(screen.phase=='waiting' and p.seeks==1 and p.volume==0 and screen.videoHost.props.opacity==0)
p.advance=true;tick(.7);p.advance=false
local opacity,volume,mix=screen.videoHost.props.opacity,p.volume,lastMix
assert(opacity>0 and opacity<1)
tick(1);assert(screen.phase=='videoIn' and screen.videoHost.props.opacity==opacity and p.volume==volume and lastMix==mix)
p.advance=true;tick(1.5);assert(screen.phase=='video' and screen.videoHost.props.opacity==1)
assert(p.props.backgroundColor[4]==0 and screen.videoHost.props.backgroundColor==false,'no stacked black under translucent film')
graphics.width,graphics.height=2560,1080;screen:Update(.02)
assert(screen.matteA.props.height=='100%' and screen.matteA.props.width~='100%')
graphics.width,graphics.height=390,844;screen:Update(.02)
assert(screen.matteA.props.width=='100%' and screen.matteA.props.height~='100%')
''',
'heartbeat, incidental sounds and ambience leave in separate stages; defeat still fades in .4s':r'''
local a=require('Core.GameAudio').New();a:SetMode('game')
local sim={ending='victory',world={abilityRunId=1,immuneAlertLevel=0}};a:BindSim(sim)
local pulse=a.heartbeat[1];pulse:Play(a.heartbeatSound,0,.5)
a.cardChoice:Play(a.cardChoiceSound,0,.5);a.effects.ambience:SetGain(.2)
a:Update(.75,sim)
assert(not pulse.playing and a.cardChoice.playing and a.music:IsPlaying())
assert(a.effects.ambience:GetGain()>0)
a:Update(.4,sim);assert(not a.cardChoice.playing and a.effects.ambience:GetGain()>0)
a:Update(.7,sim);assert(a.effects.ambience:GetGain()==0 and a.music:IsPlaying())
a:SetMode('menu');a:SetMode('game');sim.ending='extinct';a:BindSim(sim)
a:Update(.42,sim);assert(not a.music:IsPlaying())
''',
'a paused decoder during the dissolve offers resume and an escape route without a volume jump':r'''
local p=victory();p.ready=true;tick(.02);p.advance=true;tick(.6)
p.playing=false;tick(2.1)
assert(screen.phase=='videoIn' and screen.play:IsVisible() and not screen.back:IsVisible())
local volume=p.volume;screen:HandleKey(KEY_SPACE);assert(p.playing)
p.advance=false;holdExit()
assert(screen.phase=='videoOut' and math.abs(screen.exitGain*.42-volume)<1e-8 and p.volume<=volume)
tick(.1);assert(p.volume<volume);tick(.4);assert(menuCalls==1 and p.destroyed)
''',
'real camera framing moves continuously toward nearby infection and reserves its HUD viewport':r'''
package.loaded['Game.GameScene']=nil
local Scene=require('Game.GameScene')
local infected={x=11,y=10,state='PRODUCTIVE'}
local scene=setmetatable({props={},camera={x=10,y=10},cellView={worldView={x=8,y=8,w=4,h=4}},
 sim={world={cells={{x=10.1,y=10,state='HEALTHY'},infected,{x=20,y=20,state='PRODUCTIVE'}}}},
 viewport={x=0,y=90,w=1280,h=490}},Scene)
scene:SetEndingPose(1,false,0);assert(scene.camera.x==10)
scene:SetEndingPose(.86,false,.5);assert(scene.camera.x==10.5 and scene.camera.y==10)
scene:UpdateViewport({x=0,y=0,w=1280,h=720});assert(scene.viewport.y==90 and scene.viewport.h==490)
scene:UpdateCamera(.1);assert(scene.camera.x==10.5,'normal tracking must not overwrite the ending shot')
scene:SetEndingPose(.72,true,1);assert(scene.camera.x==11 and not scene:IsVisible())
assert(infected.x==11 and infected.state=='PRODUCTIVE','framing must not move gameplay objects')
scene:SetEndingPose(1,false);assert(scene.endingFraming==nil and scene:IsVisible())
scene.camera={x=30,y=30};scene:SetEndingPose(.72,false,1)
assert(scene.camera.x==30 and scene.camera.y==30,'no pan to a remote infection')
'''
}

def runtime():
 lua=LuaRuntime(unpack_returned_tuples=True)
 lua.execute('package.path='+repr((ROOT/'scripts/?.lua').as_posix())+"..';'..package.path")
 lua.execute(FIXTURE);lua.execute(VIDEO);return lua

def main():
 results=[]
 for name,code in CASES.items():
  runtime().execute(code);results.append(name);print('PASS:',name)
 lua=menu_runtime()
 lua.execute(r'''
local previousNew=package.loaded['UI.HUD'].New
package.loaded['UI.HUD'].New=function(props) endingMenu=props.onMenu;return previousNew(props) end
Start();openStory();local old=lastSim;local world=old.world
old:FinishRun('victory');endingMenu();flush()
assert(UI.root.props.id=='mainMenu')
assert(UI.root:FindById('storyMode').props.text=='开始','finished run must not offer Continue')
click('storyMode');flush(.1);finishEntry()
assert(lastSim==old and old.world~=world and old.ending==nil and old:CanAct())
Stop()
''')
 results.append('completed run returns to a fresh Start through the real main/menu lifecycle')
 out=ROOT/'validation/ending-handoff-20261019';out.mkdir(parents=True,exist_ok=True)
 (out/'regression.json').write_text(json.dumps({'passed':len(results),'checks':results,'boundary':'mock UI/video decoder; real production ending/menu/audio logic','native_visual_verified':False},ensure_ascii=False,indent=2),encoding='utf-8')
 print(f'{len(results)} ending integration checks passed; native rendering is a separate check.')

if __name__=='__main__':main()
