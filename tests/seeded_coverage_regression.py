"""Measure real playable-space coverage, including each region's perimeter."""
from pathlib import Path
import json, math, sys, hashlib
from lua_test_runtime import LuaRuntime
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'validation/seeded-map'
lua=LuaRuntime(unpack_returned_tuples=True)
lua.globals().SOURCE_PATH=str(ROOT/'scripts/?.lua').replace('\\','/')
lua.execute("package.path=SOURCE_PATH..';'..package.path;print=function()end;Config=require('Core.Config');Map=require('Core.RespiratoryMap')")
lua.execute('''
function coverage(seed,version)
 local cfg={};for k,v in pairs(Config.Gameplay)do cfg[k]=v end
 cfg.mapSeed=seed;cfg.mapGenerationVersion=version;cfg.cellCount=version==2 and 108 or 216
 local map=Map.New(cfg)
 local result={seed=seed,version=version,regions={},maxGap=0,generationMs=map.generationMs}
 for _,r in ipairs(map.regions)do
  local row={id=r.id,count=0,edgeCount=0,sectors={},maxRimGap=0}
  for i=1,8 do row.sectors[i]=0 end
  for _,c in ipairs(map.cells)do
   if c.regionId==r.id then
    row.count=row.count+1
    local x,y=(c.x-r.x)/r.rx,(c.y-r.y)/r.ry
    local d=math.sqrt(x*x+y*y)
    if d>=.68 then
     row.edgeCount=row.edgeCount+1
     local sector=math.floor((math.atan(y,x)+math.pi)/(math.pi*2)*8)%8+1
     row.sectors[sector]=row.sectors[sector]+1
    end
   end
  end
  for i=1,64 do
   local a=i*math.pi*2/64
   local x,y=r.x+math.cos(a)*r.rx*.87,r.y+math.sin(a)*r.ry*.87
   if map:Contains(x,y,.5) then
    local best=math.huge
    for _,c in ipairs(map.cells)do best=math.min(best,math.sqrt((x-c.x)^2+(y-c.y)^2))end
    row.maxRimGap=math.max(row.maxRimGap,best)
   end
  end
  result.regions[#result.regions+1]=row
 end
 for y=1,map.height-1,1 do for x=1,map.width-1,1 do
  if map:Contains(x,y,.5)then
   local best=math.huge
   for _,c in ipairs(map.cells)do best=math.min(best,math.sqrt((x-c.x)^2+(y-c.y)^2))end
   result.maxGap=math.max(result.maxGap,best)
  end
 end end
 return result,map
end
''')
def convert(value):
    if not hasattr(value,'items'): return value
    if len(value) and all(isinstance(k,int) for k in value.keys()):
        return [convert(value[i])for i in range(1,len(value)+1)]
    return {k:convert(v)for k,v in value.items()}
rows=[]
for seed in [314159,1,2,3,17,73,999,20261012,2147483646,'组织探索']:
    result,_=lua.globals().coverage(seed,3)
    rows.append(convert(result))
baseline,oldmap=lua.globals().coverage(314159,2)
assert hashlib.sha256(oldmap.Snapshot(oldmap).encode()).hexdigest()=='bdccf26886342de1eda6b35d42fea58864a6f7d8e0779151ea216a8aa47166d7'
data=dict(baseline=convert(baseline),current=rows)
(OUT/'coverage.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(data,ensure_ascii=False,indent=2))
for row in rows:
    assert row['maxGap']<=6, row
    for r in row['regions']:
        assert r['edgeCount']>=6 and all(r['sectors']), (row['seed'],r)
        assert r['maxRimGap']<=5, (row['seed'],r)
print('PASS: 10 seeds have targets in all 8 rim sectors and bounded playable-space gaps')
