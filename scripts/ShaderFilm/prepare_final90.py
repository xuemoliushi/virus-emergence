"""Assemble the approved shots into an independent, reproducible 90 s project."""
from pathlib import Path
import shutil,re,json,subprocess,hashlib,os,sys
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'assets/video/emergence_shader';OUT=ROOT/'assets/video/emergence_final90'
OUT.mkdir(exist_ok=True);(OUT/'qa').mkdir(exist_ok=True);(OUT/'street').mkdir(exist_ok=True)
shutil.copytree(SRC/'shaders',OUT/'shaders',dirs_exist_ok=True)
ground_frag=(OUT/'shaders/ground.frag').read_text('utf-8').replace('uniform float uHaze;','uniform float uHaze;\nuniform float uFeather;').replace('frag=vec4(c,uOpacity);','float edge=smoothstep(0.,.085,min(min(vUV.x,1.-vUV.x),min(vUV.y,1.-vUV.y)));\n frag=vec4(c,uOpacity*mix(1.,edge,uFeather));')
(OUT/'shaders/ground.frag').write_text(ground_frag,encoding='utf-8')
shutil.copy2(SRC/'flight-cycle.js',OUT/'flight-cycle.js')
shutil.copytree(SRC/'flock_v2',OUT/'flock',dirs_exist_ok=True,ignore=shutil.ignore_patterns('motion.f32','manifest.json'))

def replace(s,a,b):
    if a not in s:raise ValueError('Missing source anchor: '+a[:90])
    return s.replace(a,b)

# Longer real-time boids simulation. Motion is not slowed to fill the film.
sim=(ROOT/'scripts/ShaderFilm/prepare_dense_flock.py').read_text('utf-8')
sim=replace(sim,"OUT = ROOT / 'assets/video/emergence_shader/flock_v2'","OUT = ROOT / 'assets/video/emergence_final90/flock'")
sim=replace(sim,'FPS, SECONDS, SEED = 24, 22, 1987','FPS, SECONDS, SEED = 24, 43, 1987')
sim=sim.replace('t >= 15','t >= 31.6').replace('t-15','t-31.6').replace('hero_leaves_neighbourhood_at=15','hero_leaves_neighbourhood_at=31.6')
exec(compile(sim,str(ROOT/'scripts/ShaderFilm/prepare_dense_flock.py'),'exec'),{'__file__':str(ROOT/'scripts/ShaderFilm/prepare_dense_flock.py'),'__name__':'__main__'})

# Robust projected bounds include both depth groups. Smooth over +/-1 second,
# then save camera data alongside the deterministic animation cache.
meta=json.loads((OUT/'flock/manifest.json').read_text('utf-8'))
motion=np.fromfile(OUT/'flock/motion.f32',dtype='<f4').reshape(meta['frame_count'],meta['count'],7)
framing=[]
for i,p in enumerate(motion):
    pp=p[:meta['hero']];x=960+1450*(pp[:,0]-45*i/24)/pp[:,2];y=450-1450*pp[:,1]/pp[:,2]
    x0,x1=np.quantile(x,[.01,.99]);y0,y1=np.quantile(y,[.01,.99])
    framing.append([(x0+x1)/2,(y0+y1)/2,min(1.,1480/(x1-x0),710/(y1-y0))])
f=np.asarray(framing);kernel=np.exp(-.5*(np.arange(-24,25)/11)**2);kernel/=kernel.sum()
f=np.column_stack([np.convolve(np.pad(f[:,j],24,mode='edge'),kernel,'valid') for j in range(3)])
meta['framing']=f.tolist();meta['framing_notes']='1st–99th percentile projected group bounds, symmetric one-second smoothing; subject focus only during motivated push.'
(OUT/'flock/manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')

dense=(SRC/'flock_v2/dense-flock.js').read_text('utf-8')
for a,b in [("base='flock_v2/'","base='flock/'"),('(t-5.3)/3.2','(t-18.0)/4.0'),('(t-12.0)/2.4','(t-32.0)/2.4'),
 ('projectAt(15)','projectAt(36)'),('(t-14.4)/1.2','(t-34.4)/3.2'),('t<14.4?t:14.4+1.2','t<34.4?t:34.4+3.2'),
 ('t<=15||','t<=36||'),('ramp(7.5,8.3)','ramp(18.0,19.0)'),('ramp(6.1,7.4)','ramp(15.6,17.8)')]:dense=replace(dense,a,b)
