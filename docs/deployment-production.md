# 生产环境部署指南

本文档提供 Cert Control Plane 的生产环境部署建议、配置要点和运维手册。

## 架构建议

### 推荐部署架构

```
                    ┌─────────────────┐
                    │   Load Balancer │
                    │   (HTTPS 443)   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────▼──────┐ ┌────▼─────┐ ┌──────▼─────┐
        │  Nginx #1  │ │ Nginx #2 │ │   Nginx #N │
        │  (Port 443)│ │(Port 443)│ │ (Port 443) │
        └─────┬──────┘ └────┬─────┘ └──────┬─────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────▼────────┐
                    │   Control Plane │
                    │   (FastAPI)     │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   PostgreSQL    │
                    │   (Primary)     │
                    └─────────────────┘

Agent Nodes (独立部署):
  ┌─────────────┐  ┌─────────────┐
  │  Agent #1   │  │  Agent #N   │
  │  (nginx)    │  │  (nginx)    │
  └─────────────┘  └─────────────┘
        │                │
        └────────┬───────┘
                 │
        Agent API (Port 8443)
                 │
        ┌────────▼────────┐
        │  Control Plane  │
        └─────────────────┘
```

### 关键设计决策

1. **端口隔离**: Control API (443) 与 Agent API (8443) 物理隔离，降低攻击面
2. **数据库高可用**: PostgreSQL 配置流复制或使用托管服务 (RDS/Cloud SQL)
3. **证书存储**: 控制平面加密存储私钥 (Fernet)，Agent 本地明文存储
4. **Agent 认证**: 基于 `agent_token`，不依赖 mTLS，降低运维复杂度

## 环境准备

### 系统要求

| 组件 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 2 核 | 4 核 |
| 内存 | 4 GB | 8 GB |
| 磁盘 | 20 GB SSD | 50 GB SSD |
| 数据库 | PostgreSQL 14+ | PostgreSQL 15+ |

### 依赖软件

- Docker 24.0+ 和 Docker Compose Plugin
- 或 Python 3.11+ 和 PostgreSQL 14+
- Nginx 1.24+ (用于端口隔离和 TLS 终止)

### 网络要求

| 端口 | 来源 | 用途 |
|------|------|------|
| 443/TCP | 运维网络、办公网络 | Control API、Dashboard |
| 8443/TCP | Agent 节点网络 | Agent API |
| 5432/TCP | 应用服务器 | PostgreSQL (仅内网) |

## 配置清单

### 必需环境变量

```bash
# 数据库连接 (生产环境必须使用 PostgreSQL)
DATABASE_URL=postgresql+asyncpg://user:pass@db-host:5432/certcp

# Fernet 密钥 (用于加密存储私钥)
# 生成方式: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
CA_KEY_ENCRYPTION_KEY=your-fernet-key-here

# Admin API Key (用于 Dashboard 和运维 API 认证)
# 生成方式: python -c "import secrets; print(secrets.token_hex(32))"
ADMIN_API_KEY=your-admin-api-key-here

# 服务基础 URL (用于生成 Agent 配置)
BASE_URL=https://cp.example.com
```

### 可选环境变量

```bash
# Rollout 超时配置
ROLLOUT_ITEM_TIMEOUT_MINUTES=60

# 日志级别
LOG_LEVEL=INFO

# CORS 配置 (如果前端单独部署)
CORS_ORIGINS=https://dashboard.example.com
```

### 数据库配置 (PostgreSQL)

推荐配置 (`postgresql.conf`):

```ini
# 连接池
max_connections = 200

# 性能调优
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200

# 日志
log_min_duration_statement = 1000
log_line_prefix = '%t [%p] '
```

## 部署步骤

### 方案一: Docker Compose (推荐用于测试和小规模部署)

1. **准备配置文件**

```bash
# 克隆仓库
git clone https://github.com/your-org/cert-control-plane.git
cd cert-control-plane

# 生成配置
cp .env.example .env
# 编辑 .env 填入生产配置
```

2. **准备 TLS 证书**

```bash
# 使用内部 CA 或 Let's Encrypt
# 将证书放在 certs/ 目录
cp /path/to/server.crt certs/
cp /path/to/server.key certs/
```

3. **启动服务**

```bash
docker compose up -d

# 验证服务状态
docker compose ps
curl -k https://localhost:443/healthz
```

4. **数据库迁移**

```bash
docker compose exec app alembic upgrade head
```

### 方案二: 独立部署 (推荐用于生产环境)

1. **部署 PostgreSQL**

