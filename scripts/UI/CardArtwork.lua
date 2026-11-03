-- A formal offer is one visual batch. Download callbacks never reveal a card;
-- NanoVG handles are prepared inside the owning UI render frame, one per frame.
local Art=require('UI.CardArt')
local Images=require('urhox-libs/UI/Core/ImageCache')
local Artwork={}
---@class CardArtworkEntry
---@field id string
---@field path string?
---@field status string
---@field prepared boolean
---@field retried boolean?
---@class CardArtworkBatch
---@field entries CardArtworkEntry[]
---@field cancelled boolean
---@field elapsed number
---@field ready boolean

---@return CardArtworkBatch
function Artwork.New(cards)
    local batch={entries={},cancelled=false,elapsed=0,ready=false}
    for _,card in ipairs(cards) do
        local path=Art.paths[card.id]
        batch.entries[#batch.entries+1]={id=card.id,path=path,status=path and 'pending' or 'failed',prepared=false}
    end
    for _,entry in ipairs(batch.entries) do
        if entry.path then
            if cache and cache.GetResourceAsync then
                local ok=pcall(function()
                    cache:GetResourceAsync('Texture2D',entry.path,function(resource)
                        if not batch.cancelled and entry.status=='pending' then
                            entry.status=resource and 'loaded' or 'failed'
                        end
                    end)
                end)
                if not ok then entry.status='failed' end
            else
                -- Older/local runtimes can prepare an existing image directly.
                -- Dimensions are still checked in Warm; no timer-only reveal.
                entry.status='loaded'
            end
        end
    end
    return batch
end

function Artwork.Cancel(batch)
    if batch then batch.cancelled=true;batch.entries={} end
end

function Artwork.Update(batch,dt)
    if not batch or batch.cancelled or batch.ready then return end
    batch.elapsed=batch.elapsed+math.max(0,dt)
    if batch.elapsed>=10 then
        for _,entry in ipairs(batch.entries) do
            if not entry.prepared then entry.status='failed' end
        end
    end
end

-- Called only by cardInfoOverlay.Render. No contexts, fonts or frames are made.
function Artwork.Warm(batch,root)
    if not batch or batch.cancelled or batch.ready or not root then return end
    local budget=1
    local ready=true
    for _,entry in ipairs(batch.entries) do
        if not entry.prepared then
            if entry.status=='failed' then
                local widget=root:FindById('cardArt_'..entry.id)
                if widget then widget:SetStyle{backgroundImage=false,backgroundColor={17,13,29,255},
                    borderWidth=1,borderColor={104,97,126,255}} end
                entry.prepared=true
            elseif entry.status=='loaded' and budget>0 and entry.path then
                budget=budget-1
                local ok,handle,width,height=pcall(function()
                    local image=Images.Get(entry.path)
                    local w,h=Images.GetSize(entry.path)
                    return image,w,h
                end)
                if not ok then entry.status='failed'
                elseif handle and handle>0 and width>4 and height>4 then
                    entry.prepared=true
                    local widget=root:FindById('cardArt_'..entry.id)
                    if widget then widget:SetStyle{backgroundImage=entry.path,backgroundColor=false,borderWidth=0} end
                elseif not entry.retried then
                    -- A prior failed lazy load may have left a negative cache.
                    if Images.Release then Images.Release(entry.path) end
                    entry.retried=true
                end
            end
        end
        if not entry.prepared then ready=false end
    end
    batch.ready=ready
end

return Artwork
