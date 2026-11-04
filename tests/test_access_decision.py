"""Pure policy/trust boundaries plus disposable PostgreSQL HTTP contract proof."""

import copy
import os
import unittest
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import psycopg
from backend_support import DatabaseCase
from fastapi.testclient import TestClient
from test_evidence_v2_policy import NOW, legacy, record
from test_evidence_v2_store import batch, source

from api.main import create_app
from vpnlens import service
from vpnlens.access_policy import decide_access
from vpnlens.config import Settings
from vpnlens.database import read_connection
from vpnlens.evidence_policy import apply_policy
from vpnlens.evidence_store import initialize_extended, publish_contract


def listed_security(*types, checked=NOW):
    result = legacy()
    for kind in types:
        result[kind + "_status"] = "listed"
        evidence = dict(checked_at=checked, stale=False)
        if kind == "proxy":
            evidence.update(
                basis="exit_observation",
                role="exit",
                service_category="proxy",
                review_state="approved",
                observed_at=checked,
                expires_at=checked + timedelta(hours=24),
            )
            result.setdefault("additional_evidence", []).append(evidence)
        else:
            evidence["indicator_type"] = "vpn_server" if kind == "vpn" else "tor_exit"
            result["evidence"].append(evidence)
    return result


class AccessPolicyTests(unittest.TestCase):
    def decide(self, security, recent=("a",), now=NOW):
        return decide_access(security, {"a"}, set(recent), now)

    def test_all_overlap_reasons_in_stable_order_and_degraded_block(self):
        security = listed_security("proxy", "tor", "vpn")
        before = copy.deepcopy(security)
        decision = self.decide(security, recent=())
        self.assertEqual(
            decision,
            dict(
                policy_id="streaming-access-v1",
                action="block",
                reason_codes=[
                    "recent_vpn_evidence",
                    "recent_tor_evidence",
                    "recent_proxy_evidence",
                ],
                scheduled_source_health="degraded",
                evaluated_at=NOW,
            ),
        )
        self.assertEqual(security, before)
        for kind in ("vpn", "tor", "proxy"):
            with self.subTest(kind=kind):
                self.assertEqual(
                    self.decide(listed_security(kind))["reason_codes"],
                    [f"recent_{kind}_evidence"],
                )

    def test_health_uses_expected_identities_and_allow_is_uncertain(self):
        for recent, health, reason in (
            (("a", "unexpected"), "ready", "no_recent_blocking_evidence"),
            (("unexpected",), "degraded", "insufficient_recent_evidence"),
        ):
            decision = self.decide(legacy(), recent)
            self.assertEqual(decision["action"], "allow")
            self.assertEqual(decision["scheduled_source_health"], health)
            self.assertEqual(decision["reason_codes"], [reason])

    def test_listed_status_requires_attributable_recent_evidence(self):
        for delta, action in (
            (timedelta(hours=48), "block"),
            (timedelta(hours=48, microseconds=1), "allow"),
            (timedelta(seconds=-1), "allow"),
        ):
            with self.subTest(delta=delta):
                self.assertEqual(
                    self.decide(listed_security("vpn", "tor", checked=NOW - delta))["action"],
                    action,
                )
        security = listed_security("vpn")
        security["evidence"][0]["stale"] = True
        self.assertEqual(self.decide(security)["action"], "allow")
        security["evidence"] = []
        self.assertEqual(self.decide(security)["action"], "allow")

    def test_weak_network_and_unrelated_country_or_asn_cannot_block(self):
        weak = record(basis="network_inference", method="cidr_text", network="8.8.8.0/24")
        security = apply_policy(legacy(), [weak], {}, NOW)
        security.update(country_code="ZZ", asn="64500")
        self.assertEqual(security["vpn_assessment"], "network_only")
        self.assertEqual(self.decide(security)["action"], "allow")
        self.assertEqual(security["residential_proxy_status"], "unknown")

    def test_existing_projection_public_48_hour_boundary(self):
        for age, action in (
            (timedelta(hours=48), "block"),
            (timedelta(hours=48, microseconds=1), "allow"),
        ):
            at = NOW - age
            security = apply_policy(
                legacy(),
                [
                    record(
                        checked_at=at.isoformat(),
                        fetched_at=at.isoformat(),
                        expires_at=(at + timedelta(hours=48)).isoformat(),
                    )
                ],
                {},
                NOW,
            )
            self.assertEqual(self.decide(security)["action"], action)

    def test_original_observation_expiry_approval_and_residential_unknown(self):
        observation = record(
            basis="exit_observation",
            role="exit",
            method="explicit_http_proxy",
            service_category="proxy",
            review_state="approved",
            connection_type_claim="residential",
            observed_at=NOW.isoformat(),
            expires_at=(NOW + timedelta(hours=24)).isoformat(),
        )
        for now, action in (
            (NOW, "block"),
            (NOW + timedelta(hours=24) - timedelta(microseconds=1), "block"),
            (NOW + timedelta(hours=24), "allow"),
        ):
            security = apply_policy(legacy(), [observation], {}, now)
            self.assertEqual(self.decide(security, now=now)["action"], action)
            self.assertEqual(security["residential_proxy_status"], "unknown")
        for review in ("pending", "rejected", None):
            security = apply_policy(legacy(), [{**observation, "review_state": review}], {}, NOW)
            self.assertEqual(self.decide(security)["action"], "allow")
        # Even a previously normalized listed status cannot renew the original expiry.
        normalized = listed_security("proxy")
        self.assertEqual(self.decide(normalized, now=NOW + timedelta(hours=24))["action"], "allow")


