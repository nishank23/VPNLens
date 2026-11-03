# Public Evidence Collectors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Produce validated, reproducible public-evidence candidate batches without changing lookup data.

**Architecture:** Use one reviewed registry and format adapters. Save immutable raw archives and normalized candidate envelopes under ignored data/evidence-v2; activation belongs to the integration plan. Existing eleven-source code remains unchanged.

**Tech Stack:** Python 3.12, urllib/csv/ipaddress, dnspython 2.9.1, unittest.

---

Root: /Users/nishankbansal/Documents/VPNLens. Prerequisite: approved [design](../specs/2026-11-02-vpn-evidence-expansion-design.md). Follow [execution/ownership](2026-11-02-vpn-evidence-expansion.md). Each checkbox is a small action; stop between tasks if the diff departs from the design.

## Task 1: Shared artifact and normalization contract

**Create:** vpnlens/evidence_contract.py; tests/test_evidence_collectors.py.

- [x] Add these meaningful initial tests, run `.venv/bin/python -m unittest discover -s tests -p 'test_evidence_collectors.py' -v`, and confirm failure is the missing module/function rather than test syntax.

```python
import tempfile
import unittest
from pathlib import Path
from vpnlens.evidence_contract import public_network, canonical, write_once

class ArtifactTests(unittest.TestCase):
    def test_network_normalization_does_not_expand_ranges(self):
        self.assertEqual(public_network('103.108.230.0/24'), '103.108.230.0/24')
        self.assertEqual(public_network('8.8.8.8'), '8.8.8.8/32')
        for value in ('10.0.0.1', '0.0.0.0/0', '103.108.230.1/24'):
            with self.assertRaises(ValueError):
                public_network(value)
    def test_immutable_artifacts_are_idempotent_and_reject_conflicts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'record.json'
            write_once(path, canonical({'x': 1}))
            write_once(path, canonical({'x': 1}))
            with self.assertRaises(ValueError):
                write_once(path, canonical({'x': 2}))
```

- [x] Implement the complete shared module. It contains no SQL or classification policy.

```python
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from ipaddress import ip_network
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def stamp(value=None):
    value = value or datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError('Timestamp requires timezone')
    return value.astimezone(UTC).isoformat()


def instant(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('Timestamp requires timezone')
    return parsed.astimezone(UTC)


def public_network(value):
    network = ip_network(value, strict=True)
    if network.version != 4:
        raise ValueError('Only IPv4 networks are supported')
    if network.prefixlen == 0 or not network.is_global:
        raise ValueError('A public non-catch-all IPv4 network is required')
    return str(network)


def write_once(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise ValueError('Conflicting or corrupted immutable artifact')
    finally:
        os.unlink(temporary)
```

- [x] Run the same test command; expect both tests to pass. Confirm artifacts use private temporary-file permissions and no path replacement.
- [x] Add tests for naive timestamps, JSON non-finite values and corruption of an existing archive. Use the same public network inputs; documentation/private ranges are intentionally invalid collection inputs.

## Task 2: Registry and record identity

**Create:** config/evidence_sources.json. **Create/modify:** vpnlens/evidence_collectors.py; tests/test_evidence_collectors.py.

- [x] Save this registry; it supplies the exact initial source/provenance data, not a promise of whole-provider coverage.

```json
{
  "schema_version": 1,
  "sources": [
    {"source_id":"x4b-vpn-v4","family":"x4b","enabled":true,"adapter":"cidr_text","basis":"network_inference","provider":null,"role":"unknown","url":"https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv4.txt","max_bytes":5000000,"max_age_hours":48,"attribution_url":"https://github.com/X4BNet/lists_vpn"},
    {"source_id":"vpngate-v4","family":"vpngate","enabled":true,"adapter":"vpngate_csv","basis":"provider_list","provider":"VPN Gate","role":"server","url":"https://www.vpngate.net/api/iphone/","max_bytes":25000000,"max_age_hours":48,"attribution_url":"https://www.vpngate.net/en/"},
    {"source_id":"urbanvpn-dns-v4","family":"urbanvpn-reviewed-hostnames","enabled":true,"adapter":"dns_a","basis":"provider_dns","provider":"UrbanVPN","role":"unknown","url":"https://www.netify.ai/resources/ips/103.108.230.50","hosts":["p-jp1.urban-vpn.com"],"max_bytes":5000000,"max_age_hours":48,"attribution_url":"https://www.urban-vpn.com/"}
  ]
}
```

