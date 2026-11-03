# UI 与按钮素材用途说明

核对日期：2026-10-14。按项目内实际文件生成：`UI/` 有 27 张图标，`按钮/` 有 24 张底框与控件图，共 51 张。

本文逐张解释素材用途，再列出游戏中的每个按钮及操作结果。**底框＋图标＋程序文字组成按钮**：同一底框可以用于多个操作，一张技能图标也不一定是可点击按钮。

用途依据当前 `HUD.lua`、`MainMenu.lua`、`SkillPanel.lua`、`SkillControls.lua`、`CardPanel.lua` 和 `Config.lua`。下表是素材与功能的接入对应说明；本次没有修改游戏代码，也未将新图自动接入。数量、名称、快捷键、成本、冷却与状态继续由程序显示。

## 一、按钮文件夹：逐张用途

这24张中包括真正的按钮底框，也包括面板、滑条、摇杆和装饰。点击文件名可打开源图。

| 图片文件 | 尺寸（像素） | 类型 | 用途 | 对应ID／位置 |
|---|---|---|---|---|
| [ui_action_button_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_action_button_normal.png>) | 384×128 | 可点击按钮底框 | 玩法快捷操作：基础吸附、分离、切群、菜单；也用于紧急冲刺、脱落诱饵和功能菜单入口。 | absorbBtn、splitBtn、switchBtn、menuBtn、quickDash、quickDecoy、skillMenuToggle、quickMenu |
| [ui_dialog_panel_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_dialog_panel_normal.png>) | 1024×1280 | 面板底框 | 设定、选卡、结算等大弹窗的外观。它承载内容，本身不代表确认或返回。 | settingsScreen内层、cardPanel内层、endingOverlay内层；功能菜单可用其精简版本 |
| [ui_dropdown_field_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_dropdown_field_normal.png>) | 640×96 | 可点击选择控件 | 界面缩放和帧率上限下拉框。点击展开选项；当前缩放85%／100%／115%，帧率30／60／120。 | uiScale、frameLimit；下拉选项列表共用P05底框 |
| [ui_ending_video_frame_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_ending_video_frame_normal.png>) | 1920×1080 | 装饰素材〔规划〕 | 围绕结局视频的外框，不是播放器或播放按钮。鸟由视频呈现；当前视频播放逻辑尚未接入。 | 后续结局视频外框，可选；当前尚未接入视频播放器 |
| [ui_hud_panel_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_hud_panel_normal.png>) | 768×512 | 面板底框 | 任务、阶段、地图信息、数量统计、病毒群状态及功能菜单等信息区的背景。 | stagePanel、scalePanel、entityPanel、strategyBar、skillMenuPopup的面板外观 |
| [ui_joystick_base_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_joystick_base_normal.png>) | 256×256 | 可拖动控件部件 | 虚拟摇杆底盘，限定触摸移动区域及中心位置，不执行一次性点击技能。 | moveJoystick底盘；拖动控件，不能作为点击按钮 |
| [ui_joystick_knob_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_joystick_knob_normal.png>) | 96×96 | 可拖动控件部件 | 摇杆随手指移动的帽；偏离中心的方向与距离决定病毒群移动输入。 | moveJoystick可移动摇杆帽 |
| [ui_keycap_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_keycap_normal.png>) | 128×96 | 信息标签 | 快捷键提示底框，叠加E、空格、Tab、Shift、F、V或数字；标签本身不执行操作。 | 动作／技能快捷键说明，按需叠加，不改变原输入逻辑 |
| [ui_menu_button_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_menu_button_normal.png>) | 768×128 | 可点击按钮底框 | 主菜单的开始／继续、无尽模式、设定、制作名单、退出共用。图片本身不决定操作，由按钮名称和点击回调区分。 | storyMode、endlessMode、openSettings、openCredits、exitGame；开始／继续、无尽、设定、名单、退出共用 |
| [ui_minimap_frame_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_minimap_frame_normal.png>) | 384×512 | 小地图外框 | 包围组织导航小地图。真实地形、病毒群位置和镜头框继续由程序绘制；没有肺部选择功能。 | 组织导航小地图；只替换外框，保留程序绘制地图 |
| [ui_primary_button_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_primary_button_normal.png>) | 640×128 | 可点击按钮底框 | 突出主要操作：开始游戏、选择此卡、继续游戏、再来一局。建议主要确认操作共用。 | storyMode 的主操作版本、cardGet_<cardId>、cardContinue、restartBtn |
| [ui_progress_fill_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_progress_fill_normal.png>) | 768×32 | 进度显示控件 | 进度条内部填充纹理。长度由程序按照真实进度裁切，不代表固定百分比。 | 任务与阈值进度填充；长度和其他颜色由程序控制 |
| [ui_progress_track_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_progress_track_normal.png>) | 768×64 | 进度显示控件 | 任务、炎症阈值和组织损伤阈值的空槽。搭配填充条呈现当前进度，不可点击。 | taskProgressBar、inflammationBar、damageBar共用空槽 |
| [ui_scroll_thumb_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_scroll_thumb_normal.png>) | 32×256 | 可拖动控件部件 | 滚动条滑块，表示并改变设定、选卡、功能菜单、HUD或结算内容的滚动位置。 | 设定、选卡、HUD数据、功能菜单、结算滚动区 |
| [ui_secondary_button_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_secondary_button_normal.png>) | 640×128 | 可点击按钮底框 | 次要操作：返回主菜单、设定返回、恢复默认、取消点选、返回／关闭功能菜单。 | endingMenuBtn、skillCancel、skillMenuBack、skillMenuClose、resetSettings、settingsBack；也可用于cardContinue次要版本 |
| [ui_skill_row_gold_192x64.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_skill_row_gold_192x64.png>) | 192×64 | 可点击按钮底框 | 功能菜单的长条选项。随本局获得的能力显示不同内容，也承载进入／离开节点、集合／留守选项。 | skillMenu_1…6：主动技能、藏身群进出、集合／留守子菜单共用 |
| [ui_slider_thumb_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_slider_thumb_normal.png>) | 64×64 | 可拖动控件部件 | 音量滑条的拖动滑块；拖动改变数值，结束拖动保存设定。 | 五类音量滑条共用滑块 |
| [ui_slider_track_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_slider_track_normal.png>) | 768×48 | 可拖动控件部件 | 五类音量滑条的轨道：主音量、音乐、音效、环境、语音。搭配独立滑块。 | volume_master、volume_music、volume_effects、volume_ambient、volume_voice：五类音量滑条共用 |
| [ui_square_button_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_square_button_normal.png>) | 128×128 | 可点击按钮底框 | 用于小型数字／图标操作；当前主要对应默认隐藏的警戒调试等级0—6。 | cardDebugLevel_0…6；隐藏调试数字按钮 |
| [ui_swarm_button_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_swarm_button_normal.png>) | 512×128 | 可点击按钮底框 | 点击接管指定病毒群。群编号、规模及状态由程序显示；需要区分当前选中群。 | selectSwarm_<slot>：动态数量的病毒群选择按钮 |
| [ui_title_ornament_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_title_ornament_normal.png>) | 1024×256 | 装饰素材 | 游戏标题、设定／结算标题周边的装饰。标题仍用程序字体，无点击用途。 | gameTitle、设定标题、结算标题；实际中文使用程序字体 |
| [ui_toggle_thumb_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_toggle_thumb_normal.png>) | 64×64 | 可点击开关部件 | 动态背景开关的滑块；左右位置随开关状态变化。 | menuMotion：动态背景开关共用滑块 |
| [ui_toggle_track_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_toggle_track_normal.png>) | 160×80 | 可点击开关部件 | 开始界面动态背景的开关轨道。与滑块共同表达开／关。 | menuMotion：动态背景设置开关的轨道 |
| [ui_tooltip_panel_normal.png](<C:/Users/admin/Documents/病毒模拟/按钮/ui_tooltip_panel_normal.png>) | 512×256 | 提示底框 | 显示技能目标、操作失败原因和帮助说明。提示内容随状态更新，不是独立按钮。 | skillTargetPrompt、技能／操作失败提示；文字仍由程序绘制 |

