"""Extract the user's artwork into reproducible, editable animation layers."""
from pathlib import Path
import sys, json, hashlib
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'.tmp/shader-film-deps'))
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
SRC=ROOT/'assets/video/素材'
OUT=ROOT/'assets/video/emergence_shader'
ART=OUT/'art'
ART.mkdir(parents=True,exist_ok=True)
(OUT/'qa').mkdir(exist_ok=True)
AUDIO=ROOT/'assets/audio/emergence_shader'
AUDIO.mkdir(parents=True,exist_ok=True)

def save(name, im):
    im.save(ART/name)

def mask_poly(size, points):
    m=Image.new('L',size);ImageDraw.Draw(m).polygon(points,fill=255)
    return m

def dark_cut(im):
    arr=np.asarray(im.convert('RGB')).astype(np.float32)
    lum=arr.mean(2)
    # Decontaminate ivory at feather edges instead of leaving bright outlines.
    a=np.clip((235-lum)/45,0,1)
    bg=np.array([247,246,240],np.float32)
    rgb=np.clip((arr-bg[None,None,:]*(1-a[:,:,None]))/np.maximum(a[:,:,None],.02),0,255)
    return Image.fromarray(np.dstack([rgb,a*255]).astype(np.uint8),'RGBA')

sheet=Image.open(SRC/'01_bird_a_sheet.png').convert('RGB')
bird=dark_cut(sheet.crop((100,0,600,500)))
wingmask=mask_poly(bird.size,[(95,5),(175,5),(260,145),(320,268),(339,343),
    (309,376),(247,340),(151,300),(126,223)])
wing=bird.copy();wing.putalpha(Image.fromarray((np.asarray(bird.getchannel('A')).astype(float)*np.asarray(wingmask)/255).astype('uint8')))
# The back contour excludes the residual upper-wing stump in the old Canvas artwork.
bodymask=mask_poly(bird.size,[(57,414),(178,401),(263,369),(305,355),(349,357),
    (373,349),(412,351),(439,368),(465,382),(435,391),(390,426),(352,444),
    (294,454),(249,447),(206,440),(177,455),(74,466),(106,435)])
body=bird.copy();body.putalpha(Image.fromarray((np.asarray(bird.getchannel('A')).astype(float)*np.asarray(bodymask)/255).astype('uint8')))
save('bird_body.png',body);save('bird_wing.png',wing)
fall=dark_cut(Image.open(SRC/'12_bird_losing_lift.png'))
b=fall.getchannel('A').getbbox();fall=fall.crop(b)
save('bird_fall.png',fall)

# Inpaint the existing bird from the landscape; preserve the original mountain atmosphere.
sky=np.array(Image.open(SRC/'03_K02_single_bird.png').convert('RGB'))
yy,xx=np.mgrid[:1080,:1920]
base=np.stack([246-yy*.008,244-yy*.008,237-yy*.007],2)
weight=np.clip((yy-790)/110,0,1)[:,:,None]
sky=np.clip(base*(1-weight)+sky*weight,0,255).astype('uint8')
save('sky.jpg',Image.fromarray(sky).filter(ImageFilter.GaussianBlur(2)))

street=np.array(Image.open(SRC/'13_intersection_closeup.png').convert('RGB'))
# Manually traced silhouettes include their cast shadows. Kept as editable masks.
objects=[
 ('walker_a',[(800,545),(818,524),(839,521),(843,540),(850,555),(849,570),(862,576),(861,587),
  (843,578),(849,600),(861,608),(857,620),(831,631),(805,642),(791,636),(805,617),(810,587),(802,570)]),
 ('walker_b',[(935,558),(951,556),(953,572),(957,583),(965,598),(960,606),(966,628),(960,642),
  (966,650),(984,657),(975,668),(947,675),(928,680),(913,673),(911,657),(915,639),(920,628),(924,604),(929,582)]),
 ('waiting_a',[(1433,513),(1448,501),(1460,512),(1460,532),(1467,552),(1459,561),
  (1460,589),(1450,599),(1450,613),(1468,627),(1467,641),(1448,637),(1431,624),(1423,606),(1434,585),(1434,554),(1429,540)]),
 ('waiting_b',[(1475,528),(1490,524),(1499,535),(1495,550),(1500,567),(1504,581),
  (1510,592),(1505,602),(1505,615),(1525,630),(1524,646),(1508,649),(1496,636),(1479,621),(1479,601),(1469,587),(1473,566)]),
 ('car_a',[(575,650),(635,608),(688,603),(728,609),(744,623),(771,629),(785,647),
  (785,666),(767,689),(742,710),(687,740),(624,757),(583,750),(559,728),(553,700)]),
 ('car_b',[(1496,254),(1526,234),(1563,227),(1583,231),(1598,245),(1607,259),
  (1615,277),(1595,298),(1558,321),(1523,325),(1490,310),(1488,288)])]