- [x] Add normalization/registry functions to vpnlens/evidence_collectors.py. Keep record identity separate from observation timestamps.

```python
import re
from urllib.parse import urlsplit
from vpnlens.evidence_contract import canonical, digest, public_network


def registry_entries(registry):
    if registry.get('schema_version') != 1 or not isinstance(registry.get('sources'), list):
        raise ValueError('Unsupported source registry')
    entries, seen = [], set()
    for source in registry['sources']:
        source_id = source.get('source_id', '')
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,99}', source_id) or source_id in seen:
            raise ValueError('Invalid or repeated source ID')
        seen.add(source_id)
        if not isinstance(source.get('enabled'), bool):
            raise ValueError('Source enabled state requires a boolean')
        parts = urlsplit(source.get('url', ''))
        if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
            raise ValueError('Source URL must be credential-free HTTPS')
        if source.get('adapter') not in {'host_text','cidr_text','vpngate_csv','dns_a'}:
            raise ValueError('Unsupported source adapter')
        expected_basis = {'host_text':'provider_list', 'cidr_text':'network_inference',
                          'vpngate_csv':'provider_list', 'dns_a':'provider_dns'}
        if source.get('basis') != expected_basis[source['adapter']]:
            raise ValueError('Adapter and evidence basis disagree')
        if source.get('role') not in {'server','exit','unknown'}:
            raise ValueError('Unsupported endpoint role')
        if not isinstance(source.get('family'), str) or not source['family']:
            raise ValueError('Source family is required')
        if source.get('provider') is not None and not isinstance(source['provider'], str):
            raise ValueError('Provider must be text or null')
        if source.get('max_age_hours') != 48:
            raise ValueError('This release uses the reviewed 48-hour source policy')
        cap = 25000000 if source['adapter'] == 'vpngate_csv' else 5000000
        if source.get('max_bytes') != cap:
            raise ValueError('Source cap differs from reviewed adapter policy')
        if source['adapter'] == 'dns_a':
            hosts = source.get('hosts', [])
            if not hosts or len(hosts) != len(set(hosts)):
                raise ValueError('DNS source requires distinct reviewed hosts')
            if any(not isinstance(host, str) or len(host) > 253 or
                   any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label)
                       for label in host.split('.')) for host in hosts):
                raise ValueError('Invalid reviewed hostname')
        entries.append(dict(source))
    return entries


def indicator(source, address, hostname=None, metadata=None):
    record = dict(network=public_network(address), provider=source['provider'],
                  basis=source['basis'], role=source['role'], hostname=hostname,
                  service_category='vpn', method=source['adapter'])
    record['record_key'] = digest(canonical(record))
    record['metadata'] = metadata or {}
    return record
```

- [x] Test duplicate IDs, false/disabled entries retained in registry metadata, credentialed URLs, unreviewed adapters, invalid hosts, network-range identity and provider/hostname overlaps. Ensure disabled entries are not fetched in Task 5.
- [x] Run the pure test command. Expected: all registry/artifact tests pass without opening a DB or socket.

## Task 3: Host, CIDR and CSV parsers

**Modify:** vpnlens/evidence_collectors.py; tests/test_evidence_collectors.py.

- [x] Add a failing test that parses a /24 into one indicator, skips a supported syntactic IPv6 row with an explicit count, and rejects invalid public-IPv4 data rather than publishing a partial feed.
- [x] Implement these functions with the imports shown.

```python
import csv
import io
from ipaddress import ip_network


def parse_text(payload, source):
    result, skipped = {}, 0
    for line in payload.decode('utf-8-sig').splitlines():
        value = line.strip()
        if not value or value.startswith('#'):
            continue
        network = ip_network(value, strict=True)
        if network.version == 6:
            skipped += 1
            continue
        if source['adapter'] == 'host_text' and network.prefixlen != 32:
            raise ValueError('Host feed contains a range')
        item = indicator(source, value)
        result[item['record_key']] = item
    if not result:
        raise ValueError('HTTP feed has no supported IPv4 records')
    return sorted(result.values(), key=lambda item: item['record_key']), skipped


def parse_vpngate(payload, source):
    csv.field_size_limit(source['max_bytes'])
    lines = [line for line in payload.decode('utf-8-sig').splitlines()
             if line.strip() and not line.startswith('*')]
    reader = csv.DictReader(io.StringIO('\n'.join(lines)))
    if not reader.fieldnames or 'IP' not in reader.fieldnames or '#HostName' not in reader.fieldnames:
        raise ValueError('VPN Gate CSV headers changed')
    result, skipped = {}, 0
    for row in reader:
        network = ip_network(row.get('IP', ''), strict=True)
        if network.version == 6:
            skipped += 1
            continue
        if network.prefixlen != 32 or not row.get('#HostName'):
            raise ValueError('VPN Gate requires a host IP and hostname')
        item = indicator(source, row['IP'], hostname=row['#HostName'])
        result[item['record_key']] = item
    if not result:
        raise ValueError('VPN Gate has no supported IPv4 records')
    return sorted(result.values(), key=lambda item: item['record_key']), skipped
```

