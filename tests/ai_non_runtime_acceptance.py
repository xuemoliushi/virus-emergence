"""Repeatable production-map AI acceptance without the native engine/window.

Run: python -B tests/ai_non_runtime_acceptance.py
Requires Lua 5.4 via Lupa (normal Python environment or local .tmp/test-deps).
Never builds/submits, starts previews, replaces Core functions or edits balance.
"""
import argparse
from collections import deque
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.tmp/test-deps'))
from lua_test_runtime import LuaRuntime


def plain(value):
    if not hasattr(value, 'items'):
        return value
    keys = list(value.keys())
    if keys and set(keys) == set(range(1, len(keys) + 1)):
        return [plain(value[i]) for i in range(1, len(keys) + 1)]
    return {str(k): plain(v) for k, v in value.items()}


def manifest():
    paths = sorted((ROOT / 'scripts/Core').glob('*.lua'))
    paths += [ROOT / 'tests/ai_non_runtime_scenarios.lua', Path(__file__).resolve(),ROOT/'scripts/UI/HUD.lua',ROOT/'scripts/Game/Views/CellView.lua']
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def run_case(seed, name, seconds):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('package.path=' + repr((ROOT / 'scripts/?.lua').as_posix()) + "..';'..package.path")
    logs = deque(maxlen=12)
    lua.globals().print = lambda *args: logs.append(' '.join(map(str, args)))
    suite = lua.execute((ROOT / 'tests/ai_non_runtime_scenarios.lua').read_text(encoding='utf-8'))
    started = time.perf_counter()
    try:
        if name.startswith('stress'):
            result = suite.Stress(seed, seconds, name != 'stress_base', name == 'stress_active')
        else:
            result = suite[name](seed)
        result = plain(result)
        if 'state_signature' in result:
            result['state_sha256'] = hashlib.sha256(result.pop('state_signature').encode()).hexdigest()
        result.update(seed=seed, case=name, status='PASS', wall_seconds=round(time.perf_counter()-started, 3))
    except Exception as error:
        result = dict(seed=seed, case=name, status='FAIL', error=str(error),
                      checks=plain(lua.globals().ACCEPTANCE_TRACE), logs=list(logs),
                      wall_seconds=round(time.perf_counter()-started, 3))
    print(f"{result['status']}: seed={seed} {name} ({result['wall_seconds']}s)", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', nargs='+', type=int, default=[314159, 271828, 161803])
    parser.add_argument('--stress-seconds', type=int, default=60)
    parser.add_argument('--only', choices=['Base', 'Camouflage', 'Commands', 'stress_base', 'stress_cards', 'stress_active'])
    parser.add_argument('--output', type=Path, default=ROOT / 'validation/ai-non-runtime')
    args = parser.parse_args()
    assert args.stress_seconds >= 1
    sources = manifest()
    results = []
    names = [args.only] if args.only else ['Base', 'Camouflage', 'Commands', 'stress_base', 'stress_cards', 'stress_active']
    for seed in args.seeds:
        for name in names:
            results.append(run_case(seed, name, args.stress_seconds))
    # Re-run the same scripted cards stress scenario from a fresh Lua environment.
    replay = None
    if not args.only:
        repeated = run_case(args.seeds[0], 'stress_active', args.stress_seconds)
        original = next(r for r in results if r['seed']==args.seeds[0] and r['case']=='stress_active')
        fields = ('samples', 'simulated_seconds', 'ending', 'auto_choices', 'state_sha256')
        equal = repeated['status']=='PASS' and original['status']=='PASS' and all(repeated.get(k)==original.get(k) for k in fields)
        replay = dict(seed=args.seeds[0], passed=equal, scope='Same-seed timeline and final signature of all cell states/timers, group and immune decisions/positions, released viruses, mass statistics and RNG; excludes wall-clock timings.')
        repeated['case'] = 'stress_active_replay'
        results.append(repeated)
    unchanged = sources == manifest()
    passed = all(r['status']=='PASS' for r in results) and unchanged and (not replay or replay['passed'])
    head = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    report = dict(passed=passed, generated_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
                  git_head=head, uncommitted_sources=True, environment=dict(os=platform.platform(), python=platform.python_version(), lua='Lupa Lua 5.4'),
                  seeds=args.seeds, stress_seconds=args.stress_seconds, sources_unchanged_during_run=unchanged,
                  source_sha256=sources, results=results, deterministic_replay=replay,
                  limitations=['局部场景显式布置现有实体位置，或通过真实死亡入口安排残骸；不证明自然游玩必然出现该情境。',
                               '测试入口获得机制卡，不证明正式六轮卡池的可获得性。',
                               '脚本化压力模拟验证稳定性和解锁门槛，不证明胜率、平衡或涌现体验。',
                               '原生输入、渲染、音频、FPS、界面可发现性和玩家验收仍未验证。'])
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    rows = ['# AI 非实机验收结果', '', f"整体结果：{'通过' if passed else '未通过'}。执行时间：{report['generated_at']}。", '',
            '采用当前正式 v5 地图（120×144，960 细胞）、真实 Lua 5.4 Core 模块与默认 AI 参数。', '',
            '| 地图种子 | 场景 | 结果 | 模拟秒数 |', '| --- | --- | --- | --- |']
    for r in results:
        seconds=r.get('simulated_seconds')
        rows.append(f"| {r['seed']} | {r['case']} | {r['status']} | {round(seconds, 3) if seconds is not None else '—'} |")
    rows += ['', '| 种子 | 活跃传播模拟 | 感染细胞 | 实际释放 | 实际清除 | 免疫数 |',
             '| --- | --- | --- | --- | --- | --- |']
    for r in results:
        if r['case']=='stress_active' and r['status']=='PASS':
            s=r['stats']
            rows.append(f"| {r['seed']} | {round(r['simulated_seconds'], 3)}秒 | {s['infected']} | {s['released']} | {s['killed']} | {s['initial_immunes']}→{s['final_immunes']} |")
    rows += ['', f"同种子重复模拟：{'通过' if replay and replay['passed'] else '未运行或未通过'}。",
             f"执行期间源码指纹保持一致：{unchanged}。", '', '详细断言、事件数据、配置来源和源码 SHA-256 见 checks.json。', '',
             'Base 为无卡基础免疫边界；Camouflage 为残骸清理和卡牌掩护；Commands 为留守失效、危险、解锁门槛与接管；stress_base/stress_cards 为无初始卡/指定初始卡的空闲稳定性模拟，stress_active 为至少 120 秒的实际传播模拟。', '',
             '## 证据边界', ''] + ['- '+s for s in report['limitations']]
    (args.output / 'report.md').write_text('\n'.join(rows)+'\n', encoding='utf-8')
    print(f"{'PASS' if passed else 'FAIL'}: {len(results)} scenarios; report={args.output / 'report.md'}", flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
