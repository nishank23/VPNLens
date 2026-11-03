"""Disposable PostgreSQL fixture proof; these public IP strings prove no VPN use."""

import copy
import importlib.util
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
from backend_support import DatabaseCase
from psycopg.rows import dict_row

from vpnlens.evidence_collectors import indicator
from vpnlens.evidence_contract import canonical, digest, stamp


def source(name="fixture-list", adapter="host_text", provider="Fixture VPN"):
    return dict(
        source_id=name,
        enabled=True,
        family="fixture",
        provider=provider,
        adapter=adapter,
        basis={
            "host_text": "provider_list",
            "cidr_text": "network_inference",
            "dns_a": "provider_dns",
        }[adapter],
        role="server",
        url="https://example.com/" + name,
        attribution_url="https://example.com",
        max_bytes=5000000,
        max_age_hours=48,
        **({"hosts": ["vpn.example.com"]} if adapter == "dns_a" else {}),
    )


def batch(sources=None, networks=None, at=None, hashes=None):
    sources = [source()] if sources is None else sources
    at = datetime.now(UTC) - timedelta(seconds=10) if at is None else at
    registry = dict(schema_version=1, sources=sources)
    snapshots = []
    for n, item in enumerate(sources):
        if not item["enabled"]:
            continue
        records = [
            indicator(item, network)
            for network in (networks[n] if networks is not None else ["8.8.8.8"])
        ]
        snapshots.append(
            dict(
                source=item,
                content_sha256=(hashes[n] if hashes else digest(canonical(records))),
                fetched_at=stamp(at),
                checked_at=stamp(at),
                publisher_at=None,
                raw_ref="raw/private.bin",
                records=records,
                ipv6_skipped=0,
            )
        )
    return dict(
        schema_version=1,
        batch_id=str(uuid4()),
        checked_at=stamp(at),
        registry_sha256=digest(canonical(registry)),
        registry=registry,
        snapshots=snapshots,
    )


class ExtendedStoreTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        self.assertIsNotNone(
            importlib.util.find_spec("vpnlens.evidence_store"), "extended store must exist"
        )
        from vpnlens.evidence_store import EvidenceStore, initialize_extended, publish_contract

        self.Store, self.initialize, self.publish = (
            EvidenceStore,
            initialize_extended,
            publish_contract,
        )
        self.initialize(self.dsn)

    def query(self, operation, payload=None):
        with psycopg.connect(self.dsn, row_factory=dict_row) as connection:
            return self.Store(connection).run(operation, payload or {})

    def count(self, table):
        with psycopg.connect(self.dsn) as connection:
            return connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    def test_initialize_twice_and_validate_missing_index(self):
        self.assertTrue(self.initialize(self.dsn)["compatible"])
        with psycopg.connect(self.dsn) as connection:
            connection.execute("DROP INDEX evidence_v2_indicators_network_gist")
        self.assertFalse(self.query("validate")["compatible"])
        with self.assertRaises(ValueError):
            self.publish(self.dsn, "publish", batch())

    def test_overlap_boundaries_identity_and_readonly(self):
        sources = [source("first", "cidr_text", None), source("second", provider="Other")]
        candidate = batch(sources, [["8.8.8.0/24"], ["8.8.8.8"]])
        self.assertEqual(self.publish(self.dsn, "publish", candidate)["status"], "loaded")
        self.assertEqual(len(self.query("lookup", {"ip_address": "8.8.8.8"})["matches"]), 2)
        self.assertEqual(len(self.query("lookup", {"ip_address": "8.8.8.0"})["matches"]), 1)
        self.assertEqual(len(self.query("lookup", {"ip_address": "8.8.8.255"})["matches"]), 1)
        self.assertEqual(self.query("lookup", {"ip_address": "8.8.9.0"})["matches"], [])
        with psycopg.connect(self.dsn, row_factory=dict_row) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            self.assertEqual(len(self.Store(connection).run("sources", {})["sources"]), 2)
            self.Store(connection).run("lookup", {"ip_address": "8.8.8.8"})

    def test_unchanged_http_preserves_fetched_and_advances_check(self):
        first = batch(at=datetime.now(UTC) - timedelta(hours=1))
        self.publish(self.dsn, "publish", first)
        later = copy.deepcopy(first)
        rechecked = stamp(datetime.now(UTC) - timedelta(seconds=2))
        for key in ("checked_at", "fetched_at"):
            later["snapshots"][0][key] = rechecked
        later["checked_at"] = later["snapshots"][0]["checked_at"]
        self.assertEqual(self.publish(self.dsn, "publish", later)["status"], "unchanged")
        status = self.query("sources")["sources"][0]
        self.assertEqual(
            datetime.fromisoformat(status["fetched_at"]),
            datetime.fromisoformat(first["snapshots"][0]["fetched_at"]),
        )
        self.assertEqual(
            datetime.fromisoformat(status["checked_at"]),
            datetime.fromisoformat(later["checked_at"]),
        )
        self.assertEqual(self.count("evidence_v2_snapshots"), 1)

    def test_reactivation_a_b_a_reports_loaded(self):
        first = batch(hashes=["a" * 64])
        self.publish(self.dsn, "publish", first)
        second = batch(networks=[["9.9.9.9"]], hashes=["b" * 64])
        self.publish(self.dsn, "publish", second)
        restored = batch(hashes=["a" * 64])
        self.assertEqual(self.publish(self.dsn, "publish", restored)["status"], "loaded")
        self.assertEqual(
            self.query("lookup", {"ip_address": "8.8.8.8"})["matches"][0]["content_sha256"],
            "a" * 64,
        )

    def test_disable_reenable_history_and_all_disabled(self):
        candidate = batch()
        self.publish(self.dsn, "publish", candidate)
        disabled = source()
        disabled["enabled"] = False
        self.publish(self.dsn, "publish", batch([disabled]))
        self.assertEqual(self.query("sources")["enabled_source_ids"], [])
        self.assertEqual(self.query("lookup", {"ip_address": "8.8.8.8"})["matches"], [])
        self.assertEqual(self.count("evidence_v2_snapshots"), 1)
        self.publish(self.dsn, "publish", candidate)
        self.assertEqual(len(self.query("lookup", {"ip_address": "8.8.8.8"})["matches"]), 1)

    def test_dns_dated_snapshots_and_successful_withdrawal(self):
        dns = source(adapter="dns_a")
        self.publish(self.dsn, "publish", batch([dns], hashes=["a" * 64]))
        self.publish(self.dsn, "publish", batch([dns], hashes=["b" * 64]))
        self.publish(self.dsn, "publish", batch([dns], [[]], hashes=["c" * 64]))
        self.assertEqual(self.count("evidence_v2_snapshots"), 3)
        self.assertEqual(self.query("sources")["sources"][0]["ipv4_count"], 0)
        self.assertEqual(self.query("lookup", {"ip_address": "8.8.8.8"})["matches"], [])

    def test_bad_final_source_rolls_back_entire_batch(self):
        self.publish(self.dsn, "publish", batch())
        before = {
            table: self.count(table)
            for table in ("evidence_v2_registry", "evidence_v2_snapshots", "evidence_v2_indicators")
        }
        candidate = batch([source("one"), source("two")])
        candidate["snapshots"][-1]["records"][0]["network"] = "10.0.0.0/8"
        with self.assertRaises((ValueError, psycopg.Error)):
            self.publish(self.dsn, "publish", candidate)
        self.assertEqual(before, {table: self.count(table) for table in before})
        self.assertEqual(self.query("sources")["enabled_source_ids"], ["fixture-list"])

    def test_sql_bypass_rejects_nonpublic_overlap_and_immutable_edits(self):
        self.publish(self.dsn, "publish", batch())
        for network in (
            "0.0.0.0/0",
            "8.0.0.0/6",
            "10.0.0.0/8",
            "192.0.0.0/16",
            "224.0.0.0/4",
            "::/0",
        ):
            with (
                self.subTest(network=network),
                self.assertRaises(psycopg.Error),
                psycopg.connect(self.dsn) as connection,
            ):
                connection.execute("UPDATE evidence_v2_indicators SET network=%s", (network,))
        with self.assertRaises(psycopg.Error), psycopg.connect(self.dsn) as connection:
            connection.execute("DELETE FROM evidence_v2_snapshots")

    def test_hostname_identity_and_containment_index(self):
        candidate = batch()
        item = candidate["snapshots"][0]
        item["records"] = [indicator(item["source"], "8.8.8.8", host) for host in ("one", "two")]
        item["content_sha256"] = digest(canonical(item["records"]))
        self.publish(self.dsn, "publish", candidate)
        self.assertEqual(len(self.query("lookup", {"ip_address": "8.8.8.8"})["matches"]), 2)
        with psycopg.connect(self.dsn) as connection:
            connection.execute("SET LOCAL enable_seqscan=off")
            plan = connection.execute(
                "EXPLAIN SELECT * FROM evidence_v2_indicators WHERE network >>= '8.8.8.8'::inet"
            ).fetchall()
        self.assertIn("evidence_v2_indicators_network_gist", str(plan))

    def test_lock_contention_and_no_legacy_mutation(self):
        self.seed()
        with psycopg.connect(self.dsn) as connection:
            before = connection.execute("SELECT count(*) FROM asn_prefix_origins").fetchone()
            connection.execute("SELECT pg_advisory_xact_lock(872410052)")
            with self.assertRaises(RuntimeError):
                self.publish(self.dsn, "publish", batch())
            with self.assertRaises(RuntimeError):
                self.publish(self.dsn, "observe", {})
        self.publish(self.dsn, "publish", batch())
        with psycopg.connect(self.dsn) as connection:
            self.assertEqual(
                connection.execute("SELECT count(*) FROM asn_prefix_origins").fetchone(), before
            )
            self.assertEqual(
                connection.execute("SELECT count(*) FROM ip_evidence_snapshots").fetchone()[0], 0
            )

    def test_incompatible_existing_table_rolls_back(self):
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                "ALTER TABLE evidence_v2_indicators DROP CONSTRAINT evidence_v2_indicators_network_public"
            )
        self.assertFalse(self.query("validate")["compatible"])
        with self.assertRaises((ValueError, psycopg.Error)):
            self.initialize(self.dsn)

    def test_observation_pending_approved_idempotent_conflict_and_expiry(self):
        now = datetime.now(UTC) - timedelta(seconds=2)
        observation_id = str(uuid4())
        measurement = dict(
            observation_id=observation_id,
            observation_sha256="d" * 64,
            profile_sha256="e" * 64,
            source_id="observation-fixture",
            family="measured_exit",
            record_key="d" * 64,
            network="8.8.8.8/32",
            provider="Fixture Proxy",
            basis="exit_observation",
            role="exit",
            method="explicit_http_proxy",
            service_category="proxy",
            source_url="https://example.com",
            content_sha256="d" * 64,
            observed_at=stamp(now),
            expires_at=stamp(now + timedelta(hours=24)),
            connection_type_claim="residential",
        )
        pending = dict(measurement=measurement, review=None)
        self.publish(self.dsn, "observe", pending)
        self.assertEqual(self.query("lookup", {"ip_address": "8.8.8.8"})["matches"], [])
        review = dict(
            observation_id=observation_id,
            observation_sha256="d" * 64,
            review_state="approved",
            reviewed_at=stamp(now + timedelta(seconds=1)),
            reviewer_sha256="f" * 64,
        )
        payload = dict(measurement=measurement, review=review)
        self.publish(self.dsn, "observe", payload)
        match = self.query("lookup", {"ip_address": "8.8.8.8"})["matches"][0]
        self.assertEqual(match["service_category"], "proxy")
        self.assertEqual(match["connection_type_claim"], "residential")
        self.assertNotIn("reviewer_sha256", match)
        self.assertEqual(self.publish(self.dsn, "observe", payload)["status"], "unchanged")
        conflict = copy.deepcopy(payload)
        conflict["measurement"]["provider"] = "Changed"
        with self.assertRaises(psycopg.Error):
            self.publish(self.dsn, "observe", conflict)
        stale = copy.deepcopy(payload)
        stale["measurement"]["observation_id"] = str(uuid4())
        stale["measurement"]["observed_at"] = stamp(now - timedelta(days=2))
        stale["measurement"]["expires_at"] = stamp(now - timedelta(days=1))
        stale["review"]["observation_id"] = stale["measurement"]["observation_id"]
        with self.assertRaises(psycopg.Error):
            self.publish(self.dsn, "observe", stale)

    def test_direct_insert_nonpublic_networks_and_null_registry_rejected(self):
        self.publish(self.dsn, "publish", batch())
        for network in (
            "0.0.0.0/0",
            "8.0.0.0/6",
            "10.0.0.0/8",
            "192.0.0.0/16",
            "224.0.0.0/4",
            "::/0",
        ):
            record = dict(
                network=network,
                provider="Fixture VPN",
                basis="network_inference",
                role="server",
                hostname=None,
                method="cidr_text",
                service_category="vpn",
            )
            with (
                self.subTest(network=network),
                self.assertRaises(psycopg.errors.CheckViolation) as error,
                psycopg.connect(self.dsn, row_factory=dict_row) as connection,
            ):
                self.Store(connection).run(
                    "publish", batch([source("creation-fixture", "cidr_text")])
                )
                connection.execute(
                    "INSERT INTO evidence_v2_indicators SELECT snapshot_id,%s,%s,provider,basis,role,'other',method,service_category,metadata FROM evidence_v2_indicators WHERE snapshot_id IN (SELECT snapshot_id FROM evidence_v2_snapshots WHERE source_id='creation-fixture') LIMIT 1",
                    (digest(canonical({**record, "hostname": "other"})), network),
                )
            self.assertEqual(
                error.exception.diag.constraint_name, "evidence_v2_indicators_network_public"
            )
        invalid = source("null-family")
        invalid["family"] = None
        with self.assertRaises(psycopg.Error):
            self.publish(self.dsn, "publish", batch([invalid]))

    def test_manifest_immutable_and_active_set_cannot_be_partial(self):
        self.publish(self.dsn, "publish", batch())
        with self.assertRaises(psycopg.Error), psycopg.connect(self.dsn) as connection:
            connection.execute("UPDATE evidence_v2_manifest SET definition='{}'::jsonb")
        with self.assertRaises(psycopg.Error), psycopg.connect(self.dsn) as connection:
            connection.execute("DELETE FROM evidence_v2_active")
        with self.assertRaises(psycopg.Error), psycopg.connect(self.dsn) as connection:
            connection.execute("TRUNCATE evidence_v2_indicators")

    def test_wrong_count_and_bad_timestamp_fail_atomically(self):
        malformed = batch()
        malformed["snapshots"][0]["fetched_at"] = stamp(datetime.now(UTC) - timedelta(seconds=1))
        with self.assertRaises(psycopg.Error):
            self.publish(self.dsn, "publish", malformed)
        self.assertEqual(self.count("evidence_v2_registry"), 0)
        malformed = batch()
        malformed["checked_at"] = None
        with self.assertRaises(psycopg.Error):
            self.publish(self.dsn, "publish", malformed)
        malformed = batch()
        malformed["snapshots"][0]["checked_at"] = datetime.now(UTC).replace(tzinfo=None).isoformat()
        with self.assertRaises(psycopg.Error):
            self.publish(self.dsn, "publish", malformed)

    def test_observation_helper_strips_private_and_binds_review(self):
        from test_exit_recorder import observation_fixture

        from vpnlens.evidence_store import observation_payload

        profile, record = observation_fixture("explicit_http_proxy")
        now = datetime.fromisoformat(record["active_receipts"][-1]["observed_at"]) + timedelta(
            seconds=1
        )
        review = dict(
            observation_id=record["observation_id"],
            observation_sha256=digest(canonical(record)),
            review_state="approved",
            reviewed_at=stamp(now),
            operator="private-os-user",
        )
        payload = observation_payload(record, profile, review, now)
        public = str(payload)
        for secret in (
            "private-os-user",
            "FIXTURE_PROXY_URL",
            "response_body",
            "baseline",
            "1.1.1.1",
        ):
            self.assertNotIn(secret, public)
        self.assertEqual(payload["measurement"]["basis"], "exit_observation")
        self.assertEqual(
            payload["measurement"]["expires_at"],
            stamp(now - timedelta(seconds=1) + timedelta(hours=24)),
        )
        review["observation_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            observation_payload(record, profile, review, now)

    def test_real_prepared_envelope_binds_registry_and_preserves_nulls(self):
        from vpnlens.evidence_collectors import prepare_batch

        sources = [source("first", "cidr_text", None), source("second", provider="Second")]
        registry = dict(schema_version=1, sources=sources)
        at = datetime.now(UTC) - timedelta(seconds=2)
        candidate = prepare_batch(
            registry,
            self.folder,
            fetcher=lambda entry: (
                b"8.8.8.0/24\n" if entry["adapter"] == "cidr_text" else b"8.8.8.8\n"
            ),
            clock=lambda: at,
        )
        import json

        payload = json.loads(candidate.read_text())
        self.publish(self.dsn, "publish", payload)
        matches = self.query("lookup", {"ip_address": "8.8.8.8"})["matches"]
        self.assertEqual(len(matches), 2)
        self.assertIsNone(matches[0]["provider"])
        self.assertIsNone(matches[0]["observed_at"])
        self.assertNotIn("raw_ref", str(matches))
        invalid = copy.deepcopy(payload)
        invalid["snapshots"][-1]["source"]["provider"] = "Unreviewed"
        with self.assertRaises(psycopg.Error):
            self.publish(self.dsn, "publish", invalid)
        self.assertEqual(self.count("evidence_v2_snapshots"), 2)

    def test_install_rejects_preexisting_incompatible_shape_without_mutation(self):
        from psycopg import sql
        from psycopg.conninfo import make_conninfo

        schema = "v2_bad_" + uuid4().hex
        dsn = make_conninfo(self.base, options=f"-c search_path={schema},public")
        with psycopg.connect(self.base, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            with psycopg.connect(dsn) as connection:
                connection.execute("CREATE TABLE evidence_v2_indicators(network text)")
                connection.execute("INSERT INTO evidence_v2_indicators VALUES('keep')")
            with self.assertRaises(ValueError):
                self.initialize(dsn)
            with psycopg.connect(dsn) as connection:
                self.assertEqual(
                    connection.execute("SELECT * FROM evidence_v2_indicators").fetchall(),
                    [("keep",)],
                )
                self.assertIsNone(
                    connection.execute("SELECT to_regclass('evidence_v2_registry')").fetchone()[0]
                )
        finally:
            with psycopg.connect(self.base, autocommit=True) as connection:
                connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))

    def test_exact_expiry_rejects_approval_and_approved_history_remains(self):
        # A short remaining lifetime provides actual-clock expiry proof without
        # changing immutable measurement timestamps or mocking PostgreSQL time.
        observed = datetime.now(UTC) - timedelta(hours=24) + timedelta(seconds=2)
        ident = str(uuid4())
        measurement = dict(
            observation_id=ident,
            observation_sha256="1" * 64,
            profile_sha256="2" * 64,
            source_id="observation-history",
            family="measured_exit",
            record_key="1" * 64,
            network="8.8.8.8/32",
            provider="Fixture",
            basis="exit_observation",
            role="exit",
            method="system_tunnel",
            service_category="vpn",
            source_url="https://example.com",
            content_sha256="1" * 64,
            observed_at=stamp(observed),
            expires_at=stamp(observed + timedelta(hours=24)),
            connection_type_claim="unknown",
        )
        review = dict(
            observation_id=ident,
            observation_sha256="1" * 64,
            review_state="approved",
            reviewed_at=stamp(datetime.now(UTC) - timedelta(milliseconds=1)),
            reviewer_sha256="3" * 64,
        )
        self.publish(self.dsn, "observe", dict(measurement=measurement, review=review))
        pending = copy.deepcopy(measurement)
        pending["observation_id"] = str(uuid4())
        self.publish(self.dsn, "observe", dict(measurement=pending, review=None))
        with psycopg.connect(self.dsn) as connection:
            connection.execute("SELECT pg_sleep(2)")
        historical = self.query("lookup", {"ip_address": "8.8.8.8"})["matches"][0]
        self.assertEqual(historical["review_state"], "approved")
        self.assertLessEqual(datetime.fromisoformat(historical["expires_at"]), datetime.now(UTC))
        self.assertEqual(datetime.fromisoformat(historical["checked_at"]), observed)
        self.assertEqual(self.query("sources")["enabled_source_ids"], [])
        # A fresh review of that old measurement cannot create a second approved row.
        review["observation_id"] = pending["observation_id"]
        # Reviewed before expiry, but publication after expiry must still fail.
        with self.assertRaises(psycopg.Error):
            self.publish(self.dsn, "observe", dict(measurement=pending, review=review))
        review["reviewed_at"] = pending["expires_at"]
        with self.assertRaises(psycopg.Error):
            self.publish(self.dsn, "observe", dict(measurement=pending, review=review))

    def test_unicode_identity_digest_matches_producer(self):
        item = source(provider="Fixture é " + chr(0x1F310))
        self.assertIn(chr(0x1F310), item["provider"])
        candidate = batch([item])
        self.publish(self.dsn, "publish", candidate)
        self.assertEqual(
            self.query("lookup", {"ip_address": "8.8.8.8"})["matches"][0]["provider"],
            item["provider"],
        )

    def test_committed_snapshot_rejects_indicator_append(self):
        candidate = batch()
        self.publish(self.dsn, "publish", candidate)
        record = indicator(candidate["snapshots"][0]["source"], "9.9.9.9")
        with self.assertRaises(psycopg.Error), psycopg.connect(self.dsn) as connection:
            connection.execute(
                """INSERT INTO evidence_v2_indicators
                SELECT snapshot_id,%s,%s,provider,basis,role,hostname,method,
                       service_category,metadata
                FROM evidence_v2_indicators LIMIT 1""",
                (record["record_key"], record["network"]),
            )
        with psycopg.connect(self.dsn) as connection:
            self.assertEqual(
                connection.execute(
                    """SELECT ipv4_count,
                    (SELECT count(*) FROM evidence_v2_indicators i
                     WHERE i.snapshot_id=s.snapshot_id)
                    FROM evidence_v2_snapshots s"""
                ).fetchone(),
                (1, 1),
            )
        self.assertEqual(self.query("lookup", {"ip_address": "9.9.9.9"})["matches"], [])

    def test_registry_types_are_not_silently_coerced(self):
        for key, value in (("family", 123), ("max_age_hours", "48"), ("source_id", 123)):
            candidate = batch()
            item = candidate["registry"]["sources"][0]
            item[key] = value
            candidate["snapshots"][0]["source"] = copy.deepcopy(item)
            candidate["registry_sha256"] = digest(canonical(candidate["registry"]))
            with self.subTest(key=key), self.assertRaises(psycopg.Error):
                self.publish(self.dsn, "publish", candidate)
        candidate = batch()
        candidate["schema_version"] = "1"
        with self.assertRaises(psycopg.Error):
            self.publish(self.dsn, "publish", candidate)
