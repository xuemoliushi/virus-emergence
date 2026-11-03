"""Delayed DWP card batches and production branch-route lifecycle regression.

UI/native boundaries are mocked; production simulation/navigation run unchanged.
This is not a native screenshot or device-FPS test.
"""
from pathlib import Path
import json,time
from bird_ui_regression import runtime
from compact_ui_regression import SMALL
from lua_test_runtime import LuaRuntime

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'validation/midgame-cards-20261018'
SETUP=SMALL+r'''
function delayedOffer()
 local h,g,s=fixture();local callbacks={};local loads={}
 cache={GetResourceAsync=function(_,kind,path,callback)
  assert(kind=='Texture2D');callbacks[path]=callback
 end}
 local images=package.loaded['urhox-libs/UI/Core/ImageCache'];local get=images.Get
 images.Get=function(path)loads[#loads+1]=path;return get(path)end
 local sounds=0
 h.onCardChoiceShown=function()sounds=sounds+1;return {duration=.5,position=function()return 0 end}end
 assert(s:GrantCardChoice('stage:1'))
 local paths={};for _,card in ipairs(s.cards.pending.cards)do paths[#paths+1]=require('UI.CardArt').paths[card.id]end
 return h,s,callbacks,loads,paths,function()return sounds end
end
'''
CASES={
'third image delayed: all cards stay hidden and one sound/reveal starts after native preparation':r'''
local h,s,callbacks,loads,paths,sounds=delayedOffer()
local overlay=h.root:FindById('cardInfoOverlay');local deck=h.root:FindById('cardDeck')
assert(not deck:IsVisible() and deck.props.opacity==0 and sounds()==0)
for _=1,30 do overlay:Render({});overlay:Update(1/60)end
assert(#loads==0 and not deck:IsVisible() and sounds()==0,'no placeholder image is revealed or loaded in foreground')
callbacks[paths[1]]({});callbacks[paths[2]]({})
overlay:Render({});assert(#loads==1,'at most one new NanoVG handle per render frame')
overlay:Update(.1);overlay:Render({});assert(#loads==2)
for _=1,60 do overlay:Render({});overlay:Update(1/60)end
assert(not deck:IsVisible() and sounds()==0 and h.cardRevealElapsed_==0)
assert(h.root:FindById('cardContinue'):IsDisabled())
callbacks[paths[3]]({});overlay:Render({});assert(#loads==3 and not deck:IsVisible())
overlay:Update(1/60)
assert(deck:IsVisible() and deck.props.opacity==0 and sounds()==1)
for _,card in ipairs(s.cards.pending.cards)do assert(h.root:FindById('cardBox_'..card.id):IsVisible())end
overlay:Update(.1);assert(deck.props.opacity>0 and deck.props.opacity<1)
-- A suspended audio cursor cannot trap the choice forever.
for _=1,8 do overlay:Update(.1)end
assert(deck.props.opacity==1 and h.cardRevealElapsed_==nil and sounds()==1)
callback(h,'cardBox_'..s.cards.pending.cards[1].id);callback(h,'cardContinue')
assert(not s.cards.pending and not h.cardInfoShown_ and not s.paused)
''',
'timeout gives a stable neutral card and a late completion cannot change it during reveal':r'''
local h,s,callbacks,loads,paths,sounds=delayedOffer()
local overlay=h.root:FindById('cardInfoOverlay')
callbacks[paths[1]]({});callbacks[paths[2]]({})
overlay:Render({});overlay:Render({})
overlay:Update(10);overlay:Render({});overlay:Update(.01)
local id=s.cards.pending.cards[3].id;local art=h.root:FindById('cardArt_'..id)
assert(art.props.backgroundImage==false and sounds()==1)
callbacks[paths[3]]({});overlay:Render({});assert(art.props.backgroundImage==false)
for _=1,35 do overlay:Update(1/60)end
assert(h.cardRevealElapsed_==nil)
callback(h,'cardBox_'..id);callback(h,'cardContinue');assert(not s.paused)
-- The same art can recover on a future offer; fallback is not permanent.
local A=require('UI.CardArtwork');local b=A.New({{id=id}})
callbacks[paths[3]]({});A.Warm(b,h.root)
assert(b.ready and art.props.backgroundImage==paths[3])
''',
'resource failure and image creation exception complete with a neutral card':r'''
local h,s,callbacks,loads,paths=delayedOffer()
callbacks[paths[1]](nil);callbacks[paths[2]]({});callbacks[paths[3]]({})
local images=package.loaded['urhox-libs/UI/Core/ImageCache'];local original=images.Get
images.Get=function(path)if path==paths[2]then error('injected texture failure')end;return original(path)end
local overlay=h.root:FindById('cardInfoOverlay')
for _=1,5 do overlay:Render({});overlay:Update(1/60)end
for _=1,40 do overlay:Update(1/60)end
assert(h.cardRevealElapsed_==nil and h.root:FindById('cardDeck').props.opacity==1)
for i=1,2 do assert(h.root:FindById('cardArt_'..s.cards.pending.cards[i].id).props.backgroundImage==false)end
''',
'destroyed/restarted HUD ignores old async callbacks':r'''
local h,s,callbacks,loads,paths,sounds=delayedOffer()
local batch=h.cardArtwork_;h:Destroy()
for _,path in ipairs(paths)do callbacks[path]({})end
assert(batch.cancelled and #batch.entries==0 and #loads==0 and sounds()==0)
''',
'restart and a new formal offer cannot adopt the previous offer downloads':r'''
local h,s,callbacks,loads,paths,sounds=delayedOffer()
local previous=h.cardArtwork_;local old={};for path,callback in pairs(callbacks)do old[path]=callback end
assert(s:StartRun('UPPER_AIRWAY'))
assert(previous.cancelled and not h.cardInfoShown_)
assert(s:GrantCardChoice('new-run'));local current=h.cardArtwork_
assert(current and current~=previous and not current.ready)
for _,callback in pairs(old)do callback({})end
local overlay=h.root:FindById('cardInfoOverlay');overlay:Render({});overlay:Update(.2)
for _,entry in ipairs(current.entries)do assert(entry.status=='pending')end
assert(not h.root:FindById('cardDeck'):IsVisible() and sounds()==0 and #loads==0)
for _,entry in ipairs(current.entries)do callbacks[entry.path]({})end
finishCardReveal(h);assert(h.cardRevealElapsed_==nil and sounds()==1)
''',
}

