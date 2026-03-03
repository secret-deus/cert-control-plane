#!/usr/bin/env bash
# ============================================================
# cert-agent 安装脚本
# 在 nginx 节点上运行此脚本完成 agent 部署
# 用法: sudo bash scripts/install.sh  (或从任意目录: sudo bash /path/to/install.sh)
# ============================================================
set -euo pipefail

# 基于脚本所在位置定位项目文件
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

INSTALL_DIR="/opt/cert-agent"
CONFIG_DIR="/etc/cert-agent"
STATE_DIR="/var/lib/cert-agent"
NGINX_CERT_DIR="/etc/nginx/certs"

echo "=== cert-agent installer ==="
echo "  项目目录: $PROJECT_DIR"

# 1. 创建目录
echo "[1/5] 创建目录..."
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$STATE_DIR" "$NGINX_CERT_DIR"

# 2. 复制 agent 代码
echo "[2/5] 安装 agent 代码到 $INSTALL_DIR..."
cp -r "$PROJECT_DIR/agent/" "$INSTALL_DIR/agent/"
cp "$PROJECT_DIR/pyproject.toml" "$INSTALL_DIR/"

# 3. 安装 Python 依赖
echo "[3/5] 安装 Python 依赖..."
if command -v pip3 &>/dev/null; then
    pip3 install --no-cache-dir httpx cryptography
else
    echo "错误: pip3 未找到，请先安装 python3-pip"
    exit 1
fi

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
cp "$PROJECT_DIR/agent/cert-agent.service" /etc/systemd/system/cert-agent.service
systemctl daemon-reload
echo "  服务已安装，使用以下命令管理："
echo "    systemctl enable cert-agent   # 开机自启"
echo "    systemctl start cert-agent    # 启动"
echo "    systemctl status cert-agent   # 查看状态"
echo "    journalctl -u cert-agent -f   # 查看日志"

echo ""
echo "=== 安装完成 ==="
echo "下一步："
echo "  1. 将 CA 证书复制到 $CONFIG_DIR/ca.crt"
echo "  2. 编辑 $CONFIG_DIR/agent.env 填入控制面板地址和 bootstrap token"
echo "  3. 运行 systemctl start cert-agent"
