"""Exploration visibility, persistence, opaque masking and real scene integration."""
import json
from map_overview_regression import runtime, ROOT

SETUP=r'''
local Fog=require('Game.MapExploration')
function fogFixture()
 local player={id=1,x=12,y=12,mass=30,radius=.4}
 local world={width=100,height=100,player=player,currentControlledSwarmId=1,
  swarms={player,{id=2,x=90,y=90,mass=20}},map={seed=7,regions={},channels={}},
  viruses={{id=1,x=12,y=12},{id=2,x=90,y=90}},releasedViruses={{id=1,x=90,y=90,state='RELEASED'}},
  cells={{id=1,x=13,y=12,state='HEALTHY'},{id=2,x=90,y=90,state='HEALTHY'}},
  immunes={{id=1,x=14,y=12},{id=2,x=90,y=90}}}
 function world:SwarmById(id)for _,s in ipairs(self.swarms)do if s.id==id then return s end end end
 return Fog.New(),world
end
'''

CASES={
 'only controlled swarm reveals nearby terrain; remote units do not leak':r'''
local fog,world=fogFixture();fog:Observe(world)
assert(fog:IsExplored(12,12) and not fog:IsExplored(90,90) and not fog:IsExplored(0,0))
assert(not fog:IsExplored(-1,12) and not fog:IsExplored(100,12))
local map=require('Game.MapOverview').New();map:Capture(world,1,fog)
assert(#map.bins==1 and map.bins[1].count==1)
assert(#map.healthy==1 and map.healthy[1].x==13 and #map.immunes==1 and map.immunes[1].x==14)
world.player=world.swarms[2];world.currentControlledSwarmId=2;fog:Observe(world)
assert(fog:IsExplored(90,90) and fog:IsExplored(12,12) and not fog:IsExplored(50,50))
map:Capture(world,1,fog);local count=0;for _,b in ipairs(map.bins)do count=count+b.count end
assert(count==3 and #map.healthy==2 and #map.immunes==2)
''',
 'exploration only grows, has a soft edge and resets for a new world with the same seed':r'''
local fog,world=fogFixture();fog:Observe(world)
local previous={};local edge=false
for key,level in pairs(fog.coverage)do previous[key]=level;if level>0 and level<8 then edge=true end end
assert(edge)
world.player.x,world.player.y=35,35;fog:Observe(world)
for key,level in pairs(previous)do assert(fog.coverage[key]>=level)end
assert(fog:IsExplored(12,12) and fog:IsExplored(35,35) and not fog:IsExplored(24,24))
local other=select(2,fogFixture());other.player.x,other.player.y=80,80
fog:Observe(other);assert(not fog:IsExplored(12,12) and fog:IsExplored(80,80))
''',
 'fog mask covers unknown pixels fully and caches its batched rows':r'''
local fog,world=fogFixture();fog:Observe(world)
local black=false;local seen=0
function nvgShapeAntiAlias(vg,value)assert(value==0,'native NanoVG expects an integer flag')end
function nvgRGBA(r,g,b,a)return {r,g,b,a}end
function nvgFillColor(vg,c)assert(c[1]==0 and c[2]==0 and c[3]==0);if c[4]==255 then black=true end end
fog:Draw({},{x=0,y=0,w=600,h=600},5,0,0)
assert(black and not fog.dirty)
local cached=fog.maskRuns
fog:Draw({},{x=0,y=0,w=600,h=600},5,0,0);assert(fog.maskRuns==cached)
for level,runs in pairs(cached)do
 for _,r in ipairs(runs)do
  if r.x<=90 and r.x+r.w>90 and r.y<=90 and r.y+r.h>90 then assert(level==0);seen=seen+1 end
  if r.x<=12 and r.x+r.w>12 and r.y<=12 and r.y+r.h>12 then error('known centre must be clear')end
 end
end
assert(seen==1)
''',
 'scene remembers travel without opening map, tracks substeps and clears only on run reset':r'''
Config.Gameplay.mapGenerationVersion=1;Config.Gameplay.width=80;Config.Gameplay.height=96;Config.Gameplay.cellCount=72
local game,sim=sceneFixture(true);local fog=game.exploration
local sx,sy=sim.world.player.x,sim.world.player.y
assert(fog:IsExplored(sx,sy))
local original=sim.Update
sim.Update=function(self,dt,beforeStep)
 for _,p in ipairs({{24,30},{40,45},{65,70}})do beforeStep(self.world);self.world.player.x,self.world.player.y=p[1],p[2]end
end
game:Update(.1);sim.Update=original
assert(fog:IsExplored(sx,sy) and fog:IsExplored(24,30) and fog:IsExplored(40,45) and fog:IsExplored(65,70))
assert(game:ToggleMap());local history=fog.coverage;game:CancelMap()
assert(fog.coverage==history and fog:IsExplored(24,30))
assert(game:ToggleMap());assert(fog.coverage==history);game:CancelMap()
Bus.Emit(Bus.Events.SIM_RESET,{})
assert(not fog:IsExplored(24,30) and fog:IsExplored(65,70))
game:Destroy()
''',
 'pullback fog is drawn at full opacity above both fading scene layers':r'''
Config.Gameplay.mapGenerationVersion=1;Config.Gameplay.width=26;Config.Gameplay.height=32;Config.Gameplay.cellCount=72
local game,sim=sceneFixture(true);game:Update(.016);assert(game:ToggleMap());game:Update(.1)
local alpha,stack=1,{}
function nvgSave()stack[#stack+1]=alpha end
function nvgRestore()alpha=table.remove(stack)end
function nvgGlobalAlpha(vg,value)alpha=value end
local drawn=false;local ring=false
game.cellView.DrawWorld=function()end
game.mapView.Draw=function()assert(alpha<1)end
game.exploration.Draw=function()near(alpha,1);drawn=true end
game.mapView.DrawPlayer=function()assert(drawn);ring=true end
game:Render({});assert(drawn and ring and #stack==0)
game:Destroy()
''',
}

if __name__=='__main__':
 passed=[]
 for name,code in CASES.items():
  lua=runtime();lua.globals().print=lambda *args:None
  lua.execute(SETUP+code);passed.append(name);print('PASS '+name,flush=True)
 out=ROOT/'validation/map-overview';out.mkdir(parents=True,exist_ok=True)
 (out/'exploration.json').write_text(json.dumps({'passed':passed,
  'scope':'Real Lua exploration and scene composition; native pixels/Yoga unverified'},indent=2),encoding='utf8')
 print(f'{len(passed)} exploration checks passed')