allmask=Image.new('L',(1920,1080))
meta=[]
for name,pts in objects:
    m=mask_poly((1920,1080),pts)
    ImageDraw.Draw(allmask).polygon(pts,fill=255)
    box=m.getbbox();im=Image.fromarray(street).convert('RGBA');im.putalpha(m.filter(ImageFilter.GaussianBlur(.65)))
    save(name+'.png',im.crop(box))
    meta.append({'name':name,'box':box,'anchor':[(box[0]+box[2])/2,box[3]-12]})
# Texture-aware repair plus a wider exclusion band prevents duplicated feet/shadows.
mask=np.array(allmask);mask=cv2.dilate(mask,np.ones((9,9),np.uint8))
cv2.ellipse(mask,(1452,635),(24,43),-12,0,360,255,-1)
cv2.ellipse(mask,(1509,644),(23,39),-12,0,360,255,-1)
# Large painted objects do not inpaint reliably: transport an empty road texture
# instead of keeping the radial streaks produced by Telea/NS on large holes.
yy,xx=np.mgrid[:1080,:1920]
road=street[485:595,990:1150]
repair=road[(yy%110),(xx%160)].copy()
repair=cv2.GaussianBlur(repair,(3,3),.65)
soft=Image.fromarray(mask).filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(5))
alpha=np.array(soft).astype(float)/255
plate=np.clip(street*(1-alpha[:,:,None])+repair*alpha[:,:,None],0,255).astype('uint8')
# Restore the zebra paint where the two walkers were removed. The stripes are
# parallel and share a single road plane; this is retained as an editable plate.
zebra=np.array(plate)
for offset in range(-2,8):
    x=739+offset*39;y=527+offset*22.5
    poly=np.array([[x,y],[x+18,y+10],[x-119,y+79],[x-137,y+69]],np.int32)
    paint=np.zeros((1080,1920),np.uint8);cv2.fillConvexPoly(paint,poly,255)
    affected=(paint>0)&(mask>0)&(xx>775)&(xx<1000)&(yy>510)&(yy<720)
    zebra[affected]=np.clip(np.array([236,231,217])+repair[affected].astype(float)*.035,0,255)
