"""Pure cell-contact visual regression against the real Lua 5.4 authority.

Imports swarm_regression's isolated runner fixtures; never loads engine/UI modules.
Run: PYTHONDONTWRITEBYTECODE=1 python3 /workspace/tests/cell_contact_regression.py
可选历史备份对照仅排除视觉字段后检查逐位状态相同；有意改变权威机制会使其失效。
当前接触语义使用 --units-only 验证，历史对照失败必须独立如实报告。
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import time

import swarm_regression as swarm

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP = ROOT / 'backups/cell-layers-before-integration/scripts/Core/SwarmWorld.lua'

SETUP = r"""
function contactFixture()
 local w=quietWorld()
 local c=unitCell(w); w.cells={c}
 return w,c,w.player
end
function contactTick(w,t)
 w.time=t
 w:_AccumulateExposure(cfg.movementStep)
end
function contactBy(c,kind,id)
 for _,r in ipairs(c.contactVisuals) do
  if r.sourceType==kind and r.sourceId==id then return r end
 end
 return nil
end
function verifyContact(c,r)
 assert(r.strength>0 and r.fade>=0 and r.fade<=1)
 assert(r.cellId==c.id and r.key==c.id..':'..r.sourceType..':'..r.sourceId)
 assert(finite(r.sourceX) and finite(r.sourceY) and finite(r.sourceRadius))
 assert(finite(r.normalX) and finite(r.normalY))
 near(r.normalX*r.normalX+r.normalY*r.normalY,1,1e-12)
 assert(r.stableDirectionX==r.normalX and r.stableDirectionY==r.normalY)
 assert(r.stableAngle==r.stableLocalAngle and finite(r.visualCellRotation))
 near(r.worldContactX,c.x+r.normalX*c.radius,1e-12)
 near(r.worldContactY,c.y+r.normalY*c.radius,1e-12)
 assert(r.lastSeen>=r.firstSeen)
end
function contactAngleDelta(a,b)
 return (a-b+math.pi)%(2*math.pi)-math.pi
end
function reverseArray(items)
 local other={}
 for i=#items,1,-1 do other[#other+1]=items[i] end
 return other
end
"""

TESTS = {
    'accepted player has exact positive strength and Y-down membrane projection': r"""
