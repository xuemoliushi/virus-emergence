-- ============================================================================
-- Config.lua - 全局配置（配色 / 模拟参数 / 策略 / 美术挂载位登记）
-- 依据: docs/玩法文档.md + docs/美术风格规范.md
-- ⚠️ 所有模拟数值均为占位值，策划调数值时只改这里
-- ============================================================================

---@class GameConfig
---@field CardAbilities table
---@field EndingVideo table<string, string|boolean>
---@field EndingTransition {duration:number,hudHide:number,zoomEnd:number,zoom:number,videoStart:number,videoOffset:number,blend:number,audioFade:number,pulseFade:number,effectsFade:number}
---@field Bioluminescence {enabled:boolean,glowEnabled:boolean,emissionAtlas:string,glowAlpha:number,maxGlowDraws:number,denseGlowDraws:number,denseThreshold:number,minGlowPixels:number,minVirusGlowPixels:number}
local Config = {}

Config.Title = "病毒涌现 · 群体生存"

-- Scheduling affects wall-clock catch-up only, never simulation rules/quality.
Config.Performance = {
    maxStepsPerFrame = 2, simulationBudgetMs = 8, spatialGridSize = 1.5,
    hudRefreshSeconds = 0.12, surfaceTexturesPerFrame = 2,
    collectTimings = false, timingWindow = 600,
    cameraFollowRate = 18, renderSnapDistance = 0.5,
}

-- 细胞沙盒：单位为米，实体数量即画面数量；组织分区只保留在后台。
Config.Swarm = {
    worldWidth = 32, worldHeight = 24,
    cellsPerRegion = 100, initialVirus = 30, initialInfected = 1,
    seed = 314159,
    cellRadiusMin = 0.28, cellRadiusMax = 0.38, virusRadius = 0.045,
    infectionRadius = 0.24, infectionSeconds = 2.8, exposureDecay = 0.35,
    burstSeconds = 6, burstJitter = 1.2, burstVirus = 6,
    moveSpeed = 2.3, stealthMoveMul = 0.9,
    gatherRadius = 0.48, radiusGrowth = 0.018,
    formationResponse = 4, virusSpeed = 4.8, returnSpeed = 5.8,
    -- 扩散分出主群的一半，弹射后在释放点附近独立行动；不额外生成病毒。
    splitFraction = 0.5, splitCooldown = 1.2,
    splitLaunchSpeed = 7.5, splitLaunchSeconds = 0.45, splitLaunchDrag = 4,
    splitRoamRadius = 3.2, splitMoveSpeed = 1.15, splitFleeSpeed = 1.2,
    -- 有限感知与反应：免疫能追上分裂体，独立感染需要更长的安全停留。
    splitAvoidRadius = 0.65, splitThinkInterval = 0.45, splitReactionInterval = 0.45,
    splitInfectionSeconds = 4.2,
    stealthDetectRadius = 0.68, immuneDetectRadius = 4.2,
    immuneMainFraction = 0.5,
    immuneSpeed = 1.45, immuneRadius = 0.50, tcellRadius = 0.30,
    immuneAttackInterval = 0.8, immuneKillsPerAttack = 3,
    immuneRecruitInterval = 14, immuneMax = 12, initialImmune = 4,
}

-- ============================================================================
-- 1. 调色板（来自美术风格规范 §7 色彩角色）
-- ============================================================================
Config.Palette = {
    -- 组织背景: 近黑、深紫
    bgDeep        = { 8, 6, 16, 255 },
    bgViolet      = { 26, 18, 44, 255 },
    bgFiber       = { 46, 34, 74, 120 },   -- 微弱分支纤维
    bgGranule     = { 60, 46, 92, 90 },    -- 稀疏颗粒

    -- 健康细胞: 红色颗粒膜、深色内部、原色液泡
    cellMembrane  = { 214, 82, 91, 255 },
    cellInterior  = { 29, 9, 19, 255 },
    cellVacuole   = { 180, 180, 180, 180 },-- 缺图回退仅用中性灰；正式图按原色绘制

    -- 感染区域: 琥珀、橙红、珊瑚红
    infectWarm    = { 235, 160, 60, 255 },
    infectGlow    = { 255, 120, 50, 140 },
    damaged       = { 90, 60, 110, 255 },  -- 受损: 暗紫灰紫

    -- 病毒: 暖黄至橙红小亮点
    virus         = { 255, 190, 80, 255 },
    virusHot      = { 255, 120, 60, 255 },

    -- 免疫细胞: 冷青、蓝青（与健康细胞区分）
    immuneCool    = { 90, 190, 230, 255 },
    immuneTCell   = { 120, 150, 240, 255 },

    -- UI
    textMain      = { 230, 235, 240, 255 },
    textDim       = { 150, 160, 180, 200 },
    panelBg       = { 14, 12, 26, 220 },
    panelBorder   = { 70, 60, 110, 140 },
}

