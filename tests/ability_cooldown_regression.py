"""Actual Lua ability validation: rejected casts preserve resources and cooldowns."""
from mechanism_cards_regression import ROOT, SETUP, GROWTH_SETUP, EXTRA, LuaRuntime

HELPERS = r'''
function rejected(w,id,target,request)
 local s=w.player;local mass=s.mass;local cd=w.abilities.cooldowns[id]
 local used=eventCount(w,'skill_used');s.camouflaged=true
 local ok,reason=skill(w,id,target,request)
 assert(not ok and type(reason)=='string',id..' should reject')
 assert(w.abilities.cooldowns[id]==cd and not w.abilities.requests[request])
 assert(s.mass==mass and s.camouflaged and eventCount(w,'skill_used')==used)
 return reason
end
function flowingPosition(w)
 for y=.5,w.map.height-.5,.5 do for x=.5,w.map.width-.5,.5 do
  if w.map:Contains(x,y,w.player.radius) then
   local fx,fy=w.map:FlowAt(x,y,w.time)
   if fx*fx+fy*fy>1e-6 then return x,y,fx,fy end
  end
 end end
 error('fixture needs a real flow region')
end
'''

TESTS = {
    'production calm spawn rejects flow without replacing an existing field; retry succeeds in water': r'''
cfg.mapGenerationVersion=5
-- Restore production dimensions overridden by the historical SETUP.
local flat=require('Core.FlatMapConfig');cfg.width,cfg.height,cfg.cellCount=flat.width,flat.height,flat.cellCount
cfg.mapSeed=314159
local w=quietWorld('UPPER_AIRWAY');grant(w,'local_flow');local s=w.player
local fx,fy=w.map:FlowAt(s.x,s.y,w.time);near(fx,0);near(fy,0)
local previous={x=-10,y=-10,ux=1,uy=0,radius=3,expiresAt=10};w.map.flowOverride=previous
assert(rejected(w,'local_flow',{x=s.x+.05,y=s.y},'retry-flow'):find('组织流'))
assert(w.map.flowOverride==previous)
local x,y,vx,vy=flowingPosition(w);place(w,s,x,y);local speed=math.sqrt(vx*vx+vy*vy)
assert(skill(w,'local_flow',{x=x-vx/speed*.05,y=y-vy/speed*.05},'retry-flow'))
near(w.abilities.cooldowns.local_flow-w.time,25)
local ax,ay=w.map:FlowAt(x,y,w.time);near(ax,-vx);near(ay,-vy)
near(math.sqrt(ax*ax+ay*ay),speed)
''',
    'dash cooldown is exactly four simulation seconds and rejected repeats do not extend it': r'''
local w=quietWorld();grant(w,'emergency_dash');w:SetMovement(1,0);w:SetMovement(0,0)
assert(skill(w,'emergency_dash',nil,'dash-one'));near(A.State(w,'emergency_dash',w.player).cooldown,4)
w.time=3.999;rejected(w,'emergency_dash',nil,'dash-two')
w.time=4;A.Update(w,0);assert(skill(w,'emergency_dash',nil,'dash-two'))
near(w.abilities.cooldowns.emergency_dash,8)
''',
    'dash fully blocked at a real wall rejects; turning into open space succeeds': r'''
local w=quietWorld();grant(w,'emergency_dash');local s=w.player
-- Reach the rightmost wall on the region's horizontal centreline.
local region=w.map.regions[5];place(w,s,region.x,region.y)
for _=1,400 do local x,y=w.map:Move(s.x,s.y,s.x+.1,s.y,s.radius);place(w,s,x,y) end
w:SetMovement(1,0);w:SetMovement(0,0)
assert(rejected(w,'emergency_dash',nil,'wall-dash'):find('阻挡'))
assert(not s.dashUntil)
w:SetMovement(-1,0);w:SetMovement(0,0);assert(skill(w,'emergency_dash',nil,'wall-dash'))
local before=s.x;w:Update(cfg.movementStep);assert(s.x<before)
''',
    'recall rejects empty expired terminal and out-of-range targets; valid retry really pulls': r'''
local w=quietWorld();grant(w,'discrete_recall');local s=w.player
assert(rejected(w,'discrete_recall',nil,'recall'):find('游离病毒'))
local v=releaseAt(w,1,s.x+2.5,s.y)[1]
v.age=v.lifetime;rejected(w,'discrete_recall',nil,'recall');v.age=0
for _,state in ipairs({'ABSORBED','CLEARED','LOST','CONVERTED'}) do
 v.state=state;rejected(w,'discrete_recall',nil,'recall')
end
v.state='RELEASED';local x,y=v.x,v.y;v.x,v.y=s.x+10,s.y
rejected(w,'discrete_recall',nil,'recall');v.x,v.y=x,y
assert(skill(w,'discrete_recall',nil,'recall'));near(w.abilities.cooldowns.discrete_recall-w.time,18)
local before=distance(s,v);w:_MoveReleased(cfg.movementStep);assert(distance(s,v)<before)
''',
    'recall rejects a nearby virus separated by a real wall': r'''
local w=quietWorld();grant(w,'discrete_recall');local s=w.player
local v=releaseAt(w,1,s.x,s.y)[1];local found=false
for y=.5,31.5,.5 do for x=.5,25.5,.5 do
 if not found and w.map:Contains(x,y,s.radius) then
  for dy=-3,3,.5 do for dx=-3,3,.5 do
   local tx,ty=x+dx,y+dy
   if not found and dx*dx+dy*dy<9 and w.map:Contains(tx,ty,v.radius)
    and not w:_DirectPathClear(x,y,tx,ty,v.radius) then
    place(w,s,x,y);v.x,v.y=tx,ty;found=true
   end
  end end
 end
end end
assert(found,'real occluded target fixture missing')
rejected(w,'discrete_recall',nil,'blocked-recall');assert(not s.recallUntil)
''',
    'dispatch with no eligible group fails without resetting old intentions': r'''
local w=quietWorld();grant(w,'cluster_dispatch')
rejected(w,'cluster_dispatch',{command='gather'},'dispatch')
assert(w:Split());local child=w.swarms[2];local old={kind='hold'};child.groupCommand=old
for _,field in ipairs({'anchored','isHidden','relayCellId','rescueUntil'}) do
 child[field]=field=='rescueUntil' and 10 or true
 rejected(w,'cluster_dispatch',{command='gather'},'dispatch');assert(child.groupCommand==old)
 child[field]=nil
end
assert(skill(w,'cluster_dispatch',{command='gather'},'dispatch'));assert(child.groupCommand.kind=='gather')
''',
    'trail cannot turn on at minimum mass but can still turn off': r'''
local w=quietWorld();grant(w,'infection_trail');local s=w.player
w:DamageSwarm(s.id,s.mass-3);rejected(w,'infection_trail',nil,'trail');assert(not s.trailEnabled)
s.trailEnabled=true;assert(skill(w,'infection_trail',nil,'trail'));assert(not s.trailEnabled)
''',
    'node target failures preserve cooldown mass and requests; valid buffs remain usable': r'''
local w=quietWorld();local c=unitCell(w);local s=w.player
for _,id in ipairs({'node_hide','node_cover','node_takeover','membrane_glide','shed_decoy','swarm_anchor','merge_seed'}) do grant(w,id) end
c.state='DEAD';w.cells={c}
for _,id in ipairs({'node_hide','node_cover','node_takeover','membrane_glide'}) do
 rejected(w,id,{cellId=c.id},'dead-'..id)
end
c.state='HEALTHY';rejected(w,'membrane_glide',{cellId=c.id},'untouched')
c.state='PRODUCTIVE';c.releaseCount=1;place(w,s,c.x+.7,c.y)
assert(skill(w,'node_takeover',{cellId=c.id},'reservation'));assert(c.takeoverReservation)
w:KillCell(c,'immune');assert(not w.abilities.cooldowns.node_takeover)
assert(skill(w,'swarm_anchor',nil,'anchor'));assert(s.anchored)
assert(skill(w,'merge_seed',nil,'merge'));assert(not w.abilities.mergeSeedEnabled)
assert(skill(w,'shed_decoy',nil,'decoy'));assert(#w.releasedViruses==4)
''',
}

def run():
    passed = 0
    for name, code in TESTS.items():
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute('package.path=' + repr(str(ROOT / 'scripts/?.lua').replace('\\', '/')) + "..';'..package.path")
        try:
            lua.execute(SETUP + GROWTH_SETUP + EXTRA + HELPERS + code)
            print('PASS', name)
            passed += 1
        except Exception as error:
            print('FAIL', name, str(error))
    print(f'Ability cooldowns: {passed}/{len(TESTS)}')
    return passed == len(TESTS)

if __name__ == '__main__':
    raise SystemExit(0 if run() else 1)
