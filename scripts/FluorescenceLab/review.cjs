/* Pack a double-clickable preview, QA real WebGL output and encode a 12s sample. */
const fs=require('fs'),path=require('path'),http=require('http'),crypto=require('crypto');
const {spawn}=require('child_process');
const ROOT=path.resolve(__dirname,'../..'),OUT=path.join(ROOT,'validation/fluorescence-lab-20261015');
const DEPS='C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const EDGE='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const FF='C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe';
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
fs.mkdirSync(OUT,{recursive:true});
const textures=Object.fromEntries(['base','maps','field','noise','background'].map(n=>{const ext=n==='background'?'jpg':'png';return [n,`data:image/${ext==='jpg'?'jpeg':ext};base64,`+fs.readFileSync(path.join(OUT,'textures',n+'.'+ext)).toString('base64')];}));
const js=fs.readFileSync(path.join(__dirname,'lab.js'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'index.html'),'utf8').replace('<script src="lab.js"></script>',`<script>window.LAB_TEXTURES=${JSON.stringify(textures)};</script><script>${js}</script>`);
fs.writeFileSync(path.join(OUT,'preview.html'),html);
function serve(){return http.createServer((req,res)=>{res.setHeader('Content-Type','text/html;charset=utf-8');res.end(html);});}
async function main(){const s=serve();await new Promise(r=>s.listen(process.argv.includes('--serve')?8771:0,'127.0.0.1',r));const port=s.address().port;console.log('URL http://127.0.0.1:'+port);
if(process.argv.includes('--serve'))return;
const {chromium}=require(path.join(DEPS,'playwright'));
const browser=await chromium.launch({executablePath:EDGE,headless:true,args:['--enable-unsafe-swiftshader','--disable-background-timer-throttling','--disable-renderer-backgrounding']});
try{const page=await browser.newPage({viewport:{width:1440,height:1080},deviceScaleFactor:1});const errors=[];
page.on('pageerror',e=>errors.push(e.message));await page.goto('http://127.0.0.1:'+port);const info=await page.evaluate(()=>ready);console.log('RENDERER '+JSON.stringify(info));
await page.evaluate(()=>lab.state.playing=false);
if(process.argv.includes('--bench')){const report=await page.evaluate(()=>lab.benchmark());fs.writeFileSync(path.join(OUT,'browser-benchmark.json'),JSON.stringify({info,...report},null,2));console.log('BENCH_DONE '+report.results.length+' scenarios');}
for(const t of [1.5,5.8,9.7]){const data=await page.evaluate(t=>capture(t),t);fs.writeFileSync(path.join(OUT,`frame-${t}.png`),Buffer.from(data,'base64'));}
await page.evaluate(()=>{lab.state.time=5.8;lab.render(5.8);});await page.screenshot({path:path.join(OUT,'preview-screen.png'),fullPage:true});
// Meaningful render assertions: exact duplicated scene without bloom, non-zero
// local bloom contribution, route differences, animated output, GL errors.
const checks=await page.evaluate(()=>{const g=lab.getGL(),s=lab.state;s.strength=0;lab.render(5.8,{ui:false});let a=new Uint8Array(1280*720*4);g.readPixels(0,0,1280,720,g.RGBA,g.UNSIGNED_BYTE,a);let mismatch=0,routeDiff=0;for(let y=0;y<720;y++)for(let x=0;x<640;x++)for(let c=0;c<3;c++){const i=(y*1280+x)*4+c;if(a[i]!==a[i+640*4])mismatch++;if(y<360)routeDiff+=Math.abs(a[i]-a[i+360*1280*4]);}
s.strength=.28;lab.render(5.8,{ui:false});let b=new Uint8Array(a.length);g.readPixels(0,0,1280,720,g.RGBA,g.UNSIGNED_BYTE,b);let changed=0,leftChanged=0,white=0;for(let y=0;y<720;y++)for(let x=0;x<1280;x++){const i=(y*1280+x)*4;let d=Math.abs(a[i]-b[i])+Math.abs(a[i+1]-b[i+1])+Math.abs(a[i+2]-b[i+2]);if(d>0){changed++;if(x<640)leftChanged++;}if(b[i]>245&&b[i+1]>245&&b[i+2]>245)white++;}
lab.render(1.5,{ui:false});let c=new Uint8Array(a.length);g.readPixels(0,0,1280,720,g.RGBA,g.UNSIGNED_BYTE,c);let animated=0;for(let i=0;i<c.length;i+=4)if(Math.abs(b[i]-c[i])+Math.abs(b[i+1]-c[i+1])+Math.abs(b[i+2]-c[i+2])>5)animated++;
return {zeroBloomPairMismatch:mismatch,routeDifferenceSum:routeDiff,weakBloomChangedPixels:changed,noBloomColumnChangedPixels:leftChanged,nearWhitePixels:white,animatedPixels:animated,glError:g.getError()};});
if(checks.zeroBloomPairMismatch!==0||checks.routeDifferenceSum<1000||checks.weakBloomChangedPixels<100||checks.noBloomColumnChangedPixels!==0||checks.animatedPixels<100||checks.glError)throw Error('Render QA failed '+JSON.stringify(checks));
// User controls are exercised against actual browser interaction.
await page.selectOption('#size','game');await page.selectOption('#count','16');await page.locator('[data-t="9.7"]').click();const control=await page.evaluate(()=>({size:lab.state.size,count:lab.state.count,time:lab.state.time,playing:lab.state.playing}));
if(control.size!=='game'||control.count!==16||control.time!==9.7||control.playing)throw Error('Controls failed');
await page.selectOption('#count','1');await page.selectOption('#size','large');
if(process.argv.includes('--render')){const log=fs.openSync(path.join(OUT,'encode.log'),'w');const enc=spawn(FF,['-v','warning','-f','image2pipe','-framerate','24','-vcodec','mjpeg','-i','pipe:0','-an','-c:v','libx264','-threads','2','-preset','fast','-crf','19','-pix_fmt','yuv420p','-f','mp4','-movflags','frag_keyframe+empty_moov+default_base_moof','pipe:1'],{stdio:['pipe','pipe',log],windowsHide:true});const file=fs.createWriteStream(path.join(OUT,'comparison.mp4'));enc.stdout.pipe(file);let pipeError;enc.stdin.on('error',e=>pipeError=e);const done=Promise.all([new Promise((yes,no)=>{enc.on('error',no);enc.on('exit',c=>c===0?yes():no(Error('ffmpeg '+c)));}),new Promise((yes,no)=>{file.on('finish',yes);file.on('error',no);})]);done.catch(()=>{});for(let f=0;f<288;f++){if(pipeError)throw pipeError;const data=await page.evaluate(t=>capture(t,'image/jpeg'),f/24);if(!enc.stdin.write(Buffer.from(data,'base64')))await Promise.race([new Promise(r=>enc.stdin.once('drain',r)),done]);if(f%72===0)console.log('FRAME '+f+'/288');}enc.stdin.end();await done;fs.closeSync(log);}
const manifest=JSON.parse(fs.readFileSync(path.join(OUT,'source-manifest.json'),'utf8'));const unchanged=Object.entries(manifest.runtime_sha256).every(([p,h])=>hash(path.join(ROOT,p))===h)&&Object.entries(manifest.sources_sha256).every(([p,h])=>hash(path.join(ROOT,'assets/image',p))===h);if(!unchanged)throw Error('Protected project files changed');
fs.writeFileSync(path.join(OUT,'qa.json'),JSON.stringify({info,checks,control,errors,protectedGameFilesUnchanged:unchanged,enginePerformance:'UNDETERMINED: browser rendering is not UrhoX execution'},null,2));if(errors.length)throw Error(errors.join('\n'));console.log('QA_OK '+JSON.stringify(checks));
}finally{await browser.close();s.close();}}
main().catch(e=>{console.error(e);process.exitCode=1;});