-- ============================================================================
-- 2. 模拟参数（占位数值 —— 调数值只改这里）
-- ============================================================================
-- ⚠️ 下列数值为「已粗调的占位值」：目标是病程约 2~4 分钟、康复与死亡两种结局均可达。
--    精调到设计目标的 5~8 分钟由策划后续完成（玩法文档 §9 数值表职责）。
Config.Sim = {
    tickInterval   = 0.25,   -- 模拟步长（秒）
    timeScale      = 1.0,    -- 调试时可加速（如 4.0）
    infectionVisualSeconds = 1.5, -- 正式感染后的贴图过渡时长，不改变感染或破裂计时。
    regionCount    = 4,      -- 4 个相邻组织区域（A 起始/B 通道/C 易感/D 高监视）

    -- 区域初始状态
    initSusceptible = 100,   -- 每区域易感细胞数
    initInfected    = 1,     -- 起始感染细胞（仅区域 1）
    initVirus       = 6,     -- 起始病毒浓度（仅区域 1）

    -- 感染与复制（规则 1/2: 浓度越高感染机会越大；感染细胞释放新病毒）
    infectRate      = 0.0006,-- 每 tick 每单位病毒的感染概率系数
    releaseRate     = 0.13,  -- 每个感染细胞每 tick 释放病毒量
    virusDecay      = 0.050, -- 游离病毒自然衰减/tick
    incubationTicks = 16,    -- 感染后到开始释放的延迟（tick）

    -- 炎症与免疫（规则 3/4: 感染提高炎症；免疫有延迟）
    inflamPerInfect = 0.6,   -- 每次新感染的炎症增量
    inflamPerDead   = 0.4,   -- 每个死亡细胞的炎症增量
    inflamDecay     = 0.020, -- 炎症衰减/tick
    immuneRise      = 0.12,  -- 免疫压力向全局信号逼近的速度（延迟来源）
    immuneDecay     = 0.008, -- 病毒清除后免疫回落速度

    -- 清除与损伤（规则 5: 过强感染/炎症增加损伤）
    virusClearRate  = 0.110, -- 免疫压力清除病毒的系数
    tCellKillRate   = 0.022, -- 免疫压力清除感染细胞的系数
    damagePerInfect = 0.004, -- 感染细胞造成的损伤/tick
    damagePerInflam = 0.002, -- 炎症造成的损伤/tick

    -- 病毒跨区域扩散
    diffusionRate   = 0.04,  -- 相邻区域病毒扩散比例/tick

    -- 小鼠（规则 6/7: 症状由载量+炎症+损伤决定，且不立即清零）
    -- 健康模型: 损耗来自「当前活跃感染 + 当前炎症」；累积损伤只降低恢复效率，
    --           不再永久扣血——这样免疫控制住感染后健康能回升，康复才可达。
    mouseHealthMax  = 100,
    infectToHealth  = 0.013, -- 当前感染细胞数对健康的消耗系数/tick（活跃威胁）
    inflamToHealth  = 0.0035,-- 当前炎症对健康的消耗系数/tick（活跃威胁）
    regenRate       = 0.55,  -- 健康自然恢复量/tick（累积损伤会降低此效率）
    damagePenaltyDiv= 0.6,   -- 累积损伤惩罚分母: penalty = damage/(cells*regions*此值)
    symptomLag      = 0.02,  -- 症状显示值的滞后逼近系数（越小有滞后感）

    -- 结局判定（玩法新 §3.4/§14: 多死亡条件 + 康复需稳定期）
    deathHealth     = 0,     -- 健康 <= 0 → 死亡
    lethalDamage    = 220,   -- 全局组织损伤超过此值 → 死亡（呼吸衰竭的代理指标）
    minRespiration  = 0.25,  -- 呼吸状态持续低于此值 → 死亡
    recoveryVirus   = 1.0,   -- 总病毒浓度低于此值
    recoveryTicks   = 20,    -- 且无感染细胞持续 N tick → 康复
    recoveryStableSec = 12,  -- 康复还需症状稳定改善持续 N 秒（康复有延迟）

    -- 附着与进入（玩法新 §9: 附着有失败概率，失败滑过、成功停留后进入）
    attachChance    = 0.35,  -- 基础附着成功率（×局部密度系数后 clamp 0..1）
    attachStaySec   = 0.8,   -- 成功附着后停留时长（停留→进入）
    entrySec        = 0.6,   -- 进入动画时长（病毒缩小淡入）

    -- 病程三阶段（感染过程.txt: 小鼠流感 0-2天潜伏无症状 / 3-7天急性达峰 / 8天+恢复）
    -- 映射到一局: 潜伏期无症状且小鼠不扣血（病毒暗中复制）；急性期症状爆发、
    -- 免疫进场；恢复窗口期免疫若已压制病毒则走向康复，否则继续恶化至死亡。
    latencySec      = 40,    -- 潜伏期时长（秒）
    acuteSec        = 120,   -- 急性期时长（秒）；结束后进入恢复窗口
    latencyInfectMul = 0.45, -- 潜伏期感染系数（复制慢、不引发症状）
}

-- ============================================================================
-- 2.5 病毒变异（感染过程.txt: 抗原漂移=点突变微调 / 抗原转变=重配质变大招）
--     玩法文档口径: 只做一次带收益与代价的选择，不做复杂变异树
-- ============================================================================
Config.Mutations = {
    drift = {
        id = "drift", name = "抗原漂移", maxCount = 2,
        desc = "HA/NA 点突变积累: 传染性小幅提升并逃逸部分免疫，但复制略降",
        mods = { infectMul = 1.25, visMul = 0.8, releaseMul = 0.9 },
        tint = { 255, 170, 90 },      -- 感染细胞叠色（乘法）: 偏橙
    },
    shift = {
        id = "shift", name = "抗原转变", maxCount = 1,
        desc = "基因片段重配的质变大招: 复制与传染暴增，但免疫可见度同步暴增",
        mods = { infectMul = 1.4, visMul = 1.7, releaseMul = 1.6 },
        tint = { 230, 90, 70 },       -- 叠色: 偏红
    },
}

-- ============================================================================
-- 3. 玩家策略（玩法文档 §3: 聚集 / 扩增 / 隐匿）
-- ============================================================================
Config.Strategies = {
    none = {
        id = "none", name = "无策略", desc = "病毒自然行动",
        mods = { flowBias = 0.0, releaseMul = 1.0, visMul = 1.0, infectMul = 1.0 },
    },
    gather = {
        id = "gather", name = "收拢", desc = "召回存活分裂体连续归队；归队途中仍会感染或被免疫消灭",
        mods = { flowBias = 0.55, releaseMul = 1.0, visMul = 1.0, infectMul = 1.0 },
    },
    spread = {
        id = "spread", name = "扩散", desc = "弹射释放一半主群；局部自主感染有被追杀风险，按1召回存活分裂体",
        mods = { flowBias = 0.0, releaseMul = 1.0, visMul = 1.0, infectMul = 1.0 },
    },
    amplify = {
        id = "amplify", name = "扩增", desc = "感染细胞释放病毒更快，但细胞损伤和免疫信号增加",
        mods = { flowBias = 0.0, releaseMul = 2.2, visMul = 1.5, infectMul = 1.1 },
    },
    stealth = {
        id = "stealth", name = "隐匿", desc = "主群收拢并降低免疫感知；远处分裂体不受保护，按1才召回",
        mods = { flowBias = 0.0, releaseMul = 0.55, visMul = 0.35, infectMul = 0.8 },
    },
}

