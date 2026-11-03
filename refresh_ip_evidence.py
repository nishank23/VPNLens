"""Refresh free local VPN-server/Tor evidence; no API key or paid service."""

import argparse
import json
import logging
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from ingestion.ip_evidence import refresh

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--init-schema",
        action="store_true",
        help="Create the evidence tables and indexes if absent",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    load_dotenv(ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is not set")
    if args.init_schema:
        with psycopg.connect(database_url) as connection:
            connection.execute((ROOT / "sql/ip_evidence_schema.sql").read_text())
    print(json.dumps(refresh(database_url), indent=2))


if __name__ == "__main__":
    main()
