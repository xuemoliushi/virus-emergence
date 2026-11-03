"""Actual tutorial/audio logic, with a deterministic native playback boundary.

Validates WAV identity, cue order, playback cursor pause/resume and real menu entry.
It does not establish native audibility, device mixing or pronunciation acceptance.
"""
from pathlib import Path
import hashlib
import json
import sys
import wave
from main_menu_regression import runtime as menu_runtime

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'validation/tutorial-voice-20261017'
MAPPING=json.loads((ROOT/'assets/audio/tutorial/mapping.json').read_text(encoding='utf-8'))

SETUP=r'''
autoSkipTutorial=false
now=0;voiceCalls={};resourceLoads={}
local get=cache.GetResource
function cache:GetResource(kind,path)
 resourceLoads[path]=(resourceLoads[path] or 0)+1
 local sound=get(self,kind,path)
 if sound then sound.GetLength=function() return lengths[path] or 4 end end
 return sound
end
local create=Scene
function Scene()
 local scene=create();local child=scene.CreateChild
 function scene:CreateChild(name)
  local node=child(self,name);local component=node.CreateComponent
  function node:CreateComponent(kind)
   local source=component(self,kind);local play=source.Play
   function source:Play(sound,frequency,gain)
    play(self,sound,frequency,gain);self.startedAt=now
    if name=='TutorialVoiceSource' then voiceCalls[#voiceCalls+1]={path=sound.path,frequency=frequency,gain=gain} end
   end
   function source:GetTimePosition() return math.min(self.sound:GetLength(),math.max(0,now-(self.startedAt or now))) end
   function source:Seek(seconds) self.startedAt=now-seconds;self.seek=seconds end
   function source:IsPlaying() return self.playing and (self.sound.looped or self:GetTimePosition()<self.sound:GetLength()) end
   return source
  end
  return node
 end
 return scene
end
Audio=require('Core.GameAudio');Cues=require('Core.TutorialVoiceCues')
function near(a,b) assert(math.abs(a-b)<1e-6,tostring(a)..' != '..tostring(b)) end
function fixture(step)
 local a=Audio.New();a:SetMode('game')
 local t={active=true,step=step or 'intro',settings={values={skipTutorial=false}}}
 local world={immunes={},SwarmById=function() return nil end}
 local sim={tutorial=t,pauseReasons={tutorial=true},world=world,started=true}
 a:Update(.01,sim)
 return a,sim,t,a.tutorialVoice
end
function advance(a,sim,seconds)
 for _=1,math.floor(seconds/.02+.5) do now=now+.02;a:Update(.02,sim) end
end
'''