-- ============================================================================
-- 3.5 四个组织区域（玩法新 §6: A 起始 / B 通道 / C 易感 / D 高监视，2×2 相邻）
--     fluidSpeed: 流体速度（病毒漂移快慢 + 跨区流出系数）
--     fluidDir:   流体方向（归一化向量，病毒整体漂移方向）
--     immuneDelayMul: 免疫到达延迟倍率（>1 免疫更慢察觉）
--     immuneBase: 初始免疫压力基数（D 高监视区较高）
-- ============================================================================
Config.Regions = {
    { id = 1, name = "A 起始区", neighbors = { 2, 3 },
      fluidSpeed = 0.5, fluidDir = { 0.8, 0.3 }, immuneDelayMul = 1.0, immuneBase = 0.0,
      tip = "初始感染建立点，适合聚集或扩增。" },
    { id = 2, name = "B 通道区", neighbors = { 1, 4 },
      fluidSpeed = 1.0, fluidDir = { 0.9, -0.2 }, immuneDelayMul = 1.0, immuneBase = 0.0,
      tip = "流体强: 病毒容易经过，也容易随流动离开。" },
    { id = 3, name = "C 易感区", neighbors = { 1, 4 },
      fluidSpeed = 0.3, fluidDir = { 0.4, 0.6 }, immuneDelayMul = 1.2, immuneBase = 0.0,
      tip = "健康细胞多、免疫弱: 病毒到达后可建立新感染点。" },
    { id = 4, name = "D 高监视区", neighbors = { 2, 3 },
      fluidSpeed = 0.35, fluidDir = { -0.3, 0.5 }, immuneDelayMul = 0.6, immuneBase = 0.35,
      tip = "免疫监视强: 扩增风险高，隐匿可延缓被发现。" },
}

-- 策略施加规则（玩法新 §7.4: 每区域施加 + 持续 + 冷却，同一时间仅一个区域生效）
Config.StrategyRules = {
    duration = 20,   -- 策略持续秒
    cooldown = 8,    -- 结束后冷却秒
}

-- ============================================================================
-- 3.6 毒株谱系系统（病毒表型谱系与简单突变机制）
--     每个区域维护一组毒株，每株有附着/复制/隐匿三个表型值和种群份额。
--     表型→乘数校准: initX 初始值 → 恰好输出 1.0x 乘数（基准平衡不变）
-- ============================================================================
Config.StrainSystem = {
    initAttach    = 0.50,  -- 初始附着表型 (0..1)
    initReplicate = 0.50,  -- 初始复制表型 (0..1)
    initStealth   = 0.20,  -- 初始隐匿表型 (0..1)
    initMutRate   = 0.08,  -- 初始突变率
    maxStrains    = 8,     -- 每区域最多维持的毒株数
    mergeThreshold = 0.12, -- 表型距离低于此值时合并相似毒株
    minShare      = 0.02,  -- 低于此份额时清除稀有毒株
    -- 线性映射: 乘数 = 下限 + 表型值 × (上限 - 下限)
    -- attach=0.5  → 0.6 + 0.5*(1.4-0.6) = 1.0x  ✓
    -- replicate=0.5 → 0.5 + 0.5*(1.5-0.5) = 1.0x ✓
    -- stealth=0.2 → 1.2 + 0.2*(0.2-1.2) = 1.0x  ✓（隐匿高→免疫可见度↓）
    attachInfluence    = { 0.6, 1.4 },
    replicateInfluence = { 0.5, 1.5 },
    stealthInfluence   = { 1.2, 0.2 },
    costCoupling  = 0.18,  -- 成本耦合: 高附着+高复制代价是隐匿略降
    immuneTrainThreshold  = 0.35, -- 免疫压力超过此值时开始训练识别目标表型
    recognitionSensitivity = 1.8, -- 识别灵敏度（表型漂移→识别率下降斜率）
    -- 四种策略对突变方向施加的偏置（每 tick 叠加到子代表型偏移）
    strategyBias = {
        none    = { attach=0,     replicate=0,     stealth=0,     mutRateBonus=0    },
        gather  = { attach=0.10,  replicate=0,     stealth=0,     mutRateBonus=0    },
        amplify = { attach=0,     replicate=0.12,  stealth=0,     mutRateBonus=0.04 },
        stealth = { attach=-0.04, replicate=-0.04, stealth=0.12,  mutRateBonus=0    },
    },
}

-- 细胞层布局（玩法新 §11: 重点细胞 + 低细节暗色轮廓补组织感，不铺满）
Config.CellLayer = {
    focusCells  = 5,    -- 重点细胞数（完整贴图 + 状态）
    bgCells     = 18,   -- 低细节暗色细胞轮廓数
    macrophages = 1,    -- 巨噬细胞最多 1 个（玩法新 §12.2）
    tcells      = 1,    -- T 细胞最多 1 个
}

-- ============================================================================
-- 3b. 免疫 Agent 参数（双轨制: agent 负责可见行为，聚合值负责性能兜底）
-- ============================================================================
Config.ImmuneAgents = {
    macro = {
        capacity      = 8.0,   -- 最大负载
        phagocyteRate = 1.8,   -- 每秒吞噬病毒量（受疲劳乘）
        speed         = 0.025, -- 归一化/秒（视觉层用）
        fatigueRate   = 0.05,  -- 每单位吞噬增加疲劳
        fatigueRecov  = 0.008, -- 每秒恢复疲劳
        inflamRelease = 0.012, -- 每单位吞噬释放炎症
    },
    tcell = {
        speed         = 0.020,
        killBase      = 0.55,  -- 基础杀伤效率（受识别度 × 疲劳乘）
        fatigueRate   = 0.06,
        fatigueRecov  = 0.006,
        misfireThresh = 2.2,   -- 炎症超过此值开始有误伤风险
        misfireChance = 0.12,  -- 高炎症时每秒误伤基础概率
        inflamRelease = 0.008,
        recruitDelay  = 4.0,   -- 首次招募等待秒数
    },
    maxPerRegion       = 8,    -- 两类合计上限
    recruitInflamThresh= 0.4,  -- 炎症达到此值才开始招募
}

-- ============================================================================
-- 3c. 细胞因子场（5 采样点，干扰素 + 促炎因子；双轨制 agent 场兜底）
-- ============================================================================
Config.CytokineField = {
    -- 5 个采样点归一化坐标（对应 CellView focusSpots，复用布局）
    samplePts = {
        { 0.30, 0.28 }, { 0.64, 0.24 }, { 0.46, 0.54 },
        { 0.72, 0.62 }, { 0.24, 0.70 },
    },

    -- 干扰素（IFN）
    ifn = {
        releasePerInfected = 0.04,  -- 每感染细胞每 tick 释放量
        latencyMul         = 0.2,   -- 潜伏期释放倍率
        decay              = 0.035, -- 每 tick 自然衰减比例
        diffuse            = 0.18,  -- 采样点间扩散比例
        regionDiffuse      = 0.06,  -- 跨区域扩散比例
        protectMax         = 0.55,  -- 最大感染降低比例（干扰素满量时）
        protectVsAttach    = 0.6,   -- 高附着毒株的保护效率系数（< 1 = 更难挡）
        recruitSuppress    = 0.30,  -- 对免疫招募的抑制系数
    },

    -- 促炎因子（ProInflamm）
    pro = {
        releasePerDead     = 0.10,  -- 每死亡细胞释放量
        releasePerKill     = 0.04,  -- 免疫杀伤每次释放量
        releasePerDebris   = 0.008, -- 碎片持续释放（每 tick，按 dead 比例）
        releasePerDamage   = 0.003, -- 组织损伤持续释放（每 tick）
        decay              = 0.028, -- 每 tick 自然衰减比例
        damageDecayMul     = 0.55,  -- 高损伤时衰减减慢（乘以 1-damageDecayMul*damageRatio）
        diffuse            = 0.22,  -- 采样点间扩散比例（略快于 IFN，远处招募）
        regionDiffuse      = 0.08,  -- 跨区域扩散比例
        damageThresh       = 1.8,   -- 超过此值开始造成组织损伤
        damageRate         = 0.012, -- 超阈后每 tick 每单位超量的损伤量
        ifnSuppress        = 0.35,  -- 高促炎削弱干扰素保护的系数
        recruitBoost       = 1.6,   -- 对免疫招募的增强系数
    },
}

