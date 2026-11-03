import type { Security } from '../types';
import { formatDate } from '../presentation';
import { UiIcon } from '../icons';

export function ExtendedEvidence({ security }: { security: Security }) {
  if (security.vpn_assessment === undefined) return null;
  return (
    <section className="evidence-panel panel" aria-labelledby="extended-evidence-title">
      <div className="section-heading">
        <h2 id="extended-evidence-title">Additional evidence</h2>
      </div>
      {security.vpn_assessment === 'network_only' && (
        <p>Possible VPN-network association. No direct VPN endpoint evidence.</p>
      )}
      <p>Proxy exit association: {security.proxy_status === 'listed' ? 'Listed' : 'Unknown'}</p>
      <p>Residential proxy: Unknown. Qualifying evidence is not available.</p>
      <ul className="evidence-list">
        {(security.additional_evidence ?? []).map((item) => (
          <li key={`${item.source_id}-${item.record_key}`}>
            <div>
              <strong>{item.provider ?? item.source_id}</strong>
              {item.stale && <span className="status-tag warning">Stale match</span>}
            </div>
            <p>
              <code>{item.network}</code> ·{' '}
              <span>
                {item.basis === 'network_inference'
                  ? 'Network inference'
                  : 'Dated service observation'}
              </span>
            </p>
            <p>
              Method: {item.method} · Role: {item.role}
            </p>
            {item.observed_at && (
              <p>
                Observed{' '}
                <time dateTime={item.observed_at} title={item.observed_at}>
                  {formatDate(item.observed_at)}
                </time>
              </p>
            )}
            {item.expires_at && (
              <p>
                Expires{' '}
                <time dateTime={item.expires_at} title={item.expires_at}>
                  {formatDate(item.expires_at)}
                </time>
              </p>
            )}
            {item.operator_attested && (
              <p>
                {item.method === 'browser_import'
                  ? 'Operator-attested browser import; not recorder-verified.'
                  : 'Operator-attested provider label.'}
              </p>
            )}
            {item.connection_type_claim && item.connection_type_claim !== 'unknown' && (
              <p>Reported pool: {item.connection_type_claim} (unverified)</p>
            )}
            {item.source_url.startsWith('https://') && (
              <a href={item.source_url} target="_blank" rel="noreferrer">
                Open source record <UiIcon name="arrow" size={14} />
              </a>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
