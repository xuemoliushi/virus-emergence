"""Bounded crosswalk routes, different walking speeds and continuous arrival."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFilter
import numpy as np
import math,json,subprocess,sys
import rig_pedestrians as rig

ROOT=Path(__file__).resolve().parents[2]
CONTINUOUS='--continuous' in sys.argv
OUT=ROOT/('assets/video/素材/路口人车_v6_持续行走' if CONTINUOUS else 'assets/video/素材/路口人车_v5_错速与到达')
STEM='路口人车_持续行走_6秒' if CONTINUOUS else '路口人车_错速停步_6秒'
OUT.mkdir(exist_ok=True)
PREVIOUS=ROOT/'assets/video/素材/路口人车_v4'
PEOPLE=ROOT/'assets/video/素材/行人场景_v3_流畅快走'
FPS=24;SECONDS=6;S=.19
rig.STANCE=.60
rig.LIFT_HEIGHT=.020
rig.TOE_OFF_ANGLE=math.radians(50)
rig.HEEL_STRIKE_ANGLE=math.radians(-8)
rig.ARM_SWING=.22
routes={
 'P01':{'start_u':-126.,'end_u':126.,'v':190.,'speed':1.45,'span':.68,'phase_offset':.07},
 'P02':{'start_u':126.,'end_u':-126.,'v':170.,'speed':1.18,'span':.62,'phase_offset':.42}}
if CONTINUOUS:
    routes={
      'P01':{'start_u':-130.,'end_u':0.,'v':190.,'speed':1.02,'span':.68,'phase_offset':.07},
      'P02':{'start_u':134.,'end_u':0.,'v':170.,'speed':1.10,'span':.62,'phase_offset':.42}}
    for key,route in routes.items():
        sign=1 if key=='P01' else -1
        route['end_u']=route['start_u']+sign*route['speed']*SECONDS*rig.SCALE*S/math.hypot(.82,.41)
layers={key:{name:Image.open(PEOPLE/key/'拆层'/(name+'.png')).convert('RGBA') for name in cfg['parts']} for key,cfg in rig.CONFIG.items()}
background=Image.open(ROOT/'assets/video/素材/路口完整背景_v3_样片匹配/路口背景_样片匹配_1920x1080.png').convert('RGBA')

def world(u,v):return np.array([960+.82*u-.82*v,540+.41*u+.41*v])
def unproject(p):
    x,y=np.array(p)-[960,540]
    return np.array([.5*(x/.82+y/.41),.5*(y/.41-x/.82)])
def integral5(u):return u**6-3*u**5+2.5*u**4

def progress(route,t):
    if CONTINUOUS:
        # The camera cuts at six seconds while both people are still walking.
        # Speed itself keeps the entire footpath on pavement; no clamp or idle.
        d=route['speed']*max(0.,t)
        sign=1 if route['end_u']>route['start_u'] else -1
        u=route['start_u']+sign*d*rig.SCALE*S/math.hypot(.82,.41)
        phase=(route['phase_offset']+d/(route['span']/rig.STANCE))%1
        return world(u,route['v']),phase,0.,None,route['speed']
    length=float(np.linalg.norm(world(route['end_u'],route['v'])-world(route['start_u'],route['v']))/(rig.SCALE*S))
    v=route['speed'];a=.20;b=.40
    arrival=length/v+(a+b)*.5
    decel=arrival-b
    if t<=0:d=0.;speed=0.
    elif t<a:
        u=t/a;d=v*a*integral5(u);speed=v*rig.smooth5(u)
    elif t<decel:d=v*(t-.5*a);speed=v
    elif t<arrival:
        u=(t-decel)/b;d=length-.5*v*b+v*b*(u-integral5(u));speed=v*(1-rig.smooth5(u))
    else:d=length;speed=0.
    u=route['start_u']+(route['end_u']-route['start_u'])*d/length
    phase=(route['phase_offset']+d/(route['span']/rig.STANCE))%1
    blend=1-rig.smooth5(speed/v)
    return world(u,route['v']),phase,blend,arrival,speed

def pose_person(key,t,draw=False):
    route=routes[key];cfg=rig.CONFIG[key]
    root,phase,blend,arrival,speed=progress(route,t)
    rig.SPAN=route['span']
    joints,_,contacts=rig.pose(cfg,phase)
    source_root=np.array(cfg['root'])
    idle={name:np.array(cfg[name],dtype=float)-source_root+[256,438] for name in joints if name in cfg}
    result={name:value*(1-blend)+idle[name]*blend for name,value in joints.items()}
    if draw:
        sprite=rig.render(cfg,layers[key],phase,joint_override=result)[0]
        sprite=sprite.resize((round(512*S),round(512*S)),Image.Resampling.LANCZOS)
    else:sprite=None
    return root,sprite,result,phase,blend,speed

cars={
 '让行车':{'u':52,'scale':.58,'anchor':np.array([133,101]),'file':'让行车_透明素材.png'},
 '先行对向车':{'u':-52,'scale':1.07,'anchor':np.array([66,54]),'file':'先行对向车_透明素材.png'}}
for meta in cars.values():
    im=Image.open(PREVIOUS/meta['file']).convert('RGBA')
    meta['image']=im.resize((round(im.width*meta['scale']),round(im.height*meta['scale'])),Image.Resampling.LANCZOS)

def car_position(name,t):
    if name=='让行车':
        release=4.95 if CONTINUOUS else 3.55
        if t<1.2:return 320+90*(1-t/1.2)**2
        if t<release:return 320.
        return 320-80*(t-release)**2
    return 180+190*t

def paste(image,sprite,pos):
    px,py=pos;ix=math.floor(px);iy=math.floor(py)
    shifted=sprite.transform((sprite.width+2,sprite.height+2),Image.Transform.AFFINE,(1,0,-(px-ix),0,1,-(py-iy)),Image.Resampling.BICUBIC)
    image.alpha_composite(shifted,(ix,iy))

# Validate route bounds with actual animated toe points, including arrival blend.
min_margin=1e9;max_root_error=0.;snapshot=[]
for t in np.linspace(0,6,1441):
    for key in routes:
        root,_,joints,phase,blend,speed=pose_person(key,float(t))
        u,v=unproject(root)
        root_limit=138 if CONTINUOUS else 126.0001
        assert -root_limit<=u<=root_limit and 155<=v<=207
        if CONTINUOUS:
            assert speed>0 and blend==0
            later=progress(routes[key],float(t)+1/24)[0]
            actual_speed=np.linalg.norm(later-root)*24/(rig.SCALE*S)
            assert abs(actual_speed-routes[key]['speed'])<1e-8
        for side in ['near','far']:
            toe=root+(joints['toe_'+side]-[256,438])*S
            tu,tv=unproject(toe)
            assert -150<tu<150 and 155<tv<207,(key,float(t),tu,tv)
            min_margin=min(min_margin,150-abs(tu),tv-155,207-tv)
        for name,meta in cars.items():
            overlap=abs(u-meta['u'])<46 and abs(v-car_position(name,float(t)))<75
            assert not overlap,(key,name,float(t),u,v)
        if not CONTINUOUS and t>=progress(routes[key],0)[3]:
            expected=world(routes[key]['end_u'],routes[key]['v'])
            max_root_error=max(max_root_error,float(np.linalg.norm(root-expected)))
    if abs(t-round(t))<1e-6:
        snapshot.append({'time':float(t),'people':{key:{'uv':unproject(progress(route,float(t))[0]).tolist(),'speed_m_s':progress(route,float(t))[4],'idle_blend':progress(route,float(t))[2]} for key,route in routes.items()}})
assert max_root_error<1e-8

# Reviewable route map, kept out of rendered movie.
guide=background.copy();gd=ImageDraw.Draw(guide)
for key,route in routes.items():
    a=world(route['start_u'],route['v']);b=world(route['end_u'],route['v'])
    color='#dc795f' if key=='P01' else '#559fc7'
    gd.line([tuple(a),tuple(b)],fill=color,width=3)
    for p in [a,b]:gd.ellipse((p[0]-5,p[1]-5,p[0]+5,p[1]+5),fill=color)
guide.resize((960,540),Image.Resampling.LANCZOS).save(OUT/'过街路线检查.png')

FF='C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe'
stream=(OUT/(STEM+'.mp4')).open('wb')
enc=subprocess.Popen([FF,'-hide_banner','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','24','-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','17','-pix_fmt','yuv420p','-movflags','frag_keyframe+empty_moov','-f','mp4','pipe:1'],stdin=subprocess.PIPE,stdout=stream,stderr=subprocess.PIPE)
previews=[]
for n in range(144):
    t=n/24;image=background.copy();actors=[]
    shadow=Image.new('RGBA',image.size);sd=ImageDraw.Draw(shadow)
    for key in routes:
        root,sprite,joints,phase,blend,speed=pose_person(key,t,True)
        actors.append((root[1],sprite,root-[256*S,438*S]))
        x,y=root
        sd.ellipse((x-9,y-2,x+9,y+3),fill=(25,23,21,35))
        for side,off in [('near',0),('far',.5)]:
            fx,fy=root+(joints['toe_'+side]-[256,438])*S
            rig.SPAN=routes[key]['span']
            contact=rig.step((phase+off)%1)[1]
            alpha=round(75*(blend+(1-blend)*(1.0 if contact else .35)))
            sd.ellipse((fx-4,fy-1,fx+4,fy+1.5),fill=(22,20,18,alpha))
    for name,meta in cars.items():
        v=car_position(name,t);root=world(meta['u'],v)
        actors.append((root[1],meta['image'],root-meta['anchor']*meta['scale']))
        corners=[tuple(world(meta['u']+du,v+dv)+[3,3]) for du,dv in [(-22,-56),(22,-56),(22,56),(-22,56)]]
        sd.polygon(corners,fill=(18,17,16,68))
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(1.6)))
    for _,sprite,pos in sorted(actors,key=lambda a:a[0]):paste(image,sprite,pos)
    rgb=image.convert('RGB');enc.stdin.write(rgb.tobytes())
    previews.append(rgb.resize((960,540),Image.Resampling.LANCZOS))
    if n in [0,36,72,108,132,143]:rgb.save(OUT/f'场景检查_{n:03d}.png')
enc.stdin.close();err=enc.stderr.read();assert enc.wait()==0,err.decode(errors='replace');stream.close()
palette=previews[0].quantize(colors=160,dither=Image.Dither.NONE)
gif=[im.quantize(palette=palette,dither=Image.Dither.NONE) for im in previews]
dur=[round((n+1)*100/24)*10-round(n*100/24)*10 for n in range(144)]
gif[0].save(OUT/(STEM+'.gif'),save_all=True,append_images=gif[1:],duration=dur,loop=0,optimize=True,disposal=1)
report={'duration_seconds':6,'fps':24,'frames':144,'people':{key:{**route,'arrival_seconds':progress(route,0)[3]} for key,route in routes.items()},
 'paths':'Both routes remain in crossing/sidewalk strip abs(u)<150, v=155..207. In continuous mode the shot ends mid-walk, no arrival stop.',
 'toe_check':'Both animated toe positions checked in walkable strip at 1441 time samples.',
 'minimum_toe_margin_world_units':float(min_margin),'post_arrival_root_drift_px':None if CONTINUOUS else max_root_error,
 'walking_entire_shot':CONTINUOUS,'idle_blend_used':not CONTINUOUS,'car_release_seconds':4.95 if CONTINUOUS else 3.55,
 'car_pedestrian_overlap':False,'timeline':snapshot,'gait':'Distance-driven independent phase, heel-strike and toe-off roll; continuous mode has no deceleration, no idle pose, no frozen frames.'}
(OUT/'路线与通行检查.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({key:{'speed':route['speed'],'arrival':progress(route,0)[3]} for key,route in routes.items()}))
print('Validated footpath bounds, motion behavior, and vehicle clearance at 1441 timestamps.')
