"""Six-second 24fps crosswalk, continuous gait sampling and C2 joint motion."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
import numpy as np
import subprocess, shutil, json, math
import rig_pedestrians as rig

ROOT=Path(__file__).resolve().parents[2]
OLD=rig.OUT
OUT=ROOT/'assets/video/素材/行人场景_v3_流畅快走'
OUT.mkdir(exist_ok=True)
rig.OUT=OUT
rig.SPAN=.64
rig.T=.80
rig.STANCE=.60
FPS=24
DURATION=6
for key in ['P01','P02']:
    shutil.copy2(OLD/(key+'_站立源.png'),OUT/(key+'_站立源.png'))
rig.main()
layers={key:{name:Image.open(OUT/key/'拆层'/(name+'.png')).convert('RGBA') for name in cfg['parts']} for key,cfg in rig.CONFIG.items()}
background=Image.open(ROOT/'assets/video/素材/路口完整背景_v3_样片匹配/路口背景_样片匹配_1920x1080.png').convert('RGBA')
S=.19
PIXEL_SPEED=rig.SPAN/(rig.STANCE*rig.T)*rig.SCALE*S
START=np.array([694.,554.])
D=np.array([.894427,.447214])
END=START+D*PIXEL_SPEED*DURATION
FF='C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe'
video_file=(OUT/'路口行走_6秒_24fps.mp4').open('wb')
encoder=subprocess.Popen([FF,'-hide_banner','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r',str(FPS),'-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','17','-pix_fmt','yuv420p','-movflags','frag_keyframe+empty_moov','-f','mp4','pipe:1'],stdin=subprocess.PIPE,stdout=video_file,stderr=subprocess.PIPE)
previews=[]
for n in range(FPS*DURATION):
    t=n/FPS
    actors=[]
    for key,d,origin,off in [('P01',D,START,0),('P02',-D,END,.5)]:
        phase=(t/rig.T+off)%1
        sprite,joints,_,contacts=rig.render(rig.CONFIG[key],layers[key],phase)
        sprite=sprite.resize((round(512*S),round(512*S)),Image.Resampling.LANCZOS)
        lateral=np.array([-5.,10.]) if key=='P01' else np.array([5.,-10.])
        root=origin+d*PIXEL_SPEED*t+lateral
        actors.append((root[1],key,root,sprite,joints,contacts))
    image=background.copy()
    shadow=Image.new('RGBA',image.size)
    sd=ImageDraw.Draw(shadow)
    for _,key,(x,y),sprite,joints,contacts in actors:
        sd.ellipse((x-9,y-2,x+9,y+3),fill=(25,23,21,35))
        for side in ['near','far']:
            # Fade contact shadow as swing starts, avoiding a binary shadow pop.
            ankle=joints['ankle_'+side]
            fy=y+(joints['toe_'+side][1]-438)*S
            fx=x+(joints['toe_'+side][0]-256)*S
            # Track sole height from physical pose, not screen depth.
            phase=(t/rig.T+(0 if key=='P01' else .5)+(0 if side=='near' else .5))%1
            h=rig.step(phase)[0][1]-.045
            alpha=round(80*math.exp(-h/.025))
            sd.ellipse((fx-4,fy-1,fx+4,fy+1.5),fill=(22,20,18,alpha))
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(1.2)))
    for _,key,(x,y),sprite,joints,contacts in sorted(actors,key=lambda a:a[0]):
        # Subpixel placement avoids frame-to-frame rounding of root movement.
        px=x-256*S;py=y-438*S
        ix=math.floor(px);iy=math.floor(py)
        shifted=sprite.transform((sprite.width+2,sprite.height+2),Image.Transform.AFFINE,(1,0,-(px-ix),0,1,-(py-iy)),Image.Resampling.BICUBIC)
        image.alpha_composite(shifted,(ix,iy))
    rgb=image.convert('RGB')
    encoder.stdin.write(rgb.tobytes())
    previews.append(rgb.resize((960,540),Image.Resampling.LANCZOS))
    if n in [0,36,72,108,143]:rgb.save(OUT/f'场景检查_{n:03d}.png')
encoder.stdin.close()
err=encoder.stderr.read()
assert encoder.wait()==0,err.decode(errors='replace')
video_file.close()
palette=previews[0].quantize(colors=160,dither=Image.Dither.NONE)
gif=[im.quantize(palette=palette,dither=Image.Dither.NONE) for im in previews]
dur=[round((n+1)*100/FPS)*10-round(n*100/FPS)*10 for n in range(len(gif))]
gif[0].save(OUT/'路口行走_6秒.gif',save_all=True,append_images=gif[1:],duration=dur,loop=0,optimize=True,disposal=1)

# Compare velocities across every branch boundary; tests the reported jerk,
# not merely that repeated endpoint positions match.
checks={}
eps=1e-5
for key,cfg in rig.CONFIG.items():
    boundaries=[0,.5,rig.STANCE,(rig.STANCE+.5)%1]
    maximum=0
    for phase in boundaries:
        a=rig.pose(cfg,phase-eps)[0];b=rig.pose(cfg,phase)[0];c=rig.pose(cfg,phase+eps)[0]
        for name in b:
            v0=(b[name]-a[name])/eps
            v1=(c[name]-b[name])/eps
            maximum=max(maximum,float(np.linalg.norm(v1-v0)))
    assert maximum<.5,(key,maximum)
    checks[key]={'joint_velocity_boundary_difference_px_per_cycle':maximum,'no_duplicate_sprite_frame_sampling':True}
checks.update({'duration_seconds':DURATION,'fps':FPS,'video_frames':FPS*DURATION,
 'walk_speed_m_s':rig.SPAN/(rig.STANCE*rig.T),'old_speed_m_s':.6989247312,
 'cycle_seconds':rig.T,'rendering':'Exact phase re-rendered at every video frame, no integer sprite-index reuse',
 'changes':['quintic C2 foot trajectory','smooth pelvis constraint exchange','continuous toe roll','subpixel root placement','faded contact shadow','subtle torso lean and shoulder sway']})
(OUT/'流畅性检查.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(checks,ensure_ascii=False))
