param(
    [ValidateSet("cuda", "cpu", "amd")]
    [string]$Device = "cuda",
    [string]$RuntimeDir = "",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 7870
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$PluginRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = if ($RuntimeDir) { [System.IO.Path]::GetFullPath($RuntimeDir) } else { Join-Path $PluginRoot "runtime" }
$Python = Join-Path $PluginRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Plugin is not installed. Run .\install.ps1 first."
}
& $Python -m chickenrice_service --runtime-dir $RuntimeDir --device $Device --check
if ($LASTEXITCODE -ne 0) { throw "ChickenRice runtime check failed. Run .\install.ps1 -Device $Device -Force." }
& $Python -m chickenrice_service --runtime-dir $RuntimeDir --device $Device --host $HostAddress --port $Port
