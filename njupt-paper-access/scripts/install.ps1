$ErrorActionPreference = "Stop"

$source = Split-Path -Parent $PSScriptRoot
$agentsRoot = Join-Path $HOME ".agents\skills"
$destination = Join-Path $agentsRoot "njupt-paper-access"
$codexRoot = Join-Path $HOME ".codex\skills"
$codexLink = Join-Path $codexRoot "njupt-paper-access"

New-Item -ItemType Directory -Path $agentsRoot -Force | Out-Null
New-Item -ItemType Directory -Path $codexRoot -Force | Out-Null

if (-not [string]::Equals(
    [IO.Path]::GetFullPath($source),
    [IO.Path]::GetFullPath($destination),
    [StringComparison]::OrdinalIgnoreCase
)) {
    if (Test-Path -LiteralPath $destination) {
        throw "Destination already exists. Move it aside before reinstalling: $destination"
    }
    Copy-Item -LiteralPath $source -Destination $destination -Recurse
}

if (-not (Test-Path -LiteralPath $codexLink)) {
    New-Item -ItemType Junction -Path $codexLink -Target $destination | Out-Null
}

$python = Get-Command py -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command python -ErrorAction SilentlyContinue
}

Write-Host "Installed portable skill: $destination"
Write-Host "Codex global entry:        $codexLink"
if ($python) {
    Write-Host "Python found:             $($python.Source)"
} else {
    Write-Warning "Python 3.10+ is required before paper download commands can run."
}
Write-Host "Test with: & '$destination\scripts\njupt-paper.ps1' doctor"
