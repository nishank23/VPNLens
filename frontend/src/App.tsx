import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import {
  ApiError,
  checkIP,
  checkVisitorConnection,
  isLoopbackOrigin,
  loadSources,
  validIPv4,
} from './api';
import type { DecisionResponse, SourceResponse } from './types';
import { LensMark, UiIcon } from './icons';
import { ConnectionResult } from './components/ConnectionResult';
import { ConnectionComparison, type ConnectionSnapshot } from './components/ConnectionComparison';
import { InspectionBackdrop } from './components/InspectionBackdrop';
import { InspectionHero } from './components/InspectionHero';
import { ResultView } from './components/ResultView';
import { JsonView } from './components/JsonView';
import { SourcesView } from './components/SourcesView';
import { useLookupIntro, useResultFeedback, useSourceScroll } from './useMotion';
import './connection.css';
import './inspection.css';

type Target = { kind: 'connection' } | { kind: 'manual'; ip: string };
const ownConnection: Target = { kind: 'connection' };
const localDiscoveryKey = 'vpnlens:ipify-consent';

export default function App() {
  const [view, setView] = useState(location.hash === '#sources' ? 'sources' : 'lookup');
  const [input, setInput] = useState('');
  const [data, setData] = useState<DecisionResponse | null>(null);
  const [baseline, setBaseline] = useState<ConnectionSnapshot | null>(null);
  const [endpoint, setEndpoint] = useState('/v1/connection');
  const [allowIpify, setAllowIpify] = useState(() => {
    if (!isLoopbackOrigin()) return false;
    try {
      return localStorage.getItem(localDiscoveryKey) !== 'disabled';
    } catch {
      return true;
    }
  });
  const [querying, setQuerying] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [target, setTarget] = useState<Target>(ownConnection);
  const [latency, setLatency] = useState<number | null>(null);
  const [panel, setPanel] = useState<'details' | 'json' | null>(null);
  const [sources, setSources] = useState<SourceResponse | null>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const request = useRef<AbortController | null>(null);
  const sourceRequest = useRef<AbortController | null>(null);
  const requestId = useRef(0);
  const inputEditId = useRef(0);
  const focusLookup = useRef(false);

  const performCheck = useCallback(
    async (nextTarget: Target) => {
      request.current?.abort();
      const controller = new AbortController();
      request.current = controller;
      const id = ++requestId.current;
      const editId = inputEditId.current;
      setTarget(nextTarget);
      setData(null);
      setError(null);
      setQuerying(true);
      setFieldError(null);
      setLatency(null);
      setPanel(null);
      const started = performance.now();
      try {
        const result =
          nextTarget.kind === 'connection'
            ? await checkVisitorConnection(controller.signal, allowIpify, (ip) => {
                if (
                  !controller.signal.aborted &&
                  id === requestId.current &&
                  editId === inputEditId.current
                ) {
                  setInput(ip);
                }
              })
            : {
                data: await checkIP(nextTarget.ip, controller.signal),
                endpoint: `/v1/access-decision/${nextTarget.ip}`,
              };
        if (controller.signal.aborted || id !== requestId.current) return;
        setData(result.data);
        setEndpoint(result.endpoint);
        setLatency(performance.now() - started);
      } catch (failure) {
        if (controller.signal.aborted || id !== requestId.current) return;
        setError(
          failure instanceof ApiError
            ? failure
            : new ApiError('The check could not be completed. Try again.'),
        );
      } finally {
        if (!controller.signal.aborted && id === requestId.current) setQuerying(false);
      }
    },
    [allowIpify],
  );

  const refreshSources = useCallback(async () => {
    sourceRequest.current?.abort();
    const controller = new AbortController();
    sourceRequest.current = controller;
    setSourceLoading(true);
    setSourceError(null);
    try {
      const next = await loadSources(controller.signal);
      if (!controller.signal.aborted) setSources(next);
    } catch (failure) {
      if (!controller.signal.aborted)
        setSourceError(failure instanceof Error ? failure.message : 'Sources unavailable.');
    } finally {
      if (!controller.signal.aborted) setSourceLoading(false);
    }
  }, []);

  useEffect(() => {
    void performCheck(ownConnection);
    return () => {
      ++requestId.current;
      request.current?.abort();
    };
  }, [performCheck]);
  useEffect(() => {
    if (view === 'sources') void refreshSources();
    return () => sourceRequest.current?.abort();
  }, [view, refreshSources]);
  useEffect(() => {
    const navigate = () => {
      setView(location.hash === '#sources' ? 'sources' : 'lookup');
      window.scrollTo({ top: 0, behavior: 'instant' });
    };
    const key = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'k') {
        event.preventDefault();
        focusLookup.current = true;
        setView('lookup');
        location.hash = 'lookup';
        if (inputRef.current) {
          inputRef.current.focus();
          focusLookup.current = false;
        }
      }
    };
    window.addEventListener('hashchange', navigate);
    window.addEventListener('keydown', key);
    return () => {
      window.removeEventListener('hashchange', navigate);
      window.removeEventListener('keydown', key);
    };
  }, []);
  useEffect(() => {
    if (view === 'lookup' && focusLookup.current) {
      inputRef.current?.focus();
      focusLookup.current = false;
    }
  }, [view]);
  useLookupIntro(view === 'lookup');
  useResultFeedback(view === 'lookup' && data ? `${data.lookup.ip}-${latency}` : undefined);
  useSourceScroll(view === 'sources' || panel !== null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!validIPv4(input)) {
      request.current?.abort();
      ++requestId.current;
      setData(null);
      setError(null);
      setQuerying(false);
      setPanel(null);
      setFieldError(
        input.includes(':')
          ? 'IPv6 is not supported yet.'
          : 'Enter a valid IPv4 address, such as 8.8.8.8.',
      );
      inputRef.current?.focus();
      return;
    }
    void performCheck({ kind: 'manual', ip: input.trim() });
  }
  const connectionUnavailable = error?.code === 'public_ipv4_unavailable';
  const unsupported = error?.code === 'ipv6_not_supported';
  const currentConnection: ConnectionSnapshot | null =
    target.kind === 'connection' && data
      ? { data, method: endpoint === '/v1/connection' ? 'site' : 'ipify' }
      : null;
  const offerIpify = !allowIpify && isLoopbackOrigin() && (connectionUnavailable || unsupported);

  function setLocalDiscovery(enabled: boolean) {
    try {
      localStorage.setItem(localDiscoveryKey, enabled ? 'enabled' : 'disabled');
    } catch {
      // Keep the choice for the current page when storage is unavailable.
    }
    setAllowIpify(enabled);
  }
  return (
    <div className="app-shell public-demo" data-app>
      <a
        className="skip-link"
        href="#main-content"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById('main-content')?.focus();
        }}
      >
        Skip to content
      </a>
      <div className="connection-shell">
        <header className="product-bar" data-lookup-intro>
          <a href="#lookup" className="brand" aria-label="VPNLens lookup">
            <LensMark />
            <span>VPNLens</span>
          </a>
          <a className="product-api-link" href="/docs" target="_blank" rel="noreferrer">
            <UiIcon name="code" size={18} />
            API docs
          </a>
        </header>
        <main
          className={view === 'sources' ? 'report-sheet' : undefined}
          id="main-content"
          tabIndex={-1}
        >
          {view === 'sources' ? (
            <SourcesView
              data={sources}
              loading={sourceLoading}
              error={sourceError}
              refresh={() => void refreshSources()}
            />
          ) : (
            <div className="lookup-workspace">
              <div className="inspection-hero">
                <InspectionHero
                  key={data?.lookup.ip}
                  data={data}
                  querying={querying}
                  manual={target.kind === 'manual'}
                />
                <InspectionBackdrop />
              </div>
              <section className="lookup-controls" aria-label="Look up an IPv4 address">
                <form className="connection-search" onSubmit={submit} noValidate data-lookup-intro>
                  <label htmlFor="ip-input">IPv4 address</label>
                  <div className="connection-search-row">
                    <input
                      ref={inputRef}
                      id="ip-input"
                      value={input}
                      onChange={(event) => {
                        ++inputEditId.current;
                        setInput(event.target.value);
                        setFieldError(null);
                      }}
                      placeholder="Enter an IP address"
                      autoComplete="off"
                      spellCheck={false}
                      inputMode="decimal"
                      aria-invalid={!!fieldError}
                      aria-describedby={fieldError ? 'ip-error' : undefined}
                    />
                    <button className="lookup-action" type="submit">
                      Look up
                      <UiIcon name="arrow" />
                    </button>
                  </div>
                  {fieldError && (
                    <p className="connection-field-error" id="ip-error" role="alert">
                      {fieldError}
                    </p>
                  )}
                </form>
              </section>
              <div className="report-sheet">
                <section
                  className="connection-result"
                  aria-label="Connection result"
                  aria-busy={querying}
                >
                  <div className="connection-result-header" data-lookup-intro>
                    <p>{target.kind === 'connection' ? 'Your connection' : 'Manual lookup'}</p>
                    <button
                      className="recheck-action"
                      onClick={() => void performCheck(ownConnection)}
                      disabled={offerIpify}
                      type="button"
                    >
                      <UiIcon name="refresh" />
                      Recheck
                    </button>
                  </div>
                  {data ? (
                    <ConnectionResult data={data} />
                  ) : (
                    <div className="connection-empty" role={error ? 'alert' : undefined}>
                      <h2>
                        {querying
                          ? 'Checking…'
                          : offerIpify
                            ? 'Detect your public IPv4'
                            : connectionUnavailable
                              ? 'Your public IPv4 is unavailable here'
                              : unsupported
                                ? 'IPv6 is not supported yet.'
                                : error
                                  ? 'Check unavailable'
                                  : 'Ready to check'}
                      </h2>
                      <p>
                        {querying
                          ? 'Reading local evidence.'
                          : offerIpify
                            ? 'On this local site, your browser will contact ipify, which sees your public IPv4.'
                            : connectionUnavailable || unsupported
                              ? 'Enter an IPv4 address above.'
                              : error?.message || 'Enter an IPv4 address to begin.'}
                      </p>
                      {querying ? (
                        <div className="connection-loading" aria-hidden="true">
                          <span />
                          <span />
                          <span />
                        </div>
                      ) : offerIpify ? (
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() => setLocalDiscovery(true)}
                        >
                          Enable automatic detection
                        </button>
                      ) : error && !connectionUnavailable && !unsupported ? (
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() => void performCheck(target)}
                        >
                          Retry
                        </button>
                      ) : null}
                    </div>
                  )}
                </section>
                {currentConnection && baseline && (
                  <ConnectionComparison
                    baseline={baseline}
                    current={currentConnection}
                    onClear={() => setBaseline(null)}
                  />
                )}
                <div className="connection-disclosures">
                  <div className="disclosure-actions">
                    {(['details', 'json'] as const).map((name) => (
                      <button
                        key={name}
                        type="button"
                        disabled={!data || querying}
                        aria-expanded={panel === name}
                        aria-controls={`${name}-panel`}
                        onClick={() => setPanel(panel === name ? null : name)}
                      >
                        {name === 'details' ? 'Details' : 'JSON'}
                        <UiIcon name="arrow" size={14} />
                      </button>
                    ))}
                    {currentConnection && !baseline && (
                      <button type="button" onClick={() => setBaseline(currentConnection)}>
                        Compare VPN
                      </button>
                    )}
                  </div>
                  {data && (
                    <time
                      className="check-time"
                      dateTime={data.decision.evaluated_at}
                      title={data.decision.evaluated_at}
                    >
                      Checked{' '}
                      {new Intl.DateTimeFormat('en', { hour: '2-digit', minute: '2-digit' }).format(
                        new Date(data.decision.evaluated_at),
                      )}
                    </time>
                  )}
                </div>
                {data && panel === 'details' && (
                  <section className="connection-details" id="details-panel" aria-label="Details">
                    <ResultView data={data.lookup} compact />
                  </section>
                )}
                {data && panel === 'json' && (
                  <section id="json-panel" aria-label="JSON">
                    <JsonView
                      data={data.lookup}
                      loading={querying}
                      latency={latency}
                      endpoint={endpoint}
                      lookupExcerpt
                    />
                  </section>
                )}
              </div>
              <span className="sr-only" role="status" aria-live="polite">
                {querying
                  ? 'Checking connection'
                  : data
                    ? `Check complete for ${data.lookup.ip}`
                    : ''}
              </span>
            </div>
          )}
        </main>
        <footer className="connection-footer">
          {data?.lookup.selected_sources.geolocation?.provider === 'dbip_city_lite' ? (
            <a href="https://db-ip.com">IP Geolocation by DB-IP</a>
          ) : null}
          <nav aria-label="More information">
            <a href={view === 'sources' ? '#lookup' : '#sources'}>
              {view === 'sources' ? 'IP check' : 'Sources'}
            </a>
            <details>
              <summary>About</summary>
              <div className="about-content">
                <p>
                  VPNLens checks public evidence for VPN, Tor, and proxy associations. Coverage
                  varies by source.
                </p>
                <p>
                  The risk score reflects matching evidence. A direct match scores 80, a
                  network-only match scores 35, and an address without matching evidence is unrated.
                </p>
                {allowIpify && (
                  <div>
                    <p>On localhost, ipify sees your public IPv4 during automatic detection.</p>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => setLocalDiscovery(false)}
                    >
                      Disable automatic detection
                    </button>
                  </div>
                )}
                <p>
                  IBM Plex fonts ·{' '}
                  <a
                    href="https://www.figma.com/community/file/1166831539721848736"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Solar icons by 480 Design
                  </a>{' '}
                  (CC BY 4.0).
                </p>
              </div>
            </details>
          </nav>
        </footer>
      </div>
    </div>
  );
}
