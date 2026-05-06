import unittest

from cogs.music import Music, _track_autocomplete


class MusicCommandShapeTests(unittest.TestCase):
    def test_music_commands_are_flat_top_level_commands(self):
        names = {command.name for command in Music.__cog_app_commands__}

        self.assertIn("play", names)
        self.assertIn("skip", names)
        self.assertIn("stop", names)
        self.assertIn("queue", names)
        self.assertIn("nowplaying", names)
        self.assertIn("filter", names)
        self.assertIn("save", names)
        self.assertIn("load", names)
        self.assertIn("saved", names)
        self.assertIn("lyrics", names)
        self.assertNotIn("music", names)
        self.assertNotIn("filters", names)

    def test_queue_command_exposes_management_actions(self):
        command = next(command for command in Music.__cog_app_commands__ if command.name == "queue")
        params = {parameter.name: parameter for parameter in command.parameters}

        self.assertTrue(params["action"].required)
        self.assertFalse(params["index"].required)
        self.assertFalse(params["target"].required)
        self.assertEqual(
            [choice.value for choice in params["action"].choices],
            ["view", "clear", "remove", "move"],
        )

    def test_play_command_uses_track_autocomplete(self):
        command = next(command for command in Music.__cog_app_commands__ if command.name == "play")

        self.assertIs(command._params["query"].autocomplete, _track_autocomplete)


if __name__ == "__main__":
    unittest.main()
