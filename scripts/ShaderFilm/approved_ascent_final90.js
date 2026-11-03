// APPROVED_ASCENT_REVISION4: render the accepted city/Earth v2 without regrading.
const approvedAscent={
 programs:{},tex:[],
 async init(){
  const full=await (await fetch('shaders/full.vert')).text();
  programs.approvedPresent=program(full,`#version 300 es
   precision highp float;in vec2 vUV;uniform sampler2D uTex;uniform vec2 uResolution;uniform float uTime;uniform float uIntro;out vec4 frag;
   float hash(vec2 p){return fract(sin(dot(p,vec2(12.9898,78.233)))*43758.5453);}
   void main(){vec3 c=texture(uTex,vec2(vUV.x,1.-vUV.y)).rgb;
    if(uIntro>0.){float vignette=1.-.12*smoothstep(.25,.8,length((vUV-.5)*vec2(1.,.72)));float grain=(hash(floor(vUV*uResolution)+floor(uTime*24.))-.5)*.006;c=mix(c,c*vignette+grain,uIntro);}
    frag=vec4(c,1.);}`);
  const vert='#version 300 es\nprecision highp float;out vec2 vUV;void main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);vUV=p;gl_Position=vec4(p*2.-1.,0,1);}';
  for(const name of ['city','earth','cloud']){
   const source=await (await fetch('shaders/approved-'+name+'.frag')).text();
   this.programs[name]=program(vert,source);
  }
  const aniso=gl.getExtension('EXT_texture_filter_anisotropic');
  for(const [i,file,wrap]of [[0,'earth_topography_nasa.jpg',gl.REPEAT],[1,'clouds_nasa.jpg',gl.REPEAT],[2,'city.jpg',gl.CLAMP_TO_EDGE]]){
   const im=new Image();im.src='approved-art/'+file;await im.decode();
   gl.activeTexture(gl.TEXTURE0+i);const tex=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,tex);
   gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,wrap);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
   gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
   gl.texImage2D(gl.TEXTURE_2D,0,gl.RGB,gl.RGB,gl.UNSIGNED_BYTE,im);gl.generateMipmap(gl.TEXTURE_2D);
   if(i<2&&aniso)gl.texParameterf(gl.TEXTURE_2D,aniso.TEXTURE_MAX_ANISOTROPY_EXT,Math.min(8,gl.getParameter(aniso.MAX_TEXTURE_MAX_ANISOTROPY_EXT)));
   this.tex[i]=tex;
  }
  const e=this.programs.earth,c=this.programs.city;
  gl.useProgram(e.p);gl.uniform1i(e.uniform.uEarth,0);gl.uniform1i(e.uniform.uClouds,1);gl.uniform2f(e.uniform.uResolution,W,H);
  gl.useProgram(c.p);gl.uniform1i(c.uniform.uCity,2);gl.uniform2f(c.uniform.uResolution,W,H);
  gl.activeTexture(gl.TEXTURE0);
 },
 render(time){
  const local=Math.max(0,Math.min(647/24,time)),pose=pathPose(local);
  for(let i=0;i<3;i++){gl.activeTexture(gl.TEXTURE0+i);gl.bindTexture(gl.TEXTURE_2D,this.tex[i]);}
  gl.disable(gl.BLEND);
  if(local<4.5){
   const p=this.programs.city,q=pose.logHeight-pathLogAltitude(0);gl.useProgram(p.p);
   gl.uniform1f(p.uniform.uScale,1.5*Math.exp(-.14*q));gl.uniform1f(p.uniform.uHorizon,110+12*local);
  }else{
   const p=this.programs.earth;gl.useProgram(p.p);gl.uniform1f(p.uniform.uTime,local);
  }
  gl.drawArrays(gl.TRIANGLES,0,3);
  const fog=pathFog(local);
  if(fog>0){
   if(pose.altitudeKm>18)throw Error('Foreground cloud above low-altitude crossing');
   const p=this.programs.cloud;gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.useProgram(p.p);
   gl.uniform1f(p.uniform.uTime,local+60);gl.uniform1f(p.uniform.uCoverage,fog);gl.uniform1f(p.uniform.uTravel,(local-3.5)*.45+2);
   gl.drawArrays(gl.TRIANGLES,0,3);gl.disable(gl.BLEND);
  }
  gl.activeTexture(gl.TEXTURE0);return pose;
 }
};
function ascent(t){
 approvedAscent.render(t-60);
 // Full-screen procedural mist has no rectangular texture-card edges.
 if(t<61.3){const fog=1-ramp(t,60,61.3);cloud(t,fog,10.35+(t-60)*.4);}
}
window.transitionDebug={
 ascentPose:t=>pathPose(Math.min(647/24,Math.max(0,t-60))),
 ascentDistance:t=>pathLogAltitude(Math.min(647/24,Math.max(0,t-60))),
 entry:t=>({cityOpacity:1-ramp(t,44.35,46),streetOpacity:ramp(t,44.35,46),cityScale:logmix(1.04,1.55,ramp(t,43,46)),streetScale:logmix(1.045,1,ramp(t,44.35,46)),cloud:1-ramp(t,43,45.1)}),
 cloudsEnd:65.45,approvedWindow:[60,87]
};
