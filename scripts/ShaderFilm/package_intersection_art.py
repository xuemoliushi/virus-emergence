"""Composite generated parcels through the approved masks, preserving road pixels."""
from pathlib import Path
import json
import shutil
import numpy as np
from PIL import Image, ImageChops

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'assets/video/素材/路口几何底稿'
OUT=ROOT/'assets/video/素材/路口完整背景_v1'
OUT.mkdir(parents=True,exist_ok=True)
RAW=Path('C:/Users/admin/.codex/generated_images/01a13ebf-cdeb-7dc2-95bf-dafb9f13f470/exec-f9868dd6-c1db-4a75-805a-3af96d6a584a.png')
base=Image.open(SRC/'07_上方街角建筑_道路锁定.png').convert('RGB')
draft=Image.open(SRC/'01_路口底稿_3840x2160.png').convert('RGB')
protection=Image.open(SRC/'02_保护蒙版_白保护黑生成.png').convert('L')
# Polygon rasterization shares boundary pixels. Give road protection precedence.
base=Image.composite(draft,base,protection)
raw=Image.open(RAW).convert('RGB')
mask=Image.open(SRC/'08_剩余三街角_白生成黑保护.png').convert('L')
mask=ImageChops.subtract(mask,protection)
generated=raw.resize(base.size,Image.Resampling.LANCZOS)
final=Image.composite(generated,base,mask)
final.save(OUT/'路口完整背景_3840x2160.png')
final.resize((1920,1080),Image.Resampling.LANCZOS).save(OUT/'路口完整背景_1920x1080.png')
shutil.copy2(RAW,OUT/'AI原始输出_剩余三街角.png')
for corner in ['上','右','下','左']:
    part=final.convert('RGBA')
    alpha=Image.open(SRC/f'分区_{corner}_白生成黑保护.png').convert('L')
    alpha=ImageChops.subtract(alpha,protection)
    part.putalpha(alpha)
    part.save(OUT/f'图层_街角_{corner}.png')
shutil.copy2(SRC/'05_道路人行道_透明覆盖层.png',OUT/'图层_道路人行道.png')
shutil.copy2(SRC/'02_保护蒙版_白保护黑生成.png',OUT/'蒙版_道路_白保护黑生成.png')
shutil.copy2(SRC/'路口底稿_可编辑.svg',OUT/'道路几何源文件.svg')
roads=np.asarray(Image.open(SRC/'02_保护蒙版_白保护黑生成.png'))==255
f=np.asarray(final)
changed=int(np.any(f!=np.asarray(draft),axis=2)[roads].sum())
black=np.asarray(mask)==0
other_changed=int(np.any(f!=np.asarray(base),axis=2)[black].sum())
assert changed==0 and other_changed==0
report={'generator':'built-in image_gen','raw_generated_size':list(raw.size),
        'delivery_size':list(final.size),'native_4k_detail':False,
        'note':'AI output resampled to match 4K geometry; original output retained.',
        'road_and_sidewalk_changed_pixels_vs_original_draft':changed,
        'changed_pixels_outside_remaining_three_parcels':other_changed,
        'top_corner_preserved':True,'shared_mask_edge_priority':'road wins',
        'game_or_sample_replaced':False,
        'layers':'Full canvas RGBA, original pixel alignment; not depth-separated buildings or trees.'}
(OUT/'保护校验.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
