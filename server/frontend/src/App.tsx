import { useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import AuthScreen from './components/AuthScreen';
import Layout from './components/Layout';
import Dashboard from './components/Dashboard';
import CertManagementPage from './components/CertManagementPage';
import AgentsPage from './components/AgentsPage';
import SettingsPage from './components/SettingsPage';
import KubernetesPage from './components/KubernetesPage';

function App() {
  const [apiKey, setApiKey] = useState<string | null>(() =>
    sessionStorage.getItem('admin_api_key')
  );

  if (!apiKey) {
    return <AuthScreen onLogin={(key) => {
      sessionStorage.setItem('admin_api_key', key);
      setApiKey(key);
    }} />;
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout onLogout={() => {
          sessionStorage.removeItem('admin_api_key');
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
