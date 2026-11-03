"""Production tutorial/HUD/audio behavior; native Yoga and physical hearing excluded."""
from pathlib import Path
import json
from tutorial_regression import menu_runtime,SETUP as TUTORIAL_SETUP
from tutorial_voice_regression import runtime as voice_runtime
from bird_ui_regression import runtime as hud_runtime

OUT=Path(__file__).resolve().parents[1]/'validation/tutorial-sync-20261018'

TUTORIAL_CASES={
    'final lesson permits real movement, all actions, auto completion and input pass-through':r'''
local s,t,settings=tutorialFixture();t:Enter('task')
local view=Overlay.New(s,sceneFixture(s));view:Update()
assert(s:CanAct() and not s.pauseReasons.tutorial)
for _,action in ipairs({'move','absorb','split','switch','skill'}) do assert(s:CanUseAction(action)) end
assert(not view.blocker:IsVisible() and not view.continueButton:IsVisible())
assert(view.card.props.pointerEvents=='none' and view.root:IsVisible())
local x,y=s.world.player.x,s.world.player.y
for _=1,20 do frame(s,.05,1,0);view:Update() end
assert((s.world.player.x-x)^2+(s.world.player.y-y)^2>0)
assert(t.active)
t:Continue();t:Update(0);assert(t.active,'final lesson must not require or consume Continue')
for _=1,49 do t:Update(.1) end
view:Update();assert(t.active and view.card.props.opacity>0 and view.card.props.opacity<1)
t:Update(.1);view:Update()
assert(not t.active and t.completed and not view.root:IsVisible())
assert(s:CanAct())
''',
    'final hint timer freezes under settings/focus and the next run starts fresh':r'''
local s,t,settings=tutorialFixture();t:Enter('task');t:Update(.1)
for _,reason in ipairs({'settings','focus','card-choice'}) do
 s:SetPaused(reason,true);for _=1,100 do t:Update(.1) end
 assert(t.stepTime==.1 and t.active)
 s:SetPaused(reason,false)
end
t:Stop(false);assert(not t.completed and not t:StartIfNeeded())
t=Tutorial.New(s);assert(t:StartIfNeeded() and t.step=='intro' and not t.completed)
''',
    'same update presents the new title and starts its recording without an extra frame':r'''
disk=nil;Start();openStory()
for _=1,5 do flush(.1) end
key(KEY_RETURN);flush(.1)
assert(lastSim.tutorial.step=='target')
local title=UI.root:FindById('tutorialCard').children[2]
assert(title.props.text==lastSim.tutorial.lesson.title)
local Cues=require('Core.TutorialVoiceCues')
assert(sources.TutorialVoiceSource.sound.path==Cues.clips.healthy_cell.path)
assert(sources.TutorialVoiceSource:GetTimePosition()==Cues.clips.healthy_cell.start)
Stop()
''',
}

