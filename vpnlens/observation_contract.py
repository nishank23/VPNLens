"""Validate operator-attested, locally recorded exit observations.

Profile labels and connection claims are reviewed metadata, not echo-service proof.
"""

import json
import re
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from urllib.parse import urlsplit
from uuid import UUID

from vpnlens.evidence_contract import canonical, digest, instant, public_network, stamp

ECHO = "https://api.ipify.org?format=json"
TRANSPORTS = frozenset({"system_tunnel", "explicit_http_proxy", "browser_import"})


def identifier(value):
    """Require canonical UUID spelling so identifiers cannot become paths."""
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Expected a canonical UUID")
    return value


def text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected nonempty text")
    return value


def profile_contract(profile):
    """Return only normalized public profile metadata, excluding secret references' values."""
    if not isinstance(profile, dict):
        raise ValueError("Expected a profile object")
    profile_id = profile.get("profile_id")
    if not isinstance(profile_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,99}", profile_id):
        raise ValueError("Invalid profile ID")
    provider = text(profile.get("provider"))
    category = profile.get("service_category")
    transport = profile.get("transport")
    if category not in ("vpn", "proxy") or transport not in TRANSPORTS:
        raise ValueError("Invalid service category or transport")
    url = text(profile.get("documentation_url"))
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "?" in url
        or "#" in url
        or "\\" in url
        or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url)
    ):
        raise ValueError("Expected a credential-free HTTPS documentation URL")
    try:
        parsed.port
    except ValueError:
        raise ValueError("Invalid documentation URL") from None
    proxy_env = profile.get("proxy_env")
    if transport == "explicit_http_proxy":
        if not isinstance(proxy_env, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]+", proxy_env):
            raise ValueError("Expected uppercase proxy environment variable name")
    elif proxy_env is not None:
        raise ValueError("Proxy reference only belongs to explicit proxy profiles")
    claim = profile.get("connection_type_claim", "unknown")
    if claim not in ("residential", "mobile", "datacenter", "unknown"):
        raise ValueError("Invalid connection type claim")
    return {
        "profile_id": profile_id,
        "provider": provider,
        "service_category": category,
        "transport": transport,
        "documentation_url": url,
        "proxy_env": proxy_env,
        "connection_type_claim": claim,
    }


def strict_json(body):
    """Reject duplicate keys and non-standard NaN/Infinity JSON constants."""

    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate JSON key")
            value[key] = item
        return value

    def reject(_):
        raise ValueError("Non-standard JSON constant")

    return json.loads(body, object_pairs_hook=pairs, parse_constant=reject)


def public_host(value):
    if not isinstance(value, str) or "/" in value:
        raise ValueError("Expected a canonical public IPv4 host")
    address = ip_address(value)
    if address.version != 4 or str(address) != value:
        raise ValueError("Expected a canonical public IPv4 host")
    public_network(value)
    return value


def utc_now(now):
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("Expected an aware current time")
    return now.astimezone(UTC)


def receipt_contract(receipt, now):
    """Validate raw echo response and its original timing, returning observed time."""
    now = utc_now(now)
    if not isinstance(receipt, dict):
        raise ValueError("Expected a receipt object")
    identifier(receipt.get("receipt_id"))
    ip = public_host(receipt.get("ip"))
    if receipt.get("endpoint") != ECHO:
        raise ValueError("Unexpected echo endpoint")
    body = receipt.get("response_body")
    if not isinstance(body, str):
        raise ValueError("Expected a UTF-8 response body")
    encoded = body.encode("utf-8")
    if len(encoded) > 4096 or digest(encoded) != receipt.get("response_sha256"):
        raise ValueError("Invalid response size or digest")
    decoded = strict_json(body)
    if not isinstance(decoded, dict) or public_host(decoded.get("ip")) != ip:
        raise ValueError("Echo response and receipt IP disagree")
    started, observed = instant(receipt["started_at"]), instant(receipt["observed_at"])
    if not started <= observed <= now:
        raise ValueError("Invalid receipt timing")
    return observed


def baseline_contract(baseline, profile, now):
    """Check the disconnected baseline, including optional historical identity fields."""
    profile = profile_contract(profile)
    if not isinstance(baseline, dict):
        raise ValueError("Expected a baseline object")
    if baseline.get("profile_sha256") != digest(canonical(profile)):
        raise ValueError("Baseline profile changed")
    if baseline.get("operator_attested_disconnected") is not True:
        raise ValueError("Disconnected baseline attestation required")
    # Older browser exports may omit these fields; present fields must never contradict.
    for key, expected in (("profile_id", profile["profile_id"]), ("kind", "baseline")):
        if key in baseline and baseline[key] != expected:
            raise ValueError("Baseline identity mismatch")
    if "schema_version" in baseline and (
        type(baseline["schema_version"]) is not int or baseline["schema_version"] != 1
    ):
        raise ValueError("Invalid baseline schema")
    if "baseline_id" in baseline:
        identifier(baseline["baseline_id"])
    return receipt_contract(baseline["receipt"], now)


def validate_observation(record, profile, now):
    """Validate a fresh immutable measurement and derive its evidence attributes."""
    now = utc_now(now)
    profile = profile_contract(profile)
    if not isinstance(record, dict):
        raise ValueError("Expected an observation object")
    if type(record.get("schema_version")) is not int or record["schema_version"] != 1:
        raise ValueError("Unsupported observation schema")
    if record.get("kind") != "exit_observation":
        raise ValueError("Unexpected observation kind")
    identifier(record.get("observation_id"))
    if (
        record.get("profile_id") != profile["profile_id"]
        or record.get("profile_sha256") != digest(canonical(profile))
        or record.get("method") != profile["transport"]
    ):
        raise ValueError("Observation profile binding changed")
    if (
        record.get("review_state") != "pending"
        or record.get("operator_attested_active") is not True
    ):
        raise ValueError("Expected an attested pending measurement")
    before = baseline_contract(record["baseline"], profile, now)
    receipts = record.get("active_receipts")
    if not isinstance(receipts, list) or len(receipts) != 2:
        raise ValueError("Exactly two active receipts required")
    first, last = (receipt_contract(item, now) for item in receipts)
    if receipts[0]["receipt_id"] == receipts[1]["receipt_id"]:
        raise ValueError("Distinct active receipts required")
    if not before <= first <= last or last - before > timedelta(minutes=15):
        raise ValueError("Measurement outside the 15 minute baseline window")
    ip = receipts[0]["ip"]
    if ip != receipts[1]["ip"] or ip == record["baseline"]["receipt"]["ip"]:
        raise ValueError("Active IP must agree and differ from baseline")
    expiry = last + timedelta(hours=24)
    if now >= expiry:
        raise ValueError("Observation expired")
    return {
        "ip": ip,
        "observed_at": stamp(last),
        "expires_at": stamp(expiry),
        "provider": profile["provider"],
        "service_category": profile["service_category"],
        "method": profile["transport"],
        "operator_attested": True,
        "connection_type_claim": profile["connection_type_claim"],
    }
