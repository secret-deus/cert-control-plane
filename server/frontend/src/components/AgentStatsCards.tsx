import { AlertTriangle, CheckCircle2, Clock, XCircle } from 'lucide-react';

interface AgentStatsCardsProps {
  online: number;
  offline: number;
  pending: number;
  delayed: number;
}

export default function AgentStatsCards({ online, offline, pending, delayed }: AgentStatsCardsProps) {
  const cards = [
    { label: '在线', value: online, icon: CheckCircle2, tone: 'border-white/8 bg-white/[0.03] text-white' },
    { label: '离线', value: offline, icon: XCircle, tone: 'border-white/8 bg-white/[0.03] text-white' },
    { label: '待审批', value: pending, icon: Clock, tone: 'border-white/8 bg-white/[0.03] text-white' },
    { label: '延迟', value: delayed, icon: AlertTriangle, tone: 'border-white/8 bg-white/[0.03] text-white' },
  ];

  return (
    <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map(({ label, value, icon: Icon, tone }) => (
        <div key={label} className={`rounded-[20px] border p-4 ${tone}`}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-xs uppercase tracking-[0.18em] text-white/60">{label}</div>
              <div className="mt-2 text-2xl font-semibold text-white">{value}</div>
            </div>
            <div className="rounded-lg border border-white/10 bg-white/5 p-2.5 text-white">
              <Icon size={16} />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}