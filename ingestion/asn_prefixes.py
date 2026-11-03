"""Atomically load and transform one explicitly selected IPv4 routing snapshot."""

import argparse
import json

from vpnlens.config import Settings
from vpnlens.refresh import load_routing, publication


def ingest_asn_prefixes(file_path, *, database_url=None):
    database_url = database_url or Settings.from_env().database_url
    if not database_url:
        raise ValueError("DATABASE_URL is required")
    with publication(database_url, "routing") as connection:
        return load_routing(file_path, connection)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file_path", help="Path to routeviews-rv2-YYYYMMDD-HHMM.pfx2as.gz")
    args = parser.parse_args()
    print(json.dumps(ingest_asn_prefixes(args.file_path), indent=2))


if __name__ == "__main__":
    main()
