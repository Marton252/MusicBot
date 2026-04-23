import asyncio
import base64
import datetime
import hashlib
import hmac
import logging
import os
import re
import time
from collections import deque

import bcrypt
import psutil
from cryptography.fernet import Fernet, InvalidToken
from quart import Quart, request, jsonify, redirect, make_response, websocket, send_from_directory


# ─── Log Capture Handler ────────────────────────────────────────────────────────

class MemoryLogHandler(logging.Handler):
    def __init__(self, capacity: int = 500) -> None:
        super().__init__()
        self.capacity = capacity
        self.logs: deque[str] = deque(maxlen=capacity)
        self.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.logs.append(msg)
        except Exception:
            self.handleError(record)


mem_log_handler = MemoryLogHandler()


# ─── Rate Limiter ────────────────────────────────────────────────────────────────

class RateLimiter:
    """In-memory rate limiter with exponential backoff.

    After ``max_attempts`` failed logins within ``window_seconds``, the
    key is locked out.  Each subsequent block doubles the window up to
    ``max_window_seconds`` to discourage sustained brute-force.
    """

    def __init__(
        self,
        max_attempts: int = 3,
        window_seconds: int = 300,
        max_window_seconds: int = 3600,
    ) -> None:
        self.max_attempts = max_attempts
        self.base_window = window_seconds
        self.max_window = max_window_seconds
        self._attempts: dict[str, list[float]] = {}
        self._lockout_until: dict[str, float] = {}
        self._lockout_count: dict[str, int] = {}

    def _cleanup(self, now: float) -> None:
        """Evict expired entries to prevent unbounded memory growth."""
        expired = [
            k for k, v in self._attempts.items()
            if all(now - t >= self.base_window for t in v)
        ]
        for k in expired:
            del self._attempts[k]
            self._lockout_until.pop(k, None)
            self._lockout_count.pop(k, None)

    def is_rate_limited(self, key: str) -> bool:
        now = time.monotonic()
        self._cleanup(now)

        # Check exponential lockout
        if key in self._lockout_until and now < self._lockout_until[key]:
            return True

        attempts = self._attempts.get(key, [])
        attempts = [t for t in attempts if now - t < self.base_window]
        self._attempts[key] = attempts
        return len(attempts) >= self.max_attempts

    def record_attempt(self, key: str) -> None:
        now = time.monotonic()
        if key not in self._attempts:
            self._attempts[key] = []
        self._attempts[key].append(now)

        # Trigger exponential lockout when threshold exceeded
        recent = [t for t in self._attempts[key] if now - t < self.base_window]
        if len(recent) >= self.max_attempts:
            count = self._lockout_count.get(key, 0) + 1
            self._lockout_count[key] = count
            lockout_secs = min(self.base_window * (2 ** (count - 1)), self.max_window)
            self._lockout_until[key] = now + lockout_secs


# ─── HMAC-Signed Session Cookie (with user identity) ────────────────────────────

class CookieSigner:
    """Stateless session via HMAC-signed cookies with embedded user identity.
    Token format: timestamp:username:is_admin:can_restart:can_view_logs.signature
    Survives restarts because there is no server-side session store."""

    def __init__(self, secret: str, max_age: int = 2592000) -> None:
        self._key = hashlib.sha256(f'cookie-signer-{secret}'.encode('utf-8')).digest()
        self.max_age = max_age

    def create_token(
        self, username: str, is_admin: bool, can_restart: bool, can_view_logs: bool
    ) -> str:
        """Create a signed token encoding user identity and permissions."""
        payload = f"{int(time.time())}:{username}:{int(is_admin)}:{int(can_restart)}:{int(can_view_logs)}"
        sig = hmac.new(self._key, payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}.{sig}"

    def decode_token(self, token: str | None) -> dict | None:
        """Verify signature, check expiration, and decode user identity.
        Returns {username, is_admin, can_restart, can_view_logs} or None."""
        if not token or '.' not in token:
            return None
        try:
            payload, sig = token.rsplit('.', 1)
            expected = hmac.new(self._key, payload.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected):
                return None
            parts = payload.split(':')
            if len(parts) != 5:
                return None
            ts_str, username, is_admin, can_restart, can_view_logs = parts
            age = int(time.time()) - int(ts_str)
            if not (0 <= age <= self.max_age):
                return None
            return {
                'username': username,
                'is_admin': bool(int(is_admin)),
                'can_restart': bool(int(can_restart)),
                'can_view_logs': bool(int(can_view_logs)),
            }
        except (ValueError, TypeError):
            return None


# ─── Validation helpers ──────────────────────────────────────────────────────────

