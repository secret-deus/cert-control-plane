# Docker Compose 部署与排障

本文档描述当前仓库的 `docker compose` 启动方式、最小验证步骤，以及已知排障要点。当前基线是“外部证书分发模式”：

- 单端口入口：`http://localhost:8080`
- Dashboard、Control API、Agent API 都由同一个 FastAPI 进程提供
- Control API 使用 `X-Admin-API-Key`
- Agent API 使用 `X-Agent-Token`，`/api/agent/register` 与 `/api/agent/register/status` 用于首次注册审批流程
- Compose 不再启动控制面 nginx；生产 TLS、来源限制和 WAF 放到外部负载均衡或网关处理

## 前置条件

- 已安装 Docker 与 Docker Compose Plugin
- 仓库根目录存在 `.env`

如果本地还没有 `.env`，可先执行：

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

## 最小烟雾验证

1. 健康检查：

```bash
curl http://localhost:8080/healthz
```

期望返回：

```json
{"status":"ok"}
```

2. OpenAPI 文档：

```bash
curl -I http://localhost:8080/docs
```

3. Dashboard：

```bash
curl -I http://localhost:8080/dashboard
```

4. Agent 入口可达性：

```bash
curl -i http://localhost:8080/api/agent/register
```

说明：

- `GET /api/agent/register` 返回 `405 Method Not Allowed` 是预期行为，因为注册接口是 `POST`
- 只要不是 SPA fallback 的 `200 index.html`，即可证明 Agent 路由已被 FastAPI 正确挂载
- Control API 和 Agent API 不再靠端口隔离，必须依赖各自的认证头和外部网络访问控制

## Live Agent Smoke

如果你要验证真实的 `Agent -> fetch-certs -> nginx reload` 链路，可以直接执行：

```bash
bash tools/agent-smoke/run-live-smoke.sh
```

这个脚本会自动：

- 重建 `db`、`app` 和临时 `edge-node`
- 清理旧的 `edge-node-live-1` smoke Agent 记录，避免指纹漂移
- 自动批准 `edge-node-live-1`（如果还在 `pending_approval`）
- 生成一张新的测试证书并上传到控制面
- 分配到 `/etc/nginx/certs/api.example.com.crt`
- 轮询直到 `edge-node` 完成部署并 reload 自身 nginx

成功后会打印新的 serial、subject 和到期时间；业务入口固定在：

```bash
https://localhost:9444
```

如果你要验证 Go 版纯二进制 Agent，可执行：

```bash
SMOKE_EDGE_OVERLAY=tools/agent-smoke/docker-compose.edge-go.yml \
SMOKE_PUBLIC_PORT=9445 \
bash tools/agent-smoke/run-live-smoke.sh
```

对应业务入口：

```bash
https://localhost:9445
```

## 常用日志命令

查看全部服务日志：

```bash
docker compose logs --tail=200
```

聚焦单个服务：

```bash
docker compose logs app --tail=200
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
cd server/frontend
npm install
npm run build
```

当前仓库要求前端必须能完成生产构建，否则 `docker compose` 不会成功。

### 3. `8080` 不通

优先检查：

- `docker compose ps` 中 `app` 是否已启动
- `docker compose logs app --tail=200` 是否有迁移或配置错误
- 本机是否已有其他进程占用 `8080`
- `.env` 中 `CA_KEY_ENCRYPTION_KEY` 与 `ADMIN_API_KEY` 是否有效

### 4. Agent API 返回 401/403

这是预期认证行为。除注册和审批状态轮询外，Agent API 需要有效 `X-Agent-Token`。

需要时可进入容器内进一步检查：

```bash
docker compose exec app alembic upgrade head
docker compose exec app python -m pytest tests/test_agent_api.py -q
```
