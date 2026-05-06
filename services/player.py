from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING

import discord

from services.extractor import YTDLSource
from services.music.playback import AudioFilter, PlaybackState, coerce_filter, ffmpeg_filter_options
from services.music.queue import MusicQueue

from config import MAX_QUEUE_SIZE

if TYPE_CHECKING:
    from cogs.music import Music

logger = logging.getLogger('MusicBot.Player')


class MusicPlayer:
    """Per-guild music player with an event-driven queue (no spin-loop)."""

    def __init__(
        self,
        bot: discord.Client,
        guild: discord.Guild,
        channel: discord.abc.Messageable,
        cog: Music,
    ) -> None:
        self.bot = bot
        self.guild = guild
        self.channel = channel
        self.cog = cog

        self.queue = MusicQueue(MAX_QUEUE_SIZE)
        self.next: asyncio.Event = asyncio.Event()

        # Event to signal queue availability (replaces spin-loop)
        self._queue_ready: asyncio.Event = asyncio.Event()

        self.current: dict | None = None
        self.volume: float = 1.0
        self.paused: bool = False
        self.repeat: bool = False
        self.active_filter: AudioFilter = AudioFilter.NONE
        self.state: PlaybackState = PlaybackState.IDLE
        self.last_error: str | None = None
        self.np_message: discord.Message | None = None

        # Playback time tracking (for seeking on filter change)
        self._play_start: float = 0.0          # monotonic time when playback started
        self._elapsed_before_pause: float = 0.0  # accumulated play time before last pause
        self._seek_offset: float = 0.0          # seconds to seek into next track
        self._is_filter_restart: bool = False   # suppress NP panel on filter restart
        self._filter_restart_pending: bool = False
        self._start_offset: float = 0.0         # cumulative start base (kept across filter restarts)
        self._closed: bool = False

        self.ffmpeg_options: dict[str, str] = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': ffmpeg_filter_options(self.active_filter),
        }

        self.task: asyncio.Task = asyncio.create_task(self.player_loop())

    async def player_loop(self) -> None:
        await self.bot.wait_until_ready()

        while not self.bot.is_closed() and not self._closed:
            self.next.clear()
            self.paused = False
            source: discord.PCMVolumeTransformer | None = None

            try:
                # Wait for the next song with a 5-minute inactivity timeout
                self.state = PlaybackState.IDLE
                self.current = await asyncio.wait_for(self._queue_get(), timeout=300)
            except asyncio.TimeoutError:
                await self.destroy(self.guild)
                return
            except asyncio.CancelledError:
                return

            if not self.guild.voice_client:
                self.current = None
                continue

            # For filter restarts on non-YouTube platforms, re-extract a
            # fresh stream URL because SoundCloud (and others) expire fast.
            if self._is_filter_restart and self.current:
                self.state = PlaybackState.RECOVERING
                webpage = self.current.get('webpage_url', '')
                is_yt = any(d in webpage for d in ('youtube.com', 'youtu.be'))
                if webpage and not is_yt:
                    try:
                        fresh = await YTDLSource._extract_url(webpage)
                        if fresh and fresh.get('url'):
                            self.current['url'] = fresh['url']
                            logger.debug("Refreshed stream URL for filter restart")
                    except Exception as e:
                        logger.warning("Failed to refresh stream URL: %s", e)

            # Build FFmpeg before_options with optional seek
            before = '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
            if self._seek_offset > 0:
                before = f'-ss {self._seek_offset:.1f} {before}'
                self._start_offset = self._seek_offset
                self._seek_offset = 0.0
            else:
                self._start_offset = 0.0

            try:
                self.state = PlaybackState.RESOLVING
                source = discord.PCMVolumeTransformer(
                    discord.FFmpegPCMAudio(
                        self.current['url'],
                        before_options=before,
                        options=self.ffmpeg_options['options'],
                    ),
                    volume=self.volume,
                )

                # Reset playback timer
                self._play_start = time.monotonic()
                self._elapsed_before_pause = 0.0

                voice_client = self.guild.voice_client
                if not voice_client:
                    self.current = None
                    continue

                # NOTE: bot.loop.call_soon_threadsafe is correct here —
                # this lambda runs on FFmpeg's thread, not the async loop
                voice_client.play(
                    source,
                    after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set),
                )
                self.state = PlaybackState.PLAYING

                # Send the now-playing panel (skip on filter restart — same song)
                if self._is_filter_restart:
                    self._is_filter_restart = False
                    self._filter_restart_pending = False
                else:
                    try:
                        await self.cog.send_np_panel(self)
                    except Exception as e:
                        logger.error("Failed to send NP panel: %s", e)

                await self.next.wait()

                # If repeat is on, re-enqueue the current track at the front
                if self.repeat and self.current and not self._closed:
                    self.queue.appendleft(self.current)
                    self._queue_ready.set()

            except asyncio.CancelledError:
                return
            except Exception as e:
                self.state = PlaybackState.FAILED
                self.last_error = str(e)
                logger.error("Playback failed in guild %s: %s", self.guild.id, e)
                self._is_filter_restart = False
                self._filter_restart_pending = False
            finally:
                if source:
                    source.cleanup()
                self.current = None
                if not self._closed and self.state is PlaybackState.FAILED:
                    self.state = PlaybackState.IDLE

    async def _queue_get(self) -> dict:
        """Wait efficiently for the next queue item (no busy-wait)."""
        while not self.queue:
            self._queue_ready.clear()
            await self._queue_ready.wait()
        return self.queue.popleft()

    def enqueue(self, item: dict) -> bool:
        """Add an item to the queue. Returns False if queue is full."""
        if len(self.queue) >= MAX_QUEUE_SIZE:
            return False
        if not self.queue.add(item):
            return False
        self._queue_ready.set()
        return True

    async def destroy(self, guild: discord.Guild) -> None:
        await self.cog.cleanup(guild)

    async def close(self) -> None:
        """Stop playback, disconnect voice, and stop the background loop."""
        self._closed = True
        self.queue.clear()
        self.repeat = False
        self._is_filter_restart = False
        self._filter_restart_pending = False
        self._queue_ready.set()
        self.next.set()

        voice_client = self.guild.voice_client
        if voice_client:
            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()
            if voice_client.source:
                voice_client.source.cleanup()
            await voice_client.disconnect()

        if self.task is not asyncio.current_task():
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task

    def skip(self) -> None:
        if self.guild.voice_client and (
            self.guild.voice_client.is_playing() or self.guild.voice_client.is_paused()
        ):
            self.guild.voice_client.stop()

    def stop(self) -> None:
        self.queue.clear()
        self.repeat = False
        self._is_filter_restart = False
        self._filter_restart_pending = False
        if self.guild.voice_client and (
            self.guild.voice_client.is_playing() or self.guild.voice_client.is_paused()
        ):
            self.guild.voice_client.stop()

    def pause(self) -> None:
        if self.guild.voice_client and self.guild.voice_client.is_playing():
            # Save elapsed time before pausing
            self._elapsed_before_pause += time.monotonic() - self._play_start
            self.guild.voice_client.pause()
            self.paused = True
            self.state = PlaybackState.PAUSED

    def resume(self) -> None:
        if self.guild.voice_client and self.guild.voice_client.is_paused():
            # Reset play start for the new segment
            self._play_start = time.monotonic()
            self.guild.voice_client.resume()
            self.paused = False
            self.state = PlaybackState.PLAYING

    def shuffle(self) -> None:
        self.queue.shuffle()

    def set_volume(self, vol: float) -> None:
        self.volume = vol
        # Update live source if playing
        vc = self.guild.voice_client
        if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = vol

    def toggle_repeat(self) -> bool:
        self.repeat = not self.repeat
        return self.repeat

    def set_filter(self, filter_name: str | AudioFilter) -> None:
        """Apply an audio filter. If a track is playing, restart at the current position."""
        self.active_filter = coerce_filter(filter_name)
        self.ffmpeg_options['options'] = ffmpeg_filter_options(self.active_filter)

        # Restart the current track at current position so the filter applies immediately
        vc = self.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()) and self.current:
            if self._filter_restart_pending:
                return
            # Calculate how far into the song we are
            if self.paused:
                elapsed = self._start_offset + self._elapsed_before_pause
            else:
                elapsed = self._start_offset + self._elapsed_before_pause + (time.monotonic() - self._play_start)

            self._seek_offset = elapsed
            self._is_filter_restart = True
            self._filter_restart_pending = True
            self.queue.appendleft(self.current)
            self._queue_ready.set()
            vc.stop()  # triggers after -> next.set() -> player_loop replays at seek offset


class PlayerManager:
    """Holds one MusicPlayer per guild."""

    def __init__(self) -> None:
        self.players: dict[int, MusicPlayer] = {}

    def get_player(
        self,
        interaction: discord.Interaction,
        cog: Music,
    ) -> MusicPlayer:
        guild_id = interaction.guild.id
        if guild_id not in self.players:
            self.players[guild_id] = MusicPlayer(
                bot=interaction.client,
                guild=interaction.guild,
                channel=interaction.channel,
                cog=cog,
            )
        return self.players[guild_id]

    def get_existing_player(self, guild_id: int) -> MusicPlayer | None:
        return self.players.get(guild_id)

    async def cleanup(self, guild: discord.Guild) -> None:
        player = self.players.pop(guild.id, None)
        if player:
            await player.close()
        elif guild.voice_client:
            await guild.voice_client.disconnect()


manager = PlayerManager()
