'use strict';
const $=id=>document.getElementById(id),canvas=$('gl'),gl=canvas.getContext('webgl2',{alpha:false,antialias:false,preserveDrawingBuffer:true,powerPreference:'high-performance'});
if(!gl)throw Error('需要 WebGL 2');if(!gl.getExtension('EXT_color_buffer_float'))throw Error('需要半浮点颜色缓冲以保持暗部渐变');
const state={time:0,playing:true,view:'gallery',mode:'new',variant:0,background:'final',lighting:'soft',healthy:'new',bloom:true,stress:false,benchmark:false};
const timer=gl.getExtension('EXT_disjoint_timer_query_webgl2'),dbg=gl.getExtension('WEBGL_debug_renderer_info');
const renderer=dbg?gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER),stats={gpu:[],cpu:[],queries:[],draws:0,count:0};
const fullVS=`#version 300 es
precision highp float;out vec2 uv;void main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);uv=p;gl_Position=vec4(p*2.-1.,0,1);}`;
const cellVS=`#version 300 es
precision highp float;layout(location=0)in vec2 pos;layout(location=1)in vec4 transform;layout(location=2)in vec4 info;
out vec2 uv;out vec4 data;uniform float t;
void main(){uv=pos;data=info;vec2 p=transform.xy+(pos-.5)*transform.z;gl_Position=vec4(p/vec2(1280,720)*vec2(2,-2)+vec2(-1,1),0,1);}`;
const materialFS=`#version 300 es
precision highp float;in vec2 uv;in vec4 data;uniform sampler2D baseTex,mapsTex,fieldTex,noiseTex;uniform float t,highlight;uniform int plain;
layout(location=0)out vec4 color;layout(location=1)out vec4 emission;
void main(){vec2 tile=vec2(mod(data.x,4.),floor(data.x/4.));vec2 auv=(tile+clamp(uv,vec2(.002),vec2(.998)))/vec2(4.,3.);
vec4 base=texture(baseTex,auv);float alpha=base.a*data.w;if(alpha<.002)discard;vec3 albedo=pow(max(base.rgb,vec3(0)),vec3(2.2));
if(plain==1){color=vec4(albedo*alpha,alpha);emission=vec4(0,0,0,alpha);return;}
vec4 m=texture(mapsTex,auv),f=texture(fieldTex,auv);float noise=texture(noiseTex,uv*2.4+vec2(t*.012,-t*.009)+data.z*.017).r;
float wave=.5+.5*sin(uv.y*26.-uv.x*10.-t*2.1+noise*4.5+data.z);float flow=pow(wave,4.);
float directional=clamp(dot(f.rg*2.-1.,vec2(-.65,-.76))*.5+.5,0.,1.);
float activation=smoothstep(3.7,5.,t)*(1.-smoothstep(7.8,10.,t));vec2 local=uv-vec2(.77,.47);float hot=exp(-dot(local,local)*125.);vec3 light;
if(data.y<.5){
 albedo*=.78;float granular=m.b*(.10+.24*noise);float thread=m.r*(.05+flow*.17);
 light=vec3(.88,.25,.012)*(thread+granular)+vec3(.75,.34,.018)*m.b*.09;
 light+=vec3(.65,.22,.01)*hot*activation*m.r*.13;
}else if(data.y<2.5){
 vec2 drift=vec2(sin(uv.y*8.-t*.65),cos(uv.x*7.+t*.5))*.002;
 vec2 shifted=(tile+clamp(uv+drift,vec2(.002),vec2(.998)))/vec2(4.,3.);vec4 moving=texture(mapsTex,shifted);
 float thread=moving.r*(1.-m.g*.9);float transmission=.74+.26*clamp(m.a*2.,0.,1.);alpha*=mix(transmission,1.,m.g);
 albedo*=.74+directional*.12;
 vec3 tint=data.y<1.5?vec3(.025,.46,.39):vec3(.025,.35,.54);
 vec3 particle=data.y<1.5?vec3(.09,.62,.57):vec3(.06,.48,.67);
 light=tint*thread*(.10+flow*.32)+particle*m.b*(.12+.42*noise);
 float travel=max(0.,t-4.5)*.11;float response=exp(-pow((length(local)-travel)*32.,2.))*activation;
 light+=particle*thread*(hot*.35+response*.32)*activation;
 light+=vec3(.035,.09,.14)*m.a*(.1+.2*directional)*(1.-m.g);
}else{
 if(data.x>8.5){
   albedo*=.60;light=vec3(.92,.065,.115)*(m.r*(.06+.25*directional+.30*flow)+m.g*(.07+.27*flow)+m.b*(.20+noise*.35));
   light+=vec3(.07,.012,.045)*f.b*(.2+flow*.5);
 }else{
   float thread=m.r*(1.-m.g*.9);float transmission=.74+.26*clamp(m.a*2.,0.,1.);alpha*=mix(transmission,1.,m.g);
   albedo*=.54+directional*.07;
   light=vec3(.56,.025,.065)*thread*(.045+flow*.16)+vec3(.70,.08,.14)*m.b*(.10+.25*noise);
   light+=vec3(.30,.015,.045)*thread*hot*activation*.12;
 }
}
// Broad reflected light is kept out of the emission buffer: bright material need not bloom.
vec2 shoulder=(uv-vec2(.34,.31))/vec2(.25,.29);
vec2 glintPos=(uv-vec2(.34,.245))/vec2(.115,.055);
float shoulderLight=exp(-dot(shoulder,shoulder)*1.35);
float glint=exp(-dot(glintPos,glintPos)*1.8);
vec3 reflectionTint=data.y<.5?vec3(1.,.67,.29):data.y<2.5?vec3(.48,.77,.91):vec3(1.,.53,.58);
vec3 reflected=reflectionTint*(shoulderLight*.050+glint*.15)*m.a*(1.-m.g*.55)*highlight;
albedo*=1.+highlight*(.38+shoulderLight*.3);
light*=alpha;color=vec4((albedo+reflected)*alpha+light*.52,alpha);emission=vec4(light,alpha);}`;
const bgFS=`#version 300 es
precision highp float;in vec2 uv;uniform sampler2D finalTex,approvedTex,oldTex;uniform int bgMode;uniform float highlight;
layout(location=0)out vec4 color;layout(location=1)out vec4 emission;
void main(){vec2 p=vec2(uv.x,1.-uv.y);vec3 c;
if(bgMode==0)c=pow(texture(finalTex,p).rgb,vec3(2.2))*.72;
else if(bgMode==1)c=pow(texture(approvedTex,p).rgb,vec3(2.2))*.78;
else c=pow(texture(oldTex,p).rgb,vec3(2.2))*.055+pow(vec3(.052,.038,.083),vec3(2.2));
float fill=exp(-dot((p-vec2(.48,.43))*vec2(1.2,1.),(p-vec2(.48,.43))*vec2(1.2,1.))*3.);
c=c*(1.+highlight*.32)+vec3(.0012,.0017,.0028)*highlight*(.3+.7*fill);
color=vec4(c,1);emission=vec4(0);}`;
const blurFS=`#version 300 es
precision highp float;in vec2 uv;uniform sampler2D src;uniform vec2 axis;out vec4 color;
void main(){vec3 c=texture(src,uv).rgb*.227027;c+=(texture(src,uv+axis*1.384615).rgb+texture(src,uv-axis*1.384615).rgb)*.316216;c+=(texture(src,uv+axis*3.230769).rgb+texture(src,uv-axis*3.230769).rgb)*.070270;color=vec4(c,1);}`;
const copyFS=`#version 300 es
precision highp float;in vec2 uv;uniform sampler2D src;out vec4 color;void main(){color=texture(src,uv);}`;
const outFS=`#version 300 es
precision highp float;in vec2 uv;uniform sampler2D scene,glow;uniform float gain;out vec4 color;
void main(){vec3 c=texture(scene,uv).rgb+texture(glow,uv).rgb*gain;float peak=max(c.r,max(c.g,c.b));c/=1.+max(peak-.6,0.)*.75;color=vec4(pow(max(c,vec3(0)),vec3(1./2.2)),1);}`;
//__SHARED_RENDER_HELPERS__
function layout(t){let count=0;const slot=kind=>state.mode==='old'?(kind===0?4:kind===1?5:6+state.variant):(kind===0?0:kind===1?1:2+state.variant);
function add(x,y,size,kind,seed=0,alpha=1){instances.set([x,y,size/.90625,0,kind===3?(state.mode==='old'||state.healthy==='old'?9:8):slot(kind),kind,seed,alpha],count++*8);}
if(state.view==='background'){stats.count=0;return;}
if(state.view==='gallery'){
 add(160,193,130,0);add(480,193,205,1,.7);add(800,193,195,2,1.4);add(1120,193,210,3,.2);
 for(let i=0;i<6;i++)add(100+i*24,310,12,0,i*.3);
 add(340,551,120,3,1);add(1020,575,120,3,2);add(760,554,123,1,.5);add(950,550,77,2,1);
 for(let i=0;i<36;i++){const a=i*2.39996,r=18+Math.sqrt(i)*6;add(560+Math.cos(a)*r+Math.sin(t/12*Math.PI)*85,552+Math.sin(a)*r,12,0,i*.53);}
}else{
 [[230,205],[1040,210],[340,560],[1080,555]].forEach((p,i)=>add(p[0],p[1],120,3,i*.8));
 add(690+Math.sin(t*.35)*8,300,123,1,.5);add(895,565,123,1,2);add(755,420,77,2,1);add(495,550,77,2,2.3);
 for(let cloud=0;cloud<2;cloud++)for(let i=0;i<42;i++){const a=i*2.39996,r=15+Math.sqrt(i)*7;add(510+cloud*460+Math.cos(a)*r+Math.sin(t*.25)*18,300+cloud*100+Math.sin(a)*r,12,0,i*.37+cloud);}
}
if(state.stress){for(let i=0;i<512;i++)add(25+i%48*26,420+Math.floor(i/48)*23,12,0,i*.13);for(let i=0;i<32;i++)add(50+i%16*77,470+Math.floor(i/16)*165,i%2?77:123,i%2?2:1,i*.7);}
stats.count=count;gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferSubData(gl.ARRAY_BUFFER,0,instances,0,count*8);}
function render(t,measure=false){const start=performance.now();state.time=((t%12)+12)%12;layout(state.time);stats.draws=0;let query;
if(measure&&timer&&stats.queries.length<10){query=gl.createQuery();gl.beginQuery(timer.TIME_ELAPSED_EXT,query);}
gl.disable(gl.BLEND);use(P.bg,R.scene);bind(P.bg,'finalTex',T.background,0);bind(P.bg,'approvedTex',T.approvedBackground,1);bind(P.bg,'oldTex',T.oldBackground,2);gl.uniform1f(un(P.bg,'highlight'),state.lighting==='soft'?1:0);gl.uniform1i(un(P.bg,'bgMode'),state.background==='final'?0:state.background==='approved'?1:2);tri();
if(stats.count){gl.useProgram(P.cell.p);gl.bindVertexArray(vao);for(const [i,n]of ['base','maps','field','noise'].entries())bind(P.cell,n+'Tex',T[n],i);gl.uniform1f(un(P.cell,'highlight'),state.lighting==='soft'?1:0);gl.uniform1f(un(P.cell,'t'),state.time);gl.uniform1i(un(P.cell,'plain'),state.mode==='old'?1:0);gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.drawArraysInstanced(gl.TRIANGLES,0,6,stats.count);stats.draws++;gl.disable(gl.BLEND);}
const bloom=state.bloom&&state.mode==='new'&&stats.count>0;
if(bloom){use(P.copy,R.small);bind(P.copy,'src',R.scene.ts[1],0);tri();use(P.blur,R.x);bind(P.blur,'src',R.small.ts[0],0);gl.uniform2f(un(P.blur,'axis'),1/640,0);tri();use(P.blur,R.y);bind(P.blur,'src',R.x.ts[0],0);gl.uniform2f(un(P.blur,'axis'),0,1/360);tri();}
use(P.out,null);bind(P.out,'scene',R.scene.ts[0],0);bind(P.out,'glow',R.y.ts[0],1);gl.uniform1f(un(P.out,'gain'),bloom?.25:0);tri();if(query){gl.endQuery(timer.TIME_ELAPSED_EXT);stats.queries.push(query);}stats.cpu.push(performance.now()-start);if(stats.cpu.length>180)stats.cpu.shift();}
function drain(){if(!timer)return;const disjoint=gl.getParameter(timer.GPU_DISJOINT_EXT);while(stats.queries.length&&gl.getQueryParameter(stats.queries[0],gl.QUERY_RESULT_AVAILABLE)){const q=stats.queries.shift(),ms=gl.getQueryParameter(q,gl.QUERY_RESULT)/1e6;if(!disjoint){stats.gpu.push(ms);if(stats.gpu.length>180)stats.gpu.shift();}gl.deleteQuery(q);}if(disjoint){stats.gpu=[];for(const q of stats.queries)gl.deleteQuery(q);stats.queries=[];}}
function pc(a,p){const b=[...a].sort((x,y)=>x-y);return b.length?b[Math.floor((b.length-1)*p)]:null;}
function summary(){return {renderer,gpuMedianMs:pc(stats.gpu,.5),gpuP95Ms:pc(stats.gpu,.95),cpuSubmitMedianMs:pc(stats.cpu,.5),instances:stats.count,draws:stats.draws,scope:'Browser WebGL only; UrhoX/mobile remains UNDETERMINED.'};}
function ui(){$('seek').value=state.time;$('clock').textContent=state.time.toFixed(1)+'s';$('stage').dataset.view=state.view;$('phase').textContent=state.time<4?'平静 · 内部活动':state.time<8?'局部激活 · 颗粒与细丝响应':'恢复 · 回到平静';const s=summary();$('metrics').textContent=`${s.instances} 个实例 · ${s.draws} 次绘制 · GPU ${s.gpuMedianMs?.toFixed(2)??'—'}ms · 浏览器测量`;}
let last=0;function animate(now){if(!state.benchmark){if(state.playing)state.time=(state.time+(last?Math.min(.1,(now-last)/1000):0))%12;render(state.time,true);drain();ui();}last=now;requestAnimationFrame(animate);}
$('play').onclick=()=>{state.playing=!state.playing;$('play').textContent=state.playing?'暂停':'播放';};$('seek').oninput=e=>{state.playing=false;$('play').textContent='播放';render(+e.target.value);ui();};
for(const id of ['view','mode','background','variant','lighting','healthy'])$(id).onchange=e=>{state[id]=id==='variant'?+e.target.value:e.target.value;render(state.time);ui();};$('bloom').onchange=e=>{state.bloom=e.target.checked;render(state.time);ui();};document.querySelectorAll('[data-t]').forEach(b=>b.onclick=()=>{state.playing=false;$('play').textContent='播放';render(+b.dataset.t);ui();});
const tick=()=>new Promise(r=>requestAnimationFrame(r));async function benchmark(){const prev={...state};state.benchmark=true;$('bench').disabled=true;state.view='scene';const results=[];try{for(const stress of [false,true])for(const mode of ['old','new'])for(const bloom of mode==='old'?[false]:[false,true]){state.stress=stress;state.mode=mode;state.bloom=bloom;for(let i=0;i<20;i++){render(i/10);await tick();drain();}stats.cpu=[];stats.gpu=[];for(let i=0;i<90;i++){render(4+i/40,true);await tick();drain();}for(let i=0;i<8;i++){await tick();drain();}results.push({stress,mode,bloom,...summary()});$('results').textContent=results.map(x=>`${x.stress?'压力':'常规'} ${x.mode} ${x.bloom?'弱 Bloom':'无 Bloom'} / ${x.instances} instances / GPU p50 ${x.gpuMedianMs?.toFixed(3)??'—'}ms · p95 ${x.gpuP95Ms?.toFixed(3)??'—'}ms`).join('\n');}return {results,recordedAt:new Date().toISOString()};}finally{Object.assign(state,prev);state.benchmark=false;$('bench').disabled=false;render(state.time);ui();}}
$('bench').onclick=benchmark;
$('stress').onchange=e=>{state.stress=e.target.checked;render(state.time);ui();};
const assets=[['healthy','健康红细胞','新作 · 统一薄膜与荧光材质'],['virus','病毒','琥珀核心 · 新版'],['macrophage','巨噬细胞','已确认的重做版'],['tcell-01','T 细胞 · 形态一','青蓝细丝 · 新版'],['tcell-02','T 细胞 · 形态二','椭圆轮廓 · 新版'],['background','组织背景','最终背景 · 新版']];
for(const [id,name,desc]of assets){const card=document.createElement('article');card.className='card';const img=document.createElement('img');img.src=window.FINAL_THUMBS[id];img.alt=name;const body=document.createElement('div');body.className='body';const title=document.createElement('strong');title.textContent=name;const small=document.createElement('small');small.textContent=desc;const button=document.createElement('button');button.textContent='查看原图';button.dataset.asset=id;button.onclick=()=>{$('assetTitle').textContent=name;$('assetImage').src='art/'+id+'.png';$('assetImage').alt=name;$('assetDownload').href='art/'+id+'.png';$('assetDownload').download=id+'.png';$('assetDialog').showModal();};body.append(title,small,button);card.append(img,body);$('assets').append(card);}
$('closeAsset').onclick=()=>$('assetDialog').close();$('assetDialog').onclick=e=>{if(e.target===$('assetDialog'))$('assetDialog').close();};
window.lab={state,render,summary,benchmark,gl};window.capture=(t,type='image/png')=>{render(t);const c=document.createElement('canvas');c.width=1280;c.height=790;const x=c.getContext('2d');x.fillStyle='#08110c';x.fillRect(0,0,1280,790);x.drawImage(canvas,0,70);x.fillStyle='#d5eadd';x.font='22px Microsoft YaHei';x.fillText('生物荧光 · 全细胞统一高光版',20,30);x.font='13px Microsoft YaHei';x.fillStyle='#9fbca9';x.fillText((state.lighting==='soft'?'适量高光':'上一版照明')+' · 独立视觉稿 · '+t.toFixed(1)+'s · T 细胞形态 '+(state.variant+1),20,55);if(state.view==='gallery'){['病毒 · 琥珀','巨噬细胞 · 珍珠青','T 细胞 · 青蓝','健康红细胞 · 珊瑚红'].forEach((s,i)=>{x.fillStyle='#09140fdf';x.fillRect(i*1280/4,70,1280/4,40);x.fillStyle='#c5dfce';x.font='17px Microsoft YaHei';x.fillText(s,i*1280/4+16,96);});x.fillStyle='#09140fdf';x.fillRect(0,430,1280,28);x.fillStyle='#b6d0bd';x.font='13px Microsoft YaHei';x.fillText('同屏尺度参考 · 巨噬 123px / T 细胞 77px / 病毒 12px / 健康红细胞 120px · 新版统一材质',16,449);}return c.toDataURL(type,.92).split(',')[1];};
window.ready=Promise.all(['base','maps','field','noise','background','approvedBackground','oldBackground'].map(n=>load(n,window.FINAL_TEXTURES[n]))).then(()=>{render(1.5);requestAnimationFrame(animate);return {renderer,atlas:[1024,768],bloomBuffer:[640,360],baseFormat:'RGBA16F',renderTargetBytes:13824000,engineValidated:false};});
window.addEventListener('pagehide',()=>{for(const r of Object.values(R)){gl.deleteFramebuffer(r.fb);r.ts.forEach(tx=>gl.deleteTexture(tx));}Object.values(T).forEach(tx=>gl.deleteTexture(tx));Object.values(P).forEach(p=>gl.deleteProgram(p.p));stats.queries.forEach(q=>gl.deleteQuery(q));gl.deleteBuffer(quad);gl.deleteBuffer(buffer);gl.deleteVertexArray(vao);gl.deleteVertexArray(empty);});
