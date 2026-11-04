import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, isLookupResponse, lookupIP, validExtendedSecurity, validIPv4 } from '../src/api';
import { countryName, formatDate, summarize } from '../src/presentation';
import type { LookupResponse } from '../src/types';

const owner = (asn: string, name: string | null = 'Example Network') => ({
  asn,
  org_name: name,
  org_country_code: name ? 'OM' : null,
  org_snapshot_at: name ? '2026-10-01T00:00:00Z' : null,
  org_source_file: name ? 'fixture-org.gz' : null,
});
function fixture(): LookupResponse {
  const security = {
    vpn_status: 'unknown' as const,
    tor_status: 'unknown' as const,
    evidence: [],
    active_source_count: 11,
    recently_checked_source_count: 11,
    stale_after_hours: 48,
  };
  return {
    ip: '185.186.206.1',
    selected_sources: {
      routing: { source_file: 'routing.gz', snapshot_at: '2026-10-31T12:00:00Z' },
      organization: { source_file: 'org.gz', snapshot_at: '2026-10-01T00:00:00Z' },
    },
    results: [
      {
        ip: '185.186.206.1',
        country_code: 'OM',
        city_name: 'Muscat',
        prefix: '185.186.206.0/24',
        origin_group: '206350',
        snapshot_at: '2026-10-31T12:00:00Z',
        asn_owners: [owner('206350')],
        security,
      },
      {
        ip: '185.186.206.1',
        country_code: 'OM',
        city_name: 'Muscat',
        prefix: '185.186.206.0/24',
        origin_group: '28885,206350',
        snapshot_at: '2026-10-31T12:00:00Z',
        asn_owners: [owner('28885'), owner('206350')],
        security,
      },
    ],
  };
}
beforeEach(() =>
  vi.stubGlobal('window', {
    setTimeout: globalThis.setTimeout,
    clearTimeout: globalThis.clearTimeout,
  }),
);
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('API quota', () => {
  it.each([
    ['17', 'Too many requests. Try again in 17s.'],
    [null, 'Too many requests. Try again shortly.'],
  ])('handles Retry-After %s on HTTP 429', async (retryAfter, message) => {
    const headers = retryAfter ? { 'Retry-After': retryAfter } : undefined;
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 429, headers })));
    await expect(lookupIP('8.8.8.8')).rejects.toMatchObject({
      status: 429,
      code: 'rate_limit_exceeded',
      message,
    });
  });
});

