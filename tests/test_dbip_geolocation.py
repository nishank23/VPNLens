"""Verify the DB-IP provider switch and publication boundaries."""

import gzip
from datetime import UTC, datetime
from unittest.mock import Mock

import psycopg
from backend_support import DatabaseCase
from fastapi.testclient import TestClient

from api.main import create_app
from vpnlens.config import Settings
from vpnlens.geolocation import DBIP_CITY_LITE
from vpnlens.refresh import load_geolocation, refresh_datasets

NOVEMBER = datetime(2026, 11, 4, tzinfo=UTC)
DATA = (
    '192.0.2.0,192.0.2.255,AS,JP,Tokyo,"Chiyoda, Tokyo",35.7,139.7\n'
    "2001:db8::,2001:db8::ffff,AS,JP,Tokyo,Tokyo,35.7,139.7\n"
)


class DbIpGeolocationTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        self.seed()
        self.client = TestClient(
            create_app(Settings(database_url=self.dsn, geolocation_provider=DBIP_CITY_LITE)),
            client=("192.0.2.1", 50000),
        )

    def refresh(self, **kwargs):
        return refresh_datasets(
            self.dsn,
            datasets=("geolocation",),
            geolocation_provider=DBIP_CITY_LITE,
            data_dir=self.folder / "data",
            **kwargs,
        )[0]

    def file(self, text=DATA, month="11"):
        path = self.folder / f"dbip-city-lite-2026-{month}.csv.gz"
        with gzip.open(path, "wt", encoding="utf-8") as output:
            output.write(text)
        return path

    def test_dbip_api_requires_matching_committed_data_and_returns_provenance(self):
        self.assertEqual(self.client.get("/health/ready").status_code, 503)
        self.assertEqual(self.client.get("/v1/lookup/192.0.2.1").status_code, 503)
        self.assertEqual(self.client.get("/v1/access-decision/192.0.2.1").status_code, 503)
        self.assertFalse(self.client.get("/v1/sources").json()["geolocation"]["available"])

        path = self.file()
        self.assertEqual(self.refresh(geolocation_file=path)["rows"], 1)
        self.assertEqual(self.refresh(geolocation_file=path)["status"], "unchanged")
        self.assertEqual(self.client.get("/health/ready").status_code, 200)
        geo = self.client.get("/v1/sources").json()["geolocation"]
        self.assertTrue(geo["available"])
        self.assertEqual(geo["provider"], DBIP_CITY_LITE)
        self.assertEqual(geo["source_file"], path.name)
        self.assertEqual(datetime.fromisoformat(geo["snapshot_at"]), NOVEMBER.replace(day=1))
        for ip in ("192.0.2.0", "192.0.2.255"):
            lookup = self.client.get(f"/v1/lookup/{ip}").json()
            self.assertEqual(lookup["selected_sources"]["geolocation"]["source_file"], path.name)
            self.assertEqual(lookup["results"][0]["country_code"], "JP")
            self.assertEqual(lookup["results"][0]["city_name"], "Chiyoda, Tokyo")
        self.assertIsNone(self.client.get("/v1/lookup/192.0.3.0").json()["results"][0]["city_name"])

    def test_bad_refresh_preserves_previous_data_and_legacy_import_clears_marker(self):
        path = self.file()
        self.refresh(geolocation_file=path)
        bad = self.file(DATA + "192.0.2.20,192.0.2.25,AS,JP,Tokyo,Overlap,0,0\n", month="12")
        with self.assertRaises(ValueError):
            self.refresh(geolocation_file=bad)
        self.assertEqual(
            self.client.get("/v1/sources").json()["geolocation"]["source_file"], path.name
        )
        with psycopg.connect(self.dsn) as conn:
            load_geolocation(self.geo(), conn)
        self.assertEqual(self.client.get("/v1/lookup/192.0.2.1").status_code, 503)
        local = TestClient(create_app(Settings(database_url=self.dsn)))
        self.assertEqual(
            local.get("/v1/lookup/192.0.2.1").json()["results"][0]["city_name"], "City"
        )

    def test_automatic_download_uses_dbip_monthly_url_and_skips_same_month(self):
        def download(url, path):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.file().read_bytes())
            return path

        downloader = Mock(side_effect=download)
        params = dict(now=NOVEMBER, downloader=downloader, geolocation_url="https://legacy.test/")
        self.assertEqual(self.refresh(**params)["status"], "loaded")
        self.assertEqual(self.refresh(**params)["status"], "not_due")
        self.assertEqual(downloader.call_count, 1)
        self.assertEqual(
            downloader.call_args.args[0],
            "https://download.db-ip.com/free/dbip-city-lite-2026-11.csv.gz",
        )
