"""Card choice staging, feedback and centering. Native Yoga/GPU are separate acceptance boundaries."""
from compact_ui_regression import SMALL
from bird_ui_regression import runtime

SETUP=SMALL+'''
function cardFixture()
 local h,g,s=fixture();assert(s:GrantCardChoice('stage:1'))
 local pending=s.cards.pending
 finishCardReveal(h)
 return h,g,s,pending
end
'''
CASES={
 'clicks select and allow switching, confirmation alone commits once and resumes': '''
local h,g,s,pending=cardFixture();local a,b=pending.cards[1].id,pending.cards[2].id
local confirm=h.root:FindById('cardContinue');assert(confirm:IsDisabled() and confirm:GetText()=='确定')
callback(h,'cardContinue');assert(s.cards.pending==pending and s.world.immuneAlertLevel==0)
callback(h,'cardBox_'..a);assert(h.cardSelectedId_==a and s.cards.pending==pending and not s.cardNotice)
assert(not confirm:IsDisabled() and s.paused and s.world.immuneAlertLevel==0)
callback(h,'cardBox_'..b);assert(h.cardSelectedId_==b and not s.cardNotice)
for _,c in ipairs(pending.cards) do assert(h.root:FindById('cardBox_'..c.id):IsVisible()) end
callback(h,'cardContinue');assert(not h.cardInfoShown_ and not s.cards.pending and not s.cardNotice)
assert(s.world.immuneAlertLevel==1 and s.stage==2 and not s.paused)
callback(h,'cardContinue');assert(s.world.immuneAlertLevel==1 and s.stage==2)
''',
 'hover lifts with mild glow; selected ring survives pointer leave and transfers on reselection': '''
local h,g,s,pending=cardFixture();local a,b=pending.cards[1].id,pending.cards[2].id
local box=h.root:FindById('cardBox_'..a);local art=h.root:FindById('cardArt_'..a)
box.props.onPointerEnter();assert(art.props.scale>1 and art.props.translateY<0 and art.props.shadowBlur>0)
box.props.onPointerLeave();assert(art.props.scale==1 and art.props.shadowBlur==0)
callback(h,'cardBox_'..a);box.props.onPointerLeave()
assert(art.props.borderWidth==2 and art.props.shadowBlur==28)
assert(h.root:FindById('cardSelection_'..a):GetText():find('已选中'))
callback(h,'cardBox_'..b);assert(art.props.borderWidth==0 and art.props.shadowBlur==0)
assert(h.root:FindById('cardArt_'..b).props.borderWidth==2)
''',
 'reveal, secondary click and noncandidate clicks cannot enable confirmation': '''
local h,g,s=fixture();assert(s:GrantCardChoice('stage:1'));local pending=s.cards.pending
callback(h,'cardBox_'..pending.cards[1].id);assert(not h.cardSelectedId_)
finishCardReveal(h)
callback(h,'cardBox_'..pending.cards[1].id,{IsPrimaryAction=function() return false end})
assert(not h.cardSelectedId_)
local invalid;for _,c in ipairs(Config.Cards.definitions) do
 local found=false;for _,o in ipairs(pending.cards) do if c.id==o.id then found=true end end
 if not found then invalid=c.id;break end
end
callback(h,'cardBox_'..invalid);assert(not h.cardSelectedId_ and h.root:FindById('cardContinue'):IsDisabled())
''',
 'confirmation preserves other pause reasons and a new choice starts unselected': '''
local h,g,s,pending=cardFixture();callback(h,'cardBox_'..pending.cards[1].id)
s:SetPaused('external',true);callback(h,'cardContinue')
assert(not h.cardInfoShown_ and s.paused and s.pauseReasons.external)
s:SetPaused('external',false);assert(s:GrantCardChoice('stage:2'))
assert(not h.cardSelectedId_ and h.root:FindById('cardContinue'):IsDisabled())
''',
 'compact panel clears top ornament and keeps footer tight, without per-card acquisition buttons': '''
local h,g,s,pending=cardFixture();local P=require('UI.CardPanel')
for _,size in ipairs({{1280,720},{1920,1080},{640,360},{390,844}}) do
 local safe=h.root:FindById('cardSafeArea');safe.rect={x=0,y=0,w=size[1],h=size[2]};P.Layout(h)
 local header,footer=h.root:FindById('cardHeader'),h.root:FindById('cardFooter')
 assert(header.props.height>=footer.props.height and header.props.paddingTop>=16)
 local content=h.root:FindById('cardDeckContent');assert(content.props.justifyContent=='center')
 assert(header.props.height<=68 and footer.props.height<=48)
 local first=h.root:FindById('cardBox_'..pending.cards[1].id)
 assert(h.root:FindById('cardDeckViewport').props.height<=first.props.width/.75+38)
 local frame=h.root:FindById('cardPanelFrame');assert(frame.props.width<=size[1]*.94 and frame.props.height=='auto')
 assert(h.root:FindById('cardDeckViewport').props.height+header.props.height+footer.props.height+frame.props.padding*2+frame.props.gap*2<=size[2]*.92+.001)
end
for _,c in ipairs(pending.cards) do
 assert(not h.root:FindById('cardGet_'..c.id):IsVisible())
 assert(not h.root:FindById('cardState_'..c.id):IsVisible())
end
''',
}

if __name__=='__main__':
    failed=[]
    for name,code in CASES.items():
        try:
            lua=runtime();lua.globals().print=lambda *a:None;lua.execute(SETUP+code)
            print('PASS',name)
        except Exception as e:failed.append(name);print('FAIL',name,e)
    raise SystemExit(bool(failed))
