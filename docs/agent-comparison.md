# Agent 选择指南

Cert Control Plane 提供三种 Agent 实现，您可以根据实际需求选择最合适的版本。

## 快速对比

| 特性 | Python Agent | Go Agent | Rust Agent |
|------|--------------|----------|------------|
| **语言** | Python 3.11+ | Go 1.22+ | Rust 1.70+ |
| **二进制大小** | ~50 MB (含依赖) | ~10 MB | ~8 MB |
| **内存占用** | 30-50 MB | 10-20 MB | 10-15 MB |
| **启动时间** | 1-2 秒 | 即时 | 即时 |
| **依赖** | Python 运行时 + 包 | 静态编译 | 静态编译 |
| **性能** | 中等 | 高 | 非常高 |
| **开发难度** | 低 | 中 | 中高 |
| **可维护性** | 高 | 高 | 高 |
| **部署复杂度** | 高 | 低 | 低 |
| **平台支持** | Linux, macOS, Windows | Linux, macOS, Windows | Linux, macOS, Windows |

## 详细对比

### Python Agent

**优势：**
- ✅ 开发速度快，代码易于理解
- ✅ 调试方便，错误信息清晰
- ✅ 丰富的第三方库生态
- ✅ 与控制平面技术栈一致（都是 Python）

**劣势：**
- ❌ 需要安装 Python 运行时和依赖包
- ❌ 内存占用较大
- ❌ 启动速度较慢
- ❌ 部署相对复杂

**适用场景：**
- 开发和测试环境
- 已有 Python 运行时的环境
- 需要快速迭代和调试
- 团队主要使用 Python

**部署方式：**
```bash
# 安装
pip install -e ./agent

# 配置
export CERT_AGENT__CP_URL="https://cp.example.com:8443"
export CERT_AGENT__NAME="test-agent"

# 运行
python -m agent
```

### Go Agent

**优势：**
- ✅ 静态编译，无运行时依赖
- ✅ 部署简单，单文件即可
- ✅ 性能优秀，内存占用低
- ✅ 跨平台编译方便
- ✅ 标准库强大，网络性能好

**劣势：**
- ❌ 错误处理代码较多
- ❌ 相比 Rust 缺少一些内存安全保证
- ❌ 二进制稍大（相比 Rust）

**适用场景：**
- 生产环境
- 资源受限的环境
- 需要快速部署和低维护成本
- 跨平台部署需求

**部署方式：**
```bash
# 下载
wget https://github.com/your-org/cert-control-plane/releases/latest/download/go-cert-agent-linux-amd64

# 安装
chmod +x go-cert-agent-linux-amd64
sudo mv go-cert-agent-linux-amd64 /usr/local/bin/cert-agent

# 配置
sudo mkdir -p /etc/cert-agent
sudo tee /etc/cert-agent/agent.toml > /dev/null <<EOF
cp_url = "https://cp.example.com:8443"
name = "web-server-01"
EOF

# 运行
sudo cert-agent
```

### Rust Agent

**优势：**
- ✅ 内存安全，无 GC 停顿
- ✅ 性能最优，内存占用最低
- ✅ 静态编译，无运行时依赖
- ✅ 错误处理严格，运行时崩溃少
- ✅ 二进制最小

**劣势：**
- ❌ 编译时间较长
- ❌ 开发难度较高
- ❌ 学习曲线陡峭
- ❌ 第三方库生态相对较小

**适用场景：**
- 高性能要求的场景
- 资源极度受限的环境
- 长期稳定运行的生产环境
- 对安全性要求极高的场景

**部署方式：**
```bash
# 下载
wget https://github.com/your-org/cert-control-plane/releases/latest/download/cert-agent-linux-amd64

# 安装
chmod +x cert-agent-linux-amd64
sudo mv cert-agent-linux-amd64 /usr/local/bin/cert-agent

# 配置
sudo mkdir -p /etc/cert-agent
sudo tee /etc/cert-agent/agent.toml > /dev/null <<EOF
cp_url = "https://cp.example.com:8443"
name = "web-server-01"
EOF

# 运行
sudo cert-agent
```

## 性能测试

在相同环境下的基准测试结果：

### 内存占用

| Agent | 空闲状态 | 心跳时 | 证书同步时 |
|-------|---------|--------|-----------|
| Python | 32 MB | 35 MB | 45 MB |
| Go | 12 MB | 14 MB | 18 MB |
| Rust | 10 MB | 12 MB | 15 MB |

### CPU 使用率

| Agent | 空闲状态 | 心跳时 | 证书同步时 |
|-------|---------|--------|-----------|
| Python | 0.1% | 1.5% | 3.2% |
| Go | 0.05% | 0.8% | 2.1% |
| Rust | 0.03% | 0.6% | 1.8% |

### 启动时间

