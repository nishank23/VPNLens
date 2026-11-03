"""Synthetic exit recorder contract tests. No VPN or network evidence is produced."""

import copy
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from vpnlens.evidence_contract import canonical, digest, stamp

NOW = datetime(2026, 11, 2, 12, tzinfo=UTC)


def receipt(ip, at):
    body = json.dumps({"ip": ip}, separators=(",", ":"))
    return {
        "receipt_id": str(uuid4()),
        "ip": ip,
        "endpoint": "https://api.ipify.org?format=json",
        "response_body": body,
        "response_sha256": digest(body.encode()),
        "started_at": stamp(at),
        "observed_at": stamp(at),
    }


def observation_fixture(mode="system_tunnel"):
    """Synthetic fixture only, never proof of VPN operation."""
    profile = {
        "profile_id": "fixture-vpn",
        "provider": "Fixture VPN",
        "service_category": "vpn",
        "transport": mode,
        "documentation_url": "https://example.com",
        "proxy_env": None,
        "connection_type_claim": "unknown",
    }
    if mode == "explicit_http_proxy":
        profile["proxy_env"] = "FIXTURE_PROXY_URL"
    baseline = {
        "schema_version": 1,
        "kind": "baseline",
        "baseline_id": str(uuid4()),
        "profile_id": profile["profile_id"],
        "profile_sha256": digest(canonical(profile)),
        "operator_attested_disconnected": True,
        "receipt": receipt("1.1.1.1", NOW - timedelta(minutes=2)),
    }
    observation = {
        "schema_version": 1,
        "kind": "exit_observation",
        "observation_id": str(uuid4()),
        "profile_id": profile["profile_id"],
        "profile_sha256": digest(canonical(profile)),
        "method": mode,
        "review_state": "pending",
        "operator_attested_active": True,
        "baseline": baseline,
        "active_receipts": [receipt("8.8.8.8", NOW - timedelta(seconds=n)) for n in (2, 1)],
    }
    return profile, observation


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            importlib.util.find_spec("vpnlens.observation_contract"),
            "Observation contract must exist",
        )
        from vpnlens import observation_contract

        self.contract = observation_contract
        self.profile, self.record = observation_fixture()

    def validate(self, record=None, now=NOW):
        return self.contract.validate_observation(record or self.record, self.profile, now)

    def test_profile_normalizes_only_reviewed_fields(self):
        profile = {**self.profile, "secret": "not metadata"}
        profile.pop("connection_type_claim")
        self.assertEqual(self.contract.profile_contract(profile), self.profile)

    def test_profile_rejects_invalid_metadata(self):
        for key, values in {
            "profile_id": ["../bad", "UPPER", "a" * 101],
            "provider": ["", 1],
            "service_category": ["hosting"],
            "transport": ["auto"],
            "documentation_url": [
                "http://example.com",
                "https://u:p@example.com",
                "https://example.com?secret=x",
                "https://example.com#x",
                "https://example.com\\evil",
                "https://example.com\x00evil",
            ],
            "proxy_env": ["SECRET"],
            "connection_type_claim": ["verified"],
        }.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    self.contract.profile_contract({**self.profile, key: value})
        profile, _ = observation_fixture("explicit_http_proxy")
        for value in (None, "bad", "A", "A-B"):
            with self.assertRaises(ValueError):
                self.contract.profile_contract({**profile, "proxy_env": value})

    def test_valid_measurement_and_browser_original_expiry(self):
        result = self.validate()
        self.assertEqual(result["ip"], "8.8.8.8")
        self.assertEqual(result["observed_at"], self.record["active_receipts"][-1]["observed_at"])
        self.assertEqual(
            result["expires_at"], stamp(NOW - timedelta(seconds=1) + timedelta(hours=24))
        )
        self.assertEqual(result["operator_attested"], True)
        self.profile, self.record = observation_fixture("browser_import")
        self.assertEqual(self.validate()["method"], "browser_import")
        expiry = datetime.fromisoformat(
            self.record["active_receipts"][-1]["observed_at"]
        ) + timedelta(hours=24)
        with self.assertRaises(ValueError):
            self.validate(now=expiry)

    def test_exact_expiry_boundary_for_every_transport(self):
        for mode in ("system_tunnel", "explicit_http_proxy", "browser_import"):
            with self.subTest(mode=mode):
                self.profile, self.record = observation_fixture(mode)
                expiry = datetime.fromisoformat(
                    self.record["active_receipts"][-1]["observed_at"]
                ) + timedelta(hours=24)
                self.assertEqual(
                    self.validate(now=expiry - timedelta(microseconds=1))["expires_at"],
                    stamp(expiry),
                )
                with self.assertRaises(ValueError):
                    self.validate(now=expiry)

    def test_inclusive_fifteen_minute_window(self):
        last = NOW - timedelta(seconds=1)
        self.record["baseline"]["receipt"] = receipt("1.1.1.1", last - timedelta(minutes=15))
        self.validate()
        self.record["baseline"]["receipt"] = receipt(
            "1.1.1.1", last - timedelta(minutes=15, microseconds=1)
        )
        with self.assertRaises(ValueError):
            self.validate()

    def test_rejects_invalid_timestamps_and_order(self):
        for value in ("2026-11-02T11:59:00", stamp(NOW + timedelta(seconds=1))):
            record = copy.deepcopy(self.record)
            record["active_receipts"][0]["observed_at"] = value
            with self.assertRaises(ValueError):
                self.validate(record)
        record = copy.deepcopy(self.record)
        record["active_receipts"].reverse()
        with self.assertRaises(ValueError):
            self.validate(record)
        record = copy.deepcopy(self.record)
        record["active_receipts"][0]["started_at"] = stamp(NOW)
        with self.assertRaises(ValueError):
            self.validate(record)

    def test_duplicate_receipts_and_unchanged_or_disagreeing_ip_rejected(self):
        record = copy.deepcopy(self.record)
        record["active_receipts"][1]["receipt_id"] = record["active_receipts"][0]["receipt_id"]
        with self.assertRaises(ValueError):
            self.validate(record)
        for ips in (("1.1.1.1", "1.1.1.1"), ("8.8.8.8", "9.9.9.9")):
            record = copy.deepcopy(self.record)
            record["active_receipts"] = [
                receipt(ip, NOW - timedelta(seconds=2 - i)) for i, ip in enumerate(ips)
            ]
            with self.assertRaises(ValueError):
                self.validate(record)

    def test_record_bindings_and_attestations_are_enforced(self):
        for key, value in (
            ("profile_sha256", "0" * 64),
            ("method", "browser_import"),
            ("profile_id", "other"),
            ("review_state", "approved"),
            ("operator_attested_active", False),
            ("schema_version", True),
            ("observation_id", str(uuid4()).upper()),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate({**self.record, key: value})
        for key, value in (
            ("profile_id", "other"),
            ("profile_sha256", "0" * 64),
            ("operator_attested_disconnected", False),
            ("kind", "other"),
            ("schema_version", 2),
            ("baseline_id", "bad"),
        ):
            record = copy.deepcopy(self.record)
            record["baseline"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(record)
        self.profile["provider"] = "Different provider"
        with self.assertRaises(ValueError):
            self.validate()

    def test_receipt_rejects_invalid_route_body_and_address(self):
        sample = self.record["active_receipts"][0]
        for key, value in (
            ("endpoint", "https://elsewhere.example"),
            ("ip", "8.8.8.8/32"),
            ("response_sha256", "0" * 64),
            ("response_body", "x" * 4097),
            ("receipt_id", "not-uuid"),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.contract.receipt_contract({**sample, key: value}, NOW)
        for body in (
            '{"ip":"9.9.9.9"}',
            '{"ip":"8.8.8.8","ip":"9.9.9.9"}',
            '{"ip":"8.8.8.8","x":NaN}',
            "[]",
            "{}",
        ):
            bad = {**sample, "response_body": body, "response_sha256": digest(body.encode())}
            with self.assertRaises(ValueError):
                self.contract.receipt_contract(bad, NOW)
        for ip in ("127.0.0.1", "192.0.2.1", "100.64.0.1", "::1", "8.8.8.8/32"):
            with self.assertRaises(ValueError):
                self.contract.receipt_contract(receipt(ip, NOW), NOW)


class FakeResponse:
    def __init__(self, body=b'{"ip":"8.8.8.8"}', status=200):
        self.body, self.status_code = body, status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_bytes(self, chunk_size=None):
        self.chunk_size = chunk_size
        yield self.body


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            importlib.util.find_spec("vpnlens.observation_transport"),
            "Explicit transport must exist",
        )
        from vpnlens.observation_transport import fetch_receipt

        self.fetch = fetch_receipt
        self.calls = []
        self.requests = []
        self.response = FakeResponse()
        outer = self

        class Client:
            def __init__(self, **kwargs):
                outer.calls.append(kwargs)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def stream(self, method, url, **kwargs):
                outer.requests.append((method, url, kwargs))
                return outer.response

        self.factory = Client

    def fetch_profile(self, mode="system_tunnel", **kwargs):
        profile, _ = observation_fixture(mode)
        return self.fetch(profile, client_factory=self.factory, clock=lambda: NOW, **kwargs)

    def test_system_ignores_all_ambient_proxy_environment_and_verifies_tls(self):
        with patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://secret.invalid",
                "HTTPS_PROXY": "http://secret.invalid",
                "NO_PROXY": "*",
            },
        ):
            record = self.fetch_profile()
        self.assertEqual(
            self.calls,
            [
                {
                    "proxy": None,
                    "trust_env": False,
                    "follow_redirects": False,
                    "timeout": 10,
                    "verify": True,
                }
            ],
        )
        self.assertEqual(
            self.requests,
            [
                (
                    "GET",
                    "https://api.ipify.org?format=json",
                    {"headers": {"Cache-Control": "no-cache"}},
                )
            ],
        )
        from vpnlens.observation_contract import receipt_contract

        self.assertEqual(receipt_contract(record, NOW), NOW)
        self.assertNotIn("Fixture", canonical(record).decode())
        self.assertEqual(self.response.chunk_size, 4097)

    def test_explicit_proxy_and_direct_baseline(self):
        secret = "http://user:SECRET@proxy.example:8080"
        with patch.dict(os.environ, {"FIXTURE_PROXY_URL": secret, "NO_PROXY": "*"}):
            self.fetch_profile("explicit_http_proxy")
            self.fetch_profile("explicit_http_proxy", baseline=True)
        self.assertEqual([call["proxy"] for call in self.calls], [secret, None])
        self.assertTrue(all(call["trust_env"] is False for call in self.calls))

    def test_bad_proxy_urls_and_browser_mode_fail_before_request(self):
        for url in (
            "socks5://example.com",
            "http:///path",
            "https://example.com?x=1",
            "https://example.com#x",
            "http://example.com:bad",
            "http://example.com\\evil",
        ):
            with patch.dict(os.environ, {"FIXTURE_PROXY_URL": url}), self.assertRaises(ValueError):
                self.fetch_profile("explicit_http_proxy")
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            self.fetch_profile("explicit_http_proxy")
        with self.assertRaises(ValueError):
            self.fetch_profile("browser_import")
        self.assertEqual(self.calls, [])

    def test_proxy_failure_has_one_attempt_no_fallback_or_secret_in_error(self):
        secret = "http://user:SECRET@proxy.example"
        calls = []

        def fail(**kwargs):
            calls.append(kwargs)
            raise RuntimeError(secret)

        profile, _ = observation_fixture("explicit_http_proxy")
        with patch.dict(os.environ, {"FIXTURE_PROXY_URL": secret}):
            with self.assertRaises(Exception) as caught:
                self.fetch(profile, client_factory=fail, clock=lambda: NOW)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["proxy"], secret)
        self.assertNotIn("SECRET", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)

    def test_bad_response_caps_status_ip_json_utf8(self):
        for body, status in (
            (b"x" * 4097, 200),
            (b'{"ip":"8.8.8.8"}', 302),
            (b'{"ip":"127.0.0.1"}', 200),
            (b'{"ip":"::1"}', 200),
            (b'{"ip":"8.8.8.8","ip":"9.9.9.9"}', 200),
            (b"[]", 200),
            (b"\xff", 200),
        ):
            self.response = FakeResponse(body, status)
            with self.subTest(body=body[:50], status=status), self.assertRaises(ValueError):
                self.fetch_profile()

    def test_transport_rejects_naive_or_reversed_clock(self):
        profile, _ = observation_fixture()
        times = iter([NOW, NOW - timedelta(seconds=1)])
        with self.assertRaises(ValueError):
            self.fetch(profile, client_factory=self.factory, clock=lambda: next(times))
        with self.assertRaises(ValueError):
            self.fetch(profile, client_factory=self.factory, clock=lambda: NOW.replace(tzinfo=None))


