-- Conservative centre buckets. Queries preserve source-array order; exact
-- distance, wall and state checks remain with the authoritative caller.
---@class SpatialGrid
local Grid = {}
Grid.__index = Grid

function Grid.New(size)
    local self=setmetatable({},Grid)
    self:init(size)
    return self
end

function Grid:init(size)
    self.size=size
    ---@type table<number,table<number,table[]>>
    self.rows={}
    ---@type table<table,number>
    self.order={}
    self.maxRadius=0
    self.sourceCount=0
end

function Grid:Build(items)
    self.sourceCount=#items
    for _, row in pairs(self.rows) do
        for _, bucket in pairs(row) do
            for i=#bucket,1,-1 do bucket[i]=nil end
        end
    end
    for item in pairs(self.order) do self.order[item]=nil end
    self.maxRadius=0
    for index,item in ipairs(items) do
        local x,y=math.floor(item.x/self.size),math.floor(item.y/self.size)
        local row=self.rows[y]
        if not row then row={};self.rows[y]=row end
        local bucket=row[x]
        if not bucket then bucket={};row[x]=bucket end
        bucket[#bucket+1]=item
        self.order[item]=index
        self.maxRadius=math.max(self.maxRadius,item.radius or 0)
    end
end

function Grid:Query(x,y,radius,result)
    result=result or {}
    for i=#result,1,-1 do result[i]=nil end
    local size=self.size
    local order=self.order
    local last,sorted=0,true
    for by=math.floor((y-radius)/size),math.floor((y+radius)/size) do
        local row=self.rows[by]
        if row then
            for bx=math.floor((x-radius)/size),math.floor((x+radius)/size) do
                local bucket=row[bx]
                if bucket and #bucket>0 then
                    -- Each bucket is already in source order. Dense queries often
                    -- touch just one; only sort when concatenating reverses order.
                    if order[bucket[1]]<last then sorted=false end
                    last=order[bucket[#bucket]]
                    for _,item in ipairs(bucket) do result[#result+1]=item end
                end
            end
        end
    end
    if not sorted then table.sort(result,function(a,b) return order[a]<order[b] end) end
    return result
end

-- Boolean contact queries need neither a sorted candidate array nor the nearest
-- identity. Keep the exact distance comparison used by the original caller.
function Grid:AnyInRange(x,y,padding,radius,stateA,stateB)
    local reach=padding+radius+self.maxRadius
    local size=self.size
    for by=math.floor((y-reach)/size),math.floor((y+reach)/size) do
        local row=self.rows[by]
        if row then for bx=math.floor((x-reach)/size),math.floor((x+reach)/size) do
            local bucket=row[bx]
            if bucket then for _,item in ipairs(bucket) do
                if item.state==stateA or item.state==stateB then
                    local dx,dy=x-item.x,y-item.y
                    local range=item.radius+padding+radius
                    if math.abs(dx)<=range and math.abs(dy)<=range
                        and math.sqrt(dx*dx+dy*dy)<=range then return true end
                end
            end end
        end end
    end
    return false
end

return Grid
