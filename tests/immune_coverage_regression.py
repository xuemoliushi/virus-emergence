"""Production-map coverage and real immune actions; no native balance claim."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / '.tmp/test-deps'), str(ROOT / 'tests')]
from lua_test_runtime import LuaRuntime
from ai_non_runtime_acceptance import plain

SETUP = r'''
Config=require('Core.Config');World=require('Core.SwarmWorld')
Immune=require('Core.ImmuneSystem');Director=require('Core.ImmuneDirector')
Config.Gameplay.mapSeed=SEED
w=World.New('UPPER_AIRWAY');dt=w.config.movementStep
function counts(home)
 local rows={}
 for i=1,#w.map.regions do rows[i]={tcell=0,macrophage=0,total=0} end
 for _,im in ipairs(w.immunes) do
  local r=home and im.patrolHome and im.patrolHome.regionId or w.map:RegionAt(im.x,im.y)
  rows[r][im.kind]=rows[r][im.kind]+1;rows[r].total=rows[r].total+1
 end
 return rows
end
function tick(seconds,full)
 for _=1,math.ceil(seconds/dt) do
  if full then w:Update(dt) else w.time=w.time+dt;Immune.Update(w,dt) end
  for _,im in ipairs(w.immunes) do assert(w.map:Contains(im.x,im.y,im.radius),'immune crossed wall') end
 end
end
function reset(im,x,y)
 Director.Release(w,im);im.x,im.y=x,y;im.regionId=w.map:RegionAt(x,y)
 im.state='patrol';im.targetId,im.targetType=nil,nil;im.cooldown=0
 im._screenCellId=nil;im._patrolTimer=0;im._stuckTimer=0;im._homeRoute=nil
 im.returningHome=false;im.processingLoad=0
 im._patrolX,im._patrolY=x,y
end
function signature()
 local rows={}
 for _,im in ipairs(w.immunes) do rows[#rows+1]=string.format('%d:%s:%.9f:%.9f:%s:%s',
  im.id,im.kind,im.x,im.y,im.state,tostring(im.targetId)) end
 return table.concat(rows,'|')
end
'''

ASSAYS = r'''
local result={initial=counts(false),initialCount=#w.immunes}
assert(#w.immunes==10,'ordinary production start requires ten residents')
for _,r in ipairs(result.initial) do assert(r.tcell==1 and r.macrophage==1,'missing regional role') end
for _,im in ipairs(w.immunes) do
 assert(im.patrolHome and im.patrolHome.regionId==im.regionId)
 assert((im.x-w.player.x)^2+(im.y-w.player.y)^2>=(w.config.immuneSafeDistance+im.radius+w.player.radius)^2)
 local entry=false;for _,p in ipairs(w.map.immuneSpawns) do if p.x==im.x and p.y==im.y then entry=true end end
 assert(entry,'spawn must use a registered entrance')
end
-- Reinitialize on the same unchanged map/actors/RNG, then compare actual patrol.
local rng=w._rng
Immune.Init(w,Config.StartRegions[1]);local startRng=w._rng
tick(8);local first=signature()
w.time=0;w._rng=rng;Immune.Init(w,Config.StartRegions[1]);assert(w._rng==startRng)
tick(8);assert(signature()==first,'same-seed resident patrol replay drift')
for _,im in ipairs(w.immunes) do assert(Director.InPatrolArea(w,im,im.x,im.y),'idle patrol left home sector') end
result.patrolReplay=true
-- Three real infections in the starting area, then full World ticks.
local ordered={};for _,c in ipairs(w.cells) do ordered[#ordered+1]=c end
table.sort(ordered,function(a,b) return (a.x-w.player.x)^2+(a.y-w.player.y)^2<(b.x-w.player.x)^2+(b.y-w.player.y)^2 end)
for i=1,3 do w:_Infect(ordered[i],'fixture') end
local hot=ordered[1].regionId
tick(12,true);result.afterHotspot=counts(false)
for id,r in ipairs(result.afterHotspot) do if id~=hot then assert(r.total>=2,'early hotspot emptied a remote sector') end end
-- Actual clear at a second district, with every other resident left in place.
local m
for _,im in ipairs(w.immunes) do if im.kind=='macrophage' and im.patrolHome.regionId~=hot then m=im;break end end
reset(m,m.patrolHome.x,m.patrolHome.y)
w:_Release(ordered[1],1);local v=w.releasedViruses[#w.releasedViruses];v.x,v.y=m.x,m.y
local killed=w.stats.totalKilled
tick(3);assert(v.state=='CLEARED' and w.stats.totalKilled>=killed+1,'remote resident failed actual clear')
result.remoteClear=true
-- An overloaded hotspot cannot monopolize all finite reinforcements.
w.activeImmuneAlertLevel=5
for i=1,60 do Immune.Recruit(w,w.config.immuneCoverage.deploymentInterval) end
assert(#w.immunes==Director.PopulationLimit(w),'must reach finite budget when safe entrances remain')
result.reinforced=counts(true)
for _,r in ipairs(result.reinforced) do assert(r.tcell>=4 and r.macrophage>=4,'reinforcements abandoned a sector') end
-- All occupied/unsafe entrances postpone recruiting instead of teleporting.
local entrances=w.map.immuneSpawns;local all=w.immunes;w.immunes={all[1]}
w.map.immuneSpawns={{x=w.player.x,y=w.player.y}}
Immune.Recruit(w,w.config.immuneRecruitInterval);assert(#w.immunes==1)
w.map.immuneSpawns=entrances;w.immunes=all
result.unsafeDeferred=true
-- Respect a caller's explicit smaller/zero population cap.
w.activeImmuneAlertLevel=0
local cap=w.config.immuneMax;w.config.immuneMax=3;Immune.Init(w,Config.StartRegions[1]);assert(#w.immunes==3)
w.config.immuneMax=0;Immune.Init(w,Config.StartRegions[1]);assert(#w.immunes==0)
w.config.immuneMax=cap
result.explicitCaps=true
result.startBudgets={10}
for i=2,3 do
 Immune.Init(w,Config.StartRegions[i]);assert(#w.immunes==Config.StartRegions[i].flatImmuneCount)
 result.startBudgets[i]=#w.immunes
 for _,r in ipairs(counts(true)) do assert(r.tcell>=1 and r.macrophage>=1) end
end
return result
'''

RETURN_ASSAY = r'''
-- Isolate one actual resident, using a traversable route on production geometry.
Immune.Init(w,Config.StartRegions[1]);local im=w.immunes[1];w.immunes={im}
w.activeImmuneAlertLevel=0
local home=im.patrolHome;local Nav=require('Core.ImmuneNavigation');local away,route
for _,p in ipairs(w.map.immuneSpawns) do
 local d=math.sqrt((p.x-home.x)^2+(p.y-home.y)^2)
 if d>w.config.immuneCoverage.patrolRadius+1 and d<25 then
  local r=Nav.Route(w.map,p,home,im.radius)
  if r then away,route=p,r;break end
 end
end
assert(away,'production return fixture needs reachable outside point')
-- Move player far away; remove fixture infections before testing idle return.
for _,c in ipairs(w.cells) do c.state='HEALTHY' end
w.releasedViruses={};w._spatialActive=false
w.player.isHidden=true;reset(im,away.x,away.y)
local homeDistance=math.sqrt((im.x-home.x)^2+(im.y-home.y)^2)
tick(1);assert(im.returningHome and not im.targetId,'outside idle resident must return')
local firstDistance=math.sqrt((im.x-home.x)^2+(im.y-home.y)^2)
assert(firstDistance<homeDistance or im._homeRoute,'return must physically route')
-- Returning does not grant invulnerability or suppress ordinary local discovery.
w.player.isHidden=false;w.player.x,w.player.y=im.x,im.y
tick(dt);assert(im.targetType=='swarm' and im.targetId==w.player.id,'returning resident ignored local player')
local mass=w.player.mass;tick(3);assert(w.player.mass<mass,'resident did not make real contact attack')
w.player.isHidden=true
tick(1);assert(not im.targetId,'hidden player retained live target')
tick(65)
assert(not im.returningHome and Director.InPatrolArea(w,im,im.x,im.y),'resident failed to return')
return {actualChaseHit=true,physicalReturn=true,initialDistance=homeDistance}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', type=int, nargs='+', default=[314159, 271828, 161803])
    parser.add_argument('--output', type=Path, default=ROOT/'validation/immune-coverage-20261017')
    args = parser.parse_args()
    rows = []
    for seed in args.seeds:
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().print = lambda *a: None
        lua.globals().SEED = seed
        lua.execute("package.path='scripts/?.lua;'..package.path")
        try:
            lua.execute(SETUP)
            baseline = None
            if seed == args.seeds[0]:
                lua.execute("currentConfig=Config;currentDirector=Director;currentImmune=Immune;currentRng=w._rng")
                for name in ['Config', 'ImmuneDirector', 'ImmuneSystem']:
                    lua.globals().baselineSource = (ROOT / 'validation/immune-coverage-20261017/baseline/scripts/Core' / (name+'.lua')).read_text(encoding='utf-8-sig')
                    lua.execute("package.loaded['Core."+name+"']=assert(load(baselineSource))()")
                lua.execute("local c=require('Core.Config');w.config=c.Gameplay;require('Core.ImmuneSystem').Init(w,c.StartRegions[1])")
                baseline = plain(lua.execute("return {count=#w.immunes,regions=counts(false)}"))
                lua.execute("package.loaded['Core.Config']=currentConfig;package.loaded['Core.ImmuneDirector']=currentDirector;package.loaded['Core.ImmuneSystem']=currentImmune;w.config=currentConfig.Gameplay;w._rng=currentRng;Immune.Init(w,Config.StartRegions[1])")
            data = plain(lua.execute(ASSAYS))
            row = dict(seed=seed, passed=True, metrics=data)
            if baseline is not None:
                row['baseline'] = baseline
            print('PASS coverage', seed, flush=True)
            if seed == args.seeds[0]:
                # The first seed also exercises a real route and attack after pursuit.
                row['return'] = plain(lua.execute(RETURN_ASSAY))
                print('PASS return/contact', seed, flush=True)
        except Exception as exc:
            row = dict(seed=seed, passed=False, error=str(exc))
            print('FAIL', seed, str(exc), flush=True)
        rows.append(row)
    folder = args.output
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'coverage.json').write_text(json.dumps(dict(passed=all(r['passed'] for r in rows), results=rows,
        scope='Production v5 geometry; explicit seed, infection/release and contact arrangements. Not native/player acceptance.'),
        ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return int(any(not r['passed'] for r in rows))


if __name__ == '__main__':
    raise SystemExit(main())
