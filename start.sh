#!/usr/bin/env bash
# ============================================================
# Cert Control Plane — 一键启动脚本 (Linux / macOS)
# 用法: bash start.sh
# ============================================================
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "========================================"
echo "  Cert Control Plane — 一键启动"
echo "========================================"
echo ""

# ── 1. 检查 Python ──
echo "[1/6] 检查 Python..."
if ! command -v python3 &>/dev/null; then
    echo "  ERROR: 未找到 python3，请先安装 Python 3.11+"
    exit 1
fi
echo "  $(python3 --version)"

# ── 2. 安装 Python 依赖 ──
echo "[2/6] 检查 Python 依赖..."
pip3 install --quiet fastapi uvicorn sqlalchemy pydantic-settings \
    cryptography apscheduler aiosqlite httpx 2>/dev/null || true
echo "  依赖就绪"

# ── 3. 生成 .env ──
echo "[3/6] 检查环境配置 (.env)..."
ENV_FILE="$ROOT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$ROOT_DIR/.env.example" ]; then
        cp "$ROOT_DIR/.env.example" "$ENV_FILE"
    else
        cat > "$ENV_FILE" <<'EOF'
DATABASE_URL=sqlite+aiosqlite:///./certcp.db
CA_CERT_PATH=./certs/ca.crt
CA_KEY_PATH=./certs/ca.key
STRICT_CA_STARTUP=true
CERT_VALIDITY_DAYS=365
BOOTSTRAP_TOKEN_EXPIRE_HOURS=24
ROLLOUT_INTERVAL_SECONDS=30
ROLLOUT_ITEM_TIMEOUT_MINUTES=10
EOF
    fi
    echo "  创建 .env"
fi

# 切换到 SQLite
if grep -q "postgresql+asyncpg://" "$ENV_FILE" 2>/dev/null; then
    sed -i.bak 's|DATABASE_URL=postgresql+asyncpg://.*|DATABASE_URL=sqlite+aiosqlite:///./certcp.db|' "$ENV_FILE"
    echo "  DATABASE_URL 已切换为 SQLite"
fi

# 自动生成密钥
if grep -q "CA_KEY_ENCRYPTION_KEY=REPLACE" "$ENV_FILE" || ! grep -qP "CA_KEY_ENCRYPTION_KEY=\S{20}" "$ENV_FILE" 2>/dev/null; then
    FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    sed -i.bak '/CA_KEY_ENCRYPTION_KEY=REPLACE/d' "$ENV_FILE"
    echo "CA_KEY_ENCRYPTION_KEY=$FERNET_KEY" >> "$ENV_FILE"
    echo "  自动生成 CA_KEY_ENCRYPTION_KEY"
fi

if grep -q "ADMIN_API_KEY=REPLACE" "$ENV_FILE" || ! grep -qP "ADMIN_API_KEY=\S{20}" "$ENV_FILE" 2>/dev/null; then
    API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i.bak '/ADMIN_API_KEY=REPLACE/d' "$ENV_FILE"
    echo "ADMIN_API_KEY=$API_KEY" >> "$ENV_FILE"
    echo "  自动生成 ADMIN_API_KEY"
else
    API_KEY=$(grep "ADMIN_API_KEY=" "$ENV_FILE" | tail -1 | cut -d= -f2)
fi
echo "  .env 就绪"

# ── 4. 生成 CA 证书 ──
echo "[4/6] 检查 CA 证书..."
CERTS_DIR="$ROOT_DIR/certs"
if [ ! -f "$CERTS_DIR/ca.crt" ]; then
    echo "  生成 CA + 服务端证书..."
    python3 "$ROOT_DIR/scripts/init_ca.py" --out-dir "$CERTS_DIR"
else
    echo "  CA 证书已存在"
fi

# ── 5. 启动后端 ──
echo "[5/6] 启动 FastAPI 后端 (port $BACKEND_PORT)..."
# 杀旧进程
lsof -ti:$BACKEND_PORT 2>/dev/null | xargs -r kill -9 2>/dev/null || true
sleep 1

cd "$ROOT_DIR"
python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" &
BACKEND_PID=$!
echo "  后端 PID: $BACKEND_PID"

# ── 6. 启动前端 ──
echo "[6/6] 启动 React 前端 (Vite dev)..."
FRONTEND_DIR="$ROOT_DIR/frontend"
if [ -d "$FRONTEND_DIR" ]; then
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        echo "  安装前端依赖..."
        cd "$FRONTEND_DIR" && npm install --silent 2>/dev/null
    fi

    cd "$FRONTEND_DIR"
    npm run dev -- --host &
    FRONTEND_PID=$!
    echo "  前端 PID: $FRONTEND_PID"
else
    echo "  frontend 目录不存在，跳过"
    FRONTEND_PID=""
fi

# ── 完成 ──
sleep 2
echo ""
echo "========================================"
echo "  ✅ 启动成功！"
echo "========================================"
echo ""
echo "  后端 API:    http://127.0.0.1:$BACKEND_PORT"
echo "  API 文档:    http://127.0.0.1:$BACKEND_PORT/docs"
[ -n "$FRONTEND_PID" ] && echo "  前端面板:    http://localhost:$FRONTEND_PORT"
echo ""
echo "  ADMIN_API_KEY: $API_KEY"
echo ""
echo "  停止服务:"
echo "    kill $BACKEND_PID"
[ -n "$FRONTEND_PID" ] && echo "    kill $FRONTEND_PID"
echo ""

# 等待后端进程
wait $BACKEND_PID
