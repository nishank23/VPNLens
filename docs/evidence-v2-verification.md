# Extended evidence SQL and runtime fixture verification

This document records the additive SQL contracts and the opt-in runtime
integration. The earlier SQL/runtime checkpoints below use disposable PostgreSQL 18 or offline
fixtures. A separately dated live-database checkpoint follows them; neither
fixture tests nor feed association checks establish actual VPN/proxy operation.

## Physical model and SQL boundary

`sql/evidence_v2_schema.sql` creates immutable registry versions, committed source
configurations, content-addressed snapshots, snapshot/record-key indicators,
a singleton committed registry pointer, enabled-source active pointers, immutable
measurements, and separate immutable approved/rejected reviews. The only history
renewal is a monotonic successful snapshot `checked_at` update; original
`fetched_at`, publisher time, metadata, and records remain unchanged. All source
pointer replacements and registry activation share one transaction. Deferred
checks reject an incomplete enabled source set at commit. Empty DNS withdrawals
and an all-disabled registry are valid. No historical rows are pruned.

Indicators use `cidr`; `evidence_v2_indicators_network_gist` uses GiST `inet_ops`.
The database rejects IPv6, /0, and CIDRs overlapping the same nonpublic/special
IPv4 blocks rejected by `evidence_contract.public_network`. Uniqueness is
(snapshot, deterministic record key), preserving overlaps, providers, and separate
hostnames. Metadata is bound to the committed source configuration. Python and
PostgreSQL digest parity includes the provider string `Fixture é 🌐`.

The five parameterized files each contain one statement, accept one
`%(payload)s::jsonb` parameter, and return one JSON object named `result`:

- `validate`: schema version 1 plus catalog compatibility. The immutable manifest
  compares exact column types/nullability/defaults, constraints, valid indexes,
  enabled triggers, and contract function definitions; this is not a version-only
  check. Explicit reinitialization rejects existing incompatible structures.
- `publish`: the complete immutable `prepare_batch` JSON envelope. Returns
  `status` (`loaded`/`unchanged`), `registry_sha256`, and public `sources`.
- `lookup`: `{ "ip_address": "8.8.8.8" }`; returns deterministic `matches` from
  enabled active snapshots plus approved observations, retaining expired history.
- `sources`: `{}`; returns scheduled public `sources` and `enabled_source_ids`.
  Observations do not inflate scheduled source counts. Counts describe records
  and networks, not the number of addresses inside CIDRs.
- `observe`: the normalized publication shape below; returns `status`
  (`published`/`unchanged`), `observation_id`, and original `expires_at`.

`observation_payload(record, profile, review=None, now=None)` validates original
private artifacts using the approved recorder contracts and builds:

```json
{
  "measurement": {
    "observation_id": "canonical UUID",
    "observation_sha256": "SHA256 of canonical original measurement",
    "profile_sha256": "reviewed profile hash",
    "source_id": "observation-<profile_id>",
    "family": "measured_exit",
    "record_key": "same observation hash",
    "network": "8.8.8.8/32",
    "provider": "operator reviewed provider",
    "basis": "exit_observation",
    "role": "exit",
    "method": "system_tunnel | explicit_http_proxy | browser_import",
    "service_category": "vpn | proxy",
    "source_url": "credential-free HTTPS documentation URL",
    "content_sha256": "same observation hash",
    "observed_at": "original last actual measurement timestamp",
    "expires_at": "observed_at plus exactly 24 hours",
    "connection_type_claim": "residential | mobile | datacenter | unknown"
  },
  "review": {
    "observation_id": "matching UUID",
    "observation_sha256": "matching observation hash",
    "review_state": "approved | rejected",
    "reviewed_at": "original separate review timestamp",
    "reviewer_sha256": "hash of private operator label"
  }
}
```

`review: null` stores a pending measurement without a public positive. The SQL
boundary checks normalized identity, immutable retries/conflicts, review binding,
measurement time, and derived expiry. Exact expiry rejects new approval; a later
check/import/approval never renews measurement expiry. Raw receipts, baseline IP,
proxy credentials/environment references, raw artifact paths, and operator labels
are absent from public SQL projections. Proxy observations retain category
`proxy`; network inference is not projected as a legacy VPN server positive.

`publish_contract` permits only publish/observe, connects with a five second
connection timeout, sets a five second lock timeout, takes nonblocking transaction
advisory lock `872410052` (shared with legacy evidence ingestion), validates the
catalog, then executes the mutation in one outer transaction. Lock contention or
any validation/publication error rolls everything back. Lookup and sources run
successfully inside repeatable-read read-only transactions.

Ordinary `initialize()` remains the base compatibility path. Extended DDL is
explicitly selected using `python -m vpnlens.setup --extended-evidence` or
`initialize_extended(database_url)`. Ordinary setup/startup/lookup does not install
it. A feature flag rollback can leave these additive tables/history intact while
the application uses its legacy path.

