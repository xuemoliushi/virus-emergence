"""Original deterministic organ/pad score, ambience and English SAPI narration mix."""
from pathlib import Path
import numpy as np
import wave, json, subprocess

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'assets/audio/emergence_90s'
FF=Path(r'C:\Users\admin\Downloads\vocaloid-style-mv-pipeline\vendor\ffmpeg\ffmpeg.exe')
SR=48000; N=SR*90
def read(path):
    with wave.open(str(path),'rb') as w:
        raw=w.readframes(w.getnframes());c=w.getnchannels();s=w.getframerate();width=w.getsampwidth()
    assert width==2
    data=np.frombuffer(raw,dtype='<i2').astype(np.float32)/32768
    data=data.reshape(-1,c).mean(axis=1)
    return np.interp(np.arange(round(len(data)*SR/s))*s/SR,np.arange(len(data)),data).astype(np.float32)
def save(name,data):
    if data.ndim==1: data=np.column_stack([data,data])
    data=np.clip(data,-.98,.98)
    with wave.open(str(OUT/name),'wb') as w:
        w.setnchannels(data.shape[1]);w.setsampwidth(2);w.setframerate(SR)
        w.writeframes((data*32767).astype('<i2').tobytes())
def note(track,start,duration,midi,amp,kind='organ',pan=0):
    start=max(start,0);a=int(start*SR);b=min(N,a+int(duration*SR))
    if b<=a:return
    tt=np.arange(b-a,dtype=np.float32)/SR;f=440*2**((midi-69)/12)
    if kind=='organ':
        signal=sum(g*np.sin(2*np.pi*f*k*tt) for k,g in [(1,1),(2,.31),(3,.20),(4,.08),(6,.025)])
        attack=np.minimum(tt/.32,1);release=np.minimum((duration-tt)/1.1,1)
    elif kind=='pad':
        signal=np.zeros(len(tt),np.float32)
        for det in [-.004,0,.004]:
            signal+=np.sin(2*np.pi*f*(1+det)*tt)*.30+np.sin(4*np.pi*f*(1+det)*tt)*.035
        attack=np.minimum(tt/1.6,1);release=np.minimum((duration-tt)/2.4,1)
    else:
        signal=np.sin(2*np.pi*f*tt)+.13*np.sin(4*np.pi*f*tt)
        attack=np.minimum(tt/.024,1);release=np.exp(-tt/1.05)*np.minimum((duration-tt)/.25,1)
    env=np.clip(attack*release,0,1);signal=(signal*env*amp).astype(np.float32)
    track[a:b,0]+=signal*np.sqrt((1-pan)/2);track[a:b,1]+=signal*np.sqrt((1+pan)/2)
def reverb(x):
    original=x.copy()
    for delay,gain in [(0.137,.10),(.277,.09),(.421,.08),(.683,.065),(1.01,.05),(1.51,.04),(2.1,.025)]:
        d=int(delay*SR);x[d:]+=original[:-d,::-1]*gain
    return x

organ=np.zeros((N,2),np.float32);pad=organ.copy();motif=organ.copy();bass=organ.copy()
chords=[(2,12,[38,50,57,60,64],.027),(13.3,6,[38,50,57,62,65,69],.044),
        (18,9,[34,46,53,57,60],.038),(27,9,[36,48,55,58,62],.044),
        (37,16,[38,50,57],.010),(53,7,[38,50,57,60],.023),
        (59,9,[34,46,53,57,60],.034),(68,8,[41,53,60,65,69],.039),
        (76,4,[36,48,55,60,62],.040),(81.3,8.7,[29,41,53,57,60,65,69,72,77],.047)]
for start,dur,notes,amp in chords:
    for j,n in enumerate(notes):
        note(organ,start,dur,n,amp,'organ',(-.25 if j%2 else .25))
        if n>=50:note(pad,start,dur,n,.016 if start<59 else .028,'pad',(-.65 if j%2 else .65))
    note(bass,start,dur,notes[0]-12,amp*.9,'organ',0)
beat=60/64
for start,end,amp,trans in [(18,36,.018,0),(59,79.5,.024,0),(81.3,85.5,.03,12)]:
    for j,tt in enumerate(np.arange(start,end,beat/2)):
        note(motif,tt,min(2.4,90-tt),[50,57,60,64,57,62,60,57][j%8]+trans,amp,'motif',.4*np.sin(j))
