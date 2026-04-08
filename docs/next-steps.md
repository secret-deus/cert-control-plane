# 下一步行动计划

## 当前状态
- ✅ Sprint 3 完成
- ✅ M3 里程碑完成
- ✅ M4 准备工作完成
- 📝 16 个本地提交待推送

## 立即可执行的任务

### 1. 代码推送和发布准备

#### 推送到远程仓库
```bash
# 查看待推送的提交
git log origin/master..HEAD --oneline

# 推送到远程
git push origin master

# 或者创建 PR 进行代码审查
git checkout -b feature/sprint3-completion
git push origin feature/sprint3-completion
# 然后在 GitHub 创建 Pull Request
```

#### 创建版本标签
```bash
# 创建带注释的标签
git tag -a v0.2.0 -m "Release v0.2.0 - Sprint 3 completion and M4 preparation"

# 推送标签
git push origin v0.2.0
```

### 2. CI/CD 验证

#### 触发 CI 流程
推送代码后会自动触发：
- ✅ 后端测试
- ✅ 前端构建
- ✅ 前端 E2E 测试
- ✅ Agent 构建

#### 触发安全扫描
推送代码后会自动触发：
- ✅ Python 依赖扫描
- ✅ NPM 依赖扫描
- ✅ 容器漏洞扫描
- ✅ 代码安全分析
- ✅ 密钥扫描

#### 检查 CI 结果
```bash
# 使用 GitHub CLI 检查
gh run list --limit 5
gh run view
```

### 3. 性能测试执行

#### 准备测试环境
```bash
# 进入性能测试目录
cd tools/performance

# 安装依赖
pip install locust httpx
```

#### 运行基准测试
```bash
# 快速测试 (1 分钟，50 用户)
python run_all_tests.py --duration 1m --users 50 --host https://localhost:443

# 标准测试 (5 分钟，100 用户)
python run_all_tests.py --duration 5m --users 100 --host https://localhost:443

# 压力测试 (10 分钟，500 用户)
python run_all_tests.py --duration 10m --users 500 --host https://localhost:443
```

#### 分析测试结果
```bash
# 查看生成的报告
open results/heartbeat_test_*/report.html
open results/cert_sync_test_*/report.html
```

### 4. 预生产部署

#### 准备部署环境
按照 `docs/pre-production-checklist.md` 执行：

1. **代码质量检查**
   ```bash
   python3 -m pytest tests/ -v
   ruff check app/ agent/ tests/
   ```

2. **配置验证**
   ```bash
   # 检查环境变量
   cat .env | grep -v "^#" | grep -v "^$"

   # 测试数据库连接
   psql $DATABASE_URL -c "SELECT version();"
   ```

3. **部署执行**
   ```bash
   # 备份数据库
   pg_dump $DATABASE_URL > backup_$(date +%Y%m%d_%H%M%S).sql

   # 部署服务
   docker-compose down
   docker-compose up -d --build

   # 验证部署
   curl -k https://localhost:443/healthz
   ```

### 5. 文档发布

#### 更新 GitHub Pages（如配置）
```bash
# 推送文档到 gh-pages 分支
git checkout -b gh-pages
# 构建文档
git push origin gh-pages
```

#### 发布 Release Notes
```bash
# 使用 GitHub CLI 创建 release
gh release create v0.2.0 \
  --title "v0.2.0 - Sprint 3 Completion" \
  --notes-file docs/release-template.md \
  --draft
```

## 优先级排序

### 高优先级（今天完成）
1. ✅ 推送代码到远程仓库
2. ✅ 检查 CI 结果
3. ✅ 修复任何 CI 失败

### 中优先级（本周完成）
1. 运行性能基准测试
2. 分析性能测试结果
3. 执行预生产部署验证

### 低优先级（下周完成）
1. 创建正式 release
2. 发布 Agent 二进制
3. 更新用户文档

## 检查清单

### 推送前检查
- [ ] 确认所有测试通过
- [ ] 确认无敏感信息泄露
- [ ] 确认文档已更新
- [ ] 确认 CHANGELOG 已更新

### 推送后检查
- [ ] CI 流程全部通过
- [ ] 安全扫描无高危问题
- [ ] E2E 测试通过
- [ ] Agent 构建成功

### 部署前检查
- [ ] 性能测试达标
- [ ] 预生产检查清单全部完成
- [ ] 备份策略已配置
- [ ] 监控告警已配置

## 常用命令速查

```bash
# 查看 CI 状态
gh run list
gh run view <run-id>

# 查看安全扫描结果
gh run view --log | grep -i "vulnerability\|security"

# 本地运行测试
python3 -m pytest tests/ -v

# 本地运行 lint
ruff check app/ agent/ tests/

# 构建前端
cd frontend && npm run build

# 构建 Agent
cd agent-go && go build ./cmd/cert-agent

# 查看日志
docker-compose logs -f app

# 检查服务状态
docker-compose ps
curl -k https://localhost:443/healthz
```

## 故障排查

### CI 失败
1. 查看失败日志: `gh run view <run-id>`
2. 本地复现: 按照错误信息本地运行相同命令
3. 修复并推送: `git commit --amend && git push -f`

### 安全扫描发现漏洞
1. 查看详情: 在 GitHub Security tab
2. 评估严重程度: Critical/High 必须修复
3. 更新依赖: `pip install --upgrade <package>`
4. 验证修复: 重新运行扫描

### 性能测试未达标
1. 分析报告: 查看 HTML 报告找出瓶颈
2. 性能调优: 参考 `docs/deployment-production.md`
3. 重新测试: 调整参数后再次运行

## 下一步

建议按以下顺序执行：

1. **立即执行**：推送代码并检查 CI
2. **今天完成**：确认所有自动化流程正常
3. **本周完成**：性能测试和预生产部署
4. **准备发布**：创建 v0.2.0 正式 release

---

准备好开始了吗？从推送代码开始！
