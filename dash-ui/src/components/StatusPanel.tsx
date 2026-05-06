import { Activity, Headphones, Radio, Server } from 'lucide-react';
import type { ReactNode } from 'react';
import type { Copy } from '../i18n';
import type { Stats } from '../types';

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-xs font-semibold ${ok ? 'bg-ok/10 text-emerald-200' : 'bg-danger/10 text-red-200'}`}>
      <span className={`h-2 w-2 rounded-full ${ok ? 'bg-ok' : 'bg-danger'}`} />
      {label}
    </span>
  );
}

function StatusRow({ label, value, icon }: { label: string; value: ReactNode; icon: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-panel px-4 py-3 last:border-b-0">
      <div className="flex min-w-0 items-center gap-3 text-sm text-muted">
        <span className="text-accent">{icon}</span>
        <span className="truncate">{label}</span>
      </div>
      <div className="min-w-0 text-right text-sm font-medium text-white">{value}</div>
    </div>
  );
}

export function StatusPanel({ stats, wsStatus, t }: { stats: Stats | null; wsStatus: 'connecting' | 'connected' | 'disconnected'; t: Copy }) {
  const audio = stats?.audio;
  const socketOk = wsStatus === 'connected';
  const lavalinkOk = Boolean(audio?.lavalink_connected);

  return (
    <section className="rounded-lg border border-panel bg-surface shadow-panel">
      <div className="flex items-center justify-between border-b border-panel px-4 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-white">{t.status}</h2>
        <StatusPill ok={socketOk} label={socketOk ? t.connected : t.disconnected} />
      </div>
      <div>
        <StatusRow
          icon={<Radio className="h-4 w-4" />}
          label={t.websocket}
          value={wsStatus === 'connecting' ? t.collecting : socketOk ? t.connected : t.disconnected}
        />
        <StatusRow icon={<Server className="h-4 w-4" />} label={t.configured} value={audio?.configured_backend ?? '...'} />
        <StatusRow icon={<Activity className="h-4 w-4" />} label={t.effective} value={audio?.effective_backend ?? '...'} />
        <StatusRow
          icon={<Headphones className="h-4 w-4" />}
          label={t.node}
          value={
            <div className="flex flex-col items-end gap-1">
              <StatusPill ok={lavalinkOk} label={lavalinkOk ? t.connected : audio?.lavalink_requested ? t.requested : t.notRequested} />
              <span className="max-w-[220px] truncate text-xs text-muted">{audio?.lavalink_uri ?? '...'}</span>
            </div>
          }
        />
      </div>
    </section>
  );
}