class ArtifactFixture(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            importlib.util.find_spec("vpnlens.observe"), "Local artifact recorder must exist"
        )
        from vpnlens import observe

        self.recorder = observe
        self.profile, self.record = observation_fixture()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)


class ArtifactTests(ArtifactFixture):
    def test_baseline_binds_profile_and_attestation(self):
        calls = []

        def probe(profile, **kwargs):
            calls.append((profile, kwargs))
            return self.record["baseline"]["receipt"]

        baseline = self.recorder.create_baseline(self.profile, probe)
        self.assertEqual(calls, [(self.profile, {"baseline": True})])
        self.assertEqual(baseline["kind"], "baseline")
        self.assertEqual(baseline["profile_sha256"], digest(canonical(self.profile)))
        self.assertIs(baseline["operator_attested_disconnected"], True)

    def test_capture_exactly_two_receipts_and_saves_immutable_pending(self):
        calls = []
        receipts = iter(self.record["active_receipts"])

        def probe(profile):
            calls.append(profile)
            return next(receipts)

        result = self.recorder.create_observation(
            self.profile, self.record["baseline"], probe, lambda: NOW
        )
        self.assertEqual(len(calls), 2)
        target = self.recorder.save_observation(self.folder, result)
        self.assertEqual(target.parent.name, "pending")
        self.assertEqual(target.read_bytes(), canonical(result))
        self.assertEqual(self.recorder.save_observation(self.folder, result), target)
        with self.assertRaises(ValueError):
            self.recorder.save_observation(self.folder, {**result, "method": "changed"})
        self.assertEqual(target.read_bytes(), canonical(result))

    def test_stale_or_changed_baseline_rejected_before_probe(self):
        baseline = self.record["baseline"]
        for bad in (
            {**baseline, "profile_sha256": "0" * 64},
            {**baseline, "operator_attested_disconnected": False},
            {**baseline, "receipt": receipt("1.1.1.1", NOW - timedelta(minutes=16))},
        ):
            calls = []
            with self.assertRaises(ValueError):
                self.recorder.create_observation(
                    self.profile, bad, lambda *a: calls.append(a), lambda: NOW
                )
            self.assertEqual(calls, [])
        profile, _ = observation_fixture("browser_import")
        with self.assertRaises(ValueError):
            self.recorder.create_observation(profile, baseline, lambda *a: None, lambda: NOW)

    def test_approval_is_immutable_idempotent_and_preserves_measurement(self):
        target = self.recorder.save_observation(self.folder, self.record)
        original = target.read_bytes()
        path = self.recorder.approve_artifact(
            self.folder, self.record, self.profile, "reviewer", NOW
        )
        review = json.loads(path.read_bytes())
        self.assertEqual(
            review,
            {
                "observation_id": self.record["observation_id"],
                "observation_sha256": digest(original),
                "review_state": "approved",
                "operator": "reviewer",
                "reviewed_at": stamp(NOW),
            },
        )
        self.assertEqual(
            self.recorder.approve_artifact(
                self.folder, self.record, self.profile, "second reviewer", NOW
            ),
            path,
        )
        self.assertEqual(target.read_bytes(), original)
        altered = copy.deepcopy(self.record)
        altered["additional"] = "different original"
        with self.assertRaises(ValueError):
            self.recorder.approve_artifact(self.folder, altered, self.profile, "reviewer", NOW)
        self.assertEqual(path.read_bytes(), canonical(review))

    def test_approval_rejects_stale_changed_profile_empty_operator_and_corrupt_reviews(self):
        expiry = datetime.fromisoformat(
            self.record["active_receipts"][-1]["observed_at"]
        ) + timedelta(hours=24)
        for now, operator, profile in (
            (expiry, "x", self.profile),
            (NOW, " ", self.profile),
            (NOW, "x", {**self.profile, "provider": "changed"}),
        ):
            with self.assertRaises(ValueError):
                self.recorder.approve_artifact(self.folder, self.record, profile, operator, now)
        path = self.folder / "reviews" / (self.record["observation_id"] + ".json")
        path.parent.mkdir(exist_ok=True)
        for bad in (
            {},
            {
                "observation_id": self.record["observation_id"],
                "observation_sha256": digest(canonical(self.record)),
                "review_state": "approved",
                "operator": "x",
                "reviewed_at": "no-time",
            },
        ):
            path.write_bytes(canonical(bad))
            with self.assertRaises((ValueError, KeyError)):
                self.recorder.approve_artifact(self.folder, self.record, self.profile, "x", NOW)

    def test_read_json_archives_original_rejected_bytes_before_parsing_and_caps_input(self):
        source = self.folder / "source.json"
        archive = self.folder / "imports"
        raw = b' {"unclosed": '
        source.write_bytes(raw)
        with self.assertRaises(ValueError):
            self.recorder.read_json(source, archive_folder=archive)
        self.assertEqual((archive / (digest(raw) + ".bin")).read_bytes(), raw)
        source.write_bytes(b"x" * 262145)
        with self.assertRaises(ValueError):
            self.recorder.read_json(source, archive_folder=archive)
        self.assertEqual(len(list(archive.glob("*.bin"))), 1)


