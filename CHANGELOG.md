# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/zh-CN/).

## [0.3.0] - 2026-05-15

### Added
- **前端组件拆分**: CertFilters、CertTable、CertDetailDrawer、AgentStatsCards、AgentTable、AgentDetailPage 六个子组件从大页面中拆分
- **前端样式增强**: 新增 drawer 滑入/滑出动画、表格排序图标样式、筛选条响应式布局、skeleton 变体样式
- **E2E 测试适配**: Playwright 测试用例适配新 UI（证书资产、Agent舰队、Dashboard）
- **Kubernetes Secret V1**: 新增 SA kubeconfig 集群注册、Secret assignment、dry-run/confirm、create/adopt/update/rollback/validate
- **真实 minikube 验证脚本**: 新增单 namespace E2E 与三目标节点真实拓扑模拟脚本，覆盖 RBAC 负例

### Changed
- **前端重构**: CertManagementPage 从 1019 行拆分为 4 个组件（主页面 + CertFilters + CertTable + CertDetailDrawer）
- **前端重构**: AgentsPage 从 538 行拆分为 4 个组件（主页面 + AgentStatsCards + AgentTable + AgentDetailPage）
- **登录页断言**: E2E 测试从 "Agent 管理" 更新为 "Agent 舰队"
- **证书页断言**: E2E 测试从 "证书管理" 更新为 "证书资产"，筛选按钮从 "正常" 更新为 "健康"
- **Kubernetes 凭据更新**: 更新 cluster kubeconfig 后自动对该 cluster 下活跃 assignment 执行只读 validate

### Removed
- 无旧组件残留，所有旧版组件已在之前重构中清理

## [0.2.0] - 2026-04-08

### Added
- **E2E Testing**: Playwright 测试框架，覆盖登录、Agent、证书、Rollout 页面
- **Structured Logging**: JSON 格式日志支持，可配置日志级别和格式
- **Alerting System**: 完整的告警配置文档，支持 ELK、Loki、Prometheus 集成
- **Performance Testing**: Locust 性能测试框架，包含心跳和证书同步测试
- **Security Scanning**: GitHub Actions 安全扫描 workflow（pip-audit, npm audit, Trivy, CodeQL, Gitleaks）
- **Rust Agent**: 完整的 README 文档、构建脚本、发布 workflow
- **Go Agent**: 二进制构建和发布支持

### Documentation
- **Production Deployment**: 生产环境部署指南（架构、配置、运维、故障排查）
- **Agent Comparison**: Python vs Go vs Rust Agent 详细对比文档
- **Security Audit Checklist**: 完整的安全审计检查清单
- **Pre-production Checklist**: 预生产环境部署检查清单
- **Alerting Guide**: 监控告警配置指南

### Fixed
- 修复 `tests/test_rollout.py` 中的 RuntimeWarning（AsyncMock 误用于同步方法）
- 所有测试现在通过，无 warnings

### Changed
- 项目里程碑 M3 完成，进入 M4 准备阶段
- CI 新增 E2E 测试和安全扫描
- Agent 发布流程自动化

### Security
- 添加安全扫描自动化（依赖漏洞、容器漏洞、代码安全）
- 完善安全审计流程和检查清单

## [0.1.1] - 2026-03-11

### Security
- CORS 默认值从 `["*"]` 收紧为 `[]`，必须显式配置
- Agent reload 命令使用 `shlex.split()` 防止命令注入
- Agent 重注册时清理旧私钥
- Actor 身份从 API Key 前缀推导，不再信任可伪造的 X-Actor 头
- Agent RSA 密钥从 2048 位升级到 3072 位
- 私钥文件写入使用 `os.open()` 原子设置权限，消除 TOCTOU 窗口
- start.sh 不再将 ADMIN_API_KEY 打印到终端
- PostgreSQL 密码参数化，支持通过环境变量覆盖

### Fixed
- Rollout 回滚现在同时处理 COMPLETED 和 IN_PROGRESS 状态的 items
- APScheduler 版本锁定 `<4.0` 防止大版本破坏
- bootstrap_token 添加 `min_length=1` 校验
- 数据库引擎优雅关闭（`dispose_engine()`）

### Changed
- CA 证书有效期 10 年 → 5 年，Server 证书 825 天 → 398 天
- nginx TLS 密码套件更换为显式现代 ECDHE 套件
- Dashboard 前端统一使用 `apiFetch`，消除重复 fetch 逻辑
- 提取 `_finalize_issuance()` 消除证书签发的重复代码
- Agent config `ca_cert_path` 类型从 `str` 统一为 `Path`
- 删除 docker-compose.yml 过时的 `version` 字段
- Dockerfile 锁定基础镜像版本（node:22.14-alpine3.21, python:3.12.9-slim）
- CI lint 增加 bugbear (B) 和 security (S) 规则

### Added
- Dashboard API 4 个端点添加 `response_model` 类型约束
- Rollout 编排器测试套件（9 个测试）
- Agent API 端到端测试套件（5 个测试）
- nginx 安全头：HSTS、X-Content-Type-Options、X-Frame-Options
- IP 地址提取优先使用 X-Forwarded-For

## [0.1.0] - 2026-03-06

### Added
- FastAPI 后端：Agent API（register/bundle/renew/heartbeat）
- FastAPI 后端：Control API（agents/certs/rollouts/audit CRUD）
- Dashboard API（summary/agents-health/certs-expiry/events）
- React + TypeScript + Tailwind CSS 前端
  - 登录界面（API Key 认证）
  - 仪表盘（统计卡片、Agent 健康表、证书过期预警、审计时间线）
  - Agent 管理页（创建/列表/Token 重置）
  - 证书管理页（列表/筛选/撤销）
  - Rollout 管理页（创建/暂停/恢复/回滚/进度条）
  - 审计日志页（筛选/分页/JSON 展开）
- Nginx 双端口 mTLS 隔离架构（443 Control / 8443 Agent）
- Agent 客户端（CSR 流程、心跳循环、自动续期、mTLS 失败重注册）
- Alembic 数据库迁移（001 初始 + 002 serial_hex 兼容）
- GitHub Actions CI 流水线（backend test/lint + frontend build/typecheck）
- Dockerfile 多阶段构建（Node 前端 + Python 后端 + 非 root 用户）
- 一键启动脚本（startup.ps1 / start.sh）
- Agent 一键安装脚本（install.ps1 / install.sh）
- 回归测试套件（auth/serial/audit/migration/installer/dashboard）
- systemd 服务安全加固配置

### Security
- fail-closed serial 绑定（CN + Serial 双因子认证）
- Bootstrap token 一次性使用 + 过期
- Fernet 加密服务端私钥存储
- CORS 来源可通过 CORS_ORIGINS 环境变量配置
- 审计日志覆盖全部写操作
- 移除未使用的 SECRET_KEY 字段
