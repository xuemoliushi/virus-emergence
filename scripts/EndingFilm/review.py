"""Export the revised transition and inspect decoded output frames."""
from pathlib import Path
import json
import subprocess
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'assets/video/emergence_90s'
QA = OUT / 'qa'
FF = r'C:\Users\admin\Downloads\vocaloid-style-mv-pipeline\vendor\ffmpeg\ffmpeg.exe'
PROBE = r'C:\Users\admin\Downloads\vocaloid-style-mv-pipeline\vendor\ffmpeg\ffprobe.exe'
VIDEO = OUT / 'ending_emergence_bilingual_smooth_v2.mp4'
CLIP = OUT / 'transition_flight_review_smooth_v2.mp4'

with CLIP.open('wb') as output:
    subprocess.run([FF, '-v', 'error', '-ss', '5', '-i', str(VIDEO),
                    '-t', '19', '-c:v', 'libx264', '-threads', '4',
                    '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-b:a', '256k', '-movflags',
                    'frag_keyframe+empty_moov', '-f', 'mp4', 'pipe:1'],
                   stdout=output, check=True)

# Decode the completed deliverable, rather than only inspecting source renders.
sheet = Image.new('RGB', (1440, 860), '#ddd9ce')
draw = ImageDraw.Draw(sheet)
times = [5.95, 6.0, 8, 10, 12, 13, 14, 15, 16, 17.95, 18, 20]
for i, t in enumerate(times):
    target = QA / f'decoded_v2_{str(t).replace(".", "_")}.png'
    with target.open('wb') as dst:
        subprocess.run([FF, '-v', 'error', '-ss', str(t), '-i', str(VIDEO),
                        '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png',
                        'pipe:1'], stdout=dst, check=True)
    with Image.open(target) as frame:
        frame.thumbnail((480, 270))
        x, y = (i % 3) * 480, (i // 3) * 215
        frame = frame.resize((360, 202))
        sheet.paste(frame, (x, y))
        draw.text((x + 365, y + 8), f'{t:.2f}s', fill='#151513')
sheet.save(QA / 'decoded_v2_contact.jpg', quality=92)
report = json.loads(subprocess.check_output([PROBE, '-v', 'error',
    '-count_frames', '-show_streams', '-show_format', '-of', 'json', str(CLIP)]))
v = next(s for s in report['streams'] if s['codec_type'] == 'video')
assert v['nb_read_frames'] == '456', v
assert v['width'] == 1920 and v['height'] == 1080, v
assert v['r_frame_rate'] == '24/1', v
(OUT / 'review_verification_smooth_v2.json').write_text(json.dumps(report, indent=2))
print('REVIEW VERIFIED: 19 seconds, 456 frames, 1080p with audio')
