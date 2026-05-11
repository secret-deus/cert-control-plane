# Cert Control Plane 文档中心

欢迎来到 Cert Control Plane 的文档中心！本目录包含项目的所有核心文档。

## 文档导航

### 快速开始
- [项目概览](../README.md) - 项目介绍和快速开始
- [开发计划](../PLAN.md) - 开发路线图和进度追踪
- [快速验证](quick-verification.md) - 一键验证项目状态

### 部署指南
- [Docker Compose 部署](deployment-compose.md) - Docker Compose 部署方式
- [生产环境部署](deployment-production.md) - 生产环境完整部署指南
- [预生产检查清单](pre-production-checklist.md) - 部署前完整检查清单
- [测试环境部署检查清单](test-environment-deployment.md) - 真实控制面、Agent、nginx 和 K8s Secret 测试环境准备

### 运维手册
- [监控告警配置](alerting.md) - 完整的监控和告警配置指南
- [安全审计清单](security-audit-checklist.md) - 安全审计检查清单

### Agent 文档
- [Agent 对比指南](agent-comparison.md) - Python vs Go vs Rust Agent 详细对比

### 二期规划
- [阿里云证书服务集成方案](aliyun-cert-integration-proposal.md) - 阿里云 SSL 证书 API 集成设计

### 开发文档
- [E2E 测试指南](../server/frontend/e2e/README.md) - Playwright E2E 测试文档
- [性能测试框架](../tools/performance/README.md) - Locust 性能测试文档
- [minikube 部署与 K8s Secret E2E](../k8s/minikube/README.md) - 本地 Kubernetes 集群验证流程

### 验收报告
- [投产评估报告](../specs/投产评估报告.md) - 投产风险、阻塞项和后续路线
- [真实场景测试报告](../specs/真实场景测试报告-2026-05-11.md) - 多 nginx / Agent / Kubernetes Secret 真实测试证据

### 其他文档
- [发布说明模板](release-template.md) - 版本发布说明模板

## 按角色查找

### 开发者
1. [项目概览](../README.md)
2. [开发计划](../PLAN.md)
3. [E2E 测试指南](../server/frontend/e2e/README.md)

### 运维人员
1. [生产环境部署](deployment-production.md)
2. [预生产检查清单](pre-production-checklist.md)
3. [测试环境部署检查清单](test-environment-deployment.md)
4. [监控告警配置](alerting.md)
5. [安全审计清单](security-audit-checklist.md)

### Agent 用户
1. [Agent 对比指南](agent-comparison.md)

## 快速搜索

**如何部署？**
→ [生产环境部署](deployment-production.md)

**如何配置监控？**
→ [监控告警配置](alerting.md)

**选择哪个 Agent？**
→ [Agent 对比指南](agent-comparison.md)

**如何运行测试？**
→ [快速验证](quick-verification.md)

---

_最后更新: 2026-05-11_
