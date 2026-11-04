# Public VPN evidence candidates

This collector prepares reviewable, reproducible IPv4 evidence candidates. It does
not connect to a database, activate a snapshot, control a VPN, or change lookup
results. Public-list membership and DNS attribution cover only part of the VPN
market. Absence is not proof that an address is residential or not using a VPN.

## Reviewed source registry

`config/evidence_sources.json` has `schema_version: 1` and a `sources` array. The
registry enables these sources:

| Source ID | Family | Adapter and basis | Provider / role | Byte cap |
| --- | --- | --- | --- | --- |
| `x4b-vpn-v4` | `x4b` | `cidr_text` / `network_inference` | null / unknown | 5,000,000 |
| `vpngate-v4` | `vpngate` | `vpngate_csv` / `provider_list` | VPN Gate / server | 25,000,000 |
| `urbanvpn-dns-v4` | `urbanvpn-reviewed-hostnames` | `dns_a` / `provider_dns` | UrbanVPN / unknown | 5,000,000 |
| `protonvpn-advertised-exits-v4` | `protonvpn-provider-api` | `host_text` / `provider_list` | ProtonVPN / exit | 5,000,000 |
| `windscribe-server-list-v4` | `windscribe-provider-api` | `host_text` / `provider_list` | Windscribe / server | 5,000,000 |
| `tunnelbear-server-list-v4` | `tunnelbear-provider-api` | `host_text` / `provider_list` | TunnelBear / server | 5,000,000 |

Every entry requires a unique lowercase `source_id` (at most 100 characters),
nonempty `family`, boolean `enabled`, reviewed `adapter` and matching `basis`,
`provider` (text or null), `role` (`server`, `exit`, or `unknown`), credential-free
HTTPS `url` and `attribution_url`, `max_bytes`, and `max_age_hours: 48`. Disabled
entries remain in the archived registry and are not fetched. The additional
reviewed `host_text` adapter uses `provider_list`, a 5,000,000-byte cap, and public
IPv4 hosts only. No datacenter feed is included.

A DNS source also requires 1–100 unique, syntactically valid reviewed hostnames in
`hosts`. The initial list contains only `p-jp1.urban-vpn.com`. Its `url` is review
provenance, not a URL that the DNS adapter fetches. Adding a hostname is an
explicit registry review, not automatic enumeration.

## Attribution and interpretation

