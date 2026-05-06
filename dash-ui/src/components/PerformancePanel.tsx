import { Activity, Cpu, Database } from 'lucide-react';
import type { ReactNode } from 'react';
import type { Copy } from '../i18n';
import type { HistoryPoint, Stats } from '../types';

const TIME_RANGES = [
  { label: '1m', seconds: 60 },
  { label: '5m', seconds: 300 },
  { label: '10m', seconds: 600 },
  { label: '30m', seconds: 1800 },
  { label: '1h', seconds: 3600 },
  { label: '4h', seconds: 14400 },
  { label: '12h', seconds: 43200 },
  { label: '1d', seconds: 86400 },
] as const;

type MetricKey = 'cpu' | 'ram' | 'ping';

interface MetricConfig {
  key: MetricKey;
  title: string;
  value: string;
  icon: ReactNode;
  color: string;
  unit: string;
  fixedMax?: number;
}

function round(value: number, digits = 1): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function getMetricValue(point: HistoryPoint, key: MetricKey): number {
  return point[key];
}

function downsample(points: HistoryPoint[], maxPoints: number): HistoryPoint[] {
  if (points.length <= maxPoints) return points;

  const step = points.length / maxPoints;
  const result: HistoryPoint[] = [];
  for (let i = 0; i < maxPoints; i += 1) {
    const start = Math.floor(i * step);
    const end = i === maxPoints - 1 ? points.length : Math.max(start + 1, Math.floor((i + 1) * step));
    const bucket = points.slice(start, end);
    result.push({
      t: bucket[bucket.length - 1].t,
      cpu: round(bucket.reduce((sum, point) => sum + point.cpu, 0) / bucket.length),
      ram: round(bucket.reduce((sum, point) => sum + point.ram, 0) / bucket.length),
      ping: Math.round(bucket.reduce((sum, point) => sum + point.ping, 0) / bucket.length),
    });
  }
  return result;
}

function formatTimeLabel(timestamp: number, includeSeconds: boolean): string {
  return new Date(timestamp * 1000).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: includeSeconds ? '2-digit' : undefined,
  });
}

function summarize(points: HistoryPoint[], key: MetricKey) {
  const values = points.map((point) => getMetricValue(point, key));
  const current = values[values.length - 1] ?? 0;
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 0;
  const avg = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
  return {
    current,
    min: round(min),
    max: round(max),
    avg: round(avg),
  };
}

