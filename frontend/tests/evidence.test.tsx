// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ResultView } from '../src/components/ResultView';
import { SourcesView } from '../src/components/SourcesView';
import { JsonView } from '../src/components/JsonView';
import type { LookupResponse, SourceResponse } from '../src/types';

function fixture(): LookupResponse {
  return {
    ip: '8.8.8.8',
    selected_sources: {
      routing: { source_file: 'route.gz', snapshot_at: '2026-11-01T00:00:00Z' },
      organization: { source_file: 'org.gz', snapshot_at: '2026-11-01T00:00:00Z' },
    },
    results: [
      {
        ip: '8.8.8.8',
        country_code: null,
        city_name: null,
        prefix: null,
        origin_group: null,
        snapshot_at: null,
        asn_owners: [],
        security: {
          vpn_status: 'unknown',
          tor_status: 'unknown',
          evidence: [],
          active_source_count: 11,
          recently_checked_source_count: 11,
          stale_after_hours: 48,
        },
      },
    ],
  };
}
function extended(): LookupResponse {
  const data = fixture();
  Object.assign(data.results[0].security, {
    vpn_assessment: 'network_only',
    proxy_status: 'unknown',
    residential_proxy_status: 'unknown',
    residential_proxy_reason: 'No qualifying residential-relay evidence has been collected',
    additional_evidence: [
      {
        source_id: 'x4b-fixture',
        family: 'x4b',
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
  });
  return data;
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('evidence explanations in the current interface', () => {
  it('keeps the legacy presentation without an additional section', () => {
    render(<ResultView data={fixture()} />);
    expect(screen.queryByRole('heading', { name: 'Additional evidence' })).toBeNull();
    expect(screen.getByText('No recent VPN or Tor list match')).toBeTruthy();
  });
  it('explains weak networks without claiming direct VPN or residential evidence', () => {
    render(<ResultView data={extended()} />);
    const panel = screen.getByRole('region', { name: 'Additional evidence' });
    expect(
      within(panel).getByText('Possible VPN-network association. No direct VPN endpoint evidence.'),
    ).toBeTruthy();
    expect(
      within(panel).getByText('Residential proxy: Unknown. Qualifying evidence is not available.'),
    ).toBeTruthy();
    expect(within(panel).getByText('Proxy exit association: Unknown')).toBeTruthy();
    expect(within(panel).getByText('Network inference')).toBeTruthy();
    expect(within(panel).getByText('x4b-fixture')).toBeTruthy();
    expect(within(panel).getByText('8.8.8.0/24')).toBeTruthy();
    const supporting = screen.getByRole('region', { name: 'Supporting evidence' });
    expect(
      supporting.compareDocumentPosition(panel) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
  it('shows proxy-only findings and labels stale attestation and pool claims as unverified', () => {
    const data = extended();
    const security: any = data.results[0].security;
    security.proxy_status = 'listed';
    security.vpn_assessment = 'unknown';
    Object.assign(security.additional_evidence[0], {
      basis: 'exit_observation',
      method: 'browser_import',
      role: 'exit',
      service_category: 'proxy',
      operator_attested: true,
      connection_type_claim: 'residential',
      stale: true,
      review_state: 'approved',
      observed_at: '2026-11-01T10:00:00Z',
      expires_at: '2026-11-02T10:00:00Z',
    });
    render(<ResultView data={data} />);
    expect(screen.getByText('Proxy exit association found')).toBeTruthy();
    expect(screen.getByText('Proxy exit association: Listed')).toBeTruthy();
    expect(screen.getByText('Stale match')).toBeTruthy();
    expect(screen.getByText(/Operator-attested.*not recorder-verified/)).toBeTruthy();
    expect(screen.getByText('Reported pool: residential (unverified)')).toBeTruthy();
    expect(screen.getByText('Dated service observation')).toBeTruthy();
  });
  it('retains distinct hostname records, original exit dates and method/role labels', () => {
    const data = extended();
    const security: any = data.results[0].security;
    security.vpn_assessment = 'direct_association';
    security.vpn_status = 'listed';
    const record = {
      source_id: 'same-provider',
      provider: 'Fixture VPN',
      indicator_type: 'vpn_server',
      source_url: 'https://example.test/list',
      checked_at: '2026-11-03T12:00:00Z',
      fetched_at: '2026-11-03T12:00:00Z',
      stale: false,
      method: 'browser_import',
      role: 'exit',
      observed_at: '2026-11-01T10:15:00Z',
      expires_at: '2026-11-02T10:15:00Z',
      operator_attested: true,
      connection_type_claim: 'mobile',
    };
    security.evidence = [
      { ...record, record_key: 'host-a' },
      { ...record, record_key: 'host-b' },
    ];
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {});
    render(<ResultView data={data} />);
    const panel = screen.getByRole('region', { name: 'Supporting evidence' });
    expect(within(panel).getAllByText('Fixture VPN')).toHaveLength(2);
    expect(within(panel).getAllByText('Method: browser_import · Role: exit')).toHaveLength(2);
    expect(within(panel).getAllByText(/Operator-attested.*not recorder-verified/)).toHaveLength(2);
    expect(within(panel).getAllByText('Reported pool: mobile (unverified)')).toHaveLength(2);
    expect(panel.querySelectorAll('time[datetime="2026-11-01T10:15:00Z"]')).toHaveLength(2);
    expect(panel.querySelectorAll('time[datetime="2026-11-02T10:15:00Z"]')).toHaveLength(2);
    expect(panel.textContent).toContain('Observed');
    expect(panel.textContent).toContain('Expires');
    expect(errors).not.toHaveBeenCalled();
    const link = within(panel).getAllByRole('link', { name: 'Open source record' })[0];
    link.focus();
    expect(document.activeElement).toBe(link);
  });
  it('preserves and copies exact returned JSON after rendering extended evidence', async () => {
    const data = extended();
    const original = JSON.stringify(data, null, 2);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    render(
      <>
        <ResultView data={data} />
        <JsonView data={data} loading={false} latency={null} />
      </>,
    );
    expect(screen.getByLabelText('Exact API response for 8.8.8.8').textContent).toBe(original);
    const copy = screen.getByRole('button', { name: 'Copy JSON response' });
    copy.focus();
    expect(document.activeElement).toBe(copy);
    fireEvent.click(copy);
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(original));
    expect(JSON.stringify(data, null, 2)).toBe(original);
  });
  it('names unknown providers by source ID and counts network records without expanding addresses', () => {
    const source: any = {
      ...(extended().results[0].security as any).additional_evidence[0],
      indicator_type: 'network_inference',
      record_kind: 'network',
      ipv4_count: 10999,
      ipv6_skipped: 0,
    };
    const data: SourceResponse = {
      geolocation: { available: false, snapshot_at: null },
      routing: [],
      organization: [],
      security: [source],
      security_stale_after_hours: 48,
      refresh: {},
      ...{ security_expected_source_ids: ['x4b-fixture', 'missing-enabled-source'] },
    };
    render(<SourcesView data={data} error={null} loading={false} refresh={() => {}} />);
    expect(screen.getByText('x4b-fixture')).toBeTruthy();
    expect(screen.queryByText('Tor Project')).toBeNull();
    expect(screen.getByText('VPN networks')).toBeTruthy();
    expect(screen.getByText('10,999')).toBeTruthy();
    expect(screen.getByText('1 / 2')).toBeTruthy();
    expect(
      screen.getByText(/Counts describe records and networks, not unique addresses/),
    ).toBeTruthy();
    const table = screen.getByLabelText('Public evidence feed records');
    table.focus();
    expect(document.activeElement).toBe(table);
  });
});

describe('measured exit provenance', () => {
  it.each([
    ['system_tunnel', 'vpn'],
    ['explicit_http_proxy', 'proxy'],
  ])('explains %s observations without calling them browser imports', (method, category) => {
    const data = extended();
    const security: any = data.results[0].security;
    const item = {
      ...security.additional_evidence[0],
      source_id: 'measured-exit',
      provider: 'Reviewed provider',
      basis: 'exit_observation',
      role: 'exit',
      method,
      service_category: category,
      network: '8.8.8.8/32',
      operator_attested: true,
      review_state: 'approved',
      observed_at: '2026-11-02T10:15:00Z',
      expires_at: '2026-11-03T10:15:00Z',
    };
    security.additional_evidence = [item];
    if (category === 'vpn') {
      security.vpn_assessment = 'direct_association';
      security.vpn_status = 'listed';
      security.evidence = [{ ...item, indicator_type: 'vpn_server' }];
    } else {
      security.vpn_assessment = 'unknown';
      security.proxy_status = 'listed';
    }
    const { rerender } = render(<ResultView data={data} />);
    const additional = screen.getByRole('region', { name: 'Additional evidence' });
    expect(within(additional).getByText(`Method: ${method} · Role: exit`)).toBeTruthy();
    expect(within(additional).getByText('Operator-attested provider label.')).toBeTruthy();
    expect(additional.querySelector('time[datetime="2026-11-02T10:15:00Z"]')).toBeTruthy();
    expect(additional.querySelector('time[datetime="2026-11-03T10:15:00Z"]')).toBeTruthy();
    expect(additional.textContent).toContain('Observed');
    expect(additional.textContent).toContain('Expires');
    const link = within(additional).getByRole('link', { name: 'Open source record' });
    expect(link.getAttribute('href')).toBe(item.source_url);
    link.focus();
    expect(document.activeElement).toBe(link);
    expect(screen.queryByText(/browser import|not recorder-verified/i)).toBeNull();
    if (category === 'vpn') {
      const supporting = screen.getByRole('region', { name: 'Supporting evidence' });
      expect(within(supporting).getByText('Operator-attested provider label.')).toBeTruthy();
      expect(within(supporting).getByText('Method: system_tunnel · Role: exit')).toBeTruthy();
    }
    item.source_url = 'http://example.test/untrusted';
    rerender(<ResultView data={data} />);
    expect(
      within(screen.getByRole('region', { name: 'Additional evidence' })).queryByRole('link'),
    ).toBeNull();
  });
});
