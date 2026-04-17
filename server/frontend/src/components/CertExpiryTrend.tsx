import { useMemo } from 'react';
import { Line, LineChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { TrendingUp } from 'lucide-react';

interface CertExpiryTrendProps {
  data: { date: string; count: number }[];
  isLoading?: boolean;
  totalCerts: number;
  within7Days: number;
  within30Days: number;
  pendingApprovals: number;
  runningRollouts: number;
}

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { value: number; name?: string }[];
  label?: string;
}) {
  if (!active || !payload?.length) {
    return null;
  }

  return (
    <div className="rounded-xl border border-white/10 bg-[#161a21]/95 px-3 py-2 text-xs shadow-xl backdrop-blur">
      <div className="mb-1 text-slate-400">{label}</div>
      {payload.map((item) => (
        <div key={item.name} className="font-medium text-white">
          {item.name}: {item.value}
        </div>
      ))}
    </div>
  );
}

export default function CertExpiryTrend({
  data,
  isLoading,
  totalCerts,
  within7Days,
  within30Days,
  pendingApprovals,
  runningRollouts,
}: CertExpiryTrendProps) {
  const chartData = useMemo(
    () =>
      data.map((item, index, all) => {
        const prev = all[index - 1]?.count ?? item.count;
        const next = all[index + 1]?.count ?? item.count;
        const baseline = Math.round((prev + item.count + next) / 3);

        return {
          ...item,
          baseline,
        };
      }),
    [data]
  );

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
          <div className="metric-badge border-white/8 bg-white/[0.03] text-neutral-300">90D</div>

          <div className="mt-8 text-[3rem] font-semibold leading-none text-white">{within30Days}</div>
          <div className="mt-2 text-sm text-slate-400">30 天内需要关注</div>

          <div className="mt-5 inline-flex items-center gap-2 text-sm text-[#9adf90]">
            <TrendingUp size={15} />
            On track
          </div>

          <div className="mt-6 space-y-3 text-sm text-slate-400">
              <div className="flex items-center justify-between rounded-[16px] border border-white/6 bg-white/[0.02] px-3 py-2.5">
                <span>证书总数</span>
                <span className="font-medium text-white">{totalCerts}</span>
              </div>
            <div className="flex items-center justify-between rounded-[16px] border border-white/6 bg-white/[0.02] px-3 py-2.5">
                <span>7 天内过期</span>
                <span className="font-medium text-[#ffb566]">{within7Days}</span>
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

        {chartData.length === 0 ? (
          <div className="ops-chart-frame flex h-[340px] items-center justify-center rounded-[24px] text-sm text-slate-500">
            暂无未来 90 天到期数据。
          </div>
        ) : (
          <div className="ops-chart-frame rounded-[22px] p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="section-kicker">Expiry Window</div>
                <div className="mt-2 text-[1.1rem] font-semibold text-white">未来 90 天到期趋势</div>
              </div>
              <div className="rounded-[16px] border border-white/8 bg-white/[0.03] p-3 text-slate-400">
                <TrendingUp size={16} />
              </div>
            </div>

            <div className="mt-5 flex flex-wrap gap-4 text-sm">
              <div className="inline-flex items-center gap-2 text-[#ff9830]">
                <span className="h-2 w-2 rounded-full bg-[#ff9830]" />
                实时趋势
              </div>
              <div className="inline-flex items-center gap-2 text-slate-300">
                <span className="h-2 w-2 rounded-full bg-slate-300" />
                平滑基线
              </div>
            </div>

            <div className="mt-5 h-[250px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid vertical={false} stroke="rgba(148,163,184,0.10)" />
                  <XAxis
                    dataKey="date"
                    stroke="#64748b"
                    tick={{ fill: '#64748b', fontSize: 11 }}
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
                  <Tooltip content={<CustomTooltip />} />
                  <Line type="monotone" dataKey="baseline" name="基线" stroke="#e5e7eb" strokeWidth={2.4} dot={false} activeDot={false} />
                  <Line type="monotone" dataKey="count" name="趋势" stroke="#ff9830" strokeWidth={2.8} dot={{ fill: '#ff9830', r: 3 }} activeDot={{ r: 6, fill: '#ff9830' }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
