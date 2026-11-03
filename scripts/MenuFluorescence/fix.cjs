// Rebuild the menu approval prototype from the audited baseline. Source assets stay intact.
const fs=require('fs'),path=require('path'),{spawnSync}=require('child_process');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'validation/menu-fluorescence-fixed-20261015');fs.mkdirSync(out,{recursive:true});
const data=p=>'data:image/png;base64,'+fs.readFileSync(path.join(root,p)).toString('base64');
let html=fs.readFileSync(path.join(root,'validation/menu-fluorescence-20261015/preview.html'),'utf8');
function replace(a,b){if(!html.includes(a))throw Error('Missing patch boundary: '+a.slice(0,90));html=html.replace(a,b);}
// Maintain full precision through scene, emission, downsample and both blur targets.
replace('ts.push(tex(w,h,n===2&&i===0));','ts.push(tex(w,h,true));');
replace('albedo*=.60;light=vec3(.92,.065,.115)*(m.r*(.06+.25*directional+.30*flow)+m.g*(.07+.27*flow)+m.b*(.20+noise*.35));\n light+=vec3(.07,.012,.045)*f.b*(.2+flow*.5);',`
 float angle=atan(uv.y-.5,uv.x-.5);
 float breath=.5+.5*sin(t*.523598776+data.z);
 float arc=pow(.5+.5*sin(angle*2.-t*.523598776+data.z),5.);
 float travel=.5+.5*sin(uv.y*19.+uv.x*11.-t*1.04719755+data.z);
 float rim=m.r*(.035+.38*arc)*(.82+.18*breath);
 float threads=m.g*(.018+.07*pow(travel,5.));
 float sparks=m.b*(.12+.88*pow(.5+.5*sin(uv.x*43.+uv.y*29.-t*1.57079633+data.z),7.));
 albedo*=mix(.32,.59,f.b);
 light=vec3(1.,.10,.17)*(rim+threads)+vec3(1.,.42,.42)*sparks;
`);
// Soft-knee extraction selects emission hotspots, without blurring albedo or the UI.
replace('out vec4 color;void main(){color=texture(src,uv);}',`out vec4 color;void main(){vec3 c=texture(src,uv).rgb;
float peak=max(c.r,max(c.g,c.b));float knee=.08;float soft=clamp(peak-.16+knee,0.,2.*knee);soft=soft*soft/(4.*knee+.00001);
float contribution=max(peak-.16,soft)/max(peak,.00001);color=vec4(c*contribution,1.);}`);
replace("bloom?.25:0","bloom?.32:0");
// Expose render targets solely for diagnostic checks.
replace('window.lab={state,render,summary,benchmark,gl};','window.lab={state,render,summary,benchmark,gl,P,R,T,use,bind,tri};');
const layers=['cell_body.png','cell_vacuole.png','cell_membrane.png'].map(n=>data('assets/image/'+n));
const prepare=`
async function menuTextures(){
 const originals=await Promise.all(${JSON.stringify(layers)}.map(async src=>{const i=new Image();i.src=src;await i.decode();return i;}));
 const dim=originals[0].width,c=document.createElement('canvas');c.width=c.height=dim;const x=c.getContext('2d',{willReadFrequently:true});originals.forEach(i=>x.drawImage(i,0,0));
 const pixels=x.getImageData(0,0,dim,dim).data;let x0=dim,y0=dim,x1=0,y1=0;for(let y=0;y<dim;y++)for(let z=0;z<dim;z++)if(pixels[(y*dim+z)*4+3]>20){x0=Math.min(x0,z);y0=Math.min(y0,y);x1=Math.max(x1,z+1);y1=Math.max(y1,y+1);}
 const N=768,s=N*.90625/Math.max(x1-x0,y1-y0),w=Math.round((x1-x0)*s),h=Math.round((y1-y0)*s),ox=Math.floor((N-w)/2),oy=Math.floor((N-h)/2);
 function tile(img){const a=document.createElement('canvas');a.width=a.height=N;const q=a.getContext('2d',{willReadFrequently:true});q.imageSmoothingEnabled=false;q.drawImage(img,x0,y0,x1-x0,y1-y0,ox,oy,w,h);return a;}
 const base=tile(c),nucleus=tile(originals[1]).getContext('2d').getImageData(0,0,N,N).data,b=base.getContext('2d').getImageData(0,0,N,N).data;
 const map=document.createElement('canvas');map.width=map.height=N;const ctx=map.getContext('2d'),m=ctx.createImageData(N,N);let lit=0,occupied=0,nuclearLeak=0;
 for(let y=0;y<N;y++)for(let z=0;z<N;z++){const k=(y*N+z)*4,a=b[k+3]/255;if(a<.01)continue;occupied++;let minimum=a;for(const [dx,dy]of [[-3,0],[3,0],[0,-3],[0,3],[-2,-2],[2,2],[-2,2],[2,-2]]){const xx=Math.max(0,Math.min(N-1,z+dx)),yy=Math.max(0,Math.min(N-1,y+dy));minimum=Math.min(minimum,b[(yy*N+xx)*4+3]/255);}
 const rim=Math.max(0,a-minimum),n=nucleus[k+3]/255,r=b[k]/255,g=b[k+1]/255,bb=b[k+2]/255,lum=r*.2126+g*.7152+bb*.0722;
 const thread=Math.max(0,Math.min(1,(r-g-.15)*2))*Math.max(0,Math.min(1,(lum-.07)*5))*(1-n)*(1-rim)*a;
 const spark=Math.max(0,Math.min(1,(lum-.5)*3.3))*(1-n)*a*(1-rim);
 m.data[k]=Math.round(rim*255);m.data[k+1]=Math.round(thread*255);m.data[k+2]=Math.round(spark*255);m.data[k+3]=255;if(rim>.1||spark>.1)lit++;if(n>.9&&spark>.1)nuclearLeak++;
 }ctx.putImageData(m,0,0); const field=document.createElement('canvas');field.width=field.height=N;const fctx=field.getContext('2d'),fd=fctx.createImageData(N,N);for(let k=0;k<fd.data.length;k+=4){fd.data[k]=128;fd.data[k+1]=128;fd.data[k+2]=nucleus[k+3];fd.data[k+3]=255;}fctx.putImageData(fd,0,0);
 for(const [name,newTile]of [['base',base],['maps',map],['field',field]]){const old=new Image();old.src=window.FINAL_TEXTURES[name];await old.decode();const a=document.createElement('canvas');a.width=a.height=N*3;const q=a.getContext('2d');q.imageSmoothingEnabled=false;q.drawImage(old,0,0,N*3,N*3);q.clearRect(N*2,N*2,N,N);q.drawImage(newTile,N*2,N*2);window.FINAL_TEXTURES[name]=a.toDataURL();}
 window.menuMaskQA={tileSize:N,occupied,hotMaskPixels:lit,hotMaskCoverage:lit/occupied,nuclearLeak};
}
window.ready=menuTextures().then(()=>Promise.all(`;
replace("window.ready=Promise.all(",prepare);
replace("return {renderer,atlas:[768,768],bloomBuffer:[640,360],baseFormat:'RGBA16F',renderTargetBytes:13824000,engineValidated:false};});","return {renderer,atlas:[2304,2304],bloomBuffer:[640,360],allTargets:'RGBA16F',engineValidated:false};}));");
fs.writeFileSync(path.join(out,'preview.html'),html);
async function main(){const {chromium}=require('C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
try{const page=await browser.newPage({viewport:{width:1328,height:900},deviceScaleFactor:1}),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('file:///'+path.join(out,'preview.html').replaceAll('\\','/'));const info=await page.evaluate(()=>ready);await page.evaluate(()=>{lab.state.playing=false;lab.state.benchmark=true;lab.state.view='scene';lab.render(2);});await page.locator('#stage').screenshot({path:path.join(out,'menu-still.png')});
const checks=await page.evaluate(()=>{const {gl:g,R}=lab,n=1280*720*4;function pixels(t,bloom){lab.state.bloom=bloom;lab.render(t);const a=new Uint8Array(n);g.readPixels(0,0,1280,720,g.RGBA,g.UNSIGNED_BYTE,a);return a;}function diff(a,b){let count=0,sum=0,max=0;for(let i=0;i<n;i+=4){let d=0;for(let k=0;k<3;k++){const q=Math.abs(a[i+k]-b[i+k]);d+=q;sum+=q;max=Math.max(max,q);}if(d>3)count++;}return{pixels:count,mean:sum/(n*.75),max};}const a=pixels(2,false),b=pixels(2,true),c=pixels(5,true),d=pixels(0,true),e=pixels(12,true);const formats={};for(const [name,r]of Object.entries(R)){g.bindFramebuffer(g.FRAMEBUFFER,r.fb);formats[name]=r.ts.map((_,i)=>g.getFramebufferAttachmentParameter(g.FRAMEBUFFER,g.COLOR_ATTACHMENT0+i,g.FRAMEBUFFER_ATTACHMENT_COMPONENT_TYPE));}let nearWhite=0;for(let i=0;i<n;i+=4)if(b[i]>245&&b[i+1]>245&&b[i+2]>245)nearWhite++;return {bloom:diff(a,b),animation:diff(b,c),loop:diff(d,e),nearWhite,formats,masks:menuMaskQA,glError:g.getError()};});
if(errors.length||checks.glError||checks.animation.pixels<100||checks.bloom.pixels<100||checks.masks.nuclearLeak||Object.values(checks.formats).flat().some(x=>x!==5126))throw Error(JSON.stringify({errors,checks}));
// Capture fresh frames every run, so no stale pre-fix image can enter the new animation.
const frames=path.join(out,'frames');fs.mkdirSync(frames,{recursive:true});for(let i=0;i<144;i++){await page.evaluate(t=>{lab.state.bloom=true;lab.render(t);},i/12);await page.locator('#stage').screenshot({path:path.join(frames,String(i).padStart(3,'0')+'.png')});if(i%48===0)console.log('FRAME '+i+'/144');}
const ff='C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe';const r=spawnSync(ff,['-v','error','-framerate','12','-i',path.join(frames,'%03d.png'),'-vf','scale=960:-1,split[a][b];[a]palettegen=max_colors=192[p];[b][p]paletteuse=dither=bayer','-loop','0','-f','gif','pipe:1'],{windowsHide:true,maxBuffer:100*1024*1024});if(r.status)throw Error(r.stderr.toString());fs.writeFileSync(path.join(out,'menu-motion.gif'),r.stdout);
fs.writeFileSync(path.join(out,'qa.json'),JSON.stringify({info,checks,errors,scope:'Fixed standalone WebGL menu prototype; original art and runtime Lua unchanged.'},null,2));console.log('QA_OK '+JSON.stringify(checks));
}finally{await browser.close();}}
main().catch(e=>{console.error(e);process.exitCode=1});

