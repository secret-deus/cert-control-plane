import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ShieldCheck, Wifi, Clock, RefreshCw } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { apiFetch } from '../lib/api';
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

interface ExternalCert {
  id: string;
  subject_cn: string;
  not_after: string;
  provider?: string;
}

interface CertAlertItem {
  id: string;
  subject_cn: string;
  days_remaining: number;
  urgency: 'expired' | 'critical' | 'warning' | 'notice';
  not_after: string;
  type: 'external' | 'agent';
  provider?: string;
}

interface CertAlertResponse {
  summary: {
    external: { expired: number; critical: number; warning: number; notice: number };
    agent: { expired: number; critical: number; warning: number; notice: number };
  };
  external_certs?: {
    expired?: CertAlertItem[];
    critical?: CertAlertItem[];
    warning?: CertAlertItem[];
    notice?: CertAlertItem[];
  };
  agent_certs?: {
    expired?: CertAlertItem[];
    critical?: CertAlertItem[];
    warning?: CertAlertItem[];
    notice?: CertAlertItem[];
  };
}

const chartTooltipStyle = {
  borderRadius: 12,
  border: '1px solid rgba(255,255,255,0.08)',
  background: 'rgba(13,17,23,0.98)',
  boxShadow: '0 14px 30px rgba(0,0,0,0.35)',
  backdropFilter: 'blur(8px)',
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
  const [externalCerts, setExternalCerts] = useState<ExternalCert[]>([]);
  const [alertData, setAlertData] = useState<CertAlertResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchData = useCallback(async () => {
    setIsLoading(true);

    try {
      const [summaryData, healthData, alertsData, extCertsData] = await Promise.all([
        apiFetch<DashboardSummary>('/dashboard/summary'),
        apiFetch<AgentHealth[]>('/dashboard/agents-health'),
        apiFetch<CertAlertResponse>('/dashboard/cert-alerts'),
        apiFetch<{ items: ExternalCert[]; total: number }>('/external-certs?limit=100'),
      ]);

      setSummary(summaryData);
      setAgents(healthData);
      setAlertData(alertsData);
      setExternalCerts(extCertsData.items);
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const [summaryData, healthData, alertsData, extCertsData] = await Promise.all([
        apiFetch<DashboardSummary>('/dashboard/summary'),
        apiFetch<AgentHealth[]>('/dashboard/agents-health'),
        apiFetch<CertAlertResponse>('/dashboard/cert-alerts'),
        apiFetch<{ items: ExternalCert[]; total: number }>('/external-certs?limit=100'),
      ]);

      setSummary(summaryData);
      setAgents(healthData);
      setAlertData(alertsData);
      setExternalCerts(extCertsData.items);
    } catch (error) {
      console.error('Failed to refresh dashboard data:', error);
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const onlineAgents = agents.filter((agent) => agent.liveness === 'online').length;
  const delayedAgents = agents.filter((agent) => agent.liveness === 'delayed').length;
  const offlineAgents = agents.filter((agent) => agent.liveness === 'offline').length;
  const connectedAgents = agents.length;
  const abnormalAgents = agents.filter((agent) => agent.liveness !== 'online').slice(0, 5);
  const pendingApprovals = summary?.agents.pending_approval || 0;
  const runningRollouts = summary?.rollouts.running || 0;

  const allCertsForTable = useMemo(() => {
    const now = new Date();
    const alertCerts: CertAlertItem[] = [
      ...(alertData?.external_certs?.expired || []),
      ...(alertData?.external_certs?.critical || []),
      ...(alertData?.external_certs?.warning || []),
      ...(alertData?.external_certs?.notice || []),
    ];
    const certMap = new Map<string, { id: string; domain: string; daysRemaining: number; urgency: 'expired' | 'critical' | 'warning' | 'notice' | 'normal'; notAfter: string; provider?: string }>();
    alertCerts.forEach((c) => {
      certMap.set(c.id, {
        id: c.id,
        domain: c.subject_cn,
        daysRemaining: c.days_remaining,
        urgency: c.urgency,
        notAfter: c.not_after.replace(/\+00:00$/, 'Z'),
        provider: c.provider,
      });
    });
    externalCerts.forEach((c) => {
      if (!certMap.has(c.id)) {
        const notAfterStr = c.not_after.replace(/\+00:00$/, 'Z');
        const notAfter = new Date(notAfterStr);
        const days = Math.ceil((notAfter.getTime() - now.getTime()) / 86400000);
        let urgency: 'expired' | 'critical' | 'warning' | 'notice' | 'normal' = 'normal';
        if (days < 0) urgency = 'expired';
        else if (days <= 7) urgency = 'critical';
        else if (days <= 30) urgency = 'warning';
        else if (days <= 60) urgency = 'notice';
        certMap.set(c.id, {
          id: c.id,
          domain: c.subject_cn,
          daysRemaining: days,
          urgency,
          notAfter: notAfterStr,
          provider: c.provider,
        });
      }
    });
    return Array.from(certMap.values());
  }, [alertData, externalCerts]);

  const expiryDistribution = useMemo(() => {
    let within7 = 0;
    let within30 = 0;
    let within60 = 0;
    let beyond60 = 0;
    allCertsForTable.forEach((c) => {
      if (c.daysRemaining < 0 || c.daysRemaining <= 7) within7++;
      else if (c.daysRemaining <= 30) within30++;
      else if (c.daysRemaining <= 60) within60++;
      else beyond60++;
    });
    return [
      { bucket: '7天内', name: '7天内', count: within7, color: '#f2495c' },
      { bucket: '7-30天', name: '7-30天', count: within30, color: '#f2cc0c' },
      { bucket: '30-60天', name: '30-60天', count: within60, color: '#5794f2' },
      { bucket: '60天以上', name: '60天以上', count: beyond60, color: '#73bf69' },
    ];
  }, [allCertsForTable]);

  const kpis = [
    {
      label: 'Certificates',
      title: '证书总数',
      value: externalCerts.length,
      hint: `批次 ${runningRollouts}`,
      icon: ShieldCheck,
      tone: 'text-white',
    },
    {
      label: 'Expiring 7D',
      title: '7天内过期',
      value: expiryDistribution[0].count,
      hint: `需立即处理`,
      icon: AlertTriangle,
      tone: expiryDistribution[0].count > 0 ? 'text-[#f2495c]' : 'text-white',
    },
    {
      label: 'Expiring 30D',
      title: '7-30天过期',
      value: expiryDistribution[1].count,
      hint: `纳入续期计划`,
      icon: Clock,
      tone: expiryDistribution[1].count > 0 ? 'text-[#f2cc0c]' : 'text-white',
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
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Dashboard</h1>
        <button
          onClick={() => handleRefresh()}
          disabled={isRefreshing}
          className="flex items-center gap-2 rounded-[14px] border border-white/6 bg-white/[0.03] px-3 py-2 text-sm text-white/70 transition hover:bg-white/[0.06] hover:text-white disabled:opacity-50"
        >
          <RefreshCw size={14} className={isRefreshing ? 'animate-spin' : ''} />
          刷新
        </button>
      </div>

      <div className="grid gap-4 xl:grid-cols-4">
        {kpis.map(({ label, title, value, hint, icon: Icon, tone }) => (
          <section key={label} className="glass-panel rounded-[24px] px-5 py-5">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-[18px] border border-white/6 bg-white/[0.03] text-white">
                <Icon size={20} />
              </div>
              <div className={`min-w-0 ${tone}`}>
                <div className="text-[13px] text-white/70">{title}</div>
                <div className="mt-1 text-[2rem] font-semibold leading-none text-white">{value}</div>
                <div className="mt-2 text-xs tracking-[0.12em] text-white/50 uppercase">{hint}</div>
              </div>
            </div>
          </section>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <CertExpiryTrend
          isLoading={isLoading}
          totalCerts={externalCerts.length}
          within7Days={expiryDistribution[0].count}
          within30Days={expiryDistribution[0].count + expiryDistribution[1].count}
          pendingApprovals={pendingApprovals}
          runningRollouts={runningRollouts}
          expiryDistribution={expiryDistribution}
        />

        <section className="glass-panel rounded-[24px] px-5 py-5 lg:px-6 lg:py-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[13px] font-medium text-white/70">Agent 健康状态</div>
              <h3 className="mt-1 text-[1.35rem] font-semibold tracking-tight text-white">Fleet Health</h3>
            </div>
            <span className="metric-badge border-white/8 bg-white/[0.03] text-white/80">总数 {connectedAgents}</span>
          </div>

          <div className="ops-chart-frame relative mt-5 h-[220px] p-3" style={{ minWidth: 0 }}>
            {isLoading && !summary ? (
              <ChartSkeleton />
            ) : agentStatusChart.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-white/50">暂无 Agent 数据。</div>
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
                    <div className="mt-1 text-[11px] uppercase tracking-[0.18em] text-white/50">在线节点</div>
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
              <div className="ops-chart-frame px-4 py-6 text-center text-sm text-white/50">当前没有异常 Agent。</div>
            ) : (
              abnormalAgents.map((agent) => (
                <div key={agent.id} className="rounded-[18px] border border-white/8 bg-white/[0.02] px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-white">{agent.name}</div>
                      <div className="mt-1 text-xs text-white/50">
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