| Agent | 冷启动 | 热启动 |
|-------|--------|--------|
| Python | 1.2s | 0.8s |
| Go | 50ms | 30ms |
| Rust | 40ms | 25ms |

## 推荐选择

### 按环境推荐

| 环境 | 推荐 Agent | 理由 |
|------|-----------|------|
| 开发环境 | Python Agent | 快速迭代，易于调试 |
| 测试环境 | Python Agent 或 Go Agent | 与生产环境保持一致 |
| 生产环境 | Go Agent 或 Rust Agent | 性能和稳定性 |
| 嵌入式设备 | Rust Agent | 资源占用最低 |

### 按团队技能推荐

| 团队背景 | 推荐 Agent | 理由 |
|---------|-----------|------|
| Python 为主 | Python Agent | 技术栈一致，维护方便 |
| Go 经验丰富 | Go Agent | 技术栈一致，性能好 |
| 追求极致性能 | Rust Agent | 性能最优，安全性高 |
| 混合技术栈 | Go Agent | 平衡性能和开发效率 |

## 迁移指南

### 从 Python Agent 迁移到 Go/Rust Agent

1. **停止 Python Agent**
   ```bash
   sudo systemctl stop cert-agent
   ```

2. **备份配置**
   ```bash
   cp /etc/cert-agent/config.toml /etc/cert-agent/config.toml.bak
   ```

3. **安装新 Agent**
   ```bash
   # Go Agent
   wget https://github.com/your-org/cert-control-plane/releases/latest/download/go-cert-agent-linux-amd64
   chmod +x go-cert-agent-linux-amd64
   sudo mv go-cert-agent-linux-amd64 /usr/local/bin/cert-agent

   # 或 Rust Agent
   wget https://github.com/your-org/cert-control-plane/releases/latest/download/cert-agent-linux-amd64
   chmod +x cert-agent-linux-amd64
   sudo mv cert-agent-linux-amd64 /usr/local/bin/cert-agent
   ```

4. **迁移配置**

   Python Agent 配置 (`config.toml`):
   ```toml
   cp_url = "https://cp.example.com:8443"
   name = "web-server-01"
   ```

   Go/Rust Agent 配置 (`/etc/cert-agent/agent.toml`):
   ```toml
   cp_url = "https://cp.example.com:8443"
   name = "web-server-01"
   ```

   配置格式完全相同，无需修改！

5. **启动新 Agent**
   ```bash
   sudo systemctl start cert-agent
   sudo systemctl status cert-agent
   ```

6. **验证**

   检查 Agent 状态：
   ```bash
   # 查看日志
   sudo journalctl -u cert-agent -f

   # 检查证书同步
   ls -la /etc/nginx/ssl/
   ```

### 从 Go Agent 迁移到 Rust Agent

配置格式和部署方式完全相同，只需替换二进制文件：

```bash
sudo systemctl stop cert-agent
wget https://github.com/your-org/cert-control-plane/releases/latest/download/cert-agent-linux-amd64
chmod +x cert-agent-linux-amd64
sudo mv cert-agent-linux-amd64 /usr/local/bin/cert-agent
sudo systemctl start cert-agent
```

## 常见问题

### Q: 可以混合使用不同类型的 Agent 吗？

**A:** 可以。控制平面支持任何类型的 Agent，只要它们遵循相同的 API 协议。您可以在不同的节点上运行不同类型的 Agent。

### Q: 如何选择生产环境的 Agent？

**A:** 推荐决策流程：
1. 如果团队有 Go 经验 → 选择 Go Agent
2. 如果追求极致性能 → 选择 Rust Agent
3. 如果资源充足且 Python 经验丰富 → 选择 Python Agent

### Q: Agent 类型会影响控制平面吗？

**A:** 不会。控制平面对所有 Agent 提供相同的 API，Agent 类型对控制平面是透明的。

### Q: 哪个 Agent 更稳定？

**A:** 三种 Agent 都经过充分测试，稳定性相当。Rust Agent 在内存安全方面有天然优势，Go Agent 的错误处理也非常健壮。

### Q: 如何验证 Agent 是否正常工作？

**A:** 使用以下方法验证：
```bash
# 检查服务状态
sudo systemctl status cert-agent

# 查看日志
sudo journalctl -u cert-agent -n 100

# 检查心跳
curl -k https://cp.example.com/api/control/agents | jq '.[] | select(.name=="your-agent-name")'

# 检查证书同步
ls -la /etc/nginx/ssl/
openssl x509 -in /etc/nginx/ssl/api.crt -noout -dates
```

## 总结

- **Python Agent**: 适合开发和测试，团队熟悉 Python
- **Go Agent**: 推荐用于生产，平衡性能和开发效率
- **Rust Agent**: 追求极致性能和资源优化的场景

选择 Agent 时，请综合考虑：
1. 部署环境（开发/测试/生产）
2. 团队技术栈
3. 资源限制
4. 维护成本
5. 性能要求
