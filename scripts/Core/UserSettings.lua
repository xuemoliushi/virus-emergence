-- 客户端设置：使用引擎的项目/用户隔离存储，不写项目配置。
local UI = require("urhox-libs/UI")

---@class UserSettingsValues
---@field master number
---@field music number
---@field effects number
---@field ambient number
---@field voice number
---@field uiScale number
---@field maxFps integer
---@field menuMotion boolean

---@class UserSettings
---@field values UserSettingsValues
local Settings = {}
Settings.__index = Settings
local SAVE_FILE = "virus-emergence-settings.json"

---@return UserSettingsValues
local function defaults()
    return { master = 100, music = 80, effects = 100, ambient = 80, voice = 100,
        uiScale = 1, maxFps = 60, menuMotion = true }
end

local function validNumber(value, minimum, maximum, fallback)
    if type(value) ~= "number" or value ~= value then return fallback end
    return math.max(minimum, math.min(maximum, value))
end

function Settings.New()
    local self = setmetatable({}, Settings)
    self:init()
    return self
end

function Settings:init()
    self.values = defaults()
    if not fileSystem:FileExists(SAVE_FILE) then return end
    local file = File(SAVE_FILE, FILE_READ)
    if not file:IsOpen() then file:Dispose(); return end
    local ok, saved = pcall(cjson.decode, file:ReadString())
    file:Dispose()
    if not ok or type(saved) ~= "table" then
        print("[Settings] 设置存档无效，使用默认值")
        return
    end
    for _, key in ipairs({ "master", "music", "effects", "ambient", "voice" }) do
        self.values[key] = math.floor(validNumber(saved[key], 0, 100, self.values[key]) + 0.5)
    end
    if saved.uiScale == 0.85 or saved.uiScale == 1 or saved.uiScale == 1.15 then
        self.values.uiScale = saved.uiScale
    end
    if saved.maxFps == 30 or saved.maxFps == 60 or saved.maxFps == 120 then
        self.values.maxFps = math.floor(saved.maxFps)
    end
    if type(saved.menuMotion) == "boolean" then self.values.menuMotion = saved.menuMotion end

end

function Settings:ApplyAudio()
    audio:SetMasterGain(SOUND_MASTER, self.values.master / 100)
    audio:SetMasterGain(SOUND_MUSIC, self.values.music / 100)
    audio:SetMasterGain(SOUND_EFFECT, self.values.effects / 100)
    audio:SetMasterGain(SOUND_AMBIENT, self.values.ambient / 100)
    audio:SetMasterGain(SOUND_VOICE, self.values.voice / 100)
end

function Settings:Apply()
    self:ApplyAudio()
    engine:SetMaxFps(self.values.maxFps)
    -- 在默认 DPR/小屏适配上乘玩家选择，不切换物理窗口分辨率。
    UI.SetScale(function() return UI.Scale.DEFAULT() * self.values.uiScale end)
    local root = UI.GetRoot()
    if root then UI.SetRoot(root) end -- SetScale 本身不标记 Yoga 布局脏。
end

---@return boolean
function Settings:Save()
    local file = File(SAVE_FILE, FILE_WRITE)
    if not file:IsOpen() then
        file:Dispose()
        print("[Settings] 本地存储不可写，本次设置仍然生效")
        return false
    end
    local written = file:WriteString(cjson.encode(self.values))
    file:Dispose()
    if not written then print("[Settings] 设置保存失败") end
    return written
end

function Settings:Reset()
    self.values = defaults()
    self:Apply()
    return self:Save()
end

return Settings
