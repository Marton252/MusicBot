import os
import logging
import secrets
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger('MusicBot.Config')

# Discord Tokens
DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "your_discord_bot_token_here")
CLIENT_ID: str = os.getenv("CLIENT_ID", "your_client_id_here")
GUILD_ID: int | None = None

_guild_id_raw = os.getenv("GUILD_ID", None)
if _guild_id_raw and _guild_id_raw.lower() != "null":
    try:
        GUILD_ID = int(_guild_id_raw)
    except ValueError:
        GUILD_ID = None

# Spotify API
SPOTIFY_CLIENT_ID: str = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET: str = os.getenv("SPOTIFY_CLIENT_SECRET", "")

# Genius API
GENIUS_ACCESS_TOKEN: str = os.getenv("GENIUS_ACCESS_TOKEN", "")

# Bot Details
STATUS: str = os.getenv("STATUS", "🎵 Music Bot | /play")
EMBED_COLOR: str = os.getenv("EMBED_COLOR", "#FF6B6B")
SUPPORT_SERVER: str = os.getenv("SUPPORT_SERVER", "https://discord.gg/your_server_invite")
WEBSITE: str = os.getenv("WEBSITE", "https://your_website.com")

# Owner & Reporting
OWNER_ID: int | None = None
_owner_id_raw = os.getenv("OWNER_ID", None)
if _owner_id_raw:
    try:
        OWNER_ID = int(_owner_id_raw)
    except ValueError:
        OWNER_ID = None

REPORT_CHANNEL_ID: int | None = None
_report_ch_raw = os.getenv("REPORT_CHANNEL_ID", None)
if _report_ch_raw:
    try:
        REPORT_CHANNEL_ID = int(_report_ch_raw)
    except ValueError:
        REPORT_CHANNEL_ID = None

# Audio Settings
DEFAULT_VOLUME: int = 100
MAX_QUEUE_SIZE: int = 100
MAX_PLAYLIST_SIZE: int = 50

# Runtime Settings
BOT_TIMEZONE: str = os.getenv("BOT_TIMEZONE", "UTC")

# Convert color hex strings to integers for discord.Embed
def get_embed_color() -> int:
    try:
        return int(EMBED_COLOR.replace("#", ""), 16)
    except ValueError:
        return 0xFF6B6B  # Default color

# Dashboard secret key — used for cookie signing & password encryption.
# Auto-generates if not set, but you should persist it in .env so sessions
# survive restarts.
_secret_key_raw = os.getenv("DASHBOARD_SECRET_KEY", "")
if _secret_key_raw:
    DASHBOARD_SECRET_KEY: str = _secret_key_raw
else:
    DASHBOARD_SECRET_KEY = secrets.token_hex(32)
    logger.warning(
        "DASHBOARD_SECRET_KEY is not set — generated a random key. "
        "Sessions will NOT survive bot restarts. Set DASHBOARD_SECRET_KEY in .env to fix this."
    )

# Sharding Settings
TOTAL_SHARDS: int | str = os.getenv("TOTAL_SHARDS", "auto")
if isinstance(TOTAL_SHARDS, str) and TOTAL_SHARDS.lower() != "auto":
    try:
        TOTAL_SHARDS = int(TOTAL_SHARDS)
    except ValueError:
        TOTAL_SHARDS = "auto"

# YouTube Cookie Settings
COOKIES_FROM_BROWSER: str = os.getenv("COOKIES_FROM_BROWSER", "")
COOKIES_FILE: str = os.getenv("COOKIES_FILE", "")

# Web Dashboard Settings
def _parse_port(value: str, default: int = 25825, name: str = "DASHBOARD_PORT") -> int:
    try:
        port = int(value)
        if 1 <= port <= 65535:
            return port
    except (TypeError, ValueError):
        pass
    logger.warning("Invalid %s=%r; using %d.", name, value, default)
    return default


DASHBOARD_PORT: int = _parse_port(os.getenv("DASHBOARD_PORT", "25825"), name="DASHBOARD_PORT")
DASHBOARD_BIND: str = os.getenv("DASHBOARD_BIND", "0.0.0.0")
SSL_CERT_PATH: str = os.getenv("SSL_CERT_PATH", "certs/cert.pem")
SSL_KEY_PATH: str = os.getenv("SSL_KEY_PATH", "certs/key.pem")
TRUSTED_PROXY_IPS: tuple[str, ...] = tuple(
    ip.strip() for ip in os.getenv("TRUSTED_PROXY_IPS", "").split(",") if ip.strip()
)

# Audio backend settings. Lavalink is the default; FFmpeg remains available as a fallback mode.
MUSIC_BACKEND: str = os.getenv("MUSIC_BACKEND", "lavalink").strip().lower()
if MUSIC_BACKEND not in {"ffmpeg", "lavalink", "auto"}:
    logger.warning("Invalid MUSIC_BACKEND=%r; using lavalink.", MUSIC_BACKEND)
    MUSIC_BACKEND = "lavalink"

LAVALINK_HOST: str = os.getenv("LAVALINK_HOST", "lavalink").strip() or "lavalink"
LAVALINK_PORT: int = _parse_port(os.getenv("LAVALINK_PORT", "2333"), 2333, name="LAVALINK_PORT")
LAVALINK_PASSWORD: str = os.getenv("LAVALINK_PASSWORD", "change_me")
LAVALINK_SECURE: bool = os.getenv("LAVALINK_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
try:
    LAVALINK_CONNECT_RETRIES: int = max(1, int(os.getenv("LAVALINK_CONNECT_RETRIES", "12")))
except ValueError:
    logger.warning(
        "Invalid LAVALINK_CONNECT_RETRIES=%r; using 12.",
        os.getenv("LAVALINK_CONNECT_RETRIES"),
    )
    LAVALINK_CONNECT_RETRIES = 12
try:
    LAVALINK_CONNECT_RETRY_DELAY: float = max(0.5, float(os.getenv("LAVALINK_CONNECT_RETRY_DELAY", "5")))
except ValueError:
    logger.warning(
        "Invalid LAVALINK_CONNECT_RETRY_DELAY=%r; using 5.",
        os.getenv("LAVALINK_CONNECT_RETRY_DELAY"),
    )
    LAVALINK_CONNECT_RETRY_DELAY = 5.0
try:
    LAVALINK_CROSSFADE_SECONDS: int = max(0, int(os.getenv("LAVALINK_CROSSFADE_SECONDS", "0")))
except ValueError:
    logger.warning(
        "Invalid LAVALINK_CROSSFADE_SECONDS=%r; using 0.",
        os.getenv("LAVALINK_CROSSFADE_SECONDS"),
    )
    LAVALINK_CROSSFADE_SECONDS = 0

# Dashboard admin credentials — refuse to use known-weak password defaults
DASHBOARD_ADMIN_USER: str = os.getenv("DASHBOARD_ADMIN_USER", "admin")
_INSECURE_DEFAULTS = {"admin123", "password", "admin", "CHANGE_ME_TO_A_STRONG_PASSWORD", ""}
_dashboard_pw = os.getenv("DASHBOARD_ADMIN_PASSWORD", "")
if _dashboard_pw in _INSECURE_DEFAULTS:
    logger.warning(
        "DASHBOARD_ADMIN_PASSWORD is not set or uses a known-insecure default! "
        "The web dashboard will be DISABLED until a strong password is set in .env"
    )
    DASHBOARD_ADMIN_PASSWORD: str | None = None
else:
    DASHBOARD_ADMIN_PASSWORD = _dashboard_pw
