# VPN Evidence Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand local multi-provider evidence and add an auditable exit recorder without inventing residential-proxy classifications.

**Architecture:** Build collection and recorder artifacts independently, then bind them to the user-reviewed SQL contract and existing read-only API. Retain legacy evidence and make extended publication/reads opt-in. Apply the approved evidence and expiry rules without changing routing/geolocation/organization SQL.

**Tech Stack:** Python 3.12, unittest, psycopg/PostgreSQL 18, FastAPI/Pydantic, React/TypeScript/Vite/Vitest, dnspython 2.9.1.

---

Approved design: [VPN evidence expansion](../specs/2026-11-02-vpn-evidence-expansion-design.md).
Active repository: /Users/nishankbansal/Documents/VPNLens. Run all commands from that directory.
This is a planning artifact; code fences are instructions for future execution, not implemented code.

## Execution order and ownership

### Execution delegation update - 2026-11-02

The user subsequently requested that the agent complete all implementation, including schema and core SQL, autonomously and report when ready. This supersedes the earlier user-attempt SQL checkpoint for this execution. The historical approval and proposed ownership text below is retained for context. Fresh implementation agents and independent specification then quality reviews are required for each coherent task; the final diff remains for user review. At that initial delegation, Git publication was not yet authorized; the later authorization below now governs final staging, commit and push. Deployment, paid services and automatic VPN control remain outside scope. Disposable migration and lookup proof plus independent schema review precede any live migration.

The user later explicitly requested resuming the unfinished work and committing/pushing after completion. Final staging, a Conventional Commit and a normal push of the current feature branch are therefore authorized after all implementation, review and acceptance gates; the coordinating agent owns those final Git actions. No force push, main-branch merge, paid service, public deployment or automatic VPN control is authorized.

Execution status on 2026-11-03: public collectors and recorder producers passed independent specification and quality reviews (39 and 29 focused tests). Additive SQL/store/setup passed independent specification and quality reviews with 182 disposable tests; three nonblocking status/test-precision followups are included in runtime integration. Runtime integration, minimal UI and the concise README diagrams are complete and independently reviewed. Final gates passed: 198 backend tests, 81 frontend tests, scoped lint, formatting, production build and diff check. Actual local HTTP and desktop/phone UI acceptance passed; the real recorder path remains unmeasured. The coordinating agent is completing the explicitly authorized final Git publication.

The approved scope has two independently testable producers and one integration consumer. Separate plans prevent database work from blocking pure Python work or prematurely choosing the user's physical schema.

1. [Public collectors](2026-11-02-public-evidence-collectors.md): working CLI that validates and archives candidate batches; it cannot activate database evidence.
2. [Exit recorder](2026-11-02-exit-recorder.md): working baseline/capture/import/review artifact workflow; local review alone cannot change live lookup before integration.
3. [Database/API integration](2026-11-02-evidence-integration.md): reviewed schema/query contract, transactional publication, feature flag, policy projection, source health, minimal UI and rollback.

Shared artifact helpers are created by the collectors plan first. After that, collector adapters and recorder modules can be built independently. SQL review can happen alongside those Python tasks. Do not start live database integration before the SQL checkpoint passes.

The user owns architecture, data modeling, core SQL, failure policy and final review. Preserve that division: present the contract and let them attempt schema/queries first; review and hint before replacing core SQL. Routine Python, API/configuration, tests and documentation are agent work. A complete SQL solution is deliberately not embedded in these plans because that would preempt the user's explicit ownership.

No worktree creation, staging, commit, push, public deployment, paid resource, VPN installation or network-setting change is authorized by this planning step. During execution, use the active checkout unless the user requests isolation. Preserve all existing uncommitted work. Commit checkpoints mean summarize a reviewable diff; run git commit only when requested. A later push always needs explicit approval.

## File map

