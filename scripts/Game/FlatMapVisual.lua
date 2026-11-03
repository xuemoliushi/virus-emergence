-- Uses the runtime's authoritative grid; UI owns NanoVG's frame and DPR.
local Config=require('Core.Config')
local Geometry=require('Game.FlatMapGeometry')
local Visual={}
local function rgba(vg,r,g,b,a) nvgFillColor(vg,nvgRGBA(r,g,b,a)) end
local function flowDecal(vg,art,segment,width,scale,ox,oy,x0,y0,x1,y1)
    local a,b=segment.a,segment.b
    if not art or math.max(a.x,b.x)+width<x0 or math.min(a.x,b.x)-width>x1
        or math.max(a.y,b.y)+width<y0 or math.min(a.y,b.y)-width>y1 then return end
    local length,ux,uy,n=segment.length,segment.ux,segment.uy,segment.count
    for i=1,n do
        local start,finish=(i-1)*length/n,i*length/n
        local ax,ay=a.x+ux*start,a.y+uy*start
        local bx,by=a.x+ux*finish,a.y+uy*finish
        if math.max(ax,bx)+width<x0 or math.min(ax,bx)-width>x1
            or math.max(ay,by)+width<y0 or math.min(ay,by)-width>y1 then goto continue end
        local half=width*.5;local nx,ny=-uy*half,ux*half
        nvgBeginPath(vg)
        nvgMoveTo(vg,ox+(ax+nx)*scale,oy+(ay+ny)*scale)
        nvgLineTo(vg,ox+(bx+nx)*scale,oy+(by+ny)*scale)
        nvgLineTo(vg,ox+(bx-nx)*scale,oy+(by-ny)*scale)
        nvgLineTo(vg,ox+(ax-nx)*scale,oy+(ay-ny)*scale);nvgClosePath(vg)
        -- Existing decal's visible foreground is half the canvas width and
        -- 46.1% of its height. Orient that foreground to the actual flow band.
        local iw,ih=(finish-start)*2*scale,width/.461*scale
        local cx,cy=ox+(ax+bx)*.5*scale,oy+(ay+by)*.5*scale
        local painted=art:Paint(vg,Config.ArtSlots.flowBed,cx-ux*iw*.5+uy*ih*.5,cy-uy*iw*.5-ux*ih*.5,
            iw,ih,Config.EnvironmentVisual.flatFlowBedAlpha,math.atan(uy,ux))
        if painted and not art.flatFlowReported then
            art.flatFlowReported=true
            print('[FlatMapVisual] flow texture loaded: '..Config.ArtSlots.flowBed)
        end
        ::continue::
    end
end
function Visual.Floor(vg,map,scale,ox,oy,x0,y0,x1,y1,art)
    nvgBeginPath(vg)
    for y=math.max(0,math.floor(y0)),math.min(map.height-1,math.ceil(y1)) do
        for _,run in ipairs(map.renderRows[y+1]) do
            local left,right=math.max(run.x,x0),math.min(run.x+run.w,x1)
            if right>left then nvgRect(vg,ox+left*scale,oy+y*scale,(right-left)*scale,scale+.15) end
        end
    end
    rgba(vg,25,15,38,255);nvgFill(vg)
    if art then
        local tile=Config.EnvironmentVisual.tileWidthMeters*scale
        art:Paint(vg,Config.ArtSlots.tissueBg,ox,oy,tile,tile*9/16,Config.EnvironmentVisual.flatBaseAlpha or .50,0,(NVG_IMAGE_REPEATX or 2)|(NVG_IMAGE_REPEATY or 4))
    end
end
-- Positions advance along the full polyline/ring, including turns and branches.
-- Presentation animation never moves the static authoritative flow or uses RNG.
function Visual.MarkPosition(map,mark,time)
    local flow=map.flows[mark.flowId]
    if flow.kind=='vortex' then
        local a=mark.angle+(time or 0)*flow.speed*flow.direction/flow.ringRadius
        return flow.cx+math.cos(a)*flow.ringRadius,flow.cy+math.sin(a)*flow.ringRadius
    end
    local along=(mark.along+(time or 0)*flow.speed)%flow.length
    for _,seg in ipairs(map.flowGeometry[flow.id]) do
        if along<=seg.along+seg.length then
            local t=(along-seg.along)/seg.length
            return seg.a.x+(seg.b.x-seg.a.x)*t,seg.a.y+(seg.b.y-seg.a.y)*t
        end
    end
    return mark.x,mark.y
