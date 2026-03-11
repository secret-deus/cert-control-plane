# Cert Control Plane 项目收尾执行方案

Date: 2026-03-06
Status: **COMPLETED** (2026-03-11)
Scope: 前端 (`frontend/`)、测试 (`tests/`)、CI/CD、部署加固、安全收敛、文档完善

## 1. 现状总结

### 1.1 已完成（无需改动）

| 模块 | 完成度 | 关键成果 |
|------|--------|---------|
| 后端 API（Agent/Control/Dashboard） | 95% | 全部端点实现，含审计日志 |
| Agent 客户端（runner/client/crypto/deployer） | 98% | CSR 流程、心跳循环、mTLS 失败重注册 |
| 加密核心（CertManager/Fernet/CA 单例） | 100% | serial_hex、fail-closed 认证 |
| 数据库模型 + Alembic 迁移 | 100% | 001 初始 + 002 兼容迁移 |
| Nginx 双端口隔离 | 100% | 443 Control / 8443 Agent mTLS |
| 安装脚本（install.sh/install.ps1） | 100% | preflight + smoke 校验 |
| 审计系统 | 100% | 全写操作审计，action 文档对齐 |
| README | 90% | 架构图、API 文档、部署指南 |

### 1.2 缺口矩阵

| 编号 | 维度 | 当前完成度 | 目标 | 差距描述 |
|------|------|-----------|------|---------|
| GAP-01 | CI/CD | 0% | 基本门控 | 无 GitHub Actions，测试和 lint 全靠手动 |
| GAP-02 | 前端页面 | 60% | 全功能管理 UI | 仅有 Dashboard + 登录，缺 4 个核心管理页面 |
| GAP-03 | 测试覆盖 | 55% | ≥80% 关键路径 | 缺 Control API、Orchestrator、Register/Renew 集成测试 |
| GAP-04 | 部署配置 | 85% | 生产可用 | Dockerfile 无前端构建、无非 root 用户 |
| GAP-05 | 安全收敛 | 85% | 生产级别 | CORS 全开、无速率限制 |
| GAP-06 | 文档 | 90% | 完整 | 缺 CHANGELOG、前端构建说明 |
| GAP-07 | 低优先级遗留 | — | 清理 | FOLLOWUP-001/002 未修复 |

---

## 2. 分阶段执行计划

### Phase 0: 基础设施（CI/CD + 部署加固）

> 目标：建立自动化门控，确保后续开发有安全网。

#### TASK-P0-1: GitHub Actions CI 流水线

**优先级**: 高
**关联**: GAP-01

创建 `.github/workflows/ci.yml`：

```yaml
# 目标流程
on: [push, pull_request]
jobs:
  backend-test:
    - python 3.12
    - pip install -e ".[dev]"
    - pytest tests/ -v --tb=short
  backend-lint:
    - ruff check app/ agent/ tests/
  frontend-build:
    - cd frontend && npm ci && npm run build
  frontend-lint:
    - cd frontend && npm run lint
```

实施步骤：

1. 创建 `.github/workflows/ci.yml`，包含 backend-test、backend-lint、frontend-build、frontend-lint 四个 job。
2. backend-test job 中设置环境变量 mock（`ADMIN_API_KEY`、`DATABASE_URL=sqlite+aiosqlite:///:memory:`、`STRICT_CA_STARTUP=false`）。
3. frontend-build job 中执行 `npm ci && npm run build`，验证 TypeScript 编译和 Vite 构建通过。
4. 可选：添加 Dependabot 配置用于依赖自动更新。

**Done 条件**：PR 合并需 CI 全绿，至少覆盖 `pytest` + `tsc` + `vite build`。

#### TASK-P0-2: Dockerfile 多阶段构建

**优先级**: 高
**关联**: GAP-04

当前问题：Dockerfile 未包含 `frontend/dist/` 构建，容器内无 UI 静态资源。

实施步骤：

1. 添加 Node.js 构建阶段（stage: frontend-builder）：
   ```dockerfile
   FROM node:22-alpine AS frontend-builder
   WORKDIR /frontend
   COPY frontend/package.json frontend/package-lock.json ./
   RUN npm ci
   COPY frontend/ .
   RUN npm run build
   ```
2. 在 Python 阶段中 COPY 构建产物：
   ```dockerfile
   COPY --from=frontend-builder /frontend/dist /app/frontend/dist
   ```
3. 添加非 root 用户：
   ```dockerfile
   RUN adduser --disabled-password --no-create-home appuser
   USER appuser
   ```
