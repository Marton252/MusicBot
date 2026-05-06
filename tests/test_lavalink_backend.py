import unittest
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from cogs.music import Music
from services.music import lavalink
from services.music.backends import FFmpegBackend, LavalinkBackend, _lavalink_filters, create_backend
from services.music.playback import AudioFilter
from services.player import manager


class LavalinkBackendTests(unittest.TestCase):
    def setUp(self):
        self._backend = lavalink.MUSIC_BACKEND
        self._connected = lavalink._connected

    def tearDown(self):
        lavalink.MUSIC_BACKEND = self._backend
        lavalink._connected = self._connected

    def test_backend_selection_defaults_to_ffmpeg(self):
        lavalink.MUSIC_BACKEND = "ffmpeg"
        lavalink._connected = False

        self.assertIsInstance(create_backend(), FFmpegBackend)

    def test_backend_selection_uses_lavalink_when_connected(self):
        lavalink.MUSIC_BACKEND = "lavalink"
        lavalink._connected = True

        self.assertIsInstance(create_backend(), LavalinkBackend)

    def test_auto_backend_falls_back_until_lavalink_connects(self):
        lavalink.MUSIC_BACKEND = "auto"
        lavalink._connected = False
        self.assertEqual(lavalink.effective_backend(), "ffmpeg")

        lavalink._connected = True
        self.assertEqual(lavalink.effective_backend(), "lavalink")

    def test_strict_lavalink_unavailable_detects_missing_node(self):
        lavalink.MUSIC_BACKEND = "lavalink"
        lavalink._connected = False

        self.assertTrue(lavalink.strict_lavalink_unavailable())
        self.assertTrue(lavalink.should_use_lavalink_path())

    def test_lavalink_filter_mapping_builds_payloads(self):
        bassboost = _lavalink_filters(AudioFilter.BASSBOOST)
        nightcore = _lavalink_filters(AudioFilter.NIGHTCORE)
        karaoke = _lavalink_filters(AudioFilter.KARAOKE)
        eight_d = _lavalink_filters(AudioFilter.EIGHT_D)

        self.assertIn("gain", repr(bassboost.equalizer))
        self.assertIn("speed", repr(nightcore.timescale))
        self.assertIn("filterBand", repr(karaoke.karaoke))
        self.assertIn("rotationHz", repr(eight_d.rotation))


class _FakeLavalinkVoice:
    def __init__(self):
        self.pauses = []
        self.volume = None
        self.filters = None
        self.stopped = False
        self.disconnected = False
        self.play_calls = []

    async def play(self, playable, **kwargs):
        self.play_calls.append((playable, kwargs))

    async def pause(self, value):
        self.pauses.append(value)

    async def stop(self):
        self.stopped = True

    async def set_volume(self, value):
        self.volume = value

    async def set_filters(self, filters, **kwargs):
        self.filters = (filters, kwargs)

    async def disconnect(self):
        self.disconnected = True


class LavalinkAdapterAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_lavalink_adapter_controls_mocked_player(self):
        backend = LavalinkBackend()
        voice = _FakeLavalinkVoice()
        guild = SimpleNamespace(voice_client=voice)
        player = SimpleNamespace(
            guild=guild,
            volume=0.75,
            active_filter=AudioFilter.NIGHTCORE,
            next=SimpleNamespace(set=lambda: None),
        )

        await backend.pause(player)
        await backend.resume(player)
        await backend.stop(player)
        await backend.set_volume(player, 0.5)
        await backend.set_filter(player, AudioFilter.BASSBOOST)
        await backend.disconnect(player)

        self.assertEqual(voice.pauses, [True, False])
        self.assertTrue(voice.stopped)
        self.assertEqual(voice.volume, 50)
        self.assertIsNotNone(voice.filters)
        self.assertTrue(voice.disconnected)

    async def test_node_disconnect_marks_players_recovering_and_preserves_current(self):
        bot = SimpleNamespace()
        cog = Music(bot)
        player = SimpleNamespace(
            backend=SimpleNamespace(name="lavalink"),
            state=None,
            last_error=None,
            current={"title": "Song"},
            queue=deque(),
            _queue_ready=Mock(),
            next=Mock(),
        )
        original = dict(manager.players)
        manager.players.clear()
        manager.players[123] = player
        lavalink._connected = True

        try:
            await cog.on_wavelink_node_disconnected(SimpleNamespace())
        finally:
            manager.players.clear()
            manager.players.update(original)

        self.assertFalse(lavalink._connected)
        self.assertEqual(player.state.value, "recovering")
        self.assertEqual(player.queue[0]["title"], "Song")
        player._queue_ready.set.assert_called_once()
        player.next.set.assert_called_once()

    async def test_connect_lavalink_retries_until_node_is_ready(self):
        lavalink.MUSIC_BACKEND = "lavalink"
        lavalink._connected = False
        node = Mock()
        fake_wavelink = SimpleNamespace(
            Node=Mock(return_value=node),
            Pool=SimpleNamespace(connect=AsyncMock(side_effect=[RuntimeError("booting"), {"main": node}])),
        )

        with (
            patch.object(lavalink, "_import_wavelink", return_value=fake_wavelink),
            patch.object(lavalink, "LAVALINK_CONNECT_RETRIES", 2),
            patch.object(lavalink, "LAVALINK_CONNECT_RETRY_DELAY", 0.01),
        ):
            await lavalink.connect_lavalink(SimpleNamespace())

        self.assertTrue(lavalink._connected)
        self.assertEqual(fake_wavelink.Pool.connect.await_count, 2)


if __name__ == "__main__":
    unittest.main()
