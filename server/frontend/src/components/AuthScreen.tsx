import { useState } from 'react';
import { ShieldCheck, KeyRound, Loader2 } from 'lucide-react';

interface AuthScreenProps {
  onLogin: (apiKey: string) => void;
}

export default function AuthScreen({ onLogin }: AuthScreenProps) {
  const [key, setKey] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!key.trim()) return;

    setIsVerifying(true);
    setError(null);

    try {
      // Verify key by making a lightweight API call
      const res = await fetch('/api/control/dashboard/summary', {
        headers: {
          'X-Admin-API-Key': key,
        },
      });

      if (res.ok) {
        onLogin(key);
      } else if (res.status === 401 || res.status === 403) {
        setError('API Key 无效');
      } else {
        setError(`服务器错误: ${res.status}`);
      }
    } catch {
      setError('连接失败，请确认服务器正在运行');
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[70vh]">
      <div className="glass-panel p-8 w-full max-w-md animate-in fade-in zoom-in duration-300">
        <div className="flex flex-col items-center mb-8">
          <div className="bg-[var(--color-background-base)] p-4 rounded-full border border-[var(--color-border-subtle)] mb-4">
            <ShieldCheck size={40} className="text-[var(--color-accent-blue)]" />
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">访问控制台</h2>
          <p className="text-[var(--color-text-secondary)] text-center text-sm">
            输入您的 Admin API Key 以管理证书和监控 Agent 状态。
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <KeyRound className="h-5 w-5 text-gray-500" />
              </div>
              <input
                type="password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                className="block w-full pl-10 pr-3 py-3 border border-[var(--color-border-subtle)] rounded-md leading-5 bg-[#0d1117] text-[var(--color-text-primary)] placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-[var(--color-accent-blue)] focus:border-[var(--color-accent-blue)] sm:text-sm transition-all shadow-inner"
                placeholder="X-Admin-API-Key"
                required
              />
            </div>
            {error && (
              <p className="mt-2 text-sm text-[var(--color-status-red)] flex items-center gap-1">
                <span>•</span> {error}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={isVerifying || !key.trim()}
            className="w-full flex justify-center items-center py-3 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-[var(--color-accent-blue)] hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[var(--color-accent-blue)] focus:ring-offset-[#0f1115] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isVerifying ? (
              <>
                <Loader2 className="animate-spin -ml-1 mr-2 h-4 w-4" />
                验证中...
              </>
            ) : (
              '连接'
            )}
          </button>
        </form>
      </div>

      <div className="mt-8 text-xs text-[var(--color-text-secondary)] flex gap-4 opacity-50">
        <span>443 端口 API</span>
        <span>•</span>
        <span>8443 端口 Agent API</span>
      </div>
    </div>
  );
}
