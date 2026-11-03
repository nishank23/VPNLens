"""Bounded public VPN evidence collection; preparation never activates data."""

import copy
import csv
import io
import re
from datetime import UTC, datetime
from ipaddress import ip_address, ip_network
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
from uuid import uuid4

import dns.resolver

from vpnlens.evidence_contract import canonical, digest, instant, public_network, stamp, write_once

_ADAPTERS = {
    "host_text": ("provider_list", 5_000_000),
    "cidr_text": ("network_inference", 5_000_000),
    "vpngate_csv": ("provider_list", 25_000_000),
    "dns_a": ("provider_dns", 5_000_000),
}
_SOURCE_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,99}", re.ASCII)
_HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.ASCII)
_MAX_HOSTS = 100


def _https_url(value):
    """Reject credentials and incomplete HTTPS URLs without echoing their values."""
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        raise ValueError("Expected a credential-free HTTPS URL")
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
        )
        parsed.port  # Force validation of malformed or out-of-range ports.
    except ValueError:
        raise ValueError("Expected a credential-free HTTPS URL") from None
    if not valid or "\\" in value or any(ord(c) < 32 for c in value):
        raise ValueError("Expected a credential-free HTTPS URL")


def _content_length(headers, max_bytes):
    length = headers.get("Content-Length")
    if length is None:
        return None
    if not isinstance(length, str) or not re.fullmatch(r"[0-9]+", length):
        raise ValueError("Invalid response content length")
    length = int(length)
    if length > max_bytes:
        raise ValueError("Response exceeds reviewed byte cap")
    return length


class _HTTPSOnlyRedirectHandler(HTTPRedirectHandler):
    """Validate redirect targets and discard bodies without urllib's unbounded drain."""

    def __init__(self, max_bytes):
        super().__init__()
        self.max_bytes = max_bytes

    def http_error_302(self, request, response, code, message, headers):
        try:
            _content_length(headers, self.max_bytes)
        finally:
            response.close()
        # urllib drains its supplied redirect body before following. Supply an
        # empty body after closing the actual response so it never reads that body.
        with io.BytesIO() as empty_body:
            return super().http_error_302(request, empty_body, code, message, headers)

    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302
    http_error_308 = http_error_302

    def redirect_request(self, request, response, code, message, headers, new_url):
        try:
            _https_url(new_url)
        except ValueError:
            response.close()
            raise
        return super().redirect_request(request, response, code, message, headers, new_url)


def _hostname(value):
    if not isinstance(value, str) or len(value) > 253 or not value:
        raise ValueError("Expected a bounded DNS hostname")
    labels = value.lower().split(".")
    if len(labels) < 2 or not all(_HOST_LABEL.fullmatch(label) for label in labels):
        raise ValueError("Expected a DNS hostname")
    try:
        ip_address(value)
    except ValueError:
        return
    raise ValueError("Expected a DNS hostname, not an address")


def registry_entries(registry):
    """Validate the reviewed schema and return independent copies, including disabled sources."""
    if (
        not isinstance(registry, dict)
        or type(registry.get("schema_version")) is not int
        or registry["schema_version"] != 1
        or not isinstance(registry.get("sources"), list)
    ):
        raise ValueError("Unsupported evidence registry")
    sources = []
    identifiers = set()
    for source in registry["sources"]:
        if not isinstance(source, dict):
            raise ValueError("Expected a source object")
        identifier = source.get("source_id")
        if (
            not isinstance(identifier, str)
            or not _SOURCE_ID.fullmatch(identifier)
            or identifier in identifiers
        ):
            raise ValueError("Invalid or duplicate source identifier")
        identifiers.add(identifier)
        if type(source.get("enabled")) is not bool:
            raise ValueError("Expected boolean source enablement")
        adapter = source.get("adapter")
        if not isinstance(adapter, str) or adapter not in _ADAPTERS:
            raise ValueError("Unreviewed source adapter")
        basis, max_bytes = _ADAPTERS[adapter]
        if source.get("basis") != basis or source.get("role") not in ("server", "exit", "unknown"):
            raise ValueError("Invalid source basis or role")
        if not isinstance(source.get("family"), str) or not source["family"].strip():
            raise ValueError("Expected a nonempty source family")
        if "provider" not in source or (
            source["provider"] is not None
            and (not isinstance(source["provider"], str) or not source["provider"].strip())
        ):
            raise ValueError("Expected a provider name or null")
        for key in ("url", "attribution_url"):
            _https_url(source.get(key))
        if (
            type(source.get("max_bytes")) is not int
            or source["max_bytes"] != max_bytes
            or type(source.get("max_age_hours")) is not int
            or source["max_age_hours"] != 48
        ):
            raise ValueError("Unreviewed collection bounds")
        if adapter == "dns_a":
            hosts = source.get("hosts")
            if not isinstance(hosts, list) or not 1 <= len(hosts) <= _MAX_HOSTS:
                raise ValueError("Expected bounded reviewed DNS hosts")
            for host in hosts:
                _hostname(host)
            if len({host.lower() for host in hosts}) != len(hosts):
                raise ValueError("Duplicate reviewed DNS host")
        sources.append(copy.deepcopy(source))
    return sources


