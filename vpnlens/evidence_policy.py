"""Pure public evidence projection. Country, ASN, and hosting never imply VPN use."""

import re
from copy import deepcopy
from datetime import datetime, timedelta

from vpnlens.evidence_collectors import _https_url
from vpnlens.evidence_contract import instant, public_network, stamp

PUBLIC_KEYS = frozenset(
    "source_id family record_key network provider basis role method service_category source_url content_sha256 fetched_at checked_at observed_at expires_at review_state hostname connection_type_claim".split()
)
_HASH = re.compile(r"[0-9a-f]{64}")
_METHODS = {
    "provider_list": {"host_text", "vpngate_csv"},
    "provider_dns": {"dns_a"},
    "network_inference": {"cidr_text"},
    "exit_observation": {"system_tunnel", "explicit_http_proxy", "browser_import"},
}


def _time(value):
    return instant(stamp(value)) if isinstance(value, datetime) else instant(value)


def public_record(record, now):
    """Return an allowlisted normalized record, or None for invalid/unreviewed input."""
    try:
        now = _time(now)
        result = {key: deepcopy(record.get(key)) for key in PUBLIC_KEYS}
        basis = result["basis"]
        if basis not in _METHODS or result["method"] not in _METHODS[basis]:
            return None
        if result["role"] not in ("server", "exit", "unknown"):
            return None
        if any(
            not isinstance(result[key], str) or not result[key].strip()
            for key in ("source_id", "family")
        ):
            return None
        if any(
            not isinstance(result[key], str) or not _HASH.fullmatch(result[key])
            for key in ("record_key", "content_sha256")
        ):
            return None
        if result["provider"] is not None and (
            not isinstance(result["provider"], str) or not result["provider"].strip()
        ):
            return None
        result["network"] = public_network(result["network"])
        _https_url(result["source_url"])
        observation = basis == "exit_observation"
        if observation:
            if (
                result["review_state"] != "approved"
                or result["role"] != "exit"
                or result["service_category"] not in ("vpn", "proxy")
                or not result["provider"]
            ):
                return None
            if result["connection_type_claim"] not in (
                "residential",
                "mobile",
                "datacenter",
                "unknown",
            ):
                return None
            observed = _time(result["observed_at"])
            expiry = _time(result["expires_at"])
            if expiry != observed + timedelta(hours=24):
                return None
            result.update(
                observed_at=stamp(observed),
                fetched_at=stamp(observed),
                checked_at=stamp(observed),
                expires_at=stamp(expiry),
                operator_attested=True,
            )
            stale = observed > now or now >= expiry
        else:
            if result["service_category"] != "vpn" or result["review_state"] is not None:
                return None
            checked, fetched, expiry = (
                _time(result[key]) for key in ("checked_at", "fetched_at", "expires_at")
            )
            if fetched > checked or expiry != checked + timedelta(hours=48):
                return None
            result.update(
                checked_at=stamp(checked), fetched_at=stamp(fetched), expires_at=stamp(expiry)
            )
            stale = checked > now or now - checked > timedelta(hours=48)
        if result["method"] != "cidr_text" and not result["network"].endswith("/32"):
            return None
        result["stale"] = stale
        return result
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return None


def apply_policy(legacy, matches, source_counts, now):
    """Extend a deep copy of legacy security without scoring correlated records."""
    result = deepcopy(legacy)
    additional = []
    proxy, weak = False, False
    for raw in matches:
        item = public_record(raw, now)
        if item is None:
            continue
        direct = item["basis"] in ("provider_list", "provider_dns", "exit_observation")
        if direct and item["service_category"] == "vpn":
            result["evidence"].append(dict(item, indicator_type="vpn_server"))
            if not item["stale"]:
                result["vpn_status"] = "listed"
        else:
            additional.append(item)
            if not item["stale"]:
                weak |= item["basis"] == "network_inference"
                proxy |= item["basis"] == "exit_observation" and item["service_category"] == "proxy"
    result.update(
        vpn_assessment="direct_association"
        if result["vpn_status"] == "listed"
        else "network_only"
        if weak
        else "unknown",
        proxy_status="listed" if proxy else "unknown",
        residential_proxy_status="unknown",
        residential_proxy_reason="No qualifying residential-relay evidence has been collected",
        additional_evidence=additional,
    )
    result["active_source_count"] += source_counts.get("active", 0)
    result["recently_checked_source_count"] += source_counts.get("recent", 0)
    return result
