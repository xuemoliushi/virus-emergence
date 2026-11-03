"""Render already rigged sprites in place and across the approved crosswalk."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import subprocess, json, math
import rig_pedestrians as rig

ROOT=Path(__file__).resolve().parents[2]
OUT=rig.OUT
FONT=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',18)
FF='C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe'

sprites={key:[Image.open(OUT/key/f'{key}_walk_{n:02d}.png').convert('RGBA') for n in range(rig.N)] for key in ['P01','P02']}
FPS=20
assert abs(FPS*rig.T-rig.N)<1e-9
background=Image.open(ROOT/'assets/video/素材/路口完整背景_v3_样片匹配/路口背景_样片匹配_1920x1080.png').convert('RGBA')
scene_scale=.19
avatar_size=round(512*scene_scale)
avatars={key:[frame.resize((avatar_size,avatar_size),Image.Resampling.LANCZOS) for frame in frames] for key,frames in sprites.items()}
speed=rig.SPAN/(rig.STANCE*rig.T)*rig.SCALE*scene_scale
duration=12
start1=(694,554)
end1=(start1[0]+.894427*speed*duration,start1[1]+.447214*speed*duration)
frames=[]
for n in range(FPS*duration):
    t=n/FPS
    phase=n%24
    image=background.copy()
    actors=[]
    for key,d,origin,offset in [('P01',(.894427,.447214),start1,0),('P02',(-.894427,-.447214),end1,12)]:
        # Adjacent pedestrian tracks avoid body collisions at passing.
        lateral=(-5,10) if key=='P01' else (5,-10)
        root=(origin[0]+d[0]*speed*t+lateral[0],origin[1]+d[1]*speed*t+lateral[1])
        idx=(phase+offset)%24
        actors.append((root[1],key,idx,root))
    shadow=Image.new('RGBA',image.size)
    sd=ImageDraw.Draw(shadow)
    for _,key,idx,(x,y) in actors:
        sd.ellipse((x-9,y-2,x+9,y+3),fill=(25,23,21,45))
        joints,_,contacts=rig.pose(rig.CONFIG[key],idx/24)
        for side in ['near','far']:
            if contacts[side]:
                foot=joints['toe_'+side]
                fx=x+(foot[0]-256)*scene_scale
                fy=y+(foot[1]-438)*scene_scale
                sd.ellipse((fx-4,fy-1,fx+4,fy+1.5),fill=(22,20,18,85))
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(1.4)))
    for _,key,idx,(x,y) in sorted(actors):
        image.alpha_composite(avatars[key][idx],(round(x-256*scene_scale),round(y-438*scene_scale)))
    small=image.convert('RGB').resize((960,540),Image.Resampling.LANCZOS)
    frames.append(small)

# FFmpeg writes to stdout because this bundled build cannot open Unicode paths.
process=subprocess.Popen([FF,'-hide_banner','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s','960x540','-r',str(FPS),'-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','frag_keyframe+empty_moov','-f','mp4','pipe:1'],stdin=subprocess.PIPE,stdout=(OUT/'路口行走检查.mp4').open('wb'),stderr=subprocess.PIPE)
for image in frames:process.stdin.write(image.tobytes())
process.stdin.close()
error=process.stderr.read()
assert process.wait()==0,error.decode('utf-8',errors='replace')
palette=frames[0].quantize(colors=128,dither=Image.Dither.NONE)
gif_frames=[image.quantize(palette=palette,dither=Image.Dither.NONE) for image in frames[::2]]
gif_frames[0].save(OUT/'路口行走检查.gif',save_all=True,append_images=gif_frames[1:],duration=100,loop=0,optimize=True,disposal=1)
frames[100].save(OUT/'路口行走检查_5秒.png')

# Side-by-side clean sprite / skeleton animation, no scrolling to hide joints.
layers={}
for key,cfg in rig.CONFIG.items():
    layers[key]={name:Image.open(OUT/key/'拆层'/(name+'.png')).convert('RGBA') for name in cfg['parts']}
debug=[]
for n in range(24):
    im=Image.new('RGBA',(1024,512),'#ddd9d1')
    for key,x in [('P01',0),('P02',512)]:
        sprite=rig.render(rig.CONFIG[key],layers[key],n/24,True)[0]
        im.alpha_composite(sprite,(x,0))
    debug.append(im.convert('RGB'))
debug[0].save(OUT/'关节轨迹动画.gif',save_all=True,append_images=debug[1:],duration=50,loop=0,disposal=2)
print('Rendered 12 seconds / 240 frames; sprites are 24 phases at 20 fps.')