VOICE_CASES={
    'asynchronous preparation waits for real resources and ignores callbacks after disposal':r'''
local a,s,t,v=fixture('intro');local pending={}
cache.GetResourceAsync=function(_,kind,path,callback)
 assert(kind=='Sound');pending[#pending+1]={path=path,callback=callback}
end
v:Preload();assert(#pending==14 and not a:IsEntryAudioReady(.016))
for i=1,#pending-1 do
 local request=pending[i];request.callback(cache:GetResource('Sound',request.path))
 assert(not a:IsEntryAudioReady(.016))
end
local last=pending[#pending];last.callback(cache:GetResource('Sound',last.path))
assert(a:IsEntryAudioReady(.016))
local b,bs,bt,bv=fixture('intro');local index=#pending;bv:Preload()
b:Destroy()
for i=index+1,#pending do pending[i].callback(cache:GetResource('Sound',pending[i].path)) end
assert(next(bv.sounds)==nil and not bv.preload_)
''',
    'unavailable recordings time out to text without blocking startup forever':r'''
local a,s,t,v=fixture('intro')
cache.GetResourceAsync=function() end
v:Preload()
for _=1,149 do assert(not a:IsEntryAudioReady(.1)) end
assert(a:IsEntryAudioReady(.1) or a:IsEntryAudioReady(.1))
t.step='target';a:Update(.02,s)
assert(not v.current and t.active,'unavailable speech must preserve the lesson')
''',
    'all recordings skip measured empty margins and are preloaded only once':r'''
local a,s,t,v=fixture('intro');v:Preload()
for id,cue in pairs(Cues.clips) do
 assert(cue.start>=0 and cue.start<cue.finish and cue.finish<=cue.seconds+.001)
 assert(resourceLoads[cue.path]==1)
end
local src=sources.TutorialVoiceSource
for _,step in ipairs({'target','infect','wait','collect','split','tcell','macrophage','escape','task'}) do
 t.step=step;a:Update(.02,s)
 local first=Cues.steps[step][1]
 assert(v.current==first and src.sound.path==Cues.clips[first].path)
 near(src:GetTimePosition(),Cues.clips[first].start)
 assert(resourceLoads[Cues.clips[first].path]==1)
end
''',
    'trailing silence does not delay the next sentence':r'''
local a,s,t,v=fixture('target');local cue=Cues.clips.healthy_cell
advance(a,s,cue.finish-cue.start+.04)
assert(v.current=='contact_infection')
assert(now<cue.seconds and sources.TutorialVoiceSource.seek==Cues.clips.contact_infection.start)
''',
    'completed final voice continues after prompt expiry and still stops on skip or ending':r'''
local a,s,t,v=fixture('task');advance(a,s,6)
t.active=false;t.completed=true;a:Update(.02,s)
assert(v.current,'auto-hide must not cut a spoken sentence')
advance(a,s,12);assert(#voiceCalls==3 and not v.current)
for _,condition in ipairs({'skip','ending'}) do
 local a,s,t,v=fixture('task');advance(a,s,6);t.active=false;t.completed=true
 if condition=='skip' then t.completed=false else s.ending='victory' end
 a:Update(.02,s);assert(not v.current and #v.queue==0 and not sources.TutorialVoiceSource:IsPlaying())
end
''',
}

HUD_CASES={
    'tutorial and normal play retain identical action sizes, order and wrapping rules':r'''
local h,g,s=fixture()
local Tutorial=require('Core.Tutorial')
local settings={values={skipTutorial=false},MarkTutorialSeen=function() end}
s.tutorial=Tutorial.New(s,settings);local t=s.tutorial;t.active=true;s.world.tutorial=t
local ids={'absorbBtn','splitBtn','switchBtn','menuBtn','groupsToggle'}
local function geometry()
 local parts={}
 for _,id in ipairs(ids) do
  local b=assert(h.root:FindById(id));assert(b:IsVisible())
  for _,key in ipairs({'width','height','flexBasis','flexGrow','flexShrink'}) do
   parts[#parts+1]=id..key..tostring(b.props[key])
  end
 end
 local row=h.root:FindById('baseActionRow');assert(row.props.flexWrap=='wrap')
 for i,id in ipairs(ids) do assert(row.children[i].props.id==id) end
 parts[#parts+1]=tostring(row.props.width)
 return table.concat(parts,';')
end
for _,size in ipairs({{1280,720},{844,390},{390,844}}) do
 local content=h.root:FindById('hudContent');content.rect={x=0,y=0,w=size[1],h=size[2]}
 h.layoutWidth_=0;h:Update(.016);local expected=geometry()
 for _,step in ipairs({'intro','target','infect','wait','collect','split','switch','switch_done','tcell','macrophage','escape','task'}) do
  t:Enter(step);h:Update(.016);assert(geometry()==expected,'layout changed at '..step)
 end
 t:Stop(true);h:Update(.016);assert(geometry()==expected)
 t.active=true;s.world.tutorial=t
end
''',
}

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True);results=[]
    for factory,cases,setup in [(menu_runtime,TUTORIAL_CASES,TUTORIAL_SETUP),
                               (voice_runtime,VOICE_CASES,''),(hud_runtime,HUD_CASES,
        'Config.Gameplay.mapGenerationVersion=1;Config.Gameplay.width=26;Config.Gameplay.height=32;Config.Gameplay.cellCount=72')]:
        for name,code in cases.items():
            lua=factory();lua.globals().print=lambda *args:None
            lua.execute(setup);lua.execute(code)
            results.append(name);print('PASS:',name,flush=True)
    (OUT/'sync-regression.json').write_text(json.dumps({'passed':results,
        'scope':'Production Lua state, audio cursor/dispatch and HUD geometry properties; excludes native Yoga/GPU and device hearing'},ensure_ascii=False,indent=2),encoding='utf8')
