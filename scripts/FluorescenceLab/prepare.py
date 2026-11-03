"""Build an isolated material experiment from read-only project textures.

No runtime assets or game entry files are changed. RGB beneath alpha is deliberately
discarded before downsampling. Packed maps are technical render inputs, not new art.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'validation/fluorescence-lab-20261015'
TEX = OUT / 'textures'
TEX.mkdir(parents=True, exist_ok=True)
SIZE = 512

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def load(name):
    return Image.open(ROOT / 'assets/image' / name).convert('RGBA')

def arr(im):
    return np.asarray(im).astype(np.float32) / 255

def save(name, a):
    Image.fromarray(np.uint8(np.clip(a, 0, 1) * 255 + .5)).save(TEX / name)

def blur(a, radius):
    return arr(Image.fromarray(np.uint8(np.clip(a, 0, 1)*255)).filter(ImageFilter.GaussianBlur(radius)))

def small(im):
    return im.convert('RGBa').resize((SIZE, SIZE), Image.Resampling.LANCZOS).convert('RGBA')

source_names = ['cell_body.png', 'cell_membrane.png', 'cell_vacuole.png', 'integrated/tissue_base_seamless.png']
sources = {n: digest(ROOT/'assets/image'/n) for n in source_names}
runtime = {p.relative_to(ROOT).as_posix(): digest(p) for p in (ROOT/'scripts').rglob('*.lua')}
body, membrane, vacuole = [load(n) for n in source_names[:3]]
combined = Image.new('RGBA', body.size)
for layer in [body, vacuole, membrane]:
    combined = Image.alpha_composite(combined, layer)
b, m, v = arr(small(body)), arr(small(membrane)), arr(small(vacuole))
base = arr(small(combined))
base[base[:,:,3] < .001, :3] = 0
save('base.png', base)
mem = m[:,:,3]
vac = v[:,:,3]
lum = b[:,:,:3] @ np.array([.2126,.7152,.0722])
granules = np.clip((lum-.32)/.42,0,1)*b[:,:,3]*(1-vac)
filaments = np.clip((b[:,:,0]-.22)/.45,0,1)*np.clip((.50-lum)/.18,0,1)*b[:,:,3]*(1-vac)
save('maps.png', np.stack([mem,filaments,granules,vac],axis=-1))
thickness = blur(base[:,:,3], 24)
thickness = np.clip(thickness/.97,0,1)
gy,gx = np.gradient(blur(base[:,:,3], 10))
save('field.png', np.stack([np.clip(-gx*22,-1,1)*.5+.5,np.clip(-gy*22,-1,1)*.5+.5,thickness,base[:,:,3]],axis=-1))
rng = np.random.default_rng(20261015)
noise = Image.fromarray(rng.integers(0,256,(64,64),dtype=np.uint8)).resize((256,256),Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(2))
noise.convert('RGB').save(TEX/'noise.png')
load(source_names[3]).convert('RGB').resize((768,432),Image.Resampling.LANCZOS).save(TEX/'background.jpg',quality=90)
manifest = {'sources_sha256':sources, 'runtime_sha256':runtime, 'canvas':512,
 'maps_channels':['membrane','internal_structure','granules','vacuole'],
 'field_channels':['pseudo_normal_x','pseudo_normal_y','pseudo_thickness','silhouette'],
 'note':'WebGL material experiment; not an UrhoX implementation or engine performance certification.'}
(OUT/'source-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'output':str(OUT),'textures':len(list(TEX.iterdir())),'runtime_lua_files':len(runtime)}))
