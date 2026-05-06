import unittest

from services.web_dashboard import DashboardServer, RateLimiter


class _FakeProcess:
    def cpu_percent(self, interval=None):
        return 0.0

    def memory_info(self):
        class Info:
            rss = 0

        return Info()


class _FakeDB:
    async def upsert_admin_user(self, username, password_hash):
        return None


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


if __name__ == "__main__":
    unittest.main()
