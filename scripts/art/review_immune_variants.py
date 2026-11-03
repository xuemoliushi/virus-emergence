"""Audit supplied immune images and produce a game-scale offline proof."""
from pathlib import Path
import hashlib
import json

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'validation/immune-variants-20261011'
NAMES = ('macrophage_master01.png.png', 'macrophage_master02.png.png',
         'macrophage_master03.png.png', 't_cell_master02.png.png', 't_cell_master03.png.png')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    records = {}
    images = []
    for name in NAMES:
        path = ROOT / 'assets/image' / name
        img = Image.open(path).convert('RGBA')
        bounds = img.getchannel('A').getbbox()
        assert bounds and img.getchannel('A').getextrema() == (0, 255)
        fill = max(bounds[2]-bounds[0], bounds[3]-bounds[1]) / max(img.size)
        records['image/' + name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                   'canvas': list(img.size), 'bounds': list(bounds), 'fill': fill}
        images.append(img)
    (OUT / 'sources.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    sheet = Image.new('RGB', (1250, 670), '#120e1e')
    draw = ImageDraw.Draw(sheet)
    font = lambda n: ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', n)
    draw.text((20, 16), '免疫细胞新素材 · 透明留白补偿检查', font=font(26), fill='#ece7f0')
    draw.text((20, 56), '离线合成，非实机截图｜各形态前景最大边统一｜保留素材原色', font=font(17), fill='#b9a9c4')
    for i, (name, image) in enumerate(zip(NAMES, images)):
        x = i*250
        label = '巨噬 ' + str(i+1) if i < 3 else 'T 细胞 ' + str(i-2)
        draw.text((x+16, 104), label, font=font(22), fill='#d5eaf1')
        for row, diameter in enumerate((80, 123, 184)):
            size = round(diameter / records['image/' + name]['fill'])
            sprite = image.convert('RGBa').resize((size, size), Image.Resampling.BILINEAR).convert('RGBA')
            sprite.putalpha(sprite.getchannel('A').point(lambda a: round(a*.96)))
            tile = Image.new('RGBA', (250, 210), '#120e1e')
            tile.alpha_composite(sprite, ((250-size)//2, (210-size)//2))
            sheet.paste(tile.convert('RGB'), (x, 140+row*170))
            draw.text((x+12, 144+row*170), f'{diameter}px', font=font(15), fill='#b9a9c4')
    sheet.save(OUT / 'proof.png')
    print(json.dumps({'images': len(images), 'output': str(OUT)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