| File/group | Responsibility |
| --- | --- |
| vpnlens/evidence_contract.py | Canonical JSON, immutable private artifacts, public IPv4 normalization |
| vpnlens/evidence_collectors.py | Host/CIDR/CSV/DNS adapters, bounded transports and candidate preparation |
| vpnlens/evidence_collect.py | Candidate-only public collection CLI |
| config/evidence_sources.json | Reviewed source registry and provenance |
| vpnlens/observation_contract.py | Profile/receipt validation, eligibility and immutable review artifacts |
| vpnlens/observation_transport.py | Explicit system/proxy IP-echo transport |
| vpnlens/observe.py | Baseline/capture/import/approve CLI, with later publication binding |
| vpnlens/evidence_store.py | Execute user-reviewed migration/publication/read/observation SQL contracts |
| vpnlens/evidence_policy.py | Pure evidence classification and legacy-compatible projection |
| sql/evidence_v2_schema.sql | User-authored additive migration |
| sql/evidence_v2_validate.sql | Agent-written compatibility query against the reviewed schema |
| sql/evidence_v2_publish.sql | Agent-written publication against the reviewed user model |
| sql/evidence_v2_lookup.sql | User-authored enabled/current containment and observation read |
| sql/evidence_v2_sources.sql | Agent-written status query against the reviewed user model |
| sql/evidence_v2_observe.sql | Agent-written observation publication against the reviewed user model |
| vpnlens/config.py, setup.py, refresh.py, service.py, lookup_ip.py | Feature flag, explicit setup, extra refresh group and read integration |
| api/models.py, api/main.py | Additive response schema and extended health expectations |
| frontend/src/types.ts, api.ts, presentation.ts | Validate/explain additive fields and optional old responses |
| frontend/src/components/ExtendedEvidence.tsx | Minimal evidence explanation using existing visual system |
| frontend/src/components/ResultView.tsx, SourcesView.tsx | Render extension and accurate source/record labels |
| tests/test_evidence_collectors.py, test_exit_recorder.py | Pure producer behavior with injected transports/clocks |
| tests/test_evidence_v2_store.py, test_evidence_v2_policy.py | Disposable DB publication/rollback and classification |
| tests/test_backend_api.py, test_refresh_workflow.py | Existing API/refresh compatibility and failure isolation |
| frontend/tests/evidence.test.tsx, api.test.ts | Additive/legacy parsing and status rendering |
| requirements.txt, requirements.lock, .env.example, .github/workflows/tests.yml | Pin DNS dependency and check the new owned files |
| docs/public-evidence.md, docs/exit-recorder.md, docs/evidence-v2-verification.md, README.md | Setup, provenance, operator workflow and actual results |

## Gates and acceptance

- [x] Confirm the active repository/branch, absent CodeGraph index, and existing dirty files before execution. Do not touch the older chat worktree's codex-session file.
- [x] Pass pure producer tests before database wiring. Tests use fixtures, not live provider calls.
- [x] Complete additive SQL implementation and independent schema/core-query reviews under the user's later full delegation. Live migration followed disposable proof and those reviews.
- [x] With the feature flag off, preserve existing payloads and eleven-source behavior.
- [x] With it on, retain legacy success when extended publication fails; failed checks never renew freshness.
- [x] Preserve reviewed-browser imports as operator-attested; baseline age, two active receipts, changed IP and review are mandatory.
- [x] Keep residential_proxy_status unknown. The recorder does not manufacture connection-type evidence.
- [x] Run the existing test runner, new owned-file lint, frontend format/tests/build, and bounded browser checks after integration.
- [x] Record real source observations separately from fixtures and external vendor classifications. Do not claim most-provider coverage or remote CI success without measurement.
- [x] Complete final diff/risk checks and perform the explicitly authorized normal feature-branch commit/push after acceptance. No force push or main-branch merge.

## Repository self-review

Each design requirement maps to one of the three plans: source onboarding/parsing/archive -> collectors; transport/baseline/import/approval/expiry -> recorder; user SQL, atomic groups, flag, disabled sources, API/UI/health, migration/rollback and live proof -> integration. Names and artifact fields are shared explicitly below; no physical table layout is assumed before the user's SQL review.

## Planning validation completed

Self-review checked the approved design section by section, shared field/function names, user ownership, disabled-source and rollback behavior, and the separation of public source check age from actual recorder observation age. Corrected explicit-proxy environment handling, browser-import validation/archiving, source-label fallback, CLI feature-flag composition and future/expired observation guards.

Planning checks: 17 Python code fences parsed, 2 JSON examples parsed, 4 TypeScript/TSX fences passed the installed compiler's syntax-only --noCheck/--noEmit check, and all 12 inter-document links resolved. This is example-syntax/document validation, not type checking, runtime tests, live source collection, migration proof or implemented feature evidence. Production tests/build/live checks remain execution gates above. No packages were installed and no product/database behavior changed during planning.

Publication checkpoint 2026-11-03: reviewed implementation commit `06539f7` was pushed to `origin/codex/vpn-evidence-expansion`. Local checks passed (198 backend tests, 81 frontend tests, owned lint, format and build); running-server and bounded browser proof is in the verification document. GitHub Actions was in progress when this note was written; no remote pass is claimed here.
