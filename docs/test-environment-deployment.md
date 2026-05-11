# 测试环境部署检查清单

本文档用于把当前仓库版本部署到受控测试环境。目标是先验证真实控制面、真实 Agent、真实 nginx reload 和可选 Kubernetes Secret 链路，不使用 mock。

## 适用范围

- 控制面：Dashboard、Control API、Agent API 单端口服务。
- 数据库：PostgreSQL。
- Agent：Python Agent 或 Go Agent。
- Kubernetes Secret：可选，建议先在 minikube 或测试集群 namespace 内验证。
- Rust Agent：当前不建议作为测试环境主 Agent。

## 配置要求

`.env` 至少包含：

```bash
POSTGRES_PASSWORD=<strong-test-db-password>
DATABASE_URL=postgresql+asyncpg://postgres:<strong-test-db-password>@db:5432/certcp
CA_KEY_ENCRYPTION_KEY=<fernet-key>
ADMIN_API_KEY=<strong-admin-api-key>
CORS_ORIGINS=["http://<test-host>:8080"]
DEV_MODE=false
```

生成密钥：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

约束：

- `DEV_MODE` 必须为 `false`。
- `POSTGRES_PASSWORD`、`ADMIN_API_KEY`、`CA_KEY_ENCRYPTION_KEY` 不允许使用示例值。
- Agent 节点需要能访问控制面单端口地址，例如 `http://<control-plane>:8080`。
- 测试环境如果使用反向代理或负载均衡，只转发到应用端口即可，不需要额外 nginx 层。

## 控制面部署

```bash
docker compose pull || true
docker compose up -d --build db app
docker compose ps
```

健康检查：

```bash
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/readyz
curl -fsS http://127.0.0.1:8080/metrics
```

预期：

- `/healthz` 返回 `{"status":"ok"}`。
- `/readyz` 返回 `db=connected`。
- `/metrics` 包含 `certcp_up 1` 和 `certcp_db_up 1`。

## Agent 部署验证

Python Agent 或 Go Agent 均按同一流程验证：

1. Agent 首次启动，向 `/api/agent/register` 注册。
2. 管理端在 Dashboard 或 Control API 审批。
3. Agent 保存 `agent_token` 后开始 heartbeat。
4. 上传测试证书，并分配到 Agent 的真实 nginx 证书路径。
5. Agent 拉取证书，写入 cert/key/chain，执行 nginx reload。
6. 在 Agent 节点读取证书 serial，确认与控制面上传的 serial 一致。

Go Agent 已验证的真实 smoke 命令：

```bash
COMPOSE_PROJECT_NAME=certcp_go_smoke \
SMOKE_EDGE_OVERLAY=tools/agent-smoke/docker-compose.edge-go.yml \
SMOKE_PUBLIC_PORT=9445 \
bash tools/agent-smoke/run-live-smoke.sh
```

## Kubernetes Secret 验证

测试集群建议使用 namespace-scoped ServiceAccount，不使用 cluster-admin。

验证场景：

- 新证书创建新 TLS Secret。
- 新证书替换旧 TLS Secret。
- 已存在 Secret adopt 到平台管理。
- 最近一次成功部署前 snapshot 回滚。
- 更新 kubeconfig 后重新 validate。

当前 V1 边界：

- 不管理 workload。
- 不读取 Ingress/Gateway。
- 删除 assignment 不删除业务 Secret。
- 一个 assignment 对应一个 Secret。

## 上线测试前确认

- 当前代码已 commit，测试环境使用固定 commit 或镜像 tag。
- `.env` 不进入 git。
- Dashboard 可登录并访问 `/dashboard`。
- Dashboard API Key session 30 分钟无活动后会自动清除，需要重新登录。
- Agent 列表能看到真实节点 hostname/name、状态和最近心跳。
- 证书替换后，目标机器或目标 Secret 的 serial 与控制面 active cert 一致。
- 失败 reload 场景会回滚旧证书和旧私钥。
- 测试完成后导出 smoke 记录、关键截图和部署 serial。
