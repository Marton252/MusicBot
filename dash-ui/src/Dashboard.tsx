import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Server, Users, Activity, Music, LogOut, RefreshCw, Cpu, Database, Disc3,
  AlertTriangle, BarChart3, UserPlus, Trash2, Pencil, Shield, ShieldCheck, X,
  Eye, EyeOff,
} from 'lucide-react';
import type { DashUser } from './App';

interface Stats {
  ping: number;
  guilds: number;
  users: number;
  voice_clients: number;
  ram_usage_mb: number;
  cpu_usage: number;
  uptime: string;
}

interface DashboardUser {
  id: number;
  username: string;
  is_admin: boolean;
  can_restart: boolean;
  can_view_logs: boolean;
  password_display?: string;
  created_at?: string;
}

const MAX_LOGS = 500;
const WS_RECONNECT_BASE = 3000;
const WS_RECONNECT_MAX = 30000;
const DISCONNECT_GRACE_MS = 3000;
const MAX_HISTORY = 86400;

const TIME_RANGES = [
  { label: '1m',  seconds: 60 },
  { label: '5m',  seconds: 300 },
  { label: '10m', seconds: 600 },
  { label: '30m', seconds: 1800 },
  { label: '1h',  seconds: 3600 },
  { label: '4h',  seconds: 14400 },
  { label: '12h', seconds: 43200 },
  { label: '1d',  seconds: 86400 },
] as const;

function downsample(data: number[], maxPoints: number): number[] {
  if (data.length <= maxPoints) return data;
  const step = data.length / maxPoints;
  const result: number[] = [];
  for (let i = 0; i < maxPoints; i++) {
    const start = Math.floor(i * step);
    const end = Math.floor((i + 1) * step);
    let sum = 0;
    for (let j = start; j < end; j++) sum += data[j];
    result.push(Math.round((sum / (end - start)) * 10) / 10);
  }
  return result;
}

function LogLine({ text }: { text: string }) {
  const parts: React.ReactNode[] = [];
  const regex = /\[(INFO|ERROR|WARNING)]/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let keyIdx = 0;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(<span key={keyIdx++}>{text.slice(lastIndex, match.index)}</span>);
    }
    const level = match[1];
    const color = level === 'INFO' ? 'text-blue-400' : level === 'ERROR' ? 'text-red-400' : 'text-yellow-400';
    parts.push(<span key={keyIdx++} className={color}>[{level}]</span>);
    lastIndex = regex.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push(<span key={keyIdx++}>{text.slice(lastIndex)}</span>);
  }

  return <>{parts}</>;
}

