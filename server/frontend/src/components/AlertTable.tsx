import { format } from 'date-fns';

interface AlertItem {
  id: string;
  domain: string;
  daysRemaining: number;
  urgency: 'expired' | 'critical' | 'warning' | 'notice' | 'normal';
  source?: string;
  machine?: string;
  agent?: string;
  notAfter: string;
}

interface AlertTableProps {
  alerts: AlertItem[];
  isLoading?: boolean;
}

const urgencyConfig: Record<string, { label: string; color: string; bg: string; icon: string }> = {
  expired: { label: '已过期', color: 'text-[#ff7383]', bg: 'bg-[rgba(242,73,92,0.14)]', icon: '🔴' },
  critical: { label: '7天内', color: 'text-[#ffb566]', bg: 'bg-[rgba(255,152,48,0.14)]', icon: '🟠' },
  warning: { label: '30天内', color: 'text-[#f6d94b]', bg: 'bg-[rgba(242,204,12,0.14)]', icon: '🟡' },
  notice: { label: '提醒', color: 'text-[#8fb8ff]', bg: 'bg-[rgba(87,148,242,0.14)]', icon: '🔵' },
  normal: { label: '正常', color: 'text-[#9adf90]', bg: 'bg-[rgba(115,191,105,0.14)]', icon: '🟢' },
};

export default function AlertTable({ alerts, isLoading }: AlertTableProps) {
  if (isLoading) {
    return (
      <div className="glass-panel p-5 lg:p-6">
        <div className="skeleton h-6 w-32 mb-4" />
        <div className="space-y-3">
          {[1, 2, 3].map((item) => <div key={item} className="skeleton h-10 rounded" />)}
        </div>
      </div>
    );
  }

  const criticalAlerts = alerts.filter((alert) => alert.urgency === 'expired' || alert.urgency === 'critical');
  const warningAlerts = alerts.filter((alert) => alert.urgency === 'warning');
  const severityOrder = { expired: 0, critical: 1, warning: 2, notice: 3, normal: 4 };
  const sorted = [...criticalAlerts, ...warningAlerts]
    .sort((left, right) => {
      const urgencyGap = severityOrder[left.urgency] - severityOrder[right.urgency];
      if (urgencyGap !== 0) {
        return urgencyGap;
      }
      return left.daysRemaining - right.daysRemaining;
    })
    .slice(0, 20);

  return (
    <div className="glass-panel rounded-[24px] p-5 lg:p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="section-kicker">Risk Queue</div>
          <h3 className="mt-2 text-lg font-semibold text-white">证书风险列表</h3>
          <p className="mt-1 text-sm text-slate-500">优先处理临近到期或已经过期的证书，按风险等级排序。</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="metric-badge border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] text-[#ffbf8f]">立即处理 {criticalAlerts.length}</span>
          <span className="metric-badge border-white/8 bg-white/[0.03] text-neutral-300">观察队列 {warningAlerts.length}</span>
          <span className="metric-badge border-white/8 bg-white/[0.03] text-neutral-300">总计 {sorted.length}</span>
        </div>
      </div>

      {sorted.length === 0 ? (
        <div className="ops-chart-frame mt-5 py-10 text-center text-sm text-slate-500">暂无需要处理的证书告警。</div>
      ) : (
        <div className="ops-chart-frame mt-5 overflow-x-auto rounded-[22px]">
          <table className="w-full text-sm">
            <thead className="bg-white/[0.02]">
              <tr className="border-b border-white/6 text-[11px] uppercase tracking-[0.14em] text-slate-500">
                <th className="px-3 py-3 text-left font-medium">风险</th>
                <th className="px-3 py-3 text-left font-medium">证书主体</th>
                <th className="px-3 py-3 text-left font-medium">来源</th>
                <th className="px-3 py-3 text-left font-medium">到期时间</th>
                <th className="px-3 py-3 text-left font-medium">剩余天数</th>
                <th className="px-3 py-3 text-left font-medium">Agent / 节点</th>
                <th className="px-3 py-3 text-left font-medium">建议动作</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((alert) => {
                const config = urgencyConfig[alert.urgency];
                return (
                  <tr key={alert.id} className="table-row align-top">
                    <td className="px-3 py-3.5">
                      <span className={`inline-flex items-center gap-1.5 rounded-full border border-white/6 px-2.5 py-1 text-xs font-medium ${config.bg} ${config.color}`}>
                        {config.icon} {config.label}
                      </span>
                    </td>
                    <td className="px-3 py-3.5">
                      <div className="font-medium text-white">{alert.domain}</div>
                      <div className="mt-1 text-xs text-slate-500">证书对象 {alert.id.slice(0, 8)}</div>
                    </td>
                    <td className="px-3 py-3.5 text-slate-400">{alert.source || '控制平面'}</td>
                    <td className="px-3 py-3.5 text-slate-300">{format(new Date(alert.notAfter), 'yyyy-MM-dd')}</td>
                    <td className="px-3 py-3.5">
                      <span className={`font-medium ${config.color}`}>
                        {alert.daysRemaining < 0
                          ? `已过期 ${Math.abs(alert.daysRemaining)} 天`
                          : alert.daysRemaining === 0
                            ? '今天到期'
                            : `${alert.daysRemaining} 天`}
                      </span>
                    </td>
                    <td className="px-3 py-3.5 text-sm text-slate-400">
                      <div>{alert.agent || '未绑定 Agent'}</div>
                      <div className="mt-1 text-xs text-slate-500">{alert.machine || '未上报节点位置'}</div>
                    </td>
                    <td className="px-3 py-3.5 text-sm">
                      <span className="font-medium text-[#8fb8ff]">
                        {alert.urgency === 'expired' || alert.urgency === 'critical' ? '优先续期并重发' : '纳入本周续期计划'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
