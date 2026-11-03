$ErrorActionPreference = 'Stop'
$filmRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$audioRoot = Join-Path $filmRoot 'assets\audio\emergence_90s'
$voice = New-Object -ComObject SAPI.SpVoice
$candidate = @($voice.GetVoices() | Where-Object { $_.GetDescription() -match 'David' })[0]
if (-not $candidate) { throw 'English male David voice not found.' }
$voice.Voice = $candidate
$voice.Rate = -1
$voice.Volume = 100
$lines = @(
 'Within this bird, an unseen world was changing. A small infection spread.',
 'Each bird follows its neighbours.',
 'Keeping distance. Turning together. Staying close.',
 'From these small actions, order emerges.',
 'This bird died of acute pneumonia.',
 'The flock continued its flight.',
 'Below, another world moves.',
 'People meet, exchange, cooperate, and compete.',
 'Their lives intertwine, shaping a society no one person could create alone.',
 'Across generations, these connections grow into cities, cultures, and civilizations.'
)
for ($i=0; $i -lt $lines.Count; $i++) {
 $stream = New-Object -ComObject SAPI.SpFileStream
 $path = Join-Path $audioRoot ('narration_{0:00}.wav' -f $i)
 $stream.Open($path,3,$false)
 $voice.AudioOutputStream = $stream
 $voice.Speak('<pitch middle="-3">'+$lines[$i]+'</pitch>',8) | Out-Null
 $stream.Close()
 Write-Output $path
}
Write-Output ('NARRATOR=' + $voice.Voice.GetDescription())
