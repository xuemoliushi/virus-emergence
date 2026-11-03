param([ValidateSet('Preview','Prepare','Audio','Render','Subtitles','Finalize','QA','Verify')][string]$Mode='Preview')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$runtimeRoot=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies'
function Find-Runtime([string]$override,[string]$bundled,[string]$fallback){
 if($override -and (Test-Path -LiteralPath $override)){return $override}
 if(Test-Path -LiteralPath $bundled){return $bundled}
 $found=Get-Command $fallback -ErrorAction SilentlyContinue
 if($found){return $found.Source}
 throw "Missing runtime: $fallback"
}
Push-Location $projectRoot
try{
 if($Mode -in @('Prepare','Audio','Finalize','Verify')){
  $pythonExe=Find-Runtime $env:SHADER_PYTHON (Join-Path $runtimeRoot 'python\python.exe') 'python'
  switch($Mode){
   'Prepare' { & $pythonExe scripts/ShaderFilm/prepare_final90.py }
   'Audio' {
    & "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File scripts/ShaderFilm/narration90.ps1
    if($LASTEXITCODE -ne 0){throw 'Narration failed'}
    & $pythonExe scripts/ShaderFilm/audio_final90.py
   }
   'Verify' { & $pythonExe scripts/ShaderFilm/verify_final90.py }
   'Finalize' { & $pythonExe scripts/ShaderFilm/finalize_final90.py }
  }
 }else{
  $nodeExe=Find-Runtime $env:SHADER_NODE (Join-Path $runtimeRoot 'node\bin\node.exe') 'node'
  if(-not $env:SHADER_NODE_DEPS){$env:SHADER_NODE_DEPS=Join-Path $runtimeRoot 'node\node_modules'}
  switch($Mode){
   'Preview' { & $nodeExe scripts/ShaderFilm/render_final90.cjs --serve }
   'QA' { & $nodeExe scripts/ShaderFilm/render_final90.cjs --qa }
   'Subtitles' { & $nodeExe scripts/ShaderFilm/render_final90.cjs --subtitle }
   'Render' {
    & $nodeExe scripts/ShaderFilm/render_final90.cjs
    if($LASTEXITCODE -ne 0){throw 'Picture render failed'}
    & $nodeExe scripts/ShaderFilm/render_final90.cjs --subtitle
    if($LASTEXITCODE -ne 0){throw 'Subtitle render failed'}
    $pythonExe=Find-Runtime $env:SHADER_PYTHON (Join-Path $runtimeRoot 'python\python.exe') 'python'
    & $pythonExe scripts/ShaderFilm/finalize_final90.py
   }
  }
 }
 if($LASTEXITCODE -ne 0){throw "Final film command failed: $LASTEXITCODE"}
}finally{Pop-Location}
