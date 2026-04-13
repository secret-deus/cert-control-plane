import { useState, useEffect } from 'react';
import {
  Users, Activity, ShieldAlert, History,
  CheckCircle2, AlertTriangle
} from 'lucide-react';
import { formatDistanceToNow, format } from 'date-fns';
import { apiFetch } from '../lib/api';

// Types for our API responses
interface Stats {
  agents: { total: number; active: number };
  certificates: { total_active: number; expiring_soon: number };
  rollouts: { running: number };
}

interface AgentHealth {
  id: string;
  name: string;
  status: string;
  liveness: 'online' | 'delayed' | 'offline';
  last_seen: string | null;
  cert_expires_at: string | null;
}

interface CertExpiry {
  id: string;
  subject_cn: string;
  serial_hex: string;
  not_after: string;
}

interface AuditEvent {
  id: string;
  action: string;
  entity_type: string;
  actor: string;
  created_at: string;
}

// 状态映射
const livenessMap: Record<string, string> = {
  'online': '在线',
  'delayed': '延迟',
  'offline': '离线'
};

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [agents, setAgents] = useState<AgentHealth[]>([]);
  const [expirations, setExpirations] = useState<CertExpiry[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const fetchData = async () => {
    try {
      const [stats, agents, exp, ev] = await Promise.all([
        apiFetch<Stats>('/dashboard/summary'),
        apiFetch<AgentHealth[]>('/dashboard/agents-health'),
        apiFetch<CertExpiry[]>('/dashboard/certs-expiry'),
        apiFetch<AuditEvent[]>('/dashboard/events'),
      ]);

      setStats(stats);
      setAgents(agents);
      setExpirations(exp);
      setEvents(ev);
      setLastRefresh(new Date());
    } catch (err) {
      console.error("Failed to fetch dashboard data:", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // 30s auto-refresh
    return () => clearInterval(interval);
  }, []);

  if (isLoading && !stats) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[var(--color-accent-blue)]"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-500">

      {/* Top Stats Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={<Users size={24} className="text-[var(--color-accent-blue)]" />}
          title="Agent 总数"
          value={stats?.agents.total || 0}
          subtitle={`${stats?.agents.active || 0} 个活跃`}
        />
        <StatCard
          icon={<CheckCircle2 size={24} className="text-[var(--color-status-green)]" />}
          title="活跃证书"
          value={stats?.certificates.total_active || 0}
        />
        <StatCard
          icon={
            stats?.certificates.expiring_soon && stats.certificates.expiring_soon > 0
              ? <AlertTriangle size={24} className="text-[var(--color-status-yellow)]" />
              : <ShieldAlert size={24} className="text-[var(--color-text-secondary)]" />
          }
          title="即将过期 (30天内)"
          value={stats?.certificates.expiring_soon || 0}
          valueColor={stats?.certificates.expiring_soon && stats.certificates.expiring_soon > 0 ? 'text-[var(--color-status-yellow)]' : ''}
        />
        <StatCard
          icon={<Activity size={24} className="text-[var(--color-accent-blue)]" />}
          title="运行中的 Rollout"
          value={stats?.rollouts.running || 0}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Main Column: Agents Table */}
        <div className="lg:col-span-2 space-y-6">
          <div className="glass-panel p-6">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <Activity size={20} className="text-[var(--color-text-secondary)]"/>
                Agent 健康状态
              </h3>
              <span className="text-xs text-[var(--color-text-secondary)]">
                更新时间: {format(lastRefresh, 'HH:mm:ss')}
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-[var(--color-text-secondary)] uppercase bg-[var(--color-background-base)] border-b border-[var(--color-border-subtle)]">
                  <tr>
                    <th className="px-4 py-3 rounded-tl-lg">Agent 名称</th>
                    <th className="px-4 py-3">存活状态</th>
                    <th className="px-4 py-3">证书过期</th>
                    <th className="px-4 py-3 rounded-tr-lg">最后心跳</th>
                  </tr>
                </thead>
                <tbody>
                  {agents.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="px-4 py-8 text-center text-[var(--color-text-secondary)]">
                        暂无已注册的 Agent
                      </td>
                    </tr>
                  ) : (
                    agents.map((agent) => (
                      <tr key={agent.id} className="border-b border-[var(--color-border-subtle)] hover:bg-[rgba(255,255,255,0.02)] transition-colors">
                        <td className="px-4 py-3 font-medium text-white">{agent.name}</td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <span className={`status-dot ${agent.liveness}`}></span>
                            <span className="text-xs">{livenessMap[agent.liveness] || agent.liveness}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 font-mono text-xs">
                          {agent.cert_expires_at ? format(new Date(agent.cert_expires_at), 'yyyy-MM-dd') : '-'}
                        </td>
                        <td className="px-4 py-3 text-xs text-[var(--color-text-secondary)]">
                          {agent.last_seen ? formatDistanceToNow(new Date(agent.last_seen), { addSuffix: true }) : '从未'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Sidebar Column: Expirations & Timeline */}
        <div className="space-y-6">

          {/* Expirations Card */}
          <div className="glass-panel p-6">
            <h3 className="text-lg font-semibold flex items-center gap-2 mb-4">
              <AlertTriangle size={20} className="text-[var(--color-status-yellow)]"/>
              即将过期的证书
            </h3>
            <div className="space-y-3">
              {expirations.length === 0 ? (
                <p className="text-sm text-[var(--color-text-secondary)]">30 天内无证书过期</p>
              ) : (
                expirations.map((cert) => (
                  <div key={cert.id} className="bg-[var(--color-background-base)] p-3 rounded-md border border-[var(--color-border-subtle)]">
                    <div className="text-sm font-medium text-white mb-1">{cert.subject_cn}</div>
                    <div className="flex justify-between text-xs text-[var(--color-text-secondary)]">
                      <span className="font-mono">{cert.serial_hex.substring(0, 8)}...</span>
                      <span className="text-[var(--color-status-yellow)]">
                        {formatDistanceToNow(new Date(cert.not_after), { addSuffix: true })}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Audit Timeline Card */}
          <div className="glass-panel p-6">
            <h3 className="text-lg font-semibold flex items-center gap-2 mb-4">
              <History size={20} className="text-[var(--color-text-secondary)]"/>
              最近操作
            </h3>
            <div className="relative border-l border-[var(--color-border-subtle)] ml-3 space-y-6">
              {events.slice(0, 5).map((ev) => (
                <div key={ev.id} className="ml-5 relative">
                  <div className="absolute -left-[25px] top-1 h-3 w-3 rounded-full bg-[var(--color-background-base)] border-2 border-[var(--color-border-subtle)]"></div>
                  <div className="text-sm">
                    <span className="font-medium text-[var(--color-accent-blue)]">{ev.action}</span>
                  </div>
                  <div className="text-xs text-[var(--color-text-secondary)] mt-1">
                    {ev.actor} • {formatDistanceToNow(new Date(ev.created_at), { addSuffix: true })}
                  </div>
                </div>
              ))}
              {events.length === 0 && (
                <div className="ml-5 text-sm text-[var(--color-text-secondary)]">暂无操作记录</div>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

// Reusable Stat Card Component
function StatCard({ icon, title, value, subtitle, valueColor = 'text-white' }: { icon: React.ReactNode, title: string, value: string | number, subtitle?: string, valueColor?: string }) {
  return (
    <div className="glass-panel p-6 flex flex-col justify-between h-32 hover:border-[rgba(240,246,252,0.2)] transition-colors">
      <div className="flex justify-between items-start">
        <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">{title}</h3>
        <div className="bg-[var(--color-background-base)] p-2 rounded-lg border border-[var(--color-border-subtle)]">
          {icon}
        </div>
      </div>
      <div>
        <div className={`text-3xl font-bold tracking-tight ${valueColor}`}>{value}</div>
        {subtitle && <div className="text-xs text-[var(--color-text-secondary)] mt-1">{subtitle}</div>}
      </div>
    </div>
  );
}
