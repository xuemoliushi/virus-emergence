"""Install the user's accepted v2 shot into the existing 90-second renderer."""
from pathlib import Path
import shutil,json,hashlib

def install(root,out):
 root=Path(root);out=Path(out);accepted=root/'assets/video/city_earth_review_v2';art=out/'approved-art';art.mkdir(exist_ok=True)
 for name in ['city','earth','cloud']:shutil.copy2(accepted/(name+'.frag'),out/'shaders'/('approved-'+name+'.frag'))
 shutil.copy2(accepted/'camera-path.js',out/'approved-camera-path.js')
 for name in ['earth_topography_nasa.jpg','clouds_nasa.jpg']:shutil.copy2(root/'assets/video/earth_transition_review_v1/art'/name,art/name)
 shutil.copy2(root/'assets/video/emergence_shader/art/city.jpg',art/'city.jpg')
 engine=(out/'engine.js').read_text('utf-8')
 marker='// APPROVED_ASCENT_REVISION4' if '// APPROVED_ASCENT_REVISION4' in engine else '// Absolute-time camera.'
 start=engine.index(marker);end=engine.index('let subtitleLayout=',start)
 engine=engine[:start]+(root/'scripts/ShaderFilm/approved_ascent_final90.js').read_text('utf-8')+'\n'+engine[end:]
 if 'await approvedAscent.init();' not in engine:engine=engine.replace('await document.fonts.ready;','await approvedAscent.init();await document.fonts.ready;')
 old="bind(null);blend(false);use(programs.post);bindTex(scene.tex);\n uniforms(programs.post,{uTex:0,uResolution:[W,H],uTime:t,uBlur:12*(1-ramp(t,3.0,11.5)),uBlack:1-ramp(t,.65,2.1)});gl.drawArrays(gl.TRIANGLES,0,6);"
 new="bind(null);blend(false);bindTex(scene.tex);\n if(t>=60){use(programs.approvedPresent);uniforms(programs.approvedPresent,{uTex:0,uResolution:[W,H],uTime:t,uIntro:1-ramp(t,60,61.3)});}\n else{use(programs.post);uniforms(programs.post,{uTex:0,uResolution:[W,H],uTime:t,uBlur:12*(1-ramp(t,3.0,11.5)),uBlack:1-ramp(t,.65,2.1)});}\n gl.drawArrays(gl.TRIANGLES,0,6);"
 previous="bind(null);blend(false);bindTex(scene.tex);\n if(t>=60){use(programs.copy);uniforms(programs.copy,{uTex:0});}\n else{use(programs.post);uniforms(programs.post,{uTex:0,uResolution:[W,H],uTime:t,uBlur:12*(1-ramp(t,3.0,11.5)),uBlack:1-ramp(t,.65,2.1)});}\n gl.drawArrays(gl.TRIANGLES,0,6);"
 if previous in engine:engine=engine.replace(previous,new)
 if old in engine:engine=engine.replace(old,new)
 elif new not in engine:raise ValueError('Missing post-pass anchor')
 engine=engine.replace("fillText('E M E R G E N C E',960,877)","fillText('E M E R G E N C E',960,904)").replace("fillText('涌 现',960,925)","fillText('涌 现',960,952)")
 (out/'engine.js').write_text(engine,encoding='utf-8')
 # The upward street exit uses only procedural mist; retain the approved
 # downward entrance before the street, including its original cloud cards.
 engine=engine.replace('cloudBanks(t,fog,4.4+(t-43)*.35);cloud(t,fog,4.4+(t-43)*.35);',
  'if(t<59)cloudBanks(t,fog,4.4+(t-43)*.35);cloud(t,fog,4.4+(t-43)*.35);')
 (out/'engine.js').write_text(engine,encoding='utf-8')
 html=(out/'index.html').read_text('utf-8')
 if 'approved-camera-path.js' not in html:html=html.replace('<script src="engine.js">','<script src="approved-camera-path.js"></script><script src="engine.js">')
 (out/'index.html').write_text(html,encoding='utf-8')
 timeline=json.loads((out/'timeline.json').read_text('utf-8'));timeline['revision']=5
 timeline['shots']=[s for s in timeline['shots'] if s['end']<=60]+[{'start':a,'end':b,'shot':name} for a,b,name in [(60,63.5,'城市持续升高'),(63.5,65.45,'低空穿云'),(65.45,73,'无近景云的连续上升'),(73,87,'已认可的三维地球拉远'),(87,90,'同一地球定格与片名')]]
 timeline['transition_windows']={'cloud_emergence':[43,45.1],'full_frame_city_to_street':[44.35,46],'street_to_city_cloud_exit':[60,61.3],'low_altitude_cloud_crossing':[63.5,65.45],'continuous_ascent_camera':[60,87],'foreground_clouds_end':65.45}
 (out/'timeline.json').write_text(json.dumps(timeline,ensure_ascii=False,indent=2),encoding='utf-8')
 inputs=[accepted/n for n in ['camera-path.js','city.frag','earth.frag','cloud.frag','城市至地球_低空穿云_连续上升预览_v2.mp4']]
 manifest={'revision':5,'source':'assets/video/city_earth_review_v2','accepted_window':[60,87],'duration':90,'street_window':[46,60],
  'street_exit_cloud_cards':False,'street_exit_fog':'full-screen procedural only',
  'intro_boundary_cloud_exit':[60,61.3],'last_accepted_frame_held_from':87,'title_centers':[[960,904],[960,952]],'additional_grade_on_accepted_shot':False,
  'inputs':{str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}}
 (out/'accepted_ascent.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 print('Installed accepted city/Earth v2 into 60–87s; street and dialogue unchanged.',flush=True)

if __name__=='__main__':
 root=Path(__file__).resolve().parents[2];install(root,root/'assets/video/emergence_final90')
