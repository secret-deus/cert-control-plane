#!/usr/bin/env bash
# ============================================================
# cert-agent 安装脚本
# 在 nginx 节点上运行此脚本完成 agent 部署
# 用法: sudo bash agent/scripts/install.sh
#       sudo bash /path/to/install.sh  (从任意目录)
# ============================================================
set -euo pipefail

# 基于脚本所在位置定位项目文件
# 目录结构: agent/scripts/install.sh  →  SCRIPT_DIR = agent/scripts/
#            PROJECT_DIR = agent/  (agent Python 包 + 元数据文件所在目录)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

INSTALL_DIR="/opt/cert-agent"
CONFIG_DIR="/etc/cert-agent"
STATE_DIR="/var/lib/cert-agent"
NGINX_CERT_DIR="/etc/nginx/certs"

echo "=== cert-agent installer ==="
echo "  Project dir : $PROJECT_DIR"
echo "  Install dir : $INSTALL_DIR"

# ---- preflight checks (TASK-005) ----

_preflight_ok=true

_require_file() {
    if [ ! -f "$1" ]; then
        echo "ERROR: required file not found: $1"
        _preflight_ok=false
    fi
}

_require_cmd() {
    if ! command -v "$1" &>/dev/null; then
        echo "ERROR: required command not found: $1"
        _preflight_ok=false
    fi
}

# Required source files
_require_file "$PROJECT_DIR/__init__.py"
_require_file "$PROJECT_DIR/__main__.py"
_require_file "$PROJECT_DIR/runner.py"
_require_file "$PROJECT_DIR/client.py"
_require_file "$PROJECT_DIR/config.py"
_require_file "$PROJECT_DIR/crypto.py"
_require_file "$PROJECT_DIR/deployer.py"
_require_file "$PROJECT_DIR/pyproject.toml"
_require_file "$PROJECT_DIR/agent.env.example"
_require_file "$PROJECT_DIR/cert-agent.service"

# Required system commands
_require_cmd python3
_require_cmd pip3
_require_cmd systemctl

if [ "$_preflight_ok" != "true" ]; then
    echo ""
    echo "Preflight failed. Fix the above errors and re-run."
    exit 1
fi

echo "Preflight OK"

# ---- installation ----

# 1. 创建目录
echo "[1/5] 创建目录..."
mkdir -p "$INSTALL_DIR/agent" "$CONFIG_DIR" "$STATE_DIR" "$NGINX_CERT_DIR"

# 2. 复制 agent 代码
# PROJECT_DIR 本身就是 agent/ 包目录，其中 *.py 是 Python 模块
echo "[2/5] 安装 agent 代码到 $INSTALL_DIR..."
cp "$PROJECT_DIR"/*.py "$INSTALL_DIR/agent/"
cp "$PROJECT_DIR/pyproject.toml" "$INSTALL_DIR/"

# 3. 安装 Python 依赖
echo "[3/5] 安装 Python 依赖..."
pip3 install --no-cache-dir httpx cryptography

# 4. 安装环境变量配置（不覆盖已有配置）
echo "[4/5] 配置环境..."
if [ ! -f "$CONFIG_DIR/agent.env" ]; then
    cp "$PROJECT_DIR/agent.env.example" "$CONFIG_DIR/agent.env"
    chmod 600 "$CONFIG_DIR/agent.env"
    echo "  已创建 $CONFIG_DIR/agent.env，请编辑填入实际配置"
else
    echo "  $CONFIG_DIR/agent.env 已存在，跳过"
fi

# 5. 安装 systemd service
echo "[5/5] 安装 systemd 服务..."
cp "$PROJECT_DIR/cert-agent.service" /etc/systemd/system/cert-agent.service
systemctl daemon-reload
echo "  服务已安装，使用以下命令管理："
echo "    systemctl enable cert-agent   # 开机自启"
echo "    systemctl start cert-agent    # 启动"
echo "    systemctl status cert-agent   # 查看状态"
echo "    journalctl -u cert-agent -f   # 查看日志"

# ---- post-install smoke test (TASK-005) ----

echo ""
echo "[smoke] 验证安装..."
_smoke_ok=true

# Check installed files
for f in "$INSTALL_DIR/agent/__init__.py" \
         "$INSTALL_DIR/agent/runner.py" \
         "$INSTALL_DIR/pyproject.toml" \
         "$CONFIG_DIR/agent.env" \
         "/etc/systemd/system/cert-agent.service"; do
    if [ ! -f "$f" ]; then
        echo "  WARN: expected file missing: $f"
        _smoke_ok=false
    fi
done

# Check Python import
if python3 -c "import sys; sys.path.insert(0, '$INSTALL_DIR'); import agent" 2>/dev/null; then
    echo "  Python import OK"
else
    echo "  WARN: 'import agent' failed from $INSTALL_DIR"
    _smoke_ok=false
fi

if [ "$_smoke_ok" = "true" ]; then
    echo "  Smoke test PASSED"
else
    echo "  Smoke test had warnings — review above output"
fi

echo ""
echo "=== 安装完成 ==="
echo "下一步："
echo "  1. 将 CA 证书复制到 $CONFIG_DIR/ca.crt"
echo "  2. 编辑 $CONFIG_DIR/agent.env 填入控制面板地址和 bootstrap token"
echo "  3. 运行 systemctl start cert-agent"
