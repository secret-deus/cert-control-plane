import { format } from 'date-fns';

interface AlertItem {
  id: string;
  domain: string;
  daysRemaining: number;
  urgency: 'expired' | 'critical' | 'warning' | 'notice' | 'normal';
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
  notice: { label: '提醒', color: 'text-blue-400', bg: 'bg-blue-500/10', icon: '🔵' },
  normal: { label: '正常', color: 'text-green-400', bg: 'bg-green-500/10', icon: '🟢' },
};

export default function AlertTable({ alerts, isLoading }: AlertTableProps) {
  if (isLoading) {
    return (
      <div className="glass-panel p-6">
        <div className="skeleton h-6 w-32 mb-4" />
        <div className="space-y-3">
          {[1, 2, 3].map(i => <div key={i} className="skeleton h-10 rounded" />)}
        </div>
      </div>
    );
  }

  const criticalAlerts = alerts.filter(a => a.urgency === 'expired' || a.urgency === 'critical');
  const warningAlerts = alerts.filter(a => a.urgency === 'warning');
  const sorted = [...criticalAlerts, ...warningAlerts].slice(0, 20);

  return (
    <div className="glass-panel p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-semibold text-white">告警列表</h3>
        <span className="text-xs text-zinc-500">{sorted.length} 条告警</span>
      </div>

      {sorted.length === 0 ? (
        <div className="text-center py-8 text-zinc-500 text-sm">暂无告警</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-zinc-500 text-xs border-b border-white/5">
                <th className="text-left py-2 px-3 font-medium">状态</th>
                <th className="text-left py-2 px-3 font-medium">域名</th>
                <th className="text-left py-2 px-3 font-medium">到期时间</th>
                <th className="text-left py-2 px-3 font-medium">剩余</th>
                <th className="text-left py-2 px-3 font-medium">所在机器</th>
                <th className="text-left py-2 px-3 font-medium">Agent</th>
                <th className="text-left py-2 px-3 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map(alert => {
                const config = urgencyConfig[alert.urgency];
                return (
                  <tr key={alert.id} className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                    <td className="py-2.5 px-3">
                      <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${config.bg} ${config.color}`}>
                        {config.icon} {config.label}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-white font-medium">{alert.domain}</td>
                    <td className="py-2.5 px-3 text-zinc-400">{format(new Date(alert.notAfter), 'yyyy-MM-dd')}</td>
                    <td className="py-2.5 px-3">
                      <span className={config.color}>
                        {alert.daysRemaining < 0
                          ? `已过期 ${Math.abs(alert.daysRemaining)} 天`
                          : alert.daysRemaining === 0
                          ? '今天到期'
                          : `${alert.daysRemaining} 天`}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-zinc-500">{alert.machine || '—'}</td>
                    <td className="py-2.5 px-3 text-zinc-400">{alert.agent || '—'}</td>
                    <td className="py-2.5 px-3">
                      <button className="text-xs text-blue-400 hover:text-blue-300 transition-colors">
                        {alert.urgency === 'expired' || alert.urgency === 'critical' ? '续期' : '查看'}
                      </button>
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