"""Real simulation/event bridge/audio adapter; only engine playback is mocked.

Uses exact WAV lengths, validates actual actions and lifecycle boundaries.
This does not verify native audibility, mixing or the environment loop seam.
"""
from pathlib import Path
import hashlib
import json
import wave
from chase_music_regression import runtime as base_runtime
from swarm_growth_regression import GROWTH_SETUP
from mechanism_cards_regression import EXTRA

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation/sfx-integration-20261017'

SETUP = r'''
SOUND_AMBIENT='Ambient'
function playCount(id)
 local count=0
 for _,call in ipairs(calls) do if call.path=='audio/'..id..'.wav' then count=count+1 end end
 return count
end
local createScene=Scene
function Scene()
 local scene=createScene();local create=scene.CreateChild
 function scene:CreateChild(name)
  local node=create(self,name);local component=node.CreateComponent
  function node:CreateComponent(kind)
   local source=component(self,kind);local play=source.Play
   function source:Play(sound,frequency,gain)
    play(self,sound,frequency,gain);calls[#calls].path=sound.path
   end
   return source
  end
  return node
 end
 return scene
end
function setup()
 local sim=newSim('UPPER_AIRWAY',true)
 local audio=Audio.New();audio:SetMode('game');audio:BindSim(sim)
 return sim,audio,sim.world
end
function frame(audio,sim,dt)
 now=now+(dt or .05);audio:Update(dt or .05,sim)
end
function forward(sim,audio,dt)
 sim:ConsumeEvents();frame(audio,sim,dt)
end
'''

