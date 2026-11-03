# Zero-budget VPN and Tor evidence: proposed next slice

Date: 2026-11-02

The user clarified that VPNLens is a zero-budget portfolio project and chose
local public VPN/Tor feeds first, with no API dependency. Enterprise bulk-data
purchases are outside this project plan. This records the chosen direction and
verified source findings; database modeling and failure policy remain user-owned.
Implementation authorized by the user on 2026-11-02, including the evidence table and remaining plumbing. The loader, snapshot publication, local lookup and daily macOS refresh are now implemented; see [usage and verification](../../ip-evidence.md).

## Approaches considered

- Local public feeds: selected. No per-lookup service quota or subscription;
  partial and potentially stale coverage must remain visible.
- Local feeds plus VPNAPI.io: deferred. Its documented free plan allows 1,000
  requests/day, but adds credentials, quotas, network dependency and usage terms.
  It is not needed for the first portfolio milestone.

The existing geolocation, routing and organization pipelines remain reusable.
The portfolio value is reproducible ingestion, indexed lookups, source tracking,
automatic refresh, tests, and clearly bounded conclusions.

## Verified free sources

### VPN server association

Candidate: [Open Source VPN IP Lists](https://github.com/Joe12387/open-source-vpn-ip-lists).

- The repository contains a [CC0-1.0 license](https://raw.githubusercontent.com/Joe12387/open-source-vpn-ip-lists/master/LICENSE).
- Its README lists ten VPN provider files, with one host IP per line. The
  maintainer describes these as derived from provider-published server data;
  that upstream collection claim was not independently audited here.
- A representative [Mullvad file](https://raw.githubusercontent.com/Joe12387/open-source-vpn-ip-lists/master/mullvad.txt)
  was accessible during research. Published lists include IPv4 and IPv6.
- The README explicitly distinguishes server/entry/egress addresses and warns
  that entry and exit pools can differ. A match means association with a listed
  VPN service, not proof that the current request traversed a VPN exit.
- An absent address is unknown. Retired addresses and incomplete coverage can
  cause false positives or missed VPNs. Record source identity and freshness.

Start the implementation with a small explicit allowlist of provider files and
expand after validation, rather than scraping arbitrary links or executing
upstream scripts. Initial lookup scope remains IPv4. Decide with the user
whether IPv6 entries are stored or counted as unsupported during ingestion.

### Tor exit association

[The Tor Project public exit list](https://check.torproject.org/torbulkexitlist)
was accessible during research. It is a separate signal: Tor is not a VPN.
Preserve the source identity, downloaded file/hash and fetch time. A fetch time
must not be presented as the source's observation time.

## Website investigation findings

[VPNAPI.io documentation](https://vpnapi.io/api-documentation) exposes VPN,
proxy, Tor and relay flags and documents a free quota of 1,000 daily requests,
resetting at 00:00 UTC. Its [pricing page](https://vpnapi.io/pricing) confirms
the free tier. API lookup access does not grant a complete downloadable corpus.
Its [free-use terms](https://vpnapi.io/terms-of-use) specify personal,
non-commercial use; that is separate from a production customer deployment.

The indexed [Teoh About page](https://ip.teoh.io/about/) states that its current
IP information comes from VPNAPI.io; its earlier multi-API voting description is
struck through. The indexed [legacy API page](https://ip.teoh.io/vpn-proxy-api)
states that the older API is no longer maintained. Do not count the Teoh site
and VPNAPI.io as independent evidence sources for consensus.

A REA browser navigation to the live Teoh About URL returned a Cloudflare
security-verification page. It did not expose the current application backend.
Evidence: `ev_1b691375f18bd72edf1352111c083ab32a744a97063c80b446943a3e8f96639e`.
The owned browser was terminated after capture. No anti-bot challenge was bypassed.
Website descriptions are published claims, not recovered detection algorithms;
no accuracy percentages or private database coverage were verified.

## Proposed implementation and acceptance

1. A Python refresh command downloads selected plain-text feeds to temporary
   files. These inputs are not ZIP archives. Validate IP syntax and nonempty
   supported data before handing a snapshot to ingestion.
2. Record content hashes and source metadata; skip an unchanged completed
   snapshot. Keep a last successful snapshot available when a download fails.
3. Ingest using the user-reviewed schema and transaction policy. Keep independent
   evidence rows when one IP is listed by multiple providers or sources.
4. Add local lookup evidence with the matched source, provider where available,
   indicator type, snapshot identity and fetch time. Keep hosting, VPN-server
   association and Tor-exit association distinct.
5. Test positive matches, no match, stale or failed sources, duplicate evidence,
   changed/unchanged refreshes and rollback. Preserve existing lookup tests.
6. Schedule the tested refresh command after agreeing its host and cadence.
   A local Mac must be awake for scheduled work; an always-on deployment is a
   separate operational choice. No paid hosting is required for a local demo.

A failed or missing source must not silently produce a confident negative.
Response labels, staleness thresholds, activation behavior and retention are
proposals to settle with the user, not policies already approved here.

## Next user-owned task

Sketch storage for one evidence record. Consider IP, indicator type, provider
(optional), source identity, source version/file, content hash, fetch time and
snapshot identity. Decide the uniqueness key and replacement/rollback policy.
Use the smallest model that preserves multiple independent evidence records.
Codex will review that attempt and implement routine downloading, parsing,
ingestion plumbing, tests and documentation against the agreed contract.

This slice adds evidence; it does not claim exhaustive commercial VPN coverage
or production-grade geoblocking accuracy. API and frontend work follow the
reviewed data and lookup contract. No subscription, API key or payment is needed
for the selected local-feed implementation.
