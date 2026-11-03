"""Verify the actual final encodes, audio, subtitles and decoded transitions."""
from pathlib import Path
import json,subprocess,hashlib,wave,os
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'assets/video/emergence_final90'
FF=Path(os.environ.get('SHADER_FFMPEG','C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe'));FP=FF.with_name('ffprobe.exe')
def ff(args):return subprocess.run([str(FF),'-v','error',*args],capture_output=True,check=True)
report={'revision':5,'duration':90,'fps':24,'expected_frames':2160,'videos':[]}
for name in ['涌现_90秒_无字幕.mp4','涌现_90秒_双语字幕.mp4']:
 p=OUT/name
 probe=json.loads(subprocess.check_output([str(FP),'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(p)]))
 v=next(x for x in probe['streams'] if x['codec_type']=='video');a=next(x for x in probe['streams'] if x['codec_type']=='audio')
 assert (v['width'],v['height'],v['r_frame_rate'],int(v['nb_read_frames']))==(1920,1080,'24/1',2160)
 assert abs(float(v['duration'])-90)<1/24
 assert a['sample_rate']=='48000' and a['channels']==2
 decoded=ff(['-i',str(p),'-f','null','-']);assert not decoded.stderr
 report['videos'].append({'file':name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
  'video':{k:v.get(k) for k in ['codec_name','width','height','r_frame_rate','nb_read_frames','duration']},'audio':{k:a.get(k) for k in ['codec_name','sample_rate','channels','duration']},'full_decode_ok':True})
movie=OUT/'涌现_90秒_双语字幕.mp4'
raw=ff(['-i',str(movie),'-vf','scale=320:180','-pix_fmt','rgb24','-f','rawvideo','pipe:1']).stdout
frames=np.frombuffer(raw,np.uint8).reshape(-1,180,320,3);assert len(frames)==2160
adj=np.array([np.abs(frames[i].astype(np.int16)-frames[i-1].astype(np.int16)).mean() for i in range(1,len(frames))])
times=[6,10,15,19,23,27,30,33,36,41,45,46,49,52,56,59,64,70,76,79,82,89.5]
sheet=Image.new('RGB',(1280,6*205),(24,25,28));draw=ImageDraw.Draw(sheet)
for i,t in enumerate(times):
 x=i%4*320;y=i//4*205;sheet.paste(Image.fromarray(frames[round(t*24)]),(x,y));draw.text((x+8,y+184),f'{t:05.1f} s',fill=(235,230,214))
sheet.save(OUT/'正片画面总览.jpg',quality=94)
for t in [10,19,23,27,30,33,36,45,46,50.5,53,56,58,59.96,60,60.5,61.3,63.5,64.5,65.45,66,68,73,78.5,80,82.5,87.5,89.5]:
 png=ff(['-ss',str(t),'-i',str(movie),'-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1']).stdout
 (OUT/'qa'/f'encoded_{t:.1f}.png').write_bytes(png)
report['boundary_frame_mean_differences']={str(t):float(adj[round(t*24)-1]) for t in [15,19,27.6,30,31.6,39,43,46,59,60,61.3,74,78,79,81.5,87]}
cues=json.loads((OUT/'cues.json').read_text('utf-8'))
assert all(0<=c['start']<c['end']<=90 for c in cues)
assert all(a['end']<=b['start'] for a,b in zip(cues,cues[1:]))
report['subtitles']={'count':len(cues),'last_end':cues[-1]['end'],'nonoverlap':True,'source':'measured narration clips'}
layout=json.loads((OUT/'subtitle_layout.json').read_text('utf-8'))
ass=(OUT/'subtitles.ass').read_text('utf-8-sig')
assert ass.count(',Background,')==len(cues) and ass.count(',Chinese,')==len(cues) and ass.count(',English,')==len(cues)
assert all(q['y']<q['zhY']<q['enY']<q['y']+q['height'] for q in layout)
assert ',0,0,3,10,' not in ass
# Measure the actual encoded rectangle in the empty left padding of one cue.
q=next(c for c in layout if c['start']<=50.5<c['end']);strips=[]
for name in ['涌现_90秒_无字幕.mp4','涌现_90秒_双语字幕.mp4']:
 raw=ff(['-ss','50.5','-i',str(OUT/name),'-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','pipe:1']).stdout
 im=np.frombuffer(raw,np.uint8).reshape(1080,1920,3)
 strips.append(im[q['y']+4:q['y']+q['height']-4,q['x']+5:q['x']+18].astype(float))
# YUV range conversion adds a constant black-level offset, so use the fitted
# transmission slope rather than raw RGB ratios on dark background pixels.
slope,offset=np.polyfit(strips[0].ravel(),strips[1].ravel(),1)
assert .30<slope<.50,(slope,offset)
residual=np.median(abs(strips[1]-(strips[0]*slope+offset)),axis=(1,2))
assert residual.max()<6,residual.tolist()
report['subtitles'].update(backgrounds_per_cue=1,rows=['Chinese','English'],encoded_padding_transmission=float(slope),maximum_row_residual=float(residual.max()),no_stacked_background_seam=True)
qa=json.loads((OUT/'qa_report.json').read_text('utf-8'))
assert qa['revision']==5 and not qa['errors']
assert qa['cloudExit']['textureCardDraws']==0
report['street_exit_cloud_fix']=qa['cloudExit']
report['transitions']=qa['transitions']
report['approved_preview_pixel_comparisons']=qa['approvedPixels']
assert all(x['meanRgbDifference']<.2 for x in qa['approvedPixels'])
assert all(x['velocity']>0 and abs(x['velocityLeft']-x['velocityRight'])<.001 for x in qa['transitions']['ascent'])
assert all(x['streetScale']>=1 and x['cityScale']>=1 for x in qa['transitions']['entry'])
preserved=json.loads((OUT/'revision5_preserved_hashes.json').read_text('utf-8'))
assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in preserved.items())
report['approved_materials_preserved']={'dialogue_subtitles_music_and_336_street_frames_identical':True,'files':len(preserved)}
frozen=json.loads((OUT/'revision5_preserved_hashes.json').read_text('utf-8'))
assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in frozen.items())
report['approved_materials_preserved']['protected_files_unchanged']=len(frozen)
audio_packets=ff(['-i',str(movie),'-map','0:a:0','-c:a','copy','-f','adts','pipe:1']).stdout
clean_audio_packets=ff(['-i',str(OUT/'涌现_90秒_无字幕.mp4'),'-map','0:a:0','-c:a','copy','-f','adts','pipe:1']).stdout
assert audio_packets==clean_audio_packets
report['approved_materials_preserved']['both_delivery_audio_tracks_identical']=True
def pcm(path):
 with wave.open(str(path),'rb') as w:return np.frombuffer(w.readframes(w.getnframes()),'<i2').reshape(-1,2)
audio=ROOT/'assets/audio/emergence_final90'
old_mix=pcm(OUT/'archive_v4/audio/mix.wav');new_mix=pcm(audio/'mix.wav')
ambience=pcm(audio/'ambience.wav')
assert not np.any(ambience[46*48000:60*48000])
assert np.array_equal(old_mix[:int(45.8*48000)],new_mix[:int(45.8*48000)])
assert np.array_equal(old_mix[int(60.2*48000):],new_mix[int(60.2*48000):])
report['street_audio_fix']={'ambience_peak_46_60':0,'master_outside_45_8_60_2_identical':True,'source_report':'assets/audio/emergence_final90/street_audio_repair.json'}
clouds=[x for x in qa['transitions']['samples'] if x['cloud']>0]
assert max(x['altitudeKm'] for x in clouds)<18
assert all(x['cloud']==0 for x in qa['transitions']['samples'] if x['time']>=65.45)
assert all(x['velocity']>.2 for x in qa['transitions']['ascent'] if x['time'] in [64.5,73])
report['foreground_clouds']={'last_film_second':65.45,'maximum_crossing_altitude_km':max(x['altitudeKm'] for x in clouds),'high_altitude_foreground_cloud_draws':0}
# Inspect the active ascent; the approved approach to the final Earth view
# deliberately settles before the final frame is held for the title.
motion=adj[round(61.5*24):round(82*24)]
assert motion.min()>0,'Repeated frozen ascent frame'
report['transitions']['encoded_ascent']={'start':61.5,'end':82,'identical_adjacent_frames':int((motion==0).sum()),'minimum_frame_difference':float(motion.min()),'maximum_frame_difference':float(motion.max()),'settling_and_title_hold_excluded':True}
report['flock_framing']=qa['framing']
for f in qa['framing']:assert abs(f['center'][0]-960)<70 and abs(f['center'][1]-540)<70
street_report=json.loads((ROOT/'assets/video/素材/路口人车_v7_十四秒/通行检查.json').read_text('utf-8'))
assert street_report['seconds']==14 and street_report['walking_entire_shot'] and street_report['toes_on_pavement'] and not street_report['car_pedestrian_overlap']
report['street']={'seconds':14,'playback_rate':1,'route_check_samples':street_report['check_samples'],'report':'assets/video/素材/路口人车_v7_十四秒/通行检查.json'}
# Check encoded space outside the actual planetary limb. The revised continuous
# pullback keeps a larger Earth in frame at 81.5, so a fixed broad bottom-corner
# rectangle would incorrectly count the illuminated planetary surface as a cloud.
corner=[]
yy,xx=np.mgrid[:180,:320];xx=(xx+.5)*6;yy=(yy+.5)*6
corner_roi=((xx<360)|(xx>1560))&((yy<210)|(yy>870))
for pose in qa['transitions']['space']:
 t0=pose['time'];f=frames[round(t0*24)]
 d=pose['distance'];tilt=pose['tilt'];fov=np.tan(np.deg2rad(18))
 sx=(xx/1920*2-1)*(1920/1080);sy=yy/1080*2-1
 rx=sx*fov;ry=np.sin(tilt)-np.cos(tilt)*sy*fov;rz=-np.cos(tilt)-np.sin(tilt)*sy*fov
 rz=rz/np.sqrt(rx*rx+ry*ry+rz*rz);b=d*rz
 # Analytic silhouette of the same perspective sphere, with extra margin for
 # the thin atmospheric shell. This also works while the camera is tilted.
 discriminant=b*b-(d*d-1.08**2)
 outside=(discriminant<0)|(-b+np.sqrt(np.maximum(0,discriminant))<=0)
 mask=corner_roi&outside;assert mask.sum()>3000
 parts=f[mask]
 corner.append(float(parts.mean()));assert parts.mean()<20,(t0,parts.mean())
report['space']={'foreground_clouds_after_earth_reveal':False,'corner_check_seconds':[81.5,89.5],'maximum_encoded_corner_mean':max(corner),'mask':'four corner regions outside a perspective sphere inflated to 1.08 Earth radii; >3000 decoded pixels each sample'}
audio=ROOT/'assets/audio/emergence_final90'
report['stems']={}
for name in ['mix.wav','music.wav','narration_en.wav','ambience.wav']:
 with wave.open(str(audio/name),'rb') as w:
  assert (w.getframerate(),w.getnchannels(),w.getsampwidth(),w.getnframes())==(48000,2,2,4320000)
  data=np.frombuffer(w.readframes(w.getnframes()),'<i2').astype(np.float32)/32768
 report['stems'][name]={'seconds':90,'pcm_peak':float(abs(data).max()),'tail_rms':float(np.sqrt((data[-9600:]**2).mean()))}
 assert abs(data).max()<1
report['mix_measurement']=json.loads((audio/'audio_report.json').read_text('utf-8'))['measured_mix']
report['source_notes']=['Extended street is newly rendered at 1x speed for fourteen seconds from approved rigs, with continuous rounded sidewalk routes.',
 'Accepted city/Earth v2 occupies 60–87s, with a low-altitude cloud crossing ending at 65.45s and nonzero continuous camera velocities at both joins. The perspective Earth uses stable NASA surface/cloud maps; the city illustration is not a surveyed reconstruction.',
 'Existing local synthetic English voice, original score, subtitle files and 336 street frames remain identical. Street sound effects are removed at 46–60s; master PCM outside 45.8–60.2s is unchanged. No rectangular cloud cards draw at 59–61.3s. The last accepted Earth frame is held beneath the 87–90s title.']
(OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'videos':report['videos'],'subtitles':report['subtitles'],'mix_measurement':report['mix_measurement']},ensure_ascii=False,indent=2),flush=True)
