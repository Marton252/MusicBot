import { useEffect } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { AlertTriangle, X } from 'lucide-react';
import type { Copy } from '../i18n';

interface ConfirmDialogProps {
  title: string;
  body: string;
  confirmLabel: string;
  tone?: 'danger' | 'default';
  t: Copy;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ConfirmDialog({ title, body, confirmLabel, tone = 'default', t, onCancel, onConfirm }: ConfirmDialogProps) {
  const confirmClass = tone === 'danger' ? 'bg-danger hover:bg-danger/90' : 'bg-accent hover:bg-accent-strong';
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onCancel]);

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      initial={reduceMotion ? false : { opacity: 0 }}
      animate={reduceMotion ? undefined : { opacity: 1 }}
      exit={reduceMotion ? undefined : { opacity: 0 }}
      transition={{ duration: 0.16 }}
      onClick={onCancel}
    >
      <motion.div
        className="w-full max-w-sm rounded-lg border border-panel bg-surface p-5 shadow-panel"
        initial={reduceMotion ? false : { opacity: 0, scale: 0.98, y: 10 }}
        animate={reduceMotion ? undefined : { opacity: 1, scale: 1, y: 0 }}
        exit={reduceMotion ? undefined : { opacity: 0, scale: 0.98, y: 10 }}
        transition={{ duration: 0.18, ease: 'easeOut' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md border border-danger/30 bg-danger/10">
              <AlertTriangle className="h-5 w-5 text-red-300" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">{title}</h2>
              <p className="mt-1 text-sm text-muted">{body}</p>
            </div>
          </div>
          <button type="button" onClick={onCancel} className="rounded-md p-1 text-muted hover:bg-panel hover:text-white" aria-label={t.cancel}>
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="rounded-md border border-panel px-4 py-2 text-sm font-medium text-muted hover:bg-panel hover:text-white">
            {t.cancel}
          </button>
          <button type="button" onClick={onConfirm} className={`rounded-md px-4 py-2 text-sm font-semibold text-white ${confirmClass}`}>
            {confirmLabel}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
