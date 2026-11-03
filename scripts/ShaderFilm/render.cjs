/* Local server, shader QA and deterministic 1080p/24fps movie export. */
const fs=require('fs'),path=require('path'),http=require('http'),crypto=require('crypto');
const {spawn}=require('child_process');
const ROOT=path.resolve(__dirname,'../..'),OUT=path.join(ROOT,'assets/video/emergence_shader');
const NODE_DEPS=process.env.SHADER_NODE_DEPS||'C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const EDGE=process.env.SHADER_BROWSER||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const FF=process.env.SHADER_FFMPEG||'C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe';
const WITH_SUBS=!process.argv.includes('--no-subs');
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
 await p.goto(`http://127.0.0.1:${port}/assets/video/emergence_shader/index.html`);
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
 const times=[0,1.2,2.5,4.5,6,8.5,10,12,15,16.1,16.6,18,20,21.8,23,25,27,28.5,30,32,33.8,34.72,34.76,36,37.54,37.56,38.5,39.78,39.82,41,43,45,47.5];
 for(const t of times){let f=Math.round(t*24);const data=await p.evaluate(f=>window.capture(f,true,'image/png'),f);fs.writeFileSync(path.join(OUT,'qa',`frame_${f.toString().padStart(4,'0')}.png`),Buffer.from(data,'base64'));console.log('QA',t);}
 const hashes={};for(const f of [120,240,400,528,660,780,864,912,1000,1140]){hashes[f]=crypto.createHash('sha256').update(await p.evaluate(f=>capture(f,true,'image/png'),f)).digest('hex');}
 for(const f of [1140,240,864,120,1000,528,400,660,912,780]){const h=crypto.createHash('sha256').update(await p.evaluate(f=>capture(f,true,'image/png'),f)).digest('hex');if(h!==hashes[f])throw Error('Random seek changed frame '+f);}
 // Actual player controls and audio seeking are checked, not merely frame export.
 await p.locator('[data-time="27"]').click();await p.locator('#play').click();await p.waitForTimeout(1200);
 const playback=await p.evaluate(()=>({time:document.getElementById('audio').currentTime,paused:document.getElementById('audio').paused}));
 await p.locator('#play').click();if(playback.paused||playback.time<=27)throw Error('Preview playback failed');
 fs.writeFileSync(path.join(OUT,'qa_report.json'),JSON.stringify({renderer:info,frames:times.length,deterministic:true,hashes,playback,errors},null,2));
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
 const enc=pipeProcess(['-v','warning','-f','concat','-safe','0','-i',path.join(OUT,'concat.txt'),'-i',path.join(ROOT,'assets/audio/emergence_shader/mix.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-t','48','-f','mp4','-movflags','frag_keyframe+empty_moov+default_base_moof','pipe:1'],path.join(OUT,WITH_SUBS?'sample_bilingual.mp4':'sample_clean.mp4'),path.join(OUT,'mux.log'));
 enc.p.stdin.end();await enc.done;
}
async function main(){
 const s=server();await new Promise(r=>s.listen(process.argv.includes('--serve')?8766:0,'127.0.0.1',r));const port=s.address().port;
 console.log(`PREVIEW http://127.0.0.1:${port}/assets/video/emergence_shader/index.html`);
 if(process.argv.includes('--serve'))return;
 try{if(process.argv.includes('--qa'))await qa(port);
 else{
   if(process.argv.includes('--mux-only')){await mux();console.log('SAMPLE_REMUXED');return;}
   const report=await Promise.all([worker(port,0,576,0),worker(port,576,1152,1)]);await mux();
   fs.writeFileSync(path.join(OUT,'render_report.json'),JSON.stringify({frames:1152,fps:24,duration:48,workers:report},null,2));console.log('SAMPLE_RENDERED');
 }}finally{s.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
