# Monthly IP2Location download

The user requested automatic downloads when a new month arrives. This completes
the already approved optional geolocation downloader using the existing daily
refresh job, PostgreSQL transaction policy, ZIP validation, and status file.
No schema, core lookup SQL, or scheduler replacement is needed.

Use the official account-token download endpoint for DB11LITE IPv4 CSV. Existing
IP2LOCATION_DOWNLOAD_URL remains an override; otherwise read the local
IP2LOCATION_DOWNLOAD_TOKEN. No credentials enter logs, status files, or Git.

Download immediately for first setup or recovery when loaded geolocation is
missing. After that, choose a deterministic per-database day in the month's
first week, following IP2Location's documented recommendation. The daily job
catches up on its next available run if that date was missed. Skip remote fetches
once a validated load/check completed for the current UTC calendar month. Failed
loads retain working rows and remain eligible for the next daily run. Explicit
local files remain supported. An explicit recovery flag can force a fresh fetch.

Calendar download month is not a claim about the publisher's release date.
Acceptance: token URL encoding and URL override, first setup, same-month skips,
new-month eligibility/catch-up/year rollover, failed-load retry and rollback,
missing-data recovery, local-file override, no token persistence, and unchanged
baseline tests. Live verification requires the user's own token in local .env.

Reference: https://lite.ip2location.com/faq

Status: implemented; 91 fixture/database tests passed. Authenticated provider download and same-month network skipping verified on 2026-11-02. See ../../monthly-ip2location.md.
