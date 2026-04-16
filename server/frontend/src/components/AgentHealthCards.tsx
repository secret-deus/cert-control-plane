import { Server } from 'lucide-react';

interface AgentHealthItem {
  id: string;
  name: string;
  liveness: 'online' | 'delayed' | 'offline';
  lastSeen: string | null;
  certExpiresAt: string | null;
}

interface AgentHealthCardsProps {
  agents: AgentHealthItem[];
  isLoading?: boolean;
}

const livenessConfig = {
  online: { label: '在线', dot: 'bg-green-400', bg: 'bg-green-500/10', color: 'text-green-400' },
  delayed: { label: '延迟', dot: 'bg-yellow-400', bg: 'bg-yellow-500/10', color: 'text-yellow-400' },
  offline: { label: '离线', dot: 'bg-red-400', bg: 'bg-red-500/10', color: 'text-red-400' },
};

export default function AgentHealthCards({ agents, isLoading }: AgentHealthCardsProps) {
  if (isLoading) {
    return (
      <div className="glass-panel p-6">
        <div className="skeleton h-6 w-32 mb-4" />
        <div className="space-y-3">
          {[1, 2, 3].map(i => <div key={i} className="skeleton h-16 rounded-lg" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="glass-panel p-6">
      <h3 className="text-base font-semibold text-white mb-4">Agent 健康状态</h3>
      <div className="space-y-2 max-h-[400px] overflow-y-auto">
        {agents.length === 0 ? (
          <div className="text-center py-8 text-zinc-500 text-sm">暂无 Agent</div>
        ) : (
          agents.map(agent => {
            const cfg = livenessConfig[agent.liveness];
            return (
              <div key={agent.id} className="flex items-center gap-3 p-3 rounded-lg bg-white/[0.02] hover:bg-white/[0.04] transition-colors">
                <div className={`w-2 h-2 rounded-full ${cfg.dot} shrink-0`} />
                <Server size={16} className="text-zinc-500 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-white font-medium truncate">{agent.name}</div>
                  <div className="text-xs text-zinc-500">
                    {agent.lastSeen ? `${agent.lastSeen}` : '从未连接'}
                  </div>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full ${cfg.bg} ${cfg.color}`}>
                  {cfg.label}
                </span>
                {agent.certExpiresAt && (
                  <span className="text-xs text-zinc-500">
                    证书: {new Date(agent.certExpiresAt).toLocaleDateString()}
                  </span>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}