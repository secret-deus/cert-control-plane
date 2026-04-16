import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { TrendingUp } from 'lucide-react';

interface CertExpiryTrendProps {
  data: { date: string; count: number }[];
  isLoading?: boolean;
}

function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-zinc-800 border border-white/10 rounded-lg px-3 py-2 text-xs">
      <div className="text-zinc-400 mb-1">{label}</div>
      <div className="text-white font-medium">{payload[0].value} 个证书即将过期</div>
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
      <div className="flex items-center gap-2 mb-4">
        <TrendingUp size={18} className="text-blue-400" />
        <h3 className="text-base font-semibold text-white">证书到期趋势</h3>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis
            dataKey="date"
            stroke="#71717a"
            tick={{ fill: '#71717a', fontSize: 11 }}
            tickLine={false}
          />
          <YAxis
            stroke="#71717a"
            tick={{ fill: '#71717a', fontSize: 11 }}
            tickLine={false}
            allowDecimals={false}
          />
          <Tooltip content={<CustomTooltip />} />
          <Line
            type="monotone"
            dataKey="count"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={{ fill: '#3b82f6', r: 3 }}
            activeDot={{ r: 5, fill: '#3b82f6' }}
            name="即将过期"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}