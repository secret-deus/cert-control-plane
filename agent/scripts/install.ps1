# ============================================================
# cert-agent 一键安装脚本 (Windows PowerShell)
# 用法 (管理员权限): .\agent\scripts\install.ps1
#
# 参数:
#   -CpUrl         控制面板地址  (必填或交互输入)
#   -AgentName     Agent 名称    (必填或交互输入)
#   -Token         Bootstrap Token (必填或交互输入)
#   -CaCertPath    CA 证书路径   (可选, 默认从项目 certs/ 拉取)
# ============================================================
param(
    [string]$CpUrl,
    [string]$AgentName,
    [string]$Token,
    [string]$CaCertPath
)

$ErrorActionPreference = "Stop"

# 路径推断
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AgentSrcDir = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$ProjectRoot = (Resolve-Path (Join-Path $AgentSrcDir "..")).Path

$InstallDir = "$env:ProgramData\cert-agent"
$ConfigDir  = "$InstallDir\config"
$StateDir   = "$InstallDir\state"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  cert-agent — Windows 一键安装" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  源码目录:   $AgentSrcDir"
Write-Host "  安装目录:   $InstallDir"
Write-Host ""

# ── 交互式采集参数 ──
if (-not $CpUrl) {
    $CpUrl = Read-Host "请输入控制面板地址 (如 https://cp.example.com:8443)"
}
if (-not $AgentName) {
    $AgentName = Read-Host "请输入 Agent 名称 (需与控制面板预注册一致)"
}
if (-not $Token) {
    $Token = Read-Host "请输入 Bootstrap Token"
}

# ── 1. Preflight 检查 ──
Write-Host "[1/6] Preflight 检查..." -ForegroundColor Yellow
$ok = $true

$requiredFiles = @(
    "__init__.py", "__main__.py", "runner.py", "client.py",
    "config.py", "crypto.py", "deployer.py", "pyproject.toml"
)
foreach ($f in $requiredFiles) {
    if (-not (Test-Path (Join-Path $AgentSrcDir $f))) {
        Write-Host "  ERROR: 缺少文件 $f" -ForegroundColor Red
        $ok = $false
    }
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "  ERROR: 未找到 python" -ForegroundColor Red
    $ok = $false
}

if (-not $ok) {
    Write-Host "  Preflight 失败，请修复以上问题后重试" -ForegroundColor Red
    exit 1
}
Write-Host "  Preflight OK" -ForegroundColor Green

# ── 2. 创建目录 ──
Write-Host "[2/6] 创建目录..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "$InstallDir\agent" | Out-Null
New-Item -ItemType Directory -Force -Path $ConfigDir           | Out-Null
New-Item -ItemType Directory -Force -Path $StateDir            | Out-Null
Write-Host "  目录就绪" -ForegroundColor Green

# ── 3. 复制代码 ──
Write-Host "[3/6] 复制 Agent 代码..." -ForegroundColor Yellow
Copy-Item "$AgentSrcDir\*.py" "$InstallDir\agent\" -Force
Copy-Item "$AgentSrcDir\pyproject.toml" "$InstallDir\" -Force
Write-Host "  代码已安装到 $InstallDir\agent\" -ForegroundColor Green

# ── 4. 安装依赖 ──
Write-Host "[4/6] 安装 Python 依赖..." -ForegroundColor Yellow
python -m pip install --quiet httpx cryptography 2>&1 | Out-Null
Write-Host "  依赖就绪" -ForegroundColor Green

# ── 5. 生成配置 ──
Write-Host "[5/6] 生成配置文件..." -ForegroundColor Yellow
$envFile = Join-Path $ConfigDir "agent.env"
if (-not (Test-Path $envFile)) {
    # 复制 CA 证书
    $caCertDst = Join-Path $ConfigDir "ca.crt"
    if ($CaCertPath -and (Test-Path $CaCertPath)) {
        Copy-Item $CaCertPath $caCertDst -Force
    } elseif (Test-Path (Join-Path $ProjectRoot "certs\ca.crt")) {
        Copy-Item (Join-Path $ProjectRoot "certs\ca.crt") $caCertDst -Force
        Write-Host "  从项目 certs/ 复制 CA 证书" -ForegroundColor DarkYellow
    } else {
        Write-Host "  WARN: 未找到 CA 证书，请手动复制到 $caCertDst" -ForegroundColor Yellow
    }

    @"
# cert-agent 配置 (自动生成)
CERT_AGENT_CP_URL=$CpUrl
CERT_AGENT_CA_CERT=$caCertDst
CERT_AGENT_NAME=$AgentName
CERT_AGENT_BOOTSTRAP_TOKEN=$Token
CERT_AGENT_STATE_DIR=$StateDir
CERT_AGENT_HEARTBEAT_INTERVAL=30
CERT_AGENT_RENEW_BEFORE_DAYS=7
CERT_AGENT_MAX_AUTH_FAILURES=3
"@ | Out-File -FilePath $envFile -Encoding utf8
    Write-Host "  配置已写入 $envFile" -ForegroundColor Green
} else {
    Write-Host "  配置已存在，跳过 ($envFile)" -ForegroundColor DarkYellow
}

# ── 6. 注册 Windows 服务 (使用 NSSM 或 Task Scheduler) ──
Write-Host "[6/6] 注册 Windows 计划任务..." -ForegroundColor Yellow
$taskName = "CertAgent"
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$pythonExe = (Get-Command python).Source
$action = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument "-m agent" `
    -WorkingDirectory $InstallDir

$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Cert Agent — 证书生命周期管理 Agent" | Out-Null

Write-Host "  计划任务 '$taskName' 已注册" -ForegroundColor Green

# ── Smoke Test ──
Write-Host ""
Write-Host "[smoke] 验证安装..." -ForegroundColor Yellow
$smokeOk = $true

$checkFiles = @(
    "$InstallDir\agent\__init__.py",
    "$InstallDir\agent\runner.py",
    "$InstallDir\pyproject.toml",
    "$ConfigDir\agent.env"
)
foreach ($f in $checkFiles) {
    if (-not (Test-Path $f)) {
        Write-Host "  WARN: 文件缺失 $f" -ForegroundColor Yellow
        $smokeOk = $false
    }
}

$importCheck = python -c "import sys; sys.path.insert(0, '$InstallDir'); import agent" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Python import OK" -ForegroundColor Green
} else {
    Write-Host "  WARN: Python import 失败" -ForegroundColor Yellow
    $smokeOk = $false
}

if ($smokeOk) {
    Write-Host "  Smoke test PASSED" -ForegroundColor Green
} else {
    Write-Host "  Smoke test 有警告 — 请检查以上输出" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  ✅ 安装完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  安装目录:   $InstallDir" -ForegroundColor White
Write-Host "  配置文件:   $envFile" -ForegroundColor White
Write-Host "  状态目录:   $StateDir" -ForegroundColor White
Write-Host ""
Write-Host "  管理命令:" -ForegroundColor Cyan
Write-Host "    Start-ScheduledTask -TaskName CertAgent     # 启动" -ForegroundColor White
Write-Host "    Stop-ScheduledTask  -TaskName CertAgent     # 停止" -ForegroundColor White
Write-Host "    Get-ScheduledTask   -TaskName CertAgent     # 查看状态" -ForegroundColor White
Write-Host ""
