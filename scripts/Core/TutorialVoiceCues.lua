-- 由用户提供的 15 段原始 WAV 按台词匹配；来源与哈希见 assets/audio/tutorial/mapping.json。
---@class TutorialVoiceClip
---@field path string
---@field text string
---@field seconds number
---@field start number Skip measured leading silence, preserving 120 ms before speech.
---@field finish number End after speech with a 200 ms tail.
---@class TutorialVoiceCues
---@field clips table<string, TutorialVoiceClip>
---@field steps table<string, string[]>
local Cues = {}
Cues.clips = {
    intro = {path="audio/tutorial/intro.wav",text="你，现在是一个流感病毒",seconds=3.622312925,start=0.46,finish=2.98},
    healthy_cell = {path="audio/tutorial/healthy_cell.wav",text="这是正常细胞",seconds=2.94893424,start=0.05,finish=2.39},
    contact_infection = {path="audio/tutorial/contact_infection.wav",text="在接触到它们一定时间后，它们就会被感染",seconds=7.174965986,start=1.49,finish=6.53},
    try_infection = {path="audio/tutorial/try_infection.wav",text="先来尝试感染它们吧",seconds=5.387029478,start=1.42,finish=4.34},
    release = {path="audio/tutorial/release.wav",text="细胞感染后，过一段时间会释放新的病毒",seconds=7.174965986,start=0.78,finish=6.40},
    collect = {path="audio/tutorial/collect.wav",text="你可以接触它们，以此聚集病毒",seconds=5.154829932,start=1.29,finish=4.28},
    absorb = {path="audio/tutorial/absorb.wav",text="也可以直接吸附",seconds=5.735328798,start=1.36,finish=3.59},
    goal = {path="audio/tutorial/goal.wav",text="我们的目标是感染尽可能多的细胞来发展病毒群",seconds=8.986122449,start=1.28,finish=8.22},
    tcell = {path="audio/tutorial/tcell.wav",text="该死，这是细胞毒性T细胞",seconds=3.552653061,start=0.15,finish=3.12},
    tcell_attack = {path="audio/tutorial/tcell_attack.wav",text="会优先识别并攻击感染细胞",seconds=6.037188209,start=1.54,finish=5.81},
    relocate = {path="audio/tutorial/relocate.wav",text="我们得去找其他细胞了",seconds=4.806530612,start=1.49,finish=3.93},
    macrophage = {path="audio/tutorial/macrophage.wav",text="巨噬细胞会优先攻击病毒群，注意躲避",seconds=8.93968254,start=1.09,finish=8.11},
    task = {path="audio/tutorial/task.wav",text="我们需要达成一定的条件来完成阶段任务",seconds=7.174965986,start=1.23,finish=6.57},
    reward = {path="audio/tutorial/reward.wav",text="完成后会提供强力增益",seconds=4.806530612,start=1.45,finish=4.41},
    explore = {path="audio/tutorial/explore.wav",text="自行探索吧",seconds=5.712108844,start=0.32,finish=2.43},
}
Cues.steps = {
    intro = {"intro"},
    target = {"healthy_cell","contact_infection"},
    infect = {"try_infection"},
    wait = {"release"},
    collect = {"collect","absorb"},
    split = {"goal"},
    tcell = {"tcell","tcell_attack"},
    macrophage = {"macrophage"},
    escape = {"relocate"},
    task = {"task","reward","explore"},
}
return Cues
