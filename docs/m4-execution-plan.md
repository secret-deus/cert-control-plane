# M4 上线推进方案

> 目标: 2026-05-15 交付首个可上线版本
>
> 当前日期: 2026-05-09 | 剩余工作日: 4 天
>
> 文档状态: 执行中

---

## 一、现状评估

### 已完成

| 模块 | 状态 | 说明 |
|------|------|------|
| 后端 API | ✅ | 150 tests passing，Control/Agent/Dashboard/Kubernetes API 全部就位 |
| 数据模型 | ✅ | Agent、ExternalCertificate、Assignment、Rollout、AuditLog |
| Agent (Python/Go/Rust) | ✅ | 三种 Agent 实现，Python + Go 已通过 live smoke |
| Docker Compose | ✅ | PostgreSQL + App + Nginx 容器化部署就绪 |
| CI 流水线 | ✅ | 后端测试 + 前端构建 + 安全扫描 |
| 文档体系 | ✅ | 生产部署、运维手册、安全审计、预生产检查清单 |
| 性能测试框架 | ✅ | Locust 脚本就绪 (tools/performance/) |
| 前端骨架重建 | ✅ | Layout + 路由 + 4 个主页面结构 |
| Dashboard 监控面板 | ✅ | KPI 卡片 + 告警表格 + Agent 健康 + 趋势图 |
| 前端 M4 组件拆分 | ✅ | Cert/Agent 页面已拆分 6 个子组件 |
| Kubernetes Secret V1 | ✅ | 已通过真实 minikube 与三目标节点拓扑模拟 |

### 存在缺口

| 编号 | 缺口 | 严重程度 | 说明 |
|------|------|----------|------|
| GAP-1 | 性能基准测试执行 | P1 | Locust 框架就绪但未执行实际压测 |
| GAP-2 | 预生产部署验证 | P1 | 检查清单已有，但需按目标生产配置完整跑一次 |
| GAP-3 | Docker/镜像发布验证 | P1 | 前端重构与 K8s V1 后需重建镜像并做发布前 smoke |
| GAP-4 | 投产阻塞项修复 | P0 | 仍需处理 DEV_MODE 生产护栏、限流、metrics、生产 compose 等投产评估项 |

---

## 二、执行计划

### Day 1 (5/9): 前端构建恢复 + 证书管理页完善 [已完成]

**目标**: 前端可构建、证书管理页功能完整

#### 任务 1.1: 前端依赖恢复 [P0, 30min]

```bash
cd server/frontend
npm install
npx tsc --noEmit        # TypeScript 编译检查
npm run build           # Vite 构建
```

**验收**: `npm run build` 成功，`dist/` 目录生成

**实际结果**: 已通过 `npm run lint`、`npm run build`。

#### 任务 1.2: 证书管理页子组件拆分 [P0, 3h]

从现有 `CertManagementPage.tsx` (328 行) 拆分出：

| 组件 | 职责 | 预估行数 |
|------|------|----------|
| `CertFilters.tsx` | 域名搜索 + 状态/时间范围/类型筛选条 | ~60 行 |
| `CertTable.tsx` | 证书主表格(域名/类型/到期/剩余/节点/状态/操作) | ~120 行 |
| `CertDetailDrawer.tsx` | 右侧滑出抽屉(PEM/私钥/分发历史/节点列表) | ~150 行 |

**实施要点**:
- `CertFilters`: 搜索框用 `<input>` + `onChange` debounce，筛选用 `<select>`
- `CertTable`: 复用 `apiFetch('/external-certs')` 数据源，状态颜色逻辑: >30天绿 / 7~30天黄 / <7天红
- `CertDetailDrawer`: 右侧固定定位，`transform: translateX()` 动画，PEM 展示用 `<pre>` + 复制按钮

**验收**: `npx tsc --noEmit` 通过，证书页表格可筛选、详情抽屉可展开

