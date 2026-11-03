"""Lua 5.4 协议与绘制调用回归，不冒充引擎实际像素截图验收。

运行：PYTHONDONTWRITEBYTECODE=1 python3 -B /workspace/tests/latent_particles_regression.py
仅使用已核准元数据和三张原始精灵，不生成测试产物。
"""
from collections import Counter
from copy import deepcopy
import json
import math
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, "/home/Maker/.local/swarm-test")
from lua_test_runtime import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
SOURCE_META = ROOT / "docs/latent_particles_meta.json"
ASSET_META = ROOT / "assets/image/latent_particles_meta.json"
META = json.loads(SOURCE_META.read_bytes())

SETUP = r"""
package.path = SCRIPT_PATH .. ';' .. package.path
calls, created, deleted, logs, filePaths = {}, {}, {}, {}, {}
fileReads, fileDisposes, decodes = 0, 0, 0
failedPath, failKind, fileMode = '', '', ''
NVG_IMAGE_NEAREST = 1 << 5
NVG_SOURCE_OVER = 0
renderState = {a=1,b=0,c=0,d=1,e=0,f=0,aa=1,composite=8}
local stack, nextId = {}, 100
local function record(name, ...)
    local call = {name, ...}; calls[#calls+1] = call; return call
end
local function copy(t)
    local out = {}; for k,v in pairs(t) do out[k] = v end; return out
end
function print(...) logs[#logs+1] = table.concat({...}, ' ') end
function nvgCreateImage(ctx, path, flags)
    local handle = nextId; nextId = nextId+1
    created[#created+1] = {ctx,path,flags,handle}
    if failedPath == '*' or path == failedPath then
        if failKind == 'throw' then error('图片加载被拒绝') end
        if failKind == 'nil' then return nil end
        if failKind == 'zero' then return 0 end
        if failKind == 'negative' then return -1 end
    end
    return handle
end
function nvgImageSize(ctx, handle)
    for _,item in ipairs(created) do
        if item[4] == handle and (failedPath == '*' or item[2] == failedPath) then
            if failKind == 'size-throw' then error('图片尺寸查询被拒绝') end
            if failKind == 'size' then return 32,32 end
        end
    end
    return 50,50
end
function nvgDeleteImage(ctx, handle) deleted[#deleted+1] = {ctx,handle} end
function nvgSave(ctx) stack[#stack+1] = copy(renderState); record('save',ctx) end
function nvgRestore(ctx)
    renderState = assert(stack[#stack]); stack[#stack] = nil; record('restore',ctx)
end
function nvgTranslate(ctx, x, y)
    renderState.e = renderState.e + renderState.a*x + renderState.c*y
    renderState.f = renderState.f + renderState.b*x + renderState.d*y
end
function nvgRotate(ctx, angle)
    local co,si = math.cos(angle),math.sin(angle)
    local a,b,c,d = renderState.a,renderState.b,renderState.c,renderState.d
    renderState.a,renderState.b = a*co+c*si,b*co+d*si
    renderState.c,renderState.d = c*co-a*si,d*co-b*si
end
function nvgScale(ctx, x, y)
    renderState.a,renderState.b = renderState.a*x,renderState.b*x
    renderState.c,renderState.d = renderState.c*y,renderState.d*y
end
function nvgShapeAntiAlias(ctx, enabled) renderState.aa=enabled;record('aa',ctx,enabled) end
function nvgGlobalCompositeOperation(ctx, op) renderState.composite=op;record('composite',ctx,op) end
function nvgImagePattern(ctx, x, y, w, h, angle, handle, alpha)
    local paint = {x=x,y=y,w=w,h=h,angle=angle,handle=handle,alpha=alpha,
        transform=copy(renderState)}
    record('paint',ctx,paint); return paint
end
function nvgBeginPath(ctx) record('begin',ctx) end
function nvgRect(ctx, x, y, w, h) record('rect',ctx,x,y,w,h) end
function nvgFillPaint(ctx, paint) record('fillPaint',ctx,paint) end
function nvgFill(ctx) record('fill',ctx) end
for _,name in ipairs({'nvgCreate','nvgDelete','nvgBeginFrame','nvgEndFrame','nvgSetBloomEnabled',
    'nvgImagePatternTinted','nvgGlobalAlpha','nvgReset','nvgResetTransform','nvgCircle',
    'nvgRadialGradient','nvgGlobalCompositeBlendFunc','nvgGlobalCompositeBlendFuncSeparate'}) do
    _G[name] = function() error('禁止渲染副作用：'..name) end
end
-- 禁止通过共享图片缓存或 VisualUtils 悄悄退回线性过滤。
package.preload['urhox-libs/UI/Core/ImageCache'] = function() error('不应访问共享图片缓存') end
package.preload['Game.VisualUtils'] = function() error('不应访问采用默认过滤方式的 VisualUtils') end
cache = {}
function cache:GetFile(path)
    fileReads=fileReads+1;filePaths[#filePaths+1]=path
    if fileMode == 'missing' then return nil end
    assert(path == 'image/latent_particles_meta.json', '元数据必须使用已打包的资源路径')
    local lines = {}; for line in (META_TEXT..'\n'):gmatch('(.-)\n') do lines[#lines+1]=line end
    local file = {at=1}
    function file:IsEof() return self.at>#lines end
    function file:ReadLine()
        if fileMode == 'read-error' then error('文件读取被拒绝') end
        local line=lines[self.at];self.at=self.at+1;return line
    end
    function file:Dispose() fileDisposes=fileDisposes+1 end
    return file
end
cjson = {}
function cjson.decode(text) decodes=decodes+1;return DECODE(text) end
Particles = require('Game.Views.LatentParticles')
function clearCalls() calls={} end
function recorded(name)
    local out={};for _,call in ipairs(calls) do if call[1]==name then out[#out+1]=call end end
    return out
end
"""


