"""Production main/audio startup gating; engine playback and WebAudio are boundaries."""
from pathlib import Path
import json
from main_menu_regression import runtime

CASES={
    'slow preload stays silent through settings, credits and long frames':r'''
Start();local Sim=require('Core.SimState');local original=Sim.New
Sim.New=function() for _=1,40 do coroutine.yield() end;return original() end
assert(sounds['audio/menu_theme.wav'],'request the resource while startup is silent')
assert(sources.MusicSource.plays==0)
for _=1,4 do flush(.4) end
click('openSettings');flush(.4)
local slider=UI.root:FindById('volume_music');slider.props.onChange(slider,35)
slider.props.onChangeEnd(slider,35)
key(KEY_ESCAPE);flush(.4);click('openCredits');flush(.4);skipCredits()
for _=1,6 do flush(.4) end
assert(sources.MusicSource.plays==0 and sources.MenuClickSource.plays==0)
finishPreload()
local music=sources.MusicSource
assert(music.plays==1 and music.sound.path=='audio/menu_theme.wav' and music.sound.looped)
for _=1,600 do flush(1/60) end
assert(music.plays==1 and audio.gains[SOUND_MUSIC]==.35)
click('openSettings');flush();key(KEY_ESCAPE);flush()
assert(music.plays==1 and sources.MenuClickSource.plays==2)
Stop();assert(not music.playing)
''',
    'an early Start never plays the menu track between loading and game music':r'''
Start();local music=sources.MusicSource;local original=music.Play;local paths={}
function music:Play(sound,freq,gain)
 paths[#paths+1]=sound.path;original(self,sound,freq,gain)
end
openStory()
assert(#paths==1 and paths[1]=='audio/bgm.mp3')
assert(music.plays==1 and lastSim:CanAct())
key(KEY_ESCAPE);flush();click('pauseMenu');flush()
assert(#paths==2 and paths[2]=='audio/menu_theme.wav')
assert(lastSim.pauseReasons.mainMenu)
Stop()
''',
    'render warmup must complete before the first menu note':r'''
Start()
for _=1,100 do
 flush(.1)
 if UI.root:FindById('gameScene') then break end
end
assert(UI.root:FindById('gameScene'))
for _=1,60 do flush(.1) end
assert(sources.MusicSource.plays==0)
for _=1,2 do uiTick(.016);flush(.016);assert(sources.MusicSource.plays==0) end
uiTick(.016);flush(.016)
assert(sources.MusicSource.plays==1)
Stop()
''',
}

if __name__=='__main__':
    passed=[]
    for name,code in CASES.items():
        lua=runtime();lua.globals().print=lambda *args:None;lua.execute(code)
        passed.append(name);print('PASS:',name)
    out=Path(__file__).resolve().parents[1]/'validation/menu-audio-preload-20261018'
    out.mkdir(parents=True,exist_ok=True)
    (out/'regression.json').write_text(json.dumps({'passed':passed,
        'scope':'Production Lua startup and playback dispatch; WebAudio underruns and device hearing are not simulated'},ensure_ascii=False,indent=2),encoding='utf8')
