"""Evidence parsing and isolated PostgreSQL publication/lookup checks."""
from pathlib import Path
import os
from io import BytesIO
from unittest.mock import patch
import tempfile
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from ingestion.ip_evidence import Feed, parse_feed, refresh, lookup_evidence, download

ROOT = Path(__file__).resolve().parents[1]
VPN = Feed('test-vpn','vpn_server','Example VPN','https://example.invalid/vpn')
TOR = Feed('test-tor','tor_exit',None,'https://example.invalid/tor')


class EvidenceParserTests(unittest.TestCase):
    def test_ipv4_deduplication_and_ipv6_count(self):
        self.assertEqual(parse_feed(b'8.8.8.8\n1.1.1.1\n8.8.8.8\n2001:db8::1\n'), (['1.1.1.1','8.8.8.8'],1))

    def test_invalid_or_empty_rejected(self):
        for content in (b'',b'<html>error</html>',b'8.8.8.8/32',b'2001:db8::1',b'8.8.8.8\nbroken'):
            with self.subTest(content=content), self.assertRaises(ValueError):
                parse_feed(content)


    def test_incomplete_download_rejected(self):
        response = BytesIO(b'8.8.8.8')
        response.headers = {'Content-Length':'100'}
        with patch('ingestion.ip_evidence.urlopen',return_value=response):
            with self.assertRaisesRegex(ValueError,'Incomplete download'):
                download(VPN.url)



class EvidenceDatabaseTests(unittest.TestCase):
    def setUp(self):
        dsn = os.environ.get('VPNLENS_TEST_DATABASE_URL')
        if not dsn:
            raise RuntimeError('Set VPNLENS_TEST_DATABASE_URL; no project database fallback')
        self.schema = 'test_evidence_' + uuid4().hex
        admin = psycopg.connect(dsn,autocommit=True)
        self.addCleanup(admin.close)
        admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        self.addCleanup(lambda: admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema))))
        self.dsn = make_conninfo(dsn,options=f'-c search_path={self.schema},pg_catalog')
        with psycopg.connect(self.dsn) as connection:
            connection.execute((ROOT/'sql/ip_evidence_schema.sql').read_text())
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def publish(self, payload=b'8.8.8.8\n', feeds=(VPN,)):
        return refresh(self.dsn,feeds=feeds,data_dir=self.folder.name,fetcher=lambda url: payload)

    def lookup(self, address='8.8.8.8'):
        with psycopg.connect(self.dsn) as connection:
            connection.read_only = True
            return lookup_evidence(connection,address)

    def test_load_archive_and_unknown_semantics(self):
        result = self.publish()
        self.assertEqual(result[0]['status'],'loaded')
        self.assertTrue((Path(self.folder.name)/VPN.source_id/(result[0]['sha256']+'.txt')).exists())
        actual = self.lookup()
        self.assertEqual(actual['vpn_status'],'listed')
        self.assertEqual(actual['tor_status'],'unknown')
        self.assertEqual(actual['evidence'][0]['provider'],'Example VPN')
        self.assertEqual(self.lookup('1.1.1.1')['vpn_status'],'unknown')

    def test_unchanged_reuses_snapshot(self):
        self.publish()
        result = self.publish()
        self.assertEqual(result[0]['status'],'unchanged')
        with psycopg.connect(self.dsn) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM ip_evidence_snapshots').fetchone()[0],1)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM ip_evidence').fetchone()[0],1)

    def test_changed_snapshot_retires_previous_members(self):
        self.publish()
        self.publish(b'1.1.1.1\n')
        self.assertEqual(self.lookup()['vpn_status'],'unknown')
        self.assertEqual(self.lookup('1.1.1.1')['vpn_status'],'listed')
        with psycopg.connect(self.dsn) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*),COUNT(*) FILTER(WHERE active) FROM ip_evidence_snapshots').fetchone(),(2,1))

    def test_stale_match_retains_evidence_without_current_flag(self):
        self.publish()
        with psycopg.connect(self.dsn) as connection:
            connection.execute("UPDATE ip_evidence_snapshots SET checked_at=CURRENT_TIMESTAMP-INTERVAL '49 hours'")
        result = self.lookup()
        self.assertEqual(result['vpn_status'],'unknown')
        self.assertTrue(result['evidence'][0]['stale'])
        self.assertEqual(result['recently_checked_source_count'],0)

    def test_multiple_sources_preserved_and_tor_separate(self):
        self.publish(feeds=(VPN,TOR))
        result = self.lookup()
        self.assertEqual((result['vpn_status'],result['tor_status']),('listed','listed'))
        self.assertEqual(len(result['evidence']),2)
        self.assertEqual(result['active_source_count'],2)

    def test_download_or_parse_failure_preserves_previous_batch(self):
        self.publish()
        with self.assertRaises(ValueError):
            self.publish(b'invalid')
        def fail_second(url):
            if url == TOR.url:
                raise OSError('simulated download failure')
            return b'1.1.1.1\n'
        with self.assertRaises(OSError):
            refresh(self.dsn,feeds=(VPN,TOR),data_dir=self.folder.name,fetcher=fail_second)
        self.assertEqual(self.lookup()['vpn_status'],'listed')
        self.assertEqual(self.lookup('1.1.1.1')['vpn_status'],'unknown')

    def test_database_failure_rolls_back_entire_publication(self):
        self.publish()
        bad = Feed('test-bad','invalid',None,'https://example.invalid/bad')
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.publish(b'1.1.1.1\n',feeds=(VPN,bad))
        self.assertEqual(self.lookup()['vpn_status'],'listed')
        self.assertEqual(self.lookup()['active_source_count'],1)

    def test_overlapping_publication_fails_without_replacement(self):
        self.publish()
        with psycopg.connect(self.dsn) as blocker:
            blocker.execute('SELECT pg_advisory_xact_lock(872410052)')
            with self.assertRaisesRegex(RuntimeError,'Another evidence'):
                self.publish(b'1.1.1.1\n')
        self.assertEqual(self.lookup()['vpn_status'],'listed')

    def test_corrupted_archive_is_rejected(self):
        result = self.publish()
        archive = Path(self.folder.name)/VPN.source_id/(result[0]['sha256']+'.txt')
        archive.write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError,'Archived feed hash'):
            self.publish()
        self.assertEqual(self.lookup()['vpn_status'],'listed')

    def test_empty_database_is_unknown(self):
        result = self.lookup()
        self.assertEqual(result['evidence'],[])
        self.assertEqual(result['active_source_count'],0)
        self.assertEqual((result['vpn_status'],result['tor_status']),('unknown','unknown'))


if __name__ == '__main__':
    unittest.main()
