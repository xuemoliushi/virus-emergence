"""Pack unchanged project sprites and derived material data for an isolated preview."""
from pathlib import Path
import hashlib, json
import numpy as np
from PIL import Image, ImageFilter

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'validation/fluorescence-agents-20261015'
TEX=OUT/'textures'; TEX.mkdir(parents=True,exist_ok=True)
N=256
names=['integrated/virus_256.png','macrophage_master01.png.png','macrophage_master02.png.png',
       'macrophage_master03.png.png','t_cell_master02.png.png','t_cell_master03.png.png']
sources=names+['cell_body.png','cell_vacuole.png','cell_membrane.png','integrated/tissue_base_seamless.png']
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest={'source_sha256':{n:digest(ROOT/'assets/image'/n) for n in sources},
          'runtime_sha256':{p.relative_to(ROOT).as_posix():digest(p) for p in (ROOT/'scripts').rglob('*.lua')},
          'atlas_size':[1024,512],'tile_size':256,'sprites':names+['composed original cell'],
          'scope':'WebGL material preview only. No UrhoX integration or performance certification.'}
baseAtlas=Image.new('RGBA',(N*4,N*2)); mapsAtlas=Image.new('RGBA',baseAtlas.size); fieldAtlas=Image.new('RGBA',baseAtlas.size)
def ar(im):return np.asarray(im).astype(np.float32)/255
def gray(a):return Image.fromarray(np.uint8(np.clip(a,0,1)*255+.5))
def blur(a,r):return ar(gray(a).filter(ImageFilter.GaussianBlur(r)))
images=[Image.open(ROOT/'assets/image'/n).convert('RGBA') for n in names]
cell=Image.new('RGBA',images[1].size)
for n in ['cell_body.png','cell_vacuole.png','cell_membrane.png']:
    cell=Image.alpha_composite(cell,Image.open(ROOT/'assets/image'/n).convert('RGBA'))
images.append(cell)
for i,im in enumerate(images):
    bbox=im.getchannel('A').point(lambda x:255 if x>20 else 0).getbbox()
    im=im.crop(bbox)
    width,height=im.size; ratio=232/max(width,height)
    im=im.convert('RGBa').resize((round(width*ratio),round(height*ratio)),Image.Resampling.LANCZOS).convert('RGBA')
    tile=Image.new('RGBA',(N,N));tile.alpha_composite(im,((N-im.width)//2,(N-im.height)//2))
    a=ar(tile); alpha=a[:,:,3]; lum=a[:,:,:3]@np.array([.2126,.7152,.0722])
    inside=ar(gray(alpha).filter(ImageFilter.MinFilter(13)))
    rim=np.clip((alpha-inside)*1.25,0,1)
    local=blur(lum*alpha,5)
    detail=np.clip((lum-local)/.22,0,1)*alpha*(1-rim*.85)
    texture=np.clip((lum-local*.65)/.35,0,1)*alpha*(1-rim)
    # Suppress broad pale lobes so they do not turn into a white light ring.
    granules=detail*np.clip((lum-.22)/.5,0,1)
    maps=np.stack([rim,texture,granules,alpha],axis=-1)
    soft=blur(alpha,9);gy,gx=np.gradient(blur(alpha,4))
    field=np.stack([np.clip(-gx*12,-1,1)*.5+.5,np.clip(-gy*12,-1,1)*.5+.5,soft,alpha],axis=-1)
    x,y=i%4*N,i//4*N
    baseAtlas.paste(tile,(x,y));mapsAtlas.paste(Image.fromarray(np.uint8(np.clip(maps,0,1)*255+.5)),(x,y))
    fieldAtlas.paste(Image.fromarray(np.uint8(np.clip(field,0,1)*255+.5)),(x,y))
baseAtlas.save(TEX/'base.png');mapsAtlas.save(TEX/'maps.png');fieldAtlas.save(TEX/'field.png')
old=ROOT/'validation/fluorescence-lab-20261015/textures'
for n in ['background.jpg','noise.png']:(TEX/n).write_bytes((old/n).read_bytes())
(OUT/'source-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
print('ATLAS_READY',len(images),'unchanged source sprites; 3 shared 1024x512 atlases')
