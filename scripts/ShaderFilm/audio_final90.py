"""Original 90 s score, retained English narrator, measured subtitle timings."""
from pathlib import Path
import ast,wave,json,subprocess,os,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'assets/audio/emergence_final90';VID=ROOT/'assets/video/emergence_final90'
OUT.mkdir(exist_ok=True);VID.mkdir(exist_ok=True)
FF=Path(os.environ.get('SHADER_FFMPEG','C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe'))
SR=48000;DURATION=90;N=SR*DURATION
# Reuse the established waveform/file helpers, without executing the old score.
tree=ast.parse((ROOT/'scripts/ShaderFilm/audio.py').read_text('utf-8'))
exec(compile(ast.Module(body=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in ['read','save','tone']],type_ignores=[]),'audio_helpers','exec'))
organ=np.zeros((N,2),np.float32);pad=organ.copy();motif=organ.copy();bass=organ.copy()
events=[(2,8.5,[38,50,57],.016),(10.3,7.5,[38,50,57,62,65],.030),
 (17,8,[34,46,53,57,60],.022),(25,6.6,[38,50,57,60,65],.026),
 (31.6,11.4,[38,50,57],.005),(43,12,[38,50,57,60],.020),
 (55,10,[41,53,60,65],.027),(65,15,[36,48,55,62,65],.031),
 (81.9,8.1,[29,41,53,57,60,65,69,72],.046)]
for start,dur,notes,amp in events:
 for j,note in enumerate(notes):
  tone(organ,start,dur,note,amp,pan=.3*(-1)**j)
  if note>=50:tone(pad,start,dur,note,.018 if start<80 else .026,'pad',.6*(-1)**j)
 tone(bass,start,dur,notes[0]-12,amp*.60)
for start,end,amp in [(15,31.3,.014),(48,79.5,.018),(82.0,86.2,.025)]:
 for j,tt in enumerate(np.arange(start,end,60/64/2)):
  tone(motif,tt,min(2.2,90-tt),[50,57,60,64,57,62,60,57][j%8],amp,'motif',.35*np.sin(j))
for track in [organ,pad,motif,bass]:
 dry=track.copy()
 for delay,gain in [(.137,.1),(.277,.08),(.421,.07),(.683,.05),(1.01,.04),(1.51,.025)]:
  d=int(delay*SR);track[d:]+=dry[:-d,::-1]*gain
t=np.arange(N)/SR;fade=np.minimum(t/.5,1)*np.minimum((90-t)/2.5,1)
gap=1-.97*np.clip((t-31.5)/.15,0,1)*np.clip((32.65-t)/.45,0,1)
breath=1-.68*np.clip((t-79.5)/.20,0,1)*np.clip((80.7-t)/.35,0,1)
music=((organ+pad+motif)*gap[:,None]*breath[:,None]+bass)*fade[:,None]
save('music.wav',music)
for name,tr in [('organ',organ),('pad',pad),('motif',motif),('bass',bass)]:save(name+'.wav',tr*fade[:,None])
rng=np.random.default_rng(5505)
noise=np.convolve(rng.normal(0,1,N).astype(np.float32),np.ones(64,dtype=np.float32)/64,'same')
wind=.035*np.clip((t-30)/6,0,1)*np.clip((46-t)/3,0,1)
city=.006*np.clip((t-43)/3,0,1)*np.clip((74-t)/5,0,1)
wing=.012*np.maximum(0,np.sin(t*2.5520763271073856*2*np.pi))**4*np.clip((t-4)/4,0,1)*np.clip((15-t)/3,0,1)
amb=np.column_stack([noise*(wind+city+wing),noise*(wind+city+wing)])
for start in np.arange(46.2,59.8,.52):
 a=int(start*SR);tt=np.arange(int(.12*SR))/SR
 hit=(rng.normal(0,1,len(tt))*.004+.018*np.sin(2*np.pi*115*tt))*np.exp(-tt*45)
 amb[a:a+len(tt),:]+=hit[:,None]*np.array([.8,1])
