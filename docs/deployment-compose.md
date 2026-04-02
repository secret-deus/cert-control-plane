# Docker Compose 部署与排障

本文档描述当前仓库的 `docker compose` 启动方式、最小验证步骤，以及已知排障要点。当前基线是“外部证书分发模式”：

- `443` 提供 Control API、Swagger 和前端 Dashboard
- `8443` 仅提供 Agent API
- Agent 认证依赖 `X-Agent-Token`，不是 mTLS

## 前置条件

- 已安装 Docker 与 Docker Compose Plugin
- 仓库根目录存在 `.env`
- 仓库根目录存在 `certs/`，至少包含 `server.crt` 与 `server.key`

如果本地还没有 `.env` 与测试证书，可先执行：

```bash
bash start.sh
```

或手动生成：

```bash
cp .env.example .env
python scripts/init_ca.py --out-dir ./certs
```

## 启动步骤

在仓库根目录执行：

```bash
docker compose up -d --build
```

启动后检查容器状态：

```bash
docker compose ps
```

正常情况下应至少看到以下服务：

- `db`
- `app`
- `nginx`

## 最小烟雾验证

1. 健康检查：

```bash
curl -k https://localhost:443/healthz
```

期望返回：

```json
{"status":"ok"}
```

2. OpenAPI 文档：

```bash
curl -k -I https://localhost:443/docs
```

3. Agent 入口可达性：

```bash
curl -k -I https://localhost:8443/api/agent/register
```

说明：

- `8443` 上访问 `/api/agent/*` 有响应即表示 Agent 路由打通
- `8443` 访问 `/` 返回 `404` 是预期行为
- `443` 访问 `/api/agent/*` 返回 `403` 是预期行为

## Live Agent Smoke

如果你要验证真实的 `Agent -> fetch-certs -> nginx reload` 链路，可以直接执行：

```bash
bash tools/agent-smoke/run-live-smoke.sh
```

这个脚本会自动：

- 重建 `app`、`nginx` 和临时 `edge-node`
- 清理旧的 `edge-node-live-1` smoke Agent 记录，避免指纹漂移
- 自动批准 `edge-node-live-1`（如果还在 `pending_approval`）
- 生成一张新的测试证书并上传到控制面
- 分配到 `/etc/nginx/certs/api.example.com.crt`
- 轮询直到 `edge-node` 完成部署

成功后会打印新的 serial、subject 和到期时间；业务入口固定在：

```bash
https://localhost:9444
```

## 常用日志命令

查看全部服务日志：

```bash
docker compose logs --tail=200
```

聚焦单个服务：

```bash
docker compose logs app --tail=200
docker compose logs nginx --tail=200
docker compose logs db --tail=200
```

## 已知排障要点

### 1. 首次构建很慢

首次 `docker compose up -d --build` 可能很慢，尤其在 ARM 机器或无缓存环境下，主要耗时在：

- `frontend` 的 `npm ci` / `npm run build`
- `app` 镜像内的 `pip install -e .`

这通常不是卡死，先看 `docker compose logs` 或构建输出是否仍在前进。

### 2. 前端镜像构建失败

如果失败点在 `frontend` 构建阶段，先在本地验证：

```bash
cd frontend
npm install
npm run build
```

当前仓库要求前端必须能完成生产构建，否则 `docker compose` 不会成功。

### 3. `443` 正常但 `8443` 不通

优先检查：

- `nginx/nginx.conf` 是否仍将 `8443` 路由到 `/api/agent/`
- `docker compose ps` 中 `nginx` 是否已启动
- 本机是否已有其他进程占用 `8443`

### 4. `443` 访问 `/api/agent/*` 返回 403

这是预期行为。Agent API 只允许走 `8443`。

### 5. `app` 服务启动失败

优先检查：

- `.env` 中 `CA_KEY_ENCRYPTION_KEY` 与 `ADMIN_API_KEY` 是否已设置
- `DATABASE_URL` 是否能连到 `db`
- 数据库迁移是否已执行

需要时可进入容器内进一步检查：

```bash
docker compose exec app alembic upgrade head
docker compose exec app python -m pytest tests/test_agent_api.py -q
```
