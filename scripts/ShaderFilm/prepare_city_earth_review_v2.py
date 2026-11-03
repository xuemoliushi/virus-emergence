"""Low-altitude cloud crossing and a C1 ascent into the approved Earth look."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'assets/video/city_earth_review_v1';APPROVED=ROOT/'assets/video/earth_transition_review_v1';OUT=ROOT/'assets/video/city_earth_review_v2'
OUT.mkdir(exist_ok=True);(OUT/'qa').mkdir(exist_ok=True)
s=(OLD/'player.js').read_text('utf-8')
start=s.index('function fogAt(');end=s.index('window.fogAt=',start)
s=s[:start]+'''function fogAt(time){return pathFog(time);}
function cameraAt(time){return pathPose(time);}
function renderFrame(frame){
 const time=Math.max(0,Math.min(FRAMES-1,frame))/FPS,pose=pathPose(time);
 gl.disable(gl.BLEND);
 if(time<4.5){
  const q=pose.logHeight-pathLogAltitude(0);
  gl.useProgram(cityProgram);gl.uniform1f(cityLocations.uScale,1.5*Math.exp(-.14*q));
  gl.uniform1f(cityLocations.uHorizon,110+12*time);gl.drawArrays(gl.TRIANGLES,0,3);
 }else{
  gl.useProgram(program);gl.uniform1f(locations.uTime,time);gl.drawArrays(gl.TRIANGLES,0,3);
 }
 const fog=fogAt(time);
 if(fog>0){
  if(pose.altitudeKm>18)throw Error('Foreground cloud above low-altitude crossing');
  gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
  gl.useProgram(cloudProgram);gl.uniform1f(cloudLocations.uTime,time+60);
  gl.uniform1f(cloudLocations.uCoverage,fog);gl.uniform1f(cloudLocations.uTravel,(time-3.5)*.45+2);
  gl.drawArrays(gl.TRIANGLES,0,3);gl.disable(gl.BLEND);
 }
 const error=gl.getError();if(error!==gl.NO_ERROR)throw Error('WebGL '+error);
 return pose;
}
'''+s[end:]
s=s.replace("['uCity','uCurve','uTime','uResolution']","['uCity','uScale','uHorizon','uResolution']")
s=s.replace(";await extraTexture('../emergence_shader/art/curvature.jpg',3)","")
s=s.replace('gl.uniform1i(cityLocations.uCurve,3);','')
s=s.replace('城市至地球衔接 v1','城市至地球衔接 v2 · 低空穿云、持续升高')
(OUT/'player.js').write_text(s,encoding='utf-8')
html=(OLD/'index.html').read_text('utf-8').replace('审核 v1','审核 v2').replace('<script src="player.js">','<script src="camera-path.js"></script><script src="player.js">')
(OUT/'index.html').write_text(html,encoding='utf-8')
shader=(APPROVED/'earth.frag').read_text('utf-8')
shader=shader.replace('vec3 worldNormal(vec3 n,float time){','''float latitudeAtPhase(float phase){
 float u=pow(clamp(phase/3.,0.,1.),1./((11./14.)*8.5/3.));
 return 24.+21.*(1.-smoothstep(0.,1.,u));
}
vec3 worldNormal(vec3 n,float time){''')
shader=shader.replace('lat=radians(24.);','lat=radians(latitudeAtPhase(time));')
anchor='vec3 shade(vec2 pixel,float time){'
shader=shader.replace(anchor,(OUT/'camera-path.glsl').read_text('utf-8')+'\n'+anchor)
shader=shader.replace('float u=ease(time/12.),d=1.+.12*exp(log(4.2/.12)*u),angular=asin(1./d);','float timeline=time;time=pathEarthPhase(timeline);\n float d=pathDistance(timeline),angular=asin(1./d);')
shader=shader.replace('gray+=grain*.04*land;','gray+=grain*.04*land;\n  gray+=(fbm(wn*2600.)-.5)*.15*land*(1.-smoothstep(.008,.10,d-1.));')
shader=shader.replace('if(air.x>0.){\n  float end=min(air.y,surface),stepSize=max(0.,end-air.x)/20.;','if(air.y>0.){\n  float start=max(0.,air.x),end=min(air.y,surface),stepSize=max(0.,end-start)/20.;')
shader=shader.replace('air.x+(float(i)+.5)*stepSize','start+(float(i)+.5)*stepSize')
(OUT/'earth.frag').write_text(shader,encoding='utf-8')
baseline=json.loads((OLD/'production_baseline.json').read_text('utf-8'))
for p in [OLD/'player.js',OLD/'earth.frag',OLD/'城市至地球_衔接预览_v1.mp4']:
 baseline[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
(OUT/'production_baseline.json').write_text(json.dumps(baseline,ensure_ascii=False,indent=2),encoding='utf-8')
print('Prepared city/Earth v2: low-altitude cloud crossing, nonzero join velocity.')
