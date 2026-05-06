import os
import tempfile
import unittest

from services import database
from services.database import Database


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._old_db_path = database.DB_PATH
        self._tmp = tempfile.NamedTemporaryFile(delete=False)
        self._tmp.close()
        database.DB_PATH = self._tmp.name
        self.db = Database()
        await self.db.connect()

    async def asyncTearDown(self):
        await self.db.close()
        database.DB_PATH = self._old_db_path
        try:
            os.unlink(self._tmp.name)
        except FileNotFoundError:
            pass

    async def test_guild_language_defaults_and_updates(self):
        self.assertEqual(await self.db.get_guild_language(123), "en")

        await self.db.set_guild_language(123, "hu")

        self.assertEqual(await self.db.get_guild_language(123), "hu")

    async def test_dashboard_user_lifecycle(self):
        user = await self.db.create_dashboard_user(
            "moderator",
            "hash-v1",
            "encrypted-v1",
            can_restart=True,
            can_view_logs=False,
        )

        fetched = await self.db.get_dashboard_user("moderator")
        self.assertEqual(fetched["username"], "moderator")
        self.assertTrue(fetched["can_restart"])
        self.assertFalse(fetched["can_view_logs"])

        listed = await self.db.list_dashboard_users()
        self.assertEqual(listed[0]["password_encrypted"], "encrypted-v1")

        updated = await self.db.update_dashboard_user(
            user["id"],
            password_hash="hash-v2",
            password_encrypted="encrypted-v2",
            can_restart=False,
            can_view_logs=True,
        )
        self.assertTrue(updated)

        fetched = await self.db.get_dashboard_user("moderator")
        self.assertEqual(fetched["password_hash"], "hash-v2")
        self.assertFalse(fetched["can_restart"])
        self.assertTrue(fetched["can_view_logs"])

        self.assertTrue(await self.db.delete_dashboard_user(user["id"]))
        self.assertIsNone(await self.db.get_dashboard_user("moderator"))

    async def test_admin_user_cannot_be_deleted_by_regular_delete_path(self):
        await self.db.upsert_admin_user("admin", "hash")
        admin = await self.db.get_dashboard_user("admin")

        self.assertFalse(await self.db.delete_dashboard_user(admin["id"]))
        self.assertIsNotNone(await self.db.get_dashboard_user("admin"))

    async def test_saved_music_queue_lifecycle(self):
        items = [
            {
                "position": 1,
                "title": "Song A",
                "webpage_url": "https://example.test/a",
                "duration": 100,
                "source": "YouTube",
            },
            {
                "position": 2,
                "title": "Song B",
                "webpage_url": "https://example.test/b",
                "duration": 200,
                "source": "SoundCloud",
            },
        ]

        queue_id = await self.db.save_music_queue(123, "Favorites", 999, items)
        self.assertGreater(queue_id, 0)

        saved = await self.db.list_saved_music_queues(123)
        self.assertEqual(saved[0]["name"], "Favorites")
        self.assertEqual(saved[0]["item_count"], 2)

        loaded = await self.db.load_saved_music_queue(123, "favorites")
        self.assertEqual([row["title"] for row in loaded], ["Song A", "Song B"])

        await self.db.save_music_queue(123, "Favorites", 999, items[:1])
        loaded = await self.db.load_saved_music_queue(123, "Favorites")
        self.assertEqual(len(loaded), 1)


if __name__ == "__main__":
    unittest.main()
