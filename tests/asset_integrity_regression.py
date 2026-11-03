"""Independent retained-image integrity and actual Lua config dependency checks."""
from pathlib import Path
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from PIL import Image
from lua_test_runtime import LuaRuntime

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'validation/asset-cleanup-20261018'

def values(value):
    if isinstance(value,str):yield value
    elif isinstance(value,dict):
        for k,v in value.items():yield from values(k);yield from values(v)
    elif isinstance(value,list):
        for v in value:yield from values(v)
    elif hasattr(value,'items'):
        for k,v in value.items():yield from values(k);yield from values(v)

def run():
    retirement_path=ROOT/'validation/actor-asset-cleanup-20261018/removed.json'
    retirement=json.loads(retirement_path.read_text(encoding='utf8'))
    retained=retirement['retained']
    retired={row['path'].removeprefix('assets/') for row in retirement['files']}
    assert all(not (ROOT/row['path']).exists() for row in retirement['files']), 'Retired assets reappeared'
    required=set();configs=[]
    slots=[]
    for glow in [True,False]:
        lua=LuaRuntime(unpack_returned_tuples=True)
        source=(ROOT/'scripts/Core/Config.lua').read_text(encoding='utf-8-sig')
        if not glow:source=source.replace('enabled = true, glowEnabled = true,','enabled = false, glowEnabled = true,')
        config=lua.execute(source)
        found={p for p in values(config) if p.startswith(('image/','Sprites/')) and Path(p).suffix.lower() in {'.png','.jpg','.json'}}
        required.update(found);configs.append({'bioluminescence':glow,'dependencies':len(found)})
        slots.append(set(values(config['ArtSlots'])))
        assert found.isdisjoint(retired),'Config depends on retired art'
    assert slots[0]==slots[1],'Disabling extra light must retain the current base art'
    lua=LuaRuntime(unpack_returned_tuples=True)
    cards=lua.execute((ROOT/'scripts/UI/CardArt.lua').read_text(encoding='utf-8-sig'))
    card_paths=list(cards.paths.values());assert len(card_paths)==18
    required.update(card_paths)
    # Every page must exist, including pages selected only at rare angles/frames.
    pages=[]
    for name in ['image/cell_surface_atlas/manifest.json','image/bioluminescent/budding_manifest.json']:
        manifest=json.loads((ROOT/'assets'/name).read_text(encoding='utf8'))
        pages.extend(manifest['pages']);required.update(manifest['pages'])
    assert required.isdisjoint(retired),'Active atlas depends on retired art'
    latent=json.loads((ROOT/'assets/image/latent_particles_meta.json').read_text(encoding='utf8'))
    required.update('image/'+name for name in latent['sprites'].values())
    checked=[]
    for path in sorted(required):
        absolute=ROOT/'assets'/path
        assert absolute.is_file(),'Missing Lua/manifest dependency: '+path
        checked.append(path)
    for row in retained:
        path=ROOT/row['path']
        assert path.is_file(),'Retained image disappeared: '+row['path']
        assert Path(str(path)+'.meta').is_file(),'Retained Maker mapping disappeared: '+row['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'],'Retained pixels changed: '+row['path']
        if path.suffix.lower()=='.svg':ET.parse(path)
        else:
            with Image.open(path) as image:image.verify()
    for page in set(pages):
        with Image.open(ROOT/'assets'/page) as image:
            assert image.size==(1024,1024) and image.mode=='RGBA',page
    result={'passed':True,'retained_images_verified':len(retained),'config_modes':configs,
        'cards':18,'atlas_page_references':len(pages),'unique_required_paths':len(checked),
        'scope':'Real retained files and original SHA256, Lua config with extra light on/off, current manifest pages; native visuals excluded'}
    (retirement_path.parent/'integrity.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':run()
