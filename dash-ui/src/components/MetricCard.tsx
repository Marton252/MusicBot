import type { ReactNode } from 'react';

interface MetricCardProps {
  icon: ReactNode;
  label: string;
  value?: string | number;
}

export function MetricCard({ icon, label, value }: MetricCardProps) {
  return (
    <div className="grid min-h-28 grid-cols-[auto_1fr] items-center gap-4 rounded-lg border border-panel bg-surface p-4 shadow-panel">
      <div className="flex h-10 w-10 items-center justify-center rounded-md border border-panel bg-app text-accent">{icon}</div>
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-muted">{label}</p>
        <p className="mt-1 truncate text-2xl font-semibold text-white">{value ?? '...'}</p>
      </div>
    </div>
  );
}
