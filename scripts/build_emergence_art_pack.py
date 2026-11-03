"""Build portable, editable silhouette artwork; no image/video service required."""
from pathlib import Path
import json, math, random, shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets/image/emergence_art_pack'
OUT.mkdir(parents=True, exist_ok=True)
IVORY, BLACK, GREY = '#F4F2EC', '#101010', '#C8C5BD'
catalog = []

def svg(name, w, h, body, purpose, shots, pivot=None):
    p = OUT / (name + '.svg')
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{body}</svg>', encoding='utf-8')
    item = dict(id=name, svg=name+'.svg', png=name+'.png', width=w, height=h,
                purpose=purpose, shots=shots, origin='procedural vector artwork')
    if pivot: item['pivot_px'] = pivot
    catalog.append(item)

def path(d, fill=BLACK, extra=''):
    return f'<path d="{d}" fill="{fill}" {extra}/>'

def rect(x,y,w,h,fill,rx=0,extra=''):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" {extra}/>'

def ellipse(x,y,rx,ry,fill,extra=''):
    return f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="{fill}" {extra}/>'

svg('background/ivory',1920,1080,rect(0,0,1920,1080,IVORY),'全片底色；可直接用纯色替代',['S01','S02','S03','S04','S05','S06','S07','S08'])
rng = random.Random(73)
paper = Image.new('RGBA',(1920,1080),(0,0,0,0)); pd = ImageDraw.Draw(paper)
for _ in range(2000):
    x,y=rng.randrange(1920),rng.randrange(1080)
    pd.line((x,y,x+rng.randrange(1,7),y+rng.randrange(-2,3)),fill=(75,63,44,rng.randrange(2,9)))
paper.save(OUT/'background/paper_overlay.png')
catalog.append(dict(id='background/paper_overlay',png='background/paper_overlay.png',width=1920,height=1080,shots=['ALL'],purpose='可选低强度纸纹；全片固定或随同背景移动，避免闪烁',origin='procedural raster artwork'))

# One shared torso/head/tail across all poses; the separate wing paths form a rig.
body_d = 'M 264 346 C 350 324 403 289 461 276 C 510 266 550 273 585 271 C 596 237 621 217 658 218 C 695 217 717 237 723 257 L 791 280 L 723 289 C 704 332 666 363 612 378 C 534 399 461 388 406 367 L 266 369 C 237 368 235 358 264 346 Z'
wings = {
 'up': ('M 498 307 C 441 247 324 123 211 91 C 184 82 170 88 187 104 C 245 175 350 271 431 343 Z','M 554 277 C 528 212 490 163 449 147 C 433 139 427 149 439 164 L 513 293 Z'),
 'level': ('M 499 305 C 412 271 298 248 186 250 C 159 250 156 262 180 275 C 251 310 341 341 445 354 Z','M 552 277 C 499 248 460 237 416 238 C 397 238 401 249 416 257 L 522 303 Z'),
 'down': ('M 503 297 C 467 347 408 423 355 485 C 337 505 338 521 359 511 C 418 485 482 429 528 353 Z','M 556 288 C 539 330 527 375 506 407 C 495 424 508 429 522 415 L 583 339 Z'),
 'slack': ('M 505 302 C 467 330 432 375 420 408 C 414 425 424 432 438 420 L 531 350 Z','M 565 289 C 557 323 548 350 547 373 C 545 390 557 394 566 378 L 593 332 Z')
}
for pose,(near,far) in wings.items():
    content = '<g id="far_wing">'+path(far)+'</g><g id="body">'+path(body_d)+'</g><g id="near_wing">'+path(near)+'</g>'
    if pose=='slack':
        content += '<g id="passive_feet">'+path('M 576 373 L 575 400 L 563 407 L 580 403 L 587 408 M 611 375 L 610 397 L 600 408 L 615 402',fill='none',extra='stroke="#101010" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"')+'</g>'
    svg('bird/bird_a_'+pose,1024,640,content,'同一 BIRD_A；身体完全一致，只改变翅膀；朝右',['S02','S03','S04','S05'],[540,328])
svg('bird/chest_mask',1024,640,ellipse(595,330,62,40,'#FFFFFF'),'白色区域是微观纹理窗口；与鸟使用相同画布和变换',['S01','S02'],[540,328])

