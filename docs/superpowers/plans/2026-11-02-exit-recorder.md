# Exit Recorder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Capture, import and review dated exit observations without changing network settings or inventing residential evidence.

**Architecture:** A local CLI writes immutable private baseline/measurement artifacts and separate approval artifacts. Explicit system-tunnel or HTTP-proxy requests use one public IPv4 echo receiver; browser imports remain operator-attested. Database publication is a later integration step.

**Tech Stack:** Python 3.12, HTTPX, unittest, shared artifact helpers from the collectors plan.

---

Root: /Users/nishankbansal/Documents/VPNLens. Prerequisite: Task 1 of [collectors](2026-11-02-public-evidence-collectors.md). Follow the approved [design](../specs/2026-11-02-vpn-evidence-expansion-design.md) and [ownership](2026-11-02-vpn-evidence-expansion.md).

## Task 1: Profile and receipt contract

**Create:** vpnlens/observation_contract.py; tests/test_exit_recorder.py.

- [x] Add failing tests for a valid provider profile, rejected credential-bearing documentation URL, unknown route mode and receipt/body disagreement. Run `.venv/bin/python -m unittest discover -s tests -p 'test_exit_recorder.py' -v`; expect missing-module/function failure before implementation.
- [x] Implement this contract. Profile identity is operator-reviewed metadata; it is not independently proved by the echo receiver.

```python
import json
import re
from datetime import timedelta
from ipaddress import IPv4Address
from urllib.parse import urlsplit
from uuid import UUID
from vpnlens.evidence_contract import canonical, digest, instant, public_network

ECHO = 'https://api.ipify.org?format=json'
TRANSPORTS = {'system_tunnel', 'explicit_http_proxy', 'browser_import'}


def profile_contract(profile):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,99}', profile.get('profile_id', '')):
        raise ValueError('Invalid profile ID')
    if profile.get('service_category') not in {'vpn', 'proxy'}:
        raise ValueError('Unsupported service category')
    if profile.get('transport') not in TRANSPORTS:
        raise ValueError('Unsupported transport')
    if not isinstance(profile.get('provider'), str) or not profile['provider'].strip():
        raise ValueError('Provider label is required')
    url = urlsplit(profile.get('documentation_url', ''))
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query:
        raise ValueError('Documentation reference must be credential-free HTTPS')
    reference = profile.get('proxy_env')
    if profile['transport'] == 'explicit_http_proxy':
        if not isinstance(reference, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]+', reference):
            raise ValueError('A proxy environment reference is required')
    elif reference is not None:
        raise ValueError('Unexpected proxy secret reference')
    claim = profile.get('connection_type_claim', 'unknown')
    if claim not in {'residential','mobile','datacenter','unknown'}:
        raise ValueError('Invalid reported connection type')
    fields = ('profile_id','provider','service_category','transport','documentation_url')
    return {**{name:profile[name] for name in fields}, 'proxy_env':reference,
            'connection_type_claim':claim}


def receipt_contract(receipt, now):
    if str(UUID(receipt['receipt_id'])) != receipt['receipt_id']:
        raise ValueError('Invalid receipt identity')
    address = str(IPv4Address(receipt['ip']))
    public_network(address)
    if receipt['endpoint'] != ECHO:
        raise ValueError('Unreviewed echo receiver')
    body = receipt['response_body'].encode('utf-8')
    if len(body) > 4096 or digest(body) != receipt['response_sha256']:
        raise ValueError('Invalid receiver receipt')
    if str(IPv4Address(json.loads(body)['ip'])) != address:
        raise ValueError('Receipt IP disagrees with receiver body')
    started, observed = instant(receipt['started_at']), instant(receipt['observed_at'])
    if not started <= observed <= now:
        raise ValueError('Receipt times are invalid')
    return observed


def validate_observation(record, profile, now):
    profile = profile_contract(profile)
    if record['schema_version'] != 1 or record['kind'] != 'exit_observation':
        raise ValueError('Unsupported observation contract')
    if str(UUID(record['observation_id'])) != record['observation_id']:
        raise ValueError('Invalid observation identity')
    if record['profile_sha256'] != digest(canonical(profile)):
        raise ValueError('Profile binding changed')
    if record['profile_id'] != profile['profile_id'] or record['method'] != profile['transport']:
        raise ValueError('Observation/profile method mismatch')
    if record.get('review_state') != 'pending' or record.get('operator_attested_active') is not True:
        raise ValueError('Observation must be pending with explicit active-state attestation')
    baseline = record['baseline']
    if baseline['profile_sha256'] != record['profile_sha256'] or baseline.get('operator_attested_disconnected') is not True:
        raise ValueError('Invalid baseline attestation/binding')
    before = receipt_contract(baseline['receipt'], now)
    active = record['active_receipts']
    if len(active) != 2 or active[0]['receipt_id'] == active[1]['receipt_id']:
        raise ValueError('Two distinct active receipts are required')
    first, last = (receipt_contract(item, now) for item in active)
    if not before <= first <= last or last - before > timedelta(minutes=15):
        raise ValueError('Baseline must precede active receipts within 15 minutes')
    if active[0]['ip'] != active[1]['ip'] or active[0]['ip'] == baseline['receipt']['ip']:
        raise ValueError('Active IP is unstable or unchanged; transport remains unverified')
    expires = last + timedelta(hours=24)
    if now >= expires:
        raise ValueError('Observation has expired')
    return {'ip':active[-1]['ip'], 'observed_at':last.isoformat(), 'expires_at':expires.isoformat(),
            'provider':profile['provider'], 'service_category':profile['service_category'],
            'method':record['method'], 'operator_attested':True,
            'connection_type_claim':profile['connection_type_claim']}
```

