# VPNLens frontend visual review

App-screen rules govern this workspace. Picture-count and cinematic-entrance caps
for marketing pages do not apply. Scores are an internal critique, not an award.

ROUND 1
Seen in one second: an IPv4 investigation tool with live readable results and JSON.
Idea (one sentence): independently sourced IP facts become an inspectable evidence lens.
Live thing: real IPv4 lookup against the local FastAPI backend.
Layout words by section: shell=tinted frame / search=joined input / result=two panes / sources=records and freshness.
Scores: design 7.0 · usability 6.8 · creativity 7.0 · content 8.5 → overall 7.1.
Caps applied: app-screen criteria; no failed inspector measurements.
Top three problems (most visible first), each with the screenshot it shows in and the fix:
1. tablet-fold.jpg: narrow JSON column wraps identifiers aggressively. Switch tablet to readable/JSON tabs.
2. desktop-fold.jpg and mobile-fold.jpg: raw JSON and data labels are too small. Use 13px code/data labels, retain 12px metadata, enable tabular figures.
3. desktop-fold.jpg: mobile menu leaks into desktop chrome, API documentation wraps, and top bar misses the dealt 48px height. Correct visibility, label, and geometry.

All six listed round-one screenshots were opened: desktop, tablet, and mobile fold and full-page sheets.

ROUND 2
Seen in one second: readable source-backed IP results with a clear search action.
Idea (one sentence): the response and its independent evidence remain inspectable together.
Live thing: same live lookup, with readable/JSON tabs on tablet and phone.
Layout words by section: shell=framed sheet / search=joined input / result=readable plus JSON / narrow result=two tabs.
Scores: design 7.0 · usability 7.8 · creativity 7.0 · content 8.5 → overall 7.4.
Caps applied: app-screen criteria; inspector reports 0 FAIL and 0 WARN.
Top three problems (most visible first), each with the screenshot it shows in and the fix:
1. desktop-page-01.jpg: JSON's intrinsic height stretches the whole result row, leaving a large empty band below readable evidence. Size the scrollable code pane from the readable column using a cleaned-up ResizeObserver.
2. desktop-fold.jpg: JSON now reads comfortably; maintain that type size while constraining its viewport rather than shrinking text.
3. tablet-fold.jpg and mobile-fold.jpg: retain the improved tab layout and check its keyboard focus/selection behavior in the browser.
All six round-two screenshots were opened. An earlier second-pass attempt saw a stale build after a keyboard-event type error; that attempt was discarded and the reported second pass followed a successful production build.

ROUND 3 — final, 2026-11-02
Seen in one second: search one IP and inspect its independently sourced evidence.
Idea (one sentence): readable findings stay beside their exact API object and source trail.
Live thing: real local IPv4 lookup, plus actual source/check metadata.
Layout words by section: shell=framed sheet / search=joined input / result=readable plus scrollable JSON / sources=snapshot index and feed table.
Scores: design 7.8 · usability 8.2 · creativity 7.0 · content 8.6 → weighted overall 7.84/10 (displayed as 7.8).
Caps applied: app-screen criteria; no picture-count or cinematic-motion caps. No measurements failed.
Top three earlier problems and final disposition:
1. desktop-page-01.jpg: the tall JSON no longer leaves a large empty band below the readable pane; code scrolls within a viewport matched to the readable content.
2. tablet-fold.jpg and mobile-fold.jpg: readable/JSON tabs keep identifiers readable; keyboard arrows, Home, and End select and focus the correct tab.
3. desktop-fold.jpg: sidebar, documentation link, and 48px top bar align; the mobile menu is absent at desktop width.

All 12 final screenshots were opened after the final production build: desktop, tablet, and phone fold/full-page sheets for Lookup and Sources. Visual inspection and automated layout measurements agree. The final Sources bundle was also checked in the interactive browser without new console warnings.

Answers to the seven app-screen critique questions:
1. Lookup asks what is known about this address. The IP and separate VPN/Tor states answer first. Sources asks which records support lookup and how recently they were checked; the summary and snapshot records answer first.
2. Blocks share the sheet edges. The JSON viewport follows the readable pane height. No accidental full-width blank band remains. The sidebar's lower explanatory copy is intentional navigation framing.
3. Pale teal frames the workspace; teal marks source/status details. The dark lookup button is the primary action. The original lens mark and actual IP data provide the face.
4. The default 8.8.8.8 screen agrees with its JSON: one origin group, ASN 15169, Google LLC, US geolocation and organization country, unknown VPN/Tor. The Sources screen shows two routing snapshots, one ownership snapshot, and 11/11 checked feeds. The Oman browser case retains two origin groups and three owner rows while summarizing two unique ASNs. Feed record counts are not summed into unique-IP coverage.
5. Zero evidence matches reads 0 matches, while missing country/date/owner data has explicit unknown/unavailable fallbacks. None of these counts is a notification queue badge.
6. The source trail uses labels rather than an unlabeled chart. VPN/Tor states and freshness use text as well as colour. No chart legend or collision is present.
7. Phone navigation folds into a menu; readable/JSON tabs replace narrow columns. The source table scrolls within a labelled region with its first column retained, without global page overflow.

Remaining limits: the long source table requires horizontal scrolling on a phone; the visual language is intentionally restrained and not highly experimental. This is a local IPv4 workspace with partial public-list coverage, not an accuracy-certified detector. Browser-disabled JavaScript and native reduced-motion emulation were unavailable; static/controlled DOM checks are identified separately in the verification report.

Gates: Lookup and Sources each 0 FAIL / 0 WARN at 1440, 768, and 390. Source lint: 0 FAIL / 1 WARN, intentionally retained monospace on the IPv4 identifier input (styles.css). No allow flag was used. App-screen rules permit monospace identifiers. No new feature or visual round is needed before user review.
