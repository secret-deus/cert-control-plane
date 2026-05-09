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

- **已在范围内**: Agent TOFU 注册、管理员审批、外部证书上传、证书分配、Agent 拉取更新、Rollout 批量编排、过期预警、审计日志、Dashboard、Kubernetes TLS Secret V1 分发
- **暂不在当前上线范围内**: 控制平面自建 CA 签发、Agent 提交 CSR 由平台签名、平台直接完成第三方 provider 自动续期、Kubernetes workload/Ingress/Gateway 自动编排

### 架构要点

- **单端口入口**: Dashboard、Control API、Agent API 共用 FastAPI 应用端口，生产环境由外部网关/TLS 入口做路径与来源控制
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
| Kubernetes Secret V1 | ✅ | SA kubeconfig、dry-run/confirm、create/adopt/update/rollback/validate |
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
| TASK-P2-6: Registry/Store 测试 | ✅ 已完成 | 已补充 `test_registry_store.py`，覆盖 `get_current_cert`、`revoke_cert`、`record_deployed_cert` |

### Phase 3: 生产就绪 [收尾中]

目标: 从”功能可用”提升到”可部署、可验证、可回滚”。

| 任务 | 状态 | 说明 |
|------|------|------|
| TASK-P3-1: 前端 E2E 测试 | ✅ 框架就绪 | Playwright 框架已建，测试需适配新 UI |
| TASK-P3-2: 集成联调环境 | ✅ 已完成 | Docker Compose + nginx + Agent live smoke 已验证 |
| TASK-P3-3: 性能测试 | 框架就绪 | Locust 脚本就绪，待执行基准测试 |
| TASK-P3-4: 安全审计 | ✅ 已完成 | 安全审计检查清单 + CI 安全扫描 workflow |
| TASK-P3-5: 观测与告警 | ✅ 已完成 | 结构化日志 + 告警配置文档 |
| TASK-P3-6: 部署文档 | ✅ 已完成 | 生产部署指南 + 预生产检查清单 |
| TASK-P3-7: 前端重构 | ✅ 已完成 | 16/16 组件完成，6 个子组件已拆分 |

**详细推进方案**: [M4 上线推进方案](docs/m4-execution-plan.md)

### Phase 4: 上游自动续期扩展 [规划中]

目标: 对接第三方 provider API，实现”平台自动拉取新证书”。

| 任务 | 状态 | 说明 |
|------|------|------|
| TASK-P4-1: Provider 抽象层 | 规划中 | 抽象阿里云 / Let's Encrypt / 内部 PKI 接入 |
| TASK-P4-2: 自动续期策略 | 规划中 | 到期前 N 天主动拉取新证书并替换旧版本 |
| TASK-P4-3: Provider 凭据管理 | 规划中 | 安全存储 API 密钥/访问令牌 |
| TASK-P4-4: 续期失败告警 | 规划中 | 拉取失败、校验失败、下发失败分级告警 |

**详细方案**: [阿里云证书服务集成方案](docs/aliyun-cert-integration-proposal.md)

### Phase 5: Kubernetes 原生证书分发 [V1 已完成]

目标: 在现有 Agent 文件路径分发之外，增加 Kubernetes 集群内 TLS Secret 的新增、更新、回滚、校验和审计能力。

这项能力与 `k8s/minikube` 部署清单不同：`k8s/minikube` 是把控制面部署到本地 Kubernetes；Phase 5 是让控制面把证书作为业务集群资源下发到目标 namespace/Secret。

#### Phase 5 V1 范围

- 控制平面直接调用 Kubernetes API 写入目标集群 Secret；V1 不引入 in-cluster controller 或 Kubernetes Agent。
- V1 只管理 `Secret`，不读取或改动 Deployment、StatefulSet、Pod、Ingress、Gateway、HTTPRoute 或自定义工作负载资源。
- V1 不删除 Kubernetes Secret；删除平台 assignment 只删除平台侧记录，集群内 Secret 由人工处理。
- V1 不做批量 rollout、暂停/恢复或多 Secret 编排；每次操作只针对一个 `cluster + namespace + secretName`。
- V1 支持最近一次成功部署前 snapshot 的单步回滚；回滚只恢复 `tls.crt`、`tls.key` 和平台 annotations，不回滚整个 Secret 对象。
- V1 默认 `auto_track_latest=true`、`auto_deploy=false`：可发现同 CN 新证书并提示 `pending_update`，但必须 dry-run + confirm 后才写集群。

