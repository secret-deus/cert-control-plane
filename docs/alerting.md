# 告警配置指南

本文档描述如何配置 Cert Control Plane 的监控和告警系统。

## 日志配置

### 结构化日志

Cert Control Plane 支持两种日志格式：

1. **JSON 格式** (推荐用于生产环境)
   ```bash
   export LOG_FORMAT=json
   export LOG_LEVEL=INFO
   ```

2. **文本格式** (推荐用于开发环境)
   ```bash
   export LOG_FORMAT=text
   export LOG_LEVEL=DEBUG
   ```

### 日志字段说明

JSON 格式日志包含以下字段：

| 字段 | 说明 | 示例 |
|------|------|------|
| timestamp | 时间戳 | 2026-04-08T10:30:00Z |
| level | 日志级别 | INFO, WARNING, ERROR |
| logger | 日志器名称 | app.orchestrator.rollout |
| message | 日志消息 | Rollout started |
| pathname | 源文件路径 | app/orchestrator/rollout.py |
| lineno | 行号 | 42 |

### 日志聚合

推荐使用以下工具进行日志聚合：

#### ELK Stack (Elasticsearch + Logstash + Kibana)

1. 配置 Filebeat 收集日志：
   ```yaml
   # /etc/filebeat/filebeat.yml
   filebeat.inputs:
   - type: log
     enabled: true
     paths:
       - /var/log/certcp/*.log
     json.keys_under_root: true
     json.add_error_key: true

   output.elasticsearch:
     hosts: ["localhost:9200"]
     index: "certcp-%{+yyyy.MM.dd}"
   ```

2. 在 Kibana 中创建索引模式：`certcp-*`

3. 创建仪表盘和可视化

#### Grafana Loki

1. 配置 Promtail 收集日志：
   ```yaml
   # promtail-config.yml
   server:
     http_listen_port: 9080

   positions:
     filename: /tmp/positions.yaml

   clients:
     - url: http://loki:3100/loki/api/v1/push

   scrape_configs:
   - job_name: certcp
     static_configs:
     - targets:
       - localhost
       labels:
         job: certcp
         __path__: /var/log/certcp/*.log
   ```

2. 在 Grafana 中添加 Loki 数据源

3. 使用 LogQL 查询日志：
   ```
   {job="certcp"} |= "error" | json
   ```

## 监控指标

### 关键指标

Cert Control Plane 提供以下监控端点：

#### Liveness

```bash
GET /healthz
```

响应示例：
```json
{
  "status": "ok"
}
```

#### Readiness

```bash
GET /readyz
```

响应示例：
```json
{
  "status": "ok",
  "db": "connected"
}
```

状态值：
- `ok`: 应用和数据库连接正常
- `degraded`: 服务降级（如数据库连接失败）

#### Prometheus 文本指标

```bash
GET /metrics
```

当前基础指标：
- `certcp_up`: 应用进程健康状态
- `certcp_db_up`: 数据库 readiness 状态
- `certcp_uptime_seconds`: 应用运行时长

#### Dashboard API

使用 Dashboard API 获取关键指标：

1. **Agent 健康**
   ```bash
   GET /api/control/dashboard/agents-health
   ```

2. **证书过期监控**
   ```bash
   GET /api/control/dashboard/cert-alerts
   ```

3. **外部证书过期**
   ```bash
   GET /api/control/dashboard/external-certs-expiry?days=30
   ```

### Prometheus 集成

Prometheus 可直接 scrape `/metrics`。当前端点提供基础进程和数据库状态指标；证书过期、Agent 在线数、Rollout pending 数等业务指标仍建议作为后续增强。

## 告警规则

### 基于 Dashboard API 的告警

可以创建脚本定期检查 API 并发送告警：

```python
#!/usr/bin/env python3
"""Alert script for Cert Control Plane"""

import os
import requests
from datetime import datetime, timedelta

CP_URL = os.getenv("CP_URL", "https://localhost:443")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Slack/Discord webhook

def send_alert(message: str, level: str = "warning"):
    """Send alert to webhook"""
    if not WEBHOOK_URL:
        print(f"[{level.upper()}] {message}")
        return

    payload = {
        "text": f"[{level.upper()}] Cert Control Plane Alert",
        "attachments": [{
            "color": "danger" if level == "critical" else "warning",
            "text": message,
            "ts": int(datetime.now().timestamp())
        }]
    }

    requests.post(WEBHOOK_URL, json=payload)

def check_cert_expiry():
    """Check for expiring certificates"""
    resp = requests.get(
        f"{CP_URL}/api/control/dashboard/cert-alerts",
        headers={"X-Admin-API-Key": ADMIN_API_KEY},
        verify=False
    )
    data = resp.json()

    # Check for critical alerts (expiring in < 7 days)
    critical_ext = data["external_certs"]["critical"]
    critical_agent = data["agent_certs"]["critical"]

    if critical_ext or critical_agent:
        msg = f"CRITICAL: {len(critical_ext)} external certs and {len(critical_agent)} agent certs expiring within 7 days"
        send_alert(msg, "critical")

    # Check for expired certs
    expired_ext = data["external_certs"]["expired"]
    expired_agent = data["agent_certs"]["expired"]

    if expired_ext or expired_agent:
        msg = f"EXPIRED: {len(expired_ext)} external certs and {len(expired_agent)} agent certs have expired"
        send_alert(msg, "critical")

def check_agent_health():
    """Check for offline agents"""
    resp = requests.get(
        f"{CP_URL}/api/control/dashboard/agents-health",
        headers={"X-Admin-API-Key": ADMIN_API_KEY},
        verify=False
    )
    agents = resp.json()

    offline = [a for a in agents if a["liveness"] == "offline"]
    if offline:
        names = ", ".join(a["name"] for a in offline[:5])
        msg = f"WARNING: {len(offline)} agents offline: {names}"
        send_alert(msg, "warning")

if __name__ == "__main__":
    check_cert_expiry()
    check_agent_health()
```

