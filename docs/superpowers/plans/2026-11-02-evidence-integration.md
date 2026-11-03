# Evidence Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish reviewed public/exit artifacts and expose evidence-backed results without breaking legacy lookup or misclassifying residential use.

**Architecture:** Execute the user's reviewed SQL through a small JSON-envelope adapter, evaluate the approved evidence policy in Python, and add optional response/UI fields behind an off-by-default flag. Legacy tables and publication remain intact; the extended source group is separately atomic and recorder observations do not change feed counts.

**Tech Stack:** PostgreSQL 18/psycopg, Python 3.12/unittest, FastAPI/Pydantic, React/TypeScript/Vitest/Vite.

---

Root: /Users/nishankbansal/Documents/VPNLens. Prerequisites: artifact contracts from [collectors](2026-11-02-public-evidence-collectors.md) and [recorder](2026-11-02-exit-recorder.md). Follow [ownership and execution order](2026-11-02-vpn-evidence-expansion.md).

## Task 1: User-owned SQL checkpoint

Execution update 2026-11-03: the user explicitly delegated schema/core SQL implementation to the agent. The historical user-attempt steps below are superseded for this run. Additive SQL/store/setup is implemented and passed independent specification and quality reviews with 182 disposable tests. Three nonblocking status/test-precision followups are assigned to the runtime integration task and will receive its fresh reviews. No live migration or publication has occurred in worker execution.

**User attempts/reviews first:** sql/evidence_v2_schema.sql and sql/evidence_v2_lookup.sql.
**Agent implements routine SQL after that contract is reviewed:** sql/evidence_v2_validate.sql, evidence_v2_publish.sql, evidence_v2_sources.sql, evidence_v2_observe.sql. These implement the approved constraints/publication policy; they do not introduce new modeling or failure decisions.
**Agent prepares/reviews:** tests/test_evidence_v2_store.py using tests/backend_support.py's DatabaseCase pattern.

- [ ] Present the three logical entities from the approved design: extended snapshot, per-record network indicator and immutable exit observation plus separate review state. Ask the user to attempt physical tables/types/keys, active registry representation and the containment query. Do not supply a replacement SQL solution first.
- [ ] Review their attempt against concrete invariants: distinct providers/hostnames cannot collapse; HTTP source/hash is unique; one active version per enabled source; registry configuration publishes atomically; DNS withdrawal can have zero rows; /0/private data cannot become collection positives; duplicate observation UUID is idempotent only for identical content; approval cannot change observation time/expiry.
- [ ] Agree these adapter contracts. Each parameterized SQL file is **one statement**, accepts a single `%(payload)s::jsonb` envelope, and returns one column named result holding a JSON object. The migration is plain parameter-free DDL executed inside an outer transaction. This avoids the existing psycopg multiple-prepared-statements pitfall while leaving physical schema/SQL decisions with the user.

| SQL file | Input payload | Required result |
| --- | --- | --- |
| evidence_v2_validate.sql | empty object | schema_version=1, compatible=true only when required constraints/indexes/contracts exist |
| evidence_v2_publish.sql | complete candidate batch from prepare_batch, including registry and all enabled source snapshots | status loaded/unchanged, registry_sha256, sources array with public status projections |
| evidence_v2_lookup.sql | ip_address host string | matches array of active enabled-source containment records and approved observations; retain stale matches, never private baseline/receipt bodies |
| evidence_v2_sources.sql | empty object | sources array and enabled_source_ids array for scheduled public sources only |
| evidence_v2_observe.sql | validated measurement, separate matching approval, derived observed_at/expires_at, method/category/provider | status published/unchanged, observation_id, expires_at; conflicting identity or stale/invalid approval raises failure |

