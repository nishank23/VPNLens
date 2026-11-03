import hashlib
import io
import json
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from vpnlens.evidence_contract import canonical, digest, instant, public_network, stamp, write_once


class EvidenceContractTests(unittest.TestCase):
    def test_canonical_json_sorts_keys_and_rejects_non_finite_values(self):
        self.assertEqual(canonical({"z": 1, "a": 2}), b'{"a":2,"z":1}')
        with self.assertRaises(ValueError):
            canonical({"value": float("nan")})

    def test_digest_returns_sha256_hex(self):
        self.assertEqual(digest(b"abc"), hashlib.sha256(b"abc").hexdigest())

    def test_stamp_normalizes_aware_datetimes_to_utc(self):
        local_time = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=3)))
        self.assertEqual(stamp(local_time), "2024-01-02T00:04:05+00:00")

    def test_stamp_rejects_naive_datetime(self):
        with self.assertRaises(ValueError):
            stamp(datetime(2024, 1, 2))

    def test_stamp_defaults_to_current_utc_time(self):
        parsed = datetime.fromisoformat(stamp())
        self.assertEqual(parsed.utcoffset(), timedelta(0))

    def test_instant_parses_and_normalizes_aware_timestamp(self):
        self.assertEqual(
            instant("2024-01-02T03:04:05+03:00"), datetime(2024, 1, 2, 0, 4, 5, tzinfo=timezone.utc)
        )

    def test_instant_rejects_naive_timestamp(self):
        with self.assertRaises(ValueError):
            instant("2024-01-02T03:04:05")

    def test_public_network_preserves_host_and_network_prefixes(self):
        self.assertEqual(public_network("8.8.8.8"), "8.8.8.8/32")
        self.assertEqual(public_network("103.108.230.0/24"), "103.108.230.0/24")

    def test_public_network_rejects_non_public_or_non_canonical_inputs(self):
        for value in (
            "10.0.0.1",
            "0.0.0.0/0",
            "103.108.230.1/24",
            "192.0.2.1",
            "198.51.100.0/24",
            "203.0.113.1",
            "2001:4860:4860::8888",
            "100.64.0.1",
            "224.0.0.1",
            "224.0.0.0/4",
            "8.0.0.0/6",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                public_network(value)

    def test_write_once_creates_private_file_and_allows_identical_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "artifact.json"
            write_once(path, b"payload")
            write_once(path, b"payload")
            self.assertEqual(path.read_bytes(), b"payload")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_write_once_rejects_conflict_and_preserves_original_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            write_once(path, b"original")
            with self.assertRaisesRegex(ValueError, "Conflicting or corrupted immutable artifact"):
                write_once(path, b"replacement")
            self.assertEqual(path.read_bytes(), b"original")
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_write_once_rejects_corrupted_existing_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            path.write_bytes(b"corrupted")
            with self.assertRaisesRegex(ValueError, "Conflicting or corrupted immutable artifact"):
                write_once(path, b"expected")
            self.assertEqual(path.read_bytes(), b"corrupted")
            self.assertEqual(list(Path(directory).iterdir()), [path])


# Fixed public fixtures; these tests never query a network or a database.
ROOT = Path(__file__).resolve().parents[1]


def registry_fixture():
    return {
        "schema_version": 1,
        "sources": [
            {
                "source_id": "x4b-vpn-v4",
                "family": "x4b",
                "enabled": True,
                "adapter": "cidr_text",
                "basis": "network_inference",
                "provider": None,
                "role": "unknown",
                "url": "https://example.com/vpn.txt",
                "max_bytes": 5000000,
                "max_age_hours": 48,
                "attribution_url": "https://example.com/about",
            },
            {
                "source_id": "vpngate-v4",
                "family": "vpngate",
                "enabled": True,
                "adapter": "vpngate_csv",
                "basis": "provider_list",
                "provider": "VPN Gate",
                "role": "server",
                "url": "https://example.com/vpngate",
                "max_bytes": 25000000,
                "max_age_hours": 48,
                "attribution_url": "https://example.com/about",
            },
            {
                "source_id": "urbanvpn-dns-v4",
                "family": "urbanvpn-reviewed-hostnames",
                "enabled": True,
                "adapter": "dns_a",
                "basis": "provider_dns",
                "provider": "UrbanVPN",
                "role": "unknown",
                "url": "https://example.com/review",
                "hosts": ["p-jp1.urban-vpn.com"],
                "max_bytes": 5000000,
                "max_age_hours": 48,
                "attribution_url": "https://www.urban-vpn.com/",
            },
        ],
    }


def collectors():
    from vpnlens import evidence_collectors

    return evidence_collectors


class RegistryIdentityTests(unittest.TestCase):
    def test_initial_registry_matches_reviewed_sources(self):
        registry = json.loads((ROOT / "config/evidence_sources.json").read_text())
        entries = collectors().registry_entries(registry)
        self.assertEqual(
            [e["source_id"] for e in entries], ["x4b-vpn-v4", "vpngate-v4", "urbanvpn-dns-v4"]
        )
        self.assertEqual(
            entries[0]["url"],
            "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv4.txt",
        )
        self.assertEqual(entries[1]["url"], "https://www.vpngate.net/api/iphone/")
        self.assertEqual(entries[2]["url"], "https://www.netify.ai/resources/ips/103.108.230.50")
        self.assertEqual(entries[2]["hosts"], ["p-jp1.urban-vpn.com"])

    def test_entries_keep_disabled_and_return_independent_copies(self):
        registry = registry_fixture()
        registry["sources"][2]["enabled"] = False
        entries = collectors().registry_entries(registry)
        self.assertFalse(entries[2]["enabled"])
        entries[2]["hosts"].append("other.example.com")
        self.assertEqual(len(registry["sources"][2]["hosts"]), 1)

    def test_invalid_registry_fields_are_rejected(self):
        for field, value in [
            ("source_id", "../escape"),
            ("source_id", "UPPER"),
            ("source_id", "a" * 101),
            ("enabled", 1),
            ("url", "https://user:password@example.com/a"),
            ("attribution_url", "http://example.com"),
            ("url", "https:///missing"),
            ("adapter", "datacenter"),
            ("basis", "provider_list"),
            ("role", "client"),
            ("family", ""),
            ("provider", ""),
            ("max_bytes", 5000001),
            ("max_age_hours", 49),
            ("max_age_hours", True),
        ]:
            registry = registry_fixture()
            registry["sources"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                collectors().registry_entries(registry)
        for registry in [
            {},
            {"schema_version": True, "sources": []},
            {"schema_version": 2, "sources": []},
            {"schema_version": 1, "sources": {}},
            {"schema_version": 1, "sources": [None]},
        ]:
            with self.subTest(registry=registry), self.assertRaises(ValueError):
                collectors().registry_entries(registry)

    def test_duplicate_source_ids_and_invalid_dns_hosts_rejected(self):
        registry = registry_fixture()
        registry["sources"][1]["source_id"] = registry["sources"][0]["source_id"]
        with self.assertRaises(ValueError):
            collectors().registry_entries(registry)
        for hosts in [
            [],
            ["bad..host"],
            ["-bad.example.com"],
            ["a.example", "a.example"],
            ["https://example.com"],
            ["8.8.8.8"],
            ["a" * 64 + ".com"],
            ["a.example"] * 101,
        ]:
            registry = registry_fixture()
            registry["sources"][2]["hosts"] = hosts
            with self.subTest(hosts=hosts), self.assertRaises(ValueError):
                collectors().registry_entries(registry)

    def test_identity_preserves_ranges_and_overlapping_providers_and_hosts(self):
        module = collectors()
        source = registry_fixture()["sources"][0]
        row = module.indicator(source, "103.108.230.0/24", metadata={"ttl": 60})
        self.assertEqual(row["network"], "103.108.230.0/24")
        identity = {
            key: row[key]
            for key in (
                "network",
                "provider",
                "basis",
                "role",
                "hostname",
                "service_category",
                "method",
            )
        }
        self.assertEqual(row["record_key"], digest(canonical(identity)))
        self.assertEqual(
            row["record_key"],
            module.indicator(source, "103.108.230.0/24", metadata={"ttl": 120})["record_key"],
        )
        provider_source = dict(source, provider="Other provider")
        self.assertNotEqual(
            row["record_key"], module.indicator(provider_source, "103.108.230.0/24")["record_key"]
        )
        self.assertNotEqual(
            module.indicator(source, "8.8.8.8", "a.example")["record_key"],
            module.indicator(source, "8.8.8.8", "b.example")["record_key"],
        )
        with self.assertRaises(ValueError):
            module.indicator(source, "10.0.0.1")


class ParserTests(unittest.TestCase):
    def test_cidr_text_deduplicates_without_expansion_and_counts_ipv6(self):
        rows, skipped = collectors().parse_text(
            b"\xef\xbb\xbf# comment\n103.108.230.0/24\n8.8.8.8\n103.108.230.0/24\n2001:4860::/32\n",
            registry_fixture()["sources"][0],
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(skipped, 1)
        self.assertIn("103.108.230.0/24", [r["network"] for r in rows])
        self.assertEqual([r["record_key"] for r in rows], sorted(r["record_key"] for r in rows))

    def test_text_rejects_invalid_private_noncanonical_empty_and_host_ranges(self):
        source = registry_fixture()["sources"][0]
        for payload in [
            b"",
            b"# comment",
            b"2001:4860::/32",
            b"8.8.8.8\n10.0.0.1",
            b"103.108.230.1/24",
            b"8.8.8.8\nbroken",
            b"\xff",
        ]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                collectors().parse_text(payload, source)
        source = dict(source, adapter="host_text", basis="provider_list")
        with self.assertRaises(ValueError):
            collectors().parse_text(b"103.108.230.0/24", source)
        self.assertEqual(len(collectors().parse_text(b"8.8.8.8", source)[0]), 1)

    def test_host_text_skips_syntactically_valid_ipv6_ranges(self):
        source = dict(registry_fixture()["sources"][0], adapter="host_text", basis="provider_list")
        rows, skipped = collectors().parse_text(b"8.8.8.8\n2001:4860::/32", source)
        self.assertEqual(len(rows), 1)
        self.assertEqual(skipped, 1)

    def test_vpngate_ignores_configuration_preserves_hostname_and_deduplicates(self):
        payload = (
            b"*vpn_servers\n#HostName,IP,OpenVPN_ConfigData_Base64\n"
            b"a,8.8.8.8,NOT_BASE64_SHOULD_NOT_EXECUTE\n"
            b"a,8.8.8.8,other\nb,8.8.8.8,other\n"
            b"v6,2001:4860::8888,ignore\n*\n"
        )
        rows, skipped = collectors().parse_vpngate(payload, registry_fixture()["sources"][1])
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["hostname"] for row in rows}, {"a", "b"})
        self.assertEqual(skipped, 1)
        self.assertEqual([r["record_key"] for r in rows], sorted(r["record_key"] for r in rows))

    def test_vpngate_rejects_bad_utf8_headers_empty_and_invalid_rows(self):
        for payload in [
            b"",
            b"\xff",
            b"HostName,IP\na,8.8.8.8",
            b"#HostName,IP\n",
            b"#HostName,IP\na,10.0.0.1",
            b"#HostName,IP\n,8.8.8.8",
            b"#HostName,IP\na,8.8.8.0/24",
            b"#HostName,IP\na,8.8.8.8,extra",
            b'#HostName,IP\n"unfinished,8.8.8.8',
            b"#HostName,IP\nv6,2001:4860::8888",
        ]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                collectors().parse_vpngate(payload, registry_fixture()["sources"][1])


class FakeResponse(io.BytesIO):
    def __init__(
        self, payload=b"8.8.8.8", status=200, headers=None, url="https://example.com/final"
    ):
        super().__init__(payload)
        self.status = status
        self.code = status
        self.msg = "fixture"
        self.headers = {} if headers is None else headers
        self.final_url = url
        self.read_sizes = []

    def geturl(self):
        return self.final_url

    def info(self):
        return self.headers

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)