`ui_skill_row_gold_192x64.png` 对应原提示词的动态功能选项长按钮。当前文件以192×64输出，仍可用于功能菜单；它不是独立技能。

## 二、UI文件夹：逐张图标用途

前9项是基础操作与界面操作；其余18项对应机制卡能力。**6项被动／规则图标只表示已获得的效果，不应新增点击技能按钮**。主动技能在获得对应卡牌后才开放。

| 图片文件 | 中文名称 | 类型 | 对应按钮／操作方式 | 实际用途 |
|---|---|---|---|---|
| [icon_ability_menu.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_ability_menu.png>) | 功能菜单 | 界面操作 | skillMenuToggle、quickMenu / V | 打开或关闭已获得主动／开关能力菜单，模拟继续运行。 |
| [icon_absorb.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_absorb.png>) | 基础吸附 | 基础操作 | absorbBtn / E | 吸附当前群附近的游离病毒，补充真实数量；基础瞬时脉冲，共享3秒冷却。 |
| [icon_back.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_back.png>) | 返回 | 界面操作 | settingsBack、skillMenuBack、endingMenuBtn | 返回上一层或主菜单；具体去向由所在页面决定。 |
| [icon_close.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_close.png>) | 取消／关闭 | 界面操作 | skillCancel、skillMenuClose | 取消技能目标选择或关闭功能菜单。 |
| [icon_menu.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_menu.png>) | 菜单／暂停 | 界面操作 | menuBtn / Esc | 打开主菜单并暂停当前局。Esc键优先取消技能点选／菜单，再返回主菜单。 |
| [icon_restart.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_restart.png>) | 再来一局 | 界面操作 | restartBtn | 结算后重新开始一局。 |
| [icon_settings.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_settings.png>) | 设定 | 界面操作 | openSettings | 进入音量和显示设定。 |
| [icon_split.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_split.png>) | 分离 | 基础操作 | splitBtn / 空格 | 将受控群分离出新群，需要满足规模、上限与冷却。 |
| [icon_switch_swarm.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_switch_swarm.png>) | 切群 | 基础操作 | switchBtn / Tab | 在不同病毒群之间循环切换控制。 |
| [icon_cluster_dispatch.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_cluster_dispatch.png>) | 集群调度 | 可操作技能图标 | V → 集群调度 → 集合或留守 | 集合或留守；锚定和藏身群不参加。留守遇险或目标失效时解除。 |
| [icon_debris_camouflage.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_debris_camouflage.png>) | 残骸伪装 | 被动／规则标识〔不点击〕 | 获得卡牌后自动应用，在被动状态栏展示；不是点击按钮 | 未清理残骸旁停留降低远距离识别；移动、感染或掩护清除时解除。 |
| [icon_discrete_recall.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_discrete_recall.png>) | 离散回收 | 可操作技能图标 | V → 离散回收；立即启动牵引 | 6秒内牵引附近游离病毒；真实吸收才增加质量。 |
| [icon_emergency_dash.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_emergency_dash.png>) | 紧急冲刺 | 可操作技能图标 | quickDash / Shift；获得后显示独立快捷按钮 | 沿最近移动方向冲刺0.5秒，不穿墙、不无敌。 |
| [icon_infection_trail.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_infection_trail.png>) | 感染拖尾 | 可操作技能图标 | V → 感染拖尾；切换开启／关闭 | 每主动移动1.5米投入1颗真实游离病毒，低量自动关闭。 |
| [icon_local_flow.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_local_flow.png>) | 局部转流 | 可操作技能图标 | V → 局部转流 → 点选流向位置 | 临时改变附近真实流向10秒；群和游离病毒共同受影响。 |
| [icon_membrane_glide.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_membrane_glide.png>) | 贴膜滑行 | 可操作技能图标 | V → 贴膜滑行 → 点选合法细胞；已滑行时再次操作可解除 | 沿附近细胞外围切向移动，继续原有接触感染。 |
| [icon_merge_seed.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_merge_seed.png>) | 合并播种 | 可操作技能图标 | V → 合并播种；切换开启／关闭，获得后默认开启 | 默认开启：真实合并投入10%质量，最多6颗，冷却20秒。 |
| [icon_node_cover.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_node_cover.png>) | 节点包覆 | 可操作技能图标 | V → 节点包覆 → 点选合法感染节点 | 投入4颗，抵挡一次节点攻击；每节点一局一次。 |
| [icon_node_hide.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_node_hide.png>) | 寄居藏身 | 可操作技能图标 | V → 寄居藏身 → 当前群进入节点 → 点选合法节点；子菜单也可让隐藏群离开 | 进入存活感染节点，可主动退出；节点破坏损失半数。 |
| [icon_node_takeover.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_node_takeover.png>) | 节点接管 | 可操作技能图标 | V → 节点接管 → 点选合法感染节点 | 将本批5颗真实产出组织为分群，或预约下一批。 |
| [icon_rupture_spread.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_rupture_spread.png>) | 破裂散播 | 被动／规则标识〔不点击〕 | 获得卡牌后自动应用，在被动状态栏展示；不是点击按钮 | 免疫破坏生产节点时散出一半真实待释放预算。 |
| [icon_shed_decoy.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_shed_decoy.png>) | 脱落诱饵 | 可操作技能图标 | quickDecoy / F；获得后显示独立快捷按钮 | 投入4颗，留下可回收、可清除的真实诱饵。 |
| [icon_swarm_anchor.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_swarm_anchor.png>) | 群体锚定 | 可操作技能图标 | V → 群体锚定 → 点选合法病毒群；手动移动解除 | 固定指定群抵抗流动，仍可感染吸收；手动移动解除。 |
| [icon_swarm_capacity_4.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_swarm_capacity_4.png>) | 分裂扩容 | 被动／规则标识〔不点击〕 | 获得卡牌后自动应用，在被动状态栏展示；不是点击按钮 | 群体上限2→4；仍需12病毒才可分裂。 |
| [icon_swarm_capacity_6.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_swarm_capacity_6.png>) | 多群扩容 | 被动／规则标识〔不点击〕 | 获得卡牌后自动应用，在被动状态栏展示；不是点击按钮 | 群体上限4→6；前置分裂扩容。 |
| [icon_swarm_local_brain.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_swarm_local_brain.png>) | 分群小脑 | 被动／规则标识〔不点击〕 | 获得卡牌后自动应用，在被动状态栏展示；不是点击按钮 | 未控制群局部感染、避敌、补充与探索；玩家接管优先。 |
| [icon_tail_preserve.png](<C:/Users/admin/Documents/病毒模拟/UI/icon_tail_preserve.png>) | 断尾保全 | 被动／规则标识〔不点击〕 | 获得卡牌后自动应用，在被动状态栏展示；不是点击按钮 | 免疫致命攻击时保留最多2颗并短距脱离；每局一次。 |

