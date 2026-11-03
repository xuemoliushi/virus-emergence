// Rebuild the existing approved menu composition using the user's new HD healthy cell.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),{spawnSync}=require('child_process');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'validation/menu-healthy-hd-20261015');fs.mkdirSync(out,{recursive:true});
const source=path.join(root,'validation/unified-highlight-review-20261015/art/healthy.png');
const asset=path.join(root,'assets/image/menu/healthy-hd-v1.png');fs.mkdirSync(path.dirname(asset),{recursive:true});fs.copyFileSync(source,asset);
const digest=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
let html=fs.readFileSync(path.join(root,'validation/menu-fluorescence-brighter-20261015/preview.html'),'utf8');
function patch(a,b){if(!html.includes(a))throw Error('Missing HD boundary '+a.slice(0,90));html=html.replace(a,b);}
const start=html.indexOf('async function menuTextures(){'),end=html.indexOf('window.ready=menuTextures()',start);if(start<0||end<0)throw Error('Missing texture preparation');
const imageURI='data:image/png;base64,'+fs.readFileSync(asset).toString('base64');
html=html.slice(0,start)+`async function menuTextures(){
 const source=new Image();source.src=${JSON.stringify(imageURI)};await source.decode();
 const dim=source.width,c=document.createElement('canvas');c.width=source.width;c.height=source.height;const x=c.getContext('2d',{willReadFrequently:true});x.drawImage(source,0,0);
 const pixels=x.getImageData(0,0,c.width,c.height).data;let x0=c.width,y0=c.height,x1=0,y1=0;for(let y=0;y<c.height;y++)for(let z=0;z<c.width;z++)if(pixels[(y*c.width+z)*4+3]>20){x0=Math.min(x0,z);y0=Math.min(y0,y);x1=Math.max(x1,z+1);y1=Math.max(y1,y+1);}
 const N=1024,s=N*.90625/Math.max(x1-x0,y1-y0),w=Math.round((x1-x0)*s),h=Math.round((y1-y0)*s),ox=Math.floor((N-w)/2),oy=Math.floor((N-h)/2);
 const base=document.createElement('canvas');base.width=base.height=N;const bx=base.getContext('2d',{willReadFrequently:true});bx.imageSmoothingEnabled=true;bx.imageSmoothingQuality='high';bx.drawImage(c,x0,y0,x1-x0,y1-y0,ox,oy,w,h);const b=bx.getImageData(0,0,N,N).data;
 const map=document.createElement('canvas'),field=document.createElement('canvas');map.width=map.height=field.width=field.height=N;const ctx=map.getContext('2d'),m=ctx.createImageData(N,N),fx=field.getContext('2d'),f=fx.createImageData(N,N);
 const clamp=v=>Math.max(0,Math.min(1,v));let occupied=0,lit=0,nuclearLeak=0;
 for(let y=0;y<N;y++)for(let z=0;z<N;z++){const k=(y*N+z)*4,a=b[k+3]/255;f.data[k]=128;f.data[k+1]=128;f.data[k+3]=255;m.data[k+3]=255;if(a<.01)continue;occupied++;
 const r=b[k]/255,g=b[k+1]/255,bb=b[k+2]/255,lum=r*.2126+g*.7152+bb*.0722;
 const nucleus=clamp((g-r*.42)*5)*clamp((bb-g*.9)*7);
 let minimum=a;for(const [dx,dy]of [[-3,0],[3,0],[0,-3],[0,3],[-2,-2],[2,2]]){const xx=Math.max(0,Math.min(N-1,z+dx)),yy=Math.max(0,Math.min(N-1,y+dy));minimum=Math.min(minimum,b[(yy*N+xx)*4+3]/255);}
 const edge=clamp((a-minimum)*1.3),red=clamp((r-g-.17)*2.3),rim=edge*red;
 const thread=clamp((lum-.12)*2.1)*red*(1-nucleus)*a;
 const spark=clamp((lum-.48)*2.8)*(1-nucleus)*a;
 m.data[k]=Math.round(rim*255);m.data[k+1]=Math.round(thread*255);m.data[k+2]=Math.round(spark*255);f.data[k+2]=Math.round(nucleus*255);
 if(rim>.1||spark>.1)lit++;if(nucleus>.9&&spark>.1)nuclearLeak++;
 }ctx.putImageData(m,0,0);fx.putImageData(f,0,0);
 for(const [name,tile]of [['base',base],['maps',map],['field',field]]){const old=new Image();old.src=window.FINAL_TEXTURES[name];await old.decode();const a=document.createElement('canvas');a.width=a.height=N*3;const q=a.getContext('2d');q.drawImage(old,0,0,N*3,N*3);q.clearRect(N*2,N*2,N,N);q.drawImage(tile,N*2,N*2);window.FINAL_TEXTURES[name]=a.toDataURL();}
 window.menuMaskQA={sourceSize:[source.width,source.height],tileSize:N,occupied,hotMaskPixels:lit,hotMaskCoverage:lit/occupied,nuclearLeak};
}
`+html.slice(end);
// Preserve the new material's own highlights; extra emission remains local and restrained.
patch('albedo*=mix(.51,.72,f.b);','albedo*=mix(.65,.79,f.b);');
patch('float threads=m.g*(.035+.11*pow(travel,5.));','float threads=m.g*(.025+.09*pow(travel,5.));');
patch('float sparks=m.b*(.19+1.15*pow(','float sparks=m.b*(.15+.85*pow(');
patch('atlas:[2304,2304]','atlas:[3072,3072]');
// Respect each sprite's rotation while keeping the membrane and its emission aligned.
patch('vec2 p=transform.xy+(pos-.5)*transform.z;', 'float a=transform.w;vec2 q=pos-.5;vec2 rp=vec2(q.x*cos(a)-q.y*sin(a),q.x*sin(a)+q.y*cos(a));vec2 p=transform.xy+rp*transform.z;');
patch('size*(1+Math.sin(a)*.013)/.90625,0,slot,kind,seed,alpha','size*(1+Math.sin(a)*.013)/.90625,kind===3?seed*.17+Math.sin(a)*.012:0,slot,kind,seed,alpha');
fs.writeFileSync(path.join(out,'preview.html'),html);
fs.writeFileSync(path.join(out,'source-manifest.json'),JSON.stringify({source:path.relative(root,source).replaceAll('\\','/'),sourceSha256:digest(source),asset:path.relative(root,asset).replaceAll('\\','/'),assetSha256:digest(asset),atlasTile:1024,scope:'HD healthy cell menu approval prototype; main game unchanged.'},null,2));
let runner=fs.readFileSync(path.join(__dirname,'fix.cjs'),'utf8');runner=runner.slice(runner.indexOf('async function main(){'));
runner=runner.replace("masks:menuMaskQA,glError:g.getError()","masks:menuMaskQA,motes:window.menuMotes,glError:g.getError()");
runner=runner.replace("// Capture fresh frames every run,",`await page.locator('.menu').evaluate(e=>e.style.visibility='hidden');await page.evaluate(()=>lab.render(2));await page.locator('#stage').screenshot({path:path.join(out,'background-only.png')});await page.locator('.menu').evaluate(e=>e.style.visibility='');
// Capture fresh frames every run,`);
runner=runner.replace('Fixed standalone WebGL menu prototype; original art and runtime Lua unchanged.','Updated HD healthy cell menu prototype; current high resolution source and fresh emission maps; runtime Lua unchanged.');
eval(runner);
