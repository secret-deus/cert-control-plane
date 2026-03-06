import { useState, useEffect } from 'react';
import { ScrollText, ChevronDown, ChevronRight } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { format, formatDistanceToNow } from 'date-fns';

interface AuditEntry {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  actor: string;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

const ACTION_COLORS: Record<string, string> = {
  register: 'bg-emerald-500/20 text-emerald-400',
  renew: 'bg-blue-500/20 text-blue-400',
  revoke: 'bg-red-500/20 text-red-400',
  create: 'bg-purple-500/20 text-purple-400',
  delete: 'bg-red-500/20 text-red-400',
  reset_token: 'bg-amber-500/20 text-amber-400',
  rollout_start: 'bg-blue-500/20 text-blue-400',
  rollout_pause: 'bg-amber-500/20 text-amber-400',
  rollout_resume: 'bg-emerald-500/20 text-emerald-400',
  rollout_rollback: 'bg-red-500/20 text-red-400',
};

export default function AuditLogsPage() {
  const [logs, setLogs] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [filterAction, setFilterAction] = useState('');
  const [offset, setOffset] = useState(0);
  const limit = 50;

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
      if (filterAction) params.set('action', filterAction);
      const data = await apiFetch<{items: AuditEntry[]}>(`/audit?${params}`);
      setLogs(data.items || []);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchLogs(); }, [offset, filterAction]);

  const toggleExpand = (id: string) => {
    const next = new Set(expanded);
    next.has(id) ? next.delete(id) : next.add(id);
    setExpanded(next);
  };

  // Collect unique actions for filter dropdown
  const uniqueActions = [...new Set(logs.map(l => l.action))].sort();

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold flex items-center gap-3">
          <ScrollText size={24} className="text-[var(--color-accent-blue)]" />
          Audit Logs
        </h2>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">Immutable log of all system operations</p>
      </div>

      {/* Filters */}
      <div className="flex gap-3 items-center">
        <select
          value={filterAction}
          onChange={e => { setFilterAction(e.target.value); setOffset(0); }}
          className="bg-[var(--color-background-base)] border border-[var(--color-border-subtle)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--color-accent-blue)] text-[var(--color-text-primary)]"
        >
          <option value="">All Actions</option>
          {uniqueActions.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <span className="text-xs text-[var(--color-text-secondary)]">
          Showing {offset + 1}–{offset + logs.length}
        </span>
      </div>

      {/* Table */}
      <div className="glass-panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-[var(--color-text-secondary)] uppercase bg-[var(--color-background-base)] border-b border-[var(--color-border-subtle)]">
              <tr>
                <th className="px-4 py-3 w-8"></th>
                <th className="px-4 py-3">Timestamp</th>
                <th className="px-4 py-3">Action</th>
                <th className="px-4 py-3">Actor</th>
                <th className="px-4 py-3">Target</th>
                <th className="px-4 py-3">IP</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-[var(--color-text-secondary)]">Loading...</td></tr>
              ) : logs.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-12 text-center text-[var(--color-text-secondary)]">
                  <ScrollText size={32} className="mx-auto mb-3 opacity-30" />
                  No audit logs found.
                </td></tr>
              ) : (
                logs.map(log => (
                  <>
                    <tr key={log.id}
                      className="border-b border-[var(--color-border-subtle)] hover:bg-[rgba(255,255,255,0.02)] transition-colors cursor-pointer"
                      onClick={() => log.details && toggleExpand(log.id)}
                    >
                      <td className="px-4 py-3 text-[var(--color-text-secondary)]">
                        {log.details && (expanded.has(log.id) ? <ChevronDown size={14} /> : <ChevronRight size={14} />)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="text-xs font-mono">{format(new Date(log.created_at), 'yyyy-MM-dd HH:mm:ss')}</div>
                        <div className="text-xs text-[var(--color-text-secondary)]">{formatDistanceToNow(new Date(log.created_at), { addSuffix: true })}</div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`text-xs px-2 py-1 rounded-full font-medium ${ACTION_COLORS[log.action] || 'bg-gray-500/20 text-gray-400'}`}>
                          {log.action}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs">{log.actor}</td>
                      <td className="px-4 py-3 text-xs text-[var(--color-text-secondary)]">
                        {log.entity_type}{log.entity_id ? ` / ${log.entity_id.substring(0, 8)}...` : ''}
                      </td>
                      <td className="px-4 py-3 text-xs font-mono text-[var(--color-text-secondary)]">{log.ip_address || '—'}</td>
                    </tr>
                    {expanded.has(log.id) && log.details && (
                      <tr key={`${log.id}-details`}>
                        <td colSpan={6} className="px-8 py-3 bg-[var(--color-background-base)] border-b border-[var(--color-border-subtle)]">
                          <pre className="text-xs font-mono text-[var(--color-text-secondary)] overflow-x-auto whitespace-pre-wrap">
                            {JSON.stringify(log.details, null, 2)}
                          </pre>
                        </td>
                      </tr>
                    )}
                  </>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      <div className="flex justify-between items-center">
        <button
          onClick={() => setOffset(Math.max(0, offset - limit))}
          disabled={offset === 0}
          className="px-3 py-1.5 text-xs rounded-lg transition-colors disabled:opacity-30 text-[var(--color-text-secondary)] hover:text-white hover:bg-[rgba(255,255,255,0.04)]"
        >
          ← Previous
        </button>
        <button
          onClick={() => setOffset(offset + limit)}
          disabled={logs.length < limit}
          className="px-3 py-1.5 text-xs rounded-lg transition-colors disabled:opacity-30 text-[var(--color-text-secondary)] hover:text-white hover:bg-[rgba(255,255,255,0.04)]"
        >
          Next →
        </button>
      </div>
    </div>
  );
}
