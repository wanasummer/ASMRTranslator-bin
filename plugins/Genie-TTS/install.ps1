param(
    [string]$RuntimeDir = "",
    [switch]$DownloadBaseResources,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$PluginRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = if ($RuntimeDir) {
    [System.IO.Path]::GetFullPath($RuntimeDir)
} else {
    Join-Path $PluginRoot "runtime"
}
$VenvDir = Join-Path $PluginRoot ".venv"

$PythonCommand = $null
$LauncherVersion = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python -c "import struct,sys; assert (3,10) <= sys.version_info[:2] < (3,12) and struct.calcsize('P') == 8" *> $null
    if ($LASTEXITCODE -eq 0) { $PythonCommand = "python" }
}
if (-not $PythonCommand -and (Get-Command py -ErrorAction SilentlyContinue)) {
    foreach ($Version in @("-3.11", "-3.10")) {
        & py $Version -c "import struct,sys; assert (3,10) <= sys.version_info[:2] < (3,12) and struct.calcsize('P') == 8" *> $null
        if ($LASTEXITCODE -eq 0) {
            $PythonCommand = "py"
            $LauncherVersion = $Version
            break
        }
    }
}
if (-not $PythonCommand) { throw "Python 3.10 or 3.11 x64 is required." }

if ($Force -and (Test-Path -LiteralPath $VenvDir)) {
    $ResolvedVenv = [System.IO.Path]::GetFullPath($VenvDir)
    $ResolvedRoot = [System.IO.Path]::GetFullPath($PluginRoot)
    if (-not $ResolvedVenv.StartsWith($ResolvedRoot + [System.IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to remove a virtual environment outside the plugin directory."
    }
    Remove-Item -LiteralPath $ResolvedVenv -Recurse -Force
}
if (-not (Test-Path -LiteralPath $VenvDir)) {
    if ($PythonCommand -eq "py") { & py $LauncherVersion -m venv $VenvDir }
    else { & python -m venv $VenvDir }
    if ($LASTEXITCODE -ne 0) { throw "Failed to create plugin virtual environment." }
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

function Test-LocalProxy {
    try {
        $Client = [System.Net.Sockets.TcpClient]::new()
        $Task = $Client.ConnectAsync("127.0.0.1", 7890)
        if (-not $Task.Wait(1000)) { $Client.Dispose(); return $false }
        $Connected = $Client.Connected
        $Client.Dispose()
        return $Connected
    } catch { return $false }
}

function Invoke-PipInstall([string[]]$PipArguments) {
    Write-Host "Trying domestic PyPI mirror (TUNA)..." -ForegroundColor Cyan
    & $VenvPython -m pip @PipArguments `
        --index-url "https://pypi.tuna.tsinghua.edu.cn/simple" --timeout 30
    if ($LASTEXITCODE -eq 0) { return }

    if (Test-LocalProxy) {
        Write-Warning "Domestic mirror failed; retrying official PyPI through 127.0.0.1:7890."
        & $VenvPython -m pip @PipArguments `
            --index-url "https://pypi.org/simple" --proxy "http://127.0.0.1:7890" --timeout 30
        if ($LASTEXITCODE -eq 0) { return }
    } else {
        Write-Warning "Domestic mirror failed and local proxy 127.0.0.1:7890 is unavailable."
    }

    Write-Warning "Mirror/proxy attempts failed; trying official PyPI directly once."
    & $VenvPython -m pip @PipArguments --index-url "https://pypi.org/simple" --timeout 30
    if ($LASTEXITCODE -ne 0) { throw "pip install failed with all configured routes." }
}

Invoke-PipInstall @("install", "--upgrade", "pip")
Invoke-PipInstall @("install", "$PluginRoot[test]")

New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
$VoicesFile = Join-Path $RuntimeDir "voices.json"
if (-not (Test-Path -LiteralPath $VoicesFile)) {
    Copy-Item -LiteralPath (Join-Path $PluginRoot "voices.example.json") -Destination $VoicesFile
}
if ($DownloadBaseResources) {
    & $VenvPython -m genie_tts_service.bootstrap --runtime-dir $RuntimeDir --proxy-port 7890
    if ($LASTEXITCODE -ne 0) { throw "Failed to download Genie base resources." }
}

Write-Host ""
Write-Host "Genie TTS plugin installed." -ForegroundColor Green
Write-Host "1. Edit: $VoicesFile"
Write-Host "2. Put authorized character models and reference audio under: $(Join-Path $RuntimeDir 'voices')"
if (-not $DownloadBaseResources) {
    Write-Host "3. Download base resources later with:"
    Write-Host "   .\install.ps1 -DownloadBaseResources"
}
Write-Host "4. Start with: .\start.ps1 -RuntimeDir `"$RuntimeDir`""