start=dense.index(' view(t){');end=dense.index(' draw(t,opacity=1){',start)
dense=dense[:start]+(ROOT/'scripts/ShaderFilm/centered_flock_view.js').read_text('utf-8')+dense[end:]
# The integrated smooth stop now settles at t=36 rather than 15.
(OUT/'flock/dense-flock.js').write_text(dense,encoding='utf-8')
vert=(SRC/'flock_v2/bird.vert').read_text('utf-8')
vert=vert.replace('uTime-14.4','uTime-30.0').replace('uTime-15.7','uTime-31.8')
(OUT/'flock/bird.vert').write_text(vert,encoding='utf-8')

# Longer independent animation uses the approved rig at the same physical speed.
street=ROOT/'assets/video/素材/路口人车_v7_十四秒/路口人车_持续行走_14秒.mp4'
if not street.exists() or not (OUT/'street/frame_335.jpg').exists():
    subprocess.run([sys.executable,str(ROOT/'scripts/ShaderFilm/render_street14.py')],check=True)

engine=(SRC/'engine.js').read_text('utf-8')
engine=replace(engine,'DURATION=48','DURATION=90')
start=engine.index('function birds(t){');end=engine.index('function cloudBanks(',start)
engine=engine[:start]+'''function birds(t){
 denseFlock.sample(t);const view=denseFlock.view(t),pull=ramp(t,15,19);
 if(t>=15&&t<42.5)denseFlock.draw(t,1-ramp(t,40.0,42.5));
 if(t<19){
  const reveal=logmix(17,1.45,ramp(t,1.0,10.0));
  const hs=t<15?reveal:logmix(1.45,.025,pull);
  bird(view.hero[0],view.hero[1],hs,t,flock.phase[flock.hero],flock.frequency[flock.hero],0,0,1-ramp(t,18,19));
 }
}
'''+engine[end:]
engine=replace(engine,'18.2,21','39.0,42.3')
start=engine.index('function street(t){');end=engine.index('function subtitles(',start)
engine=engine[:start]+'''function street(t){
 const close=ramp(t,44.35,46);
 if(t<46)ground('city',t,[960,540,logmix(1.04,1.55,ramp(t,43,46)),0],0,0,.04);
 if(close>0)ground('approvedStreet',t,[960,540,logmix(1.045,1,close),0],0,0,0,close);
}
'''+(ROOT/'scripts/ShaderFilm/transitions_revision3.js').read_text('utf-8')+engine[end:]
engine=replace(engine,'ramp(t,46,47.1)','ramp(t,87,88.2)')
engine=replace(engine,'function cloud(t,coverage,travel){',"function cloud(t,coverage,travel){\n if(t>=78&&coverage>.001)throw Error('Foreground cloud in space');")
start=engine.index('function subtitles(');end=engine.index('window.renderFrame=',start)
engine=engine[:start]+'''let subtitleLayout=[];
function subtitles(t,show=true){
 text.clearRect(0,0,W,H);
 if(show){const c=subtitleLayout.find(c=>t>=c.start&&t<c.end);if(c){
  text.fillStyle='rgba(10,11,12,.60)';text.fillRect(c.x,c.y,c.width,c.height);
  text.textAlign='center';text.textBaseline='middle';text.fillStyle='#f4f0e6';
  text.font='38px "Microsoft YaHei",sans-serif';text.fillText(c.zh,960,c.zhY);
  text.font='27px Georgia,serif';text.fillText(c.en,960,c.enY);
 }}
 const title=ramp(t,87,88.2);
 if(title>0){text.globalAlpha=title;text.fillStyle='#eee8db';text.textAlign='center';text.textBaseline='middle';text.font='37px Georgia,serif';text.fillText('E M E R G E N C E',960,877);text.font='25px "Microsoft YaHei",sans-serif';text.fillText('涌 现',960,925);text.globalAlpha=1;}
}
'''+engine[end:]
start=engine.index('window.renderFrame=function(');end=engine.index('const exportCanvas=',start)
engine=engine[:start]+'''window.renderFrame=function(frame,show=true){
 const t=clamp(frame/FPS,0,DURATION-1/FPS);bind(scene);blend(false);
 environment(t,ramp(t,76.8,81.2),ramp(t,81.5,85.0));blend(true);
 if(t<43){
  denseFlock.sample(t);birdSky(t);birds(t);
  const cover=ramp(t,39,42.3);cloudBanks(t,cover,Math.max(0,t-39)*1.1);cloud(t,cover,Math.max(0,t-39)*1.1);
 }else if(t<60){
  street(t);const enter=1-ramp(t,43,45.1),leave=ramp(t,59,60),fog=Math.max(enter,leave);
  cloudBanks(t,fog,4.4+(t-43)*.35);cloud(t,fog,4.4+(t-43)*.35);
 }else{
  ascent(t);
 }
 bind(null);blend(false);use(programs.post);bindTex(scene.tex);
 uniforms(programs.post,{uTex:0,uResolution:[W,H],uTime:t,uBlur:12*(1-ramp(t,3.0,11.5)),uBlack:1-ramp(t,.65,2.1)});gl.drawArrays(gl.TRIANGLES,0,6);
 subtitles(t,show);const err=gl.getError();if(err!==gl.NO_ERROR)throw Error('WebGL render error: '+err);
 return {time:t,stage:t<15?'bird':t<30?'flock':t<43?'fall/cloud':t<60?'intersection':t<74?'city':t<78?'regional':'earth/space'};
};
'''+engine[end:]
engine=replace(engine,'frame<8.3*FPS','frame<19*FPS')
engine=replace(engine,"im.src='art/'+file","im.src='../emergence_shader/art/'+file")
engine=replace(engine,"['flock.json','cues.json','art/street_objects.json']","['../emergence_shader/flock.json','cues.json','../emergence_shader/art/street_objects.json']")
engine=replace(engine,'denseFlock=await DenseFlock.create(gl);',"denseFlock=await DenseFlock.create(gl,'flock/');\n const im=new Image();im.src='street/frame_000.jpg';await im.decode();images.approvedStreet=im;textures.approvedStreet=texture(im);")
engine=replace(engine,'const exportCanvas=', '''let streetFrame=0;
const streetImages=new Map();
async function prepareStreet(t){
 if(t<43||t>=60)return;
 const n=Math.max(0,Math.min(335,Math.floor((t-46)*24+1e-6)));
 if(n===streetFrame)return;
 let im=streetImages.get(n);if(!im){im=new Image();im.src='street/frame_'+String(n).padStart(3,'0')+'.jpg';await im.decode();streetImages.set(n,im);}
 if(streetImages.size>8)streetImages.delete(streetImages.keys().next().value);
 bindTex(textures.approvedStreet);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,im);streetFrame=n;
}
const exportCanvas=''' )
# The film export and the interactive player both wait for the exact street frame.
anchor='window.ready=(async()=>{'
engine=replace(engine,anchor,'''const captureBase=window.capture;
window.capture=async function(frame,show=true,type='image/jpeg'){await prepareStreet(frame/FPS);return captureBase(frame,show,type);};
'''+anchor)
engine=replace(engine,'function ground(name,t,camera,tilt=0,relief=0,haze=0){','function ground(name,t,camera,tilt=0,relief=0,haze=0,opacity=1){')
engine=replace(engine,'uOpacity:1,uHaze:haze','uOpacity:opacity,uHaze:haze,uFeather:0')
engine=replace(engine,'denseFlock=await DenseFlock.create(gl,\'flock/\');',"denseFlock=await DenseFlock.create(gl,'flock/');subtitleLayout=await (await fetch('subtitle_layout.json')).json();")
engine=engine[:engine.index('function pause(){')]+'''function pause(){playing=false;audio.pause();document.getElementById('play').textContent='播放';}
async function seek(time){current=clamp(time,0,DURATION-1/FPS);audio.currentTime=current;origin=performance.now()/1000-current;await prepareStreet(current);renderFrame(current*FPS,subs);document.getElementById('seek').value=Math.floor(current*FPS);document.getElementById('clock').textContent=clockText(current);}
function clockText(t){return `${Math.floor(t/60).toString().padStart(2,'0')}:${Math.floor(t%60).toString().padStart(2,'0')} / 01:30`;}
async function loop(){if(!playing)return;current=audio.readyState>=2&&!muted?audio.currentTime:performance.now()/1000-origin;if(current>=DURATION-1/FPS){await seek(DURATION-1/FPS);pause();return;}await prepareStreet(current);renderFrame(Math.floor(current*FPS),subs);document.getElementById('seek').value=Math.floor(current*FPS);document.getElementById('clock').textContent=clockText(current);requestAnimationFrame(loop);}
document.getElementById('play').onclick=async()=>{await ready;if(playing){pause();return;}if(current>=89.9)await seek(0);audio.currentTime=current;audio.muted=muted;await audio.play();playing=true;origin=performance.now()/1000-current;document.getElementById('play').textContent='暂停';requestAnimationFrame(loop);};
document.getElementById('seek').oninput=e=>seek(+e.target.value/FPS);
document.getElementById('subs').onclick=()=>{subs=!subs;document.getElementById('subs').textContent='字幕：'+(subs?'开':'关');renderFrame(current*FPS,subs);};
document.getElementById('mute').onclick=()=>{muted=!muted;audio.muted=muted;origin=performance.now()/1000-current;document.getElementById('mute').textContent='声音：'+(muted?'关':'开');};
document.querySelectorAll('[data-time]').forEach(b=>b.onclick=()=>seek(+b.dataset.time));
document.addEventListener('keydown',e=>{if(e.code==='Space'&&e.target.tagName!=='INPUT'){e.preventDefault();document.getElementById('play').click();}});
'''
engine=replace(engine,"'earth.frag','post.frag'","'earth.frag','post.frag','ascent.frag'")
engine=replace(engine,"['environment','cloud','earth','post']","['environment','cloud','earth','post','ascent']")
engine=replace(engine,"city:'city.jpg',region:","city:'city.jpg',curvature:'curvature.jpg',region:")
shutil.copy2(ROOT/'scripts/ShaderFilm/ascent_revision3.frag',OUT/'shaders/ascent.frag')
(OUT/'engine.js').write_text(engine,encoding='utf-8')
html=(SRC/'index.html').read_text('utf-8').replace('48 秒技术样片','90 秒正片').replace('Shader 技术样片','90 秒正片').replace('max="1151"','max="2159"').replace('00:00 / 00:48','00:00 / 01:30').replace('flock_v2/dense-flock.js','flock/dense-flock.js').replace('../../audio/emergence_shader/','../../audio/emergence_final90/').replace('sample_bilingual.mp4','涌现_90秒_双语字幕.mp4')
for a,b in [('data-time="4"','data-time="11"'),('data-time="9"','data-time="23"'),('data-time="15"','data-time="31"'),('data-time="21"','data-time="41"'),('data-time="27"','data-time="52"'),('data-time="34"','data-time="68"'),('data-time="40"','data-time="82"'),('data-time="45"','data-time="87"')]:html=html.replace(a,b)
(OUT/'index.html').write_text(html,encoding='utf-8')
earth=(OUT/'shaders/earth.frag').read_text('utf-8').replace('uniform float uSpace;','uniform float uSpace;\nuniform float uOpacity;').replace('vec3(.96,.93,.86),halo','vec3(.96,.93,.86),halo*uOpacity').replace('smoothstep(1.003,.993,r)','smoothstep(1.003,.993,r)*uOpacity')
(OUT/'shaders/earth.frag').write_text(earth,encoding='utf-8')
timeline=[{'start':a,'end':b,'shot':s} for a,b,s in [(0,15,'黑屏与单鸟揭示'),(15,30,'居中鸟群与主角推近'),(30,39,'失速与延迟跟随'),(39,43,'下坠穿云'),(43,46,'路口下降建立'),(46,60,'十四秒持续行走与车辆通行'),(60,74,'城市上升'),(74,78,'区域尺度'),(78,87,'无前景云的地球与星空'),(87,90,'标题与留白')]]
(OUT/'timeline.json').write_text(json.dumps({'revision':3,'duration':90,'fps':24,'frames':2160,'shots':timeline,'transition_windows':{'cloud_emergence':[43,45.1],'full_frame_city_to_street':[44.35,46],'city_to_curvature':[68.5,71.2],'curvature_to_region':[73,76],'region_to_earth':[78,80.5],'continuous_ascent_camera':[60,90],'foreground_clouds_end':61.3},'approved_street':{'source':str(street.relative_to(ROOT)),'sha256':hashlib.sha256(street.read_bytes()).hexdigest(),'playback_rate':1}},ensure_ascii=False,indent=2),encoding='utf-8')
print('Prepared independent 90-second WebGL project',flush=True)
from install_approved_ascent import install
install(ROOT,OUT)
