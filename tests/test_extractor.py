import unittest
from unittest.mock import AsyncMock, patch

from services import extractor
from services.extractor import YTDLSource


class ExtractorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        extractor._info_cache.clear()

    def test_detects_supported_platforms(self):
        self.assertEqual(extractor._detect_url_platform("https://youtube.com/watch?v=x"), "YouTube")
        self.assertEqual(extractor._detect_url_platform("https://youtu.be/x"), "YouTube")
        self.assertEqual(extractor._detect_url_platform("https://soundcloud.com/a/b"), "SoundCloud")
        self.assertEqual(extractor._detect_url_platform("https://open.spotify.com/track/abc"), "Spotify")
        self.assertEqual(extractor._detect_url_platform("https://example.com"), "Unknown")

    def test_detects_spotify_playlist_or_album_urls(self):
        self.assertTrue(extractor.is_playlist_url("https://open.spotify.com/playlist/abc123"))
        self.assertTrue(extractor.is_playlist_url("https://open.spotify.com/album/abc123"))
        self.assertFalse(extractor.is_playlist_url("https://open.spotify.com/track/abc123"))

    async def test_extract_info_caches_plain_text_queries(self):
        result = {
            "url": "https://stream.example/audio",
            "webpage_url": "https://example.test",
            "title": "Song",
            "duration": 123,
        }

        with patch.object(YTDLSource, "_multi_search", new=AsyncMock(return_value=result)) as search:
            first = await YTDLSource.extract_info("Song Name")
            second = await YTDLSource.extract_info("song name")

        self.assertEqual(first["title"], "Song")
        self.assertEqual(second["title"], "Song")
        self.assertIsNot(first, second)
        search.assert_awaited_once()

    async def test_extract_info_caches_direct_urls(self):
        result = {
            "url": "https://stream.example/audio",
            "webpage_url": "https://example.test/watch",
            "title": "Direct Song",
            "duration": 123,
        }

        with patch.object(YTDLSource, "_extract_url", new=AsyncMock(return_value=result)) as extract_url:
            first = await YTDLSource.extract_info("https://example.test/watch")
            second = await YTDLSource.extract_info("https://example.test/watch")

        self.assertEqual(first["title"], "Direct Song")
        self.assertEqual(second["title"], "Direct Song")
        extract_url.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
