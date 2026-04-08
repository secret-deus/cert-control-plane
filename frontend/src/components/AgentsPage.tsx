import { useState, useEffect } from 'react';
import { Server, Plus, Check, X, Clock, UserCheck, UserX } from 'lucide-react';
import { apiFetch, apiPost } from '../lib/api';
import { formatDistanceToNow } from 'date-fns';

interface Agent {
  id: string;
  name: string;
  status: string;
  fingerprint: string | null;
  last_seen: string | null;
  created_at: string;
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');

  const fetchAgents = async () => {
    try {
      const data = await apiFetch<{ items: Agent[] }>('/agents');
      setAgents(data.items || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAgents(); }, []);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(''), 3000);
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      await apiPost('/agents', { name: newName.trim() });
      setNewName('');
      setShowCreate(false);
      fetchAgents();
      showToast(`Agent "${newName.trim()}" created – waiting for it to self-register`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create');
    }
  };

  const handleApprove = async (id: string, name: string) => {
    try {
      await apiPost(`/agents/${id}/approve`);
      fetchAgents();
      showToast(`Agent "${name}" approved`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to approve');
    }
  };

  const handleReject = async (id: string, name: string) => {
    if (!confirm(`Reject agent "${name}"? This cannot be undone.`)) return;
    try {
      await apiPost(`/agents/${id}/reject`);
      fetchAgents();
      showToast(`Agent "${name}" rejected`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to reject');
    }
  };

  const statusColor = (s: string) => {
    switch (s) {
      case 'active':           return 'bg-emerald-500/20 text-emerald-400';
      case 'pending_approval': return 'bg-amber-500/20 text-amber-400';
      case 'revoked':          return 'bg-red-500/20 text-red-400';
      default:                 return 'bg-gray-500/20 text-gray-400';
    }
  };

  const pendingAgents = agents.filter(a => a.status === 'pending_approval');
  const otherAgents   = agents.filter(a => a.status !== 'pending_approval');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-3">
            <Server size={24} className="text-[var(--color-accent-blue)]" />
            Agents
          </h2>
          <p className="text-sm text-[var(--color-text-secondary)] mt-1">
            Manage agent registrations. Agents self-register via TOFU and await admin approval.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-[var(--color-accent-blue)] hover:bg-[var(--color-accent-blue)]/80 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Plus size={16} /> New Agent Slot
        </button>
      </div>

      {/* Toast */}
      {toast && (
        <div className="glass-panel border-emerald-500/30 px-4 py-3 text-sm text-emerald-400">
          {toast}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="glass-panel border-red-500/30 px-4 py-3 text-sm text-red-400 flex justify-between">
          {error}
          <button onClick={() => setError('')}><X size={14} /></button>
        </div>
      )}

      {/* Create dialog */}
      {showCreate && (
        <div className="glass-panel p-6 space-y-4">
          <h3 className="font-semibold">Pre-register Agent Slot</h3>
          <p className="text-xs text-[var(--color-text-secondary)]">
            Create a named slot. The agent will self-register via TOFU and wait for approval.
          </p>
          <div>
            <label className="block text-xs text-[var(--color-text-secondary)] mb-1">Agent Name *</label>
            <input
              type="text"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()}
              placeholder="e.g. web-node-01"
              className="w-full bg-[var(--color-background-base)] border border-[var(--color-border-subtle)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--color-accent-blue)] transition-colors"
            />
          </div>
          <div className="flex gap-2">
            <button onClick={handleCreate} className="px-4 py-2 bg-[var(--color-accent-blue)] hover:bg-[var(--color-accent-blue)]/80 text-white rounded-lg text-sm font-medium transition-colors">
              Create
            </button>
            <button onClick={() => { setShowCreate(false); setNewName(''); }} className="px-4 py-2 text-sm text-[var(--color-text-secondary)] hover:text-white transition-colors">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Pending Approval section */}
      {!loading && pendingAgents.length > 0 && (
        <div className="glass-panel overflow-hidden border border-amber-500/20">
          <div className="px-4 py-3 bg-amber-500/10 border-b border-amber-500/20 flex items-center gap-2">
            <Clock size={16} className="text-amber-400" />
            <span className="text-sm font-semibold text-amber-400">
              Pending Approval ({pendingAgents.length})
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-[var(--color-text-secondary)] uppercase bg-[var(--color-background-base)] border-b border-[var(--color-border-subtle)]">
                <tr>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Fingerprint</th>
                  <th className="px-4 py-3">Registered</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {pendingAgents.map(a => (
                  <tr key={a.id} className="border-b border-[var(--color-border-subtle)] hover:bg-[rgba(255,255,255,0.02)]">
                    <td className="px-4 py-3 font-medium text-white">{a.name}</td>
                    <td className="px-4 py-3 font-mono text-xs text-[var(--color-text-secondary)]">
                      {a.fingerprint ? `${a.fingerprint.substring(0, 16)}…` : '—'}
                    </td>
                    <td className="px-4 py-3 text-xs text-[var(--color-text-secondary)]">
                      {formatDistanceToNow(new Date(a.created_at), { addSuffix: true })}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleApprove(a.id, a.name)}
                          className="flex items-center gap-1 px-3 py-1.5 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 rounded-lg text-xs font-medium transition-colors"
                        >
                          <UserCheck size={12} /> Approve
                        </button>
                        <button
                          onClick={() => handleReject(a.id, a.name)}
                          className="flex items-center gap-1 px-3 py-1.5 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg text-xs font-medium transition-colors"
                        >
                          <UserX size={12} /> Reject
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* All other agents */}
      <div className="glass-panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-[var(--color-text-secondary)] uppercase bg-[var(--color-background-base)] border-b border-[var(--color-border-subtle)]">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Fingerprint</th>
                <th className="px-4 py-3">Last Seen</th>
                <th className="px-4 py-3">Created</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-[var(--color-text-secondary)]">Loading…</td></tr>
              ) : otherAgents.length === 0 ? (
                <tr><td colSpan={5} className="px-4 py-12 text-center text-[var(--color-text-secondary)]">
                  <Server size={32} className="mx-auto mb-3 opacity-30" />
                  {agents.length === 0
                    ? 'No agents yet. Create a slot or wait for an agent to self-register.'
                    : 'No approved agents yet.'}
                </td></tr>
              ) : (
                otherAgents.map(a => (
                  <tr key={a.id} className="border-b border-[var(--color-border-subtle)] hover:bg-[rgba(255,255,255,0.02)] transition-colors">
                    <td className="px-4 py-3 font-medium text-white">{a.name}</td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-1 rounded-full font-medium ${statusColor(a.status)}`}>
                        {a.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-[var(--color-text-secondary)]">
                      {a.fingerprint ? `${a.fingerprint.substring(0, 16)}…` : '—'}
                    </td>
                    <td className="px-4 py-3 text-xs text-[var(--color-text-secondary)]">
                      {a.last_seen ? formatDistanceToNow(new Date(a.last_seen), { addSuffix: true }) : 'Never'}
                    </td>
                    <td className="px-4 py-3 text-xs text-[var(--color-text-secondary)]">
                      {formatDistanceToNow(new Date(a.created_at), { addSuffix: true })}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