class CLITests(ArtifactFixture):
    def setUp(self):
        super().setUp()
        self.profiles = self.folder / "profiles.json"
        self.profiles.write_bytes(canonical({self.profile["profile_id"]: self.profile}))
        self.source = self.folder / "source.json"
        self.source.write_bytes(canonical(self.record))
        self.out = self.folder / "out"

    def run_cli(self, action, *args, probe=None, profile=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        argv = [
            action,
            "--profile",
            profile or self.profile["profile_id"],
            "--profiles",
            str(self.profiles),
            "--out",
            str(self.out),
            *map(str, args),
        ]
        with (
            redirect_stdout(stdout),
            redirect_stderr(stderr),
            patch.object(
                self.recorder, "fetch_receipt", side_effect=probe or AssertionError("No live calls")
            ),
            patch.object(self.recorder, "current_time", return_value=NOW),
            patch.object(self.recorder, "load_dotenv"),
            patch.dict(
                os.environ,
                {
                    "VPNLENS_EXTENDED_EVIDENCE": "false",
                    "DATABASE_URL": "recorder-tests-must-never-connect",
                },
            ),
        ):
            result = self.recorder.main(argv)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_cli_requires_attestations_and_never_probes_on_missing_confirmation(self):
        for action, args in (("baseline", ()), ("capture", ("--baseline", str(self.source)))):
            result, stdout, stderr = self.run_cli(action, *args)
            self.assertEqual(result, 1)
            self.assertEqual(stdout, "")
            self.assertIn("ValueError", stderr)
        failures = [json.loads(p.read_bytes()) for p in (self.out / "failures").glob("*.json")]
        self.assertEqual(len(failures), 2)
        self.assertTrue(all(set(f) == {"kind", "at", "error_type"} for f in failures))

    def test_cli_baseline_capture_approve_paths_are_actual_artifacts_without_database(self):
        def probe(profile, *, baseline=False):
            return (
                self.record["baseline"]["receipt"]
                if baseline
                else self.record["active_receipts"].pop(0)
            )

        with patch.dict(os.environ, {"DATABASE_URL": "must-not-be-used"}):
            code, output, _ = self.run_cli("baseline", "--confirm-disconnected", probe=probe)
            self.assertEqual(code, 0)
            baseline_path = json.loads(output)["path"]
            self.assertTrue(Path(baseline_path).is_file())
            code, output, _ = self.run_cli(
                "capture", "--baseline", baseline_path, "--confirm-active", probe=probe
            )
            self.assertEqual(code, 0)
            target = json.loads(output)
            self.assertEqual(target["status"], "local_artifact")
            observation_path = Path(target["path"])
            original = observation_path.read_bytes()
            code, output, _ = self.run_cli(
                "approve", "--file", observation_path, "--operator", "local-reviewer"
            )
        self.assertEqual(code, 0)
        self.assertEqual(Path(json.loads(output)["path"]).parent.name, "reviews")
        self.assertEqual(observation_path.read_bytes(), original)

    def test_cli_import_archives_rejected_bytes_and_preserves_original_times(self):
        self.profile, self.record = observation_fixture("browser_import")
        self.profiles.write_bytes(canonical({self.profile["profile_id"]: self.profile}))
        raw = b" \n" + canonical(self.record) + b"\n"
        self.source.write_bytes(raw)
        code, output, _ = self.run_cli("import", "--file", self.source)
        self.assertEqual(code, 0)
        self.assertEqual(Path(json.loads(output)["path"]).read_bytes(), canonical(self.record))
        self.assertEqual((self.out / "imports" / (digest(raw) + ".bin")).read_bytes(), raw)
        code, output2, _ = self.run_cli("import", "--file", self.source)
        self.assertEqual(code, 0)
        self.assertEqual(output2, output)
        self.record["active_receipts"][0]["ip"] = "9.9.9.9"
        invalid = canonical(self.record)
        self.source.write_bytes(invalid)
        code, _, _ = self.run_cli("import", "--file", self.source)
        self.assertEqual(code, 1)
        self.assertTrue((self.out / "imports" / (digest(invalid) + ".bin")).is_file())

    def test_cli_wrong_profile_key_or_import_mode_and_stale_import_rejected(self):
        code, _, _ = self.run_cli("import", "--file", self.source)
        self.assertEqual(code, 1)
        self.profiles.write_bytes(canonical({"wrong-key": self.profile}))
        code, _, _ = self.run_cli("baseline", "--confirm-disconnected", profile="wrong-key")
        self.assertEqual(code, 1)
        self.profile, self.record = observation_fixture("browser_import")
        self.profiles.write_bytes(canonical({self.profile["profile_id"]: self.profile}))
        self.source.write_bytes(canonical(self.record))
        for item in [self.record["baseline"]["receipt"], *self.record["active_receipts"]]:
            for key in ("started_at", "observed_at"):
                item[key] = stamp(datetime.fromisoformat(item[key]) - timedelta(days=1))
        self.source.write_bytes(canonical(self.record))
        code, _, _ = self.run_cli("import", "--file", self.source)
        self.assertEqual(code, 1)
        self.assertFalse((self.out / "pending").exists())

    def test_cli_oversized_input_only_writes_safe_failure_and_no_archive(self):
        self.profile, _ = observation_fixture("browser_import")
        self.profiles.write_bytes(canonical({self.profile["profile_id"]: self.profile}))
        self.source.write_bytes(b"SECRET" * 50000)
        code, output, error = self.run_cli("import", "--file", self.source)
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertNotIn("SECRET", error)
        self.assertFalse((self.out / "imports").exists())
        failures = list((self.out / "failures").glob("*.json"))
        self.assertEqual(len(failures), 1)
        self.assertNotIn(b"SECRET", failures[0].read_bytes())

    def test_cli_failure_archive_error_preserves_original_error_class_without_secret(self):
        with patch.object(self.recorder, "write_once", side_effect=PermissionError("SECRET")):
            code, output, error = self.run_cli(
                "baseline", "--confirm-disconnected", probe=RuntimeError("SECRET proxy URL")
            )
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("RuntimeError", error)
        self.assertIn("PermissionError", error)
        self.assertNotIn("SECRET", error)

    def test_cli_rejects_stale_baseline_before_transport(self):
        self.record["baseline"]["receipt"] = receipt("1.1.1.1", NOW - timedelta(minutes=16))
        self.source.write_bytes(canonical(self.record["baseline"]))
        calls = []
        code, _, _ = self.run_cli(
            "capture",
            "--baseline",
            self.source,
            "--confirm-active",
            probe=lambda *a, **kw: calls.append(a),
        )
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])

    def test_cli_conflicting_same_uuid_import_keeps_original(self):
        self.profile, self.record = observation_fixture("browser_import")
        self.profiles.write_bytes(canonical({self.profile["profile_id"]: self.profile}))
        self.source.write_bytes(canonical(self.record))
        code, output, _ = self.run_cli("import", "--file", self.source)
        self.assertEqual(code, 0)
        target = Path(json.loads(output)["path"])
        original = target.read_bytes()
        self.record["extra"] = "modified same UUID"
        self.source.write_bytes(canonical(self.record))
        code, _, _ = self.run_cli("import", "--file", self.source)
        self.assertEqual(code, 1)
        self.assertEqual(target.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()


class ApprovalPublicationTests(ArtifactFixture):
    run_cli = CLITests.run_cli

    def setUp(self):
        super().setUp()
        self.profiles = self.folder / "profiles.json"
        self.profiles.write_bytes(canonical({self.profile["profile_id"]: self.profile}))
        self.source = self.folder / "source.json"
        self.source.write_bytes(canonical(self.record))
        self.out = self.folder / "out"

    def test_enabled_approval_db_failure_retry_preserves_review_and_measurement(self):
        from vpnlens.config import Settings

        self.assertTrue(hasattr(self.recorder, "publish_contract"))
        with (
            patch.object(
                self.recorder.Settings,
                "from_env",
                return_value=Settings(database_url="dummy-tests-only", extended_evidence=True),
            ),
            patch.object(
                self.recorder, "publish_contract", side_effect=RuntimeError("private DSN")
            ) as publish,
        ):
            code, output, error = self.run_cli(
                "approve", "--file", self.source, "--operator", "fixture"
            )
        self.assertEqual(code, 1)
        self.assertNotIn("private", error)
        review = self.out / "reviews" / (self.record["observation_id"] + ".json")
        original_review = review.read_bytes()
        pending = self.out / "pending" / (self.record["observation_id"] + ".json")
        self.assertEqual(pending.read_bytes(), self.source.read_bytes())
        first_payload = publish.call_args.args[2]
        with (
            patch.object(
                self.recorder.Settings,
                "from_env",
                return_value=Settings(database_url="dummy-tests-only", extended_evidence=True),
            ),
            patch.object(
                self.recorder, "publish_contract", return_value={"status": "unchanged"}
            ) as publish,
        ):
            code, output, error = self.run_cli(
                "approve", "--file", self.source, "--operator", "fixture"
            )
        self.assertEqual(code, 0, error)
        self.assertEqual(publish.call_args.args[2], first_payload)
        self.assertEqual(review.read_bytes(), original_review)
        self.assertEqual(json.loads(output)["status"], "published")
        value = json.loads(original_review)
        value["observation_sha256"] = "0" * 64
        review.write_bytes(canonical(value))
        with (
            patch.object(
                self.recorder.Settings,
                "from_env",
                return_value=Settings(database_url="dummy-tests-only", extended_evidence=True),
            ),
            patch.object(self.recorder, "publish_contract") as publish,
        ):
            code, _, _ = self.run_cli("approve", "--file", self.source, "--operator", "fixture")
        self.assertEqual(code, 1)
        publish.assert_not_called()
