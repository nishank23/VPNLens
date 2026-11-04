# Connection checker and streaming policy

VPNLens opens with a connection check and shows IP location and origin groups.
Visitors can enter an IPv4 address, open Details for routing and evidence, or
copy lookup data from the JSON panel. Recheck detects the current connection again.
The streaming policy is available through the API.

## API

| Route | Result |
| --- | --- |
| `GET /v1/connection` | Visitor public IPv4, lookup, and one access decision |
| `GET /v1/access-decision/{ip_address}` | Explicit IPv4 lookup and one decision |
| `GET /v1/lookup/{ip_address}` | Existing lookup contract, without the policy envelope |

The new response is `{ "lookup": <existing lookup response>, "decision": {...} }`.
The decision contains `policy_id`, `action`, `reason_codes`,
`scheduled_source_health` and `evaluated_at`. Lookup and decision share one
read-only repeatable-read transaction and its clock. Tied routing origins remain
inside `lookup.results`; they do not create multiple decisions. New route
responses, including errors, use `Cache-Control: no-store`.

`streaming-access-v1` recommends blocking for fresh qualifying VPN, Tor-exit or
approved proxy-exit evidence, with all applicable reasons in that order.
Otherwise it recommends allowing playback. That is an explicit demo fallback,
not a statement that an IP is verified non-VPN. Country differences, hosting
networks and broad CIDR inference cannot independently trigger a block.

| Situation | Action / reason |
| --- | --- |
| Fresh VPN association | block / `recent_vpn_evidence` |
| Fresh Tor exit | block / `recent_tor_evidence` |
| Fresh approved proxy exit | block / `recent_proxy_evidence` |
| No qualifying match, expected sources recent | allow / `no_recent_blocking_evidence` |
| No qualifying match, sources missing or stale | allow / `insufficient_recent_evidence` |
| Database or required core dataset unavailable | HTTP 503, no decision |

Public evidence remains fresh through the inclusive 48-hour boundary; reviewed
exit observations expire at their original 24-hour expiry. Future-dated,
pending, rejected, expired and network-only records cannot independently block.
Residential-proxy classification remains unknown. Scheduled-source health
measures checks, not market coverage, detection accuracy or confidence.

The demo stays accessible to VPN users. A streaming service would apply its own
policy on its server; hiding playback in client code would not enforce it.

## Visitor IP and proxy trust

Run the application with the original transport peer available:

```bash
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
```

