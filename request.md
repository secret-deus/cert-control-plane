这个需求挺清晰的，本质是一个「证书资产管理 + 分发 + 监控」平台，我给你直接按**可落地的运维系统思路**出几套前端原型（偏偏你这种 DevOps 场景，重点是信息密度和操作效率）。

我按你说的三个模块来：
👉 监控聚合面板 / 证书面板 / Agent面板
每个都给你一个“可直接让前端照着做”的原型结构。

---

# 一、整体布局（通用骨架）

![Image](https://images.openai.com/static-rsc-4/Btxgh0aYVQUYWjUkTrf5MdV3DIqd_6iE1S5KNueRB7030sdieH-Jxhr_h_vnE4nOGPoLMgEgu7kutfbsodUKJe8qvdX9UIVDwWdqanF-Pf49Dnx6kI7PxZWZ70cLrJzvT6eKeaxDxG604Qr3JZZpyfSs-ir6tQWXbqUccurphaxzxe9mVoo-6Liu_Hf4uEcc?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/v6K_uf68M7bxouVHp1Cxuu1IMRhtPE29J7xfX4lwcVnGAGuLJq4CWuyJMXu4XkCUdFdkFMXr38W8CLn312RE-z854x57l-6NeQa1blPoEhsTfKczhoAsg7IqNUaK__uV5tgWW-_A8_KT8iwzUJPLEe5NwUhx1sPdtU_ySEWCei7aCT-IZCnDadsLl6pqXq9p?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/AhHtqB-ilGbti-9_5D2MFeJwmmSdrVI7KqZYqgKduejw6VZYZNFR8FtBz487B3_J2KAWliM6I2ti_82stePl39yx3_eJZ9uaDqdxwBUGY1wNZWBAtXVJ64536xnKimarACLGdrqCUwlKoKlWgzlgRTz6V0aQzr174OJM_1hATjmuOaWoGnTep5hdv3bZk8JN?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/wHgIsmK4LP0_fAw0bWxB7KjXz0By4uvZZkwduzCHdSoSHPmZEfCaxYPG1BL_3GGZOElWvG71xhrc-caG2HGCHgKbQq2qRnDDiGdh7ZQEeW-ylaLsQlaEj2m0p_2jpwFe3Kpye_fyWNKvj3qbINka5I3TmQZYsY3zjD0NvHyLWWuwB5eVvhm8zN9QeRUzXvLs?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/hqKXFbvlexjwdTC92aZ0-t9wXMdmnRZ3ehLH5J8BC7ecQwdd0tesL2puU5Wgo48q9VdKYAYMJO-562XRTdKIQSdzoevRg5uHDQGiJVYpuAEDhH1xk6TEwmIsJzWCM3ZWGn2R8foacDPoILoGgOQ2ql4ha_JDKaAqV48BlWFNmh30l9QD4gZsus7GRVNFiwDX?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/7fzhEbkW_RdeyaejXS-p_YxcWnZgKZMDfc7HK1UiNDEbXQUnAAQ1V7wJXjQToCQAzG2QFI7i_u9ncLq7jEO1daHPVV1QzmXfkZrs3ZO5ledPA4YQshFKgVSR5W0mAmRTYmszTJqe05ulAH_g6_1_bx5h2BNcnMQkiPE1RJ3B_ia2xG_Sv6-zDPfaM-kaGfD9?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/JlI-8G51Br5s9HaPpR0ZIMfWtTZBux25q7YWH7AiZPBKF6Gh5iVYV53b4dh_01iOyNAmmklZapDfteud6LjmpyhuLWuJ_J9OuyIJmrgNyHKyvyX3wQZTjQk8gaX9RK4D70OPyCCysMaG3XfQNwH8kLX-JfEE7JNUf0ceCnqTkeVscvxREOutETcRMLMAby2u?purpose=fullsize)

### 布局结构（建议）

* 左侧：导航栏（固定）

  * 监控面板
  * 证书管理
  * Agent管理
  * 系统设置（预留）
* 顶部：

  * 搜索 / 环境切换（prod / test）
  * 告警红点
  * 用户信息
* 主内容区：动态切换

👉 风格建议：

* 深色（类似 Grafana / K8s Dashboard）
* 高密度卡片 + 表格为主（你这种场景不适合花里胡哨）

---

# 二、监控聚合面板（核心价值页）

![Image](https://images.openai.com/static-rsc-4/-PwV4uK-b5Nvuqnu7EfuRRbYVjaUkjZHIrUNEby6JUBDNluXgOlRkaC-nFqPRIaobvx9_xGwlqCy_I0m4mzG7CZ1HLwdwwEevDuRAqNi5Y1nVY03G6gcutGFjZmvTqKlSsQrRfKHweZLtejI4e7fpCOUloZrL9A7YNsRpFQOYrJqVjXs3wq9_Njj0i0p7fOT?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/zJWj4jD-vfgcxUkZDVjIjHwiFp-UQQlKPNlBbjFrcKd7hd8WJKaKN6nHxRVMZarWuvuQBTzTg8nBbBGGmXcVfS8sxQy1Cfr8ZZtaPC9faTz317Eo1mBNn87S2-hW85zHNvzW0QC_uuxRnmLO2PFUi_yYztCRC5oc0x21dfCE3Yax-Hm2tiV1Gf5GZpdsNvKD?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/W0L2GHeg8GVobW5Vac-NI1tthgWEIM4XcIjW7yWlIdlBYoH2675GRAnI-kdZjoSQwAN-mz6xlrXpqObjBfSS2Ia0zbZg4esNC6CBx5n1lYjmN0GF-e2nONJDaNfL5yVQcEnOkYGSCo0yotgEx9GEquiQ9jlTjmkdFWg9L9Chr2sxz8L3CRwIMUTl5mnFOnI-?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/Rcv9K3FisfbT_dml1jYbfOtzGaWLyHl4WCVqeqwk4WC1lw0XN5a08t3BGNC3VqtcqBBVV9qPHZq0ltXU9Bapg9nicnsBDJ4Whjz4Csr7n5olWtt8ewOJqzkgcLrK_rtw0AjzaNkwAyeMlUthOF0xVTT4jMV_ZJc9oiq2jkjbLd-ibpnDU8nXmxZCv-L75em0?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/DwwmpmBFQ9JcFYUs9fxIPhfdgQ18DdSBoYqgOGldX26nGMxA0GMLg49J3_TZSWJbtAd8aDG040MCx013xFkO39PRG3URt_TwEHzLNvbGVqQEnDPndHzl55uQNpjGoAKlpAIWFArKhBroATKH-7YJk0ntkhWFmSB6Yuz9uc48CXjq6T5p8p6RglcV1e-8N3_l?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/4EblF_qTs369VO8IquXhGav1hXHB14BGf2aohO0Yd-YTDXOsZSR31R2xPsB46yJGx5YSQLNGh1qp-Sx9hgTjdOC7giH4xY-sPMMt9OJulp5KWrFxjg-mgeEnJxNGSj0j0VjUt21OqCN3DIhQ8Vjk5jllqSRO8ow8eKh3cTwCEt-v5tOhTGL8FdNpHn1elbFN?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/xt9qrGE84DLAv79mV0sAgGfINl77OgTIyOFrx1cgtj9bwZvTcIMGcsDaxCpcISHvHXhEkq0xc0NwLLO-LUk7d7B3mUkwEd15vdsJwhDpdAoRiFWztTsUViTcw9PlC3efrgxBBO02krTz1xTWEDz6jFG19NLYObwxOmGsAflal1xmw3YF_4iEhBp8tL3m4vS9?purpose=fullsize)

## 页面结构

### 1️⃣ 顶部 KPI 卡片

```
[证书总数] [7天内过期] [30天内过期] [异常节点] [在线Agent]
```

👉 示例：

* 证书总数：128
* 7天内过期：3（红）
* Agent在线：42/50

---

### 2️⃣ 证书过期趋势（图表）

* 折线图：

  * X轴：时间
  * Y轴：即将过期数量
* 可选：

  * 按域名分类
  * 按业务线分类

---

### 3️⃣ 告警列表（重点）

表格：

| 状态 | 域名          | 到期时间 | 所在机器     | Agent    | 操作 |
| -- | ----------- | ---- | -------- | -------- | -- |
| 🔴 | api.xxx.com | 2天   | 10.1.1.1 | agent-01 | 续期 |
| 🟡 | *.xxx.com   | 10天  | 多节点      | agent-02 | 查看 |

---

### 4️⃣ Agent健康状态

卡片式：

```
agent-01  ✅ 在线  CPU:30%  同步OK
agent-02  ❌ 离线  最后心跳: 10m前
```

---

# 三、证书面板（核心操作页）

![Image](https://images.openai.com/static-rsc-4/pIHtmFIhC-heeYlQMFs_p89_MauqT0aN5l6eBA9DCSzMX35jcLKn0sYvAMvpHmR0cFxHFPMfM9dYH-xRUf6FdJyv3uqy4ZsCSzTM-B5xh61JypUyCKzKnHQZ3Flz17eiV0FCr36oqY-zEh7rZ7e_segWnTRbih2QUzvPBYuRJDAD-qGYoaxIn9oEy6zMWQLx?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/vqORB4YxguXoboeBnzpMBvXrUO7tFGhbMHKs1NLfCd7T_ZXOEZ19PjOMI0HA71SzYrmCVGwJS2NgM3CNyfiqeD0_2pSIWUWkOl4068poJOJsMWGz8P1d_TbXO2x1Dvi-CXE3bOVKkjJ64xorqbCtmop23TbXfdr9XJaAa_7bIXdj9aSdi0nf0v8JQsrNAdkc?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/DkIDL2qxo2HdSpCB7n35r779pAhI2DxlF_3XucO09PV6fU0IDuKprm6xKhu5ybpxs2ZhSIZLFLyCcRiPb6_cfjivowPZRoitt84Z4wDb40RclGUavcGhAMcbduM5aFvqEenZQYYJ_lbinMOghjRiDgBD1sLs9mmgPyV5KkiYYTtuDo8feJi4BtWrHNECqd_8?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/ex0bDu2GfbPHWLnGDWkOeyzWM3n-7hUFwvVKzdEALh8CVhsVwwVqXVWMZIiqqw39IfHQLhxGyjNvwqiOMh3f3BHidFe3GCCHwzgLbooFLthYBE0CqUEqMHXyAp1y68qpIaB32pGTPZ46agRi6OO4hjZSUwrU631P4JiOkaQzQ9iQCZ-H0qc1tWzOh24BeJh4?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/dmbw_fCm9KprfX4TmlmUIftPebD7_DlOueWA8JUJ1v7G7iH_JYYcsAOK6LxKej_O56eVRJDjFXgIF67DZl8eIgzt4svipmbj-JgLTAAzYU53JsCbTsV_H2mxHv7lV3QAATS16FNjDlw8fGoB1OmhFxHdWmvZKGaJkBcSjPDrL4iRWGVtSPI1TVnSmPInlBtd?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/mtkdJoeAxzwS0VaNGmiD_oSmHUFdTxbRjNdckCqcEwwvCiMENVQnBH_Xf7JbuBRmGz1eWAq59WFMMYT5oVAElBUocWe2uRk8qDbA0ja0Vne895i2AzXIcRZ_3EluLGq2irFJSy4DEtQCjok9o9vX1sJQ14en7Ux8Ya6ymv9JkFDeP6BneYyddGdEwI_YglkY?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/vq9toLhWzkPF1Ae4vbMN5dwWzSlzLvwHIDh6TuNjFhSiKs9a_MqbI8qj54_ERulPVrnDmL8eg6njCIhzeKOhqogOatBsg-CdE9-zRDGCK0eeOg-EMuTI0bthNmfLCkgkfsKTZCsPgyVJwWp-dX-FP8bbWgPm2KlHq13q-OQiAxyjQIbZvJy8RRU33miAzXEa?purpose=fullsize)

## 页面结构

### 1️⃣ 筛选区

```
[域名搜索] [证书状态] [过期时间范围] [业务线] [环境]
```

---

### 2️⃣ 主表（重点）

| 域名          | 类型  | 过期时间       | 剩余天数 | 绑定节点 | 状态 | 操作    |
| ----------- | --- | ---------- | ---- | ---- | -- | ----- |
| api.xxx.com | 单域名 | 2026-05-01 | 15天  | 5台   | 正常 | 查看/续期 |
| *.xxx.com   | 泛域名 | 2026-04-20 | 3天   | 12台  | ⚠️ | 续期    |

👉 状态颜色：

* 绿色：>30天
* 黄色：7~30天
* 红色：<7天

---

### 3️⃣ 操作按钮（很关键）

* ➕ 新增证书
* 🔄 手动续期
* 🚀 分发证书（核心）
* 📥 导入证书
* 📤 导出

---

### 4️⃣ 证书详情抽屉

点击一行展开：

```
- 证书内容（PEM）
- 私钥（隐藏/显示）
- 分发历史
- 绑定的 nginx 节点
- 最近同步状态
```

---

# 四、Agent面板（运维核心）

![Image](https://images.openai.com/static-rsc-4/tEbi68L74cJwbCCOOmCg-Y_sKfWvS_3uewRDNRkBpi62UR91AkIPI32hMQMUE6vHNgSxLYR89p6MVgWywqjfn1NkU1vKPrl-4XSWyTKoTl-SWCKO0TOj74CiuPg2UhNjy2zd8HOCVNwUHg764oVy1AqKaaMTNimAzP7M65QClNgFNERS9NllpceBpk09Sk-U?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/MJX0rG2OpVcn8CokAnWDcwhMMlcaRCiBlgaHMwmCX-TVDd7V-0CaxVmw7OJ-u0atMy0kl4isyqvjrssQ03p7Q7i29l0Cujxo0Wejtmlwd3GzibG-w72u24a-j_jMU3-keMwDXZycd6UNzTl4-BbFZ9jJeOOQLW_1wAhZL_1lbcUjs418M2rrP3vGrLELXSWF?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/fMB8f5-O53qztjvWzcJ0ned39yOoSfe4YmvY7fgNo2SHKR1qBhpE9MIKQnVSyNBZEat55qYJ-rvNpeQKLgZs4ATtOfS7A0CyLFKYMnI6MA4rd8V2Ygafwzrzt1C4xmZOV0wT_DnJ868cOwyp8r72lV6CY1jdXgbjqz2ZB-7GKrdXwTjxbTOS_MthBbDt3QHS?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/KMEAyIX1r26CA2mAkmH9mOCgrEX-5ksbUqgdOKuElNYsw5Ae_eVtkCAumu_yr6V8_2cNMVNHGCe-T52QSz5BflmF_MUGRUcm5-bhF9RrE10b-wYi9_K-Eooz_3D9WN_cxwMLACOHQILUg8d86L1CDrLCvwLFkIrE1Jtusg5luqr7d7pAF1eSBdXvNzmok7f1?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/BsfgabfoUdcNU4w7hoDnOrrFg6X9Tbbo3mhM2czgOSsk47-dd2cAP8IahAmGyQpoXfeqIHhaTxpfzAadviscV5pMJCT2_xyUh7o5tHLmMFNqpC9Ip4ZFUGA5wZqQ-Ev2nTh_nzInI-eQ5xsWJNxzeMh1E1iYi9307bSe6QCLlcAmwN8-PVIGLmphY_oNxsSK?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/Bnfqw7WxqdeWIs3jxRYT9imUgBrEt0JxfMDElXuECptmWjPfHsoDlI4DA_q_yIJJP8tosj1qFSagwBuhQwEGKwVAcO_NKyiEOsE5A4aHtqiVjf_P_wGmhoZAIRXlDh-K7rl4x3aB_hUx8FCJxqeeHI6iM4rVfGui4A1crS9eCjEXW1JlbEJ-aRtZHrSLrTcN?purpose=fullsize)

## 页面结构

### 1️⃣ Agent列表

| AgentID  | IP       | 状态   | 版本   | 最后心跳 | 证书数 | 操作 |
| -------- | -------- | ---- | ---- | ---- | --- | -- |
| agent-01 | 10.1.1.1 | ✅ 在线 | v1.2 | 5s前  | 12  | 详情 |
| agent-02 | 10.1.1.2 | ❌ 离线 | v1.1 | 10m前 | 8   | 修复 |

---

### 2️⃣ 状态展示（卡片/图）

* 在线 / 离线统计
* 心跳延迟分布
* 同步失败率

---

### 3️⃣ Agent详情页

```
基础信息：
- IP / hostname
- 所属环境

运行状态：
- CPU / 内存
- Nginx状态
- 最近证书同步日志

操作：
- 🔄 强制同步证书
- 📜 查看日志
- ⚙️ 升级Agent
```

---

# 五、进阶（你这个系统建议一定要加）

### 1️⃣ 分发链路视图（很适合你现有架构）

```
域名 → SLB → Nginx → Agent
```

👉 你之前做的“域名 → SLB → Ingress 映射”，这里可以直接复用

---

### 2️⃣ 自动化策略

* 自动续期（Let’s Encrypt / 内部CA）
* 到期前自动分发
* 灰度发布证书（分批 agent）

---

### 3️⃣ 告警集成

* webhook（你已经有 Alertmanager）
* 钉钉 / Slack

---

# 六、技术栈建议（结合你现状）

你现在是：

* Vue + Vite + TS + Vant + UnoCSS

👉 我建议你这样做：

* UI：

  * element-plus（表格很强）
  * 或 naive-ui（更现代）

* 图表：

  * echarts（足够）
  * 或直接接 Grafana 思路

* 状态管理：

  * pinia

---

# 七、如果你要更狠一点（我建议）

你这个系统可以直接升级为：

👉 **证书+流量入口统一控制台**

融合：

* Nginx
* Ingress
* 证书
* SLB

基本就是你在做一个 mini：
👉 Kubernetes Dashboard + 证书系统

---

# 最后

如果你愿意，我可以帮你直接再往下一步走：

👉 给你出一版：

* **完整前端页面 JSON schema（直接给前端用）**
* 或 **Vue3 + element-plus 页面代码骨架**
* 或 **接口设计（后端API + agent协议）**

你现在这个方向，其实已经是一个“可做成内部平台甚至产品”的东西了。