def to_lua(lua, value):
    if isinstance(value, dict):
        return lua.table_from({k: to_lua(lua, v) for k, v in value.items()})
    if isinstance(value, list):
        return lua.table_from([to_lua(lua, v) for v in value])
    return value


def to_python(value):
    if hasattr(value, "items"):
        return {k: to_python(v) for k, v in value.items()}
    return value


class Harness:
    def __init__(self, meta=None):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.g = self.lua.globals()
        self.g.SCRIPT_PATH = str(ROOT / "scripts/?.lua")
        self.g.META_TEXT = ASSET_META.read_text(encoding="utf-8")
        self.g.DECODE = lambda text: to_lua(self.lua, json.loads(text))
        self.lua.execute(SETUP)
        self.meta = to_lua(self.lua, META if meta is None else meta)

    def new(self, injected=True):
        options = self.lua.table_from({"meta": self.meta}) if injected else None
        return self.g.Particles.New(options)

    def cell(self, **changes):
        data = {"state": "LATENT", "infectedVisualAt": 10, "id": 9, "phase": 987,
                "x": 4, "y": 3, "rotation": 0.7, "radius": 0.4, "exposure": 1,
                "infectedAge": 333, "mass": 16, "contactVisuals": [{"strength": 0.3}]}
        data.update(changes)
        return to_lua(self.lua, data)

    def draw(self, instance, cell=None, time=10, alpha=None, ctx="ctx-A"):
        self.g.clearCalls()
        result = instance.Draw(instance, ctx, cell if cell is not None else self.cell(), time, alpha)
        return result, [to_python(call[3]) for call in self.g.recorded("paint").values()]


