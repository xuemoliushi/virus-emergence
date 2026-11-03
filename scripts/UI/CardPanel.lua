-- 机制卡美术与横向三选一。显示读取权威状态，获取/警戒修改全部经 SimState。
local UI = require("urhox-libs/UI")
local Skin = require("UI.AssetTheme")
local Config = require("Core.Config")
local Art = require("UI.CardArt") --[[@as CardArtAPI]]
local Mobile = require("UI.MobileLayout")
local Description = require("UI.CardDescription")
local Artwork = require("UI.CardArtwork")
---@class CardPanelAPI
---@field Build fun(hud:HUD):Widget
---@field Refresh fun(hud:HUD)
---@field Layout fun(hud:HUD)
---@field BeginReveal fun(hud:HUD)
---@field ResetReveal fun(hud:HUD)
---@field UpdateReveal fun(hud:HUD,dt:number)
---@field ResetSelection fun(hud:HUD)
---@field Select fun(hud:HUD,id:string):boolean
---@field Confirm fun(hud:HUD):boolean
local Panel = {}
local function cardButton(props)
    local id=props.id or ""
    local kind=id:find("cardDebugLevel_",1,true) and "square"
        or (id:find("cardGet_",1,true) or id=="cardContinue") and "primary" or "secondary"
    return Skin.Button(props,kind)
end
local RARITY = { COMMON="普通", RARE="稀有", EPIC="史诗" }
---@type string[]
local ROMAN = { "0", "Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ", "Ⅵ" }
-- Missing-audio fallback: original WAV has 21504 samples at 44100 Hz.
local REVEAL_SECONDS = 21504 / 44100

function Panel.ResetSelection(hud)
    hud.cardSelectedId_,hud.cardHoveredId_,hud.cardSelectionChoice_=nil,nil,nil
    hud.cardConfirming_=false
end

local function offered(pending,id)
    if not pending then return false end
    for _,card in ipairs(pending.cards) do if card.id==id then return true end end
    return false
end

function Panel.UpdateCardVisual(hud,id)
    local art=hud.root and hud.root:FindById("cardArt_"..id)
    if not art then return end
    local pending=hud.sim.cards.pending
    local formal=pending and pending.mode=="formal" and offered(pending,id)
    local selected=formal and hud.cardSelectedId_==id
    local hovered=formal and hud.cardHoveredId_==id and hud.cardRevealElapsed_==nil
    local signature=tostring(formal)..":"..tostring(selected)..":"..tostring(hovered)
    if art.cardFeedbackSignature_==signature then return end
    art.cardFeedbackSignature_=signature
    art:SetStyle{
        scale=hovered and 1.035 or selected and 1.02 or 1,
        translateY=hovered and -6 or 0,
        borderWidth=selected and 2 or hovered and 1 or 0,
        borderColor=selected and {255,204,113,255} or {211,163,93,200},
        shadowBlur=selected and 28 or hovered and 18 or 0,
        shadowColor=selected and {255,184,65,190} or {230,166,68,110},
    }
    local box=hud.root:FindById("cardBox_"..id)
    if box then box:SetStyle{zIndex=hovered and 2 or selected and 1 or 0} end
    local mark=hud.root:FindById("cardSelection_"..id) --[[@as Label?]]
    if mark then
        mark:SetVisible(formal==true)
        mark:SetText(selected and "✓ 已选中" or hovered and "点击选择" or " ")
        mark:SetStyle{fontColor=selected and Skin.colors.gold or Skin.colors.muted}
    end
end

function Panel.Select(hud,id)
    local pending=hud.sim.cards.pending
    if not hud.cardInfoShown_ or hud.cardRevealElapsed_~=nil or hud.cardConfirming_
        or not pending or pending.mode~="formal" or hud.sim.ending or not offered(pending,id) then return false end
    if hud.cardSelectedId_~=id then
        local detail=hud.root and hud.root:FindById("cardSelectedDetail") --[[@as ScrollView?]]
        if detail then detail:SetScroll(0,0) end
    end
    hud.cardSelectedId_,hud.cardSelectionChoice_=id,pending.id
    hud.cardTestError_=nil
    Panel.Refresh(hud)
    return true
end

