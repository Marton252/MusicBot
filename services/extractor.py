import asyncio
import concurrent.futures
import logging
import re
import threading
from difflib import SequenceMatcher

import spotipy
import yt_dlp
from spotipy.oauth2 import SpotifyClientCredentials

from config import (
    COOKIES_FILE,
    COOKIES_FROM_BROWSER,
    MAX_PLAYLIST_SIZE,
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
)

logger = logging.getLogger('MusicBot.Extractor')

# Dedicated thread pool for slow yt-dlp operations
_ytdl_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="ytdl"
)

sp: spotipy.Spotify | None = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    try:
        sp = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET,
                cache_handler=spotipy.cache_handler.MemoryCacheHandler(),
            )
        )
        logger.info("Spotify API configured successfully.")
    except Exception as e:
        logger.error("Failed to configure Spotify: %s", e)

YTDL_OPTIONS: dict = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

if COOKIES_FROM_BROWSER:
    YTDL_OPTIONS['cookiesfrombrowser'] = (COOKIES_FROM_BROWSER,)
elif COOKIES_FILE:
    YTDL_OPTIONS['cookiefile'] = COOKIES_FILE


# ────────────────────────────────────────────────────────────────────────────────
# Scoring helpers
# ────────────────────────────────────────────────────────────────────────────────

def _title_similarity(query: str, title: str) -> float:
    """Score how well a result title matches the search query (0.0–1.0)."""
    return SequenceMatcher(None, query.lower().strip(), title.lower().strip()).ratio()


def _score_result(query: str, result: dict) -> float:
    """Score a search result for relevance to the query."""
    score = 0.0
    title = result.get('title', '')

    # Title similarity (0–1, weighted heavily)
    score += _title_similarity(query, title) * 10.0

    # Has valid duration (not 0 or missing → likely broken)
    if result.get('duration', 0) > 0:
        score += 2.0

    # Has thumbnail (quality indicator)
    if result.get('thumbnail'):
        score += 1.0

    # Has uploader info
    if result.get('uploader') and result['uploader'] != 'Unknown Artist':
        score += 0.5

    return score


# ────────────────────────────────────────────────────────────────────────────────
# Spotify helpers
# ────────────────────────────────────────────────────────────────────────────────

async def _spotify_track(track_id: str) -> dict | None:
    """Resolve a Spotify track ID to metadata."""
    if not sp:
        return None
    loop = asyncio.get_running_loop()
    try:
        info = await loop.run_in_executor(
            _ytdl_executor, lambda: sp.track(track_id)
        )
        artists = ", ".join(a['name'] for a in info.get('artists', []))
        images = info.get('album', {}).get('images', [])
        return {
            'name': info['name'],
            'artists': artists,
            'query': f"{info['name']} {artists}",
            'duration_ms': info.get('duration_ms', 0),
            'thumbnail': images[0]['url'] if images else None,
        }
    except Exception as e:
        logger.error("Spotify track resolution failed: %s", e)
        return None


async def _spotify_playlist_tracks(playlist_id: str) -> list[dict]:
    """Resolve every track in a Spotify playlist."""
    if not sp:
        return []
    loop = asyncio.get_running_loop()
    try:
        tracks: list[dict] = []
        results = await loop.run_in_executor(
            _ytdl_executor, lambda: sp.playlist_tracks(playlist_id)
        )
        while results:
            for item in results.get('items', []):
                t = item.get('track')
                if not t:
                    continue
                artists = ", ".join(a['name'] for a in t.get('artists', []))
                images = t.get('album', {}).get('images', [])
                tracks.append({
                    'name': t['name'],
                    'artists': artists,
                    'query': f"{t['name']} {artists}",
                    'thumbnail': images[0]['url'] if images else None,
                })
            # Spotify paginates — fetch next page if available
            if results.get('next'):
                results = await loop.run_in_executor(
                    _ytdl_executor, lambda r=results: sp.next(r)
                )
            else:
                break
        return tracks
    except Exception as e:
        logger.error("Spotify playlist resolution failed: %s", e)
        return []


