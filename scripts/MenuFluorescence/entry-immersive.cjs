// Timing demo of the real EntryShot profile. The destination uses a labeled existing game capture.
const fs=require('fs'),path=require('path'),{spawnSync}=require('child_process');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'validation/menu-entry-immersive-20261016');fs.mkdirSync(out,{recursive:true});
const lua=fs.readFileSync(path.join(root,'scripts/UI/EntryShot.lua'),'utf8'),timing={};for(const k of ['hide','push','blackout','hold','reveal'])timing[k]=+lua.match(new RegExp(k+' = ([0-9.]+)'))[1];
let html=fs.readFileSync(path.join(root,'validation/menu-healthy-hd-20261015/preview.html'),'utf8');
html=html.replace('uniform int bgMode;', 'uniform int bgMode;uniform float shotTravel;');
html=html.replace('vec2 p=vec2(uv.x,1.-uv.y);','vec2 p=(vec2(uv.x,1.-uv.y)-.5)/(1.+.16*shotTravel)+.5;');
html=html.replace("use(P.bg,R.scene);", "use(P.bg,R.scene);gl.uniform1f(un(P.bg,'shotTravel'),window.shotTravel||0);");
html=html.replace('stats.count=count;gl.bindBuffer', `for(let i=0;i<count;i++){const depth=i<8?[1.35,.85,1.1,.28,.34,.25,.5,.45][i]:.3+(1+i%3)*.35;const k=1+(window.shotTravel||0)*depth;instances[i*8]=640+(instances[i*8]-640)*k;instances[i*8+1]=360+(instances[i*8+1]-360)*k;instances[i*8+2]*=k;}stats.count=count;gl.bindBuffer`);
const screenshot=fs.readFileSync(path.join(root,'validation/redesign-desktop-final.png'));
const overlay=`<style>#entryCover{position:absolute;inset:0;background:#000;opacity:0;z-index:5;pointer-events:none}#destination{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:3;display:none}#shotNote{color:#b5a592;text-align:center;font:12px 'Microsoft YaHei';margin:12px}.menu{transition:none}#gl{transform-origin:center;will-change:transform}#stage{background:#000}</style>`;
html=html.replace('</head>',overlay+'</head>');
html=html.replace('<div class="heads">',`<img id="destination" alt="已有游戏截图，仅示意转场后的画面" src="data:image/png;base64,${screenshot.toString('base64')}"><div id="entryCover"></div><div class="heads">`);
html=html.replace('</main>','<p id="shotNote">转场节奏预览 · 点击「开始」或 Enter · 游戏端为已有截图示意 · R 重播</p></main>');
const code=`<script>
const shotTiming=${JSON.stringify(timing)},menu=document.querySelector('.menu'),scene=document.getElementById('gl'),cover=document.getElementById('entryCover'),destination=document.getElementById('destination');
let shotStart=null,shotRunning=false;
const smooth=v=>{const t=Math.max(0,Math.min(1,v));return t*t*(3-2*t);};
window.setShot=t=>{const c=shotTiming,end=c.hide+c.push,p=Math.max(0,Math.min(1,t/end));
menu.style.opacity=1-smooth(t/c.hide);menu.style.pointerEvents=t>0?'none':'auto';window.shotTravel=1.8*p*p*p;scene.style.transform='none';
destination.style.display=t>=end?'block':'none';let black=0;if(t<end)black=smooth((t-end+c.blackout)/c.blackout);else if(t<end+c.hold)black=1;else black=1-smooth((t-end-c.hold)/.18);const a=Math.max(0,Math.min(1,(t-end-c.hold)/.78));destination.style.transform='scale('+(1+.219512195*(1-Math.pow(1-a,3)))+')';cover.style.opacity=black;
lab.render((2+Math.max(0,t))%12);window.shotPose={t,menuOpacity:+menu.style.opacity,scale:1+1.8*p*p*p,black,gameVisible:t>=end};return window.shotPose;};
function begin(){if(shotRunning)return;shotRunning=true;shotStart=performance.now();}menu.querySelector('button').onclick=begin;
document.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();begin();}if(e.key.toLowerCase()==='r'){shotRunning=false;shotStart=null;setShot(0);}});
function shotFrame(now){if(shotStart!==null)setShot((now-shotStart)/1000);requestAnimationFrame(shotFrame);}
window.shotReady=ready.then(()=>{lab.state.playing=false;lab.state.benchmark=true;setShot(0);requestAnimationFrame(shotFrame);});
</script>`;
html=html.replace('</body>',code+'</body>');fs.writeFileSync(path.join(out,'preview.html'),html);
async function main(){const {chromium}=require('C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});try{const page=await browser.newPage({viewport:{width:1328,height:950},deviceScaleFactor:1}),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('file:///'+path.join(out,'preview.html').replaceAll('\\','/'));await page.evaluate(()=>shotReady);
const poses=await page.evaluate(()=>[0,.25,.6,1,1.1,1.2,1.38,1.98,2.2].map(t=>setShot(t)));
if(poses[1].menuOpacity!==0||poses[2].scale<=1||poses[4].black!==1||poses[8].black!==0)throw Error('Timing profile mismatch');
// Exercise actual start and repeated-start routing before deterministic frame export.
await page.evaluate(()=>setShot(0));await page.locator('.menu button').first().click();await page.waitForTimeout(300);const clicked=await page.evaluate(()=>window.shotPose);if(clicked.menuOpacity!==0||clicked.scale<=1)throw Error('Click did not start shot');await page.keyboard.press('r');await page.evaluate(()=>{shotStart=null;shotRunning=false;});
const frames=path.join(out,'frames');fs.mkdirSync(frames,{recursive:true});for(let i=0;i<96;i++){await page.evaluate(t=>setShot(t),Math.max(0,i/24-.65));await page.locator('#stage').screenshot({path:path.join(frames,String(i).padStart(3,'0')+'.png')});if(i%32===0)console.log('FRAME '+i+'/96');}
const ff='C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe';const args=['-v','error','-framerate','24','-i',path.join(frames,'%03d.png'),'-vf','fps=16,scale=960:-1,split[a][b];[a]palettegen=max_colors=192[p];[b][p]paletteuse=dither=bayer','-loop','0','-f','gif','pipe:1'];const encoded=spawnSync(ff,args,{windowsHide:true,maxBuffer:100*1024*1024});if(encoded.status)throw Error(encoded.stderr.toString());fs.writeFileSync(path.join(out,'entry-immersive.gif'),encoded.stdout);
const decoded=spawnSync(ff,['-v','error','-i','pipe:0','-f','null','pipe:1'],{windowsHide:true,input:encoded.stdout});if(decoded.status)throw Error(decoded.stderr.toString());
fs.writeFileSync(path.join(out,'preview-checks.json'),JSON.stringify({timing,poses,clicked,errors,gifDecoded:true,scope:'WebGL timing demonstration; destination is an existing game screenshot, not a new native capture.'},null,2));if(errors.length)throw Error(errors.join('\n'));console.log('IMMERSIVE_PREVIEW_OK');
}finally{await browser.close();}}main().catch(e=>{console.error(e);process.exitCode=1});
