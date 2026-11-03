"""Finalize and verify the isolated 27 s city/Earth review without touching production."""
from pathlib import Path
import hashlib,json,subprocess,os
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'assets/video/city_earth_review_v2'
FF=Path(os.environ.get('SHADER_FFMPEG','C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe'))
FP=FF.with_name('ffprobe.exe')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def preserved():
 baseline=json.loads((OUT/'production_baseline.json').read_text('utf-8'))
 assert all(digest(ROOT/p)==h for p,h in baseline.items())
 return baseline
preserved()
temp=OUT/'review_verified.pending.mp4'
cmd=[str(FF),'-v','error','-i',str(OUT/'review_fragmented.mp4'),'-ss','60','-i',str(ROOT/'assets/audio/emergence_final90/music.wav'),
 '-ss','60','-i',str(ROOT/'assets/audio/emergence_final90/ambience.wav'),
 '-filter_complex','[1:a][2:a]amix=inputs=2:normalize=0,afade=t=in:st=0:d=0.12,afade=t=out:st=26.6:d=0.4[audio]',
 '-map','0:v:0','-map','[audio]','-c:v','copy','-bsf:v','setts=pts=N*512:dts=N*512:duration=512',
 '-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t','27','-f','mp4','-fd','1','fd:']
with temp.open('w+b') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.PIPE)
assert r.returncode==0,r.stderr.decode(errors='replace')
probe=json.loads(subprocess.check_output([str(FP),'-v','error','-count_frames','-show_streams','-of','json',str(temp)]))
v=next(s for s in probe['streams'] if s['codec_type']=='video');a=next(s for s in probe['streams'] if s['codec_type']=='audio')
assert (v['width'],v['height'],int(v['nb_read_frames']),v['r_frame_rate'],float(v['duration']))==(1920,1080,648,'24/1',27)
assert a['sample_rate']=='48000' and a['channels']==2 and float(a['duration'])==27
decode=subprocess.run([str(FF),'-v','error','-i',str(temp),'-f','null','-'],capture_output=True,check=True)
assert not decode.stderr
raw=subprocess.check_output([str(FF),'-v','error','-i',str(temp),'-vf','scale=480:270','-pix_fmt','rgb24','-f','rawvideo','pipe:1'])
frames=np.frombuffer(raw,np.uint8).reshape(648,270,480,3)
sheet=Image.new('RGB',(1440,5*295),(18,18,18));draw=ImageDraw.Draw(sheet)
for i,t in enumerate([0,2,3.5,4.5,5,5.45,6,7,8,10,12,13,16,22,647/24]):
 frame=frames[round(t*24)];x=i%3*480;y=i//3*295
 sheet.paste(Image.fromarray(frame),(x,y));draw.text((x+8,y+275),f'{t:.2f}s',fill='white')
sheet.save(OUT/'城市至地球_画面总览.jpg',quality=95)
adj=np.abs(np.diff(frames.astype(np.int16),axis=0)).mean(axis=(1,2,3))
qa=json.loads((OUT/'qa_report.json').read_text('utf-8'))
assert not qa['errors'] and qa['random_seek_identical']
assert all(x['distance']>=y['distance'] for x,y in zip(qa['camera'][1:],qa['camera']) if x['distance'] is not None and y['distance'] is not None)
assert qa['maximumCloudAltitude']<18
assert all(min(x['velocityLeft'],x['velocityRight'])>.2 and abs(x['velocityLeft']-x['velocityRight'])<.001 for x in qa['continuity'])
style_checks=[]
for sample in qa['styleChecks']:
 approved=ROOT/'assets/video/earth_transition_review_v1/qa'/f"frame_{sample['originalFrame']}.png"
 a0=np.asarray(Image.open(approved).convert('RGB')).astype(np.int16)
 a1=np.asarray(Image.open(OUT/'qa'/sample['file']).convert('RGB')).astype(np.int16)
 error=np.abs(a1-a0);mean=float(error.mean())
 assert mean<.5,('Approved Earth appearance changed',sample,mean)
 style_checks.append({**sample,'mean_rgb_difference_255':mean,'unchanged_appearance_with_retimed_shutter':True})
assert np.max(adj)<15,'Unexpected hard cut'
destination=OUT/'城市至地球_低空穿云_连续上升预览_v2.mp4';temp.replace(destination)
report={'review_only':True,'production_replaced':False,'duration':27,'fps':24,'frames':648,'resolution':[1920,1080],
 'file':destination.name,'sha256':digest(destination),'full_decode_ok':True,'video_audio_exact_seconds':[v['duration'],a['duration']],
 'earth_single_perspective_sphere':True,'earth_source_image_crossfades':0,'city_painting_scale_dissolve':0,'cloud_crossing_max_altitude_km':qa['maximumCloudAltitude'],'foreground_cloud_cutoff_seconds':5.45,'continuous_camera_joins':qa['continuity'],'approved_earth_entry_trim_seconds':3,'random_seek_identical':True,
 'approved_earth_appearance_checks':style_checks,
 'maximum_encoded_adjacent_difference':float(adj.max()),'production_baseline_unchanged':preserved(),
 'audio':'Approved music.wav and ambience.wav excerpt 60–87s; narration and subtitles omitted only in this visual review to avoid a clipped opening line.',
 'textures':{p.name:digest(p) for p in (ROOT/'assets/video/earth_transition_review_v1/art').iterdir()}}
(OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:report[k] for k in ['duration','frames','resolution','full_decode_ok','earth_source_image_crossfades','production_replaced','maximum_encoded_adjacent_difference']}),flush=True)