end
function Visual.Draw(vg,map,l,scale,ox,oy,time,art)
    local geometry=Geometry.Get(map)
    local x0,y0=(l.x-ox)/scale,(l.y-oy)/scale
    local x1,y1=x0+l.w/scale,y0+l.h/scale
    nvgBeginPath(vg);nvgRect(vg,l.x,l.y,l.w,l.h);rgba(vg,3,2,7,255);nvgFill(vg)
    if art then art:BeginFrame() end
    Visual.Floor(vg,map,scale,ox,oy,x0,y0,x1,y1,art)
    nvgLineCap(vg,NVG_ROUND);nvgLineJoin(vg,NVG_ROUND)
    for _,flow in ipairs(map.flows) do
        nvgBeginPath(vg)
        local visible=false
        if flow.kind=='vortex' then
            if flow.cx+flow.ringRadius+2>x0 and flow.cx-flow.ringRadius-2<x1 and flow.cy+flow.ringRadius+2>y0 and flow.cy-flow.ringRadius-2<y1 then
                nvgCircle(vg,ox+flow.cx*scale,oy+flow.cy*scale,flow.ringRadius*scale);visible=true
            end
        else
            for i=1,#flow.points-1 do
                local a,b=flow.points[i],flow.points[i+1]
                if math.max(a.x,b.x)+2>x0 and math.min(a.x,b.x)-2<x1 and math.max(a.y,b.y)+2>y0 and math.min(a.y,b.y)-2<y1 then
                    visible=true
                end
            end
            if visible then
                for i,p in ipairs(flow.points) do
                    if i==1 then nvgMoveTo(vg,ox+p.x*scale,oy+p.y*scale) else nvgLineTo(vg,ox+p.x*scale,oy+p.y*scale) end
                end
            end
        end
        if visible then
            nvgStrokeWidth(vg,(flow.width or 3)*scale)
            -- A translucent tissue channel, below the cells and membrane rim.
            nvgStrokeColor(vg,nvgRGBA(69,89,114,12));nvgStroke(vg)
            for _,segment in ipairs(geometry.flowSegments[flow.id]) do
                flowDecal(vg,art,segment,flow.width,scale,ox,oy,x0,y0,x1,y1)
            end
        end
    end
    -- Match FlowAt's five-metre calm spawn, including the band background.
    local spawn=map.spawn
    if spawn.x+5>x0 and spawn.x-5<x1 and spawn.y+5>y0 and spawn.y-5<y1 then
        nvgBeginPath(vg);nvgCircle(vg,ox+spawn.x*scale,oy+spawn.y*scale,5*scale)
        rgba(vg,25,15,38,255);nvgFill(vg)
        if art then
            local tile=Config.EnvironmentVisual.tileWidthMeters*scale
            art:Paint(vg,Config.ArtSlots.tissueBg,ox,oy,tile,tile*9/16,Config.EnvironmentVisual.flatBaseAlpha or .50,0,(NVG_IMAGE_REPEATX or 2)|(NVG_IMAGE_REPEATY or 4))
        end
    end
    -- Opaque, textured tissue masks every blocked square. Cached runs replace
    -- per-frame per-tile submission; a rounded fibrous rim softens the raster.
    nvgBeginPath(vg)
    for y=math.max(0,math.floor(y0)),math.min(map.height-1,math.ceil(y1)) do
        for _,run in ipairs(geometry.wallRows[y+1]) do
            local left,right=math.max(run.x,x0),math.min(run.x+run.w,x1)
            if right>left then nvgRect(vg,ox+left*scale,oy+y*scale,(right-left)*scale,scale+.2) end
        end
    end
    rgba(vg,14,9,23,255);nvgFill(vg)
    if art then
        local tile=Config.EnvironmentVisual.tileWidthMeters*scale
        art:Paint(vg,Config.ArtSlots.tissueBg,ox,oy,tile,tile*9/16,.24,0,
            (NVG_IMAGE_REPEATX or 2)|(NVG_IMAGE_REPEATY or 4))
    end
    Geometry.EdgePath(vg,geometry,scale,ox,oy,x0,y0,x1,y1)
    nvgStrokeWidth(vg,scale*.70);nvgStrokeColor(vg,nvgRGBA(22,13,32,255));nvgStroke(vg)
    nvgStrokeWidth(vg,scale*.30);nvgStrokeColor(vg,nvgRGBA(44,28,57,100));nvgStroke(vg)
    -- Broken, fine membrane fibres avoid a uniform luminous outline.
    Geometry.EdgePath(vg,geometry,scale,ox,oy,x0,y0,x1,y1,true)
    nvgStrokeWidth(vg,math.max(.7,scale*.025));nvgStrokeColor(vg,nvgRGBA(105,67,120,100));nvgStroke(vg)
    -- Fine advected filaments read the same FlowAt as movement, including cards.
    -- Cool, restrained streaks stay distinct from warm independent virions.
    ---@type {x:number,y:number}[]
    local heads=geometry.heads or {};geometry.heads=heads
    local headCount=0
    nvgBeginPath(vg)
    for _,mark in ipairs(map.flowMarks) do
        local mx,my=Visual.MarkPosition(map,mark,time)
        if mx>x0-1 and mx<x1+1 and my>y0-1 and my<y1+1 then
            local vx,vy=map:FlowAt(mx,my,time);local speed=math.sqrt(vx*vx+vy*vy)
            if speed>.08 and map:Contains(mx,my,.65) then
                local ux,uy=vx/speed,vy/speed
                local len=.32+.16*speed
                local tx,ty=ox+(mx+ux*len*.5)*scale,oy+(my+uy*len*.5)*scale
                nvgMoveTo(vg,tx-ux*len*scale,ty-uy*len*scale);nvgLineTo(vg,tx,ty)
                headCount=headCount+1
                local head=heads[headCount] or {x=tx,y=ty};heads[headCount]=head
                head.x,head.y=tx,ty
            end
        end
    end
    nvgStrokeWidth(vg,math.max(.8,scale*.018))
    nvgStrokeColor(vg,nvgRGBA(133,174,184,108));nvgStroke(vg)
    nvgBeginPath(vg)
    for i=1,headCount do nvgCircle(vg,heads[i].x,heads[i].y,math.max(.65,scale*.024)) end
    rgba(vg,149,187,195,130);nvgFill(vg)
end
return Visual
