# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/zh-CN/).

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