plate=zebra
save('street_clean.png',Image.fromarray(plate));save('street_removal_mask.png',Image.fromarray(mask))
(ART/'street_objects.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
world=Image.open(SRC/'08_K08_dense_city.png').convert('RGB').resize((5760,3240),Image.Resampling.LANCZOS)
yy,xx=np.mgrid[:1080,:1920]
edge=np.minimum.reduce([xx,1919-xx,yy,1079-yy]).astype(float)
feather=np.clip(edge/110,0,1);feather=feather*feather*(3-2*feather)
world.paste(Image.fromarray(plate),(1920,1080),Image.fromarray((feather*255).astype('uint8')))
save('street_world.jpg',world)

for f,n in [('05_K05_cloud_descent.png','cloud_reference.jpg'),
 ('08_K08_dense_city.png','city.jpg'),('09b_city_to_earth_bridge.png','curvature.jpg'),
 ('14_city_to_earth_regional.png','region.jpg')]:
    save(n,Image.open(SRC/f).convert('RGB'))

# Four independently deformable cloud banks; alpha from feathered polygon windows.
cloud=Image.open(SRC/'05_K05_cloud_descent.png').convert('RGBA')
for i,box in enumerate([(0,150,690,1080),(1210,70,1920,1080),(0,0,1150,410),(650,680,1920,1080)]):
    im=cloud.crop(box);yy,xx=np.mgrid[:im.height,:im.width]
    r=((xx-im.width/2)/(im.width*.55))**2+((yy-im.height/2)/(im.height*.55))**2
    alpha=np.clip((1.08-r)/.45,0,1)
    # No rectangular boundaries or opaque corners.
    im.putalpha(Image.fromarray((alpha*255).astype('uint8')))
    save('cloud_bank_'+str(i)+'.png',im)

# One Earth texture across all sizes/backgrounds: no continental boiling from redraws.
earth=Image.open(SRC/'09c_big_earth.png').convert('RGBA').crop((423,13,1497,1057))
earth=earth.resize((1080,1080),Image.Resampling.LANCZOS)
yy,xx=np.mgrid[:1080,:1080];r=np.sqrt(((xx-539.5)/539)**2+((yy-539.5)/539)**2)
alpha=np.clip((.995-r)*220,0,1)
earth.putalpha(Image.fromarray((alpha*255).astype('uint8')))
save('earth.png',earth)

# A deterministic, separately exportable Boids trajectory. Hero keeps one identity.
rng=np.random.default_rng(1987);n0,n1=38,104
group=np.r_[np.zeros(n0),np.ones(n1),1]
ang=rng.uniform(0,2*np.pi,n0+n1);rad=np.sqrt(rng.uniform(.08,1,n0+n1))
p=np.column_stack([980+np.cos(ang)*rad*np.where(group[:-1]==0,740,520),
    np.where(group[:-1]==0,220,550)+np.sin(ang)*rad*np.where(group[:-1]==0,50,128)])
p=np.vstack([p,[1020,620]])
v=np.column_stack([rng.uniform(50,72,len(p)),rng.uniform(-8,8,len(p))])
phases=rng.uniform(0,6.283,len(p));freq=rng.uniform(2.1,2.75,len(p))
height_offsets=rng.normal(0,1,len(p))*np.where(group==0,18,48)
frames=[];dt=1/48
for step in range(1057):
    t=step*dt
    if step%2==0:frames.append(np.round(np.column_stack([p,v]),3).tolist())
    d=p[None,:,:]-p[:,None,:];d2=(d*d).sum(2)
    valid=(d2<145**2)&(d2>0)&(group[:,None]==group[None,:])
    if t>=16:valid[:,-1]=False;valid[-1,:]=False
    count=np.maximum(valid.sum(1),1)
    align=valid.astype(float)@v/count[:,None]-v
    cohesion=(d*valid[:,:,None]).sum(1)/count[:,None]
    sep=-(d/np.maximum(d2[:,:,None],1)*((d2<32**2)&(d2>0))[:,:,None]).sum(1)
    targets=np.where(group==0,220,550)+np.where(group==0,42,90)*np.sin(t*.75+np.where(group==0,0,1.2)+p[:,0]*.0012)+height_offsets
    accel=align*.9+cohesion*.045+sep*650
    accel[:,1]+=(targets-p[:,1])*.13
    accel[:,0]+=(62-v[:,0])*.25
    if t<15:accel[-1,1]+=(np.mean(p[n0:-1,1])+48-p[-1,1])*.8
    v+=accel*dt
    speed=np.linalg.norm(v,axis=1);v*=np.minimum(100/np.maximum(speed,1),1)[:,None]
    p+=v*dt;p[:,0]-=54*dt
    if t>=15:
        p[-1,1]+=(10+max(0,t-16)**2*32)*dt
        p[-1,0]+=30*dt
(OUT/'flock.json').write_text(json.dumps({'fps':24,'hero':len(p)-1,'group':group.tolist(),
    'phase':phases.tolist(),'frequency':freq.tolist(),'frames':frames},separators=(',',':')),encoding='utf-8')

manifest={'source':str(SRC),'output':'48-second technology sample; 90-second film pending visual review',
    'bird_root':[320,370],'bird_body_anchor':[310,405],
    'assets':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in SRC.glob('*.png') if not f.name.startswith('_')},
    'methods':['alpha feather-edge decontamination','manual silhouette masks','road texture transport and zebra-stripe repair',
     'deterministic local flock rules','single fixed Earth layer'],
    'limitations':['illustrated 2.5D wing deformation, not a true 3D anatomical rig',
     'regional map is fictional, not a measured projection of the final globe',
     'road silhouettes are extracted painted poses, walking deformation is approximate']}
(OUT/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('Prepared',len(list(ART.iterdir())),'layers;',len(frames),'flock states')
