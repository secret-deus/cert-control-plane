# Cert Control Plane 开发计划与进度

> 关联 OKR: O3-KR2, O3-KR3
>
> 当前基线: **外部证书分发模式**
>
> 当前目标: 实现外部 TLS 证书集中管理、Agent 节点自动拉取更新、到期前 30 天预警

---

## 项目概述

Cert Control Plane 是一个 TLS 证书生命周期管理系统，当前采用 **外部证书分发模式**：

- 证书和私钥由第三方来源提供，例如阿里云、Let's Encrypt、企业内部 PKI
- 控制平面负责上传、加密存储、分配和下发证书
- Agent 负责注册、心跳、按路径拉取更新并部署到 nginx 节点

### 当前范围边界

- **已在范围内**: Agent TOFU 注册、管理员审批、外部证书上传、证书分配、Agent 拉取更新、Rollout 批量编排、过期预警、审计日志、Dashboard
- **暂不在范围内**: 控制平面自建 CA 签发、Agent 提交 CSR 由平台签名、平台直接完成第三方 provider 自动续期

### 架构要点

- **双端口隔离**: 443 端口提供 Control API + Dashboard，8443 端口提供 Agent 通信入口
- **TOFU 注册**: Agent 首次上报指纹，等待管理员审批后获得 `agent_token`
- **外部证书分发**: 控制平面存储外部证书及私钥密文，按 `agent + local_path` 映射下发
- **Rollout 编排**: 支持按批次推进证书更新，提供暂停、恢复、回滚

---

## 当前实现基线

### 已落地能力

| 模块 | 状态 | 说明 |
|------|------|------|
| Agent 注册与审批 | ✅ | TOFU 注册、审批、拒绝、删除 |
| Agent API | ✅ | `register` / `register/status` / `heartbeat` / `fetch-certs` |
| 外部证书管理 | ✅ | 上传、列表、详情 |
| 证书分配 | ✅ | `assign-cert`、查看分配、删除分配 |
| 证书审计记录 | ✅ | Agent 证书历史、单证书详情 |
| Dashboard API | ✅ | summary、agent health、到期事件、审计时间线 |
| Rollout 编排 | ✅ | 创建、启动、暂停、恢复、回滚 |
| 前端界面 | ✅ | React + Tailwind 仪表盘 |
| CI 基线 | ✅ | 后端测试 + 前端构建 |

### 当前不应再写入文档的能力

- CSR 签发
- `/api/agent/renew`
- `/api/agent/bundle`
- bootstrap token 注册模型
- “私钥永不离开 Agent 节点”

---

## 开发阶段

### Phase 1: 分发闭环 [已完成]

目标: 证书从上传到 Agent 部署形成闭环。

| 任务 | 状态 | 说明 |
|------|------|------|
| Agent 注册与审批 | ✅ | Agent 首次注册、管理员审批、颁发 `agent_token` |
| 外部证书上传 | ✅ | 解析 PEM，提取元数据，私钥加密存储 |
| 证书分配 | ✅ | 按 `agent + local_path` 建立映射 |
| Agent 拉取更新 | ✅ | Agent 上报本地 `not_after`，平台比较后返回更新 |
| Dashboard 可视化 | ✅ | Agent 状态、证书到期、审计事件 |
| Rollout 批量编排 | ✅ | 分批推进、暂停、恢复、失败、回滚 |

### Phase 2: 测试与一致性修复 [基本完成]

目标: 提高测试可信度，收敛文档与实现。

| 任务 | 状态 | 说明 |
|------|------|------|
| TASK-P2-1: 文档口径统一 | ✅ 已完成 | 主文档、OpenAPI 描述、安装入口统一为外部证书分发模式 |
| TASK-P2-2: Agent API 测试补强 | ✅ 已完成 | 已覆盖 `fetch-certs` 判定、无分配/旧证书/新证书场景 |
| TASK-P2-3: Rollout 测试修复 | ✅ 已完成 | 已清理 `AsyncMock` 误用导致的 warnings |
| TASK-P2-4: Assignment 与证书链路测试 | ✅ 已完成 | 已覆盖上传外部证书 -> 分配 -> Agent 拉取更新链路 |
| TASK-P2-5: Dashboard 告警测试 | ✅ 已完成 | 已覆盖 `external-certs-expiry`、`cert-alerts` 视图 |
| TASK-P2-6: Registry/Store 测试 | 待处理 | 当前仍需确认历史 `revoke_cert` 语义是否保留 |

