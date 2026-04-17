import { useCallback, useDeferredValue, useEffect, useMemo, useState } from 'react';
import { FileKey2, RefreshCw, Search, ShieldCheck, Trash2, UploadCloud, X } from 'lucide-react';
import { format, formatDistanceToNow } from 'date-fns';
import { apiFetch, apiPost, apiUpload } from '../lib/api';
import FileUploadZone from './FileUploadZone';
import ArchivePreview from './ArchivePreview';

interface PaginatedResponse<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}

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

interface ExternalCertDetail extends ExternalCert {
  cert_pem: string;
  chain_pem: string | null;
}

interface AgentSummary {
  id: string;
  name: string;
  status: string;
  liveness: 'online' | 'delayed' | 'offline';
  cert_count: number;
  expiring_soon_count: number;
}

interface RawAgentAssignment {
  id: string;
  agent_id: string;
  external_cert_id: string;
  local_path: string;
  created_at: string;
}

interface CertAssignment extends RawAgentAssignment {
  agent_name: string;
  agent_liveness: 'online' | 'delayed' | 'offline';
}

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

type FilterStatus = 'all' | 'healthy' | 'warning' | 'critical' | 'inactive';
type UploadMode = 'pem' | 'archive';

const providerLabels: Record<string, string> = {
  manual: '手动上传',
  aliyun: '阿里云',
  letsencrypt: "Let's Encrypt",
  digicert: 'DigiCert',
};