async def _spotify_album_tracks(album_id: str) -> list[dict]:
    """Resolve every track in a Spotify album."""
    if not sp:
        return []
    loop = asyncio.get_running_loop()
    try:
        # Get album details for cover art
        album_info = await loop.run_in_executor(
            _ytdl_executor, lambda: sp.album(album_id)
        )
        album_images = album_info.get('images', [])
        album_thumb = album_images[0]['url'] if album_images else None

        tracks: list[dict] = []
        results = await loop.run_in_executor(
            _ytdl_executor, lambda: sp.album_tracks(album_id)
        )
        while results:
            for t in results.get('items', []):
                artists = ", ".join(a['name'] for a in t.get('artists', []))
                tracks.append({
                    'name': t['name'],
                    'artists': artists,
                    'query': f"{t['name']} {artists}",
                    'thumbnail': album_thumb,
                })
            if results.get('next'):
                results = await loop.run_in_executor(
                    _ytdl_executor, lambda r=results: sp.next(r)
                )
            else:
                break
        return tracks
    except Exception as e:
        logger.error("Spotify album resolution failed: %s", e)
        return []


async def _spotify_search(query: str) -> dict | None:
    """Search Spotify API for metadata (not playable — used for scoring)."""
    if not sp:
        return None
    loop = asyncio.get_running_loop()
    try:
        results = await loop.run_in_executor(
            _ytdl_executor, lambda: sp.search(q=query, type='track', limit=1)
        )
        items = results.get('tracks', {}).get('items', [])
        if not items:
            return None
        t = items[0]
        artists = ", ".join(a['name'] for a in t.get('artists', []))
        return {
            'name': t['name'],
            'artists': artists,
            'query': f"{t['name']} {artists}",
            'duration_ms': t.get('duration_ms', 0),
        }
    except Exception as e:
        logger.debug("Spotify API search failed: %s", e)
        return None


# ────────────────────────────────────────────────────────────────────────────────
# URL pattern helpers
# ────────────────────────────────────────────────────────────────────────────────

_RE_SPOTIFY_TRACK = re.compile(r"spotify\.com/track/([a-zA-Z0-9]+)")
_RE_SPOTIFY_PLAYLIST = re.compile(r"spotify\.com/playlist/([a-zA-Z0-9]+)")
_RE_SPOTIFY_ALBUM = re.compile(r"spotify\.com/album/([a-zA-Z0-9]+)")


def is_playlist_url(query: str) -> bool:
    """Check if the query is a Spotify playlist or album URL."""
    return bool(_RE_SPOTIFY_PLAYLIST.search(query) or _RE_SPOTIFY_ALBUM.search(query))


def _detect_url_platform(url: str) -> str:
    """Detect platform from a URL string."""
    if "youtube" in url or "youtu.be" in url:
        return "YouTube"
    if "soundcloud" in url:
        return "SoundCloud"
    if "spotify" in url:
        return "Spotify"
    return "Unknown"


def _detect_platform(track: dict) -> str:
    """Detect platform from a track dict — prefers the explicit 'platform'
    field from the extractor, falls back to URL-based detection."""
    if track.get('platform'):
        return track['platform']
    url = track.get('webpage_url', '') or track.get('url', '')
    return _detect_url_platform(url)


# ────────────────────────────────────────────────────────────────────────────────
# YTDLSource — main extractor
# ────────────────────────────────────────────────────────────────────────────────

