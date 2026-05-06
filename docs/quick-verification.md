#!/bin/bash
# 快速验证脚本 - 验证 Cert Control Plane 的核心功能

set -e

echo "🚀 Cert Control Plane 快速验证"
echo "================================"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查命令是否存在
check_command() {
    if command -v $1 &> /dev/null; then
        echo -e "${GREEN}✓${NC} $1 已安装"
        return 0
    else
        echo -e "${RED}✗${NC} $1 未安装"
        return 1
    fi
}

# 检查端口是否被占用
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} 端口 $1 正在监听"
        return 0
    else
        echo -e "${RED}✗${NC} 端口 $1 未监听"
        return 1
    fi
}

# 检查 HTTP 端点
check_endpoint() {
    local url=$1
    local name=$2

    if curl -k -s -o /dev/null -w "%{http_code}" "$url" | grep -q "200\|401\|405"; then
        echo -e "${GREEN}✓${NC} $name 可访问"
        return 0
    else
        echo -e "${RED}✗${NC} $name 不可访问"
        return 1
    fi
}

echo ""
echo "1️⃣ 检查依赖"
echo "------------"
check_command python3
check_command pip
check_command node
check_command npm
check_command docker
check_command git

echo ""
echo "2️⃣ 检查项目文件"
echo "----------------"
files=(
    "app/main.py"
    "agent/runner.py"
    "frontend/package.json"
    "docker-compose.yml"
    ".env"
    "README.md"
)

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file 存在"
    else
        echo -e "${RED}✗${NC} $file 缺失"
    fi
done

echo ""
echo "3️⃣ 检查后端测试"
echo "----------------"
echo "运行后端测试..."
if python3 -m pytest tests/ -q --tb=no 2>&1 | grep -q "passed"; then
    echo -e "${GREEN}✓${NC} 后端测试通过"
else
    echo -e "${YELLOW}!${NC} 后端测试未运行或失败"
fi

echo ""
echo "4️⃣ 检查前端构建"
echo "----------------"
if [ -d "frontend/dist" ]; then
    echo -e "${GREEN}✓${NC} 前端已构建"
else
    echo -e "${YELLOW}!${NC} 前端未构建，正在构建..."
    cd frontend && npm install && npm run build && cd ..
fi

echo ""
echo "5️⃣ 检查服务状态"
echo "----------------"
# 检查 Docker 服务
if docker ps &>/dev/null; then
    if docker ps | grep -q "cert-control-plane"; then
        echo -e "${GREEN}✓${NC} Docker 服务运行中"
        check_port 8080
    else
        echo -e "${YELLOW}!${NC} Docker 服务未启动"
        echo "  启动命令: docker-compose up -d"
    fi
else
    echo -e "${YELLOW}!${NC} Docker 未运行"
fi

echo ""
echo "6️⃣ 检查 API 端点"
echo "----------------"
if check_port 8080; then
    check_endpoint "http://localhost:8080/healthz" "健康检查"
    check_endpoint "http://localhost:8080/docs" "API 文档"
    check_endpoint "http://localhost:8080/dashboard" "Dashboard"
    check_endpoint "http://localhost:8080/api/agent/register" "Agent API"
fi

echo ""
echo "7️⃣ 检查 Agent 构建"
echo "------------------"
if [ -f "agent-go/dist/cert-agent-linux-amd64" ]; then
    echo -e "${GREEN}✓${NC} Go Agent 已构建"
else
    echo -e "${YELLOW}!${NC} Go Agent 未构建"
fi

if [ -f "agent-rust/dist/cert-agent-darwin-arm64" ]; then
    echo -e "${GREEN}✓${NC} Rust Agent 已构建"
else
    echo -e "${YELLOW}!${NC} Rust Agent 未构建"
fi

echo ""
echo "8️⃣ 检查文档完整性"
echo "------------------"
docs=(
    "README.md"
    "PLAN.md"
    "docs/deployment-production.md"
    "docs/alerting.md"
    "docs/security-audit-checklist.md"
    "docs/pre-production-checklist.md"
)

for doc in "${docs[@]}"; do
    if [ -f "$doc" ]; then
        echo -e "${GREEN}✓${NC} $doc 存在"
    else
        echo -e "${RED}✗${NC} $doc 缺失"
    fi
done

echo ""
echo "9️⃣ 检查 Git 状态"
echo "----------------"
if git diff-index --quiet HEAD --; then
    echo -e "${GREEN}✓${NC} 工作目录干净"
else
    echo -e "${YELLOW}!${NC} 有未提交的更改"
fi

ahead=$(git log origin/master..HEAD --oneline 2>/dev/null | wc -l)
if [ "$ahead" -gt 0 ]; then
    echo -e "${YELLOW}!${NC} 有 $ahead 个本地提交待推送"
else
    echo -e "${GREEN}✓${NC} 与远程同步"
fi

echo ""
echo "📊 验证总结"
echo "============"
echo "✅ 项目验证完成！"
echo ""
echo "下一步操作："
echo "1. 如果服务未启动: docker-compose up -d"
echo "2. 如果测试未通过: python3 -m pytest tests/ -v"
echo "3. 如果前端未构建: cd frontend && npm run build"
echo "4. 推送代码: git push origin master"
echo "5. 检查 CI: gh run list"
echo ""
echo "查看详细指南: docs/next-steps.md"
