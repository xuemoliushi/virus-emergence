/* Isolated review only. Does not write production film or the game's video. */
const fs=require('fs'),path=require('path'),http=require('http'),crypto=require('crypto');
const {spawn}=require('child_process');
const ROOT=path.resolve(__dirname,'../..'),OUT=path.join(ROOT,'assets/video/city_earth_review_v2');
const DEPS=process.env.SHADER_NODE_DEPS||'C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const EDGE=process.env.SHADER_BROWSER||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const FF=process.env.SHADER_FFMPEG||'C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe';
const sha=f=>crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
function unchanged(){const baseline=JSON.parse(fs.readFileSync(path.join(OUT,'production_baseline.json'),'utf8'));for(const [file,hash]of Object.entries(baseline))if(sha(path.resolve(ROOT,file))!==hash)throw Error('Production changed: '+file);}
async function main(){
 unchanged();
 const server=http.createServer((req,res)=>{
  const file=path.resolve(ROOT,'.'+decodeURIComponent(req.url.split('?')[0]));
  if(!file.startsWith(ROOT+path.sep)){res.writeHead(403).end();return;}
  fs.stat(file,(err,stat)=>{if(err||!stat.isFile()){res.writeHead(404).end();return;}
   const ext=path.extname(file);res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.jpg':'image/jpeg','.frag':'text/plain'})[ext]||'application/octet-stream');fs.createReadStream(file).pipe(res);});
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const {chromium}=require(path.join(DEPS,'playwright'));
 const browser=await chromium.launch({executablePath:EDGE,headless:true,args:['--enable-unsafe-swiftshader','--disable-background-timer-throttling','--disable-renderer-backgrounding']});
 try{
  const p=await browser.newPage({viewport:{width:1280,height:850}}),errors=[];
  p.on('pageerror',e=>errors.push(e.message));
  await p.goto(`http://127.0.0.1:${server.address().port}/assets/video/city_earth_review_v2/index.html`);
  const info=await p.evaluate(()=>ready);console.log('RENDERER',info.renderer);
  const times=[0,2,3.5,4.2,4.5,4.7,5,5.45,6,7,8,9,10,11,12,13,14,16,18,22,26.9583333333],hashes={};
  for(const time of times){const frame=Math.round(time*24),data=await p.evaluate(f=>capture(f,'image/png'),frame);fs.writeFileSync(path.join(OUT,'qa',`frame_${frame}.png`),Buffer.from(data,'base64'));hashes[frame]=crypto.createHash('sha256').update(data).digest('hex');console.log('QA',time);}
  for(const time of [...times].reverse()){const frame=Math.round(time*24),hash=crypto.createHash('sha256').update(await p.evaluate(f=>capture(f,'image/png'),frame)).digest('hex');if(hash!==hashes[frame])throw Error('Nondeterministic frame '+frame);}
  const camera=await p.evaluate(()=>Array.from({length:649},(_,i)=>cameraAt(i/24)));
  for(let i=1;i<camera.length;i++)if(camera[i].distance!==null&&camera[i-1].distance!==null&&camera[i].distance+1e-10<camera[i-1].distance)throw Error('Camera reverses');
  if(camera.at(-1).angularRadius>=18*Math.PI/180)throw Error('Planet does not fit vertically');
  const continuity=await p.evaluate(()=>{const h=.0001;return [4.5,13].map(time=>({time,velocityLeft:(pathLogAltitude(time)-pathLogAltitude(time-h))/h,velocityRight:(pathLogAltitude(time+h)-pathLogAltitude(time))/h}));});
  for(const x of continuity)if(Math.min(x.velocityLeft,x.velocityRight)<.2||Math.abs(x.velocityLeft-x.velocityRight)>.001)throw Error('Ascent stops or jumps at '+JSON.stringify(x));
  const crossing=camera.filter(x=>x.cloud>0),maximumCloudAltitude=Math.max(...crossing.map(x=>x.altitudeKm));
  if(maximumCloudAltitude>18||camera.some(x=>x.altitudeKm>=18&&x.cloud>0))throw Error('High-altitude foreground cloud');
  const active=camera.filter(x=>x.time>=4.5&&x.time<=16);if(active.some(x=>x.logVelocity<.2))throw Error('Ascent velocity drops near zero');
  const styleChecks=[];
  for(const originalFrame of [144,240,335]){
   const phase=originalFrame/24,combinedTime=13+(phase-3)/(11/14);
   const data=Buffer.from(await p.evaluate(f=>capture(f,'image/png'),combinedTime*24),'base64');
   const file=`style_original_${originalFrame}.png`;fs.writeFileSync(path.join(OUT,'qa',file),data);
   styleChecks.push({originalFrame,combinedTime,file});
  }
  fs.writeFileSync(path.join(OUT,'qa_report.json'),JSON.stringify({info,errors,camera,continuity,maximumCloudAltitude,cloudCutoff:5.45,styleChecks,random_seek_identical:true,production_unchanged:true},null,2));
  if(errors.length)throw Error(errors.join('\n'));
  if(process.argv.includes('--qa'))return;
  const log=fs.openSync(path.join(OUT,'encode.log'),'w'),dest=fs.createWriteStream(path.join(OUT,'review_fragmented.mp4'));
  const proc=spawn(FF,['-v','warning','-f','image2pipe','-framerate','24','-vcodec','mjpeg','-i','pipe:0','-ss','60','-i',path.join(ROOT,'assets/audio/emergence_final90/mix.wav'),'-map','0:v:0','-map','1:a:0','-t','27','-frames:v','648','-c:v','libx264','-preset','slow','-crf','16','-pix_fmt','yuv420p','-bf','0','-threads','4','-c:a','aac','-b:a','192k','-f','mp4','-movflags','frag_keyframe+empty_moov+default_base_moof','pipe:1'],{stdio:['pipe','pipe',log],windowsHide:true});
  const done=Promise.all([new Promise((r,j)=>{proc.on('error',j);proc.on('close',c=>c===0?r():j(Error('FFmpeg '+c)));}),new Promise((r,j)=>{dest.on('finish',r);dest.on('error',j);})]);proc.stdout.pipe(dest);
  const begin=Date.now();
  for(let frame=0;frame<648;frame++){
   const data=await p.evaluate(f=>capture(f),frame);if(!proc.stdin.write(Buffer.from(data,'base64')))await new Promise(r=>proc.stdin.once('drain',r));
   if(frame%48===0)console.log('FRAME',frame,'/648',Math.round((Date.now()-begin)/1000)+'s');
  }
  proc.stdin.end();await done;fs.closeSync(log);unchanged();console.log('ISOLATED_CITY_EARTH_RENDERED');
 }finally{await browser.close();server.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