class ProxyConfigurationTests(unittest.TestCase):
    def test_explicit_cidrs_and_environment(self):
        self.assertEqual(Settings().trusted_proxy_cidrs, ())
        with (
            patch.dict(
                os.environ,
                {"VPNLENS_TRUSTED_PROXY_CIDRS": " 10.0.0.0/8, ::1/128 "},
                clear=True,
            ),
            patch("vpnlens.config.load_dotenv"),
        ):
            self.assertEqual(Settings.from_env().trusted_proxy_cidrs, ("10.0.0.0/8", "::1/128"))

    def test_wildcards_hosts_and_invalid_networks_are_rejected(self):
        for value in ("*", "0.0.0.0/0", "::/0", "127.0.0.1", "10.0.0.1/8", "bad/24"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Settings(trusted_proxy_cidrs=(value,))


class VisitorBoundaryTests(unittest.TestCase):
    def client(self, peer="127.0.0.1", trusted=()):
        return TestClient(create_app(Settings(trusted_proxy_cidrs=trusted)), client=(peer, 50000))

    def test_untrusted_metadata_cannot_replace_nonpublic_or_missing_peer(self):
        for peer in (
            "127.0.0.1",
            "10.1.2.3",
            "100.64.0.1",
            "192.0.2.1",
            "224.0.0.1",
            "bad",
        ):
            with self.subTest(peer=peer), patch("api.main.read_connection") as connect:
                response = self.client(peer).get(
                    "/v1/connection",
                    headers={
                        "X-Forwarded-For": "8.8.8.8",
                        "Forwarded": "for=8.8.8.8",
                        "X-Real-IP": "8.8.8.8",
                    },
                )
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(response.json(), {"detail": "public_ipv4_unavailable"})
                self.assertEqual(response.headers["cache-control"], "no-store")
                connect.assert_not_called()
        app = create_app(Settings())

        @app.middleware("http")
        async def remove_peer(request, call_next):
            request.scope["client"] = None
            return await call_next(request)

        with patch("api.main.read_connection") as connect:
            self.assertEqual(TestClient(app).get("/v1/connection").status_code, 409)
            connect.assert_not_called()

    def test_ipv6_and_invalid_manual_addresses_do_not_connect(self):
        with patch("api.main.read_connection") as connect:
            response = self.client("2001:4860:4860::8888").get("/v1/connection")
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json(), {"detail": "ipv6_not_supported"})
            self.assertEqual(response.headers["cache-control"], "no-store")
            for address in ("bad", "1.2.3.999", "2001:4860::1", "8.8.8.8/24"):
                response = self.client().get("/v1/access-decision/" + address)
                self.assertTrue(400 <= response.status_code < 500)
                self.assertEqual(response.headers["cache-control"], "no-store")
            connect.assert_not_called()

    def test_trusted_peer_requires_entire_valid_chain_and_public_client(self):
        client = self.client("10.0.0.2", ("10.0.0.0/8",))
        headers = (
            {},
            {"X-Forwarded-For": ""},
            {"X-Forwarded-For": "8.8.8.8,,10.0.0.1"},
            {"X-Forwarded-For": "invalid,8.8.8.8,10.0.0.1"},
            {"X-Forwarded-For": "10.0.0.1"},
            {"X-Forwarded-For": "192.168.1.1"},
            {"X-Forwarded-For": "8.8.8.8:1234"},
            {"X-Forwarded-For": "fe80::1%eth0"},
            {"Forwarded": "for=8.8.8.8", "X-Real-IP": "8.8.8.8"},
        )
        with patch("api.main.read_connection") as connect:
            for header in headers:
                with self.subTest(header=header):
                    response = client.get("/v1/connection", headers=header)
                    self.assertEqual(response.status_code, 409, response.text)
                    self.assertEqual(response.headers["cache-control"], "no-store")
            response = client.get(
                "/v1/connection",
                headers={"X-Forwarded-For": "2001:4860:4860::8888,10.0.0.1"},
            )
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["detail"], "ipv6_not_supported")
            response = client.get(
                "/v1/connection",
                headers=[
                    ("X-Forwarded-For", "invalid"),
                    ("X-Forwarded-For", "8.8.8.8,10.0.0.1"),
                ],
            )
            self.assertEqual(response.status_code, 409)
            connect.assert_not_called()


