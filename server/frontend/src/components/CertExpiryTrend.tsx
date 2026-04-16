import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { TrendingUp } from 'lucide-react';

interface CertExpiryTrendProps {
  data: { date: string; count: number }[];
  isLoading?: boolean;
}

function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) {
  if (!active || !payload?.length) {
    return null;
  }

  return (
    <div className="rounded-md border border-white/10 bg-slate-900/95 px-3 py-2 text-xs shadow-xl">
      <div className="mb-1 text-slate-400">{label}</div>
      <div className="font-medium text-white">{payload[0].value} 个证书将在该时间点到期</div>
    </div>
  );
}

export default function CertExpiryTrend({ data, isLoading }: CertExpiryTrendProps) {
  if (isLoading) {
    return (
      <div className="glass-panel p-6">
        <div className="skeleton h-6 w-40 mb-4" />
        <div className="skeleton h-48 rounded" />
      </div>
    );
  }

  return (
    <div className="glass-panel p-6">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <div className="section-kicker">Expiry Window</div>
          <div className="mt-2 flex items-center gap-2">
            <TrendingUp size={18} className="text-teal-200" />
            <h3 className="text-lg font-semibold text-white">未来 90 天到期趋势</h3>
          </div>
          <p className="mt-1 text-sm text-slate-400">按到期日期聚合证书数量，帮助提前安排续期和分发节奏。</p>
        </div>
        <span className="metric-badge border-teal-300/15 bg-teal-500/10 text-teal-100">{data.length} 个时间点</span>
      </div>

      {data.length === 0 ? (
        <div className="flex h-[240px] items-center justify-center rounded-lg border border-white/6 bg-white/[0.02] text-sm text-slate-500">
          暂无未来 90 天到期数据。
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={data}>
            <defs>
              <linearGradient id="expiryFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#6f9a92" stopOpacity={0.32} />
                <stop offset="100%" stopColor="#6f9a92" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.12)" />
            <XAxis
              dataKey="date"
              stroke="#64748b"
              tick={{ fill: '#64748b', fontSize: 11 }}
              tickLine={false}
            />
            <YAxis
              stroke="#64748b"
              tick={{ fill: '#64748b', fontSize: 11 }}
              tickLine={false}
              allowDecimals={false}
            />
            <Tooltip content={<CustomTooltip />} />
            <Area
              type="monotone"
              dataKey="count"
              stroke="#6f9a92"
              strokeWidth={2}
              fill="url(#expiryFill)"
              dot={{ fill: '#6f9a92', r: 3 }}
              activeDot={{ r: 5, fill: '#6f9a92' }}
              name="即将过期"
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
