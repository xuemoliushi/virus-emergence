"""Joint-controlled 2.5D cutout walk. Authored source masks and fixed-length IK.

No new generative images. Source idle images are retained, layer cuts and
joint locations are reviewable. Units for kinematics are meters.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
import math, json

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'assets/video/素材/行人关节修正_v2'
SIZE=512
N=24
T=1.20
STANCE=.62
SPAN=.52
SCALE=190.0
V=math.sqrt(.75)  # elevation 30 deg: vertical projection cos(elevation)
LIFT_HEIGHT=.085
TOE_OFF_ANGLE=0.0
HEEL_STRIKE_ANGLE=0.0
ARM_SWING=.32
FONT='C:/Windows/Fonts/msyh.ttc'
font=ImageFont.truetype(FONT,16)
small=ImageFont.truetype(FONT,12)

CONFIG={
 'P01':{
  'direction':[.894427,.447214], 'pelvis':[218,196], 'root':[219,350],
  'hip_near':[201,199], 'knee_near':[200,267], 'ankle_near':[201,329], 'toe_near':[215,351],
  'hip_far':[233,191], 'knee_far':[234,256], 'ankle_far':[231,318], 'toe_far':[250,340],
  'shoulder_near':[176,105], 'elbow_near':[171,156], 'wrist_near':[177,207], 'hand_near':[180,223],
  'shoulder_far':[250,91], 'elbow_far':[259,138], 'wrist_far':[260,184], 'hand_far':[256,201],
  'parts':{
   'body':[(174,8),(260,8),(266,69),(258,85),(255,143),(248,183),(231,205),(191,214),(181,196),(184,145),(185,107),(168,99),(176,76)],
   'thigh_near':[(194,191),(218,187),(218,278),(184,280),(186,245),(192,228)],
   'shin_near':[(186,258),(215,258),(218,335),(187,338)],
   'foot_near':[(189,326),(212,326),(218,337),(229,345),(230,357),(215,365),(197,360),(187,345)],
   'thigh_far':[(218,182),(252,180),(250,267),(218,268)],
   'shin_far':[(219,251),(250,251),(249,324),(218,326)],
   'foot_far':[(219,311),(249,307),(268,340),(263,355),(222,354)],
   'upper_near':[(158,87),(185,92),(188,154),(182,174),(158,170),(154,140)],
   'fore_near':[(157,147),(185,147),(190,202),(185,214),(166,212),(159,191)],
   'hand_near':[(164,197),(188,195),(195,220),(183,234),(170,222)],
   'upper_far':[(252,83),(263,83),(270,136),(268,150),(253,148)],
   'fore_far':[(248,130),(272,131),(272,186),(259,198),(249,186)],
   'hand_far':[(248,174),(272,172),(273,200),(257,213),(248,202)],
  }},
 'P02':{
  'direction':[-.894427,-.447214], 'pelvis':[209,201], 'root':[209,352],
  'hip_near':[193,207], 'knee_near':[196,282], 'ankle_near':[201,337], 'toe_near':[187,345],
  'hip_far':[225,202], 'knee_far':[226,281], 'ankle_far':[218,343], 'toe_far':[209,355],
  'shoulder_near':[176,124], 'elbow_near':[166,168], 'wrist_near':[160,209], 'hand_near':[158,223],
  'shoulder_far':[246,117], 'elbow_far':[256,161], 'wrist_far':[262,201], 'hand_far':[265,214],
  'parts':{
   'body':[(164,30),(249,30),(267,107),(250,121),(246,161),(239,179),(253,230),(251,271),(236,288),(188,287),(160,274),(164,224),(174,180),(176,147),(164,131)],
   # Thighs are covered by dress: only the below-hem leg texture is exposed.
   'shin_near':[(188,287),(209,287),(216,337),(197,349),(187,321)],
   'foot_near':[(183,330),(211,329),(222,351),(213,365),(193,366),(177,350)],
   'shin_far':[(212,287),(237,287),(235,315),(228,350),(207,350)],
   'foot_far':[(203,333),(231,332),(234,360),(218,375),(199,365)],
   'upper_near':[(162,110),(184,114),(183,154),(175,174),(155,171)],
   'fore_near':[(154,157),(177,160),(173,202),(170,216),(151,213)],
   'hand_near':[(151,200),(170,199),(173,222),(164,232),(151,225)],
   'upper_far':[(235,103),(256,108),(269,159),(250,172),(239,148)],
   'fore_far':[(248,150),(269,151),(277,204),(259,217),(251,197)],
   'hand_far':[(256,195),(277,195),(277,219),(265,232),(254,220)],
  }}
}

def polygon_layer(source,points):
    # Supersampled masks soften only cut edges, preserving original alpha.
    mask=Image.new('L',(source.width*3,source.height*3))
    ImageDraw.Draw(mask).polygon([(x*3,y*3) for x,y in points],fill=255)
    mask=mask.resize(source.size,Image.Resampling.LANCZOS)
    arr=np.asarray(source).copy()
    arr[:,:,3]=(arr[:,:,3].astype(np.uint16)*np.asarray(mask).astype(np.uint16)//255).astype(np.uint8)
    return Image.fromarray(arr)

def tone(source):
    a=np.asarray(source).copy()
    rgb=a[:,:,:3].astype(float)
    l=rgb@np.array([.2126,.7152,.0722])
    # Gentle near-monochrome movie palette; retain tiny natural hue variation.
    neutral=np.stack([l*1.025+1,l*1.009+.5,l*.985],axis=2)
    a[:,:,:3]=np.clip(neutral*.88+rgb*.12,0,255).astype(np.uint8)
    return Image.fromarray(a)

def trim_bone(layer,a,b,radius,extra=5):
    """Remove neighboring-leg fragments and square clipping flaps."""
    yy,xx=np.mgrid[:layer.height,:layer.width]
    a=np.array(a,dtype=float);b=np.array(b,dtype=float)
    v=b-a;length=np.linalg.norm(v);e=v/length
    dx=xx-a[0];dy=yy-a[1]
    along=dx*e[0]+dy*e[1]
    across=np.abs(dx*(-e[1])+dy*e[0])
    end_distance=np.maximum(np.maximum(-along-extra*.3,along-length-extra*.3),0)
    capsule_distance=np.sqrt(across*across+end_distance*end_distance)
    coverage=np.clip(radius+.7-capsule_distance,0,1)
    arr=np.asarray(layer).copy()
    arr[:,:,3]=(arr[:,:,3]*coverage).astype(np.uint8)
    return Image.fromarray(arr)

def bone_warp(layer,s0,s1,t0,t1,width=1.0):
    s0=np.array(s0,dtype=float); s1=np.array(s1,dtype=float)
    t0=np.array(t0,dtype=float); t1=np.array(t1,dtype=float)
    sv=s1-s0; tv=t1-t0
    sl=np.linalg.norm(sv); tl=np.linalg.norm(tv)
    se=sv/sl; te=tv/tl
    sb=np.column_stack([se,[-se[1],se[0]]])
    tb=np.column_stack([te*tl/sl,np.array([-te[1],te[0]])*width])
    a=tb@sb.T
    inv=np.linalg.inv(a)
    offset=s0-inv@t0
    return layer.transform((SIZE,SIZE),Image.Transform.AFFINE,
        (inv[0,0],inv[0,1],offset[0],inv[1,0],inv[1,1],offset[1]),
        Image.Resampling.BICUBIC)

def smooth5(u):
    u=max(0.,min(1.,u))
    return u*u*u*(10+u*(-15+6*u))

def roll_angle(p):
    p=p%1
    if p<STANCE:
        strike=HEEL_STRIKE_ANGLE*(1-smooth5(p/.11))
        push=TOE_OFF_ANGLE*smooth5((p-(STANCE-.15))/.15)
        return strike+push
    return TOE_OFF_ANGLE+(HEEL_STRIKE_ANGLE-TOE_OFF_ANGLE)*smooth5((p-STANCE)/(1-STANCE))

def step(p):
    p=p%1
    if p<STANCE:
        f=SPAN/2-SPAN*p/STANCE
        h=.045
        angle=roll_angle(p)
        if angle>0:
            # Toe stays planted while heel and ankle roll up before toe-off.
            f+=.075*(1-math.cos(angle))
            h+=.075*math.sin(angle)
        contact=True
    else:
        u=(p-STANCE)/(1-STANCE)
        # Quintic swing matches stance position, velocity AND acceleration.
        m=-SPAN*(1-STANCE)/STANCE
        smooth=smooth5(u)
        x0=-SPAN/2+.075*(1-math.cos(TOE_OFF_ANGLE))
        x1=SPAN/2
        f=x0+m*u+(x1-x0-m)*smooth
        h0=.045+.075*math.sin(TOE_OFF_ANGLE)
        h=h0+(.045-h0)*smooth+LIFT_HEIGHT*64*u**3*(1-u)**3
        contact=False
    return np.array([f,h]),contact

def ik(hip,ankle,l1=.44,l2=.44):
    delta=ankle-hip
    dist=np.linalg.norm(delta)
    assert dist<l1+l2 and dist>abs(l1-l2)
    e=delta/dist
    along=(l1*l1-l2*l2+dist*dist)/(2*dist)
    height=math.sqrt(max(0,l1*l1-along*along))
    perp=np.array([-e[1],e[0]]) # human knee bends forward in sagittal plane
    return hip+e*along+perp*height

def pose(cfg,phase):
    d=np.array(cfg['direction'])
    root=np.array([256.,438.])
    # Smooth minimum removes the derivative cusp when support legs exchange.
    # Stay below the IK extension limit so the knee never locks/snaps straight.
    supporting=[step(phase+offset)[0] for offset in [0,.5]]
    limits=[float(a[1]+math.sqrt(.870**2-a[0]**2)) for a in supporting]
    lo=min(limits)
    hip_height=lo-.012*math.log(sum(math.exp(-(h-lo)/.012) for h in limits))
    pelvis=np.array([0.,hip_height])
    source_pelvis=np.array(cfg['pelvis'])
    def project(sagittal,lateral=np.zeros(2)):
        return root+lateral+d*(sagittal[0]*SCALE)+np.array([0.,-sagittal[1]*SCALE*V])
    joints={'pelvis':project(pelvis)}
    physical={}; contacts={}; arm_bones={}
    for side,off in [('near',0),('far',.5)]:
        lateral=np.array(cfg['hip_'+side])-source_pelvis
        # Preserve the projected transverse separation of hips, not source height.
        lateral=np.array([lateral[0],lateral[1]*.55])
        foot,contact=step(phase+off)
        hip=pelvis.copy()
        knee=ik(hip,foot)
        physical[side]={'hip':hip.tolist(),'knee':knee.tolist(),'ankle':foot.tolist()}
        contacts[side]=contact
        for name,val in [('hip',hip),('knee',knee),('ankle',foot)]:
            joints[name+'_'+side]=project(val,lateral)
        # Shoe heel/toe roll occurs during swing; stance sole stays on ground.
        angle=roll_angle(phase+off)
        toe=project(foot+np.array([.075*math.cos(angle),-.075*math.sin(angle)]),lateral)+np.array([0,8.2])
        joints['toe_'+side]=toe
        # Shoulder source offsets rigidly follow torso. Opposite arm swing.
        shoulder_offset=np.array(cfg['shoulder_'+side])-source_pelvis
        lean=.018*d[0]+.010*math.sin(2*math.pi*phase)
        rotation=np.array([[math.cos(lean),-math.sin(lean)],[math.sin(lean),math.cos(lean)]])
        shoulder=project(pelvis)+rotation@shoulder_offset
        theta=-ARM_SWING*math.cos(2*math.pi*(phase+off))
        arm_sag=np.array([.30*math.sin(theta),-.30*math.cos(theta)])
        fore_sag=np.array([.27*math.sin(theta+.17),-.27*math.cos(theta+.17)])
        elbow=shoulder+d*(arm_sag[0]*SCALE)+np.array([0,-arm_sag[1]*SCALE*V])
        wrist=elbow+d*(fore_sag[0]*SCALE)+np.array([0,-fore_sag[1]*SCALE*V])
        hand=wrist+(wrist-elbow)/np.linalg.norm(wrist-elbow)*15
        joints.update({'shoulder_'+side:shoulder,'elbow_'+side:elbow,'wrist_'+side:wrist,'hand_'+side:hand})
        arm_bones[side]=[.30,.27]
    return joints,physical,contacts

def render(cfg,layers,phase,skeleton=False,joint_override=None):
    j,physical,contacts=pose(cfg,phase)
    if joint_override is not None:
        j={name:np.asarray(value,dtype=float) for name,value in joint_override.items()}
    frame=Image.new('RGBA',(SIZE,SIZE))
    def add(part,a,b):
        frame.alpha_composite(bone_warp(layers[part],cfg[a],cfg[b],j[a],j[b]))
    def leg(side):
        if 'thigh_'+side in layers: add('thigh_'+side,'hip_'+side,'knee_'+side)
        else:
            # The dress hides source thighs. Continue its calf texture upward
            # behind the hem so the exposed knee never detaches from the dress.
            frame.alpha_composite(bone_warp(layers['shin_'+side],cfg['knee_'+side],cfg['ankle_'+side],j['hip_'+side],j['knee_'+side],width=1.12))
        # Rounded knee overlap joins rigid cutouts without a rectangular flap.
        kn=j['knee_'+side]
        patch=Image.new('RGBA',(SIZE,SIZE))
        pd=ImageDraw.Draw(patch)
        is_female='thigh_'+side not in layers
        color=(166,163,154,255) if is_female else (67,67,65,255)
        radius=9 if is_female else 10
        pd.ellipse((kn[0]-radius,kn[1]-radius,kn[0]+radius,kn[1]+radius),fill=color)
        frame.alpha_composite(patch)
        add('shin_'+side,'knee_'+side,'ankle_'+side)
        add('foot_'+side,'ankle_'+side,'toe_'+side)
    def arm(side):
        add('upper_'+side,'shoulder_'+side,'elbow_'+side)
        add('fore_'+side,'elbow_'+side,'wrist_'+side)
        add('hand_'+side,'wrist_'+side,'hand_'+side)
    arm('far')
    # Depth order swaps as feet pass; near-side hip stays anatomically identified.
    leg('far');leg('near')
    # Very small forward lean and shoulder sway keep the torso from reading
    # as a rigid vertical sticker; shoulder pivots follow the same transform.
    source_shoulder=(np.array(cfg['shoulder_near'])+np.array(cfg['shoulder_far']))*.5
    target_shoulder=(j['shoulder_near']+j['shoulder_far'])*.5
    body=bone_warp(layers['body'],cfg['pelvis'],source_shoulder,j['pelvis'],target_shoulder)
    frame.alpha_composite(body)
    arm('near')
    if skeleton:
        dr=ImageDraw.Draw(frame)
        for side,color in [('near','#ef805d'),('far','#55b7d2')]:
            for names in [('hip','knee','ankle','toe'),('shoulder','elbow','wrist','hand')]:
                pts=[tuple(j[n+'_'+side]) for n in names]
                dr.line(pts,fill=color,width=3)
                for name,pt in zip(names,pts):
                    dr.ellipse((pt[0]-4,pt[1]-4,pt[0]+4,pt[1]+4),fill=color)
                    dr.text((pt[0]+5,pt[1]-7),name,fill=color,font=small)
        dr.ellipse((j['pelvis'][0]-4,j['pelvis'][1]-4,j['pelvis'][0]+4,j['pelvis'][1]+4),fill='white')
    return frame,j,physical,contacts

def main():
    report={}
    preview_frames={}
    for key,cfg in CONFIG.items():
        dest=OUT/key; dest.mkdir(exist_ok=True)
        layerdir=dest/'拆层';layerdir.mkdir(exist_ok=True)
        source=tone(Image.open(OUT/(key+'_站立源.png')).convert('RGBA'))
        layers={name:polygon_layer(source,points) for name,points in cfg['parts'].items()}
        if key=='P01':
            for side in ['near','far']:
                layers['thigh_'+side]=trim_bone(layers['thigh_'+side],cfg['hip_'+side],cfg['knee_'+side],14,6)
                layers['shin_'+side]=trim_bone(layers['shin_'+side],cfg['knee_'+side],cfg['ankle_'+side],11.5,4)
                layers['upper_'+side]=trim_bone(layers['upper_'+side],cfg['shoulder_'+side],cfg['elbow_'+side],12 if side=='near' else 8.5,5)
                layers['fore_'+side]=trim_bone(layers['fore_'+side],cfg['elbow_'+side],cfg['wrist_'+side],10 if side=='near' else 7,5)
        for name,layer in layers.items():layer.save(layerdir/(name+'.png'))
        # Bind positions marked on actual source image.
        marked=Image.new('RGBA',source.size,'#e9e5db');marked.alpha_composite(source)
        md=ImageDraw.Draw(marked)
        for name,pt in cfg.items():
            if not isinstance(pt,list) or len(pt)!=2 or name in ['direction','root']:continue
            c='#ae4339' if 'near' in name else '#266a8a'
            md.ellipse((pt[0]-3,pt[1]-3,pt[0]+3,pt[1]+3),fill=c)
            md.text((pt[0]+4,pt[1]-8),name,fill=c,font=small)
        marked.resize((source.width*2,source.height*2)).save(dest/'源图关节标定.png')
        frames=[];tracks=[];skels=[]
        maxerr=0
        for n in range(N):
            phase=n/N
            frame,j,physical,contacts=render(cfg,layers,phase)
            frame.save(dest/f'{key}_walk_{n:02d}.png')
            frames.append(frame)
            tracks.append({'frame':n,'phase':phase,'joints_pixels':{k:[round(float(x),4) for x in v] for k,v in j.items()},'joints_meters':physical,'contact':contacts})
            for side,data in physical.items():
                a=np.array(data['hip']);b=np.array(data['knee']);c=np.array(data['ankle'])
                maxerr=max(maxerr,abs(np.linalg.norm(b-a)-.44),abs(np.linalg.norm(c-b)-.44))
            if n%3==0:
                skels.append(render(cfg,layers,phase,True)[0])
        # Exact loop periodicity, including all joints at phase 0 and phase 1.
        j0=pose(cfg,0)[0];j1=pose(cfg,1)[0]
        looperr=max(float(np.linalg.norm(j0[k]-j1[k])) for k in j0)
        drift=[]
        for side,offset in [('near',0),('far',.5)]:
            # During stance relative foot speed exactly cancels root travel.
            q=np.linspace(.02,STANCE-.02,20)
            world=[step(float(v))[0][0]+SPAN/STANCE*float(v) for v in q]
            drift.append(float(max(world)-min(world)))
        idle=Image.new('RGBA',(SIZE,SIZE))
        # Actual source standing image is retained as idle, same pelvis anchor.
        shift=pose(cfg,0)[0]['pelvis']-np.array(cfg['pelvis'])
        idle=source.transform((SIZE,SIZE),Image.Transform.AFFINE,(1,0,-shift[0],0,1,-shift[1]),Image.Resampling.BICUBIC)
        idle.save(dest/f'{key}_idle.png')
        sheet=Image.new('RGBA',(SIZE*6,SIZE*4))
        for n,frame in enumerate(frames):sheet.alpha_composite(frame,((n%6)*SIZE,(n//6)*SIZE))
        sheet.save(dest/f'{key}_walk_sheet_6x4.png')
        # Opaque QA sheet; indices indicate temporal sequence.
        qa=Image.new('RGB',(SIZE*4,SIZE*2),'#e9e5db')
        for n,frame in enumerate(skels):
            qa.paste(frame,((n%4)*SIZE,(n//4)*SIZE),frame)
            ImageDraw.Draw(qa).text(((n%4)*SIZE+20,(n//4)*SIZE+16),f'frame {n*3:02d}',font=font,fill='#333333')
        qa.resize((1536,768)).save(dest/'步态关节检查.png')
        report[key]={'frames':N,'canvas':[SIZE,SIZE],'cycle_seconds':T,'thigh_length_m':.44,'shin_length_m':.44,
          'max_leg_length_error_m':maxerr,'loop_joint_error_px':looperr,'stance_world_foot_drift_m':max(drift),
          'stride_span_m':SPAN,'stance_fraction':STANCE,'root_speed_m_s':SPAN/(STANCE*T),
          'limitations':'2D cutout rig; no new camera rotation. Numeric foot constraints do not prove silhouette or shadow quality.'}
        assert maxerr<1e-9 and looperr<1e-5 and max(drift)<1e-9
        (dest/'关节轨迹.json').write_text(json.dumps(tracks,ensure_ascii=False,indent=2),encoding='utf-8')
        preview_frames[key]=frames
    (OUT/'绑定参数.json').write_text(json.dumps(CONFIG,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'运动学校验.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    # Close-up actual rendered 24-phase animation; also retain deterministic frames.
    closeups=[]
    for n in range(N):
        im=Image.new('RGBA',(900,512),'#e7e3da')
        dr=ImageDraw.Draw(im)
        dr.line((0,438,900,438),fill='#aaa598',width=1)
        for key,x in [('P01',-10),('P02',420)]:
            im.alpha_composite(preview_frames[key][n],(x,0))
        closeups.append(im.convert('RGB'))
    durations=[round((i+1)*T/N*100)*10-round(i*T/N*100)*10 for i in range(N)]
    closeups[0].save(OUT/'关节步态近景.gif',save_all=True,append_images=closeups[1:],duration=durations,loop=0,disposal=2)
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