save('ambience.wav',amb*fade[:,None])
lines=[
 (6.8,11.0,'Within this bird, an unseen world was changing.','在这只鸟的体内，一个看不见的世界正在改变。'),
 (11.8,14.5,'A small infection spread.','一场微小的感染扩散开来。'),
 (17.0,19.4,'Each bird follows its neighbours.','每只鸟跟随着附近的同伴。'),
 (19.8,21.2,'Keeping distance.','保持距离。'),
 (21.5,22.9,'Turning together.','一同转向。'),
 (23.2,24.6,'Staying close.','留在群体附近。'),
 (25.0,29.3,'From these small actions, order emerges.','秩序，从这些微小的行动中涌现。'),
 (32.2,35.7,'This bird died of acute pneumonia.','这只鸟死于急性肺炎。'),
 (36.0,38.7,'The flock continued its flight.','鸟群仍在继续飞行。'),
 (46.5,49.3,'Below, another world moves.','在下方，另一个世界也在运行。'),
 (50.0,55.2,'People meet, exchange, cooperate, and compete.','人们相遇、交换、合作与竞争。'),
 (59.5,62.4,'Their lives intertwine,','他们的生活彼此交织，'),
 (64.0,69.0,'shaping a society no one person could create alone.','形成任何一个人都无法独自创造的社会。'),
 (75.7,84.0,'Across generations, these connections grow into cities, cultures, and civilizations.','世代之间，这些联系逐渐形成城市、文化与文明。')]
narr=np.zeros(N,np.float32);cues=[];voice_report=[]
for i,(start,end,en,zh) in enumerate(lines):
 y=read(OUT/f'voice_{i:02}.wav');duration=len(y)/SR;speed=max(1,duration/(end-start))
 if speed>1.35:raise RuntimeError(f'Line {i} requires excessive speed: {speed}')
 if speed>1.005:
  pcm=subprocess.run([str(FF),'-v','error','-i',str(OUT/f'voice_{i:02}.wav'),'-af',f'atempo={speed:.8f}','-ar',str(SR),'-ac','1','-f','s16le','pipe:1'],capture_output=True,check=True).stdout
  with wave.open(str(OUT/f'voice_{i:02}_fit.wav'),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(SR);w.writeframes(pcm)
  y=read(OUT/f'voice_{i:02}_fit.wav')
 assert len(y)/SR<end-start+.08
 y=y[:int((end-start)*SR)];y*=.60/max(abs(y).max(),.01);a=int(start*SR);narr[a:a+len(y)]+=y;actual_end=start+len(y)/SR
 if i==13:
  split=start+len(y)/SR*.50
  cues.extend([dict(start=start,end=split,en='Across generations, these connections grow',zh='世代之间，这些联系不断延伸，'),dict(start=split,end=actual_end,en='into cities, cultures, and civilizations.',zh='形成城市、文化与文明。')])
 else:cues.append(dict(start=start,end=actual_end,en=en,zh=zh))
 voice_report.append(dict(line=i,start=start,end=actual_end,rate=speed))
save('narration_en.wav',narr)
duck=np.ones(N,np.float32)
for c in cues:duck-=.47*np.clip((t-c['start']+.18)/.18,0,1)*np.clip((c['end']+.25-t)/.25,0,1)
mix=music*duck[:,None]+narr[:,None]+amb*fade[:,None]
save('mix_raw.wav',mix*.85/max(.85,abs(mix).max()))
pcm=subprocess.run([str(FF),'-v','error','-i',str(OUT/'mix_raw.wav'),'-af','loudnorm=I=-16:TP=-1.5:LRA=11','-ar',str(SR),'-ac','2','-f','s16le','pipe:1'],capture_output=True,check=True).stdout
with wave.open(str(OUT/'mix.wav'),'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(SR);w.writeframes(pcm[:N*4])
(VID/'cues.json').write_text(json.dumps(cues,ensure_ascii=False,indent=2),encoding='utf-8')
def stamp(x):
 ms=round(x*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
for lang in ['zh_en','zh','en']:
 text='\n\n'.join(f'{i+1}\n{stamp(c["start"])} --> {stamp(c["end"])}\n'+ ('\n'.join([c['zh'],c['en']]) if lang=='zh_en' else c[lang]) for i,c in enumerate(cues))+'\n'
 (VID/f'ending_{lang}.srt').write_text(text,encoding='utf-8')
# Final layout uses one vector background, never ASS's per-line box mode.
subprocess.run([sys.executable,str(ROOT/'scripts/ShaderFilm/subtitle_final90.py')],check=True)
measure=subprocess.run([str(FF),'-hide_banner','-i',str(OUT/'mix.wav'),'-af','loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json','-f','null','-'],capture_output=True,check=True).stderr.decode(errors='replace')
levels=json.JSONDecoder().raw_decode(measure[measure.rfind('{'):])[0]
report=dict(duration=90,frames=N,sample_rate=SR,channels=2,narrator='Microsoft David Desktop, same local synthetic English voice',music='original procedural additive score',voices=voice_report,measured_mix=levels,cues=cues)
(OUT/'audio_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'duration':90,'narration_lines':len(lines),'measured_mix':levels}),flush=True)
from repair_street_audio import repair
repair(ROOT)
