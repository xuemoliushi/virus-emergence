'use strict';
const $=id=>document.getElementById(id),canvas=$('gl'),gl=canvas.getContext('webgl2',{alpha:false,antialias:false,preserveDrawingBuffer:true,powerPreference:'high-performance'});
if(!gl)throw Error('需要 WebGL 2');
const state={time:0,playing:true,mode:'effect',variant:0,bloom:.28,stress:false,benchmark:false};
const timer=gl.getExtension('EXT_disjoint_timer_query_webgl2'),dbg=gl.getExtension('WEBGL_debug_renderer_info');
const renderer=dbg?gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER);
const stats={gpu:[],cpu:[],queries:[],draws:0,count:0};
const fullVS=`#version 300 es
precision highp float;out vec2 uv;
void main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);uv=p;gl_Position=vec4(p*2.-1.,0,1);}`;
const cellVS=`#version 300 es
precision highp float;layout(location=0)in vec2 pos;layout(location=1)in vec4 transform;layout(location=2)in vec4 info;
out vec2 uv;out vec4 data;uniform float t;
void main(){uv=pos;data=info;vec2 q=(pos-.5)*transform.z;float a=transform.w;
q*=1.+sin(t*1.3+info.z)*.008;vec2 p=transform.xy+mat2(cos(a),sin(a),-sin(a),cos(a))*q;
gl_Position=vec4(p/vec2(1280,720)*vec2(2,-2)+vec2(-1,1),0,1);}`;
const materialFS=`#version 300 es
precision highp float;in vec2 uv;in vec4 data;
uniform sampler2D baseTex,mapsTex,fieldTex,noiseTex;uniform float t;uniform int plain;
layout(location=0)out vec4 color;layout(location=1)out vec4 emission;
void main(){vec2 tile=vec2(mod(data.x,4.),floor(data.x/4.));vec2 auv=(tile+clamp(uv,vec2(.002),vec2(.998)))/vec2(4,2);
vec4 base=texture(baseTex,auv);float alpha=base.a*data.w;if(alpha<.002)discard;
vec3 albedo=pow(max(base.rgb,vec3(0)),vec3(2.2));if(plain==1){color=vec4(albedo*alpha,alpha);emission=vec4(0,0,0,alpha);return;}
vec4 m=texture(mapsTex,auv),f=texture(fieldTex,auv);float species=data.y;
float noise=texture(noiseTex,uv*2.4+vec2(t*.012,-t*.009)+data.z*.017).r;
float wave=.5+.5*sin(uv.y*26.-uv.x*10.-t*2.1+noise*4.5+data.z);
float flow=pow(wave,4.);vec2 normal=f.rg*2.-1.;
float directional=clamp(dot(normal,vec2(-.65,-.76))*.5+.5,0.,1.);
float activation=smoothstep(3.7,5.,t)*(1.-smoothstep(7.8,10.,t));
vec2 local=uv-vec2(.77,.47);float hot=exp(-dot(local,local)*125.);
vec3 tint;vec3 light;float core=.0;
if(species<.5){
 tint=vec3(.95,.30,.025);light=vec3(1.,.54,.075);
 albedo*=.64;
 float ridges=m.r*(.18+.28*directional+.25*flow)+m.b*(.13+.3*noise);
 core=(.06+flow*.13)*f.b;
 light=tint*(ridges+m.g*(.045+flow*.13))+light*(m.b*.12+core*.5);
 light+=tint*hot*activation*.15;
}else if(species<1.5){
 tint=vec3(.10,.38,.62);
 albedo*=mix(vec3(.60,.74,.85),vec3(.29,.48,.62),m.r*.5);
 light=tint*(m.r*(.10+.30*directional+.24*flow)+m.g*(.045+.16*flow));
 light+=vec3(.24,.58,.68)*m.b*(.16+.35*noise);
 light+=vec3(.08,.21,.28)*f.b*(.05+flow*.10);
 light+=vec3(.16,.60,.64)*hot*activation*(m.r*.42+m.g*.2+m.b*.7);
}else if(species<2.5){
 tint=vec3(.015,.49,.60);albedo*=.50;
 light=tint*(m.r*(.10+.28*directional+.27*flow)+m.g*(.07+flow*.23));
 light+=vec3(.045,.65,.70)*m.b*(.16+.28*noise);
 light+=tint*hot*activation*(m.r*.3+m.g*.35+m.b*.5);
}else{
 tint=vec3(.92,.065,.115);albedo*=.60;
 light=tint*(m.r*(.06+.25*directional+.30*flow)+m.g*(.07+.27*flow)+m.b*(.20+noise*.35));
 light+=vec3(.07,.012,.045)*f.b*(.2+flow*.5);
}
light*=alpha;
color=vec4(albedo*alpha+light*.52,alpha);emission=vec4(light,alpha);
}`;
const bgFS=`#version 300 es
precision highp float;in vec2 uv;uniform sampler2D background;
layout(location=0)out vec4 color;layout(location=1)out vec4 emission;
void main(){vec2 local=vec2(fract(uv.x*3.),fract(uv.y*2.));
vec3 b=pow(texture(background,vec2(local.x,1.-local.y)).rgb,vec3(2.2));
color=vec4(pow(vec3(.052,.038,.083),vec3(2.2))+b*.055,1);emission=vec4(0);}`;
const blurFS=`#version 300 es
precision highp float;in vec2 uv;uniform sampler2D src;uniform vec2 axis;out vec4 color;
void main(){vec3 c=texture(src,uv).rgb*.227027;c+=(texture(src,uv+axis*1.384615).rgb+texture(src,uv-axis*1.384615).rgb)*.316216;c+=(texture(src,uv+axis*3.230769).rgb+texture(src,uv-axis*3.230769).rgb)*.070270;color=vec4(c,1);}`;
const copyFS=`#version 300 es
precision highp float;in vec2 uv;uniform sampler2D src;out vec4 color;void main(){color=texture(src,uv);}`;
const outFS=`#version 300 es
precision highp float;in vec2 uv;uniform sampler2D scene,glow;uniform float gain;uniform int plain;out vec4 color;
void main(){vec3 c=texture(scene,uv).rgb+texture(glow,uv).rgb*gain;if(plain==0){float peak=max(c.r,max(c.g,c.b));c/=1.+max(peak-.6,0.)*.75;}color=vec4(pow(max(c,vec3(0)),vec3(1./2.2)),1);}`;
function sh(type,src){const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;}
function prog(v,f){const p=gl.createProgram(),a=sh(gl.VERTEX_SHADER,v),b=sh(gl.FRAGMENT_SHADER,f);gl.attachShader(p,a);gl.attachShader(p,b);gl.linkProgram(p);gl.deleteShader(a);gl.deleteShader(b);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(p));return {p,u:{}};}
const P={cell:prog(cellVS,materialFS),bg:prog(fullVS,bgFS),blur:prog(fullVS,blurFS),copy:prog(fullVS,copyFS),out:prog(fullVS,outFS)};
const un=(p,n)=>p.u[n]??(p.u[n]=gl.getUniformLocation(p.p,n));
const empty=gl.createVertexArray(),vao=gl.createVertexArray();gl.bindVertexArray(vao);
const quad=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,quad);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([0,0,1,0,0,1,0,1,1,0,1,1]),gl.STATIC_DRAW);gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,2,gl.FLOAT,false,0,0);
const buffer=gl.createBuffer(),instances=new Float32Array(1024*8);gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,instances.byteLength,gl.DYNAMIC_DRAW);
for(let i=1;i<=2;i++){gl.enableVertexAttribArray(i);gl.vertexAttribPointer(i,4,gl.FLOAT,false,32,(i-1)*16);gl.vertexAttribDivisor(i,1);}gl.bindVertexArray(null);
function tex(w,h){const t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,t);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA8,w,h,0,gl.RGBA,gl.UNSIGNED_BYTE,null);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);return t;}
function rt(w,h,n=1){const fb=gl.createFramebuffer();gl.bindFramebuffer(gl.FRAMEBUFFER,fb);const ts=[];for(let i=0;i<n;i++){ts.push(tex(w,h));gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0+i,gl.TEXTURE_2D,ts[i],0);}gl.drawBuffers(ts.map((_,i)=>gl.COLOR_ATTACHMENT0+i));if(gl.checkFramebufferStatus(gl.FRAMEBUFFER)!==gl.FRAMEBUFFER_COMPLETE)throw Error('渲染缓冲创建失败');return {fb,ts,w,h};}
const R={scene:rt(1280,720,2),small:rt(640,360),x:rt(640,360),y:rt(640,360)},T={};
async function load(name,url){const im=new Image();im.src=url;await im.decode();const tx=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,tx);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,im);for(const k of [gl.TEXTURE_MIN_FILTER,gl.TEXTURE_MAG_FILTER])gl.texParameteri(gl.TEXTURE_2D,k,gl.LINEAR);for(const k of [gl.TEXTURE_WRAP_S,gl.TEXTURE_WRAP_T])gl.texParameteri(gl.TEXTURE_2D,k,name==='noise'?gl.REPEAT:gl.CLAMP_TO_EDGE);T[name]=tx;}
function bind(p,n,tx,i){gl.activeTexture(gl.TEXTURE0+i);gl.bindTexture(gl.TEXTURE_2D,tx);gl.uniform1i(un(p,n),i);}
function use(p,r){gl.bindFramebuffer(gl.FRAMEBUFFER,r?r.fb:null);gl.viewport(0,0,r?r.w:1280,r?r.h:720);gl.useProgram(p.p);gl.bindVertexArray(empty);}
function tri(){gl.drawArrays(gl.TRIANGLES,0,3);stats.draws++;}
function layout(t){let count=0;const add=(x,y,size,slot,kind,seed=0,rotation=0,alpha=1)=>{instances.set([x,y,size/ .90625,rotation,slot,kind,seed,alpha],count++*8);};
const macro=1+state.variant%3,tc=4+state.variant%2;
add(213,190,138,0,0,0,t*.035);add(640,193,225,macro,1,.7,.02*Math.sin(t));add(1067,193,216,tc,2,1.5,.01*Math.sin(t));
// Source radii: virus .045m, macrophage .48m, T cell .30m; reference 128px/m.
add(350,552,120,6,3,1);add(1020,573,120,6,3,3);
add(760+Math.sin(t*.45)*10,555,122.88,macro,1,.5);add(955,555,76.8,tc,2,1);
const advance=Math.sin(t/12*Math.PI)*95;
for(let i=0;i<36;i++){const a=i*2.39996,rad=18+Math.sqrt(i)*6;const consumed=smooth(6.5,9.5,t)*Math.max(0,(i-17)/18);add(560+Math.cos(a)*rad+advance,555+Math.sin(a)*rad,11.52,0,0,i*.53,a+t*.04,1-consumed);}
for(let i=0;i<6;i++)add(143+i*27,304,11.52,0,0,i*.6);
if(state.stress){for(let i=0;i<512;i++){const x=22+(i%48)*26,y=440+Math.floor(i/48)*21;add(x,y,11.52,0,0,i*.11,i*.23);}for(let i=0;i<32;i++)add(50+(i%16)*77,480+Math.floor(i/16)*150,120,1+i%3,1,i*.5);}
stats.count=count;gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferSubData(gl.ARRAY_BUFFER,0,instances,0,count*8);}
function smooth(a,b,t){const v=Math.max(0,Math.min(1,(t-a)/(b-a)));return v*v*(3-2*v);}
function render(t,measure=false){const start=performance.now();state.time=((t%12)+12)%12;layout(state.time);stats.draws=0;let query;
if(measure&&timer&&stats.queries.length<10){query=gl.createQuery();gl.beginQuery(timer.TIME_ELAPSED_EXT,query);}
gl.disable(gl.BLEND);use(P.bg,R.scene);bind(P.bg,'background',T.background,0);tri();
gl.useProgram(P.cell.p);gl.bindVertexArray(vao);for(const [i,n]of ['base','maps','field','noise'].entries())bind(P.cell,n+'Tex',T[n],i);gl.uniform1f(un(P.cell,'t'),state.time);gl.uniform1i(un(P.cell,'plain'),state.mode==='plain'?1:0);gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.drawArraysInstanced(gl.TRIANGLES,0,6,stats.count);stats.draws++;gl.disable(gl.BLEND);
if(state.mode==='effect'){use(P.copy,R.small);bind(P.copy,'src',R.scene.ts[1],0);tri();use(P.blur,R.x);bind(P.blur,'src',R.small.ts[0],0);gl.uniform2f(un(P.blur,'axis'),1/640,0);tri();use(P.blur,R.y);bind(P.blur,'src',R.x.ts[0],0);gl.uniform2f(un(P.blur,'axis'),0,1/360);tri();}
use(P.out,null);bind(P.out,'scene',R.scene.ts[0],0);bind(P.out,'glow',R.y.ts[0],1);gl.uniform1f(un(P.out,'gain'),state.mode==='effect'?state.bloom:0);gl.uniform1i(un(P.out,'plain'),state.mode==='plain'?1:0);tri();
if(query){gl.endQuery(timer.TIME_ELAPSED_EXT);stats.queries.push(query);}stats.cpu.push(performance.now()-start);if(stats.cpu.length>180)stats.cpu.shift();return stats.draws;}
function drain(){if(!timer)return;const disjoint=gl.getParameter(timer.GPU_DISJOINT_EXT);while(stats.queries.length&&gl.getQueryParameter(stats.queries[0],gl.QUERY_RESULT_AVAILABLE)){const q=stats.queries.shift(),ms=gl.getQueryParameter(q,gl.QUERY_RESULT)/1e6;if(!disjoint){stats.gpu.push(ms);if(stats.gpu.length>180)stats.gpu.shift();}gl.deleteQuery(q);}if(disjoint){stats.gpu=[];for(const q of stats.queries)gl.deleteQuery(q);stats.queries=[];}}
function percentile(a,p){const b=[...a].sort((x,y)=>x-y);return b.length?b[Math.floor((b.length-1)*p)]:null;}
function summary(){return {renderer,gpuTimerSupported:!!timer,gpuMedianMs:percentile(stats.gpu,.5),gpuP95Ms:percentile(stats.gpu,.95),cpuSubmitMedianMs:percentile(stats.cpu,.5),instances:stats.count,draws:stats.draws,scope:'Browser WebGL2 only; not UrhoX/mobile performance.'};}
function ui(){$('clock').textContent=state.time.toFixed(1)+'s';$('seek').value=state.time;$('phase').textContent=state.time<4?'平静 · 膜与内部颗粒活动':state.time<8?'局部激活 · 吞噬侧与接触侧增强':'回落 · 保留内部结构';const s=summary();$('metrics').textContent=`${s.instances} 个实例 · ${s.draws} 次绘制 · GPU ${s.gpuMedianMs===null?'—':s.gpuMedianMs.toFixed(2)+'ms'} · 浏览器测量`;}
let last=0;function animate(now){if(!state.benchmark){if(state.playing)state.time=(state.time+(last?Math.min(.1,(now-last)/1000):0))%12;render(state.time,true);drain();ui();}last=now;requestAnimationFrame(animate);}
$('play').onclick=()=>{state.playing=!state.playing;$('play').textContent=state.playing?'暂停':'播放';};$('seek').oninput=e=>{state.playing=false;$('play').textContent='播放';render(+e.target.value);ui();};$('mode').onchange=e=>{state.mode=e.target.value;render(state.time);};$('variant').onchange=e=>{state.variant=+e.target.value;render(state.time);};$('bloom').oninput=e=>{state.bloom=+e.target.value;render(state.time);};document.querySelectorAll('[data-t]').forEach(b=>b.onclick=()=>{state.playing=false;$('play').textContent='播放';render(+b.dataset.t);ui();});
const tick=()=>new Promise(r=>requestAnimationFrame(r));
async function benchmark(){if(state.benchmark)return;const previous={...state};state.benchmark=true;$('bench').disabled=true;const results=[];try{for(const stress of [false,true])for(const mode of ['plain','noglow','effect']){state.stress=stress;state.mode=mode;for(let i=0;i<20;i++){render(i/10);await tick();drain();}stats.cpu=[];stats.gpu=[];for(let i=0;i<90;i++){render(4+i/40,true);await tick();drain();}for(let i=0;i<8;i++){await tick();drain();}results.push({stress,mode,...summary()});$('result').textContent=results.map(x=>`${x.stress?'压力':'常规'} ${x.mode.padEnd(7)} / ${x.instances} instances / GPU median ${x.gpuMedianMs?.toFixed(3)??'unavailable'}ms · P95 ${x.gpuP95Ms?.toFixed(3)??'unavailable'}ms`).join('\n');}window.lastBenchmark={results,recordedAt:new Date().toISOString()};return window.lastBenchmark;}finally{Object.assign(state,previous);state.benchmark=false;$('bench').disabled=false;render(state.time);ui();}}
$('bench').onclick=benchmark;
window.capture=(t,type='image/png')=>{render(t);const c=document.createElement('canvas');c.width=1280;c.height=790;const x=c.getContext('2d');x.fillStyle='#080e15';x.fillRect(0,0,1280,790);x.drawImage(canvas,0,70);x.font='22px Microsoft YaHei';x.fillStyle='#d7ece1';x.fillText('病毒与免疫细胞 · B＋弱 Bloom',20,30);x.font='13px Microsoft YaHei';x.fillStyle='#9bbbad';x.fillText('独立 WebGL 材质样片 · 非 UrhoX 实机 · '+t.toFixed(1)+'s · 形态组合 '+(state.variant+1),20,55);['病毒 · 琥珀亮核','巨噬细胞 · 珍珠蓝透光','T 细胞 · 青蓝流纹'].forEach((s,i)=>{x.fillStyle='#0a121bdf';x.fillRect(i*1280/3,70,1280/3,42);x.fillStyle='#cee6d8';x.font='17px Microsoft YaHei';x.fillText(s,i*1280/3+16,96);});x.fillStyle='#0a121bdf';x.fillRect(0,430,1280,34);x.fillStyle='#bad5c5';x.font='14px Microsoft YaHei';x.fillText('同屏尺度参考 · 细胞 120px / 巨噬 123px / T 细胞 77px / 病毒 12px · 局部反应为示意',16,452);return c.toDataURL(type,.92).split(',')[1];};
window.lab={state,render,summary,benchmark,gl};
window.ready=Promise.all(['base','maps','field','noise','background'].map(n=>load(n,window.AGENT_TEXTURES[n]))).then(()=>{render(1.5);requestAnimationFrame(animate);return {renderer,atlas:[1024,512],bloomBuffer:[640,360],renderTargetBytes:(1280*720*2+640*360*3)*4,engineValidated:false};});
window.addEventListener('pagehide',()=>{for(const r of Object.values(R)){gl.deleteFramebuffer(r.fb);r.ts.forEach(tx=>gl.deleteTexture(tx));}Object.values(T).forEach(tx=>gl.deleteTexture(tx));Object.values(P).forEach(p=>gl.deleteProgram(p.p));stats.queries.forEach(q=>gl.deleteQuery(q));gl.deleteBuffer(quad);gl.deleteBuffer(buffer);gl.deleteVertexArray(vao);gl.deleteVertexArray(empty);});