### Phase 3: 生产就绪 [进行中]

目标: 从“功能可用”提升到“可部署、可验证、可回滚”。

| 任务 | 状态 | 说明 |
|------|------|------|
| TASK-P3-1: 前端 E2E 测试 | 待开始 | 选择 Playwright，覆盖登录、Agent、证书、Rollout 页面 |
| TASK-P3-2: 集成联调环境 | 进行中 | 已有 Docker Compose + nginx + Agent live smoke，仍需补更系统化回归 |
| TASK-P3-3: 性能测试 | 待开始 | 并发 Agent 心跳与批量 `fetch-certs` 压测 |
| TASK-P3-4: 安全审计 | 待开始 | 依赖扫描、密钥处理检查、认证流程审查 |
| TASK-P3-5: 观测与告警 | 待开始 | 健康检查、失败日志、证书到期告警 |
| TASK-P3-6: 部署文档 | 进行中 | 已补 Compose/smoke 文档，后续仍需补生产部署与运维说明 |

### Phase 4: 上游自动续期扩展 [规划中]

目标: 对接第三方 provider API，实现“平台自动拉取新证书”。

| 任务 | 状态 | 说明 |
|------|------|------|
| TASK-P4-1: Provider 抽象层 | 规划中 | 抽象阿里云 / Let's Encrypt / 内部 PKI 接入 |
| TASK-P4-2: 自动续期策略 | 规划中 | 到期前 N 天主动拉取新证书并替换旧版本 |
| TASK-P4-3: Provider 凭据管理 | 规划中 | 安全存储 API 密钥/访问令牌 |
| TASK-P4-4: 续期失败告警 | 规划中 | 拉取失败、校验失败、下发失败分级告警 |

---

## 测试覆盖情况

### 当前测试状态 (2026-04-03)

| 文件 | 状态 | 覆盖范围 |
|------|------|----------|
| `tests/test_agent_api.py` | ✅ | Agent 注册、审批轮询、心跳、`fetch-certs` |
| `tests/test_agent_auth.py` | ✅ | Agent Token 认证 |
| `tests/test_control_api.py` | ✅ | Agent、外部证书、Rollout、审计、证书查询 |
| `tests/test_dashboard.py` | ✅ | Dashboard 汇总、外部证书到期、Agent 证书告警 |
| `tests/test_rollout.py` | ✅ | Rollout 创建、推进、超时、失败、回滚、暂停恢复 |
| `tests/test_migration.py` | ✅ | Alembic 迁移校验 |
| `tests/test_installer.py` | ✅ | Agent 安装脚本路径与烟雾检查 |
| `tests/test_audit_actions.py` | ✅ | 审计动作对齐 |
| `tests/test_serial_hex.py` | ✅ | 加密辅助函数与序列号兼容 |
| `tests/test_distribution_integration.py` | ✅ | SQLite 下的上传、分配、拉取分发链路 |
| `tests/test_agent_deploy.py` | ✅ | Agent 本地写盘、reload、失败回滚 |
| `tests/test_healthz.py` | ✅ | `/healthz` 路由与 SPA 回退顺序 |

**当前结果**:

- `101 passed`
- Python Agent live smoke 已通过
- Go 二进制 Agent live smoke 已通过

### 今日进展记录 (2026-04-03)

- 已完成外部证书 ZIP 上传、外部证书删除、Agent 当前证书状态回传与前端展示
- 已完成 Docker Compose + nginx + Agent 的真实更新链路 smoke
- 已补 Go 版纯二进制 Agent，可构建、可分发、可通过 live smoke
- 已产出 `agent-go/dist/` 下的 `darwin-arm64`、`linux-amd64`、`linux-arm64` 二进制

### 运行命令

```bash
# 运行所有测试
python3 -m pytest tests/ -v

# 快速回归
python3 -m pytest tests/ -q

# 带覆盖率报告
python3 -m pytest tests/ -v --cov=app --cov=agent
```