**实际结果**: `CertFilters`、`CertTable`、`CertDetailDrawer` 已拆分并通过 E2E 覆盖。

#### 任务 1.3: 构建验证 [P0, 15min]

```bash
npx tsc --noEmit && npm run lint && npm run build
```

**验收**: 零 TypeScript 错误，零 ESLint 错误，构建成功

**实际结果**: 已通过。

---

### Day 2 (5/12): Agent 管理页完善 + 旧组件清理 [已完成]

**目标**: Agent 页功能完整，旧文件清理，前端重构收尾

#### 任务 2.1: Agent 管理页子组件拆分 [P0, 3h]

从现有 `AgentsPage.tsx` (277 行) 拆分出：

| 组件 | 职责 | 预估行数 |
|------|------|----------|
| `AgentStatsCards.tsx` | 在线/离线/待审批/延迟 4 个统计卡片 | ~50 行 |
| `AgentTable.tsx` | Agent 列表表格(ID/IP/状态/版本/心跳/证书数/操作) | ~100 行 |
| `AgentDetailPage.tsx` | Agent 详情页(基础信息/运行状态/证书同步/操作按钮) | ~180 行 |

**实施要点**:
- `AgentStatsCards`: 从 `GET /dashboard/summary` 取 `agents.total`, `agents.active` 等
- `AgentTable`: 从 `GET /agents` 取列表，`liveness` 字段映射状态图标
- `AgentDetailPage`: 路由 `/agents/:id`，调用 `GET /agents/:id` + `GET /agents/:id/detail`
- Agent 详情页增加「强制同步」「查看日志」按钮（强制同步 → 触发 Rollout，查看日志 → 审计日志筛选）

**验收**: Agent 详情页可访问，统计卡片数据正确

**实际结果**: `AgentStatsCards`、`AgentTable`、`AgentDetailPage` 已拆分，Agent 详情页 E2E 已覆盖。

#### 任务 2.2: 旧组件清理 [P1, 30min]

确认以下文件已被删除或不再存在（已在之前的重构中处理）：

- `CertificatesPage.tsx` (旧版)
- `ExternalCertsPage.tsx`
- `RolloutsPage.tsx`
- `AuditLogsPage.tsx`
- `CertificateList.tsx`
- `Charts.tsx`

**验收**: `src/components/` 只包含新架构组件

**实际结果**: 旧页面组件未作为当前路由入口使用，当前主路由已切到新组件结构。

#### 任务 2.3: index.css 样式增强 [P1, 1h]

新增样式：
- 抽屉 (drawer) 滑入/滑出动画
- 表格排序图标
- 筛选条响应式布局
- 加载骨架屏 (skeleton)

**验收**: `npm run build` 通过，视觉效果与需求文档一致

**实际结果**: 已通过 `npm run lint`、`npm run build`、`npm run test:e2e`。

#### 任务 2.4: 前端完整构建验证 [P0, 15min]

```bash
npx tsc --noEmit && npm run lint && npm run build
```

---

### Day 3 (5/13): Docker 重建 + 性能测试 + 联调

**目标**: 新前端跑在 Docker 环境中，性能基准测试完成

#### 任务 3.1: Docker 镜像重建 [P1, 1h]

```bash
cd server/frontend && npm run build
docker build -t cert-control-plane-app:latest ../
docker compose down && docker compose up -d
```

**验证步骤**:
1. `curl -k https://localhost:443/healthz` → 200
2. `curl -k https://localhost:8443/healthz` → 200
3. 浏览器打开 `https://localhost/` → Dashboard 页面正常渲染
4. 检查 Dashboard KPI 卡片、告警表格、Agent 健康、趋势图均显示数据
5. 证书管理页筛选和详情抽屉正常工作
6. Agent 管理页列表和详情页正常工作

#### 任务 3.2: 性能基准测试执行 [P1, 2h]

