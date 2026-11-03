"""Real audio scheduler/GameAudio; playback backend is the existing engine boundary."""
from pathlib import Path
import json
import wave
import numpy as np
from chase_music_regression import runtime as audio_runtime

ROOT=Path(__file__).resolve().parents[1]

def runtime():
    lua=audio_runtime()
    for path in (ROOT/'assets/audio/bird_hints').glob('*.wav'):
        with wave.open(str(path),'rb') as sound:
            lua.globals().assetLengths['audio/bird_hints/'+path.name]=sound.getnframes()/sound.getframerate()
    lua.execute(r'''
function birdCalls()
 local result={}
 for _,call in ipairs(calls) do if call.name=='HostBirdHints' then result[#result+1]=call end end
 return result
end
local play=Scene
function Scene()
 local scene=play();local create=scene.CreateChild
 function scene:CreateChild(name)
  local node=create(self,name);local component=node.CreateComponent
  function node:CreateComponent(kind)
   local source=component(self,kind);local original=source.Play
   function source:Play(sound,frequency,gain)
    original(self,sound,frequency,gain);calls[#calls].path=sound.path
   end
   return source
  end
  return node
 end
 return scene
end
''')
    return lua

CASES={
 'sparse random intervals, no immediate repeats, original sample rate and music category':r'''
local sim=snapshot();sim.world._rng=9981;sim.world.abilityRunId=11
local a=Audio.New();a:SetMode('game');math.randomseed(123);local expected=math.random();math.randomseed(123)
advance(a,sim,1800,.1)
local played=birdCalls();assert(#played>=12 and #played<=23)
assert(played[1].time>=40 and played[1].time<=62)
local seen={}
for i,call in ipairs(played) do
 assert(call.frequency==0 and call.gain==0);seen[call.path]=true
 if i>1 then
  local before=played[i-1];assert(call.path~=before.path)
  local gap=call.time-before.time-assetLengths[before.path]
  assert(gap>=80-.2 and gap<=130+.3,tostring(gap))
 end
end
local count=0;for _ in pairs(seen) do count=count+1 end;assert(count==4)
assert(sources.HostBirdHints.kind==SOUND_MUSIC and sources.MusicSource.plays==1)
assert(a.birds.playGain>=.08 and a.birds.playGain<=.12)
assert(sim.world._rng==9981 and math.random()==expected,'presentation RNG leaked')
''',
 'all six stages use the agreed volume and post-call random interval bands':r'''
for stage=1,6 do
 now=0;calls={};local sim=snapshot();sim.evolution={stage=stage}
 local expected=stage<=2 and {.08,.12,80,130} or stage<=4 and {.14,.18,65,110} or {.22,.28,50,90}
 local a=Audio.New();local source=a.birds.source;local play=source.Play
 function source:Play(sound,frequency,gain)
  play(self,sound,frequency,gain);calls[#calls].targetGain=a.birds.playGain
 end
 a:SetMode('game');advance(a,sim,1200,.1)
 local played=birdCalls();assert(#played>=8)
 assert(played[1].time>=40 and played[1].time<=62)
 for i,call in ipairs(played) do
  assert(call.targetGain>=expected[1]-1e-8 and call.targetGain<=expected[2]+1e-8)
  if i>1 then
   local prior=played[i-1];local gap=call.time-prior.time-assetLengths[prior.path]
   assert(gap>=expected[3]-.2 and gap<=expected[4]+.3)
   assert(call.path~=prior.path)
  end
 end
 a:Destroy()
end
''',
 'stage advancement smooths a playing call and never rerolls an existing countdown':r'''
local sim=snapshot();sim.evolution={stage=1};local a=Audio.New();a:SetMode('game');a:BindSim(sim)
a.birds.remaining=0;advance(a,sim,6.4,.1);assert(#birdCalls()==1 and a.birds.waitingForEnd)
local before=a.birds.playGain;local wait=a.birds.remaining
sim.evolution.stage=5;advance(a,sim,.1,.1)
assert(#birdCalls()==1 and a.birds.remaining==wait)
assert(a.birds.playGain>before and a.birds.playGain-before<=.015*.1+1e-8)
-- End this clip, then sample from the stage active at its end.
advance(a,sim,4,.1);assert(not a.birds.waitingForEnd)
assert(a.birds.remaining>=46 and a.birds.remaining<=90)
advance(a,sim,20,.1);near(a.birds.gainMin,.22);near(a.birds.gainMax,.28)
a:SetMode('menu');a:SetMode('game');sim.evolution.stage=1;a:BindSim(sim)
a.birds.remaining=87;a.birds.quietFor=6
advance(a,sim,.1,.1);near(a.birds.remaining,86.9)
sim.evolution.stage=3;advance(a,sim,.1,.1);near(a.birds.remaining,86.8)
sim.evolution.stage=6;advance(a,sim,.1,.1);near(a.birds.remaining,86.7)
assert(#birdCalls()==1,'stage changes must not emit an extra call')
sim.paused=true;advance(a,sim,30,.1);near(a.birds.remaining,86.7)
sim.paused=false;advance(a,sim,5,.1);near(a.birds.remaining,86.7)
''',
 'pause freezes waiting and fades an existing call; tutorial and voice prevent starts':r'''
local sim=snapshot();local a=Audio.New();a:SetMode('game');a:BindSim(sim);a.birds.remaining=0
sim.paused=true;advance(a,sim,100,.1);assert(#birdCalls()==0 and a.birds.remaining==0)
sim.paused=false
a.tutorialVoice.IsSpeaking=function() return true end
advance(a,sim,100,.1);assert(#birdCalls()==0)
a.tutorialVoice.IsSpeaking=function() return false end
local Birds=require('Core.BirdAmbience');sim.tutorial={active=true}
for _=1,100 do a.birds:Update(.1,'game',sim,false) end
assert(#birdCalls()==0);sim.tutorial=nil
advance(a,sim,6.4,.1);assert(#birdCalls()==1 and sources.HostBirdHints:IsPlaying())
local remaining=a.birds.remaining;sim.paused=true;advance(a,sim,.5,.1)
assert(not sources.HostBirdHints:IsPlaying() and a.birds.remaining==remaining)
sim.paused=false;advance(a,sim,3,.1);assert(#birdCalls()==1)
''',
 'chase and release suppress clues; a quiet grace period follows pursuit':r'''
local sim=snapshot();local a=Audio.New();a:SetMode('game');a:BindSim(sim);a.birds.remaining=0
track(sim);advance(a,sim,80,.1);assert(#birdCalls()==0)
sim.world.immunes={};advance(a,sim,.1,.1);assert(#birdCalls()==0)
advance(a,sim,20,.1);assert(#birdCalls()==1 and sources.MusicSource.plays==1)
''',
 'menu loading ending destroy and a new run never retain a pending old call':r'''
local sim=snapshot();local a=Audio.New();a:SetMode('menu');advance(a,sim,300,.1);assert(#birdCalls()==0)
a:SetMode('loading');advance(a,sim,300,.1);assert(#birdCalls()==0)
a:SetMode('game');a:BindSim(sim);a.birds.remaining=0
advance(a,sim,6.4,.1);assert(#birdCalls()==1 and sources.HostBirdHints:IsPlaying())
sim.ending='victory';advance(a,sim,.1,.1)
local captured=false
for _,item in ipairs(a.endingSources) do if item.source==a.birds.source then captured=true end end
assert(captured);advance(a,sim,1.2,.1);assert(not sources.HostBirdHints:IsPlaying())
advance(a,sim,300,.1);assert(#birdCalls()==1)
a:SetMode('menu');local fresh=snapshot();fresh.world.abilityRunId=2;a:SetMode('game')
advance(a,fresh,6,.1);assert(#birdCalls()==1 and a.birds.remaining>20)
a:Destroy();advance(a,fresh,300,.1);assert(#birdCalls()==1 and not sources.HostBirdHints:IsPlaying())
''',
 'missing optional assets retry at bounded intervals and recover without a burst':r'''
for _,path in ipairs(C.BirdHints.clips) do missing[path]=true end
local requests=0;local get=cache.GetResource
function cache:GetResource(kind,path)
 if path:find('bird_hints',1,true) then requests=requests+1 end
 return get(self,kind,path)
end
local sim=snapshot();local a=Audio.New();a:SetMode('game');a:BindSim(sim)
advance(a,sim,200,.1);assert(#birdCalls()==0 and requests<=88)
missing[C.BirdHints.clips[1]]=nil;advance(a,sim,11,.1)
assert(#birdCalls()==1 and birdCalls()[1].path==C.BirdHints.clips[1])
''',
 'preload is silent; disabling and invalid or very long frames cannot produce calls':r'''
local sim=snapshot();local a=Audio.New();a:PrepareEntryMusic(false)
for _,path in ipairs(C.BirdHints.clips) do assert(sounds[path] and not sounds[path].looped) end
assert(#birdCalls()==0);a:SetMode('game');a:BindSim(sim)
local remaining=a.birds.remaining
for _,dt in ipairs({0,-1,0/0,math.huge}) do a.birds:Update(dt,'game',sim,false) end
assert(a.birds.remaining==remaining and #birdCalls()==0)
a.birds:Update(10000,'game',sim,false);assert(#birdCalls()==0)
C.BirdHints.enabled=false;advance(a,sim,1000,.1);assert(#birdCalls()==0)
''',
 'different rendering rates keep the cosmetic variant sequence independent of simulation':r'''
local function sequence(dt)
 now=0;calls={};local sim=snapshot();sim.world.abilityRunId=42
 local a=Audio.New();a:SetMode('game');advance(a,sim,1000,dt)
 local result={};for _,call in ipairs(birdCalls()) do result[#result+1]=call.path end
 a:Destroy();return result
end
local a,b=sequence(1/60),sequence(.1);assert(#a>=8 and #b>=8)
for i=1,8 do assert(a[i]==b[i]) end
''',
}

