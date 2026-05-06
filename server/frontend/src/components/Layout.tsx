import { useEffect, useMemo, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { Bell, FileKey2, LayoutDashboard, Menu, Server, Settings, ShieldCheck, X } from 'lucide-react';
import { apiFetch } from '../lib/api';

interface LayoutProps {
  onLogout: () => void;
}

const navItems = [
  {
    to: '/dashboard',
    icon: LayoutDashboard,
    label: '监控聚合',
    title: '监控聚合',
    subtitle: 'Dashboard',
  },
  {
    to: '/certificates',
    icon: FileKey2,
    label: '证书资产',
    title: '证书资产',
    subtitle: 'Certificates',
  },
  {
    to: '/agents',
    icon: Server,
    label: 'Agent 舰队',
    title: 'Agent 舰队',
    subtitle: 'Agents',
  },
  {
    to: '/settings',
    icon: Settings,
    label: '系统设置',
    title: '系统设置',
    subtitle: 'Settings',
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
    <header className="border-b border-white/6 bg-[#101010] px-6 py-6 lg:px-8">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex items-start gap-3">
          <button
            type="button"
            onClick={onOpenMenu}
            className="mt-0.5 inline-flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/[0.03] text-white lg:hidden"
          >
            <Menu size={18} />
          </button>
          <div>
            <div className="text-[11px] font-medium tracking-[0.16em] text-white/50">Pages / {subtitle}</div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white lg:text-[2.4rem]">{title}</h1>
          </div>
        </div>

        <div className="flex items-center gap-3 xl:justify-end">
          <button className="inline-flex items-center gap-2 rounded-2xl border border-white/8 bg-white/[0.03] px-3 py-2 text-xs font-medium text-white/80 transition-colors hover:border-white/12 hover:text-white">
              <Bell size={14} className="text-white/70" />
              <span className="text-white/80">Alerts</span>
            <span className="rounded-xl bg-[rgba(255,153,92,0.16)] px-1.5 py-0.5 text-[#ffbf8f]">{alertCount}</span>
          </button>
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/8 bg-white/[0.03] text-sm font-semibold text-white">
            A
          </div>
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
      <div className="border-b border-white/6 px-4 py-5">
        <div className="flex items-center gap-3 px-2 py-2">
          <div className="flex h-11 w-11 items-center justify-center rounded-[18px] border border-white/8 bg-white/[0.03] text-white">
            <ShieldCheck size={18} />
          </div>
          <div>
            <div className="text-[22px] font-semibold tracking-tight text-white">CertControl</div>
            <div className="mt-1 text-xs tracking-[0.16em] text-white/50">CONTROL PLANE</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map(({ to, icon: Icon, label }) => {
          const isActive = location.pathname === to || (to !== '/dashboard' && location.pathname.startsWith(to));
          return (
            <NavLink
              key={to}
              to={to}
              end={to === '/dashboard'}
              onClick={() => setMobileMenuOpen(false)}
              className={() =>
                `flex items-center gap-3 rounded-[18px] border px-4 py-4 transition-colors ${
                  isActive
                    ? 'border-transparent bg-white/[0.07] text-white'
                    : 'border-transparent text-white/70 hover:border-transparent hover:bg-white/[0.02] hover:text-white'
                }`
              }
            >
              <div className={`rounded-[14px] p-2.5 ${isActive ? 'bg-white/[0.05] text-white' : 'bg-transparent text-white/50'}`}>
                <Icon size={18} strokeWidth={isActive ? 2.2 : 1.8} />
              </div>
              <div className="min-w-0 flex-1 text-[15px] font-medium">{label}</div>
            </NavLink>
          );
        })}
      </nav>

      <div className="px-3 pb-4">
        <div className="rounded-[18px] border border-white/8 bg-white/[0.02] px-4 py-4 text-xs text-white/70">
          <div className="flex items-center justify-between">
            <span>入口模式</span>
            <span className="font-medium text-white">单端口</span>
          </div>
          <div className="mt-2 flex items-center justify-between">
            <span>Agent API</span>
            <span className="font-medium text-white">/api/agent</span>
          </div>
        </div>

        <button
          onClick={onLogout}
          className="mt-3 w-full rounded-[18px] border border-white/8 px-4 py-3 text-left text-sm text-white/70 transition-colors hover:border-white/12 hover:bg-white/[0.03] hover:text-white"
        >
          退出登录
        </button>
      </div>
    </>
  );

  return (
    <div className="flex min-h-screen bg-[#101010] text-white">
      <aside className="hidden w-[256px] shrink-0 border-r border-white/6 bg-[#161616] lg:flex lg:flex-col">
          {sidebarContent}
      </aside>

      {mobileMenuOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" onClick={() => setMobileMenuOpen(false)}>
          <div className="absolute inset-0 bg-black/60" />
          <aside
            className="relative flex h-full w-[296px] flex-col border-r border-white/8 bg-[#161616]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-end px-4 pt-4">
              <button
                type="button"
                onClick={() => setMobileMenuOpen(false)}
                  className="inline-flex h-10 w-10 items-center justify-center rounded-[18px] border border-white/8 bg-white/[0.03] text-white"
              >
                <X size={18} />
              </button>
            </div>
            {sidebarContent}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col bg-[#101010]">
        <TopBar
          alertCount={alertCount}
          title={currentNav.title}
          subtitle={currentNav.subtitle}
          onOpenMenu={() => setMobileMenuOpen(true)}
        />
        <main className="flex-1 overflow-auto px-6 py-6 lg:px-8 lg:py-7">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
