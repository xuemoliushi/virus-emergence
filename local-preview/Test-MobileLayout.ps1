[CmdletBinding()]
param(
    [ValidateSet('menu','hud','tutorial','skills','cards','interactive')][string]$Case='interactive',
    [ValidateRange(320,4096)][int]$Width=844,
    [ValidateRange(240,4096)][int]$Height=390,
    [ValidateRange(0,16000)][int]$ScreenshotFrame=0
)
$ErrorActionPreference='Stop'
$projectDir=Split-Path -Parent $PSScriptRoot
$bundles=Get-ChildItem -LiteralPath (Join-Path $env:USERPROFILE '.taptap-maker/mcp-runtime') -Directory |
    Where-Object { $_.Name -match '^\d+\.\d+\.\d+$' -and (Test-Path -LiteralPath (Join-Path $_.FullName 'dist/maker.js')) } |
    Sort-Object { [version]$_.Name } -Descending
if (-not $bundles) { throw 'Installed Maker CLI not found.' }
$makerScript=Join-Path $bundles[0].FullName 'dist/maker.js'
$stateText=& node $makerScript preview status --target-dir $projectDir --json
if ($LASTEXITCODE -ne 0) { throw 'Could not confirm local preview ownership.' }
$state=($stateText -join [Environment]::NewLine) | ConvertFrom-Json
if ($state.process_alive) { throw 'A normal preview is running. Close it before using this separate validation window.' }
if ($ScreenshotFrame -eq 0) {
    $ScreenshotFrame=if ($Case -eq 'menu') { 240 } elseif ($Case -eq 'interactive') { 5900 } else { 2400 }
}
$entryPath=Join-Path $projectDir 'scripts/MobilePreviewProbe.lua'
if (Test-Path -LiteralPath $entryPath) { throw 'Temporary MobilePreviewProbe.lua already exists; preserve it and inspect before retrying.' }
$template=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'mobile/probe.lua'))
$previousPython=$env:TAPTAP_MAKER_PYTHON_BIN
$previousGit=$env:TAPTAP_MAKER_GIT_BIN
try {
    $pythonPath=Join-Path $projectDir '.preview-python/Scripts/python.exe'
    if (Test-Path -LiteralPath $pythonPath) { $env:TAPTAP_MAKER_PYTHON_BIN=$pythonPath }
    $gitCommand=Get-Command git.exe -ErrorAction SilentlyContinue
    $gitCandidates=@(
        $(if ($gitCommand) { $gitCommand.Source })
        (Join-Path $env:ProgramFiles 'Git/cmd/git.exe')
        (Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe')
    )
    foreach ($candidate in $gitCandidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { $env:TAPTAP_MAKER_GIT_BIN=$candidate;break }
    }
    [IO.File]::WriteAllText($entryPath,$template.Replace('__CASE__',$Case))
    Write-Host 'Local phone layout window; desktop mouse emulates touch. No upload or build.'
    Write-Host 'Interactive mode uses the real menu and tutorial; the test window closes after capture.'
    & node $makerScript preview validate --target-dir $projectDir --entry MobilePreviewProbe.lua `
        --mode both --width $Width --height $Height --screenshot-frame $ScreenshotFrame `
        --validate-frames ($ScreenshotFrame+10) --validate-timeout 300 --validate-spike-threshold 500 `
        --output-dir (Join-Path $projectDir "validation/mobile-layout-20261019/$Case") --json
    $runExitCode=$LASTEXITCODE
}
finally {
    if (Test-Path -LiteralPath $entryPath) { Remove-Item -LiteralPath $entryPath }
    $env:TAPTAP_MAKER_PYTHON_BIN=$previousPython
    $env:TAPTAP_MAKER_GIT_BIN=$previousGit
}
exit $runExitCode
