$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "njupt_paper.py"
$pythonCommand = Get-Command py -ErrorAction SilentlyContinue

if ($pythonCommand) {
    & $pythonCommand.Source $scriptPath @args
} else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Python 3.10 or newer is required."
    }
    & $pythonCommand.Source $scriptPath @args
}

exit $LASTEXITCODE
