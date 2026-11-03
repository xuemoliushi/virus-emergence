"""Four rule families: production assays plus a labeled topology negative control."""
from pathlib import Path
import sys,json,time,hashlib,argparse
from datetime import datetime,timezone,timedelta
from collections import deque
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.tmp/test-deps'),str(ROOT/'tests')]
from ai_non_runtime_acceptance import plain,manifest
from lua_test_runtime import LuaRuntime

def run(seed,name):
    lua=LuaRuntime(unpack_returned_tuples=True)
    lua.execute('package.path='+repr((ROOT/'scripts/?.lua').as_posix()+';'+(ROOT/'tests/?.lua').as_posix())+"..';'..package.path")
    log=deque(maxlen=12);lua.globals().print=lambda *v:log.append(' '.join(map(str,v)))
    suite=lua.execute((ROOT/'tests/ai_emergence_scenarios.lua').read_text(encoding='utf-8'))
    started=time.perf_counter()
    try:
        result=plain(suite[name](seed));result.update(seed=seed,case=name,status='PASS')
    except Exception as error:
        result=dict(seed=seed,case=name,status='FAIL',error=str(error),checks=plain(lua.globals().ACCEPTANCE_TRACE),logs=list(log))
    result['wall_seconds']=round(time.perf_counter()-started,3)
    print(f"{result['status']}: {seed} {name} ({result['wall_seconds']}s)",flush=True)
    return result

def fingerprint():
    result=manifest()
    for name in ['ai_emergence_scenarios.lua','ai_emergence_acceptance.py']:
        p=ROOT/'tests'/name;result[p.relative_to(ROOT).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seeds',nargs='+',type=int,default=[314159,271828,161803])
    parser.add_argument('--only',choices=['Autonomy','Immunity','Signals','Defense','Navigation','Barrier'])
    parser.add_argument('--output',type=Path,default=ROOT/'validation/ai-emergence')
    args=parser.parse_args();before=fingerprint()
    results=[run(seed,name) for seed in args.seeds for name in ([args.only] if args.only else ['Autonomy','Immunity','Signals','Defense','Navigation','Barrier'])]
    unchanged=before==fingerprint();passed=unchanged and all(r['status']=='PASS' for r in results)
    data=dict(passed=passed,generated_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),results=results,sources_unchanged=unchanged,source_sha256=before)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'checks.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    rows=['# 四类涌现规则非实机验收','',f'总体：{"通过" if passed else "未通过"}。时间：{data["generated_at"]}。','',
          '| 种子 | 场景 | 结果 | 场景断言 |','| --- | --- | --- | --- |']
    for r in results:rows.append(f'| {r["seed"]} | {r["case"]} | {r["status"]} | {len(r.get("checks") or [])} |')
    rows+=['','生产地图为 v5 / 120×144 米 / 960 细胞；固定默认参数，Core 业务函数完整保留。',
           'Autonomy/Immunity/Signals/Defense 是明确布置演员位置、通过权威感染和病程入口建立节点的因果隔离场景；Autonomy 的临近完成选择显式设置曝光 .85。',
           'Immunity 直接步进真实免疫模块，Signals/Defense 直接步进真实场模块以隔离识别、扩散、延迟与消退，不计为自然游玩。',
           'Barrier 单独使用标注的合成双封闭区域与输入脉冲，只验证墙体阻断扩散，不能代替正式地图验收。',
           '完整真实 World/Sim 循环、质量账本及同种子重放另见 ai-non-runtime/report.md。操作、画面、FPS、整局平衡和玩家感受未验证。']
    (args.output/'report.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    print(f'{"PASS" if passed else "FAIL"}: {len(results)} scenarios; {args.output}',flush=True)
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
