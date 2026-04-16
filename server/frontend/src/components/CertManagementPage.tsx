import { useState, useEffect, useCallback } from 'react';
import { Search, UploadCloud, RefreshCw, ChevronDown, ChevronUp, X, ShieldCheck } from 'lucide-react';
import { apiFetch, apiPost } from '../lib/api';
import { format } from 'date-fns';

interface ExternalCert {
  id: string;
  name: string;
  subject_cn: string;
  serial_hex: string;
  not_before: string;
  not_after: string;
  provider: string | null;
  is_active: boolean;
  auto_renew: boolean;
  created_at: string;
}

interface CertAssignment {
  id: string;
  agent_id: string;
  agent_name: string;
  local_path: string;
  external_cert_id: string;
  created_at: string;
}

type FilterStatus = 'all' | 'active' | 'expiring' | 'expired' | 'inactive';

const urgencyLabel = (days: number): { text: string; cls: string } => {
  if (days < 0) return { text: '已过期', cls: 'text-red-400 bg-red-500/10' };
  if (days <= 7) return { text: '7天内', cls: 'text-red-400 bg-red-500/10' };
  if (days <= 30) return { text: '30天内', cls: 'text-yellow-400 bg-yellow-500/10' };
  return { text: '正常', cls: 'text-green-400 bg-green-500/10' };
};

