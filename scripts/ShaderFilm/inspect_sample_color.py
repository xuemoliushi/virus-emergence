from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'assets/video/素材/路口调色对照'
OUT.mkdir(parents=True,exist_ok=True)
FF='C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe'
movie=ROOT/'assets/video/emergence_shader/sample_clean.mp4'
jobs=[('样片每3秒连续抽帧.png',[],['-vf','fps=1/3,scale=480:-1,tile=4x4']),
      ('样片30秒_路口.png',['-ss','30'],[]),
      ('样片36秒_城市.png',['-ss','36'],[]),
      ('样片10秒_鸟群.png',['-ss','10'],[]),
      ('样片43秒_地球.png',['-ss','43'],[])]
for name,pre,filters in jobs:
    result=subprocess.run([FF,'-hide_banner','-loglevel','error',*pre,'-i',str(movie),*filters,'-frames:v','1','-f','image2pipe','-c:v','png','pipe:1'],capture_output=True,check=True)
    (OUT/name).write_bytes(result.stdout)
print('Extracted actual encoded sample frames.')