-- ============================================================================
-- 4. 尺度定义（仅细胞玩法；宿主鸟在结算 UI 展示）
-- ============================================================================
-- 组织层数据与旧视图保留，但不再出现在玩家可切换的尺度序列中。
Config.Scales = { "cell" }
Config.ScaleNames = { cell = "细胞层" }
Config.TransitionDuration = 1.0 -- 跨尺度镜头过渡时长（秒）：越大越"渐渐变成下一层"

-- 本级滚轮缩放手感（ScaleManager 用 easeInOutCubic 缓动追赶，不突变）
-- 模型: 每格固定 +step 目标缩放；实际缩放每帧按 easeInOutCubic 追赶目标
--       （起步加速、到位减速 = 加减速曲线）；放大到该层 max 后再滚少量格
--       → 慢慢渐变进入下一层次（无硬顶/蓄力）
-- 细胞层: 最大放大到 300%，每格 +5%；缩放不切换宿主或器官视图
Config.ZoomMin = 1.0           -- 下限 = 默认视图: 没放大过就不允许缩小到 100% 以下
Config.ZoomEaseDuration = 0.4  -- 缩放缓动时长（秒）: easeInOutCubic 加速→减速追赶目标
Config.ZoomWheelThreshold = 2  -- 到达本层放大上限后继续滚几格触发跨尺度渐变
Config.ZoomPerScale = {
    cell   = { max = 3.0, step = 0.05 },
}

-- 细胞层镜头平移（放大后看局部: WASD 或鼠标贴近画布边缘移动镜头）
Config.PanSpeed = 0.35         -- 平移速度（归一化/秒）
Config.PanEdgeMargin = 60      -- 鼠标距画布边缘多少 px 内触发边缘平移

-- 免疫细胞绘制尺寸（px, 美术资产清单比例: 巨噬 > 普通细胞 > T 细胞）
-- 普通细胞贴图约 78~115px，故巨噬 128、T 细胞 46
Config.ImmuneSizes = { macrophage = 128, tcell = 46 }

-- ============================================================================
-- 5. 美术挂载位登记（后续替换正式素材只改路径，nil = 用占位矢量图形）
--    路径规则: assets/ 是资源根，从下一级开始写（规则 #1.5）
-- ============================================================================
Config.ArtSlots = {
    mouseBackground = "image/edited_mouse_scene_background_clean_20261005055148.png", -- 小鼠层清理后的16:9环境背景
    mouseSprite    = "Sprites/mouse_body.png",     -- 小鼠个体层: 外观图
    mouseAnatomy   = "Sprites/mouse_anatomy.png",  -- 小鼠个体层: 解剖图（按钮切换）
    tissueBg       = "image/bioluminescent/background.png",
    tissueFibers   = { "image/tissue_fibers_01.png.png", "image/tissue_fibers_02.png.png" },
    flowBed        = "image/flow_bed_decal.png.png",
    -- 正式荧光素材；感染状态由同一套分层细胞叠加局部感染斑表现。
    ---@type string[]
    cellHealthy    = {
        "image/bioluminescent/healthy.png",
    },
    -- 拆层共用1254画布中心(627,627)，禁止按各层alpha包围盒分别居中。
    cellBody       = "image/bioluminescent/cell_body.png",
    cellVacuole    = "image/bioluminescent/cell_vacuole.png",
    cellMembrane   = "image/bioluminescent/cell_membrane.png",
    virusAttachedParticle = "image/bioluminescent/virus_attached.png",
    attachmentGlint = "image/attachment_glint.png",
    infectionPatch = "image/infection_block_flat.png",
    cellExhaustion = "image/bioluminescent/cell_exhaustion.png",
    cellDeath = "image/bioluminescent/cell_death.png",
    buddingManifest = "image/bioluminescent/budding_manifest.json",
    -- F2_B 同源尺寸梯；运行时根据屏幕尺寸选档，不消耗模拟随机数。
    virusParticle  = {
        "image/bioluminescent/virus_32.png", "image/bioluminescent/virus_96.png",
        "image/bioluminescent/virus_256.png", "image/bioluminescent/virus_512.png",
    },
    -- 新母版按出生时已有随机相位选择，单个实体外观固定，不改变模拟 RNG。
    ---@type string[]
    macrophage     = {
        "image/bioluminescent/macrophage.png",
    },
    macrophageTint = { 255, 255, 255 },
    tCell          = { "image/bioluminescent/tcell-01.png", "image/bioluminescent/tcell-02.png" },
}

-- 纯表现参数，不改变米制碰撞半径、感染进度或病程时长。
Config.CellVisual = {
    minPixelsPerMeter = 128, -- 默认视距保留约4px潜伏颗粒；缩放仍整体作用，不单独放大点位。
    infectionPatchAlpha = 0.96,
    infectionRingRadiusMul = 1.40, -- 包住原始不规则膜（最大径向约为逻辑半径的1.271倍）。
    infectionRingPadding = 8,
    infectionRingWidthMul = 0.07,
    infectionRingWidthMin = 3.2,
    infectionRingWidthMax = 6,
    buddingSeconds = 0.8,
    buddingHandoffSeconds = 0.12,
    attachmentGraceSeconds = 0.15,
    attachmentFadeSeconds = 2.4,
    deathTransitionSeconds = 0.35,
    virusFill = 466 / 512,
    macrophageFill = 965 / 1254,
    tCellFill = 752 / 1254,
    -- 各图 alpha 前景最大边 / 画布边，保持现有实体显示尺寸和中心。
    immuneFillByPath = {
        ["image/bioluminescent/macrophage.png"] = 466 / 512,
        ["image/bioluminescent/tcell-01.png"] = 466 / 512,
        ["image/bioluminescent/tcell-02.png"] = 466 / 512,
    },
}

