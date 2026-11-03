-- Positions are fractions of the safe viewport; storage is isolated by the engine.
local L={}
L.ids={"joystick","absorbBtn","splitBtn","skillWheel","switchBtn","swarm_anchor","infection_trail","merge_seed"}
L.names={joystick="移动摇杆",absorbBtn="吸附",splitBtn="分离",skillWheel="技能",switchBtn="切群",
    swarm_anchor="驻留",infection_trail="尾迹",merge_seed="播种"}
L.baseSize,L.minScale,L.maxScale=64,.75,3
L.defaultScales={joystick=2,absorbBtn=1.5,splitBtn=1,skillWheel=1.2,switchBtn=1,swarm_anchor=1,infection_trail=1,merge_seed=1}
local legacySizes={joystick=132,absorbBtn=92,splitBtn=64,skillWheel=76,switchBtn=56,swarm_anchor=56,infection_trail=56,merge_seed=56}
local SAVE="virus-emergence-controls-v1.json"
local CLOUD="touch_controls_v1"
local function finite(v) return type(v)=="number" and v==v and math.abs(v)<math.huge end
function L.Clean(value)
    local result={version=2,controls={}}
    if type(value)~="table" or (value.version~=1 and value.version~=2) or type(value.controls)~="table" then return result end
    for _,id in ipairs(L.ids) do
        local p=value.controls[id]
        if type(p)=="table" and finite(p.x) and finite(p.y) and finite(p.scale) then
            local size=value.version==1 and legacySizes[id]*p.scale/L.baseSize or p.scale
            result.controls[id]={x=math.max(0,math.min(1,p.x)),y=math.max(0,math.min(1,p.y)),scale=math.max(L.minScale,math.min(L.maxScale,size))}
        end
    end
    return result
end
function L.Load()
    local ok,value=pcall(function()
        if not fileSystem or not fileSystem:FileExists(SAVE) then return nil end
        local f=File(SAVE,FILE_READ)
        if not f:IsOpen() then f:Dispose();return nil end
        local raw=f:ReadString();f:Close();f:Dispose();return cjson.decode(raw)
    end)
    return L.Clean(ok and value or nil)
end
function L.Save(value)
    local ok,written=pcall(function()
        local encoded=cjson.encode(L.Clean(value));local f=File(SAVE,FILE_WRITE)
        if not f:IsOpen() then f:Dispose();return false end
        local success=f:WriteString(encoded);f:Close();f:Dispose();return success
    end)
    return ok and written==true
end
-- WASM files live in memory. Use the documented per-player values API there.
function L.CloudAvailable()
    if not GetPlatform or GetPlatform()~="Web" or not clientCloud then return false end
    local id=GetUserId and GetUserId() or clientCloud.userId
    return id~=nil and tostring(id)~="" and tostring(id)~="0"
end
function L.LoadCloud(done)
    if not L.CloudAvailable() then return end
    pcall(function() clientCloud:Get(CLOUD,{ok=function(values)
        local value=type(values)=="table" and values[CLOUD]
        if type(value)=="table" and (value.version==1 or value.version==2) then done(L.Clean(value)) end
    end,error=function() end,timeout=function() end}) end)
end
function L.SaveCloud(value,done)
    local finished=false
    local function finish(ok) if not finished then finished=true;done(ok) end end
    local ok=pcall(function() clientCloud:Set(CLOUD,L.Clean(value),{
        ok=function() finish(true) end,error=function() finish(false) end,timeout=function() finish(false) end}) end)
    if not ok then finish(false) end
end
function L.Bounds(value,id,w,h)
    local scale=math.max(.8,math.min(1.15,h/520))
    local defaults={joystick={155*scale,h-115*scale},absorbBtn={w-65*scale,h-68*scale},splitBtn={w-163*scale,h-65*scale},
        skillWheel={w-170*scale,h-200*scale},switchBtn={w-252*scale,h-62*scale},swarm_anchor={w-330*scale,h-62*scale},
        infection_trail={w-400*scale,h-62*scale},merge_seed={w-470*scale,h-62*scale}}
    local p=value.controls[id];local d=math.max(44,L.baseSize*scale*(p and p.scale or L.defaultScales[id]))
    local x=p and p.x*w or defaults[id][1];local y=p and p.y*h or defaults[id][2]
    x=math.max(d/2+8,math.min(w-d/2-8,x));y=math.max(math.min(126,h/2)+d/2,math.min(h-d/2-8,y))
    if id=="joystick" then x=math.min(w*.48-d/2,x);y=math.max(h*.38+d/2,y) end
    return {x=x,y=y,d=d,left=x-d/2,top=y-d/2}
end
function L.Put(value,id,x,y,size,w,h)
    value.controls[id]={x=x/w,y=y/h,scale=size or (value.controls[id] and value.controls[id].scale) or L.defaultScales[id]}
    local b=L.Bounds(value,id,w,h);value.controls[id].x=b.x/w;value.controls[id].y=b.y/h
end
function L.Conflict(value,w,h,visible)
    local bounds={}
    for _,id in ipairs(L.ids) do
        if id~="joystick" and (not visible or visible(id)) then
            local b=L.Bounds(value,id,w,h)
            for _,other in ipairs(bounds) do
                if math.sqrt((b.x-other.b.x)^2+(b.y-other.b.y)^2)<(b.d+other.b.d)/2+6 then
                    return L.names[id].."与"..L.names[other.id].."距离过近，请拖开后保存"
                end
            end
            bounds[#bounds+1]={id=id,b=b}
        end
    end
end
return L
