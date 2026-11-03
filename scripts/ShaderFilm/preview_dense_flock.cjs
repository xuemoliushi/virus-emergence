/* Render and check the revised flock through the actual film Shader pipeline. */
const fs=require('fs'),path=require('path'),http=require('http'),crypto=require('crypto');
const {spawn}=require('child_process');
const ROOT=path.resolve(__dirname,'../..');
const HERO_FOCUS=process.argv.includes('--hero-focus');
const OPENING=process.argv.includes('--opening'),BEFORE=OPENING&&process.argv.includes('--before');
const OPENING_OUT=path.join(ROOT,'assets/video/素材/单鸟_v4_自然振翅');
const OUT=OPENING?path.join(OPENING_OUT,BEFORE?'修改前对照':''):path.join(ROOT,HERO_FOCUS?'assets/video/素材/鸟群_v3_主角失速与跟随':'assets/video/素材/鸟群_v2_流动群体');
const DEPS=process.env.SHADER_NODE_DEPS||'C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const EDGE=process.env.SHADER_BROWSER||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const FF=process.env.SHADER_FFMPEG||'C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe';
const {chromium}=require(path.join(DEPS,'playwright'));
const START=OPENING?0:8.5,SECONDS=OPENING?9:12,FPS=24,STEM=OPENING?'开头单鸟_自然振翅_9秒':HERO_FOCUS?'鸟群_主角失速与延迟跟随_12秒':'鸟群_流动与坠落_12秒';
const mime={'.js':'application/javascript','.html':'text/html','.json':'application/json','.png':'image/png','.jpg':'image/jpeg','.wav':'audio/wav'};
function server(){return http.createServer((req,res)=>{
 let file;try{file=path.resolve(ROOT,'.'+decodeURIComponent(req.url.split('?')[0]));}catch{res.writeHead(400);return res.end();}
 if(!file.startsWith(ROOT+path.sep)){res.writeHead(403);return res.end();}
 fs.stat(file,(e,st)=>{if(e||!st.isFile()){res.writeHead(404);return res.end();}
 res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream','Content-Length':st.size});fs.createReadStream(file).pipe(res);});
});}
function encoder(file){
 const error=fs.openSync(path.join(OUT,'ffmpeg.log'),'w');
 const p=spawn(FF,['-v','warning','-threads','2','-f','image2pipe','-framerate',String(FPS),'-vcodec','mjpeg','-i','pipe:0','-an','-c:v','libx264','-threads','2','-preset','fast','-crf','17','-pix_fmt','yuv420p','-r',String(FPS),'-frames:v',String(SECONDS*FPS),'-f','mp4','-movflags','frag_keyframe+empty_moov+default_base_moof','pipe:1'],{stdio:['pipe','pipe',error],windowsHide:true});
 const output=fs.createWriteStream(file);p.stdout.pipe(output);
 const done=Promise.all([new Promise((ok,no)=>{p.on('error',no);p.on('close',c=>c===0?ok():no(Error('FFmpeg exit '+c)));}),new Promise((ok,no)=>{output.on('finish',ok);output.on('error',no);})]).finally(()=>fs.closeSync(error));
 return {p,done};
}
async function main(){
 fs.mkdirSync(OUT,{recursive:true});const s=server();await new Promise(r=>s.listen(0,'127.0.0.1',r));
 let browser,activeEncoder;
 try{
  browser=await chromium.launch({executablePath:EDGE,headless:true,args:['--enable-unsafe-swiftshader','--disable-background-timer-throttling','--disable-renderer-backgrounding','--autoplay-policy=no-user-gesture-required']});
  const p=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];
  if(BEFORE)for(const file of ['engine.js','shaders/sprite.vert','shaders/sprite.frag']){
   await p.route('**/assets/video/emergence_shader/'+file,route=>route.fulfill({path:path.join(OPENING_OUT,'修改前源码',path.basename(file)),contentType:file.endsWith('.js')?'application/javascript':'text/plain'}));
  }
  p.on('pageerror',e=>errors.push(e.message));p.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await p.goto(`http://127.0.0.1:${s.address().port}/assets/video/emergence_shader/index.html`);
  const info=await p.evaluate(()=>window.ready);console.log('READY',JSON.stringify(info));
  const times=OPENING?[0,1.5,2.5,3.5,4,4.05,4.10,4.15,4.20,4.25,4.30,4.35,4.8,5.3,6.8,8.3]:HERO_FOCUS?[8.5,12,13,14.4,14.8,15.5,16,16.5,17,17.5,18.5,20]:[5.3,6.7,7.5,8.3,8.5,10,12,14,15.5,17,18.5,20];
  const hashes={};
  for(const t of times){
   const frame=Math.round(t*FPS),data=await p.evaluate(f=>window.capture(f,false,'image/png'),frame);
   fs.writeFileSync(path.join(OUT,`画面_${t.toFixed(OPENING?2:1)}秒.png`),Buffer.from(data,'base64'));
   hashes[frame]=crypto.createHash('sha256').update(data).digest('hex');
  }
  for(const t of [...times].reverse()){
   const frame=Math.round(t*FPS),data=await p.evaluate(f=>window.capture(f,false,'image/png'),frame);
   if(crypto.createHash('sha256').update(data).digest('hex')!==hashes[frame])throw Error('Non-deterministic seek '+t);
  }
  const states=await p.evaluate(()=>[8.5,12,14.4,15,15.5,16,16.5,17,17.5,18.5,20].map(t=>({t,...window.flockDebug.stateAt(t)})));
  const cameraCheck=HERO_FOCUS?await p.evaluate(()=>{
   const rows=[];for(let i=0;i<=7000;i++){const t=14+i/1000,v=window.flockDebug.stateAt(t).view;rows.push({t,pan:v.fallcam,hero:v.hero,zoom:v.shotZoom,focus:v.focus,drop:v.drop});}
   const onset=rows.find(r=>r.pan>.01),held=rows.filter(r=>r.t>=15&&r.t<=16.5),all=rows.every(r=>r.hero[0]>0&&r.hero[0]<1920&&r.hero[1]>0&&r.hero[1]<1080);
   const result={follow_start:onset.t,hero_drop_before_follow:onset.drop,max_pan_before_16_5:Math.max(...held.map(r=>r.pan)),hero_stays_in_frame:all,
    maximum_pan_step_near_onset:Math.max(...rows.filter(r=>Math.abs(r.t-onset.t)<.1).map((r,i,a)=>i?Math.abs(r.pan-a[i-1].pan):0))};
   if(result.hero_drop_before_follow<115||result.max_pan_before_16_5!==0||!all)throw Error('Hero framing checks failed');return result;
  }):null;
  const flightCheck=OPENING&&!BEFORE?await p.evaluate(()=>{
   const phase=.5228858689761823,freq=2.5520763271073856,T=1/freq,keys=['shoulder','elbow','wrist','recovery','bob','pitch','tail','head'];
   let periodic=0,derivativeSeam=0,maxSpeed=0;const eps=1e-5;
   for(let i=0;i<=360;i++){
    const t=i*T/360,a=OpeningFlight.sample(t,phase,freq),b=OpeningFlight.sample(t+T,phase,freq);
    for(const k of keys)periodic=Math.max(periodic,Math.abs(a[k]-b[k]));
   }
   for(let cycle=0;cycle<20;cycle++){
    const t=(cycle*2*Math.PI-phase)/(freq*2*Math.PI),a=OpeningFlight.sample(t-eps,phase,freq),b=OpeningFlight.sample(t,phase,freq),c=OpeningFlight.sample(t+eps,phase,freq);
    for(const k of keys)derivativeSeam=Math.max(derivativeSeam,Math.abs((c[k]-b[k])/eps-(b[k]-a[k])/eps));
   }
   for(let i=0;i<4000;i++){
    const t=i*T/4000,a=OpeningFlight.sample(t,phase,freq),b=OpeningFlight.sample(t+eps,phase,freq);
    for(const k of ['shoulder','elbow','wrist'])maxSpeed=Math.max(maxSpeed,Math.abs(b[k]-a[k])/eps);
   }
   if(periodic>1e-10||derivativeSeam>.02||!Number.isFinite(maxSpeed))throw Error('Opening flight cycle continuity failed');
   return {period_seconds:T,periodicity_error:periodic,wrap_derivative_error:derivativeSeam,max_joint_speed_rad_s:maxSpeed,independent_tip_jitter:false};
  }):null;
  let renderSeconds=0;
  if(!process.argv.includes('--stills')){
   const enc=encoder(path.join(OUT,STEM+'.mp4')),begin=Date.now();activeEncoder=enc;
   for(let i=0;i<SECONDS*FPS;i++){
    const data=await p.evaluate(f=>window.capture(f,false,'image/jpeg'),Math.round(START*FPS)+i);
    if(!enc.p.stdin.write(Buffer.from(data,'base64')))await new Promise(r=>enc.p.stdin.once('drain',r));
    if(i%48===0)console.log(`RENDER ${i}/${SECONDS*FPS} ${Math.round((Date.now()-begin)/1000)}s`);
   }
   enc.p.stdin.end();await enc.done;activeEncoder=null;renderSeconds=(Date.now()-begin)/1000;
  }
  const report={info,start:START,seconds:SECONDS,fps:FPS,count:await p.evaluate(()=>flockDebug.count),
   deterministic_seeking:true,hashes,hero_states:states,camera_check:cameraCheck,flight_check:flightCheck,shutter_samples:OPENING&&!BEFORE?info.openingShutter.samples:1,comparison_before:BEFORE,render_seconds:renderSeconds,errors};
  fs.writeFileSync(path.join(OUT,process.argv.includes('--stills')?'Shader静帧检查.json':'Shader渲染检查.json'),JSON.stringify(report,null,2));
  if(errors.length)throw Error(errors.join('\n'));console.log('FLOCK_SHADER_OK');
 }finally{if(activeEncoder){activeEncoder.p.stdin.end();await activeEncoder.done.catch(()=>{});}if(browser)await browser.close();s.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
