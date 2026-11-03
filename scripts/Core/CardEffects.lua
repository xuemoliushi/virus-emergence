-- 每局能力解锁，不保留旧被动倍率或免费产量。
local Abilities=require("Core.AbilityRuntime")
local Effects={}
function Effects.Init(w)
    w.cardEffects={}
    w.playerTouchedCells={}
    Abilities.Init(w)
end
function Effects.Value(w,key,default) return default or 0 end
function Effects.Apply(w,card) Abilities.Acquire(w,card) end
function Effects.ActiveRegions(w)
    local regions,count={},0
    for _,cell in ipairs(w.cells) do
        if (cell.state=="LATENT" or cell.state=="PRODUCTIVE") and not regions[cell.regionId] then
            regions[cell.regionId]=true;count=count+1
        end
    end
    return regions,count
end
function Effects.ReleaseCount(w,cell,count) return count end
function Effects.Update(w) end
return Effects