CASES = {
    'real lethal immune attack preserves the old control and listener after automatic switch': r'''
local w,im=immuneFixture('macrophage');assert(w:Split())
local old=w.player;local oldId=old.id;local x,y=old.x,old.y
local child=w.swarms[2];local q=w.map.startPoints.UPPER_AIRWAY;place(w,child,q.x,q.y)
w:DamageSwarm(old.id,old.mass-1)
local sim=Sim.New();sim.world=w;sim.started=true;sim.paused=false;sim.pauseReasons={}
w.abilityRunId=sim.cards.runId
local a=Audio.New();a:SetMode('game');a:BindSim(sim)
im.x,im.y=x,y;im.state='attack';im.targetType='swarm';im.targetId=oldId;im.attackTimer=cfg.movementStep
Immune.Update(w,cfg.movementStep)
assert(w.currentControlledSwarmId==child.id)
local hit
for _,event in ipairs(w.events) do if event.name=='immune_attack' then hit=event.audio.payload end end
assert(hit and hit.controlId==oldId);near(hit.listenerX,x);near(hit.listenerY,y)
forward(sim,a);assert(playCount('swarm_hit')==1 and playCount('swarm_cleared')==1)
''',
    'actual infection, batch release, pair merge and nonterminal swarm loss': r'''
local sim,a,w=setup();local c=w.cells[1]
place(w,w.player,c.x+c.radius+.05,c.y)
w:_Infect(c,'released');forward(sim,a)
assert(playCount('infection_complete')==1)
w:_Release(c,3);forward(sim,a,.2);assert(playCount('release_batch')==1)
assert(sim:Split());frame(a,sim,.2)
local main,child=w.swarms[1],w.swarms[2]
main.launchTimer,main.mergeGrace,child.launchTimer,child.mergeGrace=0,0,0,0
place(w,child,main.x,main.y)
assert(w:_Merge(main,child));forward(sim,a,.2);assert(playCount('swarm_merge')==1)
w.splitCooldown=0;assert(sim:Split());frame(a,sim,.2)
child=w.swarms[2];w:DamageSwarm(child.id,child.mass);forward(sim,a,.2)
assert(playCount('swarm_cleared')==1 and not sim.ending)
''',
    'legal empty pulse succeeds; cooldown and failed split reject without success audio': r'''
local sim,a,w=setup();w.releasedViruses={}
local rng=w._rng;local n,reason=sim:AbsorbNearby();assert(n==0 and reason==nil)
frame(a,sim);assert(playCount('absorb_pulse')==1 and playCount('action_denied')==0)
assert(w._rng==rng)
sim:AbsorbNearby();frame(a,sim);assert(playCount('action_denied')==1 and playCount('absorb_pulse')==1)
w.splitCooldown=10;assert(not sim:Split());frame(a,sim,.3)
assert(playCount('swarm_split')==0 and playCount('action_denied')==2)
''',
    'actual successful split and switch forward once before normal event consumption': r'''
local sim,a,w=setup();assert(sim:Split());frame(a,sim)
assert(playCount('swarm_split')==1)
assert(sim:SwitchControl());frame(a,sim,.2);assert(playCount('switch_control')==1)
forward(sim,a,.3);assert(playCount('swarm_split')==1 and playCount('switch_control')==1)
''',
    'actual mass absorption merges twenty particles into one short audio cue': r'''
local sim,a,w=setup();local mass=w.player.mass
releaseAt(w,20,w.player.x,w.player.y)
assert(sim:AbsorbNearby()==20);frame(a,sim)
assert(w.player.mass==mass+20 and playCount('virus_absorb')==1 and playCount('absorb_pulse')==1)
''',
    'many consumed simulation steps keep immutable snapshots and deduplicate batches': r'''
local sim,a,w=setup();local batch
local token=Bus.On(Bus.Events.AUDIO_WORLD,function(p) batch=p end)
w:Emit('release_batch',{count=4,x=w.player.x,y=w.player.y});sim:ConsumeEvents()
local first=batch;assert(#w.events==0)
w:Emit('infection_complete',{cellId=w.cells[1].id});sim:ConsumeEvents()
local oldx=first.events[1].payload.x;w.player.x=w.player.x+.5
assert(first.events[1].payload.x==oldx)
Bus.Emit(Bus.Events.AUDIO_WORLD,first);frame(a,sim)
assert(playCount('release_batch')==1 and playCount('infection_complete')==1)
Bus.Off(token)
''',
    'card confirmation and alert use separate once-only authoritative entries': r'''
local sim,a,w=setup();assert(sim:AcquireTestCard('discrete_recall'))
local notice=sim.cardNotice;Bus.Emit('cards:acquired',notice)
forward(sim,a);assert(playCount('card_acquired')==1 and playCount('alert_up')==1)
Bus.Emit('cards:acquired',notice);frame(a,sim,1);assert(playCount('card_acquired')==1)
sim:ContinueAfterCard();frame(a,sim,.1)
''',
    'actual skill requests: no sound before ownership; dash recall decoy and commands': r'''
local sim,a,w=setup();local p=w.player
assert(not sim:UseSkill('emergency_dash',p.id));frame(a,sim)
assert(playCount('action_denied')==1 and playCount('skill_dash')==0)
for _,id in ipairs({'emergency_dash','discrete_recall','shed_decoy','cluster_dispatch','local_flow'}) do grant(w,id) end
p.hasMoveDirection=true;p.lastMoveX,p.lastMoveY=1,0
assert(sim:UseSkill('emergency_dash',p.id));frame(a,sim,.5);assert(playCount('skill_dash')==1)
releaseAt(w,1,p.x,p.y)
assert(sim:UseSkill('discrete_recall',p.id));frame(a,sim,.5);assert(playCount('skill_recall')==1)
assert(sim:UseSkill('shed_decoy',p.id));frame(a,sim,.5);assert(playCount('skill_decoy')==1)
assert(w:Split())
assert(sim:UseSkill('cluster_dispatch',p.id,{command='gather'}));frame(a,sim,.5)
w.abilities.cooldowns.cluster_dispatch=0
assert(sim:UseSkill('cluster_dispatch',p.id,{command='hold'}));frame(a,sim,.5)
assert(playCount('dispatch_gather')==1 and playCount('dispatch_hold')==1)
local rng=w._rng
assert(sim:UseSkill('local_flow',p.id,{x=p.x+.2,y=p.y}));frame(a,sim,.5)
assert(playCount('flow_redirect')==1 and w._rng==rng)
''',
    'anchor edge direction and movement cancellation; same-frame toggle takes final state': r'''
local sim,a,w=setup();local p=w.player;grant(w,'swarm_anchor')
assert(sim:UseSkill('swarm_anchor',p.id));frame(a,sim);assert(playCount('anchor_on')==1)
w:SetMovement(1,0);A.Movement(w,p,1,0,1,.05);forward(sim,a,.2)
assert(not p.anchored and playCount('anchor_off')==1)
assert(sim:UseSkill('swarm_anchor',p.id));assert(sim:UseSkill('swarm_anchor',p.id))
frame(a,sim,.2);assert(playCount('anchor_on')==1 and playCount('anchor_off')==2)
''',
    'actual hiding covering relay deployment recovery and takeover formation': r'''
local sim,a,w=setup();local p=w.player;local c=w.cells[1]
c.state='PRODUCTIVE';c.releaseCount=0;c.pendingProduction=0
place(w,p,c.x+c.radius+.05,c.y)
for _,id in ipairs({'node_hide','node_cover','membrane_glide','node_takeover'}) do grant(w,id) end
assert(sim:UseSkill('node_hide',p.id,{cellId=c.id}));frame(a,sim);assert(playCount('hide_enter')==1)
w:KillCell(c,'immune');forward(sim,a,.2);assert(playCount('hide_exit')==1)
local c2=w.cells[2];c2.state='PRODUCTIVE';c2.releaseCount=1;place(w,p,c2.x+c2.radius+.05,c2.y)
assert(sim:UseSkill('node_cover',p.id,{cellId=c2.id}));frame(a,sim,.5);assert(playCount('node_cover')==1)
local c3=w.cells[3];c3.state='HEALTHY';c3.exposure=0;c3._charge=0;c3._groupCharge=0;c3._releasedCharge=0
place(w,p,c3.x+c3.radius+.05,c3.y);w:_AccumulateExposure(.5);w:_InfectCells()
assert(sim:UseSkill('membrane_glide',p.id,{cellId=c3.id}));frame(a,sim,.5);assert(playCount('glide_start')==1)
assert(not sim:UseSkill('membrane_glide',p.id,{cellId=c3.id}));frame(a,sim,.2);assert(playCount('glide_start')==1)
assert(sim:AbsorbNearby()>=3);place(w,p,c2.x+c2.radius+.05,c2.y)
assert(sim:UseSkill('node_takeover',p.id,{cellId=c2.id}));frame(a,sim,.5);assert(playCount('node_takeover')==0)
w:_Release(c2,5);A.AfterRelease(w,c2);forward(sim,a,.5);assert(playCount('node_takeover')==1)
''',
    'camouflage transition sounds once while held; new binding does not fake an edge': r'''
local sim,a,w=setup();local p=w.player;local c=w.cells[1];c.state='DEAD'
place(w,p,c.x,c.y);grant(w,'debris_camouflage')
A.RefreshCamouflage(w,3.1);forward(sim,a);assert(playCount('camouflage_on')==1)
for i=1,8 do A.RefreshCamouflage(w,1);forward(sim,a,1) end
assert(playCount('camouflage_on')==1)
a:BindSim(sim);frame(a,sim);assert(playCount('camouflage_on')==1)
''',
    'hit semantics, shield exclusivity and canceled windup': r'''
local sim,a,w=setup();local p=w.player;local c=w.cells[1]
w:Emit('immune_attack',{immuneId=1,swarmId=p.id,killed=0,x=p.x,y=p.y});w:Emit('immune_clear',{immuneId=1,virusId=1,x=p.x,y=p.y})
w:Emit('node_attack',{immuneId=1,cellId=c.id,shielded=true,x=c.x,y=c.y});forward(sim,a)
assert(playCount('shield_block')==1 and playCount('node_hit')==0 and playCount('swarm_hit')==0)
w:Emit('node_attack',{immuneId=1,cellId=c.id,shielded=false,x=c.x,y=c.y});w:Emit('immune_attack',{immuneId=1,swarmId=p.id,killed=1,x=p.x,y=p.y})
forward(sim,a,.3);assert(playCount('node_hit')==1 and playCount('swarm_hit')==1)
w:Emit('node_attack_start',{immuneId=99,cellId=c.id});forward(sim,a,.3);assert(playCount('node_warning')==0)
w.immunes={{id=99,state='attack',targetType='cell',targetId=c.id}}
w:Emit('node_attack_start',{immuneId=99,cellId=c.id});forward(sim,a,.3);assert(playCount('node_warning')==1)
''',
    'failure wins same frame, keeps full tail, and replays after immediate restart': r'''
local sim,a,w=setup();frame(a,sim,1)
w:Emit('immune_attack',{swarmId=w.player.id,killed=2});w:DamageSwarm(w.player.id,w.player.mass)
sim:ConsumeEvents();sim:CheckOutcome(0);frame(a,sim)
assert(playCount('ending_defeat')==1 and playCount('swarm_hit')==0 and playCount('swarm_cleared')==0)
frame(a,sim,.5);assert(sources.DefeatSFX:IsPlaying() and not sources.MicroAmbience:IsPlaying())
assert(not sources.MusicSource:IsPlaying())
frame(a,sim,1.4);assert(not sources.DefeatSFX:IsPlaying())
sim:init();sim:StartRun('UPPER_AIRWAY',true);a:BindSim(sim);frame(a,sim,.1)
assert(not a.endingActive and sources.MicroAmbience:IsPlaying())
sim:FinishRun('extinct');frame(a,sim);assert(playCount('ending_defeat')==2)
sim:init();sim:StartRun('UPPER_AIRWAY',true);a:BindSim(sim);sim:FinishRun('victory');frame(a,sim)
assert(playCount('ending_defeat')==2 and not sources.DefeatSFX:IsPlaying())
frame(a,sim,1.8);assert(not sources.MicroAmbience:IsPlaying())
''',
    'ambience loop survives pauses and switching; menu fades out and destroy unsubscribes': r'''
local sim,a,w=setup();frame(a,sim,1);assert(sources.MicroAmbience.plays==1)
near(sources.MicroAmbience.gain,.3)
sim:SetPaused('cards',true);frame(a,sim,1);near(sources.MicroAmbience.gain,.3*.35)
assert(sources.MicroAmbience.plays==1)
sim:SetPaused('cards',false);frame(a,sim,1);near(sources.MicroAmbience.gain,.3)
for i=1,95 do frame(a,sim,1) end;assert(sources.MicroAmbience.plays==1)
a:SetMode('menu');frame(a,sim,.15);assert(sources.MicroAmbience:IsPlaying())
frame(a,sim,.16);assert(not sources.MicroAmbience:IsPlaying())
a:Destroy();Bus.Emit(Bus.Events.AUDIO_DENIED,{runId=w.abilityRunId});assert(#a.effects.queue==0)
for _,s in pairs(sources) do assert(not s.playing) end
''',
    'fixed capacity, priority, distant culling and real-time per-node rate limits': r'''
local sim,a,w=setup();local fx=a.effects;local p={x=0,y=0,listenerX=0,listenerY=0}
local n=0;for _ in pairs(sources) do n=n+1 end
for i=1,300 do p.cellId=i;fx:Queue('release_batch',p) end
assert(#fx.queue<=128);frame(a,sim);assert(playCount('release_batch')==1)
for _,slot in ipairs(fx.slots) do slot.source:Play(fx.sounds.release_batch,0,.1);slot.priority=1 end
fx:Queue('tail_preserve',{swarmId=1});frame(a,sim);assert(playCount('tail_preserve')==1)
local after=0;for _ in pairs(sources) do after=after+1 end;assert(after==n)
local distant={cellId=999,x=100,y=100,listenerX=0,listenerY=0}
fx:Queue('cell_dead',distant);frame(a,sim,1);assert(playCount('cell_dead')==0)
fx:ClearEffects();p.cellId=1;fx:Queue('node_hit',p);frame(a,sim);local count=playCount('node_hit')
fx:Queue('node_hit',p);frame(a,sim,.1);assert(playCount('node_hit')==count)
p.cellId=2;fx:Queue('node_hit',p);frame(a,sim,.1);assert(playCount('node_hit')==count+1)
''',
    'stale run batches and missing sound resources cannot leak or affect simulation': r'''
local sim,a,w=setup();local previous=w.abilityRunId
sim:init();sim:StartRun('UPPER_AIRWAY',true);a:BindSim(sim)
Bus.Emit(Bus.Events.AUDIO_WORLD,{runId=previous,events={{sequence=999,name='split',payload={}}}})
frame(a,sim);assert(playCount('swarm_split')==0)
local rng=sim.world._rng;local mass=sim.world.player.mass
a.effects.sounds.swarm_split=nil;assert(sim:Split());frame(a,sim)
assert(sim.world.player.mass<mass and sim.world._rng==rng)
''',
}


