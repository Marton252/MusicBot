import unittest

from services import lyrics
from services.lyrics import LyricsService


class LyricsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        lyrics._lyrics_cache.clear()

    async def test_fetch_lyrics_caches_successful_results(self):
        service = LyricsService()
        calls = 0

        def fake_fetch(search_query: str) -> str:
            nonlocal calls
            calls += 1
            return f"lyrics for {search_query}"

        service._sync_fetch = fake_fetch

        first = await service.fetch_lyrics("Artist Song")
        second = await service.fetch_lyrics("artist song")

        self.assertEqual(first, "lyrics for Artist Song")
        self.assertEqual(second, "lyrics for Artist Song")
        self.assertEqual(calls, 1)

    async def test_fetch_lyrics_does_not_cache_missing_results(self):
        service = LyricsService()
        calls = 0

        def fake_fetch(search_query: str) -> None:
            nonlocal calls
            calls += 1
            return None

        service._sync_fetch = fake_fetch

        self.assertIsNone(await service.fetch_lyrics("missing"))
        self.assertIsNone(await service.fetch_lyrics("missing"))
        self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
