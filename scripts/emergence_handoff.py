"""Package self-contained directing, score and caption instructions for Opus."""
from pathlib import Path
import json
import shutil

SUBTITLES = [
    (9.5,14,'在这只鸟的体内，一个看不见的世界正在改变。','Within this bird, an unseen world was changing.'),
    (14,16.5,'一场微小的感染扩散开来。','A small infection spread.'),
    (20,23,'每只鸟跟随着附近的同伴。','Each bird follows its neighbours.'),
    (23,25,'保持距离。','Keeping distance.'),
    (25,27,'一同转向。','Turning together.'),
    (27,29,'留在群体附近。','Staying close.'),
    (29,33.5,'秩序，从这些微小的行动中涌现。','From these small actions, order emerges.'),
    (36.5,41,'这只鸟死于急性肺炎。','This bird died of acute pneumonia.'),
    (41.5,45,'鸟群仍在继续飞行。','The flock continued its flight.'),
    (56,59,'在下方，另一个世界也在运行。','Below, another world moves.'),
    (60,65,'人们相遇、交换、合作与竞争。','People meet, exchange, cooperate, and compete.'),
    (66,70.5,'他们的生活彼此交织，','Their lives intertwine,'),
    (70.5,75,'形成任何一个人都无法独自创造的社会。','shaping a society no one person could create alone.'),
    (77,80,'世代之间，这些联系','Across generations, these connections'),
    (80,85.5,'逐渐形成城市、文化与文明。','grow into cities, cultures, and civilizations.'),
]

def stamp(seconds, separator=','):
    total = round(seconds * 1000)
    hours, total = divmod(total, 3600000)
    minutes, total = divmod(total, 60000)
    secs, millis = divmod(total, 1000)
    return f'{hours:02}:{minutes:02}:{secs:02}{separator}{millis:03}'

