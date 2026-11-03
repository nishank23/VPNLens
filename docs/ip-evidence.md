# Free VPN-server and Tor evidence

Backend v1 now provides a full dataset refresh command and replacement scheduler.
Use `python -m vpnlens.refresh` and `python scripts/install_refresh_schedule.py`;
see [current setup and scheduling](../README.md#refresh-and-scheduling). The
evidence-only command below remains supported, but do not run both schedulers.

This milestone uses local public lists, not a paid detection API. It identifies
exact host-IP list matches and preserves source evidence. It does not establish
that every listed server is a current traffic exit or that an unlisted IP is
not a VPN. Tor-exit evidence is a separate category.

## Sources and downloaded files

- Ten provider files from [Open Source VPN IP Lists](https://github.com/Joe12387/open-source-vpn-ip-lists), under its [CC0 license](https://raw.githubusercontent.com/Joe12387/open-source-vpn-ip-lists/master/LICENSE): AirVPN, IVPN, Mullvad, NordVPN, OVPN.com, Private Internet Access, ProtonVPN, RiseupVPN, Surfshark, and Windscribe. The maintainer describes these as provider-published server/entry/egress data; that claim has not been independently audited.
- [Tor Project exit list](https://check.torproject.org/torbulkexitlist).

Every source URL is explicit in `ingestion/ip_evidence.py`. These feeds are plain
text, not ZIP archives. Downloads live in ignored directories:

```text
data/evidence/<source-id>/<sha256>.txt
data/evidence/logs/refresh.stdout.log
data/evidence/logs/refresh.stderr.log
```

IPv4 addresses are deduplicated within each feed. IPv6 entries are counted and
skipped because the current lookup targets IPv4. Multiple providers or evidence
types may legitimately reference the same IP; those records remain separate.

## Tables and refresh behavior

`sql/ip_evidence_schema.sql` defines:

- `ip_evidence_snapshots`: source, provider, indicator type, URL, hash, first
  fetch time, most recent successful check time, counts, and active status.
- `ip_evidence`: indexed IPv4 hosts linked to a snapshot. The primary key is
  `(snapshot_id, ip)`. Snapshot history is retained; no automatic deletion occurs.

Run from the repository root with `DATABASE_URL` in `.env`:

```bash
# First installation: create only the new evidence tables/indexes, then refresh.
python3 refresh_ip_evidence.py --init-schema

# Subsequent manual refreshes.
python3 refresh_ip_evidence.py
```

All eleven selected sources are downloaded and validated before database
publication. Archives are saved atomically by content hash. Declared HTTP length,
UTF-8, host-IP syntax, and nonempty IPv4 data are checked. Existing archives are
checked against their names' hashes. A batch publishes in one transaction with
an advisory lock to reject overlapping publications. No active snapshot changes
if parsing, downloading, or database publication fails. Valid downloaded candidate
files may remain on disk after a failure, but do not become active automatically.

An unchanged hash reuses its existing snapshot and IP rows; the successful check
time advances. Historical snapshots and files are retained. Schema creation is
explicit; an installation error does not alter the existing IP/routing tables.

The CLI emits per-source progress on stderr and a JSON summary on stdout. Errors
propagate with nonzero status. No paid API key or subscription is used.

## Lookup response

`lookup_ip.py` retains its three arguments and adds `security` to each result:

```bash
python3 lookup_ip.py 8.8.8.8 routeviews-rv2-20261001-1200.pfx2as.gz 20261001.as-org2info.txt.gz
```

`security` includes `vpn_status`, `tor_status`, matching evidence records, active
source count, recently checked source count, and the 48-hour check-age threshold.
The evidence query runs once per requested IP in the existing read-only database
transaction, then the same security result is attached to each origin-group row.
The user-owned geolocation/routing/organization SQL is unchanged.

- `listed`: an exact match in an active source checked within the last 48 hours.
- `unknown`: no sufficiently recent positive evidence. This includes no match,
  no sources, or only stale matches; it never means confirmed non-VPN/non-Tor.
- Stale matching evidence remains visible with `stale: true`, even though its
  current status is unknown.

`checked_at` measures our successful fetch/validation, not upstream observation
or publication time. An upstream list can itself be outdated despite a recent
check. `fetched_at` is the first download of that content hash. API/SQL consumers
can inspect sources and dates rather than interpreting the result as ground truth.

## Automatic daily refresh on this Mac

```bash
python3 scripts/install_evidence_schedule.py
```

The installer creates the user LaunchAgent:

```text
~/Library/LaunchAgents/io.vpnlens.evidence-refresh.plist
```

It runs the refresh on job load and every 86,400 seconds while the user session
and Mac are available. It uses the installing Python executable and this checkout's
absolute path. Credentials remain in the local `.env`, not in the plist. Moving
the checkout or Python installation requires updating the job. This schedules only
the new VPN/Tor feeds; this historical evidence-only job does not update geolocation or CAIDA. The
full-refresh replacement described above handles the wider dataset workflow. A sleeping/offline Mac is not an always-on server.

Inspect status and logs:

```bash
launchctl print gui/$(id -u)/io.vpnlens.evidence-refresh
tail -30 data/evidence/logs/refresh.stderr.log
```

To stop the installed job without deleting downloaded or database data:

```bash
launchctl bootout gui/$(id -u)/io.vpnlens.evidence-refresh
```

The plist remains installed for later login sessions; remove that one plist if
permanent removal is desired. The installer refuses to replace a different
existing job configuration.

## Verification

Run all tests against a dedicated disposable/test PostgreSQL database:

```bash
VPNLENS_TEST_DATABASE_URL='postgresql://YOUR_USER@localhost/vpn_lens_lookup_test' \
  python3 -m unittest discover -s tests -v
```

Evidence tests create isolated schemas. They cover parsing, deduplication,
unsupported IPv6 accounting, malformed/empty/truncated input, archived-file
integrity, unchanged and changed snapshots, stale evidence, multiple sources,
missing matches, rollback, and overlapping-publication rejection. Existing
geolocation/routing/organization acceptance tests remain unchanged.

Live source fetches and a scheduler run are separate from fixture proof. Initial
2026-11-02 ingestion loaded 13,573 VPN-provider records across ten source files
and 1,237 Tor records, totaling 14,810 evidence rows. These are per-source rows,
not necessarily distinct addresses or independently verified VPN exits. Live
combined lookups confirmed listed matches and unknown behavior for an unlisted
documentation address.

Final 2026-11-02 verification: all 44 automated tests passed in disposable
PostgreSQL. The installed macOS LaunchAgent completed its first run with exit
code 0; all eleven sources were reported unchanged, reusing their existing IP
rows. This proves one scheduled invocation, not future uptime. Only VPN/Tor
feeds are scheduled; geolocation and CAIDA refresh remain outside this evidence-only job; use the full-refresh replacement for those sources.
