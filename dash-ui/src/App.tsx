import { useEffect, useMemo, useState } from 'react';
import { Disc3, Eye, EyeOff, Languages, Lock, LogIn, User } from 'lucide-react';
import Dashboard from './Dashboard';
import { copy, getInitialLanguage } from './i18n';
import type { DashUser, Language } from './types';

function LanguageSwitch({ language, onChange }: { language: Language; onChange: (language: Language) => void }) {
  return (
    <div className="inline-flex items-center gap-1 rounded-md border border-panel bg-surface p-1 text-xs text-muted">
      <Languages className="h-4 w-4" />
      {(['en', 'hu'] as const).map((lang) => (
        <button
          key={lang}
          type="button"
          onClick={() => onChange(lang)}
          className={`rounded px-2 py-1 font-semibold uppercase transition ${
            language === lang ? 'bg-accent text-white' : 'hover:bg-panel hover:text-white'
          }`}
        >
          {lang}
        </button>
      ))}
    </div>
  );
}

function App() {
  const [language, setLanguageState] = useState<Language>(getInitialLanguage);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [user, setUser] = useState<DashUser | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const t = useMemo(() => copy[language], [language]);

  const setLanguage = (next: Language) => {
    setLanguageState(next);
    localStorage.setItem('dashboard_language', next);
  };

  useEffect(() => {
    fetch('/api/me')
      .then(async (res) => {
        if (res.ok) {
          const data = await res.json();
          setUser(data);
          setIsAuthenticated(true);
        } else {
          setIsAuthenticated(false);
        }
      })
      .catch(() => setIsAuthenticated(false));
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data.user);
        setIsAuthenticated(true);
      } else {
        const data = await res.json();
        setError(data.error || t.invalidCredentials);
      }
    } catch {
      setError(t.connectionFailed);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    setIsAuthenticated(false);
    setUser(null);
    setUsername('');
    setPassword('');
  };

  if (isAuthenticated === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-app">
        <div className="flex items-center gap-3 rounded-lg border border-panel bg-surface px-4 py-3 text-sm text-muted">
          <Disc3 className="h-5 w-5 animate-spin text-accent" />
          {t.loading}
        </div>
      </div>
    );
  }

  if (isAuthenticated && user) {
    return <Dashboard language={language} onLanguageChange={setLanguage} user={user} onLogout={handleLogout} />;
  }

  return (
    <div className="min-h-screen bg-app px-4 py-6 text-white">
      <div className="mx-auto flex w-full max-w-md justify-end">
        <LanguageSwitch language={language} onChange={setLanguage} />
      </div>

      <div className="mx-auto mt-16 w-full max-w-md rounded-lg border border-panel bg-surface p-6 shadow-panel sm:p-8">
        <form onSubmit={handleLogin} className="flex flex-col gap-5">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-md border border-panel bg-panel">
              <Lock className="h-5 w-5 text-accent" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">{t.signInTitle}</h1>
              <p className="text-sm text-muted">{t.signInSubtitle}</p>
            </div>
          </div>

          <label className="grid gap-2 text-sm font-medium text-muted">
            {t.username}
            <span className="relative">
              <User className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                className="w-full rounded-md border border-panel bg-app py-3 pl-10 pr-3 text-white outline-none transition focus:border-accent"
              />
            </span>
          </label>

          <label className="grid gap-2 text-sm font-medium text-muted">
            {t.password}
            <span className="relative">
              <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                className="w-full rounded-md border border-panel bg-app py-3 pl-10 pr-10 text-white outline-none transition focus:border-accent"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted transition hover:text-white"
                aria-label={showPassword ? t.hidePassword : t.showPassword}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </span>
          </label>

          {error && <p className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-red-200">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-white transition hover:bg-accent-strong disabled:opacity-60"
          >
            {loading ? <Disc3 className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />}
            {loading ? t.signingIn : t.signIn}
          </button>
        </form>
      </div>
    </div>
  );
}

export default App;
export type { DashUser };
