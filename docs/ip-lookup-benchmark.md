# IP lookup performance baseline

The initial ASN observations were recorded on 2026-10-29. Combined-query plans
were supplied on 2026-10-30 during local development. Execution time and planning time are separate PostgreSQL measures;
neither includes the Python connection setup or total CLI duration.

## ASN lookup: before and after the prefix index

Query reference: the final `EXPLAIN (ANALYZE, BUFFERS)` statement in
[`sql/asn_analytics.sql`](../sql/asn_analytics.sql).

Inputs:

- IPv4 address: `185.186.206.1`.
- Source file: `routeviews-rv2-20261001-1200.pfx2as.gz`.
- Snapshot timestamp: `2026-10-01 12:00:00+00`.
- Observed output count: two origin groups in each pasted plan.

| Observation | Access method | Execution (ms) | Planning (ms) | Shared hit | Shared read |
| --- | --- | ---: | ---: | ---: | ---: |
| First supplied run, before index | Parallel sequential scan | 141.547 | 5.514 | 291 | 13,677 |
| Supplied repeat run, before index | Parallel sequential scan | 61.618 | 0.169 | 1,128 | 12,831 |
| First supplied run using index | GiST index scan | 7.998 | 6.044 | 308 | 1 |

The developer also reported repeated indexed runs around **4 ms**. Exact plans,
planning times, and buffer counts were not supplied for those runs, so that value
is approximate and is not another fully recorded plan.

The pasted plans changed from `Parallel Seq Scan` to
`Index Scan using idx_asn_prefix_origins_prefix`. The indexed plan used:

```text
Index Cond: ((prefix)::inet >>= '185.186.206.1'::inet)
```

Before indexing, the scan rejected about 1.13 million rows in total. After
indexing, PostgreSQL used prefix containment to locate matching candidates.
The recorded execution time fell from the 61.618 ms repeat baseline to 7.998 ms,
about 7.7 times faster for those two observations. Cache state and other
run-to-run effects also influence these timings; these are local observations,
not a controlled production benchmark.

Buffer counts above come from the top execution node. They count buffer
accesses, not result rows or unique pages. A shared read does not by itself prove
physical disk I/O, because the operating system may already cache that page.

## Reproduce the index definition

The definition is saved after table creation in
[`sql/asn_schema.sql`](../sql/asn_schema.sql):

```sql
CREATE INDEX IF NOT EXISTS idx_asn_prefix_origins_prefix
ON asn_prefix_origins
USING GIST (prefix inet_ops);
```

The local database already has the index used in the supplied indexed plan.
Saving this statement in the schema makes it available during fresh setup.
Do not rerun the complete table-creation script just to repeat a benchmark.

## Combined geolocation and ASN lookup

**Status: lookup milestone complete.** Three local execution plans and the
matching result values are recorded. The user approved final code review on
2026-10-30. These plans were supplied on 2026-10-30 for the combined lookup
in [`sql/ip_lookup.sql`](../sql/ip_lookup.sql). The original plans are preserved
in [`benchmarks/ip-lookup-combined-2026-10-30.txt`](benchmarks/ip-lookup-combined-2026-10-30.txt).
They were supplied by the developer, not independently rerun for this record.

Inputs were `185.186.206.1` and
`routeviews-rv2-20261001-1200.pfx2as.gz`. The combined query filters by source
filename. The earlier ASN-only benchmark also filters explicitly by snapshot
timestamp; those timings describe a different query and are not a measured
before/after speedup for this combined lookup.

| Combined lookup run | Execution (ms) | Planning (ms) | Top-node shared hit | Top-node shared read | Returned rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 13.280 | 11.764 | 308 | 0 | 2 |
| 2 | 9.494 | 8.312 | 308 | 0 | 2 |
| 3 | 3.791 | 0.276 | 305 | 0 | 2 |

All three plans show:

- `Index Scan using idx_ip2location_ip_range`, returning one geolocation row.
- `Index Scan using idx_asn_prefix_origins_prefix`, returning two ASN rows.
- `DENSE_RANK` with the rank-one filter, followed by two final result rows.
- Two `Nested Loop Left Join` nodes, with a one-row input.
- No shared reads reported during execution. Zero-valued buffer counters are
  omitted from the supplied plans; the table records them as zero.

These observations confirm index use for this input. They do not establish
performance across other IPs, a cold cache, concurrent traffic, or Python CLI
latency. Later runs were faster even though all three reported shared-buffer
hits without shared reads. These plans do not establish why the timings varied.
Planning and execution times remain separate. Do not add buffer counts from
parent and child nodes, because the parent totals include child activity.

### Repeat the measurement

The recorded plans above describe the earlier geolocation/routing query, before
organization enrichment. They are not benchmarks of the current enriched SQL.
For a new measurement:

1. Open a scratch SQL-editor tab and copy only the combined statement, from
   `WITH input AS (` through its final semicolon.
2. Replace every `%(ip_address)s` with `'185.186.206.1'` and every
   `%(source_file)s` with `'routeviews-rv2-20261001-1200.pfx2as.gz'`. Also replace
   `%(org_source_file)s` with `'20261001.as-org2info.txt.gz'`.
3. Add `EXPLAIN (ANALYZE, BUFFERS)` immediately before `WITH input AS (`.
4. Select the complete statement, including `EXPLAIN`, and execute it three
   times without changing the query, inputs, or indexes between runs.
5. Save each full plan and record the same metrics as the table above. Keep the first observation
   separate from repeated observations; do not assume either cache state.

Inspect whether the plan uses `idx_ip2location_ip_range` and
`idx_asn_prefix_origins_prefix`. Either index or bitmap access may appear;
record the actual plan rather than forcing an access method.

### Result-value check

The developer supplied the following output on 2026-10-30 after running the
combined query without `EXPLAIN`:

```json
[
  {
    "ip": "185.186.206.1",
    "country_code": "OM",
    "city_name": "Muscat",
    "prefix": "185.186.206.0/24",
    "origin_group": "206350",
    "snapshot_at": "2026-10-01 14:00:00+02"
  },
  {
    "ip": "185.186.206.1",
    "country_code": "OM",
    "city_name": "Muscat",
    "prefix": "185.186.206.0/24",
    "origin_group": "28885,206350",
    "snapshot_at": "2026-10-01 14:00:00+02"
  }
]
```

The supplied output passes the expected result-value check for this input:

- Both rows contain the six required output fields.
- Both preserve the requested IP, `185.186.206.1`, and return the containing
  prefix `185.186.206.0/24`.
- Both return `OM` and `Muscat` from the loaded geolocation dataset.
- The two distinct origin groups, `206350` and `28885,206350`, are preserved.
  The comma-separated group remains intact as stored.
- Both timestamps represent `2026-10-01 12:00:00+00`; displaying that instant as
  `2026-10-01 14:00:00+02` does not change the selected snapshot.

This records and checks the developer-supplied output; no project-database
query was rerun while updating this document. It does not independently verify
IP geolocation against an external source.

The three-run performance measurement and this result-value check are complete
for the selected input. The user completed final code review and approved the
lookup milestone on 2026-10-30. This closes the combined geolocation/routing
lookup milestone; it does not establish VPN detection or API/dashboard support.
Retain the placeholders in the saved parameterized query used by Python and the
acceptance tests.
