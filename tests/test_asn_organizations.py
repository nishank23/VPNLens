"""Source parser and isolated-schema PostgreSQL checks for organization loads."""
from datetime import datetime, timezone
import gzip
import io
import os
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg import sql

from ingestion.asn_organizations import ingest_asn_organizations, iter_records

ROOT = Path(__file__).resolve().parents[1]
ORG = '# format:org_id|changed|org_name|country|source\n'
ASN = '# format:aut|changed|aut_name|org_id|opaque_id|source\n'
VALID = ORG + 'ORG-A||Example Network|OM|RIPE\n' + ASN + '206350|||ORG-A||RIPE\n'


class ParserTests(unittest.TestCase):
    def test_blanks_and_comments(self):
        records = list(iter_records(io.StringIO('# comment\n\n' + VALID)))
        self.assertEqual(records[0], ('organization', ['ORG-A', '', 'Example Network', 'OM', 'RIPE']))
        self.assertEqual(records[1][1], ['206350', '', '', 'ORG-A', '', 'RIPE'])

    def test_reversed_sections(self):
        records = list(iter_records(io.StringIO(ASN + '1||AS|ORG-A||ARIN\n' + ORG + 'ORG-A||Name|US|ARIN\n')))
        self.assertEqual([kind for kind, fields in records], ['asn', 'organization'])

    def test_malformed_input(self):
        for contents in ('x|y\n', '# format:unexpected\na\n', ORG + 'x|y\n', ASN + '1||Name|||RIPE\n'):
            with self.subTest(contents=contents), self.assertRaises(ValueError):
                list(iter_records(io.StringIO(contents)))

    def test_dated_filename_required(self):
        with self.assertRaisesRegex(ValueError, 'dated'):
            ingest_asn_organizations('latest.as-org2info.txt.gz', database_url='unused')


class LoaderTests(unittest.TestCase):
    def setUp(self):
        dsn = os.environ.get('VPNLENS_TEST_DATABASE_URL')
        if not dsn:
            raise RuntimeError('Set VPNLENS_TEST_DATABASE_URL to a dedicated test database; no .env fallback')
        self.schema = 'test_asn_org_' + uuid4().hex
        self.admin = psycopg.connect(dsn, autocommit=True)
        self.addCleanup(self.admin.close)
        self.admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        self.addCleanup(lambda: self.admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema))))
        self.dsn = make_conninfo(dsn, options=f'-c search_path={self.schema},pg_catalog')
        with psycopg.connect(self.dsn) as connection:
            connection.execute((ROOT / 'sql/asn_org_schema.sql').read_text())
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / '20261001.as-org2info.txt.gz'

    def write(self, contents=VALID, path=None):
        target = path or self.path
        with gzip.open(target, 'wt', encoding='utf-8') as f:
            f.write(contents)
        return target

    def load(self, path=None):
        return ingest_asn_organizations(path or self.path, database_url=self.dsn)

    def rows(self):
        with psycopg.connect(self.dsn) as connection:
            return tuple(connection.execute('SELECT * FROM ' + table + ' ORDER BY source_file').fetchall()
                         for table in ('raw_org_mappings', 'raw_asn_mappings'))

    def test_load_preserves_blanks_and_metadata(self):
        self.write()
        result = self.load()
        self.assertEqual((result['organization_rows'], result['asn_rows']), (1, 1))
        orgs, asns = self.rows()
        self.assertEqual(orgs[0][1], '')
        self.assertEqual(asns[0][:6], ('206350', '', '', 'ORG-A', '', 'RIPE'))
        self.assertEqual(asns[0][6], datetime(2026, 10, 1, tzinfo=timezone.utc))
        self.assertEqual(asns[0][-1], self.path.name)

    def test_rerun_replaces_selected_file_only(self):
        self.write()
        self.load()
        other = self.write(path=self.path.with_name('20260901.as-org2info.txt.gz'))
        self.load(other)
        self.write(VALID.replace('Example Network', 'Updated Network'))
        self.load()
        orgs, asns = self.rows()
        self.assertEqual(len(orgs), 2)
        self.assertEqual(len(asns), 2)
        self.assertEqual([row[2] for row in orgs], ['Example Network', 'Updated Network'])

    def test_invalid_loads_preserve_prior_rows(self):
        self.write()
        self.load()
        previous = self.rows()
        for invalid in (ORG, ORG + 'ORG-A||Name|OM|RIPE\n', VALID + 'broken\n', VALID + '206350|||ORG-A||RIPE\n', VALID.replace('ORG-A||Example Network', 'ORG-A||Changed') + ORG + 'ORG-A||Duplicate|OM|RIPE\n'):
            with self.subTest(invalid=invalid):
                self.write(invalid)
                with self.assertRaises((ValueError, psycopg.Error)):
                    self.load()
                self.assertEqual(self.rows(), previous)

    def test_corrupt_gzip_preserves_prior_rows(self):
        self.write()
        self.load()
        previous = self.rows()
        self.path.write_bytes(b'not a gzip file')
        with self.assertRaises(gzip.BadGzipFile):
            self.load()
        self.assertEqual(self.rows(), previous)

    def test_missing_org_reference_is_preserved_in_raw(self):
        self.write(VALID.replace('206350|||ORG-A', '206350|||ORG-MISSING'))
        self.load()
        self.assertEqual(self.rows()[1][0][3], 'ORG-MISSING')


if __name__ == '__main__':
    unittest.main()
