import type { ReactNode } from 'react';

interface MetricCardProps {
  icon: ReactNode;
  label: string;
  value?: string | number;
}

export function MetricCard({ icon, label, value }: MetricCardProps) {
  return (
    <div className="grid min-h-28 min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-3 rounded-lg border border-panel bg-surface p-3 shadow-panel sm:gap-4 sm:p-4">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-panel bg-app text-accent">{icon}</div>
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-muted">{label}</p>
        <p className="mt-1 truncate text-xl font-semibold text-white sm:text-2xl">{value ?? '...'}</p>
      </div>
    </div>
  );
}