- [x] Add fixtures with a fake configuration column and verify it is ignored, not decoded or executed. Test missing headers, malformed IPs, invalid UTF-8, duplicate hosts and empty feeds. Pure fixtures may use real public IP strings but do not prove those addresses are VPNs.
- [x] Run all pure tests; expect passes and no source refresh or database writes.

## Task 4: Bounded HTTP and DNS adapters

**Modify:** requirements.txt, requirements.lock, vpnlens/evidence_collectors.py; tests/test_evidence_collectors.py.

- [x] Add `dnspython==2.9.1` to requirements.txt and insert the same pin into the alphabetically sorted requirements.lock, retaining every existing pin. Run `.venv/bin/python -m pip install --no-deps dnspython==2.9.1` during execution, then `.venv/bin/python -m pip check`; expect successful installation and no broken requirements. Review that no unrelated package upgrade entered the diff. No package installation is performed while writing this plan.
- [x] Test the adapters with fake response/resolver objects, including a selected proxy/transport failure. Then implement:

```python
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
import dns.resolver


def fetch_payload(source, opener=urlopen):
    request = Request(source['url'], headers={'User-Agent':'VPNLens-portfolio/1.0'})
    with opener(request, timeout=30) as response:
        if response.status != 200:
            raise ValueError('Source did not return HTTP 200')
        final = urlsplit(response.geturl())
        if final.scheme != 'https' or final.username or final.password:
            raise ValueError('Unsafe source redirect')
        length = response.headers.get('Content-Length')
        if length is not None and not 0 <= int(length) <= source['max_bytes']:
            raise ValueError('Source exceeds download cap')
        payload = response.read(source['max_bytes'] + 1)
    if len(payload) > source['max_bytes']:
        raise ValueError('Source exceeds download cap')
    if length is not None and len(payload) != int(length):
        raise ValueError('Source download was incomplete')
    return payload


def resolve_a(hostname, resolver=None):
    resolver = resolver or dns.resolver.Resolver()
    try:
        answer = resolver.resolve(hostname + '.', 'A', search=False,
                                  lifetime=5.0, raise_on_no_answer=False)
    except dns.resolver.NXDOMAIN:
        return {'hostname': hostname, 'addresses': [], 'ttl': None, 'state':'nxdomain'}
    if answer.rrset is None:
        return {'hostname': hostname, 'addresses': [], 'ttl': None, 'state':'no_a'}
    addresses = sorted({str(item.address) for item in answer})
    for address in addresses:
        public_network(address)
    return {'hostname': hostname, 'addresses': addresses,
            'ttl': answer.rrset.ttl, 'state':'answer'}
```

- [x] Confirm NXDOMAIN/no-A are explicit withdrawal results; timeout/SERVFAIL propagate failure. A-only DNS does not claim to enumerate IPv6; metadata records the queried family. Test malformed/special-purpose A answers, size/length limits and redirects. Avoid logging exception strings or credentials.
- [x] Run pure tests and `.venv/bin/python -m ruff check --no-cache vpnlens/evidence_contract.py vpnlens/evidence_collectors.py tests/test_evidence_collectors.py`.

