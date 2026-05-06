import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { Eye, EyeOff, Pencil, Plus, Shield, ShieldCheck, Trash2, X } from 'lucide-react';
import type { Copy } from '../i18n';
import type { DashboardUser } from '../types';
import { ConfirmDialog } from './ConfirmDialog';

interface UserFormData {
  username: string;
  password: string;
  can_restart: boolean;
  can_view_logs: boolean;
}

function Toggle({ enabled, disabled, onToggle }: { enabled: boolean; disabled?: boolean; onToggle: () => void }) {
  const trackClass = disabled ? 'border border-panel bg-app' : enabled ? 'bg-accent' : 'bg-panel';

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onToggle}
      className={`relative h-5 w-9 shrink-0 rounded-full transition focus:outline-none focus:ring-2 focus:ring-accent/60 ${trackClass} ${disabled ? 'cursor-not-allowed opacity-70' : ''}`}
      aria-pressed={enabled}
    >
      <span className={`absolute top-0.5 h-4 w-4 rounded-full transition ${disabled ? 'bg-muted' : 'bg-white'} ${enabled ? 'left-4' : 'left-0.5'}`} />
    </button>
  );
}

function PasswordCell({ user, t }: { user: DashboardUser; t: Copy }) {
  const [visible, setVisible] = useState(false);
  const password = user.password_display || '';
  const canReveal = Boolean(password);

  return (
    <div className="flex min-w-0 items-center justify-end gap-2">
      <code className="min-w-0 max-w-36 truncate rounded bg-app px-2 py-1 text-xs text-muted">
        {canReveal ? (visible ? password : '********') : t.noPasswordStored}
      </code>
      <button
        type="button"
        disabled={!canReveal}
        onClick={() => setVisible((v) => !v)}
        className="shrink-0 rounded-md p-1.5 text-muted hover:bg-panel hover:text-white focus:outline-none focus:ring-2 focus:ring-accent/60 disabled:cursor-not-allowed disabled:opacity-40"
        title={visible ? t.hidePassword : t.showPassword}
      >
        {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

function UserFormModal({
  title,
  initial,
  isEdit,
  t,
  onClose,
  onSave,
}: {
  title: string;
  initial?: DashboardUser;
  isEdit?: boolean;
  t: Copy;
  onClose: () => void;
  onSave: (data: UserFormData) => Promise<string | null>;
}) {
  const [form, setForm] = useState<UserFormData>(() => ({
    username: initial?.username ?? '',
    password: '',
    can_restart: initial?.can_restart ?? false,
    can_view_logs: initial?.can_view_logs ?? true,
  }));
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const reduceMotion = useReducedMotion();

  const passwordLabel = isEdit ? t.newPasswordOptional : t.createPassword;

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    const result = await onSave(form);
    setSaving(false);
    if (result) setError(result);
  };

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      initial={reduceMotion ? false : { opacity: 0 }}
      animate={reduceMotion ? undefined : { opacity: 1 }}
      exit={reduceMotion ? undefined : { opacity: 0 }}
      transition={{ duration: 0.16 }}
      onClick={onClose}
    >
      <motion.form
        className="w-full max-w-md rounded-lg border border-panel bg-surface p-5 shadow-panel"
        onSubmit={submit}
        onClick={(e) => e.stopPropagation()}
        initial={reduceMotion ? false : { opacity: 0, scale: 0.98, y: 10 }}
        animate={reduceMotion ? undefined : { opacity: 1, scale: 1, y: 0 }}
        exit={reduceMotion ? undefined : { opacity: 0, scale: 0.98, y: 10 }}
        transition={{ duration: 0.18, ease: 'easeOut' }}
      >
        <div className="mb-5 flex items-center justify-between gap-4">
          <h2 className="text-lg font-semibold text-white">{title}</h2>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-muted hover:bg-panel hover:text-white focus:outline-none focus:ring-2 focus:ring-accent/60" aria-label={t.cancel}>
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="grid gap-4">
          <label className="grid gap-2 text-sm font-medium text-muted">
            {t.username}
            <input
              value={form.username}
              onChange={(e) => setForm((prev) => ({ ...prev, username: e.target.value }))}
              className="rounded-md border border-panel bg-app px-3 py-2.5 text-white outline-none focus:border-accent"
              required
            />
          </label>

          <label className="grid gap-2 text-sm font-medium text-muted">
            {passwordLabel}
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm((prev) => ({ ...prev, password: e.target.value }))}
              className="rounded-md border border-panel bg-app px-3 py-2.5 text-white outline-none focus:border-accent"
              required={!isEdit}
            />
          </label>

          <div className="grid gap-3 rounded-lg border border-panel bg-app p-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted">{t.permissions}</div>
            <label className="flex items-center justify-between gap-3 text-sm text-white">
              {t.canRestart}
              <Toggle enabled={form.can_restart} onToggle={() => setForm((prev) => ({ ...prev, can_restart: !prev.can_restart }))} />
            </label>
            <label className="flex items-center justify-between gap-3 text-sm text-white">
              {t.canViewLogs}
              <Toggle enabled={form.can_view_logs} onToggle={() => setForm((prev) => ({ ...prev, can_view_logs: !prev.can_view_logs }))} />
            </label>
          </div>
        </div>

        {error && <p className="mt-4 rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-red-200">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-panel px-4 py-2 text-sm font-medium text-muted hover:bg-panel hover:text-white focus:outline-none focus:ring-2 focus:ring-accent/60">
            {t.cancel}
          </button>
          <button type="submit" disabled={saving} className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong focus:outline-none focus:ring-2 focus:ring-accent/60 disabled:opacity-60">
            {isEdit ? t.save : t.create}
          </button>
        </div>
      </motion.form>
    </motion.div>
  );
}

export function UserManagementPanel({ t }: { t: Copy }) {
  const reduceMotion = useReducedMotion();
  const [users, setUsers] = useState<DashboardUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editUser, setEditUser] = useState<DashboardUser | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DashboardUser | null>(null);

  const sortedUsers = useMemo(() => [...users].sort((a, b) => Number(b.is_admin) - Number(a.is_admin) || a.username.localeCompare(b.username)), [users]);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/users');
      if (res.ok) setUsers(await res.json());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/users');
        if (res.ok && !cancelled) setUsers(await res.json());
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const updateUser = async (user: DashboardUser, payload: Partial<UserFormData>) => {
    const res = await fetch(`/api/users/${user.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Protection': '1' },
      body: JSON.stringify(payload),
    });
    if (res.ok) await fetchUsers();
  };

  const deleteUser = async () => {
    if (!deleteTarget) return;
    const res = await fetch(`/api/users/${deleteTarget.id}`, { method: 'DELETE', headers: { 'X-CSRF-Protection': '1' } });
    if (res.ok) setUsers((prev) => prev.filter((u) => u.id !== deleteTarget.id));
    setDeleteTarget(null);
  };

  return (
    <motion.section
      className="rounded-lg border border-panel bg-surface shadow-panel"
      initial={reduceMotion ? false : { opacity: 0, y: 10 }}
      animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
    >
      <div className="flex items-center justify-between gap-3 border-b border-panel px-4 py-3">
        <div className="flex items-center gap-2">
          <Shield className="h-4 w-4 text-accent" />
          <h2 className="text-sm font-semibold uppercase tracking-wide text-white">{t.userManagement}</h2>
        </div>
        <button
          type="button"
          onClick={() => setShowAddModal(true)}
          className="inline-flex max-w-[45%] items-center gap-2 rounded-md bg-accent px-3 py-2 text-sm font-semibold text-white hover:bg-accent-strong focus:outline-none focus:ring-2 focus:ring-accent/60 sm:max-w-none"
        >
          <Plus className="h-4 w-4 shrink-0" />
          <span className="hidden truncate sm:inline">{t.addUser}</span>
          <span className="truncate sm:hidden">{t.addUserShort}</span>
        </button>
      </div>

      {loading ? (
        <div className="p-6 text-sm text-muted">{t.collecting}</div>
      ) : sortedUsers.length === 0 ? (
        <div className="p-6 text-sm text-muted">{t.noUsers}</div>
      ) : (
        <>
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full text-sm">
              <thead className="border-b border-panel text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-4 py-3 text-left">{t.user}</th>
                  <th className="px-4 py-3 text-center">{t.canRestart}</th>
                  <th className="px-4 py-3 text-center">{t.canViewLogs}</th>
                  <th className="px-4 py-3 text-right">{t.decryptedPassword}</th>
                  <th className="px-4 py-3 text-right">{t.actions}</th>
                </tr>
              </thead>
              <tbody>
                {sortedUsers.map((user) => (
                  <motion.tr
                    key={user.id}
                    className="border-b border-panel last:border-b-0"
                    initial={reduceMotion ? false : { opacity: 0 }}
                    animate={reduceMotion ? undefined : { opacity: 1 }}
                    transition={{ duration: 0.16 }}
                  >
                    <td className="px-4 py-3">
                      <div className="flex min-w-0 items-center gap-2 text-white">
                        {user.is_admin ? <ShieldCheck className="h-4 w-4 text-accent" /> : <span className="h-4 w-4 rounded-full bg-panel" />}
                        <span className="min-w-0 max-w-80 truncate font-medium">{user.username}</span>
                        {user.is_admin && <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-bold uppercase text-red-100">{t.admin}</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <Toggle enabled={user.can_restart} disabled={user.is_admin} onToggle={() => updateUser(user, { can_restart: !user.can_restart })} />
                    </td>
                    <td className="px-4 py-3 text-center">
                      <Toggle enabled={user.can_view_logs} disabled={user.is_admin} onToggle={() => updateUser(user, { can_view_logs: !user.can_view_logs })} />
                    </td>
                    <td className="px-4 py-3">
                      <PasswordCell user={user} t={t} />
                    </td>
                    <td className="px-4 py-3">
                      {!user.is_admin && (
                        <div className="flex justify-end gap-1">
                          <button type="button" onClick={() => setEditUser(user)} className="rounded-md p-2 text-muted hover:bg-panel hover:text-white focus:outline-none focus:ring-2 focus:ring-accent/60" title={t.edit}>
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button type="button" onClick={() => setDeleteTarget(user)} className="rounded-md p-2 text-red-300 hover:bg-danger/10 hover:text-red-100 focus:outline-none focus:ring-2 focus:ring-danger/60" title={t.delete}>
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      )}
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid gap-3 p-3 md:hidden">
            {sortedUsers.map((user) => (
              <motion.div
                key={user.id}
                className="rounded-lg border border-panel bg-app p-3"
                initial={reduceMotion ? false : { opacity: 0, y: 6 }}
                animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
                transition={{ duration: 0.16 }}
              >
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2 text-white">
                    {user.is_admin ? <ShieldCheck className="h-4 w-4 text-accent" /> : <span className="h-4 w-4 rounded-full bg-panel" />}
                    <span className="min-w-0 break-words font-medium">{user.username}</span>
                    {user.is_admin && <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-bold uppercase text-red-100">{t.admin}</span>}
                  </div>
                  {!user.is_admin && (
                    <div className="flex shrink-0 gap-1">
                      <button type="button" onClick={() => setEditUser(user)} className="rounded-md p-1.5 text-muted hover:bg-panel hover:text-white focus:outline-none focus:ring-2 focus:ring-accent/60" title={t.edit}>
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button type="button" onClick={() => setDeleteTarget(user)} className="rounded-md p-1.5 text-red-300 hover:bg-danger/10 focus:outline-none focus:ring-2 focus:ring-danger/60" title={t.delete}>
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  )}
                </div>
                <div className="grid gap-3 text-sm">
                  <div className="flex items-center justify-between gap-3 text-muted">
                    {t.canRestart}
                    <Toggle enabled={user.can_restart} disabled={user.is_admin} onToggle={() => updateUser(user, { can_restart: !user.can_restart })} />
                  </div>
                  <div className="flex items-center justify-between gap-3 text-muted">
                    {t.canViewLogs}
                    <Toggle enabled={user.can_view_logs} disabled={user.is_admin} onToggle={() => updateUser(user, { can_view_logs: !user.can_view_logs })} />
                  </div>
                  <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 text-muted">
                    <span className="min-w-0 truncate">{t.decryptedPassword}</span>
                    <PasswordCell user={user} t={t} />
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </>
      )}

      <AnimatePresence>
        {showAddModal && (
          <UserFormModal
            title={t.addUser}
            t={t}
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

      <AnimatePresence>
        {editUser && (
          <UserFormModal
            title={`${t.editUser}: ${editUser.username}`}
            initial={editUser}
            isEdit
            t={t}
            onClose={() => setEditUser(null)}
            onSave={async (data) => {
              const payload: Partial<UserFormData> = {};
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

      <AnimatePresence>
        {deleteTarget && (
          <ConfirmDialog
            title={t.confirmDelete}
            body={t.confirmDeleteBody}
            confirmLabel={t.delete}
            tone="danger"
            t={t}
            onCancel={() => setDeleteTarget(null)}
            onConfirm={deleteUser}
          />
        )}
      </AnimatePresence>
    </motion.section>
  );
}
