"""Build one isolated final review package. Never overwrites live game resources."""
from pathlib import Path
import hashlib,json
import numpy as np
from PIL import Image,ImageFilter
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'validation/final-art-review-20261015';ART=OUT/'art';TEX=OUT/'textures';TEX.mkdir(exist_ok=True)
N=256;digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
entries=[('virus',ART/'virus.png'),('macrophage',ART/'macrophage.png'),('tcell-01',ART/'tcell-01.png'),('tcell-02',ART/'tcell-02.png'),
 ('old-virus',ROOT/'assets/image/integrated/virus_256.png'),('old-macrophage',ROOT/'assets/image/macrophage_master01.png.png'),
 ('old-tcell-01',ROOT/'assets/image/t_cell_master02.png.png'),('old-tcell-02',ROOT/'assets/image/t_cell_master03.png.png')]
def ar(im):return np.asarray(im).astype(np.float32)/255
def im(a):return Image.fromarray(np.uint8(np.clip(a,0,1)*255+.5))
def blur(a,r):return ar(im(a).filter(ImageFilter.GaussianBlur(r)))
images=[Image.open(p).convert('RGBA') for _,p in entries]
red=Image.new('RGBA',Image.open(ROOT/'assets/image/cell_body.png').size)
for n in ['cell_body.png','cell_vacuole.png','cell_membrane.png']:red=Image.alpha_composite(red,Image.open(ROOT/'assets/image'/n).convert('RGBA'))
images.append(red);atlases=[Image.new('RGBA',(N*3,N*3)) for _ in range(3)]
for k,pic in enumerate(images):
    alpha=pic.getchannel('A');bbox=alpha.point(lambda x:255 if x>20 else 0).getbbox();pic=pic.crop(bbox)
    s=(N-24)/max(pic.size);pic=pic.convert('RGBa').resize((round(pic.width*s),round(pic.height*s)),Image.Resampling.LANCZOS).convert('RGBA')
    tile=Image.new('RGBA',(N,N));tile.alpha_composite(pic,((N-pic.width)//2,(N-pic.height)//2))
    a=ar(tile);alpha=a[:,:,3];r,g,b=[a[:,:,i] for i in range(3)];lum=a[:,:,:3]@np.array([.2126,.7152,.0722])
    rim=np.clip((alpha-ar(im(alpha).filter(ImageFilter.MinFilter(13))))*1.25,0,1)
    if k<4:
        if k==0:light=np.clip((r*.5+g*.8-b*.7-.22)*2.5,0,1)*alpha;nucleus=np.zeros_like(alpha)
        else:light=np.clip((g-r)*3.8,0,1)*alpha;nucleus=np.clip((r-g)*5,0,1)*np.clip((b-g)*5,0,1)*alpha
        granular=np.clip((lum-blur(lum,3))/.17,0,1)*light
        thickness=blur(alpha,8)*(.35+blur(np.clip(lum*.9+.25,0,1)*alpha,4)*.65)
        maps=np.stack([light,nucleus,granular,thickness],axis=-1)
    else:
        structure=np.clip((lum-blur(lum*alpha,5)*.65)/.35,0,1)*alpha*(1-rim)
        granular=np.clip((lum-blur(lum*alpha,5))/.22,0,1)*alpha*(1-rim*.85)*np.clip((lum-.22)/.5,0,1)
        maps=np.stack([rim,structure,granular,alpha],axis=-1);thickness=blur(alpha,9)
    gy,gx=np.gradient(blur(thickness,3));field=np.stack([np.clip(-gx*14,-1,1)*.5+.5,np.clip(-gy*14,-1,1)*.5+.5,thickness,alpha],axis=-1)
    for target,layer in zip(atlases,[tile,im(maps),im(field)]):target.paste(layer,(k%3*N,k//3*N))
    if k<4:tile.save(ART/(entries[k][0]+'-thumb.png'))
for name,pic in zip(['base','maps','field'],atlases):pic.save(TEX/(name+'.png'))
for src,dst in [(ART/'background.png',TEX/'background.jpg'),(ROOT/'validation/fluorescence-rework-20261015/background-reworked.png',TEX/'approvedBackground.jpg')]:Image.open(src).convert('RGB').resize((1280,720),Image.Resampling.LANCZOS).save(dst,quality=93)
(TEX/'oldBackground.jpg').write_bytes((ROOT/'validation/fluorescence-lab-20261015/textures/background.jpg').read_bytes());(TEX/'noise.png').write_bytes((ROOT/'validation/fluorescence-lab-20261015/textures/noise.png').read_bytes())
Image.open(ART/'background.png').convert('RGB').resize((480,270),Image.Resampling.LANCZOS).save(ART/'background-thumb.jpg',quality=90)
protected=[p for _,p in entries[4:]]+[ROOT/'assets/image'/n for n in ['cell_body.png','cell_vacuole.png','cell_membrane.png','integrated/tissue_base_seamless.png']]
manifest={'original_assets':{p.relative_to(ROOT).as_posix():digest(p) for p in protected},'original_lua':{p.relative_to(ROOT).as_posix():digest(p) for p in (ROOT/'scripts').rglob('*.lua')},
 'new_art':{p.name:{'sha256':digest(p),'size':list(Image.open(p).size),'mode':Image.open(p).mode} for p in ART.glob('*.png') if 'thumb' not in p.name},
 'atlas':[768,768],'tile_size':256,'slots':[n for n,_ in entries]+['original red tissue cell context'],
 'scope':'Final visual approval draft only; built-in image_gen for new raster art, WebGL for live material preview. Not integrated into UrhoX.'}
(OUT/'source-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8');print('FINAL_REVIEW_TEXTURES_READY',len(images),'slots')
