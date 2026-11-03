# Claude 接手指引

交接快照：2026-10-19（Asia/Shanghai）。本文是导航与状态快照，不替代用户后续指令、AGENTS.md 或当前源码。

## 1. 本轮已完成与 Git 状态

- 工作目录：`C:\Users\q3382\Documents\Codex\2026-10-12\https-xd-feishu-cn-wiki-knwqwr2wyiwmolkdomtcekxrnof\work\taptap-project`。
- 这是已绑定的 TapTap Maker 工程，继续使用原目录、绑定和 origin，不要 init、重新 clone 或修改 remote。
- 已执行 `git fetch origin main`，再执行 `git merge --ff-only origin/main`，从 `5934880` 快进至 `dc6b0d92a7bf7a55098df7e5e297078fb2fbbb2d`。核对 `HEAD...origin/main` 为 `0 0`，只代表本次 fetch 时的远端。
- 新增 4 个提交：`3af0e94`、`b0a3d6c`、`bb94b0a`、`dc6b0d9`。共更新 10 个文件：项目配置、视频缓存及其 meta、7 张 `_uploads/` 图片；未修改玩法脚本。
- 同步前没有已跟踪文件的本地修改，但有大量未跟踪的 `validation/` 证据、补丁、基线和少量 `tests/__pycache__/` 文件。均保留原位，不应自动删除或一并提交。
- 本轮新增本交接文档，并在根目录 CLAUDE.md 添加入口；均未提交。未推送、未远端构建、未启动预览。
- 不输出原始 remote URL：其中可能含凭据。交接文件、报告、截图和日志必须脱敏。

## 2. 接手第一步

1. 完整阅读根目录 `AGENTS.md`，不要只看本摘要。根目录 `CLAUDE.md` 已引用它。
2. 用 `git status --short --branch`、`git log -8 --oneline` 核对现场。本文记载的是快照，后续协作者可能继续更新。
3. 调用 `maker://status`，不可用时调用 `maker_status_lite`，显式传入同一个项目 `target_dir`。本次返回 bound、project_health ready、Maker 0.0.37。
4. 先向用户确认下一项具体开发目标；本次授权仅为同步 main 和准备交接，不包含继续改玩法、清理资源或发布。
5. 开发前按 AGENTS.md 阅读 `engine-docs/lua-scripting-guide.md`，从 `examples/api-index.md` 找至少 3 个相关示例。涉及 raw NanoVG 时读取 `skills/nvg-resolution-mode/SKILL.md`。引擎库 `urhox-libs/` 只读。

## 3. 项目结构与阅读顺序

本项目是 2D 俯视病毒群体涌现游戏。玩家策略影响病毒分布、细胞感染、免疫响应和组织病理，不是科研预测系统。

| 内容 | 入口 |
| --- | --- |
| 游戏入口与更新流程 | `scripts/main.lua` |
| 参数、权威世界状态与阶段进展 | `scripts/Core/Config.lua`、`SimState.lua`、`EvolutionTracker.lua` |
| 免疫行为与调度 | `scripts/Core/ImmuneSystem.lua`、`ImmuneDirector.lua`、`ImmuneNavigation.lua` |
| 群体与感染接力 | `scripts/Core/SwarmWorld.lua`、`SwarmParticles.lua`、`InfectionRelay.lua` |
| 地图 | `scripts/Core/FlatWorldMap.lua`、`RespiratoryMap.lua` |
| 教程与音频 | `scripts/Core/Tutorial.lua`、`TutorialVoice.lua`、`GameAudio.lua`、`GameplaySounds.lua`、`WorldAudioEvents.lua` |
| 界面和实际文件定位 | 在 `scripts/` 用 rg 查找 HUD、菜单、选卡等；不要假定存在 Systems 目录 |
| 设计资料 | `docs/玩法新.md`、`docs/玩法文档.md`；结合最新专项文档和源码判断，不把全部历史方案当现行规则 |
| 自动化与历史证据 | `tests/`、`validation/`；历史报告不等于当前提交已重新通过 |

优先阅读 `docs/六阶段达成条件.md`、`docs/六阶段进化接入说明.md`、`docs/机制卡牌接入说明.md`、`docs/新手教程接入说明.md`。UI、音效、免疫、性能等任务再按需阅读同名专项说明。

## 4. 最近玩法变更，避免回退

当前同步前的最新玩法提交为 `5934880`，现行阶段条件详见 `docs/六阶段达成条件.md`：

