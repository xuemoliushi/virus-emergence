"""Conservative texture audit: code, dynamic families and JSON/atlas dependencies.

No deletion is performed. All existing alternate art configurations and metadata
source references are protected, even when the current presentation bypasses them.
"""
from pathlib import Path
import hashlib
import json
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'validation/asset-cleanup-20261018'
IMAGE_EXT={'.png','.jpg','.jpeg','.webp','.dds','.tga','.svg'}

def strings(value):
    if isinstance(value,str):yield value
    elif isinstance(value,dict):
        for key,item in value.items():
            yield from strings(key);yield from strings(item)
    elif isinstance(value,list):
        for item in value:yield from strings(item)

def audit():
    images={p.relative_to(ROOT/'assets').as_posix():p for folder in ['image','Sprites']
            for p in (ROOT/'assets'/folder).rglob('*') if p.is_file() and p.suffix.lower() in IMAGE_EXT}
    reasons={name:[] for name in images}
    code={p.relative_to(ROOT).as_posix():p.read_text(encoding='utf-8-sig') for p in (ROOT/'scripts').rglob('*.lua')}
    families=set()
    for source,text in code.items():
        # Directory fragments are used by skin/icon/variant path construction.
        # Generic image/ is resolved via metadata and filename fragments below.
        for family in re.findall(r'''["']((?:image|Sprites)/(?:[^"'\n]+/)+)["']''',text):
            families.add((family,source))
        for name in images:
            if name in text:
                reasons[name].append('code:'+source)
            elif images[name].name in text:
                reasons[name].append('code-filename:'+source)
    for family,source in sorted(families):
        for name in images:
            if name.startswith(family):reasons[name].append('dynamic-family:'+source+':'+family)
    metadata={}
    for folder in ['image','Sprites']:
        for p in (ROOT/'assets'/folder).rglob('*.json'):
            values=list(strings(json.loads(p.read_text(encoding='utf-8-sig'))))
            metadata[p.relative_to(ROOT).as_posix()]=values
            normalized=[v.replace('\\','/') for v in values]
            for name,path in images.items():
                for value in normalized:
                    # Protect provenance originals too; duplicate basenames are
                    # deliberately retained rather than resolved by guessing.
                    if value==path.name or name in value or ('/'+path.name) in value:
                        reasons[name].append('asset-json:'+p.relative_to(ROOT).as_posix())
                        break
    support={}
    for folder in ['tests','local-preview','validation']:
        for p in (ROOT/folder).rglob('*'):
            if p.is_file() and p.suffix in {'.py','.lua','.js','.html','.ps1'} and 'baseline' not in p.parts:
                support[p.relative_to(ROOT).as_posix()]=p.read_text(encoding='utf-8-sig',errors='replace')
    protected=[];candidates=[]
    for name,path in sorted(images.items()):
        row={'path':'assets/'+name,'bytes':path.stat().st_size,
             'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
             'reasons':sorted(set(reasons[name]))}
        if reasons[name]:protected.append(row)
        else:
            row['support_mentions']=[source for source,text in support.items() if path.name in text or name in text]
            candidates.append(row)
    # Full paths appearing literally in any Lua file must exist locally or have
    # a Maker UUID mapping; missing historical references are kept separate.
    missing=[]
    for source,text in code.items():
        for value in re.findall(r'''["']((?:image|Sprites)/[^"'\n]+\.(?:png|jpg|jpeg|webp|dds|tga|json))["']''',text,re.I):
            if not (ROOT/'assets'/value).is_file():
                missing.append({'path':'assets/'+value,'source':source,
                    'maker_meta_exists':Path(str(ROOT/'assets'/value)+'.meta').is_file()})
    report={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'scope':'assets/image and assets/Sprites only; video/audio/source archives are preserved',
        'images':len(images),'protected_count':len(protected),'candidate_count':len(candidates),
        'candidate_bytes':sum(row['bytes'] for row in candidates),
        'dynamic_families':[{'prefix':f,'source':s} for f,s in sorted(families)],
        'preexisting_missing_literals':missing,'protected':protected,'candidates':candidates}
    OUT.mkdir(exist_ok=True)
    (OUT/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'protected','candidates','dynamic_families'}},ensure_ascii=False,indent=2))
    for row in candidates:print(row['path'],row['bytes'],','.join(row['support_mentions']))
    return report

if __name__=='__main__':audit()
