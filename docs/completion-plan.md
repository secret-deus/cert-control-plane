# Completion Plan

> 状态: 已归档
>
> 说明: 本文档原先服务于 CSR / 自签发 / mTLS 客户端证书模型，已不再作为当前项目的权威说明。

当前项目的权威基线请以以下文件为准：

- `PLAN.md`
- `README.md`
- `app/main.py`

## 当前有效产品模型

- 外部证书分发模式
- Agent 通过 TOFU 注册并等待管理员审批
- 审批后使用 `agent_token` 调用 `heartbeat` 和 `fetch-certs`
- 控制平面负责上传外部证书、维护分配关系、记录审计日志

## 已废弃假设

- CSR 提交与平台签发
- `/api/agent/bundle`
- `/api/agent/renew`
- bootstrap token 注册
- mTLS 客户端证书作为当前 Agent API 的应用层前提

## 迁移说明

如果后续需要参考历史设计，请将此文档视为“旧方案记录”，不要据此新增接口、测试或部署配置。
