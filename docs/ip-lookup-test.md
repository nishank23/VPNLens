# IP lookup acceptance tests

These tests execute `sql/ip_lookup.sql` through psycopg with `ip_address`,
`source_file`, and `org_source_file` parameters. They test the combined lookup contract, not a rewritten
Python implementation of the SQL. The project owner owns the lookup query and
its data-model and failure-handling decisions.

## Acceptance criteria

- Return one result set containing `ip`, `country_code`, `city_name`, `prefix`,
  `origin_group`, and `snapshot_at`. Additional uniquely named columns are allowed.
- Match geolocation with inclusive numeric range containment.
- Select only the longest matching prefix within the requested source file.
- Preserve every tied origin group and comma-separated AS-set text.
- Return the input IP even when geolocation, ASN, or both have no match. Missing
  lookup fields are `NULL`.
- Retain the selected source's snapshot timestamp and exclude other sources.

Result row order is not part of this contract. The suite uses valid IPv4 host
addresses only; invalid-input policy and performance tuning remain outside this
milestone's current tests.

## Run locally

Use the project's Python environment with psycopg 3 installed. Create a dedicated
test database once, using your local PostgreSQL connection settings:

```bash
createdb vpn_lens_lookup_test
```

From the repository root, supply its connection URL explicitly:

```bash
VPNLENS_TEST_DATABASE_URL='postgresql://YOUR_USER:YOUR_PASSWORD@localhost:5432/vpn_lens_lookup_test' \
  python3 -m unittest discover -s tests -p 'test_ip_lookup.py' -v -f
```

Replace the credential placeholders and URL-encode special characters in
passwords. For passwordless local authentication, use your installation's
appropriate connection URL. The test database does not need the project schema
or downloaded datasets.

The suite deliberately does not load `.env` or fall back to `DATABASE_URL`.
Each test creates connection-local temporary tables with synthetic data and
switches to a read-only transaction before executing the lookup. Connections
close after each test, removing their temporary tables. No normal ingestion or
transformation runner is invoked.

## Read the result

The terminal lists fifteen test methods. A complete passing run ends with `OK`,
without skipped tests. The boundary test also exercises four address cases.
`-f` stops at the first failure; remove it to inspect all failures.

If PostgreSQL reports `cannot insert multiple commands into a prepared statement`,
the SQL file still contains separate statements. Combine the logic into one
parameterized statement before the remaining behavioral checks can pass.

No tests have been marked as passing merely because separate geolocation and
ASN queries execute successfully. The milestone is complete only after the
combined query passes these checks and receives the project owner's final review.

## Enriched organization contract

The required root fields also include `asn_owners`, always a JSON array. Each
origin group stays intact, while its members are ordered numerically inside the
array. Member objects include `asn`, `org_name`, `org_country_code`,
`org_snapshot_at`, and `org_source_file`. Unknown member mappings retain the ASN
with null metadata. Missing organizations retain any available ASN-mapping
provenance. Missing routing data produces an empty owner array.

The six added tests exercise organization provenance distinct from routing and
location, nested AS-set membership, missing ASN mappings and organization rows,
independent organization snapshot selection, empty arrays, and bound filenames.
JSON timestamp assertions compare instants rather than display offsets.
