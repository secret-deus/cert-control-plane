# Cert Control Plane

TLS 证书生命周期管理系统，当前基线为 **外部证书分发模式**：控制平面集中管理外部证书与分配关系，Agent 负责注册、心跳、拉取更新并部署到 nginx 节点。

外部证书既支持直接粘贴 `PEM`，也支持上传第三方平台导出的 `zip` 压缩包。

## 架构概览

![架构概览](docs/architecture.png)

### 默认部署约定

| 端口 | 用途 | 认证方式 |
|------|------|---------|
| **8000** | 本地开发：Dashboard + Control API + Agent API | 路径级鉴权 |
| **8080** | Docker Compose 主机入口 | 路径级鉴权 |

- Control API 位于 `/api/control/*`，使用 `X-Admin-API-Key`
- Agent API 位于 `/api/agent/*`，使用 `X-Agent-Token`
- Agent 首次调用 `/api/agent/register` 完成 TOFU 注册；如果管理员提前预创建了同名槽位，这一步会绑定首次上报的指纹
- Agent 只有完成首次自注册并绑定指纹后，管理员才能审批并颁发 `agent_token`
- Agent 随后通过 `heartbeat + fetch-certs` 维持在线状态并拉取证书更新
- **HTTPS 支持**: 本系统默认以 HTTP 模式运行，可通过外部网关、负载均衡器或反向代理实现 HTTPS

## 技术栈

- **后端**: FastAPI + Pydantic v2 + async SQLAlchemy 2.0
- **数据库**: PostgreSQL (asyncpg 驱动)
- **迁移**: Alembic (async)
- **调度**: APScheduler (Rollout 批次推进)
- **加密**: cryptography (PEM 解析、Fernet 私钥加密存储)
- **Agent**: httpx + cryptography (运行在 nginx 节点)

## 快速开始

完整的 `docker compose` 启动、验证与排障步骤见 [docs/deployment-compose.md](/Users/xhang/Documents/github.com/cert-control-plane/docs/deployment-compose.md)。

### ⚡ 一键启动（推荐）

**Windows (PowerShell)：**
```powershell
.\startup.ps1
```

**Linux / macOS：**
```bash
bash start.sh
```

脚本会自动完成：检查依赖 → 生成 `.env` 密钥 → 启动后端 + 前端。启动后打开前端页面，输入 `.env` 文件中的 `ADMIN_API_KEY` 即可。

---

### Docker Compose 部署（推荐用于测试）

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入密钥（或脚本会自动生成）

# 2. 启动服务
docker compose up -d --build

# 3. 验证服务
curl http://localhost:8080/healthz
curl -i http://localhost:8080/api/agent/register
```

服务启动后：
- Dashboard：`http://localhost:8080/dashboard`
- Control API：`http://localhost:8080/api/control`
- API 文档：`http://localhost:8080/docs`
- 健康检查：`http://localhost:8080/healthz`
- Agent API：`http://localhost:8080/api/agent`

> **注意**: 默认以 HTTP 模式运行，如需 HTTPS，请在前面放置外部网关、负载均衡器或反向代理。

### 5. 访问 Web 仪表盘 (Dashboard)

本项目原生提供基于 React 的可视化仪表盘。

1. 进入前端目录并构建静态资源：
   ```bash
   cd server/frontend
   npm install
   npm run build
   ```
   > FastAPI 会自动服务 `frontend/dist` 目录。
2. 在浏览器中打开 `http://localhost:8080/dashboard`
3. 弹窗提示输入 `API Key`，请填入 `.env` 中的 `ADMIN_API_KEY` 以解锁面板。
4. 面板每 30 秒自动刷新，展示 Agent 状态、证书过期警告与操作审计。

### 4. 部署 Agent 到 nginx 节点

