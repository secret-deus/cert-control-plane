import { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Clock3, Play, RefreshCw, RotateCcw, Search, ServerCog, ShieldCheck, UploadCloud } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { apiFetch, apiPost } from '../lib/api';

interface PaginatedResponse<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}

type LifecycleStatus = 'pending' | 'adopted' | 'deployed' | 'failed' | 'rolled_back';
type HealthStatus =
  | 'unknown'
  | 'healthy'
  | 'missing'
  | 'unmanaged'
  | 'serial_mismatch'
  | 'invalid_secret'
  | 'rbac_error'
  | 'cluster_unreachable';
type DryRunAction = 'adopt' | 'deploy' | 'rollback';

interface KubernetesCluster {
  id: string;
  name: string;
  environment: string | null;
  api_server: string;
  default_namespace: string | null;
  connection_status: 'unknown' | 'active' | 'failed';
  last_checked_at: string | null;
  created_at: string;
  updated_at: string;
}

interface ExternalCert {
  id: string;
  name: string;
  subject_cn: string;
  serial_hex: string;
  not_after: string;
}

interface KubernetesSecretAssignment {
  id: string;
  cluster_id: string;
  external_cert_id: string;
  namespace: string;
  secret_name: string;
  lifecycle_status: LifecycleStatus;
  health_status: HealthStatus;
  auto_track_latest: boolean;
  auto_deploy: boolean;
  pending_update: boolean;
  current_resource_version: string | null;
  current_serial_hex: string | null;
  last_snapshot_serial_hex: string | null;
  last_deployed_at: string | null;
  last_validated_at: string | null;
  cluster_name: string | null;
  external_cert_subject_cn: string | null;
}

interface KubernetesDryRun {
  id: string;
  assignment_id: string;
  action: DryRunAction;
  current_resource_version: string | null;
  diff: Array<{ path: string; before: string | null; after: string | null; sensitive?: boolean }> | null;
  expires_at: string;
}

interface KubernetesOperation {
  id: string;
  assignment_id: string | null;
  cluster_id: string;
  action: 'test_connection' | 'adopt' | 'deploy' | 'rollback' | 'validate';
  status: 'running' | 'succeeded' | 'failed';
  error_code: string | null;
  error_message: string | null;
  serial_before: string | null;
  serial_after: string | null;
  started_at: string;
  finished_at: string | null;
}

const lifecycleLabels: Record<LifecycleStatus, string> = {
  pending: '待处理',
  adopted: '已接管',
  deployed: '已部署',
  failed: '失败',
  rolled_back: '已回滚',
};

const healthLabels: Record<HealthStatus, string> = {
  unknown: '未知',
  healthy: '健康',
  missing: '缺失',
  unmanaged: '未接管',
  serial_mismatch: '序列号不一致',
  invalid_secret: 'Secret 无效',
  rbac_error: 'RBAC 错误',
  cluster_unreachable: '集群不可达',
};

function statusTone(status: string) {
  if (['healthy', 'deployed', 'adopted', 'succeeded', 'active'].includes(status)) {
    return 'border-[rgba(115,191,105,0.20)] bg-[rgba(115,191,105,0.12)] text-[#b8e5b2]';
  }
  if (['failed', 'missing', 'unmanaged', 'invalid_secret', 'serial_mismatch', 'rbac_error', 'cluster_unreachable'].includes(status)) {
    return 'border-[rgba(255,153,92,0.22)] bg-[rgba(255,153,92,0.12)] text-[#ffbf8f]';
  }
  return 'border-white/10 bg-white/[0.04] text-white/70';
}

function shortId(value: string | null | undefined) {
  if (!value) return '-';
  return value.length > 12 ? `${value.slice(0, 12)}...` : value;
}

