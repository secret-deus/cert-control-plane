# Fix Plan

> 状态: 已归档
>
> 说明: 本文档的大部分问题定义来自旧的 CSR / renewal / mTLS 方案，现已不再对应当前实现。

## 仍然有效的后续问题

- 测试中过度依赖 mock，真实链路验证不足
- `tests/test_rollout.py` 仍存在 `AsyncMock` 相关 RuntimeWarning
- `fetch-certs`、Assignment、证书审计记录之间缺少更强的集成测试
- 前端仍缺少 E2E 自动化覆盖

## 已失效的问题域

- `renew` / `bundle` / CSR 相关路径
- `reset-token` 缺失问题
- `X-Client-CN` / `X-Client-Serial` 透传与校验
- `STRICT_CA_STARTUP`、`CERT_VALIDITY_DAYS`、bootstrap token 生命周期

## 当前修复入口

请优先参考：

- `PLAN.md` 中的 `Phase 2` 和 `Phase 3`
- `README.md` 中的当前接口与部署说明
