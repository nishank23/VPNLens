# Local exit recorder

The recorder creates immutable **local artifacts** for operator-reviewed IPv4 exit
measurements. Approval records a separate local review. With
`VPNLENS_EXTENDED_EVIDENCE=true`, approval also publishes the validated measurement
and review to the explicitly configured database. With the default flag off,
approval is local only. No command controls a VPN client, browser extension, browser
storage, or network settings. Disconnecting and connecting the service is always
manual operator work.

An echo receipt says only which public IPv4 address the HTTPS request used.
The echo service, **ipify**, sees that public IP. It does not identify or verify
the provider, subscription, service category, residential status, or connection
type. Those profile labels and claims are operator-reviewed metadata. Residential
status remains **unknown**, including when an unverified `connection_type_claim`
is `residential`, `mobile`, or `datacenter`. No coverage or live VPN verification
is claimed by these examples or the synthetic tests.

## Private profiles

Create `data/observations/profiles.json` locally. The profile object key must match
`profile_id`. This exact no-secret example uses an operator-managed system tunnel:

```json
{
  "urban-desktop": {
    "profile_id": "urban-desktop",
    "provider": "UrbanVPN",
    "service_category": "vpn",
    "transport": "system_tunnel",
    "documentation_url": "https://www.urban-vpn.com/",
    "proxy_env": null
  }
}
```

This example describes metadata only. It does not establish that UrbanVPN is
installed, connected, available for this platform, or verified. Review the
provider's documentation and your actual setup before measuring. The omitted
`connection_type_claim` defaults to `unknown`.

`system_tunnel` measures the Python process's system route with ambient proxy
environment variables disabled. A browser-only VPN extension can use a different
exit; its browser receipts must use a `browser_import` profile. The CLI cannot
capture browser traffic or generate original browser receipts for you.

For an `explicit_http_proxy` profile, set `proxy_env` to an uppercase environment
variable name such as `VPNLENS_PROXY_URL`. Put the authorized HTTP/HTTPS proxy URL
only in that environment variable or private `.env`; never in profile JSON,
examples, review metadata, source control, or command-line arguments. Its active
requests use exactly that proxy; its baseline is direct (`proxy=None`). A failed
proxy gets no direct fallback. Both Python routes set `trust_env=False`, verify
TLS, reject redirects, use a ten-second timeout, and contact only
`https://api.ipify.org?format=json` with `Cache-Control: no-cache`. Profiles and
provider labels are not sent to the echo service.

The repository ignores `/data/` and `.env`; this includes profiles, baselines,
receipts, rejected raw imports, reviews, and failure metadata under
`data/observations/`. Keep `--out` and custom profile paths private too: choosing
an output directory outside the ignored tree does not automatically ignore it.

## Manual system-tunnel sequence

Run the following blocks in the **same operator terminal**, from the repository
root, with the intended profile configured. The shell variables capture actual
returned paths, so no placeholder UUID or guessed file name is needed. These
commands make real requests when you choose to execute them; they are documentation
and were not executed as part of fixture verification.

First manually disconnect the VPN, then attest to the disconnected baseline:

```bash
set -euo pipefail
VPNLENS_BASELINE_FILE=$(.venv/bin/python -m vpnlens.observe baseline --profile urban-desktop --confirm-disconnected | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["path"])')
```

Manually connect the intended VPN in its own client. After checking the intended
service is active, attest and capture two active receipts:

```bash
VPNLENS_OBSERVATION_FILE=$(.venv/bin/python -m vpnlens.observe capture --profile urban-desktop --baseline "$VPNLENS_BASELINE_FILE" --confirm-active | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["path"])')
```

Review the saved baseline, both original active response bodies, hashes, times,
profile, and IP change. To record a local approval:

```bash
.venv/bin/python -m vpnlens.observe approve --profile urban-desktop --file "$VPNLENS_OBSERVATION_FILE" --operator local-reviewer
```

Local-only success prints a JSON object with `status: "local_artifact"` and the
absolute `path`. A flag-enabled approval prints `status: "published"` after SQL
publication succeeds. Baselines are written to `baselines/`, measurements to `pending/`, and
reviews to `reviews/`. Files are immutable: identical imports/saves are idempotent;
changing bytes under an existing observation UUID is a conflict. Editing reviewed
profile metadata changes its digest and invalidates measurements bound to the old
profile. Use a new capture after a profile change.

A capture checks the baseline is fresh **before any active requests**. The first
active receipt must be at or after the baseline, the second at or after the first,
and baseline-to-last-active must be **at most 15 minutes**, including the boundary.
The two active receipt UUIDs must differ. Active public IPv4 addresses must agree
and differ from the baseline. A measurement expires **24 hours after the last
original active receipt**; at the exact expiry time it is rejected. Approval and
import never renew its original timestamps or expiry.

## Browser imports

Use a separate reviewed profile with `transport: "browser_import"` and
`proxy_env: null`. Supply a complete original observation JSON via:

```bash
.venv/bin/python -m vpnlens.observe import --profile YOUR_BROWSER_PROFILE --file /absolute/private/original-observation.json
```

Then review the returned pending path and use `approve --file` with that actual
path. Browser imports require the same disconnected and active attestations,
profile binding, public IPv4 change, two distinct receipts, original response
bodies and SHA-256 hashes, and original timing checks as Python captures. Export
actual responses and actual request start/completion times from your authorized
browser measurement workflow. Merely navigating to ipify does not supply a complete
measurement artifact. Never invent receipt times, replace them with import time,
or relabel system-tunnel measurements as browser traffic. There is no automatic
browser capture implementation here.

