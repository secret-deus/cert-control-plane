import { Rocket, ShieldCheck } from 'lucide-react';
import { format, formatDistanceToNow } from 'date-fns';

interface ExternalCertDetail {
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
  cert_pem: string;
  chain_pem: string | null;
}

interface CertAssignment {
  id: string;
  agent_id: string;
  external_cert_id: string;
  local_path: string;
  created_at: string;
  agent_name: string;
  agent_liveness: 'online' | 'delayed' | 'offline';
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

interface CertDetailDrawerProps {
  selectedCert: ExternalCertDetail | null;
  selectedAssignments: CertAssignment[];
  isDetailLoading: boolean;
  detailError: string | null;
  agents: AgentSummary[];
  selectedAgentIds: Set<string>;
  onSelectedAgentIdsChange: (ids: Set<string>) => void;
  showDeploy: boolean;
  onShowDeployChange: (show: boolean) => void;
  deploying: boolean;
  deployResult: { success: number; failed: number } | null;
  onDeployResultChange: (result: { success: number; failed: number } | null) => void;
  onDeploy: () => void;
}

export default function CertDetailDrawer({
  selectedCert,
  selectedAssignments,
  isDetailLoading,
  detailError,
  agents,
  selectedAgentIds,
  onSelectedAgentIdsChange,
  showDeploy,
  onShowDeployChange,
  deploying,
  deployResult,
  onDeployResultChange,
  onDeploy,
}: CertDetailDrawerProps) {
  if (!selectedCert) {
    return (
      <aside className="glass-panel rounded-[24px] self-start p-5 xl:sticky xl:top-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="section-kicker">Certificate Drawer</div>
            <h3 className="mt-2 text-lg font-semibold text-white">证书详情抽屉</h3>
            <p className="mt-1 text-sm text-white/50">查看 PEM、绑定节点和密钥托管策略。</p>
          </div>
        </div>
        <div className="mt-6 rounded-lg border border-white/8 bg-white/[0.03] px-4 py-8 text-center text-sm text-white/50">从左侧选择一张证书查看详情。</div>
      </aside>
    );
  }

  return (
    <>
      <aside className="glass-panel rounded-[24px] self-start p-5 xl:sticky xl:top-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="section-kicker">Certificate Drawer</div>
            <h3 className="mt-2 text-lg font-semibold text-white">证书详情抽屉</h3>
            <p className="mt-1 text-sm text-white/50">查看 PEM、绑定节点和密钥托管策略。</p>
          </div>
          <span className="metric-badge border-white/8 bg-white/[0.03] text-white/80">{selectedAssignments.length} 节点</span>
        </div>

        {isDetailLoading ? (
          <div className="mt-6 space-y-3">
            <div className="skeleton h-6 rounded" />
            <div className="skeleton h-20 rounded" />
            <div className="skeleton h-32 rounded" />
          </div>
        ) : detailError ? (
          <div className="mt-6 rounded-[20px] border border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] p-4 text-sm text-[#ffbf8f]">{detailError}</div>
        ) : (
          <div className="mt-6 space-y-5">
            <div>
              <div className="text-xl font-semibold text-white">{selectedCert.subject_cn}</div>
              <div className="mt-1 text-sm text-white/70">{selectedCert.name}</div>
              <div className="mt-3 flex flex-wrap gap-2">
                <span className={`rounded-full border px-2 py-0.5 text-xs ${getCertHealth(getDaysRemaining(selectedCert.not_after), selectedCert.is_active).tone}`}>
                  {getCertHealth(getDaysRemaining(selectedCert.not_after), selectedCert.is_active).label}
                </span>
                <span className="rounded-full border border-white/8 bg-white/[0.03] px-2 py-0.5 text-xs text-white/80">
                  {providerLabels[selectedCert.provider || 'manual'] || selectedCert.provider || '手动上传'}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-[18px] border border-white/8 bg-white/[0.03] p-3">
                <div className="text-xs text-white/50">到期时间</div>
                <div className="mt-2 text-white">{format(new Date(selectedCert.not_after), 'yyyy-MM-dd HH:mm')}</div>
              </div>
              <div className="rounded-[18px] border border-white/8 bg-white/[0.03] p-3">
                <div className="text-xs text-white/50">更新于</div>
                <div className="mt-2 text-white">{formatDistanceToNow(new Date(selectedCert.updated_at), { addSuffix: true })}</div>
              </div>
              <div className="col-span-2 rounded-[18px] border border-white/8 bg-white/[0.03] p-3">
                <div className="text-xs text-white/50">序列号</div>
                <div className="mt-2 break-all font-mono text-xs text-white/85">{selectedCert.serial_hex}</div>
              </div>
            </div>

            <div>
              <div className="mb-3 flex items-center gap-2 text-sm font-medium text-white">
                <ShieldCheck size={15} className="text-[#ffbf8f]" />
                分发节点
              </div>
              {selectedAssignments.length === 0 ? (
                <div className="rounded-[18px] border border-white/8 bg-white/[0.03] px-4 py-6 text-sm text-white/50">当前还没有节点绑定这张证书。</div>
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
                          <div className="mt-1 break-all text-xs text-white/50">{assignment.local_path}</div>
                        </div>
                        <div className="text-xs text-white/50">{formatDistanceToNow(new Date(assignment.created_at), { addSuffix: true })}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={() => {
                onShowDeployChange(true);
                onDeployResultChange(null);
                onSelectedAgentIdsChange(new Set());
              }}
              className="flex w-full items-center justify-center gap-2 rounded-[18px] border border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] py-3 text-sm font-medium text-[#ffbf8f] transition hover:bg-[rgba(255,153,92,0.16)]"
            >
              <Rocket size={16} />
              一键部署到 Agent
            </button>

            <div className="rounded-[20px] border border-white/8 bg-white/[0.03] p-4">
              <div className="text-sm font-medium text-white">私钥策略</div>
              <p className="mt-2 text-sm leading-6 text-white/70">
                私钥由服务端使用 Fernet 加密托管，控制台只展示证书正文和链，不返回明文私钥。
              </p>
            </div>

            <div>
              <div className="mb-2 text-sm font-medium text-white">证书 PEM 预览</div>
              <pre className="overflow-x-auto rounded-lg border border-white/8 bg-white/[0.02] p-4 text-xs leading-6 text-white/80">
                {previewPem(selectedCert.cert_pem)}
              </pre>
            </div>

            {selectedCert.chain_pem && (
              <div>
                <div className="mb-2 text-sm font-medium text-white">证书链预览</div>
                <pre className="overflow-x-auto rounded-lg border border-white/8 bg-white/[0.02] p-4 text-xs leading-6 text-white/80">
                  {previewPem(selectedCert.chain_pem)}
                </pre>
              </div>
            )}
          </div>
        )}
      </aside>

      {showDeploy && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="glass-panel w-full max-w-lg rounded-[24px] p-6">
            <div className="flex items-center justify-between">
              <div>
                <div className="section-kicker">Deploy</div>
                <h3 className="mt-2 text-lg font-semibold text-white">一键部署证书</h3>
              </div>
              <button type="button" onClick={() => onShowDeployChange(false)} className="rounded-[16px] border border-white/8 p-2 text-white/70 hover:text-white">
                ✕
              </button>
            </div>

            <p className="mt-3 text-sm text-white/50">
              将 <span className="text-white">{selectedCert.subject_cn}</span> 部署到选中的 Agent，路径自动根据证书目录 + 域名生成。
            </p>

            <div className="mt-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs text-white/70">选择 Agent</span>
                <div className="flex gap-3">
                  <button type="button" onClick={() => onSelectedAgentIdsChange(new Set(agents.filter(a => a.status === 'active' && a.cert_paths?.length).map(a => a.id)))} className="text-xs text-[#ffbf8f] hover:underline">全选可用</button>
                  <button type="button" onClick={() => onSelectedAgentIdsChange(new Set())} className="text-xs text-white/50 hover:underline">清空</button>
                </div>
              </div>
              <div className="max-h-[280px] space-y-1.5 overflow-y-auto">
                {agents.filter(a => a.status === 'active').map((agent) => {
                  const hasPaths = !!agent.cert_paths?.length;
                  const baseDir = agent.cert_paths?.[0]?.replace(/\/[^/]+$/, '') || null;
                  const localPath = baseDir ? `${baseDir}/${selectedCert.subject_cn}.pem` : null;
                  const checked = selectedAgentIds.has(agent.id);

                  return (
                    <label key={agent.id} className={`flex cursor-pointer items-center gap-3 rounded-[14px] border border-white/4 px-3 py-2.5 transition hover:bg-white/[0.03] ${!hasPaths ? 'opacity-40' : ''}`}>
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={!hasPaths}
                        onChange={(e) => {
                          const next = new Set(selectedAgentIds);
                          if (e.target.checked) next.add(agent.id); else next.delete(agent.id);
                          onSelectedAgentIdsChange(next);
                        }}
                        className="h-4 w-4 rounded border-white/20 bg-transparent accent-[#ffbf8f]"
                      />
                      <span className={`h-2 w-2 shrink-0 rounded-full ${livenessTone[agent.liveness]}`} />
                      <div className="min-w-0 flex-1">
                        <div className="text-sm text-white">{agent.name}</div>
                        {hasPaths ? (
                          <div className="mt-0.5 truncate font-mono text-xs text-[#9adf90]">{localPath}</div>
                        ) : (
                          <div className="mt-0.5 text-xs text-white/30">未上报证书路径</div>
                        )}
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>

            {deployResult && (
              <div className={`mt-3 rounded-[14px] border p-3 text-sm ${deployResult.failed === 0 ? 'border-[rgba(115,191,105,0.18)] bg-[rgba(115,191,105,0.10)] text-[#9adf90]' : 'border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] text-[#ffbf8f]'}`}>
                部署完成：成功 {deployResult.success} 个，失败 {deployResult.failed} 个
              </div>
            )}

            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => onShowDeployChange(false)} className="btn-secondary">关闭</button>
              <button
                type="button"
                onClick={onDeploy}
                disabled={deploying || selectedAgentIds.size === 0}
                className="btn-primary flex items-center gap-1.5"
              >
                <Rocket size={14} />
                {deploying ? '部署中...' : `部署到 ${selectedAgentIds.size} 个 Agent`}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