- [x] Baseline age is evaluated at the original last active measurement, not at import time. Eligibility still expires 24 hours after that measurement; import/check/approval never resets it. Tests cover exactly 15 minutes allowed, later rejected, exactly 24 hours expired, naive/future/out-of-order timestamps and identical receipt IDs.
- [x] Add a fixture helper in tests/test_exit_recorder.py that creates valid receipts and a pending record, then assert that changing the method to browser_import still requires all the same checks. Use this complete helper and test as the starting point:

```python
import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from vpnlens.evidence_contract import canonical, digest
from vpnlens.observation_contract import ECHO, profile_contract, validate_observation

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def observation_fixture(mode='system_tunnel'):
    profile = profile_contract({'profile_id':'sample', 'provider':'Fixture VPN',
        'service_category':'vpn', 'transport':mode, 'documentation_url':'https://example.com/'})
    def receipt(ip, at):
        body = canonical({'ip':ip}).decode()
        return {'receipt_id':str(uuid4()), 'ip':ip, 'endpoint':ECHO,
                'started_at':at.isoformat(), 'observed_at':at.isoformat(),
                'response_body':body, 'response_sha256':digest(body.encode())}
    fingerprint = digest(canonical(profile))
    baseline = {'profile_sha256':fingerprint, 'operator_attested_disconnected':True,
                'receipt':receipt('1.1.1.1', NOW-timedelta(minutes=2))}
    record = {'schema_version':1, 'kind':'exit_observation', 'observation_id':str(uuid4()),
              'profile_id':'sample', 'profile_sha256':fingerprint, 'method':mode,
              'review_state':'pending', 'operator_attested_active':True, 'baseline':baseline,
              'active_receipts':[receipt('8.8.8.8', NOW-timedelta(seconds=2)),
                                 receipt('8.8.8.8', NOW-timedelta(seconds=1))]}
    return profile, record


class ObservationTests(unittest.TestCase):
    def test_browser_import_does_not_bypass_measurement_checks(self):
        profile, record = observation_fixture('browser_import')
        self.assertEqual(validate_observation(record, profile, NOW)['ip'], '8.8.8.8')
        record['active_receipts'][1] = record['active_receipts'][0]
        with self.assertRaises(ValueError):
            validate_observation(record, profile, NOW)
```

This fixture is validation proof only; it does not show the public fixture IPs are VPN exits.

## Task 2: Explicit transport without environment proxy bypass

**Create:** vpnlens/observation_transport.py. **Modify:** requirements.txt, requirements-dev.txt, requirements.lock; tests/test_exit_recorder.py.

