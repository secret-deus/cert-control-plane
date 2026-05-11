import { useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import AuthScreen from './components/AuthScreen';
import Layout from './components/Layout';
import Dashboard from './components/Dashboard';
import CertManagementPage from './components/CertManagementPage';
import AgentsPage from './components/AgentsPage';
import SettingsPage from './components/SettingsPage';
import KubernetesPage from './components/KubernetesPage';

const ADMIN_API_KEY_STORAGE_KEY = 'admin_api_key';
const ADMIN_API_KEY_LAST_ACTIVE_KEY = 'admin_api_key_last_active';
const SESSION_IDLE_TIMEOUT_MS = 30 * 60 * 1000;

function clearStoredSession() {
  sessionStorage.removeItem(ADMIN_API_KEY_STORAGE_KEY);
  sessionStorage.removeItem(ADMIN_API_KEY_LAST_ACTIVE_KEY);
}

function touchSession() {
  sessionStorage.setItem(ADMIN_API_KEY_LAST_ACTIVE_KEY, String(Date.now()));
}

function readStoredApiKey(refreshActivity = true) {
  const storedKey = sessionStorage.getItem(ADMIN_API_KEY_STORAGE_KEY);
  if (!storedKey) {
    return null;
  }

  const lastActive = Number(sessionStorage.getItem(ADMIN_API_KEY_LAST_ACTIVE_KEY) || '0');
  if (!lastActive || Date.now() - lastActive > SESSION_IDLE_TIMEOUT_MS) {
    clearStoredSession();
    return null;
  }

  if (refreshActivity) {
    touchSession();
  }
  return storedKey;
}

function App() {
  const [apiKey, setApiKey] = useState<string | null>(() => readStoredApiKey());

  useEffect(() => {
    if (!apiKey) {
      return;
    }

    const handleActivity = () => touchSession();
    const checkExpiry = () => {
      if (!readStoredApiKey(false)) {
        setApiKey(null);
      }
    };
    const events = ['click', 'keydown', 'mousemove', 'scroll', 'touchstart'];
    events.forEach((event) => window.addEventListener(event, handleActivity, { passive: true }));
    const interval = window.setInterval(checkExpiry, 60 * 1000);

    return () => {
      events.forEach((event) => window.removeEventListener(event, handleActivity));
      window.clearInterval(interval);
    };
  }, [apiKey]);

  if (!apiKey) {
    return <AuthScreen onLogin={(key) => {
      sessionStorage.setItem(ADMIN_API_KEY_STORAGE_KEY, key);
      touchSession();
      setApiKey(key);
    }} />;
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout onLogout={() => {
          clearStoredSession();
          setApiKey(null);
        }} />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/certificates" element={<CertManagementPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/agents/:id" element={<AgentsPage />} />
          <Route path="/kubernetes" element={<KubernetesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
