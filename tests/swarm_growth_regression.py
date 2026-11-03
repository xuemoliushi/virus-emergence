"""主动吸附、多群分裂/合并与容量受限增长的真实 Lua 5.4 回归。

复用旧回归的隔离 LuaRuntime 与真实 Core/地图/免疫模块，不替换业务函数。
新测试仅移动单元夹具或调用真实 _Release 创建游离个体；不是整局平衡验收。
运行：PYTHONDONTWRITEBYTECODE=1 python3 /workspace/tests/swarm_growth_regression.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from swarm_regression import ROOT, SETUP, LuaRuntime

GROWTH_SETUP = r"""
function releaseAt(w,count,x,y)
 local cell=w.cells[1]
 if not cell then
  -- 夹具在清空细胞前保留真实对象，绝不创建伪造来源。
  cell=assert(w._fixtureSource)
 end
 w._fixtureSource=cell
 local start=#w.releasedViruses+1
 w:_Release(cell,count)
 local result={}
 for i=start,#w.releasedViruses do
  local v=w.releasedViruses[i]
  v.x,v.y,v._oldX,v._oldY=x,y,x,y
  assert(w.map:Contains(x,y,v.radius),'游离夹具必须位于真实地图内')
  result[#result+1]=v
 end
 return result
end
function growByAbsorption(w,count)
 w.time=w.time+w:GetAbsorptionCooldown() -- 质量夹具等到下一次合法脉冲，冷却独立回归。
 local before=w:ControlledCount()
 releaseAt(w,count,w.player.x,w.player.y)
 assert(w:AbsorbableCount()==count)
 assert(w:AbsorbNearby()==count)
 assert(w:ControlledCount()==before+count)
 checkConservation(w,true)
end
function manyGroups(count)
 local w=quietWorld()
 w.maxPlayerSwarms=count -- 仅内部几何/守恒压测夹具，正式容量另测2/4/6。
 growByAbsorption(w,600)
 for _=2,count do
  local largest=w.swarms[1]
  for _,s in ipairs(w.swarms) do if s.mass>largest.mass then largest=s end end
  if largest.id~=w.currentControlledSwarmId then assert(w:SwitchControl(largest.id)) end
  -- 本夹具只隔离冷却时间；冷却实际8秒另有真实Update测试。
  w.splitCooldown=0
  assert(w:CanSplit() and w:Split())
  checkConservation(w)
 end
 for _,s in ipairs(w.swarms) do s.launchTimer,s.mergeGrace=0,0 end
 return w
end
function pairsValid(w)
 local seen={}
 assert(w.mergeReady==(#w.mergePairs>0))
 for _,p in ipairs(w.mergePairs) do
  local a,b=assert(w:SwarmById(p.aId)),assert(w:SwarmById(p.bId))
  assert(a~=b and a.mass>0 and b.mass>0 and not a.isHidden and not b.isHidden)
  assert(a.mergeGrace==0 and b.mergeGrace==0)
  assert(distance(a,b)<=a.radius+b.radius+cfg.mergeExtra)
  local key=math.min(a.id,b.id)..':'..math.max(a.id,b.id)
  assert(not seen[key],'群对重复');seen[key]=true
 end
end
"""

TESTS = {
    '主动吸附范围快照即时生效且重复守恒保外观': r"""
local w=quietWorld();local s=w.player
local oldRadius,oldMass=s.radius,s.mass
local range=oldRadius+cfg.activeAbsorptionExtra
local inside=releaseAt(w,2,s.x+range-.01,s.y)
local edge=releaseAt(w,1,s.x,s.y+range)
local far=releaseAt(w,1,s.x+range+.5,s.y)
local before=w:Counts().virus;local rng=w._rng
local expected={}
for _,v in ipairs(inside) do expected[#expected+1]={variant=v.variant,phase=v.phase,radius=v.radius} end
expected[#expected+1]={variant=edge[1].variant,phase=edge[1].phase,radius=edge[1].radius}
assert(w:AbsorbableCount()==3 and w.player.mass==oldMass,'查询必须无副作用')
assert(w:AbsorbNearby()==3 and s.mass==oldMass+3 and s.radius>oldRadius)
assert(w._rng==rng,'实体转移不重新抽取外观随机数')
assert(w:Counts().virus==before and far[1].state=='RELEASED')
assert(w.stats.totalAbsorbed==3 and w.stats.totalReleased==4)
assert(eventCount(w,'absorb')==3 and eventCount(w,'absorb_pulse')==1)
for i,v in ipairs(expected) do
 local particle=w.viruses[oldMass+i]
 near(particle.variant,v.variant);near(particle.phase,v.phase);near(particle.radius,v.radius)
end
local pulse=w.events[#w.events]
assert(pulse.name=='absorb_pulse' and pulse.payload.count==3 and pulse.payload.swarmId==s.id)
local effect=w.effects[#w.effects]
assert(effect.kind=='absorb');near(effect.radius,range)
w.time=w.time+w:GetAbsorptionCooldown()
assert(w:AbsorbableCount()==0 and w:AbsorbNearby()==0)
assert(w.stats.totalAbsorbed==3 and s.mass==oldMass+3 and eventCount(w,'absorb')==3)
assert(w.events[#w.events].payload.count==0)
checkConservation(w,true)
""",
    '主动吸附一次不因半径增长连锁扩大原范围': r"""
local w=quietWorld();local s=w.player;local range=s.radius+cfg.activeAbsorptionExtra
releaseAt(w,100,s.x,s.y)
local outside=releaseAt(w,1,s.x+range+.02,s.y)[1]
assert(w:AbsorbNearby()==100 and outside.state=='RELEASED')
assert(s.radius+cfg.activeAbsorptionExtra>distance(s,outside),'增长后新范围应已扩大')
w.time=w.time+w:GetAbsorptionCooldown()
assert(w:AbsorbableCount()==1 and w:AbsorbNearby()==1,'下一次按下才允许使用新范围')
checkConservation(w,true)
""",
    '全部存活游离状态可收终态与寿命边界不可收': r"""
local w=quietWorld();local mass=w.player.mass
local items=releaseAt(w,9,w.player.x,w.player.y)
for i,state in ipairs({'RELEASED','DRIFTING','ATTRACTED','INFECTING'}) do items[i].state=state end
assert(w:KillReleased(items[5]))
items[6].state='LOST';w.stats.totalLost=w.stats.totalLost+1
assert(w:_AbsorbReleased(w.player,items[7]))
items[8].age=items[8].lifetime
items[9].age=items[9].lifetime+10
assert(w:AbsorbableCount()==4 and w:AbsorbNearby()==4)
assert(w.player.mass==mass+5 and w.stats.totalAbsorbed==5)
assert(items[8].state=='RELEASED' and items[9].state=='RELEASED')
w:_MoveReleased(cfg.movementStep)
assert(items[8].state=='LOST' and items[9].state=='LOST' and w.stats.totalLost==3)
assert(w:AbsorbNearby()==0 and w.stats.totalAbsorbed==5)
checkConservation(w,true)
""",
    '真实近距枝间遮挡不穿墙且查询与主动一致': r"""
local w=quietWorld();local s=w.player
place(w,s,14.98,12.55)
local blocked=releaseAt(w,1,17.15,12.55)[1]
assert(distance(s,blocked)<s.radius+cfg.activeAbsorptionExtra)
assert(w.map:Contains(blocked.x,blocked.y,blocked.radius))
assert(w.map:_Sweep(blocked.x,blocked.y,s.x-blocked.x,s.y-blocked.y,blocked.radius)<1)
assert(w:AbsorbableCount()==0 and w:AbsorbNearby()==0 and blocked.state=='RELEASED')
local nearby=releaseAt(w,1,s.x-.1,s.y)[1]
w.time=w.time+w:GetAbsorptionCooldown()
assert(w:AbsorbableCount()==1 and w:AbsorbNearby()==1 and nearby.state=='ABSORBED')
assert(blocked.state=='RELEASED')
checkConservation(w,true)
""",
    '极细空隙精确扫掠不被离散采样漏检': r"""
local w=quietWorld();local s=w.player
-- 使用真实地图形状数据形成0.00001米空隙，仍调用真实Contains/_Sweep/Move。
-- 两圆各自合法，但直线在圆间有暗区；没有替换地图或吸附实现。
w.map.regions={{id=1,x=10,y=20,rx=1,ry=1,inflammation=0,damage=0},
 {id=2,x=11.91001,y=20,rx=1,ry=1,inflammation=0,damage=0}}
w.map._segments={}
place(w,s,10,20)
local v=releaseAt(w,1,11.91001,20)[1]
local fraction=w.map:_Sweep(v.x,v.y,s.x-v.x,s.y-v.y,v.radius)
assert(fraction<1 and fraction>0)
assert(w:AbsorbableCount()==0 and w:AbsorbNearby()==0 and live(v))
""",
    '主动吸附拒绝地图外端点及隐藏受控群': r"""
local w=quietWorld();local s=w.player
local items=releaseAt(w,2,s.x,s.y)
items[1].x,items[1].y=-.001,s.y
s.isHidden=true
assert(w:AbsorbableCount()==0 and w:AbsorbNearby()==0 and w.stats.totalAbsorbed==0)
s.isHidden=false
assert(w:AbsorbableCount()==1 and w:AbsorbNearby()==1)
assert(items[1].state=='RELEASED')
checkConservation(w)
""",
    '自动近距吸收复用转移与外观且没有主动脉冲': r"""
local w=quietWorld();local s=w.player;local mass=s.mass
local v=releaseAt(w,1,s.x,s.y)[1]
local variant,phase=v.variant,v.phase
w:_MoveReleased(cfg.movementStep)
assert(v.state=='ABSORBED' and s.mass==mass+1 and w.stats.totalAbsorbed==1)
local particle=w.viruses[#w.viruses]
assert(particle.variant==variant and particle.phase==phase)
assert(eventCount(w,'absorb')==1 and eventCount(w,'absorb_pulse')==0)
w:_MoveReleased(1);assert(s.mass==mass+1)
checkConservation(w,true)
""",
    '吸附只给当前控制群切群后接收者同步更换': r"""
local w=quietWorld();assert(w:Split());local main,other=w.swarms[1],w.swarms[2]
place(w,other,main.x+3,main.y)
local a=releaseAt(w,1,main.x,main.y)[1]
local b=releaseAt(w,2,other.x,other.y)
local m,o=main.mass,other.mass
assert(w:AbsorbableCount()==1 and w:AbsorbNearby()==1)
assert(main.mass==m+1 and other.mass==o and a.state=='ABSORBED')
assert(w:SwitchControl(other.id))
w.time=w.time+w:GetAbsorptionCooldown()
assert(w:AbsorbableCount()==2 and w:AbsorbNearby()==2)
assert(main.mass==m+1 and other.mass==o+2 and b[1].state=='ABSORBED')
assert(w.events[#w.events].payload.swarmId==other.id)
checkConservation(w,true)
""",
    '貼墙即时增长仍是合法起点可继续移动': r"""
local w=quietWorld();local s=w.player
local x,y=w.map:Move(s.x,s.y,0,s.y,s.radius)
place(w,s,x,y);local oldRadius=s.radius
releaseAt(w,300,s.x,s.y)
assert(w:AbsorbNearby()==300 and s.radius>=oldRadius-1e-7)
assert(w.map:Contains(s.x,s.y,s.radius),'增长不得挤出地图')
local oldX=s.x;w:SetMovement(1,0);step(w,.5)
assert(s.x>oldX+.01,'贴墙增长后仍可向内移动')
checkConservation(w,true)
""",
    '无活群主动自动吸附都不能复活且操作门控': r"""
local sim=newSim('UPPER_AIRWAY',true);local w=sim.world
releaseAt(w,2,w.player.x,w.player.y)
sim:SetPaused('observation',true)
assert(sim:AbsorbNearby()==0 and w.stats.totalAbsorbed==0)
sim:SetPaused('observation',false)
assert(sim:AbsorbNearby()==2)
releaseAt(w,3,w.player.x,w.player.y)
w:DamageSwarm(w.player.id,w.player.mass)
assert(w:AbsorbableCount()==0 and w:AbsorbNearby()==0 and not w:CanSplit() and not w:SwitchControl())
w:_MoveReleased(cfg.movementStep)
assert(#w.swarms==0 and w:ControlledCount()==0 and w.stats.totalAbsorbed==2)
sim:Update(cfg.movementStep)
assert(sim.ending=='extinct' and sim:AbsorbNearby()==0)
checkConservation(w,true)
local q=Sim.New();assert(q:AbsorbNearby()==0 and not q:SwitchControl(1))
""",
    '六群容量阻止第七群且成本统计守恒': r"""
local w=manyGroups(6)
assert(#w.swarms==6 and w.stats.totalSplits==5)
local before=w:Counts().virus;local cost=w.stats.splitCost;w.splitCooldown=0
assert(not w:CanSplit() and not w:Split())
assert(w:Counts().virus==before and w.stats.splitCost==cost)
local c=w:Counts();local sum=0
for _,group in ipairs(w.swarms)do if not group.isMainSwarm then sum=sum+group.mass end end
assert(c.splitMass==sum and c.mainMass+c.splitMass==c.controlled)
checkConservation(w)
""",
    '六群按存活顺序循环定点切换同群无效及输入清理': r"""
local w=manyGroups(6);assert(w:SwitchControl(w.swarms[1].id) or w.player==w.swarms[1])
local main=w:MainSwarm();local visited={}
for i=2,7 do
 w:SetMovement(1,1)
 assert(w:SwitchControl())
 local expected=w.swarms[(i-1)%6+1]
 assert(w.player==expected and w._inputX==0 and w._inputY==0)
 assert(w:MainSwarm()==main and main.isMainSwarm)
 visited[expected.id]=true
 checkConservation(w)
end
local count=0;for _ in pairs(visited) do count=count+1 end;assert(count==6)
assert(w:SwitchControl(w.swarms[5].id) and w.player==w.swarms[5])
w:SetMovement(1,0);local events=eventCount(w,'switch_control')
assert(not w:SwitchControl(w.player.id) and not w:SwitchControl(99999))
assert(w._inputX==1 and eventCount(w,'switch_control')==events,'无效切换不修改输入/事件')
local dead=w.swarms[3];w:DamageSwarm(dead.id,dead.mass)
assert(not w:SwitchControl(dead.id))
assert(w:SwitchControl(w.swarms[1].id))
for i=2,6 do assert(w:SwitchControl() and w.player==w.swarms[(i-1)%5+1]) end
checkConservation(w)
""",
    '真实八秒冷却后分群可以继续分裂且最低质量门控一致': r"""
local w=quietWorld();w.maxPlayerSwarms=4;growByAbsorption(w,60);assert(w:Split())
local other=w.swarms[2];place(w,other,w.player.x+3,w.player.y)
assert(w:SwitchControl(other.id))
other.isHidden=true;step(w,cfg.splitCooldown-cfg.movementStep)
assert(w.splitCooldown>0 and not w:CanSplit() and not w:Split())
step(w,cfg.movementStep);other.isHidden=false
assert(w:CanSplit() and w:Split() and #w.swarms==3)
w.splitCooldown=0
w:DamageSwarm(w.player.id,math.max(0,w.player.mass-cfg.splitMinMass+1))
assert(not w:CanSplit() and not w:Split())
checkConservation(w,true)
""",
    'Sim定点与循环切换门控清触屏输入': r"""
local s=newSim('UPPER_AIRWAY',true);local w=s.world;assert(s:Split())
local id=w.swarms[2].id;s.touchMove={x=1,y=1,active=true}
s:SetPaused('observation',true)
assert(not s:SwitchControl(id) and w.player==w:MainSwarm())
s:SetPaused('observation',false)
s.touchMove={x=1,y=1,active=true};assert(s:SwitchControl(id))
assert(not s.touchMove.active and s.touchMove.x==0 and s.touchMove.y==0)
s.touchMove={x=1,y=0,active=true};assert(not s:SwitchControl(id) and s.touchMove.active)
assert(s:SwitchControl() and w.player==w:MainSwarm() and not s.touchMove.active)
s:FinishRun('victory');assert(not s:SwitchControl(id) and s:AbsorbNearby()==0)
""",
    '多群仅分群合并保低id并保留无关主控群': r"""
local w=manyGroups(4);local main=w:MainSwarm()
assert(w:SwitchControl(main.id) or w.player==main)
local a,b=w.swarms[2],w.swarms[3];local unrelated=w.swarms[4]
place(w,a,main.x+3,main.y);place(w,b,a.x+.1,a.y)
place(w,unrelated,7.1,18)
a.exposedCells[11]=true;b.exposedCells[22]=true;unrelated.exposedCells[33]=true
local before=w:Counts().virus;local mass=a.mass+b.mass;local otherMass=unrelated.mass
w:SetMovement(1,0)
assert(w:_Merge(b,a),'逆序参数也应保低id')
assert(w:SwarmById(a.id)==a and not w:SwarmById(b.id) and a.mass==mass)
assert(w.player==main and w.currentControlledSwarmId==main.id and w._inputX==1)
assert(w:MainSwarm()==main and w:SwarmById(unrelated.id)==unrelated and unrelated.mass==otherMass)
assert(a.exposedCells[11] and a.exposedCells[22] and not a.exposedCells[33])
assert(unrelated.exposedCells[33] and #w.swarms==3 and w:Counts().virus==before)
assert(not w:_Merge(a,b) and w.stats.totalMerges==1,'旧引用不能重复合并')
checkConservation(w,true);pairsValid(w)
""",
    '分群合并保当前控制id且主群参与总保主id': r"""
local w=manyGroups(4);local main=w:MainSwarm()
local a,b=w.swarms[2],w.swarms[3]
place(w,a,main.x+3,main.y);place(w,b,a.x+.1,a.y)
assert(w:SwitchControl(b.id));w:SetMovement(1,0)
local total=a.mass+b.mass
assert(w:_Merge(a,b) and w.player==b and b.mass==total and w._inputX==1)
assert(w:MainSwarm()==main and not w:SwarmById(a.id))
local rest=w.swarms[#w.swarms]
place(w,b,main.x+.1,main.y);w:SetMovement(1,0)
assert(w:_Merge(b,main))
assert(w.player==main and w:MainSwarm()==main and w.currentControlledSwarmId==main.id)
assert(w._inputX==0 and w:SwarmById(rest.id)==rest)
checkConservation(w,true)
""",
    '多近距群对完整快照保护隐藏与失效对剔除': r"""
-- 显式禁AI隔离旧合并对枚举；默认自主群不主动合并另由autonomy回归验证。
cfg.autonomy.enabled=false
local w=manyGroups(4);local main=w:MainSwarm()
for _,s in ipairs(w.swarms) do place(w,s,main.x,main.y) end
w:_RefreshMergePairs();assert(#w.mergePairs==6);pairsValid(w)
local hidden=w.swarms[4];hidden.isHidden=true
w:_RefreshMergePairs();assert(#w.mergePairs==3);pairsValid(w)
local protected=w.swarms[3];protected.mergeGrace=2
w:_RefreshMergePairs();assert(#w.mergePairs==1);pairsValid(w)
local cleared=w.swarms[2];w:DamageSwarm(cleared.id,cleared.mass)
assert(#w.mergePairs==0 and not w.mergeReady)
hidden.isHidden=false;protected.mergeGrace=0
w:_RefreshMergePairs();assert(#w.mergePairs==3);pairsValid(w)
checkConservation(w,true)
""",
    '同帧重叠六群不重复合并也不丢实体': r"""
-- 旧群对去重/守恒的隔离测试，不把自主行动的新合并优先级当回归失败。
cfg.autonomy.enabled=false
local w=manyGroups(6);local main=w:MainSwarm()
for _,s in ipairs(w.swarms) do place(w,s,main.x,main.y) end
local before=w:Counts().virus
w:_MoveGroups(cfg.movementStep)
assert(#w.swarms==3 and w.stats.totalMerges==3,'每群本步最多合并一次')
assert(w:Counts().virus==before);checkConservation(w,true);pairsValid(w)
for _=1,5 do w:_MoveGroups(cfg.movementStep);checkConservation(w,true);pairsValid(w) end
assert(#w.swarms==1 and w.stats.totalMerges==5 and w:MainSwarm()==main)
""",
    '已接触分群优先合并不被低id远距吸引饿死': r"""
-- 隔离旧排序算法；自主群在默认模式下不主动合并。
cfg.autonomy.enabled=false
local w=quietWorld();local a=w.player
w.maxPlayerSwarms=4 -- 此用例隔离合并排序，显式使用扩容后的容量。
growByAbsorption(w,45);assert(w:Split());w.splitCooldown=0;assert(w:Split())
local b,c=w.swarms[2],w.swarms[3]
place(w,a,12.9,27.4);place(w,b,14.2,27.4);place(w,c,14.2,27.4)
a.vx=-cfg.baseSpeed;w:SetMovement(-1,0)
local before=w:Counts().virus
w:_RefreshMergePairs()
assert(#w.mergePairs>=2 and distance(a,b)>a.radius+b.radius)
local first=w.mergePairs[1]
local splitTotal=b.mass+c.mass;local mainMass=a.mass
w:Update(cfg.movementStep)
assert(w.stats.totalMerges==1 and #w.swarms==2,'BC应在第一个实际移动步完成合并')
assert(first.aId==b.id and first.bId==c.id,'已接触BC必须排在仅近距吸引AB/AC前')
assert(w:SwarmById(b.id)==b and not w:SwarmById(c.id) and b.mass==splitTotal)
assert(w.player==a and w:MainSwarm()==a and a.mass==mainMass,'远处无关主控群不得被抢占')
step(w,3-cfg.movementStep)
assert(w.stats.totalMerges>=1 and w:Counts().virus==before)
checkConservation(w,true);pairsValid(w)
""",
    '近距分群自动合并不清无关第三群': r"""
-- 禁AI隔离旧纯自动合并删除对象；新版自主语义不把忙碌群牵引回收。
cfg.autonomy.enabled=false
local w=manyGroups(4);local main=w:MainSwarm()
local a,b=w.swarms[2],w.swarms[3];local unrelated=w.swarms[4]
place(w,a,main.x+3,main.y);place(w,b,a.x+.1,a.y)
place(w,unrelated,7.1,18)
assert(w:SwitchControl(main.id) or w.player==main)
local mass=unrelated.mass;local before=w:Counts().virus
w:Update(cfg.movementStep)
assert(w.stats.totalMerges==1 and #w.swarms==3 and w:SwarmById(unrelated.id)==unrelated)
assert(w.player==main and unrelated.mass==mass and w:Counts().virus==before)
checkConservation(w,true)
""",
    '六群清除升主死亡控制清输入仍可循环和再分裂': r"""
local w=manyGroups(6);local main=w:MainSwarm();local active=w.swarms[5]
assert(w:SwitchControl(active.id));w:SetMovement(1,0)
w:DamageSwarm(main.id,main.mass)
assert(w:MainSwarm()==w.swarms[1] and w.player==active and w._inputX==1)
local oldId=active.id;w:DamageSwarm(active.id,active.mass)
assert(w.player==w.swarms[1] and w._inputX==0 and w._inputY==0)
assert(not w:SwitchControl(oldId) and w:SwitchControl())
w.splitCooldown=0
assert(w:CanSplit() and w:Split() and #w.swarms==5)
checkConservation(w)
""",
    '自然清群切换也清Sim触屏方向': r"""
local sim=newSim('DEEP_LUNG');local w=sim.world
assert(sim:Split());local main,other=w.swarms[1],w.swarms[2]
local im=w.immunes[1];w.immunes={im};local c=w.cells[1];w.cells={c}
place(w,other,main.x+3,main.y);other.isHidden=true
w:DamageSwarm(main.id,main.mass-cfg.immuneKillsPerAttack)
im.x,im.y=main.x,main.y
im.regionId=main.currentRegionId
im._oldX,im._oldY,im._patrolX,im._patrolY=im.x,im.y,im.x,im.y
awaitState(w,im,'attack');assert(im.targetId==main.id);other.isHidden=false
im.attackTimer=cfg.movementStep*.5
sim.touchMove={x=1,y=0,active=true}
w:SetMovement(1,0)
sim:Tick(cfg.movementStep)
assert(w.player==other and not sim.touchMove.active and sim.touchMove.x==0)
assert(w._inputX==0 and w:MainSwarm()==other and not sim.ending)
checkConservation(w,true)
""",
    '增长倍率越过旧2与总3上限仍严格单调': r"""
local w=quietWorld();local s=w.player;local c=unitCell(w);w.cells={c}
local previous=0
for _,mass in ipairs({30,40,90,160,360,640}) do
 if s.mass<mass then growByAbsorption(w,mass-s.mass) end
 c=unitCell(w,1,s.x,s.y)
 local multiplier=w:GroupInfectionMultiplier(s)
 near(multiplier,math.sqrt(mass/cfg.densityReference))
 assert(multiplier>previous);previous=multiplier
 w:_AccumulateExposure(cfg.movementStep)
 near(c._charge,cfg.movementStep*multiplier/cfg.infectionSeconds)
 near(c._groupCharge,c._charge);near(c._releasedCharge,0)
 w:_InfectCells();checkConservation(w,true)
end
assert(previous>3,'群质量增长不能停在旧功率上限')
""",
    '多群实际接触功率相加Released独立封顶贡献准确': r"""
local w=manyGroups(4);local c=unitCell(w);w.cells={c}
local groupPower=0
for _,s in ipairs(w.swarms) do
 place(w,s,c.x,c.y);s.exposedCells[c.id]=true
 groupPower=groupPower+w:GroupInfectionMultiplier(s)
end
assert(groupPower>3)
releaseAt(w,100,c.x,c.y)
local dt=cfg.movementStep;w:_AccumulateExposure(dt)
near(c._charge,dt*(groupPower+3)/cfg.infectionSeconds)
near(c._groupCharge,dt*groupPower/cfg.infectionSeconds)
near(c._releasedCharge,dt*3/cfg.infectionSeconds)
near(c._groupCharge+c._releasedCharge,c._charge)
w:_InfectCells();checkConservation(w,true)
""",
    '未受控自主群真实接触贡献且隐藏群不贡献增长功率': r"""
local w=manyGroups(4);local main=w:MainSwarm()
assert(w:SwitchControl(main.id) or w.player==main)
local c=unitCell(w);w.cells={c}
local power=0
for _,s in ipairs(w.swarms) do place(w,s,c.x,c.y);power=power+w:GroupInfectionMultiplier(s) end
local dt=cfg.movementStep
w:_AccumulateExposure(dt)
near(c._groupCharge,dt*power/cfg.infectionSeconds)
w:_InfectCells()
local contributor=w.swarms[2]
assert(contributor.exposedCells[c.id],'未受控群必须由真实接触自动获得新感染资格')
contributor.isHidden=true;c._charge,c._groupCharge,c._releasedCharge=0,0,0
w:_AccumulateExposure(dt)
near(c._groupCharge,dt*(power-w:GroupInfectionMultiplier(contributor))/cfg.infectionSeconds)
checkConservation(w,true)
""",
    '增长后相同接触条件完成感染所需真实步数减少': r"""
local function ticksAtMass(mass)
 local w=quietWorld()
 if mass>w.player.mass then growByAbsorption(w,mass-w.player.mass) end
 local c=unitCell(w);w.cells={c};local ticks=0
 while c.state~='LATENT' do
  w:_AccumulateExposure(cfg.movementStep)
  w:_InfectCells();ticks=ticks+1
  assert(ticks<2000)
 end
 assert(c.infectionSource=='player' and c.latencyTimer==0 and w.stats.totalReleased==mass-30)
 return ticks
end
local small,medium,large=ticksAtMass(30),ticksAtMass(160),ticksAtMass(640)
assert(small>medium and medium>large,'质量增长必须真的缩短达到感染完成的时间')
""",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', action='append', default=[], help='按名称子串筛选，可重复')
    parser.add_argument('--report', type=Path, help='保存新的 JSON 验证报告')
    args = parser.parse_args()
    selected = {name: code for name, code in TESTS.items()
                if not args.only or any(part in name for part in args.only)}
    if not selected:
        parser.error('未选中测试')
    started = time.perf_counter()
    results = []
    for name, code in selected.items():
        logs = []
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().test_log = lambda *items: logs.append(' '.join(map(str, items)))
        lua.globals().TEST_PACKAGE_PATH = str(ROOT / 'scripts' / '?.lua')
        case_start = time.perf_counter()
        try:
            lua.execute("package.path=TEST_PACKAGE_PATH..';'..package.path;print=test_log")
            lua.execute(SETUP)
            lua.execute(GROWTH_SETUP)
            lua.execute(code)
            result = {'name': name, 'passed': True, 'seconds': time.perf_counter()-case_start}
            print(f'PASS {name} ({result["seconds"]:.2f}s)')
        except Exception as exc:
            result = {'name': name, 'passed': False, 'seconds': time.perf_counter()-case_start,
                      'error': str(exc), 'logs': logs[-12:]}
            print(f'FAIL {name}\n{exc}')
            for line in logs[-12:]:
                print('  日志', line)
        results.append(result)
    passed = sum(item['passed'] for item in results)
    duration = time.perf_counter()-started
    print(f'{passed}/{len(results)} 通过，耗时 {duration:.2f}s')
    print('未验收：实际引擎按钮/快捷键/触屏/画面、完整10～15分钟胜败路线及数值平衡。')
    if args.report:
        report = {'passed': passed, 'total': len(results), 'seconds': duration,
                  'runtime': '真实 Lua 5.4 / lupa，真实 Core 与地图', 'results': results,
                  'not_accepted': ['实际引擎交互与画面', '完整局长、胜败路线和数值平衡']}
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
