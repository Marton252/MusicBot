import { Activity, Languages, LogOut, RefreshCw } from 'lucide-react';
import type { Copy } from '../i18n';
import type { DashUser, Language, Stats } from '../types';

interface TopBarProps {
  user: DashUser;
  stats: Stats | null;
  language: Language;
  t: Copy;
  onLanguageChange: (language: Language) => void;
  onRestart: () => void;
  onLogout: () => void;
}

export function TopBar({ user, stats, language, t, onLanguageChange, onRestart, onLogout }: TopBarProps) {
  return (
    <header className="border-b border-panel bg-app/95 backdrop-blur lg:sticky lg:top-0 lg:z-20">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-3 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-panel bg-surface">
            <Activity className="h-5 w-5 text-accent" />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold tracking-tight text-white">{t.appName}</h1>
            <p className="hidden truncate text-xs text-muted sm:block">
              {t.signedInAs} {user.username} - {t.uptime}: {stats?.uptime ?? '...'}
            </p>
            <p className="max-w-[220px] truncate text-xs text-muted sm:hidden">{user.username}</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex items-center gap-1 rounded-md border border-panel bg-surface p-1 text-xs text-muted">
            <Languages className="h-4 w-4" />
            {(['en', 'hu'] as const).map((lang) => (
              <button
                key={lang}
                type="button"
                onClick={() => onLanguageChange(lang)}
                className={`rounded px-2 py-1 font-semibold uppercase transition ${
                  language === lang ? 'bg-accent text-white' : 'hover:bg-panel hover:text-white'
                }`}
              >
                {lang}
              </button>
            ))}
          </div>

          {user.can_restart && (
            <button
              type="button"
              onClick={onRestart}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-panel bg-surface px-3 text-sm font-medium text-white hover:bg-panel"
            >
              <RefreshCw className="h-4 w-4" />
              <span className="hidden sm:inline">{t.restartBot}</span>
              <span className="sm:hidden">{t.restartShort}</span>
            </button>
          )}

          <button
            type="button"
            onClick={onLogout}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-danger/30 bg-danger/10 px-3 text-sm font-medium text-red-100 hover:bg-danger/20"
          >
            <LogOut className="h-4 w-4" />
            {t.logout}
          </button>
        </div>
      </div>
    </header>
  );
}
