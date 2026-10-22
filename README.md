# VPNLens

**A Python and PostgreSQL data pipeline for IP geolocation and internet routing intelligence.**

VPNLens turns downloaded IP datasets into structured, queryable PostgreSQL tables. It preserves raw records, cleans geolocation fields, expands routing-origin groups, and validates replacements inside transactions.

After loading data, SQL queries can retrieve an address's estimated location and its most specific matching routing origins. An ASN (Autonomous System Number) identifies a network; an IP prefix describes a block of addresses.

The long-term goal is to combine location, network operator, and VPN/proxy evidence for an IP address. **The current implementation provides local IPv4 geolocation and routing-prefix pipelines. VPN detection, the API, and the dashboard are not implemented yet.**

## At a glance

| Area | What the repository demonstrates |
| --- | --- |
| Data ingestion | Stream CSV and compressed prefix files through PostgreSQL `COPY` |
| Data modeling | Separate raw records from queryable geolocation and prefix-origin tables |
| Data quality | Reject empty loads, validate row counts, and inspect range boundaries and coverage |
| Transaction safety | Roll back failed replacements so previously committed data survives |
| IP lookups | Use indexed numeric ranges for geolocation and CIDR specificity for routing origins |
| Source traceability | Retain ASN source filename, snapshot timestamp, and ingestion timestamp |

**Stack:** Python, PostgreSQL, psycopg 3, python-dotenv, SQL. Python's standard library handles gzip files, file paths, timestamps, and IPv4 network validation. No external data-processing framework is required.

## What works today

- **Geolocation ingestion:** load a headerless, ten-column IP2Location LITE DB11 IPv4 CSV into `raw_ip2location`.
- **Geolocation transformation:** convert text placeholders (`-`) to SQL `NULL`, build inclusive `INT8RANGE` values, and replace `ip2location` atomically.
- **Geolocation lookup:** query a GiST-indexed range for the location associated with an IPv4 address.
- **ASN ingestion:** validate and stream a CAIDA RouteViews gzip snapshot into `raw_asn_prefixes`, replacing only the matching source file.
- **ASN transformation:** expand underscore-separated origin alternatives into `asn_prefix_origins`, while preserving comma-separated AS sets as text.
- **Routing lookup:** find the most specific matching prefix and return all equally specific origin groups.
- **Validation and recovery:** inspect data with SQL and verify rollback behavior with the documented manual test.

`api/main.py`, `dashboard/app.py`, and `ingestion/vpnapi.py` are empty placeholders. They do not expose a working application or VPN detection service.

### Current local data scale

Read-only database counts verified on **2026-10-22**:

| Table | Rows |
| --- | ---: |
| `raw_ip2location` | 2,996,298 |
| `ip2location` | 2,996,298 |
| `raw_asn_prefixes` | 1,125,729 |
| `asn_prefix_origins` | 1,130,627 |

These are stored range and prefix records, not counts of individual IPs or VPNs. Raw and transformed counts describe stages of the same source data and should not be added as unique coverage. Your counts may differ with another snapshot.

## Project diagram

This diagram shows the implemented local pipelines. Database setup and job execution are manual.

```mermaid
flowchart TD
    subgraph GEO["Geolocation pipeline"]
        G0["Downloaded IP2Location DB11 IPv4 CSV"] --> G1["ingestion/ip2location.py<br/>Stream with COPY"]
        G1 --> G2[("raw_ip2location")]
        G2 --> G3["transform_ip2location.py<br/>sql/transformers.sql"]
        G3 --> G4[("ip2location<br/>INT8RANGE + GiST index")]
        G4 --> G5["SQL geolocation lookup"]
    end

    subgraph ASN["Routing-prefix pipeline"]
        A0["Downloaded CAIDA RouteViews IPv4 gzip"] --> A1["ingestion/asn_prefixes.py<br/>Validate prefix and stream with COPY"]
        A1 --> A2[("raw_asn_prefixes<br/>Source and snapshot metadata")]
        A2 --> A3["transform_asn_prefixes.py<br/>sql/asn_transformers.sql"]
        A3 --> A4[("asn_prefix_origins<br/>CIDR + origin group")]
        A4 --> A5["SQL longest-prefix lookup<br/>Keep tied origins"]
    end

    G2 -.-> V["Read-only SQL profiling<br/>sql/analytics.sql<br/>sql/asn_analytics.sql"]
    G4 -.-> V
    A2 -.-> V
    A4 -.-> V
```