def indicator(source, address, hostname=None, metadata=None):
    """Build stable evidence identity; metadata and check timestamps are not identity."""
    identity = {
        "network": public_network(address),
        "provider": source["provider"],
        "basis": source["basis"],
        "role": source["role"],
        "hostname": hostname,
        "service_category": "vpn",
        "method": source["adapter"],
    }
    return dict(identity, record_key=digest(canonical(identity)), metadata=metadata or {})


def _parsed(records, skipped):
    if not records:
        raise ValueError("Source contains no public IPv4 evidence")
    return sorted(records.values(), key=lambda record: record["record_key"]), skipped


def parse_text(payload, source):
    """Strict text parsing retains CIDRs as one record and counts valid IPv6 lines."""
    if source["adapter"] not in ("host_text", "cidr_text"):
        raise ValueError("Unsupported text adapter")
    records, skipped = {}, 0
    for line in payload.decode("utf-8-sig").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        network = ip_network(value, strict=True)
        if network.version == 6:
            skipped += 1
            continue
        if source["adapter"] == "host_text" and network.prefixlen != network.max_prefixlen:
            raise ValueError("Host source contains a network range")
        record = indicator(source, value)
        records[record["record_key"]] = record
    return _parsed(records, skipped)


def parse_vpngate(payload, source):
    """Read endpoint identity only; VPN configuration columns remain inert text."""
    # Cap CSV fields as well as the transport body; never decode configuration data.
    previous_limit = csv.field_size_limit(source["max_bytes"])
    try:
        lines = [
            line
            for line in payload.decode("utf-8-sig").splitlines()
            if line.strip() and not line.lstrip().startswith("*")
        ]
        reader = csv.DictReader(io.StringIO("\n".join(lines)), strict=True)
        if (
            not reader.fieldnames
            or len(set(reader.fieldnames)) != len(reader.fieldnames)
            or not {"IP", "#HostName"}.issubset(reader.fieldnames)
        ):
            raise ValueError("VPN Gate headers are missing or duplicated")
        records, skipped = {}, 0
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Malformed VPN Gate row")
            hostname, value = row["#HostName"].strip(), row["IP"].strip()
            if not hostname or "/" in value:
                raise ValueError("VPN Gate row requires a host and address")
            address = ip_address(value)
            if address.version == 6:
                skipped += 1
                continue
            record = indicator(source, value, hostname=hostname)
            records[record["record_key"]] = record
        return _parsed(records, skipped)
    except csv.Error:
        raise ValueError("Malformed VPN Gate CSV") from None
    finally:
        csv.field_size_limit(previous_limit)


def fetch_payload(source, opener=urlopen):
    """Read at most the reviewed cap plus one byte and reject incomplete responses."""
    _https_url(source["url"])
    request = Request(source["url"], headers={"User-Agent": "VPNLens-portfolio/1.0"})
    if opener is urlopen:
        opener = build_opener(_HTTPSOnlyRedirectHandler(source["max_bytes"])).open
    with opener(request, timeout=30) as response:
        if response.status != 200:
            raise ValueError("Evidence request did not return HTTP 200")
        _https_url(response.geturl())
        max_bytes = source["max_bytes"]
        length = _content_length(response.headers, max_bytes)
        payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes or (length is not None and len(payload) != length):
            raise ValueError("Oversized or incomplete evidence response")
    return payload


def _validated_answer(answer, hostname):
    """Validate even injected resolver results before they become archived evidence."""
    if (
        not isinstance(answer, dict)
        or set(answer) != {"hostname", "addresses", "ttl", "state"}
        or answer["hostname"] != hostname
        or not isinstance(answer["addresses"], list)
    ):
        raise ValueError("Invalid DNS answer bundle")
    addresses = answer["addresses"]
    if answer["state"] in ("nxdomain", "no_a"):
        if addresses or answer["ttl"] is not None:
            raise ValueError("Invalid DNS withdrawal bundle")
    elif answer["state"] == "answer":
        if not addresses or type(answer["ttl"]) is not int or not 0 <= answer["ttl"] <= 4294967295:
            raise ValueError("Invalid DNS answer TTL or address set")
        for address in addresses:
            if not isinstance(address, str) or "/" in address:
                raise ValueError("Expected an IPv4 A answer")
            public_network(address)
        if len(addresses) != len(set(addresses)) or addresses != sorted(addresses):
            raise ValueError("DNS answer addresses must be sorted and unique")
    else:
        raise ValueError("Unsuccessful DNS resolution")
    return copy.deepcopy(answer)


