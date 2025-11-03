# PowerShell script to start Shirzad Bot locally
Write-Host "Starting Shirzad Bot Platform..." -ForegroundColor Green

# Activate venv
if (Test-Path "venv\Scripts\Activate.ps1") {
    & "venv\Scripts\Activate.ps1"
    Write-Host "Virtual environment activated" -ForegroundColor Yellow
} else {
    Write-Host "ERROR: venv not found!" -ForegroundColor Red
    Write-Host "Create it with: python -m venv venv" -ForegroundColor Yellow
    exit 1
}

# Start the app
Write-Host "`nStarting app on http://localhost:5010`n" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop`n" -ForegroundColor Gray

python app.py

