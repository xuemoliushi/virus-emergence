"""One background vector per bilingual cue; shared preview/export geometry."""
from pathlib import Path
from PIL import ImageFont
import json,math
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'assets/video/emergence_final90'

def stamp(t):
 cs=round(t*100);return f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'

def main():
 cues=json.loads((OUT/'cues.json').read_text('utf-8'))
 zhfont=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',38)
 enfont=ImageFont.truetype('C:/Windows/Fonts/georgia.ttf',27)
 layout=[]
 ass='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Text,Microsoft YaHei,38,&H00E6F0F4,&H00E6F0F4,&HFF000000,&HFF000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
 for c in cues:
  width=math.ceil(max(zhfont.getlength(c['zh']),enfont.getlength(c['en'])))+64
  assert width<1728,'Split long subtitle instead of overflowing safe area'
  q={**c,'x':round(960-width/2),'y':920,'width':width,'height':112,'zhY':954,'enY':1001}
  layout.append(q);start,end=stamp(c['start']),stamp(c['end'])
  # An independent ASS vector rect has no line boxes, borders or shadows.
  box=rf'{{\an7\pos({q["x"]},920)\p1\bord0\shad0\1c&H0C0B0A&\1a&H66&}}m 0 0 l {width} 0 l {width} 112 l 0 112'
  zh=rf'{{\an5\pos(960,954)\fnMicrosoft YaHei\fs38\bord0\shad0}}'+c['zh']
  en=rf'{{\an5\pos(960,1001)\fnGeorgia\fs27\bord0\shad0}}'+c['en']
  for layer,name,text in [(0,'Background',box),(1,'Chinese',zh),(1,'English',en)]:
   ass+=f'Dialogue: {layer},{start},{end},Text,{name},0,0,0,,{text}\n'
 (OUT/'subtitle_layout.json').write_text(json.dumps(layout,ensure_ascii=False,indent=2),encoding='utf-8')
 (OUT/'subtitles.ass').write_text(ass,encoding='utf-8-sig')
 print(f'SUBTITLE_LAYOUT_OK: {len(cues)} single backgrounds, two text rows each',flush=True)

if __name__=='__main__':main()
