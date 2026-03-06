# ============================================================
# Cert Control Plane — 一键启动脚本 (Windows PowerShell)
# 用法: .\startup.ps1
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
Write-Host "  Cert Control Plane — 一键启动" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. 检查 Python ──
Write-Host "[1/6] 检查 Python..." -ForegroundColor Yellow
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "  ERROR: 未找到 python，请先安装 Python 3.11+" -ForegroundColor Red
    exit 1
}
$pyVer = python --version 2>&1
Write-Host "  $pyVer" -ForegroundColor Green

# ── 2. 安装 Python 依赖 ──
Write-Host "[2/6] 检查 Python 依赖..." -ForegroundColor Yellow
$deps = @("fastapi", "uvicorn", "sqlalchemy", "pydantic_settings", "cryptography", "apscheduler", "aiosqlite", "httpx")
foreach ($dep in $deps) {
    $check = python -c "import $dep" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  安装缺失依赖: $dep" -ForegroundColor DarkYellow
        python -m pip install $dep --quiet 2>&1 | Out-Null
    }
}
Write-Host "  依赖就绪" -ForegroundColor Green

# ── 3. 生成 .env（如不存在或缺少 key） ──
Write-Host "[3/6] 检查环境配置 (.env)..." -ForegroundColor Yellow
$envFile = Join-Path $root ".env"
$envExample = Join-Path $root ".env.example"

if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-Host "  从 .env.example 创建 .env" -ForegroundColor DarkYellow
    } else {
        # 创建最小 .env
        @"
DATABASE_URL=sqlite+aiosqlite:///./certcp.db
CA_CERT_PATH=./certs/ca.crt
CA_KEY_PATH=./certs/ca.key
STRICT_CA_STARTUP=true
CERT_VALIDITY_DAYS=365
BOOTSTRAP_TOKEN_EXPIRE_HOURS=24
ROLLOUT_INTERVAL_SECONDS=30
ROLLOUT_ITEM_TIMEOUT_MINUTES=10
"@ | Out-File -FilePath $envFile -Encoding utf8
        Write-Host "  创建默认 .env" -ForegroundColor DarkYellow
    }
}

# 确保 DATABASE_URL 是 SQLite（本地开发）
$envContent = Get-Content $envFile -Raw
if ($envContent -match "postgresql\+asyncpg://") {
    $envContent = $envContent -replace "DATABASE_URL=postgresql\+asyncpg://[^\r\n]+", "DATABASE_URL=sqlite+aiosqlite:///./certcp.db"
    $envContent | Set-Content $envFile -Encoding utf8
    Write-Host "  DATABASE_URL 已切换为 SQLite (本地开发模式)" -ForegroundColor DarkYellow
}

# 自动生成缺失的密钥
$envContent = Get-Content $envFile -Raw
if ($envContent -match "CA_KEY_ENCRYPTION_KEY=REPLACE" -or -not ($envContent -match "CA_KEY_ENCRYPTION_KEY=\S{20}")) {
    $fernetKey = python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>&1
    if ($envContent -notmatch "`nCA_KEY_ENCRYPTION_KEY=$fernetKey") {
        # 追加或替换
        $envContent = $envContent -replace "CA_KEY_ENCRYPTION_KEY=REPLACE[^\r\n]*", ""
        Add-Content -Path $envFile -Value "CA_KEY_ENCRYPTION_KEY=$fernetKey"
        Write-Host "  自动生成 CA_KEY_ENCRYPTION_KEY" -ForegroundColor DarkYellow
    }
}
$envContent = Get-Content $envFile -Raw
if ($envContent -match "ADMIN_API_KEY=REPLACE" -or -not ($envContent -match "ADMIN_API_KEY=\S{20}")) {
    $apiKey = python -c "import secrets; print(secrets.token_hex(32))" 2>&1
    $envContent = $envContent -replace "ADMIN_API_KEY=REPLACE[^\r\n]*", ""
    Add-Content -Path $envFile -Value "ADMIN_API_KEY=$apiKey"
    Write-Host "  自动生成 ADMIN_API_KEY" -ForegroundColor DarkYellow
} else {
    # 读取已有的 key
    $apiKey = ($envContent | Select-String -Pattern "ADMIN_API_KEY=(\S+)" -AllMatches).Matches[-1].Groups[1].Value
}
Write-Host "  .env 就绪" -ForegroundColor Green

# ── 4. 生成 CA 证书（如不存在） ──
Write-Host "[4/6] 检查 CA 证书..." -ForegroundColor Yellow
$certsDir = Join-Path $root "certs"
if (-not (Test-Path (Join-Path $certsDir "ca.crt"))) {
    Write-Host "  生成 CA + 服务端证书..." -ForegroundColor DarkYellow
    python (Join-Path $root "scripts" "init_ca.py") --out-dir $certsDir 2>&1 | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Host "  CA 证书已存在" -ForegroundColor Green
}

# ── 5. 启动后端 ──
Write-Host "[5/6] 启动 FastAPI 后端 (port $BackendPort)..." -ForegroundColor Yellow

# 先清理旧进程
Get-NetTCPConnection -LocalPort $BackendPort -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

$backendJob = Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$BackendPort" `
    -WorkingDirectory $root `
    -PassThru -WindowStyle Minimized
Write-Host "  后端 PID: $($backendJob.Id)" -ForegroundColor Green

# ── 6. 启动前端 ──
if (-not $SkipFrontend) {
    Write-Host "[6/6] 启动 React 前端 (Vite dev)..." -ForegroundColor Yellow
    $frontendDir = Join-Path $root "frontend"
    
    if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
        Write-Host "  安装前端依赖 (npm install)..." -ForegroundColor DarkYellow
        Push-Location $frontendDir
        npm install --silent 2>&1 | Out-Null
        Pop-Location
    }

    # 确保 vite.config.ts 代理指向正确的后端端口
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
    Write-Host "  前端 PID: $($frontendJob.Id)" -ForegroundColor Green
} else {
    Write-Host "[6/6] 跳过前端 (--SkipFrontend)" -ForegroundColor DarkGray
}

# ── 完成 ──
Start-Sleep -Seconds 2
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  ✅ 启动成功！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  后端 API:    http://127.0.0.1:$BackendPort" -ForegroundColor White
Write-Host "  API 文档:    http://127.0.0.1:$BackendPort/docs" -ForegroundColor White
if (-not $SkipFrontend) {
    Write-Host "  前端面板:    http://localhost:$FrontendPort" -ForegroundColor White
}
Write-Host ""
Write-Host "  ADMIN_API_KEY: $apiKey" -ForegroundColor Cyan
Write-Host ""
Write-Host "  停止服务: 关闭本窗口或运行:" -ForegroundColor DarkGray
Write-Host "    Stop-Process -Id $($backendJob.Id) -Force" -ForegroundColor DarkGray
if (-not $SkipFrontend) {
    Write-Host "    Stop-Process -Id $($frontendJob.Id) -Force" -ForegroundColor DarkGray
}
Write-Host ""
