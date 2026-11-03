"""Package only the reproducible film sources and required local media."""
from pathlib import Path
import json,hashlib,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'assets/video/emergence_final90'
verification=json.loads((OUT/'verification.json').read_text('utf-8'))
for v in verification['videos']:
 p=OUT/v['file'];assert v['full_decode_ok'] and hashlib.sha256(p.read_bytes()).hexdigest()==v['sha256']
files=set()
def add(p):
 if p.is_file():files.add(p)
def tree(p):
 for f in p.rglob('*'):add(f)
for name in ['engine.js','index.html','flight-cycle.js','approved-camera-path.js','accepted_ascent.json','approved_audio_aac_sha256.json','revision4_preserved_hashes.json','cues.json','timeline.json','ending_zh_en.srt','ending_zh.srt','ending_en.srt','subtitles.ass','subtitle_layout.json','approved_materials_hashes.json','交付与复现.txt','正片画面总览.jpg','verification.json','qa_report.json','render_report.json','container_finalization.json']:add(OUT/name)
for name in ['flock','shaders','street','approved-art']:tree(OUT/name)
accepted=ROOT/'assets/video/city_earth_review_v2'
for name in ['camera-path.js','camera-path.glsl','city.frag','earth.frag','cloud.frag','城市至地球_低空穿云_连续上升预览_v2.mp4','制作说明.txt','verification.json']:add(accepted/name)
for frame in [48,144,192,240,312,384,528,647]:add(accepted/'qa'/f'frame_{frame}.png')
tree(ROOT/'assets/video/earth_transition_review_v1/art')
add(ROOT/'assets/video/earth_transition_review_v1/制作说明.txt')
for name in ['approved_ascent_final90.js','install_approved_ascent.py','deliver_final90.py']:add(ROOT/'scripts/ShaderFilm'/name)
add(OUT/'delivery_revision5.json')
add(OUT/'revision5_preserved_hashes.json')
add(ROOT/'scripts/ShaderFilm/repair_street_audio.py')
add(ROOT/'scripts/ShaderFilm/verify_delivery_fixes.py')
for name in ['mix.wav','mix_raw.wav','ambience.wav']:add(OUT/'archive_v4/audio'/name)
shared=ROOT/'assets/video/emergence_shader'
for name in ['engine.js','index.html','flight-cycle.js','flock.json']:add(shared/name)
for name in ['art','shaders']:tree(shared/name)
for f in (shared/'flock_v2').iterdir():
 if f.suffix in ['.js','.vert','.frag']:add(f)
for name in ['prepare_final90.py','prepare_dense_flock.py','centered_flock_view.js','transitions_revision3.js','ascent_revision3.frag','prepare_game_video.py','render_street14.py','rig_pedestrians.py','subtitle_final90.py','audio_final90.py','audio.py','narration90.ps1','render_final90.cjs','verify_final90.py','finalize_final90.py','package_final90.py','run_final90.ps1']:add(ROOT/'scripts/ShaderFilm'/name)
audio=ROOT/'assets/audio/emergence_final90'
for f in audio.iterdir():
 if f.suffix in ['.wav','.json'] and f.name!='mix_raw.wav':add(f)
for key in ['P01','P02']:tree(ROOT/'assets/video/素材/行人场景_v3_流畅快走'/key/'拆层')
add(ROOT/'assets/video/素材/路口完整背景_v3_样片匹配/路口背景_样片匹配_1920x1080.png')
for name in ['让行车_透明素材.png','先行对向车_透明素材.png']:add(ROOT/'assets/video/素材/路口人车_v4'/name)
for name in ['路口人车_持续行走_14秒.mp4','通行检查.json','路线检查.png']:add(ROOT/'assets/video/素材/路口人车_v7_十四秒'/name)
entries=[{'path':str(p.relative_to(ROOT)).replace('\\','/'),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files)]
manifest=OUT/'source_files.json';manifest.write_text(json.dumps({'files':entries,'count':len(entries)},ensure_ascii=False,indent=2),encoding='utf-8');files.add(manifest)
dest=OUT/'涌现_90秒_源工程与音轨.zip'
with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=5) as z:
 for p in sorted(files):z.write(p,str(p.relative_to(ROOT)))
 z.writestr('先读我.txt',(OUT/'交付与复现.txt').read_text('utf-8'))
with zipfile.ZipFile(dest) as z:assert z.testzip() is None
(OUT/'source_package.json').write_text(json.dumps({'file':dest.name,'files':len(files)+1,'bytes':dest.stat().st_size,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'files':len(files)+1,'zip_bytes':dest.stat().st_size}),flush=True)
