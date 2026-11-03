**病毒涌现：新版 UI 清单与按钮换皮定位（2026-10-13）**

**目标流程：开始菜单 → 黑屏转场 → 操控病毒 → 结局视频，鸟仅在视频中出现。视频播放尚未接入。**

小鼠外观、完整解剖、肺详情、侵入区域选择、开局参数确认，以及游戏中的宿主观察入口均已从运行界面移除。M 键不再切换观察；滚轮只在细胞场景缩放。鸟只在胜利／失败结算遮罩中显示，重开后随遮罩隐藏。

**标记约定**

- `HUD_BUTTON:<id>`：HUD 树中的全部按钮创建位置，包括技能／卡牌子模块和默认隐藏的调试按钮。
- `UI_BUTTON:<id>`：开始菜单／设定界面的按钮。
- `HUD_BUTTON_STYLE`：HUD.lua 中的基础玩法／结算按钮共用样式函数。
- `HUD_CONTROL:joystickPanel`：虚拟摇杆，属于拖动控件。
- `ENDING_ART:endingBird` 与 `ENDING_ART`：结局鸟展示位置和图片配置。

标记写在 Lua 注释中，不会作为文字显示给玩家。按钮 ID 稳定，动态按钮的编号／卡名／成本／冷却仍由现有刷新代码更新。

**【HUD按钮】全部创建位置**

以下每行是一种按钮或动态按钮模板，并非同时显示的按钮数量。表格包含 21 个模板，其中调试入口、调试选卡触发、警戒等级及退出警戒调试在正式玩法中隐藏。

| 按钮名称 | ID／标记 | 用途与显示规则 | 创建位置 |
|---|---|---|---|
| 【HUD按钮】基础吸附 | `absorbBtn` | 基础吸附；含共享冷却文字 | [HUD.lua:356](<C:/Users/admin/Documents/病毒模拟/scripts/UI/HUD.lua:356>) |
| 【HUD按钮】分离 | `splitBtn` | 病毒群分离 | [HUD.lua:361](<C:/Users/admin/Documents/病毒模拟/scripts/UI/HUD.lua:361>) |
| 【HUD按钮】切群 | `switchBtn` | 循环切群 | [HUD.lua:366](<C:/Users/admin/Documents/病毒模拟/scripts/UI/HUD.lua:366>) |
| 【HUD按钮】菜单／暂停 | `menuBtn` | 暂停并打开开始菜单；后续可替换为美术菜单按钮。 | [HUD.lua:371](<C:/Users/admin/Documents/病毒模拟/scripts/UI/HUD.lua:371>) |
| 【HUD按钮】开发调试入口 | `cardInfoBtn` | 开发调试，默认隐藏 | [HUD.lua:418](<C:/Users/admin/Documents/病毒模拟/scripts/UI/HUD.lua:418>) |
| 【HUD按钮】结算返回主菜单 | `endingMenuBtn` | 结算后返回开始菜单。 | [HUD.lua:622](<C:/Users/admin/Documents/病毒模拟/scripts/UI/HUD.lua:622>) |
| 【HUD按钮】再来一局 | `restartBtn` | 直接重开细胞玩法，不选择宿主或肺部起点。 | [HUD.lua:625](<C:/Users/admin/Documents/病毒模拟/scripts/UI/HUD.lua:625>) |
| 【HUD按钮】病毒群选择按钮 | `selectSwarm_` | 动态群体点选；编号、规模、状态随模拟更新 | [HUD.lua:827](<C:/Users/admin/Documents/病毒模拟/scripts/UI/HUD.lua:827>) |
| 【HUD按钮】能力栏功能菜单 | `skillMenuToggle` | 能力栏功能菜单入口 | [SkillPanel.lua:23](<C:/Users/admin/Documents/病毒模拟/scripts/UI/SkillPanel.lua:23>) |
| 【HUD按钮】取消目标选择 | `skillCancel` | 取消技能目标选择 | [SkillPanel.lua:34](<C:/Users/admin/Documents/病毒模拟/scripts/UI/SkillPanel.lua:34>) |
| 【HUD按钮】紧急冲刺 | `quickDash` | 紧急冲刺快捷按钮 | [SkillPanel.lua:38](<C:/Users/admin/Documents/病毒模拟/scripts/UI/SkillPanel.lua:38>) |
| 【HUD按钮】脱落诱饵 | `quickDecoy` | 脱落诱饵快捷按钮 | [SkillPanel.lua:41](<C:/Users/admin/Documents/病毒模拟/scripts/UI/SkillPanel.lua:41>) |
| 【HUD按钮】快捷栏功能菜单 | `quickMenu` | 快捷栏功能菜单入口 | [SkillPanel.lua:44](<C:/Users/admin/Documents/病毒模拟/scripts/UI/SkillPanel.lua:44>) |
| 【HUD按钮】功能选择槽／子菜单选项 | `skillMenu_` | 1—6动态功能槽，共用藏身/调度子菜单 | [SkillPanel.lua:58](<C:/Users/admin/Documents/病毒模拟/scripts/UI/SkillPanel.lua:58>) |
| 【HUD按钮】返回功能菜单 | `skillMenuBack` | 子菜单返回主功能菜单 | [SkillPanel.lua:62](<C:/Users/admin/Documents/病毒模拟/scripts/UI/SkillPanel.lua:62>) |
| 【HUD按钮】关闭功能菜单 | `skillMenuClose` | 关闭功能菜单 | [SkillPanel.lua:65](<C:/Users/admin/Documents/病毒模拟/scripts/UI/SkillPanel.lua:65>) |
| 【HUD按钮】选择此卡／测试获取 | `cardGet_` | 每张卡的选择按钮；调试模式为测试获取 | [CardPanel.lua:38](<C:/Users/admin/Documents/病毒模拟/scripts/UI/CardPanel.lua:38>) |
| 【HUD按钮】调试触发三选一 | `cardDebugOffer` | 调试触发三选一，正式选卡隐藏 | [CardPanel.lua:52](<C:/Users/admin/Documents/病毒模拟/scripts/UI/CardPanel.lua:52>) |
| 【HUD按钮】调试警戒等级 | `cardDebugLevel_` | 警戒等级0—6，正式选卡隐藏 | [CardPanel.lua:65](<C:/Users/admin/Documents/病毒模拟/scripts/UI/CardPanel.lua:65>) |
| 【HUD按钮】退出警戒调试 | `cardDebugExit` | 退出警戒调试，正式选卡隐藏 | [CardPanel.lua:70](<C:/Users/admin/Documents/病毒模拟/scripts/UI/CardPanel.lua:70>) |
| 【HUD按钮】继续游戏／关闭测试面板 | `cardContinue` | 获得卡牌后继续游戏／关闭调试面板 | [CardPanel.lua:73](<C:/Users/admin/Documents/病毒模拟/scripts/UI/CardPanel.lua:73>) |

