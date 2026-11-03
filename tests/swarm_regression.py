"""感染网络新协议回归：真实 Core 模块、独立 Lua 5.4，不依赖引擎或网络。

依据 docs/玩法重做.md 第一优先级及确认口径：活群清零未胜即失败；
EXPOSED 不算已完成节点；阶段只前进；Released 不提供远程复活/自动归队。
每例新 LuaRuntime 隔离配置。单元例仅禁用免疫出生/招募，不替换免疫实现。
默认末尾运行三分钟真实免疫压力模拟，属于守恒/稳定性检查，不是15～20分钟平衡验收。
运行：python3 /workspace/tests/swarm_regression.py [--only 子串] [--no-stress]
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, '/home/Maker/.local/swarm-test')
from lua_test_runtime import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
SETUP = r"""
Config = require('Core.Config')
World = require('Core.SwarmWorld')
Sim = require('Core.SimState')
Immune = require('Core.ImmuneSystem')
Bus = require('Core.EventBus')
cfg = Config.Gameplay
-- Historical mechanism fixtures contain authored 26x32 coordinates and IDs.
-- Pin that layout explicitly; seeded production layout has separate coverage.
cfg.mapGenerationVersion=1;cfg.width=26;cfg.height=32;cfg.cellCount=72

function near(a,b,epsilon)
 assert(math.abs(a-b)<=(epsilon or 1e-7), tostring(a)..' ~= '..tostring(b))
end
function finite(x) return x==x and x~=math.huge and x~=-math.huge end
function distance(a,b) return math.sqrt((a.x-b.x)^2+(a.y-b.y)^2) end
function noImmune()
 cfg.immuneMax=0
 for _,def in ipairs(Config.StartRegions) do def.immuneCount=0 end
end
function quietWorld(start)
 noImmune()
 local w=World.New(start or 'UPPER_AIRWAY')
 -- 默认单元夹具放在宽阔深肺合法空间，但保留上呼吸道30质量/无初始节点。
 -- 显式start的开局/地图测试不移动出生点。
 if not start then
  local p=w.map.startPoints.DEEP_LUNG
  place(w,w.player,p.x,p.y)
 end
 return w
end
function newSim(start,quiet)
 if quiet then noImmune() end
 local s=Sim.New()
 assert(s:StartRun(start or 'UPPER_AIRWAY'))
 return s
end
function step(w,seconds)
 local n=math.floor(seconds/cfg.movementStep+.5)
 for _=1,n do w:Update(cfg.movementStep) end
end
function simStep(s,seconds,fps)
 local frame=1/(fps or 60)
 for _=1,math.floor(seconds/frame+.5) do s:Update(frame) end
end
function age(w,seconds)
 for _=1,math.floor(seconds/cfg.diseaseStep+.5) do w:_AgeCells(cfg.diseaseStep) end
end
function progress(w,seconds)
 local n=math.floor(seconds/cfg.movementStep+.5)
 for _=1,n do w:_AccumulateExposure(cfg.movementStep) end
 w:_InfectCells()
end
function unitCell(w,id,x,y)
 local c=assert(w.cells[id or 1])
 c.x,c.y=x or w.player.x,y or w.player.y
 assert(w.map:Contains(c.x,c.y,c.radius),'单元夹具必须位于真实地图内')
 c.regionId=w.map:RegionAt(c.x,c.y)
 c.state,c.exposure='HEALTHY',0
 c.infectedAge,c.latencyTimer,c.productiveTimer,c.releaseCount=0,0,0,0
 c.exhaustionTimer,c.exhaustedReleaseTimer,c.immuneHits=0,0,0
 c.covered,c.everPlayerContact,c.infectionSource=false,false,'none'
 c.groupContribution,c.releasedContribution=0,0
 c._charge,c._groupCharge,c._releasedCharge=0,0,0
 return c
end
function place(w,swarm,x,y)
 assert(w.map:Contains(x,y,swarm.radius),'群夹具必须位于真实地图内')
 swarm.x,swarm.y,swarm.vx,swarm.vy=x,y,0,0
 swarm.currentRegionId=w.map:RegionAt(x,y)
 swarm.launchTimer,swarm.mergeGrace=0,0
 w:_UpdateParticles()
end
function eventCount(w,name)
 local count=0
 for _,event in ipairs(w.events) do if event.name==name then count=count+1 end end
 return count
