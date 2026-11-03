-- 仅表现几何。在调用方现有 NanoVG 帧与上下文内使用：
-- nvgTranslate(cellScreenX,cellScreenY); nvgRotate(cell.rotation);
-- nvgScale(cellDrawCanvasSize/1254,cellDrawCanvasSize/1254).
-- 原点是 1254 源画布中心 (627,627)，不是 alpha 包围盒中心。
-- 本体 -> 膜 -> 液泡 -> 潜伏颗粒 -> DrawPatch -> DrawGlint -> DrawParticle；不修改玩法数据。
local VU = require("Game.VisualUtils")
local Config = require("Core.Config")
local ImageCache = require("urhox-libs/UI/Core/ImageCache")
local Config = require("Core.Config")

---@class CellSurfaceUnion
---@field x integer
---@field y integer
---@field width integer
---@field height integer
---@field denominator integer
---@field rows string[]
---@class CellSurfacePatch
---@field path string
---@field meta_path string?
---@field canvas integer
---@field bounds integer[]
---@field anchor number[]
---@field visible_width number?
---@field grown_fraction number?
---@field cell_foreground_width number
---@field max_scale number
---@field geometry_version integer
---@field stack {scale:number,rot:number}[]
---@field stack_meta_path string?
---@field source_sha256 string
---@field crop number[]?
---@field output_pixels integer
---@class CellSurfacePatchMeta
---@field canvas integer
---@field center number[]
---@field files table<string,string>
---@field block {size:number[]}
---@field size_guide {grown_patch_frac_of_cell:string}
---@class CellSurfaceStackMeta
---@field canvas integer
---@field center number[]
---@field stack {scale:number,rot:number}[]
---@class CellSurfaceData
---@field version integer
---@field canvas integer
---@field center number[]
---@field angle_bins integer
---@field foreground_diameter number
---@field visible_particle_pixels number
---@field particle_fraction number
---@field union CellSurfaceUnion
---@field placements number[][]
---@field placement_subdivisions integer?
---@field fine_placements number[][]?
---@field patch CellSurfacePatch
---@field glint {path:string,canvas:integer,bounds:integer[]}
---@class CellSurfaceMeta
---@field canvas integer
---@field center number[]
---@field contact number[]
---@field outward number[]
---@field r_rim number
---@class CellSurfacePose
---@field x number 量化角度对应的真实膜点，以细胞画布中心为原点
---@field y number
---@field spriteX number 粒子与亮斑共享的原始画布中心
---@field spriteY number
---@field membraneX number 量化射线与真实膜交点，以细胞中心为原点
---@field membraneY number
---@field normalX number y 向下坐标系中，真实膜点环离线平滑后的外法线
---@field normalY number
---@field rotation number y 向下坐标系中的精灵旋转，单位弧度
---@field scale number 每粒子源像素对应的细胞源像素数
---@field size number 共享 192 画布在细胞源坐标中的边长
---@field bin integer 从 1 开始的原两度分档索引
---@field subBin integer 从 1 开始的闭环细分姿态索引
---@field key string
---@field cos number
---@field sin number
---@field contactX number 美术元数据接触点的实际变换结果，供验收
---@field contactY number
---@field contact table? 当前附着的只读接触快照，供局部事件光效使用
---@class CellSurfaceRun
---@field stop integer 相对裁剪后 union 行起点的右边界，不含边界像素
---@field value number 精确 alpha，范围 0..1
---@class CellSurfaceSourcePixel
---@field x number 原始源画布中的像素中心
---@field y number
---@field r integer
---@field g integer
---@field b integer
---@field a integer
---@class CellSurfaceRGBA
---@field width integer
---@field height integer
---@field pixels integer[] 非预乘 RGBA 打包值，r 在最低字节
---@field nonzero CellSurfaceSourcePixel[]
---@class CellSurfaceEntry
---@field texture Texture2D?
---@field handle integer
---@field stamp integer
---@field pixels integer
---@field x number
---@field y number
---@field size number
---@field rotation number
---@class CellSurfaceAtlas
---@field version integer
---@field encoding string
---@field page_size integer
---@field sub_bins integer
---@field tile_sizes {glint:integer,patch:integer}
---@field patch CellSurfacePatch
---@field scale number
---@field pages string[]
---@field glints integer[][]
---@field patches integer[][][]
---@class CellSurfaceOptions
---@field data CellSurfaceData? 测试可注入；正式运行从资源 JSON 加载一次
---@field atlas CellSurfaceAtlas? 离线精确蒙版图集
---@field meta CellSurfaceMeta?
---@field patchMeta CellSurfacePatchMeta?
---@field stackMeta CellSurfaceStackMeta?
---@field maxResources integer? 范围 48..96，默认 72
---@field embedPixels number? 粒子源像素中的嵌入量，按美术公式默认 8
---@class CellSurface
---@field data CellSurfaceData?
---@field meta CellSurfaceMeta?
---@field patchMeta CellSurfacePatchMeta?
---@field stackMeta CellSurfaceStackMeta?
---@field atlas CellSurfaceAtlas?
---@field atlasPages table<number,{image:Image,path:string,stamp:number}>
---@field atlasPending table<number,boolean>
---@field atlasGeneration integer
---@field unionRows CellSurfaceRun[][]
---@field sources table<string,CellSurfaceRGBA>
---@field entries table<string,CellSurfaceEntry>
---@field poses table<string,CellSurfacePose>
---@field failures table<string,boolean>
---@field nvg NVGContextWrapper?
---@field GetPlacement fun(self:CellSurface, cell:table, contact:number|table, r:number?):CellSurfacePose?
---@field DrawPatch fun(self:CellSurface, nvg:NVGContextWrapper, pose:CellSurfacePose?, progress:number, alpha:number?, activity:number?):boolean
---@field BeginFrame fun(self:CellSurface)
---@field GetData fun(self:CellSurface):CellSurfaceData?
---@field DrawGlint fun(self:CellSurface,nvg:NVGContextWrapper,pose:CellSurfacePose?,alpha:number?):boolean
---@field DrawParticle fun(self:CellSurface,nvg:NVGContextWrapper,pose:CellSurfacePose?,alpha:number?):boolean
---@field Destroy fun(self:CellSurface)
local Surface = {}
Surface.__index = Surface
local TAU = math.pi * 2
local DATA_PATH = "image/cell_surface_data.json"
local META_PATH = "image/virus_attached_meta.json"
local PARTICLE_PATH = Config.ArtSlots.virusAttachedParticle
local ATLAS_PATH = "image/cell_surface_atlas/manifest.json"
local ATLAS_PAGE_LIMIT = 8
-- 仅调度图片后台解码，不创建渲染上下文；事件节点持有到最后一个任务结束。
---@type Node?
local atlasEventNode = nil
local atlasRequests = {}
local function CleanupAtlasEvents()
    if not next(atlasRequests) and atlasEventNode then
        atlasEventNode:Dispose()
        atlasEventNode = nil
    end