“基础吸附”是E键的基础脉冲；“离散回收”是获得卡牌后启动的6秒牵引，两者用途接近但不是同一个按钮。“分离”创建新群；“分裂扩容／多群扩容”提高群上限，它们是规则效果，不能代替分离按钮。

## 三、游戏中每个按钮的用途

共28类按钮：7类菜单按钮＋21类HUD按钮模板，包含默认隐藏的调试项。群选择、功能槽、卡牌选择和警戒等级按钮会动态生成多个实例。底框和图标是推荐搭配；保留代码中的稳定ID即可定位用途与回调。

| 按钮名称 | 所在界面 | ID／标记 | 点击后用途 | 推荐底框 | 推荐图标 | 源码位置 |
|---|---|---|---|---|---|---|
| 开始／继续游戏 | 主菜单 | `storyMode` | 无当前局时进入黑屏转场并创建病毒玩法；有当前局时恢复本次运行保存的局。 | ui_primary_button_normal.png 或 ui_menu_button_normal.png | — | [MainMenu.lua:139](<C:/Users/admin/Documents/病毒模拟/scripts/UI/MainMenu.lua:139>) |
| 无尽模式 | 主菜单 | `endlessMode` | 暂未开放，按钮禁用；不是第二种已经能游玩的模式。 | ui_menu_button_normal.png | — | [MainMenu.lua:142](<C:/Users/admin/Documents/病毒模拟/scripts/UI/MainMenu.lua:142>) |
| 设定 | 主菜单 | `openSettings` | 打开音量、界面缩放、帧率和动态背景设定。 | ui_menu_button_normal.png | icon_settings.png | [MainMenu.lua:150](<C:/Users/admin/Documents/病毒模拟/scripts/UI/MainMenu.lua:150>) |
| 制作名单 | 主菜单 | `openCredits` | 打开滚动制作名单；名单页面支持点击或按键返回。 | ui_menu_button_normal.png | — | [MainMenu.lua:153](<C:/Users/admin/Documents/病毒模拟/scripts/UI/MainMenu.lua:153>) |
| 退出 | 主菜单 | `exitGame` | 关闭游戏。 | ui_menu_button_normal.png | — | [MainMenu.lua:156](<C:/Users/admin/Documents/病毒模拟/scripts/UI/MainMenu.lua:156>) |
| 恢复默认 | 设定 | `resetSettings` | 恢复默认音量、显示选项及动态背景设置。 | ui_secondary_button_normal.png | — | [MainMenu.lua:240](<C:/Users/admin/Documents/病毒模拟/scripts/UI/MainMenu.lua:240>) |
| 返回 | 设定 | `settingsBack` | 保存当前设定并回到主菜单。 | ui_secondary_button_normal.png | icon_back.png | [MainMenu.lua:243](<C:/Users/admin/Documents/病毒模拟/scripts/UI/MainMenu.lua:243>) |
| 基础吸附 | 操控病毒 HUD | `absorbBtn` | 吸附附近游离病毒以补充当前群。全群共享3秒冷却；与“离散回收”技能不同。 | ui_action_button_normal.png | icon_absorb.png | [HUD.lua:362](<C:/Users/admin/Documents/病毒模拟/scripts/UI/HUD.lua:362>) |
| 分离 | 操控病毒 HUD | `splitBtn` | 把受控病毒群分离出新群；受规模、群上限和冷却约束，当前至少12颗且冷却8秒。 | ui_action_button_normal.png | icon_split.png | [HUD.lua:367](<C:/Users/admin/Documents/病毒模拟/scripts/UI/HUD.lua:367>) |
| 切群 | 操控病毒 HUD | `switchBtn` | 循环切换当前受控病毒群。 | ui_action_button_normal.png | icon_switch_swarm.png | [HUD.lua:372](<C:/Users/admin/Documents/病毒模拟/scripts/UI/HUD.lua:372>) |
| 菜单／暂停 | 操控病毒 HUD | `menuBtn` | 暂停当前局并打开主菜单；通过继续游戏恢复。 | ui_action_button_normal.png | icon_menu.png | [HUD.lua:377](<C:/Users/admin/Documents/病毒模拟/scripts/UI/HUD.lua:377>) |
| 指定群选择 | 操控病毒 HUD | `selectSwarm_` | 直接接管点击的存活群；动态生成多个按钮。槽编号不等于真实群ID，显示文字才是真实群编号。 | ui_swarm_button_normal.png | — | [HUD.lua:848](<C:/Users/admin/Documents/病毒模拟/scripts/UI/HUD.lua:848>) |
| 功能菜单〔能力栏入口〕 | 能力栏 | `skillMenuToggle` | 打开／关闭V功能菜单，与快捷栏入口操作相同。 | ui_action_button_normal.png | icon_ability_menu.png | [SkillPanel.lua:23](<C:/Users/admin/Documents/病毒模拟/scripts/UI/SkillPanel.lua:23>) |
| 功能菜单〔快捷栏入口〕 | 快捷栏 | `quickMenu` | 打开／关闭V功能菜单。技能选择菜单不会暂停模拟。 | ui_action_button_normal.png | icon_ability_menu.png | [SkillPanel.lua:44](<C:/Users/admin/Documents/病毒模拟/scripts/UI/SkillPanel.lua:44>) |
| 紧急冲刺 | 快捷栏 | `quickDash` | 获得该卡后显示；沿最近主动移动方向立即冲刺。没有有效方向或处于冷却时不能使用。 | ui_action_button_normal.png | icon_emergency_dash.png | [SkillPanel.lua:38](<C:/Users/admin/Documents/病毒模拟/scripts/UI/SkillPanel.lua:38>) |
| 脱落诱饵 | 快捷栏 | `quickDecoy` | 获得该卡后显示；投入4颗留下真实诱饵，至少保留3颗。 | ui_action_button_normal.png | icon_shed_decoy.png | [SkillPanel.lua:41](<C:/Users/admin/Documents/病毒模拟/scripts/UI/SkillPanel.lua:41>) |
| 取消点选 | 技能目标提示 | `skillCancel` | 退出当前技能目标选择；不执行技能。 | ui_secondary_button_normal.png | icon_close.png | [SkillPanel.lua:34](<C:/Users/admin/Documents/病毒模拟/scripts/UI/SkillPanel.lua:34>) |
| 技能／子菜单选项 | V功能菜单 | `skillMenu_` | 1—6槽动态展示已获得的可操作能力；按能力进入目标点选、立即执行或开关。藏身／调度子菜单也共用这些槽。 | ui_skill_row_gold_192x64.png | 按实际能力使用对应图标 | [SkillPanel.lua:58](<C:/Users/admin/Documents/病毒模拟/scripts/UI/SkillPanel.lua:58>) |
| 返回功能菜单 | 藏身／调度子菜单 | `skillMenuBack` | 从子菜单回到V主功能菜单，不退出整套菜单。 | ui_secondary_button_normal.png | icon_back.png | [SkillPanel.lua:62](<C:/Users/admin/Documents/病毒模拟/scripts/UI/SkillPanel.lua:62>) |
| 关闭功能菜单 | V功能菜单 | `skillMenuClose` | 关闭技能菜单并取消当前选择。 | ui_secondary_button_normal.png | icon_close.png | [SkillPanel.lua:65](<C:/Users/admin/Documents/病毒模拟/scripts/UI/SkillPanel.lua:65>) |
| 选择此卡／测试获取 | 选卡／开发调试 | `cardGet_` | 正式三选一中获得点击的卡；调试中测试获取。点击会校验前置与候选资格，获得卡会提升免疫警戒。 | ui_primary_button_normal.png | — | [CardPanel.lua:107](<C:/Users/admin/Documents/病毒模拟/scripts/UI/CardPanel.lua:107>) |
| 继续游戏／关闭测试面板 | 选卡／开发调试 | `cardContinue` | 正式选卡完成后继续游戏；在调试界面关闭面板。当前三张卡揭示动画期间不能立即选择。 | ui_primary_button_normal.png 或 ui_secondary_button_normal.png | — | [CardPanel.lua:196](<C:/Users/admin/Documents/病毒模拟/scripts/UI/CardPanel.lua:196>) |
| 返回主菜单 | 结算 | `endingMenuBtn` | 结算后回到主菜单，不自动重开。继续本局会回到原结算。 | ui_secondary_button_normal.png | icon_back.png | [HUD.lua:637](<C:/Users/admin/Documents/病毒模拟/scripts/UI/HUD.lua:637>) |
| 再来一局 | 结算 | `restartBtn` | 清除当前触摸输入并创建新局，直接进入细胞玩法，不选择宿主或肺部。 | ui_primary_button_normal.png | icon_restart.png | [HUD.lua:640](<C:/Users/admin/Documents/病毒模拟/scripts/UI/HUD.lua:640>) |
| 开发调试 | HUD〔默认隐藏〕 | `cardInfoBtn` | 打开开发用卡牌／警戒调试面板。 | 复用ui_secondary_button_normal.png | — | [HUD.lua:424](<C:/Users/admin/Documents/病毒模拟/scripts/UI/HUD.lua:424>) |
| 调试触发三选一 | 开发调试〔正式隐藏〕 | `cardDebugOffer` | 将该局标为调试局并请求一轮测试三选一，不算正式六轮验收。 | 复用ui_secondary_button_normal.png | — | [CardPanel.lua:175](<C:/Users/admin/Documents/病毒模拟/scripts/UI/CardPanel.lua:175>) |
| 警戒等级0—6 | 开发调试〔正式隐藏〕 | `cardDebugLevel_` | 手动覆盖免疫警戒等级供测试，不增加卡牌获得次数。 | ui_square_button_normal.png | 程序数字 | [CardPanel.lua:188](<C:/Users/admin/Documents/病毒模拟/scripts/UI/CardPanel.lua:188>) |
| 退出警戒调试 | 开发调试〔正式隐藏〕 | `cardDebugExit` | 取消手动等级覆盖，恢复按卡牌获得次数决定的警戒。 | 复用ui_secondary_button_normal.png | — | [CardPanel.lua:193](<C:/Users/admin/Documents/病毒模拟/scripts/UI/CardPanel.lua:193>) |