Config.EnvironmentVisual = {
    tileWidthMeters = 8,
    baseAlpha = 0.22,
    fiberAlpha = 0.36,
    flowBedAlpha = 0.52,
    flatFlowBedAlpha = 0.85,
    flowMarkAlpha = 0.82,
    flowMarkWidth = 1.6,
    debugFlowBands = false,
}

-- 本轮重做独立配置；旧参数保留供旧视图/历史备份参考，不参与新玩法模拟。
Config.Title = "病毒涌现 · 感染网络"
-- 客户端音乐编排；不参与 Gameplay、固定步、随机数或质量账本。
Config.DynamicMusic = {
    introPath = "audio/chase_transition.wav", heartbeatPath = "audio/chase_heartbeat.wav",
    normalGain = .5, duckMultiplier = .35, introGain = .9, heartbeatGain = .75,
    fadeInSeconds = .25, fadeOutSeconds = 2.8,
}
Config.Gameplay = {
    -- Stable map generation is intentionally separate from the simulation RNG.
    -- Normal play chooses one new seed per world; set a value only to reproduce a map.
    width = 120, height = 144, cellCount = 960,
    mapSeed = nil, mapGenerationVersion = 5,
    mapRegionCount = 5, mapRegionSpacing = 3.0, mapDensity = 1.0,
    mapEdgeCoverage = 0.87, mapCoverageSampleSpacing = 2.0,
    mapSpawnSafeRadius = 2.0, mapChannelWidth = 3.0,
    mapRouteTargetSpacing = 4, mapCellGap = .16,
    seed = 314159,
    cellRadiusMin = 0.34, cellRadiusMax = 0.48,
    movementStep = 1 / 60, diseaseStep = 0.5,
    virusRadius = 0.045, initialMass = 30,
    baseSpeed = 1.8, minSpeed = 0.78, turnResponse = 5,
    groupRadius = 0.48, absorptionExtra = 0.42, absorptionSpeed = 2.6,
    activeAbsorptionExtra = 1.8, -- 主动瞬时吸附：当前群半径外的米数。
    activeAbsorptionCooldown = 3, -- 模拟秒；全群共享，每次合法脉冲（包括空放）进入冷却。
    initialSwarmCapacity = 2,
    autonomy = {
        enabled = true, -- 还必须获得分群小脑；绝不自动分裂。
        thinkInterval = 0.25, searchRadius = 6, dangerExtra = 2.2,
        speedMultiplier = 0.8, fleeSpeedMultiplier = 1.0,
        targetHoldSeconds = 1.2, reservationPenalty = 1.0,
        collectRadius = 2.4, collectBelowMass = 8, completionExposure = .8,
        wanderRadius = 3.2, wanderSeconds = 4, detourExtra = .12,
        escapeProbe = 1.0, directionSamples = 24,
        dangerExitExtra = 2.8, dangerMemorySeconds = 1.2,
        switchImprovement = 0.65, reservationTimeout = 4,
        distanceWeight = 1, exposureWeight = 0.4, riskWeight = 1.5,
        flowWeight = 0.4, cellClearance = 0.025,
    },
    -- 仅当前 SwarmWorld 使用；不复用旧玩法的 cytokine/fatigue 配置。
    ecology = {
        enabled = true, step = .5, spacing = 1.5,
        diffusion = .32, decay = .16, maxSignal = 6, signalEpsilon = 1e-6,
        productionRate = .45, exhaustionRate = .22, debrisRate = .32,
        releasePulse = .18, deathPulse = .6, damagePulse = .35,
        senseRadius = 4.5, investigateThreshold = .12,
        defenseThreshold = .10, defenseDelay = 4, defenseDuration = 12,
        defenseRamp = 2, defenseFade = 4, defenseSuppression = .55,
    },
    immuneBehavior = {
        loadCapacity = 8, loadResume = 4, processingRate = .5,
        debrisLoad = 3, loadedSpeedMin = .75, recognitionSeconds = 2.2,
        -- 巨噬先应对可见群；诱饵仍可争夺注意力。T 细胞保留组织识别流程。
        swarmPriority = 80, decoyPriority = 90,
        swarmWarningSeconds = .65, swarmWarningReductionPerLevel = .05,
        particleWarningSeconds = .15, debrisWarningSeconds = .65,
        swarmWindup = .30, particleWindup = .15, debrisWindup = .6,
        swarmAttackInterval = 1.2, particleAttackInterval = .35, debrisAttackInterval = 1.2,
        swarmChaseSpeed = 1.9, swarmChaseSpeedPerLevel = .06, particleChaseSpeed = 1.6,
        selectiveLoadFraction = .5, loadedDistanceWeight = 4, loadedCrowdWeight = 3,
        checkMemorySeconds = 12, checkMemoryLimit = 12, recheckSeconds = 1.1,
        -- 六个正式阶段对应已生效警戒 0..5；警戒 VI 沿用末档。
        -- 基础字段保留为回退值。计时动作开始时取值，消化按当前警戒逐步推进。
        growth = {
            swarmWarningSeconds = { .65, .60, .55, .50, .45, .40 },
            swarmChaseSpeed = { 1.90, 1.96, 2.02, 2.08, 2.14, 2.20 },
            particleWindup = { .15, .15, .14, .13, .12, .12 },
            particleAttackInterval = { .35, .33, .31, .29, .27, .25 },
            processingRate = { .50, .55, .62, .70, .78, .85 },
            swarmAttackInterval = { 1.20, 1.18, 1.14, 1.10, 1.05, 1.00 },
            tcellWarningSeconds = { 2.8, 2.6, 2.4, 2.2, 2.0, 1.8 },
            recognitionSeconds = { 2.2, 2.1, 2.0, 1.8, 1.6, 1.4 },
            -- 检查记忆仍到警戒 III 才开放，前三档不会提前获得复核资格。
            recheckSeconds = { 1.1, 1.1, 1.1, 1.1, .95, .80 },
            tcellAttackInterval = { 2.8, 2.7, 2.6, 2.4, 2.2, 2.0 },
        },
    },
    infectionReach = 0.32, infectionSeconds = 18, exposureDecay = 0.012,
    releasedInfectionPower = 0.16, densityReference = 10,
    latentSeconds = 28, releaseInterval = 18, releaseBatches = { 3, 5, 7, 8, 8, 6 },
    exhaustedSeconds = 35, exhaustedReleaseInterval = 20, exhaustedReleaseCount = 2,
    releasedLifetime = 100, releasedDrift = 0.10, releasedFlowInfluence = 0.62,
    playerFlowInfluence = 0.18, splitFlowInfluence = 0.30,
    flatMapFlowInfluence = 0.70, -- v5: clear upstream resistance, still passable.
    inactiveDrift = 0.035, splitCostFraction = 0.10, splitFraction = 0.5,
    splitMinMass = 12, splitCooldown = 8, splitLaunchSpeed = 4.2,
    splitLaunchSeconds = 0.7, splitRecoil = 0.7, mergeExtra = 0.5,
    mergeSpeed = 0.9, mergeGraceSeconds = 2,
    immuneMax = 54, immuneRecruitInterval = 65, immuneSafeDistance = 4.5,
    -- 正式大地图按区域驻巡；旧小图仍使用各起点的 immuneCount。
    immuneCoverage = { patrolRadius = 14, spawnSpacing = 12, signalWeight = 2,
        stagePopulation = {10,16,24,32,40,50}, deploymentInterval = 2,
        workAreaRadius = 4, workAreaSlots = 2 },
    immuneDetectRange = 3.2, immuneWarningSeconds = 2.8, immuneAttackWindup = 1.1,
    immuneWarningSpeedFactor = .25,
    immuneAttackInterval = 2.8, immuneKillsPerAttack = 2, immuneClearChance = 0.95,
    immuneSpeed = 0.90, immuneChaseSpeed = 1.30, immuneRadius = 0.48,
    immuneForgetExtra = 1.8, immuneNodeHits = 3,
    -- 未定稿初始值：以有操作的一局约10～15分钟为调校目标，不硬性按计时胜利。
    infectionInflammation = 0.6, releaseInflammation = 0.25,
    nodeAttackInflammation = 2.3, nodeAttackDamage = 0.8,
    deadInflammation = 1.2, deadDamage = 0.6,
    latentInflammationRate = 0.010, productiveInflammationRate = 0.030,
    exhaustedInflammationRate = 0.050, deadInflammationRate = 0.018,
    productiveDamageRate = 0.007, exhaustedDamageRate = 0.018, deadDamageRate = 0.006,
    inflammationDecayRate = 0.0012, hotspotThreshold = 8,
    inflammationMilestone = 70, irreversibleInflammation = 180, irreversibleDamage = 110,
    minRespiration = 0.20, respirationFailureSeconds = 18,
    mouseHealthMax = 100, maxFrameSeconds = 0.25,
    targetDurationMin = 900, targetDurationMax = 1200,
}
-- 开发期概率，不代表最终六轮平衡。合法池不足时绝不突破前置/B3。
Config.Cards = {
    maxChoices = 6, offerCount = 3, formalEnabled = true,
    rarityWeights = {
        { COMMON = 85, RARE = 15, EPIC = 0 },
        { COMMON = 75, RARE = 25, EPIC = 0 },
        { COMMON = 60, RARE = 35, EPIC = 5 },
        { COMMON = 45, RARE = 45, EPIC = 10 },
        { COMMON = 30, RARE = 50, EPIC = 20 },
        { COMMON = 15, RARE = 50, EPIC = 35 },
    },
    definitions = {
        { id="swarm_anchor", name="群体锚定", rarity="COMMON", kind="开关", implemented=true, desc="让选中的病毒群停在原地，抵抗组织液的推动。仍能感染和吸收病毒，手动移动即可解除。" },
        { id="discrete_recall", name="离散回收", rarity="COMMON", kind="主动", implemented=true, desc="持续6秒，把附近散落的病毒拉向当前群；吸收后才会增加群内数量。" },
        { id="emergency_dash", name="紧急冲刺", rarity="COMMON", kind="主动", implemented=true, desc="朝上一次移动的方向快速冲刺0.5秒。冲刺时仍会撞墙，也会受到攻击。" },
        { id="shed_decoy", name="脱落诱饵", rarity="COMMON", kind="主动", implemented=true, desc="放出4颗病毒作为诱饵，吸引巨噬细胞。群内需至少留下3颗；诱饵可主动收回，也会被清除。" },
        { id="debris_camouflage", name="残骸伪装", rarity="COMMON", kind="条件被动", implemented=true, desc="在残骸旁停留3秒，更难被远处的免疫细胞发现。移动、感染或残骸被清理后失效。" },
        { id="local_flow", name="局部转流", rarity="RARE", kind="主动环境", implemented=true, desc="让附近的组织液朝指定方向流动，持续10秒。病毒群和散落的病毒都会受到影响。" },
        { id="swarm_capacity_4", name="分裂扩容", rarity="RARE", kind="规则", implemented=true, desc="最多能拥有4群病毒。当前群至少有12颗病毒时，才能分裂。", capacity = 4 },
        { id="swarm_local_brain", name="分群小脑", rarity="RARE", kind="规则", implemented=true, desc="你没有操控的病毒群，会自己寻找细胞感染、躲避敌人、收集病毒和探索。你随时可以接管。", localBrain = true },
        { id="node_hide", name="寄居藏身", rarity="RARE", kind="主动节点", implemented=true, desc="藏进一个已感染的细胞，也可以主动离开。细胞被摧毁时，会损失一半藏身的病毒。" },
        { id="membrane_glide", name="感染接力", rarity="RARE", kind="感染小队", implemented=true, desc="留下3颗病毒，继续感染当前群正在感染的细胞，主群可以离开。占1个分群名额，主群至少保留3颗。完成或目标死亡后，小队转为游离病毒；附近按E回收，Tab可接管。" },
        { id="node_cover", name="节点包覆", rarity="RARE", kind="主动节点", implemented=true, desc="花费4颗病毒，替一个已感染的细胞挡住一次攻击。每个细胞每局只能保护一次。" },
        { id="tail_preserve", name="断尾保全", rarity="EPIC", kind="被动应急", implemented=true, desc="遭到致命的免疫攻击时，最多保住2颗病毒，并向外逃开一小段。每局只能触发一次。" },
        { id="node_takeover", name="节点接管", rarity="RARE", kind="主动节点", implemented=true, desc="把感染细胞刚释放的5颗病毒组成一个新群。还没释放时，可以先预约下一批。" },
        { id="infection_trail", name="感染拖尾", rarity="RARE", kind="开关", implemented=true, desc="开启后，每主动移动1.5米就在身后留下一颗病毒，沿路传播感染。群内病毒不足时自动关闭；可用基础吸附或离散回收收回。" },
        { id="swarm_capacity_6", name="多群扩容", rarity="EPIC", kind="进阶规则", implemented=true, desc="病毒群的数量上限从4群增加到6群。", capacity = 6, prerequisites = { "swarm_capacity_4" } },
        { id="cluster_dispatch", name="集群调度", rarity="EPIC", kind="群指令", implemented=true, desc="让其他病毒群集合或留守，固定和藏身的群除外。留守群遇险或目标消失时，会停止留守。" },
        { id="merge_seed", name="合并播种", rarity="EPIC", kind="合并开关", implemented=true, desc="两群合并时，拿出合并后10%的病毒向四周散播，最多6颗。每20秒可触发一次，获得后默认开启；散出的病毒可主动收回。" },
        { id="rupture_spread", name="破裂散播", rarity="EPIC", kind="节点死亡规则", implemented=true, desc="正在释放病毒的感染细胞被免疫系统摧毁时，会把剩余待释放病毒的一半散播出去。" },
    },
}