for track in [organ,pad,motif,bass]:reverb(track)
time=np.arange(N)/SR
fade=np.minimum(time/.3,1)*np.minimum((90-time)/1.3,1)
upper=1-.94*np.clip((time-35.85)/.22,0,1)*np.clip((37.4-time)/.5,0,1)
for track in [organ,pad,motif]:track*=upper[:,None]
music=(organ+pad+motif+bass)*fade[:,None]

rng=np.random.default_rng(1987);noise=rng.normal(0,1,N).astype(np.float32)
# Smoothed air instead of white noise hiss; independently seeded and timed.
noise=np.convolve(noise,np.ones(48)/48,mode='same').astype(np.float32)
wind_env=np.clip((time-30)/9,0,1)*np.clip((59-time)/6,0,1)*.021
city_env=np.clip((time-53)/7,0,1)*np.clip((77-time)/9,0,1)*.009
amb=noise*(wind_env+city_env)
amb+=.003*np.sin(2*np.pi*53*time)*city_env/.009
save('ambience.wav',amb*fade)

windows=[(9.5,16.5),(20,23),(23,29),(29,33.5),(36.5,41),(41.5,45),(56,59),(60,65),(66,75),(77,85.5)]
narr=np.zeros(N,np.float32);report=[]
for i,(start,end) in enumerate(windows):
    path=OUT/f'narration_{i:02}.wav';data=read(path)
    # Trim only trailing digital silence; preserve natural internal pauses.
    active=np.flatnonzero(np.abs(data)>.0008)
    if len(active):data=data[:min(len(data),active[-1]+int(.09*SR))]
    speed=max(1,len(data)/SR/(end-start))
    if speed>1.015:
        dst=OUT/f'narration_{i:02}_fit.wav'
        subprocess.run([str(FF),'-y','-v','error','-i',str(path),'-af',f'atempo={min(speed,1.3):.6f}',
                        '-ar',str(SR),'-ac','1',str(dst)],check=True)
        data=read(dst)
    data=data[:int((end-start)*SR)]
    data*=min(2.6,.68/max(np.max(np.abs(data)),.01))
    narr[int(start*SR):int(start*SR)+len(data)]+=data
    report.append({'line':i,'start':start,'end':start+len(data)/SR,'speed_adjustment':speed})
save('narration_en.wav',narr)
duck=np.ones(N,np.float32)
for r in report:
    duck-=.38*np.clip((time-r['start']+.2)/.2,0,1)*np.clip((r['end']+.3-time)/.3,0,1)
music*=.72/max(np.max(np.abs(music)),.72)
save('music.wav',music)
for name,track in [('organ.wav',organ),('strings_pad.wav',pad),('motif.wav',motif),('bass.wav',bass)]:save(name,track*fade[:,None])
mixed=music*duck[:,None]+narr[:,None]+amb[:,None]
gain=.87/max(.87,np.max(np.abs(mixed)));mixed*=gain
save('mix_unmeasured.wav',mixed)
# Measured loudness normalization with true-peak limiting is encoded separately.
with open(OUT/'mix.wav','wb') as dst, open(OUT/'loudnorm_pass.log','w',encoding='utf-8') as log:
    proc=subprocess.Popen([str(FF),'-y','-v','warning','-i',str(OUT/'mix_unmeasured.wav'),'-af',
      'loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json','-ar','48000','-ac','2','-f','wav','pipe:1'],
      stdout=dst,stderr=log)
    if proc.wait()!=0: raise RuntimeError('FFmpeg loudnorm failed; see loudnorm_pass.log')
(OUT/'audio_report.json').write_text(json.dumps({'sample_rate':SR,'samples_per_channel':N,
 'voice':'Microsoft David Desktop, SAPI TTS, pitch -3, rate -1; synthetic documentary draft',
 'music':'Original procedural pipe-organ/pad/motif score; no sampled orchestra',
 'narration':report,'peak_before_loudnorm':float(np.max(np.abs(mixed)))},indent=2),encoding='utf-8')
print('Audio written:',OUT)