def runtime():
    lua=base_runtime()
    for path in (ROOT/'assets/audio').glob('*.wav'):
        with wave.open(str(path),'rb') as w:
            lua.globals().assetLengths['audio/'+path.name]=w.getnframes()/w.getframerate()
    lua.execute(GROWTH_SETUP)
    lua.execute(EXTRA)
    lua.execute(SETUP)
    return lua


def main():
    results=[]
    for name,code in CASES.items():
        try:
            runtime().execute(code)
            results.append(dict(name=name,passed=True))
            print('PASS:',name,flush=True)
        except Exception as error:
            results.append(dict(name=name,passed=False,error=str(error)))
            print('FAIL:',name,str(error),flush=True)
    assets=json.loads((OUT/'assets.json').read_text('utf-8'))
    assert len(assets)==33
    for item in assets:
        path=ROOT/'assets/audio'/item['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
        assert Path(str(path)+'.meta').is_file()
    paths=['Core/Config.lua','Core/WorldAudioEvents.lua','Core/GameplaySounds.lua','Core/GameAudio.lua',
           'Core/EventBus.lua','Core/SimState.lua','Core/AbilityRuntime.lua','Core/SwarmWorld.lua',
           'Core/ImmuneSystem.lua','UI/SkillControls.lua','main.lua']
    report=dict(passed=all(r['passed'] for r in results),results=results,
                scope=__doc__,assetCount=len(assets),source_sha256={
                    'scripts/'+p:hashlib.sha256((ROOT/'scripts'/p).read_bytes()).hexdigest() for p in paths})
    (OUT/'regression.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"{sum(r['passed'] for r in results)}/{len(results)} passed; 33 exact WAVs and metadata checked.")
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