4. 添加 `.dockerignore` 排除 `node_modules/`、`.git/`、`__pycache__/` 等。

**Done 条件**：`docker-compose up` 后访问 `https://localhost/` 能看到前端页面。

---

### Phase 1: 前端核心页面（管理功能）

> 目标：补齐 4 个缺失的管理页面，使 UI 覆盖后端全部 Control API 功能。
> 原则：复用现有 Tailwind 变量和 `glass-panel` 组件风格，保持 UI 一致性。

#### TASK-P1-0: 前端路由与布局骨架

**优先级**: 高
**关联**: GAP-02（前置）

实施步骤：

1. 安装 `react-router-dom`（或使用轻量 state 路由，与现有风格对齐）。
2. 创建 `components/Layout.tsx`，包含：
   - 左侧导航菜单（Dashboard / Agents / Certificates / Rollouts / Audit Logs）
   - 顶部保留现有 navbar（logo + status + sign out）
   - 主内容区 `<Outlet />`
3. 更新 `App.tsx`，用 Router 替换当前 state 切换逻辑。
4. 更新 `app/main.py` 中 SPA 路由，添加 catch-all 回退到 `index.html`：
   ```python
   @app.get("/{path:path}")
   async def spa_fallback(path: str):
       # 排除 /api 前缀，返回 index.html
   ```
5. 将 `<title>` 从 `"frontend"` 改为 `"Cert Control Plane"`。

**Done 条件**：浏览器访问 `/agents`、`/rollouts` 等路径不返回 404，正确渲染对应页面骨架。

#### TASK-P1-1: Agents 管理页面

**优先级**: 高
**关联**: GAP-02

对接 API：
- `GET /api/control/agents` — Agent 列表
- `POST /api/control/agents` — 创建 Agent（CSR 或 server-side 模式）
- `POST /api/control/agents/{id}/reset-token` — 重置 bootstrap token

页面功能：

| 区块 | 内容 |
|------|------|
| 顶部操作栏 | "New Agent" 按钮 → 弹出创建对话框 |
| Agent 列表表格 | Name、Status（ACTIVE/INACTIVE badge）、Current Cert Serial（截断显示）、Last Heartbeat（相对时间）、Created At |
| 行内操作 | Reset Token（确认弹窗）、查看详情（展开或跳转） |
| 空状态 | 无 Agent 时显示引导文案 |

实施步骤：

1. 创建 `components/AgentsPage.tsx`。
2. 实现 Agent 列表获取（带错误/加载状态）。
3. 实现创建 Agent 对话框（Modal 或抽屉），字段：`name`（必填）、`sans`（可选 JSON 数组）。
4. 实现 Reset Token 操作（确认弹窗 + API 调用 + 刷新列表）。
5. 操作成功/失败时显示 toast 通知。

**Done 条件**：能通过 UI 完成 Agent 的创建、列表查看、token 重置。

#### TASK-P1-2: Certificates 管理页面

**优先级**: 高
**关联**: GAP-02

对接 API：
- `GET /api/control/certs` — 证书列表
- `POST /api/control/certs/{serial_hex}/revoke` — 撤销证书

页面功能：

| 区块 | 内容 |
|------|------|
| 筛选栏 | 按 Agent Name 过滤、按状态过滤（Active / Revoked / Expired） |
| 证书列表表格 | Serial（截断）、Agent Name、Not After（到期日 + 剩余天数颜色标记）、Is Current（badge）、Revoked（badge）、Created At |
| 行内操作 | Revoke（确认弹窗，仅非 revoked 证书可操作） |
| 到期预警 | 30 天内到期用 amber 标记，已过期用 red 标记 |

实施步骤：

1. 创建 `components/CertificatesPage.tsx`。
2. 实现证书列表获取（支持 query 参数过滤）。
3. 实现 Revoke 操作（二次确认弹窗，提示撤销不可逆）。
4. 到期时间用 `date-fns` 格式化，配合颜色标记。

**Done 条件**：能通过 UI 查看全部证书列表、按条件筛选、撤销指定证书。

#### TASK-P1-3: Rollouts 管理页面

**优先级**: 中
**关联**: GAP-02

对接 API：
- `GET /api/control/rollouts` — Rollout 列表
- `POST /api/control/rollouts` — 创建 Rollout
- `POST /api/control/rollouts/{id}/pause` — 暂停
- `POST /api/control/rollouts/{id}/resume` — 恢复
- `POST /api/control/rollouts/{id}/rollback` — 回滚

