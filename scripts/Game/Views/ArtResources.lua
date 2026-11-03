-- Owns a bounded set of NanoVG images; never changes the shared UI ImageCache.
---@class ArtResources
local Art = {}
Art.__index = Art

function Art.New(limit)
    local self = setmetatable({}, Art)
    self:init(limit or 8)
    return self
end

function Art:init(limit)
    self.limit = limit
    self.clock = 0
    self.images = {}
    self.failures = {}
    ---@type table<string, boolean>?
    self.pinned = nil
    ---@type NVGContextWrapper?
    self.nvg = nil
end

function Art:Destroy()
    if self.nvg then
        for _, entry in pairs(self.images) do nvgDeleteImage(self.nvg, entry.handle) end
    end
    self.images = {}
    self.failures = {}
    self.pinned = nil
    self.nvg = nil
end

-- NanoVG submits at EndFrame: images referenced this frame cannot be evicted.
-- At capacity, decline new pages until the next frame; callers retain ordinary sprites.
function Art:BeginFrame()
    self.pinned = {}
end

function Art:Get(nvg, path, flags)
    if not nvg or not path or not nvgCreateImage then return nil end
    if self.nvg ~= nvg then
        local inFrame = self.pinned ~= nil
        self:Destroy(); self.nvg = nvg
        if inFrame then self:BeginFrame() end
    end
    local key = path .. ":" .. tostring(flags or 0)
    self.clock = self.clock + 1
    local entry = self.images[key]
    if entry then
        entry.stamp = self.clock
        if self.pinned then self.pinned[key] = true end
        return entry
    end
    if self.failures[key] then return nil end
    local count, oldest, stamp = 0, "", math.huge
    for candidate, image in pairs(self.images) do
        count = count + 1
        if not (self.pinned and self.pinned[candidate]) and image.stamp < stamp then
            oldest, stamp = candidate, image.stamp
        end
    end
    if count >= self.limit and oldest == "" then return nil end
    local handle = 0
    local ok, result = pcall(function()
        handle = nvgCreateImage(nvg, path, flags or 0)
        assert(handle and handle > 0, "Cannot load " .. path)
        local width, height = nvgImageSize(nvg, handle)
        assert(width > 0 and height > 0, "Invalid image " .. path)
        return { handle = handle, width = width, height = height, stamp = self.clock }
    end)
    if not ok then
        if handle and handle > 0 then nvgDeleteImage(nvg, handle) end
        self.failures[key] = true
        print("[ArtResources] " .. tostring(result))
        return nil
    end
    if count >= self.limit then
        nvgDeleteImage(nvg, self.images[oldest].handle)
        self.images[oldest] = nil
    end
    self.images[key] = result
    if self.pinned then self.pinned[key] = true end
    return result
end

-- Build a path before calling Paint to clip decals to the real tissue union.
function Art:Paint(nvg, path, x, y, width, height, alpha, rotation, flags)
    local entry = self:Get(nvg, path, flags)
    if not entry then return false end
    nvgFillPaint(nvg, nvgImagePattern(nvg, x, y, width, height, rotation or 0, entry.handle, alpha or 1))
    nvgFill(nvg)
    return true
end

function Art:DrawTile(nvg, path, tile, rect, tileSize, pageSize, alpha)
    local entry = self:Get(nvg, path, NVG_IMAGE_NEAREST or 0)
    if not entry or entry.width ~= pageSize or entry.height ~= pageSize then return false end
    local x, y, w, h = rect[1], rect[2], rect[3], rect[4]
    nvgSave(nvg)
    nvgShapeAntiAlias(nvg, 0)
    local sx, sy = w / tileSize, h / tileSize
    nvgBeginPath(nvg)
    nvgRect(nvg, x, y, w, h)
    nvgFillPaint(nvg, nvgImagePattern(nvg, x-tile[2]*sx, y-tile[3]*sy,
        pageSize*sx, pageSize*sy, 0, entry.handle, alpha or 1))
    nvgFill(nvg)
    nvgRestore(nvg)
    return true
end

function Art.ReadJSON(path)
    if not cache or not cjson then return nil end
    local file = cache:GetFile(path)
    if not file then return nil end
    local ok, result = pcall(function()
        local lines = {}
        while not file:IsEof() do lines[#lines+1] = file:ReadLine() end
        return cjson.decode(table.concat(lines, "\n"))
    end)
    file:Dispose()
    if ok then return result end
    print("[ArtResources] JSON " .. path .. ": " .. tostring(result))
    return nil
end

return Art
