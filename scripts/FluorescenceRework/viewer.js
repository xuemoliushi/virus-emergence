'use strict';
const $=id=>document.getElementById(id),canvas=$('gl'),gl=canvas.getContext('webgl2',{alpha:false,antialias:false,preserveDrawingBuffer:true,powerPreference:'high-performance'});
if(!gl)throw Error('需要 WebGL 2');
if(!gl.getExtension('EXT_color_buffer_float'))throw Error('此独立对照需要支持半浮点颜色缓冲的浏览器，避免暗部渐变色带');
const state={time:0,playing:true,background:'split',bloom:true,stress:false,benchmark:false};
const timer=gl.getExtension('EXT_disjoint_timer_query_webgl2'),dbg=gl.getExtension('WEBGL_debug_renderer_info');
const renderer=dbg?gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER),stats={gpu:[],cpu:[],queries:[],draws:0,count:0};
const fullVS=`#version 300 es
precision highp float;out vec2 uv;void main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);uv=p;gl_Position=vec4(p*2.-1.,0,1);}`;
const cellVS=`#version 300 es
precision highp float;layout(location=0)in vec2 pos;layout(location=1)in vec4 transform;layout(location=2)in vec4 info;
out vec2 uv;out vec4 data;uniform float t;
void main(){uv=pos;data=info;vec2 p=transform.xy+(pos-.5)*transform.z;gl_Position=vec4(p/vec2(1280,720)*vec2(2,-2)+vec2(-1,1),0,1);}`;
const materialFS=`#version 300 es
precision highp float;in vec2 uv;in vec4 data;uniform sampler2D baseTex,mapsTex,fieldTex,noiseTex;uniform float t;
layout(location=0)out vec4 color;layout(location=1)out vec4 emission;
void main(){vec2 auv=(vec2(data.x,0)+clamp(uv,vec2(.002),vec2(.998)))/vec2(3,1);
vec4 base=texture(baseTex,auv);float alpha=base.a*data.w;if(alpha<.002)discard;
vec4 m=texture(mapsTex,auv),f=texture(fieldTex,auv);vec3 albedo=pow(max(base.rgb,vec3(0)),vec3(2.2));
float noise=texture(noiseTex,uv*2.4+vec2(t*.012,-t*.009)+data.z*.017).r;
float wave=.5+.5*sin(uv.y*26.-uv.x*10.-t*2.1+noise*4.5+data.z);float flow=pow(wave,4.);
vec2 normal=f.rg*2.-1.;float directional=clamp(dot(normal,vec2(-.65,-.76))*.5+.5,0.,1.);
float activation=smoothstep(3.7,5.,t)*(1.-smoothstep(7.8,10.,t));vec2 local=uv-vec2(.77,.47);float hot=exp(-dot(local,local)*125.);vec3 light;
if(data.y<.5){
 albedo*=mix(vec3(.60,.74,.85),vec3(.29,.48,.62),m.r*.5);
 light=vec3(.10,.38,.62)*(m.r*(.10+.30*directional+.24*flow)+m.g*(.045+.16*flow));
 light+=vec3(.24,.58,.68)*m.b*(.16+.35*noise);
 light+=vec3(.08,.21,.28)*f.b*(.05+flow*.10);
 light+=vec3(.16,.60,.64)*hot*activation*(m.r*.42+m.g*.2+m.b*.7);
}else if(data.y<1.5){
 // Base art carries the tissue structure. Only the cyan reticulum and granules
 // participate in light flow. The neutral membrane/nucleus remain readable.
 vec2 drift=vec2(sin(uv.y*8.-t*.65),cos(uv.x*7.+t*.5))*.002;
 vec2 shifted=(vec2(data.x,0)+clamp(uv+drift,vec2(.002),vec2(.998)))/vec2(3,1);
 vec4 moving=texture(mapsTex,shifted);
 float thread=moving.r*(1.-m.g*.9);
 float transmission=.74+.26*clamp(m.a*2.,0.,1.);
 alpha*=mix(transmission,1.,m.g);
 albedo*=.74+directional*.12;
 vec3 turquoise=vec3(.025,.46,.39);
 light=turquoise*thread*(.10+flow*.32)+vec3(.09,.62,.57)*m.b*(.12+.42*noise);
 float travel=max(0.,t-4.5)*.11;
 float response=exp(-pow((length(local)-travel)*32.,2.))*activation;
 light+=vec3(.06,.64,.51)*thread*(hot*.35+response*.32)*activation;
 light+=vec3(.035,.09,.14)*m.a*(.1+.2*directional)*(1.-m.g);
}else{
 albedo*=.64;vec3 tint=vec3(.95,.30,.025);
 light=tint*(m.r*(.18+.28*directional+.25*flow)+m.b*(.13+.3*noise)+m.g*(.045+flow*.13));
 light+=vec3(1.,.54,.075)*(m.b*.12+(.06+flow*.13)*f.b*.5);
}
light*=alpha;color=vec4(albedo*alpha+light*.52,alpha);emission=vec4(light,alpha);}`;
const bgFS=`#version 300 es
precision highp float;in vec2 uv;uniform sampler2D oldTex,newTex;uniform int bgMode;
layout(location=0)out vec4 color;layout(location=1)out vec4 emission;
void main(){bool right=uv.x>=.5;vec2 p=vec2(fract(uv.x*2.),1.-uv.y);
vec3 old=pow(texture(oldTex,vec2(p.x,fract(p.y*2.))).rgb,vec3(2.2))*.055+pow(vec3(.052,.038,.083),vec3(2.2));
vec3 revised=pow(texture(newTex,p).rgb,vec3(2.2))*.78;
bool useNew=bgMode==1||(bgMode==0&&right);color=vec4(useNew?revised:old,1);emission=vec4(0);}`;
const blurFS=`#version 300 es
precision highp float;in vec2 uv;uniform sampler2D src;uniform vec2 axis;out vec4 color;
void main(){vec3 c=texture(src,uv).rgb*.227027;c+=(texture(src,uv+axis*1.384615).rgb+texture(src,uv-axis*1.384615).rgb)*.316216;c+=(texture(src,uv+axis*3.230769).rgb+texture(src,uv-axis*3.230769).rgb)*.070270;color=vec4(c,1);}`;
const copyFS=`#version 300 es
precision highp float;in vec2 uv;uniform sampler2D src;out vec4 color;void main(){color=texture(src,uv);}`;
const outFS=`#version 300 es
precision highp float;in vec2 uv;uniform sampler2D scene,glow;uniform float gain;out vec4 color;
void main(){vec3 c=texture(scene,uv).rgb+texture(glow,uv).rgb*gain;float peak=max(c.r,max(c.g,c.b));c/=1.+max(peak-.6,0.)*.75;color=vec4(pow(max(c,vec3(0)),vec3(1./2.2)),1);}`;
//__SHARED_RENDER_HELPERS__
function layout(t){let count=0;function add(x,y,size,slot,kind,seed=0,alpha=1){instances.set([x,y,size/.9166667,0,slot,kind,seed,alpha],count++*8);}
for(let side=0;side<2;side++){const x=side*640;add(x+320,245,300,side,side,0);add(x+190,585,123,side,side,.7);add(x+440,585,80,side,side,1.7);
for(let i=0;i<24;i++){const a=i*2.39996,r=12+Math.sqrt(i)*5;add(x+300+Math.cos(a)*r+Math.sin(t*.35)*8,585+Math.sin(a)*r,12,2,2,i*.37);}
if(state.stress)for(let i=0;i<32;i++)add(x+42+(i%8)*80,120+Math.floor(i/8)*160,123,side,side,i*.73);
}stats.count=count;gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferSubData(gl.ARRAY_BUFFER,0,instances,0,count*8);}
function render(t,measure=false){const start=performance.now();state.time=((t%12)+12)%12;layout(state.time);stats.draws=0;let query;
if(measure&&timer&&stats.queries.length<10){query=gl.createQuery();gl.beginQuery(timer.TIME_ELAPSED_EXT,query);}
gl.disable(gl.BLEND);use(P.bg,R.scene);bind(P.bg,'oldTex',T.oldBackground,0);bind(P.bg,'newTex',T.newBackground,1);gl.uniform1i(un(P.bg,'bgMode'),state.background==='new'?1:state.background==='old'?2:0);tri();
gl.useProgram(P.cell.p);gl.bindVertexArray(vao);for(const [i,n]of ['base','maps','field','noise'].entries())bind(P.cell,n+'Tex',T[n],i);gl.uniform1f(un(P.cell,'t'),state.time);gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.drawArraysInstanced(gl.TRIANGLES,0,6,stats.count);stats.draws++;gl.disable(gl.BLEND);
if(state.bloom){use(P.copy,R.small);bind(P.copy,'src',R.scene.ts[1],0);tri();use(P.blur,R.x);bind(P.blur,'src',R.small.ts[0],0);gl.uniform2f(un(P.blur,'axis'),1/640,0);tri();use(P.blur,R.y);bind(P.blur,'src',R.x.ts[0],0);gl.uniform2f(un(P.blur,'axis'),0,1/360);tri();}
use(P.out,null);bind(P.out,'scene',R.scene.ts[0],0);bind(P.out,'glow',R.y.ts[0],1);gl.uniform1f(un(P.out,'gain'),state.bloom?.28:0);tri();if(query){gl.endQuery(timer.TIME_ELAPSED_EXT);stats.queries.push(query);}stats.cpu.push(performance.now()-start);if(stats.cpu.length>180)stats.cpu.shift();}
function drain(){if(!timer)return;const disjoint=gl.getParameter(timer.GPU_DISJOINT_EXT);while(stats.queries.length&&gl.getQueryParameter(stats.queries[0],gl.QUERY_RESULT_AVAILABLE)){const q=stats.queries.shift(),ms=gl.getQueryParameter(q,gl.QUERY_RESULT)/1e6;if(!disjoint){stats.gpu.push(ms);if(stats.gpu.length>180)stats.gpu.shift();}gl.deleteQuery(q);}if(disjoint){stats.gpu=[];for(const q of stats.queries)gl.deleteQuery(q);stats.queries=[];}}
function pc(a,p){const b=[...a].sort((x,y)=>x-y);return b.length?b[Math.floor((b.length-1)*p)]:null;}
function summary(){return {renderer,gpuMedianMs:pc(stats.gpu,.5),gpuP95Ms:pc(stats.gpu,.95),cpuSubmitMedianMs:pc(stats.cpu,.5),instances:stats.count,draws:stats.draws,scope:'WebGL prototype only; UrhoX/mobile performance remains unverified.'};}
function ui(){$('seek').value=state.time;$('clock').textContent=state.time.toFixed(1)+'s';const s=summary();$('metrics').textContent=`${state.time<4?'平静':state.time<8?'局部激活':'恢复'} · ${s.draws} 次绘制 · GPU ${s.gpuMedianMs?.toFixed(2)??'—'}ms · 浏览器测量`;}
let last=0;function animate(now){if(!state.benchmark){if(state.playing)state.time=(state.time+(last?Math.min(.1,(now-last)/1000):0))%12;render(state.time,true);drain();ui();}last=now;requestAnimationFrame(animate);}
$('play').onclick=()=>{state.playing=!state.playing;$('play').textContent=state.playing?'暂停':'播放';};$('seek').oninput=e=>{state.playing=false;$('play').textContent='播放';render(+e.target.value);ui();};$('background').onchange=e=>{state.background=e.target.value;render(state.time);};$('bloom').onchange=e=>{state.bloom=e.target.checked;render(state.time);};document.querySelectorAll('[data-t]').forEach(b=>b.onclick=()=>{state.playing=false;$('play').textContent='播放';render(+b.dataset.t);ui();});
const tick=()=>new Promise(r=>requestAnimationFrame(r));async function benchmark(){const prev={...state};state.benchmark=true;$('bench').disabled=true;const results=[];try{for(const stress of [false,true])for(const bloom of [false,true]){state.stress=stress;state.bloom=bloom;for(let i=0;i<20;i++){render(i/10);await tick();drain();}stats.cpu=[];stats.gpu=[];for(let i=0;i<90;i++){render(4+i/40,true);await tick();drain();}for(let i=0;i<8;i++){await tick();drain();}results.push({stress,bloom,...summary()});$('results').textContent=results.map(x=>`${x.stress?'压力':'常规'} ${x.bloom?'弱 Bloom':'无 Bloom'} / ${x.instances} instances / GPU median ${x.gpuMedianMs?.toFixed(3)??'—'}ms · P95 ${x.gpuP95Ms?.toFixed(3)??'—'}ms`).join('\n');}return {results,recordedAt:new Date().toISOString()};}finally{Object.assign(state,prev);state.benchmark=false;$('bench').disabled=false;render(state.time);ui();}}
$('bench').onclick=benchmark;window.lab={state,render,summary,benchmark,gl};
window.capture=(t,type='image/png')=>{render(t);const c=document.createElement('canvas');c.width=1280;c.height=790;const x=c.getContext('2d');x.fillStyle='#080e15';x.fillRect(0,0,1280,790);x.drawImage(canvas,0,70);x.fillStyle='#d7ece1';x.font='22px Microsoft YaHei';x.fillText('巨噬细胞 · 材质与环境重做',20,30);x.font='13px Microsoft YaHei';x.fillStyle='#9bbbad';x.fillText('独立 WebGL 样片 · 非 UrhoX 实机 · '+t.toFixed(1)+'s · '+(state.background==='split'?'整体对比':state.background==='new'?'相同新背景':'相同旧背景'),20,55);['上一版 · B＋弱 Bloom','重做版 · 内部荧光组织'].forEach((s,i)=>{x.fillStyle='#0a121bdf';x.fillRect(i*640,70,640,42);x.fillStyle='#cee6d8';x.font='18px Microsoft YaHei';x.fillText(s,i*640+16,97);});x.fillStyle='#0a121bdf';x.fillRect(0,538,1280,28);x.fillStyle='#bad5c5';x.font='13px Microsoft YaHei';x.fillText('下方为尺寸参考 · 巨噬细胞 123px / 80px · 病毒 12px · 局部反应为视觉示意',16,557);x.strokeStyle='#395044';x.beginPath();x.moveTo(640,70);x.lineTo(640,790);x.stroke();return c.toDataURL(type,.92).split(',')[1];};
window.ready=Promise.all(['base','maps','field','noise','oldBackground','newBackground'].map(n=>load(n,window.REWORK_TEXTURES[n]))).then(()=>{render(1.5);requestAnimationFrame(animate);return {renderer,atlas:[1152,384],bloomBuffer:[640,360],baseFormat:'RGBA16F',emissionAndBlurFormat:'RGBA8',renderTargetBytes:13824000,engineValidated:false};});
window.addEventListener('pagehide',()=>{for(const r of Object.values(R)){gl.deleteFramebuffer(r.fb);r.ts.forEach(tx=>gl.deleteTexture(tx));}Object.values(T).forEach(tx=>gl.deleteTexture(tx));Object.values(P).forEach(p=>gl.deleteProgram(p.p));stats.queries.forEach(q=>gl.deleteQuery(q));gl.deleteBuffer(quad);gl.deleteBuffer(buffer);gl.deleteVertexArray(vao);gl.deleteVertexArray(empty);});