CASES={
    'all fifteen clips are mapped once to the documented lesson and split sentences stay ordered':r'''
local seen={};local total=0
for step,ids in pairs(Cues.steps) do
 for _,id in ipairs(ids) do assert(Cues.clips[id] and not seen[id]);seen[id]=true;total=total+1 end
end
assert(total==15 and Cues.steps.tcell[2]=='tcell_attack')
assert(Cues.steps.escape[1]=='relocate' and Cues.steps.task[2]=='reward' and Cues.steps.task[3]=='explore')
assert(not Cues.steps.switch,'do not invent a Tab recording')
''',
    'target narration is sequential, single-source, original rate and Voice volume category':r'''
local a,s,t,v=fixture('target');local src=sources.TutorialVoiceSource
assert(src.soundType==SOUND_VOICE and v.current=='healthy_cell')
advance(a,s,Cues.clips.healthy_cell.seconds+.1);assert(v.current=='contact_infection')
advance(a,s,Cues.clips.contact_infection.seconds+.2);assert(not v.current)
assert(#voiceCalls==2 and voiceCalls[1].path==Cues.clips.healthy_cell.path and voiceCalls[2].path==Cues.clips.contact_infection.path)
for _,call in ipairs(voiceCalls) do assert(call.frequency==0 and call.gain==1) end
advance(a,s,10);assert(#voiceCalls==2,'completed lesson does not replay each frame')
''',
    'manual and natural lesson changes immediately replace stale narration':r'''
local a,s,t,v=fixture('target');t.step='infect';a:Update(.02,s)
assert(v.current=='try_infection' and #v.queue==0)
t.step='wait';a:Update(.02,s);assert(v.current=='release' and #v.queue==0)
assert(sources.TutorialVoiceSource.seek==Cues.clips.release.start)
for _,call in ipairs(voiceCalls) do assert(call.path~=Cues.clips.contact_infection.path) end
''',
    'main menu pauses at the native cursor, does not play queued lines, resumes from same position':r'''
local a,s,t,v=fixture('target');advance(a,s,1.2)
local src=sources.TutorialVoiceSource;local cursor=src:GetTimePosition()
a:SetMode('menu');s.pauseReasons.mainMenu=true;assert(not src:IsPlaying() and v.suspended)
advance(a,s,30);assert(#voiceCalls==1 and v.current=='healthy_cell')
a:SetMode('game');s.pauseReasons.mainMenu=nil;a:Update(.02,s)
assert(src:IsPlaying() and not v.suspended);near(src.seek,cursor);assert(#voiceCalls==2)
advance(a,s,Cues.clips.healthy_cell.seconds-cursor+.1);assert(v.current=='contact_infection')
''',
    'focus pause freezes speech independently of tutorial explanation pause':r'''
local a,s,t,v=fixture();advance(a,s,.5);assert(v:IsSpeaking())
s.pauseReasons.focus=true;a:Update(.02,s);assert(v.suspended and not v:IsSpeaking())
local cursor=v.position;advance(a,s,20);near(v.position,cursor)
s.pauseReasons.focus=nil;a:Update(.02,s);assert(v:IsSpeaking())
assert(s.pauseReasons.tutorial,'tutorial visual pause continues to own its pause reason')
''',
    'missing recording falls through to next sentence once and leaves tutorial functional':r'''
missingSounds[Cues.clips.healthy_cell.path]=true
local a,s,t,v=fixture('target');assert(v.current=='contact_infection')
advance(a,s,12);assert(not v.current and resourceLoads[Cues.clips.healthy_cell.path]==1)
assert(t.active and t.step=='target' and s.pauseReasons.tutorial)
''',
    'skip, reset, death and new tutorial identity clean old source and queue':r'''
for _,condition in ipairs({'skip','inactive','ending','replacement'}) do
 local a,s,t,v=fixture('target');advance(a,s,.5)
 if condition=='skip' then t.active=false;t.completed=false
 elseif condition=='inactive' then t.active=false
 elseif condition=='ending' then s.ending='extinct'
 else s.tutorial={active=true,step='intro',settings={values={skipTutorial=false}}} end
 a:Update(.02,s)
 if condition=='replacement' then assert(v.current=='intro' and #v.queue==0)
 else assert(not v.current and #v.queue==0 and not sources.TutorialVoiceSource:IsPlaying()) end
 a:Destroy();assert(not sources.TutorialVoiceSource:IsPlaying())
end
''',
    'all final task segments play once and no voice reaches the ending cinematic':r'''
local a,s,t,v=fixture('task');advance(a,s,20)
assert(#voiceCalls==3 and not v.current)
assert(voiceCalls[1].path==Cues.clips.task.path and voiceCalls[2].path==Cues.clips.reward.path and voiceCalls[3].path==Cues.clips.explore.path)
t.active=false;s.ending='victory';advance(a,s,2);assert(not sources.TutorialVoiceSource:IsPlaying())
''',
    'audio update never advances tutorial or physics even during a long narration':r'''
local a,s,t,v=fixture('collect');local frames=0
t.Update=function() frames=frames+1 end
advance(a,s,20);assert(t.step=='collect' and frames==0)
assert(#voiceCalls==2 and Cues.clips.absorb.path==voiceCalls[2].path)
a:Update(0,s);a:Update(-1,s);a:Update(0/0,s);a:Update(math.huge,s);assert(#voiceCalls==2)
''',
    'each run starts narration after entry fade and hold skip clears voice despite old saved flags':r'''
disk=nil;Start();assert(sources.TutorialVoiceSource.plays==0)
click('storyMode');flush(.1);assert(sources.TutorialVoiceSource.plays==0)
finishEntry();flush(.1);assert(lastSim.tutorial.active)
assert(sources.TutorialVoiceSource.sound.path==Cues.clips.intro.path)
for _=1,8 do flush(.1) end
key(KEY_RETURN);flush(.1);flush(.1)
assert(lastSim.tutorial.step=='target' and sources.TutorialVoiceSource.sound.path==Cues.clips.healthy_cell.path)
holdEscape(1.25);assert(not UI.root:FindById('tutorialOverlay'):IsVisible() and not sources.TutorialVoiceSource:IsPlaying())
Stop();assert(not sources.TutorialVoiceSource:IsPlaying())
disk={skipTutorial=true};Start();openStory();flush(.1);assert(lastSim.tutorial.active and sources.TutorialVoiceSource.plays==1)
Stop()
''',
}


def runtime():
    lua=menu_runtime()
    lua.globals().print=lambda *args:None
    lua.globals().lengths=lua.table_from({clip['path']:clip['seconds'] for clip in MAPPING['clips'].values()})
    lua.execute(SETUP)
    return lua


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    assets=[]
    for id,clip in MAPPING['clips'].items():
        path=ROOT/'assets'/clip['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==clip['sha256']
        with wave.open(str(path),'rb') as source:
            assert (source.getframerate(),source.getnchannels(),source.getsampwidth())==(44100,2,2)
            assert abs(source.getnframes()/source.getframerate()-clip['seconds'])<1e-8
        assets.append(id)
    results=[{'name':'15 supplied WAV hashes and PCM durations','passed':len(assets)==15}]
    for name,code in CASES.items():
        try:
            runtime().execute(code)
            result={'name':name,'passed':True}
        except Exception as error:
            result={'name':name,'passed':False,'error':str(error)}
        results.append(result)
        print(('PASS ' if result['passed'] else 'FAIL ')+name)
        if not result['passed']:print(result['error'])
    report={'passed':sum(r['passed'] for r in results),'total':len(results),'tests':results,
            'boundary':'Actual Lua audio/tutorial/menu logic with mocked native playback clock; hearing/device mixing unverified.'}
    (OUT/'regression.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"{report['passed']}/{report['total']} tutorial voice checks passed")
    return 0 if report['passed']==report['total'] else 1


if __name__=='__main__':
    raise SystemExit(run())
