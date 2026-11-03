/* Absolute-frame Canvas film. All workers read the same baked local-rule flock. */
const cv=document.getElementById('film');let ctx=cv.getContext('2d',{alpha:false});
const W=1920,H=1080,ivory='#f4f2ec',ink='#151513';
const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,v));
const sm=v=>{v=clamp(v);return v*v*(3-2*v)};
const mix=(a,b,v)=>a+(b-a)*v;
const logmix=(a,b,v)=>Math.exp(mix(Math.log(a),Math.log(b),v));
let images={},flock,timeline,showSubs=true,current=0,playing=false,origin=0;
const imageNames={body:'bird_body.png',wing:'bird_wing.png',cloud:'cloud_world.jpg',city:'city_world.jpg',earth:'earth.png',c0:'cloud_0.png',c1:'cloud_1.png'};
window.ready=(async()=>{
  await Promise.all(Object.entries(imageNames).map(async([k,n])=>{let im=new Image();im.src='art/'+n;await im.decode();images[k]=im}));
  [flock,timeline]=await Promise.all(['flock.json','timeline.json'].map(async n=>(await fetch(n)).json()));
  await document.fonts.ready; window.renderFrame(0);document.getElementById('status').textContent='90 秒 · 24 fps · 2160 帧 · 原创程序配乐 / 英文 TTS';return true;
})();
function layer(im,x,y,w,h,alpha=1){ctx.save();ctx.globalAlpha=clamp(alpha);ctx.drawImage(im,x,y,w,h);ctx.restore()}
function smoothSegment(u,a,b){return sm(clamp((u-a)/(b-a)))}
function birdPose(t,phase=0,freq=2.2,dead=false){
  if(dead)return {wing:-1.72+.035*Math.sin(t*1.15+phase),bob:.9*Math.sin(t*.65+phase),pitch:.018*Math.sin(t*.8+phase),squash:1,bend:.12,fold:.78};
  // A real stroke is asymmetric: the power stroke is quick, recovery is slower,
  // and one cycle occasionally becomes a short glide instead of another flap.
  const clock=t*freq+phase/(Math.PI*2)+.10*Math.sin(t*.93+phase);
  const macro=((clock%3.55)+3.55)%3.55;
  const glide=macro>=2;
  const cycle=glide?.55:macro%1;
  const stops=[[0,-.95],[.15,.04],[.26,-.18],[.48,-2.14],[.57,-2.18],[.72,-1.60],[1,-.95]];
  let wing=.02;
  for(let i=0;i<stops.length-1;i++){
    const [a0,v0]=stops[i],[a1,v1]=stops[i+1];
    if(cycle>=a0&&cycle<=a1){const q=smoothSegment(cycle,a0,a1);wing=mix(v0,v1,q);break;}
  }
  if(glide)wing=-1.02+.055*Math.sin((macro-2)*Math.PI/1.55);
  const lift=(glide?.25:Math.sin(cycle*Math.PI*2-.72))*(1-sm((t-34)/2)*.75);
  const fatigue=sm((t-34)/2)*.55;
  wing=mix(wing,-1.4,fatigue);
  return {
    wing,
    bob:2.8*lift+0.8*Math.sin(t*.71+phase),
    pitch:.028*Math.sin(cycle*Math.PI*2+.35)+.012*Math.sin(t*.47+phase),
    squash:1+.008*Math.sin(cycle*Math.PI*2-.2),
    bend:glide?.035:.19*Math.sin(cycle*Math.PI*2-1.0),
    fold:glide?1:1-.24*sm((cycle-.58)/.1)*(1-sm((cycle-.91)/.09))
  };
}
function texturedTriangle(im,a,b,c,aa,bb,cc){
  const d=a[0]*(b[1]-c[1])+b[0]*(c[1]-a[1])+c[0]*(a[1]-b[1]);
  const solve=v=>[(v[0]*(b[1]-c[1])+v[1]*(c[1]-a[1])+v[2]*(a[1]-b[1]))/d,
    (v[0]*(c[0]-b[0])+v[1]*(a[0]-c[0])+v[2]*(b[0]-a[0]))/d,
    (v[0]*(b[0]*c[1]-c[0]*b[1])+v[1]*(c[0]*a[1]-a[0]*c[1])+v[2]*(a[0]*b[1]-b[0]*a[1]))/d];
  const u=solve([aa[0],bb[0],cc[0]]),v=solve([aa[1],bb[1],cc[1]]);
  ctx.save();ctx.beginPath();const cx=(aa[0]+bb[0]+cc[0])/3,cy=(aa[1]+bb[1]+cc[1])/3;
  for(const [i,p] of [aa,bb,cc].entries()){const dx=p[0]-cx,dy=p[1]-cy,l=Math.hypot(dx,dy);const x=p[0]+dx/l*1.4,y=p[1]+dy/l*1.4;i?ctx.lineTo(x,y):ctx.moveTo(x,y)}
  ctx.closePath();ctx.clip();ctx.transform(u[0],v[0],u[1],v[1],u[2],v[2]);ctx.drawImage(im,0,0);ctx.restore();
}
function flexibleWing(pose,far=false){
  const nx=5,ny=10,points=[];
  for(let j=0;j<=ny;j++)for(let i=0;i<=nx;i++){
    const x=140+205*i/nx,y=25+355*j/ny,dx=x-320,dy=y-370;
    const reach=clamp((370-y)/345),a=pose.wing+pose.bend*reach*reach+(far?.09:0);
    const k=far?.83:1;const px=dx*pose.fold,py=dy;
    points.push([[x,y],[320+k*(px*Math.cos(a)-py*Math.sin(a)),370+k*(px*Math.sin(a)+py*Math.cos(a))]]);
  }
  for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){
    const a=points[j*(nx+1)+i],b=points[j*(nx+1)+i+1],c=points[(j+1)*(nx+1)+i],d=points[(j+1)*(nx+1)+i+1];
    texturedTriangle(images.wing,a[0],b[0],c[0],a[1],b[1],c[1]);texturedTriangle(images.wing,b[0],d[0],c[0],b[1],d[1],c[1]);
  }
}
const birdSprites=new Map();
function birdSprite(pose){
  const bins=[Math.round(pose.wing*48),Math.round(pose.bend*24),Math.round(pose.fold*48)];
  const key=bins.join(':');
  if(birdSprites.has(key))return birdSprites.get(key);
  pose={wing:bins[0]/48,bend:bins[1]/24,fold:bins[2]/48};
  const main=ctx,sprite=document.createElement('canvas');sprite.width=620;sprite.height=760;
  ctx=sprite.getContext('2d');ctx.translate(100,0);
  flexibleWing(pose,true);ctx.drawImage(images.body,0,0);flexibleWing(pose);
  ctx.drawImage(images.body,290,348,61,78,290,348,61,78);ctx=main;
  if(birdSprites.size>=96)birdSprites.delete(birdSprites.keys().next().value);
  birdSprites.set(key,sprite);return sprite;
}
function birdParts(x,y,s,t,phase=0,freq=2.2,angle=0,dead=false,bodyAlpha=1,wingAlpha=1){
  const pose=birdPose(t,phase,freq,dead);
  ctx.save();ctx.translate(x+310*s,y+405*s+pose.bob*s);ctx.rotate(angle+pose.pitch);ctx.scale(s*pose.squash,s);ctx.translate(-310,-405);
  ctx.globalAlpha=clamp(bodyAlpha);ctx.drawImage(birdSprite(pose),-100,0);
  ctx.restore();
}
function bird(x,y,s,t,phase=0,freq=2.2,angle=0,dead=false){birdParts(x,y,s,t,phase,freq,angle,dead,1,1)}
function birdAtParts(x,y,s,t,phase=0,freq=2.2,angle=0,dead=false,bodyAlpha=1,wingAlpha=1){
 ctx.save();ctx.translate(x,y);ctx.rotate(angle);birdParts(-310*s,-405*s,s,t,phase,freq,0,dead,bodyAlpha,wingAlpha);ctx.restore();
}
function birdAt(x,y,s,t,phase=0,freq=2.2,angle=0,dead=false){
 birdAtParts(x,y,s,t,phase,freq,angle,dead,1,1);
}
function flockState(t){return flock.states[Math.min(1080,Math.max(0,Math.round(t*24)))]}
function tissue(x,y,s,t,clip=false,alpha=1){
  ctx.save();ctx.globalAlpha=clamp(alpha);ctx.translate(x,y);ctx.scale(s,s);
  if(clip){ctx.beginPath();ctx.ellipse(18,7,30,20,0,0,Math.PI*2);ctx.clip()}
  ctx.strokeStyle='rgba(25,25,22,.85)';ctx.lineWidth=1.5;
  for(let iy=-12;iy<=12;iy++)for(let ix=-16;ix<=16;ix++){
    let a=ix*17+Math.sin(iy*5+ix)*3,b=iy*15+Math.cos(ix*4-iy)*3;
    let r=6+.35*Math.sin(t*.75+ix*2.3+iy*.8);
    ctx.beginPath();ctx.ellipse(a,b,r,r*.82,Math.sin(ix+iy)*.4,0,Math.PI*2);ctx.stroke();
    ctx.beginPath();ctx.ellipse(a+1,b,1.6,1.3,0,0,Math.PI*2);ctx.fillStyle=ink;ctx.fill();
  }ctx.restore();
}
function sky(t){
  ctx.fillStyle=ivory;ctx.fillRect(0,0,W,H);
  let g=ctx.createLinearGradient(0,0,0,H);g.addColorStop(0,'#f6f3ed');g.addColorStop(1,'#eae6dc');ctx.fillStyle=g;ctx.fillRect(0,0,W,H);
  // Barely visible distant atmospheric planes, not repeated noise.
  ctx.fillStyle='rgba(190,185,170,.12)';
  for(let j=0;j<3;j++){ctx.beginPath();ctx.moveTo(0,840+j*62);for(let x=0;x<=W;x+=40)ctx.lineTo(x,840+j*62+Math.sin(x*.003+j+t*.009)*28);ctx.lineTo(W,H);ctx.lineTo(0,H);ctx.fill()}
}
function microscopic(t){
  const s=logmix(7.1,4.8,sm((t-2)/4));tissue(1080,520,s,t);
  ctx.fillStyle=`rgba(0,0,0,${1-sm((t-.8)/1.2)})`;ctx.fillRect(0,0,W,H);
}
const tissueLayer=document.createElement('canvas');tissueLayer.width=1920;tissueLayer.height=1080;
const tc=tissueLayer.getContext('2d');
function host(t){
  const q=sm((t-6)/7.5),s=logmix(24,1.30,q);
  const x=1080,y=mix(520,485,sm((t-6)/7.5));
  const offset=1-sm((t-12)/6),bx=x-25*s*offset,by=y+3*s*offset;
  // One camera and one chest anchor: the same cells shrink into this bird.
  birdAt(bx,by,s,t,flock.phases[flock.hero],flock.freq[flock.hero],0,false);
  const fade=1-sm((t-13)/2.4);if(fade<=0)return;
  tc.setTransform(1,0,0,1,0,0);tc.clearRect(0,0,W,H);tc.globalCompositeOperation='source-over';
  const edgeCover=mix(1.5,1,sm((t-6)/2));
  const rx=s*58*edgeCover,ry=s*40*edgeCover;
  const backing=1-sm((t-8)/4.5);
  if(backing>0){tc.save();tc.translate(x,y);tc.scale(rx,ry);const bg=tc.createRadialGradient(0,0,.82,0,0,1);bg.addColorStop(0,`rgba(244,242,236,${backing})`);bg.addColorStop(1,'rgba(244,242,236,0)');tc.fillStyle=bg;tc.fillRect(-1,-1,2,2);tc.restore();}
  tc.save();tc.translate(x,y);tc.scale(s*.2,s*.2);tc.lineWidth=1.5;tc.strokeStyle='rgba(25,25,22,.85)';tc.fillStyle=ink;
  for(let iy=-12;iy<=12;iy++)for(let ix=-16;ix<=16;ix++){
    const a=ix*17+Math.sin(iy*5+ix)*3,b=iy*15+Math.cos(ix*4-iy)*3,r=6+.35*Math.sin(t*.75+ix*2.3+iy*.8);
    tc.beginPath();tc.ellipse(a,b,r,r*.82,Math.sin(ix+iy)*.4,0,Math.PI*2);tc.stroke();tc.beginPath();tc.ellipse(a+1,b,1.6,1.3,0,0,Math.PI*2);tc.fill();
  }tc.restore();
  tc.globalCompositeOperation='destination-in';tc.save();tc.translate(x,y);tc.scale(rx,ry);
  const mask=tc.createRadialGradient(0,0,.74,0,0,1);mask.addColorStop(0,'white');mask.addColorStop(1,'transparent');tc.fillStyle=mask;tc.fillRect(-1,-1,2,2);tc.restore();
  ctx.save();ctx.globalAlpha=fade;ctx.drawImage(tissueLayer,0,0);ctx.restore();
}
function groups(t){
  const st=flockState(t),h=st[flock.hero];
  let mag=logmix(16.25,1,sm((t-18)/5));
  let ax=mix(1080,1080,sm((t-18)/5)),ay=mix(485,695,sm((t-18)/5));
  let follow=sm((t-39)/6);
  let oy=(t<39?742:mix(742,h[1],follow));
  // World→screen camera follows the same hero, then descends after the hold.
  if(t<23){oy=h[1];}
  ctx.save();ctx.translate(ax,ay);ctx.scale(mag,mag);ctx.translate(-h[0],-oy);
  for(let i=0;i<st.length;i++){
    const z=st[i],dead=i===flock.hero&&t>=36;
    const ang=dead?mix(.10,.80,sm((t-36)/10))+.03*Math.sin(t*1.2):clamp(z[3]/80,-.15,.15);
    birdAt(z[0],z[1],.08,t,flock.phases[i],flock.freq[i],ang,dead);
  }ctx.restore();
}
function falling(t){
  if(t<51.8){
    const q=sm((t-45)/7);birdAt(mix(1080,1120,q),mix(695,738,q),mix(.08,.28,q),t,0,0,.8+.06*Math.sin(t),true);
  }
  const reveal=sm((t-49)/3);layer(images.cloud,0,-mix(0,80,sm((t-45)/7)),W,H+100,reveal);
  // Opaque veil guarantees a concealed change of visual layer.
  const cloudA=sm((t-49.8)/1.7)*(1-sm((t-54.5)/2));
  ctx.fillStyle=`rgba(234,231,222,${cloudA})`;ctx.fillRect(0,0,W,H);
  if(t>=52){city(t);cloudOverlay(t,sm((t-52)/2.5)*(1-sm((t-56)/3)));}
}
function cloudOverlay(t,a){
  layer(images.c0,-200,-200-(t-52)*35,900,1200,a*.92);
  layer(images.c1,1230,-180-(t-52)*48,900,1200,a*.92);
  if(t<53){ctx.fillStyle=`rgba(239,235,224,${1-sm((t-52)/1)})`;ctx.fillRect(0,0,W,H)}
}
function cityTransform(t){
  let q=sm((t-63)/13),s=logmix(2.65,1,q);
  return {s,x:mix(1070,1340,q),y:mix(590,855,q),cx:1340,cy:855};
}
function pedestrian(x,y,t,angle=0){ctx.save();ctx.translate(x,y);ctx.rotate(angle);ctx.fillStyle='#1b1b18';ctx.lineWidth=1.7;ctx.strokeStyle=ink;ctx.beginPath();ctx.arc(0,-6,1.7,0,Math.PI*2);ctx.fill();ctx.fillRect(-1.3,-4,2.6,5);ctx.beginPath();let a=Math.sin(t*8)*2;ctx.moveTo(0,0);ctx.lineTo(-1.8-a,4);ctx.moveTo(0,0);ctx.lineTo(1.8+a,4);ctx.stroke();ctx.restore()}
function car(x,y,a){ctx.save();ctx.translate(x,y);ctx.rotate(a);ctx.fillStyle='#252520';ctx.beginPath();ctx.roundRect(-5,-2.6,10,5.2,1.5);ctx.fill();ctx.fillStyle='#b5b0a1';ctx.fillRect(-1.5,-2,2,4);ctx.restore()}
function actors(t){
  // Approximate perspective routes follow the actual dense-city intersection.
  const q=clamp((t-59)/6);
  pedestrian(mix(1320,1348,q),mix(842,866,q),t,-.45);
  const wait=clamp((t-59)/1.8)*.6+clamp((t-64)/3)*.4;
  car(mix(1281,1392,wait),mix(876,829,wait),-.42);
  let meet=sm((t-59)/3),walk=clamp((t-62)/9);
  pedestrian(mix(1382,1365,meet)+walk*23,mix(810,818,meet)-walk*13,t,0);
  pedestrian(mix(1352,1369,meet)+walk*23,mix(796,820,meet)-walk*13,t+.5,0);
  let turn=clamp((t-61)/7);car(mix(1330,1410,turn),mix(914,835,turn)-18*Math.sin(turn*Math.PI),mix(-1.2,-.35,turn));
  for(let i=0;i<14;i++){let u=((t*.035+i*.17)%1);car(550+i*67+u*42,800-i*31-u*18,-.4)}
}
function city(t){
  let c=cityTransform(t);ctx.save();ctx.translate(c.x,c.y);ctx.scale(c.s,c.s);ctx.translate(-c.cx,-c.cy);
  ctx.drawImage(images.city,0,0,W,H);actors(t);ctx.restore();
}
function planet(t){
  let q=sm((t-76)/6.5),d=logmix(5600,540,q),x=mix(1410,960,q),y=mix(1100,480,q);
  // The city window is registered to one fixed point on the enlarged continent.
  ctx.save();ctx.beginPath();ctx.arc(x,y,d/2,0,Math.PI*2);ctx.clip();
  layer(images.earth,x-d/2,y-d/2,d,d);
  const a=1-sm((t-77.5)/3.2);
  if(a>0){ctx.save();ctx.globalAlpha=a;
    let ax=x-d*.08,ay=y+d*.03,sz=d*.33;
    const g=ctx.createRadialGradient(ax,ay,sz*.05,ax,ay,sz*.5);g.addColorStop(0,'#fff');g.addColorStop(1,'transparent');
    let off=document.createElement('canvas');off.width=960;off.height=540;let oc=off.getContext('2d');oc.drawImage(images.city,0,0,960,540);oc.globalCompositeOperation='destination-in';let og=oc.createRadialGradient(480,270,80,480,270,450);og.addColorStop(0,'white');og.addColorStop(1,'transparent');oc.fillStyle=og;oc.fillRect(0,0,960,540);
    ctx.drawImage(off,ax-sz/2,ay-sz*.28125,sz,sz*.5625);ctx.restore();}
  ctx.restore();
  if(t>=87){ctx.save();ctx.globalAlpha=sm(t-87);ctx.fillStyle=ink;ctx.textAlign='center';ctx.font='300 44px Georgia';ctx.letterSpacing='12px';ctx.fillText('EMERGENCE',960,817);ctx.letterSpacing='4px';ctx.font='30px "Microsoft YaHei"';ctx.fillText('涌现',960,873);ctx.restore()}
}
function subtitle(t){
  if(!showSubs)return;let cue=timeline.subtitles.find(c=>c.start<=t&&t<c.end);if(!cue)return;
  ctx.save();ctx.textAlign='center';ctx.letterSpacing='0px';ctx.font='38px "Microsoft YaHei"';let zh=ctx.measureText(cue.zh).width;
  ctx.font='27px Georgia';let en=ctx.measureText(cue.en).width;let w=Math.max(zh,en)+70;
  ctx.fillStyle='rgba(244,242,236,.94)';ctx.beginPath();ctx.roundRect(960-w/2,931,w,116,9);ctx.fill();ctx.fillStyle=ink;
  ctx.font='38px "Microsoft YaHei"';ctx.fillText(cue.zh,960,977);ctx.font='27px Georgia';ctx.fillText(cue.en,960,1022);ctx.restore();
}
window.renderFrame=function(n,subs=true){current=clamp(Math.floor(n),0,2159);showSubs=subs;const t=current/24;ctx.setTransform(1,0,0,1,0,0);ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';sky(t);
  if(t<6)microscopic(t);else if(t<18)host(t);else if(t<45)groups(t);else if(t<59)falling(t);else if(t<76)city(t);else planet(t);
  subtitle(t);return {frame:current,time:t};};
let audio=document.getElementById('audio'),slider=document.getElementById('seek');
function tick(now){if(playing){let t=(now-origin)/1000; if(audio.readyState>=2&&!audio.paused)t=audio.currentTime;if(t>=90){playing=false;audio.pause();t=89.958333}renderFrame(t*24,showSubs);slider.value=current;document.getElementById('time').textContent=t.toFixed(1)+' / 90';}requestAnimationFrame(tick)}requestAnimationFrame(tick);
document.getElementById('play').onclick=async()=>{await ready;playing=!playing;if(playing){origin=performance.now()-current/24*1000;audio.currentTime=current/24;audio.play().catch(()=>{})}else audio.pause()};
slider.oninput=()=>{renderFrame(+slider.value,showSubs);audio.currentTime=current/24;origin=performance.now()-current/24*1000};
document.getElementById('subs').onclick=()=>{showSubs=!showSubs;renderFrame(current,showSubs)};
