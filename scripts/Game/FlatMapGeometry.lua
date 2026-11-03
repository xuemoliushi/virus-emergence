-- Derived presentation data only. The floor grid remains the collision authority.
-- Weak keys release old worlds; no simulation RNG or serialized map fields.
local Geometry={}
local cache=setmetatable({},{__mode='k'})
local SIZE=8
local EMPTY={}

function Geometry.Invalidate(map) cache[map]=nil end

function Geometry.Get(map)
    local data=cache[map]
    if data and data.floor==map.floor and data.width==map.width and data.height==map.height
        and data.flows==map.flows and data.flowCount==#map.flows then return data end
    data={floor=map.floor,width=map.width,height=map.height,flows=map.flows,
        flowCount=#map.flows,wallRows={},chunks={},flowSegments={}}
    local edges,starts={},{}
    local function open(x,y)
        return x>=0 and y>=0 and x<map.width and y<map.height and map.floor[y+1][x+1]
    end
    local function edge(x,y,tx,ty,direction)
        local e={x=x,y=y,tx=tx,ty=ty,direction=direction}
        edges[#edges+1]=e
        local key=y*(map.width+1)+x
        local list=starts[key] or {};starts[key]=list;list[#list+1]=e
    end
    for y=0,map.height-1 do
        local runs={};data.wallRows[y+1]=runs
        local x=0
        while x<map.width do
            if not open(x,y) then
                local first=x
                repeat x=x+1 until x>=map.width or open(x,y)
                runs[#runs+1]={x=first,w=x-first}
            else x=x+1 end
        end
        for gx=0,map.width-1 do if not open(gx,y) then
            if open(gx,y-1) then edge(gx,y,gx+1,y,0) end
            if open(gx+1,y) then edge(gx+1,y,gx+1,y+1,1) end
            if open(gx,y+1) then edge(gx+1,y+1,gx,y+1,2) end
            if open(gx-1,y) then edge(gx,y+1,gx,y,3) end
        end end
    end
    local function piece(ax,ay,bx,by,cx,cy)
        local mx,my=(ax+bx)*.5,(ay+by)*.5
        local ix,iy=math.floor(mx/SIZE),math.floor(my/SIZE)
        local row=data.chunks[iy] or {};data.chunks[iy]=row
        local chunk=row[ix] or {};row[ix]=chunk
        chunk[#chunk+1]={ax=ax,ay=ay,bx=bx,by=by,cx=cx,cy=cy,
            minX=math.min(ax,bx)-1,maxX=math.max(ax,bx)+1,
            minY=math.min(ay,by)-1,maxY=math.max(ay,by)+1,
            highlight=(math.floor(ax*11+ay*7)%5)<2}
    end
    for _,first in ipairs(edges) do if not first.used then
        local points={};local current=first
        repeat
            current.used=true;points[#points+1]=current
            local candidates=starts[current.ty*(map.width+1)+current.tx] or {}
            ---@type table?
            local nextEdge=nil
            local best=5
            for _,candidate in ipairs(candidates) do
                if not candidate.used or candidate==first then
                    local turn=(candidate.direction-current.direction)%4
                    local priority=turn==1 and 0 or turn==0 and 1 or turn==3 and 2 or 3
                    if priority<best then nextEdge,best=candidate,priority end
                end
            end
            current=nextEdge
        until not current or current==first
        -- Remove collinear grid vertices before building rounded corners.
        local corners={}
        for i,p in ipairs(points) do
            local previous=points[(i-2)%#points+1]
            if previous.direction~=p.direction then corners[#corners+1]=p end
        end
        for i,p in ipairs(corners) do
            local previous,nextPoint=corners[(i-2)%#corners+1],corners[i%#corners+1]
            local dx,dy=p.x-previous.x,p.y-previous.y
            local length=math.sqrt(dx*dx+dy*dy)
            local ex,ey=nextPoint.x-p.x,nextPoint.y-p.y
            local nextLength=math.sqrt(ex*ex+ey*ey)
            local trim=math.min(.46,length*.46,nextLength*.46)
            p.ax,p.ay=p.x-dx/length*trim,p.y-dy/length*trim
            p.bx,p.by=p.x+ex/nextLength*trim,p.y+ey/nextLength*trim
        end
        for i,p in ipairs(corners) do
            piece(p.ax,p.ay,p.bx,p.by,p.x,p.y)
            local q=corners[i%#corners+1]
            local length=math.sqrt((q.ax-p.bx)^2+(q.ay-p.by)^2)
            local count=math.max(1,math.ceil(length/4))
            for j=1,count do
                local a,b=(j-1)/count,j/count
                piece(p.bx+(q.ax-p.bx)*a,p.by+(q.ay-p.by)*a,
                    p.bx+(q.ax-p.bx)*b,p.by+(q.ay-p.by)*b)
            end
        end
    end end
    -- Vortex chords and their decal tessellation are static, too.
    for _,flow in ipairs(map.flows) do
        local segments={};data.flowSegments[flow.id]=segments
        local function segment(a,b)
            local dx,dy=b.x-a.x,b.y-a.y;local length=math.sqrt(dx*dx+dy*dy)
            if length>1e-6 then segments[#segments+1]={a=a,b=b,length=length,
                ux=dx/length,uy=dy/length,count=math.max(1,math.ceil(length/5))} end
        end
        if flow.kind=='vortex' then
            local count=math.ceil(math.pi*2*flow.ringRadius/3)
            for i=0,count-1 do
                local a,b=i/count*math.pi*2,(i+1)/count*math.pi*2
                segment({x=flow.cx+math.cos(a)*flow.ringRadius,y=flow.cy+math.sin(a)*flow.ringRadius},
                    {x=flow.cx+math.cos(b)*flow.ringRadius,y=flow.cy+math.sin(b)*flow.ringRadius})
            end
        else for i=1,#flow.points-1 do segment(flow.points[i],flow.points[i+1]) end end
    end
    cache[map]=data
    return data
end

function Geometry.EdgePath(vg,data,scale,ox,oy,x0,y0,x1,y1,detail)
    nvgBeginPath(vg)
    local visible=data.visibleEdges or {};data.visibleEdges=visible
    if detail then
        for _,p in ipairs(visible) do if p.highlight then
            nvgMoveTo(vg,ox+p.ax*scale,oy+p.ay*scale)
            if p.cx then nvgQuadTo(vg,ox+p.cx*scale,oy+p.cy*scale,ox+p.bx*scale,oy+p.by*scale)
            else nvgLineTo(vg,ox+p.bx*scale,oy+p.by*scale) end
        end end
        return
    end
    local count=0
    for iy=math.floor((y0-4)/SIZE),math.floor((y1+4)/SIZE) do
        local row=data.chunks[iy]
        if row then for ix=math.floor((x0-4)/SIZE),math.floor((x1+4)/SIZE) do
            for _,p in ipairs(row[ix] or EMPTY) do
                if p.maxX>x0 and p.minX<x1 and p.maxY>y0 and p.minY<y1 then
                    count=count+1;visible[count]=p
                    nvgMoveTo(vg,ox+p.ax*scale,oy+p.ay*scale)
                    if p.cx then nvgQuadTo(vg,ox+p.cx*scale,oy+p.cy*scale,ox+p.bx*scale,oy+p.by*scale)
                    else nvgLineTo(vg,ox+p.bx*scale,oy+p.by*scale) end
                end
            end
        end end
    end
    for i=#visible,count+1,-1 do visible[i]=nil end
end

return Geometry
