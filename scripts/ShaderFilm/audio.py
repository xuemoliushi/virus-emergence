"""48-second original procedural score, ambience and aligned local English TTS."""
from pathlib import Path
import wave,json,subprocess,os
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'assets/audio/emergence_shader'
VID=ROOT/'assets/video/emergence_shader'
FF=Path(os.environ.get('SHADER_FFMPEG',r'C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe'))
SR=48000;DURATION=48;N=SR*DURATION
def read(p):
    with wave.open(str(p),'rb') as w:
        rate=w.getframerate();channels=w.getnchannels();width=w.getsampwidth();raw=w.readframes(w.getnframes())
    assert width==2
    y=np.frombuffer(raw,'<i2').reshape(-1,channels).mean(1).astype(np.float32)/32768
    active=np.flatnonzero(abs(y)>.001)
    if len(active):y=y[max(0,active[0]-int(rate*.045)):min(len(y),active[-1]+int(rate*.12))]
    return np.interp(np.arange(round(len(y)*SR/rate))*rate/SR,np.arange(len(y)),y).astype(np.float32)
def save(p,x):
    if x.ndim==1:x=np.column_stack([x,x])
    with wave.open(str(OUT/p),'wb') as w:
        w.setnchannels(2);w.setsampwidth(2);w.setframerate(SR)
        w.writeframes((np.clip(x,-.98,.98)*32767).astype('<i2').tobytes())
def tone(track,start,dur,note,amp,kind='organ',pan=0):
    a=int(start*SR);b=min(N,a+int(dur*SR));t=np.arange(b-a,dtype=np.float32)/SR
    f=440*2**((note-69)/12)
    if kind=='organ':
        y=sum(g*np.sin(2*np.pi*f*k*t) for k,g in [(1,1),(2,.32),(3,.18),(4,.075),(6,.022)])
        env=np.minimum(t/.45,1)*np.clip((dur-t)/1.4,0,1)
    elif kind=='pad':
        y=sum(np.sin(2*np.pi*f*(1+d)*t)*.3 for d in [-.003,0,.003])
        env=np.minimum(t/1.4,1)*np.clip((dur-t)/2,0,1)
    else:
        y=np.sin(2*np.pi*f*t)+.16*np.sin(4*np.pi*f*t)
        env=np.minimum(t/.02,1)*np.exp(-t/.8)*np.clip((dur-t)/.2,0,1)
    signal=(y*env*amp).astype(np.float32)
    track[a:b,0]+=signal*np.sqrt((1-pan)/2);track[a:b,1]+=signal*np.sqrt((1+pan)/2)
organ=np.zeros((N,2),np.float32);pad=organ.copy();motif=organ.copy();bass=organ.copy()
for start,dur,notes,amp in [(1,4,[38,50,57],.025),(5,4,[38,50,57,62,65],.038),
 (8,7,[34,46,53,57,60],.033),(17,7,[38,50,57],.009),
 (24,6,[38,50,57,60],.023),(30,7,[41,53,60,65],.033),
 (37,3,[36,48,55,62],.032),(40.6,7.4,[29,41,53,57,60,65,69,72],.047)]:
    for j,note in enumerate(notes):
        tone(organ,start,dur,note,amp,pan=.3*(-1)**j)
        if note>=50:tone(pad,start,dur,note,.019,kind='pad',pan=.6*(-1)**j)
    tone(bass,start,dur,notes[0]-12,amp*.6)
for start,end,amp in [(8,16,.016),(28,39,.02),(41,45,.028)]:
    for j,t in enumerate(np.arange(start,end,60/64/2)):
        tone(motif,t,min(2.2,48-t),[50,57,60,64,57,62,60,57][j%8],amp,'motif',.35*np.sin(j))
for track in [organ,pad,motif,bass]:
    dry=track.copy()
    for delay,gain in [(.137,.1),(.277,.08),(.421,.07),(.683,.05),(1.01,.04),(1.51,.025)]:
        d=int(delay*SR);track[d:]+=dry[:-d,::-1]*gain
