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
      const res = await fetch('/api/control/dashboard/summary', {
        headers: { 'X-Admin-API-Key': key },
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
    <div className="flex items-center justify-center min-h-screen bg-[var(--bg-primary)]">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-8">
          <div className="w-10 h-10 rounded-xl bg-white flex items-center justify-center mb-4">
            <ShieldCheck size={20} className="text-zinc-900" />
          </div>
          <h1 className="text-xl font-semibold text-white tracking-tight">Cert Control Plane</h1>
          <p className="text-[13px] text-zinc-500 mt-1.5">输入 Admin API Key 以继续</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="relative">
            <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-600" />
            <input
              type="password"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              className="input-field pl-9 py-2.5"
              placeholder="X-Admin-API-Key"
              autoFocus
              required
            />
          </div>
          {error && (
            <p className="text-[12px] text-red-400">{error}</p>
          )}
          <button
            type="submit"
            disabled={isVerifying || !key.trim()}
            className="btn-primary w-full py-2.5"
          >
            {isVerifying ? (
              <><Loader2 className="animate-spin h-4 w-4" /> 验证中...</>
            ) : (
              '连接'
            )}
          </button>
        </form>

        <div className="mt-8 text-[11px] text-zinc-600 flex justify-center gap-3">
          <span>443 Control API</span>
          <span>·</span>
          <span>8443 Agent API</span>
        </div>
      </div>
    </div>
  );
}