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
          {[1, 2, 3].map((item) => <div key={item} className="skeleton h-16 rounded-lg" />)}
        </div>
      </div>
    );
  }

  const counts = {
    online: agents.filter((agent) => agent.liveness === 'online').length,
    delayed: agents.filter((agent) => agent.liveness === 'delayed').length,
    offline: agents.filter((agent) => agent.liveness === 'offline').length,
  };
  const severityRank = { offline: 0, delayed: 1, online: 2 };
  const sortedAgents = [...agents]
    .sort((left, right) => severityRank[left.liveness] - severityRank[right.liveness])
    .slice(0, 6);

  return (
    <div className="glass-panel p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="section-kicker">Fleet Health</div>
          <h3 className="mt-2 text-lg font-semibold text-white">Agent 健康矩阵</h3>
          <p className="mt-1 text-sm text-slate-400">优先显示离线和心跳延迟的节点，方便先处理薄弱环节。</p>
        </div>
        <div className="metric-badge border-white/10 bg-white/5 text-slate-300">总数 {agents.length}</div>
      </div>

      <div className="mt-5 grid grid-cols-3 gap-3">
        {[
          { label: '在线', value: counts.online, tone: 'border-emerald-400/15 bg-emerald-500/10 text-emerald-200' },
          { label: '延迟', value: counts.delayed, tone: 'border-amber-400/15 bg-amber-500/10 text-amber-200' },
          { label: '离线', value: counts.offline, tone: 'border-rose-400/15 bg-rose-500/10 text-rose-200' },
        ].map((item) => (
          <div key={item.label} className={`rounded-lg border px-3 py-3 ${item.tone}`}>
            <div className="text-xs uppercase tracking-[0.18em] text-white/70">{item.label}</div>
            <div className="mt-2 text-2xl font-semibold text-white">{item.value}</div>
          </div>
        ))}
      </div>

      <div className="mt-5 space-y-2 max-h-[420px] overflow-y-auto">
        {agents.length === 0 ? (
          <div className="py-10 text-center text-sm text-slate-500">暂无 Agent。</div>
        ) : (
          sortedAgents.map((agent) => {
            const cfg = livenessConfig[agent.liveness];
            return (
              <div key={agent.id} className="rounded-lg border border-white/8 bg-white/[0.03] p-4 transition-colors hover:border-white/12 hover:bg-white/[0.05]">
                <div className="flex items-start gap-3">
                  <div className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${cfg.dot}`} />
                  <Server size={16} className="mt-0.5 shrink-0 text-slate-500" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="truncate text-sm font-medium text-white">{agent.name}</div>
                        <div className="mt-1 text-xs text-slate-500">{agent.lastSeen ? `${agent.lastSeen}` : '从未连接'}</div>
                      </div>
                      <span className={`rounded-full px-2 py-0.5 text-xs ${cfg.bg} ${cfg.color}`}>{cfg.label}</span>
                    </div>
                    {agent.certExpiresAt && (
                      <div className="mt-3 text-xs text-slate-400">
                        最近证书到期日 {new Date(agent.certExpiresAt).toLocaleDateString('zh-CN')}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
