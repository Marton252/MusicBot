import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { Activity, Music, Server, Users } from 'lucide-react';
import { copy } from './i18n';
import type { DashUser, HistoryPoint, Language, Stats } from './types';
import { ConfirmDialog } from './components/ConfirmDialog';
import { LogPanel } from './components/LogPanel';
import { MetricCard } from './components/MetricCard';
import { PerformancePanel } from './components/PerformancePanel';
import { StatusPanel } from './components/StatusPanel';
import { TopBar } from './components/TopBar';
import { UserManagementPanel } from './components/UserManagementPanel';

const MAX_LOGS = 500;
const WS_RECONNECT_BASE = 3000;
const WS_RECONNECT_MAX = 30000;
const DISCONNECT_GRACE_MS = 3000;
const MAX_HISTORY = 86400;

function getDashboardWsUrl() {
  const explicit = import.meta.env.VITE_DASHBOARD_WS_URL as string | undefined;
  if (explicit) return explicit;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws`;
}

export default function Dashboard({
  user,
  language,
  onLanguageChange,
  onLogout,
}: {
  user: DashUser;
  language: Language;
  onLanguageChange: (language: Language) => void;
  onLogout: () => void;
}) {
  const t = useMemo(() => copy[language], [language]);
  const reduceMotion = useReducedMotion();
  const [stats, setStats] = useState<Stats | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [wsStatus, setWsStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting');
  const [showDisconnect, setShowDisconnect] = useState(false);
  const [restartOpen, setRestartOpen] = useState(false);
  const [logoutOpen, setLogoutOpen] = useState(false);
  const [timeRange, setTimeRange] = useState(() => Number(localStorage.getItem('dash_timeRange')) || 60);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelay = useRef(WS_RECONNECT_BASE);
  const [history, setHistory] = useState<HistoryPoint[]>([]);

  useEffect(() => {
    localStorage.setItem('dash_timeRange', String(timeRange));
  }, [timeRange]);

  useEffect(() => {
    if (wsStatus !== 'connected') {
      const timer = window.setTimeout(() => setShowDisconnect(true), DISCONNECT_GRACE_MS);
      return () => window.clearTimeout(timer);
    }
    const timer = window.setTimeout(() => setShowDisconnect(false), 0);
    return () => window.clearTimeout(timer);
  }, [wsStatus]);

  useEffect(() => {
    const wsUrl = getDashboardWsUrl();
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }

      const socket = new WebSocket(wsUrl);
      wsRef.current = socket;
      setWsStatus('connecting');

      socket.onopen = () => {
        setWsStatus('connected');
        reconnectDelay.current = WS_RECONNECT_BASE;
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type !== 'update') return;

          if (data.stats_history) {
            if (Array.isArray(data.stats_history.points)) {
              setHistory(data.stats_history.points.slice(-MAX_HISTORY));
            } else if (Array.isArray(data.stats_history.cpu)) {
              const now = Date.now() / 1000;
              const legacyPoints = data.stats_history.cpu.map((cpu: number, index: number) => ({
                t: now - (data.stats_history.cpu.length - index - 1),
                cpu,
                ram: data.stats_history.ram[index],
                ping: data.stats_history.ping[index],
              }));
              setHistory(legacyPoints.slice(-MAX_HISTORY));
            }
          } else if (data.stats) {
            setHistory((prev) =>
              [
                ...prev,
                {
                  t: data.stats.sampled_at ?? Date.now() / 1000,
                  cpu: data.stats.cpu_usage,
                  ram: data.stats.ram_usage_mb,
                  ping: data.stats.ping,
                },
              ].slice(-MAX_HISTORY),
            );
          }

          if (data.stats) {
            setStats(data.stats);
          }
          if (data.full_logs) setLogs(data.full_logs.slice(-MAX_LOGS));
          if (data.new_logs) setLogs((prev) => [...prev, ...data.new_logs].slice(-MAX_LOGS));
        } catch {
          // Ignore malformed frames from stale connections.
        }
      };

      socket.onclose = () => {
        setWsStatus('disconnected');
        if (!cancelled) {
          window.setTimeout(connect, reconnectDelay.current);
          reconnectDelay.current = Math.min(reconnectDelay.current * 2, WS_RECONNECT_MAX);
        }
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, []);

  const confirmLogout = async () => {
    setLogoutOpen(false);
    await fetch('/api/logout', { method: 'POST', headers: { 'X-CSRF-Protection': '1' } });
    onLogout();
  };

  const confirmRestart = async () => {
    setRestartOpen(false);
    setWsStatus('disconnected');
    try {
      await fetch('/api/action/restart', { method: 'POST', headers: { 'X-CSRF-Protection': '1' } });
    } catch {
      // The bot may go away immediately after the restart request.
    }
  };

  return (
    <div className="min-h-screen bg-app text-white">
      <TopBar
        user={user}
        stats={stats}
        language={language}
        t={t}
        onLanguageChange={onLanguageChange}
        onRestart={() => setRestartOpen(true)}
        onLogout={() => setLogoutOpen(true)}
      />

      <main className="mx-auto grid w-full max-w-7xl gap-4 px-4 py-4 sm:px-6 sm:py-6">
        <motion.section
          className="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-3 lg:grid-cols-4"
          initial={reduceMotion ? false : { opacity: 0, y: 8 }}
          animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
        >
          <MetricCard icon={<Server className="h-5 w-5" />} label={t.servers} value={stats?.guilds} />
          <MetricCard icon={<Users className="h-5 w-5" />} label={t.totalUsers} value={stats?.users} />
          <MetricCard icon={<Music className="h-5 w-5" />} label={t.activeVoice} value={stats?.voice_clients} />
          <MetricCard icon={<Activity className="h-5 w-5" />} label={t.ping} value={stats ? `${stats.ping}ms` : undefined} />
        </motion.section>

        <motion.section
          className="grid min-w-0 gap-4 xl:grid-cols-[380px_minmax(0,1fr)]"
          initial={reduceMotion ? false : { opacity: 0, y: 10 }}
          animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.22, delay: reduceMotion ? 0 : 0.04, ease: 'easeOut' }}
        >
          <StatusPanel stats={stats} wsStatus={wsStatus} t={t} />
          <PerformancePanel
            history={history}
            timeRange={timeRange}
            stats={stats}
            t={t}
            onRangeChange={setTimeRange}
          />
        </motion.section>

        {user.can_view_logs && <LogPanel logs={logs} t={t} />}
        {user.is_admin && <UserManagementPanel t={t} />}
      </main>

      <AnimatePresence>
        {showDisconnect && (
          <motion.div
            className="fixed inset-0 z-40 flex items-center justify-center bg-black/75 p-4"
            initial={reduceMotion ? false : { opacity: 0 }}
            animate={reduceMotion ? undefined : { opacity: 1 }}
            exit={reduceMotion ? undefined : { opacity: 0 }}
            transition={{ duration: 0.16 }}
          >
            <motion.div
              className="rounded-lg border border-panel bg-surface p-6 text-center shadow-panel"
              initial={reduceMotion ? false : { opacity: 0, scale: 0.98, y: 8 }}
              animate={reduceMotion ? undefined : { opacity: 1, scale: 1, y: 0 }}
              exit={reduceMotion ? undefined : { opacity: 0, scale: 0.98, y: 8 }}
              transition={{ duration: 0.18 }}
            >
              <Activity className="mx-auto mb-3 h-8 w-8 animate-pulse text-accent" />
              <h2 className="text-lg font-semibold">{t.connectionLost}</h2>
              <p className="mt-1 text-sm text-muted">{t.reconnecting}</p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {restartOpen && (
          <ConfirmDialog
            title={t.restartTitle}
            body={t.restartBody}
            confirmLabel={t.restartShort}
            tone="danger"
            t={t}
            onCancel={() => setRestartOpen(false)}
            onConfirm={confirmRestart}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {logoutOpen && (
          <ConfirmDialog
            title={t.logoutTitle}
            body={t.logoutBody}
            confirmLabel={t.logout}
            t={t}
            onCancel={() => setLogoutOpen(false)}
            onConfirm={confirmLogout}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
