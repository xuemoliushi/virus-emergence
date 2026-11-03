"""Offline resource contact sheet, explicitly not a native engine screenshot."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'validation/bioluminescence-integration-20261015'
ART=ROOT/'assets/image/bioluminescent'


def main():
    bg=Image.open(ART/'background.png').convert('RGBA').resize((1280,720))
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',19)
    small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',13)
    def add(im,x,y,size):
        im=im.convert('RGBa').resize((size,size),Image.Resampling.LANCZOS).convert('RGBA')
        bg.alpha_composite(im,(round(x-size/2),round(y-size/2)))
    healthy=Image.new('RGBA',(1254,1254))
    for n in ['cell_body.png','cell_membrane.png','cell_vacuole.png']:
        healthy=Image.alpha_composite(healthy,Image.open(ART/n).convert('RGBA'))
    entries=[(160,'病毒 · 游戏尺寸梯',Image.open(ART/'virus_256.png')),
             (480,'巨噬细胞 · 新版',Image.open(ART/'macrophage.png')),
             (800,'T 细胞 · 新版',Image.open(ART/'tcell-01.png')),
             (1120,'健康红细胞 · 同锚点分层',healthy)]
    for x,name,im in entries:
        ImageDraw.Draw(bg).text((x-140,80),name,font=font,fill='#cee9dc')
        add(im,x,260,250 if x!=1120 else 350)
    for i,n in enumerate(['macrophage.png','tcell-01.png','tcell-02.png']):
        add(Image.open(ART/n),360+i*190,560,128 if i==0 else 85)
    add(healthy,1050,560,round(120*1254/760))
    for i in range(12):add(Image.open(ART/'virus_32.png'),100+i*13,560,14)
    d=ImageDraw.Draw(bg);d.rectangle((0,0,1280,60),fill='#09120f')
    d.text((18,12),'游戏资源接入校验 · 离线贴图合成',font=font,fill='#cee9dc')
    d.text((18,39),'使用正式资源文件；用于检查贴图、尺度和分层，不是引擎实机截图。',font=small,fill='#9ebba9')
    bg.convert('RGB').save(OUT/'resource-proof.png')
    print('RESOURCE_PROOF_READY')


if __name__=='__main__':main()
