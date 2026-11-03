const fs=require('fs'),path=require('path'),http=require('http');
const {fork,spawn,execFileSync}=require('child_process');
const ROOT=path.resolve(__dirname,'../..'),OUT=path.join(ROOT,'assets/video/emergence_90s');
const FF='C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe';
const EDGE='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const {chromium}=require('C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const MIME={'.html':'text/html;charset=utf-8','.js':'application/javascript;charset=utf-8','.json':'application/json;charset=utf-8','.png':'image/png','.jpg':'image/jpeg','.wav':'audio/wav'};
function serve(){let s=http.createServer((req,res)=>{
 let p=path.resolve(ROOT,'.'+decodeURIComponent(req.url.split('?')[0]));
 if(!p.startsWith(ROOT+path.sep)){res.writeHead(403);res.end();return}
 fs.readFile(p,(e,d)=>{if(e){res.writeHead(404);res.end();return}res.setHeader('Content-Type',MIME[path.extname(p)]||'application/octet-stream');res.end(d)})});return s;}
async function browser(port){
 let b=await chromium.launch({executablePath:EDGE,headless:true,args:['--disable-gpu','--disable-background-timer-throttling']});
 let p=await b.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
 p.on('pageerror',e=>console.error('PAGE_ERROR',e.message));
 await p.goto(`http://127.0.0.1:${port}/assets/video/emergence_90s/index.html`);await p.evaluate(()=>window.ready);
 return {b,p};
}
async function worker(port,id){
 let {b,p}=await browser(port);let start=id*540,end=start+540;
 let file=path.join(OUT,`part_${id}.mp4`),log=fs.openSync(path.join(OUT,`worker_${id}.log`),'w');
 let encoder=spawn(FF,['-y','-v','warning','-threads','2','-f','image2pipe','-framerate','24','-vcodec','mjpeg','-i','pipe:0',
 '-an','-c:v','libx264','-threads','2','-preset','fast','-crf','18','-pix_fmt','yuv420p','-r','24','-frames:v','540','-f','mp4','-movflags','frag_keyframe+empty_moov','pipe:1'],{stdio:['pipe','pipe',log],windowsHide:true});
 let output=fs.createWriteStream(file);
 let written=new Promise((resolve,reject)=>{output.once('close',resolve);output.once('error',reject)});
 encoder.stdout.pipe(output);
 let done=new Promise((resolve,reject)=>{encoder.on('error',reject);encoder.on('exit',c=>c===0?resolve():reject(new Error('encoder exit '+c)))});
 for(let n=start;n<end;n++){
   let data=await p.evaluate(n=>{window.renderFrame(n,false);return document.getElementById('film').toDataURL('image/jpeg',.97).split(',')[1]},n);
   if(!encoder.stdin.write(Buffer.from(data,'base64')))await new Promise(r=>encoder.stdin.once('drain',r));
   if((n-start)%120===0)console.log(`W${id} frame ${n} / ${end-1}`);
 }
 encoder.stdin.end();await done;await written;await b.close();fs.closeSync(log);console.log(`W${id} DONE ${start}-${end-1}`);
}
async function main(){
 fs.copyFileSync(path.join(__dirname,'film.js'),path.join(OUT,'film.js'));
 fs.mkdirSync(path.join(OUT,'qa'),{recursive:true});let server=serve();await new Promise(r=>server.listen(0,'127.0.0.1',r));let port=server.address().port;
 if(process.argv.includes('--preview')){
   let {b,p}=await browser(port);let frames=[0,48,143,144,168,192,216,240,264,288,312,336,360,384,408,431,432,438,444,450,456,462,468,474,480,486,492,498,504,552,744,816,863,864,936,1079,1080,1224,1272,1416,1512,1692,1824,1920,1944,1992,2088,2159];
   for(let n of frames){let data=await p.evaluate(n=>{renderFrame(n,true);return cv.toDataURL('image/png').split(',')[1]},n);fs.writeFileSync(path.join(OUT,'qa',`frame_${n}.png`),Buffer.from(data,'base64'));}
   // Verify sequential / random access render identity around parallel boundaries.
   const hashes={};for(let n of [539,540,1079,1080,1619,1620]){hashes[n]=await p.evaluate(n=>{renderFrame(n,false);return cv.toDataURL('image/png')},n)}
   for(let n of [1620,539,1080,540,1619,1079]){let data=await p.evaluate(n=>{renderFrame(n,false);return cv.toDataURL('image/png')},n);if(data!==hashes[n])throw Error('seek nondeterminism '+n)}
   fs.writeFileSync(path.join(OUT,'seek_check.json'),JSON.stringify({frames:Object.keys(hashes),deterministic:true}));
   await b.close();server.close();console.log('PREVIEW_OK');return;
 }
 const children=[];
 for(let id=0;id<4;id++){
   let c=fork(__filename,['--worker',String(port),String(id)],{stdio:['ignore','inherit','inherit','ipc'],windowsHide:true});
   // Windows equivalent of four cpuset groups. Applied before browser/encoder creation.
   let mask=255*Math.pow(2,id*8);
   if(process.platform==='win32')execFileSync('powershell.exe',['-NoProfile','-Command',`$p=Get-Process -Id ${c.pid}; $p.ProcessorAffinity=[IntPtr]${mask}; Write-Output ('WORKER=${id} PID=${c.pid} AFFINITY='+$p.ProcessorAffinity)`],{stdio:'inherit',windowsHide:true});
   else console.log('Linux: use taskset/cpuset to launch each worker, see README');
   const promise=new Promise((resolve,reject)=>{c.once('exit',code=>code===0?resolve():reject(new Error('worker '+id+' exit '+code)))});children.push(promise);c.send({go:true});
 }
 try{await Promise.all(children);fs.writeFileSync(path.join(OUT,'render_report.json'),JSON.stringify({frames:2160,fps:24,workers:4,platform:process.platform,affinity_masks:[255,65280,16711680,4278190080],mode:'shared snapshots; independent global-frame render; four simultaneous ffmpeg encoders'},null,2));console.log('ALL_RENDERED')}finally{server.close()}
}
if(process.argv[2]==='--worker'){process.once('message',()=>worker(+process.argv[3],+process.argv[4]).then(()=>process.exit(0)).catch(e=>{console.error(e);process.exit(1)}));}
else main().catch(e=>{console.error(e);process.exit(1)});