页面功能：

| 区块 | 内容 |
|------|------|
| 顶部操作栏 | "New Rollout" 按钮 |
| Rollout 列表 | ID、Status（badge: PENDING/IN_PROGRESS/COMPLETED/FAILED/PAUSED/ROLLED_BACK）、Agent Count、Progress Bar（completed/total items）、Created At |
| 行内操作 | Pause / Resume / Rollback（按状态条件启用/禁用） |
| 展开详情 | RolloutItem 列表：Agent Name、Item Status、Updated At |

实施步骤：

1. 创建 `components/RolloutsPage.tsx`。
2. 实现 Rollout 列表（含状态 badge 颜色映射）。
3. 实现创建 Rollout 表单（选择目标 Agents、配置批次大小）。
4. 实现 Pause/Resume/Rollback 操作按钮（按 Rollout 状态动态启用）。
5. 可选：使用 `recharts`（已安装）渲染进度可视化图表。

**Done 条件**：能通过 UI 创建 Rollout、查看进度、执行暂停/恢复/回滚。

#### TASK-P1-4: Audit Logs 浏览页面

**优先级**: 中
**关联**: GAP-02

对接 API：
- `GET /api/control/audit` — 审计日志列表

页面功能：

| 区块 | 内容 |
|------|------|
| 筛选栏 | 按 Action 类型过滤、按 Actor 过滤、时间范围选择 |
| 日志列表 | Timestamp、Action（彩色 badge）、Actor（admin/agent CN）、Target（Agent/Cert ID）、Details（JSON 可展开） |
| 分页 | 底部分页控件（offset/limit），默认每页 50 条 |

实施步骤：

1. 创建 `components/AuditLogsPage.tsx`。
2. 实现日志列表获取（支持 query 参数过滤和分页）。
3. Details 字段用可展开的 JSON 面板显示。
4. Action badge 颜色映射（如 `revoke` 用 red、`register` 用 green）。

**Done 条件**：能通过 UI 浏览全部审计日志、按条件筛选、分页翻阅。

#### TASK-P1-5: 前端公共组件抽取

**优先级**: 低
**关联**: GAP-02（重构，非功能性）

在各页面开发过程中，识别重复模式并抽取：

1. `components/ui/DataTable.tsx` — 通用数据表格（排序、筛选、空状态）。
2. `components/ui/ConfirmDialog.tsx` — 通用确认弹窗。
3. `components/ui/StatusBadge.tsx` — 状态标签（复用 Tailwind 颜色变量）。
4. `components/ui/Toast.tsx` — 操作反馈通知。
5. 启用已安装但未使用的 `clsx` + `tailwind-merge`（即 `cn()` 工具函数）。

> 遵循 YAGNI 原则：仅在 ≥2 个页面确实复用时才抽取，不做预设抽象。

---

### Phase 2: 测试覆盖扩展

> 目标：将关键路径测试从 31 个扩展到 ~70 个，覆盖 Control API 和 Orchestrator。

#### TASK-P2-1: Control API 端点测试

**优先级**: 高
**关联**: GAP-03

目标文件：`tests/test_control_api.py`

测试用例（预计 ~15 个）：

| 端点 | 正向测试 | 负向测试 |
|------|---------|---------|
| `GET /api/control/agents` | 返回 Agent 列表 | 无 API Key → 401 |
| `POST /api/control/agents` | 创建成功 + 返回 bootstrap_token | 重复名称 → 409 |
| `POST /agents/{id}/reset-token` | token 重置 + 审计记录 | 不存在 ID → 404 |
| `GET /api/control/certs` | 返回证书列表 | — |
| `POST /certs/{hex}/revoke` | 撤销 + is_revoked=True | 已撤销重复操作 → 幂等或 409 |
| `GET /api/control/rollouts` | 返回 Rollout 列表 | — |
| `GET /api/control/audit` | 返回审计日志 | — |

实施方式：使用 `httpx.AsyncClient` + `ASGITransport`（与现有 `test_dashboard.py` 一致）。

#### TASK-P2-2: Agent Register/Renew 集成测试

**优先级**: 高
**关联**: GAP-03

目标文件：`tests/test_agent_lifecycle.py`

测试用例（预计 ~10 个）：

1. **注册流程**：bootstrap token → CSR 提交 → 证书签发 → Agent 状态变更
2. **续期流程**：已认证 Agent → renew → 新证书签发 → 旧证书标记非 current
3. **Bundle 获取**：已认证 Agent → bundle → 返回 cert_pem + chain_pem（无私钥泄露）
4. **心跳**：已认证 Agent → heartbeat → last_seen_at 更新
5. **错误场景**：过期 token、无效 CSR、未注册 Agent

