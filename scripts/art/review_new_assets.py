"""Offline source/atlas composites at game scale. These are not native GPU screenshots."""
from pathlib import Path
import json
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'assets/image'
OUT = ROOT / 'validation/new-art-integration'
META = json.loads((SRC / 'integrated/manifest.json').read_text(encoding='utf-8'))
SURFACE = json.loads((SRC / 'cell_surface_data.json').read_text(encoding='utf-8'))
ATLAS = json.loads((SRC / 'cell_surface_atlas/manifest.json').read_text(encoding='utf-8'))
PARTICLE = json.loads((SRC / 'virus_attached_meta.json').read_text(encoding='utf-8'))
LATENT = json.loads((SRC / 'latent_particles_meta.json').read_text(encoding='utf-8'))
FONT = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 17)
SMALL = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 13)
BG = (14, 10, 25, 255)


def source(name):
    return Image.open(SRC / name).convert('RGBA')


def opacity(image, alpha):
    image = image.copy()
    image.putalpha(image.getchannel('A').point(lambda a: round(a * alpha)))
    return image


def sprite(canvas, image, x, y, size, angle=0, alpha=1):
    image = opacity(image, alpha).convert('RGBa').resize((round(size), round(size)), Image.Resampling.NEAREST)
    image = image.rotate(-math.degrees(angle), resample=Image.Resampling.NEAREST, expand=True).convert('RGBA')
    canvas.alpha_composite(image, (round(x-image.width/2), round(y-image.height/2)))


def baked(tile, resolution):
    page, x, y, w, h, ox, oy = tile
    image = Image.new('RGBA', (resolution, resolution))
    if w and h:
        atlas = Image.open(ROOT / 'assets' / ATLAS['pages'][page-1]).convert('RGBA')
        image.paste(atlas.crop((x, y, x+w, y+h)), (ox, oy))
    return image


def infection(canvas, progress, alpha=0.96, attached=False):
    # Same quantized membrane point and patch transform as CellSurface:GetPlacement/PatchEntry.
    index = 1080
    px, py, nx, ny = SURFACE['fine_placements'][index]
    patch = SURFACE['patch']
    crop = patch['crop']
    anchor = patch['anchor']
    for layer_index, layer in enumerate(patch['stack']):
        p = min(1, max(0, progress*3-layer_index))
        if not p:
            continue
        scale = patch['max_scale'] * layer['scale']
        angle = math.atan2(nx, -ny) + math.radians(layer['rot'])
        co, si = math.cos(angle), math.sin(angle)
        ax, ay = crop[0]+crop[2]/2-anchor[0], crop[1]+crop[2]/2-anchor[1]
        x, y = 627+px+scale*(co*ax-si*ay), 627+py+scale*(si*ax+co*ay)
        image = baked(ATLAS['patches'][index][layer_index], patch['output_pixels'])
        if p < 1:
            bottom = anchor[1] + (patch['bounds'][3]-anchor[1])*math.sqrt(p)
            a = np.array(image)
            a[max(0, math.ceil(bottom-crop[1])):, :, 3] = 0
            image = Image.fromarray(a)
        sprite(canvas, image, x, y, crop[2]*scale, angle, alpha*math.sqrt(p))
    if attached:
        scale = SURFACE['foreground_diameter']*SURFACE['particle_fraction']/SURFACE['visible_particle_pixels']
        dx, dy = PARTICLE['outward']
        angle = math.atan2(dx*(-ny)-dy*(-nx), dx*(-nx)+dy*(-ny))
        off = (PARTICLE['r_rim']-8)*scale
        x, y = 627+px+nx*off, 627+py+ny*off
        sprite(canvas, baked(ATLAS['glints'][index], 192), x, y, 192*scale, angle, .9)
        sprite(canvas, source('virus_attached_particle.png'), x, y, 192*scale, angle, .9)


def cell(state='HEALTHY', tired=0, death=0, budding=None, pose_index=135, progress=1, rotation=0):
    smooth = lambda x: x*x*(3-2*x)
    tired = smooth(tired)
    fade = smooth(death)
    a = .96-.56*tired
    body = opacity(source('cell_body.png'), a*(1-fade)+.32*fade)
    membrane = opacity(source('cell_membrane.png'), a*(1-fade))
    if budding is not None:
        pose = META['poses'][pose_index]
        x, y, w, h = pose['rect']
        page, tx, ty = pose['frames'][budding]
        tile = Image.open(ROOT/'assets'/META['pages'][page-1]).convert('RGBA')
        tile = tile.crop((tx, ty, tx+256, ty+256)).resize((w, h), Image.Resampling.NEAREST)
        membrane.paste(opacity(tile, a), (x+627, y+627))
    canvas = Image.alpha_composite(body, membrane)
    if tired:
        canvas = Image.alpha_composite(canvas, opacity(source('integrated/cell_exhaustion_no_vacuole.png'), tired*(1-fade)))
    canvas = Image.alpha_composite(canvas, opacity(source('cell_vacuole.png'), 1-fade))
    if state == 'LATENT':
        for p in LATENT['particles']:
            image = source(p['sprite'])
            pulse = p['pulse']
            alpha = pulse['alpha_min'] + (LATENT['pulse']['alpha_range'][1]-pulse['alpha_min'])*.5
            sprite(canvas, image, *p['centre'], 50, alpha=alpha)
    if state not in ('HEALTHY', 'DEAD'):
        infection(canvas, progress, .96*a*(1-.7*tired), state=='EXPOSED')
    if fade:
        canvas = Image.alpha_composite(canvas, opacity(source('cell_death_overlay.png'), fade))
    return canvas.rotate(-math.degrees(rotation), resample=Image.Resampling.NEAREST)


