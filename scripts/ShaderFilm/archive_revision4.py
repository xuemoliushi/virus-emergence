"""Preserve the delivered film and source state before the two user fixes."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'assets/video/emergence_final90';BACK=OUT/'archive_v4'
assert not BACK.exists(), 'Revision 4 archive already exists; do not overwrite it'
BACK.mkdir()
for source in OUT.iterdir():
 if source.is_file():shutil.copy2(source,BACK/source.name)
for name in ['shaders','qa']:
 shutil.copytree(OUT/name,BACK/name)
shutil.copytree(ROOT/'assets/audio/emergence_final90',BACK/'audio')
shutil.copytree(ROOT/'assets/video/ending',BACK/'game_ending')
source=BACK/'source_scripts';source.mkdir()
for p in (ROOT/'scripts/ShaderFilm').iterdir():
 if p.is_file():shutil.copy2(p,source/p.name)
frozen=json.loads((OUT/'revision4_preserved_hashes.json').read_text('utf-8'))
frozen={p:h for p,h in frozen.items() if Path(p).name!='mix.wav'}
for name in ['music.wav']:
 p=ROOT/'assets/audio/emergence_final90'/name
 frozen[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
(OUT/'revision5_preserved_hashes.json').write_text(json.dumps(frozen,ensure_ascii=False,indent=2),encoding='utf-8')
print('Revision 4 film, game copy, audio and sources archived; protected dialogue/music/street hashes recorded.')
