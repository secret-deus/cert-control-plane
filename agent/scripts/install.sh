#!/usr/bin/env bash
# ============================================================
# cert-agent 一键安装脚本 (Linux)
# 用法: sudo bash agent/scripts/install.sh
#   或: sudo bash agent/scripts/install.sh \
#         --cp-url https://cp.example.com:8443 \
#         --name web-node-01 \
#         --token <bootstrap_token>
# ============================================================
set -euo pipefail

# 基于脚本所在位置定位项目文件
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$(cd "$PROJECT_DIR/.." && pwd)"

INSTALL_DIR="/opt/cert-agent"
CONFIG_DIR="/etc/cert-agent"
STATE_DIR="/var/lib/cert-agent"
NGINX_CERT_DIR="/etc/nginx/certs"

# ── 解析参数 ──
CP_URL=""
AGENT_NAME=""
BOOTSTRAP_TOKEN=""
CA_CERT_SRC=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --cp-url)     CP_URL="$2"; shift 2 ;;
        --name)       AGENT_NAME="$2"; shift 2 ;;
        --token)      BOOTSTRAP_TOKEN="$2"; shift 2 ;;
        --ca-cert)    CA_CERT_SRC="$2"; shift 2 ;;
        *)            shift ;;
    esac
done

echo ""
echo "========================================"
echo "  cert-agent — Linux 一键安装"
echo "========================================"
echo "  源码目录:   $PROJECT_DIR"
echo "  安装目录:   $INSTALL_DIR"
echo ""

# ── 交互式采集缺失参数 ──
if [ -z "$CP_URL" ]; then
    read -rp "请输入控制面板地址 (如 https://cp.example.com:8443): " CP_URL
fi
if [ -z "$AGENT_NAME" ]; then
    read -rp "请输入 Agent 名称 (需与控制面板预注册一致): " AGENT_NAME
fi
if [ -z "$BOOTSTRAP_TOKEN" ]; then
    read -rp "请输入 Bootstrap Token: " BOOTSTRAP_TOKEN
fi

# ── preflight checks ──
echo "[1/6] Preflight 检查..."
_preflight_ok=true

_require_file() {
    if [ ! -f "$1" ]; then
        echo "  ERROR: 缺少文件: $1"
        _preflight_ok=false
    fi
}

_require_cmd() {
    if ! command -v "$1" &>/dev/null; then
        echo "  ERROR: 缺少命令: $1"
        _preflight_ok=false
    fi
}

_require_file "$PROJECT_DIR/__init__.py"
_require_file "$PROJECT_DIR/__main__.py"
_require_file "$PROJECT_DIR/runner.py"
_require_file "$PROJECT_DIR/client.py"
_require_file "$PROJECT_DIR/config.py"
_require_file "$PROJECT_DIR/crypto.py"
_require_file "$PROJECT_DIR/deployer.py"
_require_file "$PROJECT_DIR/pyproject.toml"
_require_file "$PROJECT_DIR/cert-agent.service"

_require_cmd python3
_require_cmd pip3
_require_cmd systemctl

if [ "$_preflight_ok" != "true" ]; then
    echo "  Preflight 失败，请修复以上错误后重试"
    exit 1
fi
echo "  Preflight OK"

# ── 创建目录 ──
echo "[2/6] 创建目录..."
mkdir -p "$INSTALL_DIR/agent" "$CONFIG_DIR" "$STATE_DIR" "$NGINX_CERT_DIR"

# ── 复制代码 ──
echo "[3/6] 安装 agent 代码到 $INSTALL_DIR..."
cp "$PROJECT_DIR"/*.py "$INSTALL_DIR/agent/"
cp "$PROJECT_DIR/pyproject.toml" "$INSTALL_DIR/"

# ── 安装依赖 ──
echo "[4/6] 安装 Python 依赖..."
pip3 install --no-cache-dir httpx cryptography

# ── 生成配置 ──
echo "[5/6] 生成配置文件..."
if [ ! -f "$CONFIG_DIR/agent.env" ]; then
    # 复制 CA 证书
    if [ -n "$CA_CERT_SRC" ] && [ -f "$CA_CERT_SRC" ]; then
        cp "$CA_CERT_SRC" "$CONFIG_DIR/ca.crt"
    elif [ -f "$ROOT_DIR/certs/ca.crt" ]; then
        cp "$ROOT_DIR/certs/ca.crt" "$CONFIG_DIR/ca.crt"
        echo "  从项目 certs/ 复制 CA 证书"
    else
        echo "  WARN: 未找到 CA 证书，请手动复制到 $CONFIG_DIR/ca.crt"
    fi

    cat > "$CONFIG_DIR/agent.env" <<EOF
# cert-agent 配置 (自动生成)
CERT_AGENT_CP_URL=$CP_URL
CERT_AGENT_CA_CERT=$CONFIG_DIR/ca.crt
CERT_AGENT_NAME=$AGENT_NAME
CERT_AGENT_BOOTSTRAP_TOKEN=$BOOTSTRAP_TOKEN
CERT_AGENT_STATE_DIR=$STATE_DIR
CERT_AGENT_NGINX_CERT_DIR=$NGINX_CERT_DIR
CERT_AGENT_NGINX_RELOAD_CMD=nginx -s reload
CERT_AGENT_HEARTBEAT_INTERVAL=30
CERT_AGENT_RENEW_BEFORE_DAYS=7
CERT_AGENT_MAX_AUTH_FAILURES=3
EOF
    chmod 600 "$CONFIG_DIR/agent.env"
    echo "  配置已写入 $CONFIG_DIR/agent.env"
else
    echo "  $CONFIG_DIR/agent.env 已存在，跳过"
fi

# ── 安装 systemd 服务 ──
echo "[6/6] 安装 systemd 服务..."
cp "$PROJECT_DIR/cert-agent.service" /etc/systemd/system/cert-agent.service
systemctl daemon-reload

# ── smoke test ──
echo ""
echo "[smoke] 验证安装..."
_smoke_ok=true

for f in "$INSTALL_DIR/agent/__init__.py" \
         "$INSTALL_DIR/agent/runner.py" \
         "$INSTALL_DIR/pyproject.toml" \
         "$CONFIG_DIR/agent.env" \
         "/etc/systemd/system/cert-agent.service"; do
    if [ ! -f "$f" ]; then
        echo "  WARN: 文件缺失: $f"
        _smoke_ok=false
    fi
done

if python3 -c "import sys; sys.path.insert(0, '$INSTALL_DIR'); import agent" 2>/dev/null; then
    echo "  Python import OK"
else
    echo "  WARN: 'import agent' 失败"
    _smoke_ok=false
fi

if [ "$_smoke_ok" = "true" ]; then
    echo "  Smoke test PASSED"
else
    echo "  Smoke test 有警告 — 请检查以上输出"
fi

echo ""
echo "========================================"
echo "  ✅ 安装完成！"
echo "========================================"
echo ""
echo "  安装目录:   $INSTALL_DIR"
echo "  配置文件:   $CONFIG_DIR/agent.env"
echo "  状态目录:   $STATE_DIR"
echo ""
echo "  管理命令:"
echo "    systemctl enable cert-agent   # 开机自启"
echo "    systemctl start cert-agent    # 启动"
echo "    systemctl status cert-agent   # 查看状态"
echo "    journalctl -u cert-agent -f   # 查看日志"
echo ""
