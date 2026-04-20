import { format } from 'date-fns';

interface CertItem {
  id: string;
  domain: string;
  daysRemaining: number;
  urgency: 'expired' | 'critical' | 'warning' | 'notice' | 'normal';
  source?: string;
  agent?: string;
  notAfter: string;
  provider?: string;
}

interface CertTableProps {
  certs: CertItem[];
  isLoading?: boolean;
}

const urgencyConfig: Record<string, { label: string; color: string; bg: string }> = {
  expired: { label: '已过期', color: 'text-[#ff7383]', bg: 'bg-[rgba(242,73,92,0.14)]' },
  critical: { label: '7天内', color: 'text-[#ffb566]', bg: 'bg-[rgba(255,152,48,0.14)]' },
  warning: { label: '30天内', color: 'text-[#f6d94b]', bg: 'bg-[rgba(242,204,12,0.14)]' },
};

const defaultConfig = { label: '正常', color: 'text-white/70', bg: 'bg-white/[0.04]' };

export default function CertTable({ certs, isLoading }: CertTableProps) {
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

  const expiredCerts = certs.filter((c) => c.urgency === 'expired');
  const criticalCerts = certs.filter((c) => c.urgency === 'critical');
  const warningCerts = certs.filter((c) => c.urgency === 'warning');
  const riskCerts = [...expiredCerts, ...criticalCerts, ...warningCerts];
  const sorted = riskCerts
    .sort((a, b) => a.daysRemaining - b.daysRemaining);

  return (
    <div className="glass-panel rounded-[24px] p-5 lg:p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="section-kicker">Certificate Alerts</div>
          <h3 className="mt-2 text-lg font-semibold text-white">证书到期告警</h3>
          <p className="mt-1 text-sm text-white/50">30天内即将到期的证书，按紧急程度排序。</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {expiredCerts.length > 0 && (
            <span className="metric-badge border-[rgba(242,73,92,0.18)] bg-[rgba(242,73,92,0.10)] text-[#ff7383]">已过期 {expiredCerts.length}</span>
          )}
          {criticalCerts.length > 0 && (
            <span className="metric-badge border-[rgba(255,152,48,0.18)] bg-[rgba(255,152,48,0.10)] text-[#ffb566]">7天内 {criticalCerts.length}</span>
          )}
          {warningCerts.length > 0 && (
            <span className="metric-badge border-[rgba(242,204,12,0.18)] bg-[rgba(242,204,12,0.10)] text-[#f6d94b]">30天内 {warningCerts.length}</span>
          )}
          {sorted.length === 0 && (
            <span className="metric-badge border-white/8 bg-white/[0.03] text-[#9adf90]">无告警</span>
          )}
        </div>
      </div>

      {sorted.length === 0 ? (
        <div className="ops-chart-frame mt-5 py-10 text-center text-sm text-white/50">
          暂无即将到期的证书，所有证书状态正常。
        </div>
      ) : (
        <div className="ops-chart-frame mt-5 overflow-x-auto rounded-[22px]">
          <table className="w-full text-sm">
            <thead className="bg-white/[0.02]">
              <tr className="border-b border-white/6 text-[11px] uppercase tracking-[0.14em] text-white/50">
                <th className="px-3 py-3 text-left font-medium">状态</th>
                <th className="px-3 py-3 text-left font-medium">证书主体</th>
                <th className="px-3 py-3 text-left font-medium">来源</th>
                <th className="px-3 py-3 text-left font-medium">到期时间</th>
                <th className="px-3 py-3 text-left font-medium">剩余天数</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((cert) => {
                const config = urgencyConfig[cert.urgency] || defaultConfig;
                return (
                  <tr key={cert.id} className={`table-row align-top ${cert.urgency === 'expired' ? 'bg-[rgba(242,73,92,0.06)]' : cert.urgency === 'critical' ? 'bg-[rgba(255,152,48,0.04)]' : ''}`}>
                    <td className="px-3 py-3.5">
                      <span className={`inline-flex items-center rounded-full border border-white/6 px-2.5 py-1 text-xs font-medium ${config.bg} ${config.color}`}>
                        {config.label}
                      </span>
                    </td>
                    <td className="px-3 py-3.5">
                      <div className="font-medium text-white">{cert.domain}</div>
                      <div className="mt-1 text-xs text-white/50">ID {cert.id.slice(0, 8)}</div>
                    </td>
                    <td className="px-3 py-3.5 text-white/70">{cert.provider || '手动上传'}</td>
                    <td className="px-3 py-3.5 text-white/80">{format(new Date(cert.notAfter), 'yyyy-MM-dd')}</td>
                    <td className="px-3 py-3.5">
                      <span className={`font-medium ${config.color}`}>
                        {cert.daysRemaining < 0
                          ? `已过期 ${Math.abs(cert.daysRemaining)} 天`
                          : cert.daysRemaining === 0
                            ? '今天到期'
                            : `${cert.daysRemaining} 天`}
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
