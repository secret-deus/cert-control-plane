import { Settings } from 'lucide-react';

export default function SettingsPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh]">
      <Settings size={48} className="text-zinc-700 mb-4" />
      <h2 className="text-xl font-semibold text-zinc-300 mb-2">系统设置</h2>
      <p className="text-sm text-zinc-500">即将推出</p>
    </div>
  );
}