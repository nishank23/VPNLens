"""Run the parameterized IP lookup and print its rows as JSON."""

import argparse
import json
from ipaddress import IPv4Address
from pathlib import Path

import psycopg

from ingestion.ip_evidence import lookup_evidence
from vpnlens.config import Settings
from vpnlens.database import SourcesUnavailable, read_connection
from vpnlens.geolocation import DBIP_CITY_LITE
from vpnlens.service import enrich_security, geolocation_status

ROOT = Path(__file__).resolve().parent


def lookup_ip(ip_address, source_file, org_source_file):
    ip_address = str(IPv4Address(ip_address))
    settings = Settings.from_env()

    lookup_sql = (ROOT / "sql" / "ip_lookup.sql").read_text(encoding="utf-8")
    parameters = {
        "ip_address": ip_address,
        "source_file": source_file,
        "org_source_file": org_source_file,
    }

    with read_connection(settings) as conn:
        if (
            settings.geolocation_provider == DBIP_CITY_LITE
            and not geolocation_status(conn, settings.geolocation_provider)["available"]
        ):
            raise SourcesUnavailable("DB-IP geolocation release is not loaded")
        with conn.cursor() as cur:
            cur.execute(lookup_sql, parameters)
            rows = cur.fetchall()
        security = lookup_evidence(conn, ip_address)
        if settings.extended_evidence:
            security = enrich_security(conn, ip_address, security)
        for row in rows:
            row["security"] = security
        return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Look up one IPv4 address in a selected ASN snapshot."
    )
    parser.add_argument("ip_address", help="IPv4 host address, such as 8.8.8.8")
    parser.add_argument("source_file", help="Exact source_file value in asn_prefix_origins")
    parser.add_argument("org_source_file", help="Exact source_file value in raw_asn_mappings")
    args = parser.parse_args()
    try:
        rows = lookup_ip(args.ip_address, args.source_file, args.org_source_file)
    except (ValueError, OSError, psycopg.Error, SourcesUnavailable) as error:
        parser.exit(
            1,
            f"Lookup failed ({type(error).__name__}); check IPv4 input, database configuration, and schema.\n",
        )
    print(json.dumps(rows, indent=2, default=str))
