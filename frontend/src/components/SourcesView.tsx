import type { SourceResponse } from '../types';
import { formatCount, formatDate } from '../presentation';
import { UiIcon } from '../icons';

export function SourcesView({
  data,
  error,
  loading,
  refresh,
}: {
  data: SourceResponse | null;
  error: string | null;
  loading: boolean;
  refresh: () => void;
}) {
  const expectedSourceCount = data
    ? new Set([
        ...data.security.map((source) => source.source_id),
        ...(data.security_expected_source_ids ?? []),
      ]).size
    : 0;
  return (
    <div className="sources-view">
      <header className="page-title">
        <div>
          <h1>Sources & freshness</h1>
          <p>The records behind an address, with their limits in view.</p>
        </div>
        <button className="secondary-button" onClick={refresh} disabled={loading}>
          <UiIcon name="refresh" />
          <span>{loading ? 'Checking…' : 'Check sources'}</span>
        </button>
      </header>
      {error && (
        <div className="error-notice" role="alert">
          <UiIcon name="info" />
          <div>
            <strong>Source information unavailable</strong>
            <p>{error}</p>
          </div>
          <button onClick={refresh}>Retry</button>
        </div>
      )}
      {!data && (
        <section className="panel source-loading">
          <h2>Source records</h2>
          <p>
            {loading
              ? 'Reading loaded snapshots and check times…'
              : 'Source records are unavailable until the API responds.'}
          </p>
        </section>
      )}
      {data && (
        <>
          <div className="source-summary">
            <div>
              <span className="field-label">Geolocation</span>
              <strong>{data.geolocation.available ? 'Loaded' : 'Unavailable'}</strong>
            </div>
            <div>
              <span className="field-label">Routing snapshots</span>
              <strong className="num">{data.routing.length}</strong>
            </div>
            <div>
              <span className="field-label">Ownership snapshots</span>
              <strong className="num">{data.organization.length}</strong>
            </div>
            <div>
              <span className="field-label">Fresh public feeds</span>
              <strong className="num">
                {data.security.filter((source) => !source.stale).length} / {expectedSourceCount}
              </strong>
            </div>
          </div>
          <section className="panel dataset-panel">
            <div className="section-heading">
              <h2>Snapshot records</h2>
              <span className="small muted">Dates reflect each source</span>
            </div>
            <div className="dataset-row">
              <div>
                <strong>
                  {data.geolocation.provider === 'dbip_city_lite' ? (
                    <a href="https://db-ip.com">IP Geolocation by DB-IP</a>
                  ) : data.geolocation.available ? (
                    'IP2Location LITE'
                  ) : (
                    'Geolocation'
                  )}
                </strong>
                <span>Estimated IP geolocation</span>
              </div>
              <div>
                <strong>{data.geolocation.available ? 'Available' : 'Unavailable'}</strong>
                <span>
                  {data.geolocation.snapshot_at
                    ? formatDate(data.geolocation.snapshot_at)
                    : 'Publisher date unavailable'}
                </span>
              </div>
            </div>
            {data.routing.map((source) => (
              <div className="dataset-row" key={source.source_file}>
                <div>
                  <strong>CAIDA RouteViews</strong>
                  <code>{source.source_file}</code>
                </div>
                <div>
                  <strong>{formatDate(source.snapshot_at)}</strong>
                  <span>Routing snapshot</span>
                </div>
              </div>
            ))}
            {data.organization.map((source) => (
              <div className="dataset-row" key={source.source_file}>
                <div>
                  <strong>CAIDA AS Organizations</strong>
                  <code>{source.source_file}</code>
                </div>
                <div>
                  <strong>{formatDate(source.snapshot_at)}</strong>
                  <span>Ownership snapshot</span>
                </div>
              </div>
            ))}
          </section>
          <section className="panel feed-panel">
            <div className="section-heading">
              <h2>Public evidence feeds</h2>
              <span className="small muted">
                Check-age threshold: {data.security_stale_after_hours} hours
              </span>
            </div>
            <div
              className="table-scroll"
              tabIndex={0}
              aria-label="Public evidence feed records"
              data-lenis-prevent
            >
              <table>
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Evidence</th>
                    <th>Check date</th>
                    <th className="num">IPv4 records</th>
                    <th>Freshness</th>
                  </tr>
                </thead>
                <tbody>
                  {data.security.map((feed) => (
                    <tr key={feed.source_id}>
                      <td>
                        <strong>{feed.provider ?? feed.source_id}</strong>
                      </td>
                      <td>
                        {feed.indicator_type === 'tor_exit'
                          ? 'Tor exits'
                          : feed.indicator_type === 'network_inference'
                            ? 'VPN networks'
                            : 'VPN servers'}
                      </td>
                      <td>{formatDate(feed.checked_at)}</td>
                      <td className="num">{formatCount(feed.ipv4_count)}</td>
                      <td>
                        <span className={`status-tag ${feed.stale ? 'warning' : 'neutral'}`}>
                          {feed.stale ? 'Stale' : 'Recently checked'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.security.length === 0 && (
                <p className="empty-line">No active evidence feeds are loaded.</p>
              )}
            </div>
            <p className="table-note">
              Counts describe records and networks, not unique addresses. Records can overlap
              between sources. A recent check does not guarantee current upstream observations.
            </p>
          </section>
          <div className="source-bottom-grid">
            <section className="panel refresh-panel">
              <div className="section-heading">
                <h2>Refresh activity</h2>
                <UiIcon name="refresh" />
              </div>
              {Object.entries(data.refresh || {}).map(([name, record]) => (
                <div className="refresh-row" key={name}>
                  <div>
                    <strong>
                      {(
                        {
                          routing: 'Routing',
                          organization: 'Ownership',
                          geolocation: 'Geolocation',
                          evidence: 'Public evidence',
                        } as Record<string, string>
                      )[name] || name}
                    </strong>
                    <span>
                      {record.last_success_at
                        ? `Last successful check ${formatDate(record.last_success_at)}`
                        : 'No successful refresh recorded'}
                    </span>
                    {record.next_download_on && (
                      <span>Next eligible download {formatDate(record.next_download_on)}</span>
                    )}
                  </div>
                  <span
                    className={`status-tag ${record.status === 'failed' || record.manual_update_required ? 'warning' : 'neutral'}`}
                  >
                    {record.status.replaceAll('_', ' ')}
                  </span>
                </div>
              ))}
              {!Object.keys(data.refresh || {}).length && (
                <p className="empty-line">No refresh history is available for this database.</p>
              )}
            </section>
            <section className="methodology-panel" aria-labelledby="meaning-title">
              <h2 id="meaning-title">Evidence, not assumptions.</h2>
              <p>
                A listed IP matches public infrastructure records. An unknown IP has insufficient
                recent evidence.
              </p>
              <p>
                Organization country describes the network owner. Geolocation estimates the
                address’s location. Neither reveals a user’s identity.
              </p>
              <p>
                These sources have partial coverage. Proxy exit associations require qualifying
                observations. No residential proxy label, risk score, or detection-accuracy
                percentage is inferred.
              </p>
              <a href="/docs" target="_blank" rel="noreferrer">
                Read the API contract <UiIcon name="arrow" size={16} />
              </a>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