- [x] Move HTTPX's existing supported requirement into runtime requirements; remove its duplicate dev-only declaration. Preserve the reviewed pinned version from requirements.lock; do not upgrade unrelated packages.
- [x] Add a failing fake-client test that sets HTTP_PROXY/NO_PROXY yet verifies `trust_env=False`, and a proxy failure test that verifies there is exactly one attempted configured route and no direct fallback.
- [x] Implement the full transport below. HTTPX is chosen over urllib's proxy-bypass discovery so that explicit-proxy mode cannot silently honor ambient NO_PROXY.

```python
import json
import os
from datetime import UTC, datetime
from ipaddress import IPv4Address
from urllib.parse import urlsplit
from uuid import uuid4
import httpx
from vpnlens.evidence_contract import digest, public_network, stamp
from vpnlens.observation_contract import ECHO, profile_contract


def fetch_receipt(profile, *, baseline=False, client_factory=httpx.Client, clock=None):
    profile = profile_contract(profile)
    clock = clock or (lambda: datetime.now(UTC))
    if profile['transport'] == 'browser_import':
        raise ValueError('Browser-only profiles require imported browser receipts')
    proxy = None
    if not baseline and profile['transport'] == 'explicit_http_proxy':
        proxy = os.environ.get(profile['proxy_env'])
        parts = urlsplit(proxy or '')
        if parts.scheme not in {'http','https'} or not parts.hostname:
            raise ValueError('Proxy secret reference is unset or invalid')
    started = stamp(clock())
    with client_factory(proxy=proxy, trust_env=False, follow_redirects=False,
                        timeout=10.0, verify=True) as client:
        with client.stream('GET', ECHO, headers={'Cache-Control':'no-cache'}) as response:
            if response.status_code != 200:
                raise ValueError('Echo receiver did not return HTTP 200')
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > 4096:
                    raise ValueError('Echo receiver response exceeds limit')
                chunks.append(chunk)
    payload = b''.join(chunks)
    address = str(IPv4Address(json.loads(payload)['ip']))
    public_network(address)
    return {'receipt_id':str(uuid4()), 'ip':address, 'endpoint':ECHO,
            'started_at':started, 'observed_at':stamp(clock()),
            'response_body':payload.decode('utf-8'), 'response_sha256':digest(payload)}
```

- [x] Test missing/invalid proxy secret, HTTP errors, oversized/truncated/non-JSON bodies, private/IPv6 answers and TLS/connect failures. Assert errors/receipts contain no proxy credential values and no Proxy-Authorization is added to the origin request. Keep the test endpoint fake; no actual VPN connection is started.
- [x] Run pure recorder tests and scoped Ruff. No browser storage or system network settings are accessed.

## Task 3: Immutable recorder artifacts and review

**Modify:** vpnlens/observation_contract.py; tests/test_exit_recorder.py.

- [x] Add tests for identical/conflicting observation imports and profile changes. Then add these functions, using the actual receipt transport as an injected argument.

```python
from pathlib import Path
from uuid import uuid4
from vpnlens.evidence_contract import write_once, stamp


def create_baseline(profile, probe):
    profile = profile_contract(profile)
    return {'schema_version':1, 'kind':'baseline', 'baseline_id':str(uuid4()),
            'profile_id':profile['profile_id'], 'profile_sha256':digest(canonical(profile)),
            'operator_attested_disconnected':True, 'receipt':probe(profile, baseline=True)}


def create_observation(profile, baseline, probe, now):
    profile = profile_contract(profile)
    current = now()
    before = receipt_contract(baseline['receipt'], current)
    if baseline.get('profile_sha256') != digest(canonical(profile)) or baseline.get('operator_attested_disconnected') is not True:
        raise ValueError('Baseline binding or attestation is invalid')
    if current - before > timedelta(minutes=15):
        raise ValueError('Baseline is too old to start capture')
    record = {'schema_version':1, 'kind':'exit_observation', 'observation_id':str(uuid4()),
              'profile_id':profile['profile_id'], 'profile_sha256':digest(canonical(profile)),
              'method':profile['transport'], 'review_state':'pending',
              'operator_attested_active':True, 'baseline':baseline,
              'active_receipts':[probe(profile), probe(profile)]}
    validate_observation(record, profile, now())
    return record


def save_observation(folder, record):
    path = Path(folder)/'pending'/(record['observation_id']+'.json')
    write_once(path, canonical(record))
    return path


def approve_artifact(folder, record, profile, operator, now):
    validate_observation(record, profile, now)
    if not isinstance(operator, str) or not operator.strip():
        raise ValueError('Local reviewer label is required')
    sha = digest(canonical(record))
    path = Path(folder)/'reviews'/(record['observation_id']+'.json')
    if path.exists():
        review = json.loads(path.read_text())
        if review.get('observation_sha256') != sha:
            raise ValueError('Conflicting review/observation identity')
        return path
    review = {'observation_id':record['observation_id'], 'observation_sha256':sha,
              'review_state':'approved', 'operator':operator, 'reviewed_at':stamp(now)}
    write_once(path, canonical(review))
    return path
```

