import type { Health, LookupResponse, SourceResponse } from './types';

export class ApiError extends Error {
  status: number;
  constructor(message: string, status = 0) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
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

async function getJson(path: string, external?: AbortSignal): Promise<unknown> {
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
