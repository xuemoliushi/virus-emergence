"""Real ChaseMusic/GameAudio with a labeled engine playback boundary fixture.

Includes actual immune lock/loss/control switching; not a native hearing test.
Run: python -B tests/chase_music_regression.py
"""
from pathlib import Path
import hashlib
import json
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.tmp/test-deps'))
from lua_test_runtime import LuaRuntime
from swarm_regression import SETUP
from main_menu_regression import FIXTURE as MENU_FIXTURE

MOCK = r'''
now=0; sources={}; scenes={}; sounds={}; missing={}; calls={}
SOUND_MUSIC='Music';SOUND_EFFECT='Effect'
cache={}
function cache:GetResource(kind,path)
 if missing[path] then return nil end
 if not sounds[path] then
  local sound={path=path,length=assetLengths[path] or 60,frequency=44100}
  function sound:SetLooped(value) self.looped=value end
  function sound:GetLength() return self.length end
  sounds[path]=sound
 end
 return sounds[path]
end
function Scene()
 local scene={};scenes[#scenes+1]=scene
 function scene:CreateChild(name)
  return {CreateComponent=function()
   local source={name=name,plays=0,playing=false,gain=1}
   function source:SetSoundType(value) self.kind=value end
   function source:SetGain(value) self.gain=value end
   function source:GetGain() return self.gain end
   function source:Play(sound,frequency,gain)
    self.sound,self.frequency,self.gain=sound,frequency,gain
    self.plays=self.plays+1;self.playing=true;self.ends=now+sound.length
    self.startedAt,self.seekOffset=now,0
    calls[#calls+1]={name=name,time=now,frequency=frequency,gain=gain}
   end
   function source:IsPlaying() return self.playing and ((self.sound.looped and not self.ignoreLoop) or now<self.ends) end
   function source:GetTimePosition() return (self.seekOffset or 0)+math.max(0,now-(self.startedAt or now)) end
   function source:Seek(value) self.seekOffset=value;self.startedAt=now;self.ends=now+math.max(0,self.sound.length-value) end
   function source:StopImmediate() self.playing=false end
   sources[name]=source;return source
  end}
 end
 function scene:Dispose() self.disposed=true end
 return scene
end
function snapshot()
 local group={id=1,mass=30,isHidden=false}
 local world={currentControlledSwarmId=1,swarms={group},immunes={}}
 function world:SwarmById(id) for _,s in ipairs(self.swarms) do if s.id==id then return s end end end
 return {world=world,started=true,ending=nil,paused=false},group
end
function track(sim,id,state)
 sim.world.immunes={{id=1,targetType='swarm',targetId=id or 1,state=state or 'chase'}}
end
function advance(player,sim,seconds,step)
 step=step or 1/60
 for _=1,math.floor(seconds/step+.5) do now=now+step;player:Update(step,sim) end
end
Audio=require('Core.GameAudio');Chase=require('Core.ChaseMusic');C=require('Core.Config')
function near(a,b) assert(math.abs(a-b)<1e-7,tostring(a)..' != '..tostring(b)) end
'''

