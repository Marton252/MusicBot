"""
Discord Music Bot — Entry Point

Architecture:
  • `py bot.py`          → runs the LAUNCHER (a thin loop that manages the bot subprocess)
  • `py bot.py --run`    → runs the actual BOT (discord.py + Hypercorn dashboard)

The launcher restarts the bot when it exits with code 42 (restart signal).
Ctrl+C is forwarded to the child and kills everything cleanly.
"""

import asyncio
import contextlib
import logging
import os
import signal
import ssl
import subprocess
import sys
from pathlib import Path

import discord
from discord.ext import commands

from config import (
    DISCORD_TOKEN, STATUS, get_embed_color, TOTAL_SHARDS,
    DASHBOARD_PORT, DASHBOARD_ADMIN_USER, DASHBOARD_ADMIN_PASSWORD, DASHBOARD_BIND,
    SSL_CERT_PATH, SSL_KEY_PATH,
)
from services.database import db as shared_db
from services.web_dashboard import mem_log_handler, DashboardServer

# ─── Constants ───────────────────────────────────────────────────────────────────
RESTART_EXIT_CODE = 42

# ─── Logging ─────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger('MusicBot')
logging.getLogger().addHandler(mem_log_handler)


# ─── Bot Class ───────────────────────────────────────────────────────────────────

