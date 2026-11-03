"""Annotated reference for the next asset batch; does not change the film."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'assets/video/emergence_shader/修订素材任务单'
OUT.mkdir(exist_ok=True)
im=Image.open(ROOT/'assets/video/素材/13_intersection_closeup.png').convert('RGBA')
layer=Image.new('RGBA',im.size);d=ImageDraw.Draw(layer)
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',25)
small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',21)
def arrow(points,color,width=7):
 d.line(points,fill=color,width=width,joint='curve')
 x,y=points[-1];px,py=points[-2];a=math.atan2(y-py,x-px)
 d.polygon([(x,y),(x-26*math.cos(a-.45),y-26*math.sin(a-.45)),(x-26*math.cos(a+.45),y-26*math.sin(a+.45))],fill=color)
def label(p,s,color):
 b=d.textbbox(p,s,font=small);d.rounded_rectangle((b[0]-10,b[1]-7,b[2]+10,b[3]+7),7,fill=(15,20,25,225));d.text(p,s,font=small,fill=color)
# These are intentionally rough paths to explain the workflow, not camera calibration.
arrow([(270,935),(615,735),(1030,495),(1660,130)],(74,205,255,255))
arrow([(1660,245),(1315,445),(925,670),(465,935)],(255,184,65,255))
arrow([(722,501),(846,573),(987,657)],(95,244,148,255),9)
arrow([(1008,677),(870,597),(742,523)],(198,255,204,255),5)
d.line([(580,708),(729,795)],fill=(255,95,105,255),width=10)
label((285,884),'车辆 A：沿车道直行，过街结束后再启动',(74,205,255,255))
label((1220,304),'车辆 B：反向车道，另一个观察面',(255,184,65,255))
label((760,452),'行人：沿同一斑马线迈腿，足底贴地',(95,244,148,255))
label((350,652),'停车位置示意：以车头和车轮落点校准',(255,125,130,255))
im=Image.alpha_composite(im,layer).convert('RGB')
panel=Image.new('RGB',(1920,1210),(21,24,29));panel.paste(im,(0,130));pd=ImageDraw.Draw(panel)
pd.text((35,20),'路口素材制作与运动方向示意',font=font,fill='white')
pd.text((35,65),'彩线只用于规划；先生成无标注底图。路线为近似示意，合成时需按新底图重新标定道路与遮挡。',font=small,fill=(210,214,221))
panel.save(OUT/'路口运动与素材示意.jpg',quality=95)

# A small code-native diagram of the proposed distance-based bird representation.
im=Image.new('RGB',(1600,520),(245,243,236));d=ImageDraw.Draw(im)
for i,(title,detail) in enumerate([
 ('近景：独立鸟身与双翼','主体宽约 28px 以上，保持主角身份'),
 ('中景：简化振翅轮廓','约 12–28px，去掉羽毛纹理'),
 ('远景：小翼形 / 箭头符号','约 3–12px，方向与速度一致'),
 ('极远景：抗锯齿微点','约 1–3px，避免亚像素闪烁')]):
 x=i*400
 d.text((x+18,25),title,font=small,fill=(30,32,35));d.text((x+18,430),detail,font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',17),fill=(65,65,65))
 if i==0:
  bird=Image.open(ROOT/'assets/video/emergence_shader/art/bird_body.png').convert('RGBA')
  wing=Image.open(ROOT/'assets/video/emergence_shader/art/bird_wing.png').convert('RGBA')
  bird=Image.alpha_composite(bird,wing);bird.thumbnail((340,310));im.paste(bird,(x+22,85),bird)
 elif i==1:
  d.polygon([(x+120,245),(x+245,155),(x+215,243),(x+274,255),(x+210,269),(x+155,322),(x+176,265)],fill=(29,31,30))
 elif i==2:
  for j in range(11):
   bx=x+65+(j%4)*78;by=160+(j//4)*70
   d.polygon([(bx-12,by-8),(bx+13,by),(bx-12,by+8),(bx-3,by)],fill=(35,37,36))
 else:
  for j in range(48):
   bx=x+50+(j%8)*40;by=150+(j//8)*30+(j%3)*7
   d.ellipse((bx,by,bx+3,by+3),fill=(55,57,56))
d.text((28,485),'表示层次随屏幕尺寸连续切换；图中阈值为起始调参值，最终按 1080p 动画观看效果调整。',font=small,fill=(60,60,60))
im.save(OUT/'鸟群远近层次示意.jpg',quality=95)
print(OUT)
