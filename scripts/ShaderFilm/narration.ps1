$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$audioRoot = Join-Path $projectRoot 'assets\audio\emergence_shader'
New-Item -ItemType Directory -Force -Path $audioRoot | Out-Null
$voice = New-Object -ComObject SAPI.SpVoice
$available = @($voice.GetVoices())
$selected = @($available | Where-Object { $_.GetDescription() -match 'David' })[0]
if (-not $selected) { throw 'English David voice unavailable; do not silently substitute a Chinese voice.' }
$voice.Voice = $selected
$voice.Rate = -1
$voice.Volume = 100
$lines = @(
 'Within this bird, an unseen world was changing.',
 'Each bird follows its neighbours.',
 'From these small actions, order emerges.',
 'This bird died of acute pneumonia.',
 'The flock continued its flight.',
 'Below, another world moves.',
 'People meet, exchange, cooperate, and compete.',
 'Across generations, these connections grow into cities, cultures, and civilizations.'
)
for ($i=0; $i -lt $lines.Count; $i++) {
 $stream = New-Object -ComObject SAPI.SpFileStream
 $stream.Format.Type = 22
 $stream.Open((Join-Path $audioRoot ('voice_{0:00}.wav' -f $i)),3,$false)
 $voice.AudioOutputStream = $stream
 $voice.Speak('<pitch middle="-3">'+$lines[$i]+'</pitch>',8) | Out-Null
 $stream.Close()
}
Write-Output ('Generated 8 local TTS lines: ' + $voice.Voice.GetDescription())
