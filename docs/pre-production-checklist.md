# 预生产环境部署检查清单

本文档提供预生产环境部署前的完整检查清单，确保系统已准备好进入生产环境。

## 📋 部署前检查

### 1. 代码质量检查

#### 测试覆盖
- [ ] 所有单元测试通过
  ```bash
  python3 -m pytest tests/ -v --tb=short
  ```
- [ ] 代码覆盖率 > 80%
  ```bash
  python3 -m pytest tests/ --cov=app --cov-report=html
  ```
- [ ] 无测试 warnings
- [ ] E2E 测试通过（如已配置）

#### 代码审查
- [ ] 所有 PR 已审查并合并
- [ ] 无已知的 critical 或 high severity issues
- [ ] 代码符合项目规范
- [ ] 文档已更新

#### 静态分析
- [ ] Lint 检查通过
  ```bash
  ruff check app/ tests/ --select E,F,W,B,S --ignore E501,S101,B008,S105,S106,S107
  ```
- [ ] 类型检查通过（如使用）
- [ ] 安全扫描无高危问题

### 2. 配置检查

#### 环境变量
- [ ] `.env` 文件模板完整
- [ ] 必需环境变量已配置
  - [ ] `DATABASE_URL` - 生产数据库连接
  - [ ] `CA_KEY_ENCRYPTION_KEY` - Fernet 密钥
  - [ ] `ADMIN_API_KEY` - Admin API 认证密钥
  - [ ] `BASE_URL` - 服务基础 URL
- [ ] 可选环境变量已根据需要配置
  - [ ] `LOG_LEVEL` 和 `LOG_FORMAT`
  - [ ] `CORS_ORIGINS`
  - [ ] `rollout_interval_seconds`

#### 密钥管理
- [ ] Fernet 密钥已安全生成
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- [ ] Admin API Key 已安全生成
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- [ ] 密钥已备份到安全位置
- [ ] 密钥不在代码仓库中

#### 数据库配置
- [ ] PostgreSQL 已部署
- [ ] 数据库连接已测试
  ```bash
  psql $DATABASE_URL -c "SELECT version();"
  ```
- [ ] 数据库迁移已执行
  ```bash
  alembic upgrade head
  ```
- [ ] 数据库备份策略已配置
- [ ] 数据库监控已配置

### 3. 网络和安全检查

#### TLS 证书
- [ ] 服务器证书已部署
- [ ] 证书链完整
- [ ] 证书有效期 > 30 天
- [ ] 私钥权限正确 (0600)

#### 防火墙规则
- [ ] 443 端口开放（外部 HTTPS 入口，如使用）
- [ ] 8000 端口仅对外部网关或内网调用方开放
- [ ] 5432 端口访问受限（仅应用服务器）
- [ ] 其他端口已关闭

#### 访问控制
- [ ] Admin API 访问受限（运维网络）
- [ ] Agent API 访问受限（Agent 节点）
- [ ] 数据库访问受限（应用服务器）

### 4. 服务配置检查

#### 应用服务
- [ ] Systemd 服务文件已创建
  ```bash
  cat /etc/systemd/system/cert-control-plane.service
  ```
- [ ] 服务启动正常
  ```bash
  sudo systemctl start cert-control-plane
  sudo systemctl status cert-control-plane
  ```
- [ ] 服务自动启动已启用
  ```bash
  sudo systemctl enable cert-control-plane
  ```
- [ ] 日志输出正常
  ```bash
  sudo journalctl -u cert-control-plane -f
  ```

#### 外部入口配置
- [ ] TLS 终止配置正确
- [ ] `/api/control/*` 访问来源受限
- [ ] `/api/agent/*` 访问来源受限
- [ ] 外部网关正确转发到应用 `8000`

#### Agent 配置
- [ ] Agent 二进制已部署
- [ ] Agent 配置文件正确
- [ ] Agent 服务已启动
- [ ] Agent 注册成功

### 5. 监控和告警检查

#### 健康检查
- [ ] `/healthz` 端点可访问
  ```bash
  curl -k https://your-domain/healthz
  ```
- [ ] 数据库健康检查正常
- [ ] 服务响应正常

#### 日志聚合
- [ ] 日志输出到标准输出
- [ ] 日志格式正确（JSON 或文本）
- [ ] 日志聚合工具已配置（如 ELK、Loki）
- [ ] 日志保留策略已配置

#### 告警配置
- [ ] Agent 离线告警已配置
- [ ] 证书过期告警已配置
- [ ] 服务异常告警已配置
- [ ] 告警通知渠道已测试

#### 性能监控
- [ ] CPU 使用率监控
- [ ] 内存使用率监控
- [ ] 磁盘使用率监控
- [ ] 网络流量监控
- [ ] 数据库性能监控

### 6. 备份和恢复检查

#### 数据备份
- [ ] 数据库备份已配置
  ```bash
  pg_dump -h db-host -U certcp certcp > backup_$(date +%Y%m%d).sql
  ```
- [ ] 备份计划已配置（每日）
- [ ] 备份存储位置安全
- [ ] 备份保留策略已配置

#### 恢复测试
- [ ] 备份恢复流程已测试
- [ ] 恢复时间符合要求
- [ ] 恢复文档已准备

### 7. 文档检查

#### 运维文档
- [ ] 部署文档完整
- [ ] 运维手册完整
- [ ] 故障排查指南完整
- [ ] 升级指南完整

#### 用户文档
- [ ] API 文档完整（Swagger）
- [ ] Agent 使用文档完整
- [ ] Dashboard 使用指南完整