function ChartCard({
  metric,
  points,
  timeRange,
  t,
}: {
  metric: MetricConfig;
  points: HistoryPoint[];
  timeRange: number;
  t: Copy;
}) {
  const chartPoints = downsample(points, 240);
  const stats = summarize(chartPoints, metric.key);

  if (chartPoints.length < 2) {
    return (
      <div className="rounded-lg border border-panel bg-surface p-4">
        <ChartHeader metric={metric} />
        <div className="mt-3 flex h-44 items-center justify-center rounded-md border border-panel bg-app text-xs text-muted">{t.collecting}</div>
      </div>
    );
  }

  const width = 420;
  const height = 178;
  const pad = { top: 12, right: 12, bottom: 28, left: 42 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const values = chartPoints.map((point) => getMetricValue(point, metric.key));
  const maxObserved = Math.max(...values);
  const domainMax = metric.fixedMax ?? Math.max(1, Math.ceil(maxObserved * 1.18));
  const y = (value: number) => pad.top + plotHeight - (Math.min(value, domainMax) / domainMax) * plotHeight;
  const x = (index: number) => pad.left + (index / (chartPoints.length - 1)) * plotWidth;
  const path = chartPoints.map((point, index) => `${index === 0 ? 'M' : 'L'}${x(index)},${y(getMetricValue(point, metric.key))}`).join(' ');
  const area = `${path} L${x(chartPoints.length - 1)},${height - pad.bottom} L${pad.left},${height - pad.bottom} Z`;
  const gradientId = `metric-fill-${metric.key}`;
  const startLabel = formatTimeLabel(chartPoints[0].t, timeRange <= 600);
  const endLabel = formatTimeLabel(chartPoints[chartPoints.length - 1].t, timeRange <= 600);
  const midValue = round(domainMax / 2);
  const currentX = x(chartPoints.length - 1);
  const currentY = y(values[values.length - 1]);

  return (
    <div className="rounded-lg border border-panel bg-surface p-4">
      <ChartHeader metric={metric} />
      <div className="mt-3 rounded-md border border-panel bg-app p-2">
        <svg viewBox={`0 0 ${width} ${height}`} className="aspect-[420/178] w-full" aria-hidden="true">
          <defs>
            <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={metric.color} stopOpacity="0.26" />
              <stop offset="100%" stopColor={metric.color} stopOpacity="0.02" />
            </linearGradient>
          </defs>
          {[0, 0.5, 1].map((line) => {
            const lineY = pad.top + line * plotHeight;
            return <line key={line} x1={pad.left} x2={width - pad.right} y1={lineY} y2={lineY} stroke="#293144" strokeWidth="1" />;
          })}
          <line x1={pad.left} x2={pad.left} y1={pad.top} y2={height - pad.bottom} stroke="#293144" strokeWidth="1" />
          <line x1={pad.left} x2={width - pad.right} y1={height - pad.bottom} y2={height - pad.bottom} stroke="#293144" strokeWidth="1" />
          <path d={area} fill={`url(#${gradientId})`} />
          <path d={path} fill="none" stroke={metric.color} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" vectorEffect="non-scaling-stroke" />
          <circle cx={currentX} cy={currentY} r="3.5" fill={metric.color} />
          <text x="4" y={pad.top + 4} fill="#8d97ad" fontSize="10">
            {domainMax}
            {metric.unit}
          </text>
          <text x="4" y={pad.top + plotHeight / 2 + 4} fill="#8d97ad" fontSize="10">
            {midValue}
            {metric.unit}
          </text>
          <text x="4" y={height - pad.bottom + 4} fill="#8d97ad" fontSize="10">
            0{metric.unit}
          </text>
          <text x={pad.left} y={height - 8} fill="#8d97ad" fontSize="10">
            {startLabel}
          </text>
          <text x={width - pad.right} y={height - 8} fill="#8d97ad" fontSize="10" textAnchor="end">
            {endLabel}
          </text>
        </svg>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <Stat label={t.current} value={`${stats.current}${metric.unit}`} />
        <Stat label={t.average} value={`${stats.avg}${metric.unit}`} />
        <Stat label={t.maximum} value={`${stats.max}${metric.unit}`} />
        <Stat label={t.samples} value={String(points.length)} />
      </div>
    </div>
  );
}

function ChartHeader({ metric }: { metric: MetricConfig }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-white">
        <span style={{ color: metric.color }}>{metric.icon}</span>
        <span className="truncate">{metric.title}</span>
      </div>
      <span className="font-mono text-sm text-white">{metric.value}</span>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-panel bg-app px-2 py-1.5">
      <div className="truncate text-[11px] uppercase text-muted">{label}</div>
      <div className="truncate font-mono text-xs text-white">{value}</div>
    </div>
  );
}

export function PerformancePanel({
  history,
  timeRange,
  stats,
  t,
  onRangeChange,
}: {
  history: HistoryPoint[];
  timeRange: number;
  stats: Stats | null;
  t: Copy;
  onRangeChange: (range: number) => void;
}) {
  const latest = history[history.length - 1]?.t ?? stats?.sampled_at ?? 0;
  const visible = history.filter((point) => point.t >= latest - timeRange);
  const metrics: MetricConfig[] = [
    {
      key: 'cpu',
      title: t.cpu,
      value: stats?.cpu_usage !== undefined ? `${round(stats.cpu_usage)}%` : '...',
      icon: <Cpu className="h-4 w-4" />,
      color: '#8ea0ff',
      unit: '%',
      fixedMax: 100,
    },
    {
      key: 'ram',
      title: t.ram,
      value: stats?.ram_usage_mb !== undefined ? `${stats.ram_usage_mb} MB` : '...',
      icon: <Database className="h-4 w-4" />,
      color: '#1ed39a',
      unit: ' MB',
    },
    {
      key: 'ping',
      title: t.ping,
      value: stats?.ping !== undefined ? `${stats.ping}ms` : '...',
      icon: <Activity className="h-4 w-4" />,
      color: '#ff7676',
      unit: 'ms',
    },
  ];

  return (
    <section className="rounded-lg border border-panel bg-surface p-4 shadow-panel">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-white">{t.performance}</h2>
          <p className="text-xs text-muted">{t.range}</p>
        </div>
        <div className="flex max-w-full gap-1 overflow-x-auto rounded-md border border-panel bg-app p-1">
          {TIME_RANGES.map((range) => (
            <button
              key={range.seconds}
              type="button"
              onClick={() => onRangeChange(range.seconds)}
              className={`rounded px-2.5 py-1 text-xs font-semibold transition ${
                timeRange === range.seconds ? 'bg-accent text-white' : 'text-muted hover:bg-panel hover:text-white'
              }`}
            >
              {range.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        {metrics.map((metric) => (
          <ChartCard key={metric.key} metric={metric} points={visible} timeRange={timeRange} t={t} />
        ))}
      </div>
    </section>
  );
}