const livenessTone: Record<'online' | 'delayed' | 'offline', string> = {
  online: 'bg-[#73bf69]',
  delayed: 'bg-[#ff995c]',
  offline: 'bg-[#ff995c]',
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

function previewPem(pem: string, lineCount = 8) {
  return pem.split('\n').slice(0, lineCount).join('\n').trim();
}

export default function CertManagementPage() {
  const [certs, setCerts] = useState<ExternalCert[]>([]);
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [selectedCertId, setSelectedCertId] = useState<string | null>(null);
  const [selectedCert, setSelectedCert] = useState<ExternalCertDetail | null>(null);
  const [selectedAssignments, setSelectedAssignments] = useState<CertAssignment[]>([]);
  const [bindingCounts, setBindingCounts] = useState<Record<string, number>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<FilterStatus>('all');
  const [search, setSearch] = useState('');
  const [showUpload, setShowUpload] = useState(false);
  const [deletingCertId, setDeletingCertId] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const deferredSearch = useDeferredValue(search);

  const [uploadForm, setUploadForm] = useState({
    name: '',
    description: '',
    provider: 'manual',
    cert_pem: '',
    key_pem: '',
    chain_pem: '',
  });
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  const [uploadMode, setUploadMode] = useState<UploadMode>('pem');
  const [archiveFile, setArchiveFile] = useState<File | null>(null);
  const [archivePreview, setArchivePreview] = useState<ArchivePreviewData | null>(null);
  const [archiveUploading, setArchiveUploading] = useState(false);
  const [archiveForm, setArchiveForm] = useState({
    name: '',
    description: '',
    provider: 'manual',
  });

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [certsData, agentsData] = await Promise.all([
        apiFetch<PaginatedResponse<ExternalCert>>('/external-certs?limit=1000'),
        apiFetch<PaginatedResponse<AgentSummary>>('/agents?limit=500'),
      ]);

      setCerts(certsData.items || []);
      setAgents(agentsData.items || []);
      setSelectedCertId((current) => {
        const exists = current && certsData.items.some((cert) => cert.id === current);
        return exists ? current : certsData.items[0]?.id ?? null;
      });
    } catch (error) {
      console.error('Failed to fetch certificates:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadCertDetail = useCallback(async (certId: string, agentSnapshot: AgentSummary[]) => {
    setIsDetailLoading(true);
    setDetailError(null);

    try {
      const [detail, assignmentResults] = await Promise.all([
        apiFetch<ExternalCertDetail>(`/external-certs/${certId}`),
        Promise.allSettled(
          agentSnapshot.map(async (agent) => {
            const items = await apiFetch<RawAgentAssignment[]>(`/agents/${agent.id}/assignments`);
            return items
              .filter((assignment) => assignment.external_cert_id === certId)
              .map((assignment) => ({
                ...assignment,
                agent_name: agent.name,
                agent_liveness: agent.liveness,
              }));
          })
        ),
      ]);

      const derivedAssignments = assignmentResults
        .flatMap((result) => (result.status === 'fulfilled' ? result.value : []))
        .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());

      setSelectedCert(detail);
      setSelectedAssignments(derivedAssignments);
      setBindingCounts((current) => ({ ...current, [certId]: derivedAssignments.length }));
    } catch (error) {
      setSelectedCert(null);
      setSelectedAssignments([]);
      setDetailError(error instanceof Error ? error.message : '读取证书详情失败');
    } finally {
      setIsDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (!selectedCertId) {
      setSelectedCert(null);
      setSelectedAssignments([]);
      setDetailError(null);
      return;
    }

    void loadCertDetail(selectedCertId, agents);
  }, [selectedCertId, agents, loadCertDetail]);

  const handleUpload = async (event: React.FormEvent) => {
    event.preventDefault();
    setUploading(true);
    setUploadError(null);
    setUploadSuccess(false);

    try {
      await apiPost('/external-certs', uploadForm);
      setUploadSuccess(true);
      setUploadForm({
        name: '',
        description: '',
        provider: 'manual',
        cert_pem: '',
        key_pem: '',
        chain_pem: '',
      });
      await fetchData();
      window.setTimeout(() => {
        setShowUpload(false);
        setUploadSuccess(false);
      }, 1200);
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : '上传失败');
    } finally {
      setUploading(false);
    }
  };

  const handleArchiveFileSelect = useCallback((file: File) => {
    setArchiveFile(file);
    setArchivePreview(null);
  }, []);

  const handleArchiveUpload = async () => {
    if (!archiveFile) return;

    setArchiveUploading(true);
    setUploadError(null);

    try {
      const formData = new FormData();
      formData.append('archive', archiveFile);
      if (archiveForm.name) formData.append('name', archiveForm.name);
      if (archiveForm.description) formData.append('description', archiveForm.description);
      if (archiveForm.provider) formData.append('provider', archiveForm.provider);

      const result = await apiUpload<ArchivePreviewData>('/external-certs/upload-archive', formData);
      setArchivePreview(result);
      setArchiveFile(null);
      setArchiveForm({
        name: '',
        description: '',
        provider: 'manual',
      });
      await fetchData();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : '上传失败');
    } finally {
      setArchiveUploading(false);
    }
  };

  const handleDeleteCert = async () => {
    if (!deletingCertId) return;

    try {
      await fetch(`/api/control/external-certs/${deletingCertId}`, {
        method: 'DELETE',
        headers: {
          'X-Admin-API-Key': sessionStorage.getItem('admin_api_key') || '',
        },
      });
      setShowDeleteConfirm(false);
      setDeletingCertId(null);
      if (selectedCertId === deletingCertId) {
        setSelectedCertId(null);
      }
      await fetchData();
    } catch (error) {
      console.error('Failed to delete certificate:', error);
    }
  };

  const resetUploadForm = useCallback(() => {
    setUploadForm({
      name: '',
      description: '',
      provider: 'manual',
      cert_pem: '',
      key_pem: '',
      chain_pem: '',
    });
    setArchiveForm({
      name: '',
      description: '',
      provider: 'manual',
    });
    setArchiveFile(null);
    setArchivePreview(null);
    setUploadError(null);
    setUploadSuccess(false);
  }, []);

  const filteredCerts = useMemo(() => {
    const keyword = deferredSearch.trim().toLowerCase();

    return certs.filter((cert) => {
      const daysRemaining = getDaysRemaining(cert.not_after);

      if (statusFilter === 'healthy' && (!cert.is_active || daysRemaining <= 30)) {
        return false;
      }
      if (statusFilter === 'warning' && (!cert.is_active || daysRemaining <= 7 || daysRemaining > 30)) {
        return false;
      }
      if (statusFilter === 'critical' && (!cert.is_active || daysRemaining > 7)) {
        return false;
      }
      if (statusFilter === 'inactive' && cert.is_active) {
        return false;
      }

      if (!keyword) {
        return true;
      }

      return [cert.subject_cn, cert.name, cert.serial_hex]
        .filter(Boolean)
        .some((value) => value.toLowerCase().includes(keyword));
    });
  }, [certs, deferredSearch, statusFilter]);

  const counts = useMemo(() => {
    return certs.reduce(
      (result, cert) => {
        const daysRemaining = getDaysRemaining(cert.not_after);
        if (!cert.is_active) {
          result.inactive += 1;
        } else if (daysRemaining <= 7) {
          result.critical += 1;
        } else if (daysRemaining <= 30) {
          result.warning += 1;
        } else {
          result.healthy += 1;
        }
        return result;
      },
      { healthy: 0, warning: 0, critical: 0, inactive: 0 }
    );
  }, [certs]);

  const providerCount = useMemo(
    () => new Set(certs.map((cert) => cert.provider || 'manual')).size,
    [certs]
  );

  const selectedSummary = certs.find((cert) => cert.id === selectedCertId) || null;

  return (
    <div className="space-y-6 animate-fade-in">
      <section className="glass-panel rounded-[24px] p-5 lg:p-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <div className="section-kicker">Inventory</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white">证书资产</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
              资产列表、详情抽屉和上传入口集中在这一页，先处理临近到期项，再检查绑定节点和证书内容。
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="metric-badge border-white/8 bg-white/[0.03] text-neutral-300">总数 {certs.length}</span>
              <span className="metric-badge border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] text-[#ffbf8f]">7 天内 {counts.critical}</span>
              <span className="metric-badge border-white/8 bg-white/[0.03] text-neutral-300">30 天内 {counts.warning}</span>
              {selectedSummary && (
                <span className="metric-badge border-white/8 bg-white/[0.03] text-neutral-300">
                  当前 {selectedSummary.subject_cn}
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 xl:pt-1">
            <button onClick={() => void fetchData()} className="btn-secondary flex items-center gap-1.5" disabled={isLoading}>
              <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} /> 刷新
            </button>
            <button onClick={() => setShowUpload((current) => !current)} className="btn-primary flex items-center gap-1.5">
              <UploadCloud size={14} /> 上传证书
            </button>
          </div>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[
            { label: '证书总数', value: certs.length, tone: 'border-white/8 bg-white/[0.03] text-slate-100' },
            { label: '7 天内到期', value: counts.critical, tone: 'border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] text-white' },
            { label: '30 天内关注', value: counts.warning, tone: 'border-white/8 bg-white/[0.03] text-slate-100' },
            { label: '证书来源', value: providerCount, tone: 'border-white/8 bg-white/[0.03] text-slate-100' },
          ].map((item) => (
            <div key={item.label} className={`rounded-[20px] border p-4 ${item.tone}`}>
              <div className="text-xs uppercase tracking-[0.18em] text-white/60">{item.label}</div>
              <div className="mt-2 text-2xl font-semibold text-white">{item.value}</div>
            </div>
          ))}
        </div>
      </section>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-1 flex-wrap items-center gap-3">
          <label className="relative min-w-[260px] flex-1 max-w-md">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              className="input-field pl-9"
              placeholder="搜索域名、证书名或序列号"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            {([
              ['all', '全部'],
              ['healthy', '健康'],
              ['warning', '30 天内'],
              ['critical', '7 天内'],
              ['inactive', '未启用'],
            ] as Array<[FilterStatus, string]>).map(([status, label]) => (
              <button
                key={status}
                type="button"
                onClick={() => setStatusFilter(status)}
                className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                  statusFilter === status
                    ? 'border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] text-[#ffbf8f]'
                    : 'border-white/8 bg-white/[0.03] text-neutral-400 hover:text-white'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

      </div>

      {showUpload && (
        <div className="glass-panel rounded-[24px] p-6">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="section-kicker">Upload</div>
              <h3 className="mt-2 text-lg font-semibold text-white">录入新证书</h3>
            </div>
              <button type="button" onClick={() => { setShowUpload(false); resetUploadForm(); }} className="rounded-[16px] border border-white/8 p-2 text-slate-400 hover:text-white">
                <X size={18} />
              </button>
            </div>

          {uploadError && <div className="mb-4 rounded-[18px] border border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] p-3 text-sm text-[#ffbf8f]">{uploadError}</div>}
          {uploadSuccess && <div className="mb-4 rounded-[18px] border border-[rgba(115,191,105,0.18)] bg-[rgba(115,191,105,0.10)] p-3 text-sm text-[#9adf90]">证书上传成功。</div>}

          <div className="mb-4 flex gap-2">
            <button
              type="button"
              onClick={() => setUploadMode('pem')}
              className={`rounded-lg border px-4 py-2 text-sm font-medium transition-colors ${
                uploadMode === 'pem'
                  ? 'border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] text-[#ffbf8f]'
                  : 'border-white/8 bg-white/[0.03] text-neutral-400 hover:text-white'
                }`}
            >
              PEM 文本
            </button>
            <button
              type="button"
              onClick={() => setUploadMode('archive')}
              className={`rounded-lg border px-4 py-2 text-sm font-medium transition-colors ${
                uploadMode === 'archive'
                  ? 'border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] text-[#ffbf8f]'
                  : 'border-white/8 bg-white/[0.03] text-neutral-400 hover:text-white'
                }`}
            >
              文件上传
            </button>
          </div>

          {uploadMode === 'pem' ? (
            <form onSubmit={handleUpload} className="grid gap-4 lg:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs text-slate-400">显示名称</label>
                <input
                  className="input-field"
                  value={uploadForm.name}
                  onChange={(event) => setUploadForm((current) => ({ ...current, name: event.target.value }))}
                  required
                  placeholder="api.example.com"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-400">来源</label>
                <select
                  className="input-field"
                  value={uploadForm.provider}
                  onChange={(event) => setUploadForm((current) => ({ ...current, provider: event.target.value }))}
                >
                  <option value="manual">手动上传</option>
                  <option value="aliyun">阿里云</option>
                  <option value="letsencrypt">Let's Encrypt</option>
                  <option value="digicert">DigiCert</option>
                </select>
              </div>
              <div className="lg:col-span-2">
                <label className="mb-1 block text-xs text-slate-400">备注</label>
                <input
                  className="input-field"
                  value={uploadForm.description}
                  onChange={(event) => setUploadForm((current) => ({ ...current, description: event.target.value }))}
                  placeholder="例如：支付域名的生产证书"
                />
              </div>
              <div className="lg:col-span-2">
                <label className="mb-1 block text-xs text-slate-400">证书 PEM</label>
                <textarea
                  className="input-field h-28 font-mono text-xs"
                  value={uploadForm.cert_pem}
                  onChange={(event) => setUploadForm((current) => ({ ...current, cert_pem: event.target.value }))}
                  required
                  placeholder="-----BEGIN CERTIFICATE-----"
                />
              </div>
              <div className="lg:col-span-2">
                <label className="mb-1 block text-xs text-slate-400">私钥 PEM</label>
                <textarea
                  className="input-field h-28 font-mono text-xs"
                  value={uploadForm.key_pem}
                  onChange={(event) => setUploadForm((current) => ({ ...current, key_pem: event.target.value }))}
                  required
                  placeholder="-----BEGIN PRIVATE KEY-----"
                />
              </div>
              <div className="lg:col-span-2">
                <label className="mb-1 block text-xs text-slate-400">证书链 PEM</label>
                <textarea
                  className="input-field h-24 font-mono text-xs"
                  value={uploadForm.chain_pem}
                  onChange={(event) => setUploadForm((current) => ({ ...current, chain_pem: event.target.value }))}
                  placeholder="-----BEGIN CERTIFICATE-----"
                />
              </div>
              <div className="lg:col-span-2 flex justify-end gap-2">
                <button type="button" onClick={() => { setShowUpload(false); resetUploadForm(); }} className="btn-secondary">取消</button>
                <button type="submit" className="btn-primary" disabled={uploading}>{uploading ? '上传中...' : '提交证书'}</button>
              </div>
            </form>
          ) : (
            <div className="space-y-4">
              <div className="grid gap-4 lg:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs text-slate-400">显示名称（可选）</label>
                  <input
                    className="input-field"
                    value={archiveForm.name}
                    onChange={(event) => setArchiveForm((current) => ({ ...current, name: event.target.value }))}
                    placeholder="默认使用证书 CN"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-400">来源</label>
                  <select
                    className="input-field"
                    value={archiveForm.provider}
                    onChange={(event) => setArchiveForm((current) => ({ ...current, provider: event.target.value }))}
                  >
                    <option value="manual">手动上传</option>
                    <option value="aliyun">阿里云</option>
                    <option value="letsencrypt">Let's Encrypt</option>
                    <option value="digicert">DigiCert</option>
                  </select>
                </div>
                <div className="lg:col-span-2">
                  <label className="mb-1 block text-xs text-slate-400">备注</label>
                  <input
                    className="input-field"
                    value={archiveForm.description}
                    onChange={(event) => setArchiveForm((current) => ({ ...current, description: event.target.value }))}
                    placeholder="例如：支付域名的生产证书"
                  />
                </div>
              </div>

              <FileUploadZone
                onFileSelect={handleArchiveFileSelect}
                disabled={archiveUploading}
              />

              {archivePreview && <ArchivePreview data={archivePreview} />}

              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => { setShowUpload(false); resetUploadForm(); }}
                  className="btn-secondary"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={handleArchiveUpload}
                  className="btn-primary"
                  disabled={!archiveFile || archiveUploading}
                >
                  {archiveUploading ? '上传中...' : '上传压缩包'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.9fr)_400px]">
        <div className="glass-panel overflow-hidden">
          <div className="border-b border-white/6 px-5 py-4">
            <div className="section-kicker">Inventory Table</div>
            <h3 className="mt-2 text-lg font-semibold text-white">证书资产列表</h3>
            <p className="mt-1 text-sm text-slate-400">列表保留高频字段，详情放到右侧抽屉，不再把所有信息挤在一行里。</p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/6 text-xs text-slate-500">
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
                ) : filteredCerts.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-5 py-14 text-center text-sm text-slate-500">没有匹配的证书。</td>
                  </tr>
                ) : (
                  filteredCerts.map((cert) => {
                    const daysRemaining = getDaysRemaining(cert.not_after);
                    const health = getCertHealth(daysRemaining, cert.is_active);
                    const isSelected = selectedCertId === cert.id;
                    const bindingCount = bindingCounts[cert.id];

                    return (
                      <tr
                        key={cert.id}
                        className={`table-row cursor-pointer ${isSelected ? 'bg-white/[0.05]' : ''}`}
                        onClick={() => setSelectedCertId(cert.id)}
                      >
                        <td className="px-5 py-4">
                          <div className="flex items-start gap-3">
                            <div className="rounded-[14px] border border-white/8 bg-white/[0.03] p-2 text-white">
                              <FileKey2 size={16} />
                            </div>
                            <div>
                              <div className="font-medium text-white">{cert.subject_cn}</div>
                              <div className="mt-1 text-xs text-slate-500">{cert.name}</div>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-4 text-slate-400">{providerLabels[cert.provider || 'manual'] || cert.provider || '手动上传'}</td>
                        <td className="px-4 py-4 text-slate-300">{format(new Date(cert.not_after), 'yyyy-MM-dd')}</td>
                        <td className="px-4 py-4">
                          <span className={`rounded-full border px-2 py-0.5 text-xs ${health.tone}`}>{health.label}</span>
                          <div className="mt-1 text-xs text-slate-500">
                            {daysRemaining < 0 ? `已过期 ${Math.abs(daysRemaining)} 天` : `${daysRemaining} 天`}
                          </div>
                        </td>
                        <td className="px-4 py-4 text-slate-400">{typeof bindingCount === 'number' ? `${bindingCount} 台` : '点选后计算'}</td>
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
                                setSelectedCertId(cert.id);
                              }}
                              className="text-xs font-medium text-[#ffbf8f] hover:text-[#ffd0ad]"
                            >
                              查看抽屉
                            </button>
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                setDeletingCertId(cert.id);
                                setShowDeleteConfirm(true);
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

        <aside className="glass-panel rounded-[24px] self-start p-5 xl:sticky xl:top-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="section-kicker">Certificate Drawer</div>
              <h3 className="mt-2 text-lg font-semibold text-white">证书详情抽屉</h3>
              <p className="mt-1 text-sm text-neutral-500">查看 PEM、绑定节点和密钥托管策略。</p>
            </div>
            {selectedCert && <span className="metric-badge border-white/8 bg-white/[0.03] text-neutral-300">{selectedAssignments.length} 节点</span>}
          </div>

          {!selectedCertId ? (
            <div className="mt-6 rounded-lg border border-white/8 bg-white/[0.03] px-4 py-8 text-center text-sm text-slate-500">从左侧选择一张证书查看详情。</div>
          ) : isDetailLoading ? (
            <div className="mt-6 space-y-3">
              <div className="skeleton h-6 rounded" />
              <div className="skeleton h-20 rounded" />
              <div className="skeleton h-32 rounded" />
            </div>
          ) : detailError ? (
            <div className="mt-6 rounded-[20px] border border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] p-4 text-sm text-[#ffbf8f]">{detailError}</div>
          ) : selectedCert ? (
            <div className="mt-6 space-y-5">
              <div>
                <div className="text-xl font-semibold text-white">{selectedCert.subject_cn}</div>
                <div className="mt-1 text-sm text-slate-400">{selectedCert.name}</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <span className={`rounded-full border px-2 py-0.5 text-xs ${getCertHealth(getDaysRemaining(selectedCert.not_after), selectedCert.is_active).tone}`}>
                    {getCertHealth(getDaysRemaining(selectedCert.not_after), selectedCert.is_active).label}
                  </span>
                  <span className="rounded-full border border-white/8 bg-white/[0.03] px-2 py-0.5 text-xs text-neutral-300">
                    {providerLabels[selectedCert.provider || 'manual'] || selectedCert.provider || '手动上传'}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-[18px] border border-white/8 bg-white/[0.03] p-3">
                  <div className="text-xs text-slate-500">到期时间</div>
                  <div className="mt-2 text-white">{format(new Date(selectedCert.not_after), 'yyyy-MM-dd HH:mm')}</div>
                </div>
                <div className="rounded-[18px] border border-white/8 bg-white/[0.03] p-3">
                  <div className="text-xs text-slate-500">更新于</div>
                  <div className="mt-2 text-white">{formatDistanceToNow(new Date(selectedCert.updated_at), { addSuffix: true })}</div>
                </div>
                <div className="col-span-2 rounded-[18px] border border-white/8 bg-white/[0.03] p-3">
                  <div className="text-xs text-slate-500">序列号</div>
                  <div className="mt-2 break-all font-mono text-xs text-slate-200">{selectedCert.serial_hex}</div>
                </div>
              </div>

              <div>
                <div className="mb-3 flex items-center gap-2 text-sm font-medium text-white">
                  <ShieldCheck size={15} className="text-[#ffbf8f]" />
                  分发节点
                </div>
                {selectedAssignments.length === 0 ? (
                  <div className="rounded-[18px] border border-white/8 bg-white/[0.03] px-4 py-6 text-sm text-slate-500">当前还没有节点绑定这张证书。</div>
                ) : (
                  <div className="space-y-2">
                    {selectedAssignments.map((assignment) => (
                        <div key={assignment.id} className="rounded-[18px] border border-white/8 bg-white/[0.03] p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="flex items-center gap-2 text-sm font-medium text-white">
                              <span className={`h-2 w-2 rounded-full ${livenessTone[assignment.agent_liveness]}`} />
                              {assignment.agent_name}
                            </div>
                            <div className="mt-1 break-all text-xs text-slate-500">{assignment.local_path}</div>
                          </div>
                          <div className="text-xs text-slate-500">{formatDistanceToNow(new Date(assignment.created_at), { addSuffix: true })}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="rounded-[20px] border border-white/8 bg-white/[0.03] p-4">
                <div className="text-sm font-medium text-white">私钥策略</div>
                <p className="mt-2 text-sm leading-6 text-neutral-400">
                  私钥由服务端使用 Fernet 加密托管，控制台只展示证书正文和链，不返回明文私钥。
                </p>
              </div>

              <div>
                <div className="mb-2 text-sm font-medium text-white">证书 PEM 预览</div>
                <pre className="overflow-x-auto rounded-lg border border-white/8 bg-slate-950/80 p-4 text-xs leading-6 text-slate-300">
                  {previewPem(selectedCert.cert_pem)}
                </pre>
              </div>

              {selectedCert.chain_pem && (
                <div>
                  <div className="mb-2 text-sm font-medium text-white">证书链预览</div>
                  <pre className="overflow-x-auto rounded-lg border border-white/8 bg-slate-950/80 p-4 text-xs leading-6 text-slate-300">
                    {previewPem(selectedCert.chain_pem)}
                  </pre>
                </div>
              )}
            </div>
          ) : null}
        </aside>
      </div>

      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="glass-panel max-w-md rounded-[24px] p-6">
            <h3 className="text-lg font-semibold text-white">确认删除证书</h3>
            <p className="mt-2 text-sm text-slate-300">
              此操作将删除证书记录及其所有关联的 Agent 分配，且不可恢复。确定要继续吗？
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setShowDeleteConfirm(false);
                  setDeletingCertId(null);
                }}
                className="btn-secondary"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleDeleteCert}
                className="rounded-[18px] border border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] px-4 py-2.5 text-sm font-medium text-[#ffbf8f] hover:bg-[rgba(255,153,92,0.16)]"
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
