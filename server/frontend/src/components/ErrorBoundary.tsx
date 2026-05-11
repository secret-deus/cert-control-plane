import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo });
    console.error('[ErrorBoundary] Caught error:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      const isDev = import.meta.env.DEV;

      return (
        <div className="flex min-h-screen items-center justify-center bg-[#0a0e14] p-6">
          <div className="w-full max-w-lg rounded-[24px] border border-[rgba(242,73,92,0.18)] bg-[rgba(242,73,92,0.04)] p-8 shadow-[0_24px_48px_rgba(0,0,0,0.4)] backdrop-blur-xl">
            <div className="flex items-center gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-[16px] border border-[rgba(242,73,92,0.24)] bg-[rgba(242,73,92,0.10)]">
                <AlertTriangle size={22} className="text-[#f2495c]" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-white">应用发生错误</h2>
                <p className="mt-1 text-sm text-white/50">页面渲染时出现了未预期的异常</p>
              </div>
            </div>

            <div className="mt-6 rounded-[16px] border border-white/8 bg-white/[0.02] px-4 py-3">
              <p className="text-sm font-medium text-[#ff8d9a]">
                {this.state.error?.message || '未知错误'}
              </p>
            </div>

            {isDev && this.state.errorInfo && (
              <details className="mt-4">
                <summary className="cursor-pointer text-xs text-white/40 hover:text-white/60 transition">
                  查看错误堆栈（开发模式）
                </summary>
                <pre className="mt-2 max-h-[200px] overflow-auto rounded-[12px] border border-white/6 bg-black/40 p-3 text-[11px] leading-relaxed text-white/50">
                  {this.state.error?.stack}
                  {'\n\nComponent Stack:'}
                  {this.state.errorInfo.componentStack}
                </pre>
              </details>
            )}

            <div className="mt-6 flex gap-3">
              <button
                onClick={this.handleReset}
                className="flex items-center gap-2 rounded-[14px] border border-white/10 bg-white/[0.05] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-white/[0.08]"
              >
                <RefreshCw size={14} />
                重试
              </button>
              <button
                onClick={() => window.location.reload()}
                className="rounded-[14px] border border-white/6 bg-white/[0.02] px-4 py-2.5 text-sm text-white/60 transition hover:bg-white/[0.05] hover:text-white/80"
              >
                刷新页面
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
