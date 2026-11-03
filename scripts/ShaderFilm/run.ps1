param(
 [ValidateSet('Preview','QA','Render','RenderClean','Prepare','Audio','Verify')]
 [string]$Mode='Preview'
)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$runtimeRoot=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies'
function Find-Runtime([string]$override,[string]$bundled,[string]$fallback) {
 if ($override -and (Test-Path -LiteralPath $override)) { return $override }
 if (Test-Path -LiteralPath $bundled) { return $bundled }
 $found=Get-Command $fallback -ErrorAction SilentlyContinue
 if ($found) { return $found.Source }
 throw "Missing runtime: $fallback. See assets/video/emergence_shader/渲染说明.md."
}
Push-Location $projectRoot
try {
 if ($Mode -in @('Preview','QA','Render','RenderClean')) {
  $nodeExe=Find-Runtime $env:SHADER_NODE (Join-Path $runtimeRoot 'node\bin\node.exe') 'node'
  if (-not $env:SHADER_NODE_DEPS) { $env:SHADER_NODE_DEPS=Join-Path $runtimeRoot 'node\node_modules' }
  switch ($Mode) {
   'Preview' { & $nodeExe scripts/ShaderFilm/render.cjs --serve }
   'QA' { & $nodeExe scripts/ShaderFilm/render.cjs --qa }
   'Render' { & $nodeExe scripts/ShaderFilm/render.cjs }
   'RenderClean' { & $nodeExe scripts/ShaderFilm/render.cjs --no-subs }
  }
 } else {
  $pythonExe=Find-Runtime $env:SHADER_PYTHON (Join-Path $runtimeRoot 'python\python.exe') 'python'
  switch ($Mode) {
   'Prepare' { & $pythonExe scripts/ShaderFilm/prepare.py }
   'Audio' {
    & "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File scripts/ShaderFilm/narration.ps1
    if ($LASTEXITCODE -ne 0) { throw 'Local SAPI narration failed.' }
    & $pythonExe scripts/ShaderFilm/audio.py
   }
   'Verify' { & $pythonExe scripts/ShaderFilm/verify.py }
  }
 }
 if ($LASTEXITCODE -ne 0) { throw "Shader film command failed: $LASTEXITCODE" }
} finally { Pop-Location }