export default function CertManagementPage() {
  const [certs, setCerts] = useState<ExternalCert[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<FilterStatus>('all');
  const [search, setSearch] = useState('');
  const [expandedCert, setExpandedCert] = useState<string | null>(null);
  const [assignments, setAssignments] = useState<CertAssignment[]>([]);
  const [showUpload, setShowUpload] = useState(false);

  // Upload form
  const [uploadForm, setUploadForm] = useState({ name: '', provider: 'manual', cert_pem: '', key_pem: '', chain_pem: '' });
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState(false);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [certsData] = await Promise.all([
        apiFetch<{ items: ExternalCert[]; total: number }>('/external-certs?limit=1000'),
      ]);
      setCerts(certsData.items || []);
    } catch (err) {
      console.error('Failed to fetch certificates:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const fetchAssignments = async (certId: string) => {
    try {
      const data = await apiFetch<{ items: CertAssignment[] }>(`/external-certs/${certId}/assignments`);
      setAssignments(data.items || []);
    } catch {
      setAssignments([]);
    }
  };

  const handleExpand = (certId: string) => {
    if (expandedCert === certId) {
      setExpandedCert(null);
    } else {
      setExpandedCert(certId);
      fetchAssignments(certId);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    setUploading(true);
    setUploadError(null);
    setUploadSuccess(false);
    try {
      await apiPost('/external-certs', uploadForm);
      setUploadSuccess(true);
      setUploadForm({ name: '', provider: 'manual', cert_pem: '', key_pem: '', chain_pem: '' });
      setTimeout(() => { setShowUpload(false); setUploadSuccess(false); }, 1500);
      fetchData();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : '上传失败');
    } finally {
      setUploading(false);
    }
  };

  const now = new Date();
  const filteredCerts = certs.filter(c => {
    const days = Math.ceil((new Date(c.not_after).getTime() - now.getTime()) / (86400000));
    if (statusFilter === 'active') return c.is_active && days > 30;
    if (statusFilter === 'expiring') return c.is_active && days > 0 && days <= 30;
    if (statusFilter === 'expired') return days <= 0;
    if (statusFilter === 'inactive') return !c.is_active;
    return true;
  }).filter(c => !search || c.subject_cn.toLowerCase().includes(search.toLowerCase()) || c.name.toLowerCase().includes(search.toLowerCase()));

  const filterCounts = {
    all: certs.length,
    active: certs.filter(c => { const d = Math.ceil((new Date(c.not_after).getTime() - now.getTime()) / 86400000); return c.is_active && d > 30; }).length,
    expiring: certs.filter(c => { const d = Math.ceil((new Date(c.not_after).getTime() - now.getTime()) / 86400000); return c.is_active && d > 0 && d <= 30; }).length,
    expired: certs.filter(c => { const d = Math.ceil((new Date(c.not_after).getTime() - now.getTime()) / 86400000); return d <= 0; }).length,
    inactive: certs.filter(c => !c.is_active).length,
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">证书管理</h1>
          <p className="text-sm text-zinc-400 mt-1">管理外部证书与分发状态</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={fetchData} className="btn-secondary flex items-center gap-1.5" disabled={isLoading}>
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} /> 刷新
          </button>
          <button onClick={() => setShowUpload(!showUpload)} className="btn-primary flex items-center gap-1.5">
            <UploadCloud size={14} /> 上传证书
          </button>
        </div>
      </div>

      {/* Upload form */}
      {showUpload && (
        <div className="glass-panel p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-white">上传新证书</h3>
            <button onClick={() => setShowUpload(false)} className="text-zinc-400 hover:text-white"><X size={18} /></button>
          </div>
          {uploadError && <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-red-400 text-sm mb-4">{uploadError}</div>}
          {uploadSuccess && <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-3 text-green-400 text-sm mb-4">证书上传成功！</div>}
          <form onSubmit={handleUpload} className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-zinc-400 mb-1">名称</label>
              <input className="input-field" value={uploadForm.name} onChange={e => setUploadForm(f => ({ ...f, name: e.target.value }))} required placeholder="api.example.com" />
            </div>
            <div>
              <label className="block text-xs text-zinc-400 mb-1">来源</label>
              <select className="input-field" value={uploadForm.provider} onChange={e => setUploadForm(f => ({ ...f, provider: e.target.value }))}>
                <option value="manual">手动上传</option>
                <option value="aliyun">阿里云</option>
                <option value="letsencrypt">Let's Encrypt</option>
                <option value="digicert">DigiCert</option>
              </select>
            </div>
            <div className="col-span-2">
              <label className="block text-xs text-zinc-400 mb-1">证书 PEM</label>
              <textarea className="input-field h-24 font-mono text-xs" value={uploadForm.cert_pem} onChange={e => setUploadForm(f => ({ ...f, cert_pem: e.target.value }))} required placeholder="-----BEGIN CERTIFICATE-----..." />
            </div>
            <div className="col-span-2">
              <label className="block text-xs text-zinc-400 mb-1">私钥 PEM</label>
              <textarea className="input-field h-24 font-mono text-xs" value={uploadForm.key_pem} onChange={e => setUploadForm(f => ({ ...f, key_pem: e.target.value }))} required placeholder="-----BEGIN PRIVATE KEY-----..." />
            </div>
            <div className="col-span-2">
              <label className="block text-xs text-zinc-400 mb-1">证书链 PEM（可选）</label>
              <textarea className="input-field h-24 font-mono text-xs" value={uploadForm.chain_pem} onChange={e => setUploadForm(f => ({ ...f, chain_pem: e.target.value }))} placeholder="-----BEGIN CERTIFICATE-----..." />
            </div>
            <div className="col-span-2 flex justify-end gap-2">
              <button type="button" onClick={() => setShowUpload(false)} className="btn-secondary">取消</button>
              <button type="submit" disabled={uploading} className="btn-primary flex items-center gap-1.5">
                {uploading ? '上传中...' : '上传'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            className="input-field pl-9"
            placeholder="搜索域名..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-1">
          {(['all', 'active', 'expiring', 'expired', 'inactive'] as FilterStatus[]).map(s => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                statusFilter === s ? 'bg-blue-500/20 text-blue-400' : 'text-zinc-400 hover:text-white hover:bg-white/5'
              }`}
            >
              {s === 'all' ? '全部' : s === 'active' ? '正常' : s === 'expiring' ? '即将过期' : s === 'expired' ? '已过期' : '不活跃'}
              {filterCounts[s] !== undefined && <span className="ml-1 text-zinc-500">{filterCounts[s]}</span>}
            </button>
          ))}
        </div>
      </div>

      {/* Certificate table */}
      <div className="glass-panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-zinc-500 text-xs border-b border-white/5">
                <th className="text-left py-3 px-4 font-medium">域名</th>
                <th className="text-left py-3 px-4 font-medium">序列号</th>
                <th className="text-left py-3 px-4 font-medium">来源</th>
                <th className="text-left py-3 px-4 font-medium">到期时间</th>
                <th className="text-left py-3 px-4 font-medium">剩余天数</th>
                <th className="text-left py-3 px-4 font-medium">绑定节点</th>
                <th className="text-left py-3 px-4 font-medium">状态</th>
                <th className="text-left py-3 px-4 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i} className="border-b border-white/5">
                    {Array.from({ length: 8 }).map((_, j) => (
                      <td key={j} className="py-3 px-4"><div className="skeleton h-4 rounded" /></td>
                    ))}
                  </tr>
                ))
              ) : filteredCerts.length === 0 ? (
                <tr><td colSpan={8} className="text-center py-12 text-zinc-500">暂无证书</td></tr>
              ) : (
                filteredCerts.map(cert => {
                  const days = Math.ceil((new Date(cert.not_after).getTime() - now.getTime()) / 86400000);
                  const urgency = urgencyLabel(days);
                  const isExpanded = expandedCert === cert.id;
                  const providerLabel: Record<string, string> = { manual: '手动上传', aliyun: '阿里云', letsencrypt: "Let's Encrypt", digicert: 'DigiCert' };

                  return (
                    <tbody key={cert.id}>
                      <tr
                        className="border-b border-white/5 hover:bg-white/[0.02] transition-colors cursor-pointer"
                        onClick={() => handleExpand(cert.id)}
                      >
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            {isExpanded ? <ChevronUp size={14} className="text-zinc-500" /> : <ChevronDown size={14} className="text-zinc-500" />}
                            <div>
                              <div className="font-medium text-white">{cert.subject_cn}</div>
                              <div className="text-xs text-zinc-500">{cert.name}</div>
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-4 font-mono text-xs text-zinc-500">{cert.serial_hex.substring(0, 16)}...</td>
                        <td className="py-3 px-4 text-zinc-400">{providerLabel[cert.provider || 'manual'] || cert.provider}</td>
                        <td className="py-3 px-4 text-zinc-400">{format(new Date(cert.not_after), 'yyyy-MM-dd')}</td>
                        <td className="py-3 px-4">
                          <span className={urgency.cls.split(' ')[1] || 'text-zinc-400'}>{urgency.text}</span>
                          <span className="text-zinc-500 ml-1">
                            {days < 0 ? `(${Math.abs(days)}天前)` : days === 0 ? '(今天)' : `(${days}天)`}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-zinc-400">{assignments.filter(a => a.external_cert_id === cert.id).length || '—'}台</td>
                        <td className="py-3 px-4">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${cert.is_active ? 'bg-green-500/10 text-green-400' : 'bg-zinc-500/10 text-zinc-400'}`}>
                            {cert.is_active ? '活跃' : '不活跃'}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <button className="text-xs text-blue-400 hover:text-blue-300">
                            {(days <= 30 && days > 0) || days <= 0 ? '续期' : '查看'}
                          </button>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr>
                          <td colSpan={8} className="bg-white/[0.02] px-6 py-4">
                            <div className="grid grid-cols-2 gap-4 text-sm">
                              <div>
                                <span className="text-zinc-500">有效期起</span>
                                <div className="text-white">{format(new Date(cert.not_before), 'yyyy-MM-dd HH:mm')}</div>
                              </div>
                              <div>
                                <span className="text-zinc-500">有效期止</span>
                                <div className="text-white">{format(new Date(cert.not_after), 'yyyy-MM-dd HH:mm')}</div>
                              </div>
                              <div>
                                <span className="text-zinc-500">证书 ID</span>
                                <div className="text-white font-mono text-xs">{cert.id}</div>
                              </div>
                              <div>
                                <span className="text-zinc-500">自动续期</span>
                                <div className="text-white">{cert.auto_renew ? '是' : '否'}</div>
                              </div>
                            </div>
                            {assignments.length > 0 && (
                              <div className="mt-4">
                                <span className="text-zinc-500 text-xs">分发节点：</span>
                                <div className="mt-2 space-y-1">
                                  {assignments.map(a => (
                                    <div key={a.id} className="flex items-center gap-2 text-xs">
                                      <ShieldCheck size={12} className="text-green-400" />
                                      <span className="text-white">{a.agent_name}</span>
                                      <span className="text-zinc-500">{a.local_path}</span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}