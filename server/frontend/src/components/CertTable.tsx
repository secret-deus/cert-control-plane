import { FileKey2, Trash2 } from 'lucide-react';
import { format } from 'date-fns';

interface ExternalCert {
  id: string;
  name: string;
  description: string | null;
  subject_cn: string;
  serial_hex: string;
  not_before: string;
  not_after: string;
  provider: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

const providerLabels: Record<string, string> = {
  manual: '手动上传',
  aliyun: '阿里云',
  letsencrypt: "Let's Encrypt",
  digicert: 'DigiCert',
};

function getDaysRemaining(notAfter: string) {
  return Math.ceil((new Date(notAfter).getTime() - Date.now()) / 86400000);
}

function getCertHealth(daysRemaining: number, isActive: boolean) {
  if (!isActive) {
    return { label: '未启用', tone: 'border-white/10 bg-white/5 text-slate-300' };
  }
  if (daysRemaining < 0) {
    return { label: '已过期', tone: 'border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] text-[#ffbf8f]' };
  }
  if (daysRemaining <= 7) {
    return { label: '7 天内到期', tone: 'border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] text-[#ffbf8f]' };
  }
  if (daysRemaining <= 30) {
    return { label: '30 天内关注', tone: 'border-white/8 bg-white/[0.03] text-neutral-300' };
  }
  return { label: '健康', tone: 'border-white/8 bg-white/[0.03] text-neutral-300' };
}

interface CertTableProps {
  certs: ExternalCert[];
  isLoading: boolean;
  selectedCertId: string | null;
  onSelectCert: (id: string) => void;
  bindingCounts: Record<string, number>;
  onDeleteCert: (id: string) => void;
}

export default function CertTable({
  certs,
  isLoading,
  selectedCertId,
  onSelectCert,
  bindingCounts,
  onDeleteCert,
}: CertTableProps) {
  return (
    <div className="glass-panel overflow-hidden">
      <div className="border-b border-white/6 px-5 py-4">
        <div className="section-kicker">Inventory Table</div>
        <h3 className="mt-2 text-lg font-semibold text-white">证书资产列表</h3>
        <p className="mt-1 text-sm text-white/70">列表保留高频字段，详情放到右侧抽屉，不再把所有信息挤在一行里。</p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/6 text-xs text-white/50">
              <th className="px-5 py-3 text-left font-medium">证书主体</th>
              <th className="px-4 py-3 text-left font-medium">来源</th>
              <th className="px-4 py-3 text-left font-medium">到期时间</th>
              <th className="px-4 py-3 text-left font-medium">风险</th>
              <th className="px-4 py-3 text-left font-medium">分发节点</th>
              <th className="px-4 py-3 text-left font-medium">状态</th>
              <th className="px-5 py-3 text-left font-medium">动作</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 4 }).map((_, index) => (
                <tr key={index} className="table-row">
                  {Array.from({ length: 7 }).map((__, cellIndex) => (
                    <td key={cellIndex} className="px-4 py-4">
                      <div className="skeleton h-4 rounded" />
                    </td>
                  ))}
                </tr>
              ))
            ) : certs.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-5 py-14 text-center text-sm text-white/50">没有匹配的证书。</td>
              </tr>
            ) : (
              certs.map((cert) => {
                const daysRemaining = getDaysRemaining(cert.not_after);
                const health = getCertHealth(daysRemaining, cert.is_active);
                const isSelected = selectedCertId === cert.id;
                const bindingCount = bindingCounts[cert.id];

                return (
                  <tr
                    key={cert.id}
                    className={`table-row cursor-pointer ${isSelected ? 'bg-white/[0.05]' : ''}`}
                    onClick={() => onSelectCert(cert.id)}
                  >
                    <td className="px-5 py-4">
                      <div className="flex items-start gap-3">
                        <div className="rounded-[14px] border border-white/8 bg-white/[0.03] p-2 text-white">
                          <FileKey2 size={16} />
                        </div>
                        <div>
                          <div className="font-medium text-white">{cert.subject_cn}</div>
                          <div className="mt-1 text-xs text-white/50">{cert.name}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-4 text-white/70">{providerLabels[cert.provider || 'manual'] || cert.provider || '手动上传'}</td>
                    <td className="px-4 py-4 text-white/80">{format(new Date(cert.not_after), 'yyyy-MM-dd')}</td>
                    <td className="px-4 py-4">
                      <span className={`rounded-full border px-2 py-0.5 text-xs ${health.tone}`}>{health.label}</span>
                      <div className="mt-1 text-xs text-white/50">
                        {daysRemaining < 0 ? `已过期 ${Math.abs(daysRemaining)} 天` : `${daysRemaining} 天`}
                      </div>
                    </td>
                    <td className="px-4 py-4 text-white/70">{typeof bindingCount === 'number' ? `${bindingCount} 台` : '点选后计算'}</td>
                    <td className="px-4 py-4">
                      <span className={`rounded-full border px-2 py-0.5 text-xs ${cert.is_active ? 'border-[rgba(115,191,105,0.18)] bg-[rgba(115,191,105,0.10)] text-[#9adf90]' : 'border-white/8 bg-white/[0.03] text-neutral-300'}`}>
                        {cert.is_active ? '活跃' : '未启用'}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            onSelectCert(cert.id);
                          }}
                          className="text-xs font-medium text-[#ffbf8f] hover:text-[#ffd0ad]"
                        >
                          查看抽屉
                        </button>
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            onDeleteCert(cert.id);
                          }}
                          className="text-xs font-medium text-[#ffbf8f] hover:text-[#ffd0ad]"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}