#### 应急文档
- [ ] 紧急联系人列表
- [ ] 故障响应流程
- [ ] 回滚步骤文档

### 8. 性能测试检查

#### 基准测试
- [ ] 心跳负载测试完成
  ```bash
  cd tools/performance
  python run_all_tests.py --test heartbeat --duration 5m --users 100
  ```
- [ ] 证书同步测试完成
  ```bash
  python run_all_tests.py --test cert_sync --duration 5m --users 100
  ```
- [ ] 性能指标符合要求

#### 性能指标
| 指标 | 目标值 | 实际值 | 通过 |
|------|--------|--------|------|
| 心跳响应 P95 | < 200ms | | [ ] |
| 心跳吞吐量 | > 500 RPS | | [ ] |
| 证书同步 P95 | < 1s | | [ ] |
| 并发 Agent | > 1000 | | [ ] |

### 9. 安全检查

#### 安全扫描
- [ ] 依赖漏洞扫描完成
- [ ] 无 critical 或 high severity 漏洞
- [ ] 容器镜像扫描完成
- [ ] 代码安全扫描完成

#### 安全配置
- [ ] TLS 1.2+ 已启用
- [ ] 强密码套件已配置
- [ ] 不安全的端点已禁用
- [ ] 安全头部已配置

#### 访问控制
- [ ] 默认凭证已更改
- [ ] 不必要的账户已禁用
- [ ] 权限最小化配置

### 10. 功能验证

#### Agent 流程验证
- [ ] Agent TOFU 注册流程正常
- [ ] Agent 审批流程正常
- [ ] Agent 心跳正常
- [ ] Agent 证书同步正常
- [ ] Agent 服务 reload 正常

#### 证书管理验证
- [ ] 外部证书上传正常
- [ ] 证书分配正常
- [ ] 证书拉取更新正常
- [ ] 证书过期告警正常

#### Rollout 验证
- [ ] Rollout 创建正常
- [ ] Rollout 启动正常
- [ ] Rollout 批次推进正常
- [ ] Rollout 暂停/恢复正常
- [ ] Rollout 回滚正常

#### Dashboard 验证
- [ ] Dashboard 访问正常
- [ ] 认证正常
- [ ] 数据显示正常
- [ ] 刷新正常

## 📊 部署清单

### 部署步骤

#### 1. 准备阶段
```bash
# 1. 确认代码版本
git log --oneline -1

# 2. 拉取最新代码
git pull origin main

# 3. 检查依赖
cd server
pip install -e ".[dev]"
cd ..
npm --prefix server/frontend install
npm --prefix server/frontend run build

# 4. 运行测试
cd server
python3 -m pytest tests/ -v
```

#### 2. 部署阶段
```bash
# 1. 备份数据库
pg_dump $DATABASE_URL > backup_before_deploy_$(date +%Y%m%d_%H%M%S).sql

# 2. 停止服务
sudo systemctl stop cert-control-plane

# 3. 更新代码
cd /opt/cert-control-plane
git pull origin main

# 4. 更新依赖
cd server
pip install -e .

# 5. 运行迁移
alembic upgrade head

# 6. 构建前端
cd ..
npm --prefix server/frontend run build

# 7. 启动服务
sudo systemctl start cert-control-plane

# 8. 验证服务
curl http://localhost:8000/healthz
```

#### 3. 验证阶段
```bash
# 1. 检查服务状态
sudo systemctl status cert-control-plane

# 2. 检查日志
sudo journalctl -u cert-control-plane -n 100

# 3. 测试 API
curl -k http://localhost:8000/api/control/dashboard/summary \
  -H "X-Admin-API-Key: your-key"

# 4. 测试 Dashboard
open https://your-domain/dashboard

# 5. 检查 Agent 连接
curl -k http://localhost:8000/healthz
```

#### 4. 监控阶段
```bash
# 1. 监控日志
sudo journalctl -u cert-control-plane -f

# 2. 监控性能
top -p $(pgrep -f "uvicorn app.main:app")

# 3. 监控数据库
psql $DATABASE_URL -c "SELECT count(*) FROM agents;"

# 4. 监控告警
# 检查告警系统是否正常工作
```

## 🔙 回滚计划

### 快速回滚

如果部署后发现问题：

```bash
# 1. 停止服务
sudo systemctl stop cert-control-plane

# 2. 回滚代码
git checkout <previous-version-tag>

# 3. 回滚依赖
pip install -e .

# 4. 回滚数据库（如需要）
psql $DATABASE_URL < backup_before_deploy_TIMESTAMP.sql

# 5. 重启服务
sudo systemctl start cert-control-plane

# 6. 验证
curl -k https://localhost/healthz
```

### 回滚检查
- [ ] 回滚步骤已测试
- [ ] 回滚时间符合要求（< 15 分钟）
- [ ] 数据一致性已验证

## 📞 紧急联系

### 关键联系人
| 角色 | 姓名 | 联系方式 |
|------|------|---------|
| 项目负责人 | | |
| 运维负责人 | | |
| 安全负责人 | | |
| 值班人员 | | |

### 升级流程
1. P1 故障：立即联系项目负责人
2. P2 问题：30 分钟内联系运维负责人
3. P3 问题：当个工作日处理

## ✅ 最终确认

部署完成后，由以下人员签字确认：

- [ ] 技术负责人：___________ 日期：___________
- [ ] 运维负责人：___________ 日期：___________
- [ ] 安全负责人：___________ 日期：___________

---

**注意**: 此检查清单应在每次预生产部署前完整执行，所有项目必须检查通过才能进入生产环境。
