-- Park–Miller 48271. Products stay below 2^53 (also exact in double-only Lua).
-- Stateless seed normalization; no global RNG or simulation RNG calls.
local Random = {}
local MOD = 2147483647
local serial = 0

function Random.Normalize(value)
    if type(value) == "number" then
        assert(value == value and math.abs(value) < math.huge, "mapSeed must be finite")
        local n = math.floor(value) % MOD
        return n > 0 and n or 1
    end
    assert(type(value) == "string", "mapSeed must be a number or UTF-8 string")
    -- UTF-8 byte polynomial; multiplier 131 stays exact below 2^53.
    local hash = 7
    for i = 1, #value do hash = (hash * 131 + value:byte(i)) % MOD end
    return hash > 0 and hash or 1
end

function Random.New(seed, stream)
    local state = Random.Normalize((Random.Normalize(seed) + (stream or 0) * 104729) % MOD)
    return function()
        state = state * 48271 % MOD
        return (state - 1) / (MOD - 1)
    end
end

function Random.NewSeed()
    serial = serial + 1
    return Random.Normalize((os.time() % MOD + math.floor(os.clock() * 1000000) + serial * 104729) % MOD)
end

return Random
