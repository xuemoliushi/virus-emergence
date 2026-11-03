"""Package approved material renders while preserving existing gameplay anchors.

Run bake_bioluminescence.cjs first. This is deterministic UV/texture processing,
not a repaint; approved sources and legacy geometry remain untouched.
"""
from pathlib import Path
import hashlib
import json
import math
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / 'validation/bioluminescence-integration-20261015'
BAKE = REVIEW / 'bake'
OUT = ROOT / 'assets/image/bioluminescent'
SRC = ROOT / 'assets/image'
PREFIX = 'image/bioluminescent/'
NAMES = ['virus', 'macrophage', 'tcell-01', 'tcell-02', 'healthy']


def pixels(name):
    return np.asarray(Image.open(SRC / name).convert('RGBA'))


def save(name, data):
    a = np.uint8(np.clip(np.rint(data), 0, 255))
    if a.ndim == 3 and a.shape[2] == 4:
        a[a[:, :, 3] == 0, :3] = 0
    Image.fromarray(a).save(OUT / name)


def resized(im, size):
    return im.convert('RGBa').resize(size, Image.Resampling.LANCZOS).convert('RGBA')


def anchored_coordinates(source_alpha, target_alpha):
    """Keep the exact target silhouette and (627,627) attachment coordinates."""
    yy, xx = np.indices((1254, 1254))
    sb = Image.fromarray(np.uint8(source_alpha > 20)*255).getbbox()
    tb = Image.fromarray(np.uint8(target_alpha > 20)*255).getbbox()
    # A continuous affine registration avoids angular seams around protrusions.
    return (np.clip(sb[0]+(xx+.5-tb[0])*(sb[2]-sb[0])/(tb[2]-tb[0])-.5,0,511),
            np.clip(sb[1]+(yy+.5-tb[1])*(sb[3]-sb[1])/(tb[3]-tb[1])-.5,0,511))


