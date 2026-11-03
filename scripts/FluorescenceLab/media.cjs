const fs=require('fs'),path=require('path'),{spawn}=require('child_process');
const out=path.resolve(__dirname,'../../validation/fluorescence-lab-20261015');
const ff='C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe';
function convert(args,input,name){return new Promise((resolve,reject)=>{const p=spawn(ff,args,{stdio:['pipe','pipe','pipe'],windowsHide:true});const chunks=[],err=[];p.stdout.on('data',d=>chunks.push(d));p.stderr.on('data',d=>err.push(d));p.on('error',reject);p.stdin.on('error',()=>{});p.on('exit',c=>{if(c!==0)return reject(Error(Buffer.concat(err).toString()));const b=Buffer.concat(chunks);if(name)fs.writeFileSync(path.join(out,name),b);resolve({bytes:b.length,log:Buffer.concat(err).toString()});});p.stdin.end(input);});}
(async()=>{const input=fs.readFileSync(path.join(out,'comparison.mp4'));
const verify=await convert(['-v','info','-i','pipe:0','-f','null','pipe:1'],input);
if(!/frame=\s*288/.test(verify.log))throw Error('Expected 288 decoded video frames');
fs.writeFileSync(path.join(out,'video-verification.txt'),verify.log);
await convert(['-v','warning','-i','pipe:0','-vf','fps=12,scale=800:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3','-f','gif','-loop','0','pipe:1'],input,'comparison.gif');
const frame=await convert(['-v','warning','-i','pipe:0','-ss','5.8','-frames:v','1','-f','image2pipe','-vcodec','png','-pix_fmt','rgb24','pipe:1'],input,'video-decoded-check.png');
if(frame.bytes<1000)throw Error('Video frame extraction failed');
console.log('MEDIA_OK: 12s / 24fps / 288 decoded frames; GIF created.');})().catch(e=>{console.error(e);process.exitCode=1;});
