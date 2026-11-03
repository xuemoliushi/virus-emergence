// Lighting revision of the fixed approval prototype; retains the original game assets.
const fs=require('fs'),path=require('path'),{spawnSync}=require('child_process');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'validation/menu-fluorescence-brighter-20261015');fs.mkdirSync(out,{recursive:true});
let html=fs.readFileSync(path.join(root,'validation/menu-fluorescence-fixed-20261015/preview.html'),'utf8');
function patch(a,b){if(!html.includes(a))throw Error('Missing lighting boundary: '+a.slice(0,80));html=html.replace(a,b);}
patch('float rim=m.r*(.035+.38*arc)*(.82+.18*breath);','float rim=m.r*(.075+.68*arc)*(.85+.15*breath);');
patch('float threads=m.g*(.018+.07*pow(travel,5.));','float threads=m.g*(.035+.11*pow(travel,5.));');
patch('float sparks=m.b*(.12+.88*pow(', 'float sparks=m.b*(.19+1.15*pow(');
patch('albedo*=mix(.32,.59,f.b);','albedo*=mix(.51,.72,f.b);');
patch('vec3(1.,.10,.17)*(rim+threads)+vec3(1.,.42,.42)*sparks','vec3(1.,.19,.25)*(rim+threads)+vec3(1.,.54,.49)*sparks');
// A procedural sprite branch emits small soft motes, independent of the cell's atlas.
patch('void main(){vec2 tile=','void main(){if(data.y>3.5){\n'+`
 vec2 q=uv-.5;float radius=length(q);
 float a=t*.5235987756;float slow=.5+.5*sin(a*(1.+mod(floor(data.z),3.))+data.z*2.7);
 float fast=.5+.5*sin(a*(3.+mod(floor(data.z),4.))+data.z*5.3);
 float pulse=.07+.70*pow(slow,5.)+.55*pow(fast,14.);
 float core=exp(-radius*radius*440.);float halo=exp(-radius*radius*39.);
 float alpha=(core+halo*.18)*data.w;if(alpha<.001)discard;
 float group=mod(floor(data.z),5.);
 vec3 tint=group<1.?vec3(.30,.65,.77):(group<3.?vec3(1.,.48,.18):vec3(1.,.25,.34));
 vec3 light=tint*(core*1.5+halo*.21)*pulse*data.w;
 color=vec4(light,alpha);emission=vec4(light,alpha);return;
 }vec2 tile=`);
const old='for(let i=0;i<18;i++){const x=(i*197+71)%1280;if(x>450&&x<830)continue;add(x,(i*149+60)%720,3+i%3,0,0,i*.73,.32);}';
patch(old,`// Stable per-mote random seeds; pulse frequencies are multiples of a twelve-second cycle.
let moteSeed=7319;const rnd=()=>{moteSeed=(Math.imul(moteSeed,1664525)+1013904223)>>>0;return moteSeed/4294967296;};
let motes=0;for(let i=0;i<110&&motes<72;i++){const x=24+rnd()*1232,y=16+rnd()*688;
 if(x>440&&x<840&&y>96&&y<645)continue;
 const size=5+rnd()*10,seed=rnd()*40;add(x,y,size,0,4,seed,.38+rnd()*.48);motes++;}
window.menuMotes=motes;`);
patch('#030207ec 0%,#030207b8 22%,#03020720 55%,#0003 100%','#030207d9 0%,#0302079c 22%,#0302070c 55%,#0002 100%');
fs.writeFileSync(path.join(out,'preview.html'),html);
// Reuse the validated renderer/export workflow; all 144 frames are captured afresh.
const runner=fs.readFileSync(path.join(__dirname,'fix.cjs'),'utf8').slice(fs.readFileSync(path.join(__dirname,'fix.cjs'),'utf8').indexOf('async function main(){'));
eval(runner.replace("masks:menuMaskQA,glError:g.getError()","masks:menuMaskQA,motes:window.menuMotes,glError:g.getError()").replace("Fixed standalone WebGL menu prototype; original art and runtime Lua unchanged.","Brighter standalone WebGL menu prototype with localized highlights and seeded twinkling motes; runtime Lua unchanged."));
