"""Initialize the existing model without destructive schema scripts."""

import argparse
import json

import psycopg

from .config import ROOT, Settings

# PostgreSQL internal type names; extra columns are allowed, missing or changed
# required columns are not. Never silently migrate an existing table.
GEO = dict(
    ip_from="int8",
    ip_to="int8",
    country_code="bpchar",
    country_name="varchar",
    region_name="varchar",
    city_name="varchar",
    latitude="float8",
    longitude="float8",
    zip_code="varchar",
    time_zone="varchar",
)
EXPECTED = {
    "raw_ip2location": GEO,
    "ip2location": {**GEO, "ip_range": "int8range"},
    "raw_asn_prefixes": dict(
        prefix_address="text",
        prefix_length="int4",
        origin_as_raw="text",
        source_file="text",
        snapshot_at="timestamptz",
        ingested_at="timestamptz",
    ),
    "asn_prefix_origins": dict(
        prefix="cidr",
        origin_group="text",
        source_file="text",
        snapshot_at="timestamptz",
        ingested_at="timestamptz",
    ),
    "raw_asn_mappings": dict(
        aut="text",
        changed="text",
        aut_name="text",
        org_id="text",
        opaque_id="text",
        source="text",
        snapshot_at="timestamptz",
        ingested_at="timestamptz",
        source_file="text",
    ),
    "raw_org_mappings": dict(
        org_id="text",
        changed="text",
        org_name="text",
        country="text",
        source="text",
        snapshot_at="timestamptz",
        ingested_at="timestamptz",
        source_file="text",
    ),
    "ip_evidence_snapshots": dict(
        snapshot_id="uuid",
        source_id="text",
        indicator_type="text",
        provider="text",
        source_url="text",
        content_sha256="text",
        fetched_at="timestamptz",
        checked_at="timestamptz",
        ipv4_count="int8",
        ipv6_skipped="int8",
        active="bool",
    ),
    "ip_evidence": dict(snapshot_id="uuid", ip="inet"),
}
UNIQUE = {
    "asn_prefix_origins": ("source_file", "prefix", "origin_group"),
    "raw_asn_mappings": ("source_file", "aut"),
    "raw_org_mappings": ("source_file", "org_id"),
    "ip_evidence_snapshots": ("source_id", "content_sha256"),
    "ip_evidence": ("snapshot_id", "ip"),
}


def check_existing(connection):
    for table, expected in EXPECTED.items():
        columns = dict(
            connection.execute(
                """SELECT column_name, udt_name FROM information_schema.columns
            WHERE table_schema=current_schema() AND table_name=%s""",
                (table,),
            ).fetchall()
        )
        if not columns:
            continue
        if any(columns.get(name) != kind for name, kind in expected.items()):
            raise ValueError(
                f"Incompatible existing table: {table}; review the schema before initialization"
            )
        if table in UNIQUE:
            unique_sets = connection.execute(
                """SELECT array_agg(a.attname ORDER BY key.ordinality)
                FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid
                JOIN pg_namespace n ON n.oid=t.relnamespace
                CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS key(attnum, ordinality)
                JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=key.attnum
                WHERE n.nspname=current_schema() AND t.relname=%s AND i.indisunique
                  AND i.indpred IS NULL AND i.indexprs IS NULL AND i.indisvalid
                GROUP BY i.indexrelid""",
                (table,),
            ).fetchall()
            if list(UNIQUE[table]) not in [row[0] for row in unique_sets]:
                raise ValueError(f"Incompatible uniqueness constraint: {table}; review the schema")


def initialize(database_url):
    with psycopg.connect(database_url, connect_timeout=5) as connection:
        connection.execute("SET LOCAL lock_timeout = '5s'")
        connection.execute("SELECT pg_advisory_xact_lock(872410053)")
        check_existing(connection)
        connection.execute((ROOT / "sql/bootstrap.sql").read_text())
        check_existing(connection)
    return {"status": "initialized", "tables": len(EXPECTED)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extended-evidence",
        action="store_true",
        help="Explicitly initialize additive evidence contracts",
    )
    args = parser.parse_args()
    settings = Settings.from_env()
    if not settings.database_url:
        parser.error("DATABASE_URL is required")
    try:
        result = initialize(settings.database_url)
        if args.extended_evidence:
            from .evidence_store import initialize_extended

            result["extended_evidence"] = initialize_extended(settings.database_url)
        print(json.dumps(result))
    except (psycopg.Error, ValueError) as error:
        # Drivers can include connection details in error strings.
        parser.exit(
            1,
            f"Initialization failed ({type(error).__name__}); check connectivity and schema compatibility.\n",
        )


if __name__ == "__main__":
    main()
