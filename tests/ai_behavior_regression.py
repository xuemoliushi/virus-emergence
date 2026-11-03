"""Three AI behavior fixes using real Core modules and explicitly positioned fixtures.

No native window or full-run balance acceptance is implied. Existing historical
26x32 geometry is used for isolated contact/ability checks.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.tmp/test-deps'))
from mechanism_cards_regression import ROOT, SETUP, GROWTH_SETUP, EXTRA, LuaRuntime

COMMON = r'''
AI=require('Core.SplitVirusAI')
Director=require('Core.ImmuneDirector')
local commandImmunePrototype=nil
function commandFixture(brain)
 if not commandImmunePrototype then local _,im=immuneFixture('macrophage');commandImmunePrototype=im end
 local im={};for k,v in pairs(commandImmunePrototype) do im[k]=v end
 local w=manyGroups(2)
 grant(w,'cluster_dispatch')
 if brain then grant(w,'swarm_local_brain') end
 local main,s=w.player,w.swarms[2]
 for _,g in ipairs(w.swarms) do w:DamageSwarm(g.id,g.mass-20) end
 place(w,main,13,3.1);place(w,s,12.9,27.4)
 local spare=w.cells[2]
 local c=unitCell(w,1,s.x+2,s.y);w.cells={c}
 cfg.playerFlowInfluence,cfg.splitFlowInfluence,cfg.inactiveDrift=0,0,0
 assert(skill(w,'cluster_dispatch',{command='hold'}))
 s.groupCommand.cellId=c.id;s.groupCommand.point={x=c.x-c.radius-s.radius-.1,y=c.y}
 return w,s,c,im,spare
end
'''

TESTS = {
    'base AI: discovery range stays narrow; known targets use retention range': r'''
local w,im=immuneFixture('macrophage');w.cells={}
assert(not next(w.abilities.owned) and w.activeImmuneAlertLevel==0)
local s=w.player;local extra=cfg.immuneForgetExtra
place(w,s,im.x+im.detectionRange+s.radius+extra*.5,im.y)
Immune.Update(w,cfg.movementStep);assert(not im.targetId)
place(w,s,im.x+im.detectionRange+s.radius-.1,im.y)
Immune.Update(w,cfg.movementStep);assert(im.state=='locked' and im.targetId==s.id)
Immune.Update(w,cfg.movementStep);assert(im.state=='warning')
local warning=im.warningTimer;local mass=s.mass
place(w,s,im.x+im.detectionRange+s.radius+extra*.5,im.y)
Immune.Update(w,cfg.movementStep)
assert(im.targetId==s.id and im.warningTimer<warning and im.warningTimer>0 and s.mass==mass)
assert(im._lastSeen.x==s.x and eventCount(w,'immune_lock')==1)
place(w,s,im.x+im.detectionRange+s.radius+extra+.2,im.y)
Immune.Update(w,cfg.movementStep);assert(not im.targetId and im.targetX==nil and im.state=='patrol')
Immune.Update(w,cfg.movementStep);assert(not im.targetId)
checkConservation(w,true)
''',
    'base AI: LOS loss searches only the last observation; hidden targets unlock': r'''
local w,im=immuneFixture('macrophage');w.cells={};w.activeImmuneAlertLevel=6
-- Find a legal point behind actual tissue geometry within the retention radius.
local found=false;local r=im.detectionRange+cfg.immuneForgetExtra+w.player.radius
local hiddenX,hiddenY=0,0
for y=1,w.height-1 do
 if found then break end
 for x=1,w.width-1 do
  if found then break end
  if w.map:Contains(x,y,math.max(im.radius,w.player.radius)) then
   for index=1,24 do
    local a=index*math.pi*2/24;local tx,ty=x+math.cos(a)*(r-.2),y+math.sin(a)*(r-.2)
    if w.map:Contains(tx,ty,w.player.radius) and not w:_DirectPathClear(x,y,tx,ty,0) then
     im.x,im.y=x,y;im.regionId=w.map:RegionAt(x,y)
     im._patrolX,im._patrolY=x,y;place(w,w.player,x,y)
     hiddenX,hiddenY=tx,ty;found=true;break
    end
   end
  end
 end
end
assert(found,'fixture must contain a real obstructed point')
Immune.Update(w,cfg.movementStep);local seen=im._lastSeen
assert(im.targetId==w.player.id)
place(w,w.player,hiddenX,hiddenY)
Immune.Update(w,cfg.movementStep)
assert(im.state=='search' and not im.targetId and not im.targetX)
assert(im._searchX==seen.x and im._searchY==seen.y and im._lastSeen==seen)
local q,j=immuneFixture('macrophage');q.cells={}
Immune.Update(q,cfg.movementStep);q.player.isHidden=true
Immune.Update(q,cfg.movementStep);assert(not j.targetId)
''',
    'card AI: real debris cleanup removes camouflage immediately and only once': r'''
local w,im=immuneFixture('macrophage');local s=w.player;local c=unitCell(w)
w.cells={c};w:KillCell(c,'test');grant(w,'debris_camouflage')
place(w,s,c.x+1.7,c.y);A.Update(w,Config.CardAbilities.debris_camouflage.duration)
assert(s.camouflaged and not w._immuneClearedDebris[c.id])
awaitState(w,im,'attack');assert(im.targetType=='cell' and im.targetId==c.id)
local mass=s.mass;advanceImmune(w,im.attackWindup)
assert(w._immuneClearedDebris[c.id] and not s.camouflaged and s.camouflageTime==0)
assert(c.state=='DEAD' and s.mass==mass and eventCount(w,'immune_cleanup')==1)
A.Update(w,10);assert(not s.camouflaged)
advanceImmune(w,.5);assert(eventCount(w,'immune_cleanup')==1)
checkConservation(w,true)
''',
    'card AI: another uncleaned remnant still provides cover; no card grants none': r'''
local w=quietWorld();local s=w.player
local a=unitCell(w,1,s.x-1.7,s.y);local b=unitCell(w,2,s.x+1.7,s.y)
w.cells={a,b};w:KillCell(a,'test');w:KillCell(b,'test')
A.Update(w,4);assert(not s.camouflaged and not w.swarmBrainEnabled)
grant(w,'debris_camouflage');A.Update(w,3);assert(s.camouflaged)
w._immuneClearedDebris[a.id]=true;A.RefreshCamouflage(w,0);assert(s.camouflaged)
w._immuneClearedDebris[b.id]=true;A.RefreshCamouflage(w,0);assert(not s.camouflaged)
checkConservation(w,true)
''',
    'card AI: invalid hold releases before thinking; autonomy remains card gated': r'''
for _,brain in ipairs({false,true}) do
 local w,s,c,im,spare=commandFixture(brain);w.cells={c,spare}
 local replacement=unitCell(w,2,s.x-2,s.y);w.cells={c,replacement}
 w:_Infect(c,'player')
 w:Update(cfg.movementStep)
 assert(not s.groupCommand and eventCount(w,'group_command_released')==1)
 if brain then assert(AI.IsAutonomous(w,s) and s.aiTargetCellId==replacement.id)
 else assert(not AI.IsAutonomous(w,s) and not s.aiTargetCellId and not w.swarmBrainEnabled) end
 assert(w.stats.totalAutoSplits==0 and #w.swarms==2)
 checkConservation(w,true)
end
''',
    'card AI: endangered hold resumes flee only with the brain card': r'''
for _,brain in ipairs({false,true}) do
 local w,s,c,im=commandFixture(brain)
 im.x,im.y=s.x+.8,s.y;im.state='warning';im.targetType='swarm';im.targetId=s.id
 w.immunes={im};local mass=w:ControlledCount()
 w:Update(cfg.movementStep)
 assert(not s.groupCommand and eventCount(w,'group_command_released')==1)
 if brain then assert(s.aiState=='flee' and AI.IsAutonomous(w,s))
 else assert(not AI.IsAutonomous(w,s) and not s.aiTargetCellId) end
 assert(w:ControlledCount()==mass and not s.dashUntil and not s.isHidden and #w.swarms==2)
 checkConservation(w,true)
end
''',
    'card AI: safe no-target hold and gather preserve explicit player intent': r'''
local w,s,c=commandFixture(true)
s.groupCommand.cellId=nil;s.groupCommand.point=nil
w:Update(cfg.movementStep);assert(s.groupCommand.kind=='hold' and not AI.IsAutonomous(w,s))
local x,y=s.x,s.y;w:Update(cfg.movementStep);near(s.x,x);near(s.y,y)
assert(skill(w,'cluster_dispatch',{command='gather'},'gather'))
A.Update(w,cfg.movementStep);assert(s.groupCommand.kind=='gather' and not AI.IsAutonomous(w,s))
assert(w:SwitchControl(s.id));assert(not s.groupCommand and s.isPlayerControlled)
checkConservation(w,true)
''',
}

if __name__ == '__main__':
    failed = 0
    for name, code in TESTS.items():
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute('package.path=' + repr((ROOT / 'scripts/?.lua').as_posix()) + "..';'..package.path")
        logs = []
        lua.globals().print = lambda *args: logs.append(' '.join(map(str, args)))
        try:
            lua.execute(SETUP + GROWTH_SETUP + EXTRA + COMMON + code)
            print('PASS:', name)
        except Exception as error:
            failed += 1
            print('FAIL:', name, error)
            for line in logs[-5:]:
                print(' LOG:', line)
    print(f'{len(TESTS)-failed}/{len(TESTS)} targeted behavior checks passed; native/full-run validation unverified.')
    raise SystemExit(bool(failed))