function Panel.Confirm(hud)
    local pending=hud.sim.cards.pending
    if not hud.cardInfoShown_ or hud.cardConfirming_ or hud.cardRevealElapsed_~=nil
        or not pending or pending.mode~="formal" or pending.id~=hud.cardSelectionChoice_
        or not offered(pending,hud.cardSelectedId_) then return false end
    hud.cardConfirming_=true
    local ok,result=hud.sim:CommitCardChoice(pending.id,hud.cardSelectedId_)
    if ok then
        -- Commit and resume within one UI action: there is no intermediate notice screen.
        hud:CloseCardInfo()
    else hud.cardTestError_=tostring(result) end
    hud.cardConfirming_=false
    Panel.Refresh(hud)
    return ok==true
end

---@param hud HUD
function Panel.ResetReveal(hud)
    Artwork.Cancel(hud.cardArtwork_)
    hud.cardArtwork_=nil
    hud.cardRevealStarted_=false
    hud.cardRevealElapsed_, hud.cardRevealPlayback_, hud.cardRevealChoice_ = nil, nil, nil
    local deck = hud.root and hud.root:FindById("cardDeck")
    if deck then deck:SetVisible(true);deck:SetStyle { opacity = 1 } end
    local loading=hud.root and hud.root:FindById("cardLoadingStatus")
    if loading then loading:SetVisible(false) end
end

---@param hud HUD
function Panel.BeginReveal(hud)
    local pending = hud.sim.cards.pending
    if not pending then return end
    Panel.ResetReveal(hud)
    Panel.ResetSelection(hud)
    Description.SetBrief(hud,hud.cardBriefText_==true)
    hud.cardRevealElapsed_, hud.cardRevealPlayback_, hud.cardRevealChoice_ = 0, nil, pending.id
    hud.cardArtwork_=Artwork.New(pending.cards)
    local deck = hud.root and hud.root:FindById("cardDeck")
    if deck then deck:SetVisible(false);deck:SetStyle { opacity = 0 } end
    local loading=hud.root and hud.root:FindById("cardLoadingStatus")
    if loading then loading:SetVisible(true) end
    Panel.Refresh(hud)
end

---@param hud HUD
---@param dt number
function Panel.UpdateReveal(hud, dt)
    if hud.cardRevealElapsed_ == nil then return end
    local pending = hud.sim.cards.pending
    if not hud.cardInfoShown_ or not pending or pending.id ~= hud.cardRevealChoice_ then
        Panel.ResetReveal(hud)
        return
    end
    Artwork.Update(hud.cardArtwork_,dt)
    if hud.cardArtwork_ and not hud.cardArtwork_.ready then return end
    if not hud.cardRevealStarted_ then
        hud.cardRevealStarted_=true
        local deck=hud.root and hud.root:FindById("cardDeck")
        if deck then deck:SetVisible(true) end
        local loading=hud.root and hud.root:FindById("cardLoadingStatus")
        if loading then loading:SetVisible(false) end
        if hud.onCardChoiceShown then hud.cardRevealPlayback_=hud.onCardChoiceShown() end
        return -- All cards start at alpha zero on this same frame.
    end
    local playback = hud.cardRevealPlayback_
    local duration = playback and playback.duration or REVEAL_SECONDS
    local elapsed = hud.cardRevealElapsed_ + math.max(0,math.min(.1,dt))
    -- Suspended/muted audio must not leave the paused choice locked forever.
    if playback then elapsed=math.max(elapsed,playback.position()) end
    -- One shared audio cursor controls the whole card row, independent of paused simulation.
    hud.cardRevealElapsed_ = math.max(hud.cardRevealElapsed_, elapsed)
    local t = duration > 0 and math.min(1, hud.cardRevealElapsed_ / duration) or 1
    local deck = hud.root and hud.root:FindById("cardDeck")
    if deck then deck:SetStyle { opacity = t * t * (3 - 2 * t) } end
    if t >= 1 then
        Panel.ResetReveal(hud)
        Panel.Refresh(hud)
    end
end

local function label(props)
    props.width,props.whiteSpace,props.wordBreak="100%","normal","break-word"
    props.flexShrink,props.fontColor=0,props.fontColor or Config.Palette.textMain
    props.fontSize=props.fontSize or 14
    return UI.Label(props)
end

local INK = { 241, 232, 214, 255 }

