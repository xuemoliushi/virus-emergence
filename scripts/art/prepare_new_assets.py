"""Deterministic derivatives of approved art; original assets are never rewritten."""
from pathlib import Path
import hashlib
import json
import math

import numpy as np
from PIL import Image, ImageOps, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'assets/image'
OUT = SOURCE / 'integrated'
REVIEW = ROOT / 'validation/new-art-integration'


def rgba(name):
    return np.array(Image.open(SOURCE / name).convert('RGBA'))


def save(name, pixels):
    pixels = np.array(pixels, dtype=np.uint8, copy=True)
    pixels[pixels[:, :, 3] == 0, :3] = 0
    Image.fromarray(pixels).save(OUT / name)


def mix_rgba(a, b, t):
    """Premultiplied interpolation, keeping opaque membrane edges unchanged."""
    aa, ba = a[:, :, 3:4].astype(float)/255, b[:, :, 3:4].astype(float)/255
    alpha = aa*(1-t)+ba*t
    rgb = a[:, :, :3]*aa*(1-t)+b[:, :, :3]*ba*t
    rgb = np.divide(rgb, alpha, out=np.zeros_like(rgb), where=alpha>0)
    return np.uint8(np.rint(np.concatenate([rgb, alpha*255], 2)))


def aligned_bud(image, old_centre, old_diameter, centre, diameter):
    """Align the two source buds before mixing; avoid double ghost silhouettes."""
    yy, xx = np.indices(image.shape[:2])
    sx = np.floor(old_centre[0]+(xx+.5-centre[0])*old_diameter/diameter).astype(int)
    sy = np.floor(old_centre[1]+(yy+.5-centre[1])*old_diameter/diameter).astype(int)
    valid = (sx>=0)&(sx<image.shape[1])&(sy>=0)&(sy<image.shape[0])
    pixels = image[np.clip(sy,0,image.shape[0]-1), np.clip(sx,0,image.shape[1]-1)].copy()
    pixels[~valid] = 0
    return pixels


