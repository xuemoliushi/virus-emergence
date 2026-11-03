# R02 免疫细胞 Agent 化

**日期：** 2026-10-04  
**类型：** 机制性修改  
**状态：** 已构建通过

---

## 目标

把"免疫压力"从区域级单一数值，拆解为可观察的巨噬细胞和 T 细胞个体，让免疫响应由局部信号驱动，涌现出饱和、疲劳、误伤、识别失效等故事。保留聚合 immune 值作为性能兜底。

---

## 实现内容

### 1. Config.ImmuneAgents（Config.lua）

新增配置块，分别定义巨噬细胞和 T 细胞的行为参数：

| 参数 | 作用 |
|------|------|
| `macro.capacity` | 巨噬细胞最大吞噬负载 |
| `macro.phagocyteRate` | 每秒吞噬病毒量（受疲劳乘） |
| `macro.fatigueRate/Recov` | 吞噬积累/恢复疲劳速率 |
| `macro.inflamRelease` | 每单位吞噬释放的炎症量 |
| `tcell.killBase` | T 细胞基础杀伤效率（受识别度 × 疲劳乘） |
| `tcell.recruitDelay` | T 细胞首次招募等待秒数（形成感染波与免疫波的时间差） |
| `tcell.misfireThresh/Chance` | 炎症超阈时误伤触发阈值和基础概率 |
| `maxPerRegion` | 单区域两类 agent 合计上限（性能控制） |
| `recruitInflamThresh` | 招募触发炎症阈值 |

### 2. SimState.TickImmuneAgents（SimState.lua）

新增方法，每 tick 对每个区域执行：

**招募逻辑**
- 炎症超阈先招募巨噬，T 细胞需感染细胞 > 3 且等待 `recruitDelay` 秒
- T 细胞在招募时记录当前主导隐匿表型值（`trainedSte`）作为识别基准
- 炎症长期偏低时，agent 自然退场

**巨噬细胞行为**
- 每 tick 从区域 virus 中吞噬一定量，更新 `load` 和 `fatigue`
- 负载达 90% 容量时进入 `saturated` 状态，停止有效吞噬，持续释放额外炎症，负载缓慢消化
- 状态：`patrol` / `phagocyte` / `saturated`

**T 细胞行为**
- 识别度 = `1 - |domSte - trainedSte| × recognitionSensitivity`，病毒隐匿表型漂移后下降
- 杀伤效率 = `killBase × recognition × fatigMul`，结果直接修改 `r.infected / r.dead`
- 炎症超过 `misfireThresh` 时，每 tick 概率性误伤健康细胞（`r.susceptible` 减 1，`r.damage` 增 0.8）
- 识别率低于 0.45 且首次触发时，向 Ticker 推送逃逸事件
- 状态：`patrol` / `kill` / `misfire`

在 `Tick()` 第3步循环末尾加入调用：
```
self:TickImmuneAgents(r)
```

### 3. CellView.SyncWithRegion（CellView.lua）

原来根据 `region.immune` 数值阈值生成固定数量的 macrophage/tcell 视图对象，替换为从 `region.immuneAgents` 读取真实 agent 列表：

- 增/减视图 agent 时保留已有对象的位置和动画状态
- 每帧把后台 `simState` 引用写入视图 `im.simState`，供绘制读取 `fatigue/state/load`

### 4. CellView.DrawImmune（CellView.lua）

根据后台 agent 状态改变视觉表现：

| 后台状态 | 视觉效果 |
|----------|----------|
| `patrol` | 正常冷青色，标准亮度 |
| `phagocyte` | 正常冷青色，略亮脉冲 |
| `saturated` | 暗橙色，体积增大 25%，核心画深色"撑满"圆，冷光减弱 |
| `misfire` | 鲜红色，快速脉冲红色光晕（8Hz） |
| 高 fatigue | 颜色整体压暗（最多 60%），伪足幅度缩小，体积略缩 |
| T 细胞识别失效（`escapeFlagged`） | 核心变红色 |

---

## 涌现回路

1. **免疫风暴路径**：病毒浓度高 → 巨噬饱和 → 炎症升高 → T 细胞大量进入 → 误伤健康细胞 → 组织损伤失控
2. **免疫逃逸路径**：病毒突变提高隐匿 → T 细胞识别度下降 → 杀伤效率降低 → 感染反弹 + Ticker 推送逃逸事件
3. **免疫疲劳路径**：T 细胞持续高活性 → 疲劳积累 → 杀伤效率下降 → 病毒低谷后复燃

---

## 性能约束

- 单区域 agent 总数上限 `maxPerRegion = 8`（Config 可调）
- TickImmuneAgents 只读取当前区域局部状态，不做全局遍历
- 聚合 immune 值不变，依然参与 TickRegion 的清除计算（兜底）
