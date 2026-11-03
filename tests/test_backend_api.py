"""HTTP contracts exercised against PostgreSQL, not mocked lookup rows."""

from unittest.mock import patch

import psycopg
from backend_support import DatabaseCase
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo

from api.main import create_app
from ingestion.ip_evidence import FEEDS, Feed, refresh
from vpnlens.config import Settings
from vpnlens.setup import initialize


class APITests(DatabaseCase):
    def setUp(self):
        super().setUp()
        self.seed()
        self.client = TestClient(create_app(Settings(database_url=self.dsn)))

    def test_lookup_keeps_ties_and_nested_owners(self):
        response = self.client.get("/v1/lookup/192.0.2.129")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual({row["prefix"] for row in data["results"]}, {"192.0.2.128/25"})
        self.assertEqual(data["results"][1]["asn_owners"][1]["asn"], "64502")
        self.assertIsNone(data["results"][1]["asn_owners"][1]["org_name"])
        self.assertEqual(
            data["selected_sources"]["routing"]["source_file"],
            "routeviews-rv2-20261001-1200.pfx2as.gz",
        )
        self.assertIn("X-Request-ID", response.headers)

    def test_unknown_ip_preserved(self):
        row = self.client.get("/v1/lookup/198.51.100.1").json()["results"][0]
        self.assertEqual(row["ip"], "198.51.100.1")
        self.assertIsNone(row["country_code"])
        self.assertIsNone(row["prefix"])
        self.assertEqual(row["asn_owners"], [])
        self.assertEqual(row["security"]["vpn_status"], "unknown")

    def test_invalid_inputs_do_not_connect(self):
        with patch("api.main.read_connection") as connect:
            for address in ["bad", "::1", "2001:db8::1", "1.2.3.999", "192.0.2.1/24"]:
                self.assertTrue(400 <= self.client.get("/v1/lookup/" + address).status_code < 500)
            connect.assert_not_called()

    def test_independent_latest_and_explicit_history(self):
        from vpnlens.refresh import load_routing

        newer = self.routing(
            "192.0.2.0\t24\t64500\n", name="routeviews-rv2-20261002-1200.pfx2as.gz"
        )
        with psycopg.connect(self.dsn) as connection:
            load_routing(newer, connection)
        latest = self.client.get("/v1/lookup/192.0.2.129").json()
        self.assertEqual(latest["selected_sources"]["routing"]["source_file"], newer.name)
        self.assertEqual(
            latest["selected_sources"]["organization"]["source_file"],
            "20261001.as-org2info.txt.gz",
        )
        self.assertEqual(len(latest["results"]), 1)
        historical = self.client.get(
            "/v1/lookup/192.0.2.129",
            params={"source_file": "routeviews-rv2-20261001-1200.pfx2as.gz"},
        )
        self.assertEqual(len(historical.json()["results"]), 2)
        for key in ["source_file", "org_source_file"]:
            self.assertEqual(
                self.client.get("/v1/lookup/192.0.2.1", params={key: "x' OR TRUE --"}).status_code,
                404,
            )

    def test_listed_tor_separate_and_stale_visible(self):
        feed = Feed("test-vpn", "vpn_server", "Example", "https://example.test/vpn")
        refresh(
            self.dsn,
            feeds=(feed,),
            data_dir=self.folder / "evidence",
            fetcher=lambda _: b"192.0.2.1\n",
        )
        security = self.client.get("/v1/lookup/192.0.2.1").json()["results"][0]["security"]
        self.assertEqual(security["vpn_status"], "listed")
        self.assertEqual(security["tor_status"], "unknown")
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                "UPDATE ip_evidence_snapshots SET checked_at=NOW()-INTERVAL '49 hours'"
            )
        security = self.client.get("/v1/lookup/192.0.2.1").json()["results"][0]["security"]
        self.assertEqual(security["vpn_status"], "unknown")
        self.assertTrue(security["evidence"][0]["stale"])

    def test_existing_cli_keeps_json_contract(self):
        import json
        import os
        import subprocess
        import sys

        from vpnlens.config import ROOT

        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "lookup_ip.py"),
                "192.0.2.129",
                "routeviews-rv2-20261001-1200.pfx2as.gz",
                "20261001.as-org2info.txt.gz",
            ],
            cwd=self.folder,
            env={**os.environ, "DATABASE_URL": self.dsn, "VPNLENS_EXTENDED_EVIDENCE": "false"},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)), 2)

    def test_cli_rejects_invalid_input_without_exposing_connection(self):
        import os
        import subprocess
        import sys

        from vpnlens.config import ROOT

        result = subprocess.run(
            [sys.executable, str(ROOT / "lookup_ip.py"), "::1", "unused", "unused"],
            env={**os.environ, "DATABASE_URL": "postgresql://user:secret-password@localhost/db"},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("secret-password", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_readiness_requires_expected_feed_ids(self):
        feeds = tuple(
            Feed(f"unexpected-{number}", "vpn_server", "Example", "https://example.test/list")
            for number in range(11)
        )
        refresh(
            self.dsn,
            feeds=feeds,
            data_dir=self.folder / "evidence",
            fetcher=lambda _: b"192.0.2.1\n",
        )
        status = self.client.get("/health/ready").json()
        self.assertEqual(status["status"], "degraded")
        self.assertEqual(status["recently_checked_security_sources"], 0)

    def test_readiness_and_sources(self):
        self.assertEqual(self.client.get("/health/live").json()["status"], "alive")
        self.assertEqual(self.client.get("/health/ready").json()["status"], "degraded")
        sources = self.client.get("/v1/sources")
        self.assertEqual(sources.status_code, 200, sources.text)
        self.assertIsNone(sources.json()["geolocation"]["snapshot_at"])
        with psycopg.connect(self.dsn) as connection:
            connection.execute("TRUNCATE raw_asn_mappings")
        self.assertEqual(self.client.get("/health/ready").status_code, 503)
        self.assertEqual(self.client.get("/v1/lookup/192.0.2.1").status_code, 503)

    def test_missing_schema_database_and_timeout_are_safe(self):
        client = TestClient(
            create_app(Settings(database_url=make_conninfo(self.dsn, port=1), connect_timeout=1))
        )
        response = client.get("/v1/lookup/192.0.2.1")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(self.schema, response.text)
        with patch(
            "api.main.lookup",
            side_effect=psycopg.errors.QueryCanceled("private database details"),
        ):
            response = self.client.get("/v1/lookup/192.0.2.1")
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("private", response.text)
        with psycopg.connect(self.dsn) as connection:
            connection.execute("DROP TABLE ip_evidence")
        self.assertEqual(self.client.get("/v1/lookup/192.0.2.1").status_code, 503)

    def test_unexpected_error_is_generic(self):
        with patch("api.main.lookup", side_effect=RuntimeError("secret-password")):
            response = self.client.get("/v1/lookup/192.0.2.1")
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret-password", response.text)

    def test_lookup_transaction_is_read_only_and_bounded(self):
        from vpnlens.service import lookup

        def inspect(connection, *args, **kwargs):
            self.assertEqual(
                connection.execute("SHOW transaction_read_only").fetchone()[
                    "transaction_read_only"
                ],
                "on",
            )
            self.assertEqual(
                connection.execute("SHOW statement_timeout").fetchone()["statement_timeout"],
                "5s",
            )
            self.assertEqual(
                connection.execute("SHOW transaction_isolation").fetchone()[
                    "transaction_isolation"
                ],
                "repeatable read",
            )
            return lookup(connection, *args, **kwargs)

        with patch("api.main.lookup", side_effect=inspect):
            self.assertEqual(self.client.get("/v1/lookup/192.0.2.1").status_code, 200)

    def test_openapi_and_cors(self):
        schema = self.client.get("/openapi.json").json()
        self.assertIn("LookupResponse", schema["components"]["schemas"])
        response = self.client.get("/health/live", headers={"Origin": "https://untrusted.test"})
        self.assertNotIn("access-control-allow-origin", response.headers)
        client = TestClient(
            create_app(Settings(database_url=self.dsn, cors_origins=("http://localhost:3000",)))
        )
        response = client.get("/health/live", headers={"Origin": "http://localhost:3000"})
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:3000")


class SetupTests(DatabaseCase):
    def test_rerun_preserves_data(self):
        self.seed()
        initialize(self.dsn)
        with psycopg.connect(self.dsn) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM asn_prefix_origins").fetchone()[0],
                3,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM ip2location").fetchone()[0], 1
            )

    def test_incompatible_column_or_key_stops_without_changes(self):
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                "ALTER TABLE raw_org_mappings ALTER COLUMN changed TYPE integer USING NULL"
            )
        with self.assertRaisesRegex(ValueError, "Incompatible"):
            initialize(self.dsn)
        with psycopg.connect(self.dsn) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT data_type FROM information_schema.columns WHERE table_schema=%s AND table_name='raw_org_mappings' AND column_name='changed'",
                    (self.schema,),
                ).fetchone()[0],
                "integer",
            )

    def test_empty_database_is_not_ready(self):
        client = TestClient(create_app(Settings(database_url=self.dsn)))
        self.assertEqual(client.get("/health/ready").status_code, 503)
        self.assertEqual(client.get("/health/live").status_code, 200)

    def test_missing_unique_key_is_not_silently_migrated(self):
        with psycopg.connect(self.dsn) as connection:
            constraint = connection.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid='raw_asn_mappings'::regclass AND contype='u'"
            ).fetchone()[0]
            from psycopg import sql

            connection.execute(
                sql.SQL("ALTER TABLE raw_asn_mappings DROP CONSTRAINT {}").format(
                    sql.Identifier(constraint)
                )
            )
        with self.assertRaisesRegex(ValueError, "uniqueness"):
            initialize(self.dsn)