# Organic texture is abstract art, not an anatomical or transmission simulation.
cells=[]
for row in range(8):
    for col in range(11):
        cx=70+col*140+(row%2)*35+rng.uniform(-30,30); cy=70+row*145+rng.uniform(-30,30)
        pts=[]
        for k in range(12):
            a=2*math.pi*k/12; rad=rng.uniform(.85,1.12)
            pts.append((cx+55*rad*math.cos(a),cy+47*rad*math.sin(a)))
        mid=[((pts[k][0]+pts[(k+1)%12][0])/2,(pts[k][1]+pts[(k+1)%12][1])/2) for k in range(12)]
        d=f'M {mid[-1][0]:.1f} {mid[-1][1]:.1f} '
        d+=' '.join(f'Q {pts[k][0]:.1f} {pts[k][1]:.1f} {mid[k][0]:.1f} {mid[k][1]:.1f}' for k in range(12))+' Z'
        cells.append(path(d,fill='none',extra=f'stroke="{BLACK}" stroke-width="7" stroke-linejoin="round"'))
        cells.append(ellipse(cx+rng.uniform(-10,10),cy+rng.uniform(-8,8),rng.uniform(8,16),rng.uniform(7,13),BLACK))
svg('micro/tissue',1600,1200,''.join(cells),'透明抽象细胞纹理；淡入后缩入胸腔遮罩，不是真实游戏或医学图像',['S01','S02'])

for i in range(3):
    cl=[]
    for k in range(8):
        cx=k*360-40+i*25; cy=170+rng.uniform(-50,50)
        cl.append(ellipse(cx,cy,260+rng.randrange(50),90+rng.randrange(50),GREY))
    svg(f'cloud/cloud_band_{i+1:02}',2560,640,''.join(cl),'透明浅灰云带；可叠放，S05 完全覆盖时换城市层',['S05'])

# Top-down master layout: every camera view uses these exact roads and buildings.
cw,ch=3200,2400
road_parts=[]
for y in [400,1200,2000]:
    road_parts.append(rect(0,y-70,cw,140,BLACK))
    road_parts.append(f'<path d="M 0 {y} H {cw}" fill="none" stroke="{IVORY}" stroke-width="3" stroke-dasharray="22 28"/>')
for x in [400,1600,2800]:
    road_parts.append(rect(x-70,0,140,ch,BLACK))
    road_parts.append(f'<path d="M {x} 0 V {ch}" fill="none" stroke="{IVORY}" stroke-width="3" stroke-dasharray="22 28"/>')
for x in [400,1600,2800]:
    for y in [400,1200,2000]:
        road_parts.append(rect(x-70,y-70,140,140,BLACK))
        for a in [-1,1]:
            for n in range(7):
                road_parts.append(rect(x-55+n*17,y+a*105-17,9,34,IVORY))
                road_parts.append(rect(x+a*105-17,y-55+n*17,34,9,IVORY))
roads='<g id="roads">'+''.join(road_parts)+'</g>'
blocks=[]; far=[]
for iy,(ya,yb) in enumerate([(50,280),(550,1080),(1350,1880),(2150,2350)]):
    for ix,(xa,xb) in enumerate([(45,280),(550,1480),(1750,2680),(2950,3170)]):
        # An open space near the narrative intersection allows meetings to read.
        nx=max(1,int((xb-xa)/180)); ny=max(1,int((yb-ya)/160))
        for rr in range(ny):
            for cc in range(nx):
                x=xa+cc*(xb-xa)/nx+12; y=ya+rr*(yb-ya)/ny+10
                bw=(xb-xa)/nx-35; bh=(yb-ya)/ny-35
                if ix==2 and iy==1 and cc==0 and rr==ny-1: continue
                blocks.append(rect(x,y,bw,bh,BLACK,2))
                blocks.append(rect(x+12,y+12,bw-24,bh-24,IVORY,1))
                if bw>110: blocks.append(rect(x+bw*.55,y+18,7,bh-36,BLACK))
                far.append(rect(x-7,y-7,bw+14,bh+14,GREY,3))
