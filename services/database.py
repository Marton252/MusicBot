import os

import aiosqlite
import logging

logger = logging.getLogger('MusicBot.Database')
DB_PATH = os.getenv('DATABASE_PATH', 'database.db')


class Database:
    """Persistent async SQLite connection manager with language caching."""

    def __init__(self) -> None:
        self._conn: aiosqlite.Connection | None = None
        self._lang_cache: dict[int, str] = {}

    async def connect(self) -> None:
        """Open the persistent DB connection and create tables."""
        self._conn = await aiosqlite.connect(DB_PATH)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute('''
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                language TEXT DEFAULT 'en'
            )
        ''')
        await self._conn.execute('''
            CREATE TABLE IF NOT EXISTS dashboard_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                password_encrypted TEXT NOT NULL DEFAULT '',
                is_admin INTEGER NOT NULL DEFAULT 0,
                can_restart INTEGER NOT NULL DEFAULT 0,
                can_view_logs INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        ''')
        await self._conn.commit()
        logger.info("Database initialized with persistent connection.")

    async def close(self) -> None:
        """Close the persistent DB connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("Database connection closed.")

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            await self.connect()
        return self._conn

    # ─── Guild Language ─────────────────────────────────────────────────────────

    async def get_guild_language(self, guild_id: int) -> str:
        if not guild_id:
            return 'en'

        if guild_id in self._lang_cache:
            return self._lang_cache[guild_id]

        conn = await self._get_conn()
        async with conn.execute(
            'SELECT language FROM guild_settings WHERE guild_id = ?', (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            lang = row[0] if row else 'en'
            self._lang_cache[guild_id] = lang
            return lang

    async def set_guild_language(self, guild_id: int, language: str) -> None:
        self._lang_cache[guild_id] = language
        conn = await self._get_conn()
        await conn.execute('''
            INSERT INTO guild_settings (guild_id, language)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET language=excluded.language
        ''', (guild_id, language))
        await conn.commit()

    # ─── Dashboard Users ────────────────────────────────────────────────────────

    async def upsert_admin_user(self, username: str, password_hash: str) -> None:
        """Insert or update the admin user from .env credentials."""
        conn = await self._get_conn()
        await conn.execute('''
            INSERT INTO dashboard_users (username, password_hash, is_admin, can_restart, can_view_logs)
            VALUES (?, ?, 1, 1, 1)
            ON CONFLICT(username) DO UPDATE SET
                password_hash=excluded.password_hash,
                is_admin=1,
                can_restart=1,
                can_view_logs=1
        ''', (username, password_hash))
        await conn.commit()
        logger.info("Admin user '%s' upserted.", username)

    async def get_dashboard_user(self, username: str) -> dict | None:
        """Get a dashboard user by username. Returns dict or None."""
        conn = await self._get_conn()
        async with conn.execute(
            'SELECT id, username, password_hash, is_admin, can_restart, can_view_logs FROM dashboard_users WHERE username = ?',
            (username,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                'id': row[0],
                'username': row[1],
                'password_hash': row[2],
                'is_admin': bool(row[3]),
                'can_restart': bool(row[4]),
                'can_view_logs': bool(row[5]),
            }

    async def list_dashboard_users(self) -> list[dict]:
        """List all dashboard users (with encrypted passwords for admin viewing)."""
        conn = await self._get_conn()
        async with conn.execute(
            'SELECT id, username, is_admin, can_restart, can_view_logs, created_at, password_encrypted FROM dashboard_users ORDER BY id'
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    'id': row[0],
                    'username': row[1],
                    'is_admin': bool(row[2]),
                    'can_restart': bool(row[3]),
                    'can_view_logs': bool(row[4]),
                    'created_at': row[5],
                    'password_encrypted': row[6] or '',
                }
                for row in rows
            ]

    async def create_dashboard_user(
        self, username: str, password_hash: str, password_encrypted: str,
        can_restart: bool, can_view_logs: bool,
    ) -> dict:
        """Create a new non-admin dashboard user. Returns the created user dict."""
        conn = await self._get_conn()
        cursor = await conn.execute(
            '''INSERT INTO dashboard_users (username, password_hash, password_encrypted, is_admin, can_restart, can_view_logs)
               VALUES (?, ?, ?, 0, ?, ?)''',
            (username, password_hash, password_encrypted, int(can_restart), int(can_view_logs))
        )
        await conn.commit()
        return {
            'id': cursor.lastrowid,
            'username': username,
            'is_admin': False,
            'can_restart': can_restart,
            'can_view_logs': can_view_logs,
            'password_encrypted': password_encrypted,
        }

    async def update_dashboard_user(
        self, user_id: int, *,
        username: str | None = None,
        password_hash: str | None = None,
        password_encrypted: str | None = None,
        can_restart: bool | None = None,
        can_view_logs: bool | None = None,
    ) -> bool:
        """Update a dashboard user's fields. Returns True if a row was updated."""
        conn = await self._get_conn()
        updates: list[str] = []
        values: list = []

        if username is not None:
            updates.append('username = ?')
            values.append(username)
        if password_hash is not None:
            updates.append('password_hash = ?')
            values.append(password_hash)
        if password_encrypted is not None:
            updates.append('password_encrypted = ?')
            values.append(password_encrypted)
        if can_restart is not None:
            updates.append('can_restart = ?')
            values.append(int(can_restart))
        if can_view_logs is not None:
            updates.append('can_view_logs = ?')
            values.append(int(can_view_logs))

        if not updates:
            return False

        values.append(user_id)
        query = f"UPDATE dashboard_users SET {', '.join(updates)} WHERE id = ? AND is_admin = 0"
        cursor = await conn.execute(query, values)
        await conn.commit()
        return cursor.rowcount > 0

    async def delete_dashboard_user(self, user_id: int) -> bool:
        """Delete a non-admin dashboard user. Returns True if deleted."""
        conn = await self._get_conn()
        cursor = await conn.execute(
            'DELETE FROM dashboard_users WHERE id = ? AND is_admin = 0', (user_id,)
        )
        await conn.commit()
        return cursor.rowcount > 0


# Shared module-level instance — bot.py assigns bot.db = db so
# everything (language, cogs, dashboard) uses the SAME connection.
db = Database()


async def get_guild_language(guild_id: int) -> str:
    return await db.get_guild_language(guild_id)


async def set_guild_language(guild_id: int, language: str) -> None:
    await db.set_guild_language(guild_id, language)
