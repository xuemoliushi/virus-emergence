"""Development-stage regression through real Sim ticks and card/HUD callbacks."""
import json
from evolution_regression import ROOT, SETUP, GROWTH_SETUP, EXTRA, LuaRuntime

from evolution_regression import TESTS as FLOW_TESTS

TESTS = {k:v for k,v in FLOW_TESTS.items() if k.startswith(('第一阶段','阶段二','阶段三','阶段四五六','第六阶段','六次选卡','跨阶段'))}


def main():
    rows=[]
    for name,code in TESTS.items():
        lua=LuaRuntime(unpack_returned_tuples=True)
        lua.execute("package.path='scripts/?.lua;'..package.path")
        logs=[]
        lua.globals().print=lambda *args:logs.append(' '.join(map(str,args)))
        try:
            lua.execute(SETUP+GROWTH_SETUP+EXTRA+code)
            row=dict(name=name,passed=True)
        except Exception as error:
            row=dict(name=name,passed=False,error=str(error),logs=logs[-5:])
        rows.append(row)
        print(('PASS: ' if row['passed'] else 'FAIL: ')+name,flush=True)
        if not row['passed']:print(row['error'],flush=True)
    from bird_ui_regression import runtime
    from compact_ui_regression import SMALL
    name='HUD exposes the correct goal and hint at all six stages'
    try:
        lua=runtime()
        lua.execute(SMALL+r'''
local h,g,s=fixture()
local names={'首次产出','回收与感染','多点产毒','继续扩张','扩大感染','最后进化'}
for stage=1,6 do
 s.evolution:Enter(stage,0,s.world);s:UpdateTasks(false);h:Update(.2)
 assert(h.root:FindById('stageName'):GetText():find(names[stage]))
 assert(h.root:FindById('taskText'):GetText()==s.task.text)
 assert(h.root:FindById('taskReward'):GetText()==s.task.reward)
 assert(h.root:FindById('taskHint'):IsVisible())
 assert(h.root:FindById('taskProgress'):GetText()==s.task.detail)
 assert(not s.task.text:find('分裂') and not s.task.text:find('受击'))
end
s.formalFinished=true;s.evolution:BeginFinal(s.world);s:UpdateTasks(false);h:Update(.2)
assert(h.root:FindById('stageName'):GetText():find('终局'))
assert(h.root:FindById('taskProgress'):GetText():find('获卡后新感染'))
assert(h.stageSummary.seenStage==7 and h.stageSummary.target==1)
for _,cell in ipairs(s.world.cells) do
 if cell.state=='HEALTHY' then s.world:_Infect(cell,'fixture');s.world:KillCell(cell,'tcell') end
end
s.evolution:BeginFinal(s.world);s:UpdateTasks(false);h:Update(.2)
assert(s.task.target==0 and not s.task.complete and h.root:FindById('taskProgressBar').props.value==0)
s.victoryQualified=true;s:UpdateTasks(false);h:Update(.2)
assert(s.task.complete and h.root:FindById('taskProgressBar').props.value==1)
''')
        row=dict(name=name,passed=True)
    except Exception as error:
        row=dict(name=name,passed=False,error=str(error))
    rows.append(row)
    print(('PASS: ' if row['passed'] else 'FAIL: ')+name,flush=True)
    if not row['passed']:print(row['error'],flush=True)
    folder=ROOT/'validation/flow-redesign-20261019'
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'targeted.json').write_text(json.dumps(dict(passed=all(row['passed'] for row in rows),results=rows,
        scope='Real Lua Core/Sim updates and mock HUD callbacks. Authored infection fixtures; not native player or visual acceptance.'),
        ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return int(any(not row['passed'] for row in rows))


if __name__=='__main__':raise SystemExit(main())
