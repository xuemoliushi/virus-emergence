"""Six-second crossing: existing pedestrian rig and two lane-bound car cutouts."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
import numpy as np
import subprocess, math, json
import rig_pedestrians as rig

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'assets/video/素材/路口人车_v4'
OUT.mkdir(exist_ok=True)
PEOPLE=ROOT/'assets/video/素材/行人场景_v3_流畅快走'
rig.SPAN=.64;rig.T=.80;rig.STANCE=.60
FPS=24;DURATION=6;S=.19
SPEED=rig.SPAN/(rig.STANCE*rig.T)*rig.SCALE*S
D=np.array([.894427,.447214]);START=np.array([694.,554.]);END=START+D*SPEED*DURATION
layers={key:{name:Image.open(PEOPLE/key/'拆层'/(name+'.png')).convert('RGBA') for name in cfg['parts']} for key,cfg in rig.CONFIG.items()}
background=Image.open(ROOT/'assets/video/素材/路口完整背景_v3_样片匹配/路口背景_样片匹配_1920x1080.png').convert('RGBA')

CARS={
 '让行车':{
  'source':'car_a.png','scale':.58,'anchor':[133,101],'lane_u':52,
  'outline':[(11,87),(16,72),(35,59),(52,51),(62,30),(73,21),(96,10),(115,3),(131,1),(148,8),(166,5),(175,8),(193,20),(204,23),(214,23),(224,31),(229,42),(231,49),(229,54),(219,60),(216,70),(208,78),(196,81),(190,79),(113,112),(110,119),(102,127),(90,130),(83,127),(72,126),(56,120),(36,110),(19,101),(11,95)]},
 '先行对向车':{
  'source':'car_b.png','scale':1.07,'anchor':[66,54],'lane_u':-52,
  'outline':[(10,46),(16,38),(28,29),(34,15),(45,8),(56,3),(69,3),(78,5),(86,1),(96,5),(103,9),(107,15),(112,22),(117,26),(117,31),(112,34),(111,39),(108,44),(102,46),(99,44),(72,61),(70,66),(63,72),(56,72),(49,67),(39,66),(25,62),(13,57),(9,53)]}
}

def world(u,v):
    return np.array([960+.82*u-.82*v,540+.41*u+.41*v])
def unproject(p):
    x,y=np.array(p)-[960,540]
    return np.array([.5*(x/.82+y/.41),.5*(y/.41-x/.82)])

def car_state(name,t):
    if name=='让行车':
        if t<1.2:
            v=320+90*(1-t/1.2)**2
            speed=150*(1-t/1.2)
            state='approach_and_brake'
        elif t<3.75:
            v=320.;speed=0.;state='yield'
        else:
            dt=t-3.75
            v=320-80*dt*dt
            speed=160*dt
            state='accelerate_through'
    else:
        v=160+190*t;speed=190.;state='pass_before_pedestrian_enters_lane'
    return float(v),float(speed),state

def pedestrians(t):
    result=[]
    for key,d,origin,off in [('P01',D,START,0),('P02',-D,END,.5)]:
        phase=(t/rig.T+off)%1
        root=origin+d*SPEED*t+(np.array([-5.,10.]) if key=='P01' else np.array([5.,-10.]))
        result.append((key,phase,root))
    return result

# Hand-traced cutouts remove the legacy masks' road/shadow patch. Source pixels
# and source view are preserved; no flat sprite rotation or new image generation.
for name,meta in CARS.items():
    source=Image.open(ROOT/'assets/video/emergence_shader/art'/meta['source']).convert('RGBA')
    mask=Image.new('L',(source.width*4,source.height*4))
    ImageDraw.Draw(mask).polygon([(x*4,y*4) for x,y in meta['outline']],fill=255)
    mask=mask.resize(source.size,Image.Resampling.LANCZOS)
    arr=np.asarray(source).copy()
    arr[:,:,3]=(arr[:,:,3].astype(np.uint16)*np.asarray(mask).astype(np.uint16)//255).astype(np.uint8)
    rgb=arr[:,:,:3].astype(float)
    lum=rgb@np.array([.2126,.7152,.0722])
    neutral=np.stack([lum*1.025+1,lum*1.009+.5,lum*.985],axis=2)
    arr[:,:,:3]=np.clip(rgb*.15+neutral*.85,0,255).astype(np.uint8)
    cut=Image.fromarray(arr)
    cut.save(OUT/(name+'_透明素材.png'))
    meta['image']=cut.resize((round(source.width*meta['scale']),round(source.height*meta['scale'])),Image.Resampling.LANCZOS)

# Conservative ground rectangles: half car width 28, half length 65; allow 18
# along pedestrian travel and 10 across it. Check beyond the video sample rate.
clearance=[]
for t in np.linspace(0,6,1441):
    for name,meta in CARS.items():
        v,_,state=car_state(name,float(t))
        for key,_,root in pedestrians(float(t)):
            u_p,v_p=unproject(root)
            overlap=abs(u_p-meta['lane_u'])<46 and abs(v_p-v)<75
            assert not overlap,(float(t),name,key,float(u_p),float(v_p),v)
    if abs(t-round(t))<1e-7:
        clearance.append({'time':float(t),'cars':{name:{'u':meta['lane_u'],'v':car_state(name,float(t))[0],'state':car_state(name,float(t))[2]} for name,meta in CARS.items()}})

def paste_at(image,sprite,xy):
    px,py=xy;ix=math.floor(px);iy=math.floor(py)
    shifted=sprite.transform((sprite.width+2,sprite.height+2),Image.Transform.AFFINE,(1,0,-(px-ix),0,1,-(py-iy)),Image.Resampling.BICUBIC)
    image.alpha_composite(shifted,(ix,iy))

FF='C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe'
stream=(OUT/'路口人车_6秒_24fps.mp4').open('wb')
enc=subprocess.Popen([FF,'-hide_banner','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','24','-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','17','-pix_fmt','yuv420p','-movflags','frag_keyframe+empty_moov','-f','mp4','pipe:1'],stdin=subprocess.PIPE,stdout=stream,stderr=subprocess.PIPE)
previews=[]
for n in range(144):
    t=n/24
    image=background.copy()
    actors=[]
    shadow=Image.new('RGBA',image.size);sd=ImageDraw.Draw(shadow)
    for key,phase,root in pedestrians(t):
        sprite,joints,_,contacts=rig.render(rig.CONFIG[key],layers[key],phase)
        sprite=sprite.resize((round(512*S),round(512*S)),Image.Resampling.LANCZOS)
        actors.append((root[1],sprite,root-np.array([256,438])*S))
        x,y=root
        sd.ellipse((x-9,y-2,x+9,y+3),fill=(25,23,21,35))
        for side,off in [('near',0),('far',.5)]:
            h=rig.step((phase+off)%1)[0][1]-.045
            fx,fy=root+(joints['toe_'+side]-[256,438])*S
            alpha=round(80*math.exp(-h/.025))
            sd.ellipse((fx-4,fy-1,fx+4,fy+1.5),fill=(22,20,18,alpha))
    for name,meta in CARS.items():
        v,speed,state=car_state(name,t)
        root=world(meta['lane_u'],v)
        pos=root-np.array(meta['anchor'])*meta['scale']
        actors.append((root[1],meta['image'],pos))
        # Contact shadow is a road-plane parallelogram aligned with the lane.
        corners=[tuple(world(meta['lane_u']+du,v+dv)+[3,3]) for du,dv in [(-22,-56),(22,-56),(22,56),(-22,56)]]
        sd.polygon(corners,fill=(18,17,16,68))
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(2.0)))
    for depth,sprite,pos in sorted(actors,key=lambda actor:actor[0]):paste_at(image,sprite,pos)
    rgb=image.convert('RGB')
    enc.stdin.write(rgb.tobytes())
    previews.append(rgb.resize((960,540),Image.Resampling.LANCZOS))
    if n in [0,24,60,96,120,143]:rgb.save(OUT/f'场景检查_{n:03d}.png')
enc.stdin.close();err=enc.stderr.read();assert enc.wait()==0,err.decode(errors='replace');stream.close()
palette=previews[0].quantize(colors=160,dither=Image.Dither.NONE)
gif=[im.quantize(palette=palette,dither=Image.Dither.NONE) for im in previews]
dur=[round((n+1)*100/24)*10-round(n*100/24)*10 for n in range(144)]
gif[0].save(OUT/'路口人车_6秒.gif',save_all=True,append_images=gif[1:],duration=dur,loop=0,optimize=True,disposal=1)
report={'duration_seconds':6,'fps':24,'frames':144,'projection':'same parallel oblique ground plane as approved road draft',
 'lanes':{name:meta['lane_u'] for name,meta in CARS.items()},'car_a_yield_seconds':[1.2,3.75],
 'collision_check':'1441 time samples, inflated pedestrian/car ground rectangles, no overlap',
 'car_a_end_state':'Accelerating across intersection; continues into following pullback shot. Not fully out of far crossing at six seconds.',
 'sources':'Reused original car_a/car_b pixels; tighter silhouette masks and independently composited contact shadows.',
 'old_sample_replaced':False,'timeline':clearance}
(OUT/'人车检查.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('Rendered 144 frames. No pedestrian/car footprint overlap in 1441 time samples.')
