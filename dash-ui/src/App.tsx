import { useState, useEffect } from 'react';
import { Lock, LogIn, Disc3, User, Eye, EyeOff } from 'lucide-react';
import Dashboard from './Dashboard';

export interface DashUser {
  username: string;
  is_admin: boolean;
  can_restart: boolean;
  can_view_logs: boolean;
}

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [user, setUser] = useState<DashUser | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    // Check initial auth status by calling /api/me
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
        setError(data.error || 'Invalid credentials');
      }
    } catch {
      setError('Connection failed. Is the bot running?');
    }
    setLoading(false);
  };

  const handleLogout = () => {
    setIsAuthenticated(false);
    setUser(null);
    setUsername('');
    setPassword('');
  };

  if (isAuthenticated === null) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Disc3 className="w-12 h-12 text-brand-500 animate-spin" />
      </div>
    );
  }

  if (isAuthenticated && user) {
    return <Dashboard user={user} onLogout={handleLogout} />;
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 overflow-hidden relative">
      {/* Dynamic Background Circles */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brand-500/20 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-purple-500/20 rounded-full blur-3xl pointer-events-none" />

      <form 
        onSubmit={handleLogin}
        className="relative z-10 w-full max-w-md bg-white/5 backdrop-blur-xl border border-white/10 p-8 rounded-2xl shadow-2xl flex flex-col items-center"
      >
        <div className="w-16 h-16 bg-brand-500/20 rounded-2xl flex items-center justify-center mb-6 border border-brand-500/30">
          <Lock className="w-8 h-8 text-brand-500" />
        </div>
        
        <h1 className="text-3xl font-semibold mb-2 text-white">Music Bot</h1>
        <p className="text-slate-400 mb-8 text-center">Sign in to access the bot dashboard.</p>

        <div className="w-full space-y-4">
          <div className="relative">
            <User className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500 pointer-events-none" />
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Username"
              autoComplete="username"
              className="w-full bg-black/30 border border-white/10 rounded-xl pl-11 pr-4 py-3 text-white placeholder:text-slate-500 focus:outline-none focus:border-brand-500 transition-colors"
            />
          </div>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500 pointer-events-none" />
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              autoComplete="current-password"
              className="w-full bg-black/30 border border-white/10 rounded-xl pl-11 pr-11 py-3 text-white placeholder:text-slate-500 focus:outline-none focus:border-brand-500 transition-colors"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white transition-colors cursor-pointer"
              tabIndex={-1}
            >
              {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
            </button>
          </div>
          {error && <p className="text-red-400 font-medium text-sm px-1">{error}</p>}
          
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-brand-500 hover:bg-brand-500/90 text-white font-medium py-3 rounded-xl transition-colors flex items-center justify-center gap-2 mt-4 cursor-pointer"
          >
            {loading ? <Disc3 className="w-5 h-5 animate-spin" /> : <LogIn className="w-5 h-5" />}
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default App;
