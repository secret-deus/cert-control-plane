import { useState, useEffect } from 'react';
import { Server, Plus, RotateCcw, Copy, Check, X } from 'lucide-react';
import { apiFetch, apiPost } from '../lib/api';
import { formatDistanceToNow } from 'date-fns';

interface Agent {
  id: string;
  name: string;
  status: string;
  fingerprint: string | null;
  last_seen: string | null;
  created_at: string;
  bootstrap_token?: string;
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [createdToken, setCreatedToken] = useState<{ name: string; token: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const fetchAgents = async () => {
    try {
      const data = await apiFetch<{items: Agent[]}>('/agents');
      setAgents(data.items || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAgents(); }, []);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      const result = await apiPost<Agent>('/agents', { name: newName.trim() });
      setCreatedToken({ name: result.name, token: result.bootstrap_token || '' });
      setNewName('');
      setShowCreate(false);
      fetchAgents();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create');
    }
  };

  const handleResetToken = async (id: string, name: string) => {
    if (!confirm(`Reset bootstrap token for "${name}"? The old token will be invalidated.`)) return;
    try {
      const result = await apiPost<{ bootstrap_token: string }>(`/agents/${id}/reset-token`);
      setCreatedToken({ name, token: result.bootstrap_token });
      setToast(`Token reset for ${name}`);
      setTimeout(() => setToast(''), 3000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to reset token');
    }
  };

  const copyToken = (token: string) => {
    navigator.clipboard.writeText(token);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const statusColor = (s: string) => {
    switch (s) {
      case 'active': return 'bg-emerald-500/20 text-emerald-400';
      case 'pending': return 'bg-amber-500/20 text-amber-400';
      case 'revoked': return 'bg-red-500/20 text-red-400';
      case 'expired': return 'bg-gray-500/20 text-gray-400';
      default: return 'bg-gray-500/20 text-gray-400';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-3">
            <Server size={24} className="text-[var(--color-accent-blue)]" />
            Agents
          </h2>
          <p className="text-sm text-[var(--color-text-secondary)] mt-1">Manage agent registrations and bootstrap tokens</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-[var(--color-accent-blue)] hover:bg-[var(--color-accent-blue)]/80 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Plus size={16} /> New Agent
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

      {/* Token display (after create or reset) */}
      {createdToken && (
        <div className="glass-panel border-[var(--color-accent-blue)]/30 p-4 space-y-2">
          <div className="text-sm font-medium text-[var(--color-accent-blue)]">
            Bootstrap Token for "{createdToken.name}"
          </div>
          <div className="text-xs text-[var(--color-text-secondary)]">
            Copy this token now — it won't be shown again.
          </div>
          <div className="flex items-center gap-2 bg-[var(--color-background-base)] p-3 rounded font-mono text-xs">
            <code className="flex-1 break-all">{createdToken.token}</code>
            <button onClick={() => copyToken(createdToken.token)} className="shrink-0 p-1 hover:text-white transition-colors">
              {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
            </button>
          </div>
          <button onClick={() => setCreatedToken(null)} className="text-xs text-[var(--color-text-secondary)] hover:text-white">Dismiss</button>
        </div>
      )}

      {/* Create Dialog */}
      {showCreate && (
        <div className="glass-panel p-6 space-y-4">
          <h3 className="font-semibold">Create New Agent</h3>
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

      {/* Table */}
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
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-[var(--color-text-secondary)]">Loading...</td></tr>
              ) : agents.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-12 text-center text-[var(--color-text-secondary)]">
                  <Server size={32} className="mx-auto mb-3 opacity-30" />
                  No agents registered yet. Click "New Agent" to get started.
                </td></tr>
              ) : (
                agents.map((a) => (
                  <tr key={a.id} className="border-b border-[var(--color-border-subtle)] hover:bg-[rgba(255,255,255,0.02)] transition-colors">
                    <td className="px-4 py-3 font-medium text-white">{a.name}</td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-1 rounded-full font-medium ${statusColor(a.status)}`}>
                        {a.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-[var(--color-text-secondary)]">
                      {a.fingerprint ? `${a.fingerprint.substring(0, 12)}...` : '—'}
                    </td>
                    <td className="px-4 py-3 text-xs text-[var(--color-text-secondary)]">
                      {a.last_seen ? formatDistanceToNow(new Date(a.last_seen), { addSuffix: true }) : 'Never'}
                    </td>
                    <td className="px-4 py-3 text-xs text-[var(--color-text-secondary)]">
                      {formatDistanceToNow(new Date(a.created_at), { addSuffix: true })}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleResetToken(a.id, a.name)}
                        className="flex items-center gap-1 text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-accent-blue)] transition-colors"
                      >
                        <RotateCcw size={12} /> Reset Token
                      </button>
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