buildings='<g id="buildings">'+''.join(blocks)+'</g>'
far_layer='<g id="distant_building_mass">'+''.join(far)+'</g>'
master=roads+buildings
svg('city/city_roads',cw,ch,roads,'透明道路层；主路口为世界坐标 (1600,1200)',['S05','S06','S07'])
svg('city/city_buildings',cw,ch,buildings,'透明建筑层；与道路完全同画布、同坐标',['S05','S06','S07'])
svg('city/city_distant_mass',cw,ch,far_layer,'可选浅灰远景替代层；不可与近景建筑产生错位',['S05','S06','S07'])
svg('city/city_master',cw,ch,rect(0,0,cw,ch,IVORY)+master,'同一俯视城市布局的完整参考，不含活动角色',['S05','S06','S07'])
# Close view is a crop of the SAME master, not another randomly generated city.
svg('city/intersection_reference',1920,1080,rect(0,0,1920,1080,IVORY)+'<g transform="translate(-2432,-2019) scale(2.2)">'+master+'</g>','主路口构图预览；正式动画应变换 city_master 图层，保持布局一致',['S05','S06'])
skyline=''
for k in range(28):
    x=k*94; height=rng.randrange(65,235)
    skyline+=rect(x,410-height,70+rng.randrange(15),height,GREY)
    if k%4==0: skyline+=rect(x+37,410-height-28,4,28,GREY)
svg('city/roofline_transition',2560,540,skyline,'S05 云后屋顶过渡层；由侧影转入俯视须用云遮挡切换，非物理连续城市',['S05'])

for phase in [0,1]:
    legs=('M 40 75 L 26 108 L 21 119 M 43 75 L 56 106 L 63 112' if phase==0 else 'M 40 75 L 44 112 L 51 119 M 43 75 L 30 107 L 21 110')
    person=ellipse(42,23,10,11,BLACK)+path('M 35 36 Q 42 32 49 37 L 54 75 Q 43 86 30 75 L 31 49 L 20 66 L 15 61 Z')+path(legs,fill='none',extra='stroke="#101010" stroke-width="9" stroke-linecap="round"')
    svg(f'actors/pedestrian_walk_{phase+1:02}',80,128,'<g stroke="#F4F2EC" stroke-width="1.5" paint-order="stroke">'+person+'</g>','透明行人姿态；需保持很小，适合略俯视图形化路口',['S06'],[42,78])
car=rect(12,20,140,56,BLACK,14,extra='stroke="#F4F2EC" stroke-width="3"')+rect(52,25,47,46,IVORY,5)+rect(74,25,5,46,BLACK)+rect(31,14,24,8,BLACK,3,extra='stroke="#F4F2EC" stroke-width="2"')+rect(110,14,24,8,BLACK,3,extra='stroke="#F4F2EC" stroke-width="2"')+rect(31,74,24,8,BLACK,3,extra='stroke="#F4F2EC" stroke-width="2"')+rect(110,74,24,8,BLACK,3,extra='stroke="#F4F2EC" stroke-width="2"')
svg('actors/car_topdown',168,96,car,'透明俯视车辆，默认车头向右；转弯时旋转整体',['S06'],[84,48])

# Reference bird crops: keep the source's actual silhouette; labels are outside ROIs.
ref_dir=ROOT/'视频/jimeng-2026-10-13-3237'
bird_src=next(ref_dir.glob('*-3868-*.png'))
src=Image.open(bird_src).convert('RGB')
rois={'up':(420,170,1340,500),'down':(1390,170,2260,510),'side':(380,550,1340,1030),'fall':(1420,650,2280,1330)}
seeds={'up':(1000,400),'down':(1940,400),'side':(1000,900),'fall':(1990,1030)}
for key,box in rois.items():
    # Flood the complete source so no wing or body is clipped by a guessed ROI.
    a=np.asarray(src); shade=a.min(axis=2)
    alpha=np.clip((145-shade.astype(float))*255/65,0,255).astype('uint8')
    connected=Image.fromarray(np.where(alpha>150,255,0).astype('uint8')).copy()
    seed=seeds[key]
    if connected.getpixel(seed)!=255:
        raise ValueError(f'Bird extraction seed outside silhouette: {key}')
    ImageDraw.floodfill(connected,seed,128)
    component=Image.fromarray(np.where(np.asarray(connected)==128,255,0).astype('uint8')).filter(ImageFilter.MaxFilter(3))
    mask=Image.fromarray(np.where(np.asarray(component)>0,alpha,0).astype('uint8'))
    bb=mask.getbbox()
    rgba=Image.new('RGBA',mask.size,(16,16,16,0)); rgba.putalpha(mask)
    if bb: rgba=rgba.crop(bb)
    name=f'reference/bird_source_{key}'
    (OUT/'reference').mkdir(exist_ok=True)
    rgba.save(OUT/(name+'.png'))
    catalog.append(dict(id=name,png=name+'.png',width=rgba.width,height=rgba.height,shots=['REFERENCE_ONLY'],purpose='从用户鸟形图提取的姿态参考；不同画布不能直接作为振翅序列',origin='extracted user reference',source=bird_src.name))