References checked for this plan: [resolver API](https://dnspython.readthedocs.io/en/stable/resolver-class.html), [release/Python support](https://pypi.org/project/dnspython/). Default caches/TTLs are not service-activity timestamps.

## Task 5: Candidate preparation and standalone CLI

**Create:** vpnlens/evidence_collect.py. **Modify:** vpnlens/evidence_collectors.py; tests/test_evidence_collectors.py.

- [x] Test that a failed final source leaves raw archives but no completed batch manifest, and no database publication occurs.
- [x] Add this complete orchestration function. It preserves all registry entries, including disabled ones, for later atomic registry publication.

```python
from pathlib import Path
from uuid import uuid4
from datetime import UTC, datetime
from vpnlens.evidence_contract import stamp, write_once


def prepare_batch(registry, folder, fetcher=fetch_payload, resolver=resolve_a, clock=None):
    clock = clock or (lambda: datetime.now(UTC))
    entries = registry_entries(registry)
    snapshots = []
    for source in entries:
        if not source['enabled']:
            continue
        if source['adapter'] == 'dns_a':
            answers = []
            for host in source['hosts']:
                started = stamp(clock())
                answers.append({**resolver(host), 'queried_at':started,
                                'completed_at':stamp(clock())})
            checked_at = stamp(clock())
            payload = canonical({'checked_at':checked_at, 'family':'A', 'answers':answers})
            records = [indicator(source, ip, answer['hostname'], {'ttl':answer['ttl']})
                       for answer in answers for ip in answer['addresses']]
            skipped = 0
        else:
            payload = fetcher(source)
            checked_at = stamp(clock())
            parser = parse_vpngate if source['adapter'] == 'vpngate_csv' else parse_text
            records, skipped = parser(payload, source)
        if len(payload) > source['max_bytes']:
            raise ValueError('Collected source exceeds cap')
        sha = digest(payload)
        raw = Path(folder) / 'raw' / source['source_id'] / (sha + '.bin')
        write_once(raw, payload)
        snapshots.append({'source':source, 'content_sha256':sha,
                          'fetched_at':checked_at, 'checked_at':checked_at,
                          'publisher_at':None, 'raw_ref':str(raw.relative_to(folder)),
                          'records':records, 'ipv6_skipped':skipped})
    batch = {'schema_version':1, 'batch_id':str(uuid4()), 'checked_at':stamp(clock()),
             'registry_sha256':digest(canonical(registry)), 'registry':registry,
             'snapshots':snapshots}
    path = Path(folder) / 'candidates' / (batch['batch_id'] + '.json')
    write_once(path, canonical(batch))
    return path
```

- [x] Save the full CLI entry module:

```python
import argparse
import json
from vpnlens.config import ROOT
from vpnlens.evidence_collectors import prepare_batch


def main():
    parser = argparse.ArgumentParser(description='Prepare public evidence; do not publish it.')
    parser.add_argument('--registry', default=str(ROOT/'config/evidence_sources.json'))
    parser.add_argument('--out', default=str(ROOT/'data/evidence-v2'))
    args = parser.parse_args()
    try:
        with open(args.registry, encoding='utf-8') as source:
            registry = json.load(source)
        path = prepare_batch(registry, args.out)
    except Exception as error:
        parser.exit(1, f'Collection failed ({type(error).__name__}); active data unchanged.\n')
    print(json.dumps({'status':'prepared', 'candidate':str(path)}))


if __name__ == '__main__':
    main()
```

- [x] Add fake-clock/fake-fetch tests for unchanged raw hashes, new dated DNS bundles, disabled sources, fully empty successful DNS withdrawal, resolver failure and tampered archives. Use a temporary directory; candidate metadata is not live proof.
- [x] Run pure tests and scoped lint. Do not run the live collector until the execution validation step explicitly calls for it.

## Task 6: Producer documentation and review checkpoint

**Create:** docs/public-evidence.md. **Modify:** .github/workflows/tests.yml (new files in owned lint scope only).

- [x] Document registry keys, actual adapter distinctions, raw/candidate locations, partial coverage, withdrawal versus failure, source attribution and candidate-only behavior.
- [x] Check `git check-ignore data/evidence-v2/example.json` returns the data path. No actual profile/receipt is staged.
- [x] Run `.venv/bin/python -m unittest discover -s tests -p 'test_evidence_collectors.py' -v` and scoped lint. Expected: every pure test passes; no DB/API behavior changed.
- [x] Summarize changed files, passed checks and collection limits. Treat this as a commit-sized review checkpoint; do not stage or commit unless requested. Database publication follows the integration plan's user SQL gate.

Execution checkpoint: Tasks 2-6 completed and independently approved by specification and quality reviewers. Final focused result: 39 tests passed with DNS/socket access blocked, scoped Ruff passed, pip check passed. HTTPS redirect targets and intermediate response bounds were fixed through reproduced regression tests. Live collection is a separate verification step.
