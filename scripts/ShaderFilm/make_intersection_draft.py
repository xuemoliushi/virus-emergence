"""Deterministic oblique intersection plate and masks. No source art modified."""
from pathlib import Path
import math
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parents[2] / 'assets/video/素材/路口几何底稿'
OUT.mkdir(parents=True, exist_ok=True)
W, H, S = 3840, 2160, 2
RW, SIDE, GUARD = 105, 150, 168
EXT = 2200
svg = []
plate = Image.new('RGB', (W, H), '#bdb6a5')
draw = ImageDraw.Draw(plate)

def p(u, v):
    return ((960 + .82*u - .82*v)*S, (540 + .41*u + .41*v)*S)

def poly(points, color, target=draw, record=True):
    xy = [p(*q) for q in points]
    target.polygon(xy, fill=color)
    if record:
        svg.append('<polygon points="'+' '.join(f'{x:.2f},{y:.2f}' for x,y in xy)+f'" fill="{color}"/>')

def rect(u0,v0,u1,v1,color,target=draw,record=True):
    poly([(u0,v0),(u1,v0),(u1,v1),(u0,v1)], color,target,record)

# The same projection is applied to ALL ground geometry.
rect(-EXT,-SIDE,EXT,SIDE,'#cfc7b6')
rect(-SIDE,-EXT,SIDE,EXT,'#cfc7b6')
# Paving joints only outside the carriageway.
for k in range(-EXT,EXT,34):
    for side in [-1,1]:
        lo,hi = (RW,SIDE) if side==1 else (-SIDE,-RW)
        if abs(k)>SIDE+15:
            rect(k,lo,k+.6,hi,'#b7ae9c')
            rect(lo,k,hi,k+.6,'#b7ae9c')
# Curbs are a geometric strip, not AI-painted approximations.
rect(-EXT,-RW-4,EXT,RW+4,'#e1d7c2')
rect(-RW-4,-EXT,RW+4,EXT,'#e1d7c2')
rect(-EXT,-RW,EXT,RW,'#928b7d')
rect(-RW,-EXT,RW,EXT,'#928b7d')

# Four zebra crossings: perpendicular to their road axis, no overlap in center.
for sign in [-1,1]:
    low,high = sorted((sign*155,sign*207))
    for cross in range(-90,91,20):
        rect(low,cross-5,high,cross+5,'#eee5d1')
        rect(cross-5,low,cross+5,high,'#eee5d1')

# Right-hand traffic. Stop bars occupy ONLY the approaching half of each road.
# +u arm approaches toward -u on v<0; -u arm approaches +u on v>0.
for sign in [-1,1]:
    pos = sign*226
    a,b = (-98,-7) if sign==1 else (7,98)
    rect(pos-3,a,pos+3,b,'#eee5d1')
    # +v arm approaches -v on u>0; -v arm approaches +v on u<0.
    a,b = (7,98) if sign==1 else (-98,-7)
    rect(a,pos-3,b,pos+3,'#eee5d1')

# Center separators share exact world axes; stop before crosswalks.
for sign in [-1,1]:
    a,b = sorted((sign*245,sign*EXT))
    rect(a,-1.8,b,1.8,'#d6c49b')
    rect(-1.8,a,1.8,b,'#d6c49b')

# Fine monochrome grain; geometric edges and coordinates remain unchanged.
rng = np.random.default_rng(20261015)
arr = np.asarray(plate).astype(np.int16)
grain = rng.normal(0,1.25,(H,W,1))
plate = Image.fromarray(np.uint8(np.clip(arr+grain,0,255)))
plate.save(OUT/'01_路口底稿_3840x2160.png')
plate.resize((1920,1080),Image.Resampling.LANCZOS).save(OUT/'01_路口底稿_预览.png')

# White protected, black editable. Conservative sidewalk buffer prevents curb drift.
protect = Image.new('L',(W,H),0)
pd = ImageDraw.Draw(protect)
rect(-EXT,-GUARD,EXT,GUARD,255,pd,False)
rect(-GUARD,-EXT,GUARD,EXT,255,pd,False)
protect.save(OUT/'02_保护蒙版_白保护黑生成.png')
editable = Image.eval(protect,lambda a:255-a)
editable.save(OUT/'03_编辑蒙版_白生成黑保护.png')
# OpenAI-style alpha convention: transparent is editable; opaque is protected.
alpha = Image.new('RGBA',(W,H),(255,255,255,255))
alpha.putalpha(protect)
alpha.save(OUT/'04_编辑蒙版_透明生成不透明保护.png')
overlay = plate.convert('RGBA')
overlay.putalpha(protect)
overlay.save(OUT/'05_道路人行道_透明覆盖层.png')

# Individual editable quadrants for tools that accept luminance masks.
for name,su,sv in [('上',-1,-1),('右',1,-1),('下',1,1),('左',-1,1)]:
    mask=Image.new('L',(W,H),0)
    md=ImageDraw.Draw(mask)
    u0,u1=sorted((su*GUARD,su*EXT))
    v0,v1=sorted((sv*GUARD,sv*EXT))
    rect(u0,v0,u1,v1,255,md,False)
    mask.save(OUT/f'分区_{name}_白生成黑保护.png')

preview=plate.convert('RGBA')
tint=Image.new('RGBA',(W,H),(66,169,180,0))
tint.putalpha(protect.point(lambda a:round(a*.23)))
preview=Image.alpha_composite(preview,tint)
preview.resize((1920,1080),Image.Resampling.LANCZOS).save(OUT/'06_保护范围示意_蓝色为保护区.png')

(OUT/'路口底稿_可编辑.svg').write_text(
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
    '<title>暖灰褐色双向两车道十字路口底稿</title>'
    '<rect width="100%" height="100%" fill="#bdb6a5"/>'+''.join(svg)+'</svg>',encoding='utf-8')

checks={
    'size':[W,H], 'projection':'orthographic oblique: x=960+.82u-.82v; y=540+.41u+.41v, output scale 2',
    'traffic':'right-hand; one lane each direction; fictional cinematic layout, not a traffic engineering plan',
    'road_half_width':RW,'sidewalk_outer_half_width':SIDE,'protected_half_width':GUARD,
    'crosswalk_axis_range':[155,207],'stop_bar_axis':226,'center_line_starts_at':245,
    'opposite_arms_share_axes':True,'crosswalks_clear_of_intersection':155>RW,
    'stop_bars_outside_crosswalks':226-3>207,
    'center_line_outside_crosswalks':245>207,
    'mask_binary_values':sorted(int(x) for x in np.unique(np.asarray(protect))),
    'protected_overlay_rgb_matches_plate':True,
}
assert checks['crosswalks_clear_of_intersection'] and checks['stop_bars_outside_crosswalks']
assert checks['center_line_outside_crosswalks'] and checks['mask_binary_values']==[0,255]
(OUT/'geometry_check.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
print(OUT)
