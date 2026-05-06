import unittest

from services.web_dashboard import DashboardServer, RateLimiter, _encrypt_password


class _FakeProcess:
    def cpu_percent(self, interval=None):
        return 0.0

    def memory_info(self):
        class Info:
            rss = 0

        return Info()


class _FakeDB:
    def __init__(self):
        self.user = {
            "id": 1,
            "username": "admin",
            "password_hash": "hash",
            "is_admin": True,
            "can_restart": True,
            "can_view_logs": True,
        }

    async def upsert_admin_user(self, username, password_hash):
        return None

    async def get_dashboard_user(self, username):
        if username == self.user["username"]:
            return dict(self.user)
        return None

    async def list_dashboard_users(self):
        return [
            {
                "id": 1,
                "username": "admin",
                "is_admin": True,
                "can_restart": True,
                "can_view_logs": True,
                "created_at": "2026-05-06",
                "password_encrypted": "",
            }
        ]


class _FakeBot:
    guilds = []
    voice_clients = []
    latency = 0
    db = _FakeDB()


class DashboardSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_rate_limiter_resets_successful_login_key(self):
        limiter = RateLimiter(max_attempts=2, window_seconds=300)
        limiter.record_attempt("client")
        limiter.record_attempt("client")
        self.assertTrue(limiter.is_rate_limited("client"))

        limiter.reset("client")

        self.assertFalse(limiter.is_rate_limited("client"))

    async def test_untrusted_forwarded_for_is_ignored(self):
        server = DashboardServer(_FakeBot(), 25825, "admin", "password")
        server._process = _FakeProcess()

        async with server.app.test_request_context(
            "/api/login",
            method="POST",
            headers={"X-Forwarded-For": "198.51.100.7"},
        ):
            self.assertEqual(server._get_client_ip(), "unknown")

    async def test_stats_include_safe_audio_status(self):
        server = DashboardServer(_FakeBot(), 25825, "admin", "password")
        server._process = _FakeProcess()

        stats = server._get_stats()

        self.assertIn("sampled_at", stats)
        self.assertIn("audio", stats)
        self.assertIn("configured_backend", stats["audio"])
        self.assertIn("effective_backend", stats["audio"])
        self.assertIn("lavalink_uri", stats["audio"])
        self.assertNotIn("password", stats["audio"]["lavalink_uri"].lower())

    async def test_stats_history_uses_timestamped_bucket_averages(self):
        history = [
            (1.0, 10.0, 100.0, 20),
            (2.0, 30.0, 200.0, 40),
            (3.0, 50.0, 300.0, 60),
            (4.0, 70.0, 400.0, 80),
        ]

        sampled = DashboardServer._downsample_stats_history(history, max_points=2)

        self.assertEqual(sampled, [(2.0, 20.0, 150.0, 30), (4.0, 60.0, 350.0, 70)])

    async def test_users_endpoint_preserves_admin_password_display(self):
        bot = _FakeBot()
        server = DashboardServer(bot, 25825, "admin", "password")
        bot.db.user["password_encrypted"] = _encrypt_password(server.fernet, "visible-secret")
        bot.db.list_dashboard_users = lambda: _list_users(bot.db.user)  # type: ignore[method-assign]
        token = server.signer.create_token("admin", True, True, True)

        client = server.app.test_client()
        response = await client.get("/api/users", headers={"Cookie": f"DASH_SESSION={token}"})
        payload = await response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload[0]["password_display"], "visible-secret")
        self.assertNotIn("password_encrypted", payload[0])


async def _list_users(user):
    return [
        {
            "id": user["id"],
            "username": user["username"],
            "is_admin": user["is_admin"],
            "can_restart": user["can_restart"],
            "can_view_logs": user["can_view_logs"],
            "created_at": "2026-05-06",
            "password_encrypted": user["password_encrypted"],
        }
    ]


if __name__ == "__main__":
    unittest.main()
