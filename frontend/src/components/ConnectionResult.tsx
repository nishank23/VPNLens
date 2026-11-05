import type { DecisionResponse } from '../types';
import { countryName, summarize } from '../presentation';

export function ConnectionResult({ data }: { data: DecisionResponse }) {
  const { security, location, groups } = summarize(data.lookup);
  const originGroups = [...new Set(groups.map((row) => row.origin_group))];
  const vpn = security.vpn_status === 'listed';
  const tor = security.tor_status === 'listed';
  const proxy = security.proxy_status === 'listed';
  const browserProxyProvider = security.additional_evidence?.find(
    (item) =>
      !item.stale &&
      item.basis === 'exit_observation' &&
      item.method === 'browser_import' &&
      item.service_category === 'proxy' &&
      item.provider,
  )?.provider;
  const weak = security.vpn_assessment === 'network_only';
  const listed = vpn || tor || proxy;
  const title =
    vpn && tor
      ? 'VPN + Tor association'
      : vpn
        ? 'VPN association'
        : tor
          ? 'Tor exit listed'
          : proxy
            ? browserProxyProvider
              ? 'Browser proxy observed'
              : 'Proxy association'
            : weak
              ? 'Network match only'
              : 'No evidence match';
  const provider = security.evidence.find(
    (item) => !item.stale && item.indicator_type === 'vpn_server',
  )?.provider;
  const note =
    vpn && provider
      ? `Provider evidence: ${provider}.`
      : proxy && browserProxyProvider
        ? `Observed browser exit through ${browserProxyProvider}.`
        : listed
          ? 'Recent qualifying evidence found.'
          : weak
            ? 'A network match does not confirm a VPN exit.'
            : 'The checked sources have limited coverage.';
  const country = location.country_code ? countryName(location.country_code) : '';
  const place = [location.city_name, country].filter(Boolean).join(', ') || 'Unavailable';
  return (
    <div data-result-content>
      <div className="connection-report">
        <div className="connection-main">
          <dl className="connection-address-details">
            <div>
              <dt>IP location</dt>
              <dd>{place}</dd>
            </div>
            {originGroups.length > 0 && (
              <div>
                <dt>{originGroups.length > 1 ? 'Origin groups' : 'Origin group'}</dt>
                <dd>
                  <code>{originGroups.join(' · ')}</code>
                </dd>
              </div>
            )}
          </dl>
        </div>
        <div className="connection-finding">
          <h2 className={listed ? 'listed' : undefined}>{title}</h2>
          <p>{note}</p>
          {data.decision.scheduled_source_health === 'degraded' && (
            <p className="degraded-note">Some sources are missing or stale.</p>
          )}
        </div>
        <section className="evidence-summary" aria-label="VPN, Tor, and proxy matches">
          <dl className="connection-states">
            {(
              [
                ['VPN', vpn],
                ['Tor', tor],
                ['Proxy', proxy],
              ] as const
            ).map(([label, positive]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd className={positive ? 'listed' : undefined}>
                  {positive ? 'Listed' : 'No match'}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      </div>
    </div>
  );
}