NAV_SETUP=r'''
Config=require('Core.Config');World=require('Core.SwarmWorld');Nav=require('Core.ImmuneNavigation')
Patrol=require('Core.PatrolNavigation');w=World.New('UPPER_AIRWAY')
local original=Nav.Route;calls=0
Nav.Route=function(...)calls=calls+1;return original(...)end
im=w.immunes[#w.immunes];im._stuckTimer=0
for _,r in ipairs(w.map.regions)do
 if not Nav.Clear(w.map,im,r,im.radius) and Nav.Route(w.map,im,r,im.radius)then destination={x=r.x,y=r.y};break end
end
assert(destination);calls=0;now=0
'''

def navigation():
    lua=LuaRuntime(unpack_returned_tuples=True)
    lua.globals().SRC=(ROOT/'scripts/?.lua').as_posix()
    lua.execute("package.path=SRC..';'..package.path;print=function()end")
    lua.execute(NAV_SETUP)
    lua.execute(r'''
local ox,oy=im.x,im.y
local initial=math.sqrt((im.x-destination.x)^2+(im.y-destination.y)^2)
local arrival=false
for frame=1,12000 do
 now=frame/60
 local x,y=Patrol.Point(w.map,im,destination,now)
 if x then
  assert(Nav.Clear(w.map,im,{x=x,y=y},im.radius),'cached waypoint crosses a wall')
  local dx,dy=x-im.x,y-im.y;local d=math.sqrt(dx*dx+dy*dy)
  if d>0 then local step=math.min(d,w.config.immuneSpeed/60)
   im.x,im.y=w.map:Move(im.x,im.y,im.x+dx/d*step,im.y+dy/d*step,im.radius)
  end
 end
 assert(w.map:Contains(im.x,im.y,im.radius),'body left legal floor')
 if (im.x-destination.x)^2+(im.y-destination.y)^2<.01 then arrival=true;break end
end
assert(arrival and calls<15,'cached patrol must reach distant assigned region: calls='..calls..' pos='..im.x..','..im.y)
arrivalCalls=calls
-- Returning to an obstructed start, resizing, and changing the assignment
-- invalidate the cache; a failed target retries at bounded frequency.
im.x,im.y=ox,oy
Patrol.Point(w.map,im,destination,now+1);local before=calls
im.radius=im.radius+.01;Patrol.Point(w.map,im,destination,now+2)
assert(calls>before,'body growth reused the wrong topology')
local blocked
for y=1,w.height-1 do for x=1,w.width-1 do
 if not w.map.floor[y+1][x+1] then blocked={x=x+.5,y=y+.5};break end
end;if blocked then break end end
local beforeFailure=calls
for frame=1,180 do
 local x=Patrol.Point(w.map,im,blocked,now+3+frame/60);assert(not x)
end
assert(calls-beforeFailure<=5,'unreachable route searched every frame')
''')
    return {'passed':True,'arrival_route_calls':lua.globals().arrivalCalls,'unreachable_retries_per_180_frames':'<=5'}

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    results=[]
    for name,source in CASES.items():
        try:
            lua=runtime();lua.globals().print=lambda *args:None;lua.execute(SETUP+source)
            results.append({'name':name,'passed':True});print('PASS',name,flush=True)
        except Exception as e:
            results.append({'name':name,'passed':False,'error':str(e)});print('FAIL',name,str(e),flush=True)
    nav=navigation();print('PASS production patrol routing',nav,flush=True)
    report={'scope':'real Lua, mocked download/NanoVG boundaries; no native/GPU FPS claim','cards':results,'navigation':nav}
    (OUT/'regression.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(any(not row['passed']for row in results))