function Sparkline({ data, maxVal, color, id, unit, rangeSec }: {
  data: number[]; maxVal: number; color: string; id: string; unit: string; rangeSec: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ idx: number; x: number; y: number; val: number } | null>(null);

  const w = 400;
  const h = 100;
  const pad = 2;

  if (data.length < 2) {
    return (
      <div className="w-full h-28 flex items-center justify-center text-slate-500 text-xs font-mono">
        Collecting data...
      </div>
    );
  }

  const clampedMax = Math.max(maxVal, 1);
  const step = w / (data.length - 1);
  const getY = (v: number) => h - pad - ((Math.min(v, clampedMax) / clampedMax) * (h - pad * 2));
  const points = data.map((v, i) => `${i * step},${getY(v)}`);
  const linePath = `M${points.join(' L')}`;
  const areaPath = `${linePath} L${(data.length - 1) * step},${h} L0,${h} Z`;

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const ratio = mx / rect.width;
    const idx = Math.round(ratio * (data.length - 1));
    const clamped = Math.max(0, Math.min(data.length - 1, idx));
    setHover({
      idx: clamped,
      x: (clamped * step / w) * 100,
      y: getY(data[clamped]),
      val: data[clamped],
    });
  };

  const handleMouseLeave = () => setHover(null);

  const getTimeLabel = (idx: number) => {
    const secsAgo = Math.round(((data.length - 1 - idx) / (data.length - 1)) * rangeSec);
    if (secsAgo === 0) return 'now';
    if (secsAgo < 60) return `${secsAgo}s ago`;
    if (secsAgo < 3600) return `${Math.floor(secsAgo / 60)}m ${secsAgo % 60}s ago`;
    const hrs = Math.floor(secsAgo / 3600);
    const mins = Math.floor((secsAgo % 3600) / 60);
    return `${hrs}h ${mins}m ago`;
  };

  return (
    <div ref={containerRef} className="relative">
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="w-full h-28 cursor-crosshair"
        preserveAspectRatio="none"
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      >
        <defs>
          <linearGradient id={`grad-${id}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.4" />
            <stop offset="100%" stopColor={color} stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill={`url(#grad-${id})`} />
        <path d={linePath} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" />
        {hover && (
          <>
            <line x1={hover.idx * step} y1={0} x2={hover.idx * step} y2={h} stroke="rgba(255,255,255,0.2)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
            <circle cx={hover.idx * step} cy={hover.y} r="4" fill={color} stroke="#fff" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
          </>
        )}
        {!hover && data.length > 0 && (
          <circle cx={(data.length - 1) * step} cy={getY(data[data.length - 1])} r="3" fill={color} className="animate-pulse" />
        )}
      </svg>
      {hover && containerRef.current && (
        <div className="absolute top-0 pointer-events-none z-10 -translate-x-1/2" style={{ left: `${hover.x}%` }}>
          <div className="bg-slate-800/95 backdrop-blur border border-white/10 rounded-lg px-3 py-1.5 shadow-xl text-center whitespace-nowrap">
            <div className="text-white font-mono text-sm font-semibold">{hover.val}{unit}</div>
            <div className="text-slate-400 text-xs">{getTimeLabel(hover.idx)}</div>
          </div>
        </div>
      )}
    </div>
  );
}

function TimeRangeSelector({ selected, onChange }: {
  selected: number; onChange: (seconds: number) => void;
}) {
  return (
    <div className="flex gap-1 bg-black/20 rounded-xl p-1 border border-white/5 overflow-x-auto no-scrollbar">
      {TIME_RANGES.map((r) => (
        <button
          key={r.seconds}
          onClick={() => onChange(r.seconds)}
          className={`px-2 sm:px-3 py-1 rounded-lg text-xs font-medium transition-all duration-200 whitespace-nowrap ${
            selected === r.seconds
              ? 'bg-brand-500 text-white shadow-lg shadow-brand-500/25'
              : 'text-slate-400 hover:text-white hover:bg-white/5'
          }`}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}

function ToggleSwitch({ enabled, onToggle, label }: { enabled: boolean; onToggle: () => void; label: string }) {
  return (
    <button
      onClick={onToggle}
      className="flex items-center gap-3 text-sm font-medium text-slate-400 hover:text-white transition-colors"
      aria-pressed={enabled}
    >
      <BarChart3 className="w-4 h-4" />
      <span>{label}</span>
      <div className={`w-10 h-5 rounded-full relative transition-colors duration-200 ${
        enabled ? 'bg-brand-500' : 'bg-white/10'
      }`}>
        <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200 ${
          enabled ? 'translate-x-5' : 'translate-x-0.5'
        }`} />
      </div>
    </button>
  );
}

/** Compact toggle used in user management cards/table. */
function MiniToggle({ enabled, onToggle, disabled }: { enabled: boolean; onToggle: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={disabled}
      className={`w-9 h-5 rounded-full relative transition-colors duration-200 ${
        disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
      } ${enabled ? 'bg-brand-500' : 'bg-white/10'}`}
    >
      <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200 ${
        enabled ? 'translate-x-4' : 'translate-x-0.5'
      }`} />
    </button>
  );
}

// ─── User Management Panel ──────────────────────────────────────────────────────

function UserManagementPanel() {
  const [users, setUsers] = useState<DashboardUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editUser, setEditUser] = useState<DashboardUser | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DashboardUser | null>(null);

  const fetchUsers = useCallback(async () => {
    try {
      const res = await fetch('/api/users');
      if (res.ok) {
        setUsers(await res.json());
      }
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const handleToggle = async (user: DashboardUser, field: 'can_restart' | 'can_view_logs') => {
    const update = { [field]: !user[field] };
    const res = await fetch(`/api/users/${user.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Protection': '1' },
      body: JSON.stringify(update),
    });
    if (res.ok) {
      setUsers((prev) => prev.map((u) => u.id === user.id ? { ...u, ...update } : u));
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    const res = await fetch(`/api/users/${deleteTarget.id}`, { method: 'DELETE', headers: { 'X-CSRF-Protection': '1' } });
    if (res.ok) {
      setUsers((prev) => prev.filter((u) => u.id !== deleteTarget.id));
    }
    setDeleteTarget(null);
  };

  if (loading) {
    return (
      <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-xl flex items-center justify-center">
        <Disc3 className="w-8 h-8 text-brand-500 animate-spin" />
      </div>
    );
  }

  return (
    <>
      <section className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl shadow-xl overflow-hidden">
        <div className="bg-white/5 px-4 sm:px-6 py-3 sm:py-4 border-b border-white/10 flex justify-between items-center">
          <span className="font-medium text-sm text-white flex items-center gap-2">
            <Shield className="w-4 h-4 text-brand-500" /> User Management
          </span>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-1.5 bg-brand-500 hover:bg-brand-500/90 text-white text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
          >
            <UserPlus className="w-3.5 h-3.5" /> Add User
          </button>
        </div>

        {/* Desktop table (hidden on mobile) */}
        <div className="hidden sm:block overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-white/5">
                <th className="text-left px-6 py-3 font-medium">User</th>
                <th className="text-center px-4 py-3 font-medium">Restart</th>
                <th className="text-center px-4 py-3 font-medium">View Logs</th>
                <th className="text-right px-6 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-white/5 last:border-0 hover:bg-white/[0.02] transition-colors">
                  <td className="px-6 py-3">
                    <div className="flex items-center gap-2">
                      {u.is_admin ? (
                        <ShieldCheck className="w-4 h-4 text-brand-500 shrink-0" />
                      ) : (
                        <div className="w-4 h-4 rounded-full bg-white/10 shrink-0" />
                      )}
                      <span className="text-white font-medium">{u.username}</span>
                      {u.is_admin && (
                        <span className="text-[10px] font-semibold uppercase tracking-wider bg-brand-500/20 text-brand-500 px-1.5 py-0.5 rounded">
                          Admin
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="text-center px-4 py-3">
                    <div className="flex justify-center">
                      <MiniToggle enabled={u.can_restart} onToggle={() => handleToggle(u, 'can_restart')} disabled={u.is_admin} />
                    </div>
                  </td>
                  <td className="text-center px-4 py-3">
                    <div className="flex justify-center">
                      <MiniToggle enabled={u.can_view_logs} onToggle={() => handleToggle(u, 'can_view_logs')} disabled={u.is_admin} />
                    </div>
                  </td>
                  <td className="text-right px-6 py-3">
                    {!u.is_admin && (
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => setEditUser(u)}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                          title="Edit user"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => setDeleteTarget(u)}
                          className="p-1.5 rounded-lg text-red-400/70 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                          title="Delete user"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Mobile card layout (visible only on mobile) */}
        <div className="sm:hidden divide-y divide-white/5">
          {users.map((u) => (
            <div key={u.id} className="p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {u.is_admin ? <ShieldCheck className="w-4 h-4 text-brand-500" /> : <div className="w-4 h-4 rounded-full bg-white/10" />}
                  <span className="text-white font-medium text-sm">{u.username}</span>
                  {u.is_admin && (
                    <span className="text-[10px] font-semibold uppercase tracking-wider bg-brand-500/20 text-brand-500 px-1.5 py-0.5 rounded">
                      Admin
                    </span>
                  )}
                </div>
                {!u.is_admin && (
                  <div className="flex gap-1">
                    <button onClick={() => setEditUser(u)} className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors">
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button onClick={() => setDeleteTarget(u)} className="p-1.5 rounded-lg text-red-400/70 hover:text-red-400 hover:bg-red-500/10 transition-colors">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}
              </div>
              <div className="flex gap-6 text-xs text-slate-400">
                <label className="flex items-center gap-2">
                  <MiniToggle enabled={u.can_restart} onToggle={() => handleToggle(u, 'can_restart')} disabled={u.is_admin} />
                  <span>Restart</span>
                </label>
                <label className="flex items-center gap-2">
                  <MiniToggle enabled={u.can_view_logs} onToggle={() => handleToggle(u, 'can_view_logs')} disabled={u.is_admin} />
                  <span>View Logs</span>
                </label>
              </div>
            </div>
          ))}
          {users.length === 0 && (
            <div className="p-6 text-center text-slate-500 text-sm">No users yet.</div>
          )}
        </div>
      </section>

      {/* Add User Modal */}
      <AnimatePresence>
        {showAddModal && (
          <UserFormModal
            title="Add User"
            onClose={() => setShowAddModal(false)}
            onSave={async (data) => {
              const res = await fetch('/api/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Protection': '1' },
                body: JSON.stringify(data),
              });
              if (res.ok) {
                await fetchUsers();
                setShowAddModal(false);
                return null;
              }
              const err = await res.json();
              return err.error || 'Failed to create user.';
            }}
          />
        )}
      </AnimatePresence>

      {/* Edit User Modal */}
      <AnimatePresence>
        {editUser && (
          <UserFormModal
            title={`Edit: ${editUser.username}`}
            initialData={editUser}
            isEdit
            onClose={() => setEditUser(null)}
            onSave={async (data) => {
              const payload: Record<string, unknown> = {};
              if (data.username !== editUser.username) payload.username = data.username;
              if (data.password) payload.password = data.password;
              if (data.can_restart !== editUser.can_restart) payload.can_restart = data.can_restart;
              if (data.can_view_logs !== editUser.can_view_logs) payload.can_view_logs = data.can_view_logs;
              if (Object.keys(payload).length === 0) {
                setEditUser(null);
                return null;
              }
              const res = await fetch(`/api/users/${editUser.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Protection': '1' },
                body: JSON.stringify(payload),
              });
              if (res.ok) {
                await fetchUsers();
                setEditUser(null);
                return null;
              }
              const err = await res.json();
              return err.error || 'Failed to update user.';
            }}
          />
        )}
      </AnimatePresence>

      {/* Delete Confirmation Modal */}
      <AnimatePresence>
        {deleteTarget && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-md p-4"
            onClick={() => setDeleteTarget(null)}
          >
            <motion.div
              initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9, y: 20 }}
              className="bg-slate-900 border border-white/10 p-6 sm:p-8 rounded-2xl max-w-sm w-full shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="w-14 h-14 bg-red-500/10 rounded-xl flex items-center justify-center mb-5 border border-red-500/20 mx-auto">
                <AlertTriangle className="w-7 h-7 text-red-500" />
              </div>
              <h2 className="text-xl font-bold text-white text-center mb-2">Delete User?</h2>
              <p className="text-slate-400 text-center mb-6 text-sm">
                Are you sure you want to delete <span className="text-white font-medium">{deleteTarget.username}</span>? This cannot be undone.
              </p>
              <div className="flex gap-3">
                <button onClick={() => setDeleteTarget(null)} className="flex-1 px-4 py-2.5 bg-white/5 hover:bg-white/10 text-white font-medium rounded-xl transition-colors border border-white/5 text-sm">Cancel</button>
                <button onClick={handleDelete} className="flex-1 px-4 py-2.5 bg-red-500 hover:bg-red-500/90 text-white font-medium rounded-xl transition-colors text-sm">Delete</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

function UserFormModal({ title, initialData, isEdit, onClose, onSave }: {
  title: string;
  initialData?: DashboardUser;
  isEdit?: boolean;
  onClose: () => void;
  onSave: (data: { username: string; password: string; can_restart: boolean; can_view_logs: boolean }) => Promise<string | null>;
}) {
  const [username, setUsername] = useState(initialData?.username || '');
  const [password, setPassword] = useState('');
  const [canRestart, setCanRestart] = useState(initialData?.can_restart ?? false);
  const [canViewLogs, setCanViewLogs] = useState(initialData?.can_view_logs ?? true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    const err = await onSave({ username, password, can_restart: canRestart, can_view_logs: canViewLogs });
    if (err) setError(err);
    setSaving(false);
  };

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-md p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9, y: 20 }}
        className="bg-slate-900 border border-white/10 p-6 sm:p-8 rounded-2xl max-w-sm w-full shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-lg font-bold text-white">{title}</h2>
          <button onClick={onClose} className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={isEdit ? undefined : 'e.g. moderator'}
              className="w-full bg-black/30 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm placeholder:text-slate-500 focus:outline-none focus:border-brand-500 transition-colors"
              required
              minLength={3}
              maxLength={32}
              pattern="[a-zA-Z0-9_\-]+"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              {isEdit ? 'Password (leave empty to keep current)' : 'Password'}
            </label>
            {isEdit && initialData?.password_display && (
              <p className="text-xs text-slate-500 mb-1.5 font-mono">Current: {initialData.password_display}</p>
            )}
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={isEdit ? 'Leave empty to keep current' : 'Min. 6 characters'}
                className="w-full bg-black/30 border border-white/10 rounded-xl px-4 py-2.5 pr-10 text-white text-sm placeholder:text-slate-500 focus:outline-none focus:border-brand-500 transition-colors"
                required={!isEdit}
                minLength={isEdit ? 0 : 6}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white transition-colors"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <div className="space-y-3 pt-2">
            <label className="flex items-center justify-between text-sm text-white">
              <span className="flex items-center gap-2">
                <RefreshCw className="w-4 h-4 text-slate-400" /> Can Restart Bot
              </span>
              <MiniToggle enabled={canRestart} onToggle={() => setCanRestart(!canRestart)} />
            </label>
            <label className="flex items-center justify-between text-sm text-white">
              <span className="flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-slate-400" /> Can View Logs
              </span>
              <MiniToggle enabled={canViewLogs} onToggle={() => setCanViewLogs(!canViewLogs)} />
            </label>
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}

          <button
            type="submit"
            disabled={saving}
            className="w-full bg-brand-500 hover:bg-brand-500/90 text-white font-medium py-2.5 rounded-xl transition-colors flex items-center justify-center gap-2 text-sm mt-2"
          >
            {saving ? <Disc3 className="w-4 h-4 animate-spin" /> : null}
            {saving ? 'Saving...' : isEdit ? 'Save Changes' : 'Create User'}
          </button>
        </form>
      </motion.div>
    </motion.div>
  );
}

