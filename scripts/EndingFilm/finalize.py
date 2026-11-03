from pathlib import Path
import subprocess,json,sys
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'assets/video/emergence_90s';AUDIO=ROOT/'assets/audio/emergence_90s'
FF=r'C:\Users\admin\Downloads\vocaloid-style-mv-pipeline\vendor\ffmpeg\ffmpeg.exe'
PROBE=r'C:\Users\admin\Downloads\vocaloid-style-mv-pipeline\vendor\ffmpeg\ffprobe.exe'
suffix='_smooth_v2' if '--smooth-v2' in sys.argv else ''
clean=f'ending_emergence_clean{suffix}.mp4'
bilingual=f'ending_emergence_bilingual{suffix}.mp4'
def run(args, output=None):
    command=[FF,'-y','-v','warning']+args
    if output is None: return subprocess.run(command,check=True,cwd=OUT)
    with open(output,'wb') as dst:
        p=subprocess.Popen(command,stdout=dst,stderr=subprocess.PIPE,cwd=OUT)
        err=p.stderr.read().decode('utf-8','replace'); code=p.wait()
    if code: raise RuntimeError('FFmpeg failed: '+err[-2000:])
lst=''.join(f"file 'part_{i}.mp4'\n" for i in range(4));(OUT/'concat.txt').write_text(lst)
run(['-f','concat','-safe','0','-i','concat.txt','-i',str(AUDIO/'mix.wav'),'-map','0:v:0','-map','1:a:0',
     '-c:v','copy','-c:a','aac','-b:a','256k','-t','90','-movflags','frag_keyframe+empty_moov','-f','mp4','pipe:1'],OUT/clean)
data=json.loads((OUT/'timeline.json').read_text(encoding='utf-8'))
voice=json.loads((AUDIO/'audio_report.json').read_text())['narration']
# Keep drafted semantic split points but constrain cues to actual spoken windows.
group=[[0,1],[2],[3,4,5],[6],[7],[8],[9],[10],[11,12],[13,14]]
for line,ids in zip(voice,group):
    oldstart=data['subtitles'][ids[0]]['start'];oldend=data['subtitles'][ids[-1]]['end']
    for i in ids:
        c=data['subtitles'][i];c['start']=line['start']+(c['start']-oldstart)/(oldend-oldstart)*(line['end']-line['start'])
        c['end']=line['start']+(c['end']-oldstart)/(oldend-oldstart)*(line['end']-line['start']);c['timing_status']='aligned_to_rendered_SAPI_sentence'
(OUT/'timeline.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def stamp(t,ass=False):
    if ass:return f'{int(t//3600)}:{int(t//60)%60:02}:{int(t)%60:02}.{int(t*100)%100:02}'
    ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
ass='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ZH,Microsoft YaHei,38,&H00151513,&H00151513,&H00ECF2F4,&H10ECF2F4,0,0,0,0,100,100,0,0,3,10,0,2,96,96,102,1
Style: EN,Georgia,27,&H00151513,&H00151513,&H00ECF2F4,&H10ECF2F4,0,0,0,0,100,100,0,0,3,10,0,2,96,96,56,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
srt=''
for idx,c in enumerate(data['subtitles'],1):
    for style,text in [('ZH',c['zh']),('EN',c['en'])]:ass+=f"Dialogue: 0,{stamp(c['start'],True)},{stamp(c['end'],True)},{style},,0,0,0,,{text}\n"
    srt+=f"{idx}\n{stamp(c['start'])} --> {stamp(c['end'])}\n{c['zh']}\n{c['en']}\n\n"
(OUT/'subtitles.ass').write_text(ass,encoding='utf-8');(OUT/'ending_emergence_zh_en.srt').write_text(srt,encoding='utf-8')
run(['-i',clean,'-vf','ass=subtitles.ass','-c:v','libx264','-threads','4','-preset','fast',
     '-crf','18','-pix_fmt','yuv420p','-r','24','-frames:v','2160','-c:a','copy','-avoid_negative_ts','make_zero','-movflags','frag_keyframe+empty_moov','-f','mp4','pipe:1'],OUT/bilingual)
reports={}
for name in [clean,bilingual]:
    report=json.loads(subprocess.check_output([PROBE,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(OUT/name)]))
    vid=next(s for s in report['streams'] if s['codec_type']=='video')
    assert vid['nb_read_frames']=='2160',vid
    assert vid['r_frame_rate']=='24/1',vid
    assert abs(float(vid['duration'])-90)<.05,report
    reports[name]=report
(OUT/f'verification{suffix}.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
print('VERIFIED: two 90-second 1080p videos, 24fps, 2160 frames each')