- [X4BNet lists_vpn](https://github.com/X4BNet/lists_vpn) supplies the VPN CIDR
  list at its `output/vpn/ipv4.txt` path. This is third-party network inference;
  the collector does not assign a provider to those ranges. The repository's
  scripts, curated inputs, and generated lists carry its MIT notice, copyright
  (c) 2026 X4B (Mathew Heard). Preserve the upstream license chain as well:
  scheduled builds use the IPLocate IP-to-ASN database under
  [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and IPLocate
  builds include `ASN-DATABASE.txt` with upstream attribution and license notices.
  Consult and retain those notices when redistributing derived data; this
  collector's own code license does not replace source licenses.
- [VPN Gate](https://www.vpngate.net/en/) supplies its
  [public server CSV](https://www.vpngate.net/api/iphone/). It describes part of a
  volunteer server network, not every commercial VPN or confirmed traffic exit.
  Only `IP` and `#HostName` establish identity. Configuration columns, including
  `OpenVPN_ConfigData_Base64`, are ignored and never decoded or executed.
- [UrbanVPN](https://www.urban-vpn.com/) is the provider attribution for the one
  reviewed hostname. The review link is the
  [Netify IP resource](https://www.netify.ai/resources/ips/103.108.230.50).
  This is a reviewed hostname association, not a provider-published bulk IP
  list, a guarantee of current DNS resolution, or permission to infer other
  hostnames. Collection queries only explicit A records and makes no claim to
  enumerate IPv6 addresses or the provider's entire infrastructure.

- [ProtonVPN-IPs](https://github.com/tn3w/ProtonVPN-IPs) supplies exact IPv4
  exits advertised by the Proton API. The collector uses its host list.
- [Windscribe-IPs](https://github.com/tn3w/Windscribe-IPs) extracts server
  addresses from Windscribe's public server catalog, including ping endpoints.
  These records describe provider infrastructure.
- [TunnelBear-IPs](https://github.com/tn3w/TunnelBear-IPs) publishes server
  addresses from the provider API. Its upstream list retains addresses for up
  to 30 missed checks. A VPNLens download time does not renew upstream evidence
  about when an address last appeared on a server.

These three lists are maintained by tn3w under Apache-2.0. Keep the linked
license and attribution with any redistributed list. The ProtonVPN and
Windscribe feeds can share upstream information with existing provider lists.
A repeated address does not establish an independent observation.

All sources use a 48-hour check-age policy. `checked_at` records when this
collector checked a source; it does not claim when the publisher changed its
list. The window is not a DNS cache TTL, proof of continuous ownership, or a
guarantee that traffic still uses the address. DNS TTL is stored as answer
metadata and is excluded from record identity.

## Bounds and failure semantics

HTTP requests use `VPNLens-portfolio/1.0`, a 30-second timeout, an HTTP 200
requirement, and a credential-free HTTPS final URL. Advertised content lengths
must fit the reviewed cap; reading stops at cap plus one byte. Oversized,
incomplete, malformed, private/reserved, or wholly IPv6 text sources fail the
batch. Valid IPv6 text rows are counted as skipped. CIDRs remain one record each;
they are never expanded to individual hosts. Duplicate record identities are
removed without losing different providers or hostnames on an overlapping IP.

DNS queries use an absolute hostname, A family, search disabled, and a five-second
lifetime. A successful public IPv4 answer records sorted unique addresses and
TTL. NXDOMAIN and a completed response with no A records are explicit withdrawals
(`nxdomain` or `no_a`, empty addresses, null TTL); a complete zero-record DNS
snapshot is valid. Timeout, SERVFAIL, malformed answers, and private addresses
fail collection and cannot masquerade as withdrawals. Each reviewed hostname has
`queried_at` and `completed_at`; a DNS check also has `checked_at`. Clock reversal
fails preparation.

## Preparing and inspecting candidates

From the repository root, the manually invoked preparation command is:

```sh
.venv/bin/python -m vpnlens.evidence_collect \
  --registry config/evidence_sources.json --out data/evidence-v2
```

This command performs network collection when invoked; unit tests use only fake
HTTP/DNS responses. It prints JSON with `status: prepared` and `candidate` only
after all enabled sources pass. Failure prints an exception class without URL,
credential, payload, or exception-message details and leaves active data unchanged.

Artifacts under the ignored `data/evidence-v2/` directory are:

- `raw/<source_id>/<sha256>.bin`: immutable source bytes, or canonical DNS JSON
  `{checked_at, family: "A", answers: [...]}`. Every DNS answer includes hostname,
  addresses, TTL, state, and query/completion timestamps. Identical HTTP bytes
  reuse the same archive; a new DNS check time changes the DNS archive hash.
- `candidates/<uuid>.json`: an immutable completed manifest with schema version,
  batch ID, batch check time, canonical registry hash, full registry, and
  snapshots. A snapshot contains the source entry, content hash, raw relative
  path, `fetched_at`/`checked_at`, null `publisher_at`, records, and IPv6 skip count.

Writes use private files and atomic creation. An identical retry is allowed;
conflicting or corrupted existing bytes are rejected. A late source failure may
leave earlier raw archives for inspection, but it leaves no completed candidate.
Candidates remain inactive until the explicit publication workflow below succeeds.


## Opt-in local lookup and publication

`VPNLENS_EXTENDED_EVIDENCE=false` is the default in `.env.example`. Supported
values are `true`/`1` and `false`/`0`, ignoring case and surrounding whitespace;
other values fail without echoing the setting. Direct Python service callers
also default to legacy behavior. With the flag off, lookup/source payloads and
scheduled source counts retain their previous shape and no extended tables are
queried.

Initialize the additive schema explicitly before enabling the flag:

```sh
.venv/bin/python -m vpnlens.setup --extended-evidence
```

Use the configured database only after reviewing its target. This setup command
is an operator instruction; integration verification uses disposable PostgreSQL.
Then enable the flag in the operator environment and restart the API. The
explicit-snapshot `lookup_ip.py` CLI reads the same setting. Enabling the flag
without installing the schema returns a safe HTTP 503. The GET API stays read
only and never refreshes sources or records observations.

A flag-enabled refresh request containing `evidence` inserts `evidence_extended`
immediately after the legacy evidence transaction. The existing full-refresh
session lock stays held. Extended preparation, offline validation, and SQL
publication form a separate failure boundary: extended failure retains the
previous extended active pointers and successful checks, and cannot undo the
already committed legacy refresh. Its separate refresh-state key is
`evidence_extended`. The scheduler and its single job are unchanged.

For an already prepared, reviewed candidate, the public offline validation API is:

```python
from vpnlens.evidence_collectors import load_candidate
from vpnlens.evidence_store import publish_contract
batch = load_candidate(candidate_path, archive_root, reviewed_registry, now=aware_utc_now)
report = publish_contract(database_url, "publish", batch)
```

`load_candidate(candidate_path, archive_root, registry, *, now=None)` returns the
validated batch dictionary. It reads at most 128 MiB plus one candidate-envelope
byte and each reviewed raw-source cap plus one byte. Raw references must resolve
under the expected archive root, including symlinks. The registry hash, enabled
source set, source definitions, UTC timestamps, hashes, IPv6 counts, and canonical
records are revalidated. Every raw HTTP payload is parsed again; every dated DNS
bundle is checked for the complete reviewed host set, A-only public answers,
TTLs, withdrawals, and query/check ordering. It performs no network or DB calls.
Publication and observation approval share transaction lock `872410052` with the
legacy evidence publisher; neither acquires a second full-refresh session lock.

Fresh direct provider lists, provider DNS, and approved VPN exits can set
`vpn_status: listed` and `vpn_assessment: direct_association`. Network inference
appears only in `additional_evidence` and can set `vpn_assessment: network_only`.
A fresh approved proxy exit sets only `proxy_status: listed`. Residential proxy
status remains `unknown`, with reason `No qualifying residential-relay evidence
has been collected`. Correlated records remain separate and are not scores or
independent confirmations. Stale approved history remains visibly stale; pending
and rejected observations are absent. Exact 48-hour public checks are fresh;
observations expire at exactly original observation time plus 24 hours.

`/v1/sources` appends committed enabled scheduled sources, including optional
`basis` and `record_kind` (`host`/`network`). Weak source rows use
`indicator_type: network_inference`; a null provider remains null. `ipv4_count`
is a record/network count, never CIDR address expansion. The optional top-level
`security_expected_source_ids` contains committed enabled extended IDs. Readiness
uses their union with legacy feed IDs; missing or stale feeds degrade readiness
while loaded core data remains available. Measurements never inflate the
scheduled denominator.

Rollback is setting `VPNLENS_EXTENDED_EVIDENCE=false` and restarting the API and
operator commands. This restores legacy reads without deleting extended history.
No rollback command erases artifacts or renews observation expiry.