describe('IPv4 input', () => {
  it.each(['0.0.0.0', '255.255.255.255', '8.8.8.8', ' 192.0.2.1 '])('accepts %s', (value) =>
    expect(validIPv4(value)).toBe(true),
  );
  it.each([
    '',
    '::1',
    'example.com',
    '1.2.3',
    '01.2.3.4',
    '1.2.3.256',
    '1.2.3.-1',
    '1.2.3.4/32',
    '1.2.3.4?x=1',
  ])('rejects %s', (value) => expect(validIPv4(value)).toBe(false));
  it('rejects invalid input before any network request', async () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    await expect(lookupIP('::1')).rejects.toMatchObject({ status: 422 });
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe('truthful results', () => {
  it('preserves tied groups and deduplicates only the owner summary', () => {
    const data = fixture();
    const result = summarize(data);
    expect(result.groups).toHaveLength(2);
    expect(result.owners).toHaveLength(2);
    expect(data.results[1].asn_owners).toHaveLength(2);
    expect(result.security.vpn_status).toBe('unknown');
    expect(result.finding).toBe('No recent VPN or Tor list match');
  });
  it('keeps unmapped ASN members and missing location', () => {
    const data = fixture();
    data.results[0].asn_owners = [owner('64500', null)];
    data.results.forEach((row) => {
      row.country_code = null;
      row.city_name = null;
    });
    expect(summarize(data).owners[0].org_name).toBeNull();
    expect(countryName(summarize(data).location.country_code)).toBe('Unavailable');
  });
  it('does not turn stale positive records into current listed status', () => {
    const data = fixture();
    data.results[0].security.evidence.push({
      source_id: 'fixture',
      indicator_type: 'vpn_server',
      provider: 'Example',
      source_url: 'https://example.test/list',
      checked_at: '2026-10-01T00:00:00Z',
      fetched_at: '2026-10-01T00:00:00Z',
      stale: true,
    });
    expect(summarize(data).recent).toHaveLength(0);
    expect(summarize(data).security.vpn_status).toBe('unknown');
  });
  it('keeps VPN and Tor findings separate', () => {
    const data = fixture();
    data.results[0].security.tor_status = 'listed';
    expect(summarize(data).finding).toBe('Tor exit association found');
    expect(summarize(data).security.vpn_status).toBe('unknown');
  });
  it('rejects malformed and legacy binary verdict responses', () => {
    expect(isLookupResponse(fixture())).toBe(true);
    expect(isLookupResponse({ ip: '8.8.8.8', security: { vpn: false } })).toBe(false);
    const data: any = fixture();
    data.results[0].security.active_source_count = undefined;
    expect(isLookupResponse(data)).toBe(false);
  });
  it('formats dates in the client timezone and handles missing dates', () => {
    expect(formatDate('2026-11-01T23:30:00Z')).toBe('2 Nov 2026');
    expect(formatDate(null)).toBe('Unavailable');
    expect(formatDate('invalid')).toBe('Unavailable');
  });
});

describe('API boundaries', () => {
  it('uses only the relative local lookup URL and preserves exact response data', async () => {
    const data = fixture();
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(data), { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    const result = await lookupIP(' 185.186.206.1 ');
    expect(fetch.mock.calls[0][0]).toBe('/v1/lookup/185.186.206.1');
    expect(result).toEqual(data);
  });
  it('does not expose backend error details or credentials', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('private-secret SQL', { status: 503 })),
    );
    await expect(lookupIP('8.8.8.8')).rejects.toMatchObject({ status: 503 });
    try {
      await lookupIP('8.8.8.8');
    } catch (error) {
      expect((error as Error).message).not.toContain('private-secret');
    }
  });
  it('reports malformed success data rather than inventing fallback results', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 200 })));
    await expect(lookupIP('8.8.8.8')).rejects.toMatchObject({ status: 502 });
  });
  it('cancels a superseded request', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url, options: RequestInit) =>
          new Promise((_resolve, reject) =>
            options.signal?.addEventListener('abort', () =>
              reject(new DOMException('Aborted', 'AbortError')),
            ),
          ),
      ),
    );
    const controller = new AbortController();
    const pending = lookupIP('8.8.8.8', controller.signal);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });
  it('reports a network failure without sample-data fallback', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('fetch failed')));
    await expect(lookupIP('8.8.8.8')).rejects.toBeInstanceOf(ApiError);
  });
});

