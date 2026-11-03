"""Create composition references, a portable handoff, contact sheet and ZIP."""
from pathlib import Path
import json, math, shutil, zipfile
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets/image/emergence_art_pack'
manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
# Rebuilding the package must replace the eight composition records, not append duplicates.
manifest['assets']=[a for a in manifest['assets'] if not a['id'].startswith('composition/')]
IVORY=(244,242,236,255)
font_path=Path('C:/Windows/Fonts/arial.ttf')
font=ImageFont.truetype(str(font_path),20)
small=ImageFont.truetype(str(font_path),15)

def asset(name): return Image.open(OUT/(name+'.png')).convert('RGBA')
def frame(): return Image.new('RGBA',(1920,1080),IVORY)
def paste(im,name,box,rotation=0):
    obj=asset(name); obj.thumbnail((box[2],box[3]),Image.Resampling.LANCZOS)
    if rotation: obj=obj.rotate(rotation,resample=Image.Resampling.BICUBIC,expand=True)
    im.alpha_composite(obj,(int(box[0]),int(box[1])))

refs=OUT/'composition'; refs.mkdir(exist_ok=True)
frames=[]
im=frame(); tissue=asset('micro/tissue').resize((1600,1200),Image.Resampling.LANCZOS)
im.alpha_composite(tissue,(160,-170)); frames.append(im)
im=frame(); paste(im,'bird/bird_a_level',(610,160,1024,640))
window=asset('bird/chest_mask'); texture=asset('micro/tissue').resize(window.size)
# Pale tissue visible within a registered chest opening, for staging only.
patch=Image.new('RGBA',window.size,(244,242,236,0)); patch.putalpha(window.getchannel('A'))
patch.alpha_composite(texture)
patch.putalpha(window.getchannel('A')); im.alpha_composite(patch,(610,160)); frames.append(im)
im=frame()
for n in range(25):
    x=120+n*63; y=165+25*math.sin(n*.42)
    paste(im,'bird/bird_a_'+['up','level','down'][n%3],(x,y,70,44))
for n in range(72):
    row=n//18; col=n%18
    x=245+col*70+row*30; y=460+row*58+42*math.sin(col*.31+row*.55)
    paste(im,'bird/bird_a_'+['down','up','level'][n%3],(x,y,95,60))
paste(im,'bird/bird_a_level',(1190,724,125,78)); frames.append(im)
im=frame()
for n in range(48):
    row=n//16; col=n%16
    paste(im,'bird/bird_a_'+['up','level','down'][n%3],(490+col*71+row*18,185+row*61+32*math.sin(col*.35),85,53))
paste(im,'bird/bird_a_slack',(1120,590,280,175),-43); frames.append(im)
im=frame(); paste(im,'bird/bird_a_slack',(1000,330,210,131),-65)
paste(im,'city/roofline_transition',(-120,650,2240,473))
paste(im,'cloud/cloud_band_01',(-80,330,2200,550)); frames.append(im)
im=asset('city/intersection_reference')
# Convert WORLD positions with the reference's exact camera transform.
def worldpos(x,y): return x*2.2-2432,y*2.2-2019
x,y=worldpos(1410,1235); paste(im,'actors/car_topdown',(x-80,y-46,160,92))
x,y=worldpos(1475,1190); paste(im,'actors/pedestrian_walk_01',(x-20,y-46,40,64))
for px,py in [(1760,1080),(1785,1080)]:
    x,y=worldpos(px,py); paste(im,'actors/pedestrian_walk_02',(x-18,y-40,36,58))
frames.append(im)
im=frame(); earth=asset('earth/earth_reference').resize((540,540),Image.Resampling.LANCZOS)
im.alpha_composite(earth,(690,210)); frames.append(im)
frames.append(im.copy())
for idx,im in enumerate(frames,1):
    name=f'composition/S{idx:02}_layout'
    im.convert('RGB').save(OUT/(name+'.png'))
    manifest['assets'].append(dict(id=name,png=name+'.png',width=1920,height=1080,
        shots=[f'S{idx:02}'],purpose='构图参考静帧，非最终视频；不要把此图当分层动画素材',origin='composite of supplied artwork'))