---

## 里程碑

| 里程碑 | 目标日期 | 状态 |
|--------|----------|------|
| M1: 分发闭环完成 | 2026-03-15 | ✅ 已完成 |
| M2: 文档与测试基线收敛 | 2026-04-15 | ✅ 已完成 |
| M3: 集成联调环境可复现 | 2026-04-30 | ✅ 已完成 |
| M4: 首个可上线版本 | 2026-05-15 | ⏳ 待开始 |
| M5: Provider 自动续期 PoC | 2026-06-15 | ⏳ 规划中 |

---

## 当前主要风险

### R1. 历史文档残留仍需持续清理

- 已完成主入口文档收敛，历史归档文档仍保留旧方案说明
- 风险: 新成员若误读归档文档，可能继续沿旧模型开发
- 对策: 明确 `PLAN.md` 与 `README.md` 为当前权威来源

### R2. 测试偏 mock，真实链路验证仍需继续增强

- 现有单元测试仍以 mock 为主，但已补 SQLite 集成测试与 live smoke
- 风险: 还缺少更稳定的长期回归环境与前端 E2E
- 对策: 保留 smoke 工具并继续补 Playwright 与 PostgreSQL 持续回归

### R3. 30 天能力目前是“预警”，不是“自动续期”

- 当前已经具备到期统计和告警视图
- 尚未接入 provider API 自动获取新证书
- 对策: 将“自动续期”下沉到 Phase 4，避免当前阶段目标失真

### R4. 前端缺少自动化测试

- 当前 CI 仅覆盖前端构建，不覆盖交互行为
- 风险: 页面回归只能靠人工验证
- 对策: 引入 Playwright，先覆盖核心页面与关键流程

---

## 技术债务与待办

### 已确认

- [x] pytest `asyncio_default_fixture_loop_scope` 配置已修正
- [x] Control API 基础回归已稳定
- [x] 后端测试与前端构建已纳入 CI

### 待处理

- [x] 修复 `tests/test_rollout.py` 中 `db.add()` 的 RuntimeWarning
- [x] 补齐 Assignment -> `fetch-certs` -> 证书审计记录的完整测试链路
- [x] 增加 Dashboard 到期告警接口测试
- [x] 完成生产部署文档和运维手册
- [x] 完成前端 E2E 测试基建
- [x] 完成结构化日志和告警配置
- [x] 完成 Rust Agent 文档和发布流程
- [ ] 明确 `Registry/Store` 层保留范围，决定是否继续保留 `revoke_cert` 语义

---

## 下一阶段执行计划

建议按以下顺序继续开发，优先解决“可验证性”和“真实链路闭环”：

### Sprint 1: 测试可信度提升 [已完成]

| 任务 | 优先级 | 目标 |
|------|--------|------|
| NEXT-001: 修复 Rollout 测试 warnings | ✅ | 已完成 |
| NEXT-002: Assignment -> fetch-certs 集成测试 | ✅ | 已完成 |
| NEXT-003: Dashboard 告警测试补齐 | ✅ | 已完成 |
| NEXT-004: 启动脚本与安装脚本回归 | ✅ | 已完成 |

### Sprint 2: 真实运行链路验证 [已完成]

| 任务 | 优先级 | 目标 |
|------|--------|------|
| NEXT-005: docker-compose 烟雾测试 | ✅ | 已完成，443/8443 与 `/healthz` 已验证 |
| NEXT-006: Agent 本地部署 smoke test | ✅ | 已完成，覆盖写盘、备份、回滚、reload 失败恢复 |
| NEXT-007: Rollout 与分发链路对齐 | ✅ | 已完成，测试 warnings 已修复 |
| NEXT-011: Go Agent 二进制 smoke | ✅ | 已完成，纯二进制 Agent 可通过 live smoke |

### Sprint 3: 交付质量补强 [已完成]