-- 临时平衡参数：米、模拟秒、真实病毒颗数。能力不改写 Gameplay 基础配置。
Config.Debug = Config.Debug or {}
Config.Debug.cardTools=false
Config.CardAbilities = {
    swarm_anchor={targetType="swarm"},
    discrete_recall={targetType="self",range=3,duration=6,speed=1.6,cooldown=18},
    emergency_dash={targetType="self",speed=4.5,duration=.5,cooldown=4},
    shed_decoy={targetType="self",massCost=4,minimumRemainingMass=3,cooldown=18,signalSeconds=8},
    debris_camouflage={range=1,duration=3,visibility=.55,nearRange=1,moveThreshold=.2},
    local_flow={targetType="direction",range=3,duration=10,cooldown=25},
    node_hide={targetType="node",range=.5,cooldown=3,lossFraction=.5},
    membrane_glide={targetType="cell",range=.5,massCost=3,minimumRemainingMass=3,fullInfectionSeconds=15},
    node_cover={targetType="node",range=.5,massCost=4,minimumRemainingMass=3,cooldown=10,shieldHits=1},
    tail_preserve={remaining=2,escapeDistance=.8,escapeSpeed=3.2},
    node_takeover={targetType="node",range=.5,minimumMass=5,cooldown=20},
    infection_trail={targetType="self",distancePerVirus=1.5,minimumRemainingMass=3},
    cluster_dispatch={targetType="command",gatherGap=1},
    merge_seed={targetType="global",fraction=.1,maxMass=6,minimumRemainingMass=3,cooldown=20},
    rupture_spread={fraction=.5},
}

