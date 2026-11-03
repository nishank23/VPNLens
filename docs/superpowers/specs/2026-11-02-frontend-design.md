# VPNLens frontend: evidence investigation workspace

Date: 2026-11-02
Status: Design approved by the user on 2026-11-02; implementation and local verification complete. Final user review pending.
Evidence: [frontend verification](../../frontend-verification.md).

## Intent and approved direction

Build and connect a working frontend to our existing FastAPI backend. The user
selected the light investigation workspace: white panels, graphite text,
restrained teal evidence accent, and readable results beside inspectable JSON.
VPNAPI.io is a visual reference only, not a dependency or a source of copied code,
assets, identity, claims, or prices. No paid service, frontend AI inference,
public deployment, or GitHub push is included.

The primary visitor is someone investigating one IPv4 address, including a
recruiter evaluating the actual project. The first job is submitting an IP and
understanding the returned evidence. There is no login/account system to imply.

## Verified project and reference

The active implementation is /Users/nishankbansal/Documents/VPNLens, branch main,
with existing uncommitted backend/evidence work that must be preserved. There is
no JavaScript frontend or existing package manifest; dashboard/app.py is empty.
The FastAPI process is running locally on port 8000. Its current contract includes:

- GET /v1/lookup/{ip_address}: ip, selected_sources, results.
- Each result preserves geolocation, prefix, origin_group, routing snapshot,
  nested ASN owners, and separate VPN/Tor listed/unknown evidence.
- GET /v1/sources: routing/organization snapshots, security source check dates,
  geolocation availability, and credential-free refresh status.
- GET /health/ready and /docs.

Real read-only examples were inspected: 8.8.8.8 resolves to US / Mountain View,
8.8.8.0/24 and ASN 15169. 185.186.206.1 currently resolves to OM / Muscat with two
origin groups and owner-array lengths one and two. These are current examples,
not fixed fixtures or permanent classifications.

The VPNAPI reference uses a prominent IP search and raw JSON output, followed by
marketing sections. Keep its clarity of action and result. Create a materially
new workspace and a source-oriented information hierarchy. Do not inherit its
binary VPN/proxy flags, accuracy claims, pricing, map, or identity.

## Approaches considered

- Working light workspace connected to our backend: selected by the user.
- Clickable design first with API integration deferred: not selected.
- Dark data-terminal workspace or minimal report layout: offered; the user selected
  the light investigation workspace.

Builder proposal for implementation: React, TypeScript, and Vite in frontend/,
with plain CSS tokens. No framework migration exists to preserve. Keep the user-
reviewed SQL, schema, classifiers, and data refresh behavior unchanged.

## Subject inventory, idea, and questions

VPNLens owns: IPv4 range lookup; longest-prefix ties; comma-group ASN members;
independent routing and ownership snapshots; distinct organization and IP country;
11 public evidence feeds; listed versus unknown; stale matches retained;
monthly geolocation downloads; read-only PostgreSQL; inspectable JSON.

Idea: On this screen, VPNLens's independently sourced lookup becomes an evidence
lens: each result exposes what supports it and when that source was checked.
The signature is a source-to-finding trace built from real returned fields,
not a decorative globe, synthetic risk score, or network animation.

The screen's main question: What do we know about this IP, and what supports it?
Its live action is IP lookup. Its finding is computed from the response: listed
VPN/Tor evidence when present, otherwise a clear statement of incomplete evidence.

Next questions become blocks: Where is the estimated location? Which routing
prefix/origin groups matched? Who owns each ASN? Which source records support a
VPN/Tor association? Which snapshots were selected? What is the exact API response?

## Art direction and asset plan

Apply design-taste-frontend app-screen rules as the primary design system and
build-awwwards-quality-sites for authored craft, interaction, motion discipline,
and validation. This is a worked-in application, not a long marketing landing
page; app-screen rules govern density, typography, imagery, and feedback.

Direction: Framed sheet, seed 20261102, drawn for devtools. White workspace inset
8px inside one pale frame; 228px desktop sidebar and 48px top bar; no resting
shadows. IBM Plex Sans at 22 / 16 / 14 / 12px; IBM Plex Mono for IPs, identifiers,
and raw JSON only. Teal #1b6c80 on evidence/data and the selected state; main
text #131416. One 24px gutter, surfaces #ffffff and #f4f6f8. The frame can take a
very pale blue-green tint as the product's face; no gradients, glows, or glass.

The chosen face is the product-tinted frame and a custom lens mark, with IPs and
prefixes carrying IBM Plex Mono. The data carries the accent. Use Solar interface
icons through Iconify, and locally bundled open-source IBM Plex font files with
licenses retained. The original simple brand mark and source data graphic are
allowed authored SVG. No stock photographs, avatars, testimonials, logo wall,
illustrative SVG scenery, or borrowed reference assets are needed for this app.

## Layout and content

Desktop: named VPNLens shell with Lookup, Sources, and API documentation. The
workspace opens with a compact title and the primary search. Below it, two panes:
readable evidence on the left and raw API JSON on the right. Both begin above the
fold at 1440x900. Within a 1440px viewport, 228px sidebar plus 8px outer inset leaves
1204px; 24px padding on each side leaves 1156px. A 24px column gap leaves 1132px
for the two panes, divided approximately 60/40. No empty full-width KPI strip.