def resolve_a(hostname, resolver=None):
    """Query only A records; NXDOMAIN/no-A withdraw evidence, transport failures raise."""
    _hostname(hostname)
    resolver = dns.resolver.Resolver() if resolver is None else resolver
    try:
        answer = resolver.resolve(
            hostname + ".", "A", search=False, lifetime=5.0, raise_on_no_answer=False
        )
    except dns.resolver.NXDOMAIN:
        return {"hostname": hostname, "addresses": [], "ttl": None, "state": "nxdomain"}
    if answer.rrset is None:
        return {"hostname": hostname, "addresses": [], "ttl": None, "state": "no_a"}
    result = {
        "hostname": hostname,
        "addresses": sorted({item.address for item in answer}),
        "ttl": answer.rrset.ttl,
        "state": "answer",
    }
    return _validated_answer(result, hostname)


def prepare_batch(registry, folder, fetcher=fetch_payload, resolver=resolve_a, clock=None):
    """Archive all enabled sources and publish one immutable candidate only on full success."""
    sources = registry_entries(registry)
    frozen_registry = copy.deepcopy(registry)
    clock = (lambda: datetime.now(UTC)) if clock is None else clock
    folder = Path(folder)
    snapshots = []
    previous_check = None

    def checked_stamp():
        nonlocal previous_check
        checked = stamp(clock())
        current = instant(checked)
        if previous_check is not None and current < previous_check:
            raise ValueError("Evidence check clock moved backwards")
        previous_check = current
        return checked

    for source in sources:
        if not source["enabled"]:
            continue
        if source["adapter"] == "dns_a":
            answers = []
            for hostname in source["hosts"]:
                queried_at = checked_stamp()
                answer = _validated_answer(resolver(hostname), hostname)
                completed_at = checked_stamp()
                answers.append(dict(answer, queried_at=queried_at, completed_at=completed_at))
            checked_at = checked_stamp()
            payload = canonical({"checked_at": checked_at, "family": "A", "answers": answers})
            records = [
                indicator(source, address, answer["hostname"], {"ttl": answer["ttl"]})
                for answer in answers
                for address in answer["addresses"]
            ]
            records.sort(key=lambda record: record["record_key"])
            skipped = 0
        else:
            payload = fetcher(source)
            checked_at = checked_stamp()
            if not isinstance(payload, bytes) or len(payload) > source["max_bytes"]:
                raise ValueError("Invalid or oversized evidence payload")
            parser = parse_vpngate if source["adapter"] == "vpngate_csv" else parse_text
            records, skipped = parser(payload, source)
        if len(payload) > source["max_bytes"]:
            raise ValueError("Evidence payload exceeds reviewed byte cap")
        content_sha256 = digest(payload)
        raw_ref = Path("raw") / source["source_id"] / (content_sha256 + ".bin")
        write_once(folder / raw_ref, payload)
        snapshots.append(
            {
                "source": source,
                "content_sha256": content_sha256,
                "fetched_at": checked_at,
                "checked_at": checked_at,
                "publisher_at": None,
                "raw_ref": raw_ref.as_posix(),
                "records": records,
                "ipv6_skipped": skipped,
            }
        )
    batch_id = str(uuid4())
    batch = {
        "schema_version": 1,
        "batch_id": batch_id,
        "checked_at": checked_stamp(),
        "registry_sha256": digest(canonical(frozen_registry)),
        "registry": frozen_registry,
        "snapshots": snapshots,
    }
    candidate = folder / "candidates" / (batch_id + ".json")
    write_once(candidate, canonical(batch))
    return candidate


CANDIDATE_MAX_BYTES = 128 * 1024 * 1024


def _bounded_file(path, limit):
    with Path(path).open("rb") as stream:
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("Evidence artifact exceeds byte cap")
    return payload