- [x] A review does not mutate the measurement. The original pending state remains in the immutable artifact; separate DB review state controls eligibility after integration. No fake expiry is serialized from user input; use the validator's derived expiry.
- [x] Test stale approval refusal, unchanged-IP refusal, invalid browser imports and idempotent valid approvals. Expired observations remain historical; no approval/re-import renews them.

## Task 4: CLI and bounded imports

**Create:** vpnlens/observe.py. **Modify:** tests/test_exit_recorder.py.

- [x] Add CLI tests using subprocess with injected fixture entrypoints or call main with patched transports; do not let test commands contact ipify. Then implement this entry module:

```python
import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from dotenv import load_dotenv
from vpnlens.config import ROOT
from vpnlens.evidence_contract import canonical, digest, instant, stamp, write_once
from vpnlens.observation_contract import (
    approve_artifact, create_baseline, create_observation,
    profile_contract, save_observation, validate_observation,
)
from vpnlens.observation_transport import fetch_receipt


def read_json(path, limit=262144, archive_folder=None):
    with Path(path).open('rb') as source:
        payload = source.read(limit+1)
    if len(payload) > limit:
        raise ValueError('Local input exceeds size limit')
    if archive_folder is not None:
        write_once(Path(archive_folder)/(digest(payload)+'.bin'), payload)
    return json.loads(payload)


def main():
    parser = argparse.ArgumentParser(description='Record local dated exit evidence; never switch VPNs.')
    parser.add_argument('action', choices=['baseline','capture','import','approve'])
    parser.add_argument('--profile', required=True)
    parser.add_argument('--profiles', default=str(ROOT/'data/observations/profiles.json'))
    parser.add_argument('--out', default=str(ROOT/'data/observations'))
    parser.add_argument('--baseline')
    parser.add_argument('--file')
    parser.add_argument('--operator')
    parser.add_argument('--confirm-disconnected', action='store_true')
    parser.add_argument('--confirm-active', action='store_true')
    args = parser.parse_args()
    load_dotenv(ROOT/'.env')
    clock = lambda: datetime.now(UTC)
    try:
        profile = profile_contract(read_json(args.profiles)[args.profile])
        if profile['profile_id'] != args.profile:
            raise ValueError('Profile key and identity disagree')
        if args.action == 'baseline':
            if not args.confirm_disconnected:
                raise ValueError('Disconnected-state attestation is required')
            baseline = create_baseline(profile, fetch_receipt)
            path = Path(args.out)/'baselines'/(baseline['baseline_id']+'.json')
            write_once(path, canonical(baseline))
        elif args.action == 'capture':
            if not args.confirm_active or not args.baseline:
                raise ValueError('Active-state attestation and baseline file are required')
            baseline = read_json(args.baseline)
            if clock()-instant(baseline['receipt']['observed_at']) > timedelta(minutes=15):
                raise ValueError('Baseline is too old to start capture')
            record = create_observation(profile, baseline, fetch_receipt, clock)
            path = save_observation(args.out, record)
        elif args.action == 'import':
            if not args.file or profile['transport'] != 'browser_import':
                raise ValueError('A browser-import profile and receipt file are required')
            record = read_json(args.file, archive_folder=Path(args.out)/'imports')
            validate_observation(record, profile, clock())
            path = save_observation(args.out, record)
        else:
            if not args.file:
                raise ValueError('Observation file is required')
            record = read_json(args.file)
            save_observation(args.out, record)
            path = approve_artifact(args.out, record, profile, args.operator, clock())
    except Exception as error:
        failure = {'kind':'recorder_failure', 'at':stamp(clock()), 'error_type':type(error).__name__}
        try:
            write_once(Path(args.out)/'failures'/(str(uuid4())+'.json'), canonical(failure))
            archive_error_type = None
        except Exception as archive_error:
            archive_error_type = type(archive_error).__name__
        suffix = f' Failure archive unavailable ({archive_error_type}).' if archive_error_type else ''
        parser.exit(1, f'Recorder failed ({type(error).__name__}); no eligible evidence published.{suffix}\n')
    print(json.dumps({'status':'local_artifact', 'path':str(path)}))


if __name__ == '__main__':
    main()
```

