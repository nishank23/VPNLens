# VPN evidence and automatic refresh: provider assessment

Budget decision updated 2026-11-02: **zero-budget portfolio project**. The user
selected local public VPN/Tor feeds with no API dependency. The commercial
shortlist below is background research, not the recommended next purchase.
See the [selected free-source design](superpowers/specs/2026-11-02-free-ip-evidence-design.md).

Checked 2026-11-02 against official provider documentation. No subscription was
purchased, no account was created, and no provider accuracy benchmark was run.
This is an assessment, not an approved implementation design.

## Current project

VPNLens has geolocation, routing, and organization data. There is no VPN feed.
CAIDA ownership and hosting information cannot establish that an IP is a VPN.
The RouteViews loader still pins a filename, and lookups select explicit routing
and organization snapshots. Automatic refresh must cover discovery, ingestion,
validation, and selection of a successfully published snapshot.

## Commercial shortlist

| Database | Fields useful to VPNLens | PostgreSQL and refresh | Pricing/access finding |
| --- | --- | --- | --- |
| IPinfo Privacy Detection | Separate VPN, proxy, Tor, relay, hosting flags and service name | Downloadable CSV with networks; daily database updates | Full database access requires contacting sales. API request-plan prices are not bulk-database prices. |
| MaxMind GeoIP Anonymous IP | VPN, public proxy, residential proxy, hosting and Tor flags | CIDR CSV in a dated ZIP; daily updates and automated download support | Contact the enterprise sales team for database access/pricing. |
| IP2Proxy PX2 / PX11 | PX2 supplies proxy category including VPN; PX11 adds VPN provider information | IPv4/IPv6 CSV or CIDR downloads; daily updates and downloader scripts | PX2 lists $15,980/year for the new-customer internal-use Site License. The $799/server Standard option is limited to existing customers. SaaS/redistribution needs a quote. PX11 is quote-based. |

Sources:

- [IPinfo database schema and formats](https://ipinfo.io/developers/privacy-detection-database)
- [IPinfo downloads, daily updates and full-access sales](https://ipinfo.io/data/proxy-vpn-detection)
- [MaxMind database product and daily updates](https://www.maxmind.com/en/geoip-anonymous-ip-database)
- [MaxMind CSV schema](https://dev.maxmind.com/geoip/docs/databases/anonymous-ip/)
- [IP2Proxy PX2 pricing, eligibility, formats and updates](https://www.ip2location.com/database/px2-ip-proxytype-country)
- [IP2Proxy PX11 provider field and licensing](https://www.ip2location.com/database/px11-ip-proxytype-country-region-city-isp-domain-usagetype-asn-lastseen-threat-residential-provider)

MaxMind documents that VPN networks without recognizable registration names may
only receive a hosting flag. Its standard CSV does not expose a VPN service name.
IPinfo Extended adds observation dates, confidence and evidence fields; consider
it only if those fields justify its separate quote. IP2Proxy LITE primarily
covers public proxies, so it is not a substitute for commercial VPN coverage.

- [IPinfo Extended schema](https://ipinfo.io/developers/privacy-detection-extended)
- [IP2Proxy LITE scope](https://lite.ip2location.com/ip2proxy-lite)

## Recommendation and decision still needed

IPinfo is the first technical candidate because its explicit flags and service
name map directly to an explainable response. MaxMind is the alternative to
evaluate for a simpler flag-based product. This is a fit judgment, not a claim
that either has better accuracy or a lower price.

Before purchasing, obtain a bulk-database quote that explicitly covers the
planned public lookup API, permitted output fields, update access, retention,
and IPv4 coverage. IPv6 can remain outside the current project scope. A sample
or trial proves integration only; compare the same labeled VPN exits, ordinary
ISP addresses, and non-VPN hosting addresses before making coverage claims.

IP2Location's current LITE terms include a competing-services restriction relevant
to an IP intelligence API. Confirm permission for the planned public service;
do not assume an internal-use database subscription grants public API rights.
[Current LITE terms, section 5(c)](https://www.ip2location.com/lite-terms)

## Proposed next refresh increment

Start with one Python command, then schedule that command after choosing its host
and cadence. Proposed acceptance criteria, subject to the user's architecture
and failure-policy review:

1. Discover releases through each provider's supported index/download interface.
2. Skip an already completed release using recorded identity and content metadata.
3. Download to a temporary file; validate the archive and expected data format.
4. Run ingestion/transformation and count checks; select the new snapshot only
   after the required steps succeed. Preserve the last usable lookup data on failure.
5. Record source, release date, download/load status and counts. Prevent overlapping
   refresh jobs. Keep each source's date explicit; releases need not share a date.

CAIDA can be the first refresh adapter. IP2Location's documented downloader uses
an account download token, which is not configured in the current project.
[Official download automation](https://blog.ip2location.com/knowledge-base/how-to-automate-ip2location-bin-database-download/)

VPN classification remains a separate feed addition. A missing match is unknown,
not proof that an IP is not a VPN. A hosting flag is not a VPN flag. Agree the
response semantics and snapshot model with the user before implementing VPN SQL.
