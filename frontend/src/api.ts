import type { DecisionResponse, Health, LookupResponse, SourceResponse } from './types';

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status = 0, code?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

export function validIPv4(value: string): boolean {
  const parts = value.trim().split('.');
  return (
    parts.length === 4 &&
    parts.every((part) => /^(0|[1-9]\d{0,2})$/.test(part) && Number(part) <= 255)
  );
}

const nullableText = (value: unknown): boolean => value === null || typeof value === 'string';
const validConnectionClaim = (value: unknown): boolean =>
  value === undefined ||
  value === null ||
  ['residential', 'mobile', 'datacenter', 'unknown'].includes(value as string);

export function validExtendedSecurity(value: unknown): boolean {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const security = value as Record<string, unknown>;
  const fields = [
    'vpn_assessment',
    'proxy_status',
    'residential_proxy_status',
    'residential_proxy_reason',
    'additional_evidence',
  ];
  if (!fields.some((field) => Object.hasOwn(security, field))) return true;
  return (
    ['direct_association', 'network_only', 'unknown'].includes(security.vpn_assessment as string) &&
    ['listed', 'unknown'].includes(security.proxy_status as string) &&
    security.residential_proxy_status === 'unknown' &&
    typeof security.residential_proxy_reason === 'string' &&
    Array.isArray(security.additional_evidence) &&
    security.additional_evidence.every((value: unknown) => {
      if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
      const item = value as Record<string, unknown>;
      return (
        [
          'source_id',
          'family',
          'record_key',
          'network',
          'method',
          'source_url',
          'checked_at',
          'fetched_at',
        ].every((field) => typeof item[field] === 'string') &&
        ['provider', 'hostname', 'observed_at', 'expires_at'].every((field) =>
          nullableText(item[field]),
        ) &&
        ['provider_list', 'provider_dns', 'network_inference', 'exit_observation'].includes(
          item.basis as string,
        ) &&
        ['server', 'exit', 'unknown'].includes(item.role as string) &&
        ['vpn', 'proxy'].includes(item.service_category as string) &&
        (item.review_state === null || item.review_state === 'approved') &&
        typeof item.stale === 'boolean' &&
        (item.operator_attested === undefined || typeof item.operator_attested === 'boolean') &&
        validConnectionClaim(item.connection_type_claim) &&
        (item.basis !== 'exit_observation' ||
          (typeof item.observed_at === 'string' &&
            typeof item.expires_at === 'string' &&
            item.review_state === 'approved'))
      );
    })
  );
}

export function isLookupResponse(value: unknown): value is LookupResponse {
  if (!value || typeof value !== 'object') return false;
  const data = value as Record<string, any>;
  const snapshot = (v: any): boolean =>
    Boolean(v && typeof v.source_file === 'string' && typeof v.snapshot_at === 'string');
  const optionalText = (v: unknown) => v === null || typeof v === 'string';
  const count = (v: unknown) => typeof v === 'number' && Number.isInteger(v) && v >= 0;
  return (
    typeof data.ip === 'string' &&
    validIPv4(data.ip) &&
    snapshot(data.selected_sources?.routing) &&
    snapshot(data.selected_sources?.organization) &&
    Array.isArray(data.results) &&
    data.results.length > 0 &&
    data.results.every(
      (row: any) =>
        row &&
        row.ip === data.ip &&
        [row.country_code, row.city_name, row.prefix, row.origin_group, row.snapshot_at].every(
          optionalText,
        ) &&
        Array.isArray(row.asn_owners) &&
        row.asn_owners.every(
          (owner: any) =>
            owner &&
            typeof owner.asn === 'string' &&
            [
              owner.org_name,
              owner.org_country_code,
              owner.org_snapshot_at,
              owner.org_source_file,
            ].every(optionalText),
        ) &&
        row.security &&
        validExtendedSecurity(row.security) &&
        ['listed', 'unknown'].includes(row.security.vpn_status) &&
        ['listed', 'unknown'].includes(row.security.tor_status) &&
        [
          row.security.active_source_count,
          row.security.recently_checked_source_count,
          row.security.stale_after_hours,
        ].every(count) &&
        Array.isArray(row.security.evidence) &&
        row.security.evidence.every(
          (item: any) =>
            item &&
            typeof item.source_id === 'string' &&
            ['vpn_server', 'tor_exit'].includes(item.indicator_type) &&
            typeof item.stale === 'boolean' &&
            typeof item.source_url === 'string' &&
            typeof item.checked_at === 'string' &&
            ['record_key', 'method'].every(
              (field) => item[field] === undefined || typeof item[field] === 'string',
            ) &&
            (item.role === undefined || ['server', 'exit', 'unknown'].includes(item.role)) &&
            ['observed_at', 'expires_at'].every(
              (field) => item[field] === undefined || nullableText(item[field]),
            ) &&
            (item.operator_attested === undefined || typeof item.operator_attested === 'boolean') &&
            validConnectionClaim(item.connection_type_claim),
        ),
    )
  );
}

