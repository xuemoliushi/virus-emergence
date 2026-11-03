-- 肺部选区：白色透明蒙版和像素游程由同一原图分割生成，显示与命中不分家。
local Data = require("Game.Views.LungMaskData")
local ImageCache = require("urhox-libs/UI/Core/ImageCache")

local Masks = {}

---@param regionType string
---@param rect {x:number,y:number,w:number,h:number}
---@return {x:number,y:number,w:number,h:number}
function Masks.Bounds(regionType, rect)
    local mask = Data[regionType]
    if not mask then return { x = rect.x, y = rect.y, w = 0, h = 0 } end
    local b = mask.bounds
    return { x = rect.x + b.x / mask.width * rect.w, y = rect.y + b.y / mask.height * rect.h,
        w = b.w / mask.width * rect.w, h = b.h / mask.height * rect.h }
end

-- 二维命中示意（像素阈值 alpha>40，与PNG实际着色轮廓一致）：
--       上气道
--         气管
--        /    \       气管蒙版沿主支气管延伸
--    左肺      右肺   深肺蒙版是两块不相连的组织，中央缝隙永远不命中
-- 每像素仅属于一个选区；左/上边含，右/下边不含；不扩张轮廓方便点击。
---@param regionType string
---@param rect {x:number,y:number,w:number,h:number}
---@param x number
---@param y number
---@return boolean
function Masks.Contains(regionType, rect, x, y)
    if regionType == "ALL" then
        return Masks.Contains("UPPER_AIRWAY", rect, x, y)
            or Masks.Contains("TRACHEA", rect, x, y)
            or Masks.Contains("DEEP_LUNG", rect, x, y)
    end
    local mask = Data[regionType]
    if not mask or rect.w <= 0 or rect.h <= 0 then return false end
    local u, v = (x - rect.x) / rect.w, (y - rect.y) / rect.h
    if u ~= u or v ~= v or u < 0 or v < 0 or u >= 1 or v >= 1 then return false end
    local px = math.floor(u * mask.width)
    local row = mask.rows[1 + math.floor(v * mask.height)]
    if not row then return false end
    for i = 1, #row, 2 do
        if px >= row[i] and px < row[i + 1] then return true end
    end
    return false
end

---@param nvg NVGContextWrapper
---@param path string
---@param rect {x:number,y:number,w:number,h:number}
---@param color RGBAColor
---@param alpha integer
local function DrawImage(nvg, path, rect, color, alpha)
    local handle = math.floor(ImageCache.Get(path))
    if handle <= 0 then return end
    nvgBeginPath(nvg)
    nvgRect(nvg, rect.x, rect.y, rect.w, rect.h)
    nvgFillPaint(nvg, nvgImagePatternTinted(nvg, rect.x, rect.y, rect.w, rect.h,
        0, handle, nvgRGBA(color[1], color[2], color[3], alpha)))
    nvgFill(nvg)
end

---@param nvg NVGContextWrapper
---@param regionType string
---@param rect {x:number,y:number,w:number,h:number}
---@param color RGBAColor
---@param selected boolean
---@param hovered boolean
function Masks.Draw(nvg, regionType, rect, color, selected, hovered)
    if rect.w <= 0 or rect.h <= 0 then return end
    if regionType == "ALL" then
        -- 解剖肺热点平时不画引导圈；仅悬停时把原器官轮廓覆盖为纯白。
        if not hovered then return end
        nvgSave(nvg)
        for _, part in ipairs({ "UPPER_AIRWAY", "TRACHEA", "DEEP_LUNG" }) do
            DrawImage(nvg, "Sprites/LungMasks/" .. part .. ".png", rect, { 255, 255, 255, 255 }, 255)
        end
        nvgRestore(nvg)
        return
    end
    if not Data[regionType] then return end
    local path = "Sprites/LungMasks/" .. regionType
    nvgSave(nvg)
    DrawImage(nvg, path .. ".png", rect, color, selected and 195 or (hovered and 165 or 135))
    DrawImage(nvg, path .. "_outline.png", rect, color, selected and 255 or (hovered and 245 or 225))
    nvgRestore(nvg)
end

return Masks
