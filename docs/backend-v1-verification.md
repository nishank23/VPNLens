# Backend v1 verification

Date: 2026-11-02
Checkout: `/Users/nishankbansal/Documents/VPNLens`, branch `main`.
The user approved the local backend design before implementation. Frontend and
public deployment are excluded. Existing uncommitted evidence work was preserved.

## Automated verification

- **79 tests passed** using `python scripts/run_tests.py` in an isolated temporary
  PostgreSQL 18 cluster. No project-database fallback is permitted.
- Ruff lint and formatting checks passed for API, backend, scripts, new acceptance
  tests, and modified ingestion/lookup runners.
- `python -m pip check` passed. `requirements.lock` records the tested versions.
- `git diff --check` passed. The reviewed `sql/ip_lookup.sql`, routing
  transformation, and geolocation transformation statements remain unchanged.
- GitHub Actions is configured with a dedicated PostgreSQL service. It has not
  run remotely for these unpushed changes; local success is not remote CI proof.

The tests cover baseline SQL/ingestion behavior plus real PostgreSQL HTTP
contracts, latest/historical source selection, safe errors, read-only bounded
transactions, compatibility-preserving initialization, download/ZIP validation,
rollback, changed-file detection, unchanged skips, independent dataset commits,
refresh overlap, credential-free status, CLI JSON compatibility, and scheduler
replacement/recovery. External download unit tests use fixtures.

## Real-data verification

The non-destructive initializer completed against the existing project database.
The full refresh then completed against real local/public datasets:

| Dataset | Observed result |
|---|---|
| CAIDA routing | Latest available discovery selected `routeviews-rv2-20261031-1200.pfx2as.gz`; 1,166,218 transformed origin-group rows in that snapshot |
| CAIDA organizations | `20261001.as-org2info.txt.gz`; 98,447 organizations and 122,668 ASN records |
| IP2Location DB11 | Existing authorized local CSV loaded and transformed; 2,996,298 rows |
| VPN evidence | 13,573 IPv4 source records across ten provider files |
| Tor evidence | 1,239 IPv4 source records |
| IPv6 | 1,556 feed entries counted and skipped |

Evidence record totals can include the same IP in different sources. They are
not a unique-IP count or a measured VPN coverage percentage. CAIDA snapshot time,
organization country, IP geolocation, and our evidence check time remain distinct.
During initial backend verification, automatic IP2Location downloading was not
live-tested; local CSV loading was verified. Subsequent authenticated download
verification is recorded in [monthly geolocation verification](monthly-ip2location.md).

## Local HTTP verification

The final API was started through uvicorn on `127.0.0.1:8000` and tested through
actual HTTP requests against the project database:

| Request | Observed result |
|---|---|
| `/health/live` | 200 |
| `/health/ready` | 200, ready, all 11 expected evidence sources recently checked |
| `/v1/sources` | 200, loaded snapshots and refresh status |
| `/v1/lookup/185.186.206.1` | 200, two tied origin-group rows with nested owners |
| Same lookup pinned to October 1 routing | 200, historical source selection retained |
| `/v1/lookup/8.8.8.8` | 200 |
| `/v1/lookup/192.0.2.1` | 200, preserved input, unknown VPN/Tor evidence |
| `/v1/lookup/1.220.90.178` | 200, VPN listed, Tor unknown in this evidence snapshot |
| `/v1/lookup/2.56.10.36` | 200, Tor listed, VPN unknown in this evidence snapshot |
| `/v1/lookup/not-an-ip` | 422 |
| `/openapi.json` | 200 |

Listed sample addresses are observations for this snapshot, not permanent
classifications. Single-request smoke timings do not establish throughput, an
SLA, production reliability, or detection accuracy.

## Scheduler verification

Installed `/Users/nishankbansal/Library/LaunchAgents/io.vpnlens.dataset-refresh.plist`
using the project's `.venv/bin/python`. The evidence-only job was disabled; its
old plist remains for recovery. The replacement's first run completed with
**exit code 0**. Routing, organization, and geolocation were unchanged; all 11
evidence feeds were also unchanged. The job waits for its next daily interval.
This proves one scheduled invocation, not future uptime. The Mac and user session
must remain available. Logs are under `data/refresh/logs/`.

## Changed components

| Files | Purpose |
|---|---|
| `api/main.py`, `api/models.py` | HTTP endpoints, validation, safe errors, logging, output contract |
| `vpnlens/config.py`, `vpnlens/database.py` | Explicit configuration and bounded read-only transactions |
| `vpnlens/setup.py`, `sql/bootstrap.sql` | Non-destructive initialization and compatibility checks |
| `vpnlens/service.py` | Independent source selection and reuse of reviewed lookup SQL |
| `vpnlens/downloads.py`, `vpnlens/refresh.py` | CAIDA discovery, bounded downloads, atomic publication, refresh status |
| `ingestion/asn_prefixes.py`, `ingestion/asn_organizations.py` | Explicit routing-file runner and transaction reuse |
| `lookup_ip.py` | Existing JSON CLI with shared validation/timeouts and local evidence |
| `scripts/`, new backend tests, `.github/workflows/tests.yml` | Repeatable test execution, local scheduling, and CI configuration |
| Dependency/configuration files, README, docs | Reproducible local setup, project diagram, source limits, operation instructions |

## Remaining limits and handoff

- Public evidence is incomplete. Unknown never means confirmed non-VPN/non-Tor.
- IP2Location automatic downloading needs an authorized HTTPS ZIP URL. The current
  configured CSV does not become newer merely because it is revalidated daily.
- Geolocation publication date is unknown. Refresh check time is not upstream
  observation time.
- Datasets publish independently. Large geolocation replacement can block readers;
  bounded HTTP queries can return 503 during that interval.
- Refresh status is a local file, not a transactional audit ledger. Losing it
  triggers safe reloads. Snapshot history is retained without automatic pruning.
- Final user code review remains pending. No commit, GitHub push, frontend,
  public deployment, production load test, or commercial detection-accuracy claim
  was performed in this milestone.

## Monthly geolocation follow-up (2026-11-02)

The user subsequently requested automatic monthly IP2Location downloads.
The existing daily job now supports token configuration and monthly eligibility.
All 91 tests pass with fixture downloads. Authenticated live verification later passed after the user configured the
local token: 2,965,251 rows loaded and the second invocation skipped all network
access. See [monthly download details](monthly-ip2location.md).

Authenticated monthly geolocation verification is now complete: 2,965,251 rows committed; next eligibility 2026-12-05. See [live evidence](monthly-ip2location.md#authenticated-live-verification-2026-11-02).
