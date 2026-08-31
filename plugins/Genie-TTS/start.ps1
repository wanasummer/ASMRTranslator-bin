param(
    [string]$RuntimeDir = "",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8003,
    [string]$ApiKey = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$PluginRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = if ($RuntimeDir) {
    [System.IO.Path]::GetFullPath($RuntimeDir)
} else {
    Join-Path $PluginRoot "runtime"
}
$VenvPython = Join-Path $PluginRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Plugin is not installed. Run .\install.ps1 first."
}

$env:GENIE_TTS_RUNTIME_DIR = $RuntimeDir
$env:GENIE_TTS_VOICES_FILE = Join-Path $RuntimeDir "voices.json"
$env:GENIE_DATA_DIR = Join-Path $RuntimeDir "GenieData"
if ($ApiKey) { $env:GENIE_TTS_API_KEY = $ApiKey }

& $VenvPython -m genie_tts_service --host $HostAddress --port $Port
exit $LASTEXITCODE
