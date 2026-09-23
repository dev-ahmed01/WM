# WorkMate AI — 1-Click Local Application Launcher
param (
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$WM_ROOT = $PSScriptRoot

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "   WorkMate AI — Starting Frontend, Backend & DB    " -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan

# Verify Snowflake Database Connection
Write-Host "`n[1/3] Checking Snowflake Database Connection..." -ForegroundColor Yellow
python -c "
import sys
from pathlib import Path
sys.path.insert(0, r'$WM_ROOT\backend')
from app.core.database import ping
if ping():
    print('  [OK] Snowflake database WORKMATE_AI connected successfully!')
else:
    print('  [WARNING] Snowflake connection failed. Check backend/.env credentials.')
"

# Start FastAPI Backend
Write-Host "`n[2/3] Launching FastAPI Backend on http://localhost:8000..." -ForegroundColor Green
$backendJob = Start-Job -ScriptBlock {
    param($path)
    Set-Location $path
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
} -ArgumentList "$WM_ROOT\backend"

# Start Next.js Frontend
Write-Host "`n[3/3] Launching Next.js Frontend on http://localhost:3000..." -ForegroundColor Green
$frontendJob = Start-Job -ScriptBlock {
    param($path)
    Set-Location $path
    npm run dev
} -ArgumentList "$WM_ROOT\frontend"

Start-Sleep -Seconds 4

Write-Host "`n====================================================" -ForegroundColor Cyan
Write-Host "  SUCCESS! WorkMate AI is running locally." -ForegroundColor Green
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "  Frontend UI : http://localhost:3000" -ForegroundColor White
Write-Host "  Backend API : http://localhost:8000" -ForegroundColor White
Write-Host "  API Docs    : http://localhost:8000/docs" -ForegroundColor White
Write-Host "----------------------------------------------------" -ForegroundColor Gray
Write-Host "  Test Login Credentials:" -ForegroundColor Yellow
Write-Host "    Employee: employee@workmate.ai | Password: Test1234!" -ForegroundColor White
Write-Host "    Admin   : admin@workmate.ai    | Password: Test1234!" -ForegroundColor White
Write-Host "====================================================" -ForegroundColor Cyan

if (-not $NoBrowser) {
    Start-Process "http://localhost:3000"
}