class TransportTests(unittest.TestCase):
    def test_http_request_is_bounded_and_accepts_safe_redirect(self):
        source = registry_fixture()["sources"][0]
        response = FakeResponse(headers={"Content-Length": "7"})
        opener = Mock(return_value=response)
        self.assertEqual(collectors().fetch_payload(source, opener), b"8.8.8.8")
        request = opener.call_args.args[0]
        self.assertEqual(request.get_header("User-agent"), "VPNLens-portfolio/1.0")
        self.assertEqual(opener.call_args.kwargs, {"timeout": 30})
        self.assertEqual(response.read_sizes, [5000001])

    def test_default_transport_rejects_unsafe_redirect_before_following_it(self):
        source = registry_fixture()["sources"][0]
        start, intermediate, final = (
            source["url"],
            "https://example.com/middle",
            "https://example.com/final",
        )
        for forbidden in [
            "http://example.com/downgrade",
            "https://user:secret@example.com/credentials",
        ]:
            visited = []

            def fake_open(handler, request):
                url = request.full_url
                visited.append(url)
                targets = {start: intermediate, intermediate: forbidden, forbidden: final}
                if url in targets:
                    return FakeResponse(status=302, headers={"location": targets[url]}, url=url)
                return FakeResponse(url=url)

            with self.subTest(target=forbidden), patch("urllib.request._opener", None):
                with (
                    patch("urllib.request.HTTPSHandler.https_open", fake_open),
                    patch("urllib.request.HTTPHandler.http_open", fake_open),
                ):
                    with self.assertRaises(ValueError):
                        collectors().fetch_payload(source)
                self.assertEqual(visited, [start, intermediate])

    def test_default_transport_follows_valid_https_and_relative_redirects(self):
        source = registry_fixture()["sources"][0]
        start, intermediate, final = (
            source["url"],
            "https://example.com/middle",
            "https://other.example/final",
        )
        visited = []

        def fake_open(handler, request):
            url = request.full_url
            visited.append(url)
            targets = {start: "/middle", intermediate: final}
            if url in targets:
                return FakeResponse(status=302, headers={"location": targets[url]}, url=url)
            return FakeResponse(url=url)

        with (
            patch("urllib.request._opener", None),
            patch("urllib.request.HTTPSHandler.https_open", fake_open),
        ):
            self.assertEqual(collectors().fetch_payload(source), b"8.8.8.8")
        self.assertEqual(visited, [start, intermediate, final])

    def test_default_transport_rejects_declared_oversize_redirect_without_reading(self):
        source = registry_fixture()["sources"][0]
        for status in [301, 302, 303, 307, 308]:
            redirect = FakeResponse(
                b"x" * 5000001,
                status=status,
                headers={"location": "https://example.com/final", "Content-Length": "5000001"},
                url=source["url"],
            )
            visited = []

            def fake_open(handler, request):
                visited.append(request.full_url)
                return redirect if request.full_url == source["url"] else FakeResponse()

            with self.subTest(status=status), patch("urllib.request._opener", None):
                with patch("urllib.request.HTTPSHandler.https_open", fake_open):
                    with self.assertRaises(ValueError):
                        collectors().fetch_payload(source)
                self.assertEqual(visited, [source["url"]])
                self.assertEqual(redirect.read_sizes, [])
                self.assertTrue(redirect.closed)

    def test_default_transport_does_not_drain_unknown_length_redirect_body(self):
        source = registry_fixture()["sources"][0]
        redirect = FakeResponse(
            b"x" * 5000001,
            status=302,
            headers={"location": "https://example.com/final"},
            url=source["url"],
        )
        final = FakeResponse()

        def fake_open(handler, request):
            return redirect if request.full_url == source["url"] else final

        with (
            patch("urllib.request._opener", None),
            patch("urllib.request.HTTPSHandler.https_open", fake_open),
        ):
            self.assertEqual(collectors().fetch_payload(source), b"8.8.8.8")
        self.assertEqual(redirect.read_sizes, [])
        self.assertTrue(redirect.closed)
        self.assertEqual(final.read_sizes, [5000001])

    def test_http_rejects_status_bad_redirect_lengths_and_oversize(self):
        source = registry_fixture()["sources"][0]
        for response in [
            FakeResponse(status=201),
            FakeResponse(status=404),
            FakeResponse(url="http://example.com"),
            FakeResponse(url="https://user:secret@example.com"),
            FakeResponse(url="https:///missing"),
            FakeResponse(headers={"Content-Length": "-1"}),
            FakeResponse(headers={"Content-Length": "nope"}),
            FakeResponse(headers={"Content-Length": "5000001"}),
            FakeResponse(headers={"Content-Length": "8"}),
            FakeResponse(b"x" * 5000001),
        ]:
            with (
                self.subTest(status=response.status, url=response.final_url),
                self.assertRaises(ValueError),
            ):
                collectors().fetch_payload(source, Mock(return_value=response))
        with self.assertRaises(OSError):
            collectors().fetch_payload(source, Mock(side_effect=OSError("offline")))

    def test_dns_queries_absolute_A_with_timeout_and_public_sorted_answers(self):
        class Answer:
            rrset = SimpleNamespace(ttl=120)

            def __iter__(self):
                return iter(
                    [SimpleNamespace(address=ip) for ip in ["8.8.8.8", "1.1.1.1", "8.8.8.8"]]
                )

        resolver = Mock()
        resolver.resolve.return_value = Answer()
        result = collectors().resolve_a("p-jp1.urban-vpn.com", resolver)
        resolver.resolve.assert_called_once_with(
            "p-jp1.urban-vpn.com.", "A", search=False, lifetime=5.0, raise_on_no_answer=False
        )
        self.assertEqual(
            result,
            {
                "hostname": "p-jp1.urban-vpn.com",
                "addresses": ["1.1.1.1", "8.8.8.8"],
                "ttl": 120,
                "state": "answer",
            },
        )

    def test_dns_withdrawal_is_distinct_from_transport_failure_and_private_answers(self):
        import dns.exception
        import dns.resolver

        resolver = Mock()
        resolver.resolve.side_effect = dns.resolver.NXDOMAIN()
        self.assertEqual(collectors().resolve_a("a.example", resolver)["state"], "nxdomain")
        resolver.resolve.side_effect = None
        resolver.resolve.return_value = SimpleNamespace(rrset=None)
        self.assertEqual(collectors().resolve_a("a.example", resolver)["state"], "no_a")
        for error in [dns.exception.Timeout(), dns.resolver.NoNameservers()]:
            resolver.resolve.side_effect = error
            with self.assertRaises(type(error)):
                collectors().resolve_a("a.example", resolver)

        class Answer:
            rrset = SimpleNamespace(ttl=60)

            def __iter__(self):
                return iter([SimpleNamespace(address="10.0.0.1")])

        resolver.resolve.side_effect = None
        resolver.resolve.return_value = Answer()
        with self.assertRaises(ValueError):
            collectors().resolve_a("a.example", resolver)


