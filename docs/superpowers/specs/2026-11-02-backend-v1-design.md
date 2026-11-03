# VPNLens local backend v1

Date: 2026-11-02
Status: Approved by the user on 2026-11-02. Implementation and local verification complete; final user review pending.

## Intent and constraints

Finish a zero-budget, local IPv4 intelligence backend that a frontend can use later.
Keep PostgreSQL, the reviewed lookup SQL, nested ASN owners, and local public
VPN/Tor evidence. The user retains architecture, data-model, core-SQL,
failure-policy, and final-review decisions. Codex implements routine Python,
API, configuration, logging, tests, and documentation against this contract.
No frontend, paid sources, public deployment, or GitHub push in this milestone.

## Verified starting point

The active implementation is /Users/nishankbansal/Documents/VPNLens on main.
The chat worktree is older and must not replace the active checkout.
Geolocation, routing, organization ownership, evidence ingestion, and a combined
CLI lookup exist. The VPN/Tor scheduler exists. api/main.py is empty.
There is no dependency manifest or CI workflow. The routing loader hardcodes
an October filename. Geolocation and CAIDA downloads are manual. Existing schema
scripts include destructive or non-repeatable statements. README contains stale
claims that evidence is still planned. Existing uncommitted work must be preserved.

## Approaches

1. Complete the local backend plus refresh workflow: selected by the user.
   This supplies an API and repeatable data operations before frontend work.
2. API first, refresh later: smaller immediate slice, but leaves the dataset
   lifecycle manual. The user selected the first approach.

Builder proposal: use FastAPI and uvicorn for the HTTP layer, psycopg for database
access, and the existing Python modules for ingestion. Keep a single application;
no queue, Redis, microservices, or external detection API.

## API contract

- GET /health/live: process liveness; no database request or secret output.
- GET /health/ready: bounded database/schema check and lookup-source availability.
  Return 503 for an unusable database or missing core lookup datasets. Stale or
  absent security feeds are reported as degraded rather than as non-VPN evidence.
- GET /v1/sources: loaded routing/organization filenames and snapshot dates,
  geolocation availability, and evidence source/check-age information. Report
  unknown publication dates honestly; do not invent geolocation provenance.
- GET /v1/lookup/{ip_address}: validate one IPv4 host before querying PostgreSQL.
  Reject IPv6, CIDR inputs, malformed values, and unavailable explicitly selected
  snapshots with a clear 4xx response. Missing server-side default snapshots or
  unavailable database return 503. Unexpected errors return a generic 500;
  database details and credentials never appear in responses.

The lookup response is an object with ip and results. Results retain the current
row shape, tied longest-prefix origin groups, nested asn_owners, and security.
The existing CLI remains compatible. No-match lookups return 200 with the
existing input-preserving result and unknown evidence, not a false VPN verdict.
Optional source_file and org_source_file parameters select historical snapshots.
Without overrides, resolve routing and ownership snapshots independently from
successfully loaded data, ordered by snapshot date and filename for stable ties.
Expose the selected filenames in response metadata. An empty owner array is a
valid partial result; unavailable ownership snapshot data is a readiness issue.

Set connection and statement timeouts. Use read-only lookup transactions. Bind
all SQL parameters. No per-request network downloads. Configure CORS through an
explicit allowlist, empty by default. Bind the development server to localhost.
Public hosting, authentication, and rate limiting belong to a later milestone.

## Setup and configuration

Provide a dependency manifest, .env.example, a non-destructive initialization
command, and concise local startup instructions. Initialization creates the
reviewed tables and indexes without dropping data. Reruns preserve rows. Check
existing table compatibility and stop with an actionable error rather than
silently migrating incompatible tables. Existing SQL models and lookup logic
remain unchanged; any needed core-SQL changes return to the user for review.
Never print DATABASE_URL credentials. Tests require a dedicated database and
must never fall back to the project database from .env.

## Refresh workflow and proposed failure policy

Provide one CLI with explicit dataset selection, plus an all-datasets mode.
Reuse the evidence refresh implementation and its 11-source atomic publication.
Discover dated IPv4 routing and organization snapshots from the existing official
CAIDA locations. Accept only expected dated filenames; validate gzip and source
records. Cache downloads using temporary files and atomic rename. Skip unchanged
successful snapshots without reloading. Support explicit local files for offline
operation and reproducibility. Do not retain the October filename in code.

For routing, loading raw rows and transforming the selected source must succeed
in one transaction before it becomes a default candidate. Reuse the user's
transformation SQL. Organization loading already replaces both sections in one
transaction. For geolocation, raw replacement and transformation likewise share
one transaction, preserving previously usable rows on failure.

IP2Location automatic downloading is optional and requires a user-supplied,
authorized download URL or configured local CSV/ZIP. Never invent credentials,
bypass access requirements, or claim automatic geo updates without that input.
Without automatic-download configuration, retain working geolocation data and
report manual-update-required. Validate ZIP membership and avoid unsafe extraction.

Each dataset commits independently; there is no cross-dataset atomic snapshot.
A failed dataset stops the refresh command with nonzero status. Earlier completed
datasets remain committed; the failing dataset retains its last good state.
Incomplete candidates never become selected defaults. Prevent overlapping
publication using database locks, retain historical CAIDA/evidence snapshots,
and avoid automatic history deletion. Preserve the existing all-or-nothing
11-source evidence policy and the listed/unknown distinction.

Extend scheduling only after the refresh command passes tests. Reuse macOS
LaunchAgents locally; document a portable scheduler command. Keep the existing
job intact until replacement is ready; avoid duplicate refresh jobs. Show logs,
last-success information, and manual-update-required status. Scheduling on a
sleeping/offline Mac is not an always-on deployment.

## Acceptance criteria and stop condition

1. A fresh test database can initialize, load fixtures, and serve lookups through
   HTTP using documented commands. Initialization reruns preserve existing data.
2. API tests cover valid lookup, tied origins, missing metadata, listed/unknown/
   stale evidence, historical selection, invalid input, timeout/unavailable DB,
   readiness, and credential-safe errors. CLI behavior remains compatible.
3. Refresh tests prove latest-file selection, unchanged skips, malformed/truncated
   download rejection, safe ZIP handling, overlapping-run handling, and rollback
   that preserves the last usable dataset. External-download tests use fixtures;
   real-source checks are reported separately.
4. Existing ingestion and SQL tests pass in disposable PostgreSQL. CI uses a
   dedicated PostgreSQL service with no production secrets or live downloads.
5. README documents actual features, response examples, architecture, setup,
   refresh limitations, tests, and source attribution. API has generated OpenAPI
   documentation for the later frontend.
6. Perform a local HTTP smoke test and report exactly which real datasets and
   refresh paths were verified. Do not present mock checks as live-source proof.
7. Stop at the tested local backend. Summarize changed files, test results,
   unresolved data-access limitations, and final-review items. Do not push.

## Decisions to review

The user selected the scope. FastAPI, endpoint/response shape, independent latest
snapshot selection, non-destructive initialization, independent dataset commits,
fail-fast refresh, and optional credentialed geolocation downloads are builder
proposals in this document, not previously approved architecture decisions.

## Pre-implementation verification

On 2026-11-02, all 44 existing automated tests passed in a disposable PostgreSQL
cluster. The complete organization snapshot also loaded there: 98,447
organizations and 122,668 ASN records, with spot checks for ASNs 15169, 28885,
and 206350. No project database was changed by these checks. A fresh builder
review found no important unanswered planning questions in this design.