- [ ] Agree the lookup projection keys explicitly: source_id, family, record_key, network, provider, basis, role, method, service_category, source_url, content_sha256, fetched_at, checked_at, observed_at, expires_at, review_state, hostname and public metadata. Public snapshots expose expiry derived from their check-age policy; observations expose the original measurement-derived expiry. Use public opaque artifact IDs/hashes, not local paths, baseline IPs, raw proxy credentials, operator OS usernames or receipt bodies.
- [ ] Write disposable DB acceptance cases before binding runtime code: publish two overlapping sources/providers; reuse unchanged HTTP hash without resetting first fetched time; successful DNS withdrawal; failing final source rolls back registry and active pointers; disabled source disappears from lookup/counts; exact CIDR edges; pending versus approved observation; conflicting UUID and expired approval; legacy row counts/content unchanged.
- [ ] Let the user review the DDL/core query and fixture expectations. Stop database integration here until that review passes. Pure collector/recorder tasks can proceed independently. The absent SQL solution is an intentional ownership checkpoint, not a stub to fill with guessed tables.

## Task 2: Thin transactional SQL adapter and explicit setup

**Create:** vpnlens/evidence_store.py. **Modify:** vpnlens/setup.py; tests/test_evidence_v2_store.py.

- [x] Implement the complete SQL adapter only after Task 1. It executes contracts; it does not invent schema logic.

```python
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from vpnlens.config import ROOT

CONTRACTS = {
    'validate':'evidence_v2_validate.sql', 'publish':'evidence_v2_publish.sql',
    'lookup':'evidence_v2_lookup.sql', 'sources':'evidence_v2_sources.sql',
    'observe':'evidence_v2_observe.sql',
}


class EvidenceStore:
    def __init__(self, connection):
        self.connection = connection

    def run(self, operation, payload):
        filename = CONTRACTS[operation]
        statement = (ROOT/'sql'/filename).read_text(encoding='utf-8')
        row = self.connection.execute(statement, {'payload':Jsonb(payload)}).fetchone()
        if row is None or not isinstance(row['result'], dict):
            raise ValueError('Evidence SQL contract returned an invalid result')
        return row['result']


def publish_contract(database_url, operation, payload):
    if operation not in {'publish','observe'}:
        raise ValueError('Unsupported publication operation')
    with psycopg.connect(database_url, connect_timeout=5, row_factory=dict_row) as connection:
        connection.execute("SET LOCAL lock_timeout = '5s'")
        locked = connection.execute('SELECT pg_try_advisory_xact_lock(872410052) AS locked').fetchone()
        if not locked['locked']:
            raise RuntimeError('Another evidence publication is running')
        store = EvidenceStore(connection)
        validation = store.run('validate', {})
        if validation.get('schema_version') != 1 or validation.get('compatible') is not True:
            raise ValueError('Extended evidence schema is incompatible')
        return store.run(operation, payload)


def initialize_extended(database_url):
    with psycopg.connect(database_url, connect_timeout=5, row_factory=dict_row) as connection:
        connection.execute("SET LOCAL lock_timeout = '5s'")
        locked = connection.execute('SELECT pg_try_advisory_xact_lock(872410052) AS locked').fetchone()
        if not locked['locked']:
            raise RuntimeError('Another evidence publication is running')
        connection.execute((ROOT/'sql/evidence_v2_schema.sql').read_text(encoding='utf-8'))
        result = EvidenceStore(connection).run('validate', {})
        if result.get('schema_version') != 1 or result.get('compatible') is not True:
            raise ValueError('Extended evidence schema is incompatible')
        return result
```

The lock number matches the existing evidence publisher. Do not acquire the full-refresh session lock again inside this second connection; the full-refresh owner already holds it. Setup and standalone writers coordinate through the evidence transaction lock.

- [x] Extend the existing setup parser with an explicit `--extended-evidence` action; call initialize_extended only for that action after ordinary base compatibility checks. A normal setup/lookup/startup does not silently migrate.
- [x] Run `.venv/bin/python scripts/run_tests.py`; expect the legacy suite plus new migration/publication cases to pass in a dedicated DB. Inject a failure after inserting a snapshot and verify no registry/indicator activation survives.
- [x] Verify same-schema setup twice, incompatible existing shape, lock contention and feature-off reads of an older installation. Record EXPLAIN containment index evidence on fixture data; do not assert timing from one run as a service guarantee.

## Task 3: Pure classification and compatibility projection

