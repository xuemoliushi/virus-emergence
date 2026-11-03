// Timing demo of the real EntryShot profile. The destination uses a labeled existing game capture.
const fs=require('fs'),path=require('path'),{spawnSync}=require('child_process');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'validation/menu-entry-audio-20261018');fs.mkdirSync(out,{recursive:true});
const lua=fs.readFileSync(path.join(root,'scripts/UI/EntryShot.lua'),'utf8'),timing={};for(const k of ['hide','push','blackout','hold','reveal'])timing[k]=+lua.match(new RegExp(k+' = ([0-9.]+)'))[1];
let html=fs.readFileSync(path.join(root,'validation/menu-healthy-hd-20261015/preview.html'),'utf8');
html=html.replace('uniform int bgMode;', 'uniform int bgMode;uniform float shotTravel;');
html=html.replace('vec2 p=vec2(uv.x,1.-uv.y);','vec2 p=(vec2(uv.x,1.-uv.y)-.5)/(1.+.16*shotTravel)+.5;');
html=html.replace("use(P.bg,R.scene);", "use(P.bg,R.scene);gl.uniform1f(un(P.bg,'shotTravel'),window.shotTravel||0);");
html=html.replace('stats.count=count;gl.bindBuffer', `for(let i=0;i<count;i++){const depth=i<8?[1.35,.85,1.1,.28,.34,.25,.5,.45][i]:.3+(1+i%3)*.35;const k=1+(window.shotTravel||0)*depth;instances[i*8]=640+(instances[i*8]-640)*k;instances[i*8+1]=360+(instances[i*8+1]-360)*k;instances[i*8+2]*=k;}stats.count=count;gl.bindBuffer`);
const screenshot=fs.readFileSync(path.join(root,'validation/flat-map-live/native/flow-image-final.png'));
const overlay=`<style>#entryCover{position:absolute;inset:0;background:#000;opacity:0;z-index:5;pointer-events:none}#destination{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:3;display:none}#shotNote{color:#b5a592;text-align:center;font:12px 'Microsoft YaHei';margin:12px}.menu{transition:none}#gl{transform-origin:center;will-change:transform}#stage{background:#000}</style>`;
html=html.replace('</head>',overlay+'</head>');
html=html.replace('<div class="heads">',`<img id="destination" alt="已有游戏截图，仅示意转场后的画面" src="data:image/png;base64,${screenshot.toString('base64')}"><div id="entryCover"></div><div class="heads">`);
html=html.replace('</main>','<p id="shotNote">转场节奏预览 · 点击「开始」或 Enter · 点击下方音效按钮同步试听 · 游戏端为已有截图示意，非实机录屏 · R 重播</p></main>');
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
const comparison=`<style>.auditions{display:flex;gap:12px;justify-content:center;padding:16px;color:#e4d5ce}.auditions button{cursor:pointer;padding:12px 20px;background:#251e29;color:#ffe4d5;border:1px solid #78606d;border-radius:8px}#shotNote{max-width:1100px;margin:auto}</style><div class="auditions"><button data-sound="01_pressure">01 低频空间压缩</button><button data-sound="02_membrane">02 液态穿膜</button><button data-sound="03_micrograins">03 微观颗粒</button></div>`;
html=html.replace('</main>',comparison+'</main>');
const soundCode='<script>let audition=null,auditionGeneration=0;document.querySelectorAll("[data-sound]").forEach(b=>b.onclick=()=>{const token=++auditionGeneration;if(audition)audition.pause();audition=new Audio("../../assets/audio/entry_candidates/"+b.dataset.sound+".wav");audition.volume=.8;audition.load();shotRunning=false;shotStart=null;setShot(0);const start=performance.now();let sounded=false;function play(now){if(token!==auditionGeneration)return;const t=(now-start)/1000;setShot(t);if(t>=.6&&!sounded){sounded=true;audition.play();}if(t<3.1)requestAnimationFrame(play);}requestAnimationFrame(play);});</script>';
html=html.replace('</body>',code+soundCode+'</body>');fs.writeFileSync(path.join(out,'preview.html'),html);

async function main(){const {chromium}=require('C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
try{const page=await browser.newPage({viewport:{width:1328,height:1120},deviceScaleFactor:1}),errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto('file:///'+path.join(out,'preview.html').replaceAll('\\','/'));await page.evaluate(()=>shotReady);
const frames=path.join(out,'frames');fs.mkdirSync(frames,{recursive:true});
for(let i=0;i<96;i++){await page.evaluate(t=>setShot(t),Math.max(0,i/24-.65));await page.locator('#stage').screenshot({path:path.join(frames,String(i).padStart(3,'0')+'.png')});if(i%32===0)console.log('FRAME '+i+'/96');}
await page.locator('[data-sound="02_membrane"]').click();await page.waitForTimeout(800);const audition=await page.evaluate(()=>({t:window.shotPose.t,playing:!audition.paused,readyState:audition.readyState}));
if(!audition.playing||audition.readyState<2)throw Error('Audio audition did not play');if(errors.length)throw Error(errors.join('\n'));
fs.writeFileSync(path.join(out,'preview-checks.json'),JSON.stringify({errors,audition,timing,scope:'Audio and A-motion comparison; game destination is an existing screenshot, not a native recording.'},null,2));
console.log('AUDIO_PREVIEW_FRAMES_OK');}finally{await browser.close();}}
main().catch(e=>{console.error(e);process.exitCode=1});