end
local function EnsureAtlasEvents()
    if atlasEventNode then return end
    atlasEventNode = Node()
    local handler = atlasEventNode:CreateScriptObject("LuaScriptObject")
    handler:SubscribeToEvent("ResourceBackgroundLoaded", function(_, _, eventData)
        local path = eventData:GetString("ResourceName")
        local requests = atlasRequests[path]
        if not requests then return end
        atlasRequests[path] = nil
        local image = eventData:GetBool("Success") and cache:GetExistingResource("Image",path) or nil --[[@as Image?]]
        -- 图集专属资源移出共享cache，由本模块显式持有和Dispose，避免GC前缓存积累。
        if image then cache:ReleaseResource("Image",path,true) end
        local live = {}
        for _,request in ipairs(requests) do
            local surface = request.surface
            if not surface.destroyed and surface.atlasGeneration == request.generation then
                surface.atlasPending[request.page] = nil
                live[#live+1] = request
            end
        end
        if image then
            for index,request in ipairs(live) do
                ---@type Image?
                local owned = nil
                local ok,err = pcall(function()
                    -- 多视图各持独立Image；最后一份直接移交，未移交对象立即清理。
                    owned = index == #live and image or image:GetSubimage(IntRect(0,0,1024,1024))
                    assert(owned,"Cannot clone baked atlas page")
                    request.surface:AcceptAtlasPage(request.page,path,owned)
                    owned = nil
                end)
                if not ok then
                    if owned then owned:Dispose() end
                    request.surface:Fail("atlas:"..request.page,tostring(err))
                end
            end
            if #live == 0 then image:Dispose() end
        else
            for _,request in ipairs(live) do request.surface:Fail("atlas:"..request.page,"Background image failed "..path) end
        end
        CleanupAtlasEvents()
    end)
end

---@param v number
---@return number
local function Clamp(v) return math.max(0,math.min(1,v)) end

---@param path string
---@return table?
local function ReadJSON(path)
    if not cache or not cjson then return nil end -- 允许无引擎的纯 Lua 测试桩
    local file = cache:GetFile(path)
    if not file then error("Cannot read resource "..path) end
    local lines = {}
    while not file:IsEof() do lines[#lines+1] = file:ReadLine() end
    file:Dispose()
    local result = cjson.decode(table.concat(lines,"\n"))
    if type(result) ~= "table" then error("Invalid JSON "..path) end
    return result
end

---@param options CellSurfaceOptions?
---@return CellSurface
function Surface.New(options)
    local self = setmetatable({},Surface)
    self:Init(options or {})
    return self
end

---@param options CellSurfaceOptions
function Surface:Init(options)
    self.options = options
    self.data = options.data
    self.meta = options.meta
    self.patchMeta = options.patchMeta
    self.stackMeta = options.stackMeta
    self.atlas = options.atlas
    self.atlasPages = {}
    self.atlasPending = {}
    self.atlasGeneration = math.floor((self.atlasGeneration or 0)+1)
    self.atlasWaits = 0
    self.atlasClock = 0
    self.atlasLoads = 0
    self.unionRows = {}
    self.sources = {}
    self.entries = {}
    self.poses = {}
    self.poseCount = 0
    self.failures = {}
    self.nvg = nil
    self.maxResources = math.floor(math.max(48,math.min(96,options.maxResources or 72)))
    self.embedPixels = options.embedPixels or 8
    self.clock = 0
    self.count = 0
    self.hits = 0
    self.misses = 0
    self.evictions = 0
    self.generatedPixels = 0
    self.sourceLoads = 0
    self.destroyed = false
    ---@type table<string,boolean>?
    self.framePins=nil
    self.pendingTextures={}
    self.textureQueue={}
    self.frameSerial=0
    self.frameCreated=0
    local ok,err = pcall(function()
        if not self.data then self.data = ReadJSON(DATA_PATH) --[[@as CellSurfaceData?]] end
        if not self.meta then self.meta = ReadJSON(META_PATH) --[[@as CellSurfaceMeta?]] end
        if not options.data and not self.atlas then
            self.atlas = ReadJSON(ATLAS_PATH) --[[@as CellSurfaceAtlas?]]
            assert(self.atlas,"Missing baked membrane atlas")
        end
        if not self.data or not self.meta then return end
        assert(self.data.canvas == 1254 and self.meta.canvas == 192,"Unexpected source canvas")
        assert(self.data.center[1] == 627 and self.data.center[2] == 627,"Unexpected cell centre")
        assert(self.meta.center[1] == 96 and self.meta.center[2] == 96,"Unexpected particle centre")
        assert(#self.data.placements == self.data.angle_bins,"Incomplete membrane contour")
        if self.data.fine_placements then
            assert(self.data.placement_subdivisions == 8 and #self.data.fine_placements == self.data.angle_bins*8,
                "Incomplete true membrane subdivision")
        end
        local patch = self.data.patch
        assert(self.data.version == 5 and patch.geometry_version == 2,"Outdated infection surface geometry")
        assert(patch.path == "image/infection_block_flat.png" and patch.canvas == 300
            and patch.anchor[1] == 150 and patch.anchor[2] == 150,"Wrong original infection source/anchor")
        assert(patch.cell_foreground_width == self.data.union.width and patch.visible_width == 106
            and patch.grown_fraction == .45 and math.abs(106*patch.max_scale-patch.cell_foreground_width*.45)<1e-8,
            "Patch width must be 45% of actual cell foreground")
        local expectedStack = {{scale=.55,rot=0},{scale=.78,rot=25},{scale=1,rot=-20}}
        assert(#patch.stack == #expectedStack,"Need three static infection layers")
        for index,expected in ipairs(expectedStack) do
            assert(patch.stack[index].scale == expected.scale and patch.stack[index].rot == expected.rot,
                "Wrong infection stack scale/rotation")
        end
        if patch.stack_meta_path and not self.stackMeta then
            self.stackMeta = ReadJSON(patch.stack_meta_path) --[[@as CellSurfaceStackMeta?]]
        end
        if cache then assert(self.stackMeta,"Missing infection stack metadata") end
        if self.stackMeta then
            local meta = self.stackMeta
            assert(meta.canvas == patch.canvas and meta.center[1] == 150 and meta.center[2] == 150
                and #meta.stack == #patch.stack,"Wrong infection stack metadata")
            for index,layer in ipairs(meta.stack) do
                assert(layer.scale == patch.stack[index].scale and layer.rot == patch.stack[index].rot,
                    "Infection stack disagrees with original metadata")
            end
        end
        -- crop是存储优化，不是矩形轮廓裁剪；后面的每个像素仍乘同位置union。
        local crop = patch.crop or {0,0,patch.canvas}
        assert(patch.output_pixels == crop[3] and crop[1]%1 == 0 and crop[2]%1 == 0
            and crop[1] >= 0 and crop[2] >= 0 and crop[1]+crop[3] <= patch.canvas and crop[2]+crop[3] <= patch.canvas,
            "Patch crop must preserve original pixels 1:1")
        assert(crop[1] <= patch.bounds[1]-4 and crop[2] <= patch.bounds[2]-4
            and crop[1]+crop[3] >= patch.bounds[3]+4 and crop[2]+crop[3] >= patch.bounds[4]+4,
            "Patch crop must keep entire foreground and transparent padding")
        if self.atlas then
            local atlas = self.atlas
            local samples = self.data.angle_bins*(self.data.placement_subdivisions or 1)
            assert(atlas.version == 2 and atlas.encoding == "straight-rgba-cropped" and atlas.page_size == 1024
                and atlas.sub_bins == samples and #atlas.glints == samples and #atlas.patches == samples,
                "Outdated/incomplete baked stack atlas")
            assert(atlas.tile_sizes.glint == self.meta.canvas and atlas.tile_sizes.patch == patch.output_pixels,
                "Wrong atlas output dimensions")
            for _,field in ipairs({"geometry_version","path","source_sha256","canvas","visible_width",
                                   "grown_fraction","cell_foreground_width","max_scale","output_pixels"}) do
                assert(atlas.patch[field] == patch[field],"Stale atlas patch field "..field)
            end
            ---@param baked number[]
            ---@param current number[]
            local function ValidateArray(baked,current)
                assert(#baked == #current,"Stale atlas patch array")
                for index,value in ipairs(current) do
                    assert(baked[index] == value,"Stale atlas patch array")
                end
            end
            ValidateArray(atlas.patch.anchor,patch.anchor)
            ValidateArray(atlas.patch.bounds,patch.bounds)
            ValidateArray(atlas.patch.crop or {0,0,patch.canvas},crop)
            assert(#atlas.patch.stack == #patch.stack,"Stale atlas stack length")
            for index,layer in ipairs(patch.stack) do
                assert(atlas.patch.stack[index].scale == layer.scale and atlas.patch.stack[index].rot == layer.rot,
                    "Stale atlas stack transform")
            end
            for _,tiles in ipairs(atlas.patches) do assert(#tiles == 3,"Atlas must contain three masks per pose") end
        end
        if patch.meta_path and not self.patchMeta then
            self.patchMeta = ReadJSON(patch.meta_path) --[[@as CellSurfacePatchMeta?]]
        end
        if patch.meta_path and cache then assert(self.patchMeta,"Missing infection block metadata") end
        if self.patchMeta then
            local meta = self.patchMeta
            assert(meta.canvas == patch.canvas and meta.center[1] == 150 and meta.center[2] == 150,
                "Wrong infection block canvas/centre")
            assert(meta.files.infection_block_flat and patch.path == "image/infection_block_flat.png",
                "Use recommended original flat infection block")
            assert(patch.anchor[1] == meta.center[1] and patch.anchor[2] == meta.center[2],"Wrong patch anchor")
            local actualWidth = patch.bounds[3]-patch.bounds[1]
            local percent = tonumber(meta.size_guide.grown_patch_frac_of_cell:match("([%d.]+)%%"))
            assert(percent and actualWidth == meta.block.size[1] and actualWidth == patch.visible_width,
                "Wrong visible patch width")
            local fraction = percent/100
            assert(patch.grown_fraction == fraction and patch.max_scale
                and patch.cell_foreground_width == self.data.union.width
                and math.abs(actualWidth*patch.max_scale-patch.cell_foreground_width*fraction)<1e-8,
                "Patch scale must use actual cell/patch foreground widths, not old 760/128px guide")
        end
        for rowIndex,row in ipairs(self.data.union.rows) do
            local runs = {}
            local stop = 0
            for offset = 1,#row,10 do
                local length = tonumber(row:sub(offset,offset+3),16)
                local numerator = tonumber(row:sub(offset+4,offset+9),16)
                assert(length and numerator,"Invalid union RLE")
                stop = stop + length
                runs[#runs+1] = {stop=stop,value=numerator/self.data.union.denominator}
            end
            assert(stop == self.data.union.width,"Wrong union row width")
            self.unionRows[rowIndex] = runs
        end
    end)
    if not ok then
        self.data,self.meta = nil,nil
        self:Fail("data",tostring(err))
    end
end

---@param key string
---@param reason string
function Surface:Fail(key,reason)
    if self.failures[key] then return end
    self.failures[key] = true
    -- 纯 Lua 回归测试桩允许缺少 Image/cache；真实引擎必须明确记录失败。
    -- 任何失败都不会退回绘制未经细胞 alpha 裁剪的亮斑。
    if cache and Image then print("[CellSurface] ERROR "..key..": "..reason) end
end

---@return CellSurfaceData?
---@return CellSurfaceMeta?
function Surface:GetData()
    if self.destroyed then self:Init(self.options) end
    return self.data,self.meta
end

---@return table
function Surface:GetStats()
    local pixels = 0
    for _,entry in pairs(self.entries) do pixels = pixels+entry.pixels end
    return {count=self.count,resources=self.count,maxResources=self.maxResources,hits=self.hits,misses=self.misses,
        evictions=self.evictions,sourceLoads=self.sourceLoads,generatedPixels=self.generatedPixels,
        atlasLoads=self.atlasLoads,atlasWaits=self.atlasWaits,
        atlasPending=(function() local n=0; for _ in pairs(self.atlasPending) do n=n+1 end; return n end)(),
        atlasPages=(function() local n=0; for _ in pairs(self.atlasPages) do n=n+1 end; return n end)(),
        textureBytes=pixels*4,angleBins=self.data and self.data.angle_bins or 0,
        poseCount=(function() local n=0; for _ in pairs(self.poses) do n=n+1 end; return n end)()}
end

-- 仅表现几何，不用于碰撞：中心 C 射线 -> 真实 alpha96 膜点 P。
--                    膜外
--                  粒子中心 O = P + n*(47.5-8)*scale
--                     | n（局部真实外法线，不是圆的径向法线）
--                 ----P---- 不规则膜
--                     | -n
--                  局部感染斑向内生长
-- 精灵方向 d 旋转到 -n；亮斑与粒子共享 O、rot、scale 及原始中心 (96,96)。
-- 接触方向可传世界角或显式局部角；不混用细胞世界坐标和源像素坐标。
---@param cell {x:number?,y:number?,rotation:number?}
---@param contact number|{angle:number?,x:number?,y:number?,localAngle:number?}
---@param r number? 每粒子源像素对应细胞源像素数，默认 760*.21/96
---@return CellSurfacePose?
function Surface:GetPlacement(cell,contact,r)
    if self.destroyed then self:Init(self.options) end
    if not self.data or not self.meta then return nil end
    local worldAngle = 0
    if type(contact) == "number" then
        worldAngle = contact
    elseif contact.localAngle then
        worldAngle = contact.localAngle+(cell.rotation or 0)
    elseif contact.angle then
        worldAngle = contact.angle
    elseif contact.x and contact.y then
        worldAngle = math.atan(contact.y-(cell.y or 0),contact.x-(cell.x or 0))
    end
    local localAngle = (worldAngle-(cell.rotation or 0)) % TAU
    local subdivisions = self.data.placement_subdivisions or 1
    local samples = self.data.fine_placements or self.data.placements
    local sampleCount = self.data.angle_bins*subdivisions
    local subIndex = 1+math.floor(localAngle/TAU*sampleCount+.5)%sampleCount
    local index = 1+(subIndex-1)//subdivisions
    local scale = r or self.data.foreground_diameter*self.data.particle_fraction/self.data.visible_particle_pixels
    if scale ~= scale or scale <= 0 or scale > 8 then return nil end
    -- 缩放精确参与几何和遮罩缓存键，避免量化遮罩与未量化粒子错位。
    -- 原 180 段各有 8 个弧长采样：0.25° 输入一步，不跨突起用直线虚造膜点。
    -- 只消费离线原始 alpha96 边界路径与平滑方向，不在此加入接触时间滤波。
    -- 同一细分姿态严格共享亮斑/粒子变换；热缓存不插值遮罩或重新扫描像素。
    local key = subIndex..":"..string.format("%.17g",scale)
    if self.poses[key] then return self.poses[key] end
    local point = samples[subIndex]
    local nx,ny = point[3],point[4]
    local d = self.meta.outward
    local rotation = math.atan(d[1]*(-ny)-d[2]*(-nx),d[1]*(-nx)+d[2]*(-ny))
    local co,si = math.cos(rotation),math.sin(rotation)
    local offset = (self.meta.r_rim-self.embedPixels)*scale
    local cx,cy = point[1]+nx*offset,point[2]+ny*offset
    local acx,acy = self.meta.contact[1]-self.meta.center[1],self.meta.contact[2]-self.meta.center[2]
    ---@type CellSurfacePose
    local pose = {x=point[1],y=point[2],spriteX=cx,spriteY=cy,membraneX=point[1],membraneY=point[2],normalX=nx,normalY=ny,
        rotation=rotation,scale=scale,size=self.meta.canvas*scale,bin=index,subBin=subIndex,key=key,cos=co,sin=si,
        contactX=cx+scale*(co*acx-si*acy),contactY=cy+scale*(si*acx+co*acy)}
    -- CPU 姿态缓存也有界，防止调用方不断传入新缩放值时无限增长。
    if self.poseCount >= sampleCount*2 then self.poses = {}; self.poseCount = 0 end
    self.poses[key] = pose
    self.poseCount = self.poseCount+1
    return pose
end

---@param x integer 完整画布的像素索引，不是像素中心坐标
---@param y integer
---@return number
function Surface:UnionPixel(x,y)
    if not self.data then return 0 end
    local u = self.data.union
    local ix,iy = x-u.x,y-u.y
    if ix < 0 or iy < 0 or ix >= u.width or iy >= u.height then return 0 end
    local runs = self.unionRows[iy+1]
    local low,high = 1,#runs
    while low < high do
        local middle = (low+high)//2
        if ix < runs[middle].stop then high=middle else low=middle+1 end
    end
    return runs[low].value
end

---@param x number 完整源画布的像素边界坐标
---@param y number
---@return number
function Surface:SampleUnion(x,y)
    local ix,iy = math.floor(x-.5),math.floor(y-.5)
    local fx,fy = x-.5-ix,y-.5-iy
    local a = self:UnionPixel(ix,iy)*(1-fx)+self:UnionPixel(ix+1,iy)*fx
    local b = self:UnionPixel(ix,iy+1)*(1-fx)+self:UnionPixel(ix+1,iy+1)*fx
    return a*(1-fy)+b*fy
end

---@param key string
---@param path string
---@param expected integer
---@return CellSurfaceRGBA?
function Surface:LoadSource(key,path,expected)
    if self.sources[key] then return self.sources[key] end
    if self.failures["source:"..key] or not cache or not Image then return nil end
    local ok,result = pcall(function()
        -- 源 Image 归 ResourceCache 所有，不 Dispose 共享引擎资源。
        local image = cache:GetResource("Image",path)
        assert(image and image.width == expected and image.height == expected,"Missing/wrong Image "..path)
        assert(image.components == 4 and not image.compressed,"Need straight-alpha RGBA PNG "..path)
        ---@type CellSurfaceRGBA
        local source = {width=image.width,height=image.height,pixels={},nonzero={}}
        for y=0,image.height-1 do
            for x=0,image.width-1 do
                local packed = image:GetPixelInt(x,y)
                source.pixels[1+y*image.width+x] = packed
                local alpha = (packed >> 24)&255
                if alpha > 0 then
                    source.nonzero[#source.nonzero+1] = {x=x+.5,y=y+.5,r=packed&255,
                        g=(packed >> 8)&255,b=(packed >> 16)&255,a=alpha}
                end
            end
        end
        self.sourceLoads = self.sourceLoads+1
        return source
    end)
    if not ok then self:Fail("source:"..key,tostring(result)); return nil end
    self.sources[key] = result
    return result
end

---@param source CellSurfaceRGBA
---@param x number
---@param y number
---@return integer
local function SourcePixel(source,x,y)
    local ix,iy = math.floor(x),math.floor(y)
    if ix<0 or iy<0 or ix>=source.width or iy>=source.height then return 0 end
    return source.pixels[1+iy*source.width+ix] or 0
end

---@param entry CellSurfaceEntry
function Surface:ReleaseEntry(entry)
    if entry.handle>0 and self.nvg and nvgDeleteVideo then nvgDeleteVideo(self.nvg,entry.handle) end
    if entry.texture then entry.texture:Dispose() end
    entry.handle,entry.texture = 0,nil
end

---@param nvg NVGContextWrapper
---@return boolean
function Surface:Bind(nvg)
    if self.destroyed or not nvg then return false end
    -- 不修改 ImageCache 上下文，不创建额外上下文或帧；生命周期由 main 管理。
    if ImageCache.GetContext and ImageCache.GetContext() ~= nvg then
        self:Fail("context","Caller must bind this same context to ImageCache before drawing")
        return false
    end
    if self.nvg and self.nvg ~= nvg then
        for _,entry in pairs(self.entries) do self:ReleaseEntry(entry) end
        self.entries = {}; self.count = 0
        self.pendingTextures={};self.textureQueue={};self.framePins={}
    end
    self.nvg = nvg
    return true
end

-- Only called inside the owning Widget.Render frame. Retrying a request does
-- not retain Image/page references or stale transforms from a previous frame.
function Surface:BeginFrame()
    if self.destroyed then self:Init(self.options) end
    self.frameSerial=(self.frameSerial or 0)+1
    self.framePins={}
    self.frameCreated=0
    self.pendingTextures=self.pendingTextures or {}
    self.textureQueue=self.textureQueue or {}
    local queue={}
    for _,key in ipairs(self.textureQueue) do
        if self.pendingTextures[key] and self.pendingTextures[key]>=self.frameSerial-1 then
            queue[#queue+1]=key
        else self.pendingTextures[key]=nil end
    end
    self.textureQueue=queue
end

---@param nvg NVGContextWrapper
---@param key string
---@param width integer
---@param height integer
---@param fill fun(image:Image)
---@param x number
---@param y number
---@param size number
---@param rotation number
---@return CellSurfaceEntry?
function Surface:Texture(nvg,key,width,height,fill,x,y,size,rotation)
    if not self:Bind(nvg) or not Image or not cache then return nil end
    self.clock = self.clock+1
    local cached = self.entries[key]
    if cached then
        self.hits=self.hits+1; cached.stamp=self.clock
        if self.framePins then self.framePins[key]=true end
        return cached
    end
    if self.failures[key] then return nil end
    if not Texture2D or not nvgCreateVideo or not nvgDeleteVideo then
        self:Fail("bridge","Image/Texture2D/nvgCreateVideo/nvgDeleteVideo unavailable")
        return nil
    end
    local oldestKey=""
    if self.count>=self.maxResources then
        local oldestStamp=math.huge
        for candidate,entry in pairs(self.entries) do
            if not (self.framePins and self.framePins[candidate]) and entry.stamp<oldestStamp then
                oldestKey=candidate;oldestStamp=entry.stamp
            end
        end
        if oldestKey=="" then return nil end
    end
    if self.framePins then
        if not self.pendingTextures[key] then self.textureQueue[#self.textureQueue+1]=key end
        self.pendingTextures[key]=self.frameSerial
        if self.frameCreated>=Config.Performance.surfaceTexturesPerFrame or self.textureQueue[1]~=key then
            return nil
        end
        table.remove(self.textureQueue,1);self.pendingTextures[key]=nil
        self.frameCreated=self.frameCreated+1
    end
    self.misses=self.misses+1
    ---@type Image?
    local image = nil
    ---@type Texture2D?
    local texture = nil
    local handle = 0
    local ok,result = pcall(function()
        image = Image()
        assert(image:SetSize(width,height,4),"Image:SetSize failed")
        image:ClearInt(0)
        fill(image)
        texture = Texture2D()
        texture:SetNumLevels(1)
        texture:SetFilterMode(FILTER_NEAREST)
        -- SetPixelInt 写入非预乘 RGBA；上传不乘 alpha。
        -- nvgCreateVideo 包装外部普通图片，不是预乘的渲染目标。
        assert(texture:SetData(image,true),"Texture2D:SetData failed")
        image:Dispose(); image=nil
        handle = nvgCreateVideo(nvg,texture)
        assert(handle>0,"nvgCreateVideo returned "..handle)
        ---@type CellSurfaceEntry
        local entry = {texture=texture,handle=handle,stamp=self.clock,pixels=width*height,
            x=x,y=y,size=size,rotation=rotation}
        return entry
    end)
    if image then image:Dispose() end
    if not ok then
        if handle>0 then nvgDeleteVideo(nvg,handle) end
        if texture then texture:Dispose() end
        self:Fail(key,tostring(result)); return nil
    end
    -- LRU 淘汰先删除 NanoVG 包装句柄，再 Dispose 本模块持有的外部纹理。
    if self.count>=self.maxResources then
        self:ReleaseEntry(self.entries[oldestKey])
        self.entries[oldestKey]=nil; self.count=self.count-1; self.evictions=self.evictions+1
    end
    self.entries[key]=result; self.count=self.count+1
    if self.framePins then self.framePins[key]=true end
    self.generatedPixels=self.generatedPixels+width*height
    return result
end

---@param nvg NVGContextWrapper
---@param entry CellSurfaceEntry
---@param alpha number
---@param revealBottom number? 生长前沿的局部y坐标；底层贴图已按真实细胞union裁剪。
local function DrawTexture(nvg,entry,alpha,revealBottom)
    nvgSave(nvg)
    nvgTranslate(nvg,entry.x,entry.y)
    nvgRotate(nvg,entry.rotation)
    local half = entry.size*.5
    local height = revealBottom and math.max(0, math.min(entry.size, revealBottom + half)) or entry.size
    nvgBeginPath(nvg)
    nvgRect(nvg,-half,-half,entry.size,height)
    nvgFillPaint(nvg,nvgImagePattern(nvg,-half,-half,entry.size,entry.size,0,entry.handle,Clamp(alpha)))
    nvgFill(nvg)
    nvgRestore(nvg)
end

---@param page integer
---@param path string
---@param image Image?
function Surface:AcceptAtlasPage(page,path,image)
    if not image then return end
    if image.width ~= 1024 or image.height ~= 1024 or image.components ~= 4 then
        image:Dispose()
        self:Fail("atlas:"..page,"Wrong baked image "..path)
        return
    end
    self.atlasClock = self.atlasClock+1
    self.atlasPages[page]={image=image,path=path,stamp=self.atlasClock}
    self.atlasLoads=self.atlasLoads+1
end

---@param page integer
---@return Image?
function Surface:AtlasPage(page)
    if not self.atlas then return nil end
    self.atlasClock = self.atlasClock+1
    local entry = self.atlasPages[page]
    if entry then entry.stamp=self.atlasClock; return entry.image end
    if self.atlasPending[page] or self.failures["atlas:"..page] then return nil end
    local path = self.atlas.pages[page]
    if not path then return nil end
    local count,oldest,stamp = 0,nil,math.huge
    for key,candidate in pairs(self.atlasPages) do
        count=count+1
        if candidate.stamp<stamp then oldest,stamp=key,candidate.stamp end
    end
    for _ in pairs(self.atlasPending) do count=count+1 end
    if count>=ATLAS_PAGE_LIMIT then
        if not oldest then return nil end
        self.atlasPages[oldest].image:Dispose()
        self.atlasPages[oldest]=nil
    end
    local queued = 0
    for _ in pairs(atlasRequests) do queued=queued+1 end
    if not atlasRequests[path] and queued>=ATLAS_PAGE_LIMIT then return nil end
    EnsureAtlasEvents()
    self.atlasPending[page]=true
    self.atlasWaits=self.atlasWaits+1
    local requests=atlasRequests[path]
    if requests then
        requests[#requests+1]={surface=self,page=page,generation=self.atlasGeneration}
        return nil
    end
    atlasRequests[path]={{surface=self,page=page,generation=self.atlasGeneration}}
    local ok,submitted = pcall(function() return cache:BackgroundLoadResource("Image",path,false) end)
    if not ok or not submitted then
        atlasRequests[path]=nil
        self.atlasPending[page]=nil
        self:Fail("atlas:"..page,"Cannot queue baked image "..path..(not ok and (": "..tostring(submitted)) or ""))
        CleanupAtlasEvents()
    end
    -- 首次未完成时不做同步加载；同一pose下亮斑与粒子一同等待，模拟照常进行。
    return nil
end

---@param pose CellSurfacePose
---@return boolean
function Surface:HasAtlas(pose)
    return self.atlas ~= nil and self.embedPixels == 8 and pose.subBin ~= nil
        and math.abs(pose.scale-self.atlas.scale)<1e-12
end

---@param nvg NVGContextWrapper
---@param key string
---@param tile integer[]
---@param x number
---@param y number
---@param size number
---@param rotation number
---@param resolution integer 与原glint192或patch数据crop/300尺寸一致
---@return CellSurfaceEntry?
function Surface:BakedTexture(nvg,key,tile,x,y,size,rotation,resolution)
    if #tile==0 or not self:Bind(nvg) then return nil end
    -- 命中纹理时不解码图集、不裁图、不创建Image。
    if self.entries[key] then
        self.clock=self.clock+1
        self.entries[key].stamp=self.clock
        self.hits=self.hits+1
        if self.framePins then self.framePins[key]=true end
        return self.entries[key]
    end
    local page=self:AtlasPage(tile[1])
    if not page then return nil end
    return self:Texture(nvg,key,resolution,resolution,function(image)
        local px,py=math.floor(tile[2]),math.floor(tile[3])
        local width,height=math.floor(tile[4]),math.floor(tile[5])
        local ox,oy=math.floor(tile[6]),math.floor(tile[7])
        assert(ox >= 0 and oy >= 0 and ox+width <= resolution and oy+height <= resolution,
            "Baked atlas crop exceeds output dimensions")
        local right,bottom=math.floor(px+width),math.floor(py+height)
        local rect=IntRect(px,py,right,bottom)
        local cropped=page:GetSubimage(rect)
        assert(cropped,"Baked atlas crop failed")
        local targetRight,targetBottom=math.floor(ox+width),math.floor(oy+height)
        local placed=image:SetSubimage(cropped,IntRect(ox,oy,targetRight,targetBottom))
        cropped:Dispose()
        assert(placed,"Baked atlas copy failed")
    end,x,y,size,rotation)
end

---@param nvg NVGContextWrapper
---@param pose CellSurfacePose?
---@param alpha number?
---@return boolean
function Surface:DrawGlint(nvg,pose,alpha)
    if not pose or not self.data or not self.meta or (alpha or 1)<=0 then return false end
    if self:HasAtlas(pose) then
        local tile=self.atlas.glints[pose.subBin]
        if not tile then return false end
        local entry=self:BakedTexture(nvg,"g:"..pose.key,tile,pose.spriteX,pose.spriteY,pose.size,pose.rotation,self.meta.canvas)
        if not entry then return false end
        DrawTexture(nvg,entry,alpha or 1)
        return true
    end
    local source = self:LoadSource("glint",self.data.glint.path,self.meta.canvas)
    if not source then return false end
    local entry = self:Texture(nvg,"g:"..pose.key,source.width,source.height,function(image)
        for _,pixel in ipairs(source.nonzero) do
            local dx,dy = pixel.x-self.meta.center[1],pixel.y-self.meta.center[2]
            local sx = self.data.center[1]+pose.spriteX+pose.scale*(pose.cos*dx-pose.sin*dy)
            local sy = self.data.center[2]+pose.spriteY+pose.scale*(pose.sin*dx+pose.cos*dy)
            -- 硬约束：原始亮斑 alpha × 同位置三层 source-over union alpha。
            local a = math.floor(pixel.a*self:SampleUnion(sx,sy)+.5)
            if a>0 then image:SetPixelInt(math.floor(pixel.x),math.floor(pixel.y),
                pixel.r|(pixel.g<<8)|(pixel.b<<16)|(a<<24)) end
        end
    end,pose.spriteX,pose.spriteY,pose.size,pose.rotation)
    if not entry then return false end
    DrawTexture(nvg,entry,alpha or 1)
    return true
end

---@param nvg NVGContextWrapper
---@param pose CellSurfacePose?
---@param alpha number?
---@return boolean
function Surface:DrawParticle(nvg,pose,alpha)
    if not pose or self.destroyed or (alpha or 1)<=0 or not self:Bind(nvg) then return false end
    return VU.DrawSprite(nvg,PARTICLE_PATH,pose.spriteX,pose.spriteY,pose.size,alpha or 1,pose.rotation)
end

---@param nvg NVGContextWrapper
---@param pose CellSurfacePose
---@param source CellSurfaceRGBA?
---@param layerIndex integer 从1开始的静态stack层索引，与progress无关
---@return CellSurfaceEntry?
function Surface:PatchEntry(nvg,pose,source,layerIndex)
    if not self.data then return nil end
    local patch = self.data.patch
    local layer = patch.stack[layerIndex]
    if not layer then return nil end
    -- 固定三层几何由真实感染进度驱动，不依赖接触粒子是否仍在淡出。
    -- +Y旋到-n后额外0/+25/-20度；原画布中心A=(150,150)精准落在真实膜点P。
    local scale = patch.max_scale*layer.scale
    local crop = patch.crop or {0,0,patch.canvas}
    local cropX,cropY,cropSize = crop[1],crop[2],crop[3]
    local centreX,centreY = cropX+cropSize/2,cropY+cropSize/2
    local anchor = patch.anchor
    local rotation = math.atan(pose.normalX,-pose.normalY)+math.rad(layer.rot)
    local co,si = math.cos(rotation),math.sin(rotation)
    local ax,ay = centreX-anchor[1],centreY-anchor[2]
    -- crop中心C输出位置=P+scale*R*(C-A)。故A输出=P，没有额外depth偏移。
    local cx = pose.membraneX+scale*(co*ax-si*ay)
    local cy = pose.membraneY+scale*(si*ax+co*ay)
    local resolution = patch.output_pixels
    local key = "p2:"..pose.key..":"..layerIndex
    if self:HasAtlas(pose) then
        local tiles=self.atlas.patches[pose.subBin]
        local tile=tiles and tiles[layerIndex]
        if not tile then return nil end
        return self:BakedTexture(nvg,key,tile,cx,cy,cropSize*scale,rotation,resolution)
    end
    if not source then return nil end
    return self:Texture(nvg,key,resolution,resolution,function(image)
        for y=0,resolution-1 do
            local sy = cropY+(y+.5)/resolution*cropSize
            for x=0,resolution-1 do
                local sx = cropX+(x+.5)/resolution*cropSize
                local packed = SourcePixel(source,sx,sy)
                local originalAlpha = (packed >> 24)&255
                if originalAlpha>0 then
                    local dx,dy = sx-anchor[1],sy-anchor[2]
                    local ux = self.data.center[1]+pose.membraneX+scale*(co*dx-si*dy)
                    local uy = self.data.center[2]+pose.membraneY+scale*(si*dx+co*dy)
                    local a = math.floor(originalAlpha*self:SampleUnion(ux,uy)+.5)
                    if a>0 then image:SetPixelInt(x,y,(packed&0xffffff)|(a<<24)) end
                end
            end
        end
    end,cx,cy,cropSize*scale,rotation)
end

---@param nvg NVGContextWrapper
---@param pose CellSurfacePose?
---@param progress number 只读取玩法连续进度，范围 0..1
---@param alpha number?
---@param activity number? 连续透明度倍率，不改变缓存几何
---@return boolean
function Surface:DrawPatch(nvg,pose,progress,alpha,activity)
    if not pose or not self.data or self.destroyed or progress<=0 or (alpha or 1)<=0 then return false end
    local opacity = Clamp(alpha or 1)*Clamp(activity or 1)
    if opacity<=0 then return false end
    ---@type CellSurfaceRGBA?
    local source = nil
    if not self:HasAtlas(pose) then
        source = self:LoadSource("patch",self.data.patch.path,self.data.patch.canvas)
        if not source then return false end
    end
    local patch = self.data.patch
    local q = Clamp(progress)*#patch.stack
    local drawn = false
    for layerIndex=1,#patch.stack do
        -- 几何与真实轮廓mask保持固定，只在已裁剪贴图上推进向内的显示前沿。
        -- 单调前沿与alpha共用真实进度，回落时原路收回；不重建纹理、不挪膜点P。
        local layerProgress = Clamp(q-layerIndex+1)
        if layerProgress>0 then
            local entry = self:PatchEntry(nvg,pose,source,layerIndex)
            if entry then
                local crop = patch.crop or {0,0,patch.canvas}
                local centreY = crop[2]+crop[3]*.5
                local growth = math.sqrt(layerProgress)
                local front = patch.anchor[2]+(patch.bounds[4]-patch.anchor[2])*growth
                local revealBottom = (front-centreY)*patch.max_scale*patch.stack[layerIndex].scale
                -- 满层直接复原完整裁剪贴图，保持交付图层和最终45%宽度。
                DrawTexture(nvg,entry,opacity*growth,layerProgress<1 and revealBottom or nil)
                drawn=true
            end
        end
    end
    return drawn
end

function Surface:Destroy()
    if self.destroyed then return end
    for _,entry in pairs(self.entries) do self:ReleaseEntry(entry) end
    for _,page in pairs(self.atlasPages) do page.image:Dispose() end
    self.atlasPages = {}
    self.atlasPending = {}
    self.atlasGeneration = math.floor(self.atlasGeneration+1)
    -- 在途任务保留空账本等待事件释放结果，但不继续强持已销毁/旧世界视图。
    for _,requests in pairs(atlasRequests) do
        for index=#requests,1,-1 do
            if requests[index].surface==self then table.remove(requests,index) end
        end
    end
    self.entries,self.sources,self.poses,self.unionRows = {},{},{},{}
    self.pendingTextures,self.textureQueue={},{}
    self.framePins=nil
    self.data,self.meta,self.patchMeta,self.stackMeta,self.nvg,self.atlas = nil,nil,nil,nil,nil,nil
    self.count=0; self.destroyed=true
    -- main 管理 ImageCache（包括未修改的粒子）、字体和上下文。
    -- 下次 GetPlacement 自动重新 Init，因此世界重置后仍可复用本实例。
end

return Surface
