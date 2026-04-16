import { useCallback, useEffect, useState } from 'react';
import { Activity, History, RefreshCw, Server, ShieldCheck } from 'lucide-react';
import { format, formatDistanceToNow } from 'date-fns';
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

interface Rollout {
  id: string;
  name: string;
  status: string;
  current_batch: number;
  total_batches: number;
  updated_at: string;
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

const rolloutTone: Record<string, string> = {
  pending: 'border-white/10 bg-white/5 text-slate-200',
  running: 'border-teal-300/15 bg-teal-500/10 text-teal-100',
  paused: 'border-amber-300/15 bg-amber-500/10 text-amber-200',
  completed: 'border-emerald-300/15 bg-emerald-500/10 text-emerald-200',
  failed: 'border-rose-300/15 bg-rose-500/10 text-rose-200',
};

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [agents, setAgents] = useState<AgentHealth[]>([]);
  const [alerts, setAlerts] = useState<CertAlertItem[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [rollouts, setRollouts] = useState<Rollout[]>([]);
  const [trendData, setTrendData] = useState<{ date: string; count: number }[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setIsLoading(true);

    try {
      const [summaryData, healthData, alertsData, eventsData, expiryData, rolloutData] = await Promise.all([
        apiFetch<DashboardSummary>('/dashboard/summary'),
        apiFetch<AgentHealth[]>('/dashboard/agents-health'),
        apiFetch<{
          summary: {
            external: { expired: number; critical: number; warning: number; notice: number };
            agent: { expired: number; critical: number; warning: number; notice: number };
          };
          external_certs?: { expired?: CertAlertItem[]; critical?: CertAlertItem[]; warning?: CertAlertItem[] };
          agent_certs?: { expired?: CertAlertItem[]; critical?: CertAlertItem[]; warning?: CertAlertItem[] };
        }>('/dashboard/cert-alerts'),
        apiFetch<{ items: AuditEvent[] }>('/audit?limit=10'),
        apiFetch<{ id: string; subject_cn: string; not_after: string; days_remaining: number; urgency: string }[]>('/dashboard/certs-expiry?days=90'),
        apiFetch<{ items: Rollout[] }>('/rollouts?limit=4'),
      ]);

      setSummary(summaryData);
      setAgents(healthData);
      setEvents(eventsData.items || []);
      setRollouts(rolloutData.items || []);

      const allAlerts: CertAlertItem[] = [
        ...(alertsData.external_certs?.expired || []),
        ...(alertsData.external_certs?.critical || []),
        ...(alertsData.external_certs?.warning || []),
        ...(alertsData.agent_certs?.expired || []),
        ...(alertsData.agent_certs?.critical || []),
        ...(alertsData.agent_certs?.warning || []),
      ];
      setAlerts(allAlerts);

      const now = new Date();
      const trendMap = new Map<string, number>();
      expiryData.forEach((cert) => {
        const expiry = new Date(cert.not_after);
        const diffDays = Math.ceil((expiry.getTime() - now.getTime()) / 86400000);
        if (diffDays >= 0 && diffDays <= 90) {
          const key = new Date(now.getTime() + diffDays * 86400000).toISOString().slice(0, 10);
          trendMap.set(key, (trendMap.get(key) || 0) + 1);
        }
      });
      setTrendData(
        Array.from(trendMap.entries())
          .map(([date, count]) => ({ date, count }))
          .sort((left, right) => left.date.localeCompare(right.date))
      );
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchData();
    const interval = window.setInterval(() => {
      void fetchData();
    }, 30000);

    return () => window.clearInterval(interval);
  }, [fetchData]);

  const errorNodes = agents.filter((agent) => agent.liveness !== 'online').length;
  const onlineAgents = agents.filter((agent) => agent.liveness === 'online').length;
  const totalAgents = agents.length;
  const criticalAlerts = alerts.filter((alert) => alert.urgency === 'expired' || alert.urgency === 'critical').length;
  const warningAlerts = alerts.filter((alert) => alert.urgency === 'warning').length;
  const onlineRate = totalAgents > 0 ? Math.round((onlineAgents / totalAgents) * 100) : 0;
  const pendingApprovals = summary?.agents.pending_approval || 0;

  const signalCards = [
    {
      label: '风险压强',
      value: criticalAlerts + warningAlerts,
      hint: criticalAlerts > 0 ? `${criticalAlerts} 项需要立即处理` : '暂无立即风险项',
      tone: 'border-rose-300/15 bg-rose-500/10 text-rose-100',
      icon: ShieldCheck,
    },
    {
      label: 'Agent 在线率',
      value: `${onlineRate}%`,
      hint: `${onlineAgents}/${Math.max(totalAgents, 1)} 节点在线`,
      tone: 'border-emerald-300/15 bg-emerald-500/10 text-emerald-100',
      icon: Server,
    },
    {
      label: '发布队列',
      value: summary?.rollouts.running || 0,
      hint: pendingApprovals > 0 ? `${pendingApprovals} 个待审批 Agent` : '当前无准入阻塞',
      tone: 'border-teal-300/15 bg-teal-500/10 text-teal-100',
      icon: Activity,
    },
  ];

  return (
    <div className="mx-auto max-w-[1480px] space-y-6 animate-fade-in">
      <section className="glass-panel p-5 lg:p-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <div className="section-kicker">Overview</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white">监控聚合</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
              这里按风险、批次和舰队三个视角汇总当前状态，优先看异常，再往下钻取明细。
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="metric-badge border-white/10 bg-white/[0.03] text-slate-300">证书 {summary?.certificates.total_active || 0}</span>
              <span className="metric-badge border-rose-300/15 bg-rose-500/10 text-rose-200">高危 {criticalAlerts}</span>
              <span className="metric-badge border-white/10 bg-white/[0.03] text-slate-300">批次 {summary?.rollouts.running || 0}</span>
            </div>
          </div>

          <div className="flex items-center gap-2 xl:pt-1">
            <button onClick={() => void fetchData()} className="btn-secondary flex items-center gap-1.5 text-[13px]" disabled={isLoading}>
              <RefreshCw size={13} className={isLoading ? 'animate-spin' : ''} />
              刷新面板
            </button>
          </div>
        </div>

        <div className="mt-5 grid gap-3 lg:grid-cols-3">
          {signalCards.map(({ label, value, hint, tone, icon: Icon }) => (
            <div key={label} className={`rounded-md border p-4 ${tone}`}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-white/60">{label}</div>
                  <div className="mt-2 text-2xl font-semibold text-white">{value}</div>
                  <div className="mt-2 text-sm text-white/70">{hint}</div>
                </div>
                <div className="rounded-md border border-white/10 bg-white/5 p-2.5 text-white">
                  <Icon size={16} />
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <KPICards
        totalCerts={summary?.certificates.total_active || 0}
        criticalCount={criticalAlerts}
        warningCount={warningAlerts}
        errorNodes={errorNodes}
        onlineAgents={onlineAgents}
        totalAgents={totalAgents}
      />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.8fr)_360px]">
        <div className="space-y-5">
          <AlertTable
            alerts={alerts.map((alert) => ({
              id: alert.id,
              domain: alert.subject_cn,
              daysRemaining: alert.days_remaining,
              urgency: alert.urgency,
              notAfter: alert.not_after,
              agent: alert.agent_name,
              source: alert.source === 'agent' ? 'Agent 证书' : '外部证书',
            }))}
            isLoading={isLoading}
          />

          <div className="grid gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <CertExpiryTrend data={trendData} isLoading={isLoading} />

            <div className="glass-panel p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="section-kicker">Rollout Watch</div>
                  <h3 className="mt-2 text-lg font-semibold text-white">分发批次</h3>
                  <p className="mt-1 text-sm text-slate-400">把运行中的灰度和近期批次直接拉到首页观察。</p>
                </div>
                <span className="metric-badge border-white/10 bg-white/5 text-slate-300">{rollouts.length} 条</span>
              </div>

              <div className="mt-5 space-y-3">
                {rollouts.length === 0 ? (
                  <div className="rounded-lg border border-white/6 bg-white/[0.02] px-4 py-6 text-center text-sm text-slate-500">
                    当前没有分发批次。
                  </div>
                ) : (
                  rollouts.map((rollout) => {
                    const normalizedStatus = rollout.status.toLowerCase();
                    return (
                      <div key={rollout.id} className="rounded-lg border border-white/8 bg-white/[0.03] p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="font-medium text-white">{rollout.name}</div>
                            <div className="mt-1 text-xs text-slate-500">更新于 {format(new Date(rollout.updated_at), 'MM-dd HH:mm')}</div>
                          </div>
                          <span className={`rounded-full border px-2 py-0.5 text-xs ${rolloutTone[normalizedStatus] || rolloutTone.pending}`}>
                            {normalizedStatus}
                          </span>
                        </div>
                        <div className="mt-4 flex items-center justify-between text-sm text-slate-400">
                          <span>批次进度</span>
                          <span className="text-white">{rollout.current_batch} / {rollout.total_batches}</span>
                        </div>
                        <div className="mt-2 h-1.5 rounded-full bg-white/5">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-teal-300 to-teal-500"
                            style={{ width: `${Math.min(100, rollout.total_batches > 0 ? (rollout.current_batch / rollout.total_batches) * 100 : 0)}%` }}
                          />
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>

          <div className="glass-panel p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="section-kicker">Audit Feed</div>
                <div className="mt-2 flex items-center gap-2">
                  <History size={18} className="text-slate-400" />
                  <h3 className="text-lg font-semibold text-white">最近操作</h3>
                </div>
                <p className="mt-1 text-sm text-slate-400">关键动作保留在首页，方便快速回溯谁做了什么。</p>
              </div>
              <span className="metric-badge border-white/10 bg-white/5 text-slate-300">{events.length} 条</span>
            </div>

            {events.length === 0 ? (
              <div className="py-8 text-center text-sm text-slate-500">暂无操作记录。</div>
            ) : (
              <div className="mt-5 space-y-3">
                {events.map((event) => (
                  <div key={event.id} className="rounded-lg border border-white/8 bg-white/[0.03] p-4">
                    <div className="flex items-start gap-3">
                      <div className="mt-1 h-2.5 w-2.5 rounded-full bg-teal-300" />
                      <div className="min-w-0 flex-1">
                        <div className="text-sm text-white">{actionLabels[event.action] || event.action}</div>
                        <div className="mt-1 text-xs text-slate-500">操作者 {event.actor}</div>
                      </div>
                      <div className="shrink-0 text-xs text-slate-500">
                        {formatDistanceToNow(new Date(event.created_at), { addSuffix: true })}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="space-y-5">
          <AgentHealthCards
            agents={agents.map((agent) => ({
              id: agent.id,
              name: agent.name,
              liveness: agent.liveness,
              lastSeen: agent.last_seen ? formatDistanceToNow(new Date(agent.last_seen), { addSuffix: true }) : null,
              certExpiresAt: agent.cert_expires_at,
            }))}
            isLoading={isLoading}
          />

          <div className="glass-panel p-5">
            <div className="section-kicker">Environment Snapshot</div>
            <h3 className="mt-2 text-lg font-semibold text-white">运行摘要</h3>
            <div className="mt-5 space-y-4 text-sm">
              <div className="rounded-lg border border-white/8 bg-white/[0.03] p-4">
                <div className="text-slate-400">在线节点</div>
                <div className="mt-2 text-3xl font-semibold text-white">{onlineAgents}</div>
                <div className="mt-2 text-xs text-slate-500">覆盖率 {onlineRate}%</div>
              </div>
              <div className="rounded-lg border border-white/8 bg-white/[0.03] p-4">
                <div className="text-slate-400">待审批 Agent</div>
                <div className="mt-2 text-3xl font-semibold text-white">{pendingApprovals}</div>
                <div className="mt-2 text-xs text-slate-500">新节点接入需要审批通过才能加入分发。</div>
              </div>
              <div className="rounded-lg border border-white/8 bg-white/[0.03] p-4">
                <div className="text-slate-400">30 天内到期</div>
                <div className="mt-2 text-3xl font-semibold text-white">{summary?.certificates.expiring_soon || 0}</div>
                <div className="mt-2 text-xs text-slate-500">结合风险队列决定本周续期窗口。</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
