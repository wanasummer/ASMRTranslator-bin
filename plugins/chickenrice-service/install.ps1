param(
    [ValidateSet("cuda", "cpu", "amd")]
    [string]$Device = "cuda",
    [string]$RuntimeDir = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$PluginRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = if ($RuntimeDir) { [System.IO.Path]::GetFullPath($RuntimeDir) } else { Join-Path $PluginRoot "runtime" }
$VenvDir = Join-Path $PluginRoot ".venv"

$PythonCommand = $null
$LauncherVersion = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python -c "import sys; assert (3, 10) <= sys.version_info[:2] < (3, 12)" *> $null
    if ($LASTEXITCODE -eq 0) { $PythonCommand = "python" }
}
if (-not $PythonCommand -and (Get-Command py -ErrorAction SilentlyContinue)) {
    foreach ($Version in @("-3.11", "-3.10")) {
        & py $Version -c "import sys; assert (3, 10) <= sys.version_info[:2] < (3, 12)" *> $null
        if ($LASTEXITCODE -eq 0) {
            $PythonCommand = "py"
            $LauncherVersion = $Version
            break
        }
    }
}
if (-not $PythonCommand) {
    throw "Python 3.10 or 3.11 x64 is required."
}

if (-not (Test-Path -LiteralPath $VenvDir)) {
    if ($PythonCommand -eq "py") {
        & py $LauncherVersion -m venv $VenvDir
    } else {
        & python -m venv $VenvDir
    }
}
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$PluginSrc = Join-Path $PluginRoot "src"
$PreviousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = $PluginSrc
if ($PreviousPythonPath) { $env:PYTHONPATH += ";$PreviousPythonPath" }

$BootstrapArgs = @("-m", "chickenrice_service.bootstrap", "--runtime-dir", $RuntimeDir, "--device", $Device)
if ($Force) { $BootstrapArgs += "--force" }
try {
    & $VenvPython @BootstrapArgs
} finally {
    $env:PYTHONPATH = $PreviousPythonPath
}
if ($LASTEXITCODE -ne 0) { throw "ChickenRice runtime installation failed." }

Write-Host ""
Write-Host "Installation complete. Start the service with:" -ForegroundColor Green
Write-Host "  .\start.ps1 -Device $Device -RuntimeDir `"$RuntimeDir`""
