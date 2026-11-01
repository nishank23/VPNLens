# Load CAIDA ASN organization snapshots

The user-owned `sql/asn_org_schema.sql` defines `raw_asn_mappings` and
`raw_org_mappings`. The loader expects those tables to exist; it does not create
or alter them. For a fresh database, execute that schema once in your SQL editor.
If the tables already exist with timestamp-typed `changed` columns, editing the
schema file alone does not migrate them: inspect the existing database schema
before loading. Do not drop populated tables to apply this file.

From the repository root, after setting `DATABASE_URL` in `.env`:

```bash
python3 -m ingestion.asn_organizations data/20261001.as-org2info.txt.gz
```

The input must use the dated `YYYYMMDD.as-org2info.txt.gz` filename. The loader
derives `snapshot_at` as UTC midnight on that date; midnight is a storage
convention for the daily snapshot, not an observation time supplied by CAIDA.
`changed` remains the original text, including empty strings. Names and opaque
identifiers also retain empty strings so the raw NOT NULL text columns can
preserve valid blanks. Registry `source` and downloaded `source_file` remain
separate fields.

The loader streams the same gzip twice to COPY organization and ASN records
without buffering the full dataset. It replaces records for the selected
filename in one transaction. Both sections must be nonempty, field counts and
required identifiers must be valid, and stored counts must match parsed counts.
Database uniqueness constraints reject duplicate identifiers. Any exception
rolls back both replacements; other filenames are preserved. Unresolved
organization references remain in raw storage because the schema has no foreign
key. The ownership lookup preserves ASN records with missing organization information.

Successful runs log committed counts to stderr and print a JSON summary to
stdout. Errors propagate with a nonzero exit status. The loader adds no automatic download, retry policy, transformation, or API.

## Tests

Use a dedicated PostgreSQL test database:

```bash
VPNLENS_TEST_DATABASE_URL='postgresql://YOUR_USER@localhost/vpn_lens_lookup_test' \
  python3 -m unittest discover -s tests -p 'test_asn_organizations.py' -v
```

Tests do not read `.env` or fall back to `DATABASE_URL`. Each integration test
creates a uniquely named schema and removes that schema afterward. Checks cover
raw blanks, section formats, metadata, reruns, snapshot isolation, malformed or
empty input, duplicate identifiers, corrupt gzip rollback, and unresolved raw
references. The existing IP lookup tests remain separate regression checks.

Source documentation and downloads:
https://publicdata.caida.org/datasets/as-organizations/

The CAIDA AS Organizations Dataset, October 2026:
https://www.caida.org/catalog/datasets/as-organizations/

## Verification recorded on 2026-10-31

All 18 tests passed in a disposable PostgreSQL cluster: nine organization loader
and parser tests plus nine existing IP lookup regression tests. A full October
source load in that cluster produced 98,447 organization and 122,668 ASN rows.

The reviewed schema was then applied to the normal project database after
confirming both new tables were absent. The October file loaded successfully;
read-only checks confirmed the same counts and the owner/country mappings for
ASNs 15169, 28885, and 206350. Existing geolocation and routing tables were not
modified by this loader. The standalone organization lookup described below is now implemented.
Ownership is now integrated into the combined IP lookup. The API remains unimplemented.

## Run the standalone organization lookup

The user-owned `sql/asn_org_lookup.sql` accepts `asn` and `source_file` as
psycopg parameters. The runner binds them and executes a read-only transaction:

```bash
python3 lookup_asn_org.py 206350 20261001.as-org2info.txt.gz
```

The script loads `.env` from its own repository root and returns a JSON array.
Its output fields are `aut`, `aut_name`, `org_name`, `country`, `source`, and
`snapshot_at`. `country` is the organization country code; `source` is the
organization registry source. Missing organization records preserve the ASN with
null organization fields. An unknown ASN or selected filename returns `[]`.
This describes the saved SQL's behavior, not a proposed HTTP error policy.

`lookup_asn_org(asn, source_file, database_url=...)` also accepts an explicit
connection string for controlled execution. Normal CLI execution uses
`DATABASE_URL`. Database errors propagate as nonzero exits. There are no new
runtime dependencies.

To run all current parser, loader, and lookup regression tests:

```bash
VPNLENS_TEST_DATABASE_URL='postgresql://YOUR_USER@localhost/vpn_lens_lookup_test' \
  python3 -m unittest discover -s tests -v
```

On 2026-10-31, all 25 tests passed in disposable PostgreSQL. The seven new
ownership checks cover output fields, missing organizations, snapshot-scoped
joins, unknown input, bound parameters, read-only transactions, and CLI JSON
from outside the repository. Timestamp checks compare instants so equivalent
UTC/local displays are accepted.

A read-only CLI check against the loaded project snapshot returned ASN 206350,
AS name OMREN, organization Oman Research and education Network (OMREN), country
OM, and registry RIPE. Its `2026-10-01 02:00:00+02:00` display equals the stored
snapshot instant `2026-10-01 00:00:00+00:00`. No project data was changed by the
lookup validation. Combined IP enrichment now retains each origin group with a nested owner array.

## Combined IP lookup

```bash
python3 lookup_ip.py 185.186.206.1 routeviews-rv2-20261001-1200.pfx2as.gz 20261001.as-org2info.txt.gz
```

The third argument selects the organization snapshot independently of the routing
file. Member objects expose organization source/snapshot metadata. The root
routing timestamp is preserved. See `ip-lookup-test.md` for acceptance criteria.

## Final enriched verification (2026-11-01)

All 31 automated tests passed in disposable PostgreSQL: fifteen combined IP
lookup checks, nine organization parser/loader checks, and seven standalone
organization lookup checks. The full October file also loaded in that disposable
cluster with the expected 98,447 organization and 122,668 ASN records.

A read-only run of the final three-argument IP CLI against the project database
returned two origin-group rows for 185.186.206.1, with owner counts one and two,
OM/Muscat geolocation, the routing timestamp, and independent organization
source/snapshot metadata. The normal project database was not modified during
these final checks. Historical benchmark timings describe the earlier query;
enriched-query latency has not yet been benchmarked.
