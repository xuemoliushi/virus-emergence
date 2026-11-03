"""Run existing AI/mechanism/world checks with isolated Python processes."""
import sys,re,json,subprocess,hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[1]
CASES=[('ai_behavior_regression.py',[]),('mechanism_cards_regression.py',[]),('card_system_regression.py',[]),('swarm_regression.py',['--no-stress'])]

def manifest():
    paths=list((ROOT/'scripts/Core').glob('*.lua'))+[ROOT/'tests'/name for name,_ in CASES]+[Path(__file__).resolve()]
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}

def main():
    sources=manifest();results=[];folder=ROOT/'validation/ai-emergence';folder.mkdir(parents=True,exist_ok=True)
    for name,args in CASES:
        relative='tests/'+name
        code="import sys,runpy;sys.stdout.reconfigure(encoding='utf-8');sys.path[:0]="+repr([str(ROOT/'.tmp/test-deps'),str(ROOT/'tests')])+";sys.argv="+repr([relative]+args)+";runpy.run_path("+repr(relative)+",run_name='__main__')"
        process=subprocess.run([sys.executable,'-B','-c',code],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
        output=process.stdout+process.stderr
        (folder/(Path(name).stem+'.log')).write_text(output,encoding='utf-8')
        counts=re.findall(r'(?m)^(?:Mechanism:\s*)?(\d+)/(\d+)',output)
        passed,total=map(int,counts[-1]) if counts else (0,0)
        ok=process.returncode==0 and total>0 and passed==total
        results.append(dict(file=relative,passed=ok,return_code=process.returncode,checks_passed=passed,checks_total=total))
        print(f'{"PASS" if ok else "FAIL"}: {name} {passed}/{total}',flush=True)
    unchanged=sources==manifest();ok=unchanged and all(r['passed'] for r in results)
    data=dict(passed=ok,generated_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),sources_unchanged=unchanged,source_sha256=sources,results=results,
              scope='Historical 26x32 fixtures; swarm fixed-step FPS assay disables wall-clock budget. Full production-map acceptance is separate.')
    (folder/'regression.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if ok else 1
if __name__=='__main__':raise SystemExit(main())
