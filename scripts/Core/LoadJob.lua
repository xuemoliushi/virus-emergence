-- Cooperative startup work. Only explicit checkpoints in pure Lua generation yield.
-- Other coroutines and normal synchronous map generation are unaffected.
---@class LoadJob
---@field thread thread
---@field done boolean
---@field error string?
---@field deadline number
---@field slices integer
---@field progress number
---@field message string
local Job = {}
Job.__index = Job
---@type table<thread, table>
local owners = setmetatable({}, {__mode="k"})

function Job.New(work)
    local self=setmetatable({done=false,error=nil,deadline=0,slices=0,progress=0,message="正在准备组织…"},Job)
    self.thread=coroutine.create(function()
        coroutine.yield() -- Present the loading hint once before any expensive work.
        work()
    end)
    owners[self.thread]=self
    return self
end

function Job.Checkpoint()
    local owner=owners[coroutine.running()]
    if owner and os.clock()>=owner.deadline then coroutine.yield() end
end

-- Presentation-only milestones; this never consumes RNG or yields extra work.
function Job.Report(progress,message)
    local owner=owners[coroutine.running()]
    if not owner then return end
    if progress>=owner.progress then
        owner.progress=math.min(.86,progress)
        owner.message=message
    end
end

function Job:Step()
    if self.done then return end
    self.deadline=os.clock()+0.006
    self.slices=self.slices+1
    local ok,err=coroutine.resume(self.thread)
    if not ok then self.error=tostring(err) end
    self.done=not ok or coroutine.status(self.thread)=="dead"
    if self.done then owners[self.thread]=nil end
end

return Job
