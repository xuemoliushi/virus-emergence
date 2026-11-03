"""Publish verified revision-five film aliases before updating the game video."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'assets/video/emergence_final90'


def main():
    verification = json.loads((OUT / 'verification.json').read_text('utf-8'))
    assert verification['revision'] == 5
    for video in verification['videos']:
        source = OUT / video['file']
        assert video['full_decode_ok']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == video['sha256']
    assert (OUT / 'archive_v4/game_ending/emergence90.mp4').is_file()
    aliases = {
        '涌现_90秒_双语字幕.mp4': [
            '涌现_90秒_修订版.mp4',
            '涌现_90秒_转场修正版.mp4',
            '涌现_90秒_最终整合版.mp4',
            '涌现_90秒_云层与声音修正版.mp4',
        ],
        '涌现_90秒_无字幕.mp4': ['涌现_90秒_修订版_无字幕.mp4'],
    }
    for source, destinations in aliases.items():
        for destination in destinations:
            shutil.copy2(OUT / source, OUT / destination)
    report = {
        'revision': 5,
        'date': '2026-10-17',
        'duration': 90,
        'street_range': [46, 60],
        'street_seconds': 14,
        'accepted_ascent_range': [60, 87],
        'dialogue_music_subtitle_timing_unchanged': True,
        'street_foley_removed': True,
        'rectangular_cloud_exit_removed': True,
        'preview': '涌现_90秒_云层与声音修正版.mp4',
        'previous': 'archive_v4/',
        'sha256': hashlib.sha256((OUT / '涌现_90秒_最终整合版.mp4').read_bytes()).hexdigest(),
    }
    (OUT / 'delivery_revision5.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
