import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import AuthScreen from './components/AuthScreen';
import Layout from './components/Layout';
import Dashboard from './components/Dashboard';
import AgentsPage from './components/AgentsPage';
import CertificatesPage from './components/CertificatesPage';
import RolloutsPage from './components/RolloutsPage';
import AuditLogsPage from './components/AuditLogsPage';

function App() {
  const [apiKey, setApiKey] = useState<string | null>(null);

  useEffect(() => {
    const storedKey = sessionStorage.getItem('admin_api_key');
    if (storedKey) setApiKey(storedKey);
  }, []);

  const handleLogin = (key: string) => {
    sessionStorage.setItem('admin_api_key', key);
    setApiKey(key);
  };

  const handleLogout = () => {
    sessionStorage.removeItem('admin_api_key');
    setApiKey(null);
  };

  if (!apiKey) {
    return (
      <div className="min-h-screen bg-[var(--color-background-base)] text-[var(--color-text-primary)] flex items-center justify-center">
        <AuthScreen onLogin={handleLogin} />
      </div>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout onLogout={handleLogout} />}>
          <Route index element={<Dashboard apiKey={apiKey} onAuthError={handleLogout} />} />
          <Route path="agents" element={<AgentsPage />} />
          <Route path="certificates" element={<CertificatesPage />} />
          <Route path="rollouts" element={<RolloutsPage />} />
          <Route path="audit" element={<AuditLogsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
