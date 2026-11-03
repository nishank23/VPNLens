"""Pure policy and opt-in configuration contract."""

import importlib.util
import unittest
from datetime import UTC, datetime, timedelta

NOW = datetime(2026, 11, 3, tzinfo=UTC)


def legacy():
    return dict(
        vpn_status="unknown",
        tor_status="unknown",
        evidence=[],
        active_source_count=2,
        recently_checked_source_count=1,
        stale_after_hours=48,
    )


def record(**changes):
    result = dict(
        source_id="fixture",
        family="fixture",
        record_key="a" * 64,
        network="8.8.8.8/32",
        provider="Fixture",
        basis="provider_list",
        role="server",
        method="host_text",
        service_category="vpn",
        source_url="https://example.com",
        content_sha256="b" * 64,
        fetched_at=NOW.isoformat(),
        checked_at=NOW.isoformat(),
        observed_at=None,
        expires_at=(NOW + timedelta(hours=48)).isoformat(),
        review_state=None,
        hostname=None,
        connection_type_claim=None,
        secret="private",
    )
    result.update(changes)
    return result


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("vpnlens.evidence_policy"))
        from vpnlens.evidence_policy import apply_policy, public_record

        self.apply, self.public = apply_policy, public_record

    def test_direct_lists_dns_and_deepcopy(self):
        original = legacy()
        for attrs in ({}, dict(basis="provider_dns", method="dns_a")):
            result = self.apply(original, [record(**attrs)], dict(active=1, recent=1), NOW)
            self.assertEqual(result["vpn_status"], "listed")
            self.assertEqual(result["vpn_assessment"], "direct_association")
            self.assertEqual(result["active_source_count"], 3)
            self.assertNotIn("secret", result["evidence"][0])
            result["evidence"].append({})
        self.assertEqual(original, legacy())

    def test_weak_stale_and_exact_boundary(self):
        weak = record(basis="network_inference", method="cidr_text", network="8.8.8.0/24")
        result = self.apply(legacy(), [weak], {}, NOW)
        self.assertEqual(result["vpn_status"], "unknown")
        self.assertEqual(result["vpn_assessment"], "network_only")
        for delta, stale in (
            (timedelta(hours=48), False),
            (timedelta(hours=48, microseconds=1), True),
            (timedelta(seconds=-1), True),
        ):
            item = record(
                checked_at=(NOW - delta).isoformat(),
                fetched_at=(NOW - delta).isoformat(),
                expires_at=(NOW - delta + timedelta(hours=48)).isoformat(),
            )
            result = self.apply(legacy(), [item], {}, NOW)
            self.assertEqual(result["evidence"][0]["stale"], stale)
            self.assertEqual(result["vpn_status"], "unknown" if stale else "listed")

    def test_observation_approval_expiry_proxy_and_privacy(self):
        obs = record(
            basis="exit_observation",
            role="exit",
            method="explicit_http_proxy",
            service_category="proxy",
            connection_type_claim="unknown",
            observed_at=(NOW - timedelta(hours=1)).isoformat(),
            expires_at=(NOW + timedelta(hours=23)).isoformat(),
            review_state="approved",
        )
        result = self.apply(legacy(), [obs], {}, NOW)
        self.assertEqual(result["proxy_status"], "listed")
        self.assertEqual(result["vpn_status"], "unknown")
        self.assertEqual(result["residential_proxy_status"], "unknown")
        exposed = result["additional_evidence"][0]
        self.assertTrue(exposed["operator_attested"])
        self.assertEqual(exposed["checked_at"], obs["observed_at"])
        for state in ("pending", "rejected", None):
            self.assertEqual(
                self.apply(legacy(), [{**obs, "review_state": state}], {}, NOW)[
                    "additional_evidence"
                ],
                [],
            )
        self.assertEqual(
            self.apply(legacy(), [obs], {}, NOW + timedelta(hours=23))["proxy_status"], "unknown"
        )
        for attrs in (
            dict(expires_at=None),
            dict(observed_at=(NOW + timedelta(seconds=1)).isoformat()),
            dict(expires_at=(NOW + timedelta(days=2)).isoformat()),
        ):
            self.assertEqual(
                self.apply(legacy(), [{**obs, **attrs}], {}, NOW)["proxy_status"], "unknown"
            )

    def test_invalid_records_never_classify(self):
        for attrs in (
            dict(method="exec"),
            dict(network="127.0.0.1"),
            dict(source_url="https://user:secret@example.com"),
            dict(content_sha256="bad"),
            dict(checked_at=None),
            dict(service_category="hosting"),
            dict(role="bogus"),
        ):
            self.assertEqual(
                self.apply(legacy(), [record(**attrs)], {}, NOW)["vpn_status"], "unknown"
            )
        old = legacy()
        old["vpn_status"] = "listed"
        self.assertEqual(self.apply(old, [], {}, NOW)["vpn_assessment"], "direct_association")


class FlagTests(unittest.TestCase):
    def test_strict_flag(self):
        import vpnlens.config as config

        self.assertTrue(hasattr(config, "evidence_enabled"))
        for value in ("true", " TRUE ", "1"):
            self.assertTrue(config.evidence_enabled(value))
        for value in ("false", " FALSE ", "0"):
            self.assertFalse(config.evidence_enabled(value))
        for value in ("yes", "secret", "", "2"):
            with self.assertRaises(ValueError) as error:
                config.evidence_enabled(value)
            self.assertNotIn(value or "xyz", str(error.exception))
        self.assertFalse(config.Settings().extended_evidence)
