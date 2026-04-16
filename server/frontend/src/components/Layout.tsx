import { useEffect, useMemo, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { Bell, FileKey2, LayoutDashboard, Menu, Search, Server, Settings, ShieldCheck, X } from 'lucide-react';
import { apiFetch } from '../lib/api';

interface LayoutProps {
  onLogout: () => void;
}

const navItems = [
  {
    to: '/dashboard',
    icon: LayoutDashboard,
    label: '监控聚合',
    description: '风险、批次、健康',
    title: '监控聚合',
    subtitle: '查看证书风险、Agent 健康与分发状态。',
  },
  {
    to: '/certificates',
    icon: FileKey2,
    label: '证书资产',
    description: '资产、续期、分发',
    title: '证书资产',
    subtitle: '管理证书生命周期、节点绑定与安全策略。',
  },
  {
    to: '/agents',
    icon: Server,
    label: 'Agent 舰队',
    description: '接入、心跳、覆盖',
    title: 'Agent 舰队',
    subtitle: '集中处理节点接入审批、心跳异常与证书覆盖。',
  },
  {
    to: '/settings',
    icon: Settings,
    label: '系统设置',
    description: '认证、安全、网络',
    title: '系统设置',
    subtitle: '查看控制平面的认证、安全与运行设置。',
  },
];

interface AlertSummaryResponse {
  summary: {
    external: { expired: number; critical: number; warning: number; notice: number };
    agent: { expired: number; critical: number; warning: number; notice: number };
  };
}

function TopBar({
  alertCount,
  title,
  subtitle,
  onOpenMenu,
}: {
  alertCount: number;
  title: string;
  subtitle: string;
  onOpenMenu: () => void;
}) {
  return (
    <header className="border-b border-white/6 bg-[var(--bg-primary)] px-4 lg:px-6">
      <div className="flex flex-col gap-3 py-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex items-start gap-3">
          <button
            type="button"
            onClick={onOpenMenu}
            className="mt-0.5 inline-flex h-9 w-9 items-center justify-center rounded-md border border-white/10 bg-slate-950/70 text-slate-200 lg:hidden"
          >
            <Menu size={18} />
          </button>
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-white lg:text-xl">{title}</h1>
            <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
          </div>
        </div>

        <div className="flex flex-col gap-2 xl:min-w-[420px] xl:items-end">
          <div className="flex flex-wrap items-center gap-2 xl:justify-end">
            <div className="metric-badge border-white/10 bg-white/[0.03] text-slate-300">PROD</div>
            <button className="inline-flex items-center gap-2 rounded-md border border-white/10 bg-slate-950/70 px-3 py-2 text-xs font-medium text-slate-200 transition-colors hover:border-white/20 hover:text-white">
              <Bell size={14} className="text-slate-400" />
              告警
              <span className="rounded bg-rose-500/15 px-1.5 py-0.5 text-rose-200">{alertCount}</span>
            </button>
            <div className="flex h-9 w-9 items-center justify-center rounded-md border border-white/10 bg-white/[0.03] text-sm font-semibold text-white">
              A
            </div>
          </div>

          <label className="flex w-full items-center gap-2 rounded-md border border-white/10 bg-slate-950/70 px-3 py-2">
            <Search size={15} className="text-slate-500" />
            <input
              type="text"
              placeholder="搜索证书、Agent 或发布任务"
              className="w-full bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-500"
            />
          </label>
        </div>
      </div>
    </header>
  );
}

export default function Layout({ onLogout }: LayoutProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [alertCount, setAlertCount] = useState(0);
  const location = useLocation();
  const currentNav = useMemo(
    () =>
      navItems.find(({ to }) => location.pathname === to || (to !== '/dashboard' && location.pathname.startsWith(to))) ??
      navItems[0],
    [location.pathname]
  );

  useEffect(() => {
    let active = true;

    const fetchAlertSummary = async () => {
      try {
        const data = await apiFetch<AlertSummaryResponse>('/dashboard/cert-alerts');
        if (!active) {
          return;
        }

        setAlertCount(
          data.summary.external.expired +
            data.summary.external.critical +
            data.summary.agent.expired +
            data.summary.agent.critical
        );
      } catch {
        if (active) {
          setAlertCount(0);
        }
      }
    };

    void fetchAlertSummary();
    const timer = window.setInterval(() => {
      void fetchAlertSummary();
    }, 60000);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const sidebarContent = (
    <>
      <div className="border-b border-white/6 px-4 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-md border border-teal-300/15 bg-teal-500/10 text-teal-200">
            <ShieldCheck size={18} />
          </div>
          <div>
            <div className="text-sm font-semibold tracking-tight text-white">Cert Control</div>
            <div className="mt-1 text-xs text-slate-500">证书控制平面</div>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-between rounded-md border border-white/8 bg-white/[0.02] px-3 py-2 text-xs">
          <span className="text-slate-500">当前环境</span>
          <span className="font-medium text-white">Production</span>
        </div>
        <div className="mt-2 flex items-center justify-between rounded-md border border-white/8 bg-white/[0.02] px-3 py-2 text-xs">
          <span className="text-slate-500">高危告警</span>
          <span className="font-medium text-rose-200">{alertCount}</span>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map(({ to, icon: Icon, label, description }) => {
          const isActive = location.pathname === to || (to !== '/dashboard' && location.pathname.startsWith(to));
          return (
            <NavLink
              key={to}
              to={to}
              end={to === '/dashboard'}
              onClick={() => setMobileMenuOpen(false)}
              className={() =>
                `flex items-start gap-3 rounded-md border px-3 py-3 transition-colors ${
                  isActive
                    ? 'border-teal-300/15 bg-teal-500/8 text-white'
                    : 'border-transparent text-slate-400 hover:border-white/8 hover:bg-white/[0.02] hover:text-white'
                }`
              }
            >
              <div className={`mt-0.5 rounded-md p-2 ${isActive ? 'bg-teal-500/10 text-teal-100' : 'bg-white/[0.03] text-slate-500'}`}>
                <Icon size={16} strokeWidth={isActive ? 2 : 1.75} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium">{label}</div>
                <div className="mt-1 text-xs text-slate-500">{description}</div>
              </div>
            </NavLink>
          );
        })}
      </nav>

      <div className="px-3 pb-4">
        <div className="rounded-md border border-white/8 bg-white/[0.02] px-3 py-3 text-xs text-slate-400">
          <div className="flex items-center justify-between">
            <span>入口模式</span>
            <span className="font-medium text-white">Control Plane</span>
          </div>
          <div className="mt-2 flex items-center justify-between">
            <span>Agent API</span>
            <span className="font-medium text-white">独立鉴权</span>
          </div>
        </div>

        <button
          onClick={onLogout}
          className="mt-3 w-full rounded-md border border-white/10 px-3 py-2 text-left text-sm text-slate-400 transition-colors hover:border-rose-300/20 hover:bg-rose-500/8 hover:text-white"
        >
          退出登录
        </button>
      </div>
    </>
  );

  return (
    <div className="flex min-h-screen bg-[var(--bg-primary)] text-white">
      <aside className="hidden w-[296px] shrink-0 border-r border-white/6 bg-[var(--bg-primary)] lg:flex lg:flex-col">
        {sidebarContent}
      </aside>

      {mobileMenuOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" onClick={() => setMobileMenuOpen(false)}>
          <div className="absolute inset-0 bg-black/60" />
          <aside
            className="relative flex h-full w-[296px] flex-col border-r border-white/8 bg-[var(--bg-primary)]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-end px-4 pt-4">
              <button
                type="button"
                onClick={() => setMobileMenuOpen(false)}
                className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-white/10 bg-white/[0.03] text-slate-200"
              >
                <X size={18} />
              </button>
            </div>
            {sidebarContent}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          alertCount={alertCount}
          title={currentNav.title}
          subtitle={currentNav.subtitle}
          onOpenMenu={() => setMobileMenuOpen(true)}
        />
        <main className="flex-1 overflow-auto px-4 py-5 lg:px-6 lg:py-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
