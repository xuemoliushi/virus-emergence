-- 离屏验证专用：真实入口按2释放，检查独立身份、局部运动及HUD。
local UI = require("urhox-libs/UI")
local Config = require("Core.Config")

V.atFrame(5, function()
    local root = assert(UI.GetRoot(), "UI根节点未创建")
    local scene = assert(root:FindById("gameScene"), "游戏画布未创建")
    local sim = scene.sim
    local world = sim.world
    HandleKeyDown("KeyDown", {
        GetInt = function() return KEY_2 end,
        GetBool = function() return false end,
    })
    V.assert(world:Counts().split == 15, "按2释放15只真实分裂体")
    V.assert(world:Counts().controlled == 15, "保留15只可控主群病毒")
    V.assert(world.stats.totalSpawned == 30, "分裂没有凭空增加出生数量")
    world.splitCooldown = 0
    HandleKeyDown("KeyDown", {
        GetInt = function() return KEY_2 end,
        GetBool = function() return true end,
    })
    V.assert(world:Counts().split == 15, "忽略按键重复事件")
    world:SetMovement(1, 0)
    for _ = 1, 120 do sim:Tick(1 / 60) end
    local split = 0
    for _, virus in ipairs(world.viruses) do
        if virus.state == "split" then
            split = split + 1
            V.assert(math.abs(virus.originX - 8) < 0.000001, "释放点不跟随主群")
            V.assert((virus.x - virus.originX)^2 + (virus.y - virus.originY)^2
                <= Config.Swarm.splitRoamRadius^2 + 0.000001, "分裂体限定局部活动")
        end
    end
    V.assert(split > 0 and world.player.x > 12, "主群离开后分裂体仍留在原区")
    V.assert(root:FindById("splitCount") ~= nil, "HUD具有独立分裂体计数")
    local positions = {}
    for _, virus in ipairs(world.viruses) do
        if virus.state == "split" then positions[virus.id] = { x = virus.x, y = virus.y } end
    end
    local alive, spawned = #world.viruses, world.stats.totalSpawned
    HandleKeyDown("KeyDown", { GetInt = function() return KEY_1 end })
    V.assert(world:Counts().split == 0, "按1召回全部存活分裂体")
    V.assert(#world.viruses == alive and world.stats.totalSpawned == spawned, "召回不生新病毒也不复活")
    local unchanged = true
    for _, virus in ipairs(world.viruses) do
        local p = positions[virus.id]
        if p then
            unchanged = unchanged and virus.x == p.x and virus.y == p.y and virus.state == "returning"
        end
    end
    V.assert(unchanged, "收拢只改意图，保持实体原位置并开始归队")
    sim:Tick(1 / 60)
    local continuous = true
    for _, virus in ipairs(world.viruses) do
        local p = positions[virus.id]
        if p then
            continuous = continuous and (virus.x - p.x)^2 + (virus.y - p.y)^2
                <= (Config.Swarm.returnSpeed / 60)^2 + 0.00000001
        end
    end
    V.assert(continuous, "召回第一步遵循速度上限，不瞬移")
    -- 排除后续环境干扰，验证移动主群的实际归队路径；接触杀伤另有回归覆盖。
    local cells, immunes = world.cells, world.immunes
    world.immunes, world.cells = {}, {}
    for _ = 1, 300 do sim:Tick(1 / 60) end
    world.cells, world.immunes = cells, immunes
    V.assert(world:Counts().returning == 0 and world:Counts().split == 0, "分裂体追上移动主群并完成归队")
    HandleKeyDown("KeyDown", { GetInt = function() return KEY_1 end })
    V.assert(world:Counts().returning == 0, "重复按1不重复生成归队实体")
    V.assert(world.stats.totalSpawned - world.stats.totalKilled == #world.viruses, "归队完成仍守恒")
    sim.timeScale = 0
    world:SetMovement(0, 0)
    scene:UpdateCamera(1)
end)

V.atFrame(100, function()
    local root = UI.GetRoot()
    local top = root:FindById("hudTopRow"):GetAbsoluteLayout()
    local bottom = root:FindById("hudBottomRow"):GetAbsoluteLayout()
    V.assert(bottom.y > top.y + top.h, "策略栏与上方实体统计不重叠")
    V.assert(root:FindById("hudContent"):GetAbsoluteLayout().h > 0, "HUD安全区高度正确")
    for _, id in ipairs({"hudSafeArea", "hudContent", "hudTopRow", "hudBottomRow", "strategyBar", "entityPanel", "splitCount"}) do
        local widget = root:FindById(id)
        local l = widget:GetAbsoluteLayout()
        print(string.format("[布局验证] %s x=%.1f y=%.1f w=%.1f h=%.1f", id, l.x, l.y, l.w, l.h))
    end
end)
