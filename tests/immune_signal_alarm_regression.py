"""Local signal confirmation against real field/AI modules; explicit field assays."""
import json
from immune_adaptation_regression import ROOT,SETUP,GROWTH_SETUP,COMMON,LuaRuntime
COMMON_SIGNAL=r'''
E=require('Core.LocalEcology')
function field(w,activity,damage,debris)
 for _,n in ipairs(w.ecology.nodes)do n.activity=activity or 0;n.damage=damage or 0;n.debris=debris or 0 end
end
function observe(w,m,seconds)
 for _=1,math.floor(seconds/cfg.movementStep+.5)do
  w.time=w.time+cfg.movementStep;Director.ObserveActivity(w,m,cfg.movementStep)
 end
end
'''
TESTS={
'sustained activity warns at I after three seconds without a target lock':r'''
local w,m=clearFixture('macrophage',1);field(w,.5)
observe(w,m,2.9);assert(#w.immuneAlarms==0)
observe(w,m,.1);assert(#w.immuneAlarms==1 and not m.targetId)
local a=w.immuneAlarms[1];assert(a.x==m.x and a.y==m.y and not a.targetId)
observe(w,m,3);assert(#w.immuneAlarms==1,'normal source cooldown remains active')
''',
'weak interrupted and declining traces do not accumulate confirmation':r'''
local w,m=clearFixture('macrophage',1);field(w,.5);observe(w,m,2)
field(w,.1);observe(w,m,.5);field(w,.5);observe(w,m,2)
assert(#w.immuneAlarms==0)
for i=1,10 do field(w,.5-i*.01);observe(w,m,.5)end
assert(#w.immuneAlarms==0 and m._activityAlarmTimer==0)
''',
'damage and debris channels cannot masquerade as ongoing viral production':r'''
local w,m=clearFixture('macrophage',1);field(w,0,6,6);observe(w,m,8)
assert(#w.immuneAlarms==0)
''',
'low alert T cells and processing macrophages never signal-alarm':r'''
for _,kind in ipairs({'macrophage','tcell'})do
 local w,m=clearFixture(kind,0);field(w,.5);observe(w,m,4);assert(#w.immuneAlarms==0)
 w.activeImmuneAlertLevel=1;m.state='processing';observe(w,m,4);assert(#w.immuneAlarms==0)
end
''',
'large timestep cannot compress sustained confirmation into one observation':r'''
local w,m=clearFixture('macrophage',1);field(w,.5)
Director.ObserveActivity(w,m,30);assert(#w.immuneAlarms==0 and m._activityAlarmTimer<=.5)
''',
'real authority production creates signal and a later alarm; dead source fades':r'''
local w,m=immuneFixture('macrophage');local c=unitCell(w,1,13,27.5);w.cells={c};w.activeImmuneAlertLevel=1
m.x,m.y=c.x,c.y;place(w,w.player,13,3.1)
w:_Infect(c,'fixture');w:_AgeCells(cfg.latentSeconds)
for _=1,120 do E.Update(w,.5);w.time=w.time+.5;Director.ObserveActivity(w,m,.5)end
assert(#w.immuneAlarms>0 and not m.targetId)
w:KillCell(c,'fixture')
local before=w._nextImmuneAlarmId
for _=1,120 do E.Update(w,.5);w.time=w.time+.5;Director.ObserveActivity(w,m,.5)end
assert(w._nextImmuneAlarmId==before,'local decaying field does not rearm the report')
''',
}
def main():
 rows=[]
 for name,code in TESTS.items():
  lua=LuaRuntime(unpack_returned_tuples=True)
  lua.execute('package.path='+repr((ROOT/'scripts/?.lua').as_posix())+"..';'..package.path")
  logs=[];lua.globals().print=lambda *v:logs.append(' '.join(map(str,v)))
  try:lua.execute(SETUP+GROWTH_SETUP+COMMON+COMMON_SIGNAL+code);row=dict(name=name,passed=True)
  except Exception as error:row=dict(name=name,passed=False,error=str(error),logs=logs[-5:])
  rows.append(row);print(('PASS: ' if row['passed'] else 'FAIL: ')+name,flush=True)
  if not row['passed']:print(row['error'],row['logs'],flush=True)
 folder=ROOT/'validation/immune-full-stage-20261017'
 (folder/'signal-targeted.json').write_text(json.dumps(dict(passed=all(r['passed'] for r in rows),results=rows),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 return int(any(not r['passed'] for r in rows))
if __name__=='__main__':raise SystemExit(main())
