import { useState, useEffect } from 'react';
import { FileKey2, X } from 'lucide-react';
import { apiFetch, apiPost } from '../lib/api';
import { format, formatDistanceToNow, differenceInDays } from 'date-fns';

interface Certificate {
  id: string;
  serial_hex: string;
  subject_cn: string;
  agent_id: string;
  agent_name?: string;
  not_before: string;
  not_after: string;
  is_current: boolean;
  revoked_at: string | null;
  created_at: string;
}

export default function CertificatesPage() {
  const [certs, setCerts] = useState<Certificate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [filter, setFilter] = useState<'all' | 'active' | 'revoked' | 'expired'>('all');

  const fetchCerts = async () => {
    try {
      // No global /certs endpoint; get agents first, then per-agent certs
      const agentsData = await apiFetch<{items: {id: string; name: string}[]}>('/agents');
      const agents = agentsData.items || [];
      const allCerts: Certificate[] = [];
      for (const agent of agents) {
        try {
          const certsData = await apiFetch<{items: Certificate[]}>(`/agents/${agent.id}/certs`);
          const items = certsData.items || [];
          allCerts.push(...items.map(c => ({ ...c, subject_cn: c.subject_cn || agent.name })));
        } catch { /* agent may have no certs */ }
      }
      setCerts(allCerts);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchCerts(); }, []);

  const handleRevoke = async (serialHex: string) => {
    if (!confirm(`Revoke certificate ${serialHex.substring(0, 8)}...? This action is IRREVERSIBLE.`)) return;
    try {
      await apiPost(`/certs/${serialHex}/revoke`);
      setToast(`Certificate ${serialHex.substring(0, 8)}... revoked`);
      setTimeout(() => setToast(''), 3000);
      fetchCerts();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to revoke');
    }
  };

  const now = new Date();

  const filtered = certs.filter(c => {
    if (filter === 'all') return true;
    if (filter === 'revoked') return !!c.revoked_at;
    if (filter === 'expired') return new Date(c.not_after) < now && !c.revoked_at;
    if (filter === 'active') return !c.revoked_at && new Date(c.not_after) >= now;
    return true;
  });

  const expiryBadge = (notAfter: string, revokedAt: string | null) => {
    if (revokedAt) return <span className="text-xs px-2 py-1 rounded-full bg-red-500/20 text-red-400">Revoked</span>;
    const days = differenceInDays(new Date(notAfter), now);
    if (days < 0) return <span className="text-xs px-2 py-1 rounded-full bg-red-500/20 text-red-400">Expired</span>;
    if (days <= 30) return <span className="text-xs px-2 py-1 rounded-full bg-amber-500/20 text-amber-400">{days}d left</span>;
    return <span className="text-xs px-2 py-1 rounded-full bg-emerald-500/20 text-emerald-400">{days}d left</span>;
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold flex items-center gap-3">
          <FileKey2 size={24} className="text-[var(--color-accent-blue)]" />
          Certificates
        </h2>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">View and manage all issued certificates</p>
      </div>

      {toast && <div className="glass-panel border-emerald-500/30 px-4 py-3 text-sm text-emerald-400">{toast}</div>}
      {error && (
        <div className="glass-panel border-red-500/30 px-4 py-3 text-sm text-red-400 flex justify-between">
          {error} <button onClick={() => setError('')}><X size={14} /></button>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-2">
        {(['all', 'active', 'revoked', 'expired'] as const).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              filter === f
                ? 'bg-[var(--color-accent-blue)]/15 text-[var(--color-accent-blue)]'
                : 'text-[var(--color-text-secondary)] hover:text-white hover:bg-[rgba(255,255,255,0.04)]'
            }`}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)} {f !== 'all' && `(${certs.filter(c => {
              if (f === 'revoked') return !!c.revoked_at;
              if (f === 'expired') return new Date(c.not_after) < now && !c.revoked_at;
              if (f === 'active') return !c.revoked_at && new Date(c.not_after) >= now;
              return false;
            }).length})`}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="glass-panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-[var(--color-text-secondary)] uppercase bg-[var(--color-background-base)] border-b border-[var(--color-border-subtle)]">
              <tr>
                <th className="px-4 py-3">Serial</th>
                <th className="px-4 py-3">Subject CN</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Expires</th>
                <th className="px-4 py-3">Current</th>
                <th className="px-4 py-3">Issued</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-[var(--color-text-secondary)]">Loading...</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-12 text-center text-[var(--color-text-secondary)]">
                  <FileKey2 size={32} className="mx-auto mb-3 opacity-30" />
                  No certificates found.
                </td></tr>
              ) : (
                filtered.map((c) => (
                  <tr key={c.id} className="border-b border-[var(--color-border-subtle)] hover:bg-[rgba(255,255,255,0.02)] transition-colors">
                    <td className="px-4 py-3 font-mono text-xs">{c.serial_hex.substring(0, 12)}...</td>
                    <td className="px-4 py-3 font-medium text-white">{c.subject_cn}</td>
                    <td className="px-4 py-3">{expiryBadge(c.not_after, c.revoked_at)}</td>
                    <td className="px-4 py-3 text-xs">
                      <div>{format(new Date(c.not_after), 'yyyy-MM-dd')}</div>
                      <div className="text-[var(--color-text-secondary)]">{formatDistanceToNow(new Date(c.not_after), { addSuffix: true })}</div>
                    </td>
                    <td className="px-4 py-3">
                      {c.is_current && <span className="text-xs px-2 py-1 rounded-full bg-emerald-500/20 text-emerald-400">Current</span>}
                    </td>
                    <td className="px-4 py-3 text-xs text-[var(--color-text-secondary)]">
                      {formatDistanceToNow(new Date(c.created_at), { addSuffix: true })}
                    </td>
                    <td className="px-4 py-3">
                      {!c.revoked_at && (
                        <button
                          onClick={() => handleRevoke(c.serial_hex)}
                          className="text-xs text-red-400 hover:text-red-300 transition-colors"
                        >
                          Revoke
                        </button>
                      )}
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
