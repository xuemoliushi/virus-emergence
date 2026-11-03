$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$audioRoot=Join-Path $projectRoot 'assets\audio\emergence_final90'
New-Item -ItemType Directory -Force -Path $audioRoot | Out-Null
$voice=New-Object -ComObject SAPI.SpVoice
$selected=@($voice.GetVoices() | Where-Object { $_.GetDescription() -match 'David' })[0]
if(-not $selected){throw 'The existing English David voice is unavailable.'}
$voice.Voice=$selected;$voice.Rate=-1;$voice.Volume=100
$lines=@(
 'Within this bird, an unseen world was changing.',
 'A small infection spread.',
 'Each bird follows its neighbours.',
 'Keeping distance.',
 'Turning together.',
 'Staying close.',
 'From these small actions, order emerges.',
 'This bird died of acute pneumonia.',
 'The flock continued its flight.',
 'Below, another world moves.',
 'People meet, exchange, cooperate, and compete.',
 'Their lives intertwine,',
 'shaping a society no one person could create alone.',
 'Across generations, these connections grow into cities, cultures, and civilizations.'
)
for($i=0;$i -lt $lines.Count;$i++){
 $stream=New-Object -ComObject SAPI.SpFileStream;$stream.Format.Type=22
 $stream.Open((Join-Path $audioRoot ('voice_{0:00}.wav' -f $i)),3,$false)
 $voice.AudioOutputStream=$stream;$voice.Speak('<pitch middle="-3">'+$lines[$i]+'</pitch>',8) | Out-Null;$stream.Close()
}
Write-Output ('90-second film: 14 lines, existing '+$voice.Voice.GetDescription())
