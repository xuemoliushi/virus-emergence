"""Lua 5.4 test runtime with Unicode-safe source loading on Windows.

The production Lua modules still execute unchanged in Lupa. Only host file reads
use Python so Lua's narrow Windows fopen does not reject Chinese project paths.
"""
from pathlib import Path

from lupa.lua54 import LuaRuntime as NativeLuaRuntime


def LuaRuntime(*args, **kwargs):
    lua = NativeLuaRuntime(*args, **kwargs)

    def read_source(filename):
        try:
            return Path(filename).read_text(encoding="utf-8-sig"), None
        except (OSError, UnicodeError) as error:
            return None, str(error)

    lua.globals().test_read_lua_source = read_source
    lua.execute(r'''
local read = test_read_lua_source
test_read_lua_source = nil
table.insert(package.searchers, 2, function(name)
    local modulePath = name:gsub("%.", "/")
    for template in package.path:gmatch("[^;]+") do
        local filename = template:gsub("%?", function() return modulePath end)
        local source = read(filename)
        if source then
            local loader, reason = load(source, "@" .. filename, "t")
            if not loader then error(reason) end
            return loader, filename
        end
    end
    return "\n\tno Unicode-readable Lua source for " .. name
end)
local nativeLoadfile = loadfile
loadfile = function(filename, mode, env)
    if filename == nil then return nativeLoadfile(filename, mode, env) end
    local source, reason = read(filename)
    if not source then return nil, reason end
    return load(source, "@" .. filename, mode or "bt", env or _G)
end
local nativeDofile = dofile
dofile = function(filename)
    if filename == nil then return nativeDofile() end
    local chunk, reason = loadfile(filename)
    if not chunk then error(reason, 2) end
    return chunk()
end
''')
    return lua
