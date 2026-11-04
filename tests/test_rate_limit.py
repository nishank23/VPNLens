import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import create_app
from vpnlens.config import Settings
from vpnlens.database import SourcesUnavailable


class ApiRateLimitTests(unittest.TestCase):
    def test_direct_client_cannot_rotate_forwarded_headers_or_routes(self):
        app = create_app(Settings(api_requests_per_minute=2))
        client = TestClient(app, client=("8.8.8.8", 50000))
        with patch("api.main.read_connection", side_effect=SourcesUnavailable) as connect:
            self.assertEqual(client.get("/v1/connection").status_code, 503)
            self.assertEqual(client.get("/v1/sources").status_code, 503)
            response = client.get("/v1/lookup/9.9.9.9", headers={"X-Forwarded-For": "1.1.1.1"})
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.json(), {"detail": "rate_limit_exceeded"})
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertTrue(1 <= int(response.headers["Retry-After"]) <= 60)
            self.assertEqual(client.get("/health/ready").status_code, 429)
            self.assertEqual(client.get("/health/live").status_code, 200)
            self.assertEqual(connect.call_count, 2)

    def test_proxy_clients_have_separate_quotas_and_share_the_global_cap(self):
        settings = Settings(
            trusted_proxy_cidrs=("127.0.0.1/32",),
            api_requests_per_minute=1,
            api_total_requests_per_minute=2,
        )
        with patch("vpnlens.rate_limit.monotonic", return_value=100) as clock:
            client = TestClient(create_app(settings), client=("127.0.0.1", 50000))

            def check(forwarded_for):
                return client.get("/v1/sources", headers={"X-Forwarded-For": forwarded_for})

            with patch("api.main.read_connection", side_effect=SourcesUnavailable) as connect:
                self.assertEqual(check("8.8.8.8").status_code, 503)
                clock.return_value = 102.5
                limited = check("9.9.9.9, 8.8.8.8")
                self.assertEqual(limited.status_code, 429)
                self.assertEqual(limited.headers["Retry-After"], "58")
                self.assertEqual(check("1.1.1.1").status_code, 503)
                self.assertEqual(check("9.9.9.9").status_code, 429)
                self.assertEqual(connect.call_count, 2)
                clock.return_value = 160
                self.assertEqual(check("8.8.8.8").status_code, 503)
                self.assertEqual(connect.call_count, 3)

    def test_invalid_proxy_chains_share_one_bucket(self):
        settings = Settings(
            trusted_proxy_cidrs=("127.0.0.1/32",),
            api_requests_per_minute=1,
        )
        client = TestClient(create_app(settings), client=("127.0.0.1", 50000))
        self.assertEqual(client.get("/v1/connection").status_code, 409)
        self.assertEqual(
            client.get("/v1/connection", headers={"X-Forwarded-For": "bad,8.8.8.8"}).status_code,
            429,
        )

    def test_limits_are_opt_in_and_require_a_valid_total(self):
        self.assertEqual(Settings().api_requests_per_minute, 0)
        with self.assertRaises(ValueError):
            Settings(api_requests_per_minute=31, api_total_requests_per_minute=30)