CASES = {
    'one-shot engine boundary: music resumes after track end in game and menu': r'''
local sim=snapshot();local player=Audio.New();player:SetMode('game')
advance(player,sim,181)
assert(sources.MusicSource.plays==1,'healthy loop must never be periodically restarted')
player:Destroy();player=Audio.New();player:SetMode('game')
local music=sources.MusicSource;music.ignoreLoop=true
-- Simulate a decoder ending despite the resource loop flag. This does not
-- establish that the native MP3 decoder is responsible for the reported bug.
advance(player,sim,181)
assert(music.plays==4 and music:IsPlaying(),'completed tracks must resume')
assert(sources.ChaseTransition.plays==0 and sources.Heartbeat1.plays==0)
near(music.gain,.5)
player:SetMode('menu');music.ignoreLoop=true
advance(player,sim,121)
assert(music.plays==7 and music:IsPlaying(),'menu also needs continued playback')
player:Destroy();local count=music.plays;advance(player,sim,5)
assert(music.plays==count and not music:IsPlaying(),'destroyed audio must stay stopped')
''',
    'stopped music recovers at current chase gain; failed playback retries are bounded': r'''
local sim=snapshot();local player=Audio.New();player:SetMode('game');track(sim)
advance(player,sim,2)
local music=sources.MusicSource;local intros=sources.ChaseTransition.plays
music:StopImmediate();advance(player,sim,1/60)
assert(music.plays==2 and music:IsPlaying(),'recover stopped source next audio frame')
near(music.gain,.5*.35)
assert(sources.ChaseTransition.plays==intros,'recovery cannot retrigger chase intro')
sim.world.immunes={};advance(player,sim,.6);local mixed=music.gain
music:StopImmediate();advance(player,sim,1/60)
assert(music.plays==3 and music.gain>=mixed and music.gain<.5)
-- Simulate the device refusing every Play. No frame-by-frame restart storm.
local original=music.Play
function music:Play(sound,freq,gain) original(self,sound,freq,gain);self.playing=false end
music:StopImmediate();advance(player,sim,5)
assert(music.plays>=7 and music.plays<=8,'failed starts limited to about one per second')
local count=music.plays
player:Update(0,sim);player:Update(-1,sim);player:Update(0/0,sim);player:Update(math.huge,sim)
assert(music.plays==count,'invalid time cannot retry playback')
''',
    'formal pursuit intro connects directly to one engine loop; ordinary track never restarts': r'''
local sim=snapshot();local player=Audio.New();player:SetMode('game')
advance(player,sim,1);assert(sources.ChaseTransition.plays==0 and sources.Heartbeat1.plays==0)
track(sim);advance(player,sim,.1)
assert(sources.ChaseTransition.plays==1 and sources.Heartbeat1.plays==0)
assert(sources.MusicSource.gain<C.DynamicMusic.normalGain)
advance(player,sim,30)
assert(sources.ChaseTransition.plays==1 and sources.Heartbeat1.plays==1)
assert(sources.Heartbeat1:IsPlaying() and sources.Heartbeat2==nil)
near(sources.MusicSource.gain,.5*.35);assert(sources.MusicSource.plays==1)
assert(sounds[C.DynamicMusic.heartbeatPath].looped and not sounds[C.DynamicMusic.introPath].looped)
local intro,loop=nil,nil
for _,call in ipairs(calls) do
 assert(call.frequency==0,'original sample rate must be explicit')
 if call.name=='ChaseTransition' then intro=call.time end
 if call.name=='Heartbeat1' then loop=call.time end
end
local gap=loop-intro-sounds[C.DynamicMusic.introPath].length
assert(gap>=0 and gap<=2/60,'no additional pause after intro')
near(sources.Heartbeat1.gain,C.DynamicMusic.heartbeatGain)
for _,name in ipairs({'MusicSource','ChaseTransition','Heartbeat1'}) do assert(sources[name].kind==SOUND_MUSIC) end
''',
    'acquisition and warning are silent; exact first formal chase frame starts intro': r'''
local sim=snapshot();local player=Audio.New();player:SetMode('game')
for _,state in ipairs({'patrol','search','locked','warning','investigate','processing'}) do
 track(sim,1,state);advance(player,sim,4)
 assert(sources.ChaseTransition.plays==0 and sources.Heartbeat1.plays==0)
 near(sources.MusicSource.gain,.5)
end
track(sim,1,'chase');advance(player,sim,1/60)
assert(sources.ChaseTransition.plays==1 and sources.Heartbeat1.plays==0)
assert(player.chase.mix>0)
advance(player,sim,1)
local plays=sources.Heartbeat1.plays
for _,state in ipairs({'attack','cooldown','chase'}) do
 track(sim,1,state);advance(player,sim,1)
 assert(sources.ChaseTransition.plays==1 and sources.Heartbeat1.plays==plays)
end
-- A different immune still warning cannot sustain music once actual pursuit ends.
sim.world.immunes={{state='warning',targetType='swarm',targetId=1}}
advance(player,sim,3);assert(player.chase.state=='normal')
''',
    'release is monotone; renewed pursuit strengthens without a second intro': r'''
local sim=snapshot();local player=Audio.New();player:SetMode('game');track(sim)
advance(player,sim,2);sim.world.immunes={}
local previous=sources.MusicSource.gain
for i=1,48 do advance(player,sim,1/60);assert(sources.MusicSource.gain>=previous);previous=sources.MusicSource.gain end
local low=player.chase.mix;assert(low>0 and low<1)
local plays=sources.Heartbeat1.plays
track(sim,1,'chase');advance(player,sim,.2)
assert(sources.Heartbeat1.plays==plays,'reacquisition must preserve loop phase')
assert(player.chase.mix>low and sources.MusicSource.gain<previous and sources.ChaseTransition.plays==1)
sim.world.immunes={};advance(player,sim,3)
near(player.chase.mix,0);near(sources.MusicSource.gain,.5)
assert(player.chase.state=='normal' and not sources.Heartbeat1.playing)
track(sim);advance(player,sim,1/60);assert(sources.ChaseTransition.plays==2)
''',
    'current control, hidden groups, last-seen searches and endings gate the score': r'''
local sim,group=snapshot();sim.world.swarms[2]={id=2,mass=13,isHidden=false}
local player=Audio.New();player:SetMode('game');track(sim,2)
advance(player,sim,1);assert(player.chase.state=='normal')
sim.world.currentControlledSwarmId=2;advance(player,sim,1);assert(player.chase.mix==1)
track(sim,2,'search');assert(not Chase.IsChased(sim));advance(player,sim,.2);assert(player.chase.mix<1)
for _,state in ipairs({'chase','attack','cooldown'}) do track(sim,2,state);assert(Chase.IsChased(sim)) end
for _,state in ipairs({'locked','warning','patrol','processing','search','investigate'}) do track(sim,2,state);assert(not Chase.IsChased(sim)) end
track(sim,2);sim.world.swarms[2].isHidden=true;assert(not Chase.IsChased(sim))
sim.world.swarms[2].isHidden=false;sim.ending='extinct';assert(not Chase.IsChased(sim))
advance(player,sim,4);assert(player.chase.state=='normal')
''',
    'new run, menu and destruction clear every chase source': r'''
local sim=snapshot();local player=Audio.New();player:SetMode('game');track(sim);advance(player,sim,2)
local other=snapshot();player:Update(.1,other)
assert(player.chase.state=='normal' and sources.MusicSource.plays==1)
track(other);advance(player,other,2);player:SetMode('menu')
assert(not sources.Heartbeat1.playing and not sources.ChaseTransition.playing)
assert(sources.MusicSource.sound.path=='audio/menu_theme.wav' and sources.MusicSource.gain==.5)
local count=sources.MusicSource.plays;player:SetMode('menu');assert(sources.MusicSource.plays==count)
player:Destroy();for _,s in pairs(sources) do assert(not s.playing) end;assert(scenes[1].disposed)
player:Update(.1,sim);player:PlayClick()
''',
    'original intro canceled by rapid escape never loops or sticks': r'''
local sim=snapshot();local player=Audio.New();player:SetMode('game');track(sim)
advance(player,sim,1/60);sim.world.immunes={};advance(player,sim,1)
assert(sources.ChaseTransition.plays==1 and player.chase.state=='normal')
assert(sources.Heartbeat1.plays==0)
near(sources.MusicSource.gain,.5)
''',
    'missing assets and invalid deltas are safe; stalls preserve loop phase': r'''
missing[C.DynamicMusic.introPath]=true;missing[C.DynamicMusic.heartbeatPath]=true
local sim=snapshot();local player=Audio.New();player:SetMode('game');track(sim);advance(player,sim,1)
assert(sources.ChaseTransition.plays==0 and sources.Heartbeat1.plays==0)
local mix=player.chase.mix
for _,dt in ipairs({0,-1,math.huge,0/0}) do player:Update(dt,sim);near(player.chase.mix,mix) end
player:Destroy();missing={};sources={};calls={};sounds={}
player=Audio.New();player:SetMode('game');advance(player,sim,2)
local count=sources.Heartbeat1.plays
now=now+10;player:Update(10,sim)
assert(sources.Heartbeat1.plays==count and sources.Heartbeat1:IsPlaying())
sources.Heartbeat1:StopImmediate();advance(player,sim,1/60)
assert(sources.Heartbeat1.plays==count+1,'unexpected stopped loop recovers')
''',
    '30/60/144Hz audio frames preserve fades and continuous engine loop': r'''
local results={}
for _,fps in ipairs({30,60,144}) do
 sources={};calls={};sounds={};now=0
 local sim=snapshot();local player=Audio.New();player:SetMode('game');track(sim)
 advance(player,sim,10,1/fps)
 assert(sources.Heartbeat1.plays==1 and sources.Heartbeat1:IsPlaying())
 local first,second
 for _,call in ipairs(calls) do
  if call.name=='ChaseTransition' then first=call.time end
  if call.name=='Heartbeat1' then second=call.time end
 end
 local gap=second-first-sounds[C.DynamicMusic.introPath].length
 assert(gap>=0 and gap<=2/fps,'transition must hand off within two update frames')
 results[#results+1]={count=sources.Heartbeat1.plays,mix=player.chase.mix}
 sim.world.immunes={};advance(player,sim,3,1/fps)
 assert(player.chase.state=='normal' and sources.ChaseTransition.plays==1)
 near(sources.MusicSource.gain,.5);player:Destroy()
end
for i=2,3 do assert(results[i].count==results[1].count);near(results[i].mix,results[1].mix) end
''',
    'real immune warning is silent; real chase edge and loss drive music read-only': r'''
local w,im=immuneFixture('macrophage')
local sim={started=true,world=w};local player=Audio.New();player:SetMode('game')
Immune.Update(w,cfg.movementStep);assert(im.state=='locked')
advance(player,sim,1)
assert(sources.ChaseTransition.plays==0 and player.chase.mix==0)
Immune.Update(w,cfg.movementStep);assert(im.state=='warning')
for i=1,1000 do
 if im.state~='warning' then break end
 Immune.Update(w,cfg.movementStep)
 local rng,count=w._rng,#w.events
 advance(player,sim,1/60)
 assert(w._rng==rng and #w.events==count,'music is read-only')
 if im.state=='warning' then
  assert(sources.ChaseTransition.plays==0 and player.chase.mix==0)
 else
  assert(im.state=='chase' and sources.ChaseTransition.plays==1)
 end
end
assert(im.state=='chase')
advance(player,sim,1);assert(sources.Heartbeat1.plays==1)
place(w,w.player,13,3.1);Immune.Update(w,cfg.movementStep)
assert(not im.targetId and not Chase.IsChased(sim))
advance(player,sim,3);assert(player.chase.state=='normal')
''',
    'ending fade stops continuous chase loop; next world resets the transport': r'''
local sim=snapshot();local player=Audio.New();player:SetMode('game');track(sim)
advance(player,sim,2);assert(sources.Heartbeat1:IsPlaying())
sim.ending='extinct';advance(player,sim,.5)
assert(player.endingStopped and not sources.Heartbeat1:IsPlaying())
local plays=sources.Heartbeat1.plays;advance(player,sim,2)
assert(sources.Heartbeat1.plays==plays)
local other=snapshot();advance(player,other,.1)
assert(player.chase.state=='normal' and not player.endingActive)
track(other);advance(player,other,1)
assert(sources.Heartbeat1.plays==plays+1)
''',

}