async function getJson(path: string, external?: AbortSignal, connection = false): Promise<unknown> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort('timeout'), 15000);
  const cancel = () => controller.abort();
  if (external?.aborted) cancel();
  external?.addEventListener('abort', cancel, { once: true });
  try {
    const response = await fetch(path, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });
    if (!response.ok) {
      if (connection && response.status === 409)
        throw new ApiError('Your public IPv4 is unavailable here', 409, 'public_ipv4_unavailable');
      if (connection && response.status === 422)
        throw new ApiError('IPv6 is not supported yet.', 422, 'ipv6_not_supported');
      if (response.status === 429) {
        const retryAfter = Number(response.headers.get('Retry-After'));
        const wait =
          Number.isInteger(retryAfter) && retryAfter > 0 ? ` in ${retryAfter}s` : ' shortly';
        throw new ApiError(`Too many requests. Try again${wait}.`, 429, 'rate_limit_exceeded');
      }
      if (response.status === 503)
        throw new ApiError('The local API is temporarily unavailable. Try again shortly.', 503);
      if (response.status === 422) throw new ApiError('Enter a valid IPv4 host address.', 422);
      throw new ApiError(
        `The request could not be completed (HTTP ${response.status}).`,
        response.status,
      );
    }
    try {
      return await response.json();
    } catch {
      throw new ApiError('The API returned an unreadable response. Try again.', 502);
    }
  } catch (error) {
    if (external?.aborted) throw new DOMException('Request cancelled', 'AbortError');
    if (error instanceof ApiError) throw error;
    if (controller.signal.aborted) throw new ApiError('The lookup timed out. Try again.');
    throw new ApiError('Cannot reach the local API. Check that the backend is running.');
  } finally {
    window.clearTimeout(timer);
    external?.removeEventListener('abort', cancel);
  }
}

export function isDecisionResponse(value: unknown): value is DecisionResponse {
  if (!value || typeof value !== 'object') return false;
  const data = value as Record<string, unknown>;
  if (!isLookupResponse(data.lookup) || !data.decision || typeof data.decision !== 'object')
    return false;
  const decision = data.decision as Record<string, unknown>;
  if (
    decision.policy_id !== 'streaming-access-v1' ||
    !['ready', 'degraded'].includes(decision.scheduled_source_health as string) ||
    typeof decision.evaluated_at !== 'string' ||
    !/(Z|[+-]\d{2}:\d{2})$/.test(decision.evaluated_at) ||
    !Number.isFinite(Date.parse(decision.evaluated_at)) ||
    !Array.isArray(decision.reason_codes) ||
    !decision.reason_codes.length
  )
    return false;
  const reasons = decision.reason_codes;
  if (new Set(reasons).size !== reasons.length) return false;
  if (decision.action === 'allow')
    return (
      reasons.length === 1 &&
      reasons[0] ===
        (decision.scheduled_source_health === 'ready'
          ? 'no_recent_blocking_evidence'
          : 'insufficient_recent_evidence')
    );
  if (decision.action !== 'block') return false;
  const security = data.lookup.results[0].security;
  const supported = [
    ...(security.vpn_status === 'listed' ? ['recent_vpn_evidence'] : []),
    ...(security.tor_status === 'listed' ? ['recent_tor_evidence'] : []),
    ...(security.proxy_status === 'listed' ? ['recent_proxy_evidence'] : []),
  ];
  return reasons.every((reason) => supported.includes(reason));
}