需 mock：CertManager（避免依赖真实 CA 文件）。

#### TASK-P2-3: Rollout Orchestrator 逻辑测试

**优先级**: 中
**关联**: GAP-03

目标文件：`tests/test_rollout_orchestrator.py`

测试用例（预计 ~8 个）：

1. `create_rollout()` — 创建 Rollout + RolloutItem
2. `advance_all_rollouts()` — 正常批次推进
3. 超时 Item → Rollout 标记 FAILED
4. 暂停/恢复 — 状态正确转换
5. 回滚 — 标记 ROLLED_BACK
6. 已完成 Rollout — advance 跳过
7. 空 Agent 列表 — 优雅处理

#### TASK-P2-4: CertRegistry Store 测试

**优先级**: 中
**关联**: GAP-03

目标文件：`tests/test_cert_registry.py`

测试用例（预计 ~6 个）：

1. `issue_from_csr()` — 正常签发 + DB 持久化
2. `issue_server_side()` — 服务端生成密钥 + Fernet 加密存储
3. `revoke()` — 标记 is_revoked + 审计事件
4. `build_bundle()` — 返回 cert + chain（无私钥在 CSR 模式下）
5. 重复撤销 — 幂等处理

---

### Phase 3: 安全收敛与生产加固

> 目标：消除生产环境安全风险点。

#### TASK-P3-1: CORS 配置收敛

**优先级**: 中
**关联**: GAP-05

实施步骤：

1. 在 `app/config.py` 的 Settings 中添加 `CORS_ORIGINS: list[str]` 配置项，默认值 `["*"]`（开发兼容）。
2. 在 `app/main.py` 中使用 `settings.CORS_ORIGINS` 替代硬编码 `["*"]`。
3. 在 `.env.example` 中添加 `CORS_ORIGINS=["https://your-domain.com"]` 示例。
4. 在 `docker-compose.yml` 的 app 环境变量中设置生产值。

**Done 条件**：`allow_origins` 可通过环境变量配置，不再硬编码 `*`。

#### TASK-P3-2: API 速率限制

**优先级**: 低
**关联**: GAP-05

实施步骤：

1. 安装 `slowapi`（基于 `limits` 库的 FastAPI 中间件）。
2. 对高风险端点添加速率限制：
   - `POST /api/agent/register` — 10 req/min per IP（防暴力注册）
   - `POST /api/control/agents` — 30 req/min per API Key
   - 其他端点保持默认（较宽松）
3. 返回标准 `429 Too Many Requests` + `Retry-After` 头。

> 注意：此项可推迟到有真实流量时实施，当前内网部署风险较低。

#### TASK-P3-3: 清理未使用的 SECRET_KEY

**优先级**: 低
**关联**: GAP-05

`app/config.py` 中定义了 `SECRET_KEY` 但从未使用（无 JWT/session 场景）。

选项 A（推荐）：移除该字段及 `.env.example` 中的对应项。
选项 B：如计划未来添加 JWT，保留但标注用途。

---

### Phase 4: 文档完善

#### TASK-P4-1: 创建 CHANGELOG.md

**优先级**: 中
**关联**: GAP-06

