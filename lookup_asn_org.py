"""Run the user-owned ASN organization lookup and print rows as JSON."""
import argparse
import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent


def lookup_asn_org(asn, source_file, *, database_url=None):
    if database_url is None:
        load_dotenv(ROOT / '.env')
        database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError('DATABASE_URL is not set')
    query = (ROOT / 'sql' / 'asn_org_lookup.sql').read_text(encoding='utf-8')
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute(query, {'asn': asn, 'source_file': source_file})
            return cursor.fetchall()


def main():
    parser = argparse.ArgumentParser(description='Look up one ASN in a selected organization snapshot.')
    parser.add_argument('asn', help='One ASN, such as 206350')
    parser.add_argument('source_file', help='Exact organization source filename')
    args = parser.parse_args()
    print(json.dumps(lookup_asn_org(args.asn, args.source_file), indent=2, default=str))


if __name__ == '__main__':
    main()