local function artText(id, text, zone, size)
    return UI.Label {
        id = id, text = text, position = "absolute", left = zone.left, top = zone.top,
        width = zone.width, height = zone.height, textAlign = "center", verticalAlign = "middle",
        whiteSpace = "normal", wordBreak = "break-word", lineHeight = 1.3,
        fontSize = size, minFontSize = 8, fontColor = INK, pointerEvents = "none",
    }
end

local function cardBox(hud, card, prerequisiteText)
    local id = card.id
    local path = Art.paths[id]
    local description = card.desc
    if #(card.prerequisites or {}) > 0 then description = description .. "\n" .. prerequisiteText end
    local layers = {}
    if not path then
        -- 没有已确认配图的机制使用中性框，不将数字编号当作机制顺序。
        for _, zone in ipairs({ Art.title, { left="9%",top="15%",width="82%",height="44%" }, Art.description }) do
            layers[#layers + 1] = UI.Panel {
                position="absolute",left=zone.left,top=zone.top,width=zone.width,height=zone.height,
                borderWidth=1,borderColor={110,105,130,180},backgroundColor={10,8,18,255},pointerEvents="none",
            }
        end
        layers[#layers + 1] = artText("cardNeutral_"..id, RARITY[card.rarity].."\n"..card.kind,
            { left="15%",top="27%",width="70%",height="20%" }, 15)
    end
    layers[#layers + 1] = artText("cardTitle_"..id, card.name, Art.title, 20)
    local full,brief=Description.Build(hud,id,description)
    layers[#layers+1]=full
    layers[#layers+1]=brief
    return UI.Panel {
        id="cardBox_"..id,width=240,gap=6,flexShrink=0,pointerEvents="auto",
        onPointerEnter=function()
            if hud.cardRevealElapsed_~=nil then return end
            hud.cardHoveredId_=id;Panel.UpdateCardVisual(hud,id)
        end,
        onPointerLeave=function()
            if hud.cardHoveredId_==id then hud.cardHoveredId_=nil end
            Panel.UpdateCardVisual(hud,id)
        end,
        onClick=function(_,event)
            if event and not event:IsPrimaryAction() then return end
            Panel.Select(hud,id)
        end,
        children={
            UI.Panel {
                id="cardArt_"..id,width="100%",aspectRatio=0.75,backgroundImage=path,
                backgroundFit="contain",backgroundColor=not path and {17,13,29,255} or false,
                borderWidth=not path and 2 or 0,borderColor={104,97,126,255},
                overflow="hidden",pointerEvents="box-none",children=layers,
                transition="scale 0.18s easeInOut, translateY 0.18s easeInOut, borderWidth 0.18s easeInOut, borderColor 0.18s easeInOut, shadowBlur 0.18s easeInOut, shadowColor 0.18s easeInOut",
            },
            label{id="cardSelection_"..id,text=" ",height=20,fontSize=12,textAlign="center",visible=false,pointerEvents="none"},
            label{id="cardRarity_"..id,text=RARITY[card.rarity].." · "..card.kind,fontSize=11,
                textAlign="center",fontColor=Config.Palette.textDim},
            label{id="cardState_"..id,text="未获得",fontSize=11,textAlign="center"},
            -- [HUD_BUTTON:cardGet_] 正式三选一仍由 SimState 校验；调试入口独立保留。
            cardButton{id="cardGet_"..id,text="测试获取",width="100%",height=52,
                borderRadius=3,backgroundColor={58,44,67,255},hoverBackgroundColor={93,68,96,255},
                textColor=INK,onClick=function(_,event)
                    if event and not event:IsPrimaryAction() then return end
                    if hud.cardRevealElapsed_ ~= nil then return end
                    local pending=hud.sim.cards.pending
                    local ok,result
                    if pending and pending.mode=="formal" then
                        Panel.Select(hud,id);return
                    else ok,result=hud.sim:AcquireTestCard(id) end
                    if not ok then hud.cardTestError_=tostring(result) end
                    Panel.Refresh(hud)
                end},
        },
    }
end

-- Tight, balanced bands keep cards centered without a tall empty footer.
function Panel.Layout(hud)
    if not hud.root then return end
    local viewport=hud.root:FindById("cardDeckViewport")
    local deck=hud.root:FindById("cardDeck")
    local safe=hud.root:FindById("cardSafeArea")
    local frame=hud.root:FindById("cardPanelFrame")
    if not viewport or not deck or not safe or not frame then return end
    local rect,area=viewport:GetLayout(),safe:GetLayout()
    if rect.w<=0 or rect.h<=0 or area.w<=0 or area.h<=0 then return end
    local pending=hud.sim.cards.pending
    local formal=(pending and pending.mode=="formal") or (hud.sim.cardNotice and hud.sim.cardNotice.formal) or false
    local function inset(edge)
        return safe.props[edge] or safe.props.padding or 0
    end
    local usableH=area.h-inset('paddingTop')-inset('paddingBottom')
    local usableW=area.w-inset('paddingLeft')-inset('paddingRight')
    local compact=usableH<540
    local padding=formal and (compact and 8 or 16) or 24
    local band=formal and (compact and 52 or 68) or 0
    local touch=Mobile.IsTouch(hud)
    local detailBand=formal and touch and (usableH>=420 and 84 or usableH>=280 and 56 or 0) or 0
    local footerBand=formal and 48 or 0
    local gap=compact and 4 or 8
    local deckHeight=formal and math.min(392,math.max(24,usableH-24-2*padding-band-footerBand-detailBand-3*gap)) or math.max(160,usableH*.7)
    local availableWidth=math.min(1000,usableW*.94)-2*padding
    local metrics=Art.Metrics(formal and math.max(1,availableWidth-32) or rect.w,formal and deckHeight or rect.h,formal)
    local count=pending and #pending.cards or 1
    local rowWidth=count*metrics.width+(count-1)*metrics.gap
    local rowHeight=metrics.width/.75+26
    if formal then deckHeight=math.min(deckHeight,rowHeight+12) end
    local signature=table.concat({usableW,usableH,metrics.width,metrics.gap,tostring(formal),tostring(touch),count},":")
    if deck.cardLayoutSignature_==signature then return end
    deck.cardLayoutSignature_=signature
    local frameHeight=2*padding+band+footerBand+detailBand+3*gap+deckHeight
    frame:SetStyle{width=formal and math.min(usableW*.94,rowWidth+2*padding+32) or "96%",
        maxWidth=formal and 1000 or 1200,height=formal and frameHeight or "92%",flexShrink=0,
        translateY=formal and -math.min(16,math.max(0,(usableH-frameHeight)/2-8)) or 0,padding=padding,gap=gap}
    local detail=hud.root:FindById("cardSelectedDetail")
    if detail then detail:SetVisible(formal and touch and detailBand>0);detail:SetStyle{height=detailBand} end
    local selectedCopy=hud.root:FindById("cardSelectedText")
    if selectedCopy then selectedCopy:SetStyle{fontSize=touch and 16 or 14} end
    local briefToggle=hud.root:FindById("cardBriefToggle")
    if briefToggle then briefToggle:SetVisible(not (formal and touch));briefToggle:SetStyle{height=44} end
    local header=hud.root:FindById("cardHeader")
    local footer=hud.root:FindById("cardFooter")
    if header then header:SetStyle{height=formal and band or "auto",paddingTop=0,justifyContent="center"} end
    local heading=hud.root:FindById("cardPanelTitle")
    if heading then heading:SetStyle{fontSize=compact and 20 or 26} end
    local subtitle=hud.root:FindById("cardPanelSubtitle")
    if subtitle then subtitle:SetStyle{fontSize=compact and 11 or 14} end
    if footer then footer:SetStyle{height=formal and footerBand or 52,justifyContent="center"} end
    viewport:SetStyle{height=formal and deckHeight or 0,flexShrink=0,flexGrow=formal and 0 or 1,flexBasis=formal and "auto" or 0}
    local content=hud.root:FindById("cardDeckContent")
    if content then content:SetStyle{height=formal and math.max(deckHeight,rowHeight+12) or "auto",
        width=formal and rowWidth+32 or "100%",
        minWidth=formal and rowWidth+32 or 0,justifyContent=formal and "center" or "flex-start"} end
    deck:SetStyle{flexWrap=formal and "no-wrap" or "wrap",gap=metrics.gap,
        width=formal and rowWidth or "100%",minWidth=formal and rowWidth or 0,alignItems="center"}
    for _,card in ipairs(Config.Cards.definitions --[[@as table[] ]]) do
        local box=hud.root:FindById("cardBox_"..card.id)
        if box then box:SetStyle{width=metrics.width} end
        local title=hud.root:FindById("cardTitle_"..card.id)
        if title then title:SetStyle{fontSize=metrics.titleSize} end
        local description=hud.root:FindById("cardDescription_"..card.id)
        if description then
            local size=metrics.titleSize
            description:SetStyle{fontSize=size,minFontSize=size}
        end
        local brief=hud.root:FindById("cardBrief_"..card.id)
        if brief then brief:SetStyle{fontSize=metrics.descriptionSize} end
        local neutral=hud.root:FindById("cardNeutral_"..card.id)
        if neutral then neutral:SetStyle{fontSize=metrics.descriptionSize} end
    end
end

function Panel.Build(hud)
    ---@type Widget[]
    local cardWidgets={}
    ---@type Widget[]
    local header={label{id="cardPanelTitle",text="卡牌调试 · 18张机制卡",fontSize=26,textAlign="center"},
        label{id="cardPanelSubtitle",text="测试获取进入调试局，不计作正式六轮验收；获取仍提升免疫警戒。",textAlign="center"},
        label{id="cardAlertStatus",text="免疫警戒 0",textAlign="center"}}
    ---@type Widget[]
    local children={}
    for _,card in ipairs(Config.Cards.definitions --[[@as table[] ]]) do
        local prerequisites={}
        for _,requiredId in ipairs(card.prerequisites or {}) do
            for _,definition in ipairs(Config.Cards.definitions --[[@as table[] ]]) do
                if definition.id==requiredId then prerequisites[#prerequisites+1]=definition.name end
            end
        end
        local prerequisiteText="需要先获得："..(#prerequisites>0 and table.concat(prerequisites,"、") or "无")
        cardWidgets[#cardWidgets+1]=cardBox(hud,card,prerequisiteText)
    end
    children[#children+1]=UI.Panel{id="cardDeck",width="100%",flexDirection="row",flexWrap="wrap",
        justifyContent="center",alignItems="center",gap=24,children=cardWidgets}
    -- [HUD_BUTTON:cardDebugOffer] 调试触发三选一，正式选卡隐藏
    children[#children+1]=cardButton{id="cardDebugOffer",text="调试：触发一次三选一",height=40,
        onClick=function()
            hud:CloseCardInfo()
            hud.sim.debugRun=true
            local ok,result=hud.sim:RequestCardChoice("debug:offer")
            if not ok then hud.sim.skillMessage=tostring(result) end
        end}
    children[#children+1]=label{id="cardDebugSnapshot",text="",fontSize=11}
    children[#children+1]=label{id="cardDebugTitle",text="警戒调试覆盖 · 不增加卡牌获得次数",fontSize=15}
    local levels={}
    for level=0,6 do
        local value=level
        -- [HUD_BUTTON:cardDebugLevel_] 警戒等级0—6，正式选卡隐藏
        levels[#levels+1]=cardButton{id="cardDebugLevel_"..level,text=ROMAN[level+1],width=48,height=40,
            onClick=function() hud.sim:SetDebugImmuneAlertLevel(value);Panel.Refresh(hud) end}
    end
    children[#children+1]=UI.Panel{id="cardDebugLevels",width="100%",flexDirection="row",flexWrap="wrap",gap=6,children=levels}
    -- [HUD_BUTTON:cardDebugExit] 退出警戒调试，正式选卡隐藏
    children[#children+1]=cardButton{id="cardDebugExit",text="退出警戒调试，恢复卡牌警戒",width="100%",height=44,
        onClick=function() hud.sim:SetDebugImmuneAlertLevel(nil);Panel.Refresh(hud) end}
    -- [HUD_BUTTON:cardContinue] 获得卡牌后继续游戏／关闭调试面板
    local continueButton=cardButton{id="cardContinue",text="确定",width=240,maxWidth="100%",height=48,flexShrink=0,
        onClick=function()
            local pending=hud.sim.cards.pending
            if pending and pending.mode=="formal" then Panel.Confirm(hud)
            else hud:CloseCardInfo() end
        end}
    local overlay=UI.Panel{
        id="cardInfoOverlay",visible=false,zIndex=40,position="absolute",left=0,top=0,
        width="100%",height="100%",backgroundColor={8,6,16,235},pointerEvents="auto",
        children={UI.SafeAreaView{id="cardSafeArea",width="100%",height="100%",padding=12,nativeMenuInset=true,
            alignItems="center",justifyContent="center",children={
                cardButton{id="cardBriefToggle",text="简略文本：关",position="absolute",right=4,top=4,
                    width=124,height=32,fontSize=12,zIndex=3,
                    onClick=function() Description.SetBrief(hud,not hud.cardBriefText_) end},
                Skin.Frame{frameKind="dialog",id="cardPanelFrame",width="94%",maxWidth=1000,height="auto",maxHeight="100%",minHeight=0,padding=20,gap=12,
                    backgroundColor=Config.Palette.panelBg,borderWidth=1,borderRadius=2,
                    borderColor=Config.Palette.panelBorder,children={
                        UI.Panel{id="cardHeader",width="100%",height=64,gap=4,flexShrink=0,
                            justifyContent="center",children={header[1],header[2],header[3],
                                label{id="cardTestMessage",text="",fontSize=12,textAlign="center"}}},
                        Skin.Scroll{id="cardDeckViewport",width="100%",height=392,minHeight=0,scrollY=true,
                            scrollX=true,showScrollbar=true,bounces=false,children={
                                UI.Panel{id="cardDeckContent",width="100%",height="100%",gap=12,
                                    alignItems="center",justifyContent="center",children=children},
                            }},
                        label{id="cardLoadingStatus",text="正在准备卡牌…",fontSize=14,position="absolute",
                            left=0,top="50%",height=24,textAlign="center",visible=false,pointerEvents="none"},
                        Skin.Scroll{id="cardSelectedDetail",width="100%",height=84,minHeight=0,flexShrink=0,visible=false,
                            children={label{id="cardSelectedText",text="点击一张卡牌，在这里阅读完整说明。",fontSize=14}}},
                        UI.Panel{id="cardFooter",width="100%",height=64,flexShrink=0,alignItems="center",
                            justifyContent="center",children={continueButton}},
                    }},
            }}},
    }
    overlay.Update=function(_,dt)
        Panel.UpdateReveal(hud,dt)
        Panel.Layout(hud)
        Description.Update(hud,dt)
    end
    local render=overlay.Render
    overlay.Render=function(widget,nvg)
        Artwork.Warm(hud.cardArtwork_,hud.root)
        if render then render(widget,nvg) end
    end
    return overlay
end

function Panel.Refresh(hud)
    if not hud.root then return end
    local sim,w=hud.sim,hud.sim.world
    local pending=sim.cards.pending
    if hud.cardSelectionChoice_ and (not pending or pending.id~=hud.cardSelectionChoice_) and not hud.cardConfirming_ then
        Panel.ResetSelection(hud)
    end
    if hud.cardRevealElapsed_ ~= nil and (not pending or pending.id ~= hud.cardRevealChoice_) then
        Panel.ResetReveal(hud)
    end
    local formal=(pending and pending.mode=="formal") or (sim.cardNotice and sim.cardNotice.formal)
    hud:SetText("cardPanelTitle",formal and ("阶段 "..sim.stage.." · 选择一张进化卡") or "卡牌调试 · 18张机制卡")
    hud:SetText("cardPanelSubtitle",formal and "点击卡牌选择，再按下方确定" or "测试获取进入调试局，不计作正式六轮验收。")
    for _,id in ipairs({"cardDebugTitle","cardDebugLevels","cardDebugExit","cardDebugOffer","cardDebugSnapshot"}) do
        local widget=hud.root:FindById(id)
        if widget then widget:SetVisible(not formal) end
    end
    local budgets,groups={},{}
    for _,c in ipairs(w.cells) do if c.state=="PRODUCTIVE" then budgets[#budgets+1]="#"..c.id..":"..(c.pendingProduction or 0) end end
    for _,s in ipairs(w.swarms) do groups[#groups+1]="#"..s.id.."质量"..s.mass.." "..s.aiState.."预约"..tostring(s.aiTargetCellId or "—") end
    hud:SetText("cardDebugSnapshot","群："..table.concat(groups,"；").."\n生产预算："..table.concat(budgets,"，").."\n质量账本："..(function() local lines={} for kind,count in pairs(w.massLedger.totals) do lines[#lines+1]=kind..":"..count end table.sort(lines);return table.concat(lines,"，") end)())
    local level=w.immuneAlertLevel
    local text="免疫警戒 "..ROMAN[level+1].." · 当前生效 "..ROMAN[(w.activeImmuneAlertLevel or 0)+1]
    if w.debugImmuneAlertLevel~=nil then text=text.." · 调试覆盖 "..ROMAN[w.debugImmuneAlertLevel+1] end
    if w.pendingAlertActivation then text=text..string.format(" · 恢复后缓冲 %.1f秒",w.pendingAlertActivation.remaining) end
    local warnings,searches=0,0
    for _,assignment in pairs(w.channelPatrolAssignments) do
        if w.time<assignment.startsAt then warnings=warnings+1 end
    end
    for _,immune in ipairs(w.immunes) do if immune.state=="search" then searches=searches+1 end end
    if warnings>0 then text=text.." · 支路巡逻即将开始" end
    if searches>0 then text=text.." · 附近搜索 "..searches end
    hud:SetText("cardAlertStatus",text)
    local alert=hud.root:FindById("cardAlertStatus");if alert then alert:SetVisible(not formal) end
    hud:SetText("immuneAlertHud",text)
    for _,card in ipairs(Config.Cards.definitions --[[@as table[] ]]) do
        local ok,reason=sim.cards:Eligibility(card.id,sim.cards.round+1,true)
        hud:SetText("cardState_"..card.id,ok and "未获得 · 可测试获取" or reason)
        local btn=hud.root:FindById("cardGet_"..card.id) --[[@as Button?]]
        local offered=false
        if pending then for _,choice in ipairs(pending.cards) do if choice.id==card.id then offered=true end end end
        local box=hud.root:FindById("cardBox_"..card.id)
        if box then box:SetVisible(not formal or offered or (sim.cardNotice~=nil and sim.cardNotice.card.id==card.id)) end
        for _,prefix in ipairs({"cardRarity_","cardState_"}) do
            local info=hud.root:FindById(prefix..card.id);if info then info:SetVisible(not formal) end
        end
        if btn then
            btn:SetVisible(not formal)
            btn:SetText(formal and "选择此卡" or "测试获取")
            btn:SetDisabled(hud.cardRevealElapsed_~=nil or not ok or not sim.started or sim.ending~=nil or sim.cardNotice~=nil or (formal and not offered))
        end
        if formal and offered then hud:SetText("cardState_"..card.id,"未获得 · 合法候选") end
        Panel.UpdateCardVisual(hud,card.id)
    end
    local notice=sim.cardNotice
    local message=hud.cardTestError_ or ""
    if notice and not formal then
        message="已获得“"..notice.card.name.."”。\n"..require("UI.SkillControls").Hint(notice.card.id).."\n免疫警戒"..ROMAN[notice.level+1].."："
            ..Config.ImmuneAlert.descriptions[notice.level+1].."\n点击继续，5秒模拟缓冲后启用新调度。"
    end
    hud:SetText("cardTestMessage",message)
    local messageLabel=hud.root:FindById("cardTestMessage")
    if messageLabel then messageLabel:SetVisible(message~="") end
    local selectedText="点击一张卡牌，在这里阅读完整说明。"
    for _,card in ipairs(pending and pending.cards or {}) do
        if card.id==hud.cardSelectedId_ then
            selectedText=card.name.."："..card.desc
            for _,required in ipairs(card.prerequisites or {}) do
                for _,definition in ipairs(Config.Cards.definitions) do
                    if definition.id==required then selectedText=selectedText.."\n前置："..definition.name end
                end
            end
        end
    end
    hud:SetText("cardSelectedText",selectedText)
    if Mobile.IsTouch(hud) and formal and not hud.cardBriefText_ then Description.SetBrief(hud,true) end
    Panel.Layout(hud)
    local btn=hud.root:FindById("cardContinue") --[[@as Button?]]
    if btn then
        btn:SetText(formal and "确定" or "关闭测试面板")
        btn:SetVisible(true)
        btn:SetDisabled(formal and (hud.cardSelectedId_==nil or hud.cardRevealElapsed_~=nil or hud.cardConfirming_==true) or false)
    end
end

return Panel
