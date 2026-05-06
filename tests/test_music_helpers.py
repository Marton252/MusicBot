import unittest

from cogs.music import _clean_song_title, _format_duration, _split_text


class MusicHelperTests(unittest.TestCase):
    def test_format_duration_handles_regular_and_live_tracks(self):
        self.assertEqual(_format_duration(0), "Live")
        self.assertEqual(_format_duration(65), "1:05")
        self.assertEqual(_format_duration(3661), "1:01:01")

    def test_split_text_prefers_line_boundaries(self):
        chunks = _split_text("one\ntwo\nthree", 8)

        self.assertEqual(chunks, ["one\ntwo", "three"])

    def test_clean_song_title_removes_common_video_noise(self):
        track = {
            "title": "Artist - Song (Official Music Video)",
            "uploader": "ArtistVEVO",
        }

        self.assertEqual(_clean_song_title(track), "Artist - Song")

    def test_clean_song_title_adds_useful_uploader(self):
        track = {
            "title": "Song [Official Audio]",
            "uploader": "Artist",
        }

        self.assertEqual(_clean_song_title(track), "Artist Song")


if __name__ == "__main__":
    unittest.main()
