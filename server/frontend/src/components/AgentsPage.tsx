import { useCallback, useDeferredValue, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, Clock, Plus, RefreshCw, Search, Server, XCircle } from 'lucide-react';
import { format, formatDistanceToNow } from 'date-fns';
import { useNavigate, useParams } from 'react-router-dom';
import { apiDelete, apiFetch, apiPost } from '../lib/api';

interface PaginatedResponse<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}

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

interface AgentCertDetail {
  local_path: string;
  cert_name: string;
  subject_cn: string;
  not_after: string;
  days_remaining: number;
  urgency: 'expired' | 'critical' | 'warning' | 'normal';
}

interface AgentDetail extends Agent {
  certs: AgentCertDetail[];
}

const livenessConfig: Record<AgentLiveness, { label: string; color: string; bg: string; dot: string }> = {
  online: { label: '在线', color: 'text-green-400', bg: 'bg-green-500/10', dot: 'bg-green-400' },
  delayed: { label: '延迟', color: 'text-yellow-400', bg: 'bg-yellow-500/10', dot: 'bg-yellow-400' },
  offline: { label: '离线', color: 'text-red-400', bg: 'bg-red-500/10', dot: 'bg-red-400' },
};

const statusConfig: Record<string, { label: string; color: string; bg: string }> = {
  active: { label: '活跃', color: 'text-green-400', bg: 'bg-green-500/10' },
  pending_approval: { label: '待审批', color: 'text-yellow-400', bg: 'bg-yellow-500/10' },
  revoked: { label: '已撤销', color: 'text-red-400', bg: 'bg-red-500/10' },
};

const certUrgencyTone: Record<AgentCertDetail['urgency'], string> = {
  expired: 'border-rose-300/15 bg-rose-500/10 text-rose-200',
  critical: 'border-rose-300/15 bg-rose-500/10 text-rose-200',
  warning: 'border-amber-300/15 bg-amber-500/10 text-amber-200',
  normal: 'border-emerald-300/15 bg-emerald-500/10 text-emerald-200',
};

function normalizeLiveness(value: string | null | undefined): AgentLiveness {
  if (value === 'online' || value === 'delayed' || value === 'offline') {
    return value;
  }
  return 'offline';
}

