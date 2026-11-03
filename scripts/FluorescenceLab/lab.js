/* Isolated WebGL2 renderer. A = cached masked layers; B = dynamic material.
 * Both use the same source, geometry, motion and selective low-resolution bloom.
 * No engine, network libraries, game state, readbacks, or texture allocations per frame.
 */
'use strict';
const $=id=>document.getElementById(id),canvas=$('gl');
const gl=canvas.getContext('webgl2',{alpha:false,antialias:false,preserveDrawingBuffer:true,powerPreference:'high-performance'});
if(!gl)throw new Error('需要支持 WebGL 2 的浏览器');
const W=640,H=360, BW=320,BH=180;
const state={time:0,playing:true,count:1,size:'large',strength:.28,benchmark:false};
const stats={cpu:[],gpu:[],interval:[],queries:[],last:0,draws:0};
const timer=gl.getExtension('EXT_disjoint_timer_query_webgl2');
const gpuInfo=gl.getExtension('WEBGL_debug_renderer_info');
const renderer=gpuInfo?gl.getParameter(gpuInfo.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER);
const software=/swiftshader|llvmpipe|software|basic render/i.test(renderer);
const fullVS=`#version 300 es
precision highp float;
out vec2 uv;
void main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);uv=p;gl_Position=vec4(p*2.-1.,0,1);}`;
const cellVS=`#version 300 es
precision highp float;
layout(location=0) in vec2 pos;
layout(location=1) in vec4 instance;
out vec2 uv;out float seed;
uniform float t;
void main(){uv=pos;seed=instance.w;vec2 q=(pos-.5)*instance.z;
float breathing=1.+.009*sin(t*1.35+seed);
q*=breathing;
vec2 p=instance.xy+q;
gl_Position=vec4(p/vec2(640.,360.)*vec2(2.,-2.)+vec2(-1.,1.),0,1);}`;
const common=`precision highp float;
float sat(float x){return clamp(x,0.,1.);}
float pulse(float t,float a,float b){return smoothstep(a,a+.7,t)*(1.-smoothstep(b-.7,b,t));}
vec3 linearRGB(vec3 c){return pow(max(c,vec3(0)),vec3(2.2));}
vec3 coral=vec3(.92,.065,.115);
vec3 amber=vec3(.95,.32,.025);
`;
const materialFS=`#version 300 es
${common}
in vec2 uv;in float seed;
uniform sampler2D baseTex,mapsTex,fieldTex,noiseTex;
uniform float t;uniform int route;
layout(location=0) out vec4 color;
layout(location=1) out vec4 emission;
void main(){
 vec4 base=texture(baseTex,uv),m=texture(mapsTex,uv),f=texture(fieldTex,uv);
 float cellAlpha=base.a;
 float contact=pulse(t,4.,8.2);
 float birth=pulse(t,8.,11.95);
 vec2 contactPos=vec2(.765,.365);
 float hot=exp(-dot(uv-contactPos,uv-contactPos)*240.);
 float breath=.66+.17*sin(t*1.4+seed);
 vec3 albedo=linearRGB(base.rgb);
 // The original pale particles remain colored and textured, rather than white.
 albedo=mix(albedo,albedo*vec3(1.,.55,.57),m.b*.52);
 albedo*=.67;
 vec3 e;
 if(route==0){
   float membraneGain=.42+.14*sin(t*1.2+seed);
   float structureGain=.19+.10*sin(t*1.35+1.3+seed);
   float particleGain=.46+.15*sin(t*2.1+2.+seed);
   e=coral*(m.r*membraneGain+m.g*structureGain+m.b*particleGain);
   e+=amber*hot*contact*(m.r*.55+m.g*.20+m.b*.25);
 }else{
   vec2 n=f.rg*2.-1.;
   vec2 flow=uv+vec2(t*.009,-t*.013);
   float noise=texture(noiseTex,flow*2.8+seed*.031).r;
   float wave=.5+.5*sin(uv.y*27.-uv.x*9.-t*2.5+noise*5.+seed);
   float moving=pow(wave,4.);
   float transmission=f.b*(1.-m.a*.7);
   float edgeLight=sat(dot(n,vec2(-.6,-.8))*.5+.5);
   float membrane=.035+.50*pow(edgeLight,3.)+.38*moving;
   vec3 tissueColor=linearRGB(vec3(.57,.13,.25));
   albedo=mix(albedo,albedo*.63+tissueColor*transmission*.16,.65*(1.-m.a));
   albedo*=1.-m.r*.35;
   float internal=m.g*(.10+moving*.85)+m.b*(.26+noise*.65);
   e=coral*(m.r*membrane+internal);
   // Colored broad INTERNAL transmission is masked by thickness, not an outer halo.
   e+=vec3(.055,.010,.035)*transmission*(.25+moving*.75)*(1.-m.a);
   e+=amber*hot*contact*(.16+m.r*.40+m.g*.5);
   // A traveling local response remains inside the original tissue silhouette.
   float ripple=exp(-pow((length(uv-contactPos)-(t-4.8)*.065)*80.,2.));
   e+=vec3(.32,.07,.09)*ripple*contact*(m.g+m.b*.4);
 }
 e*=cellAlpha;
 // Shared contact and budding geometry: the A/B comparison stays fair.
 float approach=smoothstep(4.,5.7,t);
 vec2 virusPos=mix(vec2(.94,.19),contactPos,approach);
 float vr=length(uv-virusPos);
 float virus=(1.-smoothstep(.009,.018,vr))*contact;
 float release=smoothstep(8.6,11.5,t);
 vec2 budPos=contactPos+normalize(vec2(.8,-.35))*(.025+release*.13);
 float budR=mix(.013,.022,smoothstep(8.1,9.6,t));
 float bud=(1.-smoothstep(budR,budR+.004,length(uv-budPos)))*birth;
 vec2 segment=budPos-contactPos;
 float along=clamp(dot(uv-contactPos,segment)/max(dot(segment,segment),.00001),0.,1.);
 float neck=(1.-smoothstep(.004,.010,length(uv-contactPos-segment*along)))*birth*(1.-smoothstep(.28,.52,release));
 bud=max(bud,neck);
 float a=max(cellAlpha,max(virus,bud));
 vec3 c=albedo*cellAlpha+e*.54;
 c=mix(c,amber*.85,virus);c=mix(c,amber*.9,bud);
 e+=amber*(virus*.65+bud*.75);
 color=vec4(c,a);emission=vec4(e,a);
}`;
const bgFS=`#version 300 es
${common}
in vec2 uv;uniform sampler2D background;uniform float t;
layout(location=0)out vec4 color;layout(location=1)out vec4 emission;
void main(){vec3 tex=linearRGB(texture(background,vec2(uv.x,1.-uv.y)).rgb);
vec3 bg=linearRGB(vec3(.052,.038,.083))+tex*.055;
color=vec4(bg,1);emission=vec4(0);}`;
const blurFS=`#version 300 es
precision highp float;in vec2 uv;uniform sampler2D src;uniform vec2 axis;out vec4 color;
void main(){vec3 v=texture(src,uv).rgb*.227027;
v+=(texture(src,uv+axis*1.384615).rgb+texture(src,uv-axis*1.384615).rgb)*.316216;
v+=(texture(src,uv+axis*3.230769).rgb+texture(src,uv-axis*3.230769).rgb)*.070270;
color=vec4(v,1);}`;
const copyFS=`#version 300 es
precision highp float;in vec2 uv;uniform sampler2D src;out vec4 color;
void main(){color=texture(src,uv);}`;
const outputFS=`#version 300 es
precision highp float;in vec2 uv;uniform sampler2D scene,glow;uniform float gain;out vec4 color;
void main(){vec3 c=texture(scene,uv).rgb+texture(glow,uv).rgb*gain;
// Chroma-preserving highlight shoulder. No independent channel clipping to white.
float peak=max(c.r,max(c.g,c.b));c/=1.+max(peak-.60,0.)*.75;
color=vec4(pow(max(c,vec3(0)),vec3(1./2.2)),1);}`;
function shader(type,src){const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;}
function program(v,f){const p=gl.createProgram();const a=shader(gl.VERTEX_SHADER,v),b=shader(gl.FRAGMENT_SHADER,f);gl.attachShader(p,a);gl.attachShader(p,b);gl.linkProgram(p);gl.deleteShader(a);gl.deleteShader(b);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(p));return {p,u:{}};}
const programs={material:program(cellVS,materialFS),bg:program(fullVS,bgFS),blur:program(fullVS,blurFS),copy:program(fullVS,copyFS),output:program(fullVS,outputFS)};
const uni=(p,n)=>p.u[n]??(p.u[n]=gl.getUniformLocation(p.p,n));
const empty=gl.createVertexArray(),cellVAO=gl.createVertexArray();gl.bindVertexArray(cellVAO);
const quad=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,quad);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([0,0,1,0,0,1,0,1,1,0,1,1]),gl.STATIC_DRAW);gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,2,gl.FLOAT,false,0,0);
const instances=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,instances);gl.bufferData(gl.ARRAY_BUFFER,64*4*4,gl.DYNAMIC_DRAW);gl.enableVertexAttribArray(1);gl.vertexAttribPointer(1,4,gl.FLOAT,false,0,0);gl.vertexAttribDivisor(1,1);gl.bindVertexArray(null);
function makeTexture(w,h){const a=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,a);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA8,w,h,0,gl.RGBA,gl.UNSIGNED_BYTE,null);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);return a;}
function target(w,h,n=1){const fb=gl.createFramebuffer();gl.bindFramebuffer(gl.FRAMEBUFFER,fb);const tex=[];for(let i=0;i<n;i++){tex.push(makeTexture(w,h));gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0+i,gl.TEXTURE_2D,tex[i],0);}gl.drawBuffers(tex.map((_,i)=>gl.COLOR_ATTACHMENT0+i));if(gl.checkFramebufferStatus(gl.FRAMEBUFFER)!==gl.FRAMEBUFFER_COMPLETE)throw Error('不支持实验所需的离屏缓冲');return {fb,tex,w,h};}
const routes=[0,1].map(()=>({scene:target(W,H,2),small:target(BW,BH),x:target(BW,BH),y:target(BW,BH)}));
const textures={};
async function loadTexture(name,url){const im=new Image();im.src=url;await im.decode();const tx=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,tx);gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,false);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,im);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,name==='noise'?gl.REPEAT:gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,name==='noise'?gl.REPEAT:gl.CLAMP_TO_EDGE);textures[name]=tx;}
function bind(p,n,tx,unit){gl.activeTexture(gl.TEXTURE0+unit);gl.bindTexture(gl.TEXTURE_2D,tx);gl.uniform1i(uni(p,n),unit);}
function use(p,rt){gl.bindFramebuffer(gl.FRAMEBUFFER,rt?rt.fb:null);gl.viewport(0,0,rt?rt.w:1280,rt?rt.h:720);gl.useProgram(p.p);gl.bindVertexArray(empty);}
function tri(){gl.drawArrays(gl.TRIANGLES,0,3);stats.draws++;}
let layoutKey='';
function updateInstances(){const key=state.count+'/'+state.size;if(key===layoutKey)return;layoutKey=key;const n=state.count,side=Math.ceil(Math.sqrt(n)),data=new Float32Array(n*4);
for(let i=0;i<n;i++){let x,y,s;if(n===1){x=W/2;y=H*.54;s=state.size==='game'?198:395;}else{x=(i%side+.5)*W/side;y=(Math.floor(i/side)+.5)*H/side;s=198;}
data.set([x,y,s,n===1?0:i*1.618],i*4);}gl.bindBuffer(gl.ARRAY_BUFFER,instances);gl.bufferSubData(gl.ARRAY_BUFFER,0,data);}
function render(t,options={}){const start=performance.now();state.time=((t%12)+12)%12;updateInstances();stats.draws=0;
const routeIds=options.route===undefined?[0,1]:[options.route];const bloom=options.bloom!==false;
let q=null;if(options.measureGPU&&timer&&stats.queries.length<12){q=gl.createQuery();gl.beginQuery(timer.TIME_ELAPSED_EXT,q);}
for(const id of routeIds){const r=routes[id];gl.disable(gl.BLEND);use(programs.bg,r.scene);bind(programs.bg,'background',textures.background,0);gl.uniform1f(uni(programs.bg,'t'),state.time);tri();
const p=programs.material;gl.useProgram(p.p);gl.bindVertexArray(cellVAO);bind(p,'baseTex',textures.base,0);bind(p,'mapsTex',textures.maps,1);bind(p,'fieldTex',textures.field,2);bind(p,'noiseTex',textures.noise,3);gl.uniform1f(uni(p,'t'),state.time);gl.uniform1i(uni(p,'route'),id);gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.drawArraysInstanced(gl.TRIANGLES,0,6,state.count);stats.draws++;gl.disable(gl.BLEND);
if(bloom){use(programs.copy,r.small);bind(programs.copy,'src',r.scene.tex[1],0);tri();use(programs.blur,r.x);bind(programs.blur,'src',r.small.tex[0],0);gl.uniform2f(uni(programs.blur,'axis'),1/BW,0);tri();use(programs.blur,r.y);bind(programs.blur,'src',r.x.tex[0],0);gl.uniform2f(uni(programs.blur,'axis'),0,1/BH);tri();}
}
use(programs.output,null);for(const id of routeIds){const r=routes[id];bind(programs.output,'scene',r.scene.tex[0],0);bind(programs.output,'glow',r.y.tex[0],1);
for(let col=0;col<2;col++){gl.viewport(col*W,(1-id)*H,W,H);gl.uniform1f(uni(programs.output,'gain'),bloom&&col===1?state.strength:0);tri();}}
if(q){gl.endQuery(timer.TIME_ELAPSED_EXT);stats.queries.push(q);}stats.cpu.push(performance.now()-start);if(stats.cpu.length>180)stats.cpu.shift();
if(options.ui!==false)updateUI();return stats.draws;}
function drain(){if(!timer)return;const disjoint=gl.getParameter(timer.GPU_DISJOINT_EXT);while(stats.queries.length&&gl.getQueryParameter(stats.queries[0],gl.QUERY_RESULT_AVAILABLE)){const q=stats.queries.shift();const ms=gl.getQueryParameter(q,gl.QUERY_RESULT)/1e6;if(!disjoint){stats.gpu.push(ms);if(stats.gpu.length>180)stats.gpu.shift();}gl.deleteQuery(q);}if(disjoint){for(const q of stats.queries)gl.deleteQuery(q);stats.queries=[];stats.gpu=[];}}
const percentile=(a,p)=>{if(!a.length)return null;const b=[...a].sort((x,y)=>x-y);return b[Math.min(b.length-1,Math.floor(b.length*p))];};
function summary(){return {renderer,softwareRenderer:software,gpuTimerSupported:!!timer,cpuSubmitMedianMs:percentile(stats.cpu,.5),cpuSubmitP95Ms:percentile(stats.cpu,.95),gpuMedianMs:percentile(stats.gpu,.5),gpuP95Ms:percentile(stats.gpu,.95),frameIntervalMedianMs:percentile(stats.interval,.5),drawCalls:stats.draws,scope:'Browser WebGL2 only. No UrhoX, gameplay or mobile performance inference.'};}
function updateUI(){$('seek').value=state.time;$('clock').textContent=state.time.toFixed(1)+'s';$('phase').textContent=state.time<4?'平静 · 缓慢生命活动':state.time<8?'接触 · 局部反应与内部传导':'出芽 · 局部增强后回落';const s=summary();$('metrics').textContent=`${state.count} 个细胞 / 路线 · ${s.drawCalls} 次绘制 / 四格 · CPU 提交 ${s.cpuSubmitMedianMs?.toFixed(2)??'—'}ms${s.gpuMedianMs!==null?' · GPU '+s.gpuMedianMs.toFixed(2)+'ms':''}${software?' · 软件渲染，不能评估显卡性能':''}`;}
let last=0;
function animate(now){if(!state.benchmark){if(state.playing){const dt=last?Math.min((now-last)/1000,.1):0;state.time=(state.time+dt)%12;}if(last&&state.playing){stats.interval.push(now-last);if(stats.interval.length>180)stats.interval.shift();}render(state.time,{measureGPU:true});drain();}last=now;requestAnimationFrame(animate);}
$('play').onclick=()=>{state.playing=!state.playing;$('play').textContent=state.playing?'暂停':'播放';};
$('seek').oninput=e=>{state.playing=false;$('play').textContent='播放';state.time=+e.target.value;render(state.time);};
$('size').onchange=e=>{state.size=e.target.value;render(state.time);};$('count').onchange=e=>{state.count=+e.target.value;render(state.time);};$('strength').oninput=e=>{state.strength=+e.target.value;render(state.time);};
document.querySelectorAll('[data-t]').forEach(b=>b.onclick=()=>{state.time=+b.dataset.t;state.playing=false;$('play').textContent='播放';render(state.time);});
const nextFrame=()=>new Promise(r=>requestAnimationFrame(r));
async function benchmark(){if(state.benchmark)return;state.benchmark=true;$('bench').disabled=true;const prev={...state};const results=[];
try{for(const count of [1,16,64])for(const route of [0,1])for(const bloom of [false,true]){
state.count=count;layoutKey='';for(let i=0;i<12;i++){render(i/10,{route,bloom,ui:false});await nextFrame();}stats.cpu=[];stats.gpu=[];
for(let i=0;i<45;i++){render(4+i/30,{route,bloom,ui:false,measureGPU:true});await nextFrame();drain();}
for(let i=0;i<6;i++){await nextFrame();drain();}
results.push({count,route:route?'B':'A',bloom,output:'two identical 640x360 viewports; one scene render',...summary()});$('results').textContent=`渲染基准 ${results.length}/12 · ${renderer}\n`+results.map(x=>`${x.route} ${String(x.count).padStart(2)} cells ${x.bloom?'weak bloom':'no bloom  '} | CPU p50 ${x.cpuSubmitMedianMs.toFixed(2)}ms p95 ${x.cpuSubmitP95Ms.toFixed(2)}ms | GPU ${x.gpuMedianMs===null?'unavailable':x.gpuMedianMs.toFixed(2)+'ms'}`).join('\n');
}window.lastBenchmark={recordedAt:new Date().toISOString(),results,scope:summary().scope};return window.lastBenchmark;
}finally{Object.assign(state,prev);state.benchmark=false;layoutKey='';$('bench').disabled=false;render(state.time);}}
$('bench').onclick=benchmark;
const labels=['A · 分层动态精灵 / 无 Bloom','A · 分层动态精灵 / 弱 Bloom','B · 程序化材质 / 无 Bloom','B · 程序化材质 / 弱 Bloom'];
window.capture=function(t,type='image/png'){render(t,{ui:false});const out=document.createElement('canvas');out.width=1280;out.height=790;const c=out.getContext('2d');c.fillStyle='#080d14';c.fillRect(0,0,1280,790);c.drawImage(canvas,0,70);c.font='22px Microsoft YaHei';c.fillStyle='#e4efeb';c.fillText('生物荧光 · 同源细胞动态材质对照',22,32);c.font='13px Microsoft YaHei';c.fillStyle='#9ebbb1';c.fillText('独立 WebGL 渲染样片 · 非 UrhoX 实机 · 同步 '+t.toFixed(1)+'s · '+(t<4?'平静':t<8?'接触':'出芽'),22,55);
labels.forEach((s,i)=>{const x=(i%2)*640,y=70+Math.floor(i/2)*360;c.fillStyle='#0a1019dc';c.fillRect(x,y,640,40);c.fillStyle='#c9e6d9';c.font='17px Microsoft YaHei';c.fillText(s,x+18,y+26);});c.strokeStyle='#34453e';c.beginPath();c.moveTo(640,70);c.lineTo(640,790);c.moveTo(0,430);c.lineTo(1280,430);c.stroke();return out.toDataURL(type,.92).split(',')[1];};
window.lab={state,render,summary,benchmark,programSources:{cellVS,materialFS,blurFS,outputFS},getGL:()=>gl};
window.ready=Promise.all(['base','maps','field','noise','background'].map(n=>loadTexture(n,window.LAB_TEXTURES?.[n]||'textures/'+n+(n==='background'?'.jpg':'.png')))).then(()=>{render(1.5);requestAnimationFrame(animate);return {renderer,softwareRenderer:software,webgl:2,packedTextures:4,textureSize:512,bloomResolution:[BW,BH],sceneResolution:[W,H],renderTargetBytes:2*(2*W*H+3*BW*BH)*4,engineValidated:false};}).catch(e=>{$('metrics').textContent=e.message;throw e;});
window.addEventListener('pagehide',()=>{for(const r of routes)for(const rt of Object.values(r)){gl.deleteFramebuffer(rt.fb);for(const tx of rt.tex)gl.deleteTexture(tx);}for(const tx of Object.values(textures))gl.deleteTexture(tx);for(const p of Object.values(programs))gl.deleteProgram(p.p);for(const q of stats.queries)gl.deleteQuery(q);gl.deleteBuffer(quad);gl.deleteBuffer(instances);gl.deleteVertexArray(empty);gl.deleteVertexArray(cellVAO);});