#### Phase 5 V1 主流程

1. 管理员在目标集群手动创建 ServiceAccount 和 RBAC；平台只提供推荐 YAML 模板，不主动创建 SA/RBAC。
2. 管理员上传该 ServiceAccount 对应的 kubeconfig；V1 只接受静态 SA token kubeconfig，不支持个人 kubeconfig、`exec`、`auth-provider`、OIDC 或云厂商动态登录插件。
3. 平台执行只读 `Test Connection`：校验 API Server 可达，读取 Kubernetes 版本；如配置了默认 namespace，则读取该 namespace。该步骤不创建、不 patch Secret。
4. 管理员创建 `KubernetesSecretAssignment`，显式指定 `cluster + namespace + secretName + external_cert_id`。
5. 平台先 GET 当前 Secret 并生成 dry-run diff，记录 `dry_run_id`、当前 `resourceVersion`、变更摘要和过期时间。
6. 管理员 confirm dry-run 后，平台再次校验 dry-run 未过期且 `resourceVersion` 未变化，再执行 create 或 merge patch。
7. 平台 read-back GET Secret，解析 `tls.crt`，确认 leaf serial 等于 `ExternalCertificate.serial_hex`，并确认平台 annotation serial 一致后才标记成功。
8. 管理员可手动触发 validate；更新 cluster credentials 后，平台自动对该 cluster 下所有 assignment 执行只读 validate。

#### Phase 5 V1 数据模型

- `KubernetesCluster`
  - 记录集群名称、环境、API Server、默认 namespace、kubeconfig 密文或解析后的 SA token/CA/server 密文、连接状态和最近校验时间。
  - kubeconfig 必须来自 ServiceAccount；原始 kubeconfig 或解析后的 token/CA 必须加密存储。
- `KubernetesSecretAssignment`
  - 显式映射 `cluster_id + namespace + secret_name + external_cert_id`。
  - 对活跃记录增加唯一约束：`UNIQUE(cluster_id, namespace, secret_name)`。
  - 状态拆分为生命周期状态和健康状态。
  - 生命周期状态：`pending`、`adopted`、`deployed`、`failed`、`rolled_back`。
  - 健康状态：`unknown`、`healthy`、`missing`、`unmanaged`、`serial_mismatch`、`invalid_secret`、`rbac_error`、`cluster_unreachable`。
  - 额外显示 `pending_update`，表示存在同 CN 的新 active 证书版本但尚未部署。
- `KubernetesSecretDryRun`
  - dry-run 结果落库，10 分钟有效。
  - 记录 `cluster_id`、`assignment_id`、`namespace`、`secret_name`、`external_cert_id`、`current_resource_version`、脱敏 diff、状态、过期时间和创建人。
  - 不存私钥，不存完整证书内容。confirm 时必须传 `dry_run_id`；过期或 `resourceVersion` 变化即拒绝。
- `KubernetesSecretOperation`
  - 所有 `test_connection`、`adopt`、`deploy`、`rollback`、`validate` 都生成操作记录。
  - 记录 `assignment_id`、`cluster_id`、`action`、`status`、`dry_run_id`、`external_cert_id`、`resource_version_before/after`、`serial_before/after`、`error_code`、`error_message`、`started_at`、`finished_at`、`created_by`。
  - 操作记录只保存脱敏 diff 与状态；最近一次成功部署前的 Secret snapshot 单独加密保存，用于最近一次回滚。

#### Phase 5 V1 Secret 写入规则

- Kubernetes Secret 写入内容完全来自平台上传的外部证书：
  - `tls.crt = cert_pem + chain_pem`；如果未上传 chain，则只写 `cert_pem`。
  - `tls.key = decrypted key_pem`。