### Cron 定时任务

配置 cron 每 5 分钟检查一次：

```bash
*/5 * * * * /usr/local/bin/certcp-alerts.py >> /var/log/certcp-alerts.log 2>&1
```

## 告警渠道

### Slack 集成

1. 创建 Slack Incoming Webhook
2. 设置环境变量：
   ```bash
   export WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
   ```

### 邮件告警

使用邮件告警脚本：

```python
import smtplib
from email.mime.text import MIMEText

def send_email_alert(subject: str, body: str):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = "alerts@example.com"
    msg["To"] = "ops-team@example.com"

    with smtplib.SMTP("smtp.example.com", 587) as server:
        server.starttls()
        server.login("user", "password")
        server.send_message(msg)
```

### PagerDuty 集成

对于关键告警，可以集成 PagerDuty：

```python
import requests

def trigger_pagerduty(summary: str, severity: str = "warning"):
    payload = {
        "routing_key": os.getenv("PAGERDUTY_KEY"),
        "event_action": "trigger",
        "dedup_key": "certcp-alert",
        "payload": {
            "summary": summary,
            "severity": severity,
            "source": "cert-control-plane",
            "timestamp": datetime.now().isoformat(),
        }
    }

    requests.post(
        "https://events.pagerduty.com/v2/enqueue",
        json=payload
    )
```

## 最佳实践

### 1. 分级告警

- **P1 Critical**: 证书已过期或即将在 24 小时内过期
- **P2 Warning**: 证书将在 7 天内过期，Agent 离线
- **P3 Notice**: 证书将在 30 天内过期

### 2. 告警抑制

避免重复告警，记录已发送的告警：

```python
import hashlib
from datetime import datetime, timedelta

alert_cache = {}

def should_send_alert(alert_key: str, ttl_hours: int = 4) -> bool:
    """Check if alert should be sent (avoid spamming)"""
    key_hash = hashlib.md5(alert_key.encode()).hexdigest()
    now = datetime.now()

    if key_hash in alert_cache:
        last_sent = alert_cache[key_hash]
        if now - last_sent < timedelta(hours=ttl_hours):
            return False

    alert_cache[key_hash] = now
    return True
```

### 3. 告警聚合

合并相关告警，减少噪音：

```python
def check_all_and_alert():
    alerts = []

    # Collect all issues
    if has_expired_certs():
        alerts.append("Expired certificates detected")

    if has_offline_agents():
        alerts.append("Agents offline")

    # Send aggregated alert
    if alerts:
        send_alert("\n".join(alerts), "warning")
```

## 监控仪表盘

### Grafana Dashboard

导入以下 JSON 创建 Grafana 仪表盘：

```json
{
  "dashboard": {
    "title": "Cert Control Plane",
    "panels": [
      {
        "title": "Agent Status",
        "type": "stat",
        "targets": [
          {
            "expr": "certcp_agents_active"
          }
        ]
      },
      {
        "title": "Certificates Expiring Soon",
        "type": "gauge",
        "targets": [
          {
            "expr": "certcp_certs_expiring_30d"
          }
        ]
      }
    ]
  }
}
```

## 故障恢复

### 告警响应流程

1. **收到告警** -> 检查告警级别
2. **P1 Critical** -> 立即响应，30 分钟内处理
3. **P2 Warning** -> 当个工作日处理
4. **P3 Notice** -> 安排计划处理

### 常见问题处理

#### 证书即将过期

```bash
# 1. 上传新证书
curl -X POST https://cp.example.com/api/control/external-certs \
  -H "X-Admin-API-Key: $KEY" \
  -F "cert_file=@new.crt" \
  -F "key_file=@new.key"

# 2. 创建 Rollout 推送
curl -X POST https://cp.example.com/api/control/rollouts \
  -H "X-Admin-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "Emergency cert rotation", "batch_size": 10}'

# 3. 启动 Rollout
curl -X POST https://cp.example.com/api/control/rollouts/{id}/start \
  -H "X-Admin-API-Key: $KEY"
```

#### Agent 离线

```bash
# 1. 检查 Agent 服务状态
ssh agent-node systemctl status cert-agent

# 2. 检查网络连通性
curl -k https://cp.example.com:8443/healthz

# 3. 重启 Agent
ssh agent-node systemctl restart cert-agent
```

## 总结

Cert Control Plane 的监控和告警系统设计为：

1. **结构化日志**: 支持日志聚合和分析
2. **Dashboard API**: 提供关键指标查询
3. **灵活告警**: 支持多种告警渠道和集成
4. **分级响应**: 根据严重程度采取不同响应措施

建议根据实际需求选择合适的监控工具和告警策略。