class YTDLSource:
    _local = threading.local()

    @classmethod
    def _get_ytdl(cls) -> yt_dlp.YoutubeDL:
        """Return a thread-local YoutubeDL instance (thread-safe)."""
        if not hasattr(cls._local, 'ytdl'):
            cls._local.ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
        return cls._local.ytdl

    # ── Single-platform search ────────────────────────────────────────────

    @classmethod
    async def _search_single(
        cls, search_query: str, platform: str,
    ) -> dict | None:
        """Run a single yt-dlp search and return the first result."""
        loop = asyncio.get_running_loop()
        try:
            data = await loop.run_in_executor(
                _ytdl_executor,
                lambda: cls._get_ytdl().extract_info(search_query, download=False),
            )
        except Exception as e:
            logger.debug("Search failed on %s: %s", platform, e)
            return None

        if not data:
            return None
        if 'entries' in data:
            entries = data['entries']
            if not entries:
                return None
            data = entries[0]
        if not data.get('url'):
            return None

        return {
            'url': data['url'],
            'webpage_url': data.get('webpage_url', search_query),
            'title': data.get('title', 'Unknown Title'),
            'thumbnail': data.get('thumbnail'),
            'duration': data.get('duration', 0),
            'uploader': data.get('uploader', 'Unknown Artist'),
            'platform': platform,
        }

    # ── Multi-platform search ─────────────────────────────────────────────

    @classmethod
    async def _multi_search(cls, query: str) -> dict | None:
        """Search YouTube + SoundCloud in parallel, optionally use Spotify
        metadata for scoring.  Returns the best match."""

        yt_task = asyncio.create_task(
            cls._search_single(f"ytsearch:{query}", "YouTube")
        )
        sc_task = asyncio.create_task(
            cls._search_single(f"scsearch:{query}", "SoundCloud")
        )
        sp_task = asyncio.create_task(_spotify_search(query)) if sp else None

        yt_result, sc_result = await asyncio.gather(yt_task, sc_task)
        spotify_meta = await sp_task if sp_task else None

        # Collect & score candidates
        candidates: list[tuple[float, str, dict]] = []
        for platform, result in [("YouTube", yt_result), ("SoundCloud", sc_result)]:
            if not result:
                continue
            score = _score_result(query, result)

            # Boost if Spotify metadata confirms this is the right track
            if spotify_meta:
                sp_query = spotify_meta['query'].lower()
                res_title = result.get('title', '').lower()
                if _title_similarity(sp_query, res_title) > 0.6:
                    score += 3.0

            candidates.append((score, platform, result))
            logger.info(
                "Search result [%s] score=%.1f: %s",
                platform, score, result.get('title', '?'),
            )

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        _best_score, best_platform, best_result = candidates[0]
        logger.info(
            "Best match: [%s] %s (score=%.1f)",
            best_platform, best_result.get('title'), _best_score,
        )
        return best_result

    # ── Direct URL extraction ─────────────────────────────────────────────

    @classmethod
    async def _extract_url(cls, url: str) -> dict | None:
        """Extract info from a direct URL (YT, SC, or any yt-dlp supported)."""
        loop = asyncio.get_running_loop()
        platform = _detect_url_platform(url)
        try:
            data = await loop.run_in_executor(
                _ytdl_executor,
                lambda: cls._get_ytdl().extract_info(url, download=False),
            )
        except Exception as e:
            logger.error("Failed to extract URL (%s): %s", url, e)
            return None

        if not data:
            return None
        if 'entries' in data:
            entries = data['entries']
            if not entries:
                return None
            data = entries[0]

        return {
            'url': data['url'],
            'webpage_url': data.get('webpage_url', url),
            'title': data.get('title', 'Unknown Title'),
            'thumbnail': data.get('thumbnail'),
            'duration': data.get('duration', 0),
            'uploader': data.get('uploader', 'Unknown Artist'),
            'platform': platform,
        }

    # ── Public API: single track ──────────────────────────────────────────

    @classmethod
    async def extract_info(cls, query: str) -> dict | None:
        """Extract info for a single track.

        Handles:
        - Spotify track links → resolve via API, then multi-search YT+SC
        - YouTube / SoundCloud / other URLs → direct yt-dlp extraction
        - Plain text → multi-platform parallel search (YT + SC)
        """

        # ── Spotify track link ────────────────────────────────────────
        m = _RE_SPOTIFY_TRACK.search(query)
        if m:
            meta = await _spotify_track(m.group(1))
            if meta:
                logger.info("Resolved Spotify track → %s", meta['query'])
                result = await cls._multi_search(meta['query'])
                if result:
                    # Prefer Spotify thumbnail if the search result lacks one
                    if meta.get('thumbnail') and not result.get('thumbnail'):
                        result['thumbnail'] = meta['thumbnail']
                    return result
            # Fallback: try as raw text search
            return await cls._multi_search(query)

        # ── Direct URL (YouTube, SoundCloud, etc.) ────────────────────
        if query.startswith(('http://', 'https://')):
            return await cls._extract_url(query)

        # ── Plain text search → multi-platform ────────────────────────
        return await cls._multi_search(query)

    # ── Public API: playlist / album ──────────────────────────────────────

    @classmethod
    async def extract_playlist(cls, query: str) -> list[dict] | None:
        """Extract track metadata from a Spotify playlist or album.

        Returns a list of dicts with ``query``, ``name``, ``artists``,
        and ``thumbnail`` keys — each must still be resolved to a playable
        stream via :meth:`extract_info` or :meth:`_search_single`.
        """
        m = _RE_SPOTIFY_PLAYLIST.search(query)
        if m:
            tracks = await _spotify_playlist_tracks(m.group(1))
            return tracks[:MAX_PLAYLIST_SIZE] if tracks else None

        m = _RE_SPOTIFY_ALBUM.search(query)
        if m:
            tracks = await _spotify_album_tracks(m.group(1))
            return tracks[:MAX_PLAYLIST_SIZE] if tracks else None

        return None

    @classmethod
    async def resolve_playlist_track(cls, search_query: str) -> dict | None:
        """Fast resolver for playlist tracks — searches YouTube only for speed."""
        return await cls._search_single(f"ytsearch:{search_query}", "YouTube")