class LatentParticlesRegression(unittest.TestCase):
    def test_packaged_metadata_is_byte_exact_and_approved_spacing_retained(self):
        self.assertEqual(SOURCE_META.read_bytes(), ASSET_META.read_bytes())
        self.assertEqual(META["min_centre_dist_px"], 54.8)
        self.assertEqual(len(META["particles"]), 14)
        distance = min(math.dist(a["centre"], b["centre"])
                       for i, a in enumerate(META["particles"]) for b in META["particles"][i+1:])
        self.assertAlmostEqual(distance, 54.817880294662984)
        self.assertLess(distance, META["placement"]["min_spacing_px"])
        for tier, filename in META["sprites"].items():
            png = (ROOT / "assets/image" / filename).read_bytes()
            self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", png[16:24]), (50, 50), tier)

    def test_count_tier_centres_size_nearest_original_rgb(self):
        h = Harness(); view = h.new()
        result, paints = h.draw(view)
        self.assertTrue(result)
        self.assertEqual(len(paints), 14)
        by_handle = {item[4]: item[2] for item in h.g.created.values()}
        counts = Counter()
        for particle, paint in zip(META["particles"], paints):
            self.assertEqual(by_handle[paint["handle"]], "image/"+particle["sprite"])
            self.assertEqual((paint["x"]+25, paint["y"]+25),
                             tuple(c-627 for c in particle["centre"]))
            self.assertEqual((paint["w"], paint["h"], paint["angle"]), (50, 50, 0))
            self.assertEqual(paint["transform"]["aa"], 0)
            self.assertEqual(paint["transform"]["composite"], h.g.NVG_SOURCE_OVER)
            counts[particle["tier"]] += 1
        self.assertEqual(dict(counts), {"dim": 11, "normal": 2, "bright": 1})
        self.assertEqual(len(h.g.created), 3)
        self.assertTrue(all(item[3] == h.g.NVG_IMAGE_NEAREST for item in h.g.created.values()))
        self.assertEqual(len(h.g.recorded("rect")), 14)
        self.assertEqual(len(h.g.recorded("fill")), 14)
        self.assertFalse(len(h.g.logs))

    def test_formula_phase_period_and_independent_pulses(self):
        h = Harness(); view = h.new(); cell = h.cell()
        for elapsed in (0, 0.17, 1, 2.6, 7.51, 73):
            _, paints = h.draw(view, cell, 10+elapsed)
            for particle, paint in zip(META["particles"], paints):
                p = particle["pulse"]
                expected = p["alpha_min"]+(META["pulse"]["alpha_range"][1]-p["alpha_min"])*(
                    0.5+0.5*math.sin(elapsed*math.tau/p["period_s"]+p["phase"]))
                self.assertAlmostEqual(paint["alpha"], expected, places=12)
            self.assertGreater(max(p["alpha"] for p in paints)-min(p["alpha"] for p in paints), 0.08)
        for i, particle in enumerate(META["particles"]):
            p = particle["pulse"]
            for angle, expected in ((math.pi/2, 1), (3*math.pi/2, 0.55)):
                elapsed = ((angle-p["phase"]) % math.tau)*p["period_s"]/math.tau
                _, paints = h.draw(view, cell, 10+elapsed)
                self.assertAlmostEqual(paints[i]["alpha"], expected, places=12)
                self.assertTrue(all(0.55 <= paint["alpha"] <= 1 for paint in paints))
            _, first = h.draw(view, cell, 10.29)
            _, after = h.draw(view, cell, 10.29+p["period_s"])
            self.assertAlmostEqual(first[i]["alpha"], after[i]["alpha"], places=12)
            self.assertTrue(any(abs(a["alpha"]-b["alpha"]) > 0.01 for j, (a, b)
                                in enumerate(zip(first, after)) if j != i))
        self.assertEqual(len(h.g.created), 3)

    def test_injected_json_alpha_bounds_not_hardcoded(self):
        meta = deepcopy(META)
        meta["pulse"]["alpha_range"] = [0.7, 0.88]
        for particle in meta["particles"]: particle["pulse"]["alpha_min"] = 0.73
        h = Harness(meta); view = h.new()
        _, paints = h.draw(view, time=11.23)
        for particle, paint in zip(meta["particles"], paints):
            p = particle["pulse"]
            expected = 0.73+0.15*(0.5+0.5*math.sin(1.23*math.tau/p["period_s"]+p["phase"]))
            self.assertAlmostEqual(paint["alpha"], expected, places=12)
        self.assertEqual(h.g.fileReads, 0)

    def test_latent_and_productive_only(self):
        h = Harness(); view = h.new()
        for state in ("HEALTHY", "EXPOSED", "EXHAUSTED", "DEAD", "latent", None):
            result, paints = h.draw(view, h.cell(state=state))
            self.assertFalse(result); self.assertEqual(paints, []); self.assertEqual(len(h.g.calls), 0)
        self.assertEqual(len(h.g.created), 0)
        self.assertFalse(view.Draw(view, "ctx-A", None, 10))
        self.assertFalse(view.Draw(view, None, h.cell(), 10))
        self.assertTrue(h.draw(view)[0])
        for state in ("EXHAUSTED", "DEAD"):
            self.assertEqual(h.draw(view, h.cell(state=state))[1], [])
        latent = h.draw(view, h.cell(state="LATENT"), 11.2)[1]
        productive = h.draw(view, h.cell(state="PRODUCTIVE"), 11.2)[1]
        self.assertEqual(latent, productive)
        self.assertEqual(len(productive), 14)

    def test_pause_anchor_and_no_cell_or_metadata_mutations(self):
        h = Harness(); view = h.new(); cell = h.cell()
        before, meta_before = to_python(cell), to_python(h.meta)
        _, first = h.draw(view, cell, 11.75)
        for _ in range(8): self.assertEqual(h.draw(view, cell, 11.75)[1], first)
        _, shifted = h.draw(view, h.cell(infectedVisualAt=1010), 1011.75)
        self.assertEqual(first, shifted)
        # 未来的时间戳限制到进入时的相位，不允许时钟倒放。
        self.assertEqual(h.draw(view, cell, 9)[1], h.draw(view, cell, 10)[1])
        # 其他玩法或视觉时钟不得替代权威的潜伏进入时间戳。
        _, altered = h.draw(view, h.cell(phase=-123, infectedAge=99, exposure=0, id=88), 11.75)
        self.assertEqual(first, altered)
        self.assertEqual(to_python(cell), before)
        self.assertEqual(to_python(h.meta), meta_before)
        self.assertEqual(h.g.fileReads, 0)
        self.assertEqual(len(h.g.created), 3)

    def test_parent_transform_and_render_state_preserved(self):
        h = Harness(); view = h.new(); ctx = "ctx-A"
        h.g.nvgTranslate(ctx, 431, 327); h.g.nvgRotate(ctx, 0.7); h.g.nvgScale(ctx, 0.18, 0.18)
        before = to_python(h.g.renderState)
        _, paints = h.draw(view, h.cell(x=999, y=-999, rotation=-34))
        self.assertEqual(to_python(h.g.renderState), before)
        for particle, paint in zip(META["particles"], paints):
            t = paint["transform"]
            self.assertEqual({k: t[k] for k in "abcdef"}, {k: before[k] for k in "abcdef"})
            x, y = particle["centre"][0]-627, particle["centre"][1]-627
            sx = t["a"]*(paint["x"]+25)+t["c"]*(paint["y"]+25)+t["e"]
            sy = t["b"]*(paint["x"]+25)+t["d"]*(paint["y"]+25)+t["f"]
            self.assertAlmostEqual(sx, 431+0.18*(math.cos(0.7)*x-math.sin(0.7)*y))
            self.assertAlmostEqual(sy, 327+0.18*(math.sin(0.7)*x+math.cos(0.7)*y))
        self.assertEqual(len(h.g.recorded("save")), 1)
        self.assertEqual(len(h.g.recorded("restore")), 1)

    def test_optional_opacity_and_invalid_inputs(self):
        h = Harness(); view = h.new()
        _, base = h.draw(view)
        for alpha, multiplier in ((0.4, 0.4), (1, 1), (2, 1)):
            _, paints = h.draw(view, alpha=alpha)
            for original, paint in zip(base, paints):
                self.assertAlmostEqual(paint["alpha"], original["alpha"]*multiplier)
        for alpha in (0, -1, math.nan, math.inf):
            self.assertFalse(h.draw(view, alpha=alpha)[0]); self.assertEqual(len(h.g.calls), 0)
        for time in (math.nan, math.inf, -math.inf, None):
            self.assertFalse(h.draw(view, time=time)[0]); self.assertEqual(len(h.g.calls), 0)
        self.assertFalse(h.draw(view, h.cell(infectedVisualAt=math.nan))[0])
        # 兼容旧细胞缺少时间戳的情况，不向细胞写入补造时间戳。
        legacy = h.cell(infectedVisualAt=None)
        _, paints = h.draw(view, legacy, 0)
        self.assertEqual(paints, base); self.assertIsNone(legacy.infectedVisualAt)

    def test_packaged_json_loaded_once_disposed_and_reused(self):
        h = Harness(); view = h.new(injected=False)
        self.assertTrue(view.valid)
        self.assertEqual((h.g.fileReads, h.g.fileDisposes, h.g.decodes), (1, 1, 1))
        for _ in range(5):
            self.assertTrue(view.Init(view)); self.assertTrue(h.draw(view)[0])
        self.assertEqual(len(h.g.created), 3)
        view.Destroy(view)
        self.assertTrue(h.draw(view)[0])
        self.assertEqual((h.g.fileReads, h.g.fileDisposes, h.g.decodes), (1, 1, 1))
        self.assertEqual(len(h.g.created), 6)
        self.assertEqual(list(h.g.filePaths.values()), ["image/latent_particles_meta.json"])

    def test_destroy_idempotent_auto_reopen_and_private_context_handles(self):
        h = Harness(); view = h.new()
        view.Destroy(view); view.Destroy(view)
        self.assertEqual(len(h.g.deleted), 0)
        _, first = h.draw(view, time=11.5)
        first_handles = {p["handle"] for p in first}
        view.Destroy(view); view.Destroy(view)
        self.assertEqual({item[2] for item in h.g.deleted.values()}, first_handles)
        self.assertEqual(len(h.g.deleted), 3)
        self.assertFalse(view.nvg)
        self.assertEqual(h.draw(view, h.cell(state="HEALTHY"))[1], [])
        self.assertEqual(len(h.g.created), 3)
        _, reopened = h.draw(view, time=11.5)
        self.assertEqual(len(h.g.created), 6)
        self.assertTrue(first_handles.isdisjoint({p["handle"] for p in reopened}))
        self.assertEqual([p["alpha"] for p in first], [p["alpha"] for p in reopened])
        _, changed = h.draw(view, time=11.5, ctx="ctx-B")
        self.assertEqual(len(h.g.created), 9)
        self.assertEqual(len(h.g.deleted), 6)
        self.assertTrue(all(item[1]=="ctx-A" for item in h.g.deleted.values()))
        self.assertEqual([p["alpha"] for p in reopened], [p["alpha"] for p in changed])
        self.assertTrue(all(item[1]=="ctx-B" for item in list(h.g.created.values())[-3:]))
        view.Destroy(view)
        self.assertEqual(len(h.g.deleted), 9)
        self.assertTrue(all(item[1]=="ctx-B" for item in list(h.g.deleted.values())[-3:]))

    def test_instances_never_delete_another_views_images(self):
        h = Harness(); first = h.new(); second = h.new()
        _, a = h.draw(first); _, b = h.draw(second)
        first_handles, second_handles = {p["handle"] for p in a}, {p["handle"] for p in b}
        self.assertTrue(first_handles.isdisjoint(second_handles))
        first.Destroy(first)
        self.assertEqual({item[2] for item in h.g.deleted.values()}, first_handles)
        self.assertEqual(h.draw(second)[1], b)
        self.assertEqual(len(h.g.created), 6)

    def test_sprite_failures_cached_no_fake_fallback_once_per_resource(self):
        for mode in ("zero", "negative", "nil", "throw", "size", "size-throw"):
            with self.subTest(mode=mode):
                h = Harness(); h.g.failedPath = "image/latent_particle_bright.png"; h.g.failKind = mode
                view = h.new(); cell = h.cell(); before = to_python(cell)
                for _ in range(5):
                    result, paints = h.draw(view, cell)
                    self.assertTrue(result); self.assertEqual(len(paints), 13)
                self.assertEqual(len(h.g.created), 3); self.assertEqual(len(h.g.logs), 1)
                self.assertEqual(to_python(cell), before)
                self.assertEqual(len(h.g.deleted), 1 if mode.startswith("size") else 0)
                view.Destroy(view)
                self.assertEqual(len(h.g.deleted), 3 if mode.startswith("size") else 2)
                # 同一实例清理后重开可重试，但同一失败不得重复打印日志。
                self.assertTrue(h.draw(view)[0]); self.assertEqual(len(h.g.logs), 1)
                self.assertEqual(len(h.g.created), 6)

    def test_all_sprite_failures_draw_nothing_and_destroy_safely(self):
        h = Harness(); h.g.failedPath = "*"; h.g.failKind = "negative"; view = h.new()
        for _ in range(4):
            result, paints = h.draw(view); self.assertFalse(result); self.assertEqual(paints, [])
        self.assertEqual(len(h.g.created), 3); self.assertEqual(len(h.g.logs), 3)
        self.assertEqual(len(h.g.recorded("fill")), 0)
        view.Destroy(view); view.Destroy(view)
        self.assertEqual(len(h.g.deleted), 0)

    def test_metadata_failures_fail_closed_once_and_dispose_owned_file(self):
        for mode in ("missing", "read-error", "decode-error"):
            with self.subTest(mode=mode):
                h = Harness(); h.g.fileMode = mode
                if mode == "decode-error": h.g.META_TEXT = "{broken"
                view = h.new(injected=False)
                for _ in range(4):
                    self.assertFalse(view.Init(view)); self.assertFalse(h.draw(view)[0])
                view.Destroy(view); self.assertFalse(h.draw(view)[0])
                self.assertEqual(len(h.g.logs), 1); self.assertEqual(len(h.g.created), 0)
                self.assertEqual(h.g.fileReads, 1)
                self.assertEqual(h.g.fileDisposes, 0 if mode == "missing" else 1)
        for mutate in (lambda meta: meta.update(count=15),
                       lambda meta: meta.update(sprite_canvas_px=32),
                       lambda meta: meta["particles"][0]["pulse"].update(period_s=0),
                       lambda meta: meta["particles"][0].update(tier="virus")):
            meta = deepcopy(META); mutate(meta)
            h = Harness(meta); view = h.new()
            self.assertFalse(h.draw(view)[0]); self.assertFalse(view.valid)
            self.assertEqual(len(h.g.created), 0); self.assertEqual(len(h.g.logs), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