export async function checkConnection(signal?: AbortSignal): Promise<DecisionResponse> {
  const data = await getJson('/v1/connection', signal, true);
  if (!isDecisionResponse(data))
    throw new ApiError('The API returned an unexpected result. Try again.', 502);
  return data;
}

export async function checkIP(ip: string, signal?: AbortSignal): Promise<DecisionResponse> {
  if (!validIPv4(ip)) throw new ApiError('Enter a valid IPv4 address, such as 8.8.8.8.', 422);
  const data = await getJson(`/v1/access-decision/${encodeURIComponent(ip.trim())}`, signal);
  if (!isDecisionResponse(data) || data.lookup.ip !== ip.trim())
    throw new ApiError('The API returned an unexpected result. Try again.', 502);
  return data;
}

export function isLoopbackOrigin(): boolean {
  return ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname);
}

export async function checkVisitorConnection(
  signal: AbortSignal,
  allowIpify: boolean,
  onAddress: (ip: string) => void,
): Promise<{ data: DecisionResponse; endpoint: string }> {
  try {
    const data = await checkConnection(signal);
    onAddress(data.lookup.ip);
    return { data, endpoint: '/v1/connection' };
  } catch (error) {
    if (
      !allowIpify ||
      !isLoopbackOrigin() ||
      !(error instanceof ApiError) ||
      (error.code !== 'public_ipv4_unavailable' && error.code !== 'ipv6_not_supported')
    ) {
      throw error;
    }
  }

  signal.throwIfAborted();
  let ip: string;
  try {
    const response = await fetch('https://api.ipify.org?format=json', {
      signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]),
      credentials: 'omit',
      referrerPolicy: 'no-referrer',
      redirect: 'error',
      cache: 'no-store',
    });
    if (!response.ok) throw new Error('IPv4 discovery failed');
    const address: unknown = await response.json();
    if (
      !address ||
      typeof address !== 'object' ||
      !('ip' in address) ||
      typeof address.ip !== 'string' ||
      !validIPv4(address.ip)
    ) {
      throw new Error('Invalid IPv4 discovery response');
    }
    ip = address.ip.trim();
  } catch {
    signal.throwIfAborted();
    throw new ApiError('Could not detect your public IPv4. Retry or enter it above.');
  }
  signal.throwIfAborted();
  onAddress(ip);
  return {
    data: await checkIP(ip, signal),
    endpoint: `/v1/access-decision/${ip}`,
  };
}

export async function lookupIP(ip: string, signal?: AbortSignal): Promise<LookupResponse> {
  if (!validIPv4(ip)) throw new ApiError('Enter a valid IPv4 host address.', 422);
  const data = await getJson(`/v1/lookup/${encodeURIComponent(ip.trim())}`, signal);
  if (!isLookupResponse(data))
    throw new ApiError('The API returned an unexpected result. Try again.', 502);
  return data;
}
export async function loadSources(signal?: AbortSignal): Promise<SourceResponse> {
  const data = (await getJson('/v1/sources', signal)) as SourceResponse;
  if (
    !data ||
    !Array.isArray(data.routing) ||
    !Array.isArray(data.organization) ||
    !Array.isArray(data.security) ||
    !data.geolocation
  ) {
    throw new ApiError('Source information is temporarily unavailable.', 502);
  }
  return data;
}
export async function loadHealth(signal?: AbortSignal): Promise<Health> {
  const data = (await getJson('/health/ready', signal)) as Health;
  if (!data || !['ready', 'degraded', 'not_ready'].includes(data.status))
    throw new ApiError('API health is unavailable.', 502);
  return data;
}