The complete example below is **synthetic**, generated from
`tests/test_exit_recorder.py::observation_fixture(mode="browser_import")`. It is
**never live evidence or VPN proof**. The DNS resolver addresses `1.1.1.1` and
`8.8.8.8` are fixture values, not measured exits. Its fixed November 2, 2026 times
expire normally; do not import it as live evidence or update its times to bypass
expiry. Replace the entire example with actual original measurements, hashes,
UUIDs, reviewed profile metadata and corresponding canonical profile digest.

Synthetic browser profile (the default `connection_type_claim` is made explicit):

```json
{
  "fixture-vpn": {
    "profile_id": "fixture-vpn",
    "provider": "Fixture VPN",
    "service_category": "vpn",
    "transport": "browser_import",
    "documentation_url": "https://example.com",
    "proxy_env": null,
    "connection_type_claim": "unknown"
  }
}
```

Complete synthetic observation:

```json
{
  "schema_version": 1,
  "kind": "exit_observation",
  "observation_id": "c3376f0b-9abd-4e78-a2fa-0a405612aa06",
  "profile_id": "fixture-vpn",
  "profile_sha256": "d06fd90d208147c72bf1fad75f7c8f64378d3b6081502ea8471b6e0ca108bd47",
  "method": "browser_import",
  "review_state": "pending",
  "operator_attested_active": true,
  "baseline": {
    "schema_version": 1,
    "kind": "baseline",
    "baseline_id": "34e7df8d-732e-44fe-8ce7-cb4292fe82e9",
    "profile_id": "fixture-vpn",
    "profile_sha256": "d06fd90d208147c72bf1fad75f7c8f64378d3b6081502ea8471b6e0ca108bd47",
    "operator_attested_disconnected": true,
    "receipt": {
      "receipt_id": "17638c9d-a7a4-4394-9653-a355e41b398f",
      "ip": "1.1.1.1",
      "endpoint": "https://api.ipify.org?format=json",
      "response_body": "{\"ip\":\"1.1.1.1\"}",
      "response_sha256": "5ff812371b9c0e5c1e8b454e8de2badb94cded074a7aa583a61d1735bbeb4efe",
      "started_at": "2026-11-02T11:58:00+00:00",
      "observed_at": "2026-11-02T11:58:00+00:00"
    }
  },
  "active_receipts": [
    {
      "receipt_id": "b7e448f9-76d2-454e-8de5-897f3839f645",
      "ip": "8.8.8.8",
      "endpoint": "https://api.ipify.org?format=json",
      "response_body": "{\"ip\":\"8.8.8.8\"}",
      "response_sha256": "9340277015b54dcec2f7ae454f68774f9ff722f4223a252eda4ebf42aec17c80",
      "started_at": "2026-11-02T11:59:58+00:00",
      "observed_at": "2026-11-02T11:59:58+00:00"
    },
    {
      "receipt_id": "51f765a8-b6e0-49ab-84c3-8c5468e11e24",
      "ip": "8.8.8.8",
      "endpoint": "https://api.ipify.org?format=json",
      "response_body": "{\"ip\":\"8.8.8.8\"}",
      "response_sha256": "9340277015b54dcec2f7ae454f68774f9ff722f4223a252eda4ebf42aec17c80",
      "started_at": "2026-11-02T11:59:59+00:00",
      "observed_at": "2026-11-02T11:59:59+00:00"
    }
  ]
}
```

The profile digest is SHA-256 of the normalized profile serialized using
`vpnlens.evidence_contract.canonical`: sorted keys, compact separators, UTF-8,
no non-standard JSON constants. Each response digest hashes the exact UTF-8
`response_body` bytes, not a reformatted JSON representation. Receipt bodies have
a 4096-byte cap and must be strict JSON whose `ip` agrees with the recorded
canonical public IPv4 host. Credentials do not belong in original receipts.

Imports are capped at 262144 bytes. Bounded original input bytes are archived as
`imports/<sha256>.bin` **before parsing**, even when invalid JSON or validation is
rejected. Oversized files are rejected without a raw archive; only safe failure
metadata is written. The archive preserves original bytes; the pending measurement
uses canonical JSON and retains original receipt timestamps. Rejected input may
contain sensitive material, so treat raw imports as private.

Failures return nonzero and write only `kind`, `at`, and the exception class
`error_type` under `failures/`. Standard error also contains class names only;
proxy URLs and exception messages are excluded. If failure archival itself fails,
the original operation still fails and standard error names both classes without
exposing their messages. Approval stays local with the flag off; with the flag
on, it explicitly publishes the validated measurement and review. A failed
publication rolls back its transaction and creates no eligible positive; local
artifacts remain available for a safe retry.


## Approved publication and safe retries

Install the extended schema explicitly (`python -m vpnlens.setup
--extended-evidence`) before using enabled approval. Approval re-reads the saved
original measurement, current reviewed profile, and immutable local review,
then builds `observation_payload` with the current clock. Approval never performs
a probe, changes VPN controls, uses import/approval time as observation time, or
renews the derived 24-hour expiry. A missing schema or publication lock conflict
fails safely. DB failure preserves the pending receipts and review for a retry;
only the exception class is emitted and saved in failure metadata. An identical
unexpired retry publishes the same payload. Expired, conflicting, or tampered
artifacts cannot create an eligible positive. Public output contains allowlisted
measurement fields and `operator_attested: true`, never raw echo bodies, private
profile contents, credentials, or the operator's identity. Set the flag to false
to return approval to local-only behavior; no history needs to be deleted.
