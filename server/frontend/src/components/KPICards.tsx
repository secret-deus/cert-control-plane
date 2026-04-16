import { CheckCircle2, AlertOctagon, AlertTriangle, Wifi } from 'lucide-react';

interface KPICardsProps {
  totalCerts: number;
  criticalCount: number;
  warningCount: number;
  errorNodes: number;
  onlineAgents: number;
  totalAgents: number;
}

const cards = [
  { key: 'total', label: '证书总数', icon: CheckCircle2, color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/20' },
  { key: 'critical', label: '7天内过期', icon: AlertOctagon, color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/20' },
  { key: 'warning', label: '30天内过期', icon: AlertTriangle, color: 'text-yellow-400', bg: 'bg-yellow-500/10', border: 'border-yellow-500/20' },
  { key: 'errorNodes', label: '异常节点', icon: AlertTriangle, color: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/20' },
  { key: 'agents', label: '在线Agent', icon: Wifi, color: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/20' },
] as const;

export default function KPICards({ totalCerts, criticalCount, warningCount, errorNodes, onlineAgents, totalAgents }: KPICardsProps) {
  const values: Record<string, string | number> = {
    total: totalCerts,
    critical: criticalCount,
    warning: warningCount,
    errorNodes,
    agents: `${onlineAgents}/${totalAgents}`,
  };

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
      {cards.map(({ key, label, icon: Icon, color, bg, border }) => (
        <div key={key} className={`glass-panel p-4 border ${border}`}>
          <div className="flex items-center gap-3 mb-2">
            <div className={`p-2 rounded-lg ${bg}`}>
              <Icon size={18} className={color} />
            </div>
            <span className="text-xs text-zinc-400">{label}</span>
          </div>
          <div className={`text-2xl font-bold ${color === 'text-blue-400' ? 'text-white' : color.replace('400', '300')}`}>
            {values[key]}
          </div>
        </div>
      ))}
    </div>
  );
}