```bash
cd tools/performance

# 心跳负载测试
python run_all_tests.py --test heartbeat --duration 5m --users 100

# 证书同步测试
python run_all_tests.py --test cert_sync --duration 5m --users 100
```

**目标指标**:

| 指标 | 目标值 | 可接受值 |
|------|--------|----------|
| 心跳响应 P95 | < 200ms | < 500ms |
| 心跳吞吐量 | > 500 RPS | > 200 RPS |
| 证书同步 P95 | < 1s | < 3s |
| 并发 Agent | > 1000 | > 500 |

**输出**: 将测试结果填入 `docs/pre-production-checklist.md` 的性能指标表格

#### 任务 3.3: Agent 端到端联调 [P1, 1h]

```bash
# 1. 启动控制平面
docker compose up -d

# 2. 启动 Python Agent
cd client/agent
python -m agent

# 3. 验证注册 → 审批 → 心跳 → 证书拉取完整流程
```

**验收**: Agent 注册成功 → 管理员审批 → Agent 获取 token → 心跳正常 → 分配证书后 Agent 拉取成功

---

### Day 4 (5/14): E2E 适配 + 预生产检查 + 发布准备

**目标**: Playwright 测试适配新 UI，预生产检查清单全部通过

#### 任务 4.1: Playwright E2E 测试适配 [P2, 2h]

更新 E2E 测试脚本适配新前端路由和组件：

| 测试用例 | 路由 | 关键断言 |
|----------|------|----------|
| 登录 | `/` | API Key 输入 → 跳转 Dashboard |
| Dashboard | `/dashboard` | KPI 卡片渲染、告警表格有数据 |
| 证书管理 | `/certificates` | 列表加载、筛选工作、详情抽屉可展开 |
| Agent 管理 | `/agents` | 列表加载、详情页可访问 |

```bash
cd server/frontend
npx playwright test --reporter=html
```

#### 任务 4.2: 预生产检查清单执行 [P1, 2h]

按照 `docs/pre-production-checklist.md` 逐项检查：

**代码质量**:
- [ ] `python3 -m pytest tests/ -v --tb=short` 全部通过
- [ ] `python3 -m pytest tests/ --cov=app --cov-report=html` 覆盖率 > 80%
- [ ] `ruff check app/ tests/` 无错误
- [ ] `npm run build` 成功

**安全**:
- [ ] 依赖漏洞扫描无 critical/high
- [ ] TLS 证书有效期 > 30 天
- [ ] Fernet 密钥已生成
- [ ] Admin API Key 已生成

**功能验证**:
- [ ] Agent TOFU 注册流程正常
- [ ] 外部证书上传 → 分配 → Agent 拉取正常
- [ ] Rollout 创建/启动/暂停/恢复/回滚正常
- [ ] Dashboard 数据展示正常

#### 任务 4.3: 发布准备 [P1, 1h]

1. 更新 `CHANGELOG.md`:
   - 新增 `[0.3.0] - 2026-05-15` 版本记录
   - 记录前端重构、新增组件、删除旧组件

2. 更新 `PLAN.md`:
   - Phase 3 标记为已完成
   - M4 里程碑标记为已完成
   - 更新测试覆盖情况

3. 创建 Release Tag:
   ```bash
   git tag -a v0.3.0 -m "M4: 首个可上线版本"
   ```

---

## 三、风险与应对

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| 前端 TypeScript 编译错误多 | 中 | 阻塞构建 | Day 1 优先修复，必要时放宽 tsconfig |
| 性能测试不达标 | 低 | 延期上线 | 先用可接受值兜底，优化放到后续版本 |
| Docker 镜像构建失败 | 低 | 阻塞联调 | Dockerfile 已验证过，增量改动小 |
| E2E 测试适配工作量大 | 中 | 可延后 | P2 优先级，不阻塞上线 |
| Agent 联调发现新 bug | 中 | 需 hotfix | 预留 Day 4 下午作为缓冲 |

---

## 四、各天交付物汇总