## Disposable proof and limits

The fixture suite uses `tests/backend_support.py` and
`python scripts/run_tests.py`; the runner starts a temporary PostgreSQL 18 cluster
and never reads the project's `.env` or falls back to a project database DSN.
The first test-first run failed 11 new tests because the store did not exist;
subsequent regression RED runs caught null metadata/timestamp acceptance,
mutable manifest state, a public basis mismatch, and SQL metadata type coercion.

Coverage includes overlaps and exact CIDR edges; hostname identities; unchanged
HTTP fetched/check times; dated DNS snapshots/withdrawal; final-source rollback;
disable/re-enable and retained history; SQL bypass checks; explicit installation
twice and incompatible shape/index/constraint detection; shared-lock contention;
pending/approved measurements, UUID conflicts, privacy and proxy metadata;
actual-clock expired approved history and exact-expiry rejection; independent
legacy routing/geolocation/evidence preservation; and read-only query execution.

The containment fixture runs:

```sql
SET LOCAL enable_seqscan = off;
EXPLAIN SELECT * FROM evidence_v2_indicators
WHERE network >>= '8.8.8.8'::inet;
```

Its assertion confirms the plan names
`evidence_v2_indicators_network_gist`. This proves index eligibility on the fixture;
it is not a timing benchmark or a production planner-performance claim.

A preexisting monthly test occasionally recreated ZIP fixtures with a wall-clock
ZIP member timestamp, making identical CSV bytes hash differently across a two
second boundary. The authorized test-only correction fixes that member timestamp
to `(2026, 1, 1, 0, 0, 0)`; monthly production code is unchanged.

Final checkpoint: `.venv/bin/python scripts/run_tests.py` passed **181 tests in
7.188 seconds**, including **20 extended-store database tests**. Scoped Ruff
checks passed for `evidence_store.py`, `setup.py`, the extended-store tests, and
the fixed monthly test fixture. `git diff --check` passed. No live database,
network feed, observation capture, staging, commit, push, or deployment was used
for this checkpoint.

## Spec review follow-up

A regression first reproduced that a direct indicator INSERT could append a
public match to an already committed content-addressed snapshot. Snapshots now
record their creation transaction using PostgreSQL `xid8`; the existing indexed
source-binding lookup rejects indicator inserts from any later transaction.
Within the creating transaction, the existing deferred snapshot count check
still validates the completed load once per snapshot. The guard adds no per-row
full-snapshot count scans. The regression confirms a rejected append leaves
stored/actual counts at `(1, 1)` and creates no `9.9.9.9` public match.

The Unicode fixture now constructs actual U+1F310 with `chr(0x1F310)` and asserts
that character is present before the complete canonical-digest/public-query
roundtrip. The earlier fixture accidentally contained the ASCII text
`U0001f310`; the production canonicalizer already supported the actual character.

After these two review corrections, the complete disposable PostgreSQL 18 suite
passed **182 tests in 7.683 seconds**, including **21 extended-store database
tests**. Scoped Ruff and `git diff --check` passed again. No live database was used.


## Runtime integration checkpoint

The policy, feature flag, read-only service/API/explicit-snapshot CLI, separate
extended refresh publication, and approved-observation publication are now
implemented. `Settings.extended_evidence` defaults to false; no actual `.env` was
edited in this checkpoint. New API fields remain absent with the flag off,
including a full HTTP equality assertion against the legacy response. Explicit
null location/owner fields remain present. Enabled reads of a missing extended
schema return HTTP 503 without private database details.

The pure policy validates public IPv4 networks, credential-free HTTPS URLs,
SHA-256 identities, known basis/method/category/role combinations, aware clocks,
and observation approval/derived expiry. It preserves direct stale evidence with
its stale label, keeps network inference in `additional_evidence`, and separates
VPN from proxy association. Scheduled source counts exclude all observations.
Public source freshness uses the same captured transaction clock as lookup;
exactly 48 hours remains fresh. Observation approval/import never renews the
original measurement or its exact 24-hour expiry. Country, ASN, and hosting are
not policy inputs. No score or independent-confirmation count is introduced.

The completed candidate validator is
`load_candidate(candidate_path, archive_root, registry, *, now=None) -> dict`.
It is offline, bounded, and re-normalizes archived HTTP/DNS content before SQL
publication. Tests reject edited indicators with an unchanged raw hash, hash
changes, missing/duplicate/disabled snapshots, changed source definitions,
traversal, symlink escape, oversized archives, malformed entry types, and invalid
dated DNS timing. Existing parser tests cover late-source failure, successful
DNS withdrawals, new dated DNS content, and unchanged HTTP. SQL publication
retains previous active data on failed batches and supports disabled registries.

