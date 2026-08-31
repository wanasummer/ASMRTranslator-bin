param([string]$OutputDir = "dist")

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$PluginRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Version = (Get-Content -LiteralPath (Join-Path $PluginRoot "plugin-manifest.json") -Raw | ConvertFrom-Json).version
$DestinationDir = Join-Path $PluginRoot $OutputDir
$StageDir = Join-Path ([System.IO.Path]::GetTempPath()) ("genie-tts-package-" + [guid]::NewGuid())
$Archive = Join-Path $DestinationDir "genie-tts-service-$Version.zip"

New-Item -ItemType Directory -Path $StageDir -Force | Out-Null
New-Item -ItemType Directory -Path $DestinationDir -Force | Out-Null
try {
    foreach ($Item in @(
        "src", "pyproject.toml", "plugin-manifest.json", "README.md", "API.md",
        "voices.example.json", "install.ps1", "start.ps1"
    )) {
        Copy-Item -LiteralPath (Join-Path $PluginRoot $Item) -Destination $StageDir -Recurse
    }
    Get-ChildItem -LiteralPath $StageDir -Directory -Filter "__pycache__" -Recurse |
        Remove-Item -Recurse -Force
    Get-ChildItem -LiteralPath $StageDir -File -Filter "*.pyc" -Recurse |
        Remove-Item -Force
    if (Test-Path -LiteralPath $Archive) { Remove-Item -LiteralPath $Archive }
    Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $Archive -CompressionLevel Optimal
    $Hash = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath "$Archive.sha256" -Value "$Hash  $(Split-Path -Leaf $Archive)" -Encoding ascii
    Write-Host "Package: $Archive"
    Write-Host "SHA256:  $Hash"
} finally {
    Remove-Item -LiteralPath $StageDir -Recurse -Force -ErrorAction SilentlyContinue
}
