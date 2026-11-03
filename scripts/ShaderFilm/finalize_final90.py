"""Produce seekable MP4s with exact video timestamps and original PCM audio."""
from pathlib import Path
from fractions import Fraction
import tempfile,subprocess,json,os,argparse
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'assets/video/emergence_final90'
FF=Path(os.environ.get('SHADER_FFMPEG','C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe'));FP=FF.with_name('ffprobe.exe')
parser=argparse.ArgumentParser();parser.add_argument('--scratch-dir');args=parser.parse_args()
def probe(p):return json.loads(subprocess.check_output([str(FP),'-v','error','-show_streams','-show_format','-of','json',str(p)]))
report=[]
with tempfile.TemporaryDirectory(prefix='emergence90_',dir=args.scratch_dir or OUT) as temp:
 for name,plain in [('涌现_90秒_无字幕.mp4','clean.mp4'),('涌现_90秒_双语字幕.mp4','bilingual.mp4')]:
  source=OUT/name;v=next(s for s in probe(source)['streams'] if s['codec_type']=='video')
  step=Fraction(1,24)/Fraction(v['time_base']);assert step.denominator==1
  ticks=int(step);dest=Path(temp)/plain
  cmd=[str(FF),'-v','error','-i',str(source),'-i',str(ROOT/'assets/audio/emergence_final90/mix.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-bsf:v',f'setts=pts=N*{ticks}:dts=N*{ticks}:duration={ticks}',
       '-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t','90','-f','mp4','-fd','1','fd:']
  # Python opens the authorized Unicode path. FFmpeg gets a seekable stdout
  # file descriptor, retaining standard MP4 edit lists and precise durations.
  with dest.open('w+b') as handle:r=subprocess.run(cmd,stdout=handle,stderr=subprocess.PIPE)
  assert r.returncode==0,r.stderr.decode(errors='replace')
  p=probe(dest);vv=next(s for s in p['streams'] if s['codec_type']=='video');aa=next(s for s in p['streams'] if s['codec_type']=='audio')
  assert int(vv['nb_frames'])==2160 and float(vv['duration'])==90 and float(aa['duration'])==90
  report.append({'file':name,'video_seconds':vv['duration'],'audio_seconds':aa['duration'],'frames':int(vv['nb_frames']),'seekable_standard_mp4':True})
 for name,plain in [('涌现_90秒_无字幕.mp4','clean.mp4'),('涌现_90秒_双语字幕.mp4','bilingual.mp4')]:
  (Path(temp)/plain).replace(OUT/name)
(OUT/'container_finalization.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report),flush=True)