格式采用 [Keep a Changelog](https://keepachangelog.com/zh-CN/) 规范：

```markdown
# Changelog

## [0.1.0] - 2026-03-06

### Added
- FastAPI 后端：Agent API（register/bundle/renew/heartbeat）
- FastAPI 后端：Control API（agents/certs/rollouts/audit CRUD）
- Dashboard API（summary/agents-health/certs-expiry/events）
- React + TypeScript + Tailwind 前端（Dashboard + 登录）
- Nginx 双端口 mTLS 隔离架构
- Agent 客户端（CSR 流程、心跳、自动续期）
- Alembic 数据库迁移（001 初始 + 002 serial_hex 兼容）
- 31 个回归测试（auth/serial/audit/migration/installer/dashboard）
- install.sh + install.ps1 安装脚本
- systemd 服务安全加固配置

### Security
- fail-closed serial 绑定（CN + Serial 双因子认证）
- Bootstrap token 一次性使用 + 过期
- Fernet 加密服务端私钥存储
- 审计日志覆盖全部写操作
```

#### TASK-P4-2: 更新 README 前端构建说明

**优先级**: 中
**关联**: GAP-06

在 README.md 中添加前端相关章节：

1. 开发环境启动（`cd frontend && npm install && npm run dev`）
2. 生产构建（`npm run build` → `dist/` 被 FastAPI 自动 serve）
3. 说明 Vite 代理配置（开发模式 `/api` → `127.0.0.1:8000`）

#### TASK-P4-3: 修复已知低优先级遗留

**优先级**: 低
**关联**: GAP-07 + FOLLOWUP-001/002

1. `agent/client.py` 第 75 行：docstring `serial` → `serial_hex`。
2. `pyproject.toml`：添加 `asyncio_default_fixture_loop_scope = "function"`。

---

## 3. 执行优先级与依赖关系

```
Phase 0 (基础设施)
  ├── TASK-P0-1 CI/CD ──────────────────────────────────────┐
  └── TASK-P0-2 Dockerfile 多阶段构建                        │
                                                             │
Phase 1 (前端页面)                                            │ CI 门控
  ├── TASK-P1-0 路由骨架 ◄──────── 前置条件                    │
  ├── TASK-P1-1 Agents 页 ◄─── P1-0                         │
  ├── TASK-P1-2 Certs 页 ◄─── P1-0                          │
  ├── TASK-P1-3 Rollouts 页 ◄─── P1-0                       │
  ├── TASK-P1-4 Audit Logs 页 ◄─── P1-0                     │
  └── TASK-P1-5 公共组件抽取 ◄─── P1-1..P1-4（并行后重构）     │
                                                             │
Phase 2 (测试扩展)                                            │
  ├── TASK-P2-1 Control API 测试 ◄──────────────────────────┘
  ├── TASK-P2-2 Agent 生命周期测试
  ├── TASK-P2-3 Rollout Orchestrator 测试
  └── TASK-P2-4 CertRegistry 测试

Phase 3 (安全加固) —— 可与 Phase 1/2 并行
  ├── TASK-P3-1 CORS 配置收敛
  ├── TASK-P3-2 速率限制（可延后）
  └── TASK-P3-3 清理 SECRET_KEY

Phase 4 (文档) —— 最后执行
  ├── TASK-P4-1 CHANGELOG.md
  ├── TASK-P4-2 README 前端说明
  └── TASK-P4-3 FOLLOWUP 修复
```

---

## 4. 任务总览

| Task ID | Phase | 优先级 | 预估工作量 | 依赖 |
|---------|-------|--------|-----------|------|
| TASK-P0-1 | 0 | **高** | 0.5 天 | 无 |
| TASK-P0-2 | 0 | **高** | 0.5 天 | 无 |
| TASK-P1-0 | 1 | **高** | 0.5 天 | 无 |
| TASK-P1-1 | 1 | **高** | 1 天 | P1-0 |
| TASK-P1-2 | 1 | **高** | 0.5 天 | P1-0 |
| TASK-P1-3 | 1 | **中** | 1 天 | P1-0 |
| TASK-P1-4 | 1 | **中** | 0.5 天 | P1-0 |
| TASK-P1-5 | 1 | **低** | 0.5 天 | P1-1..P1-4 |
| TASK-P2-1 | 2 | **高** | 1 天 | P0-1 |
| TASK-P2-2 | 2 | **高** | 1 天 | 无 |
| TASK-P2-3 | 2 | **中** | 0.5 天 | 无 |
| TASK-P2-4 | 2 | **中** | 0.5 天 | 无 |
| TASK-P3-1 | 3 | **中** | 0.2 天 | 无 |
| TASK-P3-2 | 3 | **低** | 0.5 天 | 无 |
| TASK-P3-3 | 3 | **低** | 0.1 天 | 无 |
| TASK-P4-1 | 4 | **中** | 0.2 天 | 无 |
| TASK-P4-2 | 4 | **中** | 0.2 天 | P0-2 |
| TASK-P4-3 | 4 | **低** | 0.1 天 | 无 |

**合计预估**：~9 天工作量（可并行缩短至 ~5-6 天）

---

## 5. 推荐合并策略

| PR | 包含 Task | 说明 |
|----|-----------|------|
| PR-1 | P0-1 + P0-2 | 基础设施：CI + Dockerfile |
| PR-2 | P1-0 | 前端路由骨架 + SPA 回退 |
| PR-3 | P1-1 + P1-2 | Agents + Certificates 管理页 |
| PR-4 | P1-3 + P1-4 | Rollouts + Audit Logs 管理页 |
| PR-5 | P2-1 + P2-2 | 后端核心测试扩展 |
| PR-6 | P2-3 + P2-4 | 辅助测试扩展 |
| PR-7 | P3-1 + P3-3 + P4-* | 安全收敛 + 文档 + 遗留修复 |

每个 PR 必须：
1. CI 全绿（PR-1 合并后生效）。
2. 不引入新的 lint warning。
3. 更新本文档的完成状态。

---

## 6. 验收标准

### 6.1 Phase 0 验收

- [ ] GitHub Actions 在 push/PR 时自动运行 pytest + lint + frontend build。
- [ ] `docker-compose up --build` 后，浏览器访问 `https://localhost/` 可见前端 UI。
- [ ] Dockerfile 运行时进程为非 root 用户。

### 6.2 Phase 1 验收

- [ ] 浏览器可通过导航菜单切换到 Agents / Certificates / Rollouts / Audit Logs 页面。
- [ ] 可通过 UI 创建 Agent、查看列表、重置 token。
- [ ] 可通过 UI 查看证书列表、撤销证书。
- [ ] 可通过 UI 创建 Rollout、暂停/恢复/回滚。
- [ ] 可通过 UI 浏览审计日志、按条件筛选、翻页。
- [ ] 所有操作失败时有用户友好的错误提示。

### 6.3 Phase 2 验收

- [ ] `pytest tests/ -v` 测试数从 31 增长到 ≥65。
- [ ] Control API 全部端点有至少 1 正向 + 1 负向测试。
- [ ] Agent 注册/续期/心跳端到端流程有测试覆盖。
- [ ] Rollout 编排器正常/异常路径有测试覆盖。

### 6.4 Phase 3 验收

- [ ] CORS `allow_origins` 通过环境变量配置，生产环境不再为 `*`。
- [ ] 无未使用的 `SECRET_KEY` 字段残留（或已标注用途）。

### 6.5 Phase 4 验收

- [ ] CHANGELOG.md 存在且记录当前版本功能清单。
- [ ] README.md 包含前端构建说明。
- [ ] FOLLOWUP-001 和 FOLLOWUP-002 已修复。

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 前端页面开发量大，可能延期 | Phase 1 完成时间推迟 | 按优先级分批交付：先 Agents + Certs，后 Rollouts + Audit |
| 测试需 mock 大量 DB 交互 | 编写和维护成本高 | 复用 `conftest.py` 现有 fixtures，统一 mock 模式 |
| Dockerfile 非 root 可能影响文件权限 | 容器启动失败 | 在 CI 中添加 `docker-compose up` smoke test |
| 速率限制可能影响合法高频操作 | Agent 心跳被误限 | 仅限 `/register`（一次性操作），心跳端点不限流 |

---

## 8. 完成状态跟踪

| Task ID | Status | Date | Notes |
|---------|--------|------|-------|
| TASK-P0-1 | ✅ Done | 2026-03-06 | `.github/workflows/ci.yml` |
| TASK-P0-2 | ✅ Done | 2026-03-06 | Multi-stage Dockerfile + `.dockerignore` |
| TASK-P1-0 | ✅ Done | 2026-03-06 | `react-router-dom` + `Layout.tsx` + SPA fallback |
| TASK-P1-1 | ✅ Done | 2026-03-06 | `AgentsPage.tsx` |
| TASK-P1-2 | ✅ Done | 2026-03-06 | `CertificatesPage.tsx` |
| TASK-P1-3 | ✅ Done | 2026-03-06 | `RolloutsPage.tsx` |
| TASK-P1-4 | ✅ Done | 2026-03-06 | `AuditLogsPage.tsx` |
| TASK-P1-5 | ✅ Done | 2026-03-06 | `lib/api.ts` shared helper |
| TASK-P2-1 | Pending | — | — |
| TASK-P2-2 | Pending | — | — |
| TASK-P2-3 | Pending | — | — |
| TASK-P2-4 | Pending | — | — |
| TASK-P3-1 | ✅ Done | 2026-03-06 | `cors_origins` in Settings + main.py |
| TASK-P3-2 | Deferred | — | Low priority, defer to production |
| TASK-P3-3 | ✅ Done | 2026-03-06 | Removed `SECRET_KEY` |
| TASK-P4-1 | ✅ Done | 2026-03-06 | `CHANGELOG.md` |
| TASK-P4-2 | ✅ Done | 2026-03-06 | README updated |
| TASK-P4-3 | ✅ Done | 2026-03-06 | `serial_hex` docstring + `asyncio_default_fixture_loop_scope` |

