-- ============================================================================
-- MobileLayout.lua - 触屏 / 手机端的操作文案与布局参数（纯数据 + 判定）
-- 桌面端保持原有键盘文案与布局；只有触屏判定为真时才替换文案、放大触控目标。
-- 判定：原生移动平台（PlatformUtils.NeedsVirtualJoystick）或本次运行已出现真实触摸。
-- 不写模拟状态，不注册事件；HUD 的 PointerDown 监听负责调用 MarkTouch。
-- ============================================================================

local M = {}

-- 本次运行是否出现过真实触摸（Web 触屏设备）；HUD 监听到触摸时写入。
M.touchSeen = false

function M.MarkTouch()
    M.touchSeen = true
end

-- Absolute HUD overlays must reserve the same native capsule band as SafeAreaView.
function M.SafeInsets()
    local ui=require('urhox-libs/UI')
    local s=ui.GetSafeAreaInsets()
    local result={left=s.left,top=s.top,right=s.right,bottom=s.bottom}
    local native=sdk --[[@as table?]] -- 可选 SDK 扩展，先检查能力再调用。
    if native and native.GetNativeExitMenuRect then
        local rect=native:GetNativeExitMenuRect()
        if rect and type(rect.bottom)=='number' then
            result.top=math.max(result.top,rect.bottom*ui.GetHeight())
        end
    end
    return result
end

---@param hud table?
---@return boolean
function M.IsTouch(hud)
    if hud and hud.touchSeen_ then return true end
    if M.touchSeen then return true end
    -- 每次调用读取当前模块，测试替换平台桩后也能拿到新值。
    -- 无 input 全局（无头测试 / 早期初始化）时平台查询会抛错，统一视为非触屏。
    local ok, result = pcall(function()
        return require("urhox-libs.Platform.PlatformUtils").NeedsVirtualJoystick()
    end)
    return ok and result == true
end

-- 触屏文案：去掉键盘键名，改为点按 / 拖动说明。
M.Text = {
    absorbBtn = "吸附",
    splitBtn = "分离",
    switchBtn = "切群",
    absorbReady = "吸附",
    absorbCooldown = "吸附 %.1fs",
    quickMenu = "技能",
    skillCancel = "取消",
    skillMenuClose = "关闭",
    skillMenuTitle = "功能菜单",
    skillMenuHint = "点按功能槽使用 · 点「关闭」退出 · 模拟继续运行",
    skillMenuHintEmpty = "尚未获得可操作的功能卡 · 点「关闭」退出",
    ticker = "左下摇杆移动 · 点按吸附 / 分离 / 切群 · 双指缩放 · 右下菜单暂停",
    absorptionIdle = "点「吸附」收集附近游离病毒；规模越大，感染越快。",
    absorption = "吸附：附近 %d 个 · 范围 %.2f米 · 接触感染倍率 ×%.2f",
    swarmListTitle = "存活群体 %d / %d · 点选控制",
    splitCooldown = "分离冷却 %.1f秒 · 可继续吸附，点「切群」或在群列表点选。",
    splitNeedMass = "当前群至少 %d 个才能分离；点「吸附」收集游离个体壮大当前群。",
    splitReady = "可再次分离；点「切群」切换控制；「技能」打开功能菜单。",
    splitSuccess = "分离成功：新分群沿最近移动方向弹出；点「切群」或在群列表点选切换。",
    skillKeyHintReady = "吸附：就绪（冷却3秒）",
    skillKeyHintCooldown = "吸附：冷却%.1f秒",
    skillKeyHintTail = " · 技能菜单 · 分离 · 切群",
    targetSelect = "点击高亮合法目标立即执行；点「取消」放弃，模拟继续运行",
    tutorialSkip = "长按跳过教程",
    tutorialSkipping = "正在跳过 · %.0f%%",
    menuReady = "场景已就绪 · 点击开始游戏",
    menuTutorialNote = "每局开场包含引导，可长按教程卡片上的「跳过」按钮跳过当前教程。",
}

-- 技能卡获得提示（CardPanel 通过 SkillControls.Hint 读取）的触屏版本。
M.SkillHint = {
    emergency_dash = "按住「技能」，滑向冲刺后松手：沿最近主动移动方向冲刺，冷却4秒；方向被完全阻挡时不进入冷却。",
    shed_decoy = "按住「技能」，滑向诱饵后松手：脱落4颗，至少留3颗，冷却18秒。",
    discrete_recall = "按住「技能」，滑向离散回收后松手：附近有可牵引病毒时启动6秒远距牵引，冷却18秒。",
    local_flow = "先进入组织流区域，再按住「技能」滑向局部转流，松手后指定方向；无水流时不进入冷却。",
    membrane_glide = "选择当前群正在感染的细胞，留下3颗继续感染，占1个名额；点「吸附」回收附近小队，点「切群」接管。",
    swarm_anchor = "点独立「驻留」按钮开启或关闭；手动移动会解除驻留。",
    infection_trail = "点独立「尾迹」按钮开启或关闭；规模不足时自动关闭。",
    merge_seed = "点独立「播种」按钮开启或关闭合并播种。",
    default = "按住「技能」展开，滑向技能后松手；需要目标时再点高亮目标，点「取消」放弃。",
}

-- 教程卡在触屏下的正文 / 操作提示；未列出的字段沿用 Tutorial 原文。
M.Tutorial = {
    intro = { keys = "点击屏幕继续" },
    target = { keys = "继续后，按住左侧空白处拖动移动" },
    infect = { keys = "按住左侧空白处，拖动移动" },
    collect = { text = "跟随边缘的琥珀色三角，找到细胞释放的病毒。\n靠近可以收集，也可以点「吸附」吸收附近病毒。",
        keys = "点「吸附」收集附近病毒" },
    split = { text = "分裂可以让病毒群接触不同细胞。\n先用摇杆朝希望分出的方向移动，再点「分离」。",
        keys = "点「分离」分裂 · 需要至少 12 病毒 · 成功一次" },
    switch = { text = "点「切群」切换控制，观察哪一群亮起控制标记。\n分群还不会自行寻找目标，需要你分别带到细胞附近。",
        keys = "点「切群」切换 · 成功一次" },
    tcell = { keys = "点击屏幕继续" },
    macrophage = { keys = "点击屏幕继续" },
    splitReady = "准备就绪 · 点「分离」分裂",
}

-- 触屏布局参数：按 hudContent 的逻辑尺寸给出摇杆与按钮尺寸，触控目标不小于 44。
---@param w number
---@param h number
---@return table
function M.Metrics(w, h)
    local short = h < 480
    local pad = math.floor(math.max(120, math.min(150, h * 0.32)))
    local small = w < 760
    return {
        short = short,
        pad = pad,
        knob = math.floor(pad * 0.375 + 0.5),
        joystickWidth = pad + 8,
        showJoystickHint = not short,
        buttonHeight = 56,
        actionWidth = small and 92 or 112,
        menuWidth = 56,
        groupsWidth = 72,
        iconSize = 28,
        quickHeight = 52,
        topHeight = short and math.min(150, h * 0.34) or math.min(190, h * 0.38),
        summaryHeight = short and math.min(118, h * 0.30) or math.min(152, h * 0.42),
        statsToggleHeight = 40,
        skillSlotHeight = short and 68 or 84,
    }
end

return M
