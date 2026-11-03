"""Download public host-IP feeds and publish validated evidence snapshots."""

import hashlib
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from ipaddress import ip_address
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)
VPN_BASE = "https://raw.githubusercontent.com/Joe12387/open-source-vpn-ip-lists/master/"


@dataclass(frozen=True)
class Feed:
    source_id: str
    indicator_type: str
    provider: str | None
    url: str


FEEDS = tuple(
    Feed("vpn-" + key, "vpn_server", name, VPN_BASE + key + ".txt")
    for key, name in (
        ("airvpn", "AirVPN"),
        ("ivpn", "IVPN"),
        ("mullvad", "Mullvad"),
        ("nordvpn", "NordVPN"),
        ("ovpn", "OVPN.com"),
        ("pia", "Private Internet Access"),
        ("protonvpn", "ProtonVPN"),
        ("riseupvpn", "RiseupVPN"),
        ("surfshark", "Surfshark"),
        ("windscribe", "Windscribe"),
    )
) + (Feed("tor-project", "tor_exit", None, "https://check.torproject.org/torbulkexitlist"),)


def download(url):
    request = Request(url, headers={"User-Agent": "VPNLens-portfolio/1.0"})
    with urlopen(request, timeout=30) as response:
        expected = response.headers.get("Content-Length")
        if expected is not None and int(expected) > 5_000_000:
            raise ValueError("Feed exceeds 5 MB download limit")
        payload = response.read(5_000_001)
        if expected is not None and len(payload) != int(expected):
            raise ValueError("Incomplete download: Content-Length mismatch")
    if len(payload) > 5_000_000:
        raise ValueError("Feed exceeds 5 MB download limit")
    return payload


def parse_feed(payload):
    addresses = set()
    skipped = 0
    for number, line in enumerate(payload.decode("utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            address = ip_address(line.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid host IP at line {number}") from exc
        if address.version == 4:
            addresses.add(str(address))
        else:
            skipped += 1
    if not addresses:
        raise ValueError("Feed has no supported IPv4 addresses")
    return sorted(addresses, key=lambda value: int(ip_address(value))), skipped


def refresh(database_url, *, feeds=FEEDS, data_dir=None, fetcher=download):
    """Validate every requested feed before publishing the batch atomically.

    Files are retained by hash for reproducibility. Database publication is one
    transaction; failed publication leaves prior active snapshots unchanged.
    Schema setup is an explicit separate step, never an implicit migration.
    """
    if not feeds or len({f.source_id for f in feeds}) != len(feeds):
        raise ValueError("A nonempty set of distinct source IDs is required")
    folder = Path(data_dir) if data_dir else ROOT / "data" / "evidence"
    prepared = []
    for feed in feeds:
        LOGGER.info("Checking %s", feed.source_id)
        if not re.fullmatch(r"[a-z0-9-]+", feed.source_id):
            raise ValueError("Invalid source identifier")
        payload = fetcher(feed.url)
        addresses, skipped = parse_feed(payload)
        digest = hashlib.sha256(payload).hexdigest()
        directory = folder / feed.source_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (digest + ".txt")
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError("Archived feed hash mismatch")
        if not target.exists():
            descriptor, temporary = tempfile.mkstemp(prefix=".download-", dir=directory)
            try:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(payload)
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        prepared.append((feed, digest, addresses, skipped, datetime.now(UTC)))
    report = []
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(872410052)")
            if not cursor.fetchone()[0]:
                raise RuntimeError("Another evidence publication is in progress")
            for feed, digest, addresses, skipped, fetched_at in prepared:
                cursor.execute(
                    """SELECT snapshot_id FROM ip_evidence_snapshots
                    WHERE source_id=%s AND content_sha256=%s""",
                    (feed.source_id, digest),
                )
                existing = cursor.fetchone()
                if existing:
                    snapshot_id = existing[0]
                    status = "unchanged"
                else:
                    snapshot_id = uuid4()
                    cursor.execute(
                        """INSERT INTO ip_evidence_snapshots
                        (snapshot_id,source_id,indicator_type,provider,source_url,
                         content_sha256,fetched_at,checked_at,ipv4_count,ipv6_skipped)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (
                            snapshot_id,
                            feed.source_id,
                            feed.indicator_type,
                            feed.provider,
                            feed.url,
                            digest,
                            fetched_at,
                            fetched_at,
                            len(addresses),
                            skipped,
                        ),
                    )
                    with cursor.copy("COPY ip_evidence (snapshot_id,ip) FROM STDIN") as copy:
                        for address in addresses:
                            copy.write_row((snapshot_id, address))
                    status = "loaded"
                cursor.execute(
                    "UPDATE ip_evidence_snapshots SET active=FALSE WHERE source_id=%s AND active",
                    (feed.source_id,),
                )
                cursor.execute(
                    "UPDATE ip_evidence_snapshots SET active=TRUE, checked_at=%s WHERE snapshot_id=%s",
                    (fetched_at, snapshot_id),
                )
                report.append(
                    {
                        "source_id": feed.source_id,
                        "status": status,
                        "ipv4_count": len(addresses),
                        "ipv6_skipped": skipped,
                        "sha256": digest,
                    }
                )
    return report


def lookup_evidence(connection, address):
    query = (ROOT / "sql/ip_evidence_lookup.sql").read_text()
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, {"ip_address": address})
        evidence = cursor.fetchall()
        cursor.execute("""SELECT COUNT(*) AS sources,
            COUNT(*) FILTER (WHERE checked_at >= CURRENT_TIMESTAMP - INTERVAL '48 hours') AS recently_checked
            FROM ip_evidence_snapshots WHERE active""")
        coverage = cursor.fetchone()
    return {
        "vpn_status": "listed"
        if any(e["indicator_type"] == "vpn_server" and not e["stale"] for e in evidence)
        else "unknown",
        "tor_status": "listed"
        if any(e["indicator_type"] == "tor_exit" and not e["stale"] for e in evidence)
        else "unknown",
        "evidence": evidence,
        "active_source_count": coverage["sources"],
        "recently_checked_source_count": coverage["recently_checked"],
        "stale_after_hours": 48,
    }
