# 快速验证

本文档用于在本地或测试环境快速确认当前版本是否可运行。需要真实执行时，优先使用仓库脚本，不使用 mock 作为验收依据。

## 1. 基础检查

```bash
git status --short
docker version
docker compose version
python3 --version
```

前端验证需要 Node.js。当前仓库前端位于 `server/frontend/`：

```bash
cd server/frontend
npm install
npm run lint
npm run build
```

## 2. 后端测试

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python3 -m pytest tests -q
```

Python Agent 测试：

```bash
python3 -m pytest ../client/tests -q
```

Go Agent 测试：

```bash
cd ../client/agent-go
go test ./...
```

## 3. Compose 控制面 smoke

准备 `.env`，至少包含：

```bash
POSTGRES_PASSWORD=<strong-password>
DATABASE_URL=postgresql+asyncpg://postgres:<strong-password>@db:5432/certcp
CA_KEY_ENCRYPTION_KEY=<fernet-key>
ADMIN_API_KEY=<strong-admin-key>
CORS_ORIGINS=["http://localhost:8080","http://127.0.0.1:8080"]
DEV_MODE=false
```

启动并检查：

```bash
docker compose up -d --build
docker compose ps
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/readyz
curl -fsS http://127.0.0.1:8080/metrics
```

生产镜像 smoke 脚本：

```bash
bash scripts/smoke-test.sh
```

真实 Agent + nginx 链路：

```bash
bash tools/agent-smoke/run-live-smoke.sh
```

## 4. Minikube 验证

部署控制面到 minikube：

```bash
bash scripts/minikube-deploy.sh
kubectl -n cert-control-plane port-forward svc/cert-control-plane 18080:8080
```

真实 Kubernetes Secret E2E：

```bash
export CONTROL_PLANE_URL=http://127.0.0.1:18080
export ADMIN_API_KEY="$(kubectl -n cert-control-plane get secret cert-control-plane-secrets \
  -o jsonpath='{.data.ADMIN_API_KEY}' | base64 -d)"

bash scripts/minikube-k8s-secret-e2e.sh
bash scripts/minikube-k8s-secret-real-simulation.sh
```

## 5. 验收标准

- 后端、前端、Agent 测试通过。
- `/healthz`、`/readyz`、`/metrics` 可访问。
- Dashboard 可登录并访问 `/dashboard`。
- 真实 Agent 能注册、审批、拉取证书并完成 nginx reload。
- Kubernetes Secret 场景能完成新增、替换、adopt、最近一次回滚和 read-back serial 校验。
- 关键浏览器截图和真实测试证据写入 `specs/`。