- create 时创建 `type=kubernetes.io/tls` Secret。
- update 时使用 `GET -> dry-run diff -> confirm -> merge patch/create -> read-back verify`。
- merge patch 只提交：
  - `type: kubernetes.io/tls`
  - `data.tls.crt`
  - `data.tls.key`
  - `metadata.annotations.cert-control-plane.io/*`
- 必须保留已有 labels、非平台 annotations、ownerReferences 和非 TLS data。
- 已存在但未被平台管理的 Secret 不允许直接覆盖，必须先 adopt。
- adopt 时如果已有 `tls.crt/tls.key` 且能解析，可记录基线并写入平台 annotations；后续更新允许把 `type` 修正为 `kubernetes.io/tls`。
- adopt 时如果缺少 `tls.crt/tls.key` 或内容无法解析，标记 `invalid_secret`；必须显式确认“改造成 TLS Secret”后才允许继续。
- 新上传证书必须强校验证书链、私钥匹配关系和 PEM 可解析性；失败时禁止进入 dry-run。

#### Phase 5 V1 平台 annotations

adopt 时写入：

- `cert-control-plane.io/managed: "true"`
- `cert-control-plane.io/assignment-id: "<assignment_id>"`
- `cert-control-plane.io/adopted-at: "<iso timestamp>"`
- `cert-control-plane.io/adopted-serial: "<current_secret_serial>"`

deploy/update 时写入：

- `cert-control-plane.io/managed: "true"`
- `cert-control-plane.io/assignment-id: "<assignment_id>"`
- `cert-control-plane.io/external-cert-id: "<external_cert_id>"`
- `cert-control-plane.io/serial: "<new_serial_hex>"`
- `cert-control-plane.io/updated-at: "<iso timestamp>"`

rollback 时写入：

- `cert-control-plane.io/managed: "true"`
- `cert-control-plane.io/assignment-id: "<assignment_id>"`
- `cert-control-plane.io/serial: "<rolled_back_serial_hex>"`
- `cert-control-plane.io/rolled-back-at: "<iso timestamp>"`
- `cert-control-plane.io/operation-id: "<operation_id>"`

#### Phase 5 V1 API 草案

- `POST /api/control/kubernetes/clusters`: 上传 SA kubeconfig，创建 cluster。
- `POST /api/control/kubernetes/clusters/{cluster_id}/test-connection`: 只读连接测试。
- `PUT /api/control/kubernetes/clusters/{cluster_id}/credentials`: 更新 SA kubeconfig，并触发该 cluster 下所有 assignment 的只读 validate。
- `POST /api/control/kubernetes/assignments`: 创建 Secret assignment。
- `POST /api/control/kubernetes/assignments/{assignment_id}/adopt/dry-run`: 生成 adopt dry-run。
- `POST /api/control/kubernetes/assignments/{assignment_id}/adopt/confirm`: 确认 adopt。
- `POST /api/control/kubernetes/assignments/{assignment_id}/deploy/dry-run`: 生成 deploy dry-run。
- `POST /api/control/kubernetes/assignments/{assignment_id}/deploy/confirm`: 确认 create/patch。
- `POST /api/control/kubernetes/assignments/{assignment_id}/rollback/dry-run`: 生成最近一次回滚 dry-run。
- `POST /api/control/kubernetes/assignments/{assignment_id}/rollback/confirm`: 确认最近一次回滚。
- `POST /api/control/kubernetes/assignments/{assignment_id}/validate`: 手动只读校验。
- `GET /api/control/kubernetes/operations`: 查看 K8s Secret 操作记录。

#### Phase 5 V1 测试基线

- 后端单元测试：覆盖证书解析、私钥匹配、kubeconfig 解析、Secret merge patch payload、状态机、dry-run 过期和 `resourceVersion` 冲突；这些测试不连集群。
- 真实 minikube 集成测试：创建 SA/RBAC，上传 SA kubeconfig，真实调用 Kubernetes API create/patch/read Secret；覆盖新证书部署、替换旧证书、adopt 已有 Secret、最近一次回滚、credential 更新后 validate。
- 浏览器 E2E：使用真实后端和真实 minikube，走页面上传 kubeconfig、创建 assignment、dry-run、confirm、查看 read-back 状态和操作历史；关键节点截图必须进入测试报告。
- V1 不以 mock Kubernetes API 作为验收依据；mock 只允许作为单元测试局部替身，不能替代 minikube E2E。

