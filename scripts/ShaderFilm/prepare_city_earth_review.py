"""Extend the approved Earth review with an isolated city/cloud prelude."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'assets/video/earth_transition_review_v1';OUT=ROOT/'assets/video/city_earth_review_v1'
OUT.mkdir(exist_ok=True);(OUT/'qa').mkdir(exist_ok=True)
s=(SOURCE/'earth.js').read_text('utf-8')
s=s.replace('SECONDS=14,FRAMES=336','SECONDS=27,FRAMES=648')
s=s.replace('function cameraAt(time){','function earthCameraAt(time){',1)
s=s.replace('let program,locations;','let program,locations,cityProgram,cloudProgram,cityLocations,cloudLocations;')
start=s.index('function renderFrame(frame){');end=s.index('window.capture=',start)
s=s[:start]+'''function fogAt(time){
 if(time>=13)return 0;
 return smooth((time-9.5)/.85)*(1-smooth((time-10.65)/1.2));
}
function cameraAt(time){
 if(time<10.5)return {time,stage:'city',distance:null,cloud:fogAt(time),
  horizon:105+115*smooth((time-3)/8),cityDistance:.045*time+.004*time*time};
 const t=time-13,c=earthCameraAt(Math.max(0,t));
 if(t<0){c.distance=1.08+.04*quintic((t+2.5)/2.5);c.altitudeKm=(c.distance-1)*6371;c.angularRadius=Math.asin(1/c.distance);c.tilt=c.angularRadius-9.2*Math.PI/180;}
 return {...c,time,earthTime:t,stage:t<0?'cloud-exit':'approved-earth',cloud:fogAt(time)};
}
function renderFrame(frame){
 const time=Math.max(0,Math.min(FRAMES-1,frame))/FPS;
 gl.disable(gl.BLEND);
 if(time<10.5){
  gl.useProgram(cityProgram);gl.uniform1f(cityLocations.uTime,time);gl.drawArrays(gl.TRIANGLES,0,3);
 }else{
  gl.useProgram(program);gl.uniform1f(locations.uTime,time-13);gl.drawArrays(gl.TRIANGLES,0,3);
 }
 const fog=fogAt(time);
 if(fog>0){
  gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
  gl.useProgram(cloudProgram);gl.uniform1f(cloudLocations.uTime,time+60);
  gl.uniform1f(cloudLocations.uCoverage,fog);gl.uniform1f(cloudLocations.uTravel,(time-8.8)*.65+2);
  gl.drawArrays(gl.TRIANGLES,0,3);gl.disable(gl.BLEND);
 }
 const error=gl.getError();if(error!==gl.NO_ERROR)throw Error('WebGL '+error);
 return cameraAt(time);
}
window.fogAt=fogAt;
'''+s[end:]
s=s.replace("im.src='art/earth_topography_nasa.jpg'","im.src='../earth_transition_review_v1/art/earth_topography_nasa.jpg'")
s=s.replace("cloudImage.src='art/clouds_nasa.jpg'","cloudImage.src='../earth_transition_review_v1/art/clouds_nasa.jpg'")
anchor='renderFrame(0);document.getElementById'
extra='''async function extraProgram(file,names){
 const f=await (await fetch(file)).text(),p=gl.createProgram();gl.attachShader(p,compile(gl.VERTEX_SHADER,vert));gl.attachShader(p,compile(gl.FRAGMENT_SHADER,f));gl.linkProgram(p);
 if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(p));
 const u={};for(const name of names)u[name]=gl.getUniformLocation(p,name);return [p,u];
 }
 [cityProgram,cityLocations]=await extraProgram('city.frag',['uCity','uCurve','uTime','uResolution']);
 [cloudProgram,cloudLocations]=await extraProgram('cloud.frag',['uTime','uCoverage','uTravel']);
 async function extraTexture(url,unit){
  const im=new Image();im.src=url;await im.decode();gl.activeTexture(gl.TEXTURE0+unit);const tex=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,tex);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
  gl.texImage2D(gl.TEXTURE_2D,0,gl.RGB,gl.RGB,gl.UNSIGNED_BYTE,im);gl.generateMipmap(gl.TEXTURE_2D);
 }
 await extraTexture('../emergence_shader/art/city.jpg',2);await extraTexture('../emergence_shader/art/curvature.jpg',3);
 gl.useProgram(cityProgram);gl.uniform1i(cityLocations.uCity,2);gl.uniform1i(cityLocations.uCurve,3);gl.uniform2f(cityLocations.uResolution,W,H);
 '''
assert anchor in s;s=s.replace(anchor,extra+anchor)
s=s.replace('独立审核 v1 · 同一三维地球 · 1920×1080 / 24 fps / 14 秒 · 尚未接入正片','城市至地球衔接 v1 · 1920×1080 / 24 fps / 27 秒 · 尚未接入正片')
s=s.replace('335/24','647/24').replace(" / 14.00'"," / 27.00'")
(OUT/'player.js').write_text(s,encoding='utf-8')
# Include the approved review itself among protected inputs, not just production.
baseline=json.loads((SOURCE/'production_baseline.json').read_text('utf-8'))
for p in [SOURCE/'earth.js',SOURCE/'earth.frag',SOURCE/'地球连续拉远_独立预览_v1.mp4']:
 baseline[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
(OUT/'production_baseline.json').write_text(json.dumps(baseline,ensure_ascii=False,indent=2),encoding='utf-8')
print('Prepared isolated 27-second city/Earth review; approved source protected.')