export default function KubernetesPage() {
  const [clusters, setClusters] = useState<KubernetesCluster[]>([]);
  const [certs, setCerts] = useState<ExternalCert[]>([]);
  const [assignments, setAssignments] = useState<KubernetesSecretAssignment[]>([]);
  const [operations, setOperations] = useState<KubernetesOperation[]>([]);
  const [selectedAssignmentId, setSelectedAssignmentId] = useState<string | null>(null);
  const [activeDryRun, setActiveDryRun] = useState<KubernetesDryRun | null>(null);
  const [search, setSearch] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [clusterForm, setClusterForm] = useState({
    name: '',
    environment: 'dev',
    kubeconfig: '',
    default_namespace: '',
  });
  const [assignmentForm, setAssignmentForm] = useState({
    cluster_id: '',
    namespace: 'default',
    secret_name: '',
    external_cert_id: '',
  });

  const selectedAssignment = useMemo(
    () => assignments.find((item) => item.id === selectedAssignmentId) ?? assignments[0] ?? null,
    [assignments, selectedAssignmentId]
  );

  const filteredAssignments = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    if (!keyword) return assignments;
    return assignments.filter((item) =>
      [
        item.cluster_name,
        item.namespace,
        item.secret_name,
        item.external_cert_subject_cn,
        item.current_serial_hex,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword))
    );
  }, [assignments, search]);

  const stats = useMemo(() => {
    return {
      clusters: clusters.length,
      assignments: assignments.length,
      pending: assignments.filter((item) => item.pending_update).length,
      failed: assignments.filter((item) => item.lifecycle_status === 'failed' || item.health_status.includes('error')).length,
    };
  }, [clusters, assignments]);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [clusterData, assignmentData, operationData, certData] = await Promise.all([
        apiFetch<PaginatedResponse<KubernetesCluster>>('/kubernetes/clusters?limit=500'),
        apiFetch<PaginatedResponse<KubernetesSecretAssignment>>('/kubernetes/assignments?limit=500'),
        apiFetch<PaginatedResponse<KubernetesOperation>>('/kubernetes/operations?limit=100'),
        apiFetch<PaginatedResponse<ExternalCert>>('/external-certs?limit=1000'),
      ]);
      setClusters(clusterData.items || []);
      setAssignments(assignmentData.items || []);
      setOperations(operationData.items || []);
      setCerts(certData.items || []);
      setSelectedAssignmentId((current) => {
        const exists = current && assignmentData.items.some((item) => item.id === current);
        return exists ? current : assignmentData.items[0]?.id ?? null;
      });
      setAssignmentForm((current) => ({
        ...current,
        cluster_id: current.cluster_id || clusterData.items[0]?.id || '',
        external_cert_id: current.external_cert_id || certData.items[0]?.id || '',
      }));
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '读取 Kubernetes 数据失败');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const createCluster = async (event: React.FormEvent) => {
    event.preventDefault();
    setActionError(null);
    setActionMessage(null);
    try {
      await apiPost<KubernetesCluster>('/kubernetes/clusters', {
        name: clusterForm.name,
        environment: clusterForm.environment || null,
        kubeconfig: clusterForm.kubeconfig,
        default_namespace: clusterForm.default_namespace || null,
      });
      setClusterForm({ name: '', environment: 'dev', kubeconfig: '', default_namespace: '' });
      setActionMessage('Cluster saved');
      await fetchData();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '保存 Cluster 失败');
    }
  };

  const createAssignment = async (event: React.FormEvent) => {
    event.preventDefault();
    setActionError(null);
    setActionMessage(null);
    try {
      const created = await apiPost<KubernetesSecretAssignment>('/kubernetes/assignments', {
        ...assignmentForm,
      });
      setSelectedAssignmentId(created.id);
      setAssignmentForm((current) => ({ ...current, secret_name: '' }));
      setActionMessage('Assignment saved');
      await fetchData();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '保存 Assignment 失败');
    }
  };

  const runDryRun = async (action: DryRunAction) => {
    if (!selectedAssignment) return;
    setActionError(null);
    setActionMessage(null);
    try {
      const dryRun = await apiPost<KubernetesDryRun>(
        `/kubernetes/assignments/${selectedAssignment.id}/${action}/dry-run`
      );
      setActiveDryRun(dryRun);
      setActionMessage(`${action} dry-run ready`);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : `${action} dry-run 失败`);
    }
  };

  const confirmDryRun = async () => {
    if (!selectedAssignment || !activeDryRun) return;
    setActionError(null);
    setActionMessage(null);
    try {
      const updated = await apiPost<KubernetesSecretAssignment>(
        `/kubernetes/assignments/${selectedAssignment.id}/${activeDryRun.action}/confirm`,
        { dry_run_id: activeDryRun.id }
      );
      setSelectedAssignmentId(updated.id);
      setActiveDryRun(null);
      setActionMessage(`${updated.secret_name} updated`);
      await fetchData();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '确认写入失败');
    }
  };

  const validateAssignment = async () => {
    if (!selectedAssignment) return;
    setActionError(null);
    setActionMessage(null);
    try {
      const updated = await apiPost<KubernetesSecretAssignment>(
        `/kubernetes/assignments/${selectedAssignment.id}/validate`
      );
      setSelectedAssignmentId(updated.id);
      setActionMessage('Validation complete');
      await fetchData();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '校验失败');
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <section className="glass-panel rounded-[24px] p-5 lg:p-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="section-kicker">Kubernetes Secret Targets</div>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-white">Kubernetes TLS Secret</h2>
          </div>
          <button type="button" onClick={fetchData} className="btn-secondary inline-flex items-center gap-2">
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric icon={ServerCog} label="Clusters" value={stats.clusters} />
          <Metric icon={ShieldCheck} label="Secret targets" value={stats.assignments} />
          <Metric icon={Clock3} label="Pending update" value={stats.pending} />
          <Metric icon={CheckCircle2} label="Needs action" value={stats.failed} />
        </div>
      </section>

      {(actionError || actionMessage) && (
        <div className={`rounded-[18px] border px-4 py-3 text-sm ${actionError ? statusTone('failed') : statusTone('healthy')}`}>
          {actionError || actionMessage}
        </div>
      )}

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.65fr)]">
        <div className="space-y-6">
          <div className="glass-panel rounded-[24px] p-5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="section-kicker">Assignments</div>
                <h3 className="mt-2 text-lg font-semibold text-white">Secret 映射</h3>
              </div>
              <div className="relative w-full lg:w-80">
                <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-white/40" size={16} />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="cluster / namespace / secret / CN"
                  className="input-field w-full pl-9"
                />
              </div>
            </div>

            <div className="mt-5 overflow-hidden rounded-[18px] border border-white/8">
              <div className="grid grid-cols-[1.2fr_1fr_1fr_1fr_0.9fr] gap-3 border-b border-white/8 bg-white/[0.03] px-4 py-3 text-xs font-medium uppercase tracking-[0.12em] text-white/45">
                <span>Target</span>
                <span>Certificate</span>
                <span>Lifecycle</span>
                <span>Health</span>
                <span>Serial</span>
              </div>
              {isLoading ? (
                <div className="px-4 py-8 text-sm text-white/60">Loading...</div>
              ) : filteredAssignments.length === 0 ? (
                <div className="px-4 py-8 text-sm text-white/60">No Kubernetes Secret assignments</div>
              ) : (
                filteredAssignments.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    onClick={() => {
                      setSelectedAssignmentId(item.id);
                      setActiveDryRun(null);
                    }}
                    className={`grid w-full grid-cols-[1.2fr_1fr_1fr_1fr_0.9fr] gap-3 border-b border-white/6 px-4 py-4 text-left text-sm transition-colors last:border-b-0 ${
                      selectedAssignment?.id === item.id ? 'bg-white/[0.06]' : 'hover:bg-white/[0.03]'
                    }`}
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-medium text-white">{item.cluster_name || item.cluster_id}</span>
                      <span className="mt-1 block truncate text-xs text-white/50">{item.namespace}/{item.secret_name}</span>
                    </span>
                    <span className="truncate text-white/70">{item.external_cert_subject_cn || item.external_cert_id}</span>
                    <span>
                      <StatusBadge label={lifecycleLabels[item.lifecycle_status]} status={item.lifecycle_status} />
                    </span>
                    <span>
                      <StatusBadge label={healthLabels[item.health_status]} status={item.health_status} />
                    </span>
                    <span className="truncate font-mono text-xs text-white/60">{shortId(item.current_serial_hex)}</span>
                  </button>
                ))
              )}
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <form onSubmit={createCluster} className="glass-panel rounded-[24px] p-5">
              <div className="section-kicker">Cluster</div>
              <h3 className="mt-2 text-lg font-semibold text-white">SA kubeconfig</h3>
              <div className="mt-4 space-y-3">
                <input
                  required
                  value={clusterForm.name}
                  onChange={(event) => setClusterForm((current) => ({ ...current, name: event.target.value }))}
                  placeholder="minikube-dev"
                  className="input-field w-full"
                />
                <div className="grid gap-3 sm:grid-cols-2">
                  <input
                    value={clusterForm.environment}
                    onChange={(event) => setClusterForm((current) => ({ ...current, environment: event.target.value }))}
                    placeholder="dev"
                    className="input-field w-full"
                  />
                  <input
                    value={clusterForm.default_namespace}
                    onChange={(event) => setClusterForm((current) => ({ ...current, default_namespace: event.target.value }))}
                    placeholder="default namespace"
                    className="input-field w-full"
                  />
                </div>
                <textarea
                  required
                  value={clusterForm.kubeconfig}
                  onChange={(event) => setClusterForm((current) => ({ ...current, kubeconfig: event.target.value }))}
                  placeholder="apiVersion: v1"
                  className="input-field min-h-36 w-full resize-y font-mono text-xs"
                />
                <button className="btn-primary inline-flex items-center gap-2" type="submit">
                  <UploadCloud size={16} />
                  Save cluster
                </button>
              </div>
            </form>

            <form onSubmit={createAssignment} className="glass-panel rounded-[24px] p-5">
              <div className="section-kicker">Secret Assignment</div>
              <h3 className="mt-2 text-lg font-semibold text-white">目标 Secret</h3>
              <div className="mt-4 space-y-3">
                <select
                  required
                  value={assignmentForm.cluster_id}
                  onChange={(event) => setAssignmentForm((current) => ({ ...current, cluster_id: event.target.value }))}
                  className="input-field w-full"
                >
                  <option value="">Select cluster</option>
                  {clusters.map((cluster) => (
                    <option key={cluster.id} value={cluster.id}>{cluster.name}</option>
                  ))}
                </select>
                <div className="grid gap-3 sm:grid-cols-2">
                  <input
                    required
                    value={assignmentForm.namespace}
                    onChange={(event) => setAssignmentForm((current) => ({ ...current, namespace: event.target.value }))}
                    placeholder="default"
                    className="input-field w-full"
                  />
                  <input
                    required
                    value={assignmentForm.secret_name}
                    onChange={(event) => setAssignmentForm((current) => ({ ...current, secret_name: event.target.value }))}
                    placeholder="api-tls"
                    className="input-field w-full"
                  />
                </div>
                <select
                  required
                  value={assignmentForm.external_cert_id}
                  onChange={(event) => setAssignmentForm((current) => ({ ...current, external_cert_id: event.target.value }))}
                  className="input-field w-full"
                >
                  <option value="">Select certificate</option>
                  {certs.map((cert) => (
                    <option key={cert.id} value={cert.id}>{cert.subject_cn} / {shortId(cert.serial_hex)}</option>
                  ))}
                </select>
                <button className="btn-primary inline-flex items-center gap-2" type="submit">
                  <ShieldCheck size={16} />
                  Save assignment
                </button>
              </div>
            </form>
          </div>
        </div>

        <aside className="space-y-6">
          <div className="glass-panel rounded-[24px] p-5">
            <div className="section-kicker">Selected Target</div>
            {selectedAssignment ? (
              <>
                <h3 className="mt-2 text-lg font-semibold text-white">{selectedAssignment.namespace}/{selectedAssignment.secret_name}</h3>
                <div className="mt-4 space-y-3 text-sm">
                  <DetailRow label="Cluster" value={selectedAssignment.cluster_name || selectedAssignment.cluster_id} />
                  <DetailRow label="Certificate" value={selectedAssignment.external_cert_subject_cn || selectedAssignment.external_cert_id} />
                  <DetailRow label="ResourceVersion" value={selectedAssignment.current_resource_version || '-'} />
                  <DetailRow label="Current serial" value={selectedAssignment.current_serial_hex || '-'} />
                  <DetailRow label="Rollback serial" value={selectedAssignment.last_snapshot_serial_hex || '-'} />
                </div>
                <div className="mt-5 grid grid-cols-2 gap-2">
                  <button type="button" onClick={() => runDryRun('deploy')} className="btn-primary inline-flex items-center justify-center gap-2">
                    <Play size={15} />
                    Dry run
                  </button>
                  <button type="button" onClick={validateAssignment} className="btn-secondary inline-flex items-center justify-center gap-2">
                    <RefreshCw size={15} />
                    Validate
                  </button>
                  <button type="button" onClick={() => runDryRun('adopt')} className="btn-secondary inline-flex items-center justify-center gap-2">
                    <ShieldCheck size={15} />
                    Adopt
                  </button>
                  <button type="button" onClick={() => runDryRun('rollback')} className="btn-secondary inline-flex items-center justify-center gap-2">
                    <RotateCcw size={15} />
                    Rollback
                  </button>
                </div>
              </>
            ) : (
              <div className="mt-3 text-sm text-white/60">No target selected</div>
            )}
          </div>

          <div className="glass-panel rounded-[24px] p-5">
            <div className="section-kicker">Dry Run</div>
            {activeDryRun ? (
              <div className="mt-4 space-y-4">
                <div className="rounded-[16px] border border-white/8 bg-white/[0.03] p-3 text-sm text-white/75">
                  <div className="flex items-center justify-between">
                    <span>{activeDryRun.action}</span>
                    <span className="font-mono text-xs">{shortId(activeDryRun.id)}</span>
                  </div>
                  <div className="mt-2 text-xs text-white/45">expires {new Date(activeDryRun.expires_at).toLocaleString()}</div>
                </div>
                <div className="space-y-2">
                  {(activeDryRun.diff || []).map((item) => (
                    <div key={`${item.path}-${item.after}`} className="rounded-[14px] border border-white/8 bg-black/10 p-3 text-xs">
                      <div className="font-mono text-white/70">{item.path}</div>
                      <div className="mt-1 text-white/45">{item.sensitive ? 'sensitive value' : `${item.before ?? '-'} -> ${item.after ?? '-'}`}</div>
                    </div>
                  ))}
                </div>
                <button type="button" onClick={confirmDryRun} className="btn-primary w-full">
                  Confirm {activeDryRun.action}
                </button>
              </div>
            ) : (
              <div className="mt-3 text-sm text-white/60">No active dry-run</div>
            )}
          </div>

          <div className="glass-panel rounded-[24px] p-5">
            <div className="section-kicker">Operations</div>
            <div className="mt-4 space-y-2">
              {operations.slice(0, 6).map((operation) => (
                <div key={operation.id} className="rounded-[16px] border border-white/8 bg-white/[0.03] p-3">
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="text-white">{operation.action}</span>
                    <StatusBadge label={operation.status} status={operation.status} />
                  </div>
                  <div className="mt-2 font-mono text-xs text-white/45">{shortId(operation.serial_before)}{' -> '}{shortId(operation.serial_after)}</div>
                  {operation.error_message && <div className="mt-2 text-xs text-[#ffbf8f]">{operation.error_message}</div>}
                </div>
              ))}
              {operations.length === 0 && <div className="text-sm text-white/60">No operations</div>}
            </div>
          </div>
        </aside>
      </section>
    </div>
  );
}

function Metric({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: number }) {
  return (
    <div className="rounded-[18px] border border-white/8 bg-white/[0.03] p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm text-white/55">{label}</span>
        <Icon size={17} className="text-white/45" />
      </div>
      <div className="mt-3 text-2xl font-semibold text-white">{value}</div>
    </div>
  );
}

function StatusBadge({ label, status }: { label: string; status: string }) {
  return (
    <span className={`inline-flex max-w-full items-center rounded-full border px-2.5 py-1 text-xs font-medium ${statusTone(status)}`}>
      <span className="truncate">{label}</span>
    </span>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-white/6 pb-2 last:border-0 last:pb-0">
      <span className="text-white/45">{label}</span>
      <span className="truncate text-right font-mono text-xs text-white/75">{value}</span>
    </div>
  );
}
