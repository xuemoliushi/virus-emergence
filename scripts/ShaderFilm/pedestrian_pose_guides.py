"""Explicit alternating gait guides; generated sprites follow these poses."""
from PIL import Image, ImageDraw
from pathlib import Path
OUT=Path(__file__).resolve().parents[2]/'assets/video/素材/行人素材_v1'
OUT.mkdir(parents=True,exist_ok=True)
# Longitudinal leg extension and lift: opposing limbs alternate, no mirroring.
phases=[(1,-1,0,0),(.65,-.65,0,.12),(0,0,0,.4),(-.65,.65,.1,.1),
        (-1,1,0,0),(-.65,.65,.12,0),(0,0,.4,0),(.65,-.65,.1,.1),(0,0,0,0)]
for sex,direction in [('P01',1),('P02',-1)]:
    im=Image.new('RGB',(1536,1536),'#efede7')
    dr=ImageDraw.Draw(im)
    for i,(le,re,ll,rl) in enumerate(phases):
        ox=(i%3)*512; oy=(i//3)*512; cx=ox+256
        hipy=oy+258
        dr.text((ox+18,oy+15),str(i+1),fill='#444444')
        # fixed head/torso and neutral arm insertion points
        dr.ellipse((cx-28,oy+57,cx+28,oy+113),fill='#aaa69e',outline='#555555',width=3)
        dr.polygon([(cx-39,oy+119),(cx+36,oy+123),(cx+25,hipy),(cx-26,hipy)],fill='#bab7af',outline='#555555',width=3)
        for side,extension,lift,color in [(-1,le,ll,'#bd4e46'),(1,re,rl,'#477eaf')]:
            hx=cx+side*17; hy=hipy+side*4
            # direction * extension sets forward/back along screen diagonal.
            ax=hx+direction*extension*65
            ay=oy+415+direction*extension*32-lift*100
            kx=hx+direction*extension*28-side*5
            ky=(hy+ay)/2-abs(lift)*30
            dr.line([(hx,hy),(kx,ky),(ax,ay)],fill=color,width=14)
            dr.ellipse((ax-9,ay-7,ax+9,ay+7),fill=color)
            # Opposite arm swing.
            sx=cx+side*40; sy=oy+139
            ex=sx-direction*extension*32; ey=oy+221-direction*extension*8
            dr.line([(sx,sy),((sx+ex)/2,oy+184),(ex,ey)],fill=color,width=10)
    im.save(OUT/f'{sex}_步态姿势引导_非成品.png')
print('pose guides saved')