end
function live(v) return v.state~='ABSORBED' and v.state~='CLEARED' and v.state~='LOST' end
function checkConservation(w,checkBounds)
 local c=w:Counts()
 local st=w.stats
 assert(st.initialMass+st.totalReleased-st.totalKilled-st.totalLost-st.splitCost==c.virus,
  string.format('守恒失败 initial=%d released=%d killed=%d lost=%d cost=%d counts=%d absorbed=%d',
   st.initialMass,st.totalReleased,st.totalKilled,st.totalLost,st.splitCost,c.virus,st.totalAbsorbed))
 assert(#w.viruses==c.controlled,'群粒子实体数必须等于所有群总mass')
 assert(c.virus==c.controlled+c.released and c.groups==#w.swarms)
 assert(c.healthy+c.exposed+c.latent+c.productive+c.exhausted+c.dead==#w.cells,'六态分类遗漏')
 local counts,ids={},{}
 for _,v in ipairs(w.viruses) do
  assert(not ids[v.id],'群粒子id重复'); ids[v.id]=true
  assert(w:SwarmById(v.swarmId),'粒子引用死亡/不存在的群')
  counts[v.swarmId]=(counts[v.swarmId] or 0)+1
  assert(finite(v.x) and finite(v.y))
  if checkBounds then assert(w.map:Contains(v.x,v.y,v.radius),'群粒子越过组织边界') end
 end
 local main,controlled=0,0
 for _,s in ipairs(w.swarms) do
  assert(s.mass>0 and s.mass==math.floor(s.mass) and (counts[s.id] or 0)==s.mass)
  assert(finite(s.x) and finite(s.y) and finite(s.vx) and finite(s.vy))
  if s.isMainSwarm then main=main+1 end
  if s.isPlayerControlled then controlled=controlled+1; assert(s.id==w.currentControlledSwarmId) end
  if checkBounds then assert(w.map:Contains(s.x,s.y,s.radius),'群中心越过组织边界') end
 end
 assert(main==(#w.swarms>0 and 1 or 0) and controlled==main,'活群唯一主群/受控群标记')
 local releasedIds={}
 for _,v in ipairs(w.releasedViruses) do
  assert(not releasedIds[v.id],'Released id重复'); releasedIds[v.id]=true
  assert(finite(v.x) and finite(v.y))
  if checkBounds and live(v) then assert(w.map:Contains(v.x,v.y,v.radius),'Released越过组织边界') end
 end
end
function immuneFixture(kind)
 local w=World.New('DEEP_LUNG')
 local im=assert(w.immunes[kind=='tcell' and 2 or 1],'真实免疫初始化失败')
 w.immunes={im}; local fixtureCell=w.cells[1]; w.cells={fixtureCell}
 im.kind=kind or 'macrophage'
 place(w,w.player,w.player.x,w.player.y)
 im.x,im.y=w.player.x,w.player.y
 im.regionId=w.player.currentRegionId
 im._oldX,im._oldY,im._patrolX,im._patrolY=im.x,im.y,im.x,im.y
 im.state,im.stateTimer='patrol',0
 im.targetType,im.targetId,im.targetX,im.targetY=nil,nil,nil,nil
 im.warningTimer,im.attackTimer,im.cooldown,im._stuckTimer=0,0,0,0
 return w,im
end
function advanceImmune(w,seconds)
 for _=1,math.floor(seconds/cfg.movementStep+.5) do Immune.Update(w,cfg.movementStep) end
end
function awaitState(w,im,state,timeout)
 for _=1,math.floor((timeout or 15)/cfg.movementStep) do
  if im.state==state then return end
  Immune.Update(w,cfg.movementStep)
 end
 assert(im.state==state,'免疫未进入 '..state..'，当前 '..im.state)
end
"""

TESTS = {
'开局三选择真实数量与六态': r"""
for _,def in ipairs(Config.StartRegions) do
 local w=World.New(def.type); local c=w:Counts()
 assert(c.groups==1 and c.mainMass==def.mass and c.controlled==def.mass)
 assert(c.latent==def.initialNodes and c.infected==def.initialNodes and c.released==0)
 assert(c.healthy+c.latent==cfg.cellCount and c.exposed==0 and c.dead==0)
 assert(#w.immunes>0 and #w.immunes<=def.immuneCount)
 assert(w.player.currentRegionId==w.map:RegionAt(w.player.x,w.player.y))
 checkConservation(w,true)
end
""",
'开局选择暂停及非法选项不修改': r"""
local s=Sim.New(); local w=s.world
assert(not s.started and s.paused and s.pauseReasons.selection)
s:Update(10); assert(s.time==0 and w.time==0)
assert(not s:Split() and not s:SwitchControl())
assert(not s:StartRun('not_a_region') and s.world==w and not s.started)
assert(s:StartRun('TRACHEA') and s.started and not s.paused and next(s.pauseReasons)==nil)
assert(s.selectedStartRegion=='TRACHEA' and s.world.startType=='TRACHEA')
""",
'地图固定锚点确定性且种子仅影响外观': r"""
local a=quietWorld('UPPER_AIRWAY'); local b=quietWorld('DEEP_LUNG')
assert(#a.cells==#b.cells and #a.map.regions==#b.map.regions)
for i,c in ipairs(a.cells) do local other=b.cells[i]
 near(c.x,other.x); near(c.y,other.y); near(c.radius,other.radius)
 assert(c.regionId==other.regionId)
end
local oldSeed=cfg.seed; cfg.seed=oldSeed+17; local d=quietWorld()
local different=false
for i,r in ipairs(a.map.regions) do
 local q=d.map.regions[i]; assert(r.type==q.type and r.depth==q.depth)
 assert(#r.neighbors==#q.neighbors)
 for j,id in ipairs(r.neighbors) do assert(id==q.neighbors[j]) end
end
for i,c in ipairs(a.cells) do
 local q=d.cells[i]; near(c.x,q.x); near(c.y,q.y)
 if c.radius~=q.radius or c.phase~=q.phase or c.rotation~=q.rotation or c.variant~=q.variant then different=true end
end
assert(different,'固定地图种子应改变细胞外观，不要求随机布局')
""",
'地图Verify三开局及大步不能穿枝间空隙': r"""
for _,def in ipairs(Config.StartRegions) do
 local w=quietWorld(def.type); local ok,errors=w.map:Verify()
 assert(ok,table.concat(errors,'; '))
 local x,y=w.map:Move(10.5,18,16,18,.5)
 assert(x<13 and w.map:Contains(x,y,.5),'大步量跨越中央空隙')
 local ix,iy=w.map:Move(13,19,7,18,.5)
 assert(ix==13 and iy==19,'非法起点不能被传送修正到另一枝')
 assert(w.map:RegionAt(13,19)==0 and w.map:DepthAt(13,19)==0)
end
""",
'地图细胞间距无重叠且位置合法': r"""
for _,seed in ipairs({314159,314176,20261005}) do
 cfg.seed=seed; local w=quietWorld()
 for i,a in ipairs(w.cells) do
  assert(w.map:Contains(a.x,a.y,a.radius),'细胞超出组织轮廓')
  for j=i+1,#w.cells do local b=w.cells[j]
   assert(distance(a,b)>=a.radius+b.radius+1e-7,'细胞重叠 '..i..'/'..j)
  end
 end
 checkConservation(w,true)
end
""",
'固定宏观连接与真实轮廓栅格可达': r"""
local w=quietWorld('UPPER_AIRWAY'); local regions=w.map.regions
local types,seen={},{}
for _,r in ipairs(regions) do types[r.type]=r end
for _,name in ipairs({'UPPER_AIRWAY','TRACHEA','BRONCHUS_LEFT','BRONCHUS_RIGHT','DEEP_LUNG'}) do
 assert(types[name], '缺少宏观区域 '..name)
end
local function edge(a,b)
 local found=false
 for _,id in ipairs(types[a].neighbors) do if regions[id].type==b then found=true end end
 assert(found,'缺少连接 '..a..' -> '..b)
end
edge('UPPER_AIRWAY','TRACHEA'); edge('TRACHEA','BRONCHUS_LEFT')
edge('TRACHEA','BRONCHUS_RIGHT'); edge('BRONCHUS_LEFT','DEEP_LUNG')
edge('BRONCHUS_RIGHT','DEEP_LUNG')
-- 真实轮廓、群半径和采样连线的BFS，不只信任neighbors/生成器的valid标记。
local h=.25; local radius=w.player.radius
local nx,ny=math.floor(w.width/h)+1,math.floor(w.height/h)+1
local function key(x,y) return y*nx+x+1 end
local sx,sy=math.floor(w.player.x/h+.5),math.floor(w.player.y/h+.5)
assert(w.map:Contains(sx*h,sy*h,radius),'栅格出生点不可通')
local queue={{sx,sy}}; seen[key(sx,sy)]=true; local index=1
while index<=#queue do
 local p=queue[index]; index=index+1
 for _,delta in ipairs({{1,0},{-1,0},{0,1},{0,-1}}) do
  local x,y=p[1]+delta[1],p[2]+delta[2]
  if x>=0 and x<nx and y>=0 and y<ny and not seen[key(x,y)]
    and w.map:Contains(x*h,y*h,radius)
    and w.map:Contains((x+p[1])*h/2,(y+p[2])*h/2,radius) then
   seen[key(x,y)]=true; queue[#queue+1]={x,y}
  end
 end
end
local reached,normal,normalReached,deep=0,0,0,false
for _,p in ipairs(queue) do if w.map:DepthAt(p[1]*h,p[2]*h)>=4 then deep=true end end
for _,c in ipairs(w.map.cells) do
 local accessible=false
 for dx=-4,4 do for dy=-4,4 do
  local x,y=math.floor(c.x/h+.5)+dx,math.floor(c.y/h+.5)+dy
  if x>=0 and x<nx and y>=0 and y<ny and seen[key(x,y)]
    and math.sqrt((x*h-c.x)^2+(y*h-c.y)^2)<=radius+c.radius+cfg.infectionReach then accessible=true end
 end end
 if accessible then reached=reached+1 end
 if c.cellType==nil or c.cellType=='normal' or c.cellType=='NORMAL' then
  normal=normal+1; if accessible then normalReached=normalReached+1 end
 end
end
assert(deep,'真实轮廓无法到达肺部深区')
assert(reached/#w.cells>=.8,'真实轮廓只能到达 '..reached..'/'..#w.cells..' 个感染目标')
if normal>0 then assert(normalReached/normal>=.8,'普通细胞可达率不足80%') end
""",
'出生邻近目标与不重叠': r"""
for _,def in ipairs(Config.StartRegions) do
 local w=quietWorld(def.type); local p=w.player
 assert(w.map:Contains(p.x,p.y,p.radius))
 local nearTargets=0; local nearest=math.huge
 for _,c in ipairs(w.cells) do
  local d=distance(p,c); nearest=math.min(nearest,d-p.radius-c.radius)
  assert(d>=p.radius+c.radius,'出生群与细胞重叠')
  if distance(p,c)<=2 then nearTargets=nearTargets+1 end
 end
 assert(nearTargets>=2 and nearTargets<=4,'出生2米内必须有2～4个普通细胞')
 assert(nearest<=cfg.baseSpeed*5,'出生到第一目标需超过5秒')
end
""",
'组织流非装饰且主分群Released响应不同': r"""
local w=quietWorld('TRACHEA'); w.cells={}
local fx,fy=w.map:FlowAt(w.player.x,w.player.y,0)
assert(finite(fx) and finite(fy) and fx*fx+fy*fy>1e-6,'出生通道缺少真实流场')
local x,y=w.player.x,w.player.y; w:SetMovement(0,0); step(w,1)
assert(distance(w.player,{x=x,y=y})>1e-4,'无输入主群也应受组织流影响')
assert(cfg.releasedFlowInfluence>cfg.splitFlowInfluence and cfg.splitFlowInfluence>cfg.playerFlowInfluence)
""",
'HEALTHY到EXPOSED再LATENT不立即释放': r"""
local w=quietWorld(); local c=unitCell(w); w.cells={c}
progress(w,1); assert(c.state=='EXPOSED' and c.exposure>0 and c.exposure<1)
assert(c.latencyTimer==0 and w.stats.totalReleased==0)
progress(w,cfg.infectionSeconds*2)
assert(c.state=='LATENT' and c.exposure==1 and c.latencyTimer==0)
assert(w.stats.totalInfected==1 and w.stats.totalReleased==0 and #w.releasedViruses==0)
assert(eventCount(w,'infection_complete')==1)
progress(w,10); assert(w.stats.totalInfected==1 and eventCount(w,'infection_complete')==1)
""",
'距离越近感染越快': r"""
local w=quietWorld(); local c=unitCell(w); w.cells={c}
progress(w,1); local close=c.exposure
c.state,c.exposure,c._charge,c._groupCharge,c._releasedCharge='HEALTHY',0,0,0,0
local x,y=w.player.x,w.player.y
place(w,w.player,x+.75,y); progress(w,1)
assert(c.exposure>0 and c.exposure<close,'感染速度未随距离降低')
""",
'密度越高感染越快且仅Released功率独立封顶': r"""
local w=quietWorld(); local c=unitCell(w); w.cells={c}
progress(w,1); local dense=c.exposure
w:DamageSwarm(w.player.id,24); checkConservation(w)
c.state,c.exposure,c._charge,c._groupCharge,c._releasedCharge='HEALTHY',0,0,0,0
progress(w,1)
assert(c.exposure>0 and c.exposure<dense,'质量降低应降低感染速度')
w:_Release(c,100)
for _,v in ipairs(w.releasedViruses) do v.x,v.y=c.x,c.y end
c.state,c.exposure,c._charge,c._groupCharge,c._releasedCharge='HEALTHY',0,0,0,0
progress(w,1); near(c.exposure,(3+w:GroupInfectionMultiplier(w.player))/cfg.infectionSeconds)
checkConservation(w)
""",
'离开慢回落且完全回落重置来源': r"""
local w=quietWorld(); local c=unitCell(w); w.cells={c}
progress(w,2); local before=c.exposure
place(w,w.player,w.player.x+3,w.player.y)
progress(w,.5); assert(c.state=='EXPOSED' and not c.covered and c.exposure>0)
near(c.exposure,before-cfg.exposureDecay*.5)
assert(cfg.exposureDecay<before/2,'回落应小于接触增长')
progress(w,before/cfg.exposureDecay+1)
assert(c.state=='HEALTHY' and c.exposure==0 and not c.everPlayerContact)
assert(c.groupContribution==0 and c.releasedContribution==0 and not w.player.exposedCells[c.id])
""",
'瞬间接触不虚增半秒感染': r"""
local w=quietWorld(); local c=unitCell(w); w.cells={c}
w:_AccumulateExposure(cfg.movementStep)
local expected=cfg.movementStep*math.sqrt(w.player.mass/cfg.densityReference)/cfg.infectionSeconds
place(w,w.player,w.player.x+3,w.player.y)
for _=1,29 do w:_AccumulateExposure(cfg.movementStep) end
w:_InfectCells()
near(c.exposure,math.max(0,expected-cfg.exposureDecay*29*cfg.movementStep))
""",
'六态独立潜伏计时与第一批只一次': r"""
local w=quietWorld(); local a,b=unitCell(w,1),unitCell(w,2,w.player.x+2,w.player.y)
w.cells={a,b}; w:_Infect(a,'player'); age(w,5); w:_Infect(b,'player')
age(w,cfg.latentSeconds-5-cfg.diseaseStep)
assert(a.state=='LATENT' and b.state=='LATENT' and w.stats.totalReleased==0)
age(w,cfg.diseaseStep)
assert(a.state=='PRODUCTIVE' and b.state=='LATENT' and a.releaseCount==1)
assert(w.stats.totalReleased==cfg.releaseBatches[1] and eventCount(w,'release_batch')==1)
near(b.latencyTimer,cfg.latentSeconds-5)
age(w,5); assert(b.state=='PRODUCTIVE' and b.releaseCount==1)
assert(w.stats.totalReleased==2*cfg.releaseBatches[1])
checkConservation(w)
""",
'分批释放独立次数耗竭死亡不再释放': r"""
local w=quietWorld(); local c=unitCell(w); w.cells={c}; w:_Infect(c,'player')
age(w,cfg.latentSeconds); local sum=cfg.releaseBatches[1]
for i=2,#cfg.releaseBatches do
 age(w,cfg.releaseInterval-cfg.diseaseStep)
 assert(c.releaseCount==i-1 and w.stats.totalReleased==sum)
 age(w,cfg.diseaseStep); sum=sum+cfg.releaseBatches[i]
 assert(c.state=='PRODUCTIVE' and c.releaseCount==i and w.stats.totalReleased==sum)
end
age(w,cfg.releaseInterval); assert(c.state=='EXHAUSTED' and c.exhaustionTimer==0)
age(w,cfg.exhaustedReleaseInterval); sum=sum+cfg.exhaustedReleaseCount
assert(c.state=='EXHAUSTED' and w.stats.totalReleased==sum)
age(w,cfg.exhaustedSeconds-cfg.exhaustedReleaseInterval)
assert(c.state=='DEAD' and not c.covered and c.exposure==0)
local released=w.stats.totalReleased; local deaths=eventCount(w,'cell_dead')
age(w,200); w:KillCell(c,'again')
assert(w.stats.totalReleased==released and eventCount(w,'cell_dead')==deaths)
checkConservation(w)
""",
'释放位于膜边缘且携带真实节点来源': r"""
local w=quietWorld(); local c=unitCell(w); w.cells={c}; w:_Infect(c,'player')
age(w,cfg.latentSeconds)
for _,v in ipairs(w.releasedViruses) do
 assert(v.state=='RELEASED' and v.sourceCellId==c.id and v.sourceRegionId==c.regionId)
 near(distance(c,v),c.radius+cfg.virusRadius+.04)
 assert(w.map:Contains(v.x,v.y,v.radius))
end
assert(w:Counts().controlled==w.stats.initialMass and w.stats.totalAbsorbed==0)
checkConservation(w)
""",
'Released独立真实感染不需玩家接触': r"""
local w=quietWorld(); local x,y=w.player.x,w.player.y
local source=unitCell(w,1,x+3,y); local target=unitCell(w,2,x+3.4,y)
w.cells={source,target}; w:_Infect(source,'player'); w:_Release(source,12)
-- 保留真实Release生成的id和来源，仅固定单元位置来隔离流场。
for _,v in ipairs(w.releasedViruses) do v.x,v.y=target.x,target.y end
progress(w,cfg.infectionSeconds)
assert(target.state=='LATENT' and target.infectionSource=='released' and not target.everPlayerContact)
assert(target.groupContribution==0 and target.releasedContribution>0)
assert(w.stats.independentInfections==1 and eventCount(w,'independent_infection')==1)
checkConservation(w)
""",
'真实自然分批Released传播与组织防御对照': r"""
local function run(defense)
 cfg.ecology.enabled=defense
 local w=quietWorld()
local source=unitCell(w,1,w.player.x+3,w.player.y)
local target=unitCell(w,2,source.x+1,source.y)
w.cells={source,target}; w:_Infect(source,'player')
-- 仅调整细胞夹具位置，不调整任何Released位置/状态，不替换流场、年龄或移动。
-- Released必须由潜伏结束自然出生，再自行移动并累积真实接触。
local done=false
for i=1,math.floor(150/cfg.movementStep) do
 w:Update(cfg.movementStep)
 if i%60==0 then checkConservation(w,true) end
 if target.state=='LATENT' then done=true; break end
end
checkConservation(w,true)
return w,target,done
end
-- Explicit control disables only the newly introduced tissue/trace rules; does
-- not represent default play. Same seed/input/real release and movement paths.
local base,target,done=run(false)
assert(done and target.infectionSource=='released' and not target.everPlayerContact)
assert(base.stats.independentInfections==1 and target.groupContribution==0)
assert(eventCount(base,'independent_infection')==1 and base.stats.totalReleased>cfg.releaseBatches[1])
local defended,protected,completed=run(true)
assert(not completed and defended.stats.independentInfections==0,'同种子近源组织防御应推迟传播')
assert(not protected.everPlayerContact and protected.groupContribution==0)
assert(defended.stats.totalReleased>cfg.releaseBatches[1] and protected.antiviralStrength>0)
""",
'同次历史玩家接触不冒充Released独立来源': r"""
local w=quietWorld(); local c=unitCell(w); w.cells={c}; progress(w,1)
assert(c.everPlayerContact and c.exposure>0)
place(w,w.player,w.player.x+3,w.player.y); w:_Release(c,20)
for _,v in ipairs(w.releasedViruses) do v.x,v.y=c.x,c.y end
progress(w,cfg.infectionSeconds)
assert(c.state=='LATENT' and c.infectionSource=='player' and w.stats.independentInfections==0)
assert(c.groupContribution>0 and c.releasedContribution>0,'来源必须保留实际两类贡献')
checkConservation(w)
""",
'感染真实来源和速度不因Released数组排序变化': r"""
local w=quietWorld(); local c=unitCell(w); w.cells={c}
place(w,w.player,w.player.x+3,w.player.y); w:_Release(c,10)
for i,v in ipairs(w.releasedViruses) do v.x,v.y=c.x+i*.025,c.y end
progress(w,1); local before=c.exposure
c.state,c.exposure,c._charge,c._groupCharge,c._releasedCharge='HEALTHY',0,0,0,0
local reversed={}; for i=#w.releasedViruses,1,-1 do reversed[#reversed+1]=w.releasedViruses[i] end
w.releasedViruses=reversed; progress(w,1); near(c.exposure,before)
assert(c.groupContribution==0 and not c.everPlayerContact)
checkConservation(w)
""",
'远端Released不自动追主群不自动加入质量': r"""
local w=quietWorld(); local source=unitCell(w,1,w.player.x+3,w.player.y)
w.cells={source}; w:_Infect(source,'player'); w:_Release(source,6)
local mass=w.player.mass; local x,y=w.player.x,w.player.y
step(w,8)
assert(w.player.mass==mass and w.stats.totalAbsorbed==0 and w:Counts().released==6)
for _,v in ipairs(w.releasedViruses) do
 assert(v.state=='DRIFTING' or v.state=='INFECTING' or v.state=='RELEASED')
 assert(distance(v,w.player)>w.player.radius+cfg.absorptionExtra,'远端游离被吸收')
end
checkConservation(w,true)
""",
'吸收是实体转移不能重复计出生': r"""
local w=quietWorld(); local c=unitCell(w); w.cells={c}; w:_Release(c,5)
for _,v in ipairs(w.releasedViruses) do v.x,v.y=w.player.x,w.player.y end
local n=w:Counts().virus; w:_MoveReleased(cfg.movementStep)
assert(w.player.mass==w.stats.initialMass+5 and #w.viruses==w.player.mass)
assert(w.stats.totalAbsorbed==5 and w:Counts().released==0 and w:Counts().virus==n)
assert(w.stats.totalReleased==5)
w:_MoveReleased(1); assert(w.stats.totalAbsorbed==5 and w.player.mass==w.stats.initialMass+5)
checkConservation(w)
""",
'游离清除与失活各记一次且失活不复活': r"""
local w=quietWorld(); local c=unitCell(w); w:_Release(c,3); w.cells={}
local a,b=w.releasedViruses[1],w.releasedViruses[2]
assert(w:KillReleased(a) and not w:KillReleased(a)); b.lifetime=cfg.movementStep
w:_MoveReleased(cfg.movementStep)
assert(a.state=='CLEARED' and b.state=='LOST' and w.stats.totalKilled==1 and w.stats.totalLost==1)
assert(not w:KillReleased(b))
w:_MoveReleased(cfg.movementStep); assert(w.stats.totalLost==1)
checkConservation(w)
""",
'死亡游离实体不是感染源': r"""
local w=quietWorld(); local c=unitCell(w); w.cells={c}; w:_Release(c,4)
for _,v in ipairs(w.releasedViruses) do v.x,v.y=c.x,c.y; w:KillReleased(v) end
place(w,w.player,w.player.x+3,w.player.y); progress(w,cfg.infectionSeconds)
assert(c.state=='HEALTHY' and c.exposure==0 and not c.covered and w.stats.independentInfections==0)
checkConservation(w)
""",
'分裂成本守恒冷却门控且粒子位置不瞬移': r"""
local w=quietWorld(); local positions={}
for _,v in ipairs(w.viruses) do positions[v.id]={x=v.x,y=v.y} end
local mass=w.player.mass; local cost=math.max(1,math.floor(mass*cfg.splitCostFraction))
w:SetAim(1,0); assert(w:Split())
local main,other=w.swarms[1],w.swarms[2]
assert(#w.swarms==2 and main.mass+other.mass==mass-cost and w.stats.splitCost==cost)
assert(other.mass==math.floor((mass-cost)*cfg.splitFraction))
assert(w.stats.totalReleased==0 and w.stats.totalKilled==0 and not w:Split())
for _,v in ipairs(w.viruses) do near(v.x,positions[v.id].x); near(v.y,positions[v.id].y) end
assert(other.launchX>0 and main.launchX<0 and main.isMainSwarm and not other.isMainSwarm)
checkConservation(w)
""",
'分裂弹射推力随分裂前病毒群质量增长': r"""
local function splitAtMass(mass)
 local w=quietWorld(); w.cells={}; w.viruses={}
 w.player.mass=mass; w.stats.initialMass=mass; w.stats.peakVirus=mass
 w:_AddParticles(w.player,mass); w:_UpdateParticles(); w:SetAim(1,0)
 assert(w:Split())
 return w,w:MainSwarm(),w.swarms[2]
end
local small,smallMain,smallChild=splitAtMass(cfg.initialMass)
local large,largeMain,largeChild=splitAtMass(cfg.initialMass*4)
near(smallChild.launchX,cfg.splitLaunchSpeed)
near(largeChild.launchX,smallChild.launchX*2)
near(largeMain.launchX,smallMain.launchX*2)
assert(largeChild.launchX>smallChild.launchX and -largeMain.launchX>-smallMain.launchX,
 '分裂前群质量增加必须同时加强分群弹射与主群反冲')
checkConservation(small); checkConservation(large)
""",
'分裂弹射遵守有限位移且最低质量冷却': r"""
local w=quietWorld(); w.cells={}; w:SetAim(1,0); assert(w:Split())
local a,b=w.swarms[1],w.swarms[2]; local x,y=b.x,b.y
w:Update(cfg.movementStep)
assert(b.x>x and distance(b,{x=x,y=y})<=(cfg.splitLaunchSpeed+cfg.baseSpeed+2)*cfg.movementStep)
assert(w.splitCooldown>0 and not w:Split())
w:DamageSwarm(b.id,b.mass); w.splitCooldown=0
w:DamageSwarm(a.id,math.max(0,a.mass-cfg.splitMinMass+1))
assert(not w:Split())
checkConservation(w)
""",
'Tab切换仅新控制群受输入且清旧输入': r"""
-- 旧输入隔离例禁自主巡游；自主接管/切离的真实行为由autonomy回归覆盖。
cfg.autonomy.enabled=false
local w=quietWorld(); w.cells={}; assert(w:Split()); local main=w:MainSwarm(); local other=w.swarms[2]
w:SetMovement(1,0); assert(w:SwitchControl())
assert(w.player==other and w.currentControlledSwarmId==other.id and main.isMainSwarm)
assert(not main.isPlayerControlled and other.isPlayerControlled and w._inputX==0 and w._inputY==0)
place(w,main,main.x,main.y); place(w,other,other.x+3,other.y)
local mx,my,ox=main.x,main.y,other.x; w:SetMovement(1,0); step(w,1)
assert(other.x>ox+.5 and distance(main,{x=mx,y=my})<.5)
assert(w:SwitchControl() and w.player==main and w._inputX==0)
checkConservation(w,true)
""",
'非受控群延续旧感染且真实接触开启新目标': r"""
local w=quietWorld(); assert(w:Split()); local main=w:MainSwarm(); local other=w.swarms[2]
place(w,other,other.x+3,other.y); local c=unitCell(w,1,other.x,other.y)
local fresh=w.cells[2]; w.cells={c}
assert(w:SwitchControl()); progress(w,1)
assert(c.state=='EXPOSED' and c.exposure>0 and other.exposedCells[c.id])
assert(w:SwitchControl()); local old=c.exposure; progress(w,1)
assert(c.exposure>old,'非受控群必须继续已开始的感染')
w.cells={fresh}; fresh=unitCell(w,1,other.x+.25,other.y)
progress(w,2); assert(fresh.state=='EXPOSED' and fresh.exposure>0 and fresh.covered)
assert(other.exposedCells[fresh.id] and fresh.groupContribution>0 and fresh.releasedContribution==0)
checkConservation(w)
""",
'近距离自动吸引接触合并与质量相加': r"""
local w=quietWorld(); w.cells={}; assert(w:Split())
local main,other=w.swarms[1],w.swarms[2]
place(w,main,main.x,main.y); place(w,other,main.x+1.05,main.y)
local total=main.mass+other.mass; local initial=distance(main,other)
w:Update(cfg.movementStep); assert(w.mergeReady and distance(main,other)<initial)
step(w,2)
assert(#w.swarms==1 and w:MainSwarm()==main and main.mass==total and w.currentControlledSwarmId==main.id)
assert(w.stats.totalMerges==1 and w.stats.totalSplits==1 and w.stats.totalReleased==0)
step(w,1); assert(w.stats.totalMerges==1)
checkConservation(w,true)
""",
'远距离不会合并或远程召回': r"""
local w=quietWorld(); w.cells={}; assert(w:Split())
local a,b=w.swarms[1],w.swarms[2]
place(w,a,a.x,a.y); place(w,b,a.x+3,a.y)
step(w,3)
assert(#w.swarms==2 and not w.mergeReady and w.stats.totalMerges==0)
assert(distance(a,b)>a.radius+b.radius+cfg.mergeExtra)
checkConservation(w,true)
""",
'主群清除分群升主和分群清除不杀主群': r"""
local w=quietWorld(); assert(w:Split()); local main,other=w.swarms[1],w.swarms[2]
local survivor=other.mass; w:SetMovement(1,0)
local removedMass=main.mass
assert(w:DamageSwarm(main.id,1000)==removedMass)
assert(#w.swarms==1 and w:MainSwarm()==other and w.player==other and other.isPlayerControlled)
assert(other.mass==survivor and w._inputX==0 and w._inputY==0)
checkConservation(w)
local q=quietWorld(); assert(q:Split()); local a,b=q.swarms[1],q.swarms[2]; local mass=a.mass
q:DamageSwarm(b.id,b.mass)
assert(#q.swarms==1 and q:MainSwarm()==a and a.mass==mass and eventCount(q,'split_lost')==1)
checkConservation(q)
""",
'全部群清零但节点Released尚活立即失败': r"""
local s=newSim('DEEP_LUNG',true); local w=s.world; local c=w.cells[1]
w:_Infect(c,'player'); w:_Release(c,6)
local ended=0; Bus.On(Bus.Events.SIM_ENDING,function(p) ended=ended+1 end)
for i=#w.swarms,1,-1 do local a=w.swarms[i]; w:DamageSwarm(a.id,a.mass) end
assert(w:Counts().infected>0 and w:Counts().released>0 and w:ControlledCount()==0)
s:Update(cfg.movementStep)
assert(s.ending=='extinct' and ended==1 and not s.irreversible)
local t=s.time; s:Update(10); s:FinishRun('victory')
assert(s.time==t and s.ending=='extinct' and ended==1)
checkConservation(w)
""",
'两群清除即失败而非等待潜伏复活': r"""
local s=newSim('UPPER_AIRWAY',true); assert(s:Split()); local w=s.world
w:_Infect(w.cells[1],'player')
for i=#w.swarms,1,-1 do local a=w.swarms[i]; w:DamageSwarm(a.id,a.mass) end
simStep(s,60)
assert(s.ending=='extinct' and w.stats.totalReleased==0 and w:Counts().groups==0)
""",
'调试局同一步达炎症阈值且清零胜利优先不可逆': r"""
local s=newSim('UPPER_AIRWAY',true); s.debugRun=true; local w=s.world; local ended=0
Bus.On(Bus.Events.SIM_ENDING,function(p) ended=ended+1; assert(p.outcome=='victory') end)
w.globalInflammation=cfg.irreversibleInflammation
w:DamageSwarm(w.player.id,w.player.mass)
s:Update(cfg.movementStep)
assert(s.ending=='victory' and s.irreversible and ended==1 and s.stage==6)
assert(s.task.target==100 and s.task.progress==100,'胜利任务目标必须同步为100')
assert(s.task.text=='不可逆感染达成','胜利任务不能遗留之前阶段任务文案')
assert(s.task.hint:find('胜利已锁定',1,true),'胜利任务必须明确不可逆锁定提示')
local t=s.time; w.globalInflammation=0; s:Update(20); s:FinishRun('extinct')
assert(s.ending=='victory' and s.irreversible and ended==1 and s.time==t)
""",
'调试局真实同固定步节点跨阈值加双免疫清群先胜': r"""
for _,reverse in ipairs({false,true}) do
 local s=newSim('DEEP_LUNG'); s.debugRun=true; local w=s.world
 local macro,tcell=w.immunes[1],w.immunes[2]
 w.immunes=reverse and {tcell,macro} or {macro,tcell}
 local c=unitCell(w); w.cells={c}; w:_Infect(c,'player')
 w:DamageSwarm(w.player.id,w.player.mass-cfg.immuneKillsPerAttack)
 for _,im in ipairs(w.immunes) do
  im.x,im.y,im.regionId=c.x,c.y,c.regionId
  im._oldX,im._oldY,im._patrolX,im._patrolY=im.x,im.y,im.x,im.y
 end
 -- Identification is real; stagger initial macrophage availability so both
 -- have completed warning/contact phases before the simultaneous-deadline assay.
 macro.state='cooldown'
 macro.cooldown=cfg.immuneWarningSeconds+cfg.immuneBehavior.recognitionSeconds-cfg.immuneBehavior.swarmWarningSeconds
 awaitState(w,macro,'attack'); assert(tcell.state=='attack' and tcell.recognized)
 macro.attackTimer,tcell.attackTimer=cfg.movementStep,cfg.movementStep
 assert(macro.targetType=='swarm' and tcell.targetType=='cell')
 local r=w.map.regions[c.regionId]
 local wanted=cfg.irreversibleInflammation-cfg.nodeAttackInflammation*.5
 w:AddInflammation(c.regionId,wanted-r.inflammation)
 assert(w.globalInflammation<cfg.irreversibleInflammation)
 s:ConsumeEvents(); simStep(s,cfg.movementStep)
 assert(w:ControlledCount()==0 and c.immuneHits==1)
 assert(s.ending=='victory' and s.irreversible,'真实免疫行动数组顺序不能把同一步胜利误判失败')
 checkConservation(w)
end
""",
'组织损伤阈值独立胜利而健康零不是旧死亡规则': r"""
local s=newSim('UPPER_AIRWAY',true); s.mouse.health=0; s:CheckOutcome(cfg.movementStep)
assert(s.ending==nil,'不能沿用旧health==0直接死亡/失败规则')
s.globalTissueDamage=cfg.irreversibleDamage; s:CheckOutcome(cfg.movementStep)
assert(s.victoryQualified and not s.ending);s.debugRun=true;s:CheckOutcome(0)
assert(s.ending=='victory' and s.irreversible)
""",
'呼吸低阈值必须连续并在恢复时重置': r"""
local s=newSim('UPPER_AIRWAY',true)
s.mouse.respiration=cfg.minRespiration
s:CheckOutcome(cfg.respirationFailureSeconds-1)
assert(not s.ending and s.respirationLowSeconds==cfg.respirationFailureSeconds-1)
s.mouse.respiration=cfg.minRespiration+.001; s:CheckOutcome(.5)
assert(s.respirationLowSeconds==0)
s.mouse.respiration=cfg.minRespiration; s:CheckOutcome(cfg.respirationFailureSeconds-cfg.movementStep)
assert(not s.ending)
s:CheckOutcome(cfg.movementStep)
assert(s.victoryQualified and not s.ending);s.debugRun=true;s:CheckOutcome(0)
assert(s.ending=='victory' and s.irreversible)
""",
'六阶段不因一次感染或EXPOSED立即发卡': r"""
local s=newSim('UPPER_AIRWAY',true);local w=s.world
local a,b=w.cells[1],w.cells[2]
a.state,a.exposure='EXPOSED',.99;b.state,b.exposure='EXPOSED',.5
s:UpdateTasks();assert(s.stage==1 and s.task.progress==0 and s.task.target==1)
w:_Infect(a,'player');s:ConsumeEvents();s:UpdateTasks();assert(s.stage==1 and s.task.progress==0)
w:_Infect(b,'player');s:ConsumeEvents();s:UpdateTasks();assert(s.stage==1 and not s.cards.pending)

""",
'深肺初始节点不计新感染据点且不跳过阶段': r"""
local s=newSim('DEEP_LUNG',true);local w=s.world
assert(s.stage==1 and s.evolution.completed==0 and s.task.progress==0)
local c;for _,x in ipairs(w.cells) do if x.state=='HEALTHY' then c=x;break end end
w:_Infect(c,'player');s:ConsumeEvents();s:UpdateTasks();assert(s.stage==1 and s.task.progress==0)
w:Emit('independent_infection',{cellId=c.id});s:ConsumeEvents();s:UpdateTasks()
assert(s.triggeredCardEvents.independent_infection and s.stage==1 and not s.cards.pending)

""",
'支气管同深度与区域历史不直接推进阶段': r"""
local s=newSim('TRACHEA',true);local w=s.world;assert(s:Split())
local left,right=w.map.regions[3],w.map.regions[4];assert(left.depth==right.depth)
w:Emit('region_enter',{swarmId=w.swarms[2].id,regionId=left.id});s:ConsumeEvents();s:UpdateTasks()
assert(s.stage==1 and not s.cards.pending and #w.swarms==2)

""",
'分群自动接管不伪造阶段任务完成': r"""
local s=newSim('TRACHEA',true);local w=s.world;assert(s:Split())
local main,other=w:MainSwarm(),w.swarms[2];local p=w.map.startPoints.DEEP_LUNG
place(w,other,p.x,p.y);w:DamageSwarm(main.id,main.mass);s:UpdateTasks()
assert(w:MainSwarm()==other and s.stage==1 and not s.cards.pending)

""",
'观察暂停不补跑并清移动且多暂停原因独立': r"""
local s=newSim('UPPER_AIRWAY',true); local w=s.world
s.touchMove={x=1,y=1,active=true}; w:SetMovement(1,0); s:Update(cfg.movementStep/2)
s:SetPaused('observation',true)
assert(s.paused and s.tickAccum==0 and not s.touchMove.active and w._inputX==0 and w._inputY==0)
local t,x,y=w.time,w.player.x,w.player.y; local latency=w.cells[1].latencyTimer
s:Update(20); assert(w.time==t and w.player.x==x and w.player.y==y and w.cells[1].latencyTimer==latency)
assert(not s:Split() and not s:SwitchControl())
s:SetPaused('menu',true); s:SetPaused('observation',false); assert(s.paused)
s:SetPaused('menu',false); assert(not s.paused); s:Update(cfg.movementStep)
near(w.time-t,cfg.movementStep)
""",
'固定步30_60_144帧率结果一致': r"""
-- Compare fixed-step rules independently of the wall-clock catch-up budget.
-- The following real-immunity assay uses the same isolation; production keeps 8ms.
Config.Performance.simulationBudgetMs=0
noImmune(); local sims={newSim('UPPER_AIRWAY'),newSim('UPPER_AIRWAY'),newSim('UPPER_AIRWAY')}
for i,fps in ipairs({30,60,144}) do
 local s=sims[i]; s.world:SetMovement(.6,.8); simStep(s,12,fps)
end
local a=sims[1]
for i=2,3 do local b=sims[i]
 near(a.time,b.time); assert(a.tickCount==b.tickCount)
 near(a.world.player.x,b.world.player.x); near(a.world.player.y,b.world.player.y)
 assert(a:TotalVirus()==b:TotalVirus() and a.stats.totalInfected==b.stats.totalInfected)
 for j,c in ipairs(a.world.cells) do
  local d=b.world.cells[j]; assert(c.state==d.state); near(c.exposure,d.exposure); near(c.latencyTimer,d.latencyTimer)
 end
 checkConservation(b.world,true)
end
""",
'真实免疫与分批病程固定步跨帧率一致': r"""
-- Wall-clock budget deliberately drops catch-up steps under CPU contention.
-- Disable that scheduler policy only in this determinism assay; default-budget
-- production acceptance and native FPS are separate evidence.
Config.Performance.simulationBudgetMs=0
local sims={newSim('DEEP_LUNG'),newSim('DEEP_LUNG'),newSim('DEEP_LUNG')}
for i,fps in ipairs({30,60,144}) do simStep(sims[i],40,fps) end
local a=sims[1]
assert(a.stats.totalReleased>0,'帧率测试必须真的跨越潜伏并释放，不能只比较未感染空跑')
for i=2,3 do
 local b=sims[i]; near(a.time,b.time); assert(a.tickCount==b.tickCount and a.ending==b.ending)
 near(a.world.player.x,b.world.player.x); near(a.world.player.y,b.world.player.y)
 assert(a.stats.totalReleased==b.stats.totalReleased and a.stats.totalKilled==b.stats.totalKilled)
 assert(a.stats.totalAbsorbed==b.stats.totalAbsorbed and a:TotalVirus()==b:TotalVirus())
 near(a.globalInflammation,b.globalInflammation); near(a.globalTissueDamage,b.globalTissueDamage)
 for j,c in ipairs(a.world.cells) do
  local d=b.world.cells[j]; assert(c.state==d.state and c.releaseCount==d.releaseCount)
  near(c.exposure,d.exposure); near(c.latencyTimer,d.latencyTimer)
 end
 for j,im in ipairs(a.world.immunes) do
  local other=b.world.immunes[j]; assert(im.state==other.state and im.targetId==other.targetId)
  near(im.x,other.x); near(im.y,other.y); near(im.warningTimer,other.warningTimer)
 end
 checkConservation(b.world,true)
end
""",
'重开init清全部输入计时卡片及免疫状态': r"""
local s=newSim('DEEP_LUNG',true); s.world:SetAim(1,-1); s.world:SetMovement(1,0); s:Split()
s.touchMove={x=1,y=0,active=true}; s.timeScale=4; s:SetPaused('observation',true)
s.obtainedCards={{id='invalid'}}; s.triggeredCardEvents.any=true; s.nodeAttacks[1]={escaped=true}
s:init()
assert(not s.started and s.paused and s.pauseReasons.selection and s.time==0 and s.tickAccum==0 and s.timeScale==1)
assert(s.stage==1 and not s.irreversible and not s.ending and s.respirationLowSeconds==0)
assert(s.touchMove.x==0 and s.touchMove.y==0 and not s.touchMove.active)
assert(s.world._inputX==0 and s.world._inputY==0 and s.world._aimX==0 and s.world._aimY==1)
assert(s.world.splitCooldown==0 and s.world.diseaseAccum==0 and #s.world.effects==0)
assert(#s.obtainedCards==0 and next(s.triggeredCardEvents)==nil and next(s.nodeAttacks)==nil)
assert(s.world.stats.totalKilled==0 and s.world.stats.totalReleased==0 and #s.world.releasedViruses==0)
checkConservation(s.world)
""",
'StartRun重开也清旧卡片与速度输入': r"""
local s=newSim('UPPER_AIRWAY',true); s.timeScale=4; s.obtainedCards={{id='invalid'}}
s.world:SetAim(1,0); s.world:SetMovement(1,0); s.touchMove={x=1,y=0,active=true}
s:SetPaused('observation',true); assert(s:StartRun('TRACHEA'))
assert(s.timeScale==1,'StartRun重开保留了上一局timeScale')
assert(#s.obtainedCards==0,'StartRun重开保留了上一局卡片')
assert(s.time==0 and s.tickAccum==0 and not s.paused and not s.touchMove.active)
assert(s.world._inputX==0 and s.world._inputY==0 and s.world._aimX==0 and s.world._aimY==1)
""",
'正式18张卡合法候选与独立测试获取': r"""
local s=newSim();local w=s.world
assert(#Config.Cards.definitions==18 and #s:GetEligibleCards(1)==17)
assert(not s:AcquireTestCard('swarm_capacity_6'))
assert(s:AcquireTestCard('swarm_capacity_4') and w.maxPlayerSwarms==4 and w.immuneAlertLevel==1)
assert(s.debugRun and s.obtainedCards.swarm_capacity_4 and s.cardNotice and s.paused)
s:ContinueAfterCard();assert(not s:AcquireTestCard('swarm_capacity_4'))

""",
'免疫所有开局出生安全且不重叠': r"""
for _,def in ipairs(Config.StartRegions) do
 local w=World.New(def.type)
 for i,im in ipairs(w.immunes) do
  assert(im.state=='patrol' and im.targetId==nil and w.map:Contains(im.x,im.y,im.radius))
  for _,s in ipairs(w.swarms) do
   assert(distance(im,s)>=cfg.immuneSafeDistance+im.radius+s.radius-1e-7,'免疫贴脸出生')
  end
  for j=i+1,#w.immunes do local other=w.immunes[j]
   assert(distance(im,other)>=im.radius+other.radius+.15-1e-7,'免疫出生重叠')
  end
 end
end
""",
'免疫警告和蓄力未完成前不攻击接触才少量削弱': r"""
local w,im=immuneFixture('macrophage'); local mass=w.player.mass
Immune.Update(w,cfg.movementStep); assert(im.state=='locked' and w.player.mass==mass)
Immune.Update(w,cfg.movementStep); assert(im.state=='warning')
advanceImmune(w,im.warningTime-cfg.movementStep)
assert(im.state=='warning' and w.player.mass==mass)
advanceImmune(w,cfg.movementStep); assert(im.state=='chase' and w.player.mass==mass)
Immune.Update(w,cfg.movementStep); assert(im.state=='attack' and w.player.mass==mass)
advanceImmune(w,im.attackWindup-cfg.movementStep); assert(w.player.mass==mass)
Immune.Update(w,cfg.movementStep)
assert(w.player.mass==mass-cfg.immuneKillsPerAttack and im.state=='cooldown')
local killed=w.stats.totalKilled; advanceImmune(w,im.cooldown-cfg.movementStep)
assert(w.stats.totalKilled==killed,'攻击冷却期间重复扣质量')
checkConservation(w)
""",
'免疫蓄力中离开接触则取消无远程扣量': r"""
local w,im=immuneFixture('macrophage'); awaitState(w,im,'attack')
local mass=w.player.mass; local x,y=im.x,im.y
place(w,w.player,x+1.2,y)
Immune.Update(w,cfg.movementStep)
assert(im.state=='chase' and im.attackTimer==0 and w.player.mass==mass)
assert(eventCount(w,'immune_attack_cancel')==1)
checkConservation(w)
""",
'免疫远距离不攻击隐藏或失效目标': r"""
local w,im=immuneFixture('macrophage'); awaitState(w,im,'attack'); local mass=w.player.mass
w.player.isHidden=true; advanceImmune(w,5)
assert(w.player.mass==mass and im.targetId==nil and im.state=='patrol')
w.player.isHidden=false; local far=w.map.startPoints.TRACHEA
place(w,w.player,far.x,far.y)
advanceImmune(w,1); assert(w.player.mass==mass)
checkConservation(w)
""",
'免疫高dt不能跳过预警蓄力瞬杀': r"""
local w,im=immuneFixture('macrophage'); local mass=w.player.mass
Immune.Update(w,60); assert(im.state=='locked' and w.player.mass==mass)
Immune.Update(w,60); assert(im.state=='warning' and w.player.mass==mass)
Immune.Update(w,60); assert(im.state=='chase' and w.player.mass==mass)
Immune.Update(w,60); assert(im.state=='attack' and w.player.mass==mass)
""",
'真实T节点攻击加炎症和损伤多击死亡': r"""
local w=World.New('DEEP_LUNG'); local im=assert(w.immunes[2]); w.immunes={im}
local c=unitCell(w); w.cells={c}; w:_Infect(c,'player')
place(w,w.player,w.player.x+3,w.player.y)
im.x,im.y,im.regionId=c.x,c.y,c.regionId
im._oldX,im._oldY,im._patrolX,im._patrolY=im.x,im.y,im.x,im.y
local r=w.map.regions[c.regionId]; local inflammation,damage=r.inflammation,r.damage
awaitState(w,im,'attack'); assert(im.targetType=='cell' and im.targetId==c.id)
assert(eventCount(w,'node_attack_start')==1 and c.immuneHits==0)
advanceImmune(w,im.attackWindup)
assert(c.immuneHits==1 and c.state=='LATENT')
near(r.inflammation-inflammation,cfg.nodeAttackInflammation); near(r.damage-damage,cfg.nodeAttackDamage)
assert(eventCount(w,'node_attack')==1)
for _=2,cfg.immuneNodeHits do awaitState(w,im,'attack'); advanceImmune(w,im.attackWindup) end
assert(c.state=='DEAD' and c.immuneHits==cfg.immuneNodeHits and eventCount(w,'cell_dead')==1)
local total=w.stats.totalReleased; advanceImmune(w,20); age(w,100)
assert(w.stats.totalReleased==total)
checkConservation(w)
""",
'节点警告与命中不再代替局部炎症目标': r'''
local s=newSim('DEEP_LUNG');local w=s.world;local im=w.immunes[2];w.immunes={im}
local c=unitCell(w);w.cells={c};w:_Infect(c,'player');s.evolution:Enter(5,w.time)
im.x,im.y,im.regionId=c.x,c.y,c.regionId
im._oldX,im._oldY,im._patrolX,im._patrolY=im.x,im.y,im.x,im.y
awaitState(w,im,'attack');s:ConsumeEvents()
assert(not s.evolution:Status(w).complete)
place(w,w.player,c.x+4,c.y);s:ConsumeEvents()
assert(not s.evolution:Status(w).complete)
advanceImmune(w,im.attackWindup);s:ConsumeEvents()
assert(s.triggeredCardEvents.node_attack and not s.evolution:Status(w).complete)
''',
'节点受击后撤离保留真实攻击但不直接完成阶段': r'''
local s=newSim('DEEP_LUNG');local w=s.world;local im=w.immunes[2];w.immunes={im}
local c=unitCell(w);w.cells={c};w:_Infect(c,'player');s.evolution:Enter(5,w.time)
im.x,im.y,im.regionId=c.x,c.y,c.regionId
im._oldX,im._oldY,im._patrolX,im._patrolY=im.x,im.y,im.x,im.y
awaitState(w,im,'attack');advanceImmune(w,im.attackWindup);s:ConsumeEvents()
assert(not s.evolution:Status(w).complete)
place(w,w.player,c.x+4,c.y);s:ConsumeEvents()
assert(s.triggeredCardEvents.node_attack and not s.evolution:Status(w).complete)
''',
'真实免疫Released清除单实体并尊重冷却': r"""
local w,im=immuneFixture('macrophage')
local c=unitCell(w); w:_Release(c,3); w.cells={}; cfg.immuneClearChance=1
-- Particle clearing is isolated from the higher-priority visible swarm.
place(w,w.player,13,3.1)
for _,v in ipairs(w.releasedViruses) do v.x,v.y=im.x,im.y end
awaitState(w,im,'attack'); assert(im.targetType=='virus')
advanceImmune(w,im.attackWindup)
assert(w.stats.totalKilled==1 and w:Counts().released==2 and im.state=='cooldown' and im.targetId~=nil)
assert(im.warningTimer==0 and eventCount(w,'immune_clear_chain')==1)
-- 连续清理切换了真实目标，但不能免除吞噬间隔或每帧重投清除概率。
advanceImmune(w,im.cooldown-cfg.movementStep)
assert(w.stats.totalKilled==1 and im.state=='cooldown')
checkConservation(w)
""",
'免疫招募固定间隔上限且新出生远离两个群': r"""
local w=World.New('DEEP_LUNG'); assert(w:Split()); local other=w.swarms[2]
place(w,other,other.x+3,other.y); w:_Infect(w.cells[1],'player')
local n=#w.immunes
Immune.Recruit(w,cfg.immuneRecruitInterval-cfg.diseaseStep); assert(#w.immunes==n)
Immune.Recruit(w,cfg.diseaseStep); assert(#w.immunes==n+1)
local im=w.immunes[#w.immunes]
for _,s in ipairs(w.swarms) do assert(distance(im,s)>=cfg.immuneSafeDistance+im.radius+s.radius-1e-7) end
Immune.Recruit(w,cfg.immuneRecruitInterval*10); assert(#w.immunes==n+2,'一次调用最多招募一只')
for _=1,20 do Immune.Recruit(w,cfg.immuneRecruitInterval) end
assert(#w.immunes<=cfg.immuneMax)
checkConservation(w)
""",
}

STRESS = r"""
local w=World.New('DEEP_LUNG')
local frames=math.floor(STRESS_SECONDS/cfg.movementStep+.5)
local snapshots=0
for i=1,frames do
 if i%600==1 then
  local angle=i/500; w:SetMovement(math.cos(angle),math.sin(angle))
  if #w.swarms==1 then w:Split() else w:SwitchControl() end
 end
 w:Update(cfg.movementStep)
 if i%60==0 then
  checkConservation(w,true)
  assert(#w.immunes<=cfg.immuneMax and finite(w.globalInflammation) and finite(w.globalTissueDamage))
  for _,c in ipairs(w.cells) do
   assert(finite(c.exposure) and c.exposure>=0 and c.exposure<=1)
   assert(c.releaseCount<=#cfg.releaseBatches)
  end
  snapshots=snapshots+1
 end
 -- 表现层会消费事件；压测不通过无限事件积压人为制造性能问题。
 w.events={}
end
local c=w:Counts()
print(string.format('[STRESS] %.0f秒 %d个守恒快照 群=%d 游离=%d 节点=%d 炎症=%.2f 损伤=%.2f',
 w.time,snapshots,c.controlled,c.released,c.infected,w.globalInflammation,w.globalTissueDamage))
"""

NOT_COVERED = (
    '实际引擎键盘/触屏/UI布局、镜头和素材渲染（需引擎validate-test）',
    '有操作完整15～20分钟胜败路线、局长与数值平衡',
    '所有随机种子及全部连续空间可达性（当前3种子/栅格抽样）；随机地图与特殊细胞为暂缓项',
    '六阶段与18张正式卡详见evolution_regression.py；完整自然六轮窗口路线仍待验收',
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', action='append', default=[], help='仅运行名称含此子串的例，可重复')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--no-stress', action='store_true')
    parser.add_argument('--stress-seconds', type=float, default=180.0)
    parser.add_argument('--verbose', action='store_true', help='同时输出Core日志')
    args = parser.parse_args()
    if args.stress_seconds <= 0:
        parser.error('--stress-seconds 必须大于0')
    tests = dict(TESTS)
    if not args.no_stress:
        tests['多分钟真实免疫守恒与性能稳定性'] = STRESS
    if args.only:
        tests = {name: code for name, code in tests.items() if any(part in name for part in args.only)}
    if args.list:
        for name in tests:
            print(name)
        return 0
    if not tests:
        parser.error('未选中任何测试')
    setup_path = str(ROOT / 'scripts' / '?.lua')
    failed = []
    started = time.perf_counter()
    for name, code in tests.items():
        logs = []
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().test_log = lambda *items: logs.append(' '.join(map(str, items)))
        lua.globals().TEST_PACKAGE_PATH = setup_path
        lua.globals().STRESS_SECONDS = args.stress_seconds
        case_start = time.perf_counter()
        try:
            lua.execute("package.path=TEST_PACKAGE_PATH..';'..package.path; print=test_log")
            lua.execute(SETUP)
            lua.execute(code)
            print(f'PASS {name} ({time.perf_counter()-case_start:.2f}s)')
            if args.verbose or code == STRESS:
                for line in logs:
                    if args.verbose or line.startswith('[STRESS]'):
                        print(' ', line)
        except Exception as exc:
            failed.append(name)
            print(f'FAIL {name} ({time.perf_counter()-case_start:.2f}s)\n{exc}')
            for line in logs[-12:]:
                print('  LOG', line)
    print(f'{len(tests)-len(failed)}/{len(tests)} 通过，{len(failed)} 失败，耗时 {time.perf_counter()-started:.2f}s')
    for item in NOT_COVERED:
        print('未覆盖：', item)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
