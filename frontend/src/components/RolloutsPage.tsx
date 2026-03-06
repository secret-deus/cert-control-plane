import { useState, useEffect } from 'react';
import { RefreshCw, Plus, Pause, Play, Undo2, X, ChevronDown, ChevronRight } from 'lucide-react';
import { apiFetch, apiPost } from '../lib/api';
import { formatDistanceToNow } from 'date-fns';

interface Rollout {
  id: string;
  name: string;
  status: string;
  batch_size: number;
  current_batch: number;
  total_batches: number;
  created_by: string;
  created_at: string;
  items?: RolloutItem[];
}

interface RolloutItem {
  id: string;
  agent_id: string;
  agent_name?: string;
  status: string;
  batch_number: number;
}

interface Agent {
  id: string;
  name: string;
}

export default function RolloutsPage() {
  const [rollouts, setRollouts] = useState<Rollout[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  // Create form state
  const [formName, setFormName] = useState('');
  const [formBatchSize, setFormBatchSize] = useState(10);

  const fetchRollouts = async () => {
    try {
      const data = await apiFetch<{items: Rollout[]}>('/rollouts');
      setRollouts(data.items || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchRollouts(); }, []);

  const handleCreate = async () => {
    if (!formName.trim()) return;
    try {
      await apiPost('/rollouts', {
        name: formName.trim(),
        batch_size: formBatchSize,
        agent_ids: agents.map(a => a.id), // target all agents
      });
      setToast('Rollout created');
      setTimeout(() => setToast(''), 3000);
      setShowCreate(false);
      setFormName('');
      fetchRollouts();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create');
    }
  };

  const handleAction = async (id: string, action: 'start' | 'pause' | 'resume' | 'rollback') => {
    const confirmMsg = action === 'rollback'
      ? 'Are you sure you want to rollback this rollout? Agents will revert to their previous certificates.'
      : undefined;
    if (confirmMsg && !confirm(confirmMsg)) return;

    try {
      await apiPost(`/rollouts/${id}/${action}`);
      setToast(`Rollout ${action}${action.endsWith('e') ? 'd' : 'ed'} successfully`);
      setTimeout(() => setToast(''), 3000);
      fetchRollouts();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : `Failed to ${action}`);
    }
  };

  const toggleExpand = (id: string) => {
    const next = new Set(expanded);
    next.has(id) ? next.delete(id) : next.add(id);
    setExpanded(next);
  };

  const statusColor = (s: string) => {
    switch (s) {
      case 'running': case 'in_progress': return 'bg-blue-500/20 text-blue-400';
      case 'completed': return 'bg-emerald-500/20 text-emerald-400';
      case 'pending': return 'bg-amber-500/20 text-amber-400';
      case 'paused': return 'bg-purple-500/20 text-purple-400';
      case 'failed': return 'bg-red-500/20 text-red-400';
      case 'rolled_back': return 'bg-gray-500/20 text-gray-400';
      default: return 'bg-gray-500/20 text-gray-400';
    }
  };

  const openCreate = async () => {
    try {
      const data = await apiFetch<{items: Agent[]}>('/agents');
      setAgents(data.items || []);
    } catch { /* ignore */ }
    setShowCreate(true);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-3">
            <RefreshCw size={24} className="text-[var(--color-accent-blue)]" />
            Rollouts
          </h2>
          <p className="text-sm text-[var(--color-text-secondary)] mt-1">Batch certificate rotation management</p>
        </div>
        <button onClick={openCreate}
          className="flex items-center gap-2 px-4 py-2.5 bg-[var(--color-accent-blue)] hover:bg-[var(--color-accent-blue)]/80 text-white rounded-lg text-sm font-medium transition-colors">
          <Plus size={16} /> New Rollout
        </button>
      </div>

      {toast && <div className="glass-panel border-emerald-500/30 px-4 py-3 text-sm text-emerald-400">{toast}</div>}
      {error && (
        <div className="glass-panel border-red-500/30 px-4 py-3 text-sm text-red-400 flex justify-between">
          {error} <button onClick={() => setError('')}><X size={14} /></button>
        </div>
      )}

      {/* Create Form */}
      {showCreate && (
        <div className="glass-panel p-6 space-y-4">
          <h3 className="font-semibold">Create New Rollout</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-[var(--color-text-secondary)] mb-1">Rollout Name *</label>
              <input type="text" value={formName} onChange={e => setFormName(e.target.value)}
                placeholder="e.g. Q1 cert rotation"
                className="w-full bg-[var(--color-background-base)] border border-[var(--color-border-subtle)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--color-accent-blue)]" />
            </div>
            <div>
              <label className="block text-xs text-[var(--color-text-secondary)] mb-1">Batch Size</label>
              <input type="number" value={formBatchSize} onChange={e => setFormBatchSize(Number(e.target.value))} min={1}
                className="w-full bg-[var(--color-background-base)] border border-[var(--color-border-subtle)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--color-accent-blue)]" />
            </div>
          </div>
          <div className="text-xs text-[var(--color-text-secondary)]">
            Target: {agents.length} agents
          </div>
          <div className="flex gap-2">
            <button onClick={handleCreate} className="px-4 py-2 bg-[var(--color-accent-blue)] hover:bg-[var(--color-accent-blue)]/80 text-white rounded-lg text-sm font-medium transition-colors">Create</button>
            <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm text-[var(--color-text-secondary)] hover:text-white transition-colors">Cancel</button>
          </div>
        </div>
      )}

      {/* Rollout List */}
      <div className="space-y-3">
        {loading ? (
          <div className="glass-panel p-8 text-center text-[var(--color-text-secondary)]">Loading...</div>
        ) : rollouts.length === 0 ? (
          <div className="glass-panel p-12 text-center text-[var(--color-text-secondary)]">
            <RefreshCw size={32} className="mx-auto mb-3 opacity-30" />
            No rollouts yet. Click "New Rollout" to start a certificate rotation.
          </div>
        ) : (
          rollouts.map(r => (
            <div key={r.id} className="glass-panel overflow-hidden">
              <div className="p-4 flex items-center gap-4">
                <button onClick={() => toggleExpand(r.id)} className="text-[var(--color-text-secondary)] hover:text-white">
                  {expanded.has(r.id) ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </button>
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-white">{r.name}</div>
                  <div className="text-xs text-[var(--color-text-secondary)] mt-0.5">
                    by {r.created_by} • {formatDistanceToNow(new Date(r.created_at), { addSuffix: true })}
                  </div>
                </div>
                <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${statusColor(r.status)}`}>
                  {r.status.replace('_', ' ')}
                </span>
                {/* Progress */}
                <div className="w-32 text-right">
                  <div className="text-xs text-[var(--color-text-secondary)]">
                    Batch {r.current_batch}/{r.total_batches}
                  </div>
                  <div className="w-full bg-[var(--color-background-base)] rounded-full h-1.5 mt-1">
                    <div
                      className="bg-[var(--color-accent-blue)] h-1.5 rounded-full transition-all"
                      style={{ width: `${r.total_batches > 0 ? (r.current_batch / r.total_batches) * 100 : 0}%` }}
                    />
                  </div>
                </div>
                {/* Actions */}
                <div className="flex gap-1">
                  {r.status === 'pending' && (
                    <button onClick={() => handleAction(r.id, 'start')} className="p-1.5 hover:bg-[rgba(255,255,255,0.06)] rounded text-emerald-400" title="Start">
                      <Play size={14} />
                    </button>
                  )}
                  {r.status === 'running' && (
                    <button onClick={() => handleAction(r.id, 'pause')} className="p-1.5 hover:bg-[rgba(255,255,255,0.06)] rounded text-amber-400" title="Pause">
                      <Pause size={14} />
                    </button>
                  )}
                  {r.status === 'paused' && (
                    <button onClick={() => handleAction(r.id, 'resume')} className="p-1.5 hover:bg-[rgba(255,255,255,0.06)] rounded text-emerald-400" title="Resume">
                      <Play size={14} />
                    </button>
                  )}
                  {['running', 'paused', 'failed'].includes(r.status) && (
                    <button onClick={() => handleAction(r.id, 'rollback')} className="p-1.5 hover:bg-[rgba(255,255,255,0.06)] rounded text-red-400" title="Rollback">
                      <Undo2 size={14} />
                    </button>
                  )}
                </div>
              </div>
              {/* Expanded items */}
              {expanded.has(r.id) && r.items && (
                <div className="border-t border-[var(--color-border-subtle)] px-4 py-3 bg-[var(--color-background-base)]">
                  <table className="w-full text-xs">
                    <thead className="text-[var(--color-text-secondary)] uppercase">
                      <tr>
                        <th className="text-left py-1">Agent</th>
                        <th className="text-left py-1">Batch</th>
                        <th className="text-left py-1">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {r.items.map(item => (
                        <tr key={item.id} className="border-t border-[var(--color-border-subtle)]">
                          <td className="py-1.5">{item.agent_name || item.agent_id.substring(0, 8)}</td>
                          <td className="py-1.5">#{item.batch_number}</td>
                          <td className="py-1.5">
                            <span className={`px-1.5 py-0.5 rounded ${statusColor(item.status)}`}>{item.status}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