class FrontendServingTests(DatabaseCase):
    def test_built_entry_and_assets_do_not_mask_api_routes(self):
        built = self.folder / "dist"
        (built / "assets").mkdir(parents=True)
        (built / "index.html").write_text(
            "<!doctype html><html><body>VPNLens fixture</body></html>"
        )
        (built / "assets/app.js").write_text("console.log('fixture');")
        client = TestClient(create_app(Settings(database_url=self.dsn), frontend_dir=built))
        self.assertEqual(client.get("/").status_code, 200)
        self.assertIn("text/html", client.get("/").headers["content-type"])
        self.assertEqual(client.get("/assets/app.js").status_code, 200)
        self.assertEqual(client.get("/health/live").json(), {"status": "alive"})
        self.assertEqual(client.get("/v1/not-a-route").status_code, 404)
        self.assertEqual(client.get("/assets/../.env").status_code, 404)
        self.assertNotIn("VPNLens fixture", client.get("/v1/not-a-route").text)

    def test_backend_still_starts_without_frontend_build(self):
        client = TestClient(
            create_app(Settings(database_url=self.dsn), frontend_dir=self.folder / "missing")
        )
        self.assertEqual(client.get("/").status_code, 404)
        self.assertEqual(client.get("/health/live").status_code, 200)