The pipelines are independent today. Combining their results into one IP enrichment response is a future step.

## Repository structure

```text
VPNLens/
├── README.md                    # Project overview, setup, usage, and limitations
├── .env.example                 # Local configuration template; no real credentials
├── .gitignore                   # Excludes local data, secrets, and environment artifacts
├── ingestion/
│   ├── __init__.py
│   ├── ip2location.py           # Stream DB11 CSV into the raw geolocation table
│   ├── asn_prefixes.py          # Validate and load one RouteViews snapshot
│   └── vpnapi.py                # Placeholder for future VPN/proxy ingestion
├── transform_ip2location.py     # Transactional geolocation transformation runner
├── transform_asn_prefixes.py    # Transactional transformation for one ASN source file
├── sql/
│   ├── schema.sql              # Geolocation tables and GiST range index
│   ├── transformers.sql        # Raw-to-clean geolocation SQL
│   ├── analytics.sql           # Geolocation quality checks and lookup plan
│   ├── cleaning.sql            # Read-only placeholder-cleaning preview
│   ├── asn_schema.sql          # Raw prefixes and expanded origin-group tables
│   ├── asn_transformers.sql    # Parameterized origin-group expansion
│   ├── asn_analytics.sql       # Origin profiling, previews, and prefix lookup
│   └── rollback_practice.sql   # Manual transaction-learning exercises
├── docs/
│   └── rollback-test.md         # Reproducible geolocation rollback test
├── rollback_practise.py         # Temporary-table rollback demonstration
├── api/
│   └── main.py                 # Placeholder; no API endpoints yet
├── dashboard/
│   └── app.py                  # Placeholder; no dashboard yet
└── data/                       # Local downloads; excluded from Git
    ├── IP2LOCATION-LITE-DB11.CSV
    └── routeviews-rv2-20261001-1200.pfx2as.gz
```

## Data model and design choices

| Table | One row represents | Important fields |
| --- | --- | --- |
| `raw_ip2location` | One source IPv4 geolocation range | Ten DB11 fields, including numeric range boundaries |
| `ip2location` | One cleaned geolocation range | Cleaned location fields and `ip_range INT8RANGE` |
| `raw_asn_prefixes` | One source prefix record in a snapshot | Address, prefix length, raw origin text, source file, timestamps |
| `asn_prefix_origins` | One origin alternative for one prefix in a snapshot | `prefix CIDR`, `origin_group TEXT`, source file, timestamps |

### Why keep raw and transformed tables?

Raw tables preserve the source representation for inspection and reprocessing. Transformed tables support lookups without discarding ambiguous routing information. Geolocation raw data is replaced on each load; ASN raw data retains different source files.

### Why store ranges instead of every IP?

A single range can describe many addresses. `int8range(ip_from, ip_to, '[]')` includes both source endpoints. PostgreSQL displays an integer range such as `100` through `200` as `[100,201)`, which preserves the same addresses. A GiST index supports containment lookups.

### Why is an origin group text rather than a single ASN integer?

RouteViews records may contain one origin, multiple origin alternatives, or AS sets. For example, the illustrative source value `64500,64501_64502` produces two groups:

```text
64500,64501
64502
```

The comma-separated AS set stays intact. The model does not pretend that every source record identifies one unambiguous ASN. A unique constraint on `(source_file, prefix, origin_group)` prevents duplicate transformed groups for a source.

### How do replacements stay safe?

- Geolocation ingestion truncates and reloads the raw table in one transaction. Empty loads fail.
- Geolocation transformation clears and rebuilds the clean table in one transaction. Empty raw input or unequal row counts fail before commit.
- ASN ingestion deletes only the selected `source_file`, validates the source, loads it, and checks stored counts in one transaction.
- ASN transformation replaces only the selected source file. It checks the expected number of expanded groups against the stored count before commit.

