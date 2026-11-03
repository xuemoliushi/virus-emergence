"""真实细胞接触与完整更新回归；只增加测试，不修改 production。

运行：PYTHONDONTWRITEBYTECODE=1 python3 /workspace/tests/cell_runtime_regression.py

证据口径：
* 固定方向 / center / near-center / hysteresis 是明确的固定夹具：真实 Release
  出生，实例级 _MoveReleased 包装先执行原函数，再仅将指定源放回指定位置。
  因此感染阶段有效位移为零；年龄、免疫、感染公式和完整 Update 均照常运行。
* 自然玩家场景只在初始化时设置一次合法玩家起点，之后仅 SetMovement。
  自然 Released 场景使用真实地图相邻细胞和 _Release，之后不传送任何来源。
  所有场景保留真实免疫初始化、更新和招募，绝不调用 quietWorld / noImmune。
* CellSurface 本体直接加载真实 JSON data/meta，未 mock GetPlacement 几何。
  draw 是真实 CellDiagnostics.Draw 的坐标变换记录，不是浏览器 / GPU 像素或
  人工视觉验收；颜色、旧业务指纹及真实浏览器截图由其他回归负责。
  几何断言仅覆盖坐标变换、180组/1440子档量化误差、有限值和缓存边界，不证明真实膜轮廓
  的相邻point/normal连续性或平滑视觉效果；该项需要独立资源/像素验收。

validation 中的 JSONL 每帧保留 CellDiagnosticsSink 的一个真实代表来源行，
原字段不改名、不补造。draw / geometry 是单独命名的诊断与测试几何证据。
本测试直接调用Diagnostics.Draw进行变换取样；即使其drawn字段为true，也只表示
该诊断函数获得pose，不能证明实际DrawParticle成功，更不证明GPU像素已画出。
每行drawEvidence明确标注为transform-only，正式画出与颜色由独立引擎回归验收。
exposure 每 30 个固定步结算，未结算帧 deltaExposure=0 正常；同时检查 pendingCharge。
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, '/home/Maker/.local/swarm-test')
from lua_test_runtime import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]

# 仅宿主资源接口替身；真实 Core / CellSurface / VisualUtils 均直接 require。
SETUP = r'''
Config=require('Core.Config')
World=require('Core.SwarmWorld')
Sim=require('Core.SimState')
Contacts=require('Core.CellContacts')
Diagnostics=require('Core.CellDiagnostics')
cfg=Config.Gameplay
-- Preserve the authored contact/Released trajectory fixtures, independently
-- from the new production-map integration checks.
cfg.mapGenerationVersion=1;cfg.width=26;cfg.height=32;cfg.cellCount=72
package.loaded['urhox-libs/UI/Core/ImageCache']={}
Surface=require('Game.Views.CellSurface')
surface=Surface.New({data=SURFACE_DATA,meta=SURFACE_META})
assert(surface.data and surface.meta and not next(surface.failures),'必须加载真实膜数据')
assert(surface.data.angle_bins==180,'当前真实资源保留180组')
local subdivisions=assert(surface.data.placement_subdivisions)
local sampleCount=surface.data.angle_bins*subdivisions
assert(subdivisions==8 and sampleCount==1440 and #surface.data.fine_placements==sampleCount,
 '必须加载最终真实1440档膜边界细分')
local poseLimit=sampleCount*2
assert(Contacts.Settings.epsilon==.02)
assert(Contacts.Settings.deadBand==math.rad(12))
assert(Contacts.Settings.candidateFrames==3)
assert(Contacts.Settings.maxTurn>0 and Contacts.Settings.maxTurn<=math.rad(3))

local TAU=math.pi*2
function near(a,b,e) assert(math.abs(a-b)<=(e or 1e-8),tostring(a)..' ~= '..tostring(b)) end
function delta(a,b) return (a-b+math.pi)%TAU-math.pi end
function finite(n) return type(n)=='number' and n==n and math.abs(n)<math.huge end
function allFinite(value,seen)
 if type(value)=='number' then assert(finite(value),'出现非有限值')
 elseif type(value)=='table' then
  seen=seen or {}; if seen[value] then return end; seen[value]=true
  for _,v in pairs(value) do allFinite(v,seen) end
 end
end
function distance(a,b) return math.sqrt((a.x-b.x)^2+(a.y-b.y)^2) end
function eventCount(w,name,cellId)
 local n=0
 for _,e in ipairs(w.events) do
  if e.name==name and (not cellId or e.payload.cellId==cellId) then n=n+1 end
 end
 return n
end
function contact(c,kind,id)
 for _,r in ipairs(c.contactVisuals) do
  if (not kind or r.sourceType==kind) and (not id or r.sourceId==id) then return r end
 end
end
function checkConservation(w)
 local n=w:Counts(); local st=w.stats
 assert(st.initialMass+st.totalReleased-st.totalKilled-st.totalLost-st.splitCost==n.virus)
 assert(#w.viruses==n.controlled)
 assert(n.healthy+n.exposed+n.latent+n.productive+n.exhausted+n.dead==#w.cells)
end
function freshSim()
 local s=Sim.New(); assert(s:StartRun('UPPER_AIRWAY'))
 assert(s:CanAct() and #s.world.immunes>0)
 return s,s.world
end
function placePlayerOnce(w,x,y)
 local p=w.player
 assert(w.map:Contains(x,y,p.radius),'玩家初始化必须位于真实合法地图')
 p.x,p.y,p.vx,p.vy=x,y,0,0
 p.currentRegionId=w.map:RegionAt(x,y)
 w:_UpdateParticles()
end

local frozen={}
local immutableConfig={}
lastDiagnostic=nil
lastDraw=nil
-- 每帧仅取按真实key排序的第一个代表来源，保留该完整真实行，不合成方向或感染增量。
function CellDiagnosticsSink(row)
 if not lastDiagnostic or lastDiagnostic.frame~=row.frame then
  lastDiagnostic=row
  emit_diagnostics(row)
 end
end
function CellDrawDiagnosticsSink(row) lastDraw=row; emit_draw(row) end
function startTrace(w,c,name,evidence)
 begin_trace(name,evidence)
 lastDiagnostic,lastDraw=nil,nil
 frozen={}
 for _,cell in ipairs(w.cells) do frozen[cell.id]={cell.x,cell.y,cell.rotation} end
 immutableConfig={immuneMax=cfg.immuneMax,infectionSeconds=cfg.infectionSeconds,
  infectionReach=cfg.infectionReach,releasedInfectionPower=cfg.releasedInfectionPower,
  exposureDecay=cfg.exposureDecay,counts={}}
 for i,def in ipairs(Config.StartRegions) do immutableConfig.counts[i]=def.immuneCount end
 assert(#w.immunes>0 and cfg.immuneMax>0,'测试不得禁用免疫')
 Diagnostics.Configure(w,{cellId=c.id,frames=12000,sink=CellDiagnosticsSink,drawSink=CellDrawDiagnosticsSink})
end
function observe(w,c)
 for k,v in pairs(immutableConfig) do if k~='counts' then assert(cfg[k]==v,'规则被测试修改') end end
 for i,n in ipairs(immutableConfig.counts) do assert(Config.StartRegions[i].immuneCount==n) end
 assert(#w.immunes>0,'自然/固定夹具都保留免疫')
 for _,cell in ipairs(w.cells) do
  local old=frozen[cell.id]
  assert(cell.x==old[1] and cell.y==old[2] and cell.rotation==old[3],'每帧细胞坐标/旋转不得改动')
  allFinite(cell)
 end
 for _,p in ipairs(w.swarms) do allFinite(p) end
 for _,v in ipairs(w.releasedViruses) do allFinite(v) end
 for _,im in ipairs(w.immunes) do allFinite(im) end
 allFinite(lastDiagnostic)
 assert(lastDiagnostic and lastDiagnostic.cellId==c.id)
 assert(lastDiagnostic.exposure==c.exposure and lastDiagnostic.pendingCharge==c._charge)
 assert(lastDiagnostic.progressField=='exposure' and lastDiagnostic.stateAfterUpdate==c.state)
 near(lastDiagnostic.time,w.time)
 local r=c.contactVisualAnchor
 local pose=nil
 local worldAngle=nil
 local localAngle=nil
 if r then
  -- 与真实 CellView.contactAngle 相同：旧方向保留在cell-local，随后仍随细胞旋转。
  worldAngle=math.atan(r.normalY,r.normalX)+c.rotation-r.visualCellRotation
  localAngle=(worldAngle-c.rotation)%TAU
  pose=assert(surface:GetPlacement(c,{angle=worldAngle}))
  local subIndex=1+math.floor(localAngle/TAU*sampleCount+.5)%sampleCount
  assert(pose.subBin==subIndex and pose.bin==1+(subIndex-1)//subdivisions)
  near(delta((pose.subBin-1)*TAU/sampleCount,localAngle),0,TAU/sampleCount*.5+1e-9)
  local p=surface.data.fine_placements[pose.subBin]
  near(pose.x,p[1]); near(pose.y,p[2]); near(pose.normalX,p[3]); near(pose.normalY,p[4])
  near(pose.normalX^2+pose.normalY^2,1,2e-8)
  allFinite(pose)
 end
 -- 代表性米制世界→屏幕仿射，细胞源像素→屏幕缩放；不是GPU绘制截图。
 local ppm=48
 local x,y=120+c.x*ppm,80+c.y*ppm
 local scale=2*c.radius*ppm/760
 Diagnostics.Draw(w,c,x,y,scale,pose)
 allFinite(lastDraw)
 assert(lastDraw and lastDraw.frame==lastDiagnostic.frame)
 if pose then
  local co,si=math.cos(c.rotation),math.sin(c.rotation)
  near(lastDraw.drawPosition[1],x+scale*(co*pose.spriteX-si*pose.spriteY))
  near(lastDraw.drawPosition[2],y+scale*(si*pose.spriteX+co*pose.spriteY))
  near(lastDraw.drawContactPosition[1],x+scale*(co*pose.x-si*pose.y))
  near(lastDraw.drawContactPosition[2],y+scale*(si*pose.x+co*pose.y))
  near(lastDraw.drawAngle,pose.rotation+c.rotation)
 end
 emit_geometry({worldAngle=worldAngle,cellLocalAngle=localAngle,pose=pose,
  worldToScreen={ppm=ppm,offsetX=120,offsetY=80},sourcePixelsToScreen=scale,
  surfaceStats=surface:GetStats()})
 local stats=surface:GetStats()
 assert(stats.poseCount<=poseLimit and stats.resources<=stats.maxResources)
 checkConservation(w)
 return pose
end
function tick(w,c,s)
 local oldExposure,oldTime=c.exposure,w.time
 if s then s:Update(cfg.movementStep); assert(not s.ending,'测试自然模拟不能被冻结局截断')
 else w:Update(cfg.movementStep) end
 near(w.time,oldTime+cfg.movementStep)
 if s then near(s.time,w.time); assert(s.tickCount==lastDiagnostic.frame) end
 near(lastDiagnostic.deltaExposure,c.exposure-oldExposure)
 return observe(w,c)
end
function fixedReleased(name)
 local w=World.New('UPPER_AIRWAY'); local c=w.cells[55]
 assert(c.state=='HEALTHY' and c.exposure==0)
 assert(distance(w.player,c)>20,'固定Released夹具避免主群吸收')
 w:_Release(c,1); local v=w.releasedViruses[1]
 local home={x=v.x,y=v.y}
 local original=w._MoveReleased
 -- 仅本实例夹具hook；先运行真实移动（含状态、年龄、吸收），再取消源位移。
 -- 不改 infection 调用，不更改进度/state/参数，也不改类方法或生产文件。
 w._MoveReleased=function(self,dt)
  original(self,dt)
  assert(v.state~='CLEARED' and v.state~='LOST' and v.state~='ABSORBED')
  v.x,v.y=home.x,home.y
 end
 local function setPoint(dx,dy)
  home.x,home.y=c.x+dx,c.y+dy
  assert(w.map:Contains(home.x,home.y,v.radius))
  v.x,v.y=home.x,home.y
 end
 startTrace(w,c,name,'固定Released夹具：每完整模拟步取消指定源位移，真实年龄/免疫/感染照常')
 return w,c,v,setPoint
end
function assertAccepted(c,v,oldSum)
 local combined=c.exposure+c._charge
 assert(combined>oldSum,'用真实累计charge检查逐步增长，不要求exposure每帧增长')
 assert(c.covered and not c.everPlayerContact and c._groupCharge==0)
 assert(lastDiagnostic.acceptedContact and lastDiagnostic.acceptedPower>0)
 assert(lastDiagnostic.sourceType=='RELEASED_VIRUS' and lastDiagnostic.sourceId==v.id)
 near(lastDiagnostic.sourcePosition[1],v.x); near(lastDiagnostic.sourcePosition[2],v.y)
 if lastDiagnostic.frame%30~=0 then assert(lastDiagnostic.deltaExposure==0) end
 return combined
end
function steerTo(w,x,y)
 local p=w.player
 local fx,fy=w.map:FlowAt(p.x,p.y,w.time+cfg.movementStep)
 local speed=math.max(cfg.minSpeed,cfg.baseSpeed/math.sqrt(math.max(1,p.mass/30)))
 -- 输入反馈维持位置；不替换移动，不直接修改速度/来源坐标，流场仍在_Update内执行。
 w:SetMovement(((x-p.x)*5-fx*cfg.playerFlowInfluence)/speed,
  ((y-p.y)*5-fy*cfg.playerFlowInfluence)/speed)
end
'''

TESTS = {
    '固定Released上下左右各120完整帧': r'''
local directions={{'up',0,-.3},{'down',0,.3},{'left',-.3,0},{'right',.3,0}}
for _,d in ipairs(directions) do
 local w,c,v,setPoint=fixedReleased('fixed_released_'..d[1])
 setPoint(d[2],d[3]); local sum=0; local record,bin
 for frame=1,120 do
  setPoint(d[2],d[3])
  local pose=tick(w,c)
  local r=assert(contact(c,'RELEASED_VIRUS',v.id))
  if frame==1 then record,bin=r,pose.subBin else assert(r==record and pose.subBin==bin) end
  near(r.normalX,d[2]/.3); near(r.normalY,d[3]/.3)
  near(r.rawNormalX,d[2]/.3); near(r.rawNormalY,d[3]/.3)
  near(r.worldContactX,c.x+r.normalX*c.radius)
  near(r.worldContactY,c.y+r.normalY*c.radius)
  sum=assertAccepted(c,v,sum)
 end
 near(v.age,120*cfg.movementStep)
 assert(c.state=='EXPOSED' and c.exposure>0)
end
''',
    'center重合120帧保留旧方向但不归一化零向量': r'''
local w,c,v,setPoint=fixedReleased('center_previous_direction')
setPoint(0,-.3); tick(w,c)
local r=assert(contact(c)); local oldAngle=r.stableLocalAngle; local first=r.firstSeen
setPoint(0,0); local sum=c.exposure+c._charge
for frame=1,120 do
 setPoint(0,0); local pose=tick(w,c)
 assert(contact(c)==r and c.contactVisualAnchor==r and r.firstSeen==first)
 near(delta(r.stableLocalAngle,oldAngle),0)
 near(r.normalX,0); near(r.normalY,-1)
 assert(not r.rawNormalX and not r.rawNormalY)
 assert(not lastDiagnostic.rawDirection and pose)
 near(distance(c,v),0)
 sum=assertAccepted(c,v,sum)
end
''',
    'center无旧方向120帧即使真实速度非零也不伪造附着': r'''
local w,c,v,setPoint=fixedReleased('center_no_previous_direction')
assert(v.vx^2+v.vy^2>0,'真实Release带速度，仍不得借速度发明接触方向')
setPoint(0,0); local sum=0
for frame=1,120 do
 setPoint(0,0); assert(tick(w,c)==nil)
 assert(#c.contactVisuals==0 and not c.contactVisualAnchor)
 assert(not lastDiagnostic.rawDirection and not lastDiagnostic.stableDirection)
 assert(not lastDraw.drawPosition and not lastDraw.drawAngle)
 sum=assertAccepted(c,v,sum)
end
assert(c.state=='EXPOSED' and c.exposure>0 and c.releasedContribution>0)
''',
    'nearcenter正负噪声120帧保留历史或保持无方向': r'''
for _,history in ipairs({true,false}) do
 local w,c,v,setPoint=fixedReleased(history and 'nearcenter_history' or 'nearcenter_no_history')
 local record,angle
 if history then setPoint(-.3,0); tick(w,c); record=assert(contact(c)); angle=record.stableLocalAngle end
 local sum=c.exposure+c._charge
 for frame=1,120 do
  local sign=frame%2==0 and 1 or -1
  setPoint(.009*sign,.008*(-sign))
  local pose=tick(w,c)
  assert(distance(c,v)<Contacts.Settings.epsilon)
  assert(not lastDiagnostic.rawDirection)
  if history then
   assert(contact(c)==record and pose); near(delta(record.stableLocalAngle,angle),0)
   near(record.normalX,-1); near(record.normalY,0)
  else assert(#c.contactVisuals==0 and not c.contactVisualAnchor and not pose) end
  sum=assertAccepted(c,v,sum)
 end
end
''',
    '自然玩家SetMovement接近穿过离开并回落': r'''
local s,w=freshSim(); local c=w.cells[55]
placePlayerOnce(w,c.x-1.5,c.y)
startTrace(w,c,'natural_player_pass_through','自然模拟：一次初始化玩家位置，此后仅SetMovement，完整SimState.Update')
w:SetMovement(1,0)
local minimum=math.huge; local peak=0; local seen=false; local gone=false; local firstRecord
local previousX=w.player.x
for frame=1,300 do
 local pose=tick(w,c,s)
 assert(w.player.x>previousX,'自然穿过路径应继续向右，不能逐帧传送')
 previousX=w.player.x; minimum=math.min(minimum,distance(w.player,c)); peak=math.max(peak,c.exposure)
 local r=contact(c,'PLAYER_SWARM',w.player.id)
 if r and r.active then
  seen=true; if not firstRecord then firstRecord=r else assert(firstRecord==r) end
  assert(c.everPlayerContact and c.covered and pose)
 elseif seen then gone=true end
 assert(c.state~='LATENT','短暂自然穿过不能伪装持续感染')
end
assert(seen and gone and minimum<.02 and w.player.x>c.x+3)
assert(peak>0 and c.exposure>0 and c.exposure<peak and c.state=='EXPOSED')
assert(not c.covered and #c.contactVisuals==0 and c.contactVisualAnchor==firstRecord)
assert(s.tickCount==300 and #w.immunes>0)
''',
    '自然玩家持续接触达到LATENT且后120帧不重置': r'''
local s,w=freshSim(); local c=w.cells[55]
placePlayerOnce(w,c.x+.3,c.y)
startTrace(w,c,'natural_player_until_latent','自然模拟：SetMovement反馈保持接触，不写来源逐帧坐标，真实免疫保留')
local infectedFrame=nil; local timestamp=nil; local anchor=nil; local sum=0
local moves=0; local ox,oy=w.player.x,w.player.y
for frame=1,2400 do
 steerTo(w,c.x+.3,c.y); tick(w,c,s)
 if w.player.x~=ox or w.player.y~=oy then moves=moves+1 end
 ox,oy=w.player.x,w.player.y
 assert(distance(c,w.player)<.34)
 if not infectedFrame then
  local combined=c.exposure+c._charge
  if c.state~='LATENT' then assert(combined>=sum-1e-9) end
  sum=combined -- LATENT结算有1.0 clamp，上帧待结算量可能已经略超1。
  if c.state=='LATENT' then
   infectedFrame,timestamp,anchor=frame,c.infectedVisualAt,c.contactVisualAnchor
   assert(timestamp==w.time and anchor and c.infectionSource=='player')
   assert(c.groupContribution>0 and c.releasedContribution==0 and c.everPlayerContact)
  end
 else
  assert(c.state=='LATENT' and c.exposure==1 and c.infectedVisualAt==timestamp)
  assert(c.contactVisualAnchor==anchor and c.infectionSource=='player')
  if frame-infectedFrame>=120 then break end
 end
end
assert(infectedFrame and infectedFrame>=120 and moves>120)
assert(w.stats.totalInfected==1 and c.latencyTimer>0)
-- SimState已消费世界业务事件；累计统计和触发标志必须各自来自真实更新。
assert(s.triggeredCardEvents.infection_complete and s.stage==1 and not s.cards.pending)
assert(c.infectionSerial==1 and not c.hasReleasedVirus, '成功感染保存权威序号；首次释放前不完成首轮任务')
assert(#c.contactVisuals==0 and c.contactVisualAnchor==anchor)
''',
    '真实Release完整World更新至邻胞LATENT且后120帧不重置': r'''
local w=World.New('UPPER_AIRWAY'); local source,target=w.cells[67],w.cells[63]
assert(source.state=='HEALTHY' and target.state=='HEALTHY' and target.exposure==0)
assert(distance(w.player,source)>20 and distance(w.player,target)>20)
-- 测试注入一次真实Release事件，36个真实出生；保留全部72细胞、初始来源位置/速度。
-- 不强改感染状态，不搬运Released到目标，不提高power或缩短感染时间。
w:_Release(source,36)
local v=w.releasedViruses[1]; local birthX,birthY=v.x,v.y
local births={}
for _,item in ipairs(w.releasedViruses) do births[item.id]={item.sourceCellId,item.sourceRegionId} end
startTrace(w,target,'natural_released_until_latent','自然Released：真实67号Release出生，完整地图/免疫更新，不传送来源、不改感染公式')
local infectedFrame=nil; local timestamp=nil; local anchor=nil; local moved=false; local seen=false
for frame=1,4200 do
 tick(w,target)
 if v.x~=birthX or v.y~=birthY then moved=true end
 assert(not target.everPlayerContact and target.groupContribution==0)
 assert(target._groupCharge==0)
 for _,item in ipairs(w.releasedViruses) do
  local birth=births[item.id]
  if birth then assert(item.sourceCellId==birth[1] and item.sourceRegionId==birth[2]) end
 end
 if lastDiagnostic.acceptedContact then assert(lastDiagnostic.sourceType=='RELEASED_VIRUS'); seen=true end
 if not infectedFrame then
  if target.state=='LATENT' then
   infectedFrame,timestamp,anchor=frame,target.infectedVisualAt,target.contactVisualAnchor
   assert(target.infectionSource=='released' and target.exposure==1 and target.releasedContribution>0)
   assert(eventCount(w,'infection_complete',target.id)==1)
   assert(eventCount(w,'independent_infection',target.id)==1)
  end
 else
  assert(target.state=='LATENT' and target.exposure==1 and target.infectedVisualAt==timestamp)
  assert(target.contactVisualAnchor==anchor and target.infectionSource=='released')
  assert(eventCount(w,'infection_complete',target.id)==1 and eventCount(w,'independent_infection',target.id)==1)
  if frame-infectedFrame>=120 then break end
 end
end
assert(infectedFrame and infectedFrame>=120 and moved and seen and anchor)
assert(target.latencyTimer>0 and #target.contactVisuals==0)
assert(w.stats.independentInfections>=1 and w.stats.totalAbsorbed==0)
assert(distance(w.player,target)>15 and #w.immunes>0)
''',
    'hysteresis跨2度binnoise稳定120帧并拒绝不稳定候选': r'''
local w,c,v,setPoint=fixedReleased('hysteresis_bin_noise')
local base=math.rad(1)
local function angle(a) setPoint(.3*math.cos(c.rotation+a),.3*math.sin(c.rotation+a)) end
angle(base); local firstPose=tick(w,c); local r=assert(contact(c)); local stable=r.stableLocalAngle
local oldSum=c.exposure+c._charge; local rawBins={}
for frame=1,120 do
 local a=base+math.rad(frame%2==0 and .6 or -.6)
 angle(a); local pose=tick(w,c)
 assert(contact(c)==r and pose.bin==firstPose.bin and pose.subBin==firstPose.subBin)
 near(delta(r.stableLocalAngle,stable),0); assert(r.candidateFrames==0)
 rawBins[1+math.floor((a% (math.pi*2))/(math.pi*2)*180+.5)%180]=true
 oldSum=assertAccepted(c,v,oldSum)
end
assert(rawBins[1] and rawBins[2],'原始方向实际跨量化边界，不能只测试同一bin')
-- 大于12度但每帧相差超过3度，候选不能连满3帧而改变target。
for frame=1,120 do
 angle(base+math.rad(frame%2==0 and 25 or 55)); tick(w,c)
 assert(r.candidateFrames==1); near(delta(r.stableLocalAngle,stable),0)
end
-- 死区内11.9度仍不转；超过12度且连续稳定3帧才开始每帧3度。
for frame=1,3 do angle(base+math.rad(11.9)); tick(w,c); near(delta(r.stableLocalAngle,stable),0) end
for frame=1,3 do
 angle(base+math.rad(12.1)); tick(w,c)
 if frame<3 then near(delta(r.stableLocalAngle,stable),0); assert(r.candidateFrames==frame)
 else near(delta(r.stableLocalAngle,stable),Contacts.Settings.maxTurn); assert(r.candidateFrames==0) end
end
''',
    '真实固定源90度转向至少3稳定帧且每帧至多3度': r'''
local w,c,v,setPoint=fixedReleased('hysteresis_ninety_degree_turn')
local function angle(a) setPoint(.3*math.cos(c.rotation+a),.3*math.sin(c.rotation+a)) end
angle(0); tick(w,c); local r=assert(contact(c)); local initial=r.stableLocalAngle
local oldPose=assert(surface:GetPlacement(c,{localAngle=initial}))
local previous=initial; local bins={oldPose.bin}; local turns=0
local expectedTurns=math.ceil((math.pi/2)/Contacts.Settings.maxTurn-1e-9)
for frame=1,math.max(120,expectedTurns+3) do
 angle(math.pi/2); local pose=tick(w,c)
 assert(contact(c)==r)
 local change=delta(r.stableLocalAngle,previous)
 assert(change>=-1e-9 and change<=Contacts.Settings.maxTurn+1e-9)
 if frame<3 then near(change,0); assert(r.candidateFrames==frame)
 elseif frame==3 then near(change,Contacts.Settings.maxTurn); near(delta(r.targetLocalAngle,math.pi/2),0)
 end
 if change>1e-9 then turns=turns+1 end
 local sampleCount=surface.data.angle_bins*surface.data.placement_subdivisions
 local subStep=math.abs((pose.subBin-oldPose.subBin+sampleCount/2)%sampleCount-sampleCount/2)
 assert(subStep<=math.ceil(Contacts.Settings.maxTurn/(math.pi*2)*sampleCount+1e-9),
  '细分姿态不能超出真实转向上限对应子档数')
 local binStep=math.abs((pose.bin-oldPose.bin+90)%180-90)
 assert(binStep<=2,'不超过3度转向最多跨两个2度组')
 previous,oldPose=r.stableLocalAngle,pose; bins[#bins+1]=pose.bin
end
assert(turns==expectedTurns,'90度应按真实maxTurn逐步转向，不能突变')
near(delta(r.stableLocalAngle,math.pi/2),0)
assert(bins[2]==bins[1] and bins[3]==bins[1])
if Contacts.Settings.maxTurn>=math.rad(1) then assert(bins[4]~=bins[1]) end
''',
    '真实CellSurface全角量化误差和CPU姿态缓存有界': r'''
local w,c,v,setPoint=fixedReleased('surface_real_quantization_and_cache')
local count=surface.data.angle_bins*surface.data.placement_subdivisions
local limit=count*2
local seen={}
for frame=1,count do
 local a=(frame-1)*math.pi*2/count
 setPoint(.3*math.cos(c.rotation+a),.3*math.sin(c.rotation+a)); tick(w,c)
 -- 独立遍历真实GetPlacement所有子档，每个边界前后严格限制误差<=0.125度。
 for _,noise in ipairs({-.49,.49}) do
  local q=(a+noise*math.pi*2/count)%(math.pi*2)
  local pose=assert(surface:GetPlacement(c,{localAngle=q}))
  local expected=1+math.floor(q/(math.pi*2)*count+.5)%count
  assert(pose.subBin==expected and pose.bin==1+(expected-1)//surface.data.placement_subdivisions)
  near(delta((pose.subBin-1)*math.pi*2/count,q),0,math.pi/count+1e-9)
  local point=surface.data.fine_placements[pose.subBin]
  near(pose.x,point[1]); near(pose.y,point[2]); near(pose.normalX,point[3]); near(pose.normalY,point[4])
  seen[pose.subBin]=true; allFinite(pose)
  local outward=surface.meta.outward
  local rx=pose.cos*outward[1]-pose.sin*outward[2]
  local ry=pose.sin*outward[1]+pose.cos*outward[2]
  near(rx,-pose.normalX,2e-8); near(ry,-pose.normalY,2e-8)
 end
 assert(surface:GetStats().poseCount<=limit)
end
local covered=0; for _ in pairs(seen) do covered=covered+1 end; assert(covered==count)
-- 新缩放键数量超过真实CPU上限，必须实际清空/淘汰；不削弱为只测少量键，也不冒称GPU LRU。
local cleared=false
local before=surface:GetStats().poseCount
for i=1,limit+1 do
 local pose=assert(surface:GetPlacement(c,{localAngle=i*.017},1+i*.0001))
 allFinite(pose)
 local after=surface:GetStats().poseCount
 assert(after<=limit)
 if after<before then cleared=true end
 before=after
end
assert(cleared,'必须实际观察CPU姿态缓存触达边界后的回收')
assert(surface:GetStats().resources==0,'本回归不创建GPU纹理')
''',
}


def to_lua(lua: LuaRuntime, value):
    if isinstance(value, dict):
        return lua.table_from({key: to_lua(lua, item) for key, item in value.items()})
    if isinstance(value, list):
        return lua.table_from([to_lua(lua, item) for item in value])
    return value


def to_python(value):
    if hasattr(value, 'items'):
        items = dict(value.items())
        if not items:
            return []
        if all(isinstance(key, int) for key in items) and set(items) == set(range(1, len(items) + 1)):
            return [to_python(items[key]) for key in range(1, len(items) + 1)]
        return {str(key): to_python(item) for key, item in items.items()}
    if isinstance(value, float) and not math.isfinite(value):
        raise AssertionError(f'诊断JSON包含非有限数值 {value}')
    return value


def new_runtime(data, meta):
    lua = LuaRuntime(unpack_returned_tuples=True)
    logs = []
    traces = {}
    current = {'name': None}
    lua.globals().test_log = lambda *args: logs.append(' '.join(map(str, args)))
    lua.globals().TEST_PATH = str(ROOT / 'scripts' / '?.lua')
    lua.execute("package.path=TEST_PATH..';'..package.path; print=test_log")
    lua.globals().SURFACE_DATA = to_lua(lua, data)
    lua.globals().SURFACE_META = to_lua(lua, meta)

    def begin_trace(name, evidence):
        if name in traces:
            raise AssertionError(f'重复trace名称 {name}')
        current['name'] = name
        traces[name] = {'evidence': evidence, 'rows': []}

    def sink(row):
        record = to_python(row)
        record['evidence'] = traces[current['name']]['evidence']
        record['drawEvidence'] = 'transform-only；直接Diagnostics.Draw取样，非实际DrawParticle/GPU像素证据'
        traces[current['name']]['rows'].append(record)

    def attach(key, row):
        traces[current['name']]['rows'][-1][key] = to_python(row)

    lua.globals().begin_trace = begin_trace
    lua.globals().emit_diagnostics = sink
    lua.globals().emit_draw = lambda row: attach('draw', row)
    lua.globals().emit_geometry = lambda row: attach('geometry', row)
    lua.execute(SETUP)
    return lua, logs, traces


def validate_trace(name, rows):
    assert len(rows) >= 120, f'{name} 不足120真实固定帧'
    required = {'frame', 'time', 'cellId', 'sourceType', 'sourceId', 'cellPosition',
                'sourcePosition', 'acceptedContact', 'acceptedPower', 'deltaExposure',
                'pendingCharge', 'exposure', 'infectionProgress', 'progressField',
                'oldState', 'newState', 'stateAfterUpdate', 'cellRotation', 'draw', 'geometry'}
    for frame, row in enumerate(rows, 1):
        assert required <= row.keys(), f'{name} 真实诊断字段缺失 {required-row.keys()}'
        assert row['frame'] == frame and row['draw']['frame'] == frame
        assert row['stateAfterUpdate'] == row['newState']
        assert row['infectionProgress'] == row['exposure']
        json.dumps(row, ensure_ascii=False, allow_nan=False)
    # 固定夹具和自然累计都应真实有非结算delta=0帧，而不能伪造每帧exposure增长。
    assert sum(row['deltaExposure'] == 0 for row in rows) >= 100


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', help='只运行名称包含给定文字的测试')
    parser.add_argument('--output', type=Path, default=ROOT / 'validation')
    args = parser.parse_args()
    selected = {name: code for name, code in TESTS.items() if not args.only or args.only in name}
    if not selected:
        parser.error('--only 没有匹配测试')
    data = json.loads((ROOT / 'assets/image/cell_surface_data.json').read_text(encoding='utf-8'))
    meta = json.loads((ROOT / 'assets/image/virus_attached_meta.json').read_text(encoding='utf-8'))
    args.output.mkdir(parents=True, exist_ok=True)
    failures = []
    started = time.perf_counter()
    written = []
    max_turn = None
    for name, code in selected.items():
        start = time.perf_counter()
        lua, logs, traces = new_runtime(data, meta)
        max_turn = math.degrees(lua.globals().Contacts.Settings.maxTurn)
        passed = False
        try:
            lua.execute(code)
            for trace_name, trace in traces.items():
                validate_trace(trace_name, trace['rows'])
            passed = True
            print(f'PASS {name} ({time.perf_counter()-start:.2f}s)')
        except Exception as exc:
            failures.append(name)
            print(f'FAIL {name}\n{exc}')
            for line in logs[-6:]:
                print(' LOG', line)
        finally:
            # 失败仍保留真实trace供诊断，不将失败证据宣传为通过或人工验收。
            for trace_name, trace in traces.items():
                path = args.output / f'cell_runtime_{trace_name}.jsonl'
                with path.open('w', encoding='utf-8') as file:
                    for row in trace['rows']:
                        file.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
                written.append((path, len(trace['rows']), passed))
            del lua
    print(f' RUNTIME maxTurn={max_turn:.6f}度 '
          f'angleBins={data["angle_bins"]} subBins={len(data["fine_placements"])} '
          f'CPU姿态上限={len(data["fine_placements"])*2}')
    for path, count, passed in written:
        print(f' TRACE {path}: {count}帧，所属测试{"通过" if passed else "失败"}')
    print(f'{len(selected)-len(failures)}/{len(selected)} 通过，{len(failures)} 失败 '
          f'({time.perf_counter()-started:.2f}s)')
    print('仅Lua真实运行时/诊断变换回归；未build，未执行真实浏览器/GPU像素或人工视觉验收。')
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
