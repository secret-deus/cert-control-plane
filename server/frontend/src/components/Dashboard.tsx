import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ShieldCheck, Wifi } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { apiFetch } from '../lib/api';
import AlertTable from './AlertTable';
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

interface AlertBucket {
  expired: number;
  critical: number;
  warning: number;
  notice: number;
}

interface CertAlertResponse {
  summary: {
    external: AlertBucket;
    agent: AlertBucket;
  };
  external_certs?: {
    expired?: CertAlertItem[];
    critical?: CertAlertItem[];
    warning?: CertAlertItem[];
  };
  agent_certs?: {
    expired?: CertAlertItem[];
    critical?: CertAlertItem[];
    warning?: CertAlertItem[];
  };
}

const chartTooltipStyle = {
  borderRadius: 12,
  border: '1px solid rgba(255,255,255,0.08)',
  background: 'rgba(15,18,24,0.98)',
  boxShadow: '0 14px 30px rgba(0,0,0,0.35)',
};

const agentTone: Record<AgentHealth['liveness'], string> = {
  online: 'border-[rgba(115,191,105,0.24)] bg-[rgba(115,191,105,0.10)] text-[#9adf90]',
  delayed: 'border-[rgba(242,204,12,0.24)] bg-[rgba(242,204,12,0.10)] text-[#f6d94b]',
  offline: 'border-[rgba(242,73,92,0.24)] bg-[rgba(242,73,92,0.10)] text-[#ff8d9a]',
};

const agentLabel: Record<AgentHealth['liveness'], string> = {
  online: '在线',
  delayed: '延迟',
  offline: '离线',
};

