import { useState, useEffect } from 'react';
import { ShieldCheck } from 'lucide-react';
import Dashboard from './components/Dashboard';
import AuthScreen from './components/AuthScreen';

function App() {
  const [apiKey, setApiKey] = useState<string | null>(null);

  useEffect(() => {
    const storedKey = sessionStorage.getItem('admin_api_key');
    if (storedKey) {
      setApiKey(storedKey);
    }
  }, []);

  const handleLogin = (key: string) => {
    sessionStorage.setItem('admin_api_key', key);
    setApiKey(key);
  };

  const handleLogout = () => {
    sessionStorage.removeItem('admin_api_key');
    setApiKey(null);
  };

  // Main UI Wrapper Layout
  return (
    <div className="min-h-screen bg-[var(--color-background-base)] text-[var(--color-text-primary)]">
      {/* Top Navigation Bar */}
      <nav className="glass-panel rounded-none border-x-0 border-t-0 p-4 sticky top-0 z-50 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ShieldCheck className="text-[var(--color-accent-blue)]" size={28} />
          <h1 className="text-xl font-semibold tracking-tight">Cert Control Plane <span className="text-[var(--color-text-secondary)] font-normal text-sm ml-2">v0.1.0</span></h1>
        </div>
        
        {apiKey && (
          <div className="flex items-center gap-6">
             <div className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
                <span className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--color-status-green)] opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-[var(--color-status-green)]"></span>
                </span>
                System Online
             </div>
             <button 
                onClick={handleLogout}
                className="text-sm text-[var(--color-text-secondary)] hover:text-white transition-colors"
             >
                Sign Out
             </button>
          </div>
        )}
      </nav>

      <main className="container mx-auto p-4 md:p-8 max-w-7xl">
        {!apiKey ? (
          <AuthScreen onLogin={handleLogin} />
        ) : (
          <Dashboard apiKey={apiKey} onAuthError={handleLogout} />
        )}
      </main>
    </div>
  );
}

export default App;
