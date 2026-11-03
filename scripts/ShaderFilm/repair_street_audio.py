"""Remove street foley locally, preserving narration, score and all other PCM."""
from pathlib import Path
import json,subprocess,wave,os,hashlib
import numpy as np

def read(path):
 with wave.open(str(path),'rb') as w:
  assert (w.getframerate(),w.getnchannels(),w.getsampwidth())==(48000,2,2)
  return np.frombuffer(w.readframes(w.getnframes()),'<i2').reshape(-1,2).copy()

def save(path,data):
 with wave.open(str(path),'wb') as w:
  w.setnchannels(2);w.setsampwidth(2);w.setframerate(48000)
  w.writeframes(np.asarray(data,dtype='<i2').tobytes())

def repair(root):
 root=Path(root);out=root/'assets/audio/emergence_final90'
 baseline=root/'assets/video/emergence_final90/archive_v4/audio'
 old=read(baseline/'mix.wav');raw=read(baseline/'mix_raw.wav')
 ambience=read(baseline/'ambience.wav')
 # The original premix is below the .85 peak threshold and therefore unscaled.
 # Confirm the known premix using the unchanged music/voice, rather than guessing.
 music=read(out/'music.wav').astype(np.float32)/32767
 voice=read(out/'narration_en.wav').astype(np.float32)/32767
 t=np.arange(len(old))/48000
 cues=json.loads((root/'assets/video/emergence_final90/cues.json').read_text('utf-8'))
 duck=np.ones(len(old),np.float32)
 for c in cues:duck-=.47*np.clip((t-c['start']+.18)/.18,0,1)*np.clip((c['end']+.25-t)/.25,0,1)
 reconstructed=music*duck[:,None]+voice+ambience.astype(np.float32)/32767
 assert np.max(np.abs(reconstructed))<.85
 assert np.max(np.abs(reconstructed-raw.astype(np.float32)/32767))<.00015
 # Silence the scene effects for the full street shot. Short fades are outside
 # the 46–60s shot, and the last original footstep ends before its right fade.
 gate=np.clip((t-45.8)/.2,0,1)*np.clip((60.2-t)/.2,0,1)
 new_raw=np.clip(raw.astype(np.float64)-ambience*gate[:,None],-32768,32767).astype('<i2')
 save(out/'mix_raw.wav',new_raw)
 ff=os.environ.get('SHADER_FFMPEG','C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe')
 result=subprocess.run([ff,'-v','error','-i',str(out/'mix_raw.wav'),'-af','loudnorm=I=-16:TP=-1.5:LRA=11',
  '-ar','48000','-ac','2','-f','s16le','pipe:1'],capture_output=True,check=True)
 candidate=np.frombuffer(result.stdout,'<i2').reshape(-1,2)[:len(old)]
 assert candidate.shape==old.shape
 # Loudness processing sees the whole programme for context; only the edited
 # scene is spliced back. Outside 45.8–60.2s the master is byte-identical.
 final=np.rint(old*(1-gate[:,None])+candidate*gate[:,None]).astype('<i2')
 cleaned_amb=np.rint(ambience*(1-gate[:,None])).astype('<i2')
 save(out/'mix.wav',final);save(out/'ambience.wav',cleaned_amb)
 assert not np.any(cleaned_amb[46*48000:60*48000])
 assert np.array_equal(final[gate==0],old[gate==0])
 report={'revision':5,'street_range':[46,60],'street_ambience_pcm_peak':0,
  'removed':'repeating synthetic footsteps and street noise bed',
  'master_edit_range':[45.8,60.2],'pcm_outside_edit_identical':True,
  'narration_source_unchanged':True,'music_source_unchanged':True,
  'mix_sha256':hashlib.sha256((out/'mix.wav').read_bytes()).hexdigest()}
 (out/'street_audio_repair.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 levels=subprocess.run([ff,'-hide_banner','-i',str(out/'mix.wav'),'-af',
  'loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json','-f','null','-'],capture_output=True,check=True).stderr.decode(errors='replace')
 audio_report=json.loads((out/'audio_report.json').read_text('utf-8'))
 audio_report['measured_mix']=json.JSONDecoder().raw_decode(levels[levels.rfind('{'):])[0]
 audio_report['street_audio_repair']=report
 (out/'audio_report.json').write_text(json.dumps(audio_report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report),flush=True)

if __name__=='__main__':repair(Path(__file__).resolve().parents[2])