功能菜单的 1—6 槽按本局获得顺序显示；同一槽也用于“当前群进入节点／各隐藏群离开节点”以及“集合／留守”子菜单。它们已经由 `skillMenu_` 标记覆盖，不需要另做一套点击逻辑。

`selectSwarm_1…N` 按群体槽位生成，编号文字才是真实群 ID；`cardGet_<cardId>` 为每张卡生成，正式选卡只显示本轮候选。`cardDebugLevel_0…6` 为调试警戒等级按钮。

**技能按钮内容对照**

| 呈现位置 | 内容名称 | 用途 |
|---|---|---|
| 独立快捷按钮 | 紧急冲刺、脱落诱饵 | 立即发动能力，显示快捷键、成本、冷却和不可用原因 |
| V 菜单动态按钮 | 群体锚定、离散回收、局部转流、寄居藏身、贴膜滑行、节点包覆、节点接管、感染拖尾、集群调度、合并播种 | 操作已获得的主动／开关能力；目标技能进入点选模式 |
| 被动能力文字栏 | 残骸伪装、分裂扩容、分群小脑、断尾保全、多群扩容、破裂散播 | 展示已获得规则、生效状态及一次性能力是否使用，不是点击按钮 |

18 张卡均使用 `cardGet_<cardId>` 的选择按钮模板，卡名、说明、稀有度和前置条件由卡牌定义提供。

**【菜单按钮】开始／设定界面**

| 按钮名称 | ID／标记 | 用途 | 创建位置 |
|---|---|---|---|
| 【菜单按钮】开始／继续游戏 | `storyMode` | 开始／继续游戏 | [MainMenu.lua:139](<C:/Users/admin/Documents/病毒模拟/scripts/UI/MainMenu.lua:139>) |
| 【菜单按钮】无尽模式 | `endlessMode` | 无尽模式，暂未开放 | [MainMenu.lua:142](<C:/Users/admin/Documents/病毒模拟/scripts/UI/MainMenu.lua:142>) |
| 【菜单按钮】设定 | `openSettings` | 打开设定 | [MainMenu.lua:150](<C:/Users/admin/Documents/病毒模拟/scripts/UI/MainMenu.lua:150>) |
| 【菜单按钮】制作名单 | `openCredits` | 制作名单 | [MainMenu.lua:153](<C:/Users/admin/Documents/病毒模拟/scripts/UI/MainMenu.lua:153>) |
| 【菜单按钮】退出 | `exitGame` | 退出游戏 | [MainMenu.lua:156](<C:/Users/admin/Documents/病毒模拟/scripts/UI/MainMenu.lua:156>) |
| 【菜单按钮】恢复默认 | `resetSettings` | 设定恢复默认。 | [MainMenu.lua:240](<C:/Users/admin/Documents/病毒模拟/scripts/UI/MainMenu.lua:240>) |
| 【菜单按钮】设定返回 | `settingsBack` | 设定返回菜单。 | [MainMenu.lua:243](<C:/Users/admin/Documents/病毒模拟/scripts/UI/MainMenu.lua:243>) |

无尽模式仍禁用并标注“暂未开放”。“继续游戏”恢复本次运行中保存的当前局，并非退出后读档。结算返回菜单后继续游戏会回到本局结算；“再来一局”才会重置世界。

**其他保留 UI：这些不是按钮**

