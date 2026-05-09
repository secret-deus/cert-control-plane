import { useCallback, useDeferredValue, useEffect, useMemo, useState } from 'react';
import { Plus, RefreshCw, Search } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { apiDelete, apiFetch, apiPost } from '../lib/api';
import AgentStatsCards from './AgentStatsCards';
import AgentTable from './AgentTable';
import AgentDetailPage from './AgentDetailPage';

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
      const data = await apiFetch<PaginatedResponse<Agent>>('/agents?limit=500');
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

  return (
    <div className="space-y-6 animate-fade-in">
      <section className="glass-panel rounded-[24px] p-5 lg:p-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <div className="section-kicker">Fleet</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white">Agent 舰队</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-white/50">
              左侧处理舰队列表和待审批节点，右侧 dossier 查看单节点心跳、指纹和证书覆盖情况。
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="metric-badge border-white/8 bg-white/[0.03] text-white/80">在线 {stats.online}</span>
              <span className="metric-badge border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] text-[#ffbf8f]">离线 {stats.offline}</span>
              <span className="metric-badge border-white/8 bg-white/[0.03] text-white/80">待审批 {stats.pending}</span>
              {selectedAgent && (
                <span className="metric-badge border-white/8 bg-white/[0.03] text-white/80">当前 {selectedAgent.name}</span>
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

        <AgentStatsCards
          online={stats.online}
          offline={stats.offline}
          pending={stats.pending}
          delayed={stats.delayed}
        />
      </section>

      {toast && (
        <div className="rounded-[18px] border border-[rgba(115,191,105,0.18)] bg-[rgba(115,191,105,0.10)] p-3 text-sm text-[#9adf90]">
          {toast}
        </div>
      )}
      {error && (
        <div className="rounded-[18px] border border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] p-3 text-sm text-[#ffbf8f]">
          {error}
        </div>
      )}

      {showCreate && (
        <div className="glass-panel rounded-[24px] p-4">
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
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/50" />
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
                    ? 'border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] text-[#ffbf8f]'
                    : 'border-white/8 bg-white/[0.03] text-white/70 hover:text-white'
                }`}
              >
                {status === 'all' ? '全部' : status === 'pending_approval' ? '待审批' : status === 'delayed' ? '延迟' : status === 'offline' ? '离线' : '在线'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {pendingAgents.length > 0 && (
        <div className="glass-panel rounded-[24px] p-5 border-white/8">
          <div className="section-kicker">Pending Queue</div>
          <h3 className="mt-2 text-lg font-semibold text-white">待审批 Agent</h3>
          <div className="mt-4 space-y-3">
            {pendingAgents.map((agent) => (
              <div key={agent.id} className="rounded-[20px] border border-white/8 bg-white/[0.03] p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div className="flex items-start gap-3">
                    <div className="rounded-md border border-white/10 bg-white/5 p-2 text-white">
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="20" height="8" x="2" y="2" rx="2" ry="2"/><rect width="20" height="8" x="2" y="14" rx="2" ry="2"/><line x1="6" x2="6.01" y1="6" y2="6"/><line x1="6" x2="6.01" y1="18" y2="18"/></svg>
                    </div>
                    <div>
                      <div className="text-sm font-medium text-white">{agent.name}</div>
                      <div className="mt-1 text-xs text-white/50">{agent.fingerprint ? `${agent.fingerprint.slice(0, 24)}...` : 'TOFU 自注册，等待审批'}</div>
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
        <AgentTable
          agents={listedAgents}
          isLoading={isLoading}
          activeAgentId={activeAgentId}
          onSelectAgent={(id) => {
            setLocalSelectedAgentId(id);
            navigate(`/agents/${id}`);
          }}
        />

        <AgentDetailPage
          agent={selectedAgent}
          isLoading={isDetailLoading}
          error={detailError}
          onApprove={handleApprove}
          onReject={handleReject}
        />
      </div>
    </div>
  );
}