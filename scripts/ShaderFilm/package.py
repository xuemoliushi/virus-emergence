"""Bundle only the independent film project, its source art and local audio."""
from pathlib import Path
import json,zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'assets/video/emergence_shader'
manifest=json.loads((OUT/'source_manifest.json').read_text(encoding='utf-8'))
manifest['methods']=['alpha feather-edge decontamination','manual silhouette masks',
 'road texture transport and zebra-stripe repair','deterministic local flock rules','single fixed Earth layer']
manifest['limitations'].append('street-to-city composite has visible scale/stitch differences') if 'street-to-city composite has visible scale/stitch differences' not in manifest['limitations'] else None
(OUT/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
files=[]
for base in [ROOT/'scripts/ShaderFilm',ROOT/'assets/audio/emergence_shader',OUT]:
 for p in base.rglob('*'):
  if not p.is_file():continue
  if '__pycache__' in p.parts:continue
  if p.suffix=='.log' or p.name.startswith('part_') or p.name in ['concat.txt','mix_raw.wav']:continue
  if 'qa' in p.relative_to(base).parts and p.name not in ['encoded_contact_sheet.jpg','encoded_wing_motion.jpg']:continue
  files.append(p)
files.extend(ROOT/'assets/video/素材'/name for name in manifest['assets'])
files.append(ROOT/'视频/主要剧本.md')
target=ROOT/'assets/video/涌现_Shader_技术样片工程.zip'
with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 z.writestr('开始阅读.md','# 《涌现》48 秒技术样片\n\n工程说明在 assets/video/emergence_shader/README.md。\n\n解压后在本目录执行：\n\n```powershell\npowershell -NoProfile -ExecutionPolicy Bypass -File scripts/ShaderFilm/run.ps1 -Mode Preview\n```\n\n然后打开 http://127.0.0.1:8766/assets/video/emergence_shader/index.html 。\n\n也可直接播放 assets/video/emergence_shader/sample_bilingual.mp4。\n\n原主要剧本保留供参考；本工程以 README 和镜头与素材缺口.md 记录的用户确认修改为准。\n')
 for p in sorted(set(files)):
  z.write(p,p.relative_to(ROOT).as_posix(),compress_type=zipfile.ZIP_STORED if p.suffix in ['.mp4','.png','.jpg'] else zipfile.ZIP_DEFLATED)
print(f'{target}\n{target.stat().st_size/1024/1024:.1f} MiB; {len(set(files))} files')
