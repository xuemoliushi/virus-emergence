"""Description mode and scroll timing using game UI with an engine boundary fixture."""
from card_selection_regression import SETUP
from bird_ui_regression import runtime

CASES = {
    'short phone keeps confirmation inside a bounded dialog with safe margins': '''
local h,g,s,p=cardFixture();require('UI.MobileLayout').MarkTouch()
local P=require('UI.CardPanel');local safe=h.root:FindById('cardSafeArea')
for _,size in ipairs({{924,520},{1147,530},{667,375},{620,250}}) do
 safe.rect={x=0,y=0,w=size[1],h=size[2]}
 safe.props.paddingTop=48;safe.props.paddingBottom=20
 P.Layout(h)
 local frame=h.root:FindById('cardPanelFrame').props
 local header=h.root:FindById('cardHeader').props
 local deck=h.root:FindById('cardDeckViewport').props
 local detail=h.root:FindById('cardSelectedDetail').props
 local footer=h.root:FindById('cardFooter').props
 local content=2*frame.padding+header.height+deck.height+detail.height+footer.height+3*frame.gap
 assert(content==frame.height and frame.height<=size[2]-48-20-24)
 assert(footer.height>=48 and deck.flexShrink==0 and frame.translateY<=0)
end
''',
    'phone selection provides stable full copy without automatic scrolling or committing': """
local h,g,s,p=cardFixture();require('UI.MobileLayout').MarkTouch()
local P=require('UI.CardPanel');local D=require('UI.CardDescription')
local id=p.cards[1].id;assert(P.Select(h,id))
assert(h.cardSelectedId_==id and s.cards.pending==p and not s.cardNotice)
assert(h.root:FindById('cardSelectedText'):GetText():find(p.cards[1].desc,1,true))
local v=h.cardDescriptionViews_[id];local moved=false
v.scroll.SetScroll=function() moved=true end
for i=1,100 do D.Update(h,.1) end
assert(not moved and s.cards.pending==p and h.cardSelectedId_==id)
local detail=h.root:FindById('cardSelectedDetail');local resets=0
local original=detail.SetScroll
detail.SetScroll=function(self,x,y) assert(x==0 and y==0);resets=resets+1;original(self,x,y) end
assert(P.Select(h,p.cards[2].id) and resets==1)
assert(P.Select(h,p.cards[2].id) and resets==1)
""",

    'all cards retain full copy and supply a bounded short version': '''
local h,g,s=cardFixture();local D=require('UI.CardDescription');local n=0
for _,card in ipairs(Config.Cards.definitions) do
 local full=h.root:FindById('cardDescription_'..card.id)
 assert(full:GetText():find(card.desc,1,true) and not full.props.height)
 assert(full.props.fontSize==h.root:FindById('cardTitle_'..card.id).props.fontSize and full.props.minFontSize==full.props.fontSize)
 local short=h.root:FindById('cardBrief_'..card.id)
 assert(short:GetText()==D.brief[card.id] and utf8.len(short:GetText())<=26)
 assert(not short:IsVisible());n=n+1
end
assert(n==18)
''',
    'mode toggle preserves selection and pending authority; full mode restores': '''
local h,g,s,p=cardFixture();local id=p.cards[1].id;callback(h,'cardBox_'..id)
callback(h,'cardBriefToggle');assert(h.cardBriefText_ and h.cardSelectedId_==id and s.cards.pending==p)
for _,card in ipairs(p.cards) do
 assert(h.root:FindById('cardBrief_'..card.id):IsVisible())
 assert(not h.root:FindById('cardDescriptionScroll_'..card.id):IsVisible())
end
callback(h,'cardBriefToggle');assert(not h.cardBriefText_ and h.cardSelectedId_==id)
assert(h.root:FindById('cardDescriptionScroll_'..id):IsVisible())
''',
    'overflow reverses smoothly; manual input pauses; brief and closed modes stop': '''
local h,g,s,p=cardFixture();local D=require('UI.CardDescription')
local v=h.cardDescriptionViews_[p.cards[1].id];local y=0
v.scroll.GetContentSize=function() return 140,200 end
v.scroll.GetLayout=function() return {w=140,h=100} end
v.scroll.GetScroll=function() return 0,y end
v.scroll.SetScroll=function(self,x,nextY) y=nextY;self.props.onScroll(self,x,y) end
local peak,turned=0,false
for i=1,350 do local old=y;D.Update(h,.1);assert(y>=0 and y<=100)
 peak=math.max(peak,y);if old>99 and y<old then turned=true end end
assert(peak>99 and turned)
v.scroll:SetScroll(0,43);for i=1,39 do D.Update(h,.1);assert(y==43) end
for i=1,8 do D.Update(h,.1) end;assert(y~=43)
D.SetBrief(h,true);local old=y;D.Update(h,1);assert(y==old)
D.SetBrief(h,false);h.cardInfoShown_=false;D.Update(h,1);assert(y==0)
''',
}
if __name__ == '__main__':
    failed=[]
    for name,code in CASES.items():
        try:
            lua=runtime();lua.globals().print=lambda *a:None;lua.execute(SETUP+code)
            print('PASS',name)
        except Exception as e:
            failed.append(name);print('FAIL',name,e)
    raise SystemExit(bool(failed))
