-- Runtime adapter over the approved candidate data. No second world or RNG.
local Preview=require('Core.FlatMapPreview')
local Random=require('Core.MapRandom')
local Defaults=require('Core.FlatMapConfig')
---@class FlatWorldMap: FlatMapPreview
---@field flowOverride {x:number,y:number,ux:number,uy:number,radius:number,expiresAt:number}?
---@field InitRuntime fun(self:FlatWorldMap,startType:string?)
local Map={}
Map.__index=Map
setmetatable(Map,{__index=Preview})
local EPS=1e-7
local function finite(x) return type(x)=='number' and x==x and math.abs(x)<math.huge end
local function clamp(x,a,b) return math.max(a,math.min(b,x)) end

---@return FlatWorldMap
function Map.New(cfg,startType)
    local options={}
    for k,v in pairs(Defaults) do options[k]=v end
    options.mapSeed=cfg.mapSeed==nil and Random.NewSeed() or cfg.mapSeed
    for _,key in ipairs({'width','height','cellCount','cellRadiusMin','cellRadiusMax'}) do
        if cfg[key]~=nil then options[key]=cfg[key] end
    end
    options.mapGenerationVersion=cfg.mapGenerationVersion or Defaults.mapGenerationVersion
    options.coverageCellCount=options.cellCount-options.supplementCellCount
    local self=Preview.New(options) --[[@as FlatWorldMap]]
    setmetatable(self,Map)
    self:InitRuntime(startType)
    return self
end

function Map:NearestOpen(x,y,radius)
    if self:Contains(x,y,radius) then return x,y end
    local best,bx,by=math.huge,self.spawn.x,self.spawn.y
    for gy=0,self.height-1 do for gx=0,self.width-1 do
        local px,py=gx+.5,gy+.5
        local d=(px-x)^2+(py-y)^2
        if d<best and self:Contains(px,py,radius) then best,bx,by=d,px,py end
    end end
    return bx,by
end

