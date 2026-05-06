import { Activity, Cpu, Database, Maximize2, X } from 'lucide-react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import type { MouseEvent, PointerEvent, ReactNode, TouchEvent } from 'react';
import { useEffect, useState } from 'react';
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
type ChartSize = 'compact' | 'large';

interface MetricConfig {
  key: MetricKey;
  title: string;
  value: string;
  icon: ReactNode;
  color: string;
  unit: string;
  fixedMax?: number;
}

interface ChartGeometry {
  width: number;
  height: number;
  pad: { top: number; right: number; bottom: number; left: number };
}

function round(value: number, digits = 1): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function getMetricValue(point: HistoryPoint, key: MetricKey): number {
  return point[key];
}

function metricDigits(key: MetricKey): number {
  return key === 'ram' ? 0 : 1;
}

function formatMetricValue(metric: Pick<MetricConfig, 'key' | 'unit'>, value: number): string {
  return `${round(value, metricDigits(metric.key))}${metric.unit}`;
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
    current: round(current, metricDigits(key)),
    min: round(min, metricDigits(key)),
    max: round(max, metricDigits(key)),
    avg: round(avg, metricDigits(key)),
  };
}

function chartGeometry(size: ChartSize): ChartGeometry {
  return size === 'large'
    ? { width: 760, height: 320, pad: { top: 18, right: 18, bottom: 36, left: 54 } }
    : { width: 420, height: 178, pad: { top: 12, right: 12, bottom: 28, left: 42 } };
}