class MusicBot(commands.AutoShardedBot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.voice_states = True
        intents.guilds = True

        shard_count = None if TOTAL_SHARDS == "auto" else TOTAL_SHARDS

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
            shard_count=shard_count,
        )
        self.embed_color: int = get_embed_color()
        self.db = shared_db
        self.dashboard_task: asyncio.Task | None = None
        from datetime import datetime, UTC
        self.start_time = datetime.now(UTC)

    async def setup_hook(self) -> None:
        # Filter harmless SSL/Hypercorn errors from asyncio
        def custom_exception_handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
            exc = context.get('exception')
            if isinstance(exc, ssl.SSLError) and 'APPLICATION_DATA_AFTER_CLOSE_NOTIFY' in str(exc):
                return
            if isinstance(exc, TimeoutError) and 'SSL shutdown timed out' in str(exc):
                return
            if isinstance(exc, (RuntimeError, asyncio.CancelledError)):
                msg = str(exc)
                if any(s in msg for s in ('TaskGroup', 'Event loop stopped', 'is shutting down')):
                    return
            if isinstance(exc, SystemExit):
                return
            loop.default_exception_handler(context)

        self.loop.set_exception_handler(custom_exception_handler)

        # Register error handler (runs exactly once, unlike on_ready)
        @self.tree.error
        async def on_app_command_error(
            interaction: discord.Interaction,
            error: discord.app_commands.AppCommandError,
        ) -> None:
            logger.error("AppCommand error in %s: %s", interaction.command, error)

            from services.language import language
            msg = await language.get_string(interaction.guild_id, "msg_error_command")

            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)

        logger.info("Setting up database...")
        await self.db.connect()

        # Register command translator
        from services.language import CommandTranslator
        await self.tree.set_translator(CommandTranslator())

        # Start web dashboard (only if admin password is configured)
        if DASHBOARD_ADMIN_PASSWORD:
            logger.info("Starting Web Dashboard...")
            dash = DashboardServer(
                self, DASHBOARD_PORT, DASHBOARD_ADMIN_USER, DASHBOARD_ADMIN_PASSWORD,
                SSL_CERT_PATH, SSL_KEY_PATH, DASHBOARD_BIND,
            )
            self.dashboard_task = asyncio.create_task(dash.start())

            def _log_dashboard_failure(task: asyncio.Task) -> None:
                if task.cancelled():
                    return
                exc = task.exception()
                if exc:
                    logger.error(
                        "Web Dashboard task stopped unexpectedly.",
                        exc_info=(type(exc), exc, exc.__traceback__),
                    )

            self.dashboard_task.add_done_callback(_log_dashboard_failure)
        else:
            logger.warning("Web Dashboard DISABLED — set a strong DASHBOARD_ADMIN_PASSWORD in .env to enable it.")

        # Load cogs using pathlib
        logger.info("Setting up cogs...")
        cogs_dir = Path('cogs')
        cogs_dir.mkdir(exist_ok=True)
        for cog_file in sorted(cogs_dir.glob('[!_]*.py')):
            try:
                await self.load_extension(f'cogs.{cog_file.stem}')
                logger.info("Loaded cog: %s", cog_file.name)
            except Exception as e:
                logger.error("Failed to load cog %s: %s", cog_file.name, e)

        # Slash commands will be synced to each guild in on_ready
        logger.info("Cogs loaded. Commands will sync to guilds on ready.")

    async def on_ready(self) -> None:
        logger.info('Logged in as %s (ID: %s)', self.user, self.user.id)
        await self.change_presence(
            activity=discord.CustomActivity(name=STATUS),
        )

        # Sync commands to all guilds (only once, not on reconnects)
        if not getattr(self, '_synced', False):
            self._synced = True
            logger.info("Syncing commands to %d guild(s)...", len(self.guilds))

            # Sync to each guild for instant availability
            failed = 0
            for guild in self.guilds:
                try:
                    self.tree.copy_global_to(guild=guild)
                    await self.tree.sync(guild=guild)
                except Exception as e:
                    logger.warning("Failed to sync commands to guild %s: %s", guild.id, e)
                    failed += 1
            logger.info(
                "Commands synced to %d guild(s)%s.",
                len(self.guilds) - failed,
                f" ({failed} failed)" if failed else "",
            )

            # Clear stale global commands so they don't duplicate guild commands
            # Save commands, clear global, sync empty, restore
            saved = self.tree.get_commands()
            self.tree.clear_commands(guild=None)
            await self.tree.sync()  # pushes empty set globally
            for cmd in saved:
                self.tree.add_command(cmd)
            logger.info("Cleared stale global commands.")

        logger.info('Bot is ready!')

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Sync commands to new guilds immediately."""
        try:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Commands synced to new guild: %s (%s)", guild.name, guild.id)
        except Exception as e:
            logger.error("Failed to sync commands to guild %s: %s", guild.id, e)

    async def shutdown_resources(self, *, cancel_dashboard: bool = True) -> None:
        """Release resources owned by services before process shutdown."""
        if cancel_dashboard and self.dashboard_task and not self.dashboard_task.done():
            self.dashboard_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.dashboard_task

        from services.player import manager
        for player in list(manager.players.values()):
            await manager.cleanup(player.guild)
        for vc in list(self.voice_clients):
            with contextlib.suppress(Exception):
                if vc.source:
                    vc.source.cleanup()
                await vc.disconnect()

        from services.extractor import shutdown_ytdl_executor
        from services.lyrics import shutdown_lyrics_executor
        shutdown_ytdl_executor()
        shutdown_lyrics_executor()

        await self.db.close()

    async def close(self) -> None:
        """Clean shutdown: close DB, then call super."""
        await self.shutdown_resources()
        await super().close()


# ─── Launcher (default: `py bot.py`) ─────────────────────────────────────────────

def run_launcher():
    """Run the bot as a managed subprocess. Restart it when it exits with code 42."""
    logger.info("Launcher started. Press Ctrl+C to stop.")

    child: subprocess.Popen | None = None

    def _stop(sig, frame):
        """Ctrl+C handler for the launcher — kill the child and exit."""
        logger.info("Ctrl+C received — shutting down.")
        if child and child.poll() is None:
            child.kill()
        os._exit(0)

    signal.signal(signal.SIGINT, _stop)

    while True:
        child = subprocess.Popen(
            [sys.executable, sys.argv[0], '--run'],
            cwd=os.getcwd(),
        )

        # Poll with timeout so Python can process Ctrl+C signals.
        # child.wait() without timeout blocks in C, making signals invisible.
        while True:
            try:
                exit_code = child.wait(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                continue

        if exit_code == RESTART_EXIT_CODE:
            logger.info("Bot exited with restart code. Restarting...")
            continue
        else:
            logger.info("Bot exited with code %d. Stopping.", exit_code)
            break

    sys.exit(0)


# ─── Bot Runner (when called with --run) ─────────────────────────────────────────

def run_bot():
    """Run the actual Discord bot."""
    if DISCORD_TOKEN == "your_discord_bot_token_here":
        logger.error("Please set your DISCORD_TOKEN in the .env file!")
        sys.exit(1)

    bot = MusicBot()

    # Suppress asyncio cleanup noise
    logging.getLogger('asyncio').setLevel(logging.CRITICAL)

    # Ctrl+C handler: close DB, then force-exit with code 0 (not 42, so launcher stops)
    def _handle_sigint(sig, frame):
        logger.info("Ctrl+C received — shutting down.")
        try:
            if bot.db._conn:
                bot.db._conn._conn.close()
                logger.info("Database connection closed.")
        except Exception:
            pass
        os._exit(0)

    signal.signal(signal.SIGINT, _handle_sigint)

    try:
        bot.run(DISCORD_TOKEN, log_handler=None)
    except (KeyboardInterrupt, RuntimeError, SystemExit):
        pass

    os._exit(0)


# ─── Entry Point ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if '--run' in sys.argv:
        run_bot()
    else:
        run_launcher()
