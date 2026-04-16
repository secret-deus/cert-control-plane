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
  expired: { label: '已过期', color: 'text-red-400', bg: 'bg-red-500/10', icon: '🔴' },
  critical: { label: '7天内', color: 'text-red-400', bg: 'bg-red-500/10', icon: '🔴' },
  warning: { label: '30天内', color: 'text-yellow-400', bg: 'bg-yellow-500/10', icon: '🟡' },
  notice: { label: '提醒', color: 'text-teal-200', bg: 'bg-teal-500/10', icon: '🔵' },
  normal: { label: '正常', color: 'text-green-400', bg: 'bg-green-500/10', icon: '🟢' },
};

export default function AlertTable({ alerts, isLoading }: AlertTableProps) {
  if (isLoading) {
    return (
      <div className="glass-panel p-6">
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
    <div className="glass-panel p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="section-kicker">Risk Queue</div>
          <h3 className="mt-2 text-lg font-semibold text-white">证书风险列表</h3>
          <p className="mt-1 text-sm text-slate-400">优先处理临近到期或已经过期的证书，按风险等级排序。</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="metric-badge border-rose-400/15 bg-rose-500/10 text-rose-200">立即处理 {criticalAlerts.length}</span>
          <span className="metric-badge border-amber-400/15 bg-amber-500/10 text-amber-200">观察队列 {warningAlerts.length}</span>
          <span className="metric-badge border-white/10 bg-white/5 text-slate-300">总计 {sorted.length}</span>
        </div>
      </div>

      {sorted.length === 0 ? (
        <div className="py-10 text-center text-sm text-slate-500">暂无需要处理的证书告警。</div>
      ) : (
        <div className="mt-5 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/6 text-xs text-slate-500">
                <th className="py-3 px-3 text-left font-medium">风险</th>
                <th className="py-3 px-3 text-left font-medium">证书主体</th>
                <th className="py-3 px-3 text-left font-medium">来源</th>
                <th className="py-3 px-3 text-left font-medium">到期时间</th>
                <th className="py-3 px-3 text-left font-medium">剩余天数</th>
                <th className="py-3 px-3 text-left font-medium">Agent / 节点</th>
                <th className="py-3 px-3 text-left font-medium">建议动作</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((alert) => {
                const config = urgencyConfig[alert.urgency];
                return (
                  <tr key={alert.id} className="table-row align-top">
                    <td className="py-3 px-3">
                      <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${config.bg} ${config.color}`}>
                        {config.icon} {config.label}
                      </span>
                    </td>
                    <td className="py-3 px-3">
                      <div className="font-medium text-white">{alert.domain}</div>
                      <div className="mt-1 text-xs text-slate-500">证书对象 {alert.id.slice(0, 8)}</div>
                    </td>
                    <td className="py-3 px-3 text-slate-400">{alert.source || '控制平面'}</td>
                    <td className="py-3 px-3 text-slate-300">{format(new Date(alert.notAfter), 'yyyy-MM-dd')}</td>
                    <td className="py-3 px-3">
                      <span className={config.color}>
                        {alert.daysRemaining < 0
                          ? `已过期 ${Math.abs(alert.daysRemaining)} 天`
                          : alert.daysRemaining === 0
                            ? '今天到期'
                            : `${alert.daysRemaining} 天`}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-sm text-slate-400">
                      <div>{alert.agent || '未绑定 Agent'}</div>
                      <div className="mt-1 text-xs text-slate-500">{alert.machine || '未上报节点位置'}</div>
                    </td>
                    <td className="py-3 px-3 text-sm">
                      <span className="text-teal-200">
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