// ─── Main Dashboard ─────────────────────────────────────────────────────────────

export default function Dashboard({ user, onLogout }: { user: DashUser; onLogout: () => void }) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [wsStatus, setWsStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting');
  const [showDisconnect, setShowDisconnect] = useState(false);
  const [isRestartModalOpen, setIsRestartModalOpen] = useState(false);
  const [isLogoutModalOpen, setIsLogoutModalOpen] = useState(false);
  const [graphMode, setGraphMode] = useState(() => localStorage.getItem('dash_graphMode') === 'true');
  const [timeRange, setTimeRange] = useState(() => Number(localStorage.getItem('dash_timeRange')) || 60);
  const wsRef = useRef<WebSocket | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);
  const reconnectDelay = useRef(WS_RECONNECT_BASE);
  const disconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelBtnRef = useRef<HTMLButtonElement>(null);

  const cpuHistory = useRef<number[]>([]);
  const ramHistory = useRef<number[]>([]);
  const pingHistory = useRef<number[]>([]);
  const [, forceGraphUpdate] = useState(0);

  const handleLogScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    isAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  }, []);

  useEffect(() => { localStorage.setItem('dash_graphMode', String(graphMode)); }, [graphMode]);
  useEffect(() => { localStorage.setItem('dash_timeRange', String(timeRange)); }, [timeRange]);

  useEffect(() => {
    if (wsStatus !== 'connected') {
      disconnectTimer.current = setTimeout(() => setShowDisconnect(true), DISCONNECT_GRACE_MS);
    } else {
      if (disconnectTimer.current) clearTimeout(disconnectTimer.current);
      setShowDisconnect(false);
    }
    return () => { if (disconnectTimer.current) clearTimeout(disconnectTimer.current); };
  }, [wsStatus]);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = import.meta.env.DEV 
        ? `ws://127.0.0.1:8080/ws` 
        : `${protocol}//${window.location.host}/ws`;

    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }

      const socket = new WebSocket(wsUrl);
      wsRef.current = socket;

      socket.onopen = () => {
        setWsStatus('connected');
        reconnectDelay.current = WS_RECONNECT_BASE;
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'update') {
            if (data.stats_history) {
              cpuHistory.current = data.stats_history.cpu.slice(-MAX_HISTORY);
              ramHistory.current = data.stats_history.ram.slice(-MAX_HISTORY);
              pingHistory.current = data.stats_history.ping.slice(-MAX_HISTORY);
            } else if (data.stats) {
              // O(1) push+shift instead of O(n) spread+slice
              cpuHistory.current.push(data.stats.cpu_usage);
              ramHistory.current.push(data.stats.ram_usage_mb);
              pingHistory.current.push(data.stats.ping);
              if (cpuHistory.current.length > MAX_HISTORY) cpuHistory.current.shift();
              if (ramHistory.current.length > MAX_HISTORY) ramHistory.current.shift();
              if (pingHistory.current.length > MAX_HISTORY) pingHistory.current.shift();
            }
            if (data.stats) {
              setStats(data.stats);
              forceGraphUpdate((n) => n + 1);
            }
            if (data.full_logs) setLogs(data.full_logs.slice(-MAX_LOGS));
            if (data.new_logs) setLogs((prev) => [...prev, ...data.new_logs].slice(-MAX_LOGS));
          }
        } catch {
          /* ignore malformed frames */
        }
      };

      socket.onclose = () => {
        setWsStatus('disconnected');
        if (!cancelled) {
          setTimeout(connect, reconnectDelay.current);
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

  useEffect(() => {
    if (isAtBottomRef.current) {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  useEffect(() => {
    if (isRestartModalOpen) {
      cancelBtnRef.current?.focus();
    }
  }, [isRestartModalOpen]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isRestartModalOpen) {
        setIsRestartModalOpen(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isRestartModalOpen]);

  const confirmLogout = async () => {
    setIsLogoutModalOpen(false);
    await fetch('/api/logout', { method: 'POST', headers: { 'X-CSRF-Protection': '1' } });
    onLogout();
  };

  const handleRestart = async () => {
    setIsRestartModalOpen(true);
  };

  const confirmRestart = async () => {
    setIsRestartModalOpen(false);
    setWsStatus('disconnected');
    try {
      await fetch('/api/action/restart', { method: 'POST', headers: { 'X-CSRF-Protection': '1' } });
    } catch {
      // ignore — the bot is going away
    }
  };

  return (
    <div className="min-h-screen p-4 sm:p-8 max-w-7xl mx-auto flex flex-col gap-4 sm:gap-8">
      {/* Background Orbs */}
      <div className="fixed -z-10 top-0 left-0 w-full h-full overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] bg-brand-500/10 rounded-full blur-[100px]" />
        <div className="absolute bottom-1/4 right-1/4 w-[500px] h-[500px] bg-indigo-500/10 rounded-full blur-[100px]" />
      </div>

      <header className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4 sm:p-6 shadow-xl">
        <div className="flex items-center gap-3 sm:gap-4 min-w-0">
          <div className="w-10 h-10 sm:w-12 sm:h-12 bg-brand-500/20 rounded-xl flex items-center justify-center border border-brand-500/30 shrink-0">
            <Activity className="text-brand-500 animate-pulse w-5 h-5 sm:w-6 sm:h-6" />
          </div>
          <div className="min-w-0">
            <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">Music Bot</h1>
            <p className="text-xs sm:text-sm font-mono text-slate-400 truncate">
              {user.is_admin ? '👑' : '👤'} {user.username} · UPTIME: {stats ? stats.uptime : '...'}
            </p>
          </div>
        </div>

        <div className="flex gap-2 sm:gap-4 w-full sm:w-auto">
          {user.can_restart && (
            <button onClick={handleRestart} className="flex-1 sm:flex-none flex items-center justify-center gap-2 bg-slate-800 hover:bg-slate-700 px-3 sm:px-5 py-2.5 rounded-xl transition-colors text-sm font-medium border border-white/10">
              <RefreshCw className="w-4 h-4 shrink-0" /><span className="hidden sm:inline">Restart Bot</span><span className="sm:hidden">Restart</span>
            </button>
          )}
          <button onClick={() => setIsLogoutModalOpen(true)} className="flex-1 sm:flex-none flex items-center justify-center gap-2 bg-red-500/10 hover:bg-red-500/20 text-red-500 px-3 sm:px-5 py-2.5 rounded-xl transition-colors text-sm font-medium border border-red-500/20">
            <LogOut className="w-4 h-4 shrink-0" /><span>Logout</span>
          </button>
        </div>
      </header>

      <main className="grid grid-cols-2 md:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-6">
        <StatCard icon={<Server className="text-blue-400" />} label="Servers" value={stats?.guilds} />
        <StatCard icon={<Users className="text-green-400" />} label="Total Users" value={stats?.users} />
        <StatCard icon={<Music className="text-purple-400" />} label="Active Voice" value={stats?.voice_clients} />
        <StatCard icon={<Activity className="text-brand-500" />} label="Ping" value={stats ? `${stats.ping}ms` : undefined} />

        <div className="col-span-2 lg:col-span-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
          {graphMode && <TimeRangeSelector selected={timeRange} onChange={setTimeRange} />}
          {!graphMode && <div />}
          <ToggleSwitch enabled={graphMode} onToggle={() => setGraphMode((v) => !v)} label="Graph View" />
        </div>

        {graphMode ? (
          (() => {
            const cpuSlice = downsample(cpuHistory.current.slice(-timeRange), 300);
            const ramSlice = downsample(ramHistory.current.slice(-timeRange), 300);
            const pingSlice = downsample(pingHistory.current.slice(-timeRange), 300);
            return (
              <div className="col-span-2 lg:col-span-4 grid grid-cols-1 md:grid-cols-3 gap-3 sm:gap-6">
                <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-xl">
                  <div className="flex justify-between items-center mb-3">
                    <span className="flex items-center gap-2 font-medium text-white text-sm"><Cpu className="w-4 h-4 text-indigo-400" /> CPU</span>
                    <span className="font-mono text-sm text-white">{stats?.cpu_usage !== undefined ? `${stats.cpu_usage}%` : '...'}</span>
                  </div>
                  <div className="bg-black/30 rounded-xl border border-white/5 p-2">
                    <Sparkline data={cpuSlice} maxVal={100} color="#818cf8" id="cpu" unit="%" rangeSec={timeRange} />
                  </div>
                </div>
                <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-xl">
                  <div className="flex justify-between items-center mb-3">
                    <span className="flex items-center gap-2 font-medium text-white text-sm"><Database className="w-4 h-4 text-emerald-400" /> RAM</span>
                    <span className="font-mono text-sm text-white">{stats?.ram_usage_mb !== undefined ? `${stats.ram_usage_mb} MB` : '...'}</span>
                  </div>
                  <div className="bg-black/30 rounded-xl border border-white/5 p-2">
                    <Sparkline data={ramSlice} maxVal={512} color="#34d399" id="ram" unit=" MB" rangeSec={timeRange} />
                  </div>
                </div>
                <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4 sm:p-6 shadow-xl">
                  <div className="flex justify-between items-center mb-3">
                    <span className="flex items-center gap-2 font-medium text-white text-sm"><Activity className="w-4 h-4 text-brand-500" /> Ping</span>
                    <span className="font-mono text-sm text-white">{stats?.ping !== undefined ? `${stats.ping}ms` : '...'}</span>
                  </div>
                  <div className="bg-black/30 rounded-xl border border-white/5 p-2">
                    <Sparkline data={pingSlice} maxVal={Math.max(200, ...pingSlice)} color="#FF6B6B" id="ping" unit="ms" rangeSec={timeRange} />
                  </div>
                </div>
              </div>
            );
          })()
        ) : (
          <>
            <div className="col-span-2 lg:col-span-2 bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4 sm:p-6 flex flex-col justify-center gap-4 sm:gap-6 shadow-xl">
              <div className="flex justify-between items-center text-slate-400 mb-2">
                <span className="flex items-center gap-2 font-medium text-white"><Cpu className="w-5 h-5 text-indigo-400" /> CPU Usage</span>
                <span className="font-mono text-xl text-white">{stats?.cpu_usage !== undefined ? `${stats.cpu_usage}%` : '...'}</span>
              </div>
              <div className="h-4 w-full bg-black/40 rounded-full overflow-hidden border border-white/5 relative">
                <motion.div 
                  initial={{ width: 0 }}
                  animate={{ width: stats?.cpu_usage ? `${Math.min(stats.cpu_usage, 100)}%` : 0 }}
                  transition={{ type: "spring", bounce: 0, duration: 1 }}
                  className="absolute top-0 left-0 h-full bg-indigo-500 rounded-full"
                />
              </div>
            </div>
            <div className="col-span-2 lg:col-span-2 bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4 sm:p-6 flex flex-col justify-center gap-4 sm:gap-6 shadow-xl">
              <div className="flex justify-between items-center text-slate-400 mb-2">
                <span className="flex items-center gap-2 font-medium text-white"><Database className="w-5 h-5 text-emerald-400"/> RAM Usage</span>
                <span className="font-mono text-xl text-white">{stats?.ram_usage_mb !== undefined ? `${stats.ram_usage_mb} MB` : '...'}</span>
              </div>
              <div className="h-4 w-full bg-black/40 rounded-full overflow-hidden border border-white/5 relative">
                <motion.div 
                  initial={{ width: 0 }}
                  animate={{ width: stats?.ram_usage_mb ? `${Math.min((stats.ram_usage_mb / 512) * 100, 100)}%` : 0 }}
                  transition={{ type: "spring", bounce: 0, duration: 1 }}
                  className="absolute top-0 left-0 h-full bg-emerald-500 rounded-full"
                />
              </div>
            </div>
          </>
        )}
      </main>

      {/* Terminal Log View — only visible if user has can_view_logs */}
      {user.can_view_logs && (
        <section className="bg-[#0a0a0c] border border-white/10 rounded-2xl shadow-xl overflow-hidden flex flex-col h-64 sm:h-96">
          <div className="bg-white/5 px-4 sm:px-6 py-3 sm:py-4 border-b border-white/10 flex justify-between items-center">
            <span className="font-mono text-xs sm:text-sm text-slate-400 flex items-center gap-2">
               <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" /> Live Terminal
            </span>
          </div>
          <div className="flex-1 overflow-y-auto p-3 sm:p-6 font-mono text-xs sm:text-sm leading-relaxed space-y-1" onScroll={handleLogScroll}>
            {logs.map((log, i) => (
              <div key={`log-${i}`} className="text-slate-300 break-words">
                <LogLine text={log} />
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        </section>
      )}

      {/* User Management Panel (admin only) */}
      {user.is_admin && <UserManagementPanel />}

      {/* Connection State Overlay */}
      <AnimatePresence>
        {showDisconnect && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xl"
          >
            <div className="flex flex-col items-center gap-4 bg-white/5 p-12 rounded-3xl border border-white/10 shadow-2xl">
              <Disc3 className="w-16 h-16 text-brand-500 animate-spin" />
              <div className="text-center">
                <h2 className="text-2xl font-bold text-white mb-2">Connection Lost</h2>
                <p className="text-slate-400">Reconnecting to Dashboard Server...</p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Restart Confirmation Modal */}
      <AnimatePresence>
        {isRestartModalOpen && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-md"
            onClick={() => setIsRestartModalOpen(false)}
            role="dialog"
            aria-modal="true"
            aria-labelledby="restart-title"
          >
            <motion.div 
              initial={{ scale: 0.9, y: 20 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.9, y: 20 }}
              className="bg-slate-900 border border-white/10 p-8 rounded-3xl max-w-sm w-full shadow-2xl m-4"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="w-16 h-16 bg-red-500/10 rounded-2xl flex items-center justify-center mb-6 border border-red-500/20 mx-auto">
                <AlertTriangle className="w-8 h-8 text-red-500" />
              </div>
              <h2 id="restart-title" className="text-2xl font-bold text-white text-center mb-2">Restart Bot?</h2>
              <p className="text-slate-400 text-center mb-8">
                This will temporarily disconnect the bot from Discord and interrupt active music sessions. Are you sure?
              </p>
              <div className="flex gap-4">
                <button 
                  ref={cancelBtnRef}
                  onClick={() => setIsRestartModalOpen(false)}
                  className="flex-1 px-4 py-3 bg-white/5 hover:bg-white/10 text-white font-medium rounded-xl transition-colors border border-white/5"
                >
                  Cancel
                </button>
                <button 
                  onClick={confirmRestart}
                  className="flex-1 px-4 py-3 bg-red-500 hover:bg-red-500/90 text-white font-medium rounded-xl transition-colors"
                >
                  Restart
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Logout Confirmation Modal */}
      <AnimatePresence>
        {isLogoutModalOpen && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-md"
            onClick={() => setIsLogoutModalOpen(false)}
          >
            <motion.div 
              initial={{ scale: 0.9, y: 20 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.9, y: 20 }}
              className="bg-slate-900 border border-white/10 p-8 rounded-3xl max-w-sm w-full shadow-2xl m-4"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="w-16 h-16 bg-red-500/10 rounded-2xl flex items-center justify-center mb-6 border border-red-500/20 mx-auto">
                <LogOut className="w-8 h-8 text-red-500" />
              </div>
              <h2 className="text-2xl font-bold text-white text-center mb-2">Logout?</h2>
              <p className="text-slate-400 text-center mb-8">
                Are you sure you want to sign out of the dashboard?
              </p>
              <div className="flex gap-4">
                <button 
                  onClick={() => setIsLogoutModalOpen(false)}
                  className="flex-1 px-4 py-3 bg-white/5 hover:bg-white/10 text-white font-medium rounded-xl transition-colors border border-white/5"
                >
                  Cancel
                </button>
                <button 
                  onClick={confirmLogout}
                  className="flex-1 px-4 py-3 bg-red-500 hover:bg-red-500/90 text-white font-medium rounded-xl transition-colors"
                >
                  Logout
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode, label: string, value?: number | string }) {
  return (
    <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-3 sm:p-6 shadow-xl flex items-center gap-3 sm:gap-5 hover:bg-white/10 transition-colors">
      <div className="p-2.5 sm:p-4 bg-black/20 rounded-xl border border-white/5 shrink-0">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-slate-400 text-xs sm:text-sm font-medium truncate">{label}</p>
        <p className="text-xl sm:text-2xl font-semibold text-white mt-0.5 sm:mt-1">
          {value !== undefined ? value : <span className="opacity-50">...</span>}
        </p>
      </div>
    </div>
  );
}
