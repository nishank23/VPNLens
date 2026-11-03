# Monthly IP2Location automation

Implemented 2026-11-02 following the user's request. The existing daily macOS job
now supports a monthly geolocation download without browser automation.

## Configure privately

1. Sign in at https://www.ip2location.com/log-in.
2. In the account Download page, copy the download token.
3. Add `IP2LOCATION_DOWNLOAD_TOKEN=YOUR_DOWNLOAD_TOKEN` to local `.env`.
4. Run `python -m vpnlens.refresh --dataset geolocation` for the initial check.

Do not commit `.env` or paste the token into chat. The command builds the official
request for `DB11LITE`, the provider's IPv4 CSV package. An explicitly configured
`IP2LOCATION_DOWNLOAD_URL` takes priority. Explicit `--geolocation-file` input
continues to load a local file even when automatic downloads are configured.

## Behavior

The first automatic check downloads immediately. Later downloads use a stable
per-database date between the first and seventh of each UTC calendar month.
Eligibility catches up after that date if the Mac was unavailable. A successful
validated download/load, or verified unchanged data, records `download_month` and
prevents another remote fetch during that month. `next_download_on` exposes the
next eligible date. A missing loaded dataset triggers recovery even when the
current month's earlier check succeeded. Source checks do not assert the actual
upstream release/observation date.

Failed downloads/ZIP parsing/loads retain the previous committed dataset and
previous successful download month. The existing daily job retries on its next
available run. `--force-geolocation-download` is an explicit recovery override;
normal operation uses the monthly limit. No schema or core lookup SQL changed.
Credentials are excluded from status files and logs. The local `.env` was not
modified by Codex.

## Verification

All **91 automated tests passed** in isolated PostgreSQL, including 12 new
monthly policy/download cases. They cover token encoding and URL override,
initial setup, same-month network skip, first-week scheduling/catch-up, year
rollover, missing-data recovery, unchanged-month content, failed ZIP rollback and
retry, explicit local files, explicit recovery override, and token-free status.
Downloads in these tests use fixtures; this is not an authenticated live-provider
download. Authenticated live verification subsequently passed; see the section below.
The existing backend and its real-data verification are documented separately in
[backend v1 verification](backend-v1-verification.md).

Official references:
- https://lite.ip2location.com/faq
- https://www.ip2location.com/free/downloader

## Authenticated live verification (2026-11-02)

After the user configured the download token in local `.env`, the ordinary
`python -m vpnlens.refresh --dataset geolocation` command completed successfully
against the real provider and project database. The token was not displayed,
recorded in this report, or added to Git. `.env` is ignored by Git.

- Download: 49,717,261-byte ZIP containing the expected DB11 CSV.
- Validated and committed geolocation rows: **2,965,251**.
- Successful download month: `2026-11`. This is the download
  calendar month, not independently verified publisher observation metadata.
- Next eligible download date: **2026-12-05**; the existing
  daily job catches up when the Mac and user session are available.
- Second invocation of the same CLI returned `not_due`. HTTP access was replaced
  with a failing spy for this invocation: it recorded **zero calls**. The ZIP's
  modification time also remained unchanged.
- Live `/health/ready`, `/v1/lookup/8.8.8.8`, and `/v1/sources` returned **200**.
  Readiness reported `ready`; source metadata reflected the successful download.

No product code changed during this check. The previous 91 passing automated
tests remain applicable. This proves one authenticated download and same-month
skipping, not future provider availability or geolocation accuracy. No commit
or GitHub push was performed.