- [x] Verify the CLI's bounded rejected-import archive and safe failure fallback. A candidate of at most 262144 bytes is archived under data/observations/imports by its hash before JSON parsing/validation. Oversize input keeps only a failure reason. The archive is private and never lookup-eligible. Test its existence after validation fails and a nonzero safe error when the archive directory cannot be written.
- [x] Add CLI tests for required attestations, browser-mode capture rejection, invalid/stale import, no direct fallback and credentials never appearing in stderr/artifacts. Test errors while writing failure metadata do not mask the original nonzero result; keep a safe stderr fallback.
- [x] Run `.venv/bin/python -m unittest discover -s tests -p 'test_exit_recorder.py' -v` and scoped Ruff for the three new modules/tests. Expected: all pass without network or DB access.

## Task 5: Operator instructions and review checkpoint

**Create:** docs/exit-recorder.md.

- [x] Document the exact local profile format with no credentials in the example:

```json
{"urban-desktop":{"profile_id":"urban-desktop","provider":"UrbanVPN","service_category":"vpn","transport":"system_tunnel","documentation_url":"https://www.urban-vpn.com/","proxy_env":null}}
```

- [x] Explain manual connect/disconnect, ipify's visibility of the public IP, system versus browser-extension paths, operator-attested provenance, proxy environment references and the 15-minute/24-hour rules. Explain the local review artifact is not yet live DB publication.
- [x] Show these exact command shapes; use actual returned artifact paths when executing:

With the operator's VPN disconnected, save the returned actual path in the same terminal session:

```bash
set -euo pipefail
VPNLENS_BASELINE_FILE=$(.venv/bin/python -m vpnlens.observe baseline --profile urban-desktop --confirm-disconnected | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["path"])')
```

The operator now connects their accessible VPN. Only after that intentional state change, run:

```bash
VPNLENS_OBSERVATION_FILE=$(.venv/bin/python -m vpnlens.observe capture --profile urban-desktop --baseline "$VPNLENS_BASELINE_FILE" --confirm-active | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["path"])')
```

After reviewing the actual receipt/profile binding:

```bash
.venv/bin/python -m vpnlens.observe approve --profile urban-desktop --file "$VPNLENS_OBSERVATION_FILE" --operator local-reviewer
```

These commands use actual returned paths, not literal sample UUIDs. Run them in the same operator terminal; separate agent shell calls do not preserve shell variables. Never execute baseline/capture while merely writing this plan.

- [x] Include a complete browser import example generated from observation_fixture('browser_import'), labelled synthetic and never loaded into the live database. Show how to replace each receipt with actual browser/profile observations while retaining original times/body hashes; do not promote copied fixture data.
- [x] Check ignored private directories, run pure tests/lint and summarize current limits. Stop at a reviewable diff; no commit/push without the user's request. Live publication follows the user SQL/integration plan.

Transport references checked during planning: [HTTPX environment handling](https://www.python-httpx.org/environment_variables/), [Client proxy API](https://www.python-httpx.org/api/#client). The installed lock currently pins HTTPX 0.28.1; retain that pin.

Execution checkpoint: Tasks 1-5 completed and independently approved by specification and quality reviewers. Final focused result: 29 distinct recorder tests passed with network/database connections blocked; scoped Ruff and pip check passed, and 39 collector tests remained green. Exact 24-hour expiry coverage was corrected during spec review. This is controlled producer proof only; no live tunnel or browser import was measured. Database publication is the next integration step.
