import { useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { LayoutDashboard, ShieldCheck, Server, FileKey2, Settings, Menu, Bell, Search } from 'lucide-react';

interface LayoutProps {
  onLogout: () => void;
}

const navItems = [
  { to: '/dashboard', icon: LayoutDashboard, label: '监控面板' },
  { to: '/certificates', icon: FileKey2, label: '证书管理' },
  { to: '/agents', icon: Server, label: 'Agent 管理' },
  { to: '/settings', icon: Settings, label: '系统设置' },
];

function TopBar({ alertCount }: { alertCount: number }) {
  return (
    <header className="h-12 border-b border-zinc-800 flex items-center justify-between px-5 bg-[var(--bg-primary)]">
      <div className="flex items-center gap-2.5 flex-1 max-w-sm">
        <Search size={15} className="text-zinc-600" />
        <input
          type="text"
          placeholder="搜索..."
          className="bg-transparent text-[13px] text-zinc-300 placeholder-zinc-600 outline-none w-full"
        />
      </div>
      <div className="flex items-center gap-3">
        <button className="flex items-center gap-1.5 px-2 py-1 rounded text-[11px] text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors">
          Prod
        </button>
        <button className="relative text-zinc-600 hover:text-zinc-300 transition-colors">
          <Bell size={16} />
          {alertCount > 0 && (
            <span className="absolute -top-1 -right-1 min-w-[14px] h-[14px] bg-red-500 rounded-full text-[9px] font-semibold text-white flex items-center justify-center px-0.5">
              {alertCount > 9 ? '9+' : alertCount}
            </span>
          )}
        </button>
        <div className="w-7 h-7 rounded-full bg-zinc-800 flex items-center justify-center text-zinc-400 text-[11px] font-medium hover:bg-zinc-700 transition-colors cursor-pointer">
          A
        </div>
      </div>
    </header>
  );
}

export default function Layout({ onLogout }: LayoutProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const location = useLocation();

  const sidebarContent = (
    <>
      <div className="px-4 py-4 flex items-center gap-2.5">
        <div className="w-6 h-6 rounded-md bg-white flex items-center justify-center">
          <ShieldCheck size={14} className="text-zinc-900" />
        </div>
        <span className="text-[13px] font-semibold text-zinc-200 tracking-tight">Cert Control</span>
      </div>

      <nav className="flex-1 px-2.5 pt-2 space-y-0.5">
        {navItems.map(({ to, icon: Icon, label }) => {
          const isActive = location.pathname === to || (to !== '/dashboard' && location.pathname.startsWith(to));
          return (
            <NavLink
              key={to}
              to={to}
              end={to === '/dashboard'}
              className={() =>
                `flex items-center gap-2.5 px-2.5 py-[7px] rounded-md text-[13px] transition-all duration-150 ${
                  isActive
                    ? 'bg-zinc-800 text-white font-medium'
                    : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50'
                }`
              }
            >
              <Icon size={16} strokeWidth={isActive ? 2 : 1.5} />
              {label}
            </NavLink>
          );
        })}
      </nav>

      <div className="px-2.5 pb-3">
        <div className="flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] text-zinc-600 mb-1">
          <span className="relative flex h-[5px] w-[5px]">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-[5px] w-[5px] bg-emerald-500" />
          </span>
          系统正常
        </div>
        <button
          onClick={onLogout}
          className="w-full text-[11px] text-zinc-600 hover:text-zinc-300 transition-colors duration-150 text-left px-2.5 py-1 rounded-md hover:bg-zinc-800/50"
        >
          退出登录
        </button>
      </div>
    </>
  );

  return (
    <div className="flex h-screen bg-[var(--bg-primary)]">
      {/* Desktop sidebar */}
      <aside className="w-[200px] bg-[var(--bg-primary)] border-r border-zinc-800/70 flex flex-col shrink-0 hidden lg:flex">
        {sidebarContent}
      </aside>

      {/* Mobile overlay */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" onClick={() => setMobileMenuOpen(false)}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <aside className="relative w-[200px] h-full bg-[var(--bg-primary)] border-r border-zinc-800" onClick={e => e.stopPropagation()}>
            {sidebarContent}
          </aside>
        </div>
      )}

      {/* Main area */}
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar alertCount={0} />
        <main className="flex-1 overflow-auto p-5 lg:p-6">
          <Outlet />
        </main>
      </div>

      {/* Mobile menu button */}
      <button
        className="fixed bottom-4 right-4 lg:hidden bg-white text-zinc-900 p-2.5 rounded-xl shadow-lg z-40 hover:bg-zinc-200 transition-colors"
        onClick={() => setMobileMenuOpen(true)}
      >
        <Menu size={18} />
      </button>
    </div>
  );
}