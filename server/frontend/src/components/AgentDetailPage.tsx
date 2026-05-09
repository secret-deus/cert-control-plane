import { format, formatDistanceToNow } from 'date-fns';

type AgentLiveness = 'online' | 'delayed' | 'offline';

interface AgentCertDetail {
  local_path: string;
  cert_name: string;
  subject_cn: string;
  not_after: string;
  days_remaining: number;
  urgency: 'expired' | 'critical' | 'warning' | 'normal';
}

interface AgentDetailData {
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
  certs: AgentCertDetail[];
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

const certUrgencyTone: Record<AgentCertDetail['urgency'], string> = {
  expired: 'border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] text-[#ffbf8f]',
  critical: 'border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] text-[#ffbf8f]',
  warning: 'border-white/8 bg-white/[0.03] text-neutral-300',
  normal: 'border-[rgba(115,191,105,0.18)] bg-[rgba(115,191,105,0.10)] text-[#9adf90]',
};

function normalizeLiveness(value: string | null | undefined): AgentLiveness {
  if (value === 'online' || value === 'delayed' || value === 'offline') {
    return value;
  }
  return 'offline';
}

interface AgentDetailPageProps {
  agent: AgentDetailData | null;
  isLoading: boolean;
  error: string | null;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}

export default function AgentDetailPage({
  agent,
  isLoading,
  error,
  onApprove,
  onReject,
}: AgentDetailPageProps) {
  if (!agent) {
    return (
      <aside className="glass-panel rounded-[24px] self-start p-5 xl:sticky xl:top-6">
        <div>
          <div className="section-kicker">Agent Dossier</div>
          <h3 className="mt-2 text-lg font-semibold text-white">节点详情</h3>
          <p className="mt-1 text-sm text-white/50">查看心跳、指纹、接入状态和挂载证书。</p>
        </div>
        <div className="mt-6 rounded-lg border border-white/8 bg-white/[0.03] px-4 py-8 text-center text-sm text-white/50">从左侧选择一个 Agent 查看详情。</div>
      </aside>
    );
  }

  const liveness = normalizeLiveness(agent.liveness);
  const status = statusConfig[agent.status] || { label: agent.status, color: 'text-slate-300', bg: 'bg-white/5' };

  return (
    <aside className="glass-panel rounded-[24px] self-start p-5 xl:sticky xl:top-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="section-kicker">Agent Dossier</div>
          <h3 className="mt-2 text-lg font-semibold text-white">节点详情</h3>
          <p className="mt-1 text-sm text-white/50">查看心跳、指纹、接入状态和挂载证书。</p>
        </div>
        <span className="metric-badge border-white/8 bg-white/[0.03] text-white/80">{agent.certs.length} 证书</span>
      </div>

      {isLoading ? (
        <div className="mt-6 space-y-3">
          <div className="skeleton h-6 rounded" />
          <div className="skeleton h-20 rounded" />
          <div className="skeleton h-32 rounded" />
        </div>
      ) : error ? (
        <div className="mt-6 rounded-[20px] border border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] p-4 text-sm text-[#ffbf8f]">{error}</div>
      ) : (
        <div className="mt-6 space-y-5">
          <div>
            <div className="text-xl font-semibold text-white">{agent.name}</div>
            <div className="mt-1 text-sm text-white/70">{agent.description || '未填写描述'}</div>
            <div className="mt-3 flex flex-wrap gap-2">
              <span className={`rounded-full px-2 py-0.5 text-xs ${status.bg} ${status.color}`}>{status.label}</span>
              <span className={`rounded-full px-2 py-0.5 text-xs ${livenessConfig[liveness].bg} ${livenessConfig[liveness].color}`}>
                {livenessConfig[liveness].label}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
              <div className="text-xs text-white/50">最后心跳</div>
              <div className="mt-2 text-white">{agent.last_seen ? formatDistanceToNow(new Date(agent.last_seen), { addSuffix: true }) : '从未连接'}</div>
            </div>
            <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
              <div className="text-xs text-white/50">创建时间</div>
              <div className="mt-2 text-white">{format(new Date(agent.created_at), 'MM-dd HH:mm')}</div>
            </div>
            <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
              <div className="text-xs text-white/50">证书总数</div>
              <div className="mt-2 text-white">{agent.cert_count}</div>
            </div>
            <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
              <div className="text-xs text-white/50">30 天内到期</div>
              <div className="mt-2 text-white">{agent.expiring_soon_count}</div>
            </div>
          </div>

          <div className="rounded-lg border border-white/8 bg-white/[0.03] p-4">
            <div className="text-xs text-white/50">指纹</div>
            <div className="mt-2 break-all font-mono text-xs text-white/80">{agent.fingerprint || '未上报公钥指纹，可能仍处于 TOFU 注册阶段。'}</div>
          </div>

          {agent.status === 'pending_approval' && (
            <div className="flex gap-2">
              <button type="button" onClick={() => onApprove(agent.id)} className="btn-primary">批准接入</button>
              <button type="button" onClick={() => onReject(agent.id)} className="btn-danger">拒绝接入</button>
            </div>
          )}

          <div>
            <div className="mb-3 text-sm font-medium text-white">挂载证书</div>
            {agent.certs.length === 0 ? (
              <div className="rounded-lg border border-white/8 bg-white/[0.03] px-4 py-6 text-sm text-white/50">该节点还没有挂载证书。</div>
            ) : (
              <div className="space-y-2">
                {[...agent.certs]
                  .sort((left, right) => left.days_remaining - right.days_remaining)
                  .map((cert) => (
                    <div key={`${cert.local_path}-${cert.subject_cn}`} className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-medium text-white">{cert.subject_cn}</div>
                          <div className="mt-1 text-xs text-white/50">{cert.local_path}</div>
                        </div>
                        <span className={`rounded-full border px-2 py-0.5 text-xs ${certUrgencyTone[cert.urgency]}`}>{cert.urgency}</span>
                      </div>
                      <div className="mt-3 flex items-center justify-between text-xs text-white/70">
                        <span>{cert.cert_name}</span>
                        <span>{cert.days_remaining < 0 ? `已过期 ${Math.abs(cert.days_remaining)} 天` : `${cert.days_remaining} 天`}</span>
                      </div>
                    </div>
                  ))}
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}