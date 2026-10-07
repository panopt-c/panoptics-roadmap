param([Parameter(ValueFromRemainingArguments = $true)][string[]]$GameArgs)
$ErrorActionPreference = 'Stop'
$workspacePython = Join-Path $PSScriptRoot '../../../work/rpg-venv/Scripts/python.exe'
$projectPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (Test-Path -LiteralPath $projectPython) {
    $pythonPath = $projectPython
} elseif (Test-Path -LiteralPath $workspacePython) {
    $pythonPath = $workspacePython
} else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw 'Python 3.11+ with rich, markdown-it-py and pygments is required.' }
    $pythonPath = $pythonCommand.Source
}
& $pythonPath (Join-Path $PSScriptRoot 'game.py') @GameArgs
exit $LASTEXITCODE