| UI 名称 | 用途 |
|---|---|
| 开始背景、游戏标题、副标题 | 展示组织／细胞氛围和游戏名称；没有宿主鸟 |
| 菜单键盘选择高亮、暂停提示 | 提示导航方式和当前暂停状态 |
| 黑屏转场遮罩 | 菜单进入玩法时遮住世界创建过程，并阻挡转场期间操作 |
| 主／音乐／音效／环境／语音音量滑条及百分比 | 调整音量并显示数值 |
| 分辨率标签 | 显示当前窗口尺寸 |
| 界面缩放、帧率上限下拉框 | 选择85%／100%／115%和30／60／120 FPS |
| 动态背景开关、设置保存提示 | 控制菜单动画并反馈设置是否保存 |
| 制作名单滚动区、按键／点击返回提示 | 展示署名并提供返回提示，整页点击不是独立按钮 |
| 六阶段名称、任务说明、进度数字／进度条、行动提示 | 告知当前目标及完成情况 |
| 本局时间、地图种子／版本／尺寸信息 | 显示时长和地图复现信息 |
| 移动／技能快捷键说明 | 展示当前可用操作 |
| 炎症／组织损伤阈值进度、不可逆病程提示 | 显示距离胜利判定的进度 |
| 活病毒、主群／分群规模、释放病毒统计 | 展示当前病毒数量 |
| 健康／接触／潜伏／释放／耗竭／死亡细胞及感染节点统计 | 展示细胞与感染网络状态 |
| 免疫细胞数量、免疫警戒与调度提示 | 展示免疫压力变化 |
| 累计感染／释放／吸收／清除／离区失活／独立感染统计 | 展示本局累计结果 |
| 组织导航小地图 | 显示组织区域、通道、群位置和镜头视野框；不提供肺部选区 |
| 当前受控群信息、吸附范围／倍率、分群自主行为、操作失败原因 | 解释当前操控对象与可用操作 |
| 虚拟摇杆 | 触摸移动；换皮需保留拖动捕获、死区和取消事件 |
| 控制群轮廓／准星／名称、感染进度圈 | 场景内定位与感染反馈 |
| 免疫锁定／预警倒计时／危险范围 | 场景内避敌提示 |
| 技能目标提示、合法目标高亮 | 说明点选对象；只有取消按钮属于按钮 |
| 卡牌标题、稀有度、效果、前置、获得说明、警戒升级说明 | 解释候选卡与获得后的变化 |
| 结局呈现区域、状态说明 | 当前为临时鸟占位；最新需求改为结局视频，不需要鸟静态图 |
| 胜负标题、结局原因、时长与本局统计 | 解释胜负及最终统计 |

**结局视频呈现（最新需求）**

用户已确定鸟仅通过结局视频呈现，不制作鸟静态图、头像或宿主选择美术。只需复用结算按钮，并按需制作视频外围装饰框。完整可复制提示词见 [UI美术生成提示词](<C:/Users/admin/Documents/病毒模拟/docs/UI美术生成提示词_像素旧金雕花.md>)。

当前代码仍保留上一轮的 `endingBirdPlaceholder` 鸟 Emoji 和 `Config.EndingBird` 静态图片槽；它们是临时实现，不是本轮美术需求。视频播放逻辑尚未接入，本次只更新提示词和需求说明。

现有胜负规则保持为病毒导致不可逆重症／病毒群被清除；影片如何表现鸟的结局由后续视频方案确定。

**按钮换皮注意事项**

- 基础玩法和结算按钮从 `HUD_BUTTON_STYLE` 调整共用外观；技能按钮在 `SkillPanel.lua`，卡牌按钮在 `CardPanel.lua`，菜单按钮在 `MainMenu.lua`。
- 保留稳定 ID、onClick、SetDisabled 和动态 SetText；图片只负责外观。冷却数字、群编号、病毒规模和成本用程序文字显示。
- 按钮准备普通、悬停、按下、禁用状态；群选择还需要选中状态，开关技能需要开启／关闭状态。冷却信息可以叠加显示。
- 动态群按钮的选中边框由 `HUD:RefreshStrategyHighlight` 更新；技能文字由 `SkillPanel.Refresh` 更新；选卡按钮文字与禁用状态由 `CardPanel.Refresh` 更新。换皮时同时核对这些刷新入口。
- 鸟展示、数据面板、进度条、摇杆及场景提示不要误标成点击按钮。

**已移除的旧 UI**

小鼠观察按钮、细胞玩法／小鼠观察切换按钮、解剖切换、胸腔肺热点、肺详情返回、三区蒙版选择、起点参数确认、选择区域后开始、小鼠健康／呼吸／体温／体重观察面板、结算观察小鼠、观察返回结算。旧资源和未引用的历史视图文件留存，不再由主入口、GameScene 或 HUD 加载。

**验证边界**

53 份用户 Lua 语法检查通过。新鸟结局6项、菜单10项、技能界面13项、六阶段16项回归通过；这些执行真实 Lua 模块与回调，原生 UI／渲染边界使用桩。本地预览检查为 stopped／process_alive=false，未启动窗口，因此本轮不宣称视觉布局和真机输入通过。