USERNAME_RE = re.compile(r'^[a-zA-Z0-9_-]{3,32}$')
MIN_PASSWORD_LENGTH = 6


def _validate_username(username: str) -> str | None:
    """Returns an error string if invalid, else None."""
    if not username or not USERNAME_RE.match(username):
        return 'Username must be 3-32 characters (letters, numbers, _ or -).'
    return None


def _validate_password(password: str) -> str | None:
    """Returns an error string if invalid, else None."""
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        return f'Password must be at least {MIN_PASSWORD_LENGTH} characters.'
    return None


def _hash_password(password: str) -> str:
    """Hash a password with bcrypt (cost factor 12)."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')


def _check_password(password: str, password_hash: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


def _make_fernet(secret_key: str) -> Fernet:
    """Derive a Fernet key from the dashboard secret key."""
    derived = hashlib.sha256(f'fernet-{secret_key}'.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def _encrypt_password(fernet: Fernet, password: str) -> str:
    """Encrypt a password for storage. Returns base64 ciphertext."""
    return fernet.encrypt(password.encode('utf-8')).decode('utf-8')


def _decrypt_password(fernet: Fernet, ciphertext: str) -> str:
    """Decrypt a stored password. Returns 'N/A' on failure."""
    if not ciphertext:
        return ''
    try:
        return fernet.decrypt(ciphertext.encode('utf-8')).decode('utf-8')
    except (InvalidToken, Exception):
        return 'N/A'


# ─── Dashboard Server ────────────────────────────────────────────────────────────

class DashboardServer:

    def __init__(
        self,
        bot,
        port: int,
        admin_user: str,
        admin_password: str,
        cert_path: str = 'certs/cert.pem',
        key_path: str = 'certs/key.pem',
        bind: str = '127.0.0.1',
    ) -> None:
        self.bot = bot
        self.port = port
        self.admin_user = admin_user
        self.admin_password = admin_password
        self.cert_path = cert_path
        self.key_path = key_path
        self.bind = bind
        self.app = Quart(__name__)
        self.app.config['MAX_CONTENT_LENGTH'] = 16 * 1024  # 16 KB — enough for login/user JSON

        # Use dedicated secret key for cookie signing (not the admin password)
        from config import DASHBOARD_SECRET_KEY
        self.signer = CookieSigner(secret=DASHBOARD_SECRET_KEY)
        self.fernet = _make_fernet(DASHBOARD_SECRET_KEY)
        self.login_limiter = RateLimiter(max_attempts=3, window_seconds=300)

        self.start_time = datetime.datetime.now(datetime.UTC)
        self._process = psutil.Process(os.getpid())

        # Prime psutil cpu_percent for per-process measurement
        self._process.cpu_percent(interval=None)

        # Server-side stats history — survives page refresh / logout
        self._stats_history: deque[tuple[float, float, int]] = deque(maxlen=86400)

        # Stats cache (avoid redundant syscalls when multiple WS clients connected)
        self._stats_cache: dict | None = None
        self._stats_cache_time: float = 0.0

        self.setup_routes()

    async def _init_admin(self) -> None:
        """Hash admin password and upsert into DB at startup."""
        hashed = _hash_password(self.admin_password)
        await self.bot.db.upsert_admin_user(self.admin_user, hashed)

    def _get_stats(self) -> dict:
        """Gather system stats — cached for 1 second to avoid redundant syscalls."""
        now = time.monotonic()
        if self._stats_cache and (now - self._stats_cache_time) < 1.0:
            return self._stats_cache

        ram_mb = self._process.memory_info().rss / 1024 / 1024
        users = sum(g.member_count for g in self.bot.guilds if g.member_count)
        uptime = str(datetime.datetime.now(datetime.UTC) - self.start_time).split('.')[0]

        self._stats_cache = {
            'ping': round(self.bot.latency * 1000),
            'guilds': len(self.bot.guilds),
            'users': users,
            'voice_clients': len(self.bot.voice_clients),
            'ram_usage_mb': round(ram_mb, 1),
            'cpu_usage': self._process.cpu_percent(interval=None),
            'uptime': uptime,
        }
        self._stats_cache_time = now
        return self._stats_cache

    def _get_client_ip(self) -> str:
        """Return the real client IP, respecting X-Forwarded-For behind a proxy."""
        forwarded = request.headers.get('X-Forwarded-For', '')
        if forwarded:
            # X-Forwarded-For: client, proxy1, proxy2 — take the first
            return forwarded.split(',')[0].strip()
        return request.headers.get('CF-Connecting-IP', '') or request.remote_addr or 'unknown'

    def setup_routes(self) -> None:
        @self.app.after_request
        async def add_security_headers(response):
            response.headers['Alt-Svc'] = f'h3=":{self.port}"; ma=86400'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            host = request.host
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' ajax.cloudflare.com static.cloudflareinsights.com; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "img-src 'self' data:; "
                f"connect-src 'self' wss://{host} ws://{host} https://cloudflareinsights.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "object-src 'none'; "
                "form-action 'self'; "
                "frame-ancestors 'none'"
            )
            if request.is_secure:
                response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
            return response

        @self.app.before_request
        async def auth_and_csrf_middleware():
            # --- CSRF protection: require custom header on mutating requests ---
            if request.method in ('POST', 'PUT', 'DELETE'):
                # /api/login is exempt (unauthenticated entry point)
                if request.path != '/api/login':
                    csrf_header = request.headers.get('X-CSRF-Protection', '')
                    if csrf_header != '1':
                        return jsonify({'error': 'CSRF check failed'}), 403

            # --- Auth: skip for unprotected paths ---
            unprotected_paths = ['/', '/api/login', '/favicon.ico']
            if request.path in unprotected_paths or request.path.startswith('/assets/'):
                return

            token = request.cookies.get('DASH_SESSION')
            token_user = self.signer.decode_token(token)
            if not token_user:
                if request.path.startswith('/api/'):
                    return jsonify({'error': 'Unauthorized'}), 401
                else:
                    return redirect('/')

            # --- HIGH-2 fix: re-validate against DB on every request ---
            db_user = await self.bot.db.get_dashboard_user(token_user['username'])
            if not db_user:
                # User was deleted — invalidate session
                resp = await make_response(jsonify({'error': 'Session invalidated'}), 401)
                resp.delete_cookie('DASH_SESSION')
                return resp

            # Use live DB permissions, not stale token permissions
            request.dash_user = {
                'username': db_user['username'],
                'is_admin': db_user['is_admin'],
                'can_restart': db_user['can_restart'],
                'can_view_logs': db_user['can_view_logs'],
            }

        # ─── Static file routes ──────────────────────────────────────────

        @self.app.route('/')
        async def handle_index():
            try:
                return await send_from_directory('dash-ui/dist', 'index.html')
            except FileNotFoundError:
                return "Dashboard UI not found. Did you run 'npm run build' inside dash-ui?", 404

        @self.app.route('/assets/<path:filename>')
        async def handle_assets(filename):
            try:
                return await send_from_directory('dash-ui/dist/assets', filename)
            except FileNotFoundError:
                return "Asset not found", 404

        # ─── Auth endpoints ──────────────────────────────────────────────

        @self.app.route('/api/login', methods=['POST'])
        async def api_login():
            client_ip = self._get_client_ip()

            if self.login_limiter.is_rate_limited(client_ip):
                return jsonify({'error': 'Too many attempts. Try again later.'}), 429

            try:
                data = await request.get_json()
            except Exception:
                return jsonify({'error': 'Invalid request body'}), 400

            self.login_limiter.record_attempt(client_ip)

            username = (data or {}).get('username', '').strip()
            password = (data or {}).get('password', '')

            if not username or not password:
                return jsonify({'error': 'Username and password are required.'}), 401

            # Look up user in DB
            db_user = await self.bot.db.get_dashboard_user(username)
            if not db_user or not _check_password(password, db_user['password_hash']):
                return jsonify({'error': 'Invalid username or password.'}), 401

            # Create signed token with user permissions
            token = self.signer.create_token(
                db_user['username'],
                db_user['is_admin'],
                db_user['can_restart'],
                db_user['can_view_logs'],
            )
            user_info = {
                'username': db_user['username'],
                'is_admin': db_user['is_admin'],
                'can_restart': db_user['can_restart'],
                'can_view_logs': db_user['can_view_logs'],
            }
            resp = await make_response(jsonify({'status': 'ok', 'user': user_info}))
            resp.set_cookie(
                'DASH_SESSION',
                token,
                max_age=2592000,
                httponly=True,
                secure=True,
                samesite='Strict',
            )
            return resp

        @self.app.route('/api/logout', methods=['POST'])
        async def api_logout():
            resp = await make_response(jsonify({'status': 'ok'}))
            resp.delete_cookie('DASH_SESSION')
            return resp

        @self.app.route('/api/me')
        async def api_me():
            """Return the current user's identity and permissions from the token."""
            user = request.dash_user
            return jsonify({
                'username': user['username'],
                'is_admin': user['is_admin'],
                'can_restart': user['can_restart'],
                'can_view_logs': user['can_view_logs'],
            })

        # ─── Stats & Logs endpoints ──────────────────────────────────────

        @self.app.route('/api/stats')
        async def api_stats():
            return jsonify(self._get_stats())

        @self.app.route('/api/logs')
        async def api_logs():
            if not request.dash_user.get('can_view_logs'):
                return jsonify({'error': 'Forbidden'}), 403
            return jsonify(list(mem_log_handler.logs))

        # ─── Bot action endpoints ────────────────────────────────────────

        @self.app.route('/api/action/restart', methods=['POST'])
        async def api_restart():
            if not request.dash_user.get('can_restart'):
                return jsonify({'error': 'Forbidden: you do not have restart permission.'}), 403
            asyncio.create_task(self._perform_restart())
            return jsonify({'status': 'restarting'})

        # ─── User management endpoints (admin only) ─────────────────────

        @self.app.route('/api/users')
        async def api_list_users():
            if not request.dash_user.get('is_admin'):
                return jsonify({'error': 'Forbidden'}), 403
            users = await self.bot.db.list_dashboard_users()
            # Decrypt passwords server-side for admin viewing
            for u in users:
                u['password_display'] = _decrypt_password(self.fernet, u.pop('password_encrypted', ''))
            return jsonify(users)

        @self.app.route('/api/users', methods=['POST'])
        async def api_create_user():
            if not request.dash_user.get('is_admin'):
                return jsonify({'error': 'Forbidden'}), 403

            try:
                data = await request.get_json()
            except Exception:
                return jsonify({'error': 'Invalid request body'}), 400

            username = (data or {}).get('username', '').strip()
            password = (data or {}).get('password', '')
            can_restart = bool((data or {}).get('can_restart', False))
            can_view_logs = bool((data or {}).get('can_view_logs', True))

            # Validate
            err = _validate_username(username)
            if err:
                return jsonify({'error': err}), 400
            err = _validate_password(password)
            if err:
                return jsonify({'error': err}), 400

            # Check if username already exists
            existing = await self.bot.db.get_dashboard_user(username)
            if existing:
                return jsonify({'error': 'Username already exists.'}), 409

            hashed = _hash_password(password)
            encrypted = _encrypt_password(self.fernet, password)
            user = await self.bot.db.create_dashboard_user(username, hashed, encrypted, can_restart, can_view_logs)
            # Replace ciphertext with readable password for the response
            user['password_display'] = password
            user.pop('password_encrypted', None)
            return jsonify(user), 201

        @self.app.route('/api/users/<int:user_id>', methods=['PUT'])
        async def api_update_user(user_id: int):
            if not request.dash_user.get('is_admin'):
                return jsonify({'error': 'Forbidden'}), 403

            try:
                data = await request.get_json()
            except Exception:
                return jsonify({'error': 'Invalid request body'}), 400

            kwargs: dict = {}
            if 'username' in (data or {}) and data['username']:
                new_username = data['username'].strip()
                err = _validate_username(new_username)
                if err:
                    return jsonify({'error': err}), 400
                # Check uniqueness
                existing = await self.bot.db.get_dashboard_user(new_username)
                if existing and existing['id'] != user_id:
                    return jsonify({'error': 'Username already exists.'}), 409
                kwargs['username'] = new_username
            if 'can_restart' in (data or {}):
                kwargs['can_restart'] = bool(data['can_restart'])
            if 'can_view_logs' in (data or {}):
                kwargs['can_view_logs'] = bool(data['can_view_logs'])
            if 'password' in (data or {}) and data['password']:
                err = _validate_password(data['password'])
                if err:
                    return jsonify({'error': err}), 400
                kwargs['password_hash'] = _hash_password(data['password'])
                kwargs['password_encrypted'] = _encrypt_password(self.fernet, data['password'])

            if not kwargs:
                return jsonify({'error': 'No fields to update.'}), 400

            updated = await self.bot.db.update_dashboard_user(user_id, **kwargs)
            if not updated:
                return jsonify({'error': 'User not found or is admin (cannot modify admin).'}), 404
            return jsonify({'status': 'ok'})

        @self.app.route('/api/users/<int:user_id>', methods=['DELETE'])
        async def api_delete_user(user_id: int):
            if not request.dash_user.get('is_admin'):
                return jsonify({'error': 'Forbidden'}), 403

            deleted = await self.bot.db.delete_dashboard_user(user_id)
            if not deleted:
                return jsonify({'error': 'User not found or is admin (cannot delete admin).'}), 404
            return jsonify({'status': 'ok'})

        # ─── WebSocket ───────────────────────────────────────────────────

        @self.app.websocket('/ws')
        async def ws_endpoint():
            token = websocket.cookies.get('DASH_SESSION')
            user = self.signer.decode_token(token)
            if not user:
                await websocket.close(1008, 'Unauthorized')
                return

            dash_logger = logging.getLogger('MusicBot.Dashboard')
            can_view_logs = user.get('can_view_logs', False)
            last_log_index = 0
            first_tick = True
            tick_count = 0

            while True:
                try:
                    # Re-validate against DB every 30 ticks (~30 seconds)
                    tick_count += 1
                    if tick_count % 30 == 0:
                        db_user = await self.bot.db.get_dashboard_user(user['username'])
                        if not db_user:
                            await websocket.close(1008, 'User deleted')
                            return
                        # Refresh live permissions from DB
                        user = {
                            'username': db_user['username'],
                            'is_admin': db_user['is_admin'],
                            'can_restart': db_user['can_restart'],
                            'can_view_logs': db_user['can_view_logs'],
                        }
                        can_view_logs = user['can_view_logs']

                    stats = self._get_stats()

                    # Accumulate server-side history
                    self._stats_history.append((
                        stats['cpu_usage'],
                        stats['ram_usage_mb'],
                        stats['ping'],
                    ))

                    payload: dict = {
                        'type': 'update',
                        'stats': stats,
                        'user': user,
                    }

                    # On first tick, send downsampled history so client can resume graphs
                    if first_tick:
                        history = list(self._stats_history)
                        max_pts = 1000
                        if len(history) > max_pts:
                            step = len(history) / max_pts
                            sampled = [history[int(i * step)] for i in range(max_pts)]
                        else:
                            sampled = history
                        payload['stats_history'] = {
                            'cpu':  [h[0] for h in sampled],
                            'ram':  [h[1] for h in sampled],
                            'ping': [h[2] for h in sampled],
                        }
                        first_tick = False

                    # Only send logs if user has permission
                    if can_view_logs:
                        current_logs = list(mem_log_handler.logs)
                        current_len = len(current_logs)
                        if current_len != last_log_index:
                            if last_log_index < current_len:
                                payload['new_logs'] = current_logs[last_log_index:]
                            else:
                                payload['full_logs'] = current_logs
                            last_log_index = current_len

                    await websocket.send_json(payload)
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    dash_logger.debug('WebSocket error: %s', exc)
                    break

    async def _perform_restart(self) -> None:
        """Exit with restart code — the launcher will respawn us."""
        dash_logger = logging.getLogger('MusicBot.Dashboard')
        dash_logger.info("Dashboard triggered bot restart...")

        # Close DB (the only state that needs flushing)
        await self.bot.db.close()

        # Disconnect voice clients and cleanup FFmpeg sources
        for vc in list(self.bot.voice_clients):
            try:
                if vc.source:
                    vc.source.cleanup()
                await vc.disconnect()
            except Exception:
                pass

        # Exit with code 42 — the launcher sees this and respawns
        os._exit(42)

    async def start(self) -> None:
        from hypercorn.asyncio import serve
        from hypercorn.config import Config

        # Initialize admin user in DB before starting the server
        await self._init_admin()

        config = Config()
        config.bind = [f"{self.bind}:{self.port}"]
        config.quic_bind = [f"{self.bind}:{self.port}"]
        config.alpn_protocols = ["h3", "h2", "http/1.1"]
        config.logconfig = None

        dash_logger = logging.getLogger('MusicBot.Dashboard')
        if not (os.path.exists(self.cert_path) and os.path.exists(self.key_path)):
            dash_logger.info("SSL certs not found — auto-generating self-signed certificate...")
            try:
                from generate_cert import generate_certificate
                cert_dir = os.path.dirname(self.cert_path) or 'certs'
                generate_certificate(cert_dir)
                dash_logger.info("Self-signed certificate generated successfully.")
            except Exception as e:
                dash_logger.error("Failed to auto-generate certificate: %s", e)

        if os.path.exists(self.cert_path) and os.path.exists(self.key_path):
            config.certfile = self.cert_path
            config.keyfile = self.key_path
            dash_logger.info(
                "Secure Dashboard running on https://%s:%s with HTTP/2 support",
                self.bind, self.port,
            )
        else:
            dash_logger.warning(
                "SSL certs not found and auto-generation failed! "
                "Run generate_cert.py manually or provide cert/key paths."
            )
            dash_logger.warning(
                "Dashboard running INSECURELY on http://%s:%s", self.bind, self.port,
            )

        await serve(self.app, config)
