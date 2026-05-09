import { useCallback, useDeferredValue, useEffect, useMemo, useState } from 'react';
import { RefreshCw, UploadCloud, X } from 'lucide-react';
import { apiFetch, apiPost, apiUpload } from '../lib/api';
import CertFilters from './CertFilters';
import CertTable from './CertTable';
import CertDetailDrawer from './CertDetailDrawer';
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
  cert_paths?: string[] | null;
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

function getDaysRemaining(notAfter: string) {
  return Math.ceil((new Date(notAfter).getTime() - Date.now()) / 86400000);
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
  const [showDeploy, setShowDeploy] = useState(false);
  const [selectedAgentIds, setSelectedAgentIds] = useState<Set<string>>(new Set());
  const [deploying, setDeploying] = useState(false);
  const [deployResult, setDeployResult] = useState<{ success: number; failed: number } | null>(null);

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

  const handleDeploy = async () => {
    if (!selectedCertId || !selectedCert || selectedAgentIds.size === 0) return;

    setDeploying(true);
    setDeployResult(null);

    let success = 0;
    let failed = 0;

    for (const agentId of selectedAgentIds) {
      const agent = agents.find((a) => a.id === agentId);
      if (!agent || !agent.cert_paths?.length) {
        failed++;
        continue;
      }

      const baseDir = agent.cert_paths[0].replace(/\/[^/]+$/, '');
      const localPath = `${baseDir}/${selectedCert.subject_cn}.crt`;

      try {
        await apiPost(`/agents/${agent.id}/assign-cert`, {
          external_cert_id: selectedCertId,
          local_path: localPath,
        });
        success++;
      } catch {
        failed++;
      }
    }

    setDeployResult({ success, failed });
    setDeploying(false);
    await fetchData();
    if (selectedCertId) {
      void loadCertDetail(selectedCertId, agents);
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
            <p className="mt-2 max-w-3xl text-sm leading-6 text-white/50">
              资产列表、详情抽屉和上传入口集中在这一页，先处理临近到期项，再检查绑定节点和证书内容。
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="metric-badge border-white/8 bg-white/[0.03] text-white/80">总数 {certs.length}</span>
              <span className="metric-badge border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] text-[#ffbf8f]">7 天内 {counts.critical}</span>
              <span className="metric-badge border-white/8 bg-white/[0.03] text-white/80">30 天内 {counts.warning}</span>
              {selectedSummary && (
                <span className="metric-badge border-white/8 bg-white/[0.03] text-white/80">
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
            { label: '证书总数', value: certs.length, tone: 'border-white/8 bg-white/[0.03] text-white/90' },
            { label: '7 天内到期', value: counts.critical, tone: 'border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] text-white' },
            { label: '30 天内关注', value: counts.warning, tone: 'border-white/8 bg-white/[0.03] text-white/90' },
            { label: '证书来源', value: providerCount, tone: 'border-white/8 bg-white/[0.03] text-white/90' },
          ].map((item) => (
            <div key={item.label} className={`rounded-[20px] border p-4 ${item.tone}`}>
              <div className="text-xs uppercase tracking-[0.18em] text-white/60">{item.label}</div>
              <div className="mt-2 text-2xl font-semibold text-white">{item.value}</div>
            </div>
          ))}
        </div>
      </section>

      <CertFilters
        search={search}
        onSearchChange={setSearch}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
      />

      {showUpload && (
        <div className="glass-panel rounded-[24px] p-6">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="section-kicker">Upload</div>
              <h3 className="mt-2 text-lg font-semibold text-white">录入新证书</h3>
            </div>
              <button type="button" onClick={() => { setShowUpload(false); resetUploadForm(); }} className="rounded-[16px] border border-white/8 p-2 text-white/70 hover:text-white">
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
                <label className="mb-1 block text-xs text-white/70">显示名称</label>
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
                <label className="mb-1 block text-xs text-white/70">证书 PEM</label>
                <textarea
                  className="input-field h-28 font-mono text-xs"
                  value={uploadForm.cert_pem}
                  onChange={(event) => setUploadForm((current) => ({ ...current, cert_pem: event.target.value }))}
                  required
                  placeholder="-----BEGIN CERTIFICATE-----"
                />
              </div>
              <div className="lg:col-span-2">
                <label className="mb-1 block text-xs text-white/70">私钥 PEM</label>
                <textarea
                  className="input-field h-28 font-mono text-xs"
                  value={uploadForm.key_pem}
                  onChange={(event) => setUploadForm((current) => ({ ...current, key_pem: event.target.value }))}
                  required
                  placeholder="-----BEGIN PRIVATE KEY-----"
                />
              </div>
              <div className="lg:col-span-2">
                <label className="mb-1 block text-xs text-white/70">证书链 PEM</label>
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
                  <label className="mb-1 block text-xs text-white/70">显示名称（可选）</label>
                  <input
                    className="input-field"
                    value={archiveForm.name}
                    onChange={(event) => setArchiveForm((current) => ({ ...current, name: event.target.value }))}
                    placeholder="默认使用证书 CN"
                  />
                </div>
                <div>
                <label className="mb-1 block text-xs text-white/70">来源</label>
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
                <label className="mb-1 block text-xs text-white/70">备注</label>
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
        <CertTable
          certs={filteredCerts}
          isLoading={isLoading}
          selectedCertId={selectedCertId}
          onSelectCert={setSelectedCertId}
          bindingCounts={bindingCounts}
          onDeleteCert={(id) => { setDeletingCertId(id); setShowDeleteConfirm(true); }}
        />

        <CertDetailDrawer
          selectedCert={selectedCert}
          selectedAssignments={selectedAssignments}
          isDetailLoading={isDetailLoading}
          detailError={detailError}
          agents={agents}
          selectedAgentIds={selectedAgentIds}
          onSelectedAgentIdsChange={setSelectedAgentIds}
          showDeploy={showDeploy}
          onShowDeployChange={setShowDeploy}
          deploying={deploying}
          deployResult={deployResult}
          onDeployResultChange={setDeployResult}
          onDeploy={handleDeploy}
        />
      </div>

      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="glass-panel max-w-md rounded-[24px] p-6">
            <h3 className="text-lg font-semibold text-white">确认删除证书</h3>
            <p className="mt-2 text-sm text-white/80">
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