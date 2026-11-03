const fs=require('fs'),path=require('path');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'validation/menu-fluorescence-audit-20261015');fs.mkdirSync(out,{recursive:true});
const source=fs.readFileSync(path.join(root,'validation/menu-fluorescence-20261015/preview.html'),'utf8');
// Instrument the isolated approval draft; never patch the game or the other art review.
const probe=source.replace('window.lab={state,render,summary,benchmark,gl};','window.lab={state,render,summary,benchmark,gl,P,R,T,use,bind,tri};');
const target=path.join(out,'diagnostic.html');fs.writeFileSync(target,probe);
async function main(){const {chromium}=require('C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');const b=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
try{const p=await b.newPage({viewport:{width:1328,height:900}});const errors=[];p.on('pageerror',e=>errors.push(e.message));await p.goto('file:///'+target.replaceAll('\\','/'));await p.evaluate(()=>ready);await p.evaluate(()=>{lab.state.playing=false;lab.state.benchmark=true;});
const result=await p.evaluate(async()=>{const {gl:g,R,P,use,bind,tri}=lab,W=1280,H=720;
function raw(){const a=new Uint8Array(W*H*4);g.readPixels(0,0,W,H,g.RGBA,g.UNSIGNED_BYTE,a);return a;}
function render(bloom){lab.state.mode='new';lab.state.bloom=bloom;lab.render(2);return raw();}
const off=render(false),on=render(true);const delta=new Uint8Array(on.length);let changed=0,total=0,max=0,hot=0;
for(let i=0;i<on.length;i+=4){let d=0;for(let k=0;k<3;k++){const v=Math.abs(on[i+k]-off[i+k]);delta[i+k]=Math.min(255,v*8);d+=v;max=Math.max(max,v);total+=v;}delta[i+3]=255;if(d>3)changed++;if(on[i]>245&&on[i+1]>245&&on[i+2]>245)hot++;}
function displayTexture(tex){use(P.out,null);bind(P.out,'scene',tex,0);bind(P.out,'glow',tex,1);g.uniform1f(g.getUniformLocation(P.out.p,'gain'),0);tri();return raw();}
const emission=displayTexture(R.scene.ts[1]),blur=displayTexture(R.y.ts[0]);
function toCanvas(a){const c=document.createElement('canvas');c.width=W;c.height=H;const x=c.getContext('2d'),d=x.createImageData(W,H);for(let y=0;y<H;y++)d.data.set(a.subarray((H-1-y)*W*4,(H-y)*W*4),y*W*4);x.putImageData(d,0,0);return c;}
const sections=[['材质本身 · 关闭 Bloom',off],['原版合成 · 开启 Bloom',on],['发光遮罩经过材质计算后的输出',emission],['Bloom 单独贡献 · 显示差值放大 8 倍',delta]];
const board=document.createElement('canvas');board.width=1600;board.height=1000;const x=board.getContext('2d');x.fillStyle='#07090f';x.fillRect(0,0,1600,1000);
for(let i=0;i<4;i++){const ox=i%2*800,oy=Math.floor(i/2)*500;x.fillStyle='#e9d9c0';x.font='21px Microsoft YaHei';x.fillText(sections[i][0],ox+18,oy+31);x.drawImage(toCanvas(sections[i][1]),ox,oy+48,800,450);}
// Same cell close-up, with no menu dimming overlay, to distinguish atlas softness from bloom.
const detail=document.createElement('canvas');detail.width=1440;detail.height=570;const z=detail.getContext('2d');z.fillStyle='#080910';z.fillRect(0,0,1440,570);const crops=[['Bloom 关闭',off],['Bloom 开启',on],['发光缓冲',emission]];
for(let i=0;i<3;i++){z.fillStyle='#dfcfb8';z.font='22px Microsoft YaHei';z.fillText(crops[i][0],i*480+20,34);z.drawImage(toCanvas(crops[i][1]),900,190,360,360,i*480,70,480,480);}
let formats={};for(const [name,r]of Object.entries(R)){g.bindFramebuffer(g.FRAMEBUFFER,r.fb);formats[name]=r.ts.map((_,i)=>g.getFramebufferAttachmentParameter(g.FRAMEBUFFER,g.COLOR_ATTACHMENT0+i,g.FRAMEBUFFER_ATTACHMENT_COMPONENT_TYPE));}
return{board:board.toDataURL().split(',')[1],detail:detail.toDataURL().split(',')[1],checks:{bloomChangedPixels:changed,bloomMeanChannelDelta:total/(W*H*3),bloomMaxChannelDelta:max,nearWhitePixels:hot,formats,glError:g.getError(),formatLegend:{5126:'FLOAT',35863:'UNSIGNED_NORMALIZED'}}};});
for(const [key,file]of [['board','pipeline-comparison.png'],['detail','cell-closeup.png']])fs.writeFileSync(path.join(out,file),Buffer.from(result[key],'base64'));
fs.writeFileSync(path.join(out,'audit.json'),JSON.stringify({checks:result.checks,errors,scope:'Existing standalone WebGL menu preview only. Runtime menu has no corresponding material/bloom integration.'},null,2));if(errors.length||result.checks.glError)throw Error(JSON.stringify({errors,checks:result.checks}));console.log(JSON.stringify(result.checks));
}finally{await b.close();}}main().catch(e=>{console.error(e);process.exitCode=1;});
