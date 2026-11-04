# Public demo implementation verification

Verified locally on 2026-11-03 against the built frontend and existing PostgreSQL data.
The work remains uncommitted on `codex/vpn-evidence-expansion`; no public deployment or GitHub push was performed.

## Automated checks

| Check | Result |
| --- | --- |
| Backend regression suite | 220 passed, including 22 new policy/visitor/API tests |
| Frontend regression suite | 103 passed, including request races, exact JSON, invalid-input clearing, legacy residential uncertainty and Sources-to-search keyboard focus |
| Production frontend build | Passed, TypeScript and Vite |
| Frontend format check | Passed |
| Scoped backend Ruff | Passed |
| Whitespace check | Passed |
| App-screen static lint | 0 failures, 1 warning |

The lint warning is the About disclosure's shadow. It is an actual floating overlay; result panels have no shadow. Backend tests use the repository's disposable PostgreSQL runner and isolated schemas, never the project database. The first frontend test attempts were blocked by sandbox writes to Vite's cache; the completed suite ran with approved filesystem access. The final fixes were applied after an interrupted automatic approval review became available again.

## Local data and HTTP evidence

| IP | Existing security assessment | Demo action | Lookup compared with legacy route |
| --- | --- | --- | --- |
| `103.108.230.50` | Listed, direct UrbanVPN association | block / `recent_vpn_evidence` | Equal |
| `8.8.8.8` | Unknown | allow / `no_recent_blocking_evidence` | Equal |
| `216.246.27.1` | Unknown, network-only | allow / `no_recent_blocking_evidence` | Equal |
| `185.186.206.1` | Unknown, two tied origin groups preserved | allow / `no_recent_blocking_evidence` | Equal |

These checks used existing local snapshots, not fresh VPN connection measurements. No feeds were downloaded or refreshed for this feature. They establish four local compatibility cases, not general detection accuracy. Source UI showed 14 of 14 scheduled security sources recently checked. `/v1/connection` correctly returned the local public-IP-unavailable state because the transport peer was loopback.

Real PostgreSQL fixtures cover overlap, weak/stale/future/unapproved/expired evidence, original observation expiry, source health, empty required geolocation data, proxy trust/spoofing, malformed chains, no upstream I/O, legacy serialization and tied origins. A missing core dataset returns no decision. The consuming streaming platform still owns enforcement.

## Browser and responsive proof

CUA checked the production build through `http://127.0.0.1:8000/`, served by FastAPI with `--no-proxy-headers --no-access-log`. The browser viewport presets 1440, 768 and 390 produced observed CSS widths 1309, 698 and 354 because of the browser's display scaling. No horizontal page overflow occurred at those widths. The positive result ended at about 602px in the phone's 767px viewport. The main positive-result view had 38 words.

Verified interactions: initial loopback fallback, manual positive and unknown queries, invalid input removing a previous allow, Details, the complete `{lookup, decision}` JSON envelope and correct endpoint, Sources, and Ctrl+K returning from Sources with focus in the IP field. Automated tests additionally cover exact JSON copying, cancellation, late completions, retry target preservation, unsupported IPv6, degraded health, and live reduced-motion cleanup.

Screenshots:

- [Desktop](screenshots/public-demo-desktop.jpg)
- [Tablet](screenshots/public-demo-tablet.jpg)
- [Phone](screenshots/public-demo-phone.jpg)

## Visual review and limitations

The approved Achromatic ledger direction, seed `964701165`, preserves IBM Plex, Solar icons and the original lens mark. The IP and finding lead; the form, result and optional panels share edges; status colour stays on evidence and policy. The three detection categories share one strip rather than separate metric cards. Missing/unknown values are not presented as zero or safe. The phone stacks the same finding and retains manual entry, Recheck and disclosures. A chart or decorative image would not add useful information to this single-IP question.

Existing licensed assets were reused; there are no invented customers, sample-result fallbacks, new data dependencies, Three.js or AI classifier. GSAP gives brief feedback and Lenis is the only scroll engine, enabled for expanded views. Static first-frame content and the no-JavaScript fallback were reviewed in source; reduced-motion behavior is covered by tests. Browser controls did not expose JavaScript-disabled or reduced-motion emulation, so no such browser check is claimed. The separate skill inspector was not run because browser interaction was confined to CUA; static lint, DOM measurements and screenshots supplied the actual visual checks.

Automatic visitor lookup works only when the request carries a public IPv4 or a correctly configured trusted proxy chain. Public hosting, TLS, request limits, hosting logs, infrastructure configuration and costs remain release work. Local tests do not establish remote CI success or production operation.