def put_cell(sheet, image, x, y, ppm=128):
    size = round(.34*2*ppm*1254/760)
    image = image.convert('RGBa').resize((size, size), Image.Resampling.NEAREST).convert('RGBA')
    sheet.alpha_composite(image, (round(x-size/2), round(y-size/2)))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sheet = Image.new('RGBA', (1540, 510), BG)
    draw = ImageDraw.Draw(sheet)
    draw.text((22, 16), '病程素材核对 · 游戏尺寸离线合成', font=FONT, fill='white')
    draw.text((22, 46), '按实际资源、图集锚点与图层参数合成；不包含原生 GPU、UI 或实机游玩验收。', font=SMALL, fill='#aaa1ba')
    cases = [('健康', 'HEALTHY', 0, 0, None, 1), ('接触 / 暴露', 'EXPOSED', 0, 0, None, .38),
             ('潜伏', 'LATENT', 0, 0, None, 1), ('真实释放第六帧', 'PRODUCTIVE', 0, 0, 5, 1),
             ('耗竭 50%', 'EXHAUSTED', .5, 0, None, 1), ('耗竭 100%', 'EXHAUSTED', 1, 0, None, 1),
             ('死亡 0.35s 后', 'DEAD', 1, 1, None, 1)]
    for row, ppm in enumerate((128, 256)):
        y = 190+row*220
        draw.text((22, y-98), f'{ppm}px/m · 实体直径 {round(.68*ppm)}px', font=SMALL, fill='#b9aacd')
        for i, (label, state, tired, death, bud, progress) in enumerate(cases):
            x = 110+i*220
            put_cell(sheet, cell(state, tired, death, bud, progress=progress), x, y, ppm)
            draw.text((x-80, y+75 if row==0 else y+85), label, font=SMALL, fill='#e2d6ed')
    sheet.convert('RGB').save(OUT/'病程游戏尺寸_离线合成.png')
    frames = Image.new('RGBA', (1320, 850), BG)
    draw = ImageDraw.Draw(frames)
    draw.text((22, 16), '出芽六帧 / 真实膜轮廓适配 · 离线合成', font=FONT, fill='white')
    draw.text((22, 46), '六个源关键姿态之间补间，共25帧/0.8s；三排为不同局部锚点及旋转，实体直径174px。', font=SMALL, fill='#aaa1ba')
    for row, (pose, rotation) in enumerate(((135, 0), (0, .7), (45, -.4))):
        for f in range(6):
            x, y = 110+f*220, 190+row*250
            put_cell(frames, cell(budding=META['keyframe_indices'][f]-1, pose_index=pose, rotation=rotation), x, y, 256)
            key=META['keyframe_indices'][f]
            draw.text((x-75, y+105), f'F{f+1} · {(key-1)*.8/META["animation_frames"]:.3f}s', font=SMALL, fill='#e2d6ed')
    frames.convert('RGB').save(OUT/'出芽六帧_离线合成.png')
    entities = Image.new('RGBA', (1000, 350), BG)
    draw = ImageDraw.Draw(entities)
    draw.text((22, 16), '免疫母版及 F2_B 病毒 · 原色 / 有效前景尺寸补偿', font=FONT, fill='white')
    for i, (name, r, fill, label) in enumerate((('macrophage_master.png.png', .5, 965/1254, '巨噬细胞 · 128px'),
               ('t_cell_master.png.png', .3, 752/1254, 'T 细胞 · 77px'),
               ('integrated/virus_32.png', .045, .78, '病毒 · 12px'),
               ('integrated/virus_96.png', .045*4, .78, '病毒 4× · 46px'))):
        sprite(entities, source(name), 125+i*250, 180, 2*r*128/fill)
        draw.text((35+i*250, 285), label, font=SMALL, fill='#e2d6ed')
    entities.convert('RGB').save(OUT/'免疫与病毒_游戏尺寸.png')
    print('Wrote offline composites:', OUT)


if __name__ == '__main__':
    main()
