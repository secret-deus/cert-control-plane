import { useState, useEffect } from 'react';
import { History, RefreshCw } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { apiFetch } from '../lib/api';
import KPICards from './KPICards';
import AlertTable from './AlertTable';
import AgentHealthCards from './AgentHealthCards';
import CertExpiryTrend from './CertExpiryTrend';

interface DashboardSummary {
  agents: { total: number; active: number; pending_approval: number };
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
  cert_revoked_at: string | null;
}

interface CertAlertItem {
  id: string;
  subject_cn: string;
  days_remaining: number;
  urgency: 'expired' | 'critical' | 'warning' | 'notice';
  not_after: string;
  source: 'external' | 'agent';
  agent_name?: string;
}

interface AuditEvent {
  id: string;
  action: string;
  entity_type: string;
  actor: string;
  created_at: string;
}

const actionLabels: Record<string, string> = {
  agent_created: '创建 Agent',
  agent_approved: '审批 Agent',
  agent_rejected: '拒绝 Agent',
  agent_revoked: '撤销 Agent',
  external_cert_uploaded: '上传证书',
  cert_assigned: '分配证书',
  cert_unassigned: '取消分配',
  rollout_created: '创建 Rollout',
  rollout_started: '启动 Rollout',
  rollout_paused: '暂停 Rollout',
  rollout_resumed: '恢复 Rollout',
  rollout_completed: '完成 Rollout',
};

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [agents, setAgents] = useState<AgentHealth[]>([]);
  const [alerts, setAlerts] = useState<CertAlertItem[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [trendData, setTrendData] = useState<{ date: string; count: number }[]>([]);

  const fetchData = async () => {
    setIsLoading(true);
    try {
      const [summaryData, healthData, alertsData, eventsData] = await Promise.all([
        apiFetch<DashboardSummary>('/dashboard/summary'),
        apiFetch<AgentHealth[]>('/dashboard/agents-health'),
        apiFetch<{
          summary: { external: { expired: number; critical: number; warning: number; notice: number }; agent: { expired: number; critical: number; warning: number; notice: number } };
          external_certs?: { expired?: CertAlertItem[]; critical?: CertAlertItem[]; warning?: CertAlertItem[] };
          agent_certs?: { expired?: CertAlertItem[]; critical?: CertAlertItem[]; warning?: CertAlertItem[] };
        }>('/dashboard/cert-alerts'),
        apiFetch<{ items: AuditEvent[] }>('/audit?limit=10'),
      ]);

      setSummary(summaryData);
      setAgents(healthData);
      setEvents(eventsData.items || []);

      const allAlerts: CertAlertItem[] = [
        ...(alertsData.external_certs?.expired || []),
        ...(alertsData.external_certs?.critical || []),
        ...(alertsData.external_certs?.warning || []),
        ...(alertsData.agent_certs?.expired || []),
        ...(alertsData.agent_certs?.critical || []),
        ...(alertsData.agent_certs?.warning || []),
      ];
      setAlerts(allAlerts);

      const criticalCount = (alertsData.summary.external.expired || 0) + (alertsData.summary.external.critical || 0) + (alertsData.summary.agent.expired || 0) + (alertsData.summary.agent.critical || 0);
      const warningCount = (alertsData.summary.external.warning || 0) + (alertsData.summary.agent.warning || 0);

      const expiryData = await apiFetch<{ id: string; subject_cn: string; not_after: string; days_remaining: number; urgency: string }[]>('/dashboard/certs-expiry?days=90');
      const now = new Date();
      const trendMap = new Map<string, number>();
      expiryData.forEach(cert => {
        const expiry = new Date(cert.not_after);
        const diffDays = Math.ceil((expiry.getTime() - now.getTime()) / (86400000));
        if (diffDays >= 0 && diffDays <= 90) {
          const key = new Date(now.getTime() + diffDays * 86400000).toISOString().slice(0, 10);
          trendMap.set(key, (trendMap.get(key) || 0) + 1);
        }
      });
      setTrendData(Array.from(trendMap.entries()).map(([date, count]) => ({ date, count })).sort((a, b) => a.date.localeCompare(b.date)));

      void criticalCount;
      void warningCount;
    } catch (err) {
      console.error('Failed to fetch dashboard data:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const errorNodes = agents.filter(a => a.liveness !== 'online').length;
  const onlineAgents = agents.filter(a => a.liveness === 'online').length;
  const totalAgents = agents.length;
  const criticalAlerts = alerts.filter(a => a.urgency === 'expired' || a.urgency === 'critical').length;
  const warningAlerts = alerts.filter(a => a.urgency === 'warning').length;

  return (
    <div className="space-y-5 animate-fade-in max-w-[1400px]">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-white tracking-tight">监控面板</h1>
          <p className="text-[13px] text-zinc-500 mt-0.5">系统概览与实时监控</p>
        </div>
        <button onClick={fetchData} className="btn-secondary flex items-center gap-1.5 text-[13px]" disabled={isLoading}>
          <RefreshCw size={13} className={isLoading ? 'animate-spin' : ''} />
          刷新
        </button>
      </div>

      <KPICards
        totalCerts={summary?.certificates.total_active || 0}
        criticalCount={criticalAlerts}
        warningCount={warningAlerts}
        errorNodes={errorNodes}
        onlineAgents={onlineAgents}
        totalAgents={totalAgents}
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2">
          <AlertTable alerts={alerts.map(a => ({
            id: a.id,
            domain: a.subject_cn,
            daysRemaining: a.days_remaining,
            urgency: a.urgency,
            notAfter: a.not_after,
            agent: a.agent_name,
          }))} isLoading={isLoading} />
        </div>
        <div>
          <AgentHealthCards
            agents={agents.map(a => ({
              id: a.id,
              name: a.name,
              liveness: a.liveness,
              lastSeen: a.last_seen ? formatDistanceToNow(new Date(a.last_seen), { addSuffix: true }) : null,
              certExpiresAt: a.cert_expires_at,
            }))}
            isLoading={isLoading}
          />
        </div>
      </div>

      <CertExpiryTrend data={trendData} isLoading={isLoading} />

      <div className="glass-panel p-5">
        <div className="flex items-center gap-2 mb-3">
          <History size={15} className="text-zinc-500" />
          <h3 className="text-sm font-medium text-white">最近操作</h3>
        </div>
        {events.length === 0 ? (
          <div className="text-center py-6 text-zinc-600 text-[13px]">暂无操作记录</div>
        ) : (
          <div className="space-y-2">
            {events.map(event => (
              <div key={event.id} className="flex items-start gap-2.5 text-[13px]">
                <div className="w-1 h-1 rounded-full bg-zinc-600 mt-1.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <span className="text-zinc-300">{actionLabels[event.action] || event.action}</span>
                  <span className="text-zinc-600 ml-1.5">{event.actor}</span>
                </div>
                <span className="text-[11px] text-zinc-600 shrink-0">
                  {formatDistanceToNow(new Date(event.created_at), { addSuffix: true })}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}