| 日期 | 交付物 | 验收标准 |
|------|--------|----------|
| Day 1 (5/9) | 前端可构建 + 证书管理页完整 | `npm run build` 通过，证书页可用 |
| Day 2 (5/12) | Agent 页完整 + 旧代码清理 | 全部新组件就位，构建通过 |
| Day 3 (5/13) | Docker 环境 + 性能基准 + 联调 | Docker 跑通，性能达标，Agent 联调通过 |
| Day 4 (5/14) | E2E 适配 + 预生产检查 + 发布 | 检查清单通过，Release Tag 创建 |

---

## 五、前端组件完成度追踪

### 已完成 (10/16)

| 组件 | 文件 | 行数 | 状态 |
|------|------|------|------|
| Layout | `Layout.tsx` | 134 | ✅ |
| Dashboard | `Dashboard.tsx` | 206 | ✅ |
| KPICards | `KPICards.tsx` | 45 | ✅ |
| AlertTable | `AlertTable.tsx` | 101 | ✅ |
| AgentHealthCards | `AgentHealthCards.tsx` | 67 | ✅ |
| CertExpiryTrend | `CertExpiryTrend.tsx` | 63 | ✅ |
| CertManagementPage | `CertManagementPage.tsx` | 328 | ✅ (待拆分子组件) |
| AgentsPage | `AgentsPage.tsx` | 277 | ✅ (待拆分子组件) |
| AuthScreen | `AuthScreen.tsx` | 86 | ✅ |
| SettingsPage | `SettingsPage.tsx` | 10 | ✅ |

### 待完成 (6/16)

| 组件 | 文件 | 来源 | 计划日期 |
|------|------|------|----------|
| CertFilters | `CertFilters.tsx` | 从 CertManagementPage 拆出 | Day 1 |
| CertTable | `CertTable.tsx` | 从 CertManagementPage 拆出 | Day 1 |
| CertDetailDrawer | `CertDetailDrawer.tsx` | 新增 | Day 1 |
| AgentStatsCards | `AgentStatsCards.tsx` | 从 AgentsPage 拆出 | Day 2 |
| AgentTable | `AgentTable.tsx` | 从 AgentsPage 拆出 | Day 2 |
| AgentDetailPage | `AgentDetailPage.tsx` | 新增，路由 `/agents/:id` | Day 2 |

---

## 六、后端 API 现状确认

当前 API 完全满足前端需求，无需新增接口：

| 前端功能 | API 端点 | 确认状态 |
|----------|----------|----------|
| KPI 数据 | `GET /dashboard/summary` | ✅ |
| 告警列表 | `GET /dashboard/cert-alerts` | ✅ |
| Agent 健康 | `GET /dashboard/agents-health` | ✅ |
| 到期趋势 | `GET /dashboard/certs-expiry` | ✅ |
| 审计时间线 | `GET /audit` | ✅ |
| 证书列表 | `GET /external-certs` | ✅ |
| 证书上传 | `POST /external-certs/upload` | ✅ |
| 证书分配 | `POST /assign-cert` | ✅ |
| Agent 列表 | `GET /agents` | ✅ |
| Agent 详情 | `GET /agents/:id/detail` | ✅ |
| Agent 审批 | `POST /agents/:id/approve` | ✅ |
| Rollout CRUD | `POST/GET/PUT /rollouts` | ✅ |

---

## 七、Phase 3 → M4 收尾后的下一步

M4 交付后，进入 Phase 4 规划：

| 任务 | 优先级 | 预计时间 |
|------|--------|----------|
| 阿里云证书服务集成 PoC | P1 | 2 周 |
| 自动续期策略设计 | P1 | 1 周 |
| Provider 凭据安全存储 | P1 | 1 周 |
| 续期失败告警集成 | P2 | 3 天 |
| 证书+流量入口统一控制台 (远期) | P3 | 待评估 |

详见: `PLAN.md` Phase 4 章节
