# Execution Checklist

> 状态: 已归档
>
> 说明: 旧 checklist 基于 CSR / renewal / mTLS 校验路径，和当前实现不一致，不能继续作为执行依据。

## 当前执行应检查的内容

- 文档与实现口径一致
- Agent 注册、审批轮询、`heartbeat`、`fetch-certs` 流程可用
- 外部证书上传、分配、Agent 拉取更新链路可回归
- Rollout 状态机和回滚逻辑可回归
- Dashboard 到期告警与审计视图可回归

## 当前建议的回归命令

```bash
python3 -m pytest tests/ -q
python3 -m pytest tests/test_agent_api.py tests/test_control_api.py tests/test_rollout.py -q
```
