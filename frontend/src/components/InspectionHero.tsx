import { Component, lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import type { PointerEvent, ReactNode } from 'react';
import { summarize, countryName } from '../presentation';
import type { DecisionResponse } from '../types';
import { LensMark } from '../icons';

const OpticalLens = lazy(() => import('./OpticalLens'));

export interface LensMotion {
  target: { x: number; y: number } | null;
  pinned: boolean;
  invalidate?: () => void;
}

class GlassFallback extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}

function inspectionFacts(data: DecisionResponse) {
  const { location, groups, owners, security } = summarize(data.lookup);
  const countryCode = location.country_code;
  const flag =
    countryCode && /^[A-Z]{2}$/.test(countryCode)
      ? String.fromCodePoint(...Array.from(countryCode, (letter) => 127397 + letter.charCodeAt(0)))
      : null;
  const operatorNames = [
    ...new Set(owners.flatMap(({ org_name }) => (org_name ? [org_name] : []))),
  ];
  const originAsns = [
    ...new Set(
      groups.flatMap(({ origin_group }) => origin_group?.split(',').map((asn) => asn.trim()) ?? []),
    ),
  ];
  const vpn = security.vpn_status === 'listed';
  const tor = security.tor_status === 'listed';
  const proxy = security.proxy_status === 'listed';
  const network = security.vpn_assessment === 'network_only';
  const direct = vpn || tor || proxy;
  return {
    country: countryName(countryCode),
    flag,
    operator: operatorNames.length ? operatorNames.join(' / ') : 'Network operator unavailable',
    asns: originAsns.filter(Boolean).map((asn) => `AS${asn}`),
    verdict: vpn
      ? 'VPN detected'
      : tor
        ? 'Tor exit listed'
        : proxy
          ? 'Proxy listed'
          : network
            ? 'VPN network match'
            : 'No VPN match',
    score: direct ? 80 : network ? 35 : null,
    direct,
  };
}

export function InspectionHero({
  data,
  querying,
  manual,
}: {
  data: DecisionResponse | null;
  querying: boolean;
  manual: boolean;
}) {
  const stage = useRef<HTMLElement>(null);
  const address = useRef<HTMLHeadingElement>(null);
  const floating = useRef<HTMLDivElement>(null);
  const motion = useRef<LensMotion>({ target: null, pinned: false });
  const [capable, setCapable] = useState(false);
  const [visible, setVisible] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [hovered, setHovered] = useState(false);
  const revealed = pinned || hovered;
  const facts = data ? inspectionFacts(data) : null;

  const hideHoverLens = useCallback(() => {
    motion.current.target = null;
    motion.current.invalidate?.();
    setHovered(false);
  }, []);

  useEffect(() => {
    const host = stage.current;
    if (!host || typeof IntersectionObserver === 'undefined') return;
    const preference = window.matchMedia(
      '(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)',
    );
    const update = () => {
      setCapable(preference.matches && 'WebGL2RenderingContext' in window);
      hideHoverLens();
    };
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting));
    update();
    observer.observe(host);
    preference.addEventListener('change', update);
    window.addEventListener('blur', hideHoverLens);
    return () => {
      observer.disconnect();
      preference.removeEventListener('change', update);
      window.removeEventListener('blur', hideHoverLens);
    };
  }, [hideHoverLens]);

  useEffect(() => {
    if (!revealed) return;
    const dismiss = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      motion.current.pinned = false;
      motion.current.invalidate?.();
      setPinned(false);
      setHovered(false);
    };
    document.addEventListener('keydown', dismiss);
    return () => document.removeEventListener('keydown', dismiss);
  }, [revealed]);

  function moveLens(event: PointerEvent<HTMLElement>) {
    if (!capable || event.pointerType === 'touch') return;
    const bounds = event.currentTarget.getBoundingClientRect();
    motion.current.target = { x: event.clientX - bounds.left, y: event.clientY - bounds.top };
    motion.current.invalidate?.();
  }

  function pinLens(next: boolean) {
    if (next) floating.current?.removeAttribute('data-aligned');
    motion.current.pinned = next;
    motion.current.invalidate?.();
    setPinned(next);
  }

  return (
    <section
      className="inspection-stage relative isolate grid place-items-center overflow-hidden text-center"
      aria-labelledby="inspection-address"
      ref={stage}
      onPointerEnter={moveLens}
      onPointerMove={moveLens}
      onPointerLeave={hideHoverLens}
      onPointerCancel={hideHoverLens}
    >
      {data && capable && visible && (
        <GlassFallback>
          <Suspense fallback={null}>
            <OpticalLens
              ip={data.lookup.ip}
              stage={stage}
              address={address}
              floating={floating}
              motion={motion}
            />
          </Suspense>
        </GlassFallback>
      )}
      <div className="inspection-copy flex min-w-0 max-w-full flex-col items-center">
        <p className="inspection-kicker inline-flex items-center gap-2">
          <span aria-hidden="true" />
          {manual ? 'IP lookup' : 'Your public IPv4'}
        </p>
        <h1
          className={`inspection-ip${data ? ' inspection-ip-live' : ''}`}
          id="inspection-address"
          ref={address}
          onPointerEnter={(event) => {
            if (!facts || !capable || event.pointerType === 'touch') return;
            if (!pinned) floating.current?.removeAttribute('data-aligned');
            setHovered(true);
          }}
          onPointerLeave={() => setHovered(false)}
        >
          {data?.lookup.ip ?? (querying ? 'Checking IP…' : 'Check an IP address')}
        </h1>
        {facts && (
          <div className="inspection-meta flex flex-wrap items-center justify-center">
            <span className="inspection-operator" title="Network operator">
              {facts.operator}
            </span>
            <span className="inspection-country inline-flex items-center gap-2">
              {facts.flag && (
                <span className="inspection-flag" aria-hidden="true">
                  {facts.flag}
                </span>
              )}
              {facts.country === 'Unavailable' ? 'Location unavailable' : facts.country}
            </span>
          </div>
        )}
      </div>
      {facts && (
        <>
          <div
            className="inspection-float"
            ref={floating}
            aria-label="IP inspection"
            role="region"
            id="inspection-readout"
            hidden={!revealed}
          >
            <div className="inspection-readout">
              <p className={facts.direct ? 'inspection-hit' : undefined}>{facts.verdict}</p>
              <dl className="grid grid-cols-2">
                <div>
                  <dt>ASN</dt>
                  <dd title={facts.asns.join(', ')}>
                    {facts.asns.length ? facts.asns[0] : 'Unavailable'}
                    {facts.asns.length > 1 && <small> +{facts.asns.length - 1}</small>}
                  </dd>
                </div>
                <div>
                  <dt>Risk score</dt>
                  <dd>
                    {facts.score === null ? (
                      'Unrated'
                    ) : (
                      <>
                        {facts.score}
                        <small> / 100</small>
                      </>
                    )}
                  </dd>
                </div>
              </dl>
              <small>Based on evidence</small>
            </div>
          </div>
          <button
            className="inspection-toggle inline-flex items-center justify-center gap-2"
            type="button"
            aria-expanded={revealed}
            aria-controls="inspection-readout"
            onClick={() => pinLens(!pinned)}
          >
            <LensMark />
            {pinned ? 'Close inspection' : 'Inspect IP'}
          </button>
        </>
      )}
    </section>
  );
}