Exceptions escaping the psycopg connection context roll back the transaction. **Raw ingestion and transformation are separate jobs and separate transactions.** A successful ingestion does not imply its transformation has run.

## Run locally

### 1. Prepare Python and PostgreSQL

The implementation checks described below used Python 3.12 and PostgreSQL 18. You need a running PostgreSQL server, its `psql` client, and permission to create a development database.

```bash
git clone https://github.com/nishank23/VPNLens.git
cd VPNLens
python3 -m venv .venv
source .venv/bin/activate
python -m pip install 'psycopg[binary]' python-dotenv
```

On Windows, activate the virtual environment using the command appropriate for your shell. The commands below use a POSIX shell.

### 2. Configure your connection

```bash
cp .env.example .env
```

Edit `.env` with your PostgreSQL username, password, and database. The template contains:

```dotenv
DATABASE_URL=postgresql://YOUR_USER:YOUR_PASSWORD@localhost:5432/vpn_lens
IP2LOCATION_CSV=data/IP2LOCATION-LITE-DB11.CSV
```

Replace both credential placeholders; URL-encode special characters in passwords. For local passwordless authentication, use the connection URL appropriate for your PostgreSQL installation. Keep `.env` out of Git.

The Python scripts load `.env` automatically. For the `psql` commands in the same terminal, load these shell-compatible values first:

```bash
set -a
. ./.env
set +a
```

Use quoted values in `.env` when your shell requires them. Create `vpn_lens` through your SQL client or, if your local PostgreSQL role can create databases, run `createdb vpn_lens`. Create the database only once.

### 3. Obtain the input files

Download datasets from their official sources and extract the geolocation CSV into `data/`:

- **IP2Location LITE DB11, IPv4 CSV:** `data/IP2LOCATION-LITE-DB11.CSV`. The loader expects ten columns, in the order documented by DB11, with no header.
- **CAIDA RouteViews IPv4 prefix-to-AS snapshot:** `data/routeviews-rv2-20261001-1200.pfx2as.gz`. Keep it gzip-compressed.

```bash
mkdir -p data
```

`IP2LOCATION_CSV` can point to another compatible CSV. The ASN loader currently hardcodes the filename above in `ingestion/asn_prefixes.py`; using a different snapshot requires updating that path. Its filename must match `routeviews-rv2-YYYYMMDD-HHMM.pfx2as.gz`, because the loader derives the UTC snapshot timestamp from it.

Downloads are manual. Dataset files are not included in the repository. Review the source terms and attribution requirements before using or redistributing data.

### 4. Create the tables

**Initial setup only:** `sql/schema.sql` drops and recreates both geolocation tables. It destroys any existing data in those tables. `sql/asn_schema.sql` creates the ASN tables and is not safe to rerun unchanged against existing tables.

Confirm the target database first:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c 'SELECT current_database();'
```

Expected database: `vpn_lens`, or the dedicated development database you configured. Then initialize:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/schema.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/asn_schema.sql
```

### 5. Load and transform

Run these commands from the repository root:

```bash
python ingestion/ip2location.py
python transform_ip2location.py

python ingestion/asn_prefixes.py
python transform_asn_prefixes.py routeviews-rv2-20261001-1200.pfx2as.gz
```

Successful geolocation runs print `IP2Location data loaded successfully.` and `Transformation committed successfully.` The ASN loader prints snapshot metadata and row counts. The ASN transformer prints `Committed ... origin groups from ... raw rows for ...` after its transaction commits.

Row counts depend on the downloaded snapshot. ASN transformation can produce more rows than ingestion because one source row may contain multiple origin alternatives.