function Map:InitRuntime(startType)
    self.isFlatMap=true
    self.startType=startType or 'UPPER_AIRWAY'
    self._scale=1
    self.cellGap=self.config.cellGap
    self.spawnSafeRadius=self.config.spawnSafeRadius
    self.regions,self.channels,self.immuneSpawns,self.renderRows={},{},{},{}
    self.navigationCache={}
    -- Statistics partitions only; these neither carve rooms nor block movement.
    local definitions={{'UPPER_AIRWAY','出生组织',self.spawn.x,self.spawn.y,.15,.1},
        {'TRACHEA','开阔组织',60,36,.30,.16},
        {'BRONCHUS_LEFT','西侧组织',28,82,.56,.24},
        {'BRONCHUS_RIGHT','东侧组织',92,84,.62,.27},
        {'DEEP_LUNG','远端组织',60,125,.92,.35}}
    for id,d in ipairs(definitions) do
        local x,y=self:NearestOpen(d[3],d[4],1.35)
        self.regions[id]={id=id,type=d[1],name=d[2],x=x,y=y,rx=12,ry=12,
            depth=d[5],baseImmunePressure=d[6],neighbors={},inflammation=0,damage=0}
        for other=1,5 do if other~=id then self.regions[id].neighbors[#self.regions[id].neighbors+1]=other end end
    end
    self.startPoints={UPPER_AIRWAY=self.spawn,TRACHEA=self.spawn,DEEP_LUNG=self.spawn}
    for _,c in ipairs(self.cells) do c.regionId=self:RegionAt(c.x,c.y) end
    -- Director continues assigning adjacent areas through real traversable routes.
    for _,route in ipairs(self.majorRoutes) do
        local a,b=route.points[1],route.points[#route.points]
        self.channels[#self.channels+1]={id=#self.channels+1,points=route.points,width=route.width,
            connectedRegions={self:RegionAt(a.x,a.y),self:RegionAt(b.x,b.y)},strength=0,speed=0,channelType='normal'}
    end
    -- Deterministic legal entry points; no simulation random calls in map setup.
    local sx,sy=self.spawn.x,self.spawn.y
    for _,offset in ipairs({{8,0},{0,8},{-8,0},{0,-8},{6,6},{-6,6}}) do
        local x,y=sx+offset[1],sy+offset[2]
        if self:Contains(x,y,.5) then self.immuneSpawns[#self.immuneSpawns+1]={x=x,y=y,regionId=self:RegionAt(x,y)} end
    end
    for _,c in ipairs(self.cells) do
        if c.id%8==0 and (c.x-sx)^2+(c.y-sy)^2>64 and self:Contains(c.x,c.y,.5) then
            self.immuneSpawns[#self.immuneSpawns+1]={x=c.x,y=c.y,regionId=c.regionId}
        end
    end
    -- Run-length floor geometry is reused by normal view and minimap, not masks.
    for y=0,self.height-1 do
        local row={};local x=0
        while x<self.width do
            if self.floor[y+1][x+1] then
                local first=x
                repeat x=x+1 until x>=self.width or not self.floor[y+1][x+1]
                row[#row+1]={x=first,w=x-first}
            else x=x+1 end
        end
        self.renderRows[y+1]=row
    end
    self.flowMarks={}
    self.flowGeometry={}
    for _,f in ipairs(self.flows) do
        self.flowGeometry[f.id]={}
        local color=f.kind=='vortex' and 'vortex' or f.kind=='counter' and 'counter' or 'jet'
        if f.kind=='vortex' then
            local n=math.ceil(math.pi*2*f.ringRadius/2.5)
            for i=0,n-1 do
                local a=i/n*math.pi*2
                self.flowMarks[#self.flowMarks+1]={x=f.cx+math.cos(a)*f.ringRadius,y=f.cy+math.sin(a)*f.ringRadius,color=color,flowId=f.id,angle=a}
            end
        else
            local along,nextMark=0,1
            for i=1,#f.points-1 do
                local a,b=f.points[i],f.points[i+1]
                local length=math.sqrt((b.x-a.x)^2+(b.y-a.y)^2)
                self.flowGeometry[f.id][i]={a=a,b=b,length=length,along=along}
                while nextMark<=along+length do
                    local t=(nextMark-along)/length
                    self.flowMarks[#self.flowMarks+1]={x=a.x+(b.x-a.x)*t,y=a.y+(b.y-a.y)*t,color=color,flowId=f.id,along=nextMark}
                    nextMark=nextMark+2.5
                end
                along=along+length
            end
        end
    end
    print(string.format('[FlatMap] seed=%d version=%d size=%dx%dm cells=%d islands=10 ridges=8 flows=%d open=%.2f%% generation=%.2fms',
        self.seed,self.generationVersion,self.width,self.height,#self.cells,#self.flows,self.walkableRatio*100,self.generationMs))
end

function Map:RegionAt(x,y)
    if not self:Contains(x,y,0) then return 0 end
    local best,id=math.huge,1
    for _,r in ipairs(self.regions) do
        local d=(r.x-x)^2+(r.y-y)^2
        if d<best then best,id=d,r.id end
    end
    return id
end
function Map:DepthAt(x,y)
    local id=self:RegionAt(x,y)
    return id>0 and self.regions[id].depth or 0
end

-- Exact disk sweep against the rounded expansion of every solid metre square.
-- Union of two rectangles and four corner circles, never endpoint-only checks.
local function boxHit(x,y,dx,dy,l,t,r,b)
    local enter,leave=0,1
    if math.abs(dx)<1e-14 then if x<=l or x>=r then return 1 end
    else local a,c=(l-x)/dx,(r-x)/dx;enter=math.max(enter,math.min(a,c));leave=math.min(leave,math.max(a,c)) end
    if math.abs(dy)<1e-14 then if y<=t or y>=b then return 1 end
    else local a,c=(t-y)/dy,(b-y)/dy;enter=math.max(enter,math.min(a,c));leave=math.min(leave,math.max(a,c)) end
    return enter<leave and enter>=0 and enter<1 and enter or 1
end
local function circleHit(x,y,dx,dy,cx,cy,r)
    local px,py=x-cx,y-cy
    local a=dx*dx+dy*dy
    if a<1e-20 then return 1 end
    local b=px*dx+py*dy
    local c=px*px+py*py-r*r
    local disc=b*b-a*c
    if disc<=0 then return 1 end
    local t=(-b-math.sqrt(disc))/a
    return t>=-1e-12 and t<1 and math.max(0,t) or 1
end
function Map:_Sweep(x,y,dx,dy,radius)
    local r=radius or 0
    if not self:Contains(x,y,r) then return 0,0,0 end
    if dx*dx+dy*dy<1e-20 then return 1,0,0 end
    local hit,hx,hy=1,0,0
    for gy=math.max(0,math.floor(math.min(y,y+dy)-r)),math.min(self.height-1,math.floor(math.max(y,y+dy)+r)) do
        for gx=math.max(0,math.floor(math.min(x,x+dx)-r)),math.min(self.width-1,math.floor(math.max(x,x+dx)+r)) do
            if not self.floor[gy+1][gx+1] then
                local t=math.min(boxHit(x,y,dx,dy,gx-r,gy,gx+1+r,gy+1),boxHit(x,y,dx,dy,gx,gy-r,gx+1,gy+1+r))
                if r>0 then
                    for cy=gy,gy+1 do for cx=gx,gx+1 do t=math.min(t,circleHit(x,y,dx,dy,cx,cy,r)) end end
                end
                if t<hit then hit,hx,hy=t,gx,gy end
            end
        end
    end
    if hit==1 then return 1,0,0 end
    local px,py=x+dx*hit,y+dy*hit
    local nx,ny=px-clamp(px,hx,hx+1),py-clamp(py,hy,hy+1)
    local length=math.sqrt(nx*nx+ny*ny)
    if length>1e-12 then return hit,nx/length,ny/length end
    local lengthD=math.sqrt(dx*dx+dy*dy)
    return hit,-dx/lengthD,-dy/lengthD
end
function Map:_ConvexPathClear(x,y,tx,ty,radius)
    if not self:Contains(tx,ty,radius) then return false end
    return self:_Sweep(x,y,tx-x,ty-y,radius)>=1
end
function Map:Move(x,y,tx,ty,radius)
    local r=radius or 0
    if not finite(x) or not finite(y) or not finite(tx) or not finite(ty) or not finite(r) or r<0 then return x,y end
    local dx,dy=tx-x,ty-y
    -- A short step whose entire swept disk stays strictly inside one open
    -- metre square cannot touch any wall. Most drifting particles take this
    -- path; boundaries/corners/long moves retain the exact sweep below.
    local gx,gy=math.floor(x),math.floor(y)
    local row=self.floor[gy+1]
    if gx>=0 and gy>=0 and gx<self.width and gy<self.height and row and row[gx+1]
        and math.min(x,tx)-r>gx+EPS and math.max(x,tx)+r<gx+1-EPS
        and math.min(y,ty)-r>gy+EPS and math.max(y,ty)+r<gy+1-EPS then
        return x+dx,y+dy
    end
    -- Crossing an open grid seam is also safe when every square touched by
    -- the swept bounding box is open. Near walls retain the exact sweep/slide.
    if r<=.5 and math.abs(dx)<.25 and math.abs(dy)<.25 then
        local left,right=math.min(x,tx)-r,math.max(x,tx)+r
        local top,bottom=math.min(y,ty)-r,math.max(y,ty)+r
        if left>EPS and top>EPS and right<self.width-EPS and bottom<self.height-EPS then
            local open=true
            for by=math.floor(top),math.floor(bottom) do
                for bx=math.floor(left),math.floor(right) do
                    if not self.floor[by+1][bx+1] then open=false;break end
                end
                if not open then break end
            end
            if open then return x+dx,y+dy end
        end
    end
    if not self:Contains(x,y,r) then return x,y end
    for _=1,3 do
        local t,nx,ny=self:_Sweep(x,y,dx,dy,r)
        if t==1 then
            if self:Contains(x+dx,y+dy,r) then return x+dx,y+dy end
            local length=math.sqrt(dx*dx+dy*dy)
            local back=length>EPS and 1-EPS/length or 0
            local px,py=x+dx*back,y+dy*back
            if self:Contains(px,py,r) then return px,py end
            return x,y
        end
        local length=math.sqrt(dx*dx+dy*dy)
        if length<EPS then return x,y end
        local travel=math.max(0,t-EPS/length)
        local px,py=x+dx*travel,y+dy*travel
        if not self:Contains(px,py,r) then return x,y end
        x,y=px,py
        dx,dy=dx*(1-travel),dy*(1-travel)
        local into=math.min(0,dx*nx+dy*ny)
        dx,dy=dx-nx*into,dy-ny*into
    end
    return x,y
end

---@return number, number
function Map:FlowAt(x,y,time)
    local vx,vy=Preview.FlowAt(self,x,y,time)
    local override=self.flowOverride
    if override and (time or 0)<override.expiresAt then
        local d=math.sqrt((x-override.x)^2+(y-override.y)^2)
        if d<override.radius then
            local u=1-d/override.radius;local blend=u*u*(3-2*u)
            local speed=math.sqrt(vx*vx+vy*vy)
            local old=math.atan(vy,vx);local wanted=math.atan(override.uy,override.ux)
            local angle=old+((wanted-old+math.pi)%(2*math.pi)-math.pi)*blend
            vx,vy=math.cos(angle)*speed,math.sin(angle)*speed
        end
    end
    return vx,vy
end
return Map
