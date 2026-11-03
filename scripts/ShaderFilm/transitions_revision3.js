// Absolute-time camera. Integrating a continuous velocity avoids a stop at
// illustration changes; all scales and the planetary limb share this distance.
function integratedSmooth(t,start,duration){
 const x=(t-start)/duration;
 if(x<=0)return 0;
 if(x>=1)return t-start-duration*.5;
 return duration*(x*x*x-.5*x*x*x*x);
}
function ascentDistance(t){
 t=Math.max(60,t);
 return .035*(t-60)+.40*integratedSmooth(t,64,13)-.43*integratedSmooth(t,81,6);
}
function ascentPose(t){
 const q=ascentDistance(t),horizon=mix(110,205,ramp(t,74,87));
 const radius=285*Math.exp(ascentDistance(87)-q);
 return {distance:q,horizon,radius,center:[960,radius+horizon],
  cityScale:1.12*Math.exp(.24*(ascentDistance(71.2)-q)),
  curveScale:1.12*Math.exp(.22*(ascentDistance(76)-q)),
  regionScale:1.12*Math.exp(.10*(ascentDistance(80.5)-q))};
}
function ascentLayer(name,t,scale,sourceHorizon,opacity=1){
 if(opacity<=0)return;
 const p=programs.ascent,pose=ascentPose(t);
 use(p);bindTex(textures[name]);uniforms(p,{uTex:0,uResolution:[W,H],uScale:scale,
  uHorizon:pose.horizon,uSourceHorizon:sourceHorizon,uOpacity:opacity});
 gl.drawArrays(gl.TRIANGLES,0,6);
}
function ascent(t){
 const p=ascentPose(t),toCurve=ramp(t,68.5,71.2),toRegion=ramp(t,73,76),toEarth=ramp(t,78,80.5);
 if(t<71.2)ascentLayer('city',t,p.cityScale,70);
 if(t>=68.5&&t<76)ascentLayer('curvature',t,p.curveScale,150,toCurve);
 if(t>=73&&t<80.5)ascentLayer('region',t,p.regionScale,95,toRegion);
 if(t>=78){
  const shader=programs.earth;use(shader);bindTex(textures.earth);
  uniforms(shader,{uTex:0,uResolution:[W,H],uCenter:p.center,uRadius:p.radius,
   uSpace:ramp(t,78,82),uOpacity:toEarth});gl.drawArrays(gl.TRIANGLES,0,6);
 }
 // The street-to-wide edit is concealed once. No cloud resets at city/region
 // joins, and no foreground cloud renderer is called in space.
 if(t<61.3){const fog=1-ramp(t,60,61.3);cloudBanks(t,fog,10.35+(t-60)*.4);cloud(t,fog,10.35+(t-60)*.4);}
}
window.transitionDebug={ascentPose,ascentDistance,
 entry:t=>({cityOpacity:1-ramp(t,44.35,46),streetOpacity:ramp(t,44.35,46),
  cityScale:logmix(1.04,1.55,ramp(t,43,46)),streetScale:logmix(1.045,1,ramp(t,44.35,46)),
  cloud:1-ramp(t,43,45.1)}),cloudsEnd:61.3};
