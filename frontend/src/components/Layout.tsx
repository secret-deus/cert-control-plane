import { NavLink, Outlet } from 'react-router-dom';
import {
  ShieldCheck, LayoutDashboard, Server, FileKey2,
  RefreshCw, ScrollText
} from 'lucide-react';

interface LayoutProps {
  onLogout: () => void;
}

const navItems = [
  { to: '/',            icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/agents',      icon: Server,          label: 'Agents' },
  { to: '/certificates',icon: FileKey2,        label: 'Certificates' },
  { to: '/rollouts',    icon: RefreshCw,       label: 'Rollouts' },
  { to: '/audit',       icon: ScrollText,      label: 'Audit Logs' },
];

export default function Layout({ onLogout }: LayoutProps) {
  return (
    <div className="min-h-screen bg-[var(--color-background-base)] text-[var(--color-text-primary)] flex">
      {/* Sidebar */}
      <aside className="w-56 glass-panel rounded-none border-t-0 border-l-0 border-b-0 flex flex-col sticky top-0 h-screen">
        {/* Logo */}
        <div className="p-5 flex items-center gap-3 border-b border-[var(--color-border-subtle)]">
          <ShieldCheck className="text-[var(--color-accent-blue)]" size={24} />
          <span className="font-semibold text-sm tracking-tight">Cert Control Plane</span>
        </div>

        {/* Nav links */}
        <nav className="flex-1 py-4 px-3 space-y-1">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-[var(--color-accent-blue)]/15 text-[var(--color-accent-blue)] font-medium'
                    : 'text-[var(--color-text-secondary)] hover:text-white hover:bg-[rgba(255,255,255,0.04)]'
                }`
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Bottom status */}
        <div className="p-4 border-t border-[var(--color-border-subtle)]">
          <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)] mb-3">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--color-status-green)] opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--color-status-green)]"></span>
            </span>
            System Online
          </div>
          <button
            onClick={onLogout}
            className="w-full text-xs text-[var(--color-text-secondary)] hover:text-white transition-colors text-left"
          >
            Sign Out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 p-6 lg:p-8 max-w-7xl overflow-x-hidden">
        <Outlet />
      </main>
    </div>
  );
}