Refresh inserts `evidence_extended` immediately after requested legacy evidence,
while retaining the existing full-refresh session lock. A controlled extended
parse failure leaves the legacy state successful and records only the failure
class in a separate extended state entry. Successful refresh validates the saved
candidate again and publishes under the shared evidence transaction lock.
Standalone publication and observation recording both reject contention on that
same lock; no second scheduler job or nested full-refresh lock was introduced.

The recorder's enabled approval re-reads immutable originals, current profile,
and the local review before creating the public payload. Synthetic CLI tests
inject a dummy DSN and mock publication; flag-off tests explicitly force false.
A controlled DB failure preserves pending bytes and review bytes. Retry submits
the identical payload; review tampering fails before publication. Approval makes
no network request. Public projections omit private receipts, profile contents,
operator identity, proxy configuration, and import paths.

Three requested SQL checks are now precise: A-to-B-to-fresh-A compares the
previous active snapshot pointer and reports `loaded`; the nonpublic direct
INSERT executes in the snapshot creation transaction and asserts the named
`evidence_v2_indicators_network_public` constraint; a pending measurement is
created before expiry, then approval of the same identity after expiry is
rejected. A separate assertion rejects `reviewed_at == expires_at`. Historical
approved rows remain visible without gaining renewed eligibility.

Final controlled verification for this runtime checkpoint:

- `.venv/bin/python scripts/run_tests.py`: **198 tests passed in 8.165 seconds**
  using the runner-created ephemeral PostgreSQL cluster; project `.env` was not
  used for a database connection.
- Isolated collector suite: **42 tests passed in 0.278 seconds**.
- Isolated recorder suite: **30 tests passed in 0.169 seconds**.
- CI-scope Ruff (including `test_evidence_v2_policy.py`) and `git diff --check`
  passed. Ruff was run with `--no-cache` for the final read-only check.

No live database, live feed collection, real observation probe, VPN control,
actual environment activation, staging, commit, push, or deployment was used.
The existing prepared activation candidate was not modified or published.


## Minimal frontend explanation checkpoint (2026-11-03)

The existing React layout now appends an `Additional evidence` section only when
extended fields are returned. It separates possible network association from
direct endpoint evidence, displays proxy association independently, and keeps
residential proxy status unknown. Stale, operator-attested browser imports, and
unverified pool claims are labeled. Strong evidence cards retain distinct record
keys. Both strong and additional evidence expose method, role, original
observed/expiry dates, and a public HTTPS source link when available. Legacy payloads
remain valid and keep their prior section structure. Sources use source IDs when
provider is null, label inference as VPN networks, and describe counts as records
and networks rather than unique addresses. Committed expected extended IDs are
included in the displayed scheduled-source denominator.

The API guard accepts an unchanged legacy shape. Any extended key requires the
complete typed extension, including approved exits with original clocks; partial
or malformed extensions and residential positives are rejected. Optional strong
metadata newly rendered by the UI is also type-checked. Controlled rendering and clipboard tests verify equality to the exact API
fixture response; no fields are removed or renamed.

Test-first proof: the original 30 frontend tests passed. The first expanded run
had 38 expected failures exposing the missing extension validation, presentation,
and source semantics. After those passed, a second regression run had 7 expected
failures for unsafe optional strong metadata, followed by a passing fix. Review
then reproduced two missing tunnel/proxy provenance cases before correction.
Only `browser_import` is labeled as a browser import and not recorder-verified;
measured `system_tunnel` and `explicit_http_proxy` records keep the operator-
attested provider label while displaying their actual method. Original dates and
source links are also visible for proxy observations in additional evidence. Final
checks passed: **81 frontend tests**, `npm --prefix frontend run format:check`,
`npm --prefix frontend run build`, and `git diff --check`. Rendering tests cover
old and extended payloads, network/proxy wording, stale/attested/pool labels,
method/role/original dates, measured tunnel and proxy provenance, HTTPS-only
source links, multiple same-source record keys without React
warnings, focusable source links/table/copy controls, and exact JSON/clipboard.

The successful frontend checks used Node.js **22.23.3**, with `node` and `npm`
resolved from `/Users/nishankbansal/.nvm/versions/node/v22.23.3/bin` in a non-login
zsh shell (`login:false`). A later login-shell gate selected `/usr/local/bin/node`
22.12.0, which lacks `node:zlib.createZstdDecompress`, and failed during undici
import before UI tests could run. This was a runtime-selection failure; no
packages or dependency pins were changed. No precise minimum supported Node
version was established by these checks.

These are controlled jsdom rendering/keyboard-focus and mocked-fetch checks,
not live browser or VPN measurements. CSS, navigation, motion, dependencies, and
package pins were not changed. The README is a 174-line overview with three
Mermaid diagrams and links to detailed operator and verification documents. All
eight relative README file links resolve locally. Standard Mermaid flowchart
syntax was reviewed; external renderer verification is not claimed.

