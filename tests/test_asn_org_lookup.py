"""Check the saved ownership query and read-only runner in isolated test schemas."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

import lookup_asn_org as runner

ROOT = Path(__file__).resolve().parents[1]
SOURCE_A = '20261001.as-org2info.txt.gz'
SOURCE_B = '20260901.as-org2info.txt.gz'
STAMP = datetime(2026, 10, 1, tzinfo=timezone.utc)


class ASNOrganizationLookupTests(unittest.TestCase):
    def setUp(self):
        dsn = os.environ.get('VPNLENS_TEST_DATABASE_URL')
        if not dsn:
            raise RuntimeError('Set VPNLENS_TEST_DATABASE_URL; no project .env fallback')
        schema = 'test_asn_lookup_' + uuid4().hex
        admin = psycopg.connect(dsn, autocommit=True)
        self.addCleanup(admin.close)
        admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        self.addCleanup(lambda: admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema))))
        self.dsn = make_conninfo(dsn, options=f'-c search_path={schema},pg_catalog')
        with psycopg.connect(self.dsn) as connection:
            connection.execute((ROOT / 'sql/asn_org_schema.sql').read_text())
            with connection.cursor() as cursor:
                cursor.executemany('''INSERT INTO raw_org_mappings
                    (org_id,changed,org_name,country,source,snapshot_at,source_file)
                    VALUES (%s,'',%s,%s,'RIPE',%s,%s)''',
                    [('ORG-A', 'Example Owner', 'OM', STAMP, SOURCE_A),
                     ('ORG-A', 'Older Owner', 'US', STAMP, SOURCE_B)])
                cursor.executemany('''INSERT INTO raw_asn_mappings
                    (aut,changed,aut_name,org_id,opaque_id,source,snapshot_at,source_file)
                    VALUES (%s,'',%s,%s,'','RIPE',%s,%s)''',
                    [('206350', 'EXAMPLE-AS', 'ORG-A', STAMP, SOURCE_A),
                     ('206350', 'OLDER-AS', 'ORG-A', STAMP, SOURCE_B),
                     ('28885', 'MISSING-ORG-AS', 'ABSENT', STAMP, SOURCE_A)])

    def lookup(self, asn='206350', source=SOURCE_A):
        return runner.lookup_asn_org(asn, source, database_url=self.dsn)

    def test_matches_expected_fields(self):
        self.assertEqual(self.lookup(), [{'aut': '206350', 'aut_name': 'EXAMPLE-AS',
            'org_name': 'Example Owner', 'country': 'OM', 'source': 'RIPE', 'snapshot_at': STAMP}])

    def test_missing_org_preserves_asn(self):
        row, = self.lookup('28885')
        self.assertEqual(row['aut'], '28885')
        self.assertEqual(row['aut_name'], 'MISSING-ORG-AS')
        for field in ('org_name', 'country', 'source'):
            self.assertIsNone(row[field])

    def test_org_join_is_snapshot_scoped(self):
        self.assertEqual(self.lookup()[0]['org_name'], 'Example Owner')
        self.assertEqual(self.lookup(source=SOURCE_B)[0]['org_name'], 'Older Owner')

    def test_unknown_asn_or_snapshot_returns_empty(self):
        self.assertEqual(self.lookup('999999'), [])
        self.assertEqual(self.lookup(source='missing'), [])

    def test_parameters_cannot_change_query(self):
        self.assertEqual(self.lookup("206350' OR TRUE --"), [])
        self.assertEqual(self.lookup(source="x' OR TRUE --"), [])

    def test_runner_transaction_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'sql').mkdir()
            (root / 'sql/asn_org_lookup.sql').write_text(
                "SELECT current_setting('transaction_read_only') AS read_only")
            with patch.object(runner, 'ROOT', root):
                self.assertEqual(self.lookup(), [{'read_only': 'on'}])

    def test_cli_json_outside_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(ROOT / 'lookup_asn_org.py'), '206350', SOURCE_A],
                cwd=directory, env=dict(os.environ, DATABASE_URL=self.dsn),
                capture_output=True, text=True, check=True)
        rows = json.loads(result.stdout)
        self.assertEqual(rows[0]['org_name'], 'Example Owner')
        self.assertEqual(datetime.fromisoformat(rows[0]['snapshot_at']), STAMP)


if __name__ == '__main__':
    unittest.main()
