"""Contract tests for the user-owned, parameterized IP lookup SQL.

Run against a dedicated test database. Fixtures use connection-local tables;
the lookup itself runs in a read-only transaction.
"""

from datetime import datetime, timezone
from ipaddress import IPv4Address
import os
from pathlib import Path
import unittest

import psycopg


ROOT = Path(__file__).resolve().parents[1]
SOURCE_A = "fixture-a.pfx2as.gz"
SOURCE_B = "fixture-b.pfx2as.gz"
SNAPSHOT_A = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
SNAPSHOT_B = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
ORG_SOURCE = "fixture-org-a.txt.gz"
ORG_OTHER = "fixture-org-b.txt.gz"
ORG_STAMP = datetime(2026, 10, 1, tzinfo=timezone.utc)
FIELDS = ("ip", "country_code", "city_name", "prefix", "origin_group", "snapshot_at")


class IPLookupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.environ.get("VPNLENS_TEST_DATABASE_URL")
        if not cls.database_url:
            raise RuntimeError(
                "Set VPNLENS_TEST_DATABASE_URL to a dedicated PostgreSQL test database. "
                "The tests deliberately do not load .env or DATABASE_URL."
            )
        cls.lookup_sql = (ROOT / "sql" / "ip_lookup.sql").read_text(encoding="utf-8")

    def setUp(self):
        self.connection = psycopg.connect(self.database_url, connect_timeout=5)
        self.addCleanup(self.connection.close)
        with self.connection.cursor() as cursor:
            # Match the existing production column types without touching its tables.
            cursor.execute(
                """
                CREATE TEMP TABLE ip2location (
                    ip_from BIGINT NOT NULL,
                    ip_to BIGINT NOT NULL,
                    country_code CHAR(2),
                    country_name VARCHAR(64),
                    region_name VARCHAR(128),
                    city_name VARCHAR(128),
                    latitude DOUBLE PRECISION,
                    longitude DOUBLE PRECISION,
                    zip_code VARCHAR(30),
                    time_zone VARCHAR(8),
                    ip_range INT8RANGE NOT NULL
                );
                CREATE TEMP TABLE asn_prefix_origins (
                    prefix CIDR NOT NULL,
                    origin_group TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    snapshot_at TIMESTAMPTZ NOT NULL,
                    ingested_at TIMESTAMPTZ NOT NULL,
                    UNIQUE (source_file, prefix, origin_group)
                );
                """
            )
            cursor.execute((ROOT / "sql/asn_org_schema.sql").read_text().replace(
                "CREATE TABLE ", "CREATE TEMP TABLE "))
            cursor.executemany("""INSERT INTO raw_org_mappings
                (org_id,changed,org_name,country,source,snapshot_at,source_file)
                VALUES (%s,'',%s,%s,'FIXTURE',%s,%s)""", [
                ('ORG-ONE','Current Owner','OM',ORG_STAMP,ORG_SOURCE),
                ('ORG-ONE','Other Snapshot Owner','US',SNAPSHOT_B,ORG_OTHER)])
            cursor.executemany("""INSERT INTO raw_asn_mappings
                (aut,changed,aut_name,org_id,opaque_id,source,snapshot_at,source_file)
                VALUES (%s,'','AS-NAME',%s,'','FIXTURE',%s,%s)""", [
                ('64500','ORG-ONE',ORG_STAMP,ORG_SOURCE),
                ('64501','ORG-ONE',ORG_STAMP,ORG_SOURCE),
                ('64502','MISSING-ORG',ORG_STAMP,ORG_SOURCE),
                ('64530','ORG-ONE',ORG_STAMP,ORG_SOURCE),
                ('64500','ORG-ONE',SNAPSHOT_B,ORG_OTHER)])
            locations = [
                ("192.0.2.0", "192.0.2.255", "ZZ", "Example City"),
                ("198.51.100.0", "198.51.100.255", "YY", "Second City"),
                ("198.18.0.0", "198.18.0.255", "XX", "Location Only"),
            ]
            cursor.executemany(
                """
                INSERT INTO ip2location
                    (ip_from, ip_to, country_code, city_name, ip_range)
                VALUES (%s, %s, %s, %s, int8range(%s, %s, '[]'))
                """,
                [
                    (int(IPv4Address(start)), int(IPv4Address(end)), country, city,
                     int(IPv4Address(start)), int(IPv4Address(end)))
                    for start, end, country, city in locations
                ],
            )
            origins = [
                ("192.0.2.0/24", "64500", SOURCE_A, SNAPSHOT_A),
                ("192.0.2.128/25", "64501", SOURCE_A, SNAPSHOT_A),
                ("192.0.2.128/25", "64502", SOURCE_A, SNAPSHOT_A),
                ("198.51.100.0/24", "64520", SOURCE_A, SNAPSHOT_A),
                ("198.51.100.128/25", "64521", SOURCE_A, SNAPSHOT_A),
                ("203.0.113.0/24", "64530,64531", SOURCE_A, SNAPSHOT_A),
                ("192.0.2.0/24", "64590", SOURCE_B, SNAPSHOT_B),
                ("192.0.2.128/26", "64599", SOURCE_B, SNAPSHOT_B),
            ]
            cursor.executemany(
                """
                INSERT INTO asn_prefix_origins
                    (prefix, origin_group, source_file, snapshot_at, ingested_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [(prefix, origin, source, snapshot, snapshot)
                 for prefix, origin, source, snapshot in origins],
            )
        self.connection.commit()
        self.connection.read_only = True
        with self.connection.cursor() as cursor:
            cursor.execute("SET LOCAL search_path = pg_temp, pg_catalog")
            cursor.execute("SET LOCAL statement_timeout = '3s'")

    def lookup(self, ip_address, source_file=SOURCE_A, org_source_file=ORG_SOURCE, *, full=False):
        with self.connection.cursor() as cursor:
            cursor.execute(
                self.lookup_sql,
                {"ip_address": ip_address, "source_file": source_file, "org_source_file": org_source_file},
            )
            self.assertIsNotNone(cursor.description, "Lookup must return a result set")
            columns = [column.name for column in cursor.description]
            self.assertEqual(len(columns), len(set(columns)), "Column names must be unique")
            self.assertTrue(set(FIELDS).issubset(columns), f"Required output fields: {FIELDS}; got {columns}")
            rows = []
            records = []
            for values in cursor.fetchall():
                record = dict(zip(columns, values))
                # psycopg may return inet/cidr as ipaddress objects or SQL text.
                for field in ("ip", "prefix"):
                    if record[field] is not None:
                        record[field] = str(record[field])
                self.assertIsInstance(record["asn_owners"], list)
                records.append(record)
                rows.append(tuple(record[field] for field in FIELDS))
            self.assertIsNone(cursor.nextset(), "Lookup must return one result set")
        return records if full else rows

    def test_01_combines_location_and_origin(self):
        self.assertCountEqual(
            self.lookup("192.0.2.1"),
            [("192.0.2.1", "ZZ", "Example City", "192.0.2.0/24", "64500", SNAPSHOT_A)],
        )

    def test_02_longest_prefix_excludes_broader_matches(self):
        self.assertCountEqual(
            self.lookup("198.51.100.129"),
            [("198.51.100.129", "YY", "Second City", "198.51.100.128/25", "64521", SNAPSHOT_A)],
        )

    def test_03_preserves_tied_origins_and_excludes_other_sources(self):
        self.assertCountEqual(
            self.lookup("192.0.2.129"),
            [("192.0.2.129", "ZZ", "Example City", "192.0.2.128/25", origin, SNAPSHOT_A)
             for origin in ("64501", "64502")],
        )

    def test_04_preserves_location_when_asn_is_missing(self):
        self.assertEqual(
            self.lookup("198.18.0.1"),
            [("198.18.0.1", "XX", "Location Only", None, None, None)],
        )

    def test_05_preserves_asn_and_as_set_when_location_is_missing(self):
        self.assertEqual(
            self.lookup("203.0.113.1"),
            [("203.0.113.1", None, None, "203.0.113.0/24", "64530,64531", SNAPSHOT_A)],
        )

    def test_06_preserves_input_when_both_matches_are_missing(self):
        self.assertEqual(
            self.lookup("198.19.0.1"),
            [("198.19.0.1", None, None, None, None, None)],
        )

    def test_07_uses_selected_source_and_its_timestamp(self):
        self.assertEqual(
            self.lookup("192.0.2.129", SOURCE_B),
            [("192.0.2.129", "ZZ", "Example City", "192.0.2.128/26", "64599", SNAPSHOT_B)],
        )

    def test_08_unknown_source_does_not_hide_geolocation(self):
        self.assertEqual(
            self.lookup("192.0.2.1", "missing-snapshot.pfx2as.gz"),
            [("192.0.2.1", "ZZ", "Example City", None, None, None)],
        )

    def test_09_geolocation_boundaries_are_inclusive_without_overextension(self):
        for ip_address in ("198.18.0.0", "198.18.0.255"):
            with self.subTest(ip=ip_address):
                self.assertEqual(
                    self.lookup(ip_address),
                    [(ip_address, "XX", "Location Only", None, None, None)],
                )
        for ip_address in ("198.17.255.255", "198.18.1.0"):
            with self.subTest(ip=ip_address):
                self.assertEqual(
                    self.lookup(ip_address),
                    [(ip_address, None, None, None, None, None)],
                )


    def test_10_ownership_and_provenance_are_separate_from_location(self):
        row, = self.lookup('192.0.2.1', full=True)
        self.assertEqual(row['country_code'], 'ZZ')
        self.assertEqual(row['snapshot_at'], SNAPSHOT_A)
        owner = dict(row['asn_owners'][0])
        self.assertEqual(datetime.fromisoformat(owner.pop('org_snapshot_at')), ORG_STAMP)
        self.assertEqual([owner], [{
            'asn': '64500', 'org_name': 'Current Owner', 'org_country_code': 'OM',
            'org_source_file': ORG_SOURCE}])

    def test_11_set_members_stay_nested_and_unmapped_member_survives(self):
        row, = self.lookup('203.0.113.1', full=True)
        self.assertEqual(row['origin_group'], '64530,64531')
        owners = row['asn_owners']
        self.assertEqual([o['asn'] for o in owners], ['64530','64531'])
        self.assertEqual(owners[0]['org_name'], 'Current Owner')
        self.assertTrue(all(value is None for key,value in owners[1].items() if key != 'asn'))

    def test_12_missing_organization_keeps_mapping_provenance(self):
        rows = self.lookup('192.0.2.129', full=True)
        row, = [r for r in rows if r['origin_group']=='64502']
        owner, = row['asn_owners']
        self.assertIsNone(owner['org_name'])
        self.assertIsNone(owner['org_country_code'])
        self.assertEqual(owner['asn'], '64502')
        self.assertEqual(owner['org_source_file'], ORG_SOURCE)

    def test_13_organization_snapshot_selection_and_unknown_source(self):
        row, = self.lookup('192.0.2.1', org_source_file=ORG_OTHER, full=True)
        self.assertEqual(row['asn_owners'][0]['org_name'], 'Other Snapshot Owner')
        self.assertEqual(row['snapshot_at'], SNAPSHOT_A)
        self.assertEqual(datetime.fromisoformat(row['asn_owners'][0]['org_snapshot_at']), SNAPSHOT_B)
        row, = self.lookup('192.0.2.1', org_source_file='missing', full=True)
        self.assertEqual(row['asn_owners'][0]['asn'], '64500')
        self.assertIsNone(row['asn_owners'][0]['org_name'])

    def test_14_missing_routing_returns_empty_owner_array(self):
        for ip in ('198.18.0.1','198.19.0.1'):
            row, = self.lookup(ip, full=True)
            self.assertEqual(row['asn_owners'], [])
        row, = self.lookup('192.0.2.1', source_file='missing', full=True)
        self.assertEqual(row['country_code'], 'ZZ')
        self.assertEqual(row['asn_owners'], [])

    def test_15_bound_organization_filename_is_literal(self):
        row, = self.lookup('192.0.2.1', org_source_file="x' OR TRUE --", full=True)
        self.assertIsNone(row['asn_owners'][0]['org_name'])


if __name__ == "__main__":
    unittest.main()
