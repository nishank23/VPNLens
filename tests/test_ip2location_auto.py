"""Monthly IP2Location automation with fixture downloads and isolated PostgreSQL."""

import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import psycopg
from backend_support import DatabaseCase

from vpnlens.ip2location_schedule import (
    configured_download_url,
    download_eligibility,
    monthly_download_date,
)
from vpnlens.refresh import read_state, refresh_datasets

NOVEMBER = datetime(2026, 11, 10, 12, tzinfo=UTC)
DECEMBER = datetime(2026, 12, 10, 12, tzinfo=UTC)
TEST_URL = "https://example.test/download?token=fixture-secret"


class MonthlyPolicyTests(TestCase):
    def test_token_encoding_package_and_explicit_url_override(self):
        with patch.dict(os.environ, {"IP2LOCATION_DOWNLOAD_TOKEN": "token +&? value"}, clear=True):
            url = configured_download_url()
            self.assertEqual(urlsplit(url).netloc, "www.ip2location.com")
            self.assertEqual(
                parse_qs(urlsplit(url).query), {"token": ["token +&? value"], "file": ["DB11LITE"]}
            )
            os.environ["IP2LOCATION_DOWNLOAD_URL"] = "https://example.test/authorized.zip"
            self.assertEqual(configured_download_url(), "https://example.test/authorized.zip")
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(configured_download_url())

    def test_initial_download_immediate_and_same_month_skipped(self):
        first = datetime(2026, 11, 1, tzinfo=UTC)
        due, next_date = download_eligibility({}, first, "database", True)
        self.assertTrue(due)
        due, next_date = download_eligibility(
            {"download_month": "2026-11"}, first, "database", True
        )
        self.assertFalse(due)
        self.assertEqual((next_date.year, next_date.month), (2026, 12))

    def test_next_month_first_week_and_catch_up(self):
        identity = next(
            str(number)
            for number in range(100)
            if monthly_download_date(str(number), 2026, 12).day > 1
        )
        scheduled = monthly_download_date(identity, 2026, 12)
        previous = {"download_month": "2026-11"}
        due, next_date = download_eligibility(
            previous, datetime(2026, 12, 1, tzinfo=UTC), identity, True
        )
        self.assertFalse(due)
        self.assertEqual(next_date, scheduled)
        due, _ = download_eligibility(
            previous, datetime(2026, 12, scheduled.day, tzinfo=UTC), identity, True
        )
        self.assertTrue(due)
        due, _ = download_eligibility(previous, datetime(2026, 12, 20, tzinfo=UTC), identity, True)
        self.assertTrue(due)

    def test_year_rollover_and_missing_data_recovery(self):
        due, next_date = download_eligibility(
            {"download_month": "2026-12"}, DECEMBER, "database", True
        )
        self.assertFalse(due)
        self.assertEqual((next_date.year, next_date.month), (2027, 1))
        due, _ = download_eligibility({"download_month": "2026-12"}, DECEMBER, "database", False)
        self.assertTrue(due)

    def test_spread_dates_are_deterministic_and_in_first_week(self):
        dates = [monthly_download_date(str(number), 2026, 11) for number in range(40)]
        self.assertTrue(all(1 <= day.day <= 7 for day in dates))
        self.assertGreater(len(set(dates)), 1)
        self.assertEqual(
            monthly_download_date("database", 2026, 11), monthly_download_date("database", 2026, 11)
        )


class MonthlyRefreshTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        self.data_dir = self.folder / "data"

    def download(self, url, path):
        self.calls.append(url)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                zipfile.ZipInfo("IP2LOCATION-LITE-DB11.CSV", date_time=(2026, 1, 1, 0, 0, 0)),
                self.geo().read_text(),
            )
        return path

    def automatic(self, when=NOVEMBER, **kwargs):
        return refresh_datasets(
            self.dsn,
            datasets=("geolocation",),
            geolocation_url=TEST_URL,
            data_dir=self.data_dir,
            downloader=self.download,
            now=when,
            **kwargs,
        )[0]

    def test_validated_success_prevents_repeat_network_downloads(self):
        first = self.automatic()
        second = self.automatic()
        self.assertEqual(first["status"], "loaded")
        self.assertEqual(first["download_month"], "2026-11")
        self.assertEqual(second["status"], "not_due")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(second["last_success_at"], first["last_success_at"])
        self.assertEqual(second["next_download_on"][:7], "2026-12")

    def test_next_month_downloads_once_even_when_content_unchanged(self):
        self.automatic()
        result = self.automatic(DECEMBER)
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(result["download_month"], "2026-12")
        self.assertEqual(self.automatic(DECEMBER)["status"], "not_due")
        self.assertEqual(len(self.calls), 2)

    def test_failed_download_keeps_previous_month_data_and_retries(self):
        first = self.automatic()

        def bad_download(url, path):
            Path(path).write_bytes(b"not-a-zip; fixture-secret")
            return path

        with self.assertRaises(zipfile.BadZipFile):
            refresh_datasets(
                self.dsn,
                datasets=("geolocation",),
                geolocation_url=TEST_URL,
                data_dir=self.data_dir,
                downloader=bad_download,
                now=DECEMBER,
            )
        with psycopg.connect(self.dsn) as connection:
            state = read_state(connection, self.data_dir)["geolocation"]
            self.assertEqual(state["download_month"], "2026-11")
            self.assertEqual(state["last_success_at"], first["last_success_at"])
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM ip2location").fetchone()[0], 1
            )
        result = self.automatic(DECEMBER)
        self.assertEqual(result["download_month"], "2026-12")
        status = "".join(path.read_text() for path in (self.data_dir / "refresh").glob("*.json"))
        self.assertNotIn("fixture-secret", status)
        self.assertNotIn("https://", status)

    def test_recovery_download_if_tables_are_empty(self):
        self.automatic()
        with psycopg.connect(self.dsn) as connection:
            connection.execute("TRUNCATE raw_ip2location,ip2location")
        self.assertEqual(self.automatic()["status"], "loaded")
        self.assertEqual(len(self.calls), 2)

    def test_explicit_local_file_overrides_automatic_download(self):
        self.automatic()
        local = self.geo("10,20,ZZ,Example,Region,Manual,0,0,-,+00:00\n")
        result = self.automatic(geolocation_file=local)
        self.assertTrue(result["manual_update_required"])
        self.assertNotIn("download_month", result)
        self.assertEqual(len(self.calls), 1)
        with psycopg.connect(self.dsn) as connection:
            self.assertEqual(
                connection.execute("SELECT city_name FROM ip2location").fetchone()[0], "Manual"
            )

    def test_explicit_recovery_flag_can_bypass_monthly_skip(self):
        self.automatic()
        self.automatic(force_geolocation_download=True)
        self.assertEqual(len(self.calls), 2)

    def test_ambiguous_clock_is_rejected_before_any_fetch(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            self.automatic(datetime(2026, 11, 10))
        self.assertEqual(self.calls, [])