**Create:** vpnlens/evidence_policy.py; tests/test_evidence_v2_policy.py.

- [x] Add failing tests for legacy-only compatibility, weak network-only evidence, fresh provider DNS/list matches, stale records, pending/approved observations, expired approved observations and proxy-only observations. Use a fixed UTC time and separate fixtures for upstream feed matches versus measured receipts.
- [x] Implement this pure policy. Physical match selection belongs to the reviewed SQL, while method/eligibility semantics remain explicit here.

```python
from copy import deepcopy
from datetime import timedelta
from vpnlens.evidence_contract import instant

PUBLIC_KEYS = ('source_id','family','record_key','network','provider','basis','role','method',
               'service_category','source_url','content_sha256','fetched_at','checked_at',
               'observed_at','expires_at','review_state','hostname','connection_type_claim')


def public_record(record, now):
    item = {key:record.get(key) for key in PUBLIC_KEYS}
    if record['basis'] == 'exit_observation':
        observed = instant(record['observed_at'])
        expiry = observed + timedelta(hours=24)
        if instant(record['expires_at']) != expiry:
            raise ValueError('Observation expiry disagrees with measurement')
        item['stale'] = observed > now or now >= expiry
        item['operator_attested'] = True
    else:
        checked = instant(record['checked_at'])
        item['stale'] = checked > now or now - checked > timedelta(hours=48)
    return item


def apply_policy(legacy, matches, source_counts, now):
    result = deepcopy(legacy)
    strong, additional, network_only, proxy = [], [], False, False
    for record in matches:
        if record['basis'] == 'exit_observation' and record.get('review_state') != 'approved':
            continue
        item = public_record(record, now)
        observation = record['basis'] == 'exit_observation'
        approved = not observation or record.get('review_state') == 'approved'
        eligible = not item['stale'] and approved
        direct = record['basis'] in {'provider_list','provider_dns','exit_observation'}
        vpn = record.get('service_category') == 'vpn'
        if direct and vpn and approved:
            strong.append({**item, 'indicator_type':'vpn_server'})
        else:
            additional.append(item)
        if eligible and record['basis'] == 'network_inference':
            network_only = True
        if eligible and observation and record.get('service_category') == 'proxy':
            proxy = True
    result['evidence'].extend(strong)
    fresh_vpn = any(not item['stale'] for item in strong)
    if fresh_vpn:
        result['vpn_status'] = 'listed'
    result['vpn_assessment'] = ('direct_association' if result['vpn_status'] == 'listed'
                                else 'network_only' if network_only else 'unknown')
    result['proxy_status'] = 'listed' if proxy else 'unknown'
    result['residential_proxy_status'] = 'unknown'
    result['residential_proxy_reason'] = 'No qualifying residential-relay evidence has been collected'
    result['additional_evidence'] = additional
    result['active_source_count'] += source_counts['active']
    result['recently_checked_source_count'] += source_counts['recent']
    return result
```

- [x] Normalize/validate SQL results before policy input: only declared basis/category/role values; public source URLs and hashes; no future observed times; per-source active/enabled membership from the committed registry. Observation checked_at/fetched_at in the legacy projection must equal original observed_at, never approval/import time. Do not expose rejected or pending observations as public positive evidence.
- [x] Test the boundary policies exactly: legacy/public feed age <=48 hours is fresh; exit measurement age >=24 hours is stale. No missing clock/expiry may turn into a positive. Multiple correlated sources remain separate records, without an invented independent-confirmation count or score.
- [x] Run pure policy tests and scoped Ruff. Add a test proving country mismatch/hosting data cannot affect the result because those values are not classification inputs.

## Task 4: Feature flag and read-only API integration

**Modify:** vpnlens/config.py, service.py; lookup_ip.py; api/models.py, main.py; .env.example; tests/test_backend_api.py; tests/test_evidence_v2_store.py.

- [x] Add strict boolean parsing and Settings.extended_evidence=False. Set `.env.example` to `VPNLENS_EXTENDED_EVIDENCE=false`; read true/1 or false/0 case-insensitively, reject other values without echoing them. Use this parser:

```python

def evidence_enabled(value):
    normalized = value.strip().lower()
    if normalized in {'true','1'}:
        return True
    if normalized in {'false','0'}:
        return False
    raise ValueError('VPNLENS_EXTENDED_EVIDENCE requires true/false or 1/0')
```

- [x] Add an optional `extended_enabled=False` keyword to service.lookup/source_status. Pass it explicitly from create_app's Settings for HTTP calls. Direct service callers keep their old default. Factor extended read/policy composition into enrich_security(connection, ip, legacy) and call it from both service.lookup and lookup_ip.py when their Settings flag is enabled. Keep the explicit-snapshot CLI argument/row shape and existing core LOOKUP_SQL/owner/longest-prefix statement untouched.
- [x] Add this shared service helper. Use it after the existing legacy lookup in both service.lookup and lookup_ip.py when their Settings flag is enabled. Its counts come from the committed registry/source query, not the number of observation rows. Attach the resulting object once per IP to all origin-group rows.

```python
from vpnlens.evidence_policy import apply_policy
from vpnlens.evidence_store import EvidenceStore


def enrich_security(connection, ip, legacy):
    now = connection.execute('SELECT CURRENT_TIMESTAMP AS now').fetchone()['now']
    store = EvidenceStore(connection)
    sources = store.run('sources', {})
    expected = set(sources['enabled_source_ids'])
    active = {row['source_id'] for row in sources['sources'] if row['source_id'] in expected}
    recent = {row['source_id'] for row in sources['sources']
              if row['source_id'] in expected and row['stale'] is False}
    matches = store.run('lookup', {'ip_address':ip})['matches']
    return apply_policy(legacy, matches, {'active':len(active), 'recent':len(recent)}, now)
```

The source query's stale calculation uses the same transaction clock. The legacy explicit-snapshot CLI currently uses a dictionary row factory through read_connection, so this helper does not require changing the base IP statement.
- [x] Preserve SourceResponse.security's old required fields and add optional basis/record_kind to extended rows. The source SQL must return canonical public record counts, not the cardinality of expanded CIDRs, and exclude disabled sources. /health/ready uses committed enabled-source IDs alongside legacy FEEDS; absent/stale manual recorder profiles never degrade health.
- [x] Add the following fields at the end of the existing Pydantic Security class; retain all legacy fields exactly:

```python
    vpn_assessment: Literal['direct_association', 'network_only', 'unknown'] | None = None
    proxy_status: Literal['listed', 'unknown'] | None = None
    residential_proxy_status: Literal['unknown'] | None = None
    residential_proxy_reason: str | None = None
    additional_evidence: list[dict[str, Any]] | None = None
```

- [x] Add optional/defaulted Security fields to Pydantic and set `response_model_exclude_unset=True` on the lookup endpoint. This permits old dictionaries to omit all new fields while preserving explicitly supplied null location/owner values. Test full flag-off response equality, not just HTTP 200.
- [x] Test no socket/network call is made during lookup, missing extended schema gives a safe 503 when enabled, feature-off legacy installs work, read-only SQL stays read-only, and tied origins receive identical evidence. No write/recorder HTTP endpoint is added.

## Task 5: Separate atomic refresh group and observation publication

**Modify:** vpnlens/refresh.py; vpnlens/observe.py; tests/test_refresh_workflow.py; tests/test_evidence_v2_store.py; docs/public-evidence.md, exit-recorder.md.

