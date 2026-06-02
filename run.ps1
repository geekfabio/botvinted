$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

if (-not (Test-Path ".\venv")) {
    python -m venv .\venv
}

Write-Host "Activating virtual environment..."
.\venv\Scripts\Activate.ps1

Write-Host "Running bot.py with arguments: $args"
python .\bot.py @args
