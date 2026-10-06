$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir
$env:PYTHONUTF8 = "1"

if (-not (Test-Path ".\.venv")) {
    python -m venv .\.venv
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Não foi possível criar o ambiente virtual."
        exit $LASTEXITCODE
    }
}

$pythonPath = ".\.venv\Scripts\python.exe"
& $pythonPath -c "import requests, yaml, dotenv, schedule" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing missing dependencies..."
    & $pythonPath -m pip install -r .\requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Error "A instalação das dependências falhou."
        exit $LASTEXITCODE
    }
}

Write-Host "Running bot.py with arguments: $args"
& $pythonPath .\bot.py @args
exit $LASTEXITCODE