def load_candidate(candidate_path, archive_root, registry, *, now=None):
    """Read and re-normalize a completed candidate offline against the reviewed registry.

    Paths are resolved under archive_root, including symlinks. No transports or DB are used.
    """
    from uuid import UUID

    from vpnlens.observation_contract import strict_json

    now = datetime.now(UTC) if now is None else instant(stamp(now))
    sources = registry_entries(registry)
    expected = {source["source_id"]: source for source in sources if source["enabled"]}
    if len(sources) > 1000:
        raise ValueError("Evidence registry exceeds source cap")
    root = Path(archive_root).resolve(strict=True)
    candidate = strict_json(_bounded_file(candidate_path, CANDIDATE_MAX_BYTES).decode("utf-8"))
    if not isinstance(candidate, dict) or set(candidate) != {
        "schema_version",
        "batch_id",
        "checked_at",
        "registry_sha256",
        "registry",
        "snapshots",
    }:
        raise ValueError("Invalid candidate envelope")
    if (
        type(candidate["schema_version"]) is not int
        or candidate["schema_version"] != 1
        or not isinstance(candidate["batch_id"], str)
        or str(UUID(candidate["batch_id"])) != candidate["batch_id"]
    ):
        raise ValueError("Invalid candidate identity")
    if canonical(candidate["registry"]) != canonical(registry) or candidate[
        "registry_sha256"
    ] != digest(canonical(registry)):
        raise ValueError("Candidate registry differs from reviewed registry")

    def timestamp(value):
        if not isinstance(value, str):
            raise ValueError("Expected candidate timestamp")
        parsed = instant(value)
        if datetime.fromisoformat(value).utcoffset().total_seconds() != 0 or parsed > now:
            raise ValueError("Invalid candidate timestamp")
        return parsed

    batch_checked = timestamp(candidate["checked_at"])
    snapshots = candidate["snapshots"]
    if not isinstance(snapshots, list) or len(snapshots) != len(expected):
        raise ValueError("Incomplete enabled source batch")
    seen = set()
    for snapshot in snapshots:
        if not isinstance(snapshot, dict) or set(snapshot) != {
            "source",
            "content_sha256",
            "fetched_at",
            "checked_at",
            "publisher_at",
            "raw_ref",
            "records",
            "ipv6_skipped",
        }:
            raise ValueError("Invalid candidate snapshot")
        source = snapshot["source"]
        if not isinstance(source, dict):
            raise ValueError("Invalid candidate source")
        identifier = source.get("source_id")
        if (
            not isinstance(identifier, str)
            or identifier not in expected
            or identifier in seen
            or canonical(source) != canonical(expected[identifier])
        ):
            raise ValueError("Snapshot not bound to enabled registry")
        seen.add(identifier)
        checked, fetched = timestamp(snapshot["checked_at"]), timestamp(snapshot["fetched_at"])
        if not fetched <= checked <= batch_checked:
            raise ValueError("Invalid source check ordering")
        if snapshot["publisher_at"] is not None and timestamp(snapshot["publisher_at"]) > fetched:
            raise ValueError("Invalid publisher timestamp")
        reference = snapshot["raw_ref"]
        if (
            not isinstance(reference, str)
            or "\\" in reference
            or Path(reference).is_absolute()
            or ".." in Path(reference).parts
        ):
            raise ValueError("Invalid archive reference")
        raw_path = (root / reference).resolve(strict=True)
        if (
            not raw_path.is_relative_to(root)
            or not raw_path.is_file()
            or not Path(reference).parts
            or Path(reference).parts[0] != "raw"
        ):
            raise ValueError("Archive path escapes expected root")
        raw = _bounded_file(raw_path, source["max_bytes"])
        if snapshot["content_sha256"] != digest(raw):
            raise ValueError("Archived content hash differs")
        if source["adapter"] == "dns_a":
            bundle = strict_json(raw.decode("utf-8"))
            if (
                not isinstance(bundle, dict)
                or set(bundle) != {"checked_at", "family", "answers"}
                or bundle["family"] != "A"
                or bundle["checked_at"] != snapshot["checked_at"]
                or not isinstance(bundle["answers"], list)
                or len(bundle["answers"]) != len(source["hosts"])
            ):
                raise ValueError("Invalid dated DNS bundle")
            records, previous = [], None
            for answer, hostname in zip(bundle["answers"], source["hosts"], strict=True):
                if not isinstance(answer, dict) or set(answer) != {
                    "hostname",
                    "addresses",
                    "ttl",
                    "state",
                    "queried_at",
                    "completed_at",
                }:
                    raise ValueError("Invalid dated DNS answer")
                queried, completed = (
                    timestamp(answer["queried_at"]),
                    timestamp(answer["completed_at"]),
                )
                if not queried <= completed <= checked or (
                    previous is not None and queried < previous
                ):
                    raise ValueError("Invalid DNS query ordering")
                previous = completed
                result = _validated_answer(
                    {key: answer[key] for key in ("hostname", "addresses", "ttl", "state")},
                    hostname,
                )
                records.extend(
                    indicator(source, address, hostname, {"ttl": result["ttl"]})
                    for address in result["addresses"]
                )
            records.sort(key=lambda value: value["record_key"])
            skipped = 0
        else:
            parser = parse_vpngate if source["adapter"] == "vpngate_csv" else parse_text
            records, skipped = parser(raw, source)
        if (
            type(snapshot["ipv6_skipped"]) is not int
            or snapshot["ipv6_skipped"] != skipped
            or not isinstance(snapshot["records"], list)
            or canonical(snapshot["records"]) != canonical(records)
        ):
            raise ValueError("Candidate records differ from archived source normalization")
    return candidate