- [x] Add `extended_enabled=False` to refresh_datasets. Build an effective dataset order from the existing DATASETS tuple: when evidence was requested and the flag is on, insert evidence_extended immediately after legacy evidence. Do not change the default DATASETS constant or behavior when the flag is off. Pass Settings.extended_evidence from the CLI.
- [x] In the new evidence_extended branch, call prepare_batch, read/validate the completed candidate envelope and raw hashes again, then publish_contract(database_url, 'publish', batch). Reuse the existing state-save/exception handling under the separate evidence_extended key. Legacy evidence has already saved success before this branch starts; an extended failure must not overwrite its state or revert its commit.
- [x] Validate every raw_ref stays beneath the candidate's expected archive root, has the declared hash and bounded size, and source entries match the manifest registry hash. Reject changed files, path traversal, missing enabled sources, repeated source IDs, unexpected disabled-source payloads or a tampered candidate. Re-normalize each archived HTTP payload with its declared parser, or the dated DNS answer bundle offline, and compare canonical records to the candidate before publication; a matching raw hash alone does not validate an edited indicator array. Never execute CSV configuration content.
- [x] When Settings.extended_evidence is on, bind observe approve to publish_contract(database_url, 'observe', payload) only after validating the original measurement, derived expiry, original profile binding, approval digest and immutable local review. The user-reviewed SQL performs idempotent insert/review. A DB failure preserves the existing public snapshots and the local receipt/review for an explicit retry; it does not create an eligible positive or renew expiry. With the flag off, approval remains a local artifact action and does not access new database tables.
- [x] Test extended-last-source parse/DB failure, unchanged HTTP content, new dated DNS bundles, complete DNS withdrawal, disabled registry publication, a publication lock conflict, missing feature schema, and legacy-success/extended-failure state separation.
- [x] Test standalone collector/recorder publication cannot overlap the legacy evidence transaction lock; no nested acquisition of the full-refresh session lock. The existing daily LaunchAgent remains unchanged and no second scheduler is installed.

## Task 6: Minimal current-interface explanation

**Create:** frontend/src/components/ExtendedEvidence.tsx; frontend/tests/evidence.test.tsx.
**Modify:** frontend/src/types.ts, api.ts, presentation.ts; components/ResultView.tsx, SourcesView.tsx; frontend/tests/api.test.ts.

- [x] Add this TypeScript interface in types.ts; source metadata is public and nullable only where the contract says unknown:

```ts
export interface AdditionalEvidence {
  source_id: string;
  family: string;
  record_key: string;
  network: string;
  provider: string | null;
  basis: 'provider_list' | 'provider_dns' | 'network_inference' | 'exit_observation';
  role: 'server' | 'exit' | 'unknown';
  method: string;
  service_category: 'vpn' | 'proxy';
  source_url: string;
  checked_at: string;
  fetched_at: string;
  observed_at: string | null;
  expires_at: string | null;
  review_state: 'approved' | null;
  hostname: string | null;
  connection_type_claim?: 'residential' | 'mobile' | 'datacenter' | 'unknown' | null;
  operator_attested?: boolean;
  stale: boolean;
}
```

Extend Security with vpn_assessment?, proxy_status?, residential_proxy_status?: 'unknown', residential_proxy_reason?: string and additional_evidence?: AdditionalEvidence[]. Extend legacy Evidence with optional record_key, method, role, observed_at, expires_at and connection_type_claim fields. The question marks are backward-compatible optional fields, not unfinished values.

- [x] Add optional enriched fields to Security and a typed AdditionalEvidence matching the public SQL projection. Evidence method/role/expiry are optional additions to the legacy Evidence type; do not expand its two indicator_type literals. Keep legacy fixtures valid.
- [x] Add these optional Security members in types.ts, retaining all old members:

```ts
  vpn_assessment?: 'direct_association' | 'network_only' | 'unknown';
  proxy_status?: 'listed' | 'unknown';
  residential_proxy_status?: 'unknown';
  residential_proxy_reason?: string;
  additional_evidence?: AdditionalEvidence[];
```

Add the runtime guard below in api.ts, then include `validExtendedSecurity(row.security)` as another conjunct of the existing row validation. No extension keys means an old response; if any extension key is present, require the full declared extension.