class ExtendedAPITests(DatabaseCase):
    def setUp(self):
        super().setUp()
        self.seed()

    def client(self, enabled):
        return TestClient(create_app(Settings(database_url=self.dsn, extended_evidence=enabled)))

    def test_opt_in_missing_schema_safe_and_flag_off_payload_exact(self):
        from api.models import LookupResponse
        from vpnlens.database import read_connection
        from vpnlens.service import lookup

        original_dsn = self.dsn
        try:
            for timezone in ("UTC", "Africa/Maputo"):
                with self.subTest(timezone=timezone):
                    self.dsn = make_conninfo(
                        self.base,
                        options=f"-c search_path={self.schema},public -c timezone={timezone}",
                    )
                    with read_connection(Settings(database_url=self.dsn)) as conn:
                        raw = lookup(conn, "192.0.2.129")
                    expected = LookupResponse.model_validate(raw).model_dump(
                        mode="json", exclude_unset=True
                    )
                    off = self.client(False).get("/v1/lookup/192.0.2.129")
                    self.assertEqual(off.json(), expected)
                    extension_fields = {
                        "vpn_assessment",
                        "proxy_status",
                        "residential_proxy_status",
                        "residential_proxy_reason",
                        "additional_evidence",
                    }
                    for row in off.json()["results"]:
                        self.assertTrue(extension_fields.isdisjoint(row["security"]))
                    on = self.client(True).get("/v1/lookup/192.0.2.129")
                    self.assertEqual(on.status_code, 503)
                    self.assertNotIn(self.schema, on.text)
        finally:
            self.dsn = original_dsn

    def test_enabled_lookup_ties_readonly_no_upstream_and_committed_sources(self):
        from test_evidence_v2_store import batch, source

        from vpnlens.evidence_store import initialize_extended, publish_contract

        initialize_extended(self.dsn)
        item = source("extended-fixture", "cidr_text", None)
        publish_contract(self.dsn, "publish", batch([item], [["8.8.8.0/24"]]))
        with patch("socket.create_connection", side_effect=AssertionError("No upstream")):
            response = self.client(True).get("/v1/lookup/192.0.2.129")
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()["results"]
        self.assertEqual(rows[0]["security"], rows[1]["security"])
        self.assertEqual(rows[0]["security"]["active_source_count"], 1)
        sources = self.client(True).get("/v1/sources").json()
        self.assertEqual(sources["security_expected_source_ids"], ["extended-fixture"])
        self.assertIsNone(sources["security"][0]["provider"])
        self.assertEqual(sources["security"][0]["record_kind"], "network")
        self.assertEqual(
            self.client(True).get("/health/ready").json()["expected_security_sources"],
            len(FEEDS) + 1,
        )

    def test_explicit_snapshot_cli_uses_flag_and_keeps_row_shape(self):
        from test_evidence_v2_store import batch

        import lookup_ip
        from vpnlens.evidence_store import initialize_extended, publish_contract

        initialize_extended(self.dsn)
        publish_contract(self.dsn, "publish", batch())
        with patch.object(
            lookup_ip.Settings,
            "from_env",
            return_value=Settings(database_url=self.dsn, extended_evidence=True),
        ):
            rows = lookup_ip.lookup_ip(
                "8.8.8.8", "routeviews-rv2-20261001-1200.pfx2as.gz", "20261001.as-org2info.txt.gz"
            )
        self.assertEqual(rows[0]["security"]["vpn_status"], "listed")
        self.assertEqual(rows[0]["security"]["vpn_assessment"], "direct_association")
        self.assertIsNone(rows[0]["country_code"])
        self.assertIsNone(rows[0]["prefix"])

    def test_stale_and_disabled_committed_sources_change_health_denominator(self):
        from datetime import UTC, datetime, timedelta

        from test_evidence_v2_store import batch, source

        from vpnlens.evidence_store import initialize_extended, publish_contract

        initialize_extended(self.dsn)
        item = source("old-extended")
        publish_contract(
            self.dsn, "publish", batch([item], at=datetime.now(UTC) - timedelta(hours=49))
        )
        enabled = self.client(True)
        result = enabled.get("/v1/lookup/8.8.8.8").json()["results"][0]["security"]
        self.assertEqual(result["vpn_status"], "unknown")
        self.assertTrue(result["evidence"][0]["stale"])
        self.assertEqual(result["active_source_count"], 1)
        self.assertEqual(result["recently_checked_source_count"], 0)
        self.assertEqual(
            enabled.get("/health/ready").json()["expected_security_sources"], len(FEEDS) + 1
        )
        item["enabled"] = False
        publish_contract(self.dsn, "publish", batch([item]))
        self.assertEqual(
            enabled.get("/health/ready").json()["expected_security_sources"], len(FEEDS)
        )
        self.assertEqual(enabled.get("/v1/sources").json()["security_expected_source_ids"], [])
        self.assertEqual(
            enabled.get("/v1/lookup/8.8.8.8").json()["results"][0]["security"]["evidence"], []
        )