By default, all forwarding headers are ignored. An ordinary local browser reaches
the server through `127.0.0.1`, so `/v1/connection` returns HTTP 409 with
`public_ipv4_unavailable`. On loopback origins, automatic detection is on by
default. The browser contacts [ipify](https://www.ipify.org/), which sees the
connection's public IPv4. VPNLens fills the search field and looks up that
address locally. **About** lets you disable the fallback for later visits.
Manual lookup remains available.
For an IPv6 peer, the backend returns HTTP 422 `ipv6_not_supported`.

For later deployment behind a controlled reverse proxy, set
`VPNLENS_TRUSTED_PROXY_CIDRS` to a comma-separated list of explicit network CIDRs.
For example, `127.0.0.1/32` is appropriate only when a trusted local proxy is the
sole route to this backend. Keep it empty for direct local use. `*`, IPv4 `/0`,
and IPv6 `/0` are rejected.

Only a trusted transport peer can supply `X-Forwarded-For`. Every chain element
is validated first; trusted hops are peeled from right to left until the first
untrusted client. Missing, malformed or entirely trusted chains fail discovery.
An untrusted peer's XFF, `Forwarded` and `X-Real-IP` do not influence selection.
Each configured proxy must append its actual upstream peer or replace inbound
XFF with an independently verified chain. Keep Uvicorn's own proxy-header
rewriting disabled; otherwise the app cannot validate the original peer.

There is no visitor-search storage or added analytics. The app's structured
request logs omit IP paths; the command above also disables Uvicorn access logs.
Hosting-platform access logging is a separate deployment setting.

## Public API limits

Set `VPNLENS_API_REQUESTS_PER_MINUTE=30` to enable 30 requests per client IP and
`VPNLENS_API_TOTAL_REQUESTS_PER_MINUTE=120` across all visitors. The quota is shared
by GET requests to `/v1/*` and `/health/ready`. Excess requests receive HTTP 429 and
a `Retry-After` header in seconds before the database is opened. The frontend shows
when to retry. Use `/health/live` for frequent probes.

The quota uses in-memory 60-second windows. Counts reset on process restart and
are independent across workers. Use one worker for the public demo. A trusted
proxy must supply a verified client IP so visitors receive individual quotas.

## Compute Engine demo

Use an eligible US `e2-micro` with a 30 GB standard persistent disk for a
low-traffic demo. Run the prebuilt frontend, one Uvicorn worker, and local
PostgreSQL. Build assets off-VM and stage refreshes separately from serving.
Keep Uvicorn and PostgreSQL on loopback. Terminate HTTPS at a controlled edge
that overwrites inbound `X-Forwarded-For` with the verified visitor address and
disables IP access logging. Configure app trust for that edge's loopback peer
and leave Uvicorn proxy-header rewriting disabled.

```bash
VPNLENS_API_REQUESTS_PER_MINUTE=30 VPNLENS_API_TOTAL_REQUESTS_PER_MINUTE=120 \
  python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 1 \
  --limit-concurrency 16 --no-proxy-headers --no-access-log
```

Before publishing, confirm CAIDA dataset citation and publication requirements
for the data served. Omit private receipts and credentials.

### Provision the VM from GitHub

The manual **Provision VPNLens VM** workflow runs from `main`. In the
`vpnlens-gcp` GitHub environment, configure `GCP_PROJECT_ID`,
`GCP_WORKLOAD_IDENTITY_PROVIDER` and `GCP_PROVISIONER_SERVICE_ACCOUNT` as variables.
Store the expected account ID as the `GCP_BILLING_ACCOUNT_ID` secret.

Use a dedicated project with active billing and an IPv4 subnet named
`vpnlens-us-central1` in `us-central1`. Configure GitHub OIDC with [Workload
Identity Federation](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines).
Restrict the provider to this repository's numeric ID and the provisioning
workflow on `main`. Give the dedicated provisioner access to manage instances
in this project and the `resourcemanager.projects.get` permission for the
billing check. Keep billing changes under an administrator account.

Run `verify` for a read-only preflight. Run `create` to provision one
`vpnlens-demo` VM in `us-central1-a`. The workflow checks the linked billing
account before Compute Engine calls and refuses an existing VM with conflicting
settings. The VM uses Ubuntu 24.04 LTS and a 30 GB standard persistent disk.
It has no external IP or runtime service account. Configure connectivity before
installing packages or deploying VPNLens from GitHub.

### DB-IP geolocation for public use

Point `DATABASE_URL` at a separate demo database. Set
`VPNLENS_GEOLOCATION_PROVIDER=dbip_city_lite` in the environments for refresh and
Uvicorn. Initialize the schema and refresh the datasets.

```bash
python -m vpnlens.setup
python -m vpnlens.refresh
```

The geolocation refresh downloads the current monthly DB-IP City Lite CSV.
Later scheduled runs check it once per month, with retry on failure. For an
offline import, use `--dataset geolocation --geolocation-file PATH` with the
original dated `dbip-city-lite-YYYY-MM.csv.gz` or its extracted CSV.

The loader streams IPv4 ranges into the existing PostgreSQL range index and
publishes the release in the same transaction. A failed import preserves the
previous release. The DB-IP API setting requires a committed DB-IP release for
readiness and lookup. `/v1/sources` and `selected_sources.geolocation` show which
release is active. The web UI links to DB-IP when it shows its geolocation data.

To roll back a failed demo setup, point the local process back to its original
database and `VPNLENS_GEOLOCATION_PROVIDER=ip2location`. Keep that database for
local use. IP2Location LITE's current terms restrict public IP lookup services.

Smoke-test automatic visitor detection, manual lookup, source freshness, and
HTTP 429 through the HTTPS endpoint. Check RAM, lookup latency, and egress under
load before announcing the link. Google Free Tier allowances apply across
eligible usage, and an external IPv4 address can be billed separately.

- [Compute Engine Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features)
- [External IP pricing](https://cloud.google.com/vpc/pricing#ipaddress)
- [IP2Location LITE terms](https://www.ip2location.com/lite-terms)
- [DB-IP Lite terms](https://db-ip.com/db/lite.php)
- [CAIDA public data agreement](https://www.caida.org/about/legal/aua/public_aua/)

## Interface and assets

The approved app-screen direction is Achromatic ledger, seed `964701165`, using
the project's IBM Plex fonts, Solar icons and original lens mark. The screen's
focal content is the IP and finding; technical detail is disclosed on demand.
GSAP provides brief result feedback, and Lenis is the sole smooth-scroll engine
for expanded views. Reduced-motion preferences bypass both and changes to that
preference clean up active animation. No decorative media, invented proof, paid
data service, Three.js or AI classifier is added. Existing font and icon notices
remain under `frontend/licenses/` and the About disclosure.
