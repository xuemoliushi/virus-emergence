"""Relocate MP4 metadata for fast startup, copying approved media bytes verbatim."""
from pathlib import Path
import struct,hashlib,json,subprocess,os
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'assets/video/emergence_final90/涌现_90秒_修订版.mp4'
OUT=ROOT/'assets/video/ending';OUT.mkdir(exist_ok=True)

def boxes(data,start=0,end=None):
 end=len(data) if end is None else end
 while start<end:
  size,kind=struct.unpack_from('>I4s',data,start);header=8
  if size==1:size=struct.unpack_from('>Q',data,start+8)[0];header=16
  if size==0:size=end-start
  assert header<=size<=end-start,(start,size,kind)
  yield start,size,kind,header
  start+=size
 assert start==end

def main():
 data=SOURCE.read_bytes()
 verification=json.loads((SOURCE.parent/'verification.json').read_text('utf-8'))
 approved=next(v for v in verification['videos'] if v['file']=='涌现_90秒_双语字幕.mp4')
 assert approved['full_decode_ok'] and hashlib.sha256(data).hexdigest()==approved['sha256'],'Game source must match the verified current bilingual film'
 top=list(boxes(data))
 assert [b[2] for b in top].count(b'mdat')==1
 movie=next(b for b in top if b[2]==b'moov');media=next(b for b in top if b[2]==b'mdat')
 assert movie[0]>media[0],'Source has already been relocated; inspect before changing offsets'
 moov=bytearray(data[movie[0]:movie[0]+movie[1]]);delta=len(moov);chunks=0
 def patch(start,end):
  nonlocal chunks
  for pos,size,kind,header in boxes(moov,start,end):
   if kind in {b'moov',b'trak',b'mdia',b'minf',b'stbl'}:patch(pos+header,pos+size)
   elif kind in {b'stco',b'co64'}:
    count=struct.unpack_from('>I',moov,pos+header+4)[0];fmt='>I' if kind==b'stco' else '>Q';step=4 if kind==b'stco' else 8
    for i in range(count):
     at=pos+header+8+i*step;offset=struct.unpack_from(fmt,moov,at)[0]
     assert media[0]+media[3]<=offset<media[0]+media[1]
     struct.pack_into(fmt,moov,at,offset+delta);chunks+=1
 patch(0,len(moov));assert chunks>0
 result=bytearray()
 for pos,size,kind,header in top:
  if kind==b'moov':continue
  if kind==b'mdat':result.extend(moov)
  result.extend(data[pos:pos+size])
 assert len(result)==len(data)
 newtop=list(boxes(result));newmedia=next(b for b in newtop if b[2]==b'mdat')
 assert next(b[0] for b in newtop if b[2]==b'moov')<newmedia[0]
 source_payload=data[media[0]+media[3]:media[0]+media[1]]
 new_payload=result[newmedia[0]+newmedia[3]:newmedia[0]+newmedia[1]]
 assert source_payload==new_payload
 dest=OUT/'emergence90.mp4';temp=OUT/'emergence90.pending.mp4';temp.write_bytes(result)
 ff=Path(os.environ.get('SHADER_FFMPEG','C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe'))
 decode=subprocess.run([str(ff),'-v','error','-i',str(temp),'-f','null','-'],capture_output=True,check=True)
 assert not decode.stderr,decode.stderr.decode(errors='replace')
 probe=json.loads(subprocess.check_output([str(ff.with_name('ffprobe.exe')),'-v','error','-count_frames','-show_streams','-of','json',str(temp)]))
 video=next(s for s in probe['streams'] if s['codec_type']=='video')
 audio=next(s for s in probe['streams'] if s['codec_type']=='audio')
 assert int(video['nb_read_frames'])==2160 and float(video['duration'])==90 and float(audio['duration'])==90
 temp.replace(dest)
 report={'film_revision':verification['revision'],'source_verified':True,'source':str(SOURCE.relative_to(ROOT)).replace('\\','/'),'source_sha256':hashlib.sha256(data).hexdigest(),
  'file':dest.name,'sha256':hashlib.sha256(result).hexdigest(),'bytes':len(result),'faststart':True,'video_audio_reencoded':False,
  'media_payload_identical':True,'patched_chunk_offsets':chunks,'full_decode_ok':True,'duration':90,'frames':2160,
  'atoms':[{'kind':k.decode('ascii'),'offset':p,'bytes':s} for p,s,k,h in newtop]}
 (OUT/'provenance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in report.items() if k not in ['source','source_sha256','sha256']}),flush=True)

if __name__=='__main__':main()