sheet=Image.new('RGB',(1440,1780),(233,231,224)); sd=ImageDraw.Draw(sheet)
titles=['S01 MICRO / after black','S02 HOST REVEAL','S03 TWO FLOCKS','S04 ONE GAP','S05 CLOUD / CITY','S06 INTERSECTION','S07 EARTH','S08 HOLD / title in post']
for idx,im in enumerate(frames):
    x=(idx%2)*720; y=(idx//2)*445
    sd.text((x+24,y+18),titles[idx],font=font,fill=(16,16,16))
    thumb=im.convert('RGB').resize((672,378),Image.Resampling.LANCZOS)
    sheet.paste(thumb,(x+24,y+52))
sheet.save(OUT/'storyboard_contact_sheet.jpg',quality=94)

assets=[a for a in manifest['assets'] if not a['id'].startswith('composition/')]
grid=Image.new('RGB',(1680,((len(assets)+3)//4)*270),(233,231,224)); gd=ImageDraw.Draw(grid)
for idx,item in enumerate(assets):
    x=(idx%4)*420; y=(idx//4)*270
    gd.rectangle((x+10,y+10,x+410,y+260),fill=(244,242,236))
    gd.text((x+20,y+20),item['id'],font=small,fill=(16,16,16))
    obj=Image.open(OUT/item['png']).convert('RGBA'); obj.thumbnail((370,190),Image.Resampling.LANCZOS)
    grid.paste(obj,(x+20+(370-obj.width)//2,y+55+(190-obj.height)//2),obj)
grid.save(OUT/'asset_contact_sheet.jpg',quality=94)

# A self-contained production brief replaces the obsolete remote-tool workflow.
brief='''# 《涌现》美术素材与 Opus 整合交接

## 已确认制作方向

90 秒，1920×1080，24fps，暖白／黑／浅灰剪影动画。Opus 无需访问原项目；本目录是完整离线素材包。用户没有视频生成工具；使用提供的分层图片和 SVG，由代码或剪辑合成实现运动。

用户已确认：《主要剧本.md》优先，旧 prompt、旧故事板、旧素材清单不作执行依据；允许按需重做图片。开场直接从黑屏播放动画，不使用游戏录屏。源剧本中“真实本局画面”的要求因此被本交接补充覆盖，其他叙事、时间与旁白保持。

## 开场与声音补充

S01 0–6 秒：0–0.8 秒黑屏；0.8–2 秒淡入抽象微观纹理；2–6 秒缓慢拉远，为鸟胸腔揭晓作准备。它是艺术化开篇，不是本局游戏画面。S02 仍在约 13 秒清晰揭晓鸟形；S03 18–34 秒；S04 34–45 秒；S05 45–59 秒；S06 59–76 秒；S07 76–87 秒；S08 87–90 秒。全片准确 2160 帧。

本包提供视觉美术、逐镜导演执行单、配乐制作要求、字幕规则及暂定双语/单语字幕文件，目前没有实际配音、BGM 或环境声音频。Opus 应在动画预演后继续制作原创配乐；有代码执行能力时，可用 Web Audio OfflineAudioContext 或 Python 合成管风琴式音色、低音、弦乐式铺底与音型并导出 WAV。合成音色的真实感取决于可用音源；不能把制作说明称为已生成音频。正式英语人声仍须试听后由用户选择。第一段英文共 12 词，以 110 词/分钟约需 6.55 秒，原 10–16 秒窗口偏紧；初排 9.5–16.5 秒，之后按真实声音调整。

## 执行文档与阅读顺序（本次新增）

1. `01_逐镜导演执行单.md`：S01–S08 的景别、构图、逐段动作、相机速度、剪接方式和验收点。
2. `02_音乐与声音制作要求.md`：原创配乐、绝对时间节点、代码合成路径、分轨、同步和音频交付。
3. `03_字幕与旁白执行说明.md`：完整双语台词、拆屏规则、排版、暂定时间和正式配音校时。
4. `timeline.json`：24fps 镜头帧范围、声音节点与字幕数据；所有模块共用同一时间轴。
5. `subtitles/`：暂定双语、中文、英文 SRT，以及网页预览用双语 WebVTT。
6. `导演剧本_原文.md`：原始叙事与详细创作依据，保留原文便于核对。

新文档只展开执行方法；用户确认的黑屏开场、无视频生成服务及现有单张地球的使用限制优先于原文。不得误用旧版 70 秒 prompt。

## 素材结构

- `manifest.json`：全部 34 件素材的尺寸、用途、来源、适用镜头和文件路径。
- `layout.json`：鸟的轴心、胸腔窗口、城市坐标、角色运动路径与字幕安全区域。
- `background/`：暖白底色、可选纸纹。
- `bird/`：4 个统一画布姿态（up/level/down/slack）与胸腔遮罩；SVG 包含 body、near_wing、far_wing 图层。
- `micro/`：透明抽象组织纹理。
- `cloud/`：3 条透明浅灰云带。
- `city/`：道路、建筑、浅灰远景、完整城市、同布局路口近景参考、屋顶转场层。
- `actors/`：2 个行人步行姿态与俯视汽车。
- `earth/`：透明外背景地球与纯黑底盘。
- `reference/`：从用户鸟形图提取的 4 个原始姿态参考；只用于审美对照，画布和身体比例不同，不作动画序列。
- `composition/`：S01–S08 构图静帧；只供 staging 参考，不替代分层动画。

PNG 透明层与 SVG 含相同画布和尺寸；透明 PNG 是 RGBA，勿用全图去背景，否则会误删车窗、建筑白色屋顶与地球大陆。纸纹 PNG 是极弱透明叠层，不可每帧重采样随机噪声。

## 统一参考与动画规则

鸟默认朝右，画布 1024×640，身体轴心 (540,328)，胸腔中心 (595,330)，窗口半径 (62,40)。4 个正式姿态的身体路径完全相同，只有翅膀／死亡时松弛脚部不同。飞行序列 up→level→down→level；若用 SVG 可围绕翼根连续变形或插值，避免硬切的闪烁。原参考图身体被清理重绘为一致矢量设计，形状仍以小型、短嘴、紧凑剪影为依据；此为本包正式 BIRD_A。

S02 用同一个父级变换管理鸟与胸腔遮罩，纹理必须始终对齐胸腔。图形主体先揭晓，再关闭窗口。主角位置追踪到近群下缘；群体之间留清楚空隙。群体不能同步振翅。可用程序化 Boids 或预设邻域响应运动；只有实际实现局部规则时才称为算法演示。S04 约 36 秒后只用 slack 姿态和被动运动，不能再次主动振翅。

S05 云带实际有透明边缘，仅叠一条未必完全遮挡。换城市前必须用多个云带叠加并缩放，使遮挡区域覆盖全画面，或以同色云遮罩填满至少 6–12 帧，再换场景。屋顶侧影与俯视城市是两种图形视角，通过云遮挡切换，不宣称这两张图是精确的物理相机连拍。

城市主图 3200×2400，主路口世界坐标 (1600,1200)，道路、建筑、活动角色共享坐标与父级相机变换。`intersection_reference` 使用同一主图的变换 `translate(-2432,-2019) scale(2.2)`，不要把两个图片随意叠化。路口中心在近景约 (1088,621)。运动路径只是图形编排参考；车辆让行、行人跨过对应斑马线，两人会合后同行，车辆沿道路转弯。59–63 秒具体动作；63–76 秒平稳升高。人物为图形化站立剪影，适合小尺寸演示，追求严格俯视时可用点状符号替代。

地球来自用户参考中心区域，黑色海洋、暖白大陆，外部透明。现有单张地球无法表示连续不同经度的真实自转。可轻微整体旋转／保持静止；若坚持自转，应另外实现球面贴图，不可拉扯大陆伪装旋转。城市缩小到追踪锚点后，以分层遮罩揭示地球，禁止建筑融化。地球最后直径约 540px。标题后期排版，英文 EMERGENCE 在上，中文 涌现 在下，置于地球下方；不能写入地球美术图。

所有关键主体应高于屏幕 y=918；底部 15% 是字幕区。SVG 内置颜色目标 #F4F2EC / #101010 / #C8C5BD。纸纹很弱；剪影必须保持锐利稳定。

## 交付与检查

先给出可运行、可播放的 90 秒时间轴动画。可选 HTML Canvas/SVG（附全部资源和本地打开说明）、Remotion 或 Python/FFmpeg。按实际环境选择，不假设已安装依赖；纯 HTML 应包含运行方式、资源加载失败提示，以及 ZIP 解压后相对路径处理。网页存在逐帧 seek、播放/暂停和 S01–S08 跳转有助于验收。

最终 MP4 若具备编码环境，应为 90 秒、24fps、1920×1080；提供复现渲染命令。若环境无法编码，交付可播放动画与渲染源代码，并明确说明 MP4 未产出。无字幕版、双语字幕版与字幕文件按具备的声音素材分别交付；没有真实配音时字幕时码只能标为暂定。

逐镜实际观看：主角一致，13 秒宿主揭晓，36 秒死亡后不复活，云转场没有裸露换图，城市几何稳定，81 秒地球揭晓，87–90 秒标题留白。检查边缘、透明度、字幕安全区和资产加载。构图参考、缩略图、素材文件数量均不能替代动画验收。

本包不包含原参考整图及其水印文字；只提取鸟轮廓与地球中心图案。所有程序化 SVG 保留可编辑几何。关于已有参考图的授权与成片使用范围，沿用用户对其原素材的授权；本包未新增任何第三方声音素材。
'''
(OUT/'README_先读我.md').write_text(brief,encoding='utf-8')
shutil.copyfile(ROOT/'视频/主要剧本.md',OUT/'导演剧本_原文.md')
prompt='''你要根据我上传的《涌现_Opus美术素材包》制作 90 秒结局剪影动画。

你不能访问我的原项目，也没有视频生成服务。使用附件里的 SVG、透明 PNG、manifest.json 和 layout.json，以代码或剪辑合成完成动画。不要调用不存在的工具，不要用静帧轮播代替动画。

先完整阅读 README_先读我.md，再读 导演剧本_原文.md，实际查看 storyboard_contact_sheet.jpg、asset_contact_sheet.jpg 和关键单独素材。README 中用户确认的开场改动优先：从黑屏进入抽象微观纹理，不需要游戏录屏；其余镜头、情绪、英文旁白和时间遵循导演剧本。

请先检查你的附件读取、代码执行、动画预览与视频编码能力，并选择能实际完成的实现路径。若能读取 ZIP 就先解压，用相对路径加载；若不能读取 ZIP，一次说明要补传哪些文件。若 SVG/PNG 丢失，请明确指出，不能凭文件名声称已经看过。

将鸟、胸腔遮罩、组织纹理、两群鸟、云层、城市层、行人车辆、地球放到连续时间轴上：S01 0–6、S02 6–18、S03 18–34、S04 34–45、S05 45–59、S06 59–76、S07 76–87、S08 87–90。1920×1080、24fps、2160 帧。

BIRD_A 飞行朝右，身体与胸腔统一父级变换；两群鸟空间分离、异步振翅与局部转向；同一个主角在近群下缘于约 36 秒失去主动飞行。云层彻底遮挡时切入城市。城市近景与拉远共享同一主图坐标，行人车辆是独立运动层；最后城市锚点通过遮罩连接到地球。单张地球只能轻微整体转动或保持，不伪造真实自转。约 13 秒和 81 秒的揭晓必须清晰，底部 15% 留字幕区。标题使用后期稳定排版。

先完成真正可播放的完整无声动画，提供播放/暂停、逐帧或时间 seek、镜头跳转；默认优先无需视频模型的 HTML Canvas/SVG 或你环境可执行的渲染方案。说明如何运行并实际检查关键时间帧。美术图只能当图层，不得把 8 张参考图交叉淡入淡出就称为成片。

本包没有配音、音乐、环境声。保留独立音轨插槽与旁白/字幕配置；需要我补充声音时集中列出。配音音色须先试听再由我选，未经我确认不要改旁白。无配音时字幕时码标为暂定，不能声称双语有声成片已完成。

如果你的环境能编码，交付 90 秒 MP4、完整源工程与复现渲染命令；不能编码则交付可播放动画、全部引用资源与渲染脚本，准确说明缺失能力。只有实际生成的文件才能称为交付。先简短列出实现方案和素材缺口，然后开始完成已能执行的工作。
'''
(OUT/'给Opus的整合指令.txt').write_text(prompt,encoding='utf-8')
(ROOT/'视频/给Opus的整合指令.txt').write_text(prompt,encoding='utf-8')
from emergence_handoff import write_handoff
write_handoff(ROOT, OUT)
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')

# Validate every listed deliverable before packaging.
for item in manifest['assets']:
    for field in ['png','svg']:
        if field in item and not (OUT/item[field]).is_file(): raise FileNotFoundError(item[field])
    with Image.open(OUT/item['png']) as obj:
        if obj.size != (item['width'],item['height']): raise ValueError(item['id'])
        if obj.mode=='RGBA' and not obj.getchannel('A').getbbox(): raise ValueError('Empty alpha: '+item['id'])
zip_path=ROOT/'视频/涌现_Opus美术素材包.zip'
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as archive:
    for p in sorted(OUT.rglob('*')):
        if p.is_file(): archive.write(p,Path('涌现_Opus美术素材包')/p.relative_to(OUT))
print(json.dumps({'assets':len(manifest['assets']),'files':len(list(OUT.rglob('*.*'))),'zip_bytes':zip_path.stat().st_size}))