local w,c,s=contactFixture(); s.x,s.y=c.x+.3,c.y+.4
contactTick(w,1)
assert(#c.contactVisuals==1)
local r=assert(contactBy(c,'PLAYER_SWARM',s.id)); verifyContact(c,r)
near(r.normalX,.6); near(r.normalY,.8)
assert(r.sourceX==s.x and r.sourceY==s.y and r.sourceRadius==s.radius)
local range=c.radius+s.radius+cfg.infectionReach
local power=math.max(.22,1-distance(c,s)/range)*math.min(2,math.sqrt(s.mass/cfg.densityReference))
assert(r.strength==power and r.firstSeen==1 and r.lastSeen==1 and r.fade==1)
assert(c._charge==cfg.movementStep*math.min(3,power)/cfg.infectionSeconds)
assert(c.contactVisualAnchor==r and #w.events==0 and w.stats.totalInfected==0)
""",
    'source identity includes type when swarm and released IDs collide': r"""
local w,c,s=contactFixture(); w:_Release(c,1)
local v=w.releasedViruses[1]; assert(s.id==v.id)
s.x,s.y=c.x+.3,c.y; v.x,v.y=c.x,c.y-.3
contactTick(w,1)
assert(#c.contactVisuals==2)
local a=assert(contactBy(c,'PLAYER_SWARM',s.id))
local b=assert(contactBy(c,'RELEASED_VIRUS',v.id))
assert(a~=b); near(a.normalX,1); near(b.normalY,-1)
verifyContact(c,a); verifyContact(c,b)
near(b.strength,cfg.releasedInfectionPower*math.max(.3,1-.3/(c.radius+cfg.infectionReach+v.radius)))
local events=#w.events; contactTick(w,2)
assert(contactBy(c,'PLAYER_SWARM',s.id)==a and contactBy(c,'RELEASED_VIRUS',v.id)==b)
assert(#w.events==events and a.firstSeen==1 and b.firstSeen==1)
""",
    'same source reuses record with stable-candidate turn limit and ended local rotation': r"""
local settings=require('Core.CellContacts').Settings
assert(finite(settings.maxTurn) and settings.maxTurn>0)
assert(settings.candidateFrames>=1 and settings.candidateFrames%1==0)
local w,c,s=contactFixture(); s.x,s.y=c.x+.3,c.y
contactTick(w,1); local r=c.contactVisuals[1]
s.x,s.y=c.x,c.y-.4; c.rotation=c.rotation+.5
-- 90°换向再加0.5弧度细胞旋转，按真实Settings计算稳定候选和限速收敛步数。
-- 至少等待33次接触提交；maxTurn减小后自动延长，不能期望瞬间换向。
local requiredTurn=contactAngleDelta(math.atan(s.y-c.y,s.x-c.x)-c.rotation,r.stableLocalAngle)
local ticks=math.max(33,settings.candidateFrames+math.ceil(math.abs(requiredTurn)/settings.maxTurn)+1)
local lastSeen=1
for i=1,ticks do
 local previous=r.stableLocalAngle
 lastSeen=2+(i-1)*cfg.movementStep; contactTick(w,lastSeen)
 assert(#c.contactVisuals==1 and c.contactVisuals[1]==r and c.contactVisualAnchor==r)
 local turn=contactAngleDelta(r.stableLocalAngle,previous)
 assert(math.abs(turn)<=settings.maxTurn+1e-12)
 if i<settings.candidateFrames then near(turn,0,1e-12); assert(r.candidateFrames==i)
 elseif i==settings.candidateFrames then
  near(turn,math.max(-settings.maxTurn,math.min(settings.maxTurn,requiredTurn)),1e-12)
  assert(r.candidateFrames==0)
 end
 near(r.rawNormalX,0); near(r.rawNormalY,-1)
 assert(r.lastSeen==lastSeen and r.firstSeen==1 and r.visualCellRotation==c.rotation)
 verifyContact(c,r)
end
near(r.normalX,0); near(r.normalY,-1)
s.x,s.y=c.x+3,c.y
local rotation,localAngle,nx,ny=r.visualCellRotation,r.stableLocalAngle,r.normalX,r.normalY
local px,py=r.worldContactX,r.worldContactY
for i=1,3 do
 c.rotation=c.rotation+.3; contactTick(w,lastSeen+i*.1)
 assert(not r._accepted and not r.active and r.fade>0 and r.fade<1)
 assert(r.lastSeen==lastSeen and r.visualCellRotation==rotation)
 assert(r.stableLocalAngle==localAngle and r.normalX==nx and r.normalY==ny)
 assert(r.worldContactX==px and r.worldContactY==py and c.contactVisualAnchor==r)
end
-- 12°死区内的真实方向只更新raw采样；反复越区但不稳定的候选不能转向。
local a,ca,sa=contactFixture(); ca.rotation=0; sa.x,sa.y=ca.x+.3,ca.y
contactTick(a,1); local held=ca.contactVisuals[1]
for i=1,6 do
 local angle=math.rad(i%2==0 and -11 or 11)
 sa.x,sa.y=ca.x+.3*math.cos(angle),ca.y+.3*math.sin(angle)
 contactTick(a,1+i*cfg.movementStep)
 near(held.normalX,1); near(held.normalY,0); assert(held.candidateFrames==0)
end
for i=1,6 do
 sa.x,sa.y=ca.x,ca.y+(i%2==0 and -.3 or .3)
 contactTick(a,2+i*cfg.movementStep)
 near(held.normalX,1); near(held.normalY,0); assert(held.candidateFrames==1)
end
""",
    'center overlap retains previous direction without RNG or velocity jitter': r"""
local w,c,s=contactFixture(); s.x,s.y=c.x,c.y-.4
contactTick(w,1); local r=c.contactVisuals[1]; local rng=w._rng
s.x,s.y=c.x,c.y; s.vx,s.vy=5,7
for i=1,20 do
 contactTick(w,1+i*.01)
 assert(c.contactVisuals[1]==r); near(r.normalX,0); near(r.normalY,-1)
 assert(r.rawNormalX==nil and r.rawNormalY==nil and r.rawContactX==nil and r.rawContactY==nil)
 assert(r.candidateFrames==0 and r.targetLocalAngle==r.stableLocalAngle)
 s.vx,s.vy=-s.vx,-s.vy
end
assert(w._rng==rng)
""",
    'first center overlap invents no direction at any velocity and keeps infection contribution': r"""
local w,c,s=contactFixture(); s.x,s.y=c.x,c.y; s.vx,s.vy=3,4
local rng=w._rng; contactTick(w,1)
assert(#c.contactVisuals==0 and not c.contactVisualAnchor)
local power=math.min(2,math.sqrt(s.mass/cfg.densityReference))
assert(c.covered and c.everPlayerContact and s.exposedCells[c.id])
assert(c._charge==cfg.movementStep*power/cfg.infectionSeconds and c._groupCharge==c._charge)
assert(w._rng==rng and #w.events==0 and w.stats.totalInfected==0)
-- .01和.019米仍在新EPS=.02内；改变速度不能替代真实接触方向。
local charge=c._charge
for i,d in ipairs({.01,.019}) do
 s.x,s.y=c.x+d,c.y; s.vx,s.vy=-s.vx,-s.vy
 local range=c.radius+s.radius+cfg.infectionReach
 charge=charge+cfg.movementStep*math.max(.22,1-distance(c,s)/range)*power/cfg.infectionSeconds
 contactTick(w,1+i*cfg.movementStep)
 assert(#c.contactVisuals==0 and not c.contactVisualAnchor)
 assert(c._charge==charge and c._groupCharge==charge and c._releasedCharge==0)
end
-- 只有>.02米的真实偏移才建立首次方向，与逆速度方向无关。
s.x,s.y=c.x+.03,c.y; s.vx,s.vy=3,4; contactTick(w,2)
local r=assert(c.contactVisuals[1]); verifyContact(c,r)
near(r.normalX,1); near(r.normalY,0); assert(r.firstSeen==2)
assert(w._rng==rng and #w.events==0)
local a,ca,sa=contactFixture(); local b,cb,sb=contactFixture()
local rngA,rngB=a._rng,b._rng
contactTick(a,1); contactTick(b,1)
assert(#ca.contactVisuals==0 and not ca.contactVisualAnchor)
assert(#cb.contactVisuals==0 and not cb.contactVisualAnchor)
assert(ca.covered and cb.covered and ca.everPlayerContact and cb.everPlayerContact)
local stationaryPower=math.min(2,math.sqrt(sa.mass/cfg.densityReference))
assert(ca._groupCharge==cfg.movementStep*stationaryPower/cfg.infectionSeconds)
for i=1,10 do contactTick(a,1+i*.01) end
assert(#ca.contactVisuals==0 and not ca.contactVisualAnchor)
assert(a._rng==rngA and b._rng==rngB and #a.events==0 and #b.events==0)
-- 真正Released来源在中心即使有速度也不造方向，原释放感染贡献照常累计。
sa.x=ca.x+3; a:_Release(ca,1); local v=a.releasedViruses[1]
v.x,v.y,v.vx,v.vy=ca.x,ca.y,0,0
local events=#a.events; local releasedRng=a._rng; contactTick(a,2)
assert(#ca.contactVisuals==0 and not ca.contactVisualAnchor and ca._releasedCharge>0)
local releasedCharge=cfg.movementStep*cfg.releasedInfectionPower/cfg.infectionSeconds
assert(ca._releasedCharge==releasedCharge)
v.vx,v.vy=3,4; contactTick(a,2+cfg.movementStep)
assert(#ca.contactVisuals==0 and not ca.contactVisualAnchor)
assert(ca._releasedCharge==releasedCharge+releasedCharge)
assert(#a.events==events and a._rng==releasedRng)
""",
    'hidden distant swarms are rejected and brainless contact is visualized': r"""
local w,c,s=contactFixture(); s.isHidden=true; contactTick(w,1)
assert(#c.contactVisuals==0 and not c.contactVisualAnchor)
s.isHidden=false; s.x=c.x+3; contactTick(w,2)
assert(#c.contactVisuals==0 and not c.contactVisualAnchor)
s.x=c.x+.2; s.isPlayerControlled=false; s.exposedCells={}
w.config.autonomy.enabled=false; contactTick(w,3)
assert(#c.contactVisuals==1 and c.contactVisualAnchor.sourceId==s.id and c._groupCharge>0)
w.config.autonomy.enabled=true; contactTick(w,4)
assert(#c.contactVisuals==1 and c.contactVisualAnchor.sourceId==s.id and c._groupCharge>0)
assert(s.exposedCells[c.id] and c.everPlayerContact,'无小脑群也保留真实接触感染')
local r=c.contactVisuals[1]; verifyContact(c,r)
contactTick(w,5); assert(c.contactVisuals[1]==r,'同一自主来源连续接触复用记录')
""",
    'zero accepted contactPower records nothing and dead swarm cannot prime infection': r"""
local w,c,s=contactFixture(); s.mass=0
w:_Release(c,1); cfg.releasedInfectionPower=0
contactTick(w,1)
assert(#c.contactVisuals==0 and not c.contactVisualAnchor and not c.covered)
assert(c._groupCharge==0 and c._releasedCharge==0)
assert(not c.everPlayerContact and not s.exposedCells[c.id],'零质量群不是有效感染来源')
assert(c._charge==-cfg.movementStep*cfg.exposureDecay)
""",
    'cap is three strongest initially independent of source array order': r"""
local function sample(reversed)
 local w,c,s=contactFixture(); s.x=c.x+3; w:_Release(c,8)
 for i,v in ipairs(w.releasedViruses) do v.x,v.y=c.x+.05*i,c.y end
 if reversed then w.releasedViruses=reverseArray(w.releasedViruses) end
 contactTick(w,1)
 assert(#c.contactVisuals==3 and c.contactVisualAnchor.sourceId==1)
 local ids={}
 for i,r in ipairs(c.contactVisuals) do verifyContact(c,r); ids[i]=r.sourceId end
 return table.concat(ids,',')
end
assert(sample(false)=='1,2,3' and sample(true)=='1,2,3')
""",
    'full cap preserves every live incumbent slot despite stronger newcomers': r"""
local w,c,s=contactFixture(); s.x=c.x+3; w:_Release(c,6)
for i,v in ipairs(w.releasedViruses) do v.x,v.y=c.x+.03*i,c.y end
contactTick(w,1); local records={table.unpack(c.contactVisuals)}
-- 新来源需要>.02米真实方向，并保持比最近的.03米incumbent更强。
for i=4,6 do w.releasedViruses[i].x=c.x+.025 end
for i=1,12 do
 w.releasedViruses=reverseArray(w.releasedViruses); contactTick(w,1+i*.02)
 assert(#c.contactVisuals==3)
 for j,r in ipairs(records) do assert(c.contactVisuals[j]==r and r._accepted and r.fade==1) end
 assert(c.contactVisualAnchor==records[1])
end
""",
    'gone slot replacement is oldest fading only and live slots cannot be evicted this step': r"""
local w,c,s=contactFixture(); s.x=c.x+3; w:_Release(c,5)
for i,v in ipairs(w.releasedViruses) do v.x,v.y=c.x+.03*i,c.y end
w.releasedViruses[4].state='CLEARED'; w.releasedViruses[5].state='CLEARED'
contactTick(w,1)
local a,b,keep=c.contactVisuals[1],c.contactVisuals[2],c.contactVisuals[3]
a.lastSeen=.8; b.lastSeen=1
w.releasedViruses[1].state='CLEARED'; w.releasedViruses[2].state='LOST'
w.releasedViruses[4].state='RELEASED'; w.releasedViruses[5].state='RELEASED'
w.releasedViruses=reverseArray(w.releasedViruses)
contactTick(w,1.1)
assert(c.contactVisuals[1].sourceId==4 and c.contactVisuals[2].sourceId==5)
assert(c.contactVisuals[3]==keep and keep.lastSeen==1.1)
assert(c.contactVisualAnchor==keep and #c.contactVisuals==3)
""",
    'anchor holds live incumbent then deterministically strongest accepted when gone': r"""
local w,c,s=contactFixture(); s.x,s.y=c.x+.3,c.y
contactTick(w,1); local anchor=c.contactVisualAnchor
w:_Release(c,3)
-- .01米已在新EPS内；使用>.02米真实方向测试更强来源及锚点切换。
for _,v in ipairs(w.releasedViruses) do v.x,v.y=c.x,c.y+.03 end
cfg.releasedInfectionPower=10
contactTick(w,1.1)
assert(c.contactVisualAnchor==anchor,'stronger new source must not thrash existing contact patch')
s.isHidden=true; w.releasedViruses=reverseArray(w.releasedViruses)
contactTick(w,1.2)
assert(c.contactVisualAnchor.sourceType=='RELEASED_VIRUS' and c.contactVisualAnchor.sourceId==1)
near(c.contactVisualAnchor.normalX,0); near(c.contactVisualAnchor.normalY,1)
for _,v in ipairs(w.releasedViruses) do v.state='ABSORBED' end
local last=c.contactVisualAnchor; contactTick(w,2)
assert(#c.contactVisuals==0 and c.contactVisualAnchor==last)
""",
    'ended contact fades in 0.75 seconds and anchor remains with no source': r"""
local w,c,s=contactFixture(); s.x,s.y=c.x+.3,c.y
contactTick(w,1); local r=c.contactVisuals[1]
w.swarms={}; contactTick(w,1.375)
assert(#c.contactVisuals==1 and c.contactVisuals[1]==r)
near(r.fade,.5,1e-12); assert(r.lastSeen==1 and r.strength>0 and not c.covered)
contactTick(w,1.749); assert(#c.contactVisuals==1 and r.fade>0)
contactTick(w,1.75); assert(#c.contactVisuals==0 and r.fade==0 and c.contactVisualAnchor==r)
contactTick(w,5); assert(c.contactVisualAnchor==r and r.lastSeen==1)
""",
    'all terminal released states clear attachments with fade without extra infection': r"""
for _,terminal in ipairs({'CLEARED','LOST','ABSORBED'}) do
 local w,c,s=contactFixture(); s.x=c.x+3; w:_Release(c,1)
 local v=w.releasedViruses[1]; v.x,v.y=c.x,c.y+.2
 contactTick(w,1); local r=assert(contactBy(c,'RELEASED_VIRUS',v.id))
 v.state=terminal; local events=#w.events; local infections=w.stats.totalInfected
 contactTick(w,1.1); assert(not r._accepted and r.lastSeen==1 and r.fade<1)
 contactTick(w,1.75)
 assert(#c.contactVisuals==0 and c.contactVisualAnchor==r and c._releasedCharge>0)
 assert(w.stats.totalInfected==infections and #w.events==events)
end
""",
    'LATENT stops accepting contact and preserves anchor after fade': r"""
local w,c,s=contactFixture(); s.x,s.y=c.x+.3,c.y
contactTick(w,2); local anchor=c.contactVisualAnchor
w:_Infect(c,'player'); assert(c.infectedVisualAt==2 and c.state=='LATENT')
local events=#w.events; local rng=w._rng; local age=c.infectedAge
s.x,s.y=c.x-.3,c.y
contactTick(w,2.375); assert(anchor.lastSeen==2 and anchor.normalX==1)
near(anchor.fade,.5); contactTick(w,2.75)
assert(#c.contactVisuals==0 and c.contactVisualAnchor==anchor)
assert(c.infectedVisualAt==2 and c.infectedAge==age and w._rng==rng and #w.events==events)
assert(w.stats.totalInfected==1 and eventCount(w,'infection_complete')==1)
""",
    'initial preinfection has visual timestamp but never invented contact anchor': r"""
for _,start in ipairs({'UPPER_AIRWAY','TRACHEA','DEEP_LUNG'}) do
 local w=quietWorld(start)
 for _,c in ipairs(w.cells) do
  assert(#c.contactVisuals==0 and c.contactVisualAnchor==nil)
  if c.state=='LATENT' then assert(c.infectedVisualAt==0 and c.infectionSource=='initial')
  else assert(c.infectedVisualAt==nil) end
  assert(c.lastReleaseVisualAt==nil and c.releaseVisualSequence==0 and #c.releaseVisualDirections==0)
 end
 assert(#w.events==0)
end
""",
    'release direction samples use only real births and unique visual batch sequence': r"""
local w,c=contactFixture(); w.time=5; w:_Release(c,8)
assert(c.lastReleaseVisualAt==5 and c.releaseVisualSequence==1 and #c.releaseVisualDirections==3)
for _,dir in ipairs(c.releaseVisualDirections) do
 local v=w.releasedViruses[dir.sourceId]
 assert(dir.x==v.x and dir.y==v.y)
 local d=distance(c,v); near(dir.normalX,(v.x-c.x)/d,1e-12); near(dir.normalY,(v.y-c.y)/d,1e-12)
end
local first=c.releaseVisualDirections; w:_Release(c,1)
assert(c.releaseVisualSequence==2 and c.lastReleaseVisualAt==5 and c.releaseCount==0)
assert(c.releaseVisualDirections~=first and #c.releaseVisualDirections==1)
assert(c.releaseVisualDirections[1].sourceId==9 and eventCount(w,'release_batch')==2)
assert(w.stats.totalReleased==9)
""",
    'center map fallback births do not invent release directions': r"""
local w,c=contactFixture(); c.x,c.y=-100,-100
w.time=8; w:_Release(c,6)
assert(c.lastReleaseVisualAt==8 and c.releaseVisualSequence==1 and #c.releaseVisualDirections==0)
for _,v in ipairs(w.releasedViruses) do assert(v.x==c.x and v.y==c.y) end
assert(w.stats.totalReleased==6 and eventCount(w,'release_batch')==1)
""",
    'real release preserves cell-local membrane anchor through later rotation': r"""
local w,c=contactFixture(); c.rotation=.37; w:_Release(c,6)
local dir=assert(c.releaseVisualDirections[1])
local bornAngle=math.atan(dir.normalY,dir.normalX)
local localAngle=bornAngle-c.rotation
local virus=w.releasedViruses[dir.sourceId]
local x,y,vx,vy=virus.x,virus.y,virus.vx,virus.vy
local rng,events=w._rng,#w.events
assert(dir.visualCellRotation==c.rotation)
c.rotation=c.rotation+.8
local drawAngle=bornAngle+c.rotation-dir.visualCellRotation
near(contactAngleDelta(drawAngle-c.rotation,localAngle),0,1e-12)
assert(virus.x==x and virus.y==y and virus.vx==vx and virus.vy==vy)
assert(w._rng==rng and #w.events==events and w.stats.totalReleased==6)
""",
    'infection diagnostics match real uncapped group and capped released charge': r"""
local Diagnostics=require('Core.CellDiagnostics')
for _,mode in ipairs({'group','released','mixed'}) do
 local w,c,s=contactFixture()
 s.mass=cfg.densityReference*100
 s.x,s.y=c.x+.3,c.y
 if mode=='released' then s.isHidden=true end
 if mode~='group' then
  w:_Release(c,80)
  for _,v in ipairs(w.releasedViruses) do v.x,v.y=c.x+.3,c.y end
 end
 local rows={}
 Diagnostics.Configure(w,{cellId=c.id,sink=function(row)rows[#rows+1]=row end})
 Diagnostics.BeginStep(w,cfg.movementStep)
 local previousCharge=c._charge
 w:_AccumulateExposure(cfg.movementStep)
 local actualCharge=c._charge-previousCharge
 local rng,events=w._rng,#w.events
 Diagnostics.EndStep(w)
 assert(#rows>0 and actualCharge>0)
 for _,row in ipairs(rows) do near(row.deltaAccruedCharge,actualCharge,1e-12) end
 assert(c._charge==previousCharge+actualCharge and w._rng==rng and #w.events==events)
 assert(c.state=='HEALTHY' and c.exposure==0,'诊断不能代替真实感染结算')
 if mode=='group' or mode=='mixed' then
  assert(actualCharge>cfg.movementStep*3/cfg.infectionSeconds,'必须覆盖超过旧总功率上限的群体')
 end
 Diagnostics.Configure(w,nil)
end
""",
    'infection and death visual timestamps are idempotent without added events': r"""
local w,c=contactFixture(); w.time=3; w:_Infect(c,'released')
assert(c.infectedVisualAt==3 and not c.contactVisualAnchor)
assert(eventCount(w,'infection_complete')==1 and eventCount(w,'independent_infection')==1)
w.time=4; w:_Infect(c,'player'); assert(c.infectedVisualAt==3 and w.stats.totalInfected==1)
w:KillCell(c,'test'); assert(c.deathVisualAt==4 and eventCount(w,'cell_dead')==1)
w.time=5; w:KillCell(c,'again'); assert(c.deathVisualAt==4 and eventCount(w,'cell_dead')==1)
""",
    'real fixed-step source disappearance and paused clock honor exact visual lifetime': r"""
local w,c,s=contactFixture(); s.x,s.y=c.x+.3,c.y
w:Update(cfg.movementStep); local r=c.contactVisuals[1]
assert(r and r.lastSeen==w.time); local t=w.time
w:DamageSwarm(s.id,s.mass)
w:Update(0); assert(w.time==t and r.lastSeen==t and r.fade==1)
step(w,.4); assert(#c.contactVisuals==1 and r.fade<.5 and r.fade>0)
step(w,.4); assert(#c.contactVisuals==0 and c.contactVisualAnchor==r)
assert(w.stats.totalInfected==0 and eventCount(w,'infection_complete')==0)
checkConservation(w)
""",
}

# Exact canonical serialization (hex floats, not rounding/tolerance). Only new
# visual keys under actual w.cells objects are omitted; even entity order stays.
FINGERPRINT_SETUP = r"""
BackupWorld=assert(dofile(BACKUP_SWARM_WORLD))
local visualKeys={contactVisuals=true,contactVisualAnchor=true,infectedVisualAt=true,
 lastReleaseVisualAt=true,releaseVisualSequence=true,releaseVisualDirections=true,deathVisualAt=true}
function businessSnapshot(w,formulaOnly)
 local cellSet={}; for _,c in ipairs(w.cells) do cellSet[c]=true end
 local releasedSet={};for _,v in ipairs(w.releasedViruses or {}) do releasedSet[v]=true end
 -- New budget/batch bookkeeping has dedicated mechanism tests. The isolated
 -- historical comparison still checks every original lifecycle field exactly.
 local budgetKeys={pendingProduction=true,pendingProductionElapsed=true}
 local ids={}; local nextId=0; local parts={}
 local function out(x) parts[#parts+1]=x end
 local function encode(value)
  local t=type(value)
  if t=='table' then
   if ids[value] then out('ref'..ids[value]..';'); return end
   nextId=nextId+1; ids[value]=nextId; out('table'..nextId..'{')
   local keys={}
   for key,item in pairs(value) do
    if type(item)~='function' and not (cellSet[value] and visualKeys[key])
      and not (formulaOnly and ((cellSet[value] and budgetKeys[key])
       or (releasedSet[value] and key=='releaseBatchId'))) then keys[#keys+1]=key end
   end
   table.sort(keys,function(a,b)
    if type(a)~=type(b) then return type(a)<type(b) end
    return a<b
   end)
   for _,key in ipairs(keys) do encode(key); encode(value[key]) end
   out('}')
  elseif t=='number' then
   out(math.type(value)=='integer' and ('int'..tostring(value)..';') or ('float'..string.format('%a',value)..';'))
  elseif t=='string' then out('str'..#value..':'..value)
  elseif t=='boolean' then out(value and 'true;' or 'false;')
  elseif t=='nil' then out('nil;')
  else error('unexpected authority value type '..t) end
 end
 encode(w); return table.concat(parts)
end
function compareExact(a,b,label,formulaOnly)
 local sa,sb=businessSnapshot(a,formulaOnly),businessSnapshot(b,formulaOnly)
 assert(sa==sb,'exact authority mismatch at '..label)
 return sa
end
"""

# Real immunity, original stress movement/split/switch schedule and natural
# latent/productive/released infection, checked each second plus RNG each tick.
FINGERPRINT_STRESS = r"""
local streams={}
local checks=0
for start in string.gmatch(FINGERPRINT_STARTS,'[^,]+') do
 local a,b=World.New(start),BackupWorld.New(start)
 streams[#streams+1]=compareExact(a,b,start..' init'); checks=checks+1
 for i=1,math.floor(FINGERPRINT_SECONDS/cfg.movementStep+.5) do
  if i%600==1 then
   local angle=i/500
   a:SetMovement(math.cos(angle),math.sin(angle)); b:SetMovement(math.cos(angle),math.sin(angle))
   if #a.swarms==1 then assert(a:Split()==b:Split()) else assert(a:SwitchControl()==b:SwitchControl()) end
  end
  a:Update(cfg.movementStep); b:Update(cfg.movementStep)
  assert(a._rng==b._rng,start..' RNG differs at tick '..i)
  assert(a._nextVirusId==b._nextVirusId and a._nextReleasedId==b._nextReleasedId)
  if i%60==0 then
   checkConservation(a,true); checkConservation(b,true)
   streams[#streams+1]=compareExact(a,b,start..' tick '..i); checks=checks+1
  end
  a.events={}; b.events={}
 end
 streams[#streams+1]=compareExact(a,b,start..' final'); checks=checks+1
 local c=a:Counts()
 fingerprint_summary(start,a._rng,a.stats.totalInfected,a.stats.totalReleased,a.stats.totalKilled,c.virus)
end
return table.concat(streams,'\n'),checks
"""

# Every movement step compared, not only disease frames. Forces genuine accepted
# contact, split continuation, release batches/absorption/kill and immune age.
FINGERPRINT_CONTACT = r"""
local a=quietWorld(); local b=BackupWorld.New('UPPER_AIRWAY')
local p=b.map.startPoints.DEEP_LUNG; place(b,b.player,p.x,p.y)
local ca,cb=unitCell(a),unitCell(b); a.cells={ca}; b.cells={cb}
a.player.x,a.player.y=ca.x+.3,ca.y; b.player.x,b.player.y=cb.x+.3,cb.y
local streams={compareExact(a,b,'contact init')}; local checks=1
for i=1,1200 do
 if i==60 then assert(a:Split()==b:Split()) end
 if i==120 then assert(a:SwitchControl()==b:SwitchControl()) end
 if i==240 or i==360 then a:_Release(ca,6); b:_Release(cb,6) end
 if i==420 then
  a:_Release(ca,1); b:_Release(cb,1)
  a:KillReleased(a.releasedViruses[#a.releasedViruses]); b:KillReleased(b.releasedViruses[#b.releasedViruses])
 end
 -- The split legitimately carries sources away; create a real accepted released
 -- source burst beside the still-healthy target, instead of forcing its state.
 if i==480 then a:_Release(ca,20); b:_Release(cb,20) end
 if i==900 then a:KillCell(ca,'test'); b:KillCell(cb,'test') end
 a:Update(cfg.movementStep); b:Update(cfg.movementStep)
 streams[#streams+1]=compareExact(a,b,'contact tick '..i); checks=checks+1
end
checkConservation(a,true); checkConservation(b,true)
assert(a.stats.totalInfected>0 and a.stats.totalReleased>0)
return table.concat(streams,'\n'),checks
"""

# Keep the original exposure/lifecycle/release formulas under identical inputs.
# Whole-world immunity replay is no longer an invariant after the card rules.
FINGERPRINT_INFECTION = r"""
local a=quietWorld();local b=quietWorld()
local ca,cb=unitCell(a),unitCell(b);a.cells={ca};b.cells={cb}
a.player.x,a.player.y=ca.x+.3,ca.y;b.player.x,b.player.y=cb.x+.3,cb.y
for _,method in ipairs({'_AccumulateExposure','_InfectCells','_AgeCells','_Infect','_Release'}) do
 b[method]=assert(BackupWorld[method])
end
local streams={};local checks=0
local function snapshot(w)
 return {cells=w.cells,releasedViruses=w.releasedViruses,stats=w.stats,rng=w._rng,
  nextReleasedId=w._nextReleasedId,events=w.events,
  inflammation=w.globalInflammation,damage=w.globalTissueDamage}
end
for i=1,math.floor(240/cfg.movementStep+.5) do
 a.time=i*cfg.movementStep;b.time=a.time
 a:_AccumulateExposure(cfg.movementStep);b:_AccumulateExposure(cfg.movementStep)
 if i%15==0 then
  a:_InfectCells();b:_InfectCells();a:_AgeCells(cfg.diseaseStep);b:_AgeCells(cfg.diseaseStep)
  streams[#streams+1]=compareExact(snapshot(a),snapshot(b),'isolated infection tick '..i,true)
  checks=checks+1;a.events={};b.events={}
 end
end
assert(a.stats.totalInfected==1 and a.stats.totalReleased>0)
return table.concat(streams,'\n'),checks
"""


def new_runtime():
    logs = []
    lua = swarm.LuaRuntime(unpack_returned_tuples=True)
    lua.globals().test_log = lambda *items: logs.append(' '.join(map(str, items)))
    lua.globals().TEST_PACKAGE_PATH = str(ROOT / 'scripts' / '?.lua')
    lua.execute("package.path=TEST_PACKAGE_PATH..';'..package.path; print=test_log")
    lua.execute(swarm.SETUP)
    lua.execute(SETUP)
    return lua, logs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup', type=Path, default=DEFAULT_BACKUP)
    parser.add_argument('--fingerprint-seconds', type=float, default=180)
    parser.add_argument('--fingerprint-start', action='append', choices=('UPPER_AIRWAY','TRACHEA','DEEP_LUNG'))
    parser.add_argument('--units-only', action='store_true', help='run just visual unit cases without backup replay')
    parser.add_argument('--legacy-world-fingerprint', action='store_true',help='historical pre-card whole-world replay; immune behavior intentionally differs')
    args = parser.parse_args()
    if not args.backup.is_file():
        parser.error(f'backup not found: {args.backup}')
    if args.fingerprint_seconds <= 0:
        parser.error('--fingerprint-seconds must be positive')
    failed = []
    started = time.perf_counter()
    for name, code in TESTS.items():
        case_start = time.perf_counter()
        lua, logs = new_runtime()
        try:
            lua.execute(code)
            print(f'PASS {name} ({time.perf_counter()-case_start:.2f}s)')
        except Exception as exc:
            failed.append(name)
            print(f'FAIL {name}\n{exc}')
            for line in logs[-8:]:
                print(' LOG', line)
    fingerprint_cases = [] if args.units_only else [('isolated exposure lifecycle release formula fingerprint',FINGERPRINT_INFECTION)]
    if args.legacy_world_fingerprint:
        fingerprint_cases += [
        ('exact backup accepted-contact fingerprint every tick', FINGERPRINT_CONTACT),
        ('exact backup real-immunity random fingerprint', FINGERPRINT_STRESS),
        ]
    for name, code in fingerprint_cases:
        case_start = time.perf_counter()
        lua, logs = new_runtime()
        summaries = []
        lua.globals().BACKUP_SWARM_WORLD = str(args.backup.resolve())
        lua.globals().FINGERPRINT_SECONDS = args.fingerprint_seconds
        lua.globals().FINGERPRINT_STARTS = ','.join(args.fingerprint_start or ['UPPER_AIRWAY','TRACHEA','DEEP_LUNG'])
        lua.globals().fingerprint_summary = lambda *items: summaries.append(items)
        try:
            lua.execute(FINGERPRINT_SETUP)
            stream, checks = lua.execute(code)
            digest = hashlib.sha256(stream.encode('utf-8')).hexdigest()
            print(f'PASS {name}: {checks} exact snapshots, SHA256={digest} ({time.perf_counter()-case_start:.2f}s)')
            for start, rng, infected, released, killed, virus in summaries:
                print(f' RNG {start}: {rng}, infected={infected}, released={released}, killed={killed}, virus={virus}')
        except Exception as exc:
            failed.append(name)
            print(f'FAIL {name}\n{exc}')
            for line in logs[-8:]:
                print(' LOG', line)
    total = len(TESTS)+len(fingerprint_cases)
    print(f'{total-len(failed)}/{total} passed, {len(failed)} failed ({time.perf_counter()-started:.2f}s)')
    print('Rendering alpha-membrane correction and offscreen visuals require separate engine/view validation.')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