Config.Evolution = {
    establish={nodes=1,released=1},
    recovery={newInfections=2},
    -- 每阶段只计本阶段起步并完成的感染；阶段三为本阶段新节点完成首次释放。
    production={released=3},
    expansion={[4]=4,[5]=8,[6]=12},
    victory={infections=16,newInfections=4},
}
Config.ImmuneAlert = {
    maxLevel = 6, maxImmuneUnits = 54, maxTCells = 27, maxMacrophages = 27,
    reinforcementInterval = 65, spawnSafeDistance = 4.5, warningDuration = 2.8,
    alertActivationDelay = 5, channelPatrolDuration = 15, channelPatrolInterval = 35,
    searchMemoryDuration = 8, searchRadius = 1.5,
    searchLevel = 5, cellMemoryLevel = 3,
    alarmLevel = 1, alarmRadius = 6, alarmDuration = 8, alarmCooldown = 18,
    alarmMaxActive = 4, alarmResponders = 1, alarmCooperationLevel = 4,
    alarmCooperationResponders = 2, alarmEncounterSeconds = 1,
    activityAlarmThreshold = .35, activityAlarmSeconds = 3,
    activityAlarmSampleInterval = .5, activityAlarmFallTolerance = .001,
    hotspotLevel = 4, hotspotRadius = 2.6, hotspotRecruitRadius = 6,
    hotspotDuration = 16, hotspotCooldown = 24, hotspotMaxActive = 2,
    hotspotQuietSeconds = 4, hotspotSweepInterval = 1.5,
    nodeAttackSlots = 1, virusAreaSlots = 1, swarmAttackSlots = 2,
    reservationTimeout = 6, separationSpeed = 0.18,
    densityGridSize = 1.5, densityWeight = 0.8, activeSignalMultiplier = 1.25,
    regionAssignmentPenalty = 8, patrolBaseRadius = 2.4, patrolAlertRadius = 3.8,
    channelMode = "branch_patrol", -- 当前小图使用支路回退，不驻守必经流道。
    descriptions = {
        "基础防御：免疫分工与目标预约。",
        "各区增援分批入场；巡逻范围扩大，巨噬确认病毒活动后引导附近闲置单位调查。",
        "继续分区增援；追击组优先病毒群，清理组处理散落病毒并按剩余负载接单。",
        "区域兵力增加；T细胞定位活跃节点，分头检查组织并短时记住结果。",
        "更多增援进入各区；T细胞确认节点后引导巨噬清理，邻近工作名额避免扎堆。",
        "高强度分区增援；支路短时巡逻，失锁后搜索最后观察位置，超时归位。",
        "免疫系统维持局部协作与搜索，仍受负载、接触和数量限制。",
    },
}
Config.StartRegions = {
    { type = "UPPER_AIRWAY", name = "上呼吸道", mass = 30, initialNodes = 0, immuneCount = 2, flatImmuneCount = 10,
      size = "中", infection = "低", immune = "低", desc = "健康细胞较多，免疫压力低。先建立节点，再沿气管向深部推进。" },
    { type = "TRACHEA", name = "气管主干", mass = 30, initialNodes = 0, immuneCount = 3, flatImmuneCount = 12,
      size = "中", infection = "中", immune = "中", desc = "组织流明显，可选择左右支路。适合分裂与跨区域感染。" },
    { type = "DEEP_LUNG", name = "肺部深区", mass = 42, initialNodes = 1, immuneCount = 4, flatImmuneCount = 14,
      size = "高", infection = "高", immune = "高", desc = "带一个初始潜伏节点，免疫压力较高。建立网络后及时转移。" },
}
-- 旧占位表已移除；正式卡池定义在 Config.Cards.definitions。
Config.ArtSlots.lungStages = {
    "Sprites/lung_stage_0.png", "Sprites/lung_stage_1.png", "Sprites/lung_stage_2.png",
    "Sprites/lung_stage_3.png", "Sprites/lung_stage_4.png",
}


