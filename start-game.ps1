[CmdletBinding()]
param([switch]$Refresh)

$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot

function Invoke-MakerPreview {
    param([string]$Action)

    $output = & $nodePath $makerScript preview $Action --target-dir $projectDir --json
    $exitCode = $LASTEXITCODE
    $jsonText = $output -join [Environment]::NewLine
    try {
        $result = $jsonText | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw "Maker returned an unreadable result.`n$jsonText"
    }
    if ($exitCode -ne 0 -or $result.ok -eq $false) {
        # Status can report a previous failed launch with a nonzero exit code.
        # An installed Runtime and a confirmed dead session can be started again.
        if ($Action -eq 'status' -and $result.state -eq 'failed' -and
            $result.process_alive -eq $false -and $result.install_state -eq 'ready') {
            Write-Host 'The previous preview failed. A new local launch will be attempted.'
        }
        else {
            $detail = if ($result.error) { $result.error } else { $jsonText }
            throw "Maker preview $Action failed (exit $exitCode).`n$detail"
        }
    }
    return $result
}

try {
    if (-not (Test-Path -LiteralPath (Join-Path $projectDir '.maker-mcp\config.json'))) {
        throw 'This folder is not a configured TapTap Maker project.'
    }

    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($nodeCommand) {
        $nodePath = $nodeCommand.Source
    }
    else {
        $nodePath = Join-Path $env:ProgramFiles 'nodejs\node.exe'
        if (-not (Test-Path -LiteralPath $nodePath)) {
            throw 'Node.js is missing. Install Node.js and reopen this launcher.'
        }
    }

    # Explorer does not inherit Codex's bundled Git on PATH. Resolve an actual
    # installed executable and pass it to both Maker and plain Git subprocesses.
    $gitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
    $gitCandidates = @(
        $env:TAPTAP_MAKER_GIT_BIN
        $(if ($gitCommand) { $gitCommand.Source })
        (Join-Path $env:ProgramFiles 'Git\cmd\git.exe')
        (Join-Path $env:LOCALAPPDATA 'Programs\Git\cmd\git.exe')
        (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe')
    )
    $gitPath = $null
    foreach ($candidate in $gitCandidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            $gitVersion = & $candidate --version 2>$null
            if ($LASTEXITCODE -eq 0) { $gitPath = $candidate; break }
        }
    }
    if (-not $gitPath) {
        throw 'Git is missing. Install Git for Windows or restore the installed Codex Git runtime.'
    }
    $env:TAPTAP_MAKER_GIT_BIN = $gitPath
    $env:PATH = (Split-Path -Parent $gitPath) + [IO.Path]::PathSeparator + $env:PATH

    # Reuse the newest installed stable Maker bundle, including local upgrades.
    # Do not pin an older bundle just because its directory still exists.
    $runtimeDir = Join-Path $env:USERPROFILE '.taptap-maker\mcp-runtime'
    $installedBundles = @(Get-ChildItem -LiteralPath $runtimeDir -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^\d+\.\d+\.\d+$' -and (Test-Path -LiteralPath (Join-Path $_.FullName 'dist\maker.js')) } |
        Sort-Object { [version]$_.Name } -Descending)
    if ($installedBundles.Count -eq 0) {
        throw 'Maker CLI is missing. Ask your AI to configure local Maker development first.'
    }
    $makerScript = Join-Path $installedBundles[0].FullName 'dist\maker.js'

    # A project-local venv survives the console's environment allowlist through
    # Maker's supported Python override. PYTHONPATH alone is not forwarded.
    $networkHelper = Join-Path $projectDir 'local-preview\python'
    if (-not (Test-Path -LiteralPath (Join-Path $networkHelper 'sitecustomize.py'))) {
        throw 'The local preview network helper is missing. Restore local-preview/python/sitecustomize.py.'
    }
    $previewPythonDir = Join-Path $projectDir '.preview-python'
    $previewPython = Join-Path $previewPythonDir 'Scripts\python.exe'
    $previewPip = Join-Path $previewPythonDir 'Lib\site-packages\pip\__init__.py'
    if (-not (Test-Path -LiteralPath $previewPython) -or -not (Test-Path -LiteralPath $previewPip)) {
        $basePython = Get-Command python.exe -ErrorAction SilentlyContinue
        if (-not $basePython -or $basePython.Source -match 'WindowsApps') {
            throw 'A local Python installation is required for the preview helper.'
        }
        Write-Host 'Preparing the isolated local preview helper (no downloads)...'
        & $basePython.Source -m venv $previewPythonDir
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the local preview Python environment.' }
    }
    Copy-Item -LiteralPath (Join-Path $networkHelper 'sitecustomize.py') `
        -Destination (Join-Path $previewPythonDir 'Lib\site-packages\sitecustomize.py') -Force
    $env:TAPTAP_MAKER_PYTHON_BIN = $previewPython

    Set-Location -LiteralPath $projectDir
    Write-Host "Using installed Maker $($installedBundles[0].Name)."
    Write-Host 'Checking local game preview...'
    $status = Invoke-MakerPreview 'status'
    if ($status.process_alive -eq $true) {
        if ($Refresh) {
            Write-Host 'Refreshing the game. Current in-memory progress will be lost.'
            $status = Invoke-MakerPreview 'refresh'
        }
        else {
            Write-Host 'The game is already running. Switch to the UrhoXRuntime window.'
            Write-Host 'To reload code changes, run this launcher with -Refresh.'
            exit 0
        }
    }
    else {
        if ($status.install_state -ne 'ready') {
            throw 'Game Runtime is not installed. Ask your AI to install the official local Runtime first.'
        }
        Write-Host 'Starting the game window. First load may download public resources...'
        $status = Invoke-MakerPreview 'start'
    }

    $status = Invoke-MakerPreview 'status'
    if ($status.process_alive -ne $true) {
        throw 'The game process did not remain running. Ask your AI to check preview logs.'
    }
    Write-Host 'Game window launched. Resources may still be loading.'
    Write-Host 'Close the game window when finished. Local preview does not submit or publish code.'
    exit 0
}
catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
