"""Package imagegen grayscale revision with invariant road geometry."""
from pathlib import Path
from PIL import Image, ImageChops
import numpy as np
import json, shutil

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'assets/video/素材/路口几何底稿'
OUT=ROOT/'assets/video/素材/路口完整背景_v2_灰白'
OUT.mkdir(parents=True,exist_ok=True)
RAW=Path('C:/Users/admin/.codex/generated_images/01a13ebf-cdeb-7dc2-95bf-dafb9f13f470/exec-2cba2c35-4725-4da2-b5a5-efa04e214ed6.png')
raw=Image.open(RAW).convert('RGB')
size=(3840,2160)
generated=raw.resize(size,Image.Resampling.LANCZOS).convert('L').convert('RGB')
road=Image.open(SRC/'01_路口底稿_3840x2160.png').convert('L').convert('RGB')
protect=Image.open(SRC/'02_保护蒙版_白保护黑生成.png').convert('L')
final=Image.composite(road,generated,protect)
final.save(OUT/'路口完整背景_灰白_3840x2160.png')
final.resize((1920,1080),Image.Resampling.LANCZOS).save(OUT/'路口完整背景_灰白_1920x1080.png')
shutil.copy2(RAW,OUT/'AI原始输出_灰白.png')
for corner in ['上','右','下','左']:
    part=final.convert('RGBA')
    alpha=Image.open(SRC/f'分区_{corner}_白生成黑保护.png').convert('L')
    alpha=ImageChops.subtract(alpha,protect)
    part.putalpha(alpha)
    part.save(OUT/f'图层_街角_{corner}_灰白.png')
overlay=road.convert('RGBA')
overlay.putalpha(protect)
overlay.save(OUT/'图层_道路人行道_灰白.png')
protect.save(OUT/'蒙版_道路_白保护黑生成.png')
a=np.asarray(final)
road_delta=int(np.any(a!=np.asarray(road),axis=2)[np.asarray(protect)==255].sum())
chroma=int(np.max(a.max(axis=2).astype(int)-a.min(axis=2).astype(int)))
assert road_delta==0 and chroma==0
(OUT/'校验.json').write_text(json.dumps({'generator':'built-in image_gen','native_generated_size':raw.size,
    'delivery_size':size,'native_4k_detail':False,'max_rgb_channel_difference':chroma,
    'road_changed_pixels_vs_original_grayscale_geometry':road_delta,
    'notes':'Road colors intentionally changed to neutral gray. Geometry locked by source mask. Architecture color correction by image_gen; fine generated details may differ.',
    'previous_version_preserved':True,'sample_replaced':False},ensure_ascii=False,indent=2),encoding='utf-8')
print('neutral gray check:',chroma,'road changed pixels:',road_delta)
