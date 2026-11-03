"""Pack preview-only images and region-aware material maps, preserving all originals."""
from pathlib import Path
import hashlib,json
import numpy as np
from PIL import Image,ImageFilter
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'validation/fluorescence-rework-20261015';TEX=OUT/'textures';TEX.mkdir(exist_ok=True)
N=384
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
sources=[ROOT/'assets/image/macrophage_master01.png.png',OUT/'macrophage-reworked.png',ROOT/'assets/image/integrated/virus_256.png']
manifest={'sources':{str(p.relative_to(ROOT)):digest(p) for p in sources},'original_lua':{p.relative_to(ROOT).as_posix():digest(p) for p in (ROOT/'scripts').rglob('*.lua')},'tile_size':N,'note':'Independent WebGL visual study; new raster material and background generated with built-in image_gen. No runtime integration.'}
def ar(im):return np.asarray(im).astype(np.float32)/255
def im(a):return Image.fromarray(np.uint8(np.clip(a,0,1)*255+.5))
def blur(a,r):return ar(im(a).filter(ImageFilter.GaussianBlur(r)))
atlases=[Image.new('RGBA',(N*3,N)) for _ in range(3)]
for k,p in enumerate(sources):
    src=Image.open(p).convert('RGBA');box=src.getchannel('A').point(lambda v:255 if v>20 else 0).getbbox();src=src.crop(box)
    ratio=(N-32)/max(src.size);src=src.convert('RGBa').resize((round(src.width*ratio),round(src.height*ratio)),Image.Resampling.LANCZOS).convert('RGBA')
    tile=Image.new('RGBA',(N,N));tile.alpha_composite(src,((N-src.width)//2,(N-src.height)//2))
    a=ar(tile);alpha=a[:,:,3];r,g,b=[a[:,:,i] for i in range(3)];lum=a[:,:,:3]@np.array([.2126,.7152,.0722])
    rim=np.clip((alpha-ar(im(alpha).filter(ImageFilter.MinFilter(17))))*1.25,0,1)
    if k==1:
        cyan=np.clip((g-r)*3.8,0,1)*alpha
        nucleus=np.clip((r-g)*5,0,1)*np.clip((b-g)*5,0,1)*alpha
        granules=np.clip((lum-blur(lum,4))/.17,0,1)*cyan
        thickness=blur(alpha,12)*(.35+blur(np.clip(lum*.9+.25,0,1)*alpha,7)*.65)
        maps=np.stack([cyan,nucleus,granules,thickness],axis=-1)
    else:
        detail=np.clip((lum-blur(lum*alpha,7))/.22,0,1)*alpha*(1-rim*.85)
        structure=np.clip((lum-blur(lum*alpha,7)*.65)/.35,0,1)*alpha*(1-rim)
        granules=detail*np.clip((lum-.22)/.5,0,1)
        maps=np.stack([rim,structure,granules,alpha],axis=-1);thickness=blur(alpha,12)
    gy,gx=np.gradient(blur(thickness,4));field=np.stack([np.clip(-gx*18,-1,1)*.5+.5,np.clip(-gy*18,-1,1)*.5+.5,thickness,alpha],axis=-1)
    for atlas,layer in zip(atlases,[tile,im(maps),im(field)]):atlas.paste(layer,(k*N,0))
for name,atlas in zip(['base','maps','field'],atlases):atlas.save(TEX/(name+'.png'))
old=ROOT/'validation/fluorescence-lab-20261015/textures'
(TEX/'oldBackground.jpg').write_bytes((old/'background.jpg').read_bytes());(TEX/'noise.png').write_bytes((old/'noise.png').read_bytes())
Image.open(OUT/'background-reworked.png').convert('RGB').resize((1024,576),Image.Resampling.LANCZOS).save(TEX/'newBackground.jpg',quality=93)
manifest['original_assets']={'assets/image/macrophage_master01.png.png':digest(sources[0]),'assets/image/integrated/virus_256.png':digest(sources[2]),'assets/image/integrated/tissue_base_seamless.png':digest(ROOT/'assets/image/integrated/tissue_base_seamless.png')}
(OUT/'source-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8');print('REWORK_TEXTURES_READY')