# Extract the planet ONLY; colour labels and watermark are outside the crop.
earth_src=next(ref_dir.glob('*-3361-*.png'))
ea=Image.open(earth_src).convert('RGB').crop((720,176,1841,1264)).resize((1140,1140),Image.Resampling.LANCZOS)
arr=np.asarray(ea); dark=arr.min(axis=2)<110
yy,xx=np.indices(dark.shape); disc=(xx-570)**2+(yy-570)**2<=566**2
rgba=np.zeros((1140,1140,4),dtype=np.uint8); rgba[:,:,:3]=(16,16,16)
continent=np.logical_and((xx-570)**2+(yy-570)**2<(566*.982)**2,~dark)
rgba[continent,:3]=(244,242,236)
rgba[disc,3]=255
earth=Image.fromarray(rgba)
(OUT/'earth').mkdir(exist_ok=True); earth.save(OUT/'earth/earth_reference.png')
catalog.append(dict(id='earth/earth_reference',png='earth/earth_reference.png',width=1140,height=1140,shots=['S07','S08'],purpose='用户地球参考提取；黑海洋、暖白大陆；透明外背景；单张平面图只能轻微整体转动，不能假装真实地球自转',origin='extracted user reference',source=earth_src.name,pivot_px=[570,570]))
svg('earth/planet_disc',1140,1140,ellipse(570,570,566,566,BLACK),'纯黑底盘；可在轮廓建立时先显示，再揭示大陆',['S07','S08'],[570,570])

layout={
 'units':'artwork pixels, not engine metres','canvas':[3200,2400],'intersection':[1600,1200],
 'roads':{'horizontal_y':[400,1200,2000],'vertical_x':[400,1600,2800],'width':140},
 'safe_screen_rect':[0,0,1920,918],
 'routes':{
  'car_yields':{'points':[[1120,1235],[1450,1235],[1500,1235],[1800,1235]],'action':'decelerate before crossing; wait for pedestrian; resume'},
  'pedestrian_crosses':{'points':[[1475,1085],[1475,1150],[1475,1260],[1475,1315]],'action':'cross north-south along marked crosswalk'},
  'meeting_person_a':{'points':[[1830,1060],[1760,1080],[1775,1020]],'action':'meet near northeast corner then walk north together'},
  'meeting_person_b':{'points':[[1760,970],[1760,1080],[1795,1020]],'action':'meet then walk alongside a'},
  'car_turns':{'points':[[1635,1590],[1635,1350],[1640,1255],[1690,1165],[1810,1165]],'action':'round turn to the east; do not teleport or pass through buildings'}},
 'camera':{'close_center':[1600,1170],'close_scale':2.2,'wide_scale':0.45},
 'bird':{'canvas':[1024,640],'pivot':[540,328],'chest':[595,330],'chest_radius':[62,40],
         'pose_order':['up','level','down','level'],'dead_pose':'slack','direction':'right'},
 'note':'Routes define graphic choreography; use the same world coordinate system for city layers, actors and camera.'}
(OUT/'layout.json').write_text(json.dumps(layout,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'manifest.json').write_text(json.dumps({'version':1,'palette':{'ivory':IVORY,'black':BLACK,'grey':GREY},'assets':catalog},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'output':str(OUT),'assets':len(catalog),'svg':len(list(OUT.rglob('*.svg')))},ensure_ascii=False))