### 动态菜单中的具体选项

| 选项 | 操作结果 | 图标 |
|---|---|---|
| 群体锚定、离散回收、局部转流、贴膜滑行、节点包覆、节点接管、感染拖尾、合并播种 | 执行对应技能；目标技能点选合法对象，开关技能切换状态 | 使用同名能力图标 |
| 当前群：进入节点 | 进入藏身点选，选合法感染节点后把当前群藏入 | icon_node_hide.png |
| 群N：离开节点 | 让指定隐藏群主动退出节点；多个隐藏群分别显示 | icon_node_hide.png＋程序群编号 |
| 集合 | 向当前受控群集合；锚定与藏身群不参与 | icon_cluster_dispatch.png＋“集合”文字 |
| 留守 | 下达留守指令；锚定与藏身群不参与，遇险或目标失效时解除 | icon_cluster_dispatch.png＋“留守”文字 |

功能菜单1—6槽按本局能力获得顺序呈现；不是固定的“1永远锚定、2永远回收”。独立快捷按钮只包括已获得的冲刺与诱饵，其余可操作能力由V菜单使用。

## 四、设定控件用途

| 控件 | 当前ID | 用途 | 使用图片 |
|---|---|---|---|
| 主音量 | volume_master | 调整所有音频的总音量 | ui_slider_track_normal.png＋ui_slider_thumb_normal.png |
| 音乐音量 | volume_music | 调整配乐音量 | 同上 |
| 音效音量 | volume_effects | 调整操作／玩法音效音量 | 同上 |
| 环境音量 | volume_ambient | 调整环境声分类音量 | 同上 |
| 语音音量 | volume_voice | 调整语音分类音量 | 同上 |
| 界面缩放 | uiScale | 85%／100%／115% | ui_dropdown_field_normal.png |
| 帧率上限 | frameLimit | 30／60／120 FPS | ui_dropdown_field_normal.png |
| 动态背景 | menuMotion | 打开／关闭开始界面背景动画 | ui_toggle_track_normal.png＋ui_toggle_thumb_normal.png |

音量滑条、下拉选择框和开关均是交互控件，但不属于28类按钮模板。分辨率目前只显示实际窗口尺寸，不提供分辨率切换按钮。

## 五、状态与结局说明

- 带`_normal`后缀的图片是普通外观；使用时还需表现悬停、按下、禁用、选中或技能开启状态。可由程序颜色／描边表达，也可后续使用同尺寸状态图。`ui_skill_row_gold_192x64.png`与27张图标虽然未用`_normal`命名，也不代表自带所有状态。
- 不能将快捷键、冷却秒数、成本、群编号和病毒数量烘焙进图片；它们都会随游戏变化。
- 结局鸟仅通过视频呈现，不需要鸟静态图。`ui_ending_video_frame_normal.png`只是视频装饰框，当前不是播放、跳过或重播按钮；视频播放器尚未接入。
- 无尽模式暂未开放；开发调试按钮默认隐藏。被动能力没有主动按钮；数据面板、标题装饰、小地图外框、进度条与提示底框也不代表点击操作。

本文已覆盖当前两个文件夹全部51张PNG，文件名及尺寸按实际读取；按钮作用按当前源码核对。
