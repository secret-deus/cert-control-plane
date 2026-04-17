import { ShieldCheck, Calendar, Hash, Globe, CheckCircle2 } from 'lucide-react';
import { format } from 'date-fns';

interface ArchivePreviewData {
  id: string;
  name: string;
  subject_cn: string;
  serial_hex: string;
  not_after: string;
  files_detected: {
    cert: string;
    key: string;
    chain: string | null;
  };
  san_domains: string[];
  message: string;
}

interface ArchivePreviewProps {
  data: ArchivePreviewData;
}

export default function ArchivePreview({ data }: ArchivePreviewProps) {
  const daysRemaining = Math.ceil(
    (new Date(data.not_after).getTime() - Date.now()) / 86400000
  );

  const getStatusLabel = () => {
    if (daysRemaining < 0) return { label: '已过期', tone: 'border-rose-300/15 bg-rose-500/10 text-rose-200' };
    if (daysRemaining <= 7) return { label: '7天内到期', tone: 'border-rose-300/15 bg-rose-500/10 text-rose-200' };
    if (daysRemaining <= 30) return { label: '30天内关注', tone: 'border-amber-300/15 bg-amber-500/10 text-amber-200' };
    return { label: '健康', tone: 'border-emerald-300/15 bg-emerald-500/10 text-emerald-200' };
  };

  const status = getStatusLabel();

  return (
    <div className="rounded-lg border border-teal-300/12 bg-teal-500/[0.03] p-4 space-y-4">
      <div className="flex items-start gap-3">
        <div className="rounded-full border border-emerald-300/15 bg-emerald-500/10 p-2 text-emerald-200">
          <CheckCircle2 size={16} />
        </div>
        <div>
          <div className="text-sm font-medium text-white">解析成功</div>
          <div className="mt-1 text-xs text-slate-400">{data.message}</div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
          <div className="text-xs text-slate-500 flex items-center gap-1.5">
            <ShieldCheck size={12} />
            证书主体
          </div>
          <div className="mt-2 text-sm font-medium text-white">{data.subject_cn}</div>
        </div>

        <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
          <div className="text-xs text-slate-500 flex items-center gap-1.5">
            <Calendar size={12} />
            到期时间
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span className="text-sm text-white">{format(new Date(data.not_after), 'yyyy-MM-dd')}</span>
            <span className={`rounded-full border px-2 py-0.5 text-xs ${status.tone}`}>{status.label}</span>
          </div>
        </div>

        <div className="sm:col-span-2 rounded-lg border border-white/8 bg-white/[0.03] p-3">
          <div className="text-xs text-slate-500 flex items-center gap-1.5">
            <Hash size={12} />
            序列号
          </div>
          <div className="mt-2 break-all font-mono text-xs text-slate-200">{data.serial_hex}</div>
        </div>
      </div>

      {data.san_domains.length > 0 && (
        <div>
          <div className="text-xs text-slate-500 flex items-center gap-1.5 mb-2">
            <Globe size={12} />
            SAN 域名
          </div>
          <div className="flex flex-wrap gap-1.5">
            {data.san_domains.map((domain) => (
              <span
                key={domain}
                className="rounded border border-white/8 bg-white/[0.03] px-2 py-1 text-xs text-slate-300"
              >
                {domain}
              </span>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="text-xs text-slate-500 mb-2">识别文件</div>
        <div className="grid gap-2 sm:grid-cols-3">
          <div className="rounded border border-white/8 bg-white/[0.03] px-3 py-2 text-xs">
            <span className="text-slate-400">证书：</span>
            <span className="text-slate-200">{data.files_detected.cert}</span>
          </div>
          <div className="rounded border border-white/8 bg-white/[0.03] px-3 py-2 text-xs">
            <span className="text-slate-400">私钥：</span>
            <span className="text-slate-200">{data.files_detected.key}</span>
          </div>
          {data.files_detected.chain && (
            <div className="rounded border border-white/8 bg-white/[0.03] px-3 py-2 text-xs">
              <span className="text-slate-400">证书链：</span>
              <span className="text-slate-200">{data.files_detected.chain}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}