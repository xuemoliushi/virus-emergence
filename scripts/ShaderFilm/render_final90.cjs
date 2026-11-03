/* Local server, shader QA and deterministic 1080p/24fps movie export. */
const fs=require('fs'),path=require('path'),http=require('http'),crypto=require('crypto');
const {spawn}=require('child_process');
const ROOT=path.resolve(__dirname,'../..'),OUT=path.join(ROOT,'assets/video/emergence_final90');
const NODE_DEPS=process.env.SHADER_NODE_DEPS||'C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const EDGE=process.env.SHADER_BROWSER||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const FF=process.env.SHADER_FFMPEG||'C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe';
const WITH_SUBS=false;
const MIME={'.html':'text/html;charset=utf-8','.js':'application/javascript;charset=utf-8','.glsl':'text/plain','.vert':'text/plain','.frag':'text/plain','.json':'application/json;charset=utf-8','.png':'image/png','.jpg':'image/jpeg','.wav':'audio/wav','.mp4':'video/mp4'};
function server(){return http.createServer((req,res)=>{
 let p;try{p=path.resolve(ROOT,'.'+decodeURIComponent(req.url.split('?')[0]));}catch{res.writeHead(400);res.end();return;}
 if(!p.startsWith(ROOT+path.sep)){res.writeHead(403);res.end();return;}
 fs.stat(p,(e,st)=>{if(e||!st.isFile()){res.writeHead(404);res.end();return;}
 res.setHeader('Content-Type',MIME[path.extname(p)]||'application/octet-stream');res.setHeader('Accept-Ranges','bytes');
 const m=/^bytes=(\d+)-(\d*)$/.exec(req.headers.range||'');
 if(m){const start=+m[1],end=Math.min(m[2]?+m[2]:st.size-1,st.size-1);if(start>end){res.writeHead(416);res.end();return;}
 res.writeHead(206,{'Content-Range':`bytes ${start}-${end}/${st.size}`,'Content-Length':end-start+1});fs.createReadStream(p,{start,end}).pipe(res);}
 else {res.setHeader('Content-Length',st.size);fs.createReadStream(p).pipe(res);}
 });
});}
async function page(port){
 const {chromium}=require(path.join(NODE_DEPS,'playwright'));
 const b=await chromium.launch({executablePath:EDGE,headless:true,args:['--enable-unsafe-swiftshader','--disable-background-timer-throttling','--disable-renderer-backgrounding','--autoplay-policy=no-user-gesture-required']});
 const p=await b.newPage({viewport:{width:1280,height:900},deviceScaleFactor:1});const errors=[];
 p.on('pageerror',e=>errors.push(e.message));p.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 await p.goto(`http://127.0.0.1:${port}/assets/video/emergence_final90/index.html`);
 const info=await p.evaluate(()=>window.ready);
 return {b,p,info,errors};
}
function pipeProcess(args,file,log){
 const err=fs.openSync(log,'w');const p=spawn(FF,args,{stdio:['pipe','pipe',err],windowsHide:true});const out=fs.createWriteStream(file);p.stdout.pipe(out);
 const done=Promise.all([new Promise((yes,no)=>{p.on('error',no);p.on('exit',c=>c===0?yes():no(Error('FFmpeg exit '+c)));}),new Promise((yes,no)=>{out.on('finish',yes);out.on('error',no);})]).finally(()=>fs.closeSync(err));
 return {p,done};
}
async function qa(port){
 const {b,p,info,errors}=await page(port);console.log(JSON.stringify(info));
 const times=[0,2,6,10,13,15,17,19,21,23,25,27,29,30,31.6,33,36,39,42.96,43,43.5,44,44.5,45,45.5,46,49,50,52,54,56,58,59,59.96,60,60.5,61.3,62,63.5,64.5,65.45,66,68,70,72,73,74,76,78,80,81.5,84,86.96,87,88.5,89.5];
 for(const t of times){let f=Math.round(t*24);const data=await p.evaluate(f=>window.capture(f,true,'image/png'),f);fs.writeFileSync(path.join(OUT,'qa',`frame_${f.toString().padStart(4,'0')}.png`),Buffer.from(data,'base64'));console.log('QA',t);}
 for(const t of [60.75,61,61.125]){const f=Math.round(t*24),data=await p.evaluate(f=>capture(f,true,'image/png'),f);fs.writeFileSync(path.join(OUT,'qa',`frame_${String(f).padStart(4,'0')}.png`),Buffer.from(data,'base64'));}
 const hashes={};for(const f of [312,576,864,1200,1368,1416,1512,1728,1944,2148]){hashes[f]=crypto.createHash('sha256').update(await p.evaluate(f=>capture(f,true,'image/png'),f)).digest('hex');}
 for(const f of [2148,576,1728,312,1944,1200,864,1416,1512,1368]){const h=crypto.createHash('sha256').update(await p.evaluate(f=>capture(f,true,'image/png'),f)).digest('hex');if(h!==hashes[f])throw Error('Random seek changed frame '+f);}
 // Actual player controls and audio seeking are checked, not merely frame export.
 const framing=await p.evaluate(()=>{
  const quant=(a,q)=>{a.sort((x,y)=>x-y);const f=(a.length-1)*q,i=Math.floor(f);return a[i]*(1-(f-i))+a[Math.min(i+1,a.length-1)]*(f-i);};
  return [19,21,23,25,27].map(t=>{denseFlock.sample(t);const v=denseFlock.view(t),s=denseFlock.state,x=[],y=[];
   for(let i=0;i<denseFlock.meta.hero;i++){const k=i*7,px=960+1450*(s[k]-v.track)/s[k+2],py=450-1450*s[k+1]/s[k+2];x.push(v.root[0]+(px-v.hx)*v.zoom);y.push(v.root[1]+(py-v.hy)*v.zoom-v.fallcam);}
   const bounds=[quant(x,.01),quant(y,.01),quant(x,.99),quant(y,.99)];return {time:t,bounds,center:[(bounds[0]+bounds[2])/2,(bounds[1]+bounds[3])/2]};});
 });
 for(const f of framing)if(Math.abs(f.center[0]-960)>70||Math.abs(f.center[1]-540)>70)throw Error('Flock not centered: '+JSON.stringify(f));
 await p.locator('[data-time="52"]').click();await p.locator('#play').click();await p.waitForTimeout(1200);
 const playback=await p.evaluate(()=>({time:document.getElementById('audio').currentTime,paused:document.getElementById('audio').paused}));
 await p.locator('#play').click();if(playback.paused||playback.time<=52)throw Error('Preview playback failed');
 const transitions=await p.evaluate(()=>{
  const ts=[60.5,61.3,63.5,64.5,65.45,66,68,70,72,73,74,76];
  return {ascent:ts.map(time=>{const pose=transitionDebug.ascentPose(time),h=.001;
   const before=transitionDebug.ascentDistance(time-h),after=transitionDebug.ascentDistance(time+h);
   return {...pose,time,velocity:(after-before)/(2*h),velocityLeft:(pose.logHeight-before)/h,velocityRight:(after-pose.logHeight)/h};}),
   entry:[43,43.5,44,44.5,45,45.5,46].map(time=>({time,...transitionDebug.entry(time)})),
   space:Array.from({length:17},(_,i)=>{const time=81.5+i*.5;return {...transitionDebug.ascentPose(time),time};}),
   samples:Array.from({length:649},(_,i)=>({...pathPose(i/24),time:60+i/24})),cloudsEnd:transitionDebug.cloudsEnd};
 });
 for(const x of transitions.ascent){if(x.velocity<=0||Math.abs(x.velocityLeft-x.velocityRight)>.001)throw Error('Ascent camera stops or jumps: '+JSON.stringify(x));}
 for(const x of transitions.entry)if(x.streetScale<1||x.cityScale<1)throw Error('Entry exposes image edges');
 const approvedPixels=[];
 for(const originalFrame of [48,144,192,240,312,384,528,647]){
  const result=await p.evaluate(async originalFrame=>{
   await capture(1440+originalFrame,false,'image/png');
   const c=document.createElement('canvas');c.width=1920;c.height=1080;const cx=c.getContext('2d');cx.drawImage(document.getElementById('film'),0,0);const actual=cx.getImageData(0,0,1920,1080).data;
   const im=new Image();im.src='../city_earth_review_v2/qa/frame_'+originalFrame+'.png';await im.decode();cx.clearRect(0,0,1920,1080);cx.drawImage(im,0,0);const ref=cx.getImageData(0,0,1920,1080).data;
   let sum=0,max=0;for(let i=0;i<actual.length;i+=4)for(let j=0;j<3;j++){const d=Math.abs(actual[i+j]-ref[i+j]);sum+=d;max=Math.max(max,d);}return {originalFrame,meanRgbDifference:sum/(1920*1080*3),maximumDifference:max};
  },originalFrame);
  if(result.meanRgbDifference>.2)throw Error('Approved preview changed during integration: '+JSON.stringify(result));approvedPixels.push(result);
 }
 const clouds=transitions.samples.filter(x=>x.cloud>0);
 if(Math.max(...clouds.map(x=>x.altitudeKm))>18)throw Error('High-altitude foreground cloud');
 for(const time of [64.5,73]){const x=transitions.ascent.find(x=>x.time===time);if(x.velocity<.2)throw Error('Camera slows near zero at integration join');}
 const cloudExit=await p.evaluate(async()=>{
  const original=cloudBanks,calls=[];
  cloudBanks=function(t,amount,travel){if(amount>.003)calls.push({t,amount});return original(t,amount,travel);};
  try{for(let frame=59*24;frame<=Math.ceil(61.3*24);frame++)await capture(frame,false);}
  finally{cloudBanks=original;}
  return {range:[59,61.3],frames:Math.ceil(61.3*24)-59*24+1,textureCardDraws:calls.length};
 });
 if(cloudExit.textureCardDraws!==0)throw Error('Rectangular cloud cards at street exit');
 fs.writeFileSync(path.join(OUT,'qa_report.json'),JSON.stringify({revision:5,renderer:info,frames:times.length,deterministic:true,hashes,framing,transitions,approvedPixels,cloudExit,playback,errors},null,2));
 await b.close();if(errors.length)throw Error(errors.join('\n'));console.log('SHADER_QA_OK');
}
async function worker(port,start,end,id){
 const {b,p,info,errors}=await page(port);console.log('RENDERER',id,info.renderer);
 const enc=pipeProcess(['-v','warning','-threads','2','-f','image2pipe','-framerate','24','-vcodec','mjpeg','-i','pipe:0','-an','-c:v','libx264','-threads','2','-preset','fast','-crf','18','-pix_fmt','yuv420p','-bf','0','-r','24','-frames:v',String(end-start),'-g','48','-f','mp4','-movflags','frag_keyframe+empty_moov+default_base_moof','pipe:1'],path.join(OUT,`part_${id}.mp4`),path.join(OUT,`render_${id}.log`));
 const begin=Date.now();
 for(let f=start;f<end;f++){
  const data=await p.evaluate(({f,subs})=>window.capture(f,subs),{f,subs:WITH_SUBS});
  if(!enc.p.stdin.write(Buffer.from(data,'base64')))await new Promise(r=>enc.p.stdin.once('drain',r));
  if((f-start)%96===0)console.log(`RENDER ${id} ${f-start}/${end-start} elapsed ${Math.round((Date.now()-begin)/1000)}s`);
 }
 enc.p.stdin.end();await enc.done;await b.close();if(errors.length)throw Error(errors.join('\n'));
 return {start,end,seconds:(Date.now()-begin)/1000,renderer:info};
}
async function mux(){
 fs.writeFileSync(path.join(OUT,'concat.txt'),"file 'part_0.mp4'\nfile 'part_1.mp4'\n");
 const enc=pipeProcess(['-v','warning','-f','concat','-safe','0','-i',path.join(OUT,'concat.txt'),'-i',path.join(ROOT,'assets/audio/emergence_final90/mix.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-t','90','-f','mp4','-movflags','frag_keyframe+empty_moov+default_base_moof','pipe:1'],path.join(OUT,'涌现_90秒_无字幕.mp4'),path.join(OUT,'mux.log'));
 enc.p.stdin.end();await enc.done;
}
async function subtitle(){
 const input=path.join(OUT,'涌现_90秒_无字幕.mp4');
 const log=fs.openSync(path.join(OUT,'subtitles.log'),'w');
 const proc=spawn(FF,['-v','warning','-i',input,'-vf','ass=subtitles.ass','-map','0:v:0','-map','0:a:0','-c:v','libx264','-preset','fast','-crf','17','-threads','4','-pix_fmt','yuv420p','-bf','0','-r','24','-fps_mode','cfr','-frames:v','2160','-c:a','copy','-t','90','-f','mp4','-movflags','frag_keyframe+empty_moov+default_base_moof','pipe:1'],{cwd:OUT,stdio:['ignore','pipe',log],windowsHide:true});
 const output=fs.createWriteStream(path.join(OUT,'涌现_90秒_双语字幕.mp4'));proc.stdout.pipe(output);
 await Promise.all([new Promise((yes,no)=>{proc.on('error',no);proc.on('close',c=>c===0?yes():no(Error('Subtitle encode '+c)));}),new Promise((yes,no)=>{output.on('finish',yes);output.on('error',no);})]);fs.closeSync(log);console.log('FINAL90_SUBTITLED');
}

async function main(){
 if(process.argv.includes('--subtitle')){await subtitle();return;}
 const s=server();await new Promise(r=>s.listen(process.argv.includes('--serve')?8766:0,'127.0.0.1',r));const port=s.address().port;
 console.log(`PREVIEW http://127.0.0.1:${port}/assets/video/emergence_final90/index.html`);
 if(process.argv.includes('--serve'))return;
 try{if(process.argv.includes('--qa'))await qa(port);
 else{
   if(process.argv.includes('--mux-only')){await mux();console.log('SAMPLE_REMUXED');return;}
   const report=process.argv.includes('--tail-only')?[await worker(port,1080,2160,1)]:await Promise.all([worker(port,0,1080,0),worker(port,1080,2160,1)]);await mux();
   fs.writeFileSync(path.join(OUT,'render_report.json'),JSON.stringify({frames:2160,fps:24,duration:90,workers:report},null,2));console.log('FINAL90_RENDERED');
 }}finally{s.close();}
}
main().catch(e=>{console.error(e);process.exit(1);});