def sample(a, x, y):
    ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x-ix)[:, :, None], (y-iy)[:, :, None]
    jx, jy = np.minimum(ix+1, a.shape[1]-1), np.minimum(iy+1, a.shape[0]-1)
    return a[iy, ix]*(1-fx)*(1-fy) + a[iy, jx]*fx*(1-fy) + a[jy, ix]*(1-fx)*fy + a[jy, jx]*fx*fy


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bases, emissions, fills = {}, {}, {}
    for name in NAMES:
        rendered = np.fromfile(BAKE / (name+'.f32'), dtype='<f4').reshape(512, 512, 4)[::-1].copy()
        alpha = np.clip(rendered[:, :, 3:4], 0, 1)
        c = np.divide(rendered[:, :, :3], alpha, out=np.zeros_like(rendered[:, :, :3]), where=alpha > .001)
        c /= 1 + np.maximum(c.max(axis=2, keepdims=True)-.6, 0)*.75
        rgba = np.concatenate([np.power(np.maximum(c, 0), 1/2.2), alpha], axis=2)*255
        bases[name] = rgba
        save(name+'.png', rgba)
        bb = Image.fromarray(np.uint8(alpha[:, :, 0] > .08)*255).getbbox()
        fills[name] = max(bb[2]-bb[0], bb[3]-bb[1])/512
        emissions[name] = [np.fromfile(BAKE/(name+'-emission-'+str(f)+'.rgba'), dtype=np.uint8)
                           .reshape(512, 512, 4)[::-1, :, :3].astype(float)/255 for f in range(4)]

    # CellSurface's precise union, latent positions, patches and attachment atlas
    # stay valid: every legacy layer retains its byte-for-byte original alpha.
    originals = [pixels(n) for n in ['cell_body.png', 'cell_membrane.png', 'cell_vacuole.png']]
    union = 1 - np.prod([1-a[:, :, 3].astype(float)/255 for a in originals], axis=0)
    mx, my = anchored_coordinates(bases['healthy'][:, :, 3], union*255)
    healthy = bases['healthy'].copy()
    # Extend only invisible edge RGB before registration. Original layer alpha
    # still supplies the exact contact silhouette, without black seam wedges.
    blurred = np.asarray(Image.fromarray(np.uint8(healthy)).convert('RGBa')
                         .filter(ImageFilter.GaussianBlur(24)).convert('RGBA')).astype(float)
    healthy[:, :, :3] = np.where((healthy[:, :, 3:4] > 20),healthy[:, :, :3],blurred[:, :, :3])
    healthy_rgb = sample(healthy[:, :, :3], mx, my)
    for name, original in zip(['cell_body.png', 'cell_membrane.png', 'cell_vacuole.png'], originals):
        save(name, np.dstack([healthy_rgb, original[:, :, 3]]))
    for name, src in [('cell_exhaustion.png', 'integrated/cell_exhaustion_no_vacuole.png'),
                      ('cell_death.png', 'cell_death_overlay.png')]:
        p = pixels(src)
        tint = healthy_rgb*np.array([.43, .30, .51])
        save(name, np.dstack([tint, p[:, :, 3]]))

    for size in [32, 96, 256, 512]:
        resized(Image.open(OUT/'virus.png'), (size, size)).save(OUT/f'virus_{size}.png')

    # Attached virus retains its exact existing 192px footprint/contact metadata.
    attached = pixels('virus_attached_particle.png')
    bb = Image.fromarray(attached[:, :, 3]).getbbox()
    virus = Image.fromarray(np.uint8(bases['virus']))
    vb = virus.getchannel('A').point(lambda x: 255 if x > 32 else 0).getbbox()
    fitted = virus.crop(vb).resize((bb[2]-bb[0], bb[3]-bb[1]), Image.Resampling.BILINEAR)
    rgb = Image.new('RGB', (192, 192)); rgb.paste(fitted.convert('RGB'), bb[:2])
    save('virus_attached.png', np.dstack([np.asarray(rgb), attached[:, :, 3]]))

    # One small shared atlas, 5 materials x 4 internal-light phases. No full-screen
    # target or per-object blur is allocated by the runtime.
    atlas = Image.new('RGBA', (640, 512))
    for col, name in enumerate(NAMES):
        for frame, e in enumerate(emissions[name]):
            if name == 'healthy':
                e = sample(e, mx, my)*union[:, :, None]
            s = np.power(np.maximum(e, 0), 1/2.2)
            peak = np.maximum(s.max(axis=2), .00001)
            rgb = s/peak[:, :, None]
            # Store energy in alpha; NVG_LIGHTER adds this premultiplied energy.
            glow = Image.fromarray(np.uint8(np.clip(np.dstack([rgb, peak*.42])*255, 0, 255)))
            glow = resized(glow, (128, 128)).filter(ImageFilter.GaussianBlur(1.15))
            atlas.paste(glow, (col*128, frame*128))
    atlas.save(OUT/'emission_atlas.png')

    # Approved background exposure, made periodic only at a narrow border.
    bg = np.asarray(Image.open(ROOT/'validation/unified-highlight-review-20261015/art/background.png')
                    .convert('RGB').resize((1280, 720), Image.Resampling.LANCZOS)).astype(float)/255
    yy, xx = np.indices((720, 1280)); p = np.stack([(xx+.5)/1280-.48, (yy+.5)/720-.43], axis=-1)
    fill = np.exp(-((p*np.array([1.2, 1]))**2).sum(axis=2)*3)
    bg = np.power(bg, 2.2)*.72*1.32 + np.array([.0012, .0017, .0028])*(.3+.7*fill[:, :, None])
    bg = np.power(bg, 1/2.2)*255
    for axis in [0, 1]:
        for i in range(48):
            w = .5*(1-i/48)**2
            a, b = [slice(None)]*3, [slice(None)]*3
            a[axis], b[axis] = i, bg.shape[axis]-1-i
            av, bv = bg[tuple(a)].copy(), bg[tuple(b)].copy()
            bg[tuple(a)] = av*(1-w)+bv*w; bg[tuple(b)] = bv*(1-w)+av*w
    save('background.png', bg)

    # Compact birth geometry uses the same frame centres and diameters; the new
    # virus is rendered directly, avoiding the 282 legacy membrane page loads.
    birth = json.loads((SRC/'integrated/manifest.json').read_text('utf8'))
    birth['pages'] = []; birth['material_mode'] = 'bioluminescent-sprites'
    (OUT/'budding_manifest.json').write_text(json.dumps(birth, separators=(',', ':')), 'utf8')
    approved = ROOT/'validation/unified-highlight-review-20261015/art'
    manifest = {'version': 1, 'source_review': 'unified-highlight-review-20261015',
                'material_bake': 'approved WebGL color at 1.5 seconds, moderate highlights; four emission phases',
                'geometry': 'original 1254 centre and exact layer alpha preserved; continuous affine UV registration',
                'fills': fills, 'glow_atlas': {'width': 640, 'height': 512, 'tile': 128, 'phases': 4},
                'sources': {n: hashlib.sha256((approved/(n+'.png')).read_bytes()).hexdigest() for n in NAMES},
                'files': {p.name: {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                          for p in OUT.glob('*') if p.is_file() and p.name != 'manifest.json'}}
    (OUT/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf8')
    (REVIEW/'pack-report.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf8')
    print('PACKAGED', len(manifest['files']), 'files; texture alpha and anchor geometry preserved')


if __name__ == '__main__':
    main()