| 任务 | 状态 | 说明 |
|------|------|------|
| TASK-P5-1: Kubernetes Cluster 与 SA kubeconfig 模型 | ✅ 已完成 | 上传并加密存储 ServiceAccount kubeconfig，拒绝动态认证 kubeconfig |
| TASK-P5-2: Kubernetes Secret Assignment 模型 | ✅ 已完成 | 建立 `cluster + namespace + secretName + external_cert` 映射，拆分生命周期状态和健康状态 |
| TASK-P5-3: dry-run、diff 与 confirm 机制 | ✅ 已完成 | dry-run 落库 10 分钟，confirm 校验 `dry_run_id`、过期时间和 `resourceVersion` |
| TASK-P5-4: Secret create/adopt/update 执行器 | ✅ 已完成 | 支持 create、adopt、merge patch、read-back serial 校验，保留非 TLS 数据和业务 metadata |
| TASK-P5-5: validate 与凭据更新联动 | ✅ 已完成 | 支持手动 validate；更新 cluster credentials 后自动只读校验该集群所有 assignment |
| TASK-P5-6: 最近一次回滚 | ✅ 已完成 | 保存最近一次成功部署前 Secret snapshot，支持单 Secret dry-run + confirm 回滚 |
| TASK-P5-7: 真实 minikube 与浏览器 E2E | ✅ 已完成 | 不用 mock 作为验收，覆盖新增、替换、adopt、回滚、凭据更新和截图报告 |

### Phase 6: 分发目标统一编排 [规划中]

目标: 将文件路径 Agent、Kubernetes Secret、未来 Provider 自动续期统一成同一套证书版本、分发目标和 rollout 状态模型。

---

## 测试覆盖情况

### 当前测试状态 (2026-05-09)

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
| `tests/test_kubernetes_secrets.py` | ✅ | Kubeconfig 解析、证书/私钥匹配、TLS Secret payload |
| `tests/test_agent_deploy.py` | ✅ | Agent 本地写盘、reload、失败回滚 |
| `tests/test_healthz.py` | ✅ | `/healthz` 路由与 SPA 回退顺序 |

**当前结果**:

- `150 passed` (2026-05-09)
- 前端 `npm run lint`、`npm run build`、`npm run test:e2e` 已通过
- Kubernetes Secret V1 已通过真实 minikube E2E 与三目标节点拓扑模拟
- Python Agent live smoke 已通过
- Go 二进制 Agent live smoke 已通过

### 今日进展记录 (2026-05-09)

- 完成 Kubernetes Secret V1：SA kubeconfig、Secret assignment、dry-run/confirm、create/adopt/update/rollback/validate。
- 补齐 cluster credentials 更新后自动 validate 该 cluster 下所有活跃 assignment。
- 完成真实 minikube 验证：中心节点部署、单 namespace E2E、三 namespace/三目标节点拓扑模拟、RBAC 403 负例。
- 完成前端 M4 组件拆分与 E2E 适配，构建、lint、Playwright E2E 全部通过。

### 今日进展记录 (2026-04-13)

- 完成 Phase 3 任务执行检查
- 性能测试框架已就绪 (tools/performance/)
- 安全审计检查通过
- 前端 E2E 测试框架已就绪 (本地需后端服务运行，CI 已集成)
- Registry/Store 测试补充完成 (test_registry_store.py)

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
| M4: 首个可上线版本 | 2026-05-15 | 🔧 执行中 → [推进方案](docs/m4-execution-plan.md) |
| M5: Provider 自动续期 PoC | 2026-06-15 | ⏳ 规划中 |
| M6: Kubernetes 原生证书分发 PoC | 2026-07-15 | ✅ V1 已提前完成 |

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

### R5. Kubernetes Secret 更新的 blast radius 更大