function extendedSecurity(): any {
  return {
    ...fixture().results[0].security,
    vpn_assessment: 'network_only',
    proxy_status: 'unknown',
    residential_proxy_status: 'unknown',
    residential_proxy_reason: 'No qualifying residential-relay evidence has been collected',
    additional_evidence: [
      {
        source_id: 'network-fixture',
        family: 'fixture',
        record_key: 'network-1',
        network: '8.8.8.0/24',
        provider: null,
        basis: 'network_inference',
        role: 'unknown',
        method: 'cidr_text',
        service_category: 'vpn',
        source_url: 'https://example.test/list',
        checked_at: '2026-11-02T00:00:00Z',
        fetched_at: '2026-11-01T00:00:00Z',
        observed_at: null,
        expires_at: null,
        review_state: null,
        hostname: null,
        stale: false,
      },
    ],
  };
}
function withSecurity(security: any) {
  const data = fixture();
  data.results[0].security = security;
  return data;
}
describe('extended evidence boundary', () => {
  it('accepts legacy and complete extended responses without mutating either', async () => {
    const data = withSecurity(extendedSecurity());
    expect(isLookupResponse(fixture())).toBe(true);
    expect(isLookupResponse(data)).toBe(true);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(data))));
    expect(await lookupIP(data.ip)).toEqual(data);
  });
  it.each([
    'vpn_assessment',
    'proxy_status',
    'residential_proxy_status',
    'residential_proxy_reason',
    'additional_evidence',
  ])('rejects partial extension introduced by %s', (field) => {
    const security: any = { ...fixture().results[0].security, [field]: extendedSecurity()[field] };
    expect(isLookupResponse(withSecurity(security))).toBe(false);
  });
  it.each([
    ['vpn_assessment', 'detected'],
    ['proxy_status', true],
    ['residential_proxy_status', 'listed'],
    ['residential_proxy_status', true],
    ['residential_proxy_reason', null],
    ['additional_evidence', {}],
  ])('rejects malformed extension %s=%s', (field, value) => {
    const security = extendedSecurity();
    security[field] = value;
    expect(isLookupResponse(withSecurity(security))).toBe(false);
  });
  it.each([
    ['source_id', null],
    ['family', 2],
    ['record_key', null],
    ['network', null],
    ['method', null],
    ['source_url', null],
    ['checked_at', null],
    ['fetched_at', null],
    ['provider', 2],
    ['hostname', false],
    ['observed_at', false],
    ['expires_at', 42],
    ['basis', 'hosting'],
    ['role', 'relay'],
    ['service_category', 'residential'],
    ['review_state', 'pending'],
    ['stale', 'false'],
    ['operator_attested', 'true'],
    ['connection_type_claim', 'verified_residential'],
  ])('rejects malformed additional record %s=%s', (field, value) => {
    const security = extendedSecurity();
    security.additional_evidence[0][field] = value;
    expect(isLookupResponse(withSecurity(security))).toBe(false);
  });
  it.each(['observed_at', 'expires_at', 'review_state'])(
    'requires original clocks and approval for exits: %s',
    (field) => {
      const security = extendedSecurity();
      Object.assign(security.additional_evidence[0], {
        basis: 'exit_observation',
        role: 'exit',
        method: 'browser_import',
        observed_at: '2026-11-01T10:00:00Z',
        expires_at: '2026-11-02T10:00:00Z',
        review_state: 'approved',
      });
      expect(isLookupResponse(withSecurity(security))).toBe(true);
      security.additional_evidence[0][field] = null;
      expect(isLookupResponse(withSecurity(security))).toBe(false);
    },
  );
  it('prioritizes VPN and Tor, then proxy, then weak network findings', () => {
    const security = extendedSecurity();
    const data = withSecurity(security);
    expect(summarize(data).finding).toBe('Possible VPN-network association');
    security.proxy_status = 'listed';
    expect(summarize(data).finding).toBe('Proxy exit association found');
    security.tor_status = 'listed';
    expect(summarize(data).finding).toBe('Tor exit association found');
    security.vpn_status = 'listed';
    expect(summarize(data).finding).toBe('VPN and Tor associations found');
  });
});

describe('safe typed evidence rendering', () => {
  it('exports a standalone extension guard with legacy compatibility', () => {
    expect(validExtendedSecurity(fixture().results[0].security)).toBe(true);
    expect(validExtendedSecurity(extendedSecurity())).toBe(true);
    expect(validExtendedSecurity(null)).toBe(false);
    expect(validExtendedSecurity({ residential_proxy_status: 'listed' })).toBe(false);
  });
  it.each([
    ['record_key', {}],
    ['method', {}],
    ['role', 'relay'],
    ['observed_at', {}],
    ['expires_at', 42],
    ['operator_attested', 'true'],
    ['connection_type_claim', 'verified'],
  ])('rejects malformed optional strong record %s=%s', (field, value) => {
    const data = fixture();
    data.results[0].security.evidence = [
      {
        source_id: 'fixture',
        indicator_type: 'vpn_server',
        provider: null,
        source_url: 'https://example.test/list',
        checked_at: '2026-11-02T00:00:00Z',
        fetched_at: '2026-11-02T00:00:00Z',
        stale: false,
        [field]: value,
      },
    ];
    expect(isLookupResponse(data)).toBe(false);
  });
});
