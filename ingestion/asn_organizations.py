"""Load one dated CAIDA AS-to-Organization gzip into the raw tables."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import json
import logging
import os
from pathlib import Path
import re

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)
FORMATS = {
    ('org_id', 'changed', 'org_name', 'country', 'source'): 'organization',
    ('aut', 'changed', 'aut_name', 'org_id', 'opaque_id', 'source'): 'asn',
}


def iter_records(lines):
    """Yield (section, source fields), retaining empty strings verbatim."""
    section = None
    width = None
    for number, line in enumerate(lines, 1):
        line = line.rstrip('\r\n')
        if not line.strip():
            continue
        if line.startswith('# format:'):
            header = tuple(line.split(':', 1)[1].strip().split('|'))
            if header not in FORMATS:
                raise ValueError(f'Unknown format at line {number}')
            section = FORMATS[header]
            width = len(header)
        elif line.startswith('#'):
            continue
        else:
            if section is None:
                raise ValueError(f'Data before format marker at line {number}')
            fields = line.split('|')
            if len(fields) != width:
                raise ValueError(f'Expected {width} fields at line {number}; got {len(fields)}')
            if not fields[0] or not fields[-1] or (section == 'asn' and not fields[3]):
                raise ValueError(f'Missing identifier or registry source at line {number}')
            yield section, fields


def ingest_asn_organizations(file_path, *, database_url=None):
    """Replace both sections for one filename in a single transaction.

    Tables must already exist. Unresolved organization references are preserved;
    the raw tables do not declare a foreign key. Database uniqueness constraints
    reject duplicate identifiers. No project schema is created or altered here.
    """
    path = Path(file_path).expanduser().resolve()
    match = re.fullmatch(r'(\d{8})\.as-org2info\.txt\.gz', path.name)
    if not match:
        raise ValueError('Expected a dated YYYYMMDD.as-org2info.txt.gz filename')
    snapshot_at = datetime.strptime(match.group(1), '%Y%m%d').replace(tzinfo=timezone.utc)
    if database_url is None:
        load_dotenv(ROOT / '.env')
        database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError('DATABASE_URL is not set')

    # Two streaming passes avoid holding the full dataset in memory or keeping
    # concurrent COPY operations open. Rewind the same file between passes.
    with gzip.open(path, 'rt', encoding='utf-8') as source:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM raw_asn_mappings WHERE source_file = %s', (path.name,))
                cursor.execute('DELETE FROM raw_org_mappings WHERE source_file = %s', (path.name,))
                first_counts = Counter()
                with cursor.copy('''COPY raw_org_mappings
                    (org_id, changed, org_name, country, source, source_file, snapshot_at)
                    FROM STDIN''') as copy:
                    for section, fields in iter_records(source):
                        first_counts[section] += 1
                        if section == 'organization':
                            copy.write_row([*fields, path.name, snapshot_at])
                if not first_counts['organization'] or not first_counts['asn']:
                    raise ValueError('Snapshot must contain both organization and ASN records')

                source.seek(0)
                second_counts = Counter()
                with cursor.copy('''COPY raw_asn_mappings
                    (aut, changed, aut_name, org_id, opaque_id, source, source_file, snapshot_at)
                    FROM STDIN''') as copy:
                    for section, fields in iter_records(source):
                        second_counts[section] += 1
                        if section == 'asn':
                            copy.write_row([*fields, path.name, snapshot_at])
                if first_counts != second_counts:
                    raise ValueError('Source record counts changed between passes')
                stored = {}
                for section, table in (('organization', 'raw_org_mappings'), ('asn', 'raw_asn_mappings')):
                    # Table names are internal constants, never user input.
                    cursor.execute(f'SELECT COUNT(*) FROM {table} WHERE source_file = %s', (path.name,))
                    stored[section] = cursor.fetchone()[0]
                    if stored[section] != first_counts[section]:
                        raise ValueError(f'{section} row count mismatch')
    result = {'source_file': path.name, 'snapshot_at': snapshot_at.isoformat(),
              'organization_rows': stored['organization'], 'asn_rows': stored['asn']}
    LOGGER.info('Committed %s organizations and %s ASN records from %s',
                stored['organization'], stored['asn'], path.name)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file_path', help='Path to YYYYMMDD.as-org2info.txt.gz')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    result = ingest_asn_organizations(args.file_path)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