- 直接更新业务集群 Secret 可能影响实际引用该 Secret 的入口或应用
- 风险: 错误 cluster、namespace、secretName、证书链或私钥会造成业务 TLS 异常
- 对策: Phase 5 V1 只允许显式 assignment，所有写操作必须 dry-run + confirm，禁止覆盖未 adopt Secret，写入后 read-back 校验 serial；V1 不做批量更新

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

### M4 准备工作 (推进中)

- [x] 性能测试框架（Locust 脚本）
- [x] 安全审计检查清单
- [x] 安全扫描 CI workflow
- [x] 预生产环境部署检查清单
- [x] CHANGELOG 更新
- [x] 版本发布说明模板
- [x] 前端子组件拆分完成（6 个组件） → Day 1-2 ✅
- [x] 前端构建通过 → Day 1 ✅
- [ ] Docker 镜像重建 → Day 3
- [ ] 性能基准测试执行 → Day 3
- [ ] Agent 端到端联调验证 → Day 3
- [ ] E2E 测试适配新 UI → Day 4
- [ ] 预生产环境部署验证 → Day 4
- [ ] Release v0.3.0 Tag → Day 4

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

### Sprint 4: Kubernetes 原生分发设计 [规划中]

| 任务 | 优先级 | 目标 |
|------|--------|------|
| NEXT-013: Kubernetes Cluster 与 SA kubeconfig 建模 | P1 | 支持上传 ServiceAccount kubeconfig、加密存储、只读 test connection |
| NEXT-014: Kubernetes Secret Assignment 建模 | P1 | 定义 `cluster + namespace + secretName + external_cert` 显式映射和状态机 |
| NEXT-015: Kubernetes dry-run 与 confirm | P1 | dry-run 落库，展示脱敏 diff、serial、resourceVersion，confirm 前防并发冲突 |
| NEXT-016: Secret create/adopt/update 执行器 PoC | P1 | 在 minikube 中完成新 Secret 创建、已有 Secret adopt、旧证书替换和 read-back 校验 |
| NEXT-017: 最近一次回滚验证 | P1 | 保存最近一次成功部署前 snapshot，验证单 Secret 回滚链路 |
| NEXT-018: 真实浏览器 E2E 与截图报告 | P1 | 通过页面完成 kubeconfig 上传、assignment、dry-run、confirm、操作历史查看并产出截图报告 |

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
- 业务 Kubernetes TLS Secret 直接写入能力；该能力归入 Phase 5 V1，且必须通过真实 minikube 与浏览器 E2E 验收

当前已识别但尚未纳入本轮改造的结构性问题：

- `RolloutItem` 目前按 `agent` 维度建模
- 外部证书分发链路实际按 `agent + local_path + external_cert` 维度工作
- 因此当前 Rollout 更适合表达“分批放行窗口”，不适合作为单条 assignment 部署完成态的精确事实来源
- 若后续需要精确追踪，应新增 assignment 级 rollout item 或显式的 agent deployment acknowledgment 模型

---

## 变更日志

### 2026-05-09

- 完成 M4 Day 1-2 前端重构任务
- 拆分 CertFilters、CertTable、CertDetailDrawer 从 CertManagementPage
- 拆分 AgentStatsCards、AgentTable、AgentDetailPage 从 AgentsPage
- 新增 index.css 样式：drawer 动画、sort-icon、filter-bar 响应式、skeleton 变体
- 前端构建验证通过（tsc + lint + build 零错误）
- E2E 测试适配新 UI（certificates、agents、dashboard、login）
- 更新 CHANGELOG v0.3.0
- 更新 PLAN.md Phase 3 前端重构状态为已完成

### 2026-05-09 (M4 推进方案)

- 完成 M4 上线推进方案 (`docs/m4-execution-plan.md`)
- 识别 8 个缺口，制定 4 天冲刺计划
- 前端重构进度: 10/16 组件完成，6 个子组件待拆分
- Phase 3 状态更新为"收尾中"
- M4 准备工作细化为按天可执行的任务清单

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
- M4 准备工作基本完成
- 性能测试框架
- 安全审计检查清单
- 安全扫描 CI workflow
- 预生产环境部署检查清单
- CHANGELOG 和发布说明模板

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
