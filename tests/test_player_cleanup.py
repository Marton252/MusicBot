import asyncio
import unittest

from services.player import MusicPlayer


class _FakeSource:
    def __init__(self):
        self.cleaned = False

    def cleanup(self):
        self.cleaned = True


class _FakeVoiceClient:
    def __init__(self):
        self.source = _FakeSource()
        self.disconnected = False
        self.stopped = False

    def is_playing(self):
        return True

    def is_paused(self):
        return False

    def stop(self):
        self.stopped = True

    async def disconnect(self):
        self.disconnected = True


class _FakeBot:
    def __init__(self):
        self.loop = asyncio.get_running_loop()

    async def wait_until_ready(self):
        return None

    def is_closed(self):
        return False


class _FakeCog:
    async def cleanup(self, guild):
        return None


class PlayerCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_close_cancels_player_task_and_disconnects_voice(self):
        voice_client = _FakeVoiceClient()
        guild = type("Guild", (), {"id": 123, "voice_client": voice_client})()
        player = MusicPlayer(_FakeBot(), guild, None, _FakeCog())

        await asyncio.sleep(0)
        await player.close()

        self.assertTrue(player.task.done())
        self.assertTrue(voice_client.stopped)
        self.assertTrue(voice_client.source.cleaned)
        self.assertTrue(voice_client.disconnected)


if __name__ == "__main__":
    unittest.main()