The readable pane leads with the searched IP and separate VPN/Tor evidence states.
It shows location, every tied origin group and its nested owners, then source
provenance. Country names may be derived from returned country codes, with code
fallbacks. A source trace uses independent branches: geolocation, routing,
ownership, and security are separate observations, never a false causal chain.

The JSON pane displays the exact returned object, including selected_sources;
copying copies that object, not a simplified reconstruction. Show genuine response
status and elapsed client request time when measured. JSON scrolls inside its own
pane, not sideways across the page. Escape all returned text; never inject raw HTML.

Sources is its own view, showing actual loaded files, dates, check ages, failed or
manual-update states, and next geolocation download eligibility. A refresh control
only re-fetches metadata; it does not run an ingestion command. API docs opens the
existing backend /docs page. Do not add dead navigation or pretend AI functionality.

At tablet width the sidebar folds and panes stack or use labeled tabs. At 390px,
search and the first result remain early in reading order, targets are at least
44px, owner rows become compact lists, and JSON is a disclosure/tab below the
readable result. All returned tied groups and owners remain accessible.

## API behavior and honest states

Use our backend only; no VPNAPI.io request, external visitor-IP service, analytics,
or token in the browser. Start with a clearly labeled live example lookup of
8.8.8.8. Users can replace it with any IPv4 host; IPv6, CIDRs, and domains remain
unsupported and are labeled accordingly.

Validate and trim IPv4 input before sending. Support Enter, labeled fields,
visible focus, and keyboard-usable examples. Fetch through a small typed client
with AbortController and a bounded timeout. Cancel superseded requests so an old
response cannot replace a new lookup. Keep the displayed result's IP unambiguous.

Support loading, no-match, unknown, stale, invalid-input, disconnected-backend,
503, and unexpected-error states. Loading preserves panel headings. A new IP clears
old results rather than presenting them under the new query. A repeated lookup
may retain its correctly labeled previous result while refreshing. Failed calls
offer Retry. No fake successful output or silent sample-data fallback.

Unknown is never rendered as clean, safe, not a VPN, false, or zero risk. A stale
positive remains visible as stale evidence while current status remains unknown.
Distinct organization country and estimated IP location stay labeled separately.
Missing metadata is a dash or unavailable; zero counts remain actual zeroes.
No proxy/relay/crawler labels are inferred from fields our API does not expose.

## Integration and motion

Builder proposal: Vite development and preview servers proxy /v1 and /health to
the local backend. Production builds can be served by FastAPI at / with /assets
mounted only when the built directory exists. Register those routes after existing
API routes. No catch-all route that masks API 404s. Frontend-only hash views avoid
needing server rewrites. Build artifacts/node_modules stay out of Git.

GSAP is the primary animation library for result-arrival and interaction feedback;
search and navigation are usable immediately. No cinematic app entrance, flashing
verdict, animated counters, or indefinite particle field. CSS handles hover/focus.
Choose Lenis as the sole smooth-scroll library, scoped to the longer Sources
view; lookup, code panes, and touch scrolling retain native behavior. Do not
install Locomotive. Integrate Lenis with GSAP/ScrollTrigger where applicable,
refresh after layout/font changes, and destroy listeners/tickers on view cleanup.
Reduced motion renders final states and bypasses smooth scrolling. Three.js is
excluded because the current API has no spatial coordinates or dataset that
justifies WebGL. The evidence interface itself is the focal asset.

## Acceptance and stop condition

1. A production build renders a working IP lookup against the existing API.
   8.8.8.8, the tied-origin Oman example, a listed VPN, a Tor exit, and an unknown
   example preserve the actual backend semantics.
2. Raw JSON matches the returned object; copy succeeds or reports failure honestly.
   Sources/health displays match backend responses. No mock result becomes live proof.
3. Unit checks cover validation, derived owner/evidence display, and error handling;
   existing backend tests pass after the small static-serving integration.
4. Run the production build, skill lint, and app inspector at 1440, 768, and 390.
   Fix every FAIL, open every resulting screenshot, record critique and intentional
   warnings, and test search, navigation, keyboard, narrow layout, reduced motion,
   and API-unavailable behavior. Verify no global horizontal overflow.
5. No-JavaScript output provides a usable explanation and link to API docs; motion
   failure never hides controls or text. New data/action states remain accessible.
6. Document design/asset provenance, startup/build commands, integration, actual
   test results, and remaining risks. No public deployment, commit, or push.
7. Stop after the integrated frontend is reviewable. AI remains a future proposal.

## AI proposal for later discussion

The first useful AI feature is an evidence explainer: validate the user's IP,
retrieve the same structured lookup JSON, and ask a language model to explain
only those facts, preserving unknown/stale states and citing source records.
A deterministic summary remains the zero-cost fallback. Natural-language questions
can later call the same bounded lookup tool; the model does not write or execute
arbitrary SQL. Local inference trades hosted API cost for hardware/latency.
Provider/model choice and any spending require a separate decision.

Test explanations on missing metadata, conflicting origins, stale evidence, and
organization-country versus IP-country distinctions. No model output becomes a
new VPN label. Learned VPN classification is a different future task requiring
independent labeled data and precision/recall evaluation; these positive public
lists plus unknown IPs do not supply trustworthy negative labels.

## Builder decisions for user review

The user selected a connected frontend and light workspace. React/TypeScript/Vite,
same-origin static serving, live example-on-load, specific navigation, motion scope,
and detail layout were approved before implementation. Final code and product review remain with the user.