t=np.arange(N)/SR;fade=np.minimum(t/.5,1)*np.minimum((48-t)/1.5,1)
gap=1-.96*np.clip((t-16)/.2,0,1)*np.clip((17-t)/.3,0,1)
music=(organ+pad+motif)*gap[:,None]+bass
music*=fade[:,None]
save('music.wav',music)
for name,tr in [('organ',organ),('pad',pad),('motif',motif),('bass',bass)]:save(name+'.wav',tr*fade[:,None])
rng=np.random.default_rng(5505)
noise=np.convolve(rng.normal(0,1,N).astype(np.float32),np.ones(64)/64,'same')
wind=.04*np.clip((t-14)/5,0,1)*np.clip((28-t)/4,0,1)
city=.007*np.clip((t-26)/2,0,1)*np.clip((37-t)/3,0,1)
amb=np.column_stack([noise*(wind+city),noise*(wind+city)])
for start in np.arange(28.2,32.5,.47):
    a=int(start*SR);tt=np.arange(int(.12*SR))/SR
    hit=(rng.normal(0,1,len(tt))*.006+.025*np.sin(2*np.pi*115*tt))*np.exp(-tt*45)
    amb[a:a+len(tt),:]+=hit[:,None]*np.array([.8,1])
save('ambience.wav',amb)
lines=[
 (4.4,8.0,'Within this bird, an unseen world was changing.','在这只鸟的体内，一个看不见的世界正在改变。'),
 (9,11.7,'Each bird follows its neighbours.','每只鸟跟随着附近的同伴。'),
 (12,15.2,'From these small actions, order emerges.','秩序，从这些微小的行动中涌现。'),
 (16.7,20,'This bird died of acute pneumonia.','这只鸟死于急性肺炎。'),
 (20.3,23.5,'The flock continued its flight.','鸟群仍在继续飞行。'),
 (27,30,'Below, another world moves.','在下方，另一个世界也在运行。'),
 (30.2,34.8,'People meet, exchange, cooperate, and compete.','人们相遇、交换、合作与竞争。'),
 (38,45.7,'Across generations, these connections grow into cities, cultures, and civilizations.','世代之间，这些联系逐渐形成城市、文化与文明。')]
narr=np.zeros(N,np.float32);cues=[]
for i,(start,end,en,zh) in enumerate(lines):
    y=read(OUT/f'voice_{i:02}.wav');speed=max(1,len(y)/SR/(end-start))
    if speed>1.01:
        fit=OUT/f'voice_{i:02}_fit.wav'
        pcm=subprocess.run([str(FF),'-v','error','-i',str(OUT/f'voice_{i:02}.wav'),'-af',f'atempo={speed:.6f}','-ar',str(SR),'-ac','1','-f','s16le','pipe:1'],capture_output=True,check=True).stdout
        with wave.open(str(fit),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(SR);w.writeframes(pcm)
        y=read(fit)
    if len(y)>int((end-start)*SR)+SR*.05:raise RuntimeError('Narration does not fit its window')
    y=y[:int((end-start)*SR)];y*=.64/max(abs(y).max(),.01)
    a=int(start*SR);narr[a:a+len(y)]+=y
    actual_end=start+len(y)/SR
    if i==7:
        split=start+len(y)/SR*.52
        cues.extend([{'start':start,'end':split,'en':'Across generations, these connections grow','zh':'世代之间，这些联系不断延伸，'},
         {'start':split,'end':actual_end,'en':'into cities, cultures, and civilizations.','zh':'形成城市、文化与文明。'}])
    else:cues.append({'start':start,'end':actual_end,'en':en,'zh':zh})
save('narration_en.wav',narr)
duck=np.ones(N,np.float32)
for c in cues:duck-=.45*np.clip((t-c['start']+.18)/.18,0,1)*np.clip((c['end']+.25-t)/.25,0,1)
mix=music*duck[:,None]+narr[:,None]+amb
save('mix_raw.wav',mix*.85/max(.85,abs(mix).max()))
pcm=subprocess.run([str(FF),'-v','error','-i',str(OUT/'mix_raw.wav'),'-af','loudnorm=I=-16:TP=-1.5:LRA=11','-ar',str(SR),'-ac','2','-f','s16le','pipe:1'],capture_output=True,check=True).stdout
with wave.open(str(OUT/'mix.wav'),'wb') as output:
    output.setnchannels(2);output.setsampwidth(2);output.setframerate(SR);output.writeframes(pcm)
(VID/'cues.json').write_text(json.dumps(cues,ensure_ascii=False,indent=2),encoding='utf-8')
def stamp(t):
    ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
(VID/'sample_zh_en.srt').write_text('\n\n'.join(f'{i+1}\n{stamp(c["start"])} --> {stamp(c["end"])}\n{c["zh"]}\n{c["en"]}' for i,c in enumerate(cues))+'\n',encoding='utf-8')
(OUT/'audio_report.json').write_text(json.dumps({'duration':48,'sample_rate':SR,'narrator':'Microsoft David Desktop local SAPI TTS; synthetic draft voice','music':'Original numerical organ/additive pads/motif, not sampled orchestra','cues':cues},ensure_ascii=False,indent=2),encoding='utf-8')
print('48-second independent audio stems and subtitle cues generated')
