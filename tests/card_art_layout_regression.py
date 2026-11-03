"""Real card UI/SimState with engine boundary fixtures; no claim of native Yoga rendering."""
from pathlib import Path
import json
import hashlib
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.tmp/test-deps'))
from observation_regression import SETUP, LuaRuntime

TESTS = {
    'all eighteen named assets have exact mechanism ID mapping': r'''
local art=require('UI.CardArt');local count=0
for id,path in pairs(art.paths) do
 count=count+1;assert(path=='image/mechanism_cards/'..id..'.png')
end
assert(count==18)
local h,g,s=hudFixture()
for _,card in ipairs(Config.Cards.definitions) do
 assert(art.paths[card.id],card.id)
 local visual=h.root:FindById('cardArt_'..card.id)
 assert(visual.props.backgroundImage==art.paths[card.id] and visual.props.aspectRatio==.75)
 local title=h.root:FindById('cardTitle_'..card.id)
 local body=h.root:FindById('cardDescription_'..card.id)
 assert(title:GetText()==card.name and body:GetText():find(card.desc,1,true))
 assert(title.props.textAlign=='center' and title.props.verticalAlign=='middle')
 assert(body.props.textAlign=='center' and body.props.height==nil)
 assert(h.root:FindById('cardDescriptionScroll_'..card.id).props.scrollY)
end
assert(h.root:FindById('cardDescription_swarm_capacity_6'):GetText():find('需要先获得：分裂扩容',1,true))
''',
    'formal three cards fit a horizontal row and respond to viewport resizing': r'''
local h,g,s,scale,obs=hudFixture();assert(s:StartRun('UPPER_AIRWAY',true));scale:JumpTo('cell');settleScale(scale);h:Update(.2)
local ok,pending=s:GrantCardChoice('stage:1');assert(ok)
local panel=require('UI.CardPanel');local viewport=h.root:FindById('cardDeckViewport');local safe=h.root:FindById('cardSafeArea')
local deck=h.root:FindById('cardDeck')
for _,size in ipairs({{1120,620},{750,430},{620,250},{330,520}}) do
 safe.rect.w,safe.rect.h=size[1],size[2];panel.Layout(h)
 assert(deck.props.flexDirection=='row' and deck.props.flexWrap=='no-wrap')
 local shown,total=0,0
 for _,card in ipairs(Config.Cards.definitions) do
  local box=h.root:FindById('cardBox_'..card.id)
  if box:IsVisible() then shown=shown+1;total=total+box.props.width end
 end
 assert(shown==3)
 assert(deck.props.minWidth==total+2*deck.props.gap)
 local width=h.root:FindById('cardBox_'..pending.cards[1].id).props.width
 if size[1]>=700 and size[2]>=400 then
  assert(total+2*deck.props.gap<=size[1] and width/.75+26<=viewport.props.height)
 else assert(width>=112 and viewport.props.scrollX and viewport.props.scrollY) end
end
assert(h.root:FindById('cardContinue'):IsVisible() and h.root:FindById('cardContinue'):IsDisabled())
assert(not h.root:FindById('cardTestMessage'):IsVisible())
h:CloseCardInfo();assert(h.cardInfoShown_ and s.cards.pending==pending)
''',
    'selection is staged until confirmation, secondary clicks do not choose, external pause is preserved': r'''
local h,g,s,scale,obs=hudFixture();assert(s:StartRun('UPPER_AIRWAY',true));scale:JumpTo('cell');settleScale(scale);h:Update(.2)
local ok,pending=s:GrantCardChoice('stage:1');assert(ok)
local card=pending.cards[1];local btn=h.root:FindById('cardGet_'..card.id)
btn.props.onClick(btn,{IsPrimaryAction=function() return false end})
assert(s.cards.pending==pending and s.world.immuneAlertLevel==0)
callback(h,'cardGet_'..card.id)
assert(s.cards.pending==pending and not s.cardNotice,'reveal must block early choices')
finishCardReveal(h)
assert(h.root:FindById('cardDeck').props.opacity==1 and not btn:IsDisabled())
callback(h,'cardGet_'..card.id)
assert(not s.cardNotice and s.cards.pending==pending and h.cardSelectedId_==card.id)
assert(s.world.immuneAlertLevel==0 and s.paused)
assert(h.root:FindById('cardContinue'):IsVisible() and not h.root:FindById('cardContinue'):IsDisabled())
assert(not h.root:FindById('cardTestMessage'):IsVisible())
local count=0
for _,c in ipairs(Config.Cards.definitions) do
 if h.root:FindById('cardBox_'..c.id):IsVisible() then count=count+1 end
end
assert(count==3)
s:SetPaused('external',true);callback(h,'cardContinue')
assert(not h.cardInfoShown_ and s.stage==2 and s.pauseReasons.external and s.paused)
''',
    'debug catalogue still contains all eighteen cards and wraps into rows': r'''
local h,g,s=hudFixture();h:OpenCardInfo()
local deck=h.root:FindById('cardDeck');assert(deck.props.flexWrap=='wrap')
local count=0
for _,c in ipairs(Config.Cards.definitions) do
 if h.root:FindById('cardBox_'..c.id):IsVisible() then count=count+1 end
end
assert(count==18 and h.root:FindById('cardDebugLevels'):IsVisible())
''',
}

def runtime():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('package.path=' + repr((ROOT/'scripts/?.lua').as_posix()) + "..';'..package.path")
    lua.globals().print = lambda *args: None
    lua.execute(SETUP)
    return lua

if __name__ == '__main__':
    mapping = json.loads((ROOT/'assets/image/mechanism_cards/mapping.json').read_text(encoding='utf-8'))
    assert len(mapping['mapped']) == 18 and not mapping['unassigned']
    for entry in mapping['mapped'].values():
        imported = ROOT/'assets/image/mechanism_cards'/entry['file']
        assert hashlib.sha256(imported.read_bytes()).hexdigest() == entry['sha256']
    assert not list((ROOT/'assets/image/mechanism_cards').glob('unassigned_*'))
    for name, code in TESTS.items():
        runtime().execute(code)
        print('PASS:', name)
    print('4 card integration checks passed; native layout/rendering unverified.')
