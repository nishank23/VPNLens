import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { CSSProperties, FormEvent, KeyboardEvent as ReactKeyboardEvent } from 'react';
import type { Health, LookupResponse, SourceResponse } from './types';
import { ApiError, loadHealth, loadSources, lookupIP, validIPv4 } from './api';
import { LensMark, UiIcon } from './icons';
import { EmptyResult, ResultView } from './components/ResultView';
import { JsonView } from './components/JsonView';
import { SourcesView } from './components/SourcesView';
import { useResultFeedback, useSourceScroll } from './useMotion';

const samples = [
  { ip: '8.8.8.8', label: 'Google DNS' },
  { ip: '185.186.206.1', label: 'Multiple origins' },
  { ip: '192.0.2.1', label: 'Unknown evidence' },
];

export default function App() {
  const [view, setView] = useState(location.hash === '#sources' ? 'sources' : 'lookup');
  const [menu, setMenu] = useState(false);
  const [input, setInput] = useState('8.8.8.8');
  const [data, setData] = useState<LookupResponse | null>(null);
  const [querying, setQuerying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState(false);
  const [latency, setLatency] = useState<number | null>(null);
  const [isExample, setExample] = useState(true);
  const [sources, setSources] = useState<SourceResponse | null>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [mobilePane, setMobilePane] = useState<'readable' | 'json'>('readable');
  const request = useRef<AbortController | null>(null);
  const sourceRequest = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const requestId = useRef(0);
  const readableRef = useRef<HTMLDivElement>(null);
  const [resultHeight, setResultHeight] = useState(580);
  useLayoutEffect(() => {
    const element = readableRef.current;
    if (!element || view !== 'lookup') return;
    const observer = new ResizeObserver((entries) => {
      setResultHeight(Math.max(580, Math.ceil(entries[0].contentRect.height)));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [view]);
  const performLookup = useCallback(async (ip: string, example = false) => {
    if (!validIPv4(ip)) {
      setFieldError(true);
      inputRef.current?.focus();
      return;
    }
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    const id = ++requestId.current;
    setQuerying(true);
    setData(null);
    setError(null);
    setFieldError(false);
    setLatency(null);
    setExample(example);
    setMobilePane('readable');
    const started = performance.now();
    try {
      const next = await lookupIP(ip.trim(), controller.signal);
      if (id !== requestId.current || controller.signal.aborted) return;
      setData(next);
      setLatency(performance.now() - started);
      void loadHealth(controller.signal)
        .then((nextHealth) => {
          if (id === requestId.current && !controller.signal.aborted) setHealth(nextHealth);
        })
        .catch(() => {
          if (id === requestId.current && !controller.signal.aborted) setHealth(null);
        });
    } catch (failure) {
      if (id !== requestId.current || controller.signal.aborted) return;
      setHealth(null);
      setError(
        failure instanceof ApiError
          ? failure.message
          : 'The lookup could not be completed. Try again.',
      );
    } finally {
      if (id === requestId.current && !controller.signal.aborted) setQuerying(false);
    }
  }, []);
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
        setSourceError(failure instanceof Error ? failure.message : 'Sources are unavailable.');
    } finally {
      if (!controller.signal.aborted) setSourceLoading(false);
    }
  }, []);
  useEffect(() => {
    void performLookup('8.8.8.8', true);
    void refreshSources();
    const controller = new AbortController();
    void loadHealth(controller.signal)
      .then(setHealth)
      .catch(() => {
        if (!controller.signal.aborted) setHealth(null);
      });
    return () => {
      request.current?.abort();
      sourceRequest.current?.abort();
      controller.abort();
    };
  }, [performLookup, refreshSources]);
  useEffect(() => {
    const change = () => {
      setView(location.hash === '#sources' ? 'sources' : 'lookup');
      setMenu(false);
      window.scrollTo({ top: 0, behavior: 'instant' });
    };
    window.addEventListener('hashchange', change);
    const key = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'k') {
        event.preventDefault();
        location.hash = 'lookup';
        window.setTimeout(() => inputRef.current?.focus(), 0);
      }
      if (event.key === 'Escape') setMenu(false);
    };
    window.addEventListener('keydown', key);
    return () => {
      window.removeEventListener('hashchange', change);
      window.removeEventListener('keydown', key);
    };
  }, []);
  useResultFeedback(view === 'lookup' && data ? `${data.ip}-${latency}` : undefined);
  useSourceScroll(view === 'sources');
  function submit(event: FormEvent) {
    event.preventDefault();
    void performLookup(input);
  }
  function tabKey(event: ReactKeyboardEvent<HTMLButtonElement>) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next =
      event.key === 'Home'
        ? 'readable'
        : event.key === 'End'
          ? 'json'
          : mobilePane === 'readable'
            ? 'json'
            : 'readable';
    setMobilePane(next);
    document.getElementById(`${next}-tab`)?.focus();
  }
  function sample(ip: string) {
    setInput(ip);
    void performLookup(ip, true);
  }
  const activeFeeds = sources?.security.filter((source) => !source.stale).length;
  return (
    <div className="app-shell" data-app>
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
      <aside className="site-sidebar" aria-label="Workspace sidebar">
        <a className="brand" href="#lookup" aria-label="VPNLens lookup">
          <LensMark />
          <span>VPNLens</span>
        </a>
        <div className="workspace-scope">
          <span className="scope-dot" />
          Local workspace
        </div>
        <nav aria-label="Main navigation">
          <a
            href="#lookup"
            className={view === 'lookup' ? 'active' : ''}
            aria-current={view === 'lookup' ? 'page' : undefined}
          >
            <UiIcon name="lookup" />
            <span>IP lookup</span>
          </a>
          <a
            href="#sources"
            className={view === 'sources' ? 'active' : ''}
            aria-current={view === 'sources' ? 'page' : undefined}
          >
            <UiIcon name="database" />
            <span>Sources & freshness</span>
          </a>
          <a href="/docs" target="_blank" rel="noreferrer">
            <UiIcon name="document" />
            <span>API reference</span>
            <UiIcon name="arrow" size={14} />
          </a>
        </nav>
        <div className="sidebar-bottom">
          <p className="sidebar-statement">
            Look closer.
            <br />
            Follow the evidence.
          </p>
          <div className="sidebar-sources">
            <span className="small muted">Intelligence layers</span>
            <span>Geolocation</span>
            <span>Routing & ownership</span>
            <span>Public VPN / Tor lists</span>
          </div>
          <a href="#sources" className="sidebar-status">
            <span className="scope-dot" />
            {activeFeeds !== undefined
              ? `${activeFeeds} public feeds recently checked`
              : 'Source status unavailable'}
          </a>
          <div className="sidebar-credits">
            <a
              href="https://www.figma.com/community/file/1166831539721848736"
              target="_blank"
              rel="noreferrer"
            >
              Solar icons by 480 Design
            </a>
            <span>CC BY 4.0 · IBM Plex type</span>
          </div>
        </div>
      </aside>
      <div className="workspace-shell">
        <header className="workspace-header">
          <a className="mobile-brand brand" href="#lookup">
            <LensMark />
            <span>VPNLens</span>
          </a>
          <div className="breadcrumb">
            <span>Workspace</span>
            <span>/</span>
            <strong>{view === 'sources' ? 'Sources' : 'IP lookup'}</strong>
          </div>
          <div className="header-actions">
            <span
              className={`api-health ${health && health.status !== 'not_ready' ? 'available' : ''}`}
            >
              <span />
              {health?.status === 'ready'
                ? 'Local API ready'
                : health?.status === 'degraded'
                  ? 'API ready · partial sources'
                  : querying
                    ? 'Checking API'
                    : 'API status unavailable'}
            </span>
            <a className="header-docs" href="/docs" target="_blank" rel="noreferrer">
              API docs <UiIcon name="arrow" size={15} />
            </a>
            <button
              className="mobile-menu icon-button"
              onClick={() => setMenu(!menu)}
              aria-label={menu ? 'Close navigation' : 'Open navigation'}
              aria-expanded={menu}
              aria-controls="mobile-navigation"
            >
              <UiIcon name={menu ? 'close' : 'menu'} size={22} />
            </button>
          </div>
        </header>
        {menu && (
          <nav id="mobile-navigation" className="mobile-navigation" aria-label="Mobile navigation">
            <a href="#lookup" onClick={() => setMenu(false)}>
              IP lookup
            </a>
            <a href="#sources" onClick={() => setMenu(false)}>
              Sources & freshness
            </a>
            <a href="/docs" target="_blank" rel="noreferrer">
              API documentation
            </a>
          </nav>
        )}
        <main className="workspace-sheet" id="main-content" tabIndex={-1}>
          {view === 'sources' ? (
            <SourcesView
              data={sources}
              error={sourceError}
              loading={sourceLoading}
              refresh={() => void refreshSources()}
            />
          ) : (
            <>
              <header className="page-title">
                <div>
                  <h1>IP investigation</h1>
                  <p>One address. The evidence behind it.</p>
                </div>
                <span className="view-note">IPv4 intelligence</span>
              </header>
              <section className="search-section" aria-label="IP address search">
                <form onSubmit={submit} noValidate>
                  <label htmlFor="ip-input">IPv4 address</label>
                  <div className={`search-control ${fieldError ? 'invalid' : ''}`}>
                    <UiIcon name="lookup" size={21} />
                    <input
                      ref={inputRef}
                      id="ip-input"
                      value={input}
                      onChange={(event) => {
                        setInput(event.target.value);
                        setFieldError(false);
                      }}
                      placeholder="Enter an IPv4 address"
                      spellCheck={false}
                      autoComplete="off"
                      inputMode="decimal"
                      aria-describedby="ip-help"
                      aria-invalid={fieldError}
                    />
                    <span className="shortcut" aria-hidden="true">
                      ⌘ K
                    </span>
                    <button type="submit" className="primary-button">
                      {querying ? 'Looking up…' : 'Look up IP'}
                      <UiIcon name="arrow" size={18} />
                    </button>
                  </div>
                  <div className="search-bottom">
                    <p id="ip-help" className={fieldError ? 'field-error' : ''}>
                      {fieldError
                        ? 'Enter four numbers from 0–255, separated by dots. IPv4 hosts only.'
                        : 'IPv4 hosts only. Domains, ranges, and IPv6 are not supported.'}
                    </p>
                    <div className="sample-links">
                      <span>Try</span>
                      {samples.map((item) => (
                        <button
                          type="button"
                          onClick={() => sample(item.ip)}
                          key={item.ip}
                          title={item.label}
                        >
                          {item.ip}
                        </button>
                      ))}
                    </div>
                  </div>
                </form>
              </section>
              <div className="result-heading">
                <div>
                  <h2>Lookup results</h2>
                  {isExample && <span className="small muted">Live example</span>}
                </div>
                <span className="small muted" aria-live="polite">
                  {querying
                    ? 'Querying local datasets…'
                    : data
                      ? `Showing ${data.ip}`
                      : error
                        ? 'Request failed'
                        : 'Ready to investigate'}
                </span>
              </div>
              {error && (
                <div className="error-notice" role="alert">
                  <UiIcon name="info" />
                  <div>
                    <strong>We couldn’t complete this lookup.</strong>
                    <p>{error}</p>
                  </div>
                  <button onClick={() => void performLookup(input)}>Retry</button>
                </div>
              )}
              <div className="mobile-result-tabs" role="tablist" aria-label="Result format">
                <button
                  role="tab"
                  onKeyDown={tabKey}
                  tabIndex={mobilePane === 'readable' ? 0 : -1}
                  aria-selected={mobilePane === 'readable'}
                  onClick={() => setMobilePane('readable')}
                  id="readable-tab"
                  aria-controls="readable-pane"
                >
                  Readable result
                </button>
                <button
                  role="tab"
                  onKeyDown={tabKey}
                  tabIndex={mobilePane === 'json' ? 0 : -1}
                  aria-selected={mobilePane === 'json'}
                  onClick={() => setMobilePane('json')}
                  id="json-tab"
                  aria-controls="json-pane"
                >
                  API JSON
                </button>
              </div>
              <div
                className={`result-workspace show-${mobilePane}`}
                style={{ '--result-height': `${resultHeight}px` } as CSSProperties}
              >
                <div
                  ref={readableRef}
                  className="readable-pane"
                  id="readable-pane"
                  aria-busy={querying}
                >
                  {data ? <ResultView data={data} /> : <EmptyResult loading={querying} />}
                </div>
                <div className="json-pane" id="json-pane">
                  <JsonView data={data} loading={querying} latency={latency} />
                </div>
              </div>
              <footer className="workspace-footer">
                <span>Public evidence has partial coverage.</span>
                <a href="#sources">
                  Understand the sources <UiIcon name="arrow" size={14} />
                </a>
              </footer>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