```ts
export function validExtendedSecurity(value: Record<string, any>): boolean {
  const keys = ['vpn_assessment', 'proxy_status', 'residential_proxy_status',
    'residential_proxy_reason', 'additional_evidence'];
  if (!keys.some((key) => key in value)) return true;
  const text = (v: unknown) => typeof v === 'string';
  const nullableText = (v: unknown) => v === null || text(v);
  return ['direct_association','network_only','unknown'].includes(value.vpn_assessment)
    && ['listed','unknown'].includes(value.proxy_status)
    && value.residential_proxy_status === 'unknown'
    && text(value.residential_proxy_reason)
    && Array.isArray(value.additional_evidence)
    && value.additional_evidence.every((item: any) => item &&
      ['source_id','family','record_key','network','method','source_url','checked_at','fetched_at']
        .every((key) => text(item[key])) &&
      ['provider','hostname','observed_at','expires_at'].every((key) => nullableText(item[key])) &&
      ['provider_list','provider_dns','network_inference','exit_observation'].includes(item.basis) &&
      ['server','exit','unknown'].includes(item.role) &&
      ['vpn','proxy'].includes(item.service_category) &&
      (item.review_state === null || item.review_state === 'approved') &&
      typeof item.stale === 'boolean' &&
      (item.operator_attested === undefined || typeof item.operator_attested === 'boolean') &&
      (item.connection_type_claim === undefined || item.connection_type_claim === null ||
        ['residential','mobile','datacenter','unknown'].includes(item.connection_type_claim)) &&
      (item.basis !== 'exit_observation' ||
        (text(item.observed_at) && text(item.expires_at) && item.review_state === 'approved')));
}
```

- [x] Extend isLookupResponse to validate new fields when present: the three vpn_assessment literals, proxy listed/unknown, residential unknown, additional_evidence array, declared basis/category values, source_id/source_url strings, stale boolean and the original observation timestamps for exit records. Old responses with absent extension fields remain valid.
- [x] Add this complete presentation component using existing panel/section classes. Use the typed item fields, never raw receipt/HTML content.

```tsx
import type { Security } from '../types';

export function ExtendedEvidence({ security }: { security: Security }) {
  if (security.vpn_assessment === undefined) return null;
  const records = security.additional_evidence ?? [];
  return (
    <section className="panel" aria-labelledby="extended-evidence-title">
      <div className="section-heading">
        <h2 id="extended-evidence-title">Additional evidence</h2>
      </div>
      {security.vpn_assessment === 'network_only' && (
        <p>Possible VPN-network association. No direct VPN endpoint evidence.</p>
      )}
      <p>Proxy exit association: {security.proxy_status === 'listed' ? 'Listed' : 'Unknown'}</p>
      <p>Residential proxy: Unknown. Qualifying evidence is not available.</p>
      {records.length > 0 && (
        <ul>
          {records.map((item) => (
            <li key={`${item.source_id}-${item.record_key}`}>
              <strong>{item.provider ?? item.source_id}</strong>{' '}
              <code>{item.network}</code>{' '}
              {item.basis === 'network_inference' ? 'Network inference' : 'Dated service observation'}
              {item.stale ? ' · Stale' : ''}
              {item.operator_attested ? ' · Operator-attested' : ''}
              {item.connection_type_claim && item.connection_type_claim !== 'unknown'
                ? ` · Reported pool: ${item.connection_type_claim} (unverified)` : ''}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
```

- [x] Import/render ExtendedEvidence in ResultView after the existing supporting evidence section. In that existing section, use `source_id + record_key` when available for keys so two reviewed hostnames from one source do not collide. Show method/role and original observed/expiry dates for the new strong records; do not relabel an imported browser claim as recorder-verified.
- [x] In summarize, retain existing VPN/Tor finding precedence, then show proxy association if fresh proxy_status is listed, then network-only evidence if vpn_assessment is network_only, then the existing unknown wording. SourcesView uses feed.provider ?? feed.source_id for source labels, so an unnamed X4B feed cannot appear as Tor Project; it labels network_inference as 'VPN networks' rather than 'VPN servers'; its record count remains rows/networks, not unique address coverage. Raw JSON/copy stays exact to the returned object.
- [x] Add actual rendering/keyboard-visible assertions for network-only wording, unknown residential status, proxy-only evidence, stale/operator-attested labels and absence of the extension with an old response. Run frontend tests, format check and production build. Do not redesign navigation, typography, layout or motion.

## Task 7: Integrated gates, rollback and live proof

