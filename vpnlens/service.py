"""HTTP-facing source selection around the user-reviewed lookup statement."""

from datetime import timedelta
from ipaddress import IPv4Address

from ingestion.ip_evidence import lookup_evidence

from .config import ROOT
from .database import SnapshotNotFound, SourcesUnavailable
from .evidence_contract import instant
from .evidence_policy import apply_policy
from .evidence_store import EvidenceStore
from .refresh import read_state

LOOKUP_SQL = (ROOT / "sql/ip_lookup.sql").read_text()


def select_snapshot(connection, table, requested=None):
    if table not in ("asn_prefix_origins", "raw_asn_mappings"):
        raise ValueError("Unsupported snapshot table")
    where = "WHERE source_file=%s" if requested is not None else ""
    row = connection.execute(
        f"SELECT source_file,snapshot_at FROM {table} {where} "
        "ORDER BY snapshot_at DESC,source_file DESC LIMIT 1",
        (requested,) if requested is not None else (),
    ).fetchone()
    if row is None:
        if requested is not None:
            raise SnapshotNotFound("Requested snapshot is not loaded")
        raise SourcesUnavailable("Required lookup snapshot is not loaded")
    return row


def extended_sources(connection, now):
    """Project only committed enabled scheduled sources against one transaction clock."""
    payload = EvidenceStore(connection).run("sources", {})
    enabled = set(payload["enabled_source_ids"])
    sources = [dict(source) for source in payload["sources"] if source["source_id"] in enabled]
    for source in sources:
        checked = instant(source["checked_at"])
        source["stale"] = checked > now or now - checked > timedelta(hours=48)
    return sources, sorted(enabled)


def enrich_security(connection, ip, legacy):
    """Read local committed evidence once; never contact an upstream source."""
    now = connection.execute("SELECT CURRENT_TIMESTAMP AS now").fetchone()["now"]
    sources, enabled = extended_sources(connection, now)
    matches = EvidenceStore(connection).run("lookup", {"ip_address": ip})["matches"]
    matches = [
        item
        for item in matches
        if item.get("basis") == "exit_observation" or item.get("source_id") in enabled
    ]
    return apply_policy(
        legacy,
        matches,
        {"active": len(sources), "recent": sum(not source["stale"] for source in sources)},
        now,
    )


def lookup(connection, address, source_file=None, org_source_file=None, *, extended_enabled=False):
    ip = str(IPv4Address(address))
    routing = select_snapshot(connection, "asn_prefix_origins", source_file)
    organization = select_snapshot(connection, "raw_asn_mappings", org_source_file)
    rows = connection.execute(
        LOOKUP_SQL,
        dict(
            ip_address=ip,
            source_file=routing["source_file"],
            org_source_file=organization["source_file"],
        ),
    ).fetchall()
    security = lookup_evidence(connection, ip)
    if extended_enabled:
        security = enrich_security(connection, ip, security)
    for row in rows:
        row["security"] = security
    rows.sort(key=lambda row: (str(row["prefix"] or ""), row["origin_group"] or ""))
    return {
        "ip": ip,
        "selected_sources": {"routing": routing, "organization": organization},
        "results": rows,
    }


def source_status(connection, *, extended_enabled=False):
    routing = connection.execute(
        "SELECT source_file,MAX(snapshot_at) AS snapshot_at "
        "FROM asn_prefix_origins GROUP BY source_file ORDER BY snapshot_at DESC,source_file DESC"
    ).fetchall()
    organization = connection.execute(
        "SELECT source_file,MAX(snapshot_at) AS snapshot_at "
        "FROM raw_asn_mappings GROUP BY source_file ORDER BY snapshot_at DESC,source_file DESC"
    ).fetchall()
    geo = connection.execute("SELECT EXISTS(SELECT 1 FROM ip2location) AS available").fetchone()[
        "available"
    ]
    evidence = connection.execute("""SELECT source_id,indicator_type,provider,source_url,
        checked_at,fetched_at,ipv4_count,ipv6_skipped,
        checked_at < CURRENT_TIMESTAMP - INTERVAL '48 hours' AS stale
        FROM ip_evidence_snapshots WHERE active ORDER BY source_id""").fetchall()
    result = {
        "geolocation": {"available": geo, "snapshot_at": None},
        "routing": routing,
        "organization": organization,
        "security": evidence,
        "security_stale_after_hours": 48,
        "refresh": read_state(connection),
    }

    if extended_enabled:
        now = connection.execute("SELECT CURRENT_TIMESTAMP AS now").fetchone()["now"]
        extended, enabled = extended_sources(connection, now)
        result["security"].extend(extended)
        result["security_expected_source_ids"] = enabled
    return result
