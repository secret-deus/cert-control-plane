import { useState, useEffect, useCallback } from 'react';
import { Server, Search, Plus, XCircle, CheckCircle2, Clock, AlertTriangle, RefreshCw } from 'lucide-react';
import { apiFetch, apiPost } from '../lib/api';
import { formatDistanceToNow } from 'date-fns';

interface Agent {
  id: string;
  name: string;
  status: string;
  fingerprint: string | null;
  last_seen: string | null;
  created_at: string;
  liveness: 'online' | 'delayed' | 'offline';
  cert_count: number;
  expiring_soon_count: number;
}

const livenessConfig = {
  online: { label: '在线', color: 'text-green-400', bg: 'bg-green-500/10', dot: 'bg-green-400' },
  delayed: { label: '延迟', color: 'text-yellow-400', bg: 'bg-yellow-500/10', dot: 'bg-yellow-400' },
  offline: { label: '离线', color: 'text-red-400', bg: 'bg-red-500/10', dot: 'bg-red-400' },
};

const statusConfig: Record<string, { label: string; color: string; bg: string }> = {
  active: { label: '活跃', color: 'text-green-400', bg: 'bg-green-500/10' },
  pending_approval: { label: '待审批', color: 'text-yellow-400', bg: 'bg-yellow-500/10' },
  revoked: { label: '已撤销', color: 'text-red-400', bg: 'bg-red-500/10' },
};

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [toast, setToast] = useState('');
  const [error, setError] = useState('');

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await apiFetch<{ items: Agent[]; total: number }>('/agents?limit=1000');
      setAgents(data.items || []);
    } catch (err) {
      console.error('Failed to fetch agents:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      await apiPost('/agents', { name: newName.trim() });
      setToast(`Agent "${newName.trim()}" 创建成功`);
      setNewName('');
      setShowCreate(false);
      fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建失败');
    }
  };

  const handleApprove = async (id: string) => {
    try {
      await apiPost(`/agents/${id}/approve`);
      setToast('Agent 已审批');
      fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : '审批失败');
    }
  };

  const handleReject = async (id: string) => {
    if (!confirm('确定要拒绝此 Agent？此操作不可撤销。')) return;
    try {
      await apiFetch(`/agents/${id}`, { method: 'DELETE' });
      setToast('Agent 已拒绝');
      fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败');
    }
  };

  const filteredAgents = agents.filter(a => {
    if (statusFilter !== 'all' && a.liveness !== statusFilter && a.status !== statusFilter) return false;
    if (search && !a.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const pendingAgents = filteredAgents.filter(a => a.status === 'pending_approval');
  const activeAgents = filteredAgents.filter(a => a.status !== 'pending_approval');
  const stats = {
    online: agents.filter(a => a.liveness === 'online').length,
    offline: agents.filter(a => a.liveness === 'offline').length,
    pending: agents.filter(a => a.status === 'pending_approval').length,
    delayed: agents.filter(a => a.liveness === 'delayed').length,
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Agent 管理</h1>
          <p className="text-sm text-zinc-400 mt-1">管理 Agent 注册与证书分发</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={fetchData} className="btn-secondary flex items-center gap-1.5" disabled={isLoading}>
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} /> 刷新
          </button>
          <button onClick={() => setShowCreate(true)} className="btn-primary flex items-center gap-1.5">
            <Plus size={14} /> 预创建 Agent
          </button>
        </div>
      </div>

      {toast && <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-3 text-green-400 text-sm flex items-center justify-between">{toast}<button onClick={() => setToast('')}><XCircle size={14} /></button></div>}
      {error && <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-red-400 text-sm flex items-center justify-between">{error}<button onClick={() => setError('')}><XCircle size={14} /></button></div>}

      {showCreate && (
        <div className="glass-panel p-4 flex items-center gap-3">
          <input className="input-field flex-1" placeholder="输入 Agent 名称" value={newName} onChange={e => setNewName(e.target.value)} />
          <button onClick={handleCreate} className="btn-primary">创建</button>
          <button onClick={() => { setShowCreate(false); setNewName(''); }} className="btn-secondary">取消</button>
        </div>
      )}

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: '在线', value: stats.online, icon: CheckCircle2, color: 'text-green-400', bg: 'bg-green-500/10' },
          { label: '离线', value: stats.offline, icon: XCircle, color: 'text-red-400', bg: 'bg-red-500/10' },
          { label: '待审批', value: stats.pending, icon: Clock, color: 'text-yellow-400', bg: 'bg-yellow-500/10' },
          { label: '延迟', value: stats.delayed, icon: AlertTriangle, color: 'text-orange-400', bg: 'bg-orange-500/10' },
        ].map(({ label, value, icon: Icon, color, bg }) => (
          <div key={label} className="glass-panel p-3 flex items-center gap-3">
            <div className={`p-2 rounded-lg ${bg}`}><Icon size={16} className={color} /></div>
            <div>
              <div className="text-lg font-bold text-white">{value}</div>
              <div className="text-xs text-zinc-500">{label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Search & filter */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input className="input-field pl-9" placeholder="搜索 Agent..." value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <div className="flex items-center gap-1">
          {['all', 'online', 'delayed', 'offline', 'pending_approval'].map(s => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                statusFilter === s ? 'bg-blue-500/20 text-blue-400' : 'text-zinc-400 hover:text-white hover:bg-white/5'
              }`}
            >
              {s === 'all' ? '全部' : s === 'pending_approval' ? '待审批' : s === 'online' ? '在线' : s === 'delayed' ? '延迟' : '离线'}
            </button>
          ))}
        </div>
      </div>

      {/* Pending section */}
      {pendingAgents.length > 0 && (
        <div className="glass-panel p-4 border-yellow-500/20">
          <h3 className="text-sm font-medium text-yellow-400 mb-3">待审批 ({pendingAgents.length})</h3>
          <div className="space-y-2">
            {pendingAgents.map(a => (
              <div key={a.id} className="flex items-center justify-between p-3 rounded-lg bg-yellow-500/5">
                <div className="flex items-center gap-3">
                  <Server size={16} className="text-yellow-400" />
                  <div>
                    <div className="text-sm text-white font-medium">{a.name}</div>
                    <div className="text-xs text-zinc-500">{a.fingerprint ? `${a.fingerprint.substring(0, 16)}...` : 'TOFU 自注册'}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => handleApprove(a.id)} className="flex items-center gap-1 px-3 py-1.5 bg-green-500/20 hover:bg-green-500/30 text-green-400 rounded-lg text-xs font-medium transition-colors">
                    批准
                  </button>
                  <button onClick={() => handleReject(a.id)} className="flex items-center gap-1 px-3 py-1.5 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg text-xs font-medium transition-colors">
                    拒绝
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Agent table */}
      <div className="glass-panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-zinc-500 text-xs border-b border-white/5">
                <th className="text-left py-3 px-4 font-medium">名称</th>
                <th className="text-left py-3 px-4 font-medium">状态</th>
                <th className="text-left py-3 px-4 font-medium">存活</th>
                <th className="text-left py-3 px-4 font-medium">证书数</th>
                <th className="text-left py-3 px-4 font-medium">即将过期</th>
                <th className="text-left py-3 px-4 font-medium">最后心跳</th>
                <th className="text-left py-3 px-4 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i} className="border-b border-white/5">
                    {Array.from({ length: 7 }).map((_, j) => (
                      <td key={j} className="py-3 px-4"><div className="skeleton h-4 rounded" /></td>
                    ))}
                  </tr>
                ))
              ) : activeAgents.length === 0 ? (
                <tr><td colSpan={7} className="text-center py-12 text-zinc-500">暂无 Agent</td></tr>
              ) : (
                activeAgents.map(a => {
                  const lCfg = livenessConfig[a.liveness] || livenessConfig.offline;
                  const sCfg = statusConfig[a.status] || { label: a.status, color: 'text-zinc-400', bg: 'bg-zinc-500/10' };
                  return (
                    <tr key={a.id} className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <Server size={14} className="text-zinc-500" />
                          <div>
                            <div className="font-medium text-white">{a.name}</div>
                            <div className="text-xs text-zinc-500 font-mono">{a.fingerprint ? `${a.fingerprint.substring(0, 16)}...` : '—'}</div>
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${sCfg.bg} ${sCfg.color}`}>
                          {sCfg.label}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-1.5">
                          <span className={`w-2 h-2 rounded-full ${lCfg.dot}`} />
                          <span className={`text-xs ${lCfg.color}`}>{lCfg.label}</span>
                        </div>
                      </td>
                      <td className="py-3 px-4 text-white">{a.cert_count}</td>
                      <td className="py-3 px-4">
                        {a.expiring_soon_count > 0 ? (
                          <span className="text-yellow-400">{a.expiring_soon_count}</span>
                        ) : (
                          <span className="text-zinc-500">0</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-zinc-500 text-xs">
                        {a.last_seen ? formatDistanceToNow(new Date(a.last_seen), { addSuffix: true }) : '从未连接'}
                      </td>
                      <td className="py-3 px-4">
                        <a href={`/agents/${a.id}`} className="text-xs text-blue-400 hover:text-blue-300">
                          详情
                        </a>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}