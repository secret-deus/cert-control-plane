# Cert Control Plane

TLS 证书生命周期管理系统 —— 控制面板 + nginx 节点 Agent。

## 架构概览

```
                    ┌─────────────────────────────────────────┐
                    │           Control Plane Server           │
                    │                                         │
                    │  ┌─────────┐  ┌──────────┐  ┌────────┐ │
                    │  │ FastAPI │  │Orchestrator│ │Registry│ │
                    │  │  (API)  │  │(APScheduler)│ │ (DB)  │ │
                    │  └────┬────┘  └─────┬─────┘  └───┬────┘ │
                    │       └──────┬──────┘            │      │
                    │              │                    │      │
                    │         ┌────┴────┐         ┌────┴────┐ │
                    │         │  nginx  │         │Postgres │ │
                    │         │ (mTLS)  │         │         │ │
                    │         └──┬───┬──┘         └─────────┘ │
                    └────────────┼───┼─────────────────────────┘
                        :443     │   │  :8443
                   (Control API) │   │  (Agent API, mTLS)
                                 │   │
             ┌───────────────────┘   └────────────────────┐
             │                                            │
     ┌───────┴────────┐                          ┌────────┴───────┐
     │  运维平台/API   │                          │  nginx 节点     │
     │  X-Admin-API-Key│                          │  cert-agent    │
     └────────────────┘                          └────────────────┘
```

### 双端口隔离

| 端口 | 用途 | 认证方式 |
|------|------|---------|
| **443** | Control API (运维管理) | `X-Admin-API-Key` 请求头 |
| **8443** | Agent API (节点通信) | mTLS 客户端证书 |

- 443 端口**禁止**访问 Agent API（nginx 直接返回 403）
- 8443 端口强制 mTLS，`/register` 除外（bootstrap 阶段无证书）
- 证书 bundle 仅通过 8443 mTLS 端口下载，运维侧无私钥暴露

## 技术栈

- **后端**: FastAPI + Pydantic v2 + async SQLAlchemy 2.0
- **数据库**: PostgreSQL (asyncpg 驱动)
- **迁移**: Alembic (async)
- **调度**: APScheduler (Rollout 批次推进)
- **加密**: cryptography (CA 签发、CSR 验证、Fernet 密钥加密)
- **代理**: nginx (mTLS 反向代理)
- **Agent**: httpx + cryptography (运行在 nginx 节点)

## 快速开始

### 1. 生成 CA 和服务端证书

```bash
pip install cryptography
python scripts/init_ca.py --out-dir ./certs
```

生成文件：
- `certs/ca.key` — CA 私钥（妥善保管）
- `certs/ca.crt` — CA 证书（分发给所有 Agent 节点）
- `certs/server.key` — 服务端 TLS 私钥
- `certs/server.crt` — 服务端 TLS 证书

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 并填入：

```bash
# 必填：生成 Fernet 密钥
CA_KEY_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# 必填：生成 Admin API Key
ADMIN_API_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
```

### 3. 启动服务

```bash
docker-compose up -d
```

服务启动后：
- 控制 API：`https://localhost:443`
- API 文档：`https://localhost:443/docs`
- 健康检查：`https://localhost:443/healthz`
- Agent API：`https://localhost:8443`（需 mTLS）

### 4. 部署 Agent 到 nginx 节点

详见 [Agent 部署](#agent-部署) 章节。

## API 文档

启动服务后访问 `https://<host>/docs` (Swagger) 或 `https://<host>/redoc` (ReDoc)。

### Agent API (端口 8443, mTLS)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/agent/register` | Agent 首次注册（bootstrap token + CSR） |
| GET | `/api/agent/bundle` | 下载证书 Bundle (PEM) |
| POST | `/api/agent/renew` | 证书续期（提交新 CSR） |
| POST | `/api/agent/heartbeat` | 心跳上报 + 查询待执行操作 |

### Control API (端口 443, Admin API Key)

**Agent 管理**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/control/agents` | 预注册 Agent (返回 bootstrap_token) |
| GET | `/api/control/agents` | Agent 列表 (分页) |
| GET | `/api/control/agents/{id}` | 查询单个 Agent |
| DELETE | `/api/control/agents/{id}` | 删除 Agent |
| POST | `/api/control/agents/{id}/reset-token` | 重置 Bootstrap Token (用于重新注册) |

**证书管理**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/control/agents/{id}/certs` | Agent 证书历史 |
| GET | `/api/control/certs/{id}` | 查询单张证书 |
| POST | `/api/control/certs/{id}/revoke` | 撤销证书 |

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

## 证书续期流程 (CSR 模式)

私钥始终在 Agent 节点本地生成，**永远不离开节点**。

```
运维人员                    控制面板                         Agent 节点
    │                         │                               │
    │  POST /control/agents   │                               │
    │  (预注册, 获取 token)    │                               │
    ├────────────────────────►│                               │
    │  ◄── bootstrap_token    │                               │
    │                         │                               │
    │  (把 token 配置到节点)    │                               │
    │─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─►│
    │                         │    POST /agent/register        │
    │                         │    (token + CSR)               │
    │                         │◄──────────────────────────────┤
    │                         │    ──► cert_pem + chain_pem    │
    │                         │──────────────────────────────►│
    │                         │                               │ 部署到 nginx
    │                         │                               │
    │                         │    POST /agent/heartbeat       │
    │                         │◄──────────────────────────────┤  (每30秒)
    │                         │    ──► pending_action: null     │
    │                         │──────────────────────────────►│
    │                         │                               │
    │  POST /rollouts (创建)   │                               │
    │  POST /rollouts/{id}/start                              │
    ├────────────────────────►│                               │
    │                         │  Orchestrator tick:            │
    │                         │  items → IN_PROGRESS           │
    │                         │                               │
    │                         │    POST /agent/heartbeat       │
    │                         │◄──────────────────────────────┤
    │                         │    ──► pending_action: "renew"  │
    │                         │──────────────────────────────►│
    │                         │                               │ 生成新密钥+CSR
    │                         │    POST /agent/renew           │
    │                         │    (新 CSR)                    │
    │                         │◄──────────────────────────────┤
    │                         │  签发新证书                     │
    │                         │  item → COMPLETED              │
    │                         │    ──► new cert_pem            │
    │                         │──────────────────────────────►│
    │                         │                               │ 部署新证书到 nginx
```

### Rollout 批次推进

1. 创建 Rollout → 按 `batch_size` 将目标 Agent 分为多个批次
2. 启动 Rollout → 编排器标记第 1 批次的 items 为 `IN_PROGRESS`
3. Agent 心跳发现 `pending_action=renew` → 提交新 CSR → 获取新证书 → 部署
4. `/renew` 端点自动将 rollout_item 标记为 `COMPLETED`
5. 编排器检测到当前批次**全部完成**后，推进下一批次
6. 超时未完成的 item 自动标记为 `FAILED`（默认 10 分钟）

支持的操作：**暂停** / **恢复** / **回滚**（恢复到旧证书）

## Agent 部署

Agent 是一个独立的 Python 进程，运行在每个 nginx 节点上。

### 安装

```bash
# 在 nginx 节点上
sudo bash agent/scripts/install.sh
```

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

# 4. 复制 CA 证书
sudo cp certs/ca.crt /etc/cert-agent/ca.crt

# 5. 安装 systemd 服务
sudo cp agent/cert-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cert-agent
```

### 配置项

| 环境变量 | 必填 | 默认值 | 说明 |
|---------|------|--------|------|
| `CERT_AGENT_CP_URL` | 是 | - | 控制面板地址 (如 `https://cp.example.com:8443`) |
| `CERT_AGENT_CA_CERT` | 是 | - | CA 证书路径 |
| `CERT_AGENT_NAME` | 是 | - | Agent 名称 (须与控制面板预注册名称一致) |
| `CERT_AGENT_BOOTSTRAP_TOKEN` | 首次 | - | 一次性注册令牌 |
| `CERT_AGENT_STATE_DIR` | 否 | `/var/lib/cert-agent` | 本地状态目录 |
| `CERT_AGENT_NGINX_CERT_DIR` | 否 | `/etc/nginx/certs` | nginx 证书目录 |
| `CERT_AGENT_NGINX_RELOAD_CMD` | 否 | `nginx -s reload` | nginx 重载命令 |
| `CERT_AGENT_HEARTBEAT_INTERVAL` | 否 | `30` | 心跳间隔 (秒) |
| `CERT_AGENT_RENEW_BEFORE_DAYS` | 否 | `7` | 过期前 N 天主动续期 |
| `CERT_AGENT_MAX_AUTH_FAILURES` | 否 | `3` | 连续认证失败 N 次后尝试重新注册 |

### Agent 容错机制

- **本地过期检测**: 每次心跳前检查证书有效期，过期前 7 天（可配置）自动续期，不依赖控制面板指令
- **mTLS 失败恢复**: 连续认证失败超过阈值后自动尝试重新注册；若无 bootstrap token 则输出操作指引日志
- **续期回滚**: 续期失败时自动恢复旧证书和密钥

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
├── app/                        # 控制面板后端
│   ├── main.py                 # FastAPI 入口 + lifespan
│   ├── config.py               # 环境变量配置 (pydantic-settings)
│   ├── database.py             # async SQLAlchemy 引擎 + session
│   ├── models.py               # ORM 模型 (Agent/Certificate/Rollout/AuditLog)
│   ├── schemas.py              # Pydantic 请求/响应 schema
│   ├── api/
│   │   ├── agent.py            # Agent API (register/bundle/renew/heartbeat)
│   │   └── control.py          # Control API (agents/certs/rollouts/audit)
│   ├── core/
│   │   ├── crypto.py           # CA 加载、CSR 签发、Fernet 加解密
│   │   ├── security.py         # Admin API Key 校验、bootstrap token 生成
│   │   └── audit.py            # 审计日志写入
│   ├── registry/
│   │   └── store.py            # 证书 CRUD (issue_from_csr/revoke/build_bundle)
│   └── orchestrator/
│       └── rollout.py          # Rollout 编排 (批次推进/暂停/恢复/回滚)
├── agent/                      # nginx 节点 Agent (独立部署)
│   ├── __main__.py             # 入口 (python -m agent)
│   ├── config.py               # Agent 配置 (环境变量)
│   ├── crypto.py               # 密钥生成 + CSR 构建
│   ├── client.py               # httpx mTLS 客户端
│   ├── runner.py               # 主循环 (注册/心跳/续期/容错)
│   ├── deployer.py             # 证书部署到 nginx + reload
│   ├── pyproject.toml          # Agent 独立包定义
│   ├── cert-agent.service      # systemd 服务文件
│   ├── agent.env.example       # 环境变量模板
│   └── scripts/
│       └── install.sh          # 安装脚本
├── alembic/                    # 数据库迁移
│   ├── env.py
│   └── versions/
│       └── 001_initial.py
├── nginx/
│   └── nginx.conf              # 双端口 mTLS 配置
├── scripts/
│   └── init_ca.py              # CA + 服务端证书生成工具
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml              # 控制面板依赖
├── alembic.ini
└── .env.example
```

## 安全设计

- **私钥不出节点**: CSR 模式下，Agent 在本地生成 RSA 私钥，只提交 CSR 给控制面板
- **mTLS 双向认证**: Agent API 端口 (8443) 强制验证客户端证书
- **端口隔离**: 443 端口无法访问 Agent 端点，防止运维侧绕过 mTLS 下载 bundle
- **证书序列号绑定**: Agent 认证不仅检查 CN，还校验证书序列号与 DB 中的当前证书匹配
- **运行时吊销**: 吊销后的证书立即被拒绝，不仅是 DB 标记
- **Header 防伪**: 443 端口主动清除 `X-Client-CN` / `X-Client-Serial` / `X-Client-Verified` 头
- **Bootstrap Token**: 一次性使用，注册后立即作废；支持过期时间（默认 24 小时）
- **密钥加密存储**: 服务端生成的私钥使用 Fernet 加密后存入数据库
- **systemd 加固**: `NoNewPrivileges=true`, `ProtectSystem=strict`, `ProtectHome=true`
- **审计日志**: 所有写操作记录到 `audit_logs` 表，不可修改

## 环境变量 (控制面板)

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `DATABASE_URL` | 否 | `postgresql+asyncpg://...` | 数据库连接 |
| `CA_KEY_ENCRYPTION_KEY` | 是 | - | Fernet 密钥 (加密存储私钥) |
| `ADMIN_API_KEY` | 是 | - | Control API 认证密钥 |
| `CA_CERT_PATH` | 否 | `/certs/ca.crt` | CA 证书路径 |
| `CA_KEY_PATH` | 否 | `/certs/ca.key` | CA 私钥路径 |
| `CERT_VALIDITY_DAYS` | 否 | `365` | 签发证书有效期 (天) |
| `BOOTSTRAP_TOKEN_EXPIRE_HOURS` | 否 | `24` | Bootstrap token 过期时间 |
| `STRICT_CA_STARTUP` | 否 | `true` | CA 缺失时是否中断启动 (dev 可设 false) |
| `ROLLOUT_INTERVAL_SECONDS` | 否 | `30` | 编排器轮询间隔 |
| `ROLLOUT_ITEM_TIMEOUT_MINUTES` | 否 | `10` | Rollout item 超时时间 |

## 开发

```bash
# 安装依赖
pip install -e ".[dev]"

# 启动数据库
docker-compose up -d db

# 运行迁移
alembic upgrade head

# 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
