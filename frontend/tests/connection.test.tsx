// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { checkConnection, checkIP, isDecisionResponse } from '../src/api';
import type { DecisionResponse } from '../src/types';

vi.mock('../src/useMotion', () => ({
  useLookupIntro: vi.fn(),
  useResultFeedback: vi.fn(),
  useSourceScroll: vi.fn(),
}));

function fixture(ip = '8.8.8.8', block = false): DecisionResponse {
  return {
    lookup: {
      ip,
      selected_sources: {
        routing: { source_file: 'routing-fixture.gz', snapshot_at: '2026-11-01T00:00:00Z' },
        organization: { source_file: 'org-fixture.gz', snapshot_at: '2026-11-01T00:00:00Z' },
      },
      results: [
        {
          ip,
          country_code: 'JP',
          city_name: 'Tokyo',
          prefix: null,
          origin_group: null,
          snapshot_at: null,
          asn_owners: [],
          security: {
            vpn_status: block ? 'listed' : 'unknown',
            tor_status: 'unknown',
            active_source_count: 11,
            recently_checked_source_count: 11,
            stale_after_hours: 48,
            evidence: block
              ? [
                  {
                    source_id: 'vpn-fixture',
                    indicator_type: 'vpn_server',
                    provider: 'Fixture VPN',
                    source_url: 'https://example.test/list',
                    checked_at: '2026-11-03T10:00:00Z',
                    fetched_at: '2026-11-03T10:00:00Z',
                    stale: false,
                  },
                ]
              : [],
          },
        },
      ],
    },
    decision: {
      policy_id: 'streaming-access-v1',
      action: block ? 'block' : 'allow',
      reason_codes: [block ? 'recent_vpn_evidence' : 'no_recent_blocking_evidence'],
      scheduled_source_health: 'ready',
      evaluated_at: '2026-11-03T10:00:00Z',
    },
  };
}
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
beforeEach(() => {
  window.location.hash = '';
  localStorage.removeItem('vpnlens:ipify-consent');
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('decision API boundary', () => {
  it('fetches only same-origin routes and preserves extra response fields exactly', async () => {
    const data = { ...fixture(), request_note: 'fixture-only extra field' };
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(response(data)));
    vi.stubGlobal('fetch', fetch);
    expect(await checkConnection()).toEqual(data);
    expect(await checkIP(' 8.8.8.8 ')).toEqual(data);
    expect(fetch.mock.calls.map((call) => call[0])).toEqual([
      '/v1/connection',
      '/v1/access-decision/8.8.8.8',
    ]);
    expect(fetch.mock.calls[0][1].cache).toBe('no-store');
  });
  it.each([
    ['action', 'safe'],
    ['reason_codes', []],
    ['scheduled_source_health', 'complete'],
    ['evaluated_at', 'invalid'],
    ['policy_id', 'other-policy'],
  ])('rejects malformed decisions: %s', (field, value) => {
    const data = fixture();
    Object.assign(data.decision, { [field]: value });
    expect(isDecisionResponse(data)).toBe(false);
  });
  it('rejects a manual result for a different IP', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(fixture('1.1.1.1'))));
    await expect(checkIP('8.8.8.8')).rejects.toMatchObject({ status: 502 });
  });
  it('rejects inconsistent actions and reason categories', () => {
    const data = fixture();
    data.decision.action = 'block';
    expect(isDecisionResponse(data)).toBe(false);
  });
  it('maps connection discovery failures without exposing server details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(response({ detail: 'private internal text' }, 409)),
    );
    await expect(checkConnection()).rejects.toMatchObject({
      status: 409,
      code: 'public_ipv4_unavailable',
    });
  });
});

