"""Run the parameterized IP lookup and print its rows as JSON."""

import argparse
import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent


def lookup_ip(ip_address, source_file, org_source_file):
    load_dotenv(ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is not set")

    lookup_sql = (ROOT / "sql" / "ip_lookup.sql").read_text(encoding="utf-8")
    parameters = {"ip_address": ip_address, "source_file": source_file,
                  "org_source_file": org_source_file}

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(lookup_sql, parameters)
            return cur.fetchall()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Look up one IPv4 address in a selected ASN snapshot.")
    parser.add_argument("ip_address", help="IPv4 host address, such as 8.8.8.8")
    parser.add_argument("source_file", help="Exact source_file value in asn_prefix_origins")
    parser.add_argument("org_source_file", help="Exact source_file value in raw_asn_mappings")
    args = parser.parse_args()
    rows = lookup_ip(args.ip_address, args.source_file, args.org_source_file)
    print(json.dumps(rows, indent=2, default=str))