### 6. Check the results

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c 'SELECT COUNT(*) AS raw_rows FROM raw_ip2location; SELECT COUNT(*) AS clean_rows FROM ip2location;'
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c 'SELECT source_file, COUNT(*) AS origin_groups FROM asn_prefix_origins GROUP BY source_file;'
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/analytics.sql
```

Inspect the terminal output: geolocation raw and clean counts should be equal and nonzero. Review the boundary, placeholder, overlap, and gap checks against the intended source coverage. SQL diagnostics report issues; they do not automatically abort an ingestion job.

`sql/asn_analytics.sql` contains origin profiling and prefix lookup examples. Run selected queries in a SQL editor: one preview intentionally returns every expanded record and may produce over a million rows for a full source file.

## Example IP lookups

Run these SQL examples after loading data. Their results depend on your snapshot; they are not fixed claims about the example address.

### Geolocation

```sql
SELECT country_code, country_name, region_name, city_name, time_zone
FROM ip2location
WHERE ip_range @> ('8.8.8.8'::inet - '0.0.0.0'::inet);
```

The subtraction converts an IPv4 address into its numeric value for range containment.

### Most specific routing prefix

```sql
WITH matching_prefixes AS (
    SELECT
        prefix,
        origin_group,
        DENSE_RANK() OVER (ORDER BY masklen(prefix) DESC) AS specificity_rank
    FROM asn_prefix_origins
    WHERE source_file = 'routeviews-rv2-20261001-1200.pfx2as.gz'
      AND '8.8.8.8'::inet <<= prefix
)
SELECT prefix, origin_group
FROM matching_prefixes
WHERE specificity_rank = 1
ORDER BY prefix, origin_group;
```

Longer prefixes describe more specific networks. `DENSE_RANK` keeps every origin group attached to the most specific match, rather than choosing one arbitrarily. No match means the selected snapshot has no matching record.

## Validation and rollback evidence

The repository includes [read-only geolocation checks](sql/analytics.sql), [ASN profiling and lookup examples](sql/asn_analytics.sql), and a [manual transformation rollback test](docs/rollback-test.md). The rollback guide uses a separate test database and explains the expected error and preserved data.

During the documentation update on **2026-10-22**, the existing scripts were exercised against synthetic fixtures in a disposable PostgreSQL 18 cluster. The checks passed for:

- Geolocation ingestion, placeholder cleaning, and inclusive range boundaries.
- Empty geolocation ingestion and transformation failures preserving previously committed data.
- ASN reruns maintaining counts and preserving other source snapshots.
- AS-set preservation and longest-prefix matching with tied origin groups.
- Malformed or empty ASN input, missing transformation sources, and duplicate-origin failures rolling back safely.
- The temporary-table rollback demonstration preserving its committed fixture.

These were local integration checks, not a committed automated test suite, production benchmark, or end-to-end API/dashboard test. The fixture checks did not reload or modify the normal project database.

## Limitations and next milestones

| Area | Current boundary / next step |
| --- | --- |
| Address family | The implemented loaders and numeric geolocation model target IPv4; IPv6 ingestion is not implemented |
| VPN/proxy detection | Add one dedicated IP/range intelligence source; a hosting ASN alone does not establish VPN use |
| Organization enrichment | Add an ASN-to-organization dataset; organization country and IP geolocation are different facts |
| Unified lookup | Combine independently matched geolocation, routing, organization, and VPN evidence |
| Performance | Geolocation has a GiST index; ASN lookup has no dedicated containment index or published benchmark |
| Automation | Add configurable snapshot selection, scheduled downloads, and job orchestration |
| Application layer | Implement API and dashboard after the underlying data model is ready |
| Quality gates | Expand automatic validation; many existing SQL checks require manual inspection |

The intended enrichment scope uses four logical datasets: geolocation, prefix-to-ASN, ASN-to-organization, and one VPN/proxy intelligence source. Only the first two are ingested today. No commercial VPN provider has been integrated.

IP geolocation is an estimate. Routing origins reflect the selected snapshot. Neither identifies a person's exact location, and a VPN exit's location would describe the exit address. Future VPN classification must retain source and observation time; missing evidence must not be presented as proof that an IP is not a VPN.

## Data sources and attribution

- VPNLens uses the [IP2Location LITE database](https://www.ip2location.com) for IP geolocation. [DB11 fields and download information](https://lite.ip2location.com/database/db11-ip-country-region-city-latitude-longitude-zipcode-timezone).
- Routing input: [CAIDA Routeviews Prefix to AS mappings Dataset for IPv4 and IPv6](https://www.caida.org/catalog/datasets/routeviews-prefix2as/). The current loader uses the IPv4 RouteViews snapshot named above. Follow CAIDA's acceptable-use and citation requirements.

Dataset licenses are independent of this repository's code. This repository does not currently include a code license file.
