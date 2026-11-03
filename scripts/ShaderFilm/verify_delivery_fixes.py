"""Verify the deployed film and record the two requested fixes with decoded frames."""
from pathlib import Path
import hashlib,json,subprocess,io,os
from datetime import datetime
from PIL import Image,ImageDraw
import numpy as np
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'assets/video/emergence_final90'
DEST=ROOT/'validation/ending-film-revision5-20261017';DEST.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
film=json.loads((OUT/'verification.json').read_text('utf-8'))
game=json.loads((ROOT/'assets/video/ending/provenance.json').read_text('utf-8'))
assert film['revision']==game['film_revision']==5
assert game['media_payload_identical'] and game['full_decode_ok']
assert sha(ROOT/'assets/video/ending/emergence90.mp4')==game['sha256']
assert sha(OUT/'涌现_90秒_云层与声音修正版.mp4')==game['source_sha256']
assert game['sha256']!=sha(OUT/'archive_v4/game_ending/emergence90.mp4')
assert 'video/ending/emergence90.mp4' in (ROOT/'scripts/Core/Config.lua').read_text('utf-8')
ff=os.environ.get('SHADER_FFMPEG','C:/Users/admin/Downloads/vocaloid-style-mv-pipeline/vendor/ffmpeg/ffmpeg.exe')
sheet=Image.new('RGB',(1920,760),(24,25,28));draw=ImageDraw.Draw(sheet)
edges=[]
for row,source in enumerate([OUT/'archive_v4/涌现_90秒_双语字幕.mp4',OUT/'涌现_90秒_双语字幕.mp4']):
 for col,time in enumerate([60.75,61,61.125]):
  data=subprocess.check_output([ff,'-v','error','-ss',str(time),'-i',str(source),'-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'])
  im=Image.open(io.BytesIO(data)).convert('RGB')
  if row==1:(OUT/'qa'/f'encoded_fix_{time:.3f}.png').write_bytes(data)
  sheet.paste(im.resize((640,360)),(col*640,row*380))
  draw.text((col*640+8,row*380+363),f'{"BEFORE" if row==0 else "AFTER"} {time:.3f}s',fill='white')
  if time==61:
   a=np.asarray(im).astype(float)
   edges.append(float(abs(a[:,695]-a[:,696]).mean()))
assert edges[1]<edges[0]*.35,edges
sheet.save(DEST/'cloud_fix_before_after.jpg',quality=94)
report={'revision':5,'timestamp':datetime.now().astimezone().isoformat(),
 'duration':90,'street_range':[46,60],'street_seconds':14,
 'runtime_replaced':True,'runtime_sha256':game['sha256'],'source_sha256':game['source_sha256'],
 'media_payload_identical':True,'full_decode_ok':True,
 'cloud_fix':film['street_exit_cloud_fix'],'former_edge_at_x696_mean_pixel_jump_before_after':edges,
 'audio_fix':film['street_audio_fix'],'preserved':film['approved_materials_preserved'],
 'preview_state':'stopped','preview_restarted':False,'native_playback_exercised':False,
 'unchanged_game_logic_regression':'validation/ending-film-revision4-20261017/regression.json',
 'previous_backup':'assets/video/emergence_final90/archive_v4/'}
(DEST/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report),flush=True)