- 阶段 1—4 逐步检查新建运行节点、产出、跨区网络及持续 30 秒；运行节点限 LATENT/PRODUCTIVE。
- 阶段 5：进入阶段后累计破坏 6 个细胞，或本阶段新释放且当前存活的游离病毒 40 只，任选一条。不要改回阶段 4 的节点规模要求。
- 阶段 6：整局累计成功感染至少 16 个、本阶段新增至少 4 个，再维持炎症或损伤不可逆阈值的 70% 达 20 秒。
- 确认第六张卡后恢复操控，另需新增至少 4 次成功感染并满足终局不可逆条件，不能立即结局或发第七张卡。累计感染不等于当前存活节点数。
- 上述数值仍待自然玩家流程与实机平衡验收。固定夹具通关不能证明自然局长、难度或原生 HUD 布局。

近期提交还包括教程每局接入与长按 Esc 跳过、左下操作区安全区适配、感染接力/多卡查询/群体性能优化，以及旧贴图清理。遇到历史素材引用先做资源审计，不要恢复已退役资源来掩盖引用错误。

## 5. 验证与本地预览

本轮只做同步与文档整理，没有运行玩法回归；不要把历史通过数量写成本轮结果。按改动范围选择测试，例如：

```powershell
python -B tests/stage_progression_regression.py
python -B tests/evolution_regression.py
python -B tests/card_runtime_regression.py
python -B tests/gameplay_sounds_regression.py
python -B tests/chase_music_regression.py
git diff --check
```

先检查 Python 与依赖，不要直接全局安装。相关测试通过 `tests/lua_test_runtime.py` 使用 `lupa.lua54` 运行 Lua，并处理 Windows 中文路径。出现 import 错误应先核对解释器与依赖，不能当游戏运行错误。

本轮通过已安装 Maker CLI 的 `preview status --target-dir <项目绝对路径> --json` 确认：`state=stopped`、`process_alive=false`；保持停止。状态保留旧会话的 `Cube/Day/DaySpecularHDR.dds` 和 `themis_x64.dll` 缺失错误，不能据此认定本次新启动失败，也不能声称已解决。

用户明确要求本地试玩时，可使用 `启动游戏.cmd` / `start-game.ps1`；该启动器会尝试启动停止的会话，不要拿它做纯状态查询。详见 `本地试玩说明.md` 和 `docs/本地启动器修复.md`。它已有 Git 查找、子进程覆盖、隔离 Python 与 CDN IPv4 优先处理，不要改系统 PATH 或共享引擎文件。

每批相关代码/资源变更后检查预览状态：仅 process_alive=true 时刷新，再取日志/check；停止的会话不自动复活。刷新会丢失内存进度。自动化逻辑通过、原生画面、触控、音频、帧率、长时运行与玩家验收分别报告。

## 6. Maker 与共享工程边界

- 普通检查、测试、文档工作不触发远端构建。用户明确要求提交/推送/构建/远端 Web 预览时，先 status，再用 `maker_build_current_directory`，不以普通 git push 替代。
- 协作者 main 有更新时，提交前先 fetch、检查并整合，保留新资源和未被替代的本地行为。若有分叉、脏文件或冲突，先保存可恢复副本再处理，不 reset --hard 或 clean。
- 超时代表结果未确认；保留本地提交，核对远端同步和构建状态，不重复宣称成功。
- 不改 Maker 服务环境，不迁移绑定，不复制 Codex MCP 配置到 Claude。若 Claude 没有 Maker 工具，依据 AGENTS.md 从 Claude 自己的配置和启动日志诊断，不拿 Codex 的连接状态证明 Claude 已连接。
- 新资源保留映射文档、原始文件名和官方 meta/UUID；禁止凭文件名猜素材用途或自行编造 UUID。音效的逻辑调用不等于本机听感已验收。

## 7. 可直接粘贴给 Claude 的接手消息

> 请接手当前目录的 TapTap Maker 工程。先完整阅读 AGENTS.md 与 docs/Claude交接指引.md，检查 Git 和 Maker 实时状态。2026-10-19 已将 main 从 5934880 快进到 dc6b0d9，本地原有未跟踪验收材料均保留。本地预览当时停止；不要自动启动、提交、推送或构建，不要清理未跟踪文件。先简要报告你确认的当前状态和需要继续的工作，等待我给出下一项具体目标；开发前按 AGENTS.md 阅读指南与相关示例。