function ChartGraphic({
  metric,
  points,
  timeRange,
  size,
  t,
}: {
  metric: MetricConfig;
  points: HistoryPoint[];
  timeRange: number;
  size: ChartSize;
  t: Copy;
}) {
  const reduceMotion = useReducedMotion();
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const geometry = chartGeometry(size);
  const { width, height, pad } = geometry;
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const values = points.map((point) => getMetricValue(point, metric.key));
  const maxObserved = Math.max(...values);
  const domainMax = metric.fixedMax ?? Math.max(1, Math.ceil(maxObserved * 1.18));
  const y = (value: number) => pad.top + plotHeight - (Math.min(value, domainMax) / domainMax) * plotHeight;
  const x = (index: number) => pad.left + (index / (points.length - 1)) * plotWidth;
  const path = points.map((point, index) => `${index === 0 ? 'M' : 'L'}${x(index)},${y(getMetricValue(point, metric.key))}`).join(' ');
  const area = `${path} L${x(points.length - 1)},${height - pad.bottom} L${pad.left},${height - pad.bottom} Z`;
  const gradientId = `metric-fill-${metric.key}-${size}`;
  const startLabel = formatTimeLabel(points[0].t, timeRange <= 600);
  const endLabel = formatTimeLabel(points[points.length - 1].t, timeRange <= 600);
  const midValue = round(domainMax / 2);
  const activeIndex = hoverIndex ?? points.length - 1;
  const activePoint = points[activeIndex];
  const activeX = x(activeIndex);
  const activeY = y(getMetricValue(activePoint, metric.key));
  const tooltipAbove = activeY > height * 0.36;
  const showGuide = hoverIndex !== null;
  const tooltipX = clamp((activeX / width) * 100, 4, 96);
  const tooltipY = clamp((activeY / height) * 100, 8, 92);
  const horizontalClass =
    activeX < width * 0.32 ? '' : activeX > width * 0.68 ? '-translate-x-full' : '-translate-x-1/2';
  const verticalClass = tooltipAbove ? '-translate-y-[calc(100%+0.5rem)]' : 'translate-y-2';

  const updateHoverFromClientX = (target: SVGSVGElement, clientX: number) => {
    const rect = target.getBoundingClientRect();
    const svgX = ((clientX - rect.left) / rect.width) * width;
    const ratio = clamp((svgX - pad.left) / plotWidth, 0, 1);
    setHoverIndex(Math.round(ratio * (points.length - 1)));
  };

  const updateHover = (event: PointerEvent<SVGSVGElement>) => {
    updateHoverFromClientX(event.currentTarget, event.clientX);
  };

  const updateClick = (event: MouseEvent<SVGSVGElement>) => {
    updateHoverFromClientX(event.currentTarget, event.clientX);
  };

  const updateTouch = (event: TouchEvent<SVGSVGElement>) => {
    const touch = event.touches[0] ?? event.changedTouches[0];
    if (!touch) return;
    updateHoverFromClientX(event.currentTarget, touch.clientX);
  };

  return (
    <div className="relative min-w-0 rounded-md border border-panel bg-app p-2">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className={`${size === 'large' ? 'aspect-[760/320]' : 'aspect-[420/178]'} w-full cursor-crosshair touch-none`}
        aria-label={`${metric.title} ${t.chartDetails}`}
        role="img"
        onPointerDown={updateHover}
        onPointerMove={updateHover}
        onPointerLeave={() => setHoverIndex(null)}
        onPointerCancel={() => setHoverIndex(null)}
        onTouchStart={updateTouch}
        onTouchMove={updateTouch}
        onTouchEnd={updateTouch}
        onClick={updateClick}
      >
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
        <motion.path
          d={path}
          fill="none"
          stroke={metric.color}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={size === 'large' ? '2.6' : '2.2'}
          vectorEffect="non-scaling-stroke"
          initial={reduceMotion ? false : { pathLength: 0, opacity: 0.65 }}
          animate={reduceMotion ? undefined : { pathLength: 1, opacity: 1 }}
          transition={{ duration: 0.42, ease: 'easeOut' }}
        />
        {showGuide ? (
          <line
            x1={activeX}
            x2={activeX}
            y1={pad.top}
            y2={height - pad.bottom}
            stroke={metric.color}
            strokeDasharray="4 4"
            strokeOpacity="0.45"
          />
        ) : null}
        <circle cx={activeX} cy={activeY} r={size === 'large' ? 4.5 : 3.5} fill={metric.color} stroke="#0b0d12" strokeWidth="2" />
        <text x="4" y={pad.top + 4} fill="#8d97ad" fontSize={size === 'large' ? '11' : '9'}>
          {domainMax}
          {metric.unit}
        </text>
        <text x="4" y={pad.top + plotHeight / 2 + 4} fill="#8d97ad" fontSize={size === 'large' ? '11' : '9'}>
          {midValue}
          {metric.unit}
        </text>
        <text x="4" y={height - pad.bottom + 4} fill="#8d97ad" fontSize={size === 'large' ? '11' : '9'}>
          0{metric.unit}
        </text>
        <text x={pad.left} y={height - 8} fill="#8d97ad" fontSize={size === 'large' ? '12' : '10'}>
          {startLabel}
        </text>
        <text x={width - pad.right} y={height - 8} fill="#8d97ad" fontSize={size === 'large' ? '12' : '10'} textAnchor="end">
          {endLabel}
        </text>
      </svg>

      {showGuide ? (
        <div
          className={`pointer-events-none absolute z-10 w-max min-w-36 max-w-[calc(100%-1rem)] rounded-md border border-panel bg-surface px-3 py-2 text-xs shadow-panel ${horizontalClass} ${verticalClass}`}
          style={{ left: `${tooltipX}%`, top: `${tooltipY}%` }}
        >
          <div className="mb-1 flex items-center justify-between gap-3">
            <span className="font-semibold text-white">{metric.title}</span>
            <span className="font-mono text-white">{formatMetricValue(metric, getMetricValue(activePoint, metric.key))}</span>
          </div>
          <div className="grid gap-0.5 text-muted">
            <span>
              {t.time}: {formatTimeLabel(activePoint.t, true)}
            </span>
            <span>
              {t.value}: {formatMetricValue(metric, getMetricValue(activePoint, metric.key))}
            </span>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ChartCard({
  metric,
  points,
  timeRange,
  t,
  onExpand,
}: {
  metric: MetricConfig;
  points: HistoryPoint[];
  timeRange: number;
  t: Copy;
  onExpand: () => void;
}) {
  const reduceMotion = useReducedMotion();
  const chartPoints = downsample(points, 240);
  const stats = summarize(chartPoints, metric.key);

  if (chartPoints.length < 2) {
    return (
      <motion.div
        className="min-w-0 rounded-lg border border-panel bg-surface p-4"
        initial={reduceMotion ? false : { opacity: 0, y: 8 }}
        animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
        transition={{ duration: 0.18 }}
      >
        <ChartHeader metric={metric} t={t} onExpand={onExpand} />
        <div className="mt-3 flex h-44 items-center justify-center rounded-md border border-panel bg-app text-xs text-muted">{t.collecting}</div>
      </motion.div>
    );
  }

  return (
    <motion.div
      className="min-w-0 rounded-lg border border-panel bg-surface p-4"
      initial={reduceMotion ? false : { opacity: 0, y: 8 }}
      animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
      whileHover={reduceMotion ? undefined : { y: -2 }}
      transition={{ duration: 0.18 }}
    >
      <ChartHeader metric={metric} t={t} onExpand={onExpand} />
      <div className="mt-3">
        <ChartGraphic metric={metric} points={chartPoints} timeRange={timeRange} size="compact" t={t} />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <Stat label={t.current} value={formatMetricValue(metric, stats.current)} />
        <Stat label={t.average} value={formatMetricValue(metric, stats.avg)} />
        <Stat label={t.maximum} value={formatMetricValue(metric, stats.max)} />
        <Stat label={t.samples} value={String(points.length)} />
      </div>
    </motion.div>
  );
}

function ChartHeader({ metric, t, onExpand }: { metric: MetricConfig; t: Copy; onExpand: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-white">
        <span style={{ color: metric.color }}>{metric.icon}</span>
        <span className="truncate">{metric.title}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="font-mono text-sm text-white">{metric.value}</span>
        <button
          type="button"
          onClick={onExpand}
          className="rounded-md p-1.5 text-muted transition hover:bg-panel hover:text-white focus:outline-none focus:ring-2 focus:ring-accent/60"
          aria-label={`${t.expandChart}: ${metric.title}`}
          title={t.expandChart}
        >
          <Maximize2 className="h-4 w-4" />
        </button>
      </div>
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

function RangeSelector({ timeRange, onRangeChange }: { timeRange: number; onRangeChange: (range: number) => void }) {
  return (
    <div className="flex max-w-full gap-1 overflow-x-auto rounded-md border border-panel bg-app p-1 no-scrollbar">
      {TIME_RANGES.map((range) => (
        <button
          key={range.seconds}
          type="button"
          onClick={() => onRangeChange(range.seconds)}
          className={`shrink-0 rounded px-2.5 py-1 text-xs font-semibold transition focus:outline-none focus:ring-2 focus:ring-accent/60 ${
            timeRange === range.seconds ? 'bg-accent text-white' : 'text-muted hover:bg-panel hover:text-white'
          }`}
        >
          {range.label}
        </button>
      ))}
    </div>
  );
}

function ChartDetailModal({
  metric,
  points,
  timeRange,
  t,
  onRangeChange,
  onClose,
}: {
  metric: MetricConfig;
  points: HistoryPoint[];
  timeRange: number;
  t: Copy;
  onRangeChange: (range: number) => void;
  onClose: () => void;
}) {
  const reduceMotion = useReducedMotion();
  const chartPoints = downsample(points, 480);
  const stats = summarize(chartPoints, metric.key);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/75 p-3 py-4 sm:items-center sm:p-4"
      role="dialog"
      aria-modal="true"
      initial={reduceMotion ? false : { opacity: 0 }}
      animate={reduceMotion ? undefined : { opacity: 1 }}
      exit={reduceMotion ? undefined : { opacity: 0 }}
      transition={{ duration: 0.16 }}
      onClick={onClose}
    >
      <motion.div
        className="w-full max-w-5xl rounded-lg border border-panel bg-surface p-4 shadow-panel sm:max-h-[92vh] sm:overflow-y-auto sm:p-5"
        initial={reduceMotion ? false : { opacity: 0, scale: 0.98, y: 10 }}
        animate={reduceMotion ? undefined : { opacity: 1, scale: 1, y: 0 }}
        exit={reduceMotion ? undefined : { opacity: 0, scale: 0.98, y: 10 }}
        transition={{ duration: 0.18, ease: 'easeOut' }}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 grid gap-3 sm:grid-cols-[1fr_auto] sm:items-start">
          <div className="min-w-0">
            <div className="flex min-w-0 items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex min-w-0 items-center gap-2 text-sm text-muted">
                  <span style={{ color: metric.color }}>{metric.icon}</span>
                  <span className="truncate">{t.chartDetails}</span>
                </div>
                <h2 className="mt-1 truncate text-xl font-semibold text-white">{metric.title}</h2>
                <p className="font-mono text-sm text-muted">{metric.value}</p>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="shrink-0 rounded-md p-2 text-muted transition hover:bg-panel hover:text-white focus:outline-none focus:ring-2 focus:ring-accent/60 sm:hidden"
                aria-label={t.close}
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>
          <div className="grid min-w-0 items-start gap-2 sm:flex sm:items-center">
            <RangeSelector timeRange={timeRange} onRangeChange={onRangeChange} />
            <button
              type="button"
              onClick={onClose}
              className="hidden rounded-md p-2 text-muted transition hover:bg-panel hover:text-white focus:outline-none focus:ring-2 focus:ring-accent/60 sm:block"
              aria-label={t.close}
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {chartPoints.length < 2 ? (
          <div className="flex h-72 items-center justify-center rounded-md border border-panel bg-app text-sm text-muted">{t.collecting}</div>
        ) : (
          <ChartGraphic metric={metric} points={chartPoints} timeRange={timeRange} size="large" t={t} />
        )}

        <div className="mt-4 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
          <Stat label={t.current} value={formatMetricValue(metric, stats.current)} />
          <Stat label={t.average} value={formatMetricValue(metric, stats.avg)} />
          <Stat label={t.maximum} value={formatMetricValue(metric, stats.max)} />
          <Stat label={t.samples} value={String(points.length)} />
        </div>
      </motion.div>
    </motion.div>
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
  const reduceMotion = useReducedMotion();
  const [expandedMetric, setExpandedMetric] = useState<MetricKey | null>(null);
  const latest = history[history.length - 1]?.t ?? stats?.sampled_at ?? 0;
  const visible = history.filter((point) => point.t >= latest - timeRange);
  const metrics: MetricConfig[] = [
    {
      key: 'cpu',
      title: t.cpu,
      value: stats?.cpu_usage !== undefined ? `${round(stats.cpu_usage, 1)}%` : '...',
      icon: <Cpu className="h-4 w-4" />,
      color: '#8ea0ff',
      unit: '%',
      fixedMax: 100,
    },
    {
      key: 'ram',
      title: t.ram,
      value: stats?.ram_usage_mb !== undefined ? `${round(stats.ram_usage_mb, 0)} MB` : '...',
      icon: <Database className="h-4 w-4" />,
      color: '#1ed39a',
      unit: ' MB',
    },
    {
      key: 'ping',
      title: t.ping,
      value: stats?.ping !== undefined ? `${round(stats.ping, 1)}ms` : '...',
      icon: <Activity className="h-4 w-4" />,
      color: '#ff7676',
      unit: 'ms',
    },
  ];
  const activeMetric = metrics.find((metric) => metric.key === expandedMetric) ?? null;

  return (
    <motion.section
      className="min-w-0 rounded-lg border border-panel bg-surface p-4 shadow-panel"
      initial={reduceMotion ? false : { opacity: 0, y: 10 }}
      animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: 'easeOut' }}
    >
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-white">{t.performance}</h2>
          <p className="text-xs text-muted">{t.range}</p>
        </div>
        <RangeSelector timeRange={timeRange} onRangeChange={onRangeChange} />
      </div>

      <div className="grid min-w-0 gap-3 lg:grid-cols-3">
        {metrics.map((metric) => (
          <ChartCard key={metric.key} metric={metric} points={visible} timeRange={timeRange} t={t} onExpand={() => setExpandedMetric(metric.key)} />
        ))}
      </div>

      <AnimatePresence>
        {activeMetric && (
          <ChartDetailModal
            key={activeMetric.key}
            metric={activeMetric}
            points={visible}
            timeRange={timeRange}
            t={t}
            onRangeChange={onRangeChange}
            onClose={() => setExpandedMetric(null)}
          />
        )}
      </AnimatePresence>
    </motion.section>
  );
}
