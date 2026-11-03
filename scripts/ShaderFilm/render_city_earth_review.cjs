/* Isolated review only. Does not write production film or the game's video. */
const fs=require('fs'),path=require('path'),http=require('http'),crypto=require('crypto');
const {spawn}=require('child_process');
const ROOT=path.resolve(__dirname,'../..'),OUT=path.join(ROOT,'assets/video/city_earth_review_v1');
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
  await p.goto(`http://127.0.0.1:${server.address().port}/assets/video/city_earth_review_v1/index.html`);
  const info=await p.evaluate(()=>ready);console.log('RENDERER',info.renderer);
  const times=[0,3,5,7.4,8.8,9.5,10,10.35,10.5,10.65,11,11.3,11.65,12,13,15,19,23,26.9583333333],hashes={};
  for(const time of times){const frame=Math.round(time*24),data=await p.evaluate(f=>capture(f,'image/png'),frame);fs.writeFileSync(path.join(OUT,'qa',`frame_${frame}.png`),Buffer.from(data,'base64'));hashes[frame]=crypto.createHash('sha256').update(data).digest('hex');console.log('QA',time);}
  for(const time of [...times].reverse()){const frame=Math.round(time*24),hash=crypto.createHash('sha256').update(await p.evaluate(f=>capture(f,'image/png'),frame)).digest('hex');if(hash!==hashes[frame])throw Error('Nondeterministic frame '+frame);}
  const camera=await p.evaluate(()=>Array.from({length:649},(_,i)=>cameraAt(i/24)));
  for(let i=1;i<camera.length;i++)if(camera[i].distance!==null&&camera[i-1].distance!==null&&camera[i].distance+1e-10<camera[i-1].distance)throw Error('Camera reverses');
  if(camera.at(-1).angularRadius>=18*Math.PI/180)throw Error('Planet does not fit vertically');
  const approvedEarth=[];
  for(const originalFrame of [0,48,144,240,335]){
   const data=Buffer.from(await p.evaluate(f=>capture(f,'image/png'),312+originalFrame),'base64');
   const approved=path.join(ROOT,'assets/video/earth_transition_review_v1/qa',`frame_${originalFrame}.png`);
   const matches=crypto.createHash('sha256').update(data).digest('hex')===sha(approved);
   if(!matches)throw Error('Approved Earth pixels changed at '+originalFrame);
   approvedEarth.push({originalFrame,combinedFrame:312+originalFrame,png_identical:true});
  }
  const concealedJoin=await p.evaluate(()=>({before:fogAt(10.5-1/24),at:fogAt(10.5),after:fogAt(10.5+1/24),earthStart:fogAt(13)}));
  if(concealedJoin.before!==1||concealedJoin.at!==1||concealedJoin.after!==1||concealedJoin.earthStart!==0)throw Error('Unconcealed ground switch or cloud in approved Earth shot');
  fs.writeFileSync(path.join(OUT,'qa_report.json'),JSON.stringify({info,errors,camera,approvedEarth,concealedJoin,random_seek_identical:true,production_unchanged:true},null,2));
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