export default function AgentsPage() {
  const navigate = useNavigate();
  const { id: routeAgentId } = useParams();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<AgentDetail | null>(null);
  const [localSelectedAgentId, setLocalSelectedAgentId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [toast, setToast] = useState('');
  const [error, setError] = useState('');

  const activeAgentId = routeAgentId ?? localSelectedAgentId;

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await apiFetch<PaginatedResponse<Agent>>('/agents?limit=1000');
      setAgents(data.items || []);
    } catch (fetchError) {
      console.error('Failed to fetch agents:', fetchError);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadAgentDetail = useCallback(async (agentId: string) => {
    setIsDetailLoading(true);
    setDetailError(null);

    try {
      const detail = await apiFetch<AgentDetail>(`/agents/${agentId}/detail`);
      setSelectedAgent(detail);
    } catch (fetchError) {
      setSelectedAgent(null);
      setDetailError(fetchError instanceof Error ? fetchError.message : '读取 Agent 详情失败');
    } finally {
      setIsDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (!routeAgentId && !localSelectedAgentId && agents.length > 0) {
      setLocalSelectedAgentId(agents[0].id);
    }
  }, [agents, localSelectedAgentId, routeAgentId]);

  useEffect(() => {
    if (!activeAgentId) {
      setSelectedAgent(null);
      setDetailError(null);
      return;
    }

    void loadAgentDetail(activeAgentId);
  }, [activeAgentId, loadAgentDetail]);

  const handleCreate = async () => {
    if (!newName.trim()) {
      return;
    }

    try {
      await apiPost('/agents', { name: newName.trim() });
      setToast(`Agent "${newName.trim()}" 创建成功`);
      setError('');
      setNewName('');
      setShowCreate(false);
      await fetchData();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : '创建失败');
    }
  };

  const handleApprove = async (id: string) => {
    try {
      await apiPost(`/agents/${id}/approve`);
      setToast('Agent 已审批');
      setError('');
      await fetchData();
      if (activeAgentId === id) {
        await loadAgentDetail(id);
      }
    } catch (approveError) {
      setError(approveError instanceof Error ? approveError.message : '审批失败');
    }
  };

  const handleReject = async (id: string) => {
    if (!confirm('确定要拒绝此 Agent？此操作不可撤销。')) {
      return;
    }

    try {
      await apiDelete(`/agents/${id}`);
      setToast('Agent 已拒绝');
      setError('');
      await fetchData();

      if (routeAgentId === id) {
        navigate('/agents');
      }
      if (localSelectedAgentId === id) {
        setLocalSelectedAgentId(null);
      }
    } catch (rejectError) {
      setError(rejectError instanceof Error ? rejectError.message : '操作失败');
    }
  };

  const filteredAgents = useMemo(() => {
    const keyword = deferredSearch.trim().toLowerCase();

    return agents.filter((agent) => {
      if (statusFilter !== 'all' && normalizeLiveness(agent.liveness) !== statusFilter && agent.status !== statusFilter) {
        return false;
      }

      if (!keyword) {
        return true;
      }

      return [agent.name, agent.fingerprint || '', agent.id]
        .join(' ')
        .toLowerCase()
        .includes(keyword);
    });
  }, [agents, deferredSearch, statusFilter]);

  const pendingAgents = filteredAgents.filter((agent) => agent.status === 'pending_approval');
  const listedAgents = filteredAgents.filter((agent) => agent.status !== 'pending_approval');
  const stats = {
    online: agents.filter((agent) => normalizeLiveness(agent.liveness) === 'online').length,
    offline: agents.filter((agent) => normalizeLiveness(agent.liveness) === 'offline').length,
    pending: agents.filter((agent) => agent.status === 'pending_approval').length,
    delayed: agents.filter((agent) => normalizeLiveness(agent.liveness) === 'delayed').length,
  };

  const selectedLiveness = normalizeLiveness(selectedAgent?.liveness);
  const selectedStatus = selectedAgent ? statusConfig[selectedAgent.status] || { label: selectedAgent.status, color: 'text-slate-300', bg: 'bg-white/5' } : null;

  return (
    <div className="space-y-6 animate-fade-in">
      <section className="glass-panel p-5 lg:p-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <div className="section-kicker">Fleet</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white">Agent 舰队</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
              左侧处理舰队列表和待审批节点，右侧 dossier 查看单节点心跳、指纹和证书覆盖情况。
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="metric-badge border-white/10 bg-white/[0.03] text-slate-300">在线 {stats.online}</span>
              <span className="metric-badge border-rose-300/15 bg-rose-500/10 text-rose-200">离线 {stats.offline}</span>
              <span className="metric-badge border-amber-300/15 bg-amber-500/10 text-amber-200">待审批 {stats.pending}</span>
              {selectedAgent && (
                <span className="metric-badge border-white/10 bg-white/[0.03] text-slate-300">当前 {selectedAgent.name}</span>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 xl:pt-1">
            <button type="button" onClick={() => setShowCreate((current) => !current)} className="btn-primary flex items-center gap-1.5">
              <Plus size={14} /> 预创建 Agent
            </button>
            <button type="button" onClick={() => void fetchData()} className="btn-secondary flex items-center gap-1.5" disabled={isLoading}>
              <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} /> 刷新舰队
            </button>
          </div>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[
            { label: '在线', value: stats.online, icon: CheckCircle2, tone: 'border-emerald-300/15 bg-emerald-500/10 text-emerald-100' },
            { label: '离线', value: stats.offline, icon: XCircle, tone: 'border-rose-300/15 bg-rose-500/10 text-rose-100' },
            { label: '待审批', value: stats.pending, icon: Clock, tone: 'border-amber-300/15 bg-amber-500/10 text-amber-100' },
            { label: '延迟', value: stats.delayed, icon: AlertTriangle, tone: 'border-orange-300/15 bg-orange-500/10 text-orange-100' },
          ].map(({ label, value, icon: Icon, tone }) => (
            <div key={label} className={`rounded-lg border p-4 ${tone}`}>
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
      </section>

      {toast && (
        <div className="rounded-md border border-emerald-300/15 bg-emerald-500/10 p-3 text-sm text-emerald-200">
          {toast}
        </div>
      )}
      {error && (
        <div className="rounded-md border border-rose-300/15 bg-rose-500/10 p-3 text-sm text-rose-200">
          {error}
        </div>
      )}

      {showCreate && (
        <div className="glass-panel p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
            <input
              className="input-field flex-1"
              placeholder="输入 Agent 名称"
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
            />
            <div className="flex gap-2">
              <button type="button" onClick={handleCreate} className="btn-primary">创建</button>
              <button type="button" onClick={() => { setShowCreate(false); setNewName(''); }} className="btn-secondary">取消</button>
            </div>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-1 flex-wrap items-center gap-3">
          <label className="relative min-w-[260px] flex-1 max-w-md">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              className="input-field pl-9"
              placeholder="搜索 Agent 名称、指纹或 ID"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            {['all', 'online', 'delayed', 'offline', 'pending_approval'].map((status) => (
              <button
                key={status}
                type="button"
                onClick={() => setStatusFilter(status)}
                className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                  statusFilter === status
                    ? 'border-teal-300/20 bg-teal-500/10 text-teal-100'
                    : 'border-white/10 bg-white/[0.03] text-slate-400 hover:text-white'
                }`}
              >
                {status === 'all' ? '全部' : status === 'pending_approval' ? '待审批' : status === 'delayed' ? '延迟' : status === 'offline' ? '离线' : '在线'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {pendingAgents.length > 0 && (
        <div className="glass-panel p-5 border-yellow-500/20">
          <div className="section-kicker">Pending Queue</div>
          <h3 className="mt-2 text-lg font-semibold text-white">待审批 Agent</h3>
          <div className="mt-4 space-y-3">
            {pendingAgents.map((agent) => (
              <div key={agent.id} className="rounded-lg border border-amber-300/15 bg-amber-500/10 p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div className="flex items-start gap-3">
                    <div className="rounded-md border border-white/10 bg-white/5 p-2 text-white">
                      <Server size={16} />
                    </div>
                    <div>
                      <div className="text-sm font-medium text-white">{agent.name}</div>
                      <div className="mt-1 text-xs text-slate-500">{agent.fingerprint ? `${agent.fingerprint.slice(0, 24)}...` : 'TOFU 自注册，等待审批'}</div>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => void handleApprove(agent.id)} className="btn-primary">批准</button>
                    <button type="button" onClick={() => void handleReject(agent.id)} className="btn-danger">拒绝</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.9fr)_400px]">
        <div className="glass-panel overflow-hidden">
          <div className="border-b border-white/6 px-5 py-4">
            <div className="section-kicker">Fleet Table</div>
            <h3 className="mt-2 text-lg font-semibold text-white">Agent 列表</h3>
            <p className="mt-1 text-sm text-slate-400">表格负责扫描全局，右侧 dossier 负责看单节点细节。</p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/6 text-xs text-slate-500">
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
                ) : listedAgents.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-5 py-14 text-center text-sm text-slate-500">没有匹配的 Agent。</td>
                  </tr>
                ) : (
                  listedAgents.map((agent) => {
                    const liveness = normalizeLiveness(agent.liveness);
                    const livenessState = livenessConfig[liveness];
                    const statusState = statusConfig[agent.status] || { label: agent.status, color: 'text-slate-300', bg: 'bg-white/5' };
                    const isSelected = activeAgentId === agent.id;

                    return (
                      <tr
                        key={agent.id}
                        className={`table-row cursor-pointer ${isSelected ? 'bg-teal-500/[0.06]' : ''}`}
                        onClick={() => {
                          setLocalSelectedAgentId(agent.id);
                          navigate(`/agents/${agent.id}`);
                        }}
                      >
                        <td className="px-5 py-4">
                          <div className="flex items-start gap-3">
                            <div className="rounded-md border border-teal-300/12 bg-teal-500/10 p-2 text-teal-100">
                              <Server size={16} />
                            </div>
                            <div>
                              <div className="font-medium text-white">{agent.name}</div>
                              <div className="mt-1 font-mono text-xs text-slate-500">{agent.fingerprint ? `${agent.fingerprint.slice(0, 18)}...` : agent.id.slice(0, 18)}</div>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <div className="space-y-2">
                            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs ${statusState.bg} ${statusState.color}`}>{statusState.label}</span>
                            <div className="flex items-center gap-1.5 text-xs text-slate-400">
                              <span className={`h-2 w-2 rounded-full ${livenessState.dot}`} />
                              {livenessState.label}
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-4 text-white">{agent.cert_count}</td>
                        <td className="px-4 py-4 text-slate-300">{agent.expiring_soon_count}</td>
                        <td className="px-4 py-4 text-xs text-slate-500">
                          {agent.last_seen ? formatDistanceToNow(new Date(agent.last_seen), { addSuffix: true }) : '从未连接'}
                        </td>
                        <td className="px-5 py-4">
                          <button type="button" className="text-xs font-medium text-teal-200 hover:text-teal-100">查看 dossier</button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        <aside className="glass-panel self-start p-5 xl:sticky xl:top-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="section-kicker">Agent Dossier</div>
              <h3 className="mt-2 text-lg font-semibold text-white">节点详情</h3>
              <p className="mt-1 text-sm text-slate-400">查看心跳、指纹、接入状态和挂载证书。</p>
            </div>
            {selectedAgent && <span className="metric-badge border-white/10 bg-white/5 text-slate-300">{selectedAgent.certs.length} 证书</span>}
          </div>

          {!activeAgentId ? (
            <div className="mt-6 rounded-lg border border-white/8 bg-white/[0.03] px-4 py-8 text-center text-sm text-slate-500">从左侧选择一个 Agent 查看详情。</div>
          ) : isDetailLoading ? (
            <div className="mt-6 space-y-3">
              <div className="skeleton h-6 rounded" />
              <div className="skeleton h-20 rounded" />
              <div className="skeleton h-32 rounded" />
            </div>
          ) : detailError ? (
            <div className="mt-6 rounded-lg border border-rose-300/15 bg-rose-500/10 p-4 text-sm text-rose-200">{detailError}</div>
          ) : selectedAgent ? (
            <div className="mt-6 space-y-5">
              <div>
                <div className="text-xl font-semibold text-white">{selectedAgent.name}</div>
                <div className="mt-1 text-sm text-slate-400">{selectedAgent.description || '未填写描述'}</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <span className={`rounded-full px-2 py-0.5 text-xs ${selectedStatus?.bg} ${selectedStatus?.color}`}>{selectedStatus?.label}</span>
                  <span className={`rounded-full px-2 py-0.5 text-xs ${livenessConfig[selectedLiveness].bg} ${livenessConfig[selectedLiveness].color}`}>
                    {livenessConfig[selectedLiveness].label}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
                  <div className="text-xs text-slate-500">最后心跳</div>
                  <div className="mt-2 text-white">{selectedAgent.last_seen ? formatDistanceToNow(new Date(selectedAgent.last_seen), { addSuffix: true }) : '从未连接'}</div>
                </div>
                <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
                  <div className="text-xs text-slate-500">创建时间</div>
                  <div className="mt-2 text-white">{format(new Date(selectedAgent.created_at), 'MM-dd HH:mm')}</div>
                </div>
                <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
                  <div className="text-xs text-slate-500">证书总数</div>
                  <div className="mt-2 text-white">{selectedAgent.cert_count}</div>
                </div>
                <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
                  <div className="text-xs text-slate-500">30 天内到期</div>
                  <div className="mt-2 text-white">{selectedAgent.expiring_soon_count}</div>
                </div>
              </div>

              <div className="rounded-lg border border-white/8 bg-white/[0.03] p-4">
                <div className="text-xs text-slate-500">指纹</div>
                <div className="mt-2 break-all font-mono text-xs text-slate-300">{selectedAgent.fingerprint || '未上报公钥指纹，可能仍处于 TOFU 注册阶段。'}</div>
              </div>

              {selectedAgent.status === 'pending_approval' && (
                <div className="flex gap-2">
                  <button type="button" onClick={() => void handleApprove(selectedAgent.id)} className="btn-primary">批准接入</button>
                  <button type="button" onClick={() => void handleReject(selectedAgent.id)} className="btn-danger">拒绝接入</button>
                </div>
              )}

              <div>
                <div className="mb-3 text-sm font-medium text-white">挂载证书</div>
                {selectedAgent.certs.length === 0 ? (
                  <div className="rounded-lg border border-white/8 bg-white/[0.03] px-4 py-6 text-sm text-slate-500">该节点还没有挂载证书。</div>
                ) : (
                  <div className="space-y-2">
                    {[...selectedAgent.certs]
                      .sort((left, right) => left.days_remaining - right.days_remaining)
                      .map((cert) => (
                        <div key={`${cert.local_path}-${cert.subject_cn}`} className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-sm font-medium text-white">{cert.subject_cn}</div>
                              <div className="mt-1 text-xs text-slate-500">{cert.local_path}</div>
                            </div>
                            <span className={`rounded-full border px-2 py-0.5 text-xs ${certUrgencyTone[cert.urgency]}`}>{cert.urgency}</span>
                          </div>
                          <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
                            <span>{cert.cert_name}</span>
                            <span>{cert.days_remaining < 0 ? `已过期 ${Math.abs(cert.days_remaining)} 天` : `${cert.days_remaining} 天`}</span>
                          </div>
                        </div>
                      ))}
                  </div>
                )}
              </div>
            </div>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