```bash
# 使用托管服务或独立部署
# 创建数据库和用户
CREATE DATABASE certcp;
CREATE USER certcp WITH ENCRYPTED PASSWORD 'your-password';
GRANT ALL PRIVILEGES ON DATABASE certcp TO certcp;
```

2. **部署应用**

```bash
# 安装依赖
pip install -e ".[dev]"

# 配置环境变量
export DATABASE_URL="postgresql+asyncpg://certcp:password@db-host:5432/certcp"
export CA_KEY_ENCRYPTION_KEY="your-fernet-key"
export ADMIN_API_KEY="your-admin-api-key"

# 数据库迁移
alembic upgrade head

# 启动服务 (使用 systemd 或 supervisor)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

3. **配置 Nginx 反向代理**

参考 `nginx/nginx.conf`，关键配置:

```nginx
# Control API (443)
server {
    listen 443 ssl;
    server_name cp.example.com;

    ssl_certificate /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

# Agent API (8443)
server {
    listen 8443 ssl;
    server_name agent.example.com;

    ssl_certificate /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;

    location /api/agent/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Agent 部署

### 下载和安装

```bash
# 下载 Agent 二进制 (从 GitHub Releases 或自行构建)
wget https://github.com/your-org/cert-control-plane/releases/latest/download/cert-agent-linux-amd64
chmod +x cert-agent
sudo mv cert-agent /usr/local/bin/
```

### 配置 Agent

创建配置文件 `/etc/cert-agent/agent.toml`:

```toml
cp_url = "https://cp.example.com:8443"
name = "web-server-01"
state_dir = "/var/lib/cert-agent"
heartbeat_interval = 30
poll_interval = 5
reload_cmd = "nginx -s reload"

[[cert_table]]
local_path = "/etc/nginx/ssl/api.example.com.crt"
cert_name = "api.example.com"

[[cert_table]]
local_path = "/etc/nginx/ssl/static.example.com.crt"
cert_name = "static.example.com"
```

### 创建 systemd 服务

创建 `/etc/systemd/system/cert-agent.service`:

```ini
[Unit]
Description=Cert Control Plane Agent
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/cert-agent
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启动服务:

```bash
sudo systemctl daemon-reload
sudo systemctl enable cert-agent
sudo systemctl start cert-agent
```

### 首次注册

Agent 首次启动时会自动发起 TOFU 注册:

```bash
# 查看 Agent 日志
sudo journalctl -u cert-agent -f

# 看到类似输出:
# INFO cert-agent: Sending TOFU registration request
# INFO cert-agent: Registration pending – waiting for admin approval
```

运维人员需要在 Dashboard 中审批该 Agent，审批后 Agent 会自动获得 `agent_token` 并开始正常工作。

## 运维手册

### 日常运维任务

#### 1. 上传外部证书

```bash
# 方式一: 通过 API
curl -k -X POST https://cp.example.com/api/control/external-certs \
  -H "X-Admin-API-Key: your-key" \
  -F "cert_file=@/path/to/cert.pem" \
  -F "key_file=@/path/to/key.pem" \
  -F "name=api.example.com"

# 方式二: 通过 Dashboard
# 打开 https://cp.example.com/dashboard
# 进入 "外部证书" -> "上传证书"
```

#### 2. 分配证书到 Agent

```bash
# 通过 API
curl -k -X POST https://cp.example.com/api/control/agents/{agent-id}/assign-cert \
  -H "X-Admin-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "local_path": "/etc/nginx/ssl/api.example.com.crt",
    "external_cert_id": "cert-uuid"
  }'
```

#### 3. 批量证书轮换 (Rollout)

```bash
# 创建 Rollout
curl -k -X POST https://cp.example.com/api/control/rollouts \
  -H "X-Admin-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Q2 证书轮换",
    "description": "更新所有生产证书",
    "batch_size": 5,
    "target_filter": {}
  }'

# 启动 Rollout
curl -k -X POST https://cp.example.com/api/control/rollouts/{rollout-id}/start \
  -H "X-Admin-API-Key: your-key"

# 暂停 Rollout
curl -k -X POST https://cp.example.com/api/control/rollouts/{rollout-id}/pause \
  -H "X-Admin-API-Key: your-key"

# 恢复 Rollout
curl -k -X POST https://cp.example.com/api/control/rollouts/{rollout-id}/resume \
  -H "X-Admin-API-Key: your-key"
```

### 监控和告警

#### 关键指标

| 指标 | 说明 | 告警阈值 |
|------|------|---------|
| Agent 心跳延迟 | Agent 最后心跳时间 | > 5 分钟 |
| 证书即将过期 | 距离过期天数 | < 30 天 |
| Rollout 失败 | 批次中失败项数量 | > 0 |
| 数据库连接数 | 当前连接数 | > 80% max_connections |

#### Dashboard 告警视图

Dashboard 自动显示:
- 最近 30 天即将过期的证书
- 心跳异常的 Agent
- 失败的 Rollout 任务

### 故障排查

#### Agent 无法注册

1. 检查网络连通性:
```bash
curl -k https://cp.example.com:8443/healthz
```

2. 检查 Agent 日志:
```bash
sudo journalctl -u cert-agent -n 100
```

3. 确认 Agent 指纹已在控制平面注册:
```bash
# 在 Dashboard 中检查 "待审批" 列表
```

#### Agent 无法拉取证书

1. 检查分配关系:
```bash
curl -k https://cp.example.com/api/control/agents/{agent-id}/assignments \
  -H "X-Admin-API-Key: your-key"
```

2. 检查本地路径权限:
```bash
ls -la /etc/nginx/ssl/
```

3. 手动触发心跳:
```bash
curl -k -X POST https://cp.example.com:8443/api/agent/heartbeat \
  -H "X-Agent-Token: your-agent-token"
```

#### Rollout 卡住

1. 检查 Rollout 状态:
```bash
curl -k https://cp.example.com/api/control/rollouts/{rollout-id} \
  -H "X-Admin-API-Key: your-key"
```

2. 检查超时配置:
```bash
# 默认超时 60 分钟
# 可以在 .env 中调整 ROLLOUT_ITEM_TIMEOUT_MINUTES
```

3. 手动回滚:
```bash
curl -k -X POST https://cp.example.com/api/control/rollouts/{rollout-id}/rollback \
  -H "X-Admin-API-Key: your-key"
```

### 备份和恢复

#### 数据库备份

```bash
# 全量备份
pg_dump -h db-host -U certcp certcp > certcp_backup_$(date +%Y%m%d).sql

# 定时备份 (crontab)
0 2 * * * pg_dump -h db-host -U certcp certcp | gzip > /backup/certcp_$(date +\%Y\%m\%d).sql.gz
```

#### 数据恢复

```bash
# 恢复数据库
psql -h db-host -U certcp certcp < certcp_backup_20260408.sql
```

#### 密钥备份

关键密钥需要安全备份:
- `CA_KEY_ENCRYPTION_KEY` - Fernet 密钥
- `ADMIN_API_KEY` - Admin API Key
- TLS 服务器证书和私钥

### 升级指南

#### 滚动升级步骤

1. **备份数据库**
```bash
pg_dump -h db-host -U certcp certcp > backup_before_upgrade.sql
```

2. **拉取新版本**
```bash
git pull origin main
```

3. **运行数据库迁移**
```bash
alembic upgrade head
```

4. **重启服务**
```bash
# Docker Compose 方式
docker compose up -d --build

# systemd 方式
sudo systemctl restart cert-agent
```

5. **验证功能**
```bash
curl -k https://cp.example.com/healthz
python3 -m pytest tests/ -q
```

## 安全最佳实践

### 网络安全

1. **最小权限原则**: Agent API 仅对 Agent 节点开放，Control API 仅对运维网络开放
2. **TLS 配置**: 使用 TLS 1.3，禁用弱密码套件
3. **防火墙规则**: 严格限制 8443 端口的访问来源 IP

### 密钥管理

1. **Fernet 密钥**: 定期轮换 (建议每年)，使用 HSM 或密钥管理服务存储
2. **Admin API Key**: 使用强随机数生成，定期轮换
3. **Agent Token**: 每个 Agent 独立，可单独撤销

### 审计和日志

1. **审计日志**: 所有写操作自动记录到 `audit_logs` 表，不可篡改
2. **访问日志**: Nginx 和应用日志集中收集，保留至少 90 天
3. **告警集成**: 对异常登录、证书操作发送告警通知

## 性能调优

### 数据库优化

```sql
-- 创建关键索引 (通常由迁移自动创建)
CREATE INDEX idx_agent_status ON agents(status);
CREATE INDEX idx_certificate_agent_id ON certificates(agent_id);
CREATE INDEX idx_rollout_status ON rollouts(status);
```

### 应用层优化

1. **连接池**: 使用 asyncpg 连接池，默认配置通常足够
2. **批量操作**: Rollout 批次大小建议 5-20，避免过大批次
3. **缓存**: Dashboard 数据可以添加 Redis 缓存 (可选)

## 联系和支持

- GitHub Issues: https://github.com/your-org/cert-control-plane/issues
- 文档: https://github.com/your-org/cert-control-plane/tree/main/docs
