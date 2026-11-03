"""Mux each original Python design with identical A-profile comparison frames."""
from pathlib import Path
import json
import subprocess

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'validation/menu-entry-audio-20261018'
FF=Path('C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe')

def run(args):
    p=subprocess.run([str(FF),'-v','error',*args],capture_output=True)
    if p.returncode:raise RuntimeError(p.stderr.decode('utf8',errors='replace'))
    return p.stdout

def main():
    # Pipe output to avoid ffmpeg's Windows Unicode output-path limitation.
    video=run(['-framerate','24','-i',str(OUT/'frames/%03d.png'),
        '-an','-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p',
        '-movflags','frag_keyframe+empty_moov','-f','mp4','pipe:1'])
    silent=OUT/'silent-a-profile.mp4';silent.write_bytes(video)
    result=[]
    for name in ['01_pressure','02_membrane','03_micrograins']:
        data=run(['-i',str(silent),'-i',str(ROOT/'assets/audio/entry_candidates'/f'{name}.wav'),
            '-filter_complex','[1:a]volume=0.8,adelay=1250|1250,apad[a]',
            '-map','0:v:0','-map','[a]','-c:v','copy','-c:a','aac','-b:a','192k',
            '-t','4','-movflags','frag_keyframe+empty_moov','-f','mp4','pipe:1'])
        target=OUT/f'{name}.mp4';target.write_bytes(data)
        run(['-i',str(target),'-f','null','pipe:1'])
        result.append({'file':target.relative_to(ROOT).as_posix(),'decoded':True,
            'duration_seconds':4,'timeline_lead_in':.65,'sound_trigger_after_motion':.60,
            'expected_swell_peak_after_motion':1.03,'scope':'A-profile composite, not native capture'})
    (OUT/'video-checks.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result))

if __name__=='__main__':main()
