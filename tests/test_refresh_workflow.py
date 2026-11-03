"""Refresh publication and download boundaries, with fixture external data."""

import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import psycopg
from backend_support import DatabaseCase

from vpnlens.downloads import (
    ORG_BASE,
    ROUTING_BASE,
    discover_organization,
    discover_routing,
    download_file,
)
from vpnlens.refresh import (
    geolocation_csv,
    load_geolocation,
    load_routing,
    read_state,
    refresh_datasets,
)


class DiscoveryTests(unittest.TestCase):
    def test_latest_valid_filename_and_empty_month_fallback(self):
        pages = {
            ROUTING_BASE: ["2026/", "https://evil.test/2027/", "../", "2025/"],
            ROUTING_BASE + "2026/": ["11/", "10/"],
            ROUTING_BASE + "2026/11/": [],
            ROUTING_BASE + "2026/10/": [
                "routeviews-rv2-20261030-1200.pfx2as.gz",
                "routeviews-rv2-20261031-1200.pfx2as.gz",
                "routeviews-rv2-20261331-1200.pfx2as.gz",
                "routeviews6-rv2-20261031-1200.pfx2as.gz",
            ],
        }
        self.assertTrue(
            discover_routing(pages.__getitem__).endswith(
                "2026/10/routeviews-rv2-20261031-1200.pfx2as.gz"
            )
        )
        result = discover_organization(
            lambda _: [
                "latest.as-org2info.txt.gz",
                "20260901.as-org2info.txt.gz",
                "20261001.as-org2info.txt.gz",
                "20261301.as-org2info.txt.gz",
                "../../20261002.as-org2info.txt.gz",
            ]
        )
        self.assertEqual(result, ORG_BASE + "20261001.as-org2info.txt.gz")

    def test_missing_snapshots_fail(self):
        with self.assertRaises(ValueError):
            discover_routing(lambda _: [])
        with self.assertRaises(ValueError):
            discover_organization(lambda _: [])

    def test_download_length_and_bound_preserve_previous_file(self):
        import tempfile

        class Response(BytesIO):
            headers = {"Content-Length": "20"}

            def geturl(self):
                return "https://example.test/data"

        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "old.gz"
            target.write_bytes(b"previous")
            with (
                patch("vpnlens.downloads.urlopen", return_value=Response(b"truncated")),
                self.assertRaises(ValueError),
            ):
                download_file("https://example.test/data", target)
            self.assertEqual(target.read_bytes(), b"previous")
            self.assertEqual(list(Path(folder).glob(".download-*")), [])
            with self.assertRaises(ValueError):
                download_file("http://example.test/data", target)


