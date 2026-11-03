 view(t){
  const h=this.meta.hero*7,p=this.state,track=45*t;
  const hx=960+1450*(p[h]-track)/p[h+2],hy=450-1450*p[h+1]/p[h+2];
  const smooth=x=>{x=Math.max(0,Math.min(1,x));return x*x*x*(x*(x*6-15)+10);};
  const pull=smooth((t-15)/4),push=smooth((t-27.6)/2.4),shotZoom=Math.exp(Math.log(2.8)*push);
  const clock=Math.max(0,Math.min(this.meta.frame_count-1,t*this.meta.fps)),a=Math.floor(clock),b=Math.min(a+1,this.meta.frame_count-1),u=clock-a;
  const framing=this.meta.framing,at=j=>framing[a][j]*(1-u)+framing[b][j]*u;
  const fit=at(2),fitMix=Math.exp(Math.log(fit)*pull),pullback=Math.exp(Math.log(58)*(1-pull)+Math.log(fit)*pull);
  const projectAt=time=>{
   const frame=Math.max(0,Math.min(this.meta.frame_count-1,time*this.meta.fps)),a=Math.floor(frame),b=Math.min(a+1,this.meta.frame_count-1),f=frame-a;
   const start=a*this.meta.count*7+h,end=b*this.meta.count*7+h;
   const x=this.motion[start]*(1-f)+this.motion[end]*f,y=this.motion[start+1]*(1-f)+this.motion[end+1]*f,z=this.motion[start+2]*(1-f)+this.motion[end+2]*f;
   return [960+1450*(x-45*time)/z,450-1450*y/z];
  };
  const atFall=projectAt(31.6),holdU=Math.max(0,Math.min(1,(t-30)/3.2));
  const integral=holdU**6-3*holdU**5+2.5*holdU**4;
  const heldTime=t<30?t:30+3.2*(holdU-integral),subject=projectAt(heldTime);
  // Group framing is baked with a symmetric temporal filter. It neither
  // depends on playback order nor chases one randomly moving individual.
  const group=[960*(1-pull)+at(0)*pull,540*(1-pull)+at(1)*pull];
  const heroFit=fitMix*(1-push)+push;
  const focus=[group[0]*(1-push)+subject[0]*push,group[1]*(1-push)+(subject[1]-110/2.8)*push];
  const originalRoot=[970*(1-pull)+hx*pull,510*(1-pull)+hy*pull];
  const root=[960+(originalRoot[0]-focus[0])*shotZoom*heroFit,540+(originalRoot[1]-focus[1])*shotZoom*heroFit];
  const zoom=(pullback*(1-push)+push)*shotZoom;
  const drop=(hy-atFall[1])*shotZoom,x=drop-115,w=55,q=Math.max(0,Math.min(1,x/w));
  const fallcam=t<=31.6||x<=0?0:x>=w?x-w/2:w*(q**6-3*q**5+2.5*q**4);
  return {track,hx,hy,root,zoom,fallcam,hero:[root[0],root[1]-fallcam],shotZoom,focus,push,drop,holdUntilPixels:115,groupCenter:[at(0),at(1)],groupFit:fit};
 }
