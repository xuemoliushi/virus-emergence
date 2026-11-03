-- Shared geometry for rendering, inverse input and the minimap view rectangle.
local Bounds = {}
local function axis(value, size, before, after)
    if before+after >= size then return (size+before-after)*.5 end
    return math.max(before,math.min(size-after,value))
end

function Bounds.Clamp(camera, world, area, ppm, cx, cy)
    camera.x=axis(camera.x,world.width,(cx-area.x)/ppm,(area.x+area.w-cx)/ppm)
    camera.y=axis(camera.y,world.height,(cy-area.y)/ppm,(area.y+area.h-cy)/ppm)
end

function Bounds.View(camera, area, ppm, cx, cy)
    return {x=camera.x+(area.x-cx)/ppm,y=camera.y+(area.y-cy)/ppm,
        w=area.w/ppm,h=area.h/ppm}
end

return Bounds
