from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any
from urllib.parse import urlparse

from config import (
    LAVALINK_CONNECT_RETRIES,
    LAVALINK_CONNECT_RETRY_DELAY,
    LAVALINK_HOST,
    LAVALINK_PASSWORD,
    LAVALINK_PORT,
    LAVALINK_SECURE,
    MUSIC_BACKEND,
)
from services.extractor import YTDLSource

logger = logging.getLogger("MusicBot.Lavalink")

_connected = False
_wavelink: Any | None = None


def _import_wavelink() -> Any:
    global _wavelink
    if _wavelink is None:
        import wavelink

        _wavelink = wavelink
    return _wavelink


def lavalink_requested() -> bool:
    return MUSIC_BACKEND in {"lavalink", "auto"}


def effective_backend() -> str:
    if MUSIC_BACKEND == "auto":
        return "lavalink" if _connected else "ffmpeg"
    return MUSIC_BACKEND


def is_lavalink_active() -> bool:
    return effective_backend() == "lavalink" and _connected


def strict_lavalink_unavailable() -> bool:
    return MUSIC_BACKEND == "lavalink" and not _connected


def should_use_lavalink_path() -> bool:
    return is_lavalink_active() or strict_lavalink_unavailable()


def mark_disconnected() -> None:
    global _connected
    _connected = False


def mark_connected() -> None:
    global _connected
    _connected = True


async def _wait_for_lavalink_socket() -> None:
    timeout = min(2.0, max(0.1, float(LAVALINK_CONNECT_RETRY_DELAY)))
    _, writer = await asyncio.wait_for(
        asyncio.open_connection(LAVALINK_HOST, LAVALINK_PORT),
        timeout=timeout,
    )
    writer.close()
    with contextlib.suppress(Exception):
        await writer.wait_closed()


async def connect_lavalink(bot: Any, *, quiet: bool = False) -> None:
    """Connect the optional Lavalink node during bot startup."""
    global _connected
    if not lavalink_requested():
        return

    try:
        wavelink = _import_wavelink()
    except ImportError as exc:
        msg = "wavelink is not installed; Lavalink backend is unavailable."
        if MUSIC_BACKEND == "lavalink":
            logger.error("%s Install wavelink or set MUSIC_BACKEND=ffmpeg.", msg)
        else:
            logger.warning("%s Falling back to FFmpeg.", msg)
        _connected = False
        return

    scheme = "https" if LAVALINK_SECURE else "http"
    uri = f"{scheme}://{LAVALINK_HOST}:{LAVALINK_PORT}"
    last_exc: Exception | None = None
    for attempt in range(1, LAVALINK_CONNECT_RETRIES + 1):
        try:
            await _wait_for_lavalink_socket()
            node = wavelink.Node(uri=uri, password=LAVALINK_PASSWORD, identifier="main")
            await wavelink.Pool.connect(nodes=[node], client=bot, cache_capacity=100)
            _connected = True
            logger.info("Connected to Lavalink node at %s.", uri)
            return
        except Exception as exc:
            last_exc = exc
            _connected = False
            with contextlib.suppress(Exception):
                await wavelink.Pool.close()
            if attempt < LAVALINK_CONNECT_RETRIES:
                logger.info(
                    "Failed to connect to Lavalink at %s (attempt %d/%d): %s. Retrying in %.1fs.",
                    uri,
                    attempt,
                    LAVALINK_CONNECT_RETRIES,
                    exc,
                    LAVALINK_CONNECT_RETRY_DELAY,
                )
                await asyncio.sleep(LAVALINK_CONNECT_RETRY_DELAY)

    if quiet:
        logger.info(
            "Lavalink is not ready yet at %s after %d attempts: %s",
            uri,
            LAVALINK_CONNECT_RETRIES,
            last_exc,
        )
        return

    if MUSIC_BACKEND == "lavalink":
        logger.error(
            "Failed to connect to Lavalink at %s after %d attempts: %s",
            uri,
            LAVALINK_CONNECT_RETRIES,
            last_exc,
        )
    else:
        logger.warning(
            "Failed to connect to Lavalink at %s after %d attempts; falling back to FFmpeg: %s",
            uri,
            LAVALINK_CONNECT_RETRIES,
            last_exc,
        )


