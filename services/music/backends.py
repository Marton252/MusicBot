from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

import discord

from services.music.playback import AudioFilter, coerce_filter, ffmpeg_filter_options
from services.music import lavalink

if TYPE_CHECKING:
    from services.player import MusicPlayer

logger = logging.getLogger("MusicBot.Backends")


class AudioBackend(Protocol):
    name: str

    async def play(self, player: MusicPlayer, track: dict, *, start_seconds: float = 0.0) -> object | None:
        ...

    async def pause(self, player: MusicPlayer) -> None:
        ...

    async def resume(self, player: MusicPlayer) -> None:
        ...

    async def stop(self, player: MusicPlayer) -> None:
        ...

    async def set_volume(self, player: MusicPlayer, volume: float) -> None:
        ...

    async def set_filter(self, player: MusicPlayer, audio_filter: AudioFilter) -> None:
        ...

    async def cleanup(self, player: MusicPlayer) -> None:
        ...

    async def disconnect(self, player: MusicPlayer) -> None:
        ...


class FFmpegBackend:
    name = "ffmpeg"

    async def play(self, player: MusicPlayer, track: dict, *, start_seconds: float = 0.0) -> object | None:
        before = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
        if start_seconds > 0:
            before = f"-ss {start_seconds:.1f} {before}"

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(
                track["url"],
                before_options=before,
                options=ffmpeg_filter_options(player.active_filter),
            ),
            volume=player.volume,
        )

        voice_client = player.guild.voice_client
        if not voice_client:
            source.cleanup()
            return None

        voice_client.play(
            source,
            after=lambda _: player.bot.loop.call_soon_threadsafe(player.next.set),
        )
        return source

    async def pause(self, player: MusicPlayer) -> None:
        vc = player.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()

    async def resume(self, player: MusicPlayer) -> None:
        vc = player.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()

    async def stop(self, player: MusicPlayer) -> None:
        vc = player.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()

    async def set_volume(self, player: MusicPlayer, volume: float) -> None:
        vc = player.guild.voice_client
        if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = volume

    async def set_filter(self, player: MusicPlayer, audio_filter: AudioFilter) -> None:
        player.ffmpeg_options["options"] = ffmpeg_filter_options(audio_filter)

    async def cleanup(self, player: MusicPlayer) -> None:
        vc = player.guild.voice_client
        if vc and getattr(vc, "source", None):
            vc.source.cleanup()

    async def disconnect(self, player: MusicPlayer) -> None:
        vc = player.guild.voice_client
        if vc:
            if vc.is_playing() or vc.is_paused():
                vc.stop()
            if getattr(vc, "source", None):
                vc.source.cleanup()
            await vc.disconnect()


class LavalinkBackend:
    name = "lavalink"

    async def play(self, player: MusicPlayer, track: dict, *, start_seconds: float = 0.0) -> object | None:
        vc = player.guild.voice_client
        if not vc:
            return None

        playable = await lavalink.load_playable(track)
        if not playable:
            raise RuntimeError("Lavalink could not load a playable track.")

        start_ms = max(0, int(start_seconds * 1000))
        filters = _lavalink_filters(player.active_filter)
        await vc.play(playable, start=start_ms, volume=int(player.volume * 100), filters=filters)
        return playable

    async def pause(self, player: MusicPlayer) -> None:
        vc = player.guild.voice_client
        if vc:
            await vc.pause(True)

    async def resume(self, player: MusicPlayer) -> None:
        vc = player.guild.voice_client
        if vc:
            await vc.pause(False)

    async def stop(self, player: MusicPlayer) -> None:
        vc = player.guild.voice_client
        if vc:
            await vc.stop()
        player.next.set()

    async def set_volume(self, player: MusicPlayer, volume: float) -> None:
        vc = player.guild.voice_client
        if vc:
            await vc.set_volume(int(volume * 100))

    async def set_filter(self, player: MusicPlayer, audio_filter: AudioFilter) -> None:
        vc = player.guild.voice_client
        if vc:
            await vc.set_filters(_lavalink_filters(audio_filter), seek=True)

    async def cleanup(self, player: MusicPlayer) -> None:
        return None

    async def disconnect(self, player: MusicPlayer) -> None:
        vc = player.guild.voice_client
        if vc:
            with _suppress_all():
                await vc.stop()
            await vc.disconnect()


class _suppress_all:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        return True


def create_backend() -> AudioBackend:
    if lavalink.is_lavalink_active():
        return LavalinkBackend()
    return FFmpegBackend()


def _lavalink_filters(audio_filter: AudioFilter):
    wavelink = lavalink._import_wavelink()
    audio_filter = coerce_filter(audio_filter)
    if audio_filter is AudioFilter.NONE:
        return wavelink.Filters()
    if audio_filter is AudioFilter.BASSBOOST:
        bands = [{"band": band, "gain": gain} for band, gain in [(0, 0.20), (1, 0.18), (2, 0.14), (3, 0.08)]]
        return wavelink.Filters.from_filters(equalizer=wavelink.Equalizer().set(bands=bands), reset=True)
    if audio_filter is AudioFilter.NIGHTCORE:
        return wavelink.Filters.from_filters(
            timescale=wavelink.Timescale({"speed": 1.20, "pitch": 1.20, "rate": 1.0}),
            reset=True,
        )
    if audio_filter is AudioFilter.VAPORWAVE:
        return wavelink.Filters.from_filters(
            timescale=wavelink.Timescale({"speed": 0.85, "pitch": 0.85, "rate": 1.0}),
            reset=True,
        )
    if audio_filter is AudioFilter.KARAOKE:
        return wavelink.Filters.from_filters(
            karaoke=wavelink.Karaoke({"level": 1.0, "monoLevel": 1.0, "filterBand": 220.0, "filterWidth": 100.0}),
            reset=True,
        )
    if audio_filter is AudioFilter.EIGHT_D:
        return wavelink.Filters.from_filters(rotation=wavelink.Rotation({"rotationHz": 0.09}), reset=True)
    return wavelink.Filters()
