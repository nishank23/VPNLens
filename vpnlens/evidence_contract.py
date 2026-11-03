"""Shared canonicalization and immutable artifact helpers for evidence collectors."""

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from ipaddress import ip_network
from pathlib import Path


def canonical(value: object) -> bytes:
    """Serialize a JSON value with stable key ordering and no NaN values."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def digest(payload: bytes) -> str:
    """Return the SHA-256 hexadecimal digest of bytes."""
    return hashlib.sha256(payload).hexdigest()


def stamp(value: datetime | None = None) -> str:
    """Return an aware timestamp normalized to UTC in ISO format."""
    value = datetime.now(UTC) if value is None else value
    if value.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return value.astimezone(UTC).isoformat()


def instant(value: str) -> datetime:
    """Parse an ISO timestamp and return its UTC-aware instant."""
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return parsed.astimezone(UTC)


_NON_PUBLIC_NETWORKS = tuple(
    ip_network(network)
    for network in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.88.99.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
    )
)


def public_network(value: str) -> str:
    """Validate a globally routable IPv4 address or strict network CIDR."""
    network = ip_network(value, strict=True)
    if (
        network.version != 4
        or network.prefixlen == 0
        or not network.is_global
        or any(network.overlaps(blocked) for blocked in _NON_PUBLIC_NETWORKS)
    ):
        raise ValueError("Expected a globally routable IPv4 network")
    return str(network)


def write_once(path: str | os.PathLike[str], payload: bytes) -> None:
    """Atomically create a private immutable artifact, allowing identical retries."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".write-", dir=destination.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        try:
            os.link(temporary_name, destination)
        except FileExistsError:
            if destination.read_bytes() != payload:
                raise ValueError("Conflicting or corrupted immutable artifact")
    finally:
        os.unlink(temporary_name)