def runtime():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('package.path=' + repr((ROOT / 'scripts/?.lua').as_posix()) + "..';'..package.path")
    lengths = lua.table()
    for name in ['chase_transition.wav', 'chase_heartbeat.wav']:
        with wave.open(str(ROOT / 'assets/audio' / name), 'rb') as f:
            lengths['audio/' + name] = f.getnframes() / f.getframerate()
    lua.globals().assetLengths = lengths
    lua.globals().print = lambda *args: None
    lua.execute(SETUP)
    lua.execute(MOCK)
    return lua


def main():
    results = []
    for name, code in CASES.items():
        try:
            runtime().execute(code)
            results.append(dict(name=name, passed=True))
            print('PASS:', name, flush=True)
        except Exception as error:
            results.append(dict(name=name, passed=False, error=str(error)))
            print('FAIL:', name, str(error), flush=True)
    # Execute actual main/menu routing with the small UI/engine boundary fixture.
    # Frame calls must reach the real adapter exactly once without advancing sim.
    name = 'actual main updates audio; menu/restart clears pursuit; category sliders remain authoritative'
    try:
        lua = runtime()
        lua.execute(MENU_FIXTURE)
        lua.execute(r'''
local widget=getmetatable(make('Panel'))
function widget:RemoveChild(child)
 for i,c in ipairs(self.children) do if c==child then table.remove(self.children,i);child.parent=nil;return end end
end
local original=package.loaded['UI.HUD'].New
package.loaded['UI.HUD'].New=function(props)
 local hud=original(props);function hud:RefreshScale() end;return hud
end
''')
        lua.execute(MOCK)
        lua.execute((ROOT/'scripts/main.lua').read_text(encoding='utf-8-sig'))
        lua.execute(r'''
Start();openStory();now=now+.1;flush(.1)
assert(lastSim and lastSim.started and not lastSim.paused)
track(lastSim,lastSim.world.currentControlledSwarmId,'warning')
for i=1,20 do now=now+.05;flush(.05) end
assert(sources.ChaseTransition.plays==0 and sources.Heartbeat1.plays==0)
track(lastSim,lastSim.world.currentControlledSwarmId,'chase')
local ticks,time=lastSim.tickCount,lastSim.time
for i=1,20 do now=now+.05;flush(.05) end
assert(sources.ChaseTransition.plays==1 and sources.Heartbeat1.plays>0)
assert(lastSim.tickCount==ticks and lastSim.time==time,'audio main hook cannot tick simulation')
local old=lastSim.world;RestartRun();holdEscape(1.25);now=now+.05;flush(.05)
assert(lastSim.world~=old and not sources.Heartbeat1.playing)
assert(sources.MusicSource.gain==.5)
track(lastSim,lastSim.world.currentControlledSwarmId,'chase')
for i=1,20 do now=now+.05;flush(.05) end
key(KEY_ESCAPE);flush(.05);click('pauseMenu');flush(.05)
assert(UI.root.props.id=='mainMenu' and sources.MusicSource.sound.path=='audio/menu_theme.wav')
assert(not sources.Heartbeat1.playing and not sources.ChaseTransition.playing)
click('openSettings');flush(.05)
local before=sources.MusicSource.plays;sources.MusicSource:StopImmediate()
now=now+.05;flush(.05)
assert(sources.MusicSource.plays==before+1 and sources.MusicSource:IsPlaying(),'actual menu main hook must restore stopped music')
local slider=UI.root:FindById('volume_music');slider.props.onChange(slider,25)
near(audio.gains[SOUND_MUSIC],.25);near(audio.gains[SOUND_EFFECT],1)
Stop();assert(scenes[#scenes].disposed)
''')
        results.append(dict(name=name, passed=True))
        print('PASS:', name, flush=True)
    except Exception as error:
        results.append(dict(name=name, passed=False, error=str(error)))
        print('FAIL:', name, str(error), flush=True)
    for entry in json.loads((ROOT / 'assets/audio/chase_audio_sources.json').read_text(encoding='utf-8')):
        imported = (ROOT / 'assets/audio' / entry['file']).read_bytes()
        assert hashlib.sha256(imported).hexdigest() == entry['sha256']
        original = Path('C:/Users/q3382/Desktop') / entry['original']
        if original.is_file():
            assert imported == original.read_bytes()
        else:
            print('INFO: external original unavailable; imported asset verified against recorded SHA-256:', entry['file'])
    paths = ['scripts/Core/ChaseMusic.lua', 'scripts/Core/GameAudio.lua', 'scripts/Core/Config.lua', 'scripts/main.lua',
             'tests/chase_music_regression.py', 'assets/audio/chase_transition.wav', 'assets/audio/chase_heartbeat.wav']
    report = dict(passed=all(r['passed'] for r in results), results=results, source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
                  scope='Real controller, adapter and immune logic. SoundSource/Scene playback API is mocked. Historical 26x32 authored contact fixture. Native timing, hearing/mixing and device output not verified.')
    out = ROOT / 'validation/chase-music'
    out.mkdir(parents=True, exist_ok=True)
    (out/'checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f"{sum(r['passed'] for r in results)}/{len(results)} passed; imported assets match recorded SHA-256.")
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
