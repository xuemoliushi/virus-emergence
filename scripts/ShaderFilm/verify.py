"""Verify the delivered movie and extract an actual encoded-frame contact sheet."""
from pathlib import Path
import json, subprocess, os, wave
import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'assets/video/emergence_shader'
FF=Path(os.environ.get('SHADER_FFMPEG',r'C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe'))
PROBE=FF.with_name('ffprobe.exe' if os.name=='nt' else 'ffprobe')
MOVIE=OUT/'sample_bilingual.mp4'
def call(args):
    return subprocess.run([str(FF),'-v','error',*args],capture_output=True,check=True)

probe=json.loads(subprocess.run([str(PROBE),'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(MOVIE)],capture_output=True,check=True).stdout)
video=next(s for s in probe['streams'] if s['codec_type']=='video')
audio=next(s for s in probe['streams'] if s['codec_type']=='audio')
assert (video['width'],video['height'],video['r_frame_rate'],int(video['nb_read_frames']))==(1920,1080,'24/1',1152)
# Fragmented MP4 can retain one AAC encoder-delay packet (21.33 ms).
# Validate exact picture count separately and allow less than one video frame.
assert abs(float(video['duration'])-48)<1/24
assert int(audio['sample_rate'])==48000 and audio['channels']==2
decode=call(['-i',str(MOVIE),'-f','null','-'])
assert not decode.stderr, decode.stderr.decode(errors='replace')
with wave.open(str(ROOT/'assets/audio/emergence_shader/mix.wav'),'rb') as w:
    assert (w.getframerate(),w.getnchannels(),w.getsampwidth(),w.getnframes())==(48000,2,2,2304000)
    samples=np.frombuffer(w.readframes(w.getnframes()),'<i2').astype(np.float32)/32768
peak=float(np.max(np.abs(samples)))
assert peak<1

# Decode the whole video at reduced resolution to check actual frame motion,
# including the independent render workers' join and cloud-hidden edits.
raw=call(['-i',str(MOVIE),'-vf','scale=320:180','-pix_fmt','rgb24','-f','rawvideo','pipe:1']).stdout
frames=np.frombuffer(raw,np.uint8).reshape(-1,180,320,3)
adj=np.abs(frames[1:].astype(np.float32)-frames[:-1]).mean(axis=(1,2,3))
boundaries={str(t):float(adj[round(t*24)-1]) for t in [16,16.5,22,24,27,33,34.75,37.55,39.8,44.3,46]}
times=[4.5,6,10,15,16.6,20,23,27,30,33.8,36,38.5,40,43,45,47.5]
sheet=Image.new('RGB',(1280,4*205),(24,25,28));d=ImageDraw.Draw(sheet)
for i,t in enumerate(times):
    x=(i%4)*320;y=(i//4)*205
    sheet.paste(Image.fromarray(frames[round(t*24)]),(x,y))
    d.text((x+8,y+184),f'{t:05.1f} s',fill=(235,230,214))
sheet.save(OUT/'qa/encoded_contact_sheet.jpg',quality=94)

# A close sampling of the actual exported near-bird motion, not source images.
wingtimes=[4.5+j/12 for j in range(6)]
strip=Image.new('RGB',(3*480,2*295),(24,25,28));d=ImageDraw.Draw(strip)
for i,t in enumerate(wingtimes):
    data=call(['-ss',str(t),'-i',str(MOVIE),'-frames:v','1','-vf','scale=480:270','-f','rawvideo','-pix_fmt','rgb24','pipe:1']).stdout
    strip.paste(Image.frombytes('RGB',(480,270),data),((i%3)*480,(i//3)*295))
    d.text(((i%3)*480+8,(i//3)*295+275),f'{t:.3f} s',fill=(235,230,214))
strip.save(OUT/'qa/encoded_wing_motion.jpg',quality=94)
report={'movie':str(MOVIE.relative_to(ROOT)),'video':{k:video.get(k) for k in ['codec_name','width','height','r_frame_rate','nb_read_frames','duration']},
    'audio':{k:audio.get(k) for k in ['codec_name','sample_rate','channels','duration']},
    'full_decode_errors':decode.stderr.decode(),'mix_pcm_peak':peak,'mix_pcm_duration':48,
    'frame_difference_mean':float(adj.mean()),'boundary_frame_differences':boundaries,
    'note':'Frame difference measures are diagnostic only; aesthetic continuity still needs human review.',
    'visual_limitations':['2.5D wing anatomy and pose change at fall need review','street-to-city painted composite has scale/stitch artifacts','regional surface and Earth are not a measured continuous projection']}
(OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
