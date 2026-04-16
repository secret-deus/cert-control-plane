import { KeyRound, LockKeyhole, Network, Settings, ShieldCheck, Workflow } from 'lucide-react';

const settingGroups = [
  {
    title: '访问与认证',
    icon: KeyRound,
    tone: 'border-teal-300/15 bg-teal-500/10 text-teal-100',
    description: '控制谁可以进入控制台、谁可以接入 Agent 通道。',
    items: [
      { label: 'Admin API Key', value: '环境变量管理', note: '控制平面通过 `X-Admin-API-Key` 鉴权。' },
      { label: 'Agent Token', value: '独立通道', note: 'Agent API 使用单独鉴权，不与控制台登录混用。' },
      { label: 'TOFU 审批', value: '人工确认', note: '新 Agent 首次注册后需要审批通过。' },
    ],
  },
  {
    title: '密钥与证书安全',
    icon: LockKeyhole,
    tone: 'border-emerald-300/15 bg-emerald-500/10 text-emerald-100',
    description: '围绕私钥加密、证书托管和敏感信息处理。',
    items: [
      { label: '私钥存储', value: 'Fernet 加密', note: '上传证书后私钥在服务端加密存储。' },
      { label: '证书详情', value: '只读 PEM', note: '控制台只展示证书正文与链，不回显明文私钥。' },
      { label: '审计日志', value: '写操作留痕', note: '关键写操作通过统一审计链路记录。' },
    ],
  },
  {
    title: '分发与编排',
    icon: Workflow,
    tone: 'border-violet-300/15 bg-violet-500/10 text-violet-100',
    description: '管理 Rollout 节奏、批次推进和失败回滚策略。',
    items: [
      { label: 'Rollout Orchestrator', value: '后台轮询', note: '按服务端配置的轮询周期推进分发批次。' },
      { label: '批次控制', value: '灰度发布', note: '按 batch size 逐批下发证书，支持暂停与恢复。' },
      { label: '失败处理', value: '暂停 / 回滚', note: '异常批次进入失败态后可人工处理。' },
    ],
  },
  {
    title: '环境与网络',
    icon: Network,
    tone: 'border-amber-300/15 bg-amber-500/10 text-amber-100',
    description: '区分本地开发、生产部署和 API 入口路由。',
    items: [
      { label: '本地开发', value: '单端口模式', note: '本地默认走单端口，不经过 nginx。' },
      { label: '生产部署', value: '双入口模式', note: '控制平面与 Agent API 在生产环境分离入口。' },
      { label: '前端代理', value: '/api', note: 'Vite 开发代理默认转发到后端控制面。' },
    ],
  },
];

const roadmapCards = [
  {
    title: '可编辑设置表单',
    description: '后续接入后端设置 API 后，在这里统一管理安全策略、CORS 和 Rollout 参数。',
  },
  {
    title: '环境快照',
    description: '补充测试 / 生产的配置快照和变更对比。',
  },
  {
    title: '密钥轮换助手',
    description: '提供 Admin API Key 轮换、Agent Token 下发和审计回放入口。',
  },
];

export default function SettingsPage() {
  return (
    <div className="mx-auto max-w-[1480px] space-y-6 animate-fade-in">
      <section className="glass-panel p-5 lg:p-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <div className="section-kicker">Settings</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white">系统设置</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
              当前页面展示控制平面的只读设置摘要。后端还没有完整的前台编辑接口，所以这里先把认证、安全、编排和网络规则整理成统一视图。
            </p>
          </div>

          <div className="grid gap-2 text-sm xl:min-w-[320px]">
            <div className="rounded-md border border-teal-300/15 bg-teal-500/10 px-4 py-3 text-teal-100">
              <div className="text-xs uppercase tracking-[0.18em] text-teal-100/70">模式</div>
              <div className="mt-1 font-medium text-white">只读设置总览</div>
            </div>
            <div className="rounded-md border border-white/8 bg-white/[0.02] px-4 py-3 text-slate-400">
              配置仍以服务端环境变量和部署脚本为准，不在页面直接修改。
            </div>
          </div>
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        {settingGroups.map(({ title, icon: Icon, tone, description, items }) => (
          <section key={title} className="glass-panel p-5">
            <div className="flex items-start gap-4">
              <div className={`rounded-md border p-3 ${tone}`}>
                <Icon size={18} />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-white">{title}</h3>
                <p className="mt-1 text-sm leading-6 text-slate-500">{description}</p>
              </div>
            </div>

            <div className="mt-5 space-y-3">
              {items.map((item) => (
                <div key={item.label} className="rounded-md border border-white/8 bg-white/[0.02] p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-white">{item.label}</div>
                      <div className="mt-2 text-sm text-slate-300">{item.value}</div>
                    </div>
                    <span className="rounded-md border border-white/10 bg-white/[0.03] px-2 py-0.5 text-xs text-slate-500">只读</span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-500">{item.note}</p>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>

      <section className="glass-panel p-5">
        <div className="flex items-start gap-4">
          <div className="rounded-md border border-white/10 bg-white/[0.03] p-3 text-slate-200">
            <Settings size={18} />
          </div>
          <div>
            <div className="section-kicker">Planned</div>
            <h3 className="mt-2 text-lg font-semibold text-white">后续可接入的设置能力</h3>
            <p className="mt-1 text-sm leading-6 text-slate-500">先保留位置，等后端接口和权限模型完善后再接入可编辑能力。</p>
          </div>
        </div>

        <div className="mt-5 grid gap-3 lg:grid-cols-3">
          {roadmapCards.map((card) => (
            <div key={card.title} className="rounded-md border border-white/8 bg-white/[0.02] p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-white">
                <ShieldCheck size={15} className="text-teal-200" />
                {card.title}
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-500">{card.description}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
