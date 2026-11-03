"""Fourteen seconds of continuous, distance-driven walking on paved routes."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
import numpy as np
import math, json, subprocess, os, sys, copy
import rig_pedestrians as rig

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'assets/video/素材/路口人车_v7_十四秒'; OUT.mkdir(exist_ok=True)
FRAMES=ROOT/'assets/video/emergence_final90/street'; FRAMES.mkdir(exist_ok=True)
FPS=24; SECONDS=14; S=.19; UNIT=rig.SCALE*S/math.hypot(.82,.41)
rig.STANCE=.60; rig.LIFT_HEIGHT=.020; rig.TOE_OFF_ANGLE=math.radians(50)
rig.HEEL_STRIKE_ANGLE=math.radians(-8); rig.ARM_SWING=.22
PEOPLE=ROOT/'assets/video/素材/行人场景_v3_流畅快走'
layers={k:{n:Image.open(PEOPLE/k/'拆层'/(n+'.png')).convert('RGBA') for n in c['parts']} for k,c in rig.CONFIG.items()}
background=Image.open(ROOT/'assets/video/素材/路口完整背景_v3_样片匹配/路口背景_样片匹配_1920x1080.png').convert('RGBA')
routes={'P01':dict(start=-130.,v=190.,speed=1.02,span=.68,phase=.07,sign=1),
        'P02':dict(start=134.,v=170.,speed=1.10,span=.62,phase=.42,sign=-1)}

def world(u,v):return np.array([960+.82*u-.82*v,540+.41*u+.41*v])
def unproject(p):
 x,y=np.asarray(p)-[960,540];return np.array([.5*(x/.82+y/.41),.5*(y/.41-x/.82)])

def path(key,t):
 r=routes[key];sg=r['sign'];dist=r['speed']*max(t,0)*UNIT
 straight=130-sg*r['start'];radius=50.;arc=radius*math.pi/2
 if dist<straight:
  uv=np.array([r['start']+sg*dist,r['v']]); tangent=np.array([sg,0.]);turn=0.
 elif dist<straight+arc:
  a=(dist-straight)/radius
  uv=np.array([sg*(130+radius*math.sin(a)),r['v']+sg*radius*(1-math.cos(a))])
  tangent=np.array([sg*math.cos(a),sg*math.sin(a)]);turn=a/(math.pi/2)
 else:
  uv=np.array([sg*180,r['v']+sg*(radius+dist-straight-arc)])
  tangent=np.array([0.,sg]);turn=1.
 phase=(r['phase']+r['speed']*t/(r['span']/rig.STANCE))%1
 return uv,tangent,phase,turn

def paved(uv):
 u,v=uv
 # Original crossing and its corner pavements; the woman continues across
 # the adjoining marked crossing, the man along the bottom block sidewalk.
 return ((-155<=u<=155 and 155<=v<=207) or
         (155<=u<=207 and v>=155) or
         (-207<=u<=-155 and v<=207) or
         (-207<=u<=-140 and 140<=v<=207) or
         (140<=u<=207 and 140<=v<=207))

def person(key,t,draw=False):
 uv,tan,phase,turn=path(key,t);cfg=copy.deepcopy(rig.CONFIG[key])
 projected=np.array([.82*(tan[0]-tan[1]),.41*(tan[0]+tan[1])])/math.hypot(.82,.41)
 cfg['direction']=projected.tolist();rig.SPAN=routes[key]['span']
 joints,_,contacts=rig.pose(cfg,phase)
 sprite=None
 if draw:
  # Torso yaw is a restrained horizontal foreshortening/reflection about the
  # pelvis, while every limb is still solved in the current travel direction.
  facing=math.cos(turn*math.pi);scale=math.copysign(max(.24,abs(facing)),facing)
  use_layers=layers[key]
  # Reflect only source anatomy before binding, so legs retain their IK pose.
  if turn>0:
   use_layers=dict(use_layers)
   body=use_layers['body'];cx=cfg['pelvis'][0]
   use_layers['body']=body.transform(body.size,Image.Transform.AFFINE,(1/scale,0,cx-cx/scale,0,1,0),Image.Resampling.BICUBIC)
  sprite=rig.render(cfg,use_layers,phase)[0]
  sprite=sprite.resize((round(512*S),round(512*S)),Image.Resampling.LANCZOS)
 return world(*uv),sprite,joints,phase

cars={'让行车':dict(u=52,scale=.58,anchor=np.array([133,101]),file='让行车_透明素材.png'),
      '先行对向车':dict(u=-52,scale=1.07,anchor=np.array([66,54]),file='先行对向车_透明素材.png')}
for m in cars.values():
 im=Image.open(ROOT/'assets/video/素材/路口人车_v4'/m['file']).convert('RGBA')
 m['image']=im.resize((round(im.width*m['scale']),round(im.height*m['scale'])),Image.Resampling.LANCZOS)

def car_v(name,t):
 if name=='先行对向车':return 180+190*t
 if t<1.2:return 320+90*(1-t/1.2)**2
 if t<5.8:return 320.
 d=t-5.8;a=min(d/1.3,1.);integ=a**6-3*a**5+2.5*a**4
 distance=190*(1.3*integ if d<1.3 else d-.65)
 return 320-distance

def paste(image,sprite,pos):
 px,py=pos;ix=math.floor(px);iy=math.floor(py)
 shifted=sprite.transform((sprite.width+2,sprite.height+2),Image.Transform.AFFINE,(1,0,-(px-ix),0,1,-(py-iy)),Image.Resampling.BICUBIC)
 image.alpha_composite(shifted,(ix,iy))

def frame(t):
 im=background.copy();actors=[];shadow=Image.new('RGBA',im.size);sd=ImageDraw.Draw(shadow)
 for key in routes:
  root,sprite,joints,phase=person(key,t,True);actors.append((root[1],sprite,root-[256*S,438*S]))
  x,y=root;sd.ellipse((x-9,y-2,x+9,y+3),fill=(25,23,21,35))
  for side,off in [('near',0),('far',.5)]:
   fx,fy=root+(joints['toe_'+side]-[256,438])*S;rig.SPAN=routes[key]['span']
   contact=rig.step((phase+off)%1)[1]
   sd.ellipse((fx-4,fy-1,fx+4,fy+1.5),fill=(22,20,18,75 if contact else 26))
 for name,m in cars.items():
  v=car_v(name,t);root=world(m['u'],v)
  actors.append((root[1],m['image'],root-m['anchor']*m['scale']))
  corners=[tuple(world(m['u']+du,v+dv)+[3,3]) for du,dv in [(-22,-56),(22,-56),(22,56),(-22,56)]]
  sd.polygon(corners,fill=(18,17,16,68))
 im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(1.6)))
 for _,sprite,pos in sorted(actors,key=lambda a:a[0]):paste(im,sprite,pos)
 return im.convert('RGB')

def main():
 snapshots=[]
 for t in np.linspace(0,14,3361):
  for k in routes:
   root,_,j,phase=person(k,float(t));uv=unproject(root)
   for side in ['near','far']:
    toe=unproject(root+(j['toe_'+side]-[256,438])*S)
    assert paved(toe),(k,t,toe)
   for name,m in cars.items():
    assert not(abs(uv[0]-m['u'])<46 and abs(uv[1]-car_v(name,float(t)))<75),(k,t,name,uv)
  if abs(t-round(t))<1e-7:snapshots.append({'time':float(t),'people':{k:path(k,float(t))[0].tolist() for k in routes}})
 guide=background.copy();gd=ImageDraw.Draw(guide)
 for k,c in [('P01','#dc795f'),('P02','#559fc7')]:
  points=[tuple(world(*path(k,float(t))[0])) for t in np.linspace(0,14,200)];gd.line(points,fill=c,width=3)
 guide.save(OUT/'路线检查.png')
 checktimes=[0,4,6,7,8,10,12,13.9583];sheet=Image.new('RGB',(1280,4*385),(25,25,25));d=ImageDraw.Draw(sheet)
 for i,t in enumerate(checktimes):
  im=frame(t);im.save(OUT/f'检查_{t:.2f}.png');sheet.paste(im.resize((640,360)),((i%2)*640,(i//2)*385));d.text(((i%2)*640+10,(i//2)*385+365),f'{t:.2f}s',fill='white')
 sheet.save(OUT/'十四秒路线总览.jpg',quality=94)
 (OUT/'通行检查.json').write_text(json.dumps(dict(seconds=14,frames=336,fps=24,routes=routes,check_samples=3361,toes_on_pavement=True,car_pedestrian_overlap=False,walking_entire_shot=True,playback_rate=1,snapshots=snapshots),ensure_ascii=False,indent=2),encoding='utf-8')
 if '--check' in sys.argv:print('STREET14_ROUTES_OK',flush=True);return
 ff=os.environ.get('SHADER_FFMPEG','C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe')
 with (OUT/'路口人车_持续行走_14秒.mp4').open('w+b') as dest:
  enc=subprocess.Popen([ff,'-v','error','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','24','-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','17','-bf','0','-pix_fmt','yuv420p','-f','mp4','-fd','1','fd:'],stdin=subprocess.PIPE,stdout=dest,stderr=subprocess.PIPE)
  for n in range(336):
   im=frame(n/24);im.save(FRAMES/f'frame_{n:03d}.jpg',quality=96,subsampling=0);enc.stdin.write(im.tobytes())
   if n%48==0:print(f'STREET14 {n}/336',flush=True)
  enc.stdin.close();err=enc.stderr.read();assert enc.wait()==0,err.decode(errors='replace')
 print('STREET14_RENDERED',flush=True)

if __name__=='__main__':main()
