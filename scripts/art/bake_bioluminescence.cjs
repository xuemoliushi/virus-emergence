// Export the approved WebGL material into ordinary engine-readable textures.
// No game or browser simulation is advanced by this authoring step.
const fs=require('fs'),path=require('path');
const {chromium}=require('C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const OUT=path.resolve(__dirname,'../../validation/bioluminescence-integration-20261015/bake');
async function main(){fs.mkdirSync(OUT,{recursive:true});const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});try{const page=await browser.newPage();await page.goto(require('url').pathToFileURL(path.resolve(__dirname,'../../validation/unified-highlight-review-20261015/preview.html')).href);await page.evaluate(()=>ready);await page.evaluate(()=>{lab.state.playing=false;lab.state.benchmark=true;});
for(const [name,slot,kind]of [['virus',0,0],['macrophage',1,1],['tcell-01',2,2],['tcell-02',3,2],['healthy',8,3]]){
 for(let frame=0;frame<4;frame++){const data=await page.evaluate(({slot,kind,frame})=>{
 const g=lab.gl;g.bindFramebuffer(g.FRAMEBUFFER,R.scene.fb);g.viewport(0,0,1280,720);g.disable(g.BLEND);g.clearColor(0,0,0,0);g.clear(g.COLOR_BUFFER_BIT);
 instances.set([640,360,512,0,slot,kind,0,1],0);g.bindBuffer(g.ARRAY_BUFFER,buffer);g.bufferSubData(g.ARRAY_BUFFER,0,instances,0,8);g.useProgram(P.cell.p);g.bindVertexArray(vao);
 for(const [i,n]of ['base','maps','field','noise'].entries())bind(P.cell,n+'Tex',T[n],i);g.uniform1f(un(P.cell,'t'),frame*3+1.5);g.uniform1f(un(P.cell,'highlight'),1);g.uniform1i(un(P.cell,'plain'),0);g.drawArraysInstanced(g.TRIANGLES,0,6,1);
 function b64(a){const bytes=new Uint8Array(a.buffer),parts=[];for(let i=0;i<bytes.length;i+=8192)parts.push(String.fromCharCode(...bytes.subarray(i,i+8192)));return btoa(parts.join(''));}
 const c=new Float32Array(512*512*4),e=new Uint8Array(512*512*4);g.readBuffer(g.COLOR_ATTACHMENT0);g.readPixels(384,104,512,512,g.RGBA,g.FLOAT,c);g.readBuffer(g.COLOR_ATTACHMENT1);g.readPixels(384,104,512,512,g.RGBA,g.UNSIGNED_BYTE,e);const error=g.getError();if(error)throw Error('Material readback '+error);return{color:frame===0?b64(c):null,emission:b64(e)};
 },{slot,kind,frame});if(data.color)fs.writeFileSync(path.join(OUT,name+'.f32'),Buffer.from(data.color,'base64'));fs.writeFileSync(path.join(OUT,name+'-emission-'+frame+'.rgba'),Buffer.from(data.emission,'base64'));
 }console.log('BAKED '+name);
}}finally{await browser.close();}}
main().catch(e=>{console.error(e);process.exitCode=1;});
