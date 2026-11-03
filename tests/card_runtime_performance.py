"""Production-map card CPU checks; native rendering/device FPS are excluded."""
import argparse
import hashlib
import json
import time
from mechanism_cards_regression import ROOT,SETUP,GROWTH_SETUP,EXTRA,LuaRuntime
from performance_regression import FIXTURE as SERIALIZER

OUT=ROOT/'validation/card-runtime-performance-20261018'
SETUP2=r'''
cfg.width,cfg.height,cfg.cellCount,cfg.mapGenerationVersion=production.width,production.height,production.cellCount,production.version
w=quietWorld('UPPER_AIRWAY');AI=require('Core.SplitVirusAI');Nav=require('Core.ImmuneNavigation')
function groups()
 w.maxPlayerSwarms=6
 for i=1,5 do
  local c=w.cells[i*150];local s=w:_CreateSwarm(c.x,c.y,20,false)
  w:_RefreshGroupShape(s);s.mergeGrace=1000
 end
end
'''
CASES={
 'recall':r'''
groups()
for i,s in ipairs(w.swarms) do s.x,s.y=w.player.x+(i-1)*.1,w.player.y;s.recallUntil=100 end
local original=w._DirectPathClear;local sweeps=0
w._DirectPathClear=function(self,...) sweeps=sweeps+1;return original(self,...) end
local result={};local t=os.clock()
for i=1,3000 do
 local v={x=w.player.x-(i%20)*.01,y=w.player.y,radius=.045}
 local owner,gap=A.RecallOwner(w,v);result[#result+1]={owner and owner.id,gap,v.tractionOwnerId}
end
return {ms=(os.clock()-t)*1000/3000,wallSweeps=sweeps,state=dump(result)}
''',
 'camouflage':r'''
groups();grant(w,'debris_camouflage')
for i=600,960 do w.cells[i].state='DEAD' end
w.cellGrid:Build(w.cells);w._cellSpatialActive=true
local t=os.clock();for _=1,600 do A.RefreshCamouflage(w,1/60) end
return {ms=(os.clock()-t)*1000/600,state=dump(w.swarms)}
''',
 'brain':r'''
groups();grant(w,'swarm_local_brain');grant(w,'debris_camouflage')
local t=os.clock();for _=1,90 do w:Update(1/60) end
return {ms=(os.clock()-t)*1000/90,state=snapshot(w)}
''',
 'large_hide_loss':r'''
groups()
for _,s in ipairs(w.swarms) do w:_AddParticles(s,3000-s.mass);s.mass=3000;w:_RefreshGroupShape(s) end
local t=os.clock();local particles=A.TakeMass(w,w.player,1500,'hide_node_loss')
return {ms=(os.clock()-t)*1000,removed=#particles,state=dump({w.viruses,particles,w.player,w.massLedger})}
''',
 'dispatch_static':r'''
groups();grant(w,'cluster_dispatch')
local s=w.swarms[2];s.radius=.2
local chosen
for _,c in ipairs(w.cells) do
 if not Nav.Clear(w.map,s,c,.2) and Nav.Route(w.map,s,c,.2) then chosen=c;break end
end
assert(chosen)
s.groupCommand={kind='hold',cellId=chosen.id,point={x=chosen.x,y=chosen.y},routeAt=0}
local original=Nav.Route;local calls=0
Nav.Route=function(...) calls=calls+1;return original(...) end
local t=os.clock()
for i=1,300 do
 w.time=i/60;local x,y=A.Movement(w,s,0,0,.5,1/60)
 -- Realise progress to avoid classifying an intentionally frozen fixture as stuck.
 s.x,s.y=w.map:Move(s.x,s.y,s.x+x/60,s.y+y/60,s.radius)
end
return {ms=(os.clock()-t)*1000/300,routeCalls=calls,legal=w.map:Contains(s.x,s.y,s.radius),distance=distance(s,chosen)}
''',
}

def runtime(baseline):
    lua=LuaRuntime(unpack_returned_tuples=True)
    lua.execute('package.path='+repr((ROOT/'scripts/?.lua').as_posix())+"..';'..package.path")
    if baseline:
        for name in ['AbilityRuntime','SplitVirusAI','SwarmWorld']:
            path=(OUT/'baseline'/(name+'.lua')).as_posix()
            lua.execute("package.preload['Core."+name+"']=function()return assert(loadfile("+repr(path)+"))()end")
    lua.execute("local c=require('Core.Config').Gameplay;production={width=c.width,height=c.height,cellCount=c.cellCount,version=c.mapGenerationVersion}")
    lua.globals().print=lambda *a:None
    lua.execute(SETUP+GROWTH_SETUP+EXTRA+SERIALIZER+SETUP2)
    return lua

def run(label):
    rows={}
    for name,code in CASES.items():
        result=dict(runtime(label=='before').execute(code).items())
        if 'state' in result:
            result['state_sha256']=hashlib.sha256(result.pop('state').encode()).hexdigest()
        rows[name]=result;print(name,result,flush=True)
    (OUT/(label+'.json')).write_text(json.dumps(rows,indent=2),encoding='utf8')
    if label!='before':
        before=json.loads((OUT/'before.json').read_text(encoding='utf8'))
        for name in ['recall','camouflage','brain','large_hide_loss']:
            assert rows[name]['state_sha256']==before[name]['state_sha256'],name+' authoritative state drift'
        assert rows['dispatch_static']['legal']
        assert rows['dispatch_static']['routeCalls']<before['dispatch_static']['routeCalls']
        assert rows['recall']['wallSweeps']<before['recall']['wallSweeps']

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--label',default='after')
    run(parser.parse_args().label)
