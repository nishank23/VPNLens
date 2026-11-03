"""Narrow SQL evidence contracts; all writes share the legacy evidence lock."""

from datetime import UTC, datetime

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from vpnlens.config import ROOT
from vpnlens.evidence_contract import canonical, digest, instant, public_network, stamp
from vpnlens.observation_contract import profile_contract, text, validate_observation

CONTRACTS = {
    name: ROOT / "sql" / f"evidence_v2_{name}.sql"
    for name in ("validate", "publish", "lookup", "sources", "observe")
}


class EvidenceStore:
    def __init__(self, connection):
        self.connection = connection

    def run(self, operation, payload):
        if operation not in CONTRACTS:
            raise ValueError("Unknown evidence operation")
        row = self.connection.execute(
            CONTRACTS[operation].read_text(), {"payload": Jsonb(payload)}
        ).fetchone()
        if not isinstance(row, dict) or not isinstance(row.get("result"), dict):
            raise ValueError("Evidence contract must return a JSON object")
        return row["result"]


def _lock(connection):
    connection.execute("SET LOCAL lock_timeout = '5s'")
    if not connection.execute("SELECT pg_try_advisory_xact_lock(872410052) AS locked").fetchone()[
        "locked"
    ]:
        raise RuntimeError("Evidence publication lock is busy")


def _compatible(store):
    result = store.run("validate", {})
    if result.get("schema_version") != 1 or result.get("compatible") is not True:
        raise ValueError("Incompatible extended evidence schema")
    return result


def publish_contract(database_url, operation, payload):
    if operation not in ("publish", "observe"):
        raise ValueError("Only evidence publications are writable contracts")
    with psycopg.connect(database_url, connect_timeout=5, row_factory=dict_row) as connection:
        _lock(connection)
        store = EvidenceStore(connection)
        _compatible(store)
        return store.run(operation, payload)


def initialize_extended(database_url):
    with psycopg.connect(database_url, connect_timeout=5, row_factory=dict_row) as connection:
        _lock(connection)
        existing = connection.execute(
            "SELECT to_regclass('evidence_v2_manifest') AS manifest, EXISTS(SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND c.relname LIKE 'evidence_v2_%') AS present"
        ).fetchone()
        if existing["present"]:
            if existing["manifest"] is None:
                raise ValueError("Incompatible preexisting extended evidence tables")
            _compatible(EvidenceStore(connection))
        connection.execute((ROOT / "sql/evidence_v2_schema.sql").read_text())
        return _compatible(EvidenceStore(connection))


def observation_payload(record, profile, review=None, now=None):
    """Validate private artifacts and return only public measurement and hashed review."""
    now = datetime.now(UTC) if now is None else now
    profile = profile_contract(profile)
    attrs = validate_observation(record, profile, now)
    identity = record["observation_id"]
    sha = digest(canonical(record))
    measurement = dict(
        observation_id=identity,
        observation_sha256=sha,
        profile_sha256=record["profile_sha256"],
        source_id="observation-" + profile["profile_id"],
        family="measured_exit",
        record_key=sha,
        network=public_network(attrs["ip"]),
        provider=attrs["provider"],
        basis="exit_observation",
        role="exit",
        method=attrs["method"],
        service_category=attrs["service_category"],
        source_url=profile["documentation_url"],
        content_sha256=sha,
        observed_at=attrs["observed_at"],
        expires_at=attrs["expires_at"],
        connection_type_claim=attrs["connection_type_claim"],
    )
    normalized_review = None
    if review is not None:
        if (
            not isinstance(review, dict)
            or set(review)
            != {"observation_id", "observation_sha256", "review_state", "operator", "reviewed_at"}
            or review["observation_id"] != identity
            or review["observation_sha256"] != sha
            or review["review_state"] not in ("approved", "rejected")
        ):
            raise ValueError("Review does not match immutable measurement")
        reviewed = instant(review["reviewed_at"])
        if not instant(attrs["observed_at"]) <= reviewed <= now or reviewed >= instant(
            attrs["expires_at"]
        ):
            raise ValueError("Invalid or expired review")
        normalized_review = {
            key: review[key] for key in ("observation_id", "observation_sha256", "review_state")
        }
        normalized_review.update(
            reviewed_at=stamp(reviewed), reviewer_sha256=digest(text(review["operator"]).encode())
        )
    return dict(measurement=measurement, review=normalized_review)