**Modify:** .github/workflows/tests.yml; README.md; docs/evidence-v2-verification.md; docs/public-evidence.md; docs/exit-recorder.md.

- [x] Include all new owned Python modules/tests in the existing Ruff scope. Do not expand cleanup to the known pre-existing full-repository import issues. Preserve the dedicated PostgreSQL CI service and frontend checks.
- [x] Run these commands, with expected success for every check:

```bash
.venv/bin/python scripts/run_tests.py
.venv/bin/python -m ruff check --no-cache api vpnlens scripts tests/test_evidence_collectors.py tests/test_exit_recorder.py tests/test_evidence_v2_store.py tests/test_evidence_v2_policy.py tests/test_backend_api.py tests/test_refresh_workflow.py
npm --prefix frontend test
npm --prefix frontend run format:check
npm --prefix frontend run build
git diff --check
```

- [x] In a disposable existing installation, migrate and publish the controlled public/approved-observation fixtures, read both flag states and disable/re-enable extended reads. Assert legacy table contents and independent source selections are unchanged, old clients parse the old shape and no history is deleted.
- [x] Ensure the existing dependencies are installed from requirements.lock and frontend/package-lock.json before verification; use `npm --prefix frontend ci` if the frontend install is absent/incomplete. After user review of the migration/core query, perform non-destructive setup and source collection on the local installation. Enable extended reads only after successful publication/validation. Restart only the verified project-owned API process if required; do not kill a guessed PID from older notes.
- [x] Fetch the approved live sources and resolve reviewed hostnames; record actual counts/hashes/dates. For 103.108.230.50, report the current dated UrbanVPN association only if still supported. If it changed upstream, preserve that result rather than hardcoding it. Verify at least two other provider examples and 8.8.8.8's non-positive hosting case.
- [x] The operator deliberately activates an accessible VPN/proxy before any live recorder check. Record the actual baseline/path/provider attestation, two receipts, pending/review state and original expiry. Do not claim a fixture or browser import proves a real system tunnel, residential exit or broad detector coverage.
- [x] Check the real app with one direct association, one weak-only result, stale/unknown, tied origins and source-health failure at desktop/phone sizes. Include raw JSON/copy and normal keyboard search; preserve the existing visual layout.
- [x] Document changed files, exact tests/results, fixture versus live evidence, rollback command/configuration and remaining gaps. No public deployment, paid API, automatic network change, accuracy percentage or 'most VPNs' claim.
- [ ] Present the final diff for user review. Commit only when requested, using exact reviewed paths; never stage data/profiles/receipts/secrets or run git add -A. Never push without explicit approval.

## Self-review map

Source schemas/normalization/provenance and collector limits are in the collectors plan; baseline/proxy/browser/review/expiry semantics are in the recorder plan. This plan covers the user SQL checkpoint, atomic groups/locks, active registry, feature-off compatibility, no-network/read-only lookup, typed policy, source counts/health, minimal UI, migration/rollback and distinct live verification. Physical SQL stays user-owned; no agent should bypass that gate by substituting guessed table names or a complete SQL answer.

Runtime execution checkpoint 2026-11-03: Tasks 3-5 passed independent specification and quality reviews. Final independent disposable PostgreSQL result: 198 tests passed in 8.174 seconds; owned Ruff and diff checks passed. Separate pure tests passed with network/DB/dotenv blocked. The three SQL quality followups were corrected. Candidate activation is delegated to the coordinating agent after bounded offline revalidation; workers have not touched the live database. Minimal UI and concise README diagrams are in progress.

Final execution checkpoint 2026-11-03: minimal UI and concise 174-line/three-diagram README passed independent specification and quality reviews. Final cross-group review approved with no findings. Final gates passed: 198 disposable backend tests, 81 frontend tests, scoped Ruff, format, build and diff check. The coordinating agent verified actual HTTP and desktop/phone UI against the enabled local server; detailed coverage and the live clipboard limitation are recorded in docs/evidence-v2-verification.md. No real recorder run was performed. Final authorized staging/commit/push remains with the coordinating agent.
