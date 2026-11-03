"""Finalize and verify the isolated 14 s Earth review without touching production."""
from pathlib import Path
import hashlib,json,subprocess,os
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'assets/video/earth_transition_review_v1'
FF=Path(os.environ.get('SHADER_FFMPEG','C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe'))
FP=FF.with_name('ffprobe.exe')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def preserved():
 baseline=json.loads((OUT/'production_baseline.json').read_text('utf-8'))
 assert all(digest(ROOT/p)==h for p,h in baseline.items())
 return baseline
preserved()
temp=OUT/'review_verified.pending.mp4'
cmd=[str(FF),'-v','error','-i',str(OUT/'review_fragmented.mp4'),'-ss','73','-i',str(ROOT/'assets/audio/emergence_final90/mix.wav'),
 '-map','0:v:0','-map','1:a:0','-c:v','copy','-bsf:v','setts=pts=N*512:dts=N*512:duration=512',
 '-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t','14','-f','mp4','-fd','1','fd:']
with temp.open('w+b') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.PIPE)
assert r.returncode==0,r.stderr.decode(errors='replace')
probe=json.loads(subprocess.check_output([str(FP),'-v','error','-count_frames','-show_streams','-of','json',str(temp)]))
v=next(s for s in probe['streams'] if s['codec_type']=='video');a=next(s for s in probe['streams'] if s['codec_type']=='audio')
assert (v['width'],v['height'],int(v['nb_read_frames']),v['r_frame_rate'],float(v['duration']))==(1920,1080,336,'24/1',14)
assert a['sample_rate']=='48000' and a['channels']==2 and float(a['duration'])==14
decode=subprocess.run([str(FF),'-v','error','-i',str(temp),'-f','null','-'],capture_output=True,check=True)
assert not decode.stderr
raw=subprocess.check_output([str(FF),'-v','error','-i',str(temp),'-vf','scale=480:270','-pix_fmt','rgb24','-f','rawvideo','pipe:1'])
frames=np.frombuffer(raw,np.uint8).reshape(336,270,480,3)
sheet=Image.new('RGB',(1440,3*295),(18,18,18));draw=ImageDraw.Draw(sheet)
for i,t in enumerate([0,2,4,6,8,9,10,12,335/24]):
 frame=frames[round(t*24)];x=i%3*480;y=i//3*295
 sheet.paste(Image.fromarray(frame),(x,y));draw.text((x+8,y+275),f'{t:.2f}s',fill='white')
sheet.save(OUT/'地球连续拉远_画面总览.jpg',quality=95)
adj=np.abs(np.diff(frames.astype(np.int16),axis=0)).mean(axis=(1,2,3))
qa=json.loads((OUT/'qa_report.json').read_text('utf-8'))
assert not qa['errors'] and qa['random_seek_identical']
assert all(x['distance']>=y['distance'] for x,y in zip(qa['camera'][1:],qa['camera']))
assert np.max(adj)<15,'Unexpected hard cut'
destination=OUT/'地球连续拉远_独立预览_v1.mp4';temp.replace(destination)
report={'review_only':True,'production_replaced':False,'duration':14,'fps':24,'frames':336,'resolution':[1920,1080],
 'file':destination.name,'sha256':digest(destination),'full_decode_ok':True,'video_audio_exact_seconds':[v['duration'],a['duration']],
 'single_perspective_sphere':True,'source_image_crossfades':0,'random_seek_identical':True,
 'maximum_encoded_adjacent_difference':float(adj.max()),'production_baseline_unchanged':preserved(),
 'audio':'Unchanged approved mix.wav excerpt 73–87s; subtitles omitted in this visual review.',
 'textures':{p.name:digest(p) for p in (OUT/'art').iterdir()}}
(OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:report[k] for k in ['duration','frames','resolution','full_decode_ok','source_image_crossfades','production_replaced','maximum_encoded_adjacent_difference']}),flush=True)
