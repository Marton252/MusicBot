import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cogs.music import _require_player_control


class MusicGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_unauthorized_control(self):
        interaction = SimpleNamespace(
            guild_id=123,
            response=SimpleNamespace(send_message=AsyncMock()),
        )
        player = SimpleNamespace(current={"requester_id": 1})

        with (
            patch("cogs.music._can_control", return_value=False),
            patch("cogs.music.language.get_string", new=AsyncMock(return_value="denied")),
        ):
            allowed = await _require_player_control(interaction, player)

        self.assertFalse(allowed)
        interaction.response.send_message.assert_awaited_once()

    async def test_rejects_member_outside_bot_voice_channel(self):
        interaction = SimpleNamespace(
            guild_id=123,
            response=SimpleNamespace(send_message=AsyncMock()),
        )
        player = SimpleNamespace(current={"requester_id": 1})

        with (
            patch("cogs.music._can_control", return_value=True),
            patch("cogs.music._is_same_voice", return_value=False),
            patch("cogs.music.language.get_string", new=AsyncMock(return_value="same voice required")),
        ):
            allowed = await _require_player_control(interaction, player)

        self.assertFalse(allowed)
        interaction.response.send_message.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