async def reconnect_until_ready(bot: Any) -> None:
    """Keep trying in the background after startup if the node was not ready yet."""
    while lavalink_requested() and not _connected and not bot.is_closed():
        await asyncio.sleep(LAVALINK_CONNECT_RETRY_DELAY)
        await connect_lavalink(bot, quiet=True)


async def close_lavalink() -> None:
    global _connected
    if _wavelink is None:
        return
    with contextlib.suppress(Exception):
        await _wavelink.Pool.close()
    _connected = False


def player_cls() -> type:
    return _import_wavelink().Player


def _is_url(query: str) -> bool:
    return query.startswith(("http://", "https://"))


def _track_source_name(track: Any) -> str:
    source = getattr(track, "source", "") or ""
    return str(getattr(source, "name", source) or "Lavalink")


def _is_spotify_url(query: str) -> bool:
    parsed = urlparse(query)
    host = (parsed.hostname or "").lower()
    return host == "open.spotify.com" and bool(parsed.path and parsed.path != "/")


def playable_to_track(track: Any, *, requester_id: int | None = None) -> dict:
    length_ms = int(getattr(track, "length", 0) or 0)
    return {
        "title": getattr(track, "title", "Unknown Title"),
        "webpage_url": getattr(track, "uri", "") or "",
        "url": getattr(track, "uri", "") or "",
        "requester_id": requester_id or 0,
        "duration": max(0, length_ms // 1000),
        "platform": _track_source_name(track),
        "thumbnail": getattr(track, "artwork", None),
        "uploader": getattr(track, "author", "Unknown Artist"),
        "_lavalink_track": track,
    }


async def _first_playable(result: Any) -> Any | None:
    if not result:
        return None
    tracks = getattr(result, "tracks", None)
    if tracks:
        return tracks[0]
    if isinstance(result, list):
        return result[0] if result else None
    try:
        return result[0]
    except (TypeError, IndexError):
        return None


async def resolve_track(query: str, *, requester_id: int | None = None) -> dict | None:
    """Resolve a user query through Lavalink/Wavelink into the existing track dict shape."""
    if not is_lavalink_active():
        if strict_lavalink_unavailable():
            logger.error("MUSIC_BACKEND=lavalink but no Lavalink node is connected.")
            return None
        return await YTDLSource.extract_info(query)

    wavelink = _import_wavelink()

    # Spotify URLs are still resolved through the existing Spotify metadata path,
    # then loaded by stable webpage URL/search result in Lavalink at playback time.
    if _is_spotify_url(query):
        fallback = await YTDLSource.extract_info(query)
        if fallback:
            query = fallback.get("webpage_url") or fallback.get("title") or query

    try:
        if _is_url(query):
            result = await wavelink.Pool.fetch_tracks(query)
            playable = await _first_playable(result)
        else:
            yt_task = wavelink.Playable.search(query, source=wavelink.TrackSource.YouTubeMusic)
            sc_task = wavelink.Playable.search(query, source=wavelink.TrackSource.SoundCloud)
            yt_result, sc_result = await asyncio.gather(yt_task, sc_task, return_exceptions=True)
            playable = None
            for result in (yt_result, sc_result):
                if isinstance(result, Exception):
                    logger.debug("Lavalink search branch failed: %s", result)
                    continue
                playable = await _first_playable(result)
                if playable:
                    break
        return playable_to_track(playable, requester_id=requester_id) if playable else None
    except Exception as exc:
        logger.warning("Lavalink resolve failed for %r: %s", query, exc)
        if MUSIC_BACKEND == "auto":
            return await YTDLSource.extract_info(query)
        return None


async def resolve_playlist_track(query: str, *, requester_id: int | None = None) -> dict | None:
    return await resolve_track(query, requester_id=requester_id)


async def load_playable(track: dict) -> Any | None:
    """Return a Wavelink Playable for a saved/current track dict."""
    if track.get("_lavalink_track"):
        return track["_lavalink_track"]

    query = track.get("webpage_url") or track.get("title")
    if not query:
        return None
    resolved = await resolve_track(query, requester_id=track.get("requester_id"))
    if not resolved:
        return None
    track["_lavalink_track"] = resolved.get("_lavalink_track")
    track["url"] = resolved.get("url") or track.get("url")
    track["webpage_url"] = resolved.get("webpage_url") or track.get("webpage_url")
    return track.get("_lavalink_track")
