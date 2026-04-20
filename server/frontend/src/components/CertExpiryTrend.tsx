import { useMemo } from 'react';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { AlertTriangle } from 'lucide-react';

interface CertExpiryTrendProps {
  data?: { date: string; count: number }[];
  isLoading?: boolean;
  totalCerts: number;
  within7Days: number;
  within30Days: number;
  pendingApprovals: number;
  runningRollouts: number;
  expiryDistribution?: { bucket: string; count: number; color: string }[];
}

function CustomTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { value: number; name?: string; payload?: { bucket: string } }[];
}) {
  if (!active || !payload?.length) {
    return null;
  }

  return (
    <div
      className="rounded-[12px] border border-white/8 px-3 py-2 text-xs shadow-xl"
      style={{ background: 'rgba(13,17,23,0.98)', backdropFilter: 'blur(8px)' }}
    >
      <div className="text-white/70">{payload[0].payload?.bucket}</div>
      <div className="font-medium text-white">{payload[0].value} 张证书</div>
    </div>
  );
}

export default function CertExpiryTrend({
  isLoading,
  totalCerts,
  within7Days,
  within30Days,
  pendingApprovals,
  runningRollouts,
  expiryDistribution,
}: CertExpiryTrendProps) {
  const chartData = useMemo(() => {
    if (expiryDistribution) return expiryDistribution;
    return [
      { bucket: '7天内', name: '7天内', count: within7Days, color: '#f2495c' },
      { bucket: '7-30天', name: '7-30天', count: within30Days - within7Days, color: '#f2cc0c' },
      { bucket: '30-60天', name: '30-60天', count: 0, color: '#5794f2' },
      { bucket: '60天以上', name: '60天以上', count: totalCerts - within30Days, color: '#73bf69' },
    ];
  }, [expiryDistribution, totalCerts, within7Days, within30Days]);

  if (isLoading) {
    return (
      <div className="glass-panel rounded-[24px] px-5 py-5 lg:px-6 lg:py-6">
        <div className="skeleton mb-4 h-6 w-40" />
        <div className="skeleton h-[320px] rounded-[24px]" />
      </div>
    );
  }

  return (
    <section className="glass-panel rounded-[24px] px-5 py-5 lg:px-6 lg:py-6">
      <div className="grid gap-5 xl:grid-cols-[250px_minmax(0,1fr)] xl:items-stretch">
        <div className="rounded-[22px] border border-white/6 bg-white/[0.02] px-5 py-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
          <div className="metric-badge border-white/8 bg-white/[0.03] text-white/80">Distribution</div>

          <div className="mt-8 text-[3rem] font-semibold leading-none text-white">{totalCerts}</div>
          <div className="mt-2 text-sm text-white/70">证书总数</div>

          <div className="mt-5 inline-flex items-center gap-2 text-sm text-[#9adf90]">
            <AlertTriangle size={15} />
            {within7Days > 0 ? `${within7Days} 张需关注` : '状态正常'}
          </div>

          <div className="mt-6 space-y-3 text-sm text-white/70">
            <div className="flex items-center justify-between rounded-[16px] border border-white/6 bg-white/[0.02] px-3 py-2.5">
              <span>7天内过期</span>
              <span className={`font-medium ${within7Days > 0 ? 'text-[#ff7383]' : 'text-white'}`}>{within7Days}</span>
            </div>
            <div className="flex items-center justify-between rounded-[16px] border border-white/6 bg-white/[0.02] px-3 py-2.5">
              <span>30天内过期</span>
              <span className={`font-medium ${within30Days > 0 ? 'text-[#ffb566]' : 'text-white'}`}>{within30Days}</span>
            </div>
            <div className="flex items-center justify-between rounded-[16px] border border-white/6 bg-white/[0.02] px-3 py-2.5">
              <span>待审批</span>
              <span className="font-medium text-white">{pendingApprovals}</span>
            </div>
            <div className="flex items-center justify-between rounded-[16px] border border-white/6 bg-white/[0.02] px-3 py-2.5">
              <span>运行批次</span>
              <span className="font-medium text-white">{runningRollouts}</span>
            </div>
          </div>
        </div>

        <div className="ops-chart-frame rounded-[22px] p-5" style={{ minHeight: 340 }}>
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="section-kicker">Expiry Distribution</div>
              <div className="mt-2 text-[1.1rem] font-semibold text-white">证书到期分布</div>
            </div>
            <div className="rounded-[16px] border border-white/8 bg-white/[0.03] p-3 text-white/70">
              <AlertTriangle size={16} />
            </div>
          </div>

          <div className="mt-5 flex flex-wrap gap-4 text-sm">
            <div className="inline-flex items-center gap-2 text-[#f2495c]">
              <span className="h-2 w-2 rounded-full bg-[#f2495c]" /> 7天内
            </div>
            <div className="inline-flex items-center gap-2 text-[#f2cc0c]">
              <span className="h-2 w-2 rounded-full bg-[#f2cc0c]" /> 7-30天
            </div>
            <div className="inline-flex items-center gap-2 text-[#5794f2]">
              <span className="h-2 w-2 rounded-full bg-[#5794f2]" /> 30-60天
            </div>
            <div className="inline-flex items-center gap-2 text-[#73bf69]">
              <span className="h-2 w-2 rounded-full bg-[#73bf69]" /> 60天以上
            </div>
          </div>

          <div className="mt-5 h-[250px]" style={{ minWidth: 0 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid vertical={false} stroke="rgba(148,163,184,0.10)" />
                <XAxis
                  dataKey="name"
                  stroke="#64748b"
                  tick={{ fill: '#64748b', fontSize: 12 }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  stroke="#64748b"
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  allowDecimals={false}
                />
            <Tooltip
              content={<CustomTooltip />}
              cursor={{ fill: 'rgba(255,255,255,0.04)' }}
              wrapperStyle={{ outline: 'none' }}
            />
                <Bar dataKey="count" name="证书数" radius={[6, 6, 0, 0]}>
                  {chartData.map((entry, index) => (
                    <Cell key={index} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </section>
  );
}
