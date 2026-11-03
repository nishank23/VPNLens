"""Each integration test owns an isolated schema in the dedicated test DB."""

import gzip
import os
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from ingestion.asn_organizations import ingest_asn_organizations
from vpnlens.refresh import load_geolocation, load_routing
from vpnlens.setup import initialize


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        self.base = os.environ.get("VPNLENS_TEST_DATABASE_URL")
        if not self.base:
            raise RuntimeError("Set VPNLENS_TEST_DATABASE_URL; no project database fallback")
        self.schema = "v1_test_" + uuid4().hex
        with psycopg.connect(self.base, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        self.dsn = make_conninfo(self.base, options=f"-c search_path={self.schema},public")
        initialize(self.dsn)
        self.temp = tempfile.TemporaryDirectory(prefix="vpnlens-v1-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def drop_schema(self):
        with psycopg.connect(self.base, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema))
            )

    def routing(
        self,
        text="192.0.2.0\t24\t64500\n",
        name="routeviews-rv2-20261001-1200.pfx2as.gz",
    ):
        path = self.folder / name
        with gzip.open(path, "wt") as output:
            output.write(text)
        return path

    def organization(self):
        path = self.folder / "20261001.as-org2info.txt.gz"
        with gzip.open(path, "wt") as output:
            output.write(
                "# format:org_id|changed|org_name|country|source\nORG||Example Network|JP|TEST\n"
                "# format:aut|changed|aut_name|org_id|opaque_id|source\n"
                "64500||EXAMPLE|ORG||TEST\n64501||SECOND|ORG||TEST\n"
            )
        return path

    def geo(self, text="3221225984,3221226239,ZZ,Example,Region,City,0,0,-,+00:00\n"):
        path = self.folder / "geo.csv"
        path.write_text(text)
        return path

    def seed(self):
        routing = self.routing(
            "192.0.2.0\t24\t64500\n192.0.2.128\t25\t64501\n192.0.2.128\t25\t64501,64502\n"
        )
        with psycopg.connect(self.dsn) as connection:
            load_routing(routing, connection)
            load_geolocation(self.geo(), connection)
            ingest_asn_organizations(self.organization(), connection=connection)
        return routing
