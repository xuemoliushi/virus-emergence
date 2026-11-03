"""Deterministic static material study. No runtime assets or game code are edited.

Run with a Python environment containing Pillow and NumPy:
    python -B scripts/art/review_fluorescent_membrane.py
"""
from pathlib import Path
import hashlib
import json
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'assets/image'
OUT = ROOT / 'validation/fluorescent-membrane-study-v2'
CANVAS = 1254
CENTER = 627
REFERENCE_DIAMETER = 760
SEED = 20261010
SIZES = (120, 80, 160)
VERSIONS = ('original', 'A', 'B', 'C')
LABELS = ('原版 · 当前素材', 'A · 局部亮颗粒', 'B · 颗粒＋断续亮纹', 'C · B＋局部柔光')
CAPTIONS = ('原始膜亮度', '保留原色，只增强四颗亮点', '三段膜纹理局部透亮', '亮部附近 1～3px 柔光')
BG = (14, 10, 25, 255)
FONT_PATH = Path('C:/Windows/Fonts/msyh.ttc')
PARAMETERS = {
    'seed': SEED, 'canvas': CANVAS, 'center': [CENTER, CENTER],
    'reference_membrane_diameter': REFERENCE_DIAMETER,
    'screen_diameters': list(SIZES), 'rotation_radians': 0,
    'body_alpha': .96, 'membrane_alpha': .96, 'vacuole_alpha': 1,
    'membrane_rgb_multiplier': 1.0,
    'segment_angles_radians': [.18, 2.15, 4.42],
    'segment_half_widths_radians': [.30, .34, .40],
    'coral_rgb': [255, 176, 190], 'coral_mix_max': .90,
    'particle_angles_radians': [.18, 2.15, 4.20, 4.62],
    'particle_rgb': [255, 234, 240], 'particle_source_radius': 12,
    'particle_mix_max': 1.0,
    'glow_rgb': [216, 65, 92], 'glow_sigma_at_120': 1.0,
    'glow_opacity_multiplier': .75, 'glow_max_extent_at_120': 3,
    'blend_policy': 'local channel-wise brighten only; no darkening; screen for glow',
    'tissue_alpha': .22, 'tissue_tile_width_meters': 8,
    'reference_cell_radius_meters': .4,
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot_runtime():
    return {p.relative_to(ROOT).as_posix(): digest(p)
            for p in sorted((ROOT / 'scripts').rglob('*.lua'))}


def load(name):
    return np.array(Image.open(SOURCE / name).convert('RGBA'))


def image(pixels):
    return Image.fromarray(np.uint8(np.clip(np.rint(pixels), 0, 255)))


def mask_image(mask):
    return Image.fromarray(np.uint8(np.clip(np.rint(mask * 255), 0, 255)))


def with_opacity(pixels, alpha):
    result = pixels.copy()
    result[:, :, 3] = np.rint(result[:, :, 3].astype(float) * alpha).astype('uint8')
    return Image.fromarray(result)


def resized(picture, width, resample=Image.Resampling.NEAREST):
    # Premultiply before resizing so invisible source RGB cannot bleed at edges.
    return picture.convert('RGBa').resize((width, width), resample).convert('RGBA')


def wrap(angle):
    return (angle + math.pi) % (2 * math.pi) - math.pi


def membrane_study(membrane, surface):
    rgb = membrane[:, :, :3].astype(float) / 255
    alpha = membrane[:, :, 3].astype(float) / 255
    luminance = rgb @ np.array([.2126, .7152, .0722])
    visible = alpha > .15
    low, high = np.quantile(luminance[visible], [.20, .94])
    detail = np.clip((luminance - low) / max(.001, high-low), 0, 1)
    yy, xx = np.mgrid[:CANVAS, :CANVAS]
    theta = np.arctan2(yy-CENTER, xx-CENTER)
    segments = np.zeros_like(alpha)
    for angle, width in zip(PARAMETERS['segment_angles_radians'],
                            PARAMETERS['segment_half_widths_radians']):
        distance = np.abs(wrap(theta-angle)) / width
        segments = np.maximum(segments, np.where(distance < 1,
                              (1 + np.cos(np.minimum(1, distance)*math.pi)) * .5, 0))
    rng = np.random.default_rng(SEED)
    low_frequency = image(rng.uniform(.50, 1, (24, 24))*255).resize(
        (CANVAS, CANVAS), Image.Resampling.BICUBIC)
    selection = segments * np.asarray(low_frequency).astype(float) / 255
    # Alpha first, texture second: invisible coloured pixels always contribute 0.
    bright_texture = alpha * detail
    stroke = bright_texture * selection

    particles = np.zeros_like(alpha)
    placements = surface['fine_placements']
    anchors = []
    for angle in PARAMETERS['particle_angles_radians']:
        index = round((angle % (2*math.pi)) / (2*math.pi) * len(placements)) % len(placements)
        px, py = placements[index][:2]
        px, py = round(CENTER+px), round(CENTER+py)
        left, top = px-20, py-20
        crop = bright_texture[top:py+21, left:px+21]
        cy, cx = np.unravel_index(np.argmax(crop), crop.shape)
        px, py = left+int(cx), top+int(cy)
        distance = np.sqrt((xx-px)**2 + (yy-py)**2)
        # Small faceted grains, using the membrane's existing alpha silhouette.
        point = np.clip(2*(1-distance/PARAMETERS['particle_source_radius']), 0, 1)
        point = np.sqrt(point) * alpha
        particles = np.maximum(particles, point)
        anchors.append([px, py])

    base = membrane[:, :, :3].astype(float)
    weight = (particles*PARAMETERS['particle_mix_max'])[:, :, None]
    # Preserve every base channel. Only the selected grains are raised in A.
    colored = base + np.maximum(0, np.array(PARAMETERS['particle_rgb'])-base)*weight
    a = membrane.copy()
    a[:, :, :3] = np.uint8(np.clip(np.rint(colored), 0, 255))
    weight = (stroke * PARAMETERS['coral_mix_max'])[:, :, None]
    coral = np.array(PARAMETERS['coral_rgb'])
    colored += np.maximum(0, coral-colored)*weight
    b = membrane.copy()
    b[:, :, :3] = np.uint8(np.clip(np.rint(colored), 0, 255))
    a[alpha == 0, :3] = 0
    b[alpha == 0, :3] = 0
    emission = np.maximum(stroke*.9, particles)
    assert np.max(emission[alpha == 0]) == 0
    for modified in (a, b):
        assert np.array_equal(modified[:, :, 3], membrane[:, :, 3])
        assert np.all(modified[visible, :3] >= membrane[visible, :3]), 'Base membrane darkened'
    assert len(anchors) == 4 and all(float(emission[y, x]) > .95 for x, y in anchors)
    angular_bin = np.floor((theta+math.pi)/(2*math.pi)*180).astype(int) % 180
    coverage = len(np.unique(angular_bin[emission > .04])) / 180
    assert coverage < .5, 'Emission must remain sparse, never form a complete ring'
    return a, b, emission, stroke, particles, anchors


def cell(body, membrane, vacuole):
    result = Image.alpha_composite(with_opacity(body, .96), with_opacity(membrane, .96))
    return Image.alpha_composite(result, Image.fromarray(vacuole))


def background(diameter, size=300):
    tile = Image.open(SOURCE / 'integrated/tissue_base_seamless.png').convert('RGBA')
    ppm = diameter / (2*PARAMETERS['reference_cell_radius_meters'])
    width = round(PARAMETERS['tissue_tile_width_meters']*ppm)
    tile = tile.resize((width, round(width*9/16)), Image.Resampling.BILINEAR)
    tile.putalpha(tile.getchannel('A').point(lambda a: round(a*PARAMETERS['tissue_alpha'])))
    result = Image.new('RGBA', (size, size), BG)
    # All versions share the same fixed world-centred background crop.
    result.alpha_composite(tile, (round(size/2-width*.52), round(size/2-tile.height*.54)))
    return result


def local_glow(emission, diameter):
    width = round(CANVAS*diameter/REFERENCE_DIAMETER)
    source = mask_image(emission).resize((width, width), Image.Resampling.NEAREST)
    pad = 8
    full = Image.new('L', (width+2*pad, width+2*pad))
    full.paste(source, (pad, pad))
    blurred = full.filter(ImageFilter.GaussianBlur(PARAMETERS['glow_sigma_at_120']*diameter/120))
    radius = math.ceil(PARAMETERS['glow_max_extent_at_120']*diameter/120)
    support = np.asarray(full.filter(ImageFilter.MaxFilter(2*radius+1))) > 0
    alpha = np.rint(np.asarray(blurred).astype(float)*PARAMETERS['glow_opacity_multiplier'])
    alpha[~support] = 0
    glow = np.zeros((width+2*pad, width+2*pad, 4), dtype='uint8')
    glow[:, :, :3] = PARAMETERS['glow_rgb']
    glow[:, :, 3] = np.uint8(alpha)
    glow[alpha == 0, :3] = 0
    return Image.fromarray(glow), pad


def panel(picture, emission, diameter, soft):
    result = background(diameter)
    width = round(CANVAS*diameter/REFERENCE_DIAMETER)
    origin = ((result.width-width)//2, (result.height-width)//2)
    if soft:
        glow, pad = local_glow(emission, diameter)
        overlay = Image.new('RGBA', result.size)
        overlay.alpha_composite(glow, (origin[0]-pad, origin[1]-pad))
        pixels = np.asarray(result).astype(float)
        light = np.asarray(overlay).astype(float)
        screen = 255-(255-pixels[:, :, :3])*(1-light[:, :, :3]/255)
        pixels[:, :, :3] += (screen-pixels[:, :, :3])*(light[:, :, 3:4]/255)
        result = image(pixels)
    result.alpha_composite(resized(picture, width), origin)
    return result


def font(size):
    if not FONT_PATH.exists():
        raise FileNotFoundError('Chinese proof labels require ' + str(FONT_PATH))
    return ImageFont.truetype(str(FONT_PATH), size)


def save_proofs(panels, anchors):
    sheet = Image.new('RGB', (1280, 1150), (19, 14, 30))
    draw = ImageDraw.Draw(sheet)
    draw.text((40, 20), '保留原图亮度 · 膜颗粒荧光对比', font=font(27), fill='#f3e5ea')
    draw.text((40, 62), '离线合成，非实机截图｜同一素材、背景、锚点与亮点位置｜液泡保持原色', font=font(17), fill='#b9a8bb')
    for column, (label, caption) in enumerate(zip(LABELS, CAPTIONS)):
        x = 40+300*column
        draw.text((x+12, 108), label, font=font(20), fill='#ffb7c8')
        draw.text((x+12, 139), caption, font=font(15), fill='#b9a8bb')
    for row, diameter in enumerate(SIZES):
        y = 185+310*row
        for column, version in enumerate(VERSIONS):
            x = 40+300*column
            sheet.paste(panels[(version, diameter)].convert('RGB'), (x, y))
            draw.text((x+12, y+12), f'{diameter}px' + (' · 主对比' if row == 0 else ''),
                      font=font(16), fill='#b9a8bb')
    draw.text((40, 1122), '建议先看 120px 行，再检查 80px 的可辨识度。A/B/C 均不使用全局 Bloom 或 HDR。',
              font=font(16), fill='#b9a8bb')
    sheet.save(OUT / 'comparison.png')

    # Fixed crop around one selected upper membrane grain; no auto contrast.
    width = round(CANVAS*120/REFERENCE_DIAMETER)
    ox = (300-width)//2
    px, py = anchors[-1]
    px, py = round(ox+px*width/CANVAS), round(ox+py*width/CANVAS)
    rect = (px-24, py-24, px+24, py+24)
    details = Image.new('RGB', (1280, 390), (19, 14, 30))
    draw = ImageDraw.Draw(details)
    draw.text((40, 18), '同一膜段局部｜上：原尺寸 48×48｜下：最近邻放大 4 倍', font=font(20), fill='#eedfe6')
    draw.text((40, 52), '离线合成，非实机截图；没有额外锐化或自动提亮', font=font(16), fill='#b9a8bb')
    for column, version in enumerate(VERSIONS):
        x = 40+300*column
        crop = panels[(version, 120)].crop(rect).convert('RGB')
        crop.save(OUT / f'{version}_detail_native.png')
        draw.text((x+12, 88), LABELS[column], font=font(18), fill='#ffb7c8')
        details.paste(crop, (x+12, 120))
        details.paste(crop.resize((192, 192), Image.Resampling.NEAREST), (x+12, 185))
    details.save(OUT / 'details.png')
    return list(rect)


def main():
    source_names = ('cell_body.png', 'cell_membrane.png', 'cell_vacuole.png',
                    'cell_surface_data.json', 'integrated/tissue_base_seamless.png')
    hashes = {name: digest(SOURCE/name) for name in source_names}
    runtime_before = snapshot_runtime()
    body, membrane, vacuole = [load(name) for name in source_names[:3]]
    assert all(p.shape == (CANVAS, CANVAS, 4) for p in (body, membrane, vacuole))
    surface = json.loads((SOURCE/'cell_surface_data.json').read_text(encoding='utf-8'))
    grain_membrane, stroke_membrane, emission, strokes, particles, anchors = membrane_study(membrane, surface)
    original = cell(body, membrane, vacuole)
    a = cell(body, grain_membrane, vacuole)
    b = cell(body, stroke_membrane, vacuole)
    assert np.array_equal(np.asarray(a)[vacuole[:, :, 3] > 0],
                          np.asarray(b)[vacuole[:, :, 3] > 0])
    assert np.array_equal(np.asarray(a)[:, :, 3], np.asarray(original)[:, :, 3])
    OUT.mkdir(parents=True, exist_ok=True)
    for name, mask in (('emission_mask', emission), ('stroke_mask', strokes),
                       ('particle_mask', particles)):
        mask_image(mask).save(OUT/f'{name}.png')
    panels = {}
    checks = []
    for diameter in SIZES:
        panels[('original', diameter)] = panel(original, emission, diameter, False)
        panels[('A', diameter)] = panel(a, emission, diameter, False)
        panels[('B', diameter)] = panel(b, emission, diameter, False)
        panels[('C', diameter)] = panel(b, emission, diameter, True)
        width = round(CANVAS*diameter/REFERENCE_DIAMETER)
        region = resized(Image.fromarray(vacuole), width).getchannel('A')
        protected = Image.new('L', (300, 300))
        protected.paste(region, ((300-width)//2, (300-width)//2))
        protected = np.asarray(protected) > 0
        pixels = {v: np.asarray(panels[(v, diameter)]) for v in VERSIONS}
        for version in VERSIONS:
            assert np.all(pixels[version][:, :, :3] >= pixels['original'][:, :, :3]), 'Output darkened'
            assert np.array_equal(pixels[version][protected], pixels['original'][protected]), 'Vacuole changed'
            assert np.array_equal(pixels[version][0], pixels['original'][0])
            assert np.array_equal(pixels[version][-1], pixels['original'][-1])
            panels[(version, diameter)].save(OUT / f'{version}_{diameter}.png')
        delta = np.max(np.abs(pixels['C'][:, :, :3].astype(int)-pixels['B'][:, :, :3].astype(int)), axis=2)
        grain_checks = []
        ox = (300-width)//2
        for x, y in anchors:
            sx, sy = ox+round(x*width/CANVAS), ox+round(y*width/CANVAS)
            warm_gain = pixels['A'][sy-1:sy+2, sx-1:sx+2, 1:3].astype(int) - pixels['original'][sy-1:sy+2, sx-1:sx+2, 1:3].astype(int)
            gain = int(warm_gain.max())
            assert gain > 10, 'A selected bright grain was lost at game scale'
            grain_checks.append(gain)
        checks.append({'diameter': diameter, 'vacuole_exact_match': True,
                       'no_pixel_darker_than_original': True,
                       'glow_changed_pixels': int((delta > 0).sum()),
                       'glow_max_channel_delta': int(delta.max()),
                       'four_grains_retained_warm_channel_gains': grain_checks,
                       'stroke_changed_pixels': int(np.any(pixels['B'] != pixels['A'], axis=2).sum())})
    crop = save_proofs(panels, anchors)
    assert hashes == {name: digest(SOURCE/name) for name in source_names}
    assert runtime_before == snapshot_runtime(), 'Runtime code/config must not change'
    report = {'scope': 'offline material study, not native GPU or gameplay acceptance',
              'parameters': PARAMETERS, 'source_sha256': hashes,
              'membrane_particle_anchors': anchors,
              'detail_crop_at_120': crop, 'checks': checks,
              'source_files_unchanged': True, 'runtime_files_unchanged': True,
              'transparent_rgb_excluded': True,
              'images_sha256': {p.name: digest(p) for p in sorted(OUT.glob('*.png'))}}
    (OUT/'parameters-and-checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(OUT), 'checks': checks, 'source_unchanged': True,
                      'runtime_unchanged': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
