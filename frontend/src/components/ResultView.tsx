import type { LookupResponse } from '../types';
import { countryName, formatDate, summarize } from '../presentation';
import { UiIcon } from '../icons';
import { ExtendedEvidence } from './ExtendedEvidence';

export function EmptyResult({ loading }: { loading: boolean }) {
  return (
    <section className="result-placeholder panel" aria-busy={loading}>
      <div className="section-heading">
        <h2>Address overview</h2>
        <UiIcon name="layers" />
      </div>
      <p className="placeholder-title">
        {loading ? 'Following the evidence…' : 'An address is a starting point.'}
      </p>
      <p>
        {loading
          ? 'Checking location, routing, ownership, and public lists.'
          : 'Search an IPv4 address to see what the available sources support.'}
      </p>
      {loading && (
        <div className="loading-lines" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      )}
      <div className="empty-source-list">
        <span>Geolocation</span>
        <span>Routing prefix</span>
        <span>ASN ownership</span>
        <span>VPN / Tor evidence</span>
      </div>
    </section>
  );
}

export function ResultView({ data }: { data: LookupResponse }) {
  const summary = summarize(data);
  const { security, location, groups, owners } = summary;
  return (
    <div className="readable-result" data-result-content>
      <section className="overview-panel panel" aria-labelledby="overview-title">
        <div className="section-heading">
          <h2 id="overview-title">Address overview</h2>
          <span className="small muted">IPv4</span>
        </div>
        <div className="address-line">
          <span className="address identifier">{data.ip}</span>
          <span className="country-code" title={countryName(location.country_code)}>
            {location.country_code || '—'}
          </span>
        </div>
        <p className="finding">{summary.finding}</p>
        <div className="privacy-results">
          <div className="privacy-result">
            <span className="field-label">VPN association</span>
            <span className={`verdict ${security.vpn_status === 'listed' ? 'is-listed' : ''}`}>
              <span className="verdict-dot" />
              {security.vpn_status === 'listed' ? 'Listed' : 'Unknown'}
            </span>
          </div>
          <div className="privacy-result">
            <span className="field-label">Tor exit association</span>
            <span className={`verdict ${security.tor_status === 'listed' ? 'is-listed' : ''}`}>
              <span className="verdict-dot" />
              {security.tor_status === 'listed' ? 'Listed' : 'Unknown'}
            </span>
          </div>
        </div>
        <p className="evidence-caveat">
          <UiIcon name="info" size={15} />
          Unknown is incomplete evidence, not a non-VPN verdict.
        </p>
        <div className="location-row">
          <span className="field-label">Estimated location</span>
          <strong>
            {location.city_name ? `${location.city_name}, ` : ''}
            {countryName(location.country_code)}
          </strong>
        </div>
        <div className="location-row">
          <span className="field-label">Recently checked sources</span>
          <span className="num">
            {security.recently_checked_source_count} / {security.active_source_count}
          </span>
        </div>
      </section>

      <section className="routing-panel panel" aria-labelledby="routing-title">
        <div className="section-heading">
          <h2 id="routing-title">Network ownership</h2>
          <span className="small muted">
            {groups.length} origin {groups.length === 1 ? 'group' : 'groups'}
          </span>
        </div>
        {groups.length ? (
          groups.map((row) => (
            <div className="origin-group" key={`${row.prefix}-${row.origin_group}`}>
              <div className="prefix-line">
                <code>{row.prefix}</code>
                <span className="small muted">Longest match</span>
              </div>
              <p className="origin-label">
                Origin group <code>{row.origin_group}</code>
              </p>
              <div className="owners-list">
                {row.asn_owners.map((owner) => (
                  <div className="owner-row" key={owner.asn}>
                    <span className="asn identifier">AS{owner.asn}</span>
                    <span className="owner-name">
                      {owner.org_name || 'Organization unavailable'}
                      <span className="owner-country">
                        {owner.org_country_code
                          ? `${countryName(owner.org_country_code)} · organization country`
                          : 'Organization country unavailable'}
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))
        ) : (
          <p className="empty-line">
            No routing prefix matched this address in the selected snapshot.
          </p>
        )}
        <div className="panel-foot">
          <span>
            {owners.length} unique {owners.length === 1 ? 'ASN' : 'ASNs'}
          </span>
          <span>Routing · {formatDate(data.selected_sources.routing.snapshot_at)}</span>
        </div>
      </section>

      <section className="evidence-panel panel" aria-labelledby="evidence-title">
        <div className="section-heading">
          <h2 id="evidence-title">Supporting evidence</h2>
          <span className="small muted">
            {security.evidence.length} {security.evidence.length === 1 ? 'match' : 'matches'}
          </span>
        </div>
        {security.evidence.length ? (
          <ul className="evidence-list">
            {security.evidence.map((item) => (
              <li key={`${item.source_id}-${item.record_key ?? item.indicator_type}`}>
                <div>
                  <strong>{item.provider ?? item.source_id}</strong>
                  <span className={`status-tag ${item.stale ? 'warning' : 'listed'}`}>
                    {item.stale ? 'Stale match' : 'Listed'}
                  </span>
                </div>
                <p>
                  {item.indicator_type === 'vpn_server'
                    ? 'VPN server association'
                    : 'Tor exit address'}{' '}
                  · Checked {formatDate(item.checked_at)}
                </p>
                {(item.method || item.role) && (
                  <p>
                    Method: {item.method ?? 'unknown'} · Role: {item.role ?? 'unknown'}
                  </p>
                )}
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
        ) : (
          <p className="empty-line">
            No exact IP match in the recently checked public lists. VPN or Tor use remains unknown.
          </p>
        )}
        {security.evidence.some((item) => item.stale) && (
          <p className="notice">
            Stale matches remain visible. They do not establish a current listed status.
          </p>
        )}
      </section>

      <ExtendedEvidence security={security} />

      <section className="source-trace" aria-labelledby="trace-title">
        <h2 id="trace-title">Every finding has a source.</h2>
        <div className="trace-grid" aria-label="Independent source layers">
          <div>
            <span className="trace-dot" />
            <strong>Location</strong>
            <span>IP2Location LITE</span>
          </div>
          <div>
            <span className="trace-dot" />
            <strong>Routing</strong>
            <span>{formatDate(data.selected_sources.routing.snapshot_at)}</span>
          </div>
          <div>
            <span className="trace-dot" />
            <strong>Ownership</strong>
            <span>{formatDate(data.selected_sources.organization.snapshot_at)}</span>
          </div>
          <div>
            <span className="trace-dot" />
            <strong>Public lists</strong>
            <span className="num">{security.recently_checked_source_count} checked</span>
          </div>
        </div>
        <p>
          Independent observations, brought together. Source check time is not the publisher’s
          observation date.
        </p>
      </section>
    </div>
  );
}
