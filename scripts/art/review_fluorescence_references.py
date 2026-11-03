"""Prepare and assemble non-runtime AI material concepts, preserving source art."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

from PIL import Image, ImageDraw, ImageFont
import review_fluorescent_membrane as study

ROOT = study.ROOT
OUT = ROOT / 'validation/fluorescence-reference-concepts'
FONT = 'C:/Windows/Fonts/msyh.ttc'
REF_IDS = (
    '5abbdcfa-b24a-42f7-b218-76ec1c9ef4b1',
    'd90218ba-c925-446c-912a-ebcd27b75c6f',
    'cebaae5d-80a0-4494-88d2-8f7f5d01282d',
)


def hash_sources():
    paths = [ROOT / 'assets/image' / n for n in (
        'cell_body.png', 'cell_membrane.png', 'cell_vacuole.png',
        'integrated/tissue_base_seamless.png')]
    paths += sorted((ROOT / 'scripts').rglob('*.lua'))
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths}


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    for i, ref in enumerate(REF_IDS, 1):
        shutil.copy2(Path('C:/Users/admin/AppData/Local/Temp') / f'codex-clipboard-{ref}.png',
                     OUT / f'reference_{i}.png')
    body, membrane, vacuole = [study.load(n) for n in
                              ('cell_body.png', 'cell_membrane.png', 'cell_vacuole.png')]
    target = study.background(620, size=1024)
    width = round(study.CANVAS * 620 / study.REFERENCE_DIAMETER)
    target.alpha_composite(study.resized(study.cell(body, membrane, vacuole), width),
                           ((1024-width)//2, (1024-width)//2))
    target.save(OUT / 'original_reference.png')
    (OUT / 'source_hashes.json').write_text(json.dumps(hash_sources(), indent=2), encoding='utf-8')
    print(OUT / 'original_reference.png')


def assemble(paths):
    baseline = json.loads((OUT / 'source_hashes.json').read_text(encoding='utf-8'))
    assert baseline == hash_sources(), 'Source art or runtime code changed'
    labels = ('原版', 'A · 明亮像素颗粒', 'B · 半透明组织质感', 'C · 颗粒与透亮结合')[:len(paths)+1]
    images = [Image.open(OUT / 'original_reference.png').convert('RGB')]
    for letter, path in zip('ABC', paths):
        img = Image.open(path).convert('RGB')
        img.save(OUT / f'{letter}_concept.png')
        images.append(img)
    sheet = Image.new('RGB', (420*len(images), 790), '#130e1e')
    draw = ImageDraw.Draw(sheet)
    font = lambda n: ImageFont.truetype(FONT, n)
    draw.text((24, 18), '参考图驱动 · 荧光材质概念对比', font=font(28), fill='#f3e3ec')
    draw.text((24, 60), 'AI 静态概念，非实机截图｜保留红膜与暖粉液泡方向｜尚未接入游戏', font=font(18), fill='#b9a8bb')
    for i, (label, img) in enumerate(zip(labels, images)):
        x = i*420
        draw.text((x+16, 110), label, font=font(21), fill='#ffb7c8')
        sheet.paste(img.resize((420, 420), Image.Resampling.LANCZOS), (x, 150))
        # Whole 1024 plate scaled to original nominal membrane reference diameter.
        # AI silhouette can drift, so these are sampling checks, not exact measurements.
        for j, size in enumerate((80, 120, 160)):
            width = round(1024*size/620)
            sample = img.resize((width, width), Image.Resampling.LANCZOS)
            sample.save(OUT / f'{("original", "A", "B", "C")[i]}_nominal_{size}.png')
            crop = sample.crop(((width-size-14)//2, (width-size-14)//2,
                                (width+size+14)//2, (width+size+14)//2))
            # Cropped native-scale silhouettes share a baseline on the sampling strip.
            cx = x + (47, 170, 333)[j]
            sheet.paste(crop, (cx-crop.width//2, 599+(174-crop.height)))
            draw.text((cx-24, 578), str(size)+'px', font=font(14), fill='#b9a8bb')
    sheet.save(OUT / 'comparison.png')
    (OUT / 'README.md').write_text(
        '# 荧光材质参考概念\n\nMaker edit_image 按用户参考图生成，非实机截图。\n'
        'A：偏参考图 2 的明亮像素颗粒；B：偏参考图 3 的半透明组织膜。'
        'C 请求返回 INSUFFICIENT_BALANCE，无可用图片，不重试。参考图 1 用于远景亮部密度。\n\n'
        '保留红膜和暖粉液泡的配色方向，AI 概念不保证液泡像素或轮廓精确一致。'
        '原版由当前拆层原图合成。缩小行以原版 620px 膜直径为标尺，'
        '属于名义尺寸检查，生成图轮廓可能偏移。\n\n'
        '源图及运行时 Lua 哈希保持一致。游戏未引用这些概念图。'
        '完整生成提示见 prompts.json。\n', encoding='utf-8')
    print(OUT / 'comparison.png')


if __name__ == '__main__':
    prepare() if len(sys.argv) == 1 else assemble(sys.argv[1:])
