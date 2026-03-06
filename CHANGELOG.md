# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/zh-CN/).

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
- CORS 来源可通过 CORS_ORIGINS 环境变量配置（默认 `*` 仅限开发）
- 审计日志覆盖全部写操作
- 移除未使用的 SECRET_KEY 字段