## Live database and TestClient checkpoint (2026-11-03)

The reviewed additive schema was installed against the configured local database.
The original November 2 archived candidate was revalidated offline, then published
with status `loaded`: **11,100 records**, comprising **10,999 X4B network rows**,
**100 VPN Gate hosts**, and **1 UrbanVPN DNS host**. No new feed fetch or real exit
capture was performed for this publication. Counts are source rows/networks,
not a unique-IP or provider-coverage measurement.

Six legacy table counts and all legacy snapshot rows remained exactly unchanged.
Six real flag-off JSON payloads remained exactly equal to their captured baseline.
With extended reads enabled inside a FastAPI TestClient:

| Address | Checked result |
| --- | --- |
| `103.108.230.50` | VPN listed, direct association, UrbanVPN `dns_a` record |
| `8.8.8.8` | VPN unknown, assessment unknown |
| `23.130.104.129` | AirVPN listed, direct association |
| `37.19.206.105` | IVPN listed, direct association |
| `216.246.27.1` | VPN unknown, network-only association |
| `185.186.206.1` | Two original routing ties retained with identical security |

An unforced `EXPLAIN (FORMAT JSON, COSTS OFF)` of the direct containment query
`evidence_v2_indicators WHERE network >>= '103.108.230.50'::inet` selected an
`Index Scan` using `evidence_v2_indicators_network_gist`. The plan is saved in
`/private/tmp/vpnlens-live-index-plan.json`. This is evidence for that direct
containment query only, not a full API query-plan or latency benchmark.

Readiness reported **14/14** scheduled sources recently checked. Residential proxy
status remained unknown in every checked response. Artifacts were saved locally
as `/private/tmp/vpnlens-live-acceptance.json`, `vpnlens-live-publication.json`,
`vpnlens-live-urban-response.json`, `vpnlens-live-sources.json`, and
`vpnlens-live-health.json`.

This checkpoint establishes local database publication and TestClient source
associations. It does not establish independent ground truth, detection accuracy,
real recorder execution, or activation of the actual running API/frontend. The
actual environment and running-server flag remained off pending frontend review
and build at this checkpoint; later activation requires separate evidence.


## Final integrated acceptance (2026-11-03)

All implementation groups passed independent specification and quality reviews.
The final independent cross-group review approved the API/CLI policy, publication,
refresh, SQL/public projection and UI seams with no actionable findings. The core
`sql/ip_lookup.sql` remains unchanged.

Final gates passed with the tested Node.js 22.23.3 runtime selected in a non-login
shell: **198 backend tests in 9.423 seconds**, using a fresh disposable PostgreSQL
cluster; **81 frontend tests in 1.24 seconds**; CI-scoped Ruff with `--no-cache`;
frontend formatting; production build; and `git diff --check`. No dependency
upgrades were needed to resolve the older login-shell Node startup failure.

The coordinating agent enabled extended reads and restarted the verified
project-owned local API. Actual HTTP checks against `127.0.0.1:8000` repeated the
six cases in the table above and reported ready with **14/14** scheduled sources.
The result is saved in `/private/tmp/vpnlens-running-server-check.json`.

Actual browser checks covered desktop **1280 x 720** and phone **390 x 844**:

- `103.108.230.50` displayed Listed, the UrbanVPN DNS method, unknown endpoint
  role, 14/14 sources, and residential proxy Unknown. Tokyo/JP geolocation and AU
  organization ownership remained separate facts, not classification rules.
- The phone layout and the API JSON tab were readable. The viewport was reset
  after the check.
- `216.246.27.1` displayed Possible VPN-network association with VPN Unknown,
  the X4B source rather than Tor Project, `cidr_text`, and expiry metadata.
- Sources displayed VPN Gate 100, UrbanVPN 1 and X4B 10,999 network records,
  with the overlap/record-count caveat.
- The copy control visibly reported `JSON copied`. Live clipboard byte equality
  was **not verified** because the browser automation clipboard bridge returned
  a stale value. Exact JSON/clipboard equality is established by controlled
  frontend tests only; the stale bridge result did not justify a product edit.

Screenshots: [desktop](screenshots/evidence-v2-desktop.jpg) and
[phone](screenshots/evidence-v2-mobile.jpg). The browser was restored to the
`103.108.230.50` result and marked as the deliverable.

These checks establish dated source associations and the local application flow,
not independent provider ground truth, broad detection accuracy, a residential
relay classification, or a real recorder measurement. No live tunnel/proxy
capture or browser receipt import was performed. Final staging, Conventional
Commit and normal feature-branch push are delegated to the coordinating agent
under the user's explicit authorization; no public deployment or main merge is
part of this acceptance.
