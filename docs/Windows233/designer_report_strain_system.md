# 设计师报告：病毒表型谱系与简单突变机制

**日期：** 2026-10-04  
**模块范围：** Config / SimState / GameScene / TissueView / CellView / HUD  
**构建状态：** 通过

---

## 一、本次迭代目标

在已有的病毒扩散模型基础上，引入**表型谱系**（phenotype spectrum）与**毒株突变**（strain mutation）机制，使病毒在演化压力下产生可感知的行为变化；并通过**实时事件日志 Ticker** 与**表型历史曲线**让玩家能够观察到这些变化。

---

## 二、机制设计说明

### 2.1 毒株（Strain）数据结构

每个区域维护一个 `strains` 列表，每条毒株记录包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `attach` | number [0,1] | 附着效率表型值 |
| `replicate` | number [0,1] | 复制速度表型值 |
| `stealth` | number [0,1] | 免疫逃逸表型值 |
| `share` | number [0,1] | 该毒株在区域中的种群比例（归一化） |

### 2.2 表型乘数校准

初始值 `(attach=0.5, replicate=0.5, stealth=0.2)` 产出恰好 `1.0×` 的基线乘数，确保机制激活不破坏现有平衡：

```
attachMult    = lerp(0.5, 2.0, attach)       → 初始: 1.25×（偏高，故意留有演化空间）
replicateMult = lerp(0.4, 2.5, replicate)    → 初始: 1.45×
stealthMult   = lerp(1.0, 0.1, stealth)      → 初始: 0.86× （stealth越高，免疫越难识别）
```

### 2.3 突变逻辑（TickStrains）

每个游戏 Tick：
1. 按 `Config.StrainSystem.mutationRate` 概率对主导毒株进行轻微随机扰动
2. 叠加当前激活策略的 `strategyBias` 向量（四种策略各有不同偏向）
3. 新毒株若与已有株的表型距离 > `mergeThreshold`，则独立存入列表；否则合并
4. 按 `share` 归一化后记录主导表型用于下游计算

### 2.4 免疫逃逸（UpdateImmuneTraining）

- `immuneTarget`：训练目标表型（初始等于首帧主导表型）
- `recognition = 1 - dist(dominant, immuneTarget)`：识别率随表型漂移下降
- 当 `recognition < escapeThreshold`（0.55）时，触发逃逸事件并更新训练目标

### 2.5 毒株迁移（DiffuseVirus）

液体流动时，源区域的毒株按 `f.actual`（实际流量）比例迁移到目标区域，遵循同样的合并规则。

---

## 三、玩家感知度增强

### 3.1 实时事件日志 Ticker（右侧竖列）

**文件：** `GameScene.lua` → `DrawStrainOverlay()`

- 最多显示 6 条，按时间倒序（最新在上）
- 每条有彩色左边框（橙=逃逸 / 黄=警告 / 绿=普通），深色背景矩形
- 老化：8s 后开始淡出，12s 后完全隐藏
- **防刷屏机制**：`strainLogCooldowns` 表记录每个区域×每种事件类型的最后触发时间，相同 key 10s 内只触发一次

触发事件类型：

| 事件 | 触发条件 | 颜色 |
|------|----------|------|
| 新毒株出现 | 新株数超过上一 Tick | 绿 |
| 表型漂移 | 表型变化 > 0.08 per Tick | 黄/橙（>0.15时） |
| 免疫逃逸 | recognition 降至阈值以下 | 橙红 |
| 毒株迁移 | 毒株通过流体进入新区域 | 绿 |

### 3.2 表型历史曲线（悬停区域时显示）

**文件：** `GameScene.lua` → `DrawStrainOverlay()`（曲线部分）+ `SimState.lua`（采样）

- 每 2s 采样一次主导表型，最多保存 60 个点（约 120s 历史）
- 仅在**组织尺度**下、**鼠标悬停某区域时**弹出 160×90 px 面板
- 三条折线：附着(绿) / 复制(橙) / 隐匿(紫)，底部图例标注 `附/复/隐`
- 纵轴范围自动适配区间，横轴对齐时间序列

---

## 四、视觉更新

### 4.1 TissueView：进度条 + 悬停信息

- 区域标签下方增加 3 条 48×4px 进度条，映射附着/复制/隐匿表型值
- 悬停 tooltip 新增两行：
  - `"表型 附X% 复X% 隐X%  株N"` — 毒株数量概览
  - `"免疫识别率: X% ⚠逃逸"` — 识别率低于 60% 时高亮橙色

### 4.2 CellView：病毒色相偏移

- 主导 `attach` 偏高 → 病毒颗粒向绿黄色偏移
- 主导 `replicate` 偏高 → 向橙热色偏移（复用 `virusHot` 插值）
- 主导 `stealth` 偏高 → `stealthDim` 乘数压低，视觉更暗淡

### 4.3 HUD：策略栏下方状态行

- 实时显示主导表型百分比、当前毒株数、免疫识别率

---

## 五、数据流总览

```
Config.StrainSystem
   ↓ mutationRate / strategyBias / mergeThreshold
SimState.TickStrains()
   → NormalizeStrains() → DominantPhenotype()
   → PushStrainLog() → strainLog[]
   → UpdateImmuneTraining() → recognition
SimState.DiffuseVirus()
   → strain migration → PushStrainLog()
SimState.Tick() step 6
   → phenoHistory[region][t] 采样

GameScene.DrawStrainOverlay()
   → Ticker（读 strainLog）
   → 历史曲线（读 phenoHistory + TissueView.HitTestRegion）

TissueView.DrawRegion()   → 进度条 + tooltip 两行
CellView.DrawCell()        → virusTint 色相偏移
HUD.Update()              → 状态文本行
```

---

## 六、已知约束与后续建议

1. **Ticker 位置硬编码**：当前固定在 `w-160, 60` 处，若 HUD 重构需同步调整。
2. **曲线面板遮挡**：当区域靠近右边缘时面板会尝试向左偏移，但极端情况下仍可能与 Ticker 重叠，可后续加碰撞检测。
3. **毒株上限**：`Config.StrainSystem.maxStrains`（默认 8）控制单区域最多毒株数，超出时按 share 淘汰末位，避免内存增长。
4. **策略偏向反馈**：玩家当前只能通过 Ticker 看到漂移结果，建议后续在策略按钮旁增加箭头图标（↑附 / ↑复 / ↑隐）明确偏向方向。
