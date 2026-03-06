# ============================================================
# Cert Control Plane - One-Click Startup (Windows PowerShell)
# Usage: .\startup.ps1
# ============================================================
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Cert Control Plane - One-Click Start" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# -- 1. Check Python --
Write-Host "[1/6] Checking Python..." -ForegroundColor Yellow
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "  ERROR: python not found. Please install Python 3.11+" -ForegroundColor Red
    exit 1
}
$pyVer = python --version 2>&1
Write-Host "  $pyVer" -ForegroundColor Green

# -- 2. Install Python deps --
Write-Host "[2/6] Checking Python dependencies..." -ForegroundColor Yellow
$deps = @("fastapi", "uvicorn", "sqlalchemy", "pydantic_settings", "cryptography", "apscheduler", "aiosqlite", "httpx")
foreach ($dep in $deps) {
    $check = python -c "import $dep" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Installing: $dep" -ForegroundColor DarkYellow
        python -m pip install $dep --quiet 2>&1 | Out-Null
    }
}
Write-Host "  Dependencies OK" -ForegroundColor Green

# -- 3. Setup .env --
Write-Host "[3/6] Checking .env config..." -ForegroundColor Yellow
$envFile = Join-Path $root ".env"
$envExample = Join-Path $root ".env.example"

if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-Host "  Created .env from .env.example" -ForegroundColor DarkYellow
    } else {
        $defaultEnv = @"
DATABASE_URL=sqlite+aiosqlite:///./certcp.db
CA_CERT_PATH=./certs/ca.crt
CA_KEY_PATH=./certs/ca.key
STRICT_CA_STARTUP=true
CERT_VALIDITY_DAYS=365
BOOTSTRAP_TOKEN_EXPIRE_HOURS=24
ROLLOUT_INTERVAL_SECONDS=30
ROLLOUT_ITEM_TIMEOUT_MINUTES=10
"@
        $defaultEnv | Out-File -FilePath $envFile -Encoding utf8
        Write-Host "  Created default .env" -ForegroundColor DarkYellow
    }
}

# Switch to SQLite for local dev
$envContent = Get-Content $envFile -Raw
if ($envContent -match "postgresql\+asyncpg://") {
    $envContent = $envContent -replace "DATABASE_URL=postgresql\+asyncpg://[^\r\n]+", "DATABASE_URL=sqlite+aiosqlite:///./certcp.db"
    $envContent | Set-Content $envFile -Encoding utf8
    Write-Host "  Switched DATABASE_URL to SQLite" -ForegroundColor DarkYellow
}

# Auto-generate missing keys
$envContent = Get-Content $envFile -Raw
if ($envContent -match "CA_KEY_ENCRYPTION_KEY=REPLACE" -or -not ($envContent -match "CA_KEY_ENCRYPTION_KEY=\S{20}")) {
    $fernetKey = python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>&1
    $envContent = $envContent -replace "CA_KEY_ENCRYPTION_KEY=REPLACE[^\r\n]*", ""
    Add-Content -Path $envFile -Value "CA_KEY_ENCRYPTION_KEY=$fernetKey"
    Write-Host "  Generated CA_KEY_ENCRYPTION_KEY" -ForegroundColor DarkYellow
}
$envContent = Get-Content $envFile -Raw
if ($envContent -match "ADMIN_API_KEY=REPLACE" -or -not ($envContent -match "ADMIN_API_KEY=\S{20}")) {
    $apiKey = python -c "import secrets; print(secrets.token_hex(32))" 2>&1
    $envContent = $envContent -replace "ADMIN_API_KEY=REPLACE[^\r\n]*", ""
    Add-Content -Path $envFile -Value "ADMIN_API_KEY=$apiKey"
    Write-Host "  Generated ADMIN_API_KEY" -ForegroundColor DarkYellow
} else {
    $matched = ($envContent | Select-String -Pattern "ADMIN_API_KEY=(\S+)" -AllMatches).Matches
    $apiKey = $matched[$matched.Count - 1].Groups[1].Value
}
Write-Host "  .env ready" -ForegroundColor Green

# -- 4. Generate CA certs --
Write-Host "[4/6] Checking CA certificates..." -ForegroundColor Yellow
$certsDir = Join-Path $root "certs"
if (-not (Test-Path (Join-Path $certsDir "ca.crt"))) {
    Write-Host "  Generating CA + server certificates..." -ForegroundColor DarkYellow
    python (Join-Path $root "scripts" "init_ca.py") --out-dir $certsDir 2>&1 | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Host "  CA certificates exist" -ForegroundColor Green
}

# -- 5. Start backend --
Write-Host "[5/6] Starting FastAPI backend (port $BackendPort)..." -ForegroundColor Yellow

# Kill old processes on that port
Get-NetTCPConnection -LocalPort $BackendPort -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

$backendJob = Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$BackendPort" `
    -WorkingDirectory $root `
    -PassThru -WindowStyle Minimized
Write-Host "  Backend PID: $($backendJob.Id)" -ForegroundColor Green

# -- 6. Start frontend --
if (-not $SkipFrontend) {
    Write-Host "[6/6] Starting React frontend (Vite dev)..." -ForegroundColor Yellow
    $frontendDir = Join-Path $root "frontend"

    if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
        Write-Host "  Installing frontend deps (npm install)..." -ForegroundColor DarkYellow
        Push-Location $frontendDir
        npm install --silent 2>&1 | Out-Null
        Pop-Location
    }

    # Ensure vite proxy points to correct backend port
    $viteConfig = Join-Path $frontendDir "vite.config.ts"
    if (Test-Path $viteConfig) {
        $viteContent = Get-Content $viteConfig -Raw
        $viteContent = $viteContent -replace "target:\s*'http://[^']+'" , "target: 'http://127.0.0.1:$BackendPort'"
        $viteContent | Set-Content $viteConfig -Encoding utf8
    }

    $frontendJob = Start-Process -FilePath "cmd" `
        -ArgumentList "/c", "npm run dev -- --host" `
        -WorkingDirectory $frontendDir `
        -PassThru -WindowStyle Minimized
    Write-Host "  Frontend PID: $($frontendJob.Id)" -ForegroundColor Green
} else {
    Write-Host "[6/6] Skipped frontend (--SkipFrontend)" -ForegroundColor DarkGray
}

# -- Done --
Start-Sleep -Seconds 2
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Started successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Backend API : http://127.0.0.1:$BackendPort" -ForegroundColor White
Write-Host "  API Docs    : http://127.0.0.1:$BackendPort/docs" -ForegroundColor White
if (-not $SkipFrontend) {
    Write-Host "  Frontend    : http://localhost:$FrontendPort" -ForegroundColor White
}
Write-Host ""
Write-Host "  ADMIN_API_KEY: $apiKey" -ForegroundColor Cyan
Write-Host ""
Write-Host "  To stop services:" -ForegroundColor DarkGray
Write-Host "    Stop-Process -Id $($backendJob.Id) -Force" -ForegroundColor DarkGray
if (-not $SkipFrontend -and $frontendJob) {
    Write-Host "    Stop-Process -Id $($frontendJob.Id) -Force" -ForegroundColor DarkGray
}
Write-Host ""