详见 [Agent 部署](#agent-部署) 章节。

## API 文档

启动服务后访问 `http://<host>/docs` (Swagger) 或 `http://<host>/redoc` (ReDoc)。生产环境如果接入外部 TLS，则使用对应的 `https://` 域名。

### Agent API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/agent/register` | Agent 首次注册，提交 `{name, fingerprint}` |
| GET | `/api/agent/register/status` | 轮询审批状态，审批通过后返回 `agent_token` |
| POST | `/api/agent/heartbeat` | 心跳上报 |
| POST | `/api/agent/fetch-certs` | 上报本地证书有效期并拉取更新 |

### Control API (Admin API Key)

**Agent 管理**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/control/agents` | 预创建 Agent 条目 |
| GET | `/api/control/agents` | Agent 列表 (分页) |
| GET | `/api/control/agents/{id}` | 查询单个 Agent |
| DELETE | `/api/control/agents/{id}` | 删除 Agent |
| POST | `/api/control/agents/{id}/approve` | 审批 Agent，颁发 `agent_token`（要求 Agent 已完成首次自注册） |
| POST | `/api/control/agents/{id}/reject` | 拒绝 Agent 注册 |

**外部证书管理**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/control/external-certs` | 上传外部证书 |
| GET | `/api/control/external-certs` | 外部证书列表 |
| GET | `/api/control/external-certs/{id}` | 外部证书详情 |

**分配管理**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/control/agents/{id}/assign-cert` | 为 Agent 的本地路径分配外部证书 |
| GET | `/api/control/agents/{id}/assignments` | 查看 Agent 分配关系 |
| DELETE | `/api/control/agents/{id}/assignments/{assignment_id}` | 删除分配关系 |

**Agent 证书记录**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/control/agents/{id}/certs` | Agent 证书历史 |
| GET | `/api/control/certs/{id}` | 查询单张证书 |

**Rollout 批量轮换**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/control/rollouts` | 创建 Rollout |
| GET | `/api/control/rollouts` | Rollout 列表 |
| GET | `/api/control/rollouts/{id}` | Rollout 详情 (含 Agent 执行状态) |
| POST | `/api/control/rollouts/{id}/start` | 启动 Rollout |
| POST | `/api/control/rollouts/{id}/pause` | 暂停 Rollout |
| POST | `/api/control/rollouts/{id}/resume` | 恢复 Rollout |
| POST | `/api/control/rollouts/{id}/rollback` | 回滚 Rollout |

**审计日志**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/control/audit` | 查询审计日志 (分页) |

**Dashboard**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/control/dashboard/summary` | 汇总统计 |
| GET | `/api/control/dashboard/agents-health` | Agent 在线状态 |
| GET | `/api/control/dashboard/certs-expiry` | Agent 证书到期列表 |
| GET | `/api/control/dashboard/external-certs-expiry` | 外部证书到期列表 |
| GET | `/api/control/dashboard/events` | 最近审计事件 |
| GET | `/api/control/dashboard/cert-alerts` | 证书告警概览 |

## 外部证书分发流程

```
运维人员                    控制面板                         Agent 节点
    │                         │                               │
    │  POST /control/agents   │                               │
    │  (预创建 Agent 条目)      │                               │
    ├────────────────────────►│                               │
    │                         │    POST /agent/register        │
    │                         │    (name + fingerprint)        │
    │                         │◄──────────────────────────────┤
    │                         │    绑定首次指纹（若为预创建槽位） │
    │                         │    ──► status=pending          │
    │                         │──────────────────────────────►│
    │                         │                               │
    │  POST /agents/{id}/approve                              │
    ├────────────────────────►│                               │
    │                         │    颁发 agent_token            │
    │                         │                               │
    │                         │    GET /agent/register/status  │
    │                         │◄──────────────────────────────┤
    │                         │    ──► agent_token             │
    │                         │──────────────────────────────►│
    │                         │                               │
    │  POST /external-certs   │                               │
    ├────────────────────────►│                               │
    │                         │                               │
    │  POST /agents/{id}/assign-cert                          │
    ├────────────────────────►│                               │
    │                         │                               │
    │                         │    POST /agent/heartbeat       │
    │                         │◄──────────────────────────────┤  (每30秒)
    │                         │    ──► acknowledged=true       │
    │                         │──────────────────────────────►│
    │                         │                               │
    │                         │    POST /agent/fetch-certs     │
    │                         │◄──────────────────────────────┤
    │                         │    对比 `current_not_after`    │
    │                         │    ──► cert_pem + key_pem      │
    │                         │──────────────────────────────►│
    │                         │                               │ 写入文件并 reload nginx
    │                         │    下一轮 fetch-certs 上报新有效期 │
    │                         │◄──────────────────────────────┤
    │                         │    写入证书台账 / 更新 rollout item │
    │                         │──────────────────────────────►│
```

### Rollout 批次推进

1. 创建 Rollout → 按 `batch_size` 将目标 Agent 分为多个批次
2. 启动 Rollout → 编排器标记第 1 批次的 items 为 `IN_PROGRESS`，只有当前批次 Agent 会收到证书更新
3. Agent 部署证书后，会在下一轮 `fetch-certs` 用新的 `current_not_after` 回报；控制平面据此写入证书台账
4. 当控制平面观察到该 Agent 的分配证书都已成为当前证书时，对应 `RolloutItem` 标记为 `COMPLETED`
5. 当前版本的 `RolloutItem` 仍是 `agent` 维度，不是 `agent + local_path + external_cert` 维度；更细粒度验收需要后续重构模型
6. 超时未完成的 item 自动标记为 `FAILED`（默认 10 分钟）

支持的操作：**暂停** / **恢复** / **回滚**（恢复到旧证书）

## Agent 部署

Agent 是一个独立的 Python 进程，运行在每个 nginx 节点上。

### ⚡ 一键安装（推荐）

**Linux (在 nginx 节点上)：**
```bash
# 交互式安装 — 脚本会提示输入控制面板地址和 Agent 名称
sudo bash agent/scripts/install.sh

# 或非交互式
sudo bash agent/scripts/install.sh \
  --cp-url https://cp.example.com \
  --name web-node-01
```

**Windows (管理员 PowerShell)：**
```powershell
.\agent\scripts\install.ps1

# 或非交互式
.\agent\scripts\install.ps1 -CpUrl "https://cp.example.com" -AgentName "web-node-01"
```

脚本会自动：检查依赖 → 安装代码 → 安装 Python 包 → 生成配置 → 注册系统服务。

### 手动安装

```bash
# 1. 复制 agent 代码
sudo mkdir -p /opt/cert-agent
sudo cp -r agent/ /opt/cert-agent/

# 2. 安装依赖
pip3 install httpx cryptography

# 3. 配置
sudo mkdir -p /etc/cert-agent
sudo cp agent/agent.env.example /etc/cert-agent/agent.env
sudo chmod 600 /etc/cert-agent/agent.env
# 编辑 /etc/cert-agent/agent.env

# 4. 如需信任自签名 TLS 证书，可额外安装 CA 证书
# sudo cp certs/ca.crt /etc/cert-agent/ca.crt

# 5. 安装 systemd 服务
sudo cp agent/cert-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cert-agent
```

### 配置项

| 环境变量 | 必填 | 默认值 | 说明 |
|---------|------|--------|------|
| `CERT_AGENT_CP_URL` | 是 | - | 控制面板地址 (如 `https://cp.example.com` 或 `http://localhost:8080`) |
| `CERT_AGENT_NAME` | 是 | - | Agent 名称 |
| `CERT_AGENT_TOKEN` | 否 | - | 已知 `agent_token` 时可直接写入，通常首次无需配置 |
| `CERT_AGENT_CERT_TABLE` | 否 | `[]` | 证书检查表，JSON 数组，元素含 `local_path` |
| `CERT_AGENT_STATE_DIR` | 否 | `/var/lib/cert-agent` | 本地状态目录 |
| `CERT_AGENT_NGINX_CERT_DIR` | 否 | `/etc/nginx/certs` | nginx 证书目录 |
| `CERT_AGENT_NGINX_RELOAD_CMD` | 否 | `nginx -s reload` | nginx 重载命令 |
| `CERT_AGENT_HEARTBEAT_INTERVAL` | 否 | `30` | 心跳间隔 (秒) |
| `CERT_AGENT_POLL_INTERVAL` | 否 | `5` | 审批轮询间隔 (秒) |

### Agent 容错机制

- **审批轮询**: 首次注册后会持续轮询审批状态，直到管理员通过
- **认证失败恢复**: `agent_token` 被拒绝时清空本地 token，并重新进入注册流程
- **部署回滚**: 写入证书或执行 nginx reload 失败时自动恢复旧文件
- **拉取重试**: 心跳或 `fetch-certs` 失败时在下一轮继续重试

### 管理命令

```bash
systemctl start cert-agent    # 启动
systemctl stop cert-agent     # 停止
systemctl status cert-agent   # 状态
journalctl -u cert-agent -f   # 实时日志
```

## 项目结构

```
cert-control-plane/
├── startup.ps1                 # ⚡ 一键启动 (Windows)
├── start.sh                    # ⚡ 一键启动 (Linux/macOS)
├── server/                     # 控制面：FastAPI + React 静态资源
│   ├── app/
│   │   ├── main.py             # FastAPI 入口、Dashboard、health/ready/metrics
│   │   ├── config.py           # 环境变量配置与生产护栏
│   │   ├── models.py           # ORM 模型
│   │   ├── schemas.py          # Pydantic 请求/响应 schema
│   │   ├── api/
│   │   │   ├── agent.py        # Agent API
│   │   │   ├── dashboard.py    # Dashboard API
│   │   │   └── control/        # Control API 拆分模块
│   │   ├── core/               # 加密、安全、审计、限流、metrics
│   │   ├── registry/           # 当前证书查询与撤销辅助
│   │   ├── services/           # 归档解析、Kubernetes Secret 执行器
│   │   └── orchestrator/       # Rollout 编排
│   ├── frontend/               # React Web Dashboard (Vite + TailwindCSS)
│   ├── tests/                  # 后端回归测试
│   ├── alembic/                # 数据库迁移 001..008
│   ├── Dockerfile              # 单端口生产镜像
│   └── pyproject.toml          # 控制面依赖
├── client/
│   ├── agent/                  # Python Agent
│   ├── agent-go/               # Go Agent，推荐生产优先验证
│   ├── agent-rust/             # Rust Agent，当前实验性
│   └── tests/                  # Python Agent 测试
├── k8s/minikube/               # 本地 minikube 部署清单
├── scripts/
│   ├── smoke-test.sh           # 生产镜像 smoke
│   ├── run-perf-test.sh        # 性能测试入口
│   └── minikube-*.sh           # minikube/K8s Secret 真实测试脚本
├── tools/                      # Agent smoke、真实 nginx 矩阵、Locust 性能测试
├── docs/                       # 部署、运维、安全、测试文档
├── specs/                      # 方案、投产评估、真实测试报告和截图
├── docker-compose.yml
└── PLAN.md
```

## 安全设计

- **鉴权分离**: Control API 使用 `X-Admin-API-Key`，Agent API 使用 `X-Agent-Token`
- **TOFU 注册**: Agent 首次只上报名称和公钥指纹，必须经管理员审批后才能进入正式通信
- **密钥加密存储**: 上传的外部证书私钥使用 Fernet 加密后存入数据库
- **路径与鉴权隔离**: Control API 与 Agent API 共用服务端口，但使用不同路径、不同认证头；生产环境应在外部网关限制来源
- **部署回滚**: Agent 覆盖本地证书文件前先备份，部署失败时自动恢复
- **审计日志**: 所有写操作写入 `audit_logs`
- **CORS 默认拒绝**: `cors_origins` 默认为空列表，必须显式配置

## 环境变量 (控制面板)

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `DATABASE_URL` | 否 | `postgresql+asyncpg://...` | 数据库连接 |
| `CA_KEY_ENCRYPTION_KEY` | 是 | - | Fernet 密钥 (加密存储私钥) |
| `ADMIN_API_KEY` | 是 | - | Control API 认证密钥 |
| `CORS_ORIGINS` | 否 | `[]` | CORS 允许的来源 (JSON 数组，如 `["https://example.com"]`) |
| `DEV_MODE` | 否 | `false` | 本地调试模式；非 SQLite 数据库禁止开启 |
| `ROLLOUT_INTERVAL_SECONDS` | 否 | `30` | 编排器轮询间隔 |
| `DEFAULT_BATCH_SIZE` | 否 | `10` | Rollout 默认批大小 |
| `ROLLOUT_ITEM_TIMEOUT_MINUTES` | 否 | `10` | Rollout item 超时时间 |
| `POSTGRES_PASSWORD` | Docker Compose 必填 | - | Docker PostgreSQL 密码，禁止使用默认弱口令 |
| `REDIS_URL` | 否 | - | 可选；配置后启用跨实例分布式限流 |

## 数据库迁移

```bash
# 全新部署
alembic upgrade head

# 从旧版 (serial BIGINT) 升级
# 002 迁移会自动检测 schema 状态：
#   - 已有 serial_hex → no-op
#   - 仅有 serial BIGINT → 添加 serial_hex + 回填 + 约束
alembic upgrade head
```

旧版数据库升级后验证：

```sql
-- 确认无空值
SELECT COUNT(*) FROM certificates WHERE serial_hex IS NULL;  -- 应返回 0

-- 确认无重复
SELECT serial_hex, COUNT(*) FROM certificates
GROUP BY serial_hex HAVING COUNT(*) > 1;  -- 应返回空
```

## 开发

```bash
# 安装依赖
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 启动数据库
cd ..
docker compose up -d db

# 运行迁移
cd server
alembic upgrade head

# 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 运行测试 (无需数据库)
pytest tests/ -v
```

如果要验证容器化部署链路，优先按 [docs/deployment-compose.md](docs/deployment-compose.md) 执行 `docker compose up -d --build`、`ps`、日志和健康检查。

### 前端开发 (Web Dashboard)

前端位于 `server/frontend/` 目录，采用 React + Vite + TailwindCSS。

```bash
cd server/frontend
npm install

# 启动带热重载的开发服务器 (默认 http://localhost:5173)
npm run dev
```

开发服务器会自动通过代理将 `/api/` 请求转发给运行在 `8000` 端口的本地 FastAPI 实例，见 `vite.config.ts`。
