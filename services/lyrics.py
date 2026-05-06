import asyncio
import concurrent.futures
import logging
import time

import lyricsgenius

from config import GENIUS_ACCESS_TOKEN

logger = logging.getLogger('MusicBot.Lyrics')

# Dedicated thread pool so slow Genius HTTP requests
# don't starve the default executor used by other services.
_lyrics_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="lyrics"
)
_CACHE_TTL_SECONDS = 600
_lyrics_cache: dict[str, tuple[float, str]] = {}


def shutdown_lyrics_executor() -> None:
    _lyrics_executor.shutdown(wait=False, cancel_futures=True)


class LyricsService:
    def __init__(self) -> None:
        self.genius: lyricsgenius.Genius | None = None
        if GENIUS_ACCESS_TOKEN:
            try:
                self.genius = lyricsgenius.Genius(
                    GENIUS_ACCESS_TOKEN, remove_section_headers=True,
                )
                self.genius.verbose = False
                logger.info("Genius API configured.")
            except Exception as e:
                logger.error("Failed to configure Genius API: %s", e)

    def _sync_fetch(self, search_query: str) -> str | None:
        """Synchronous fetch — called inside an executor."""
        if not self.genius:
            return None
        try:
            song = self.genius.search_song(search_query)
            if song:
                return song.lyrics
            return None
        except Exception as e:
            logger.error("Lyrics fetch error: %s", e)
            return None

    async def fetch_lyrics(self, search_query: str) -> str | None:
        cache_key = search_query.strip().lower()
        cached = _lyrics_cache.get(cache_key)
        if cached:
            expires_at, value = cached
            if expires_at > time.monotonic():
                return value
            _lyrics_cache.pop(cache_key, None)

        lyrics = await asyncio.get_running_loop().run_in_executor(
            _lyrics_executor, self._sync_fetch, search_query,
        )
        if lyrics:
            _lyrics_cache[cache_key] = (time.monotonic() + _CACHE_TTL_SECONDS, lyrics)
        return lyrics


lyrics_service = LyricsService()
