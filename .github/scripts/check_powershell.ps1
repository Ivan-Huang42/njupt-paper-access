$ErrorActionPreference = "Stop"

$scriptRoot = Join-Path $PSScriptRoot "..\..\njupt-paper-access\scripts"
$files = Get-ChildItem -LiteralPath $scriptRoot -Filter "*.ps1"

foreach ($file in $files) {
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $file.FullName,
        [ref]$tokens,
        [ref]$errors
    ) | Out-Null
    if ($errors.Count -gt 0) {
        throw "$($file.FullName): $($errors -join '; ')"
    }
}

Write-Host "PowerShell parse OK"
