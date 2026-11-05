import { countryName, summarize } from '../presentation';
import type { DecisionResponse } from '../types';

export interface ConnectionSnapshot {
  data: DecisionResponse;
  method: 'site' | 'ipify';
}

function report(snapshot: ConnectionSnapshot) {
  const { security, groups, location } = summarize(snapshot.data.lookup);
  const matches = [
    security.vpn_status === 'listed' ? 'VPN' : '',
    security.tor_status === 'listed' ? 'Tor' : '',
    security.proxy_status === 'listed' ? 'Proxy' : '',
  ].filter(Boolean);
  return {
    ip: snapshot.data.lookup.ip,
    method: snapshot.method,
    location:
      [location.city_name, location.country_code && countryName(location.country_code)]
        .filter(Boolean)
        .join(', ') || 'Unavailable',
    prefix: groups[0]?.prefix || 'Unavailable',
    origins: [...new Set(groups.map((row) => row.origin_group))].join(' · ') || 'Unavailable',
    matches:
      matches.join(', ') ||
      (security.vpn_assessment === 'network_only' ? 'Network only' : 'No match'),
    hasMatch: matches.length > 0,
  };
}

export function ConnectionComparison({
  baseline,
  current,
  onClear,
}: {
  baseline: ConnectionSnapshot;
  current: ConnectionSnapshot;
  onClear: () => void;
}) {
  const before = report(baseline);
  const now = report(current);
  const hasRechecked = baseline.data !== current.data;
  const changed = before.ip !== now.ip;
  const sameMethod = before.method === now.method;
  const outcome = !sameMethod
    ? 'The checks used different IP detection methods.'
    : changed
      ? 'Public IPv4 changed.'
      : 'Public IPv4 stayed the same.';
  const next = !sameMethod
    ? 'Repeat both checks using the same page and detection settings.'
    : !changed
      ? 'If you toggled a browser VPN, check that it applies to this tab, then recheck.'
      : now.hasMatch
        ? 'The current address has matching evidence. Open Details to inspect the source.'
        : 'If your VPN is connected, this exit may be missing from the evidence feeds.';

  return (
    <section className="connection-comparison" aria-labelledby="comparison-title">
      <div className="comparison-header">
        <h3 id="comparison-title">Connection comparison</h3>
        <button className="secondary-button" type="button" onClick={onClear}>
          Clear baseline
        </button>
      </div>
      {hasRechecked ? (
        <>
          <p role="status">
            <strong>{outcome}</strong> {next}
          </p>
          <table aria-label="Baseline and current connection">
            <thead>
              <tr>
                <th scope="col">Field</th>
                <th scope="col">Baseline</th>
                <th scope="col">Current</th>
              </tr>
            </thead>
            <tbody>
              {(
                [
                  ['Public IPv4', before.ip, now.ip],
                  ['IP location', before.location, now.location],
                  ['Matched prefix', before.prefix, now.prefix],
                  ['Origin groups', before.origins, now.origins],
                  ['Evidence', before.matches, now.matches],
                ] as const
              ).map(([label, previous, value]) => (
                <tr key={label}>
                  <th scope="row">{label}</th>
                  <td>{previous}</td>
                  <td className={value !== previous ? 'comparison-changed' : undefined}>{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <p role="status">Baseline saved. Toggle your VPN, then select Recheck.</p>
      )}
    </section>
  );
}
