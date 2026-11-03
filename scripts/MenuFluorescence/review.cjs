const fs=require('fs'),path=require('path'),http=require('http'),{spawnSync}=require('child_process');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'validation/menu-fluorescence-20261015');fs.mkdirSync(out,{recursive:true});
let html=fs.readFileSync(path.join(root,'validation/final-art-review-20261015/preview.html'),'utf8');
// Reuse the existing final review's atlases, material masks, HDR targets and bloom pipeline.
const start=html.indexOf('function layout(t)'),end=html.indexOf('function render(t,measure=false)',start);
if(start<0||end<0)throw Error('Review renderer boundaries missing');
html=html.slice(0,start)+`function layout(t){let count=0;
const add=(x,y,size,slot,kind,seed,alpha=1)=>{const a=t*Math.PI/6+seed;instances.set([x+Math.sin(a)*5,y+Math.cos(a)*9,size*(1+Math.sin(a)*.013)/.90625,0,slot,kind,seed,alpha],count++*8);};
add(95,105,430,8,3,.4,.73);add(1080,364,305,8,3,2,.90);add(185,610,205,8,3,4,.69);
add(1130,80,76,8,3,1,.24);add(1010,665,110,8,3,3,.22);add(350,370,63,8,3,5,.15);
add(1090,615,96,1,1,2,.32);add(275,480,65,2,2,4,.25);
for(let i=0;i<18;i++){const x=(i*197+71)%1280;if(x>450&&x<830)continue;add(x,(i*149+60)%720,3+i%3,0,0,i*.73,.32);}
stats.count=count;gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferSubData(gl.ARRAY_BUFFER,0,instances,0,count*8);}
`+html.slice(end);
// Use periodic waves to keep the twelve-second menu loop continuous.
html=html.replace('t*.012,-t*.009','sin(t*1.0471976)*.025,cos(t*1.0471976)*.025').replace('t*2.1','t*2.0943951');
html=html.replace("view:'gallery'","view:'scene'");
const skin='data:image/png;base64,'+fs.readFileSync(path.join(root,'assets/image/ui/scaled/ui_primary_button_normal.png')).toString('base64');
const css=`<style>body{background:#07070d}main{max-width:1328px}header,.tag,main>p,.cards,.foot,details,.heads,.scale,.line,.status,#metrics,#view,#mode,#variant,#background,#stress,#bench{display:none!important}#stage{border:0;border-radius:0;box-shadow:0 16px 70px #000}#stage:after{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at center,#030207ec 0%,#030207b8 22%,#03020720 55%,#0003 100%);pointer-events:none}main>.bar{justify-content:center}.menu{position:absolute;z-index:2;left:37.5%;width:25%;top:18%;text-align:center;color:#f1e0c1;font-family:'Microsoft YaHei',sans-serif}.menu h2{font-size:43px;font-weight:400;letter-spacing:7px;margin:0 0 7px;white-space:nowrap}.menu p{font-size:11px;color:#bda78b;letter-spacing:3px;margin:0 0 30px}.menu button{display:block;width:100%;height:53px;margin:10px 0;background: url('${skin}') center/100% 100%;border:0;border-radius:0;color:#d9c5a4;letter-spacing:3px;font-size:16px}.menu button:first-of-type{color:#ffe3a3;filter:brightness(1.2);box-shadow:0 0 24px #b66b1814}.menu button:disabled{opacity:.45}.menu small{font-size:10px;color:#857260}.menu button:hover{filter:brightness(1.35)}@media(max-width:800px){.menu h2{font-size:4vw}.menu p{font-size:1vw;margin-bottom:2vw}.menu button{height:4.2vw;margin:.6vw 0;font-size:1.5vw}.menu small{font-size:.8vw}}</style>`;
html=html.replace('</head>',css+'</head>').replace('<div class="heads">','<section class="menu"><h2>病毒涌现</h2><p>微观之下，生存涌现</p><button>开始</button><button disabled>无尽模式 · 暂未开放</button><button>设定</button><button>制作名单</button><button>退出</button><small>↑ ↓ 选择　 Enter 确认</small></section><div class="heads">');
fs.writeFileSync(path.join(out,'preview.html'),html);
async function main(){const {chromium}=require('C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
try{const page=await browser.newPage({viewport:{width:1328,height:900},deviceScaleFactor:1});let errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('file:///'+path.join(out,'preview.html').replaceAll('\\','/'));await page.evaluate(()=>ready);await page.evaluate(()=>{lab.state.playing=false;lab.state.view='scene';lab.render(2);});await page.locator('#stage').screenshot({path:path.join(out,'menu-still.png')});
const checks=await page.evaluate(()=>{const g=lab.gl;function read(t){lab.render(t);const a=new Uint8Array(1280*720*4);g.readPixels(0,0,1280,720,g.RGBA,g.UNSIGNED_BYTE,a);return a;}const a=read(2),b=read(5);let changed=0;for(let i=0;i<a.length;i+=4)if(Math.abs(a[i]-b[i])+Math.abs(a[i+1]-b[i+1])+Math.abs(a[i+2]-b[i+2])>5)changed++;return{changedPixels:changed,glError:g.getError(),instances:lab.summary().instances};});
const frames=path.join(out,'frames');fs.mkdirSync(frames,{recursive:true});for(let i=0;i<72;i++){if(fs.existsSync(path.join(frames,String(i).padStart(3,'0')+'.png')))continue;await page.evaluate(t=>lab.render(t),i/6);await page.locator('#stage').screenshot({path:path.join(frames,String(i).padStart(3,'0')+'.png')});if(i%24===0)console.log('FRAME '+i+'/72');}
const ff='C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe';const r=spawnSync(ff,['-y','-v','error','-framerate','6','-i',path.join(frames,'%03d.png'),'-vf','scale=960:-1,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer','-loop','0','-f','gif','pipe:1'],{windowsHide:true,maxBuffer:100*1024*1024});if(r.status)throw Error(r.stderr.toString());fs.writeFileSync(path.join(out,'menu-motion.gif'),r.stdout);
fs.writeFileSync(path.join(out,'qa.json'),JSON.stringify({errors,checks,reused:['FinalArtReview atlas slot 8: original red cell','FinalArtReview emission masks and material shader','FinalArtReview dark tissue background','existing primary button skin'],scope:'Independent menu visual prototype; runtime Lua unchanged; UrhoX validation pending'},null,2));if(errors.length||checks.glError||checks.changedPixels<100)throw Error('Preview validation failed');console.log('QA_OK '+JSON.stringify(checks));
}finally{await browser.close();}}
main().catch(e=>{console.error(e);process.exitCode=1});