| 任务 | 优先级 | 目标 |
|------|--------|------|
| NEXT-008: 前端 Playwright 基建 | ✅ | 已完成测试框架，覆盖登录、Agent、外部证书、Rollout 页面 |
| NEXT-009: 部署文档收敛 | ✅ | 已完成生产部署指南、运维手册 |
| NEXT-010: 观测与告警 | ✅ | 已完成结构化日志、告警配置文档 |
| NEXT-012: Rust Agent 最低可用版本 | ✅ | 已完成 README、构建脚本、发布 workflow、Agent 对比文档 |

---

## 关键文件索引

| 路径 | 说明 |
|------|------|
| `app/main.py` | FastAPI 应用入口与调度器启动 |
| `app/api/control.py` | Agent、外部证书、分配、Rollout、审计接口 |
| `app/api/agent.py` | Agent 注册、心跳、拉取证书接口 |
| `app/api/dashboard.py` | Dashboard 汇总、过期预警、时间线接口 |
| `app/models.py` | Agent、ExternalCertificate、Assignment、Certificate、Rollout 模型 |
| `app/schemas.py` | 请求/响应模型 |
| `app/core/crypto.py` | 密钥加解密等加密辅助 |
| `app/core/security.py` | Admin API Key 与 Agent Token 逻辑 |
| `app/orchestrator/rollout.py` | Rollout 编排与回滚逻辑 |
| `app/registry/store.py` | 当前证书查询与撤销辅助函数 |
| `agent/` | Python Agent |
| `frontend/src/` | React 前端 |
| `.github/workflows/ci.yml` | CI 配置 |

---

## 验收口径

当前版本的验收标准应明确为：

1. 运维侧可以上传外部证书并分配到指定 Agent 路径
2. Agent 可以在心跳和拉取流程中识别并获取更新后的证书
3. 平台可以查看 Agent 健康、证书历史、外部证书到期情况和审计日志
4. Rollout 提供 agent 级分批推进、暂停、恢复和回滚编排能力；分发是否实际生效仍以 Agent 拉取结果、证书历史和 Dashboard 观测为准
5. 到期前 30 天提供预警能力

以下能力不属于当前版本验收项：

- 平台自建 CA 签发
- CSR 自动签名
- 第三方 provider 自动续期

当前已识别但尚未纳入本轮改造的结构性问题：

- `RolloutItem` 目前按 `agent` 维度建模
- 外部证书分发链路实际按 `agent + local_path + external_cert` 维度工作
- 因此当前 Rollout 更适合表达“分批放行窗口”，不适合作为单条 assignment 部署完成态的精确事实来源
- 若后续需要精确追踪，应新增 assignment 级 rollout item 或显式的 agent deployment acknowledgment 模型

---

## 变更日志

### 2026-04-08

- 修复 `tests/test_rollout.py` 中的 RuntimeWarning（AsyncMock 误用）
- 完成生产部署文档 `docs/deployment-production.md`
- 包含部署架构、配置清单、运维手册、故障排查、安全最佳实践
- 完成 Playwright E2E 测试基建
- 覆盖登录、Agent、外部证书、Rollout 页面
- 集成到 CI 流程
- 完成结构化日志配置和告警文档
- 支持 JSON 和文本格式日志
- 提供完整的告警集成指南
- 完成 Rust Agent 文档和发布流程
- 创建完整的 README 和配置指南
- 添加 macOS 构建脚本
- 创建 GitHub Actions 发布 workflow
- 编写 Agent 对比文档
- Sprint 3 全部完成
- 里程碑 M3 完成

### 2026-03-31

- 将项目基线正式收敛为“外部证书分发模式”
- 完成 `NEXT-001` 到 `NEXT-006` 的主要实现与测试补齐
- 明确 `NEXT-007` 的结论：当前 Rollout 为 agent 级编排能力，不再沿用旧 CSR 完成态叙事
- 新增 `docs/deployment-compose.md` 作为容器化部署与排障基线
- 重写开发计划，移除 CSR、自签发、bootstrap token 等不符合当前实现的描述
- 将“到期前 30 天自动续期”调整为“到期前 30 天预警”
- 新增 Phase 4，用于承接未来的 provider 自动续期能力

### 2026-03-30

- 修复 `test_control_api.py` 中 3 个失败测试
- Control API 测试全部通过

### 2026-03-27

- 创建 `tests/test_control_api.py`
- 完成 Control API 端点基础测试覆盖