class AccessDecisionAPITests(DatabaseCase):
    def setUp(self):
        super().setUp()
        self.seed()
        self.client = self.make_client()

    def make_client(self, peer="8.8.8.8", trusted=(), extended=False):
        return TestClient(
            create_app(
                Settings(
                    database_url=self.dsn,
                    trusted_proxy_cidrs=trusted,
                    extended_evidence=extended,
                )
            ),
            client=(peer, 50000),
        )

    def feeds(self, address="9.9.9.9"):
        from ingestion.ip_evidence import FEEDS, refresh

        refresh(
            self.dsn,
            data_dir=self.folder / "feeds",
            fetcher=lambda _: (address + "\n").encode(),
        )
        return FEEDS

    def test_manual_envelope_preserves_exact_legacy_ties_and_optional_fields(self):
        old = self.client.get("/v1/lookup/192.0.2.129")
        response = self.client.get("/v1/access-decision/192.0.2.129")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["lookup"], old.json())
        self.assertEqual(len(data["lookup"]["results"]), 2)
        self.assertIsNone(data["lookup"]["results"][1]["asn_owners"][1]["org_name"])
        self.assertNotIn("proxy_status", data["lookup"]["results"][0]["security"])
        self.assertEqual(data["decision"]["reason_codes"], ["insufficient_recent_evidence"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn("cache-control", old.headers)
        schemas = self.client.get("/openapi.json").json()["components"]["schemas"]
        self.assertIn("AccessDecisionResponse", schemas)
        self.assertEqual(
            schemas["AccessDecision"]["properties"]["reason_codes"]["items"]["enum"],
            [
                "recent_vpn_evidence",
                "recent_tor_evidence",
                "recent_proxy_evidence",
                "no_recent_blocking_evidence",
                "insufficient_recent_evidence",
            ],
        )

    def test_ready_allows_unknown_but_unexpected_sources_do_not_replace_expected(self):
        feeds = self.feeds()
        response = self.client.get("/v1/access-decision/8.8.8.8").json()
        self.assertEqual(response["decision"]["scheduled_source_health"], "ready")
        self.assertEqual(response["decision"]["reason_codes"], ["no_recent_blocking_evidence"])
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                "UPDATE ip_evidence_snapshots SET source_id='unexpected' WHERE source_id=%s",
                (feeds[0].source_id,),
            )
        response = self.client.get("/v1/access-decision/8.8.8.8").json()
        self.assertEqual(response["decision"]["scheduled_source_health"], "degraded")
        self.assertEqual(response["decision"]["reason_codes"], ["insufficient_recent_evidence"])

    def test_vpn_tor_overlap_blocks_during_degraded_health_and_stale_does_not(self):
        feeds = self.feeds("8.8.8.8")
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                "UPDATE ip_evidence_snapshots SET active=FALSE WHERE source_id=%s",
                (feeds[0].source_id,),
            )
        decision = self.client.get("/v1/access-decision/8.8.8.8").json()["decision"]
        self.assertEqual(decision["action"], "block")
        self.assertEqual(decision["scheduled_source_health"], "degraded")
        self.assertEqual(decision["reason_codes"], ["recent_vpn_evidence", "recent_tor_evidence"])
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                "UPDATE ip_evidence_snapshots SET checked_at=NOW()-INTERVAL '49 hours'"
            )
        data = self.client.get("/v1/access-decision/8.8.8.8").json()
        self.assertEqual(data["decision"]["action"], "allow")
        self.assertTrue(
            all(row["stale"] for row in data["lookup"]["results"][0]["security"]["evidence"])
        )

    def test_future_legacy_timestamps_cannot_block_or_make_health_ready(self):
        self.feeds("8.8.8.8")
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                "UPDATE ip_evidence_snapshots SET checked_at=NOW()+INTERVAL '1 hour'"
            )
        data = self.client.get("/v1/access-decision/8.8.8.8").json()
        self.assertEqual(data["lookup"]["results"][0]["security"]["vpn_status"], "listed")
        self.assertEqual(data["decision"]["action"], "allow")
        self.assertEqual(data["decision"]["scheduled_source_health"], "degraded")

    def test_trusted_chain_uses_nearest_untrusted_peer_and_ignores_spoofed_leftmost(
        self,
    ):
        client = self.make_client("10.0.0.2", ("10.0.0.0/8",))
        response = client.get(
            "/v1/connection", headers={"X-Forwarded-For": "1.1.1.1,8.8.8.8,10.0.0.1"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["lookup"]["ip"], "8.8.8.8")
        self.assertEqual(response.headers["cache-control"], "no-store")
        repeated = client.get(
            "/v1/connection",
            headers=[
                ("X-Forwarded-For", "1.1.1.1,8.8.8.8"),
                ("X-Forwarded-For", "10.0.0.1"),
            ],
        )
        self.assertEqual(repeated.json()["lookup"]["ip"], "8.8.8.8")
        v6_proxy = self.make_client("::1", ("::1/128",))
        self.assertEqual(
            v6_proxy.get("/v1/connection", headers={"X-Forwarded-For": "8.8.8.8"}).json()["lookup"][
                "ip"
            ],
            "8.8.8.8",
        )

    def test_direct_public_peer_ignores_all_untrusted_forwarding_metadata(self):
        for forwarded in ("1.1.1.1", "bad", "10.0.0.1,,bad"):
            response = self.client.get(
                "/v1/connection",
                headers={
                    "X-Forwarded-For": forwarded,
                    "X-Real-IP": "1.1.1.1",
                    "Forwarded": "for=1.1.1.1",
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["lookup"]["ip"], "8.8.8.8")

    def test_one_readonly_transaction_reused_for_lookup_health_and_clock(self):
        from vpnlens.service import access_decision

        @contextmanager
        def inspect(settings):
            with read_connection(settings) as connection:
                self.assertEqual(
                    connection.execute("SHOW transaction_read_only").fetchone()[
                        "transaction_read_only"
                    ],
                    "on",
                )
                self.assertEqual(
                    connection.execute("SHOW transaction_isolation").fetchone()[
                        "transaction_isolation"
                    ],
                    "repeatable read",
                )
                self.assertEqual(
                    connection.execute("SHOW statement_timeout").fetchone()["statement_timeout"],
                    "5s",
                )
                self.clock = connection.execute("SELECT CURRENT_TIMESTAMP AS now").fetchone()["now"]
                yield connection

        with (
            patch("api.main.read_connection", side_effect=inspect) as connect,
            patch("api.main.access_decision", wraps=access_decision) as decide,
            patch("vpnlens.service.lookup", wraps=service.lookup) as lookup,
            patch("vpnlens.service.source_status", wraps=service.source_status) as sources,
        ):
            response = self.client.get("/v1/access-decision/192.0.2.129")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(connect.call_count, 1)
        self.assertIs(decide.call_args.args[0], lookup.call_args.args[0])
        self.assertIs(decide.call_args.args[0], sources.call_args.args[0])
        self.assertEqual(
            datetime.fromisoformat(response.json()["decision"]["evaluated_at"]),
            self.clock,
        )

    def test_missing_geolocation_blocks_only_new_decision_routes(self):
        with psycopg.connect(self.dsn) as connection:
            connection.execute("TRUNCATE ip2location")
        legacy_response = self.client.get("/v1/lookup/192.0.2.129")
        self.assertEqual(legacy_response.status_code, 200, legacy_response.text)
        self.assertIsNone(legacy_response.json()["results"][0]["country_code"])
        self.assertEqual(self.client.get("/health/ready").status_code, 503)
        for path in ("/v1/connection", "/v1/access-decision/192.0.2.129"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 503, response.text)
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertNotIn("decision", response.json())

    def test_no_upstream_calls_and_missing_data_or_database_fail_without_decision(self):
        with (
            patch("socket.create_connection", side_effect=AssertionError("No upstream")),
            patch("urllib.request.urlopen", side_effect=AssertionError("No upstream")),
            patch("dns.resolver.Resolver.resolve", side_effect=AssertionError("No DNS")),
        ):
            self.assertEqual(self.client.get("/v1/connection").status_code, 200)
            self.assertEqual(self.client.get("/v1/access-decision/8.8.8.8").status_code, 200)
        for path in ("/v1/connection", "/v1/access-decision/8.8.8.8"):
            for error, status in (
                (psycopg.OperationalError("private"), 503),
                (psycopg.errors.QueryCanceled("private"), 503),
                (RuntimeError("private"), 500),
            ):
                with patch("api.main.access_decision", side_effect=error):
                    response = self.client.get(path)
                self.assertEqual(response.status_code, status, response.text)
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertNotIn("decision", response.json())
                self.assertNotIn("private", response.text)
        with psycopg.connect(self.dsn) as connection:
            connection.execute("TRUNCATE raw_asn_mappings")
        response = self.client.get("/v1/connection")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn("decision", response.json())

    def test_enabled_scheduled_sources_health_and_network_only_allow(self):
        self.feeds()
        initialize_extended(self.dsn)
        item = source("extended-fixture", "cidr_text", None)
        publish_contract(
            self.dsn,
            "publish",
            batch([item], [["8.8.8.0/24"]], at=datetime.now(UTC) - timedelta(hours=49)),
        )
        client = self.make_client(extended=True)
        self.assertEqual(
            client.get("/v1/access-decision/8.8.8.8").json()["decision"]["scheduled_source_health"],
            "degraded",
        )
        publish_contract(self.dsn, "publish", batch([item], [["8.8.8.0/24"]]))
        data = client.get("/v1/access-decision/8.8.8.8").json()
        self.assertEqual(data["decision"]["scheduled_source_health"], "ready")
        self.assertEqual(data["decision"]["action"], "allow")
        self.assertEqual(data["lookup"]["results"][0]["security"]["vpn_assessment"], "network_only")
        item["enabled"] = False
        publish_contract(self.dsn, "publish", batch([item]))
        self.assertEqual(
            client.get("/v1/access-decision/8.8.8.8").json()["decision"]["scheduled_source_health"],
            "ready",
        )

    def test_approved_proxy_blocks_without_enlarging_scheduled_denominator(self):
        self.feeds()
        initialize_extended(self.dsn)
        # Publish just before original expiry, then prove real-clock API expiry.
        now = datetime.now(UTC) - timedelta(hours=24) + timedelta(seconds=2)
        identity = str(uuid4())
        measurement = dict(
            observation_id=identity,
            observation_sha256="d" * 64,
            profile_sha256="e" * 64,
            source_id="observation-fixture",
            family="measured_exit",
            record_key="d" * 64,
            network="8.8.8.8/32",
            provider="Fixture",
            basis="exit_observation",
            role="exit",
            method="explicit_http_proxy",
            service_category="proxy",
            source_url="https://example.com",
            content_sha256="d" * 64,
            observed_at=now.isoformat(),
            expires_at=(now + timedelta(hours=24)).isoformat(),
            connection_type_claim="residential",
        )
        publish_contract(self.dsn, "observe", dict(measurement=measurement, review=None))
        client = self.make_client(extended=True)
        self.assertEqual(client.get("/v1/connection").json()["decision"]["action"], "allow")
        review = dict(
            observation_id=identity,
            observation_sha256="d" * 64,
            review_state="approved",
            reviewed_at=(datetime.now(UTC) - timedelta(milliseconds=1)).isoformat(),
            reviewer_sha256="f" * 64,
        )
        publish_contract(self.dsn, "observe", dict(measurement=measurement, review=review))
        data = client.get("/v1/connection").json()
        self.assertEqual(data["decision"]["reason_codes"], ["recent_proxy_evidence"])
        self.assertEqual(data["decision"]["scheduled_source_health"], "ready")
        self.assertEqual(
            data["lookup"]["results"][0]["security"]["residential_proxy_status"],
            "unknown",
        )
        with psycopg.connect(self.dsn) as connection:
            connection.execute("SELECT pg_sleep(2)")
        expired = client.get("/v1/connection").json()
        self.assertEqual(expired["decision"]["action"], "allow")
        self.assertEqual(expired["decision"]["reason_codes"], ["no_recent_blocking_evidence"])
        evidence = expired["lookup"]["results"][0]["security"]["additional_evidence"][0]
        self.assertTrue(evidence["stale"])
        self.assertEqual(datetime.fromisoformat(evidence["observed_at"]), now)