function ChartSkeleton() {
  return <div className="skeleton h-[240px] rounded-[24px]" />;
}

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [agents, setAgents] = useState<AgentHealth[]>([]);
  const [alerts, setAlerts] = useState<CertAlertItem[]>([]);
  const [alertSummary, setAlertSummary] = useState<CertAlertResponse['summary'] | null>(null);
  const [trendData, setTrendData] = useState<{ date: string; count: number }[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setIsLoading(true);

    try {
      const [summaryData, healthData, alertsData, expiryData] = await Promise.all([
        apiFetch<DashboardSummary>('/dashboard/summary'),
        apiFetch<AgentHealth[]>('/dashboard/agents-health'),
        apiFetch<CertAlertResponse>('/dashboard/cert-alerts'),
        apiFetch<{ id: string; subject_cn: string; not_after: string; days_remaining: number; urgency: string }[]>('/dashboard/certs-expiry?days=90'),
      ]);

      setSummary(summaryData);
      setAgents(healthData);
      setAlertSummary(alertsData.summary);

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

  const onlineAgents = agents.filter((agent) => agent.liveness === 'online').length;
  const delayedAgents = agents.filter((agent) => agent.liveness === 'delayed').length;
  const offlineAgents = agents.filter((agent) => agent.liveness === 'offline').length;
  const connectedAgents = agents.length;
  const abnormalAgents = agents.filter((agent) => agent.liveness !== 'online').slice(0, 5);
  const pendingApprovals = summary?.agents.pending_approval || 0;
  const runningRollouts = summary?.rollouts.running || 0;
  const totalActiveCerts = summary?.certificates.total_active || 0;

  const riskSummary = useMemo(() => {
    const expired = (alertSummary?.external.expired || 0) + (alertSummary?.agent.expired || 0);
    const critical = (alertSummary?.external.critical || 0) + (alertSummary?.agent.critical || 0);
    const warning = (alertSummary?.external.warning || 0) + (alertSummary?.agent.warning || 0);
    return {
      expired,
      critical,
      warning,
      within7Days: expired + critical,
      within30Days: expired + critical + warning,
    };
  }, [alertSummary]);

  const kpis = [
    {
      label: 'Certificates',
      title: '证书总数',
      value: totalActiveCerts,
      hint: `批次 ${runningRollouts}`,
      icon: ShieldCheck,
      tone: 'text-white',
    },
    {
      label: 'Expiring 7D',
      title: '7天内过期',
      value: riskSummary.within7Days,
      hint: `${riskSummary.expired} 已过期`,
      icon: AlertTriangle,
      tone: 'text-white',
    },
    {
      label: 'Agents Online',
      title: '在线Agent',
      value: `${onlineAgents}/${connectedAgents}`,
      hint: `异常 ${delayedAgents + offlineAgents}`,
      icon: Wifi,
      tone: 'text-white',
    },
  ];

  const agentStatusChart = [
    { name: '在线', value: onlineAgents, color: '#73bf69' },
    { name: '延迟', value: delayedAgents, color: '#f2cc0c' },
    { name: '离线', value: offlineAgents, color: '#f2495c' },
  ].filter((item) => item.value > 0);

  return (
    <div className="mx-auto max-w-[1520px] space-y-6 animate-fade-in">
      <div className="grid gap-4 xl:grid-cols-3">
        {kpis.map(({ label, title, value, hint, icon: Icon, tone }) => (
          <section key={label} className="glass-panel rounded-[24px] px-5 py-5">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-[18px] border border-white/6 bg-white/[0.03] text-white">
                <Icon size={20} />
              </div>
              <div className={`min-w-0 ${tone}`}>
                <div className="text-[13px] text-neutral-400">{title}</div>
                <div className="mt-1 text-[2rem] font-semibold leading-none text-white">{value}</div>
                <div className="mt-2 text-xs tracking-[0.12em] text-neutral-500 uppercase">{hint}</div>
              </div>
            </div>
          </section>
        ))}
      </div>

      <CertExpiryTrend
        data={trendData}
        isLoading={isLoading}
        totalCerts={totalActiveCerts}
        within7Days={riskSummary.within7Days}
        within30Days={riskSummary.within30Days}
        pendingApprovals={pendingApprovals}
        runningRollouts={runningRollouts}
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.58fr)_390px]">
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

        <section className="glass-panel rounded-[24px] px-5 py-5 lg:px-6 lg:py-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[13px] font-medium text-slate-400">Agent 健康状态</div>
              <h3 className="mt-1 text-[1.35rem] font-semibold tracking-tight text-white">Fleet Health</h3>
            </div>
            <span className="metric-badge border-white/8 bg-white/[0.03] text-neutral-300">总数 {connectedAgents}</span>
          </div>

          <div className="ops-chart-frame relative mt-5 h-[220px] p-3">
            {isLoading && !summary ? (
              <ChartSkeleton />
            ) : agentStatusChart.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-slate-500">暂无 Agent 数据。</div>
            ) : (
              <>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={agentStatusChart} dataKey="value" nameKey="name" innerRadius={56} outerRadius={82} paddingAngle={3} stroke="rgba(15,23,42,0.65)" strokeWidth={2}>
                      {agentStatusChart.map((item) => (
                        <Cell key={item.name} fill={item.color} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={chartTooltipStyle} labelStyle={{ color: '#cbd5e1', fontSize: 12 }} itemStyle={{ color: '#f8fafc', fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                  <div className="text-center">
                    <div className="text-3xl font-semibold tracking-tight text-white">{onlineAgents}</div>
                    <div className="mt-1 text-[11px] uppercase tracking-[0.18em] text-slate-500">在线节点</div>
                  </div>
                </div>
              </>
            )}
          </div>

          <div className="mt-4 grid grid-cols-3 gap-3">
            {[
              { label: '在线', value: onlineAgents, tone: 'border-white/8 bg-white/[0.02] text-white', accent: 'text-[#9adf90]' },
              { label: '延迟', value: delayedAgents, tone: 'border-white/8 bg-white/[0.02] text-white', accent: 'text-[#ffbf8f]' },
              { label: '离线', value: offlineAgents, tone: 'border-white/8 bg-white/[0.02] text-white', accent: 'text-[#ffbf8f]' },
            ].map((item) => (
              <div key={item.label} className={`rounded-[18px] border px-3 py-3 ${item.tone}`}>
                <div className="text-[11px] uppercase tracking-[0.16em] text-white/65">{item.label}</div>
                <div className={`mt-2 text-2xl font-semibold ${item.accent}`}>{item.value}</div>
              </div>
            ))}
          </div>

          <div className="mt-5 space-y-2.5">
            {abnormalAgents.length === 0 ? (
              <div className="ops-chart-frame px-4 py-6 text-center text-sm text-slate-500">当前没有异常 Agent。</div>
            ) : (
              abnormalAgents.map((agent) => (
                <div key={agent.id} className="rounded-[18px] border border-white/8 bg-white/[0.02] px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-white">{agent.name}</div>
                      <div className="mt-1 text-xs text-slate-500">
                        {agent.last_seen ? formatDistanceToNow(new Date(agent.last_seen), { addSuffix: true }) : '从未连接'}
                      </div>
                    </div>
                    <span className={`shrink-0 rounded-full border px-2 py-0.5 text-xs ${agentTone[agent.liveness]}`}>
                      {agentLabel[agent.liveness]}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
