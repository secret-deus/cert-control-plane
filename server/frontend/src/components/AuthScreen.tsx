import { useState } from 'react';
import { Eye, EyeOff, KeyRound, Loader2, LockKeyhole, ShieldCheck } from 'lucide-react';

interface AuthScreenProps {
  onLogin: (apiKey: string) => void;
}

const moduleRows = [
  { name: '监控聚合', note: '查看风险告警、批次状态和 Agent 健康。' },
  { name: '证书资产', note: '管理证书生命周期、分发节点和安全信息。' },
  { name: 'Agent 舰队', note: '统一处理节点接入审批、心跳和覆盖情况。' },
];

export default function AuthScreen({ onLogin }: AuthScreenProps) {
  const [key, setKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!key.trim()) {
      return;
    }

    setIsVerifying(true);
    setError(null);

    try {
      const response = await fetch('/api/control/dashboard/summary', {
        headers: { 'X-Admin-API-Key': key },
      });

      if (response.ok) {
        onLogin(key);
      } else if (response.status === 401 || response.status === 403) {
        setError('API Key 无效');
      } else {
        setError(`服务器错误: ${response.status}`);
      }
    } catch {
      setError('连接失败，请确认服务器正在运行');
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#101010] px-4 py-6 lg:px-8 lg:py-8">
      <div className="mx-auto grid min-h-[calc(100vh-3rem)] max-w-[1320px] gap-6 lg:grid-cols-[minmax(0,1.2fr)_420px]">
        <section className="glass-panel rounded-[24px] p-6 lg:p-7">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-[18px] border border-white/8 bg-white/[0.03] text-white">
              <ShieldCheck size={18} />
            </div>
            <div>
              <div className="text-lg font-semibold tracking-tight text-white">Cert Control Plane</div>
              <div className="mt-1 text-sm text-white/50">控制平面访问入口</div>
            </div>
          </div>

          <div className="mt-6 rounded-[20px] border border-white/8 bg-white/[0.02] px-4 py-3 text-sm text-white/70">
            使用 Admin API Key 登录后进入控制台。该入口只用于控制平面，Agent API 使用独立鉴权通道。
          </div>

          <div className="mt-6 overflow-hidden rounded-[20px] border border-white/8 bg-white/[0.02]">
            <div className="border-b border-white/8 px-4 py-3 text-xs font-medium uppercase tracking-[0.18em] text-white/50">
              可用模块
            </div>
            <div>
              {moduleRows.map((module, index) => (
                <div key={module.name} className={`px-4 py-4 ${index !== moduleRows.length - 1 ? 'border-b border-white/8' : ''}`}>
                  <div className="text-sm font-medium text-white">{module.name}</div>
                  <div className="mt-1 text-sm text-white/50">{module.note}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <div className="rounded-[20px] border border-white/8 bg-white/[0.02] p-4">
              <div className="text-xs font-medium uppercase tracking-[0.18em] text-white/50">访问通道</div>
              <div className="mt-4 space-y-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-white/50">Control API</span>
                  <span className="text-white">8080</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-white/50">Agent API</span>
                  <span className="text-white">8081</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-white/50">认证方式</span>
                  <span className="text-white">API Key</span>
                </div>
              </div>
            </div>

            <div className="rounded-[20px] border border-white/8 bg-white/[0.02] p-4">
              <div className="text-xs font-medium uppercase tracking-[0.18em] text-white/50">前置条件</div>
              <div className="mt-4 space-y-3 text-sm">
                <div className="text-white/70">1. 后端服务已启动</div>
                <div className="text-white/70">2. Admin API Key 已配置</div>
                <div className="text-white/70">3. 浏览器可访问当前容器端口</div>
              </div>
            </div>
          </div>
        </section>

        <section className="glass-panel rounded-[24px] flex flex-col justify-between p-6 lg:p-7">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium text-white">
              <LockKeyhole size={16} className="text-[#ffbf8f]" />
              登录控制台
            </div>
            <p className="mt-2 text-sm leading-6 text-white/50">输入 Admin API Key 验证当前会话。</p>

            <form onSubmit={handleSubmit} className="mt-6 space-y-4">
              <div>
                <label className="mb-2 block text-xs font-medium uppercase tracking-[0.18em] text-white/50">Admin API Key</label>
                <div className="relative">
                  <KeyRound className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/50" />
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={key}
                    onChange={(event) => setKey(event.target.value)}
                    className="input-field py-3 pr-11 pl-9"
                    placeholder="X-Admin-API-Key"
                    autoFocus
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey((current) => !current)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-white/50 transition-colors hover:text-white"
                  >
                    {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              {error && (
                <div className="rounded-[18px] border border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] px-3 py-2 text-sm text-[#ffbf8f]">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={isVerifying || !key.trim()}
                className="btn-primary w-full py-3"
              >
                {isVerifying ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> 验证中...
                  </>
                ) : (
                  '进入'
                )}
              </button>
            </form>
          </div>

          <div className="mt-8 rounded-[20px] border border-white/8 bg-white/[0.02] px-4 py-3 text-sm text-white/50">
            当前界面优先展示真实运行信息，避免额外装饰。若要进一步做开发态预览，可直接在容器挂载的 `dist` 基础上继续迭代。
          </div>
        </section>
      </div>
    </div>
  );
}
