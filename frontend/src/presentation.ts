import type { LookupResponse, Owner } from './types';

export function countryName(code: string | null | undefined): string {
  if (!code) return 'Unavailable';
  try {
    return new Intl.DisplayNames(['en'], { type: 'region' }).of(code) || code;
  } catch {
    return code;
  }
}
export function formatDate(value: string | null | undefined): string {
  if (!value) return 'Unavailable';
  const date = new Date(value);
  if (!Number.isFinite(date.valueOf())) return 'Unavailable';
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'Africa/Maputo',
  }).format(date);
}
export function formatCount(value: number): string {
  return new Intl.NumberFormat('en').format(value);
}
export function summarize(data: LookupResponse) {
  const rows = data.results;
  const location = rows.find((row) => row.country_code || row.city_name) ?? rows[0];
  const groups = rows.filter((row) => row.prefix && row.origin_group);
  const owners = new Map<string, Owner>();
  for (const row of groups)
    for (const owner of row.asn_owners) if (!owners.has(owner.asn)) owners.set(owner.asn, owner);
  const security = rows[0].security;
  const recent = security.evidence.filter((evidence) => !evidence.stale);
  const finding =
    security.vpn_status === 'listed' && security.tor_status === 'listed'
      ? 'VPN and Tor associations found'
      : security.vpn_status === 'listed'
        ? 'VPN infrastructure association found'
        : security.tor_status === 'listed'
          ? 'Tor exit association found'
          : security.proxy_status === 'listed'
            ? 'Proxy exit association found'
            : security.vpn_assessment === 'network_only'
              ? 'Possible VPN-network association'
              : 'No recent VPN or Tor list match';
  return { location, groups, owners: [...owners.values()], security, recent, finding };
}
