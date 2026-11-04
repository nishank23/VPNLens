"""Pure, versioned demo access policy over the existing normalized evidence."""

from datetime import datetime, timedelta

from .evidence_contract import instant


def _time(value):
    return instant(value.isoformat() if isinstance(value, datetime) else value)


def _fresh(record, now):
    """Require an attributable fresh record without renewing observation expiry."""
    if record.get("stale") is not False:
        return False
    try:
        if record.get("basis") == "exit_observation":
            observed, expires = (
                _time(record["observed_at"]),
                _time(record["expires_at"]),
            )
            return (
                record.get("review_state") == "approved"
                and record.get("role") == "exit"
                and expires == observed + timedelta(hours=24)
                and observed <= now < expires
            )
        checked = _time(record["checked_at"])
        return checked <= now and now - checked <= timedelta(hours=48)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return False


def decide_access(security, expected_source_ids, recently_checked_source_ids, now):
    """Project listed statuses only; country, ASN and weak inference never block."""
    ready = set(expected_source_ids) <= set(recently_checked_source_ids)
    evidence = security.get("evidence", [])
    reasons = []
    for kind, indicator in (("vpn", "vpn_server"), ("tor", "tor_exit")):
        if security.get(kind + "_status") == "listed" and any(
            item.get("indicator_type") == indicator and _fresh(item, now) for item in evidence
        ):
            reasons.append(f"recent_{kind}_evidence")
    if security.get("proxy_status") == "listed" and any(
        item.get("basis") == "exit_observation"
        and item.get("service_category") == "proxy"
        and _fresh(item, now)
        for item in security.get("additional_evidence", []) or []
    ):
        reasons.append("recent_proxy_evidence")
    return {
        "policy_id": "streaming-access-v1",
        "action": "block" if reasons else "allow",
        "reason_codes": reasons
        or ["no_recent_blocking_evidence" if ready else "insufficient_recent_evidence"],
        "scheduled_source_health": "ready" if ready else "degraded",
        "evaluated_at": now,
    }