def bud_mask(image):
    """Largest warm connected foreground is the virus; pink membrane is excluded."""
    r, g, b, a = [image[:, :, i].astype(float) for i in range(4)]
    warm = (a > 16) & (r > g*1.05) & (g > b*1.6) & (g > 30)
    unseen = warm.copy()
    largest = []
    for y, x in zip(*np.where(warm)):
        if not unseen[y, x]:
            continue
        stack, component = [(int(y), int(x))], []
        unseen[y, x] = False
        while stack:
            cy, cx = stack.pop()
            component.append((cy, cx))
            for ny, nx in ((cy-1, cx), (cy+1, cx), (cy, cx-1), (cy, cx+1)):
                if 0 <= ny < image.shape[0] and 0 <= nx < image.shape[1] and unseen[ny, nx]:
                    unseen[ny, nx] = False
                    stack.append((ny, nx))
        if len(component) > len(largest):
            largest = component
    mask = np.zeros(warm.shape, dtype=np.uint8)
    yy, xx = zip(*largest)
    mask[yy, xx] = 255
    return np.array(Image.fromarray(mask).filter(ImageFilter.MaxFilter(5))) > 0


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    REVIEW.mkdir(parents=True, exist_ok=True)
    names = ['cell_body.png', 'cell_membrane.png', 'cell_vacuole.png', 'cell_exhaustion_overlay.png',
             'cell_death_overlay.png', 'virus_F2_B.png', 'tissue_base_tile.png.png',
             'tissue_fibers_01.png.png', 'tissue_fibers_02.png.png', 'flow_bed_decal.png.png',
             'macrophage_master.png.png', 't_cell_master.png.png']
    names += [f'budding_process_f{i}.png' for i in range(1, 7)]
    sources = {name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() for name in names}
    exhausted = rgba('cell_exhaustion_overlay.png')
    vacuole = rgba('cell_vacuole.png')[:, :, 3]
    exhausted[:, :, 3] = np.uint8(np.rint(exhausted[:, :, 3].astype(float) * (1 - vacuole / 255)))
    save('cell_exhaustion_no_vacuole.png', exhausted)

    # Crop meaningful foreground, preserve straight RGBA through premultiplied resampling.
    virus = Image.open(SOURCE / 'virus_F2_B.png').convert('RGBA')
    bounds = Image.fromarray(np.uint8(np.array(virus)[:, :, 3] > 16) * 255).getbbox()
    virus = virus.crop(bounds)
    for size in (32, 96, 256, 512):
        edge = round(size * .78)
        scale = edge / max(virus.size)
        small = virus.convert('RGBa').resize((round(virus.width * scale), round(virus.height * scale)),
                                             Image.Resampling.LANCZOS).convert('RGBA')
        canvas = Image.new('RGBA', (size, size))
        canvas.paste(small, ((size - small.width) // 2, (size - small.height) // 2))
        save(f'virus_{size}.png', canvas)

    # Mirrored quadrants guarantee continuous tile edges, without repainting the source.
    tile = Image.open(SOURCE / 'tissue_base_tile.png.png').convert('RGBA')
    quadrant = tile.resize((960, 540), Image.Resampling.LANCZOS)
    seamless = Image.new('RGBA', (1920, 1080))
    seamless.paste(quadrant, (0, 0))
    seamless.paste(ImageOps.mirror(quadrant), (960, 0))
    seamless.paste(ImageOps.flip(quadrant), (0, 540))
    seamless.paste(ImageOps.flip(ImageOps.mirror(quadrant)), (960, 540))
    save('tissue_base_seamless.png', seamless)
    preview = Image.new('RGBA', (960, 540))
    thumb = seamless.resize((320, 180), Image.Resampling.LANCZOS)
    for y in range(3):
        for x in range(3):
            preview.paste(thumb, (x * 320, y * 180))
    preview.convert('RGB').save(REVIEW / 'tissue-3x3.png')

    membrane = rgba('cell_membrane.png')
    body = rgba('cell_body.png')
    rotated = np.array(Image.fromarray(membrane).rotate(24, resample=Image.Resampling.BICUBIC,
                     center=(626, 626.5)).crop((327, 154, 924, 415)))
    # The delivery crop has cell centre (299,472.5), and its normal is upward.
    centre = np.array([299., 472.5])
    fy, fx = np.indices(rotated.shape[:2])
    angle = np.arctan2(fy + .5 - centre[1], fx + .5 - centre[0])
    radius = np.hypot(fx + .5 - centre[0], fy + .5 - centre[1])
    bins = np.linspace(-math.pi / 2 - .65, -math.pi / 2 + .65, 801)
    source_radii = []
    for phi in bins:
        valid = (abs(angle - phi) < .004) & (rotated[:, :, 3] > 128)
        source_radii.append(float(np.max(radius[valid])) if valid.any() else np.nan)
    source_radii = np.array(source_radii)
    good = np.isfinite(source_radii)
    source_radii = np.interp(np.arange(len(bins)), np.where(good)[0], source_radii[good])
    data = json.loads((SOURCE / 'cell_surface_data.json').read_text(encoding='utf-8'))
    points = np.array(data['fine_placements'])[:, :2]
    count = len(points)
    target_radii = np.hypot(points[:, 0], points[:, 1])

    def target_radius(phi):
        index = np.mod(phi, 2 * math.pi) / (2 * math.pi) * count
        low = np.floor(index).astype(int) % count
        return target_radii[low] * (1 - index % 1) + target_radii[(low + 1) % count] * (index % 1)

    frames = [rgba(f'budding_process_f{i}.png') for i in range(1, 7)]
    # The bud and neck must stay rigid. Only the membrane deformation is warped
    # to the target's irregular radial boundary, otherwise a circular bud stretches.
    parts, source_parts = [], []
    native_radii = np.interp(angle, bins, source_radii)
    source_anchor = np.array([centre[0], centre[1]-np.interp(-math.pi/2, bins, source_radii)])
    for f, frame in enumerate(frames):
        bud = bud_mask(frame)
        neck = (radius > native_radii+3) & (abs(fx+.5-centre[0]) < 44) & ~bud & (frame[:,:,3] > 0)
        membrane_frame = frame.copy()
        membrane_frame[bud | neck] = rotated[bud | neck]
        bud_frame, neck_frame = frame.copy(), frame.copy()
        bud_frame[~bud] = 0
        neck_frame[~neck] = 0
        weight = bud_frame[:,:,3].astype(float)
        bud_centre = np.array([(weight*(fx+.5)).sum(), (weight*(fy+.5)).sum()])/weight.sum()
        bb = Image.fromarray(bud_frame[:,:,3]).getbbox()
        diameter = max(bb[2]-bb[0], bb[3]-bb[1])
        for kind, pixels in (('bud', bud_frame), ('neck', neck_frame), ('membrane', membrane_frame)):
            save(f'budding_{kind}_f{f+1}.png', pixels)
        parts.append((membrane_frame, bud_frame, neck_frame, bud_centre, diameter))
        source_parts.append({'frame': f+1, 'bud_bounds': list(bb), 'bud_centre': bud_centre.tolist(),
                             'bud_diameter': diameter, 'neck_pixels': int(neck.sum())})
    # Six delivered poses remain the keyframes. Add an unmodified-membrane
    # start and three intermediate poses per interval (25 poses / 0.8 seconds).
    # Membrane/neck pixels mix in premultiplied space. Buds first align their
    # measured centres and diameters, so growth and detachment move continuously.
    empty = np.zeros_like(rotated)
    keys = [(rotated,empty,empty,source_anchor.copy(),6)] + parts
    smooth = []
    for frame_index in range(25):
        phase = frame_index/4
        low = min(5,int(phase)); t = phase-low
        a,b = keys[low],keys[low+1]
        bud_centre = a[3]*(1-t)+b[3]*t
        diameter = a[4]*(1-t)+b[4]*t
        bud_a = aligned_bud(a[1],a[3],a[4],bud_centre,diameter)
        bud_b = aligned_bud(b[1],b[3],b[4],bud_centre,diameter)
        smooth.append((mix_rgba(a[0],b[0],t),mix_rgba(bud_a,bud_b,t),
                       mix_rgba(a[2],b[2],t),bud_centre,diameter))
    parts = smooth
    atlas_size, tile_size = 1024, 256
    page = Image.new('RGBA', (atlas_size, atlas_size))
    pages, poses = [], []
    slot = 0
    border_errors = 0
    for pose_index in range(180):
        theta = pose_index * 2 * math.pi / 180
        angles = np.linspace(theta - .58, theta + .58, 200)
        radii = target_radius(angles)
        coords = np.concatenate([np.stack([np.cos(angles) * (radii - 90), np.sin(angles) * (radii - 90)], 1),
                                 np.stack([np.cos(angles) * (radii + 140), np.sin(angles) * (radii + 140)], 1)])
        low = np.floor(coords.min(0) - 4).astype(int)
        high = np.ceil(coords.max(0) + 4).astype(int)
        w, h = high - low
        yy, xx = np.indices((h, w))
        cx, cy = xx + low[0] + .5, yy + low[1] + .5
        phi = np.arctan2(cy, cx)
        delta = (phi - theta + math.pi) % (2 * math.pi) - math.pi
        src_phi = delta - math.pi / 2
        src_rad = np.interp(src_phi, bins, source_radii)
        rr = np.hypot(cx, cy) - target_radius(phi) + src_rad
        sx = np.floor(centre[0] + np.cos(src_phi) * rr).astype(int)
        sy = np.floor(centre[1] + np.sin(src_phi) * rr).astype(int)
        valid = (sx >= 0) & (sx < 597) & (sy >= 0) & (sy < 261)
        # Taper to the actual target membrane at the ends of the source arc.
        blend = np.clip((.48 - abs(delta)) / .10, 0, 1) * valid
        blend[:2] = 0; blend[-2:] = 0; blend[:, :2] = 0; blend[:, -2:] = 0
        mx = np.clip(np.floor(cx + 627).astype(int), 0, 1253)
        my = np.clip(np.floor(cy + 627).astype(int), 0, 1253)
        original = membrane[my, mx].copy()
        original[original[:, :, 3] == 0, :3] = 0
        original[(cx + 627 < 0) | (cx + 627 >= 1254) | (cy + 627 < 0) | (cy + 627 >= 1254)] = 0
        record = {'rect': [int(low[0]), int(low[1]), int(w), int(h)], 'frames': [], 'centres': [], 'diameters': []}
        anchor_radius = float(target_radius(np.array(theta)))
        target_anchor = np.array([math.cos(theta)*anchor_radius, math.sin(theta)*anchor_radius])
        co, si = math.cos(theta+math.pi/2), math.sin(theta+math.pi/2)
        rx, ry = cx-target_anchor[0], cy-target_anchor[1]
        rigid_x = np.floor(co*rx+si*ry+source_anchor[0]).astype(int)
        rigid_y = np.floor(-si*rx+co*ry+source_anchor[1]).astype(int)
        rigid_valid = (rigid_x >= 0) & (rigid_x < 597) & (rigid_y >= 0) & (rigid_y < 261)
        for f, (image, bud_frame, neck_frame, bud_centre, diameter) in enumerate(parts):
            sample = image[np.clip(sy, 0, 260), np.clip(sx, 0, 596)]
            # Blend premultiplied values then unpremultiply; no dark fringes.
            weight = blend[:, :, None]
            oa, sa = original[:, :, 3:4] / 255., sample[:, :, 3:4] / 255.
            alpha = oa * (1 - weight) + sa * weight
            rgb = (original[:, :, :3] * oa * (1 - weight) + sample[:, :, :3] * sa * weight)
            rgb = np.divide(rgb, alpha, out=np.zeros_like(rgb), where=alpha > 0)
            patch = np.uint8(np.rint(np.concatenate([rgb, alpha * 255], 2)))
            border_errors += int(np.any(patch[0] != original[0]) or np.any(patch[-1] != original[-1])
                                 or np.any(patch[:, 0] != original[:, 0]) or np.any(patch[:, -1] != original[:, -1]))
            # Replace only the membrane. The unchanged body is drawn underneath
            # at its usual opacity, preserving source-over blending at tile edges.
            for part in (neck_frame, bud_frame):
                rigid = part[np.clip(rigid_y,0,260), np.clip(rigid_x,0,596)].copy()
                rigid[~rigid_valid] = 0
                patch = np.array(Image.alpha_composite(Image.fromarray(patch), Image.fromarray(rigid)))
            if f < 4:
                patch = mix_rgba(original,patch,f/4)
            tile_image = Image.fromarray(patch).resize((tile_size, tile_size), Image.Resampling.NEAREST)
            tx, ty = (slot % 4) * tile_size, (slot // 4) * tile_size
            page.paste(tile_image, (tx, ty))
            record['frames'].append([len(pages) + 1, tx, ty])
            # Measured centre from original pixels, transformed with the same rigid bud.
            bx, by = bud_centre-source_anchor
            record['centres'].append([float(target_anchor[0]+co*bx-si*by), float(target_anchor[1]+si*bx+co*by)])
            record['diameters'].append(diameter)
            slot += 1
            if slot == 16:
                filename = f'budding_smooth_page_{len(pages) + 1:03d}.png'
                save(filename, page)
                pages.append('image/integrated/' + filename)
                page = Image.new('RGBA', (atlas_size, atlas_size)); slot = 0
        poses.append(record)
    if slot:
        filename = f'budding_smooth_page_{len(pages) + 1:03d}.png'
        save(filename, page); pages.append('image/integrated/' + filename)
    assert border_errors == 0, f'patch boundary differs from native membrane: {border_errors}'
    foreground = {}
    for name in ('macrophage_master.png.png', 't_cell_master.png.png'):
        img = Image.open(SOURCE / name).convert('RGBA')
        bb = img.getchannel('A').getbbox()
        foreground[name] = {'canvas': list(img.size), 'bounds': list(bb),
                            'fill': max(bb[2]-bb[0],bb[3]-bb[1]) / max(img.size)}
    manifest = {'version': 2, 'canvas': 1254, 'tile_size': 256, 'page_size': 1024,
                'animation_frames':25, 'keyframe_indices':[5,9,13,17,21,25],
                'native_intro_frames':4,
                'interpolation':'aligned rigid bud centre/diameter; premultiplied membrane and neck',
                'pages': pages, 'poses': poses, 'sources': sources,
                'source_rotation_degrees': 24, 'source_crop': [327, 154, 924, 415],
                'source_cell_centre': centre.tolist(), 'virus_crop': list(bounds),
                'patch_border_errors': border_errors,
                'mapping': 'membrane-only replacement; rigid bud/neck; radial deformation with tapered native arc ends',
                'source_membrane_anchor': source_anchor.tolist(), 'source_parts': source_parts,
                'foreground': foreground, 'virus_fill': .78,
                'exhaustion_vacuole_overlap_pixels': int(((exhausted[:,:,3]>0)&(vacuole>0)).sum())}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(json.dumps({'pages': len(pages), 'poses': len(poses), 'patch_border_errors': border_errors}))


if __name__ == '__main__':
    main()