-- [ENDING_ART] 鸟只在结算遮罩中出现；资源路径从 assets 的下一级写起。
-- 暂无鸟美术时使用 UI 鸟形占位，后续分别填写胜利/失败结局图片路径。
-- Existing clean film; extinct has no matching film asset yet.
Config.EndingVideo = { victory = "video/ending/emergence90.mp4", extinct = false }
Config.EndingTransition = {
    duration=2.6, hudHide=.55, zoomEnd=2.6, zoom=.72,
    videoStart=.55, videoOffset=2.1, blend=1.8,
    audioFade=1.8, pulseFade=.7, effectsFade=1.1,
}
Config.EndingBird = { victoryImage = false, extinctImage = false }

-- Approved 8777 material pack. These switches only control additional light;
-- base art always uses the approved textures, including when light is disabled.
-- Presentation only: all collision sizes, cell alpha/anchors and simulation RNG
-- remain the existing authoritative values.
Config.Bioluminescence = {
    enabled = true, glowEnabled = true,
    emissionAtlas = "image/bioluminescent/emission_atlas.png",
    glowAlpha = .16, maxGlowDraws = 24, denseGlowDraws = 8,
    denseThreshold = 800, minGlowPixels = 28, minVirusGlowPixels = 32,
}
Config.EnvironmentVisual.tileWidthMeters = 12
Config.EnvironmentVisual.baseAlpha = .82
Config.EnvironmentVisual.flatBaseAlpha = .82
Config.EnvironmentVisual.fiberAlpha = .12
Config.EnvironmentVisual.flatFlowBedAlpha = .16

-- 音效gain只设声源增益；用户分类音量统一由UserSettings控制。
---@class GameSoundDefinition
---@field path string
---@field gain number
---@field interval number
---@field priority number
---@field entityInterval number?
---@field persistent boolean?
---@field global boolean?
---@field distantFloor number?
---@type table<string, GameSoundDefinition>
Config.SoundEffects = {
    absorb_pulse={path="audio/absorb_pulse.wav",gain=.40,interval=.20,priority=2},
    virus_absorb={path="audio/virus_absorb.wav",gain=.15,interval=.10,priority=1},
    infection_complete={path="audio/infection_complete.wav",gain=.40,interval=.12,priority=3},
    swarm_split={path="audio/swarm_split.wav",gain=.45,interval=.15,priority=3},
    swarm_merge={path="audio/swarm_merge.wav",gain=.40,interval=.12,priority=3},
    swarm_hit={path="audio/swarm_hit.wav",gain=.65,interval=.12,priority=5,distantFloor=.20},
    node_hit={path="audio/node_hit.wav",gain=.55,interval=.08,entityInterval=.20,priority=4,distantFloor=.15},
    swarm_cleared={path="audio/swarm_cleared.wav",gain=.50,interval=.15,priority=5,global=true},
    action_denied={path="audio/action_denied.wav",gain=.18,interval=.25,priority=4,global=true},
    skill_dash={path="audio/skill_dash.wav",gain=.45,interval=0,priority=4,persistent=true},
    card_acquired={path="audio/card_acquired.wav",gain=.40,interval=0,priority=5,persistent=true,global=true},
    ending_defeat={path="audio/ending_defeat.wav",gain=.65,interval=0,priority=10,global=true},
    release_batch={path="audio/release_batch.wav",gain=.25,interval=.20,priority=1},
    cell_dead={path="audio/cell_dead.wav",gain=.30,interval=.20,priority=2},
    node_warning={path="audio/node_warning.wav",gain=.45,interval=.30,entityInterval=1.5,priority=4,distantFloor=.20},
    alert_up={path="audio/alert_up.wav",gain=.40,interval=.50,priority=5,global=true},
    skill_recall={path="audio/skill_recall.wav",gain=.35,interval=0,priority=4,persistent=true},
    skill_decoy={path="audio/skill_decoy.wav",gain=.35,interval=.15,priority=3},
    tail_preserve={path="audio/tail_preserve.wav",gain=.60,interval=0,priority=6,global=true,persistent=true},
    node_cover={path="audio/node_cover.wav",gain=.35,interval=0,priority=4,persistent=true},
    shield_block={path="audio/shield_block.wav",gain=.55,interval=.08,entityInterval=.20,priority=5,distantFloor=.20},
    node_takeover={path="audio/node_takeover.wav",gain=.45,interval=0,priority=4,persistent=true},
    switch_control={path="audio/switch_control.wav",gain=.25,interval=.10,priority=3,global=true},
    anchor_on={path="audio/anchor_on.wav",gain=.30,interval=.05,entityInterval=.15,priority=3},
    anchor_off={path="audio/anchor_off.wav",gain=.25,interval=.05,entityInterval=.15,priority=3},
    hide_enter={path="audio/hide_enter.wav",gain=.35,interval=.05,entityInterval=.15,priority=4},
    hide_exit={path="audio/hide_exit.wav",gain=.35,interval=.05,entityInterval=.15,priority=4},
    glide_start={path="audio/glide_start.wav",gain=.30,interval=.05,entityInterval=.15,priority=3},
    flow_redirect={path="audio/flow_redirect.wav",gain=.35,interval=0,priority=4,persistent=true},
    dispatch_gather={path="audio/dispatch_gather.wav",gain=.25,interval=.20,priority=3,global=true},
    dispatch_hold={path="audio/dispatch_hold.wav",gain=.25,interval=.20,priority=3,global=true},
    camouflage_on={path="audio/camouflage_on.wav",gain=.25,interval=.05,entityInterval=1,priority=2},
}
Config.SoundMix = {
    ambiencePath="audio/micro_ambience.wav",ambienceGain=.30,pauseMultiplier=.35,
    ambienceFadeIn=.8,menuFadeOut=.3,normalSources=8,importantSources=2,
    nearDistance=3,farDistance=12,maxQueue=128,
}

-- 宿主鸟类线索：不烘焙进底乐，只在安静的实际游玩中偶尔出现。
Config.BirdHints={
    enabled=true,firstMin=35,firstMax=55,
    quietGrace=6,fadeIn=.04,fadeOut=.20,gainRisePerSecond=.015,
    profiles={
        {lastStage=2,gainMin=.08,gainMax=.12,intervalMin=80,intervalMax=130},
        {lastStage=4,gainMin=.14,gainMax=.18,intervalMin=65,intervalMax=110},
        {lastStage=6,gainMin=.22,gainMax=.28,intervalMin=50,intervalMax=90},
    },
    clips={
        "audio/bird_hints/bird_hint_soft_pair.wav",
        "audio/bird_hints/bird_hint_low_chirp.wav",
        "audio/bird_hints/bird_hint_tiny_trill.wav",
        "audio/bird_hints/bird_hint_distant_answer.wav",
    },
}

return Config