describe('focused live connection screen', () => {
  it.each([
    { listed: true, network: false, verdict: 'VPN detected', score: '80 / 100' },
    { listed: false, network: true, verdict: 'VPN network match', score: '35 / 100' },
    { listed: false, network: false, verdict: 'No VPN match', score: 'Unrated' },
  ])('exposes $verdict and its evidence score without WebGL', async (example) => {
    const data = fixture('8.8.8.8', example.listed);
    const row = data.lookup.results[0];
    row.prefix = '8.8.8.0/24';
    row.origin_group = '15169';
    if (example.network) {
      Object.assign(row.security, {
        vpn_assessment: 'network_only',
        proxy_status: 'unknown',
        residential_proxy_status: 'unknown',
        residential_proxy_reason: 'No qualifying evidence',
        additional_evidence: [],
      });
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(data)));
    render(<App />);

    const inspect = await screen.findByRole('button', { name: 'Inspect IP' });
    expect(screen.getByRole('heading', { level: 1, name: '8.8.8.8' })).toBeTruthy();
    expect(screen.getByText(example.verdict).closest('[hidden]')).toBeTruthy();
    fireEvent.click(inspect);
    const readout = screen.getByLabelText('IP inspection');
    expect(readout.hidden).toBe(false);
    expect(readout.textContent).toContain('AS15169');
    expect(readout.textContent).toContain(example.score);
    fireEvent.keyDown(inspect, { key: 'Escape' });
    expect(readout.hidden).toBe(true);
  });

  it('closes an open inspection when a lookup replaces the current IP', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(response(fixture('8.8.8.8')))
        .mockResolvedValueOnce(response(fixture('1.1.1.1'))),
    );
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: 'Inspect IP' }));
    expect(screen.getByRole('region', { name: 'IP inspection' })).toBeTruthy();
    fireEvent.change(screen.getByLabelText('IPv4 address'), { target: { value: '1.1.1.1' } });
    fireEvent.click(screen.getByRole('button', { name: /look up/i }));

    await screen.findByRole('heading', { level: 1, name: '1.1.1.1' });
    expect(screen.getByRole('button', { name: 'Inspect IP' }).getAttribute('aria-expanded')).toBe(
      'false',
    );
    expect(screen.queryByRole('region', { name: 'IP inspection' })).toBeNull();
  });

  it('compares browser rechecks against a saved baseline and distinguishes an unchanged IP', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response(fixture('8.8.8.8')))
      .mockResolvedValueOnce(response(fixture('8.8.8.8')))
      .mockResolvedValueOnce(response(fixture('1.1.1.1')));
    vi.stubGlobal('fetch', fetch);
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: 'Compare VPN' }));
    expect(screen.getByText(/Baseline saved/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Recheck' }));
    expect(await screen.findByText('Public IPv4 stayed the same.')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Recheck' }));
    expect(await screen.findByText('Public IPv4 changed.')).toBeTruthy();
    expect(screen.getByText(/this exit may be missing/)).toBeTruthy();
    expect(screen.getByRole('row', { name: 'Public IPv4 8.8.8.8 1.1.1.1' })).toBeTruthy();
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      '/v1/connection',
      '/v1/connection',
      '/v1/connection',
    ]);

    fireEvent.click(screen.getByRole('button', { name: 'Clear baseline' }));
    expect(screen.queryByRole('table', { name: 'Baseline and current connection' })).toBeNull();
  });

  it('links to DB-IP when the current lookup uses its City Lite release', async () => {
    const data = fixture();
    data.lookup.selected_sources.geolocation = {
      provider: 'dbip_city_lite',
      source_file: 'dbip-city-lite-2026-11.csv.gz',
      snapshot_at: '2026-11-01T00:00:00Z',
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(data)));
    render(<App />);
    const attribution = await screen.findByRole('link', { name: 'IP Geolocation by DB-IP' });
    expect(attribution.getAttribute('href')).toBe('https://db-ip.com');
    fireEvent.click(screen.getByRole('button', { name: 'Details' }));
    expect(screen.getByText('DB-IP City Lite · 1 Nov 2026')).toBeTruthy();
    expect(screen.queryByText('IP2Location LITE')).toBeNull();
  });
  it('focuses lookup after the keyboard shortcut leaves Sources', async () => {
    window.location.hash = '#sources';
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(fixture())));
    render(<App />);
    expect(screen.getByRole('heading', { name: 'Sources & freshness' })).toBeTruthy();
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });
    const input = await screen.findByLabelText('IPv4 address');
    await waitFor(() => expect(document.activeElement).toBe(input));
  });
  it('shows residential-proxy uncertainty in legacy Details', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(fixture())));
    render(<App />);
    await screen.findByText('8.8.8.8');
    fireEvent.click(screen.getByRole('button', { name: 'Details' }));
    expect(screen.getByText('Residential proxy: Unknown.')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Streaming policy' })).toBeNull();
  });
  it('does not restore an automatic result after an invalid manual submit', async () => {
    let finishAuto: (value: Response) => void = () => {};
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(
        () =>
          new Promise<Response>((resolve) => {
            finishAuto = resolve;
          }),
      ),
    );
    render(<App />);
    fireEvent.change(screen.getByLabelText('IPv4 address'), { target: { value: '999.1.1.1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Look up' }));
    await act(async () => {
      finishAuto(response(fixture()));
    });
    expect(screen.queryByText('Allow playback')).toBeNull();
    expect(screen.queryByText('8.8.8.8')).toBeNull();
    expect(screen.getByText('Ready to check')).toBeTruthy();
  });
  it('automatically checks the connection and initially closes technical views', async () => {
    const data = fixture();
    const row = { ...data.lookup.results[0], prefix: '8.8.8.0/24' };
    data.lookup.results = [
      { ...row, origin_group: '15169' },
      { ...row, origin_group: '15169,36040' },
    ];
    const fetch = vi.fn().mockResolvedValue(response(data));
    vi.stubGlobal('fetch', fetch);
    render(<App />);
    expect(await screen.findByText('8.8.8.8')).toBeTruthy();
    expect((screen.getByLabelText('IPv4 address') as HTMLInputElement).value).toBe('8.8.8.8');
    expect(fetch.mock.calls[0][0]).toBe('/v1/connection');
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Your connection')).toBeTruthy();
    expect(screen.getByText('IP location')).toBeTruthy();
    expect(screen.getByText('Tokyo, Japan')).toBeTruthy();
    expect(screen.getByText('Origin groups')).toBeTruthy();
    expect(screen.getByText('15169 · 15169,36040')).toBeTruthy();
    expect(screen.queryByText('Demo streaming policy')).toBeNull();
    expect(screen.getByRole('heading', { name: 'No evidence match' })).toBeTruthy();
    expect(screen.getAllByText('No match')).toHaveLength(3);
    expect(screen.getByText('The checked sources have limited coverage.')).toBeTruthy();
    expect(screen.queryByRole('region', { name: 'Details' })).toBeNull();
    expect(screen.queryByLabelText(/Lookup JSON/)).toBeNull();
  });
  it('keeps manual search available when localhost discovery fails', async () => {
    localStorage.setItem('vpnlens:ipify-consent', 'disabled');
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response({ detail: 'public_ipv4_unavailable' }, 409))
      .mockResolvedValueOnce(response(fixture('103.108.230.50', true)));
    vi.stubGlobal('fetch', fetch);
    render(<App />);
    expect(await screen.findByText('Detect your public IPv4')).toBeTruthy();
    expect(fetch.mock.calls.map(([url]) => url)).toEqual(['/v1/connection']);
    expect(screen.queryByText('Allow playback')).toBeNull();
    fireEvent.change(screen.getByLabelText('IPv4 address'), {
      target: { value: '103.108.230.50' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Look up' }));
    expect(await screen.findByRole('heading', { name: 'VPN association' })).toBeTruthy();
    expect(screen.getByText('Manual lookup')).toBeTruthy();
    expect(fetch.mock.calls[1][0]).toBe('/v1/access-decision/103.108.230.50');
  });
  it('detects the public IPv4 by default and respects a saved opt-out', async () => {
    const external = 'https://api.ipify.org?format=json';
    let ip = '1.1.1.1';
    const fetch = vi.fn(async (url: string) => {
      if (url === '/v1/connection') return response({ detail: 'public_ipv4_unavailable' }, 409);
      if (url === external) return response({ ip });
      if (url === `/v1/access-decision/${ip}`) return response(fixture(ip));
      throw new Error('Unexpected request');
    });
    vi.stubGlobal('fetch', fetch);
    const first = render(<App />);
    await screen.findByText('1.1.1.1');
    expect((screen.getByLabelText('IPv4 address') as HTMLInputElement).value).toBe('1.1.1.1');
    first.unmount();
    ip = '8.8.8.8';
    const second = render(<App />);
    await screen.findByText('8.8.8.8');
    expect((screen.getByLabelText('IPv4 address') as HTMLInputElement).value).toBe('8.8.8.8');
    ip = '9.9.9.9';
    fireEvent.click(screen.getByRole('button', { name: 'Recheck' }));
    await screen.findByText('9.9.9.9');
    expect((screen.getByLabelText('IPv4 address') as HTMLInputElement).value).toBe('9.9.9.9');
    fireEvent.click(screen.getByRole('button', { name: 'JSON' }));
    expect(screen.getByText('/v1/access-decision/9.9.9.9')).toBeTruthy();
    fireEvent.click(screen.getByText('About'));
    fireEvent.click(screen.getByRole('button', { name: 'Disable automatic detection' }));
    await screen.findByRole('button', { name: 'Enable automatic detection' });
    second.unmount();
    render(<App />);
    await screen.findByRole('button', { name: 'Enable automatic detection' });
    expect(localStorage.getItem('vpnlens:ipify-consent')).toBe('disabled');
    expect(fetch.mock.calls.filter(([url]) => url === external)).toHaveLength(3);
  });
  it('retries local IPv4 discovery after the provider fails', async () => {
    localStorage.setItem('vpnlens:ipify-consent', 'enabled');
    const unavailable = () => response({ detail: 'public_ipv4_unavailable' }, 409);
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(unavailable())
        .mockRejectedValueOnce(new Error('Provider unavailable'))
        .mockResolvedValueOnce(unavailable())
        .mockResolvedValueOnce(response({ ip: '1.1.1.1' }))
        .mockResolvedValueOnce(response(fixture('1.1.1.1'))),
    );
    render(<App />);
    const retry = await screen.findByRole('button', { name: 'Retry' });
    expect(screen.queryByText('Allow playback')).toBeNull();
    fireEvent.click(retry);
    await screen.findByText('1.1.1.1');
    expect((screen.getByLabelText('IPv4 address') as HTMLInputElement).value).toBe('1.1.1.1');
  });
  it('never lets a late automatic result replace a newer manual result', async () => {
    let finishAuto: (value: Response) => void = () => {};
    const fetch = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            finishAuto = resolve;
          }),
      )
      .mockResolvedValueOnce(response(fixture('103.108.230.50', true)));
    vi.stubGlobal('fetch', fetch);
    render(<App />);
    fireEvent.change(screen.getByLabelText('IPv4 address'), {
      target: { value: '103.108.230.50' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Look up' }));
    expect(await screen.findByText('103.108.230.50')).toBeTruthy();
    await act(async () => {
      finishAuto(response(fixture()));
    });
    expect(screen.queryByText('8.8.8.8')).toBeNull();
    expect(screen.getByRole('heading', { name: 'VPN association' })).toBeTruthy();
  });
  it('shows and copies lookup JSON without playback policy fields', async () => {
    const data = { ...fixture(), extra_fixture_field: { untouched: true } };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(data)));
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    render(<App />);
    await screen.findByText('8.8.8.8');
    fireEvent.click(screen.getByRole('button', { name: 'JSON' }));
    expect(JSON.parse(screen.getByLabelText(/Lookup JSON/).textContent!)).toEqual(data.lookup);
    fireEvent.click(screen.getByRole('button', { name: 'Copy JSON response' }));
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(JSON.stringify(data.lookup, null, 2)),
    );
    expect(screen.getByText('/v1/connection')).toBeTruthy();
  });
  it('returns from manual lookup to the latest visitor connection on Recheck', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response(fixture()))
      .mockResolvedValueOnce(response(fixture('103.108.230.50', true)))
      .mockResolvedValueOnce(response(fixture('1.1.1.1')));
    vi.stubGlobal('fetch', fetch);
    render(<App />);
    await screen.findByText('8.8.8.8');
    fireEvent.change(screen.getByLabelText('IPv4 address'), {
      target: { value: '103.108.230.50' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Look up' }));
    await screen.findByRole('heading', { name: 'VPN association' });
    fireEvent.click(screen.getByRole('button', { name: 'Recheck' }));
    expect(await screen.findByText('1.1.1.1')).toBeTruthy();
    expect((screen.getByLabelText('IPv4 address') as HTMLInputElement).value).toBe('1.1.1.1');
    expect(screen.getByText('Your connection')).toBeTruthy();
    expect(fetch.mock.calls[2][0]).toBe('/v1/connection');
  });
  it.each([
    ['999.1.1.1', 'Enter a valid IPv4 address, such as 8.8.8.8.'],
    ['2001:db8::1', 'IPv6 is not supported yet.'],
  ])('validates %s without another request', async (ip, message) => {
    const fetch = vi.fn().mockResolvedValue(response(fixture()));
    vi.stubGlobal('fetch', fetch);
    render(<App />);
    await screen.findByText('8.8.8.8');
    fireEvent.change(screen.getByLabelText('IPv4 address'), { target: { value: ip } });
    fireEvent.click(screen.getByRole('button', { name: 'Look up' }));
    expect(screen.getByText(message)).toBeTruthy();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('Allow playback')).toBeNull();
    expect(screen.queryByText('8.8.8.8')).toBeNull();
  });
  it('clears an old result on failure and retries the failed request', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response(fixture()))
      .mockResolvedValueOnce(response({}, 503))
      .mockResolvedValueOnce(response(fixture('1.1.1.1')));
    vi.stubGlobal('fetch', fetch);
    render(<App />);
    await screen.findByText('8.8.8.8');
    fireEvent.change(screen.getByLabelText('IPv4 address'), { target: { value: '1.1.1.1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Look up' }));
    expect(await screen.findByText('Check unavailable')).toBeTruthy();
    expect(screen.queryByText('8.8.8.8')).toBeNull();
    fireEvent.change(screen.getByLabelText('IPv4 address'), { target: { value: '9.9.9.9' } });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('1.1.1.1')).toBeTruthy();
    expect(fetch.mock.calls[2][0]).toBe('/v1/access-decision/1.1.1.1');
  });
  it('keeps degraded uncertainty visible instead of calling an unknown IP safe', async () => {
    const data = fixture();
    data.decision.scheduled_source_health = 'degraded';
    data.decision.reason_codes = ['insufficient_recent_evidence'];
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(data)));
    render(<App />);
    await screen.findByText('8.8.8.8');
    expect(screen.getByText('Some sources are missing or stale.')).toBeTruthy();
    expect(screen.queryByText(/verified non-VPN|safe connection/i)).toBeNull();
  });
});