class BatchTests(unittest.TestCase):
    @staticmethod
    def fetch(source):
        if source["adapter"] == "cidr_text":
            return b"8.8.8.8"
        return b"#HostName,IP,OpenVPN_ConfigData_Base64\na,1.1.1.1,ignored"

    @staticmethod
    def answer(hostname):
        return {
            "hostname": hostname,
            "addresses": ["103.108.230.50"],
            "ttl": 300,
            "state": "answer",
        }

    def prepare(self, directory, **kwargs):
        return collectors().prepare_batch(
            registry_fixture(), directory, fetcher=self.fetch, resolver=self.answer, **kwargs
        )

    def test_complete_batch_and_hashes_are_reproducible_except_dns_check_time(self):
        with tempfile.TemporaryDirectory() as directory:
            first = self.prepare(directory, clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
            second = self.prepare(
                directory, clock=lambda: datetime(2026, 1, 2, tzinfo=timezone.utc)
            )
            one, two = [json.loads(p.read_text()) for p in [first, second]]
            self.assertNotEqual(one["batch_id"], two["batch_id"])
            self.assertEqual(one["registry_sha256"], digest(canonical(registry_fixture())))
            self.assertEqual(len(one["snapshots"]), 3)
            self.assertEqual(
                one["snapshots"][0]["content_sha256"], two["snapshots"][0]["content_sha256"]
            )
            self.assertNotEqual(
                one["snapshots"][2]["content_sha256"], two["snapshots"][2]["content_sha256"]
            )
            self.assertEqual(one["snapshots"][0]["raw_ref"], two["snapshots"][0]["raw_ref"])
            self.assertEqual(len(list((Path(directory) / "raw").glob("*/*.bin"))), 4)
            for snapshot in one["snapshots"]:
                raw = Path(directory) / snapshot["raw_ref"]
                self.assertEqual(digest(raw.read_bytes()), snapshot["content_sha256"])
                self.assertEqual(snapshot["fetched_at"], snapshot["checked_at"])
                self.assertIsNone(snapshot["publisher_at"])
            dns = one["snapshots"][2]
            raw_dns = json.loads((Path(directory) / dns["raw_ref"]).read_text())
            self.assertEqual(raw_dns["family"], "A")
            self.assertEqual(raw_dns["answers"][0]["queried_at"], one["checked_at"])
            self.assertEqual(raw_dns["answers"][0]["completed_at"], one["checked_at"])
            self.assertEqual(dns["records"][0]["metadata"], {"ttl": 300})

    def test_disabled_sources_remain_in_registry_and_are_never_fetched(self):
        registry = registry_fixture()
        for source in registry["sources"]:
            source["enabled"] = False
        with tempfile.TemporaryDirectory() as directory:
            fetcher, resolver = Mock(), Mock()
            path = collectors().prepare_batch(registry, directory, fetcher, resolver)
            batch = json.loads(path.read_text())
            self.assertEqual(batch["registry"], registry)
            self.assertEqual(batch["snapshots"], [])
            fetcher.assert_not_called()
            resolver.assert_not_called()

    def test_dns_zero_address_withdrawal_can_complete(self):
        registry = registry_fixture()
        registry["sources"] = registry["sources"][2:]
        with tempfile.TemporaryDirectory() as directory:

            def resolver(host):
                return {"hostname": host, "addresses": [], "ttl": None, "state": "nxdomain"}

            path = collectors().prepare_batch(registry, directory, resolver=resolver)
            snapshot = json.loads(path.read_text())["snapshots"][0]
            self.assertEqual(snapshot["records"], [])
            self.assertEqual(snapshot["ipv6_skipped"], 0)

    def test_late_failure_keeps_earlier_raw_without_candidate(self):
        with tempfile.TemporaryDirectory() as directory:

            def failure(host):
                raise TimeoutError("offline")

            with self.assertRaises(TimeoutError):
                collectors().prepare_batch(registry_fixture(), directory, self.fetch, failure)
            self.assertEqual(len(list((Path(directory) / "raw").glob("*/*.bin"))), 2)
            self.assertEqual(list((Path(directory) / "candidates").glob("*.json")), [])

    def test_injected_dns_bundles_are_fully_validated(self):
        valid = self.answer("p-jp1.urban-vpn.com")
        malformed = [
            dict(valid, hostname="different.example"),
            dict(valid, addresses=["10.0.0.1"]),
            dict(valid, addresses=["2001:4860::8888"]),
            dict(valid, addresses=["8.8.8.0/24"]),
            dict(valid, ttl=-1),
            dict(valid, ttl=True),
            dict(valid, ttl=None),
            dict(valid, state="timeout"),
            dict(valid, state="nxdomain"),
            dict(valid, addresses=[]),
            dict(valid, extra="unreviewed"),
            {"hostname": valid["hostname"], "state": "no_a", "addresses": [], "ttl": 60},
        ]
        for answer in malformed:
            with self.subTest(answer=answer), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    collectors().prepare_batch(
                        registry_fixture(), directory, self.fetch, lambda host: answer
                    )
                self.assertEqual(list((Path(directory) / "candidates").glob("*.json")), [])

    def test_check_timestamps_cannot_move_backwards_across_hosts_or_at_completion(self):
        registry = registry_fixture()
        registry["sources"] = registry["sources"][2:]
        registry["sources"][0]["hosts"].append("p-jp2.urban-vpn.com")
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for offsets in [[0, 2, 1, 3, 4, 5], [0, 1, 2, 3, 4, 2]]:
            times = iter(base + timedelta(seconds=offset) for offset in offsets)
            with self.subTest(offsets=offsets), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    collectors().prepare_batch(
                        registry, directory, self.fetch, self.answer, clock=lambda: next(times)
                    )
                self.assertEqual(list((Path(directory) / "candidates").glob("*.json")), [])

    def test_injected_http_is_bounded_and_corrupt_archive_blocks_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "raw/x4b-vpn-v4" / (digest(b"8.8.8.8") + ".bin")
            raw.parent.mkdir(parents=True)
            raw.write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                self.prepare(directory)
            self.assertEqual(raw.read_bytes(), b"tampered")
            self.assertEqual(list((Path(directory) / "candidates").glob("*.json")), [])
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            collectors().prepare_batch(
                registry_fixture(), directory, lambda source: b"x" * 5000001, self.answer
            )


class CollectorCLITests(unittest.TestCase):
    def test_cli_calls_preparation_only_and_reports_prepared_path(self):
        from vpnlens import evidence_collect

        with tempfile.TemporaryDirectory() as directory:
            registry_path = Path(directory) / "registry.json"
            registry_path.write_text(json.dumps(registry_fixture()))
            candidate = Path(directory) / "candidates/test.json"
            output = io.StringIO()
            with patch.object(evidence_collect, "prepare_batch", return_value=candidate) as prepare:
                with patch("sys.stdout", output):
                    result = evidence_collect.main(
                        ["--registry", str(registry_path), "--out", directory]
                    )
            self.assertEqual(result, 0)
            self.assertEqual(
                json.loads(output.getvalue()), {"status": "prepared", "candidate": str(candidate)}
            )
            prepare.assert_called_once_with(registry_fixture(), Path(directory))

    def test_cli_errors_do_not_disclose_exception_or_credentials(self):
        from vpnlens import evidence_collect

        error = io.StringIO()
        with (
            patch("sys.stderr", error),
            patch.object(
                evidence_collect,
                "prepare_batch",
                side_effect=ValueError("https://user:secret@example.com"),
            ),
        ):
            result = evidence_collect.main([])
        self.assertEqual(result, 1)
        self.assertEqual(
            error.getvalue(), "Collection failed (ValueError); active data unchanged.\n"
        )


if __name__ == "__main__":
    unittest.main()


class CandidateValidationTests(unittest.TestCase):
    def candidate(self, folder):
        from vpnlens.evidence_collectors import prepare_batch

        registry = registry_fixture()
        # Use one deterministic text source; transport is never invoked.
        registry["sources"] = [next(s for s in registry["sources"] if s["adapter"] == "cidr_text")]
        at = datetime(2026, 11, 2, tzinfo=timezone.utc)
        return (
            prepare_batch(registry, folder, fetcher=lambda _: b"8.8.8.8\n", clock=lambda: at),
            registry,
            at,
        )

    def test_offline_candidate_revalidation_and_tampering(self):
        import vpnlens.evidence_collectors as collectors

        self.assertTrue(hasattr(collectors, "load_candidate"))
        with tempfile.TemporaryDirectory() as folder:
            path, registry, at = self.candidate(folder)
            original = json.loads(path.read_text())
            self.assertEqual(collectors.load_candidate(path, folder, registry, now=at), original)
            for mutation in (
                "records",
                "hash",
                "missing",
                "duplicate",
                "disabled",
                "path",
                "source",
            ):
                import copy

                value = copy.deepcopy(original)
                snapshot = value["snapshots"][0]
                if mutation == "records":
                    snapshot["records"][0]["network"] = "9.9.9.9/32"
                if mutation == "hash":
                    snapshot["content_sha256"] = "0" * 64
                if mutation == "missing":
                    value["snapshots"] = []
                if mutation == "duplicate":
                    value["snapshots"].append(snapshot)
                if mutation == "disabled":
                    value["registry"]["sources"][0]["enabled"] = False
                if mutation == "path":
                    snapshot["raw_ref"] = "../outside.bin"
                if mutation == "source":
                    snapshot["source"]["provider"] = "Other"
                path.write_bytes(canonical(value))
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    collectors.load_candidate(path, folder, registry, now=at)

    def test_raw_symlink_escape_and_bounded_read(self):
        import vpnlens.evidence_collectors as collectors

        self.assertTrue(hasattr(collectors, "load_candidate"))
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as outside:
            path, registry, at = self.candidate(folder)
            value = json.loads(path.read_text())
            raw = Path(folder) / value["snapshots"][0]["raw_ref"]
            external = Path(outside) / "payload"
            external.write_bytes(raw.read_bytes())
            raw.unlink()
            raw.symlink_to(external)
            with self.assertRaises(ValueError):
                collectors.load_candidate(path, folder, registry, now=at)
            raw.unlink()
            raw.write_bytes(b" " * (registry["sources"][0]["max_bytes"] + 1))
            with self.assertRaises(ValueError):
                collectors.load_candidate(path, folder, registry, now=at)

    def test_candidate_entry_types_are_rejected_and_dns_is_renormalized(self):
        import copy

        from vpnlens.evidence_collectors import load_candidate, prepare_batch

        with tempfile.TemporaryDirectory() as folder:
            path, registry, at = self.candidate(folder)
            original = json.loads(path.read_text())
            for key, value in (("batch_id", None), ("checked_at", None), ("schema_version", True)):
                item = copy.deepcopy(original)
                item[key] = value
                path.write_bytes(canonical(item))
                with self.subTest(key=key), self.assertRaises(Exception) as error:
                    load_candidate(path, folder, registry, now=at)
                self.assertIsInstance(error.exception, ValueError)
            registry["sources"] = [
                next(s for s in registry_fixture()["sources"] if s["adapter"] == "dns_a")
            ]

            def answer(host):
                return dict(hostname=host, addresses=["8.8.8.8"], ttl=60, state="answer")

            path = prepare_batch(registry, folder, resolver=answer, clock=lambda: at)
            self.assertEqual(
                len(load_candidate(path, folder, registry, now=at)["snapshots"][0]["records"]), 1
            )
            bundle = json.loads(path.read_text())
            raw = Path(folder) / bundle["snapshots"][0]["raw_ref"]
            content = json.loads(raw.read_text())
            content["answers"][0]["completed_at"] = stamp(at + timedelta(seconds=1))
            raw.write_bytes(canonical(content))
            bundle["snapshots"][0]["content_sha256"] = digest(raw.read_bytes())
            path.write_bytes(canonical(bundle))
            with self.assertRaises(ValueError):
                load_candidate(path, folder, registry, now=at)