def write_handoff(root: Path, out: Path):
    source = root / '视频/制作交接文档'
    for name in ['01_逐镜导演执行单.md', '02_音乐与声音制作要求.md',
                 '03_字幕与旁白执行说明.md', '给Opus的整合指令.txt']:
        shutil.copyfile(source/name, out/name)
    shutil.copyfile(source/'给Opus的整合指令.txt', root/'视频/给Opus的整合指令.txt')

    subtitles=[]
    last_end = 0
    for i, (start, end, zh, en) in enumerate(SUBTITLES, 1):
        if not 0 <= last_end <= start < end <= 90:
            raise ValueError(f'Invalid subtitle {i}')
        subtitles.append(dict(id=i, start=start, end=end, start_frame=round(start*24),
                              end_frame=round(end*24), zh=zh, en=en,
                              timing_status='draft_pending_narration'))
        last_end = end

    ranges=[(0,6),(6,18),(18,34),(34,45),(45,59),(59,76),(76,87),(87,90)]
    names=['黑屏至微观','宿主揭晓','两群鸟','个体退出','云层至城市','路口至城市','城市至地球','地球与标题']
    cameras=['fade_from_black_then_dolly_out','dolly_out_then_track',
             'dolly_out_decelerate','hold_then_pan_down','pan_down_occlusion_cut',
             'hold_intersection_then_rise','dolly_out_graphic_mask_reveal','hold_title_fade']
    assets=[['background/ivory','micro/tissue'],
            ['bird/bird_a_up','bird/bird_a_level','bird/bird_a_down','bird/chest_mask','micro/tissue'],
            ['bird/bird_a_up','bird/bird_a_level','bird/bird_a_down'],
            ['bird/bird_a_slack','bird/bird_a_up','bird/bird_a_level','bird/bird_a_down'],
            ['bird/bird_a_slack','cloud/cloud_band_01','cloud/cloud_band_02','cloud/cloud_band_03','city/roofline_transition','city/city_roads','city/city_buildings'],
            ['city/city_roads','city/city_buildings','actors/car_topdown','actors/pedestrian_walk_01','actors/pedestrian_walk_02'],
            ['city/city_roads','city/city_buildings','earth/planet_disc','earth/earth_reference'],
            ['earth/earth_reference']]
    shots=[dict(id=f'S{i+1:02}',name=names[i],start=a,end=b,
                start_frame=a*24,end_frame=b*24,camera=cameras[i],assets=assets[i],
                directing_document='01_逐镜导演执行单.md',reference_png=f'composition/S{i+1:02}_layout.png')
           for i,(a,b) in enumerate(ranges)]
    cues=[
        dict(id='bass_enters',start=2,end=6,action='weak narrow-register bass'),
        dict(id='host_reveal',start=13.3,end=15,action='first harmonic expansion',trigger='0.3–0.5s after bird recognizable; target only'),
        dict(id='flock_build',start=18,end=34,action='motif and strings accumulate'),
        dict(id='death_gap',start=36,end=37,action='remove motif and most upper layers, retain low tail'),
        dict(id='sparse_fall',start=37,end=53,action='sparse music under narration and wind'),
        dict(id='restart',start=53,end=59,action='organ bass restarts'),
        dict(id='city_build',start=59,end=79.5,action='add motif and layers progressively'),
        dict(id='anticipation',start=79.5,end=80.5,action='thin texture'),
        dict(id='earth_release',start=81.3,end=85.5,action='widest harmonic release',trigger='0.3s after actual Earth recognition; target only'),
        dict(id='tail',start=85.5,end=90,action='motif stops, smooth resolving tail ending at 90'),
    ]
    timeline=dict(version=2,duration_seconds=90,fps=24,total_frames=2160,
        canvas=dict(width=1920,height=1080),interval_convention='[start,end)',
        frame_origin=0,time_origin='seconds from first black frame',
        authority='01_逐镜导演执行单.md; confirmed opening override in README',
        audio=dict(status='instructions_only_no_audio_files',sample_rate=48000,channels=2,
                   samples_per_channel=4320000,narration_status='not_recorded',
                   music_instructions='02_音乐与声音制作要求.md'),
        subtitles_status='draft_pending_narration',subtitle_instructions='03_字幕与旁白执行说明.md',
        shots=shots,music_cues=cues,subtitles=subtitles,
        title=dict(start=87,fade_end=88,end=90,en='EMERGENCE',zh='涌现',
                   center_x=960,en_baseline_y=817,zh_baseline_y=873,separate_from_subtitles=True))
    (out/'timeline.json').write_text(json.dumps(timeline,ensure_ascii=False,indent=2),encoding='utf-8')
    subdir=out/'subtitles'; subdir.mkdir(exist_ok=True)
    for lang in ['zh_en','zh','en']:
        blocks=[]
        for c in subtitles:
            lines=[c['zh'],c['en']] if lang=='zh_en' else [c[lang]]
            blocks.append(f"{c['id']}\n{stamp(c['start'])} --> {stamp(c['end'])}\n"+'\n'.join(lines))
        (subdir/f'ending_emergence_{lang}_draft.srt').write_text('\n\n'.join(blocks)+'\n',encoding='utf-8')
    blocks=['WEBVTT','NOTE Timing is draft; align to final English narration.']
    for c in subtitles:
        blocks.append(f"{c['id']}\n{stamp(c['start'],'.')} --> {stamp(c['end'],'.')}\n{c['zh']}\n{c['en']}")
    (subdir/'ending_emergence_zh_en_draft.vtt').write_text('\n\n'.join(blocks)+'\n',encoding='utf-8')

    # Validate the shared timing and artwork IDs before packaging.
    manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    ids={a['id'] for a in manifest['assets']}
    for shot in shots:
        if not set(shot['assets']).issubset(ids): raise ValueError('Missing shot asset: '+shot['id'])
    if sum(s['end_frame']-s['start_frame'] for s in shots)!=2160:
        raise ValueError('Shot duration mismatch')
