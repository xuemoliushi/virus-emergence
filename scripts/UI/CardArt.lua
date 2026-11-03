-- 按桌面当前文件中的机制名称精确匹配；原文件名与 SHA-256 保存在 mapping.json。
---@class CardArtMetrics
---@field width number
---@field gap number
---@field titleSize number
---@field descriptionSize number

---@class CardArtAPI
---@field paths table<string,string>
---@field title table
---@field description table
---@field Metrics fun(width:number,height:number,formal:boolean):CardArtMetrics
local Art = {}
Art.paths = {
    swarm_anchor = "image/mechanism_cards/swarm_anchor.png",
    discrete_recall = "image/mechanism_cards/discrete_recall.png",
    emergency_dash = "image/mechanism_cards/emergency_dash.png",
    shed_decoy = "image/mechanism_cards/shed_decoy.png",
    debris_camouflage = "image/mechanism_cards/debris_camouflage.png",
    local_flow = "image/mechanism_cards/local_flow.png",
    swarm_capacity_4 = "image/mechanism_cards/swarm_capacity_4.png",
    swarm_local_brain = "image/mechanism_cards/swarm_local_brain.png",
    node_hide = "image/mechanism_cards/node_hide.png",
    membrane_glide = "image/mechanism_cards/membrane_glide.png",
    node_cover = "image/mechanism_cards/node_cover.png",
    tail_preserve = "image/mechanism_cards/tail_preserve.png",
    node_takeover = "image/mechanism_cards/node_takeover.png",
    infection_trail = "image/mechanism_cards/infection_trail.png",
    swarm_capacity_6 = "image/mechanism_cards/swarm_capacity_6.png",
    cluster_dispatch = "image/mechanism_cards/cluster_dispatch.png",
    merge_seed = "image/mechanism_cards/merge_seed.png",
    rupture_spread = "image/mechanism_cards/rupture_spread.png",
}
-- 约 3:4 卡图的两块净留白，比例坐标随图片完整缩放，不裁切。
Art.title = { left = "16%", top = "5.2%", width = "68%", height = "6.4%" }
Art.description = { left = "13%", top = "65.5%", width = "74%", height = "23%" }

---@param width number 可用视口宽度（UI 基准像素）
---@param height number 可用视口高度
---@param formal boolean
---@return CardArtMetrics
function Art.Metrics(width, height, formal)
    local gap = width < 700 and 12 or 24
    local cardWidth = math.max(formal and 112 or 160, math.min(240, math.floor((width - gap * 2) / 3)))
    if formal then
        cardWidth = math.max(112, math.min(cardWidth, math.floor(math.max(86, height - 44) * 0.75)))
    else cardWidth = math.min(cardWidth, 260) end
    return {
        width = cardWidth, gap = gap,
        titleSize = math.max(8, math.min(20, cardWidth * 0.067)),
        descriptionSize = math.max(8, math.min(15, cardWidth * 0.052)),
    }
end

return Art
