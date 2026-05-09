import { Server } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

type AgentLiveness = 'online' | 'delayed' | 'offline';

interface Agent {
  id: string;
  name: string;
  description: string | null;
  status: string;
  fingerprint: string | null;
  last_seen: string | null;
  created_at: string;
  liveness: AgentLiveness | null;
  cert_count: number;
  expiring_soon_count: number;
}

const livenessConfig: Record<AgentLiveness, { label: string; color: string; bg: string; dot: string }> = {
  online: { label: '在线', color: 'text-[#9adf90]', bg: 'bg-[rgba(115,191,105,0.10)]', dot: 'bg-[#73bf69]' },
  delayed: { label: '延迟', color: 'text-[#ffbf8f]', bg: 'bg-[rgba(255,153,92,0.10)]', dot: 'bg-[#ff995c]' },
  offline: { label: '离线', color: 'text-[#ffbf8f]', bg: 'bg-[rgba(255,153,92,0.10)]', dot: 'bg-[#ff995c]' },
};

const statusConfig: Record<string, { label: string; color: string; bg: string }> = {
  active: { label: '活跃', color: 'text-[#9adf90]', bg: 'bg-[rgba(115,191,105,0.10)]' },
  pending_approval: { label: '待审批', color: 'text-[#ffbf8f]', bg: 'bg-[rgba(255,153,92,0.10)]' },
  revoked: { label: '已撤销', color: 'text-[#ffbf8f]', bg: 'bg-[rgba(255,153,92,0.10)]' },
};

function normalizeLiveness(value: string | null | undefined): AgentLiveness {
  if (value === 'online' || value === 'delayed' || value === 'offline') {
    return value;
  }
  return 'offline';
}

interface AgentTableProps {
  agents: Agent[];
  isLoading: boolean;
  activeAgentId: string | null;
  onSelectAgent: (id: string) => void;
}

export default function AgentTable({
  agents,
  isLoading,
  activeAgentId,
  onSelectAgent,
}: AgentTableProps) {
  return (
    <div className="glass-panel rounded-[24px] overflow-hidden">
      <div className="border-b border-white/6 px-5 py-4">
        <div className="section-kicker">Fleet Table</div>
        <h3 className="mt-2 text-lg font-semibold text-white">Agent 列表</h3>
        <p className="mt-1 text-sm text-white/50">表格负责扫描全局，右侧 dossier 负责看单节点细节。</p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/6 text-xs text-white/50">
              <th className="px-5 py-3 text-left font-medium">Agent</th>
              <th className="px-4 py-3 text-left font-medium">状态</th>
              <th className="px-4 py-3 text-left font-medium">证书覆盖</th>
              <th className="px-4 py-3 text-left font-medium">临近到期</th>
              <th className="px-4 py-3 text-left font-medium">最后心跳</th>
              <th className="px-5 py-3 text-left font-medium">动作</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 4 }).map((_, index) => (
                <tr key={index} className="table-row">
                  {Array.from({ length: 6 }).map((__, cellIndex) => (
                    <td key={cellIndex} className="px-4 py-4"><div className="skeleton h-4 rounded" /></td>
                  ))}
                </tr>
              ))
            ) : agents.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-5 py-14 text-center text-sm text-white/50">没有匹配的 Agent。</td>
              </tr>
            ) : (
              agents.map((agent) => {
                const liveness = normalizeLiveness(agent.liveness);
                const livenessState = livenessConfig[liveness];
                const statusState = statusConfig[agent.status] || { label: agent.status, color: 'text-slate-300', bg: 'bg-white/5' };
                const isSelected = activeAgentId === agent.id;

                return (
                  <tr
                    key={agent.id}
                    className={`table-row cursor-pointer ${isSelected ? 'bg-white/[0.05]' : ''}`}
                    onClick={() => onSelectAgent(agent.id)}
                  >
                    <td className="px-5 py-4">
                      <div className="flex items-start gap-3">
                        <div className="rounded-[14px] border border-white/8 bg-white/[0.03] p-2 text-white">
                          <Server size={16} />
                        </div>
                        <div>
                          <div className="font-medium text-white">{agent.name}</div>
                          <div className="mt-1 font-mono text-xs text-white/50">{agent.fingerprint ? `${agent.fingerprint.slice(0, 18)}...` : agent.id.slice(0, 18)}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-4">
                      <div className="space-y-2">
                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs ${statusState.bg} ${statusState.color}`}>{statusState.label}</span>
                        <div className="flex items-center gap-1.5 text-xs text-white/70">
                          <span className={`h-2 w-2 rounded-full ${livenessState.dot}`} />
                          {livenessState.label}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-4 text-white">{agent.cert_count}</td>
                    <td className="px-4 py-4 text-white/80">{agent.expiring_soon_count}</td>
                    <td className="px-4 py-4 text-xs text-white/50">
                      {agent.last_seen ? formatDistanceToNow(new Date(agent.last_seen), { addSuffix: true }) : '从未连接'}
                    </td>
                    <td className="px-5 py-4">
                      <button type="button" className="text-xs font-medium text-[#ffbf8f] hover:text-[#ffd0ad]">查看 dossier</button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}