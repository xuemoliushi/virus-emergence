-- 每局卡牌账本。只持有卡牌状态，群体和免疫实体仍由 SwarmWorld 管理。
local Config = require("Core.Config")
---@class CardUnlockAPI
---@field Apply fun(world:SwarmWorld,card:table)
local Effects = require("Core.CardEffects") --[[@as CardUnlockAPI]]
local CardSystem = {}
CardSystem.__index = CardSystem
local runSerial = 0

---@param definitions? table[] 仅测试注入；运行时默认正式18张定义。
function CardSystem.New(definitions)
    local self = setmetatable({}, CardSystem)
    self:init(definitions)
    return self
end

function CardSystem:init(definitions)
    runSerial = runSerial+1
    self.runId = runSerial
    self.definitions = definitions or Config.Cards.definitions
    self.acquired, self.lastOfferedRound = {}, {}
    self.round, self.acquisitionCount, self.nextChoiceId = 0, 0, 1
    self.formalCount = 0
    ---@type table?
    self.pending = nil
    ---@type table<string, number>?
    self.weightOverride = nil
end

function CardSystem:Definition(id)
    for _, card in ipairs(self.definitions) do if card.id == id then return card end end
    return nil
end

function CardSystem:Eligibility(id, round, ignoreOfferCooldown)
    local card = self:Definition(id)
    if not card or not card.implemented then return false, "卡牌尚未实现" end
    if self.acquired[id] then return false, "本局已获得" end
    if not ignoreOfferCooldown and (round or 1) < (card.minRound or 1) then
        return false, "第"..card.minRound.."轮起开放"
    end
    for _, prerequisite in ipairs(card.prerequisites or {}) do
        if not self.acquired[prerequisite] then return false, "需要先获得“分裂扩容”" end
    end
    local offered = self.lastOfferedRound[id]
    if not ignoreOfferCooldown and offered and round <= offered + 2 then return false, "未选卡回池冷却" end
    if self.acquisitionCount >= Config.Cards.maxChoices then return false, "本局获取次数已达6次" end
    return true
end

function CardSystem:GetEligibleCards(round)
    local cards = {}
    for _, card in ipairs(self.definitions) do
        if self:Eligibility(card.id, round or self.round + 1, false) then cards[#cards+1] = card end
    end
    return cards
end

-- random 为世界的确定性随机源；没有合法稀有度时按其余合法权重补位。
function CardSystem:GrantCardChoice(reason, random)
    if self.pending then return false, "已有待选择卡牌" end
    local round = self.round + 1
    local pool = self:GetEligibleCards(round)
    if #pool < Config.Cards.offerCount then return false, "卡池配置错误：合法候选不足3张" end
    local weights = self.weightOverride or Config.Cards.rarityWeights[math.min(round, 6)]
    local offered = {}
    for _ = 1, Config.Cards.offerCount do
        local rarities, total = {}, 0
        for _, rarity in ipairs({ "COMMON", "RARE", "EPIC" }) do
            local exists = false
            for _, card in ipairs(pool) do if card.rarity == rarity then exists = true; break end end
            if exists then
                local weight = math.max(0, weights[rarity] or 0)
                rarities[#rarities+1] = { id = rarity, weight = weight }
                total = total + weight
            end
        end
        local rarity = nil
        if total > 0 then
            local roll = random() * total
            for _, entry in ipairs(rarities) do
                roll = roll - entry.weight
                if roll < 0 then rarity = entry.id; break end
            end
            rarity = rarity or rarities[#rarities].id
        end
        local indices = {}
        for i, card in ipairs(pool) do if not rarity or card.rarity == rarity then indices[#indices+1] = i end end
        local selected = indices[math.min(#indices, math.floor(random()*#indices)+1)]
        offered[#offered+1] = table.remove(pool, selected)
    end
    local choice = { id = self.runId..":"..self.nextChoiceId, round = round, reason = reason, cards = offered, mode = "formal" }
    self.nextChoiceId = self.nextChoiceId + 1
    self.pending = choice
    self.round = round
    for _, card in ipairs(offered) do self.lastOfferedRound[card.id] = round end
    return true, choice
end

function CardSystem:BeginTestChoice(cardId)
    if self.pending then return false, "已有待选择卡牌" end
    local ok, reason = self:Eligibility(cardId, self.round+1, true)
    if not ok then return false, reason end
    local choice = { id = self.runId..":"..self.nextChoiceId, mode = "test", cards = { self:Definition(cardId) } }
    self.nextChoiceId = self.nextChoiceId+1
    self.pending = choice
    return true, choice
end

-- 先检查后提交；只有经过完整校验的能力能写入账本。
function CardSystem:CommitCardChoice(choiceId, cardId, world)
    local choice = self.pending
    if not choice or choice.id ~= choiceId then return false, "选择已失效或已提交" end
    local card = nil
    for _, offered in ipairs(choice.cards) do if offered.id == cardId then card = offered; break end end
    if not card then return false, "卡牌不属于本轮候选" end
    local ok, reason = self:Eligibility(cardId, choice.round or self.round+1, true)
    if not ok then return false, reason end
    Effects.Apply(world, card)
    self.acquired[cardId] = true
    self.acquisitionCount = self.acquisitionCount+1
    if choice.mode == "formal" then self.formalCount = self.formalCount+1 end
    self.pending = nil
    world:AcquireImmuneAlert()
    world:Emit("card_acquired", { cardId = cardId, choiceId = choiceId, mode = choice.mode })
    return true, card
end

return CardSystem
