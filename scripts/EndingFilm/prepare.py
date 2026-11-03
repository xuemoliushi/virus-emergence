"""Prepare editable layers from the user's 2026-10-14 reference artwork."""
from pathlib import Path
import json, shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / '2026-10-14_鸟群坠落'
OUT = ROOT / 'assets/video/emergence_90s'
ART = OUT / 'art'
ART.mkdir(parents=True, exist_ok=True)

sheet = Image.open(REF/'01_bird_a_sheet.png').convert('RGBA')
bird = sheet.crop((100, 0, 600, 500))
a = np.asarray(bird).copy()
luma = a[:,:,:3].mean(axis=2)
a[:,:,3] = np.clip((210-luma)/35, 0, 1)*255
bird = Image.fromarray(a)
# Split the same bird at its shoulder, keeping the torso and identity locked.
wingmask = Image.new('L', bird.size)
ImageDraw.Draw(wingmask).polygon([(95,5),(175,5),(260,145),(320,268),(339,343),
                                (309,376),(247,340),(151,300),(126,223)], fill=255)
wing = bird.copy()
wing.putalpha(Image.fromarray((np.asarray(bird.getchannel('A')).astype(float)*
                              np.asarray(wingmask)/255).astype('uint8')))
bodymask = Image.new('L', bird.size)
ImageDraw.Draw(bodymask).polygon([(57,414),(190,399),(244,369),(290,353),(340,357),
    (371,348),(412,351),(439,368),(465,382),(435,391),(390,426),(352,444),
    (294,454),(249,447),(206,440),(177,455),(74,466),(106,435)],fill=255)
body = bird.copy()
body.putalpha(Image.fromarray((np.asarray(bird.getchannel('A')).astype(float)*
                              np.asarray(bodymask)/255).astype('uint8')))
wing.save(ART/'bird_wing.png'); body.save(ART/'bird_body.png')
bird.save(ART/'bird_reference_cutout.png')

for src,name in [('05_K05_cloud_descent.png','cloud_world.jpg'),
                 ('08_K08_dense_city.png','city_world.jpg'),
                 ('09b_city_to_earth_bridge.png','curvature_reference.jpg')]:
    Image.open(REF/src).convert('RGB').save(ART/name, quality=94)

earth = Image.open(REF/'09c_big_earth.png').convert('RGBA').crop((422,13,1496,1057))
mask=Image.new('L',earth.size)
ImageDraw.Draw(mask).ellipse((3,3,earth.width-3,earth.height-3),fill=255)
earth.putalpha(mask.filter(ImageFilter.GaussianBlur(.8)))
earth.save(ART/'earth.png')

cloudsrc=Image.open(REF/'05_K05_cloud_descent.png').convert('RGBA')
for i,box in enumerate([(0,170,750,1050),(1160,100,1920,990)]):
    patch=cloudsrc.crop(box)
    yy,xx=np.mgrid[0:patch.height,0:patch.width]
    rr=((xx-patch.width/2)/(patch.width*.52))**2+((yy-patch.height/2)/(patch.height*.52))**2
    alpha=np.clip((1.04-rr)/.42,0,1)
    patch.putalpha(Image.fromarray((alpha*255).astype('uint8')))
    patch.save(ART/f'cloud_{i}.png')

shutil.copyfile(ROOT/'assets/image/emergence_art_pack/timeline.json',OUT/'timeline.json')
shutil.copyfile(ROOT/'assets/image/emergence_art_pack/subtitles/ending_emergence_zh_en_draft.srt',OUT/'subtitles_draft.srt')
shutil.copyfile(Path(__file__).parent/'index.html',OUT/'index.html')
shutil.copyfile(Path(__file__).parent/'film.js',OUT/'film.js')

# Fixed local-rule flock simulation. Shared snapshots support four independent workers.
rng=np.random.default_rng(1987)
counts=[30,86]
p=np.vstack([np.column_stack([rng.uniform(170,1680,30),rng.normal(230,25,30)]),
             np.column_stack([rng.uniform(280,1640,86),rng.normal(575,67,86)])])
p=np.vstack([p,[1100,742]])
v=np.column_stack([rng.uniform(17,29,len(p)),rng.normal(0,2,len(p))])
group=np.r_[np.zeros(30),np.ones(87)]
phases=rng.uniform(0,2*np.pi,len(p)); freq=rng.uniform(2.0,2.7,len(p))
states=[]
dt=1/48
for step in range(2161):
    t=step*dt
    if step%2==0:
        states.append(np.round(np.column_stack([p,v]),3).tolist())
    if step==2160: break
    delta=p[None,:,:]-p[:,None,:]
    d2=(delta**2).sum(axis=2)
    same=group[:,None]==group[None,:]
    neigh=(d2<170**2)&(d2>0)&same
    # At death the protagonist ceases to participate in local flock rules.
    if t>=36: neigh[:,-1]=False; neigh[-1,:]=False
    n=np.maximum(neigh.sum(axis=1),1)
    align=(neigh.astype(float)@v)/n[:,None]-v
    coh=(neigh[:,:,None]*delta).sum(axis=1)/n[:,None]
    sep=-((delta/np.maximum(d2[:,:,None],1))*((d2<45**2)&(d2>0)&same)[:,:,None]).sum(axis=1)
    bend=np.zeros_like(v)
    bend[:,1]=np.where(group==0,12*np.sin((t-22)*.55),18*np.sin((t-27)*.55))
    targets=np.where(group==0,230,585)
    accel=align*.65+coh*.035+sep*280+bend*.25
    accel[:,1]+=(targets-p[:,1])*.05
    accel[:,0]+=(24-v[:,0])*.4
    if t<34: accel[-1,1]+=(742-p[-1,1])*.7
    v+=accel*dt
    speed=np.linalg.norm(v,axis=1)
    v*=np.clip(38/np.maximum(speed,1),0,1)[:,None]
    p+=v*dt
    # Gentle screen-space staging, not random regeneration or wraparound.
    p[:,0]-=18*dt
    if t>=34:
        p[-1,1]+=((t-34)*1.8 if t<36 else 28+(t-36)*10)*dt
        p[-1,0]+=14*dt

(OUT/'flock.json').write_text(json.dumps({'seed':1987,'fps':24,'hero':116,
    'phases':phases.tolist(),'freq':freq.tolist(),'states':states},separators=(',',':')),encoding='utf-8')
(OUT/'reference_sources.json').write_text(json.dumps({'reference_folder':str(REF),
    'bird':'01_bird_a_sheet.png: first pose, separated torso and wing',
    'city':'08_K08_dense_city.png: same geometry used at all city scales',
    'earth':'09c_big_earth.png: circle crop, no simulated axial rotation',
    'style':'warm monochrome illustrated references, retained feather/cloud texture'},ensure_ascii=False,indent=2),encoding='utf-8')
print('Prepared layers and',len(states),'shared flock frames in',OUT)
