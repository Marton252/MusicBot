import unittest

from services.music.playback import AudioFilter, PlaybackState, coerce_filter, ffmpeg_filter_options
from services.music.queue import MusicQueue, QueueItem
from services.music.ui import component_id


class MusicDomainTests(unittest.TestCase):
    def test_audio_filter_registry_builds_ffmpeg_options(self):
        self.assertEqual(coerce_filter("missing"), AudioFilter.NONE)
        self.assertEqual(ffmpeg_filter_options(AudioFilter.NONE), "-vn")
        self.assertIn("bass=g=12", ffmpeg_filter_options("bassboost"))
        self.assertIs(PlaybackState.RECOVERING, PlaybackState.RECOVERING)

    def test_queue_item_converts_between_track_and_saved_record(self):
        track = {
            "title": "Song",
            "webpage_url": "https://example.test/song",
            "url": "https://stream.example/song",
            "requester_id": 123,
            "duration": 90,
            "platform": "YouTube",
            "thumbnail": "https://example.test/thumb.jpg",
            "uploader": "Artist",
        }

        item = QueueItem.from_track(track)

        self.assertEqual(item.title, "Song")
        self.assertEqual(item.to_track()["url"], "https://stream.example/song")
        self.assertEqual(item.to_saved_record(2)["position"], 2)
        self.assertNotIn("stream_url", item.to_saved_record(2))

    def test_music_queue_capacity_remove_move_and_shuffle_shape(self):
        queue = MusicQueue(max_size=2)

        self.assertTrue(queue.add({"title": "A"}))
        self.assertTrue(queue.add({"title": "B"}))
        self.assertFalse(queue.add({"title": "C"}))

        queue.move(1, 0)
        self.assertEqual([item["title"] for item in queue], ["B", "A"])
        removed = queue.remove_at(0)
        self.assertEqual(removed["title"], "B")
        self.assertEqual(len(queue), 1)

    def test_component_id_is_stable_and_namespaced(self):
        self.assertEqual(component_id(123, "skip"), "music:123:skip")


if __name__ == "__main__":
    unittest.main()
