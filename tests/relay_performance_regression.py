"""Actual skill-range drawing and 960-cell relay simulation; GPU drawing is stubbed."""
import argparse
import json
from pathlib import Path
from mechanism_cards_regression import ROOT, SETUP, GROWTH_SETUP, EXTRA, LuaRuntime

SCENARIO = r'''
local w=quietWorld('UPPER_AIRWAY');grant(w,'membrane_glide')
local source=w.player
local chosen
for _,c in ipairs(w.cells) do
 for i=0,15 do
  local angle=i*math.pi/8
  local x,y=c.x+math.cos(angle)*(c.radius+source.radius*.75),c.y+math.sin(angle)*(c.radius+source.radius*.75)
  if w.map:Contains(x,y,source.radius) then
   place(w,source,x,y);w:_AccumulateExposure(.01)
   if A.Validate(w,'membrane_glide',source.id,{cellId=c.id}) then chosen=c;break end
  end
 end
 if chosen then break end
end
assert(chosen)
package.loaded['urhox-libs/UI/Core/Theme']={}
package.loaded['urhox-libs/UI/Core/ImageCache']={}
local View=require('Game.Views.CellView')
for _,name in ipairs({'nvgBeginPath','nvgCircle','nvgStrokeColor','nvgStrokeWidth','nvgStroke'}) do _G[name]=function() end end
function nvgRGBA() return 0 end
local sim={world=w,skillSelection={id='membrane_glide',swarmId=source.id}}
local calls=0
function sim:ValidateSkill(id,swarmId,target)
 calls=calls+1;return A.Validate(self.world,id,swarmId,target)
end
collectgarbage('collect')
local started=os.clock()
for _=1,120 do View.DrawSkillRange({},nil,sim,20,0,0) end
local selectionSeconds=os.clock()-started
local selectionCalls=calls
-- Rendering must keep the exact authority-approved target set, including a
-- reordered array where numeric IDs no longer match array positions.
local rings={}
function nvgCircle(_,x,y,r) rings[#rings+1]={x=x,y=y,r=r} end
for _,id in ipairs({'membrane_glide','node_cover','node_hide','node_takeover'}) do
 grant(w,id);sim.skillSelection.id=id
 local expected={}
 for _,c in ipairs(w.cells) do
  if A.Validate(w,id,source.id,{cellId=c.id}) then expected[#expected+1]=c end
 end
 rings={};View.DrawSkillRange({},nil,sim,20,0,0)
 assert(#rings==#expected+1,'Highlight set differs from authority: '..id)
 for i,c in ipairs(expected) do near(rings[i+1].x,c.x*20);near(rings[i+1].y,c.y*20) end
end
local first,last=w.cells[1],w.cells[#w.cells]
w.cells[1],w.cells[#w.cells]=last,first
assert(A.CellById(w,first.id)==first and A.CellById(w,last.id)==last)
assert(A.CellById(w,nil)==nil and A.CellById(w,-999)==nil)
local sparse={id=10001};w.cells[#w.cells+1]=sparse
assert(A.CellById(w,10001)==sparse)
w.cells[#w.cells]=nil;w.cells[1],w.cells[#w.cells]=first,last
assert(skill(w,'membrane_glide',{cellId=chosen.id}))
local team=w.swarms[2]
source.anchored=true
local moves,moveSeconds=0,0
local move=w.map.Move
w.map.Move=function(map,...)
 local start=os.clock();local x,y=move(map,...)
 moves=moves+1;moveSeconds=moveSeconds+os.clock()-start;return x,y
end
started=os.clock()
for _=1,300 do w:Update(cfg.movementStep) end
local simulationSeconds=os.clock()-started
assert(team.relayCellId==chosen.id and team.mass==3 and w:ControlledCount()==30)
checkConservation(w,true)
return {cells=#w.cells,selectionFrames=120,validationCalls=selectionCalls,
 selectionMsPerFrame=selectionSeconds/120*1000,simulationSteps=300,
 simulationMsPerStep=simulationSeconds/300*1000,mapMoves=moves,mapMoveMs=moveSeconds*1000}
'''

def run(label):
    lua=LuaRuntime(unpack_returned_tuples=True)
    lua.execute('package.path='+repr((ROOT/'scripts/?.lua').as_posix())+"..';'..package.path")
    lua.execute("local c=require('Core.Config').Gameplay;production={width=c.width,height=c.height,cellCount=c.cellCount,version=c.mapGenerationVersion}")
    lua.globals().print=lambda *args:None
    lua.execute(SETUP+GROWTH_SETUP+EXTRA)
    lua.execute('cfg.width,cfg.height,cfg.cellCount,cfg.mapGenerationVersion=production.width,production.height,production.cellCount,production.version')
    row=dict(lua.execute(SCENARIO).items())
    row['scope']='Lua CPU timing only; production 960-cell map, native GPU/browser excluded'
    out=ROOT/'validation/relay-performance-20261018'
    out.mkdir(exist_ok=True)
    (out/(label+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(row,ensure_ascii=False,indent=2))
    if label!='before':
        assert row['validationCalls']<=120*12,'Skill preview must restrict authority checks to nearby cells'

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--label',default='after')
    run(parser.parse_args().label)
