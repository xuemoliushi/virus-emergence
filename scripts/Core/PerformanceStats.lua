-- Opt-in bounded diagnostics. CPU timings include Lua/native call submission,
-- not GPU completion. Engine frame intervals are sampled separately.
local Config=require("Core.Config")
local Stats={}
local enabled=Config.Performance.collectTimings
local samples={}

function Stats.Reset()
    samples={}
end

function Stats.SetEnabled(value)
    enabled=value==true
    Stats.Reset()
end

function Stats.Begin()
    if enabled then return os.clock() end
end

function Stats.Sample(name,milliseconds)
    if not enabled or milliseconds~=milliseconds or milliseconds<0 or milliseconds==math.huge then return end
    local metric=samples[name]
    if not metric then
        metric={values={},cursor=1,total=0,over50=0,over100=0};samples[name]=metric
    end
    metric.values[metric.cursor]=milliseconds
    metric.cursor=metric.cursor%Config.Performance.timingWindow+1
    metric.total=metric.total+1
    if milliseconds>50 then metric.over50=metric.over50+1 end
    if milliseconds>100 then metric.over100=metric.over100+1 end
end

function Stats.Finish(name,start)
    if start then Stats.Sample(name,(os.clock()-start)*1000) end
end

function Stats.Snapshot()
    local result={enabled=enabled,luaHeapKiB=collectgarbage("count"),metrics={}}
    for name,metric in pairs(samples) do
        local values={}
        for i,value in ipairs(metric.values) do values[i]=value end
        table.sort(values)
        local n=#values
        result.metrics[name]={sampleCount=n,totalCount=metric.total,
            p95Ms=values[math.ceil(n*.95)],p99Ms=values[math.ceil(n*.99)],maxMs=values[n],
            over50ms=metric.over50,over100ms=metric.over100}
    end
    return result
end

return Stats
