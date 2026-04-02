import { useState, useEffect, useCallback } from 'react';
import { UploadCloud, AlertCircle, CheckCircle, Shield, ChevronDown, ChevronUp, Link, Trash2 } from 'lucide-react';
import { apiFetch, apiPost, apiPostForm, apiDelete } from '../lib/api';

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
}

interface Agent {
  id: string;
  name: string;
  status: string;
}

interface Assignment {
  id: string;
  agent_id: string;
  external_cert_id: string;
  local_path: string;
  created_at: string;
}

interface PaginatedResponse<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}

export default function ExternalCertsPage() {
  const [certs, setCerts] = useState<ExternalCert[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showUploadForm, setShowUploadForm] = useState(false);
  const [expandedCert, setExpandedCert] = useState<string | null>(null);

  // Assignments per cert (loaded lazily when cert is expanded)
  const [assignmentsMap, setAssignmentsMap] = useState<Record<string, Assignment[]>>({});

  // Upload form state
  const [uploadForm, setUploadForm] = useState({
    name: '',
    description: '',
    cert_pem: '',
    key_pem: '',
    chain_pem: '',
    provider: 'aliyun',
  });
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  const [uploadMode, setUploadMode] = useState<'pem' | 'archive'>('pem');
  const [archiveFile, setArchiveFile] = useState<File | null>(null);

  // Assign form state (per expanded cert)
  const [assignAgentId, setAssignAgentId] = useState('');
  const [assignLocalPath, setAssignLocalPath] = useState('');
  const [assigning, setAssigning] = useState(false);
  const [assignError, setAssignError] = useState<string | null>(null);
  const [assignSuccess, setAssignSuccess] = useState(false);
  const [deletingCertId, setDeletingCertId] = useState<string | null>(null);

  const fetchCerts = useCallback(async () => {
    try {
      const data = await apiFetch<PaginatedResponse<ExternalCert>>('/external-certs?limit=100');
      setCerts(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch certificates');
    }
  }, []);

  const fetchAgents = useCallback(async () => {
    try {
      const data = await apiFetch<PaginatedResponse<Agent>>('/agents?limit=1000');
      setAgents(data.items.filter(a => a.status === 'active'));
    } catch (err) {
      console.error('Failed to fetch agents:', err);
    }
  }, []);

  useEffect(() => {
    Promise.all([fetchCerts(), fetchAgents()]).finally(() => setLoading(false));
  }, [fetchCerts, fetchAgents]);

  // Load assignments for an agent that has this cert assigned
  // We load per-cert assignments by asking each agent, but since the backend
  // only exposes GET /agents/{id}/assignments, we load them per-agent on expand.
  // For simplicity, we load ALL agent assignments and filter.
  const loadAssignmentsForCert = useCallback(async (certId: string) => {
    try {
      const all: Assignment[] = [];
      for (const agent of agents) {
        const data = await apiFetch<Assignment[]>(`/agents/${agent.id}/assignments`).catch(() => []);
        const filtered = data.filter(a => a.external_cert_id === certId);
        all.push(...filtered);
      }
      setAssignmentsMap(prev => ({ ...prev, [certId]: all }));
    } catch (err) {
      console.error('Failed to load assignments:', err);
    }
  }, [agents]);

  const handleExpand = (certId: string) => {
    if (expandedCert === certId) {
      setExpandedCert(null);
    } else {
      setExpandedCert(certId);
      setAssignAgentId('');
      setAssignLocalPath('');
      setAssignError(null);
      setAssignSuccess(false);
      loadAssignmentsForCert(certId);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    setUploading(true);
    setUploadError(null);
    setUploadSuccess(false);

    try {
      if (uploadMode === 'archive') {
        if (!archiveFile) {
          throw new Error('Please choose a zip archive');
        }
        const formData = new FormData();
        formData.append('archive', archiveFile);
        formData.append('name', uploadForm.name.trim());
        formData.append('description', uploadForm.description.trim());
        formData.append('provider', uploadForm.provider);
        await apiPostForm('/external-certs/upload-archive', formData);
      } else {
        await apiPost('/external-certs', uploadForm);
      }
      setUploadSuccess(true);
      setUploadForm({ name: '', description: '', cert_pem: '', key_pem: '', chain_pem: '', provider: 'aliyun' });
      setArchiveFile(null);
      setUploadMode('pem');
      await fetchCerts();
      setTimeout(() => { setShowUploadForm(false); setUploadSuccess(false); }, 2000);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const handleAssign = async (certId: string) => {
    if (!assignAgentId) { setAssignError('Please select an agent'); return; }
    if (!assignLocalPath.trim()) { setAssignError('Please enter a local path'); return; }

    setAssigning(true);
    setAssignError(null);
    setAssignSuccess(false);

    try {
      await apiPost(`/agents/${assignAgentId}/assign-cert`, {
        external_cert_id: certId,
        local_path: assignLocalPath.trim(),
      });
      setAssignSuccess(true);
      setAssignLocalPath('');
      setAssignAgentId('');
      loadAssignmentsForCert(certId);
      setTimeout(() => setAssignSuccess(false), 3000);
    } catch (err) {
      setAssignError(err instanceof Error ? err.message : 'Assignment failed');
    } finally {
      setAssigning(false);
    }
  };

  const handleDeleteAssignment = async (agentId: string, assignmentId: string, certId: string) => {
    if (!confirm('Remove this assignment?')) return;
    try {
      await apiDelete(`/agents/${agentId}/assignments/${assignmentId}`);
      loadAssignmentsForCert(certId);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Delete failed');
    }
  };

  const handleDeleteCert = async (certId: string, certName: string, assignmentCount: number) => {
    const warning = assignmentCount > 0
      ? `Delete "${certName}" and remove ${assignmentCount} assignment(s)?`
      : `Delete "${certName}"?`;
    if (!confirm(warning)) return;

    setDeletingCertId(certId);
    try {
      await apiDelete(`/external-certs/${certId}`);
      setAssignmentsMap(prev => {
        const next = { ...prev };
        delete next[certId];
        return next;
      });
      if (expandedCert === certId) {
        setExpandedCert(null);
      }
      await fetchCerts();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setDeletingCertId(null);
    }
  };

  const getDaysRemaining = (notAfter: string) => {
    return Math.ceil((new Date(notAfter).getTime() - Date.now()) / (1000 * 60 * 60 * 24));
  };

  const getUrgencyColor = (days: number) => {
    if (days < 0) return 'text-red-500';
    if (days <= 7) return 'text-red-400';
    if (days <= 14) return 'text-yellow-400';
    if (days <= 30) return 'text-blue-400';
    return 'text-green-400';
  };

  const agentNameById = (id: string) => agents.find(a => a.id === id)?.name ?? id;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--color-accent-blue)]"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">External Certificates</h1>
          <p className="text-sm text-[var(--color-text-secondary)] mt-1">
            Upload certificates from external providers and assign them to agent paths.
          </p>
        </div>
        <button
          onClick={() => setShowUploadForm(!showUploadForm)}
          className="flex items-center gap-2 px-4 py-2 bg-[var(--color-accent-blue)] hover:bg-[var(--color-accent-blue)]/80 text-white rounded-lg transition-colors"
        >
          <UploadCloud size={18} />
          {showUploadForm ? 'Cancel' : 'Upload Certificate'}
        </button>
      </div>

      {error && (
        <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 flex items-center gap-2">
          <AlertCircle size={18} /> {error}
        </div>
      )}

      {/* Upload Form */}
      {showUploadForm && (
        <div className="glass-panel rounded-xl p-6">
          <h2 className="text-lg font-medium text-white mb-4">Upload New Certificate</h2>

          {uploadSuccess && (
            <div className="mb-4 p-3 rounded-lg bg-green-500/10 border border-green-500/20 text-green-400 flex items-center gap-2">
              <CheckCircle size={18} /> Certificate uploaded successfully!
            </div>
          )}
          {uploadError && (
            <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 flex items-center gap-2">
              <AlertCircle size={18} /> {uploadError}
            </div>
          )}

          <form onSubmit={handleUpload} className="space-y-4">
            <div>
              <label className="block text-sm text-[var(--color-text-secondary)] mb-2">Upload Mode</label>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setUploadMode('pem')}
                  className={`px-3 py-2 rounded-lg text-sm transition-colors ${uploadMode === 'pem'
                    ? 'bg-[var(--color-accent-blue)] text-white'
                    : 'border border-[var(--color-border-subtle)] text-[var(--color-text-secondary)] hover:text-white'}`}
                >
                  Paste PEM
                </button>
                <button
                  type="button"
                  onClick={() => setUploadMode('archive')}
                  className={`px-3 py-2 rounded-lg text-sm transition-colors ${uploadMode === 'archive'
                    ? 'bg-[var(--color-accent-blue)] text-white'
                    : 'border border-[var(--color-border-subtle)] text-[var(--color-text-secondary)] hover:text-white'}`}
                >
                  Upload ZIP
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-[var(--color-text-secondary)] mb-1">Name *</label>
                <input
                  type="text"
                  value={uploadForm.name}
                  onChange={e => setUploadForm({ ...uploadForm, name: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-[rgba(255,255,255,0.05)] border border-[var(--color-border-subtle)] text-white focus:outline-none focus:border-[var(--color-accent-blue)]"
                  placeholder="e.g. prod-api-cert"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-[var(--color-text-secondary)] mb-1">Provider</label>
                <select
                  value={uploadForm.provider}
                  onChange={e => setUploadForm({ ...uploadForm, provider: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-[rgba(255,255,255,0.05)] border border-[var(--color-border-subtle)] text-white focus:outline-none focus:border-[var(--color-accent-blue)]"
                >
                  <option value="aliyun">阿里云 (Aliyun)</option>
                  <option value="letsencrypt">Let's Encrypt</option>
                  <option value="digicert">DigiCert</option>
                  <option value="sectigo">Sectigo</option>
                  <option value="other">Other</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-sm text-[var(--color-text-secondary)] mb-1">Description</label>
              <input
                type="text"
                value={uploadForm.description}
                onChange={e => setUploadForm({ ...uploadForm, description: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-[rgba(255,255,255,0.05)] border border-[var(--color-border-subtle)] text-white focus:outline-none focus:border-[var(--color-accent-blue)]"
                placeholder="Optional description"
              />
            </div>

            {uploadMode === 'pem' ? (
              <>
                <div>
                  <label className="block text-sm text-[var(--color-text-secondary)] mb-1">Certificate PEM *</label>
                  <textarea
                    value={uploadForm.cert_pem}
                    onChange={e => setUploadForm({ ...uploadForm, cert_pem: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-[rgba(255,255,255,0.05)] border border-[var(--color-border-subtle)] text-white focus:outline-none focus:border-[var(--color-accent-blue)] font-mono text-xs"
                    rows={4}
                    placeholder="-----BEGIN CERTIFICATE-----&#10;..."
                    required={uploadMode === 'pem'}
                  />
                </div>

                <div>
                  <label className="block text-sm text-[var(--color-text-secondary)] mb-1">Private Key PEM *</label>
                  <textarea
                    value={uploadForm.key_pem}
                    onChange={e => setUploadForm({ ...uploadForm, key_pem: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-[rgba(255,255,255,0.05)] border border-[var(--color-border-subtle)] text-white focus:outline-none focus:border-[var(--color-accent-blue)] font-mono text-xs"
                    rows={4}
                    placeholder="-----BEGIN PRIVATE KEY-----&#10;..."
                    required={uploadMode === 'pem'}
                  />
                  <p className="text-xs text-[var(--color-text-secondary)] mt-1">Encrypted before storage</p>
                </div>

                <div>
                  <label className="block text-sm text-[var(--color-text-secondary)] mb-1">Certificate Chain (Optional)</label>
                  <textarea
                    value={uploadForm.chain_pem}
                    onChange={e => setUploadForm({ ...uploadForm, chain_pem: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-[rgba(255,255,255,0.05)] border border-[var(--color-border-subtle)] text-white focus:outline-none focus:border-[var(--color-accent-blue)] font-mono text-xs"
                    rows={3}
                    placeholder="-----BEGIN CERTIFICATE-----&#10;... (Intermediate/Root CA chain)"
                  />
                </div>
              </>
            ) : (
              <div>
                <label className="block text-sm text-[var(--color-text-secondary)] mb-1">ZIP Archive *</label>
                <input
                  type="file"
                  accept=".zip,application/zip"
                  onChange={e => {
                    const file = e.target.files?.[0] || null;
                    setArchiveFile(file);
                    if (file && !uploadForm.name.trim()) {
                      setUploadForm({
                        ...uploadForm,
                        name: file.name.replace(/\.zip$/i, ''),
                      });
                    }
                  }}
                  className="block w-full text-sm text-[var(--color-text-secondary)] file:mr-4 file:rounded-lg file:border-0 file:bg-[var(--color-accent-blue)] file:px-4 file:py-2 file:text-white hover:file:bg-[var(--color-accent-blue)]/80"
                  required={uploadMode === 'archive'}
                />
                <p className="text-xs text-[var(--color-text-secondary)] mt-2">
                  Supports provider-exported zip packages containing certificate, private key, and optional chain.
                </p>
              </div>
            )}

            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  setShowUploadForm(false);
                  setArchiveFile(null);
                }}
                className="px-4 py-2 rounded-lg border border-[var(--color-border-subtle)] text-[var(--color-text-secondary)] hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={uploading}
                className="px-4 py-2 rounded-lg bg-[var(--color-accent-blue)] hover:bg-[var(--color-accent-blue)]/80 text-white transition-colors disabled:opacity-50"
              >
                {uploading ? 'Uploading…' : 'Upload Certificate'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Certificates List */}
      <div className="space-y-4">
        {certs.length === 0 ? (
          <div className="glass-panel rounded-xl p-8 text-center text-[var(--color-text-secondary)]">
            <UploadCloud size={48} className="mx-auto mb-4 opacity-50" />
            <p>No external certificates uploaded yet</p>
            <p className="text-sm mt-1">Click "Upload Certificate" to add one</p>
          </div>
        ) : (
          certs.map(cert => {
            const daysRemaining = getDaysRemaining(cert.not_after);
            const isExpanded = expandedCert === cert.id;
            const certAssignments = assignmentsMap[cert.id] ?? [];

            return (
              <div key={cert.id} className="glass-panel rounded-xl overflow-hidden">
                {/* Cert summary row */}
                <div
                  className="p-4 flex items-center justify-between cursor-pointer hover:bg-[rgba(255,255,255,0.02)] transition-colors"
                  onClick={() => handleExpand(cert.id)}
                >
                  <div className="flex items-center gap-4">
                    <Shield size={20} className={getUrgencyColor(daysRemaining)} />
                    <div>
                      <h3 className="font-medium text-white">{cert.name}</h3>
                      <p className="text-sm text-[var(--color-text-secondary)]">
                        {cert.subject_cn} • {cert.provider || 'Unknown provider'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <div className={`text-sm font-medium ${getUrgencyColor(daysRemaining)}`}>
                        {daysRemaining < 0 ? 'Expired' : `${daysRemaining} days left`}
                      </div>
                      <div className="text-xs text-[var(--color-text-secondary)]">
                        Expires: {new Date(cert.not_after).toLocaleDateString()}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={e => {
                        e.stopPropagation();
                        void handleDeleteCert(cert.id, cert.name, certAssignments.length);
                      }}
                      disabled={deletingCertId === cert.id}
                      className="p-2 rounded-lg text-[var(--color-text-secondary)] hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-50"
                      title="Delete certificate"
                    >
                      <Trash2 size={16} />
                    </button>
                    {isExpanded
                      ? <ChevronUp size={20} className="text-[var(--color-text-secondary)]" />
                      : <ChevronDown size={20} className="text-[var(--color-text-secondary)]" />
                    }
                  </div>
                </div>

                {/* Expanded details */}
                {isExpanded && (
                  <div className="border-t border-[var(--color-border-subtle)] p-4 space-y-6">
                    {/* Cert metadata */}
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-[var(--color-text-secondary)]">Serial:</span>
                        <span className="ml-2 text-white font-mono">{cert.serial_hex}</span>
                      </div>
                      <div>
                        <span className="text-[var(--color-text-secondary)]">Status:</span>
                        <span className={`ml-2 ${cert.is_active ? 'text-green-400' : 'text-red-400'}`}>
                          {cert.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </div>
                      <div>
                        <span className="text-[var(--color-text-secondary)]">Valid From:</span>
                        <span className="ml-2 text-white">{new Date(cert.not_before).toLocaleDateString()}</span>
                      </div>
                    </div>

                    {/* Current assignments */}
                    <div>
                      <h4 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
                        <Link size={16} />
                        Current Assignments
                      </h4>
                      {certAssignments.length === 0 ? (
                        <p className="text-sm text-[var(--color-text-secondary)]">
                          No agents assigned to this certificate yet.
                        </p>
                      ) : (
                        <div className="space-y-2">
                          {certAssignments.map(asn => (
                            <div
                              key={asn.id}
                              className="flex items-center justify-between p-2 rounded-lg bg-[rgba(255,255,255,0.03)] text-sm"
                            >
                              <div>
                                <span className="text-white font-medium">{agentNameById(asn.agent_id)}</span>
                                <span className="mx-2 text-[var(--color-text-secondary)]">→</span>
                                <span className="font-mono text-xs text-[var(--color-text-secondary)]">{asn.local_path}</span>
                              </div>
                              <button
                                onClick={() => handleDeleteAssignment(asn.agent_id, asn.id, cert.id)}
                                className="p-1 text-[var(--color-text-secondary)] hover:text-red-400 transition-colors"
                                title="Remove assignment"
                              >
                                <Trash2 size={14} />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Assign form */}
                    <div className="border-t border-[var(--color-border-subtle)] pt-4">
                      <h4 className="text-sm font-medium text-white mb-3">Assign to Agent</h4>

                      {assignSuccess && (
                        <div className="mb-3 p-3 rounded-lg bg-green-500/10 border border-green-500/20 text-green-400 text-sm flex items-center gap-2">
                          <CheckCircle size={16} /> Assignment created successfully
                        </div>
                      )}
                      {assignError && (
                        <div className="mb-3 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center gap-2">
                          <AlertCircle size={16} /> {assignError}
                        </div>
                      )}

                      {agents.length === 0 ? (
                        <p className="text-sm text-[var(--color-text-secondary)]">No active agents available.</p>
                      ) : (
                        <div className="flex flex-col sm:flex-row gap-3">
                          <select
                            value={assignAgentId}
                            onChange={e => setAssignAgentId(e.target.value)}
                            className="flex-1 px-3 py-2 rounded-lg bg-[rgba(255,255,255,0.05)] border border-[var(--color-border-subtle)] text-white focus:outline-none focus:border-[var(--color-accent-blue)] text-sm"
                          >
                            <option value="">Select agent…</option>
                            {agents.map(a => (
                              <option key={a.id} value={a.id}>{a.name}</option>
                            ))}
                          </select>

                          <input
                            type="text"
                            value={assignLocalPath}
                            onChange={e => setAssignLocalPath(e.target.value)}
                            placeholder="/etc/nginx/ssl/api.example.com.crt"
                            className="flex-[2] px-3 py-2 rounded-lg bg-[rgba(255,255,255,0.05)] border border-[var(--color-border-subtle)] text-white focus:outline-none focus:border-[var(--color-accent-blue)] text-sm font-mono"
                          />

                          <button
                            onClick={() => handleAssign(cert.id)}
                            disabled={assigning}
                            className="px-4 py-2 rounded-lg bg-[var(--color-accent-blue)] hover:bg-[var(--color-accent-blue)]/80 text-white text-sm transition-colors disabled:opacity-50 whitespace-nowrap"
                          >
                            {assigning ? 'Assigning…' : 'Assign Path'}
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
