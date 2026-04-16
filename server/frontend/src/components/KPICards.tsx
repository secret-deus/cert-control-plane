import { CircleAlert, ShieldCheck, TriangleAlert, Wifi, type LucideIcon } from 'lucide-react';

interface KPICardsProps {
  totalCerts: number;
  criticalCount: number;
  warningCount: number;
  errorNodes: number;
  onlineAgents: number;
  totalAgents: number;
}

export default function KPICards({ totalCerts, criticalCount, warningCount, errorNodes, onlineAgents, totalAgents }: KPICardsProps) {
  const onlineRate = totalAgents > 0 ? Math.round((onlineAgents / totalAgents) * 100) : 0;
  const cards: Array<{
    key: string;
    label: string;
    value: string | number;
    hint: string;
    progress: number;
    icon: LucideIcon;
    iconTone: string;
    barTone: string;
  }> = [
    {
      key: 'total',
      label: '证书资产',
      value: totalCerts,
      hint: '控制台正在托管的全部证书。',
      progress: totalCerts > 0 ? 100 : 16,
      icon: ShieldCheck,
      iconTone: 'border-teal-300/15 bg-teal-500/10 text-teal-100',
      barTone: 'from-teal-300 to-teal-500',
    },
    {
      key: 'critical',
      label: '7 天内到期',
      value: criticalCount,
      hint: criticalCount > 0 ? '优先续期或立即触发分发。' : '没有临近到期的高危项。',
      progress: totalCerts > 0 ? Math.min(100, Math.max(12, (criticalCount / totalCerts) * 100)) : 12,
      icon: CircleAlert,
      iconTone: 'border-rose-300/15 bg-rose-500/10 text-rose-200',
      barTone: 'from-rose-300 to-rose-500',
    },
    {
      key: 'warning',
      label: '30 天窗口',
      value: warningCount,
      hint: warningCount > 0 ? '建议提前进入续期排期。' : '未来 30 天风险压力较低。',
      progress: totalCerts > 0 ? Math.min(100, Math.max(12, (warningCount / totalCerts) * 100)) : 12,
      icon: TriangleAlert,
      iconTone: 'border-amber-300/15 bg-amber-500/10 text-amber-200',
      barTone: 'from-amber-300 to-orange-500',
    },
    {
      key: 'errorNodes',
      label: '异常节点',
      value: errorNodes,
      hint: errorNodes > 0 ? '包含离线或心跳延迟的 Agent。' : '节点存活状态稳定。',
      progress: totalAgents > 0 ? Math.min(100, Math.max(12, (errorNodes / totalAgents) * 100)) : 12,
      icon: TriangleAlert,
      iconTone: 'border-orange-300/15 bg-orange-500/10 text-orange-200',
      barTone: 'from-orange-300 to-orange-500',
    },
    {
      key: 'agents',
      label: 'Agent 覆盖率',
      value: `${onlineAgents}/${totalAgents}`,
      hint: totalAgents > 0 ? `在线率 ${onlineRate}%` : '暂无接入的 Agent。',
      progress: Math.max(12, onlineRate),
      icon: Wifi,
      iconTone: 'border-emerald-300/15 bg-emerald-500/10 text-emerald-200',
      barTone: 'from-emerald-300 to-emerald-500',
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
      {cards.map(({ key, label, value, hint, progress, icon: Icon, iconTone, barTone }) => (
        <div key={key} className="glass-panel overflow-hidden p-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="section-kicker">{label}</div>
              <div className="mt-3 text-3xl font-semibold tracking-tight text-white">{value}</div>
              <p className="mt-2 text-sm leading-6 text-slate-400">{hint}</p>
            </div>
            <div className={`rounded-md border p-3 ${iconTone}`}>
              <Icon size={18} />
            </div>
          </div>

          <div className="mt-5 h-1.5 rounded-full bg-white/5">
            <div
              className={`h-full rounded-full bg-gradient-to-r ${barTone}`}
              style={{ width: `${Math.min(100, Math.max(10, progress))}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
