import { Search } from 'lucide-react';

type FilterStatus = 'all' | 'healthy' | 'warning' | 'critical' | 'inactive';

interface CertFiltersProps {
  search: string;
  onSearchChange: (value: string) => void;
  statusFilter: FilterStatus;
  onStatusFilterChange: (status: FilterStatus) => void;
}

const statusOptions: Array<[FilterStatus, string]> = [
  ['all', '全部'],
  ['healthy', '健康'],
  ['warning', '30 天内'],
  ['critical', '7 天内'],
  ['inactive', '未启用'],
];

export default function CertFilters({
  search,
  onSearchChange,
  statusFilter,
  onStatusFilterChange,
}: CertFiltersProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-1 flex-wrap items-center gap-3">
        <label className="relative min-w-[260px] flex-1 max-w-md">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/50" />
          <input
            className="input-field pl-9"
            placeholder="搜索域名、证书名或序列号"
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </label>
        <div className="flex flex-wrap gap-2">
          {statusOptions.map(([status, label]) => (
            <button
              key={status}
              type="button"
              onClick={() => onStatusFilterChange(status)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                statusFilter === status
                  ? 'border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] text-[#ffbf8f]'
                  : 'border-white/8 bg-white/[0.03] text-white/70 hover:text-white'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}