class RefreshTests(DatabaseCase):
    def test_routing_transform_failure_rolls_back_raw_and_clean(self):
        self.seed()
        bad = self.routing("192.0.2.0\t24\t64500\n192.0.2.0\t24\t64500\n")
        with self.assertRaises(psycopg.errors.UniqueViolation):
            with psycopg.connect(self.dsn) as connection:
                load_routing(bad, connection)
        with psycopg.connect(self.dsn) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM raw_asn_prefixes").fetchone()[0],
                3,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM asn_prefix_origins").fetchone()[0],
                3,
            )

    def test_corrupt_routing_and_invalid_asn_preserve_data(self):
        self.seed()
        bad = self.routing("192.0.2.0\t24\tbad-asn\n")
        with self.assertRaises(ValueError):
            with psycopg.connect(self.dsn) as connection:
                load_routing(bad, connection)
        bad.write_bytes(b"invalid-gzip")
        with self.assertRaises(OSError):
            with psycopg.connect(self.dsn) as connection:
                load_routing(bad, connection)
        with psycopg.connect(self.dsn) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM asn_prefix_origins").fetchone()[0],
                3,
            )

    def test_geo_invalid_rows_and_transform_failure_preserve_data(self):
        self.seed()
        for text in [
            "bad,csv\n",
            "10,20,ZZ,A,B,C,0,0,-,+00:00\n15,25,ZZ,A,B,C,0,0,-,+00:00\n",
            "10,20,ZZ,A,B,C,nan,0,-,+00:00\n",
        ]:
            bad = self.geo(text)
            with self.assertRaises((ValueError, psycopg.Error)):
                with psycopg.connect(self.dsn) as connection:
                    load_geolocation(bad, connection)
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                "ALTER TABLE ip2location ADD CONSTRAINT test_failure CHECK (city_name='City')"
            )
        with self.assertRaises(psycopg.Error):
            with psycopg.connect(self.dsn) as connection:
                load_geolocation(self.geo("10,20,ZZ,A,B,Other,0,0,-,+00:00\n"), connection)
        with psycopg.connect(self.dsn) as connection:
            self.assertEqual(
                connection.execute("SELECT ip_from FROM raw_ip2location").fetchone()[0],
                3221225984,
            )
            self.assertEqual(
                connection.execute("SELECT city_name FROM ip2location").fetchone()[0],
                "City",
            )

    def test_zip_streaming_and_traversal_rejection(self):
        path = self.folder / "geo.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("DB11.CSV", self.geo().read_text())
            archive.writestr("readme.txt", "Example attribution")
        with psycopg.connect(self.dsn) as connection:
            self.assertEqual(load_geolocation(path, connection)["rows"], 1)
        for member in ["../DB11.CSV", "/DB11.CSV", "folder\\DB11.CSV"]:
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(member, "data")
            with self.assertRaises(ValueError):
                with geolocation_csv(path) as source:
                    source.read()
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("one.csv", "a")
            archive.writestr("two.csv", "b")
        with self.assertRaises(ValueError), geolocation_csv(path) as source:
            source.read()

    def test_refresh_skips_unchanged_and_exposes_status(self):
        route = self.routing()
        first = refresh_datasets(
            self.dsn,
            datasets=("routing",),
            routing_file=route,
            data_dir=self.folder / "data",
        )
        self.assertEqual(first[0]["status"], "loaded")
        with patch("vpnlens.refresh.load_routing", side_effect=AssertionError("should skip")):
            second = refresh_datasets(
                self.dsn,
                datasets=("routing",),
                routing_file=route,
                data_dir=self.folder / "data",
            )
        self.assertEqual(second[0]["status"], "unchanged")
        with psycopg.connect(self.dsn) as connection:
            self.assertEqual(read_state(connection, self.folder / "data")["routing"]["rows"], 1)

    def test_each_dataset_commits_and_failed_dataset_retains_state(self):
        route = self.routing()
        good = self.organization()
        refresh_datasets(
            self.dsn,
            datasets=("organization",),
            organization_file=good,
            data_dir=self.folder / "data",
        )
        good.write_bytes(b"bad gzip")
        with self.assertRaises(OSError):
            refresh_datasets(
                self.dsn,
                datasets=("routing", "organization"),
                routing_file=route,
                organization_file=good,
                data_dir=self.folder / "data",
            )
        with psycopg.connect(self.dsn) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM asn_prefix_origins").fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM raw_asn_mappings").fetchone()[0],
                2,
            )
            state = read_state(connection, self.folder / "data")["organization"]
            self.assertEqual(state["status"], "failed")
            self.assertIn("last_success_at", state)

    def test_geo_manual_requirement_preserves_existing(self):
        self.seed()
        result = refresh_datasets(
            self.dsn, datasets=("geolocation",), data_dir=self.folder / "data"
        )
        self.assertEqual(result[0]["status"], "manual_update_required")
        with psycopg.connect(self.dsn) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM ip2location").fetchone()[0], 1
            )

    def test_overlapping_command_rejected_before_download(self):
        with psycopg.connect(self.dsn, autocommit=True) as connection:
            connection.execute("SELECT pg_advisory_lock(872410054)")
            with patch("vpnlens.refresh.discover_routing") as discover:
                with self.assertRaisesRegex(RuntimeError, "already running"):
                    refresh_datasets(self.dsn, datasets=("routing",), data_dir=self.folder / "data")
                discover.assert_not_called()

    def test_no_credentials_in_recorded_status(self):
        def fail(*args):
            raise OSError("secret-url-password")

        with self.assertRaises(OSError):
            refresh_datasets(
                self.dsn,
                datasets=("geolocation",),
                geolocation_url="https://secret:password@example.test/data",
                downloader=fail,
                data_dir=self.folder / "data",
            )
        state = "".join(path.read_text() for path in (self.folder / "data/refresh").glob("*.json"))
        self.assertNotIn("password", state)
        self.assertNotIn("secret", state)

    def test_file_changed_during_load_rolls_back(self):
        route = self.routing()
        with patch("vpnlens.refresh.digest_file", side_effect=["before", "after"]):
            with self.assertRaisesRegex(ValueError, "changed during ingestion"):
                refresh_datasets(
                    self.dsn,
                    datasets=("routing",),
                    routing_file=route,
                    data_dir=self.folder / "data",
                )
        with psycopg.connect(self.dsn) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM asn_prefix_origins").fetchone()[0],
                0,
            )


class ExtendedRefreshTests(DatabaseCase):
    def test_legacy_success_precedes_extended_failure_and_retains_old_state(self):
        import vpnlens.refresh as module

        self.assertTrue(hasattr(module, "prepare_batch"))
        folder = self.folder / "data"
        with (
            patch("vpnlens.refresh.refresh_evidence", return_value=[]),
            patch("vpnlens.refresh.prepare_batch", side_effect=ValueError("secret parse details")),
        ):
            with self.assertRaises(ValueError):
                refresh_datasets(
                    self.dsn, datasets=("evidence",), data_dir=folder, extended_enabled=True
                )
        with psycopg.connect(self.dsn) as connection:
            state = read_state(connection, folder)
        self.assertEqual(state["evidence"]["status"], "checked")
        self.assertEqual(state["evidence_extended"]["status"], "failed")
        self.assertNotIn("secret", str(state))

    def test_extended_publishes_revalidated_candidate_without_second_session_lock(self):
        from test_evidence_v2_store import source

        from vpnlens.evidence_collectors import prepare_batch
        from vpnlens.evidence_store import initialize_extended

        initialize_extended(self.dsn)
        registry = {"schema_version": 1, "sources": [source()]}
        folder = self.folder / "data"
        candidate = prepare_batch(registry, folder / "evidence-v2", fetcher=lambda _: b"8.8.8.8\n")
        with (
            patch("vpnlens.refresh.refresh_evidence", return_value=[]),
            patch("vpnlens.refresh.prepare_batch", return_value=candidate),
            patch("vpnlens.refresh.extended_registry", return_value=registry),
        ):
            result = refresh_datasets(
                self.dsn, datasets=("evidence",), data_dir=folder, extended_enabled=True
            )
        self.assertEqual([item["dataset"] for item in result], ["evidence", "evidence_extended"])
        self.assertEqual(result[1]["status"], "loaded")