def assets():
    paths=list((ROOT/'assets/audio/bird_hints').glob('*.wav'))
    assert len(paths)==4
    for path in paths:
        assert Path(str(path)+'.meta').is_file()
        with wave.open(str(path),'rb') as sound:
            assert sound.getnchannels()==1 and sound.getsampwidth()==2 and sound.getframerate()==48000
            duration=sound.getnframes()/sound.getframerate()
            assert 2<=duration<=3.5
            pcm=np.frombuffer(sound.readframes(sound.getnframes()),dtype='<i2')/32768
            assert .1<np.max(np.abs(pcm))<.7
            assert np.sqrt(np.mean(pcm**2))>.05
            assert abs(pcm[0])<.001 and abs(pcm[-1])<.001
    return {'name':'four PCM assets are present, bounded and unclipped','passed':True}

def run():
    results=[assets()]
    print('PASS',results[0]['name'])
    for name,code in CASES.items():
        try:
            runtime().execute(code)
            results.append({'name':name,'passed':True});print('PASS',name)
        except Exception as error:
            results.append({'name':name,'passed':False,'error':str(error)});print('FAIL',name,str(error))
    folder=ROOT/'validation/bird-progression-20261020';folder.mkdir(exist_ok=True,parents=True)
    (folder/'regression.json').write_text(json.dumps({'checks':results,'native_hearing_verified':False},indent=2),encoding='utf-8')
    print(f'Bird hints: {sum(row["passed"] for row in results)}/{len(results)}')
    return all(row['passed'] for row in results)

if __name__=='__main__':
    raise SystemExit(0 if run() else 1)
