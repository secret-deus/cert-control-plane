# 性能测试套件

本目录包含 Cert Control Plane 的性能测试脚本和工具。

## 测试场景

### 1. Agent 并发心跳测试
测试控制平面处理大量 Agent 并发心跳的能力。

### 2. 批量证书同步测试
测试 Agent 批量拉取证书的性能。

### 3. Rollout 大规模部署测试
测试 Rollout 在大规模 Agent 环境下的表现。

## 快速开始

### 前置条件

```bash
# 安装依赖
pip install locust httpx

# 或使用项目虚拟环境
source ../../.venv/bin/activate
pip install locust
```

### 运行测试

```bash
# 运行所有性能测试
python run_all_tests.py

# 运行单个测试
locust -f heartbeat_test.py
locust -f cert_sync_test.py
locust -f rollout_test.py
```

## 测试脚本

### heartbeat_test.py
Agent 心跳性能测试

**测试参数**:
- 用户数: 10-1000
- 每个用户代表一个 Agent
- 每秒发送心跳请求

**关键指标**:
- 响应时间 (P50, P95, P99)
- 请求成功率
- 吞吐量 (RPS)

### cert_sync_test.py
证书同步性能测试

**测试参数**:
- 用户数: 10-500
- 每个用户每 30 秒同步一次证书
- 证书数量: 1-10 个/请求

**关键指标**:
- 同步延迟
- 数据传输量
- 内存使用

### rollout_test.py
Rollout 性能测试

**测试参数**:
- Agent 数量: 100-1000
- 批次大小: 10-50
- Rollout 推进速度

**关键指标**:
- Rollout 完成时间
- 批次推进延迟
- 数据库负载

## 性能基准

### 目标指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 心跳响应时间 (P95) | < 200ms | 95% 的请求在 200ms 内完成 |
| 心跳吞吐量 | > 500 RPS | 每秒处理 500+ 心跳请求 |
| 证书同步延迟 (P95) | < 1s | 95% 的同步在 1s 内完成 |
| Rollout 批次推进 | < 5s | 每批次推进时间 |
| 并发 Agent 支持 | > 1000 | 支持 1000+ 并发 Agent |

### 基准环境

**推荐配置**:
- CPU: 4 核
- 内存: 8 GB
- 数据库: PostgreSQL (独立部署)
- 网络: 千兆局域网

## 结果分析

测试完成后，结果会保存在 `results/` 目录：

```
results/
├── heartbeat_test_20260408_143022/
│   ├── stats.csv           # 统计数据
│   ├── stats_history.csv   # 历史统计
│   ├── failures.csv        # 失败记录
│   └── report.html         # HTML 报告
```

### 查看报告

```bash
# 打开 HTML 报告
open results/heartbeat_test_20260408_143022/report.html
```

### 分析数据

```python
import pandas as pd

# 加载统计数据
df = pd.read_csv('results/heartbeat_test_20260408_143022/stats.csv')

# 查看响应时间分布
print(df[['Name', 'Average Response Time', '95%']].head())

# 查看吞吐量
print(f"Total RPS: {df['Requests/s'].sum()}")
```

## 调优建议

### 如果心跳响应慢

1. **数据库优化**:
   ```sql
   CREATE INDEX idx_agent_last_seen ON agents(last_seen);
   ```

2. **连接池调整**:
   ```python
   # app/database.py
   engine = create_async_engine(
       DATABASE_URL,
       pool_size=20,
       max_overflow=40
   )
   ```

3. **缓存**:
   ```python
   # 添加 Redis 缓存 Agent 状态
   ```

### 如果证书同步慢

1. **批量查询优化**:
   - 使用 `IN` 查询代替多个单独查询
   - 添加复合索引

2. **响应压缩**:
   ```python
   # 启用 gzip 压缩
   from fastapi.middleware.gzip import GZipMiddleware
   app.add_middleware(GZipMiddleware)
   ```

### 如果 Rollout 慢

1. **批次大小调整**:
   ```python
   # 减小批次大小
   default_batch_size = 10
   ```

2. **推进间隔调整**:
   ```python
   # 缩短推进间隔
   rollout_interval_seconds = 10
   ```

## 持续监控

建议在生产环境中持续监控关键指标：

```yaml
# Prometheus 指标示例
- heartbeat_latency_seconds
- heartbeat_requests_total
- cert_sync_duration_seconds
- rollout_progress_total
```

## 故障排查

### 测试失败

1. **连接被拒绝**:
   - 检查服务是否启动
   - 检查端口是否开放
   - 检查防火墙规则

2. **超时**:
   - 增加超时时间
   - 减少并发用户数
   - 检查网络延迟

3. **内存不足**:
   - 减少并发用户数
   - 增加系统内存
   - 优化测试脚本

### 结果异常

1. **响应时间波动大**:
   - 检查是否有其他进程干扰
   - 检查数据库锁
   - 检查垃圾回收

2. **成功率低**:
   - 检查服务日志
   - 检查数据库连接数
   - 检查资源使用情况

## 自动化测试

### CI 集成

```yaml
# .github/workflows/performance.yml
name: Performance Tests

on:
  schedule:
    - cron: '0 2 * * 0'  # 每周日凌晨 2 点
  workflow_dispatch:

jobs:
  performance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run performance tests
        run: |
          cd tools/performance
          python run_all_tests.py --duration 5m
      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: performance-results
          path: tools/performance/results/
```

### 定期报告

建议每周运行一次性能测试，并生成趋势报告：

```bash
# 生成趋势报告
python generate_trend_report.py --weeks 4
```

## 最佳实践

1. **测试前准备**:
   - 清理测试数据
   - 重启服务
   - 预热系统 (运行 2-3 分钟)

2. **测试中监控**:
   - 监控 CPU、内存、网络
   - 监控数据库连接数
   - 监控响应时间变化

3. **测试后分析**:
   - 对比基准值
   - 分析性能瓶颈
   - 制定优化方案

4. **持续改进**:
   - 定期运行测试
   - 跟踪性能趋势
   - 及时优化瓶颈
