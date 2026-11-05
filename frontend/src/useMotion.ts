import { useEffect } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';

gsap.registerPlugin(ScrollTrigger);

export function useLookupIntro(active: boolean) {
  useEffect(() => {
    if (!active) return;
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (preference.matches) return;

    const context = gsap.context(() => {
      gsap.fromTo(
        '[data-lookup-intro]',
        { y: 8, opacity: 0.88 },
        {
          y: 0,
          opacity: 1,
          stagger: 0.055,
          duration: 0.32,
          ease: 'power2.out',
          clearProps: 'transform,opacity',
        },
      );
    });
    const stop = () => {
      if (preference.matches) context.revert();
    };
    preference.addEventListener('change', stop);
    return () => {
      preference.removeEventListener('change', stop);
      context.revert();
    };
  }, [active]);
}

export function useResultFeedback(key: string | undefined) {
  useEffect(() => {
    if (!key) return;
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    let context: ReturnType<typeof gsap.context> | undefined;
    const update = () => {
      context?.revert();
      context = undefined;
      if (preference.matches) return;
      context = gsap.context(() => {
        gsap.fromTo(
          '[data-result-content]',
          { y: 3 },
          { y: 0, duration: 0.2, ease: 'power1.out', clearProps: 'transform' },
        );
      });
    };
    update();
    preference.addEventListener('change', update);
    return () => {
      preference.removeEventListener('change', update);
      context?.revert();
    };
  }, [key]);
}

export function useSourceScroll(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    let cleanup: (() => void) | undefined;
    const start = () => {
      cleanup?.();
      cleanup = undefined;
      if (preference.matches) return;
      const lenis = new Lenis({ smoothWheel: true, syncTouch: false, duration: 0.65 });
      const tick = (time: number) => lenis.raf(time * 1000);
      lenis.on('scroll', ScrollTrigger.update);
      gsap.ticker.add(tick);
      let cancelled = false;
      void document.fonts.ready.then(() => {
        if (!cancelled) ScrollTrigger.refresh();
      });
      const visible = () => (document.hidden ? lenis.stop() : lenis.start());
      document.addEventListener('visibilitychange', visible);
      cleanup = () => {
        cancelled = true;
        document.removeEventListener('visibilitychange', visible);
        gsap.ticker.remove(tick);
        lenis.off('scroll', ScrollTrigger.update);
        lenis.destroy();
      };
    };
    start();
    preference.addEventListener('change', start);
    return () => {
      preference.removeEventListener('change', start);
      cleanup?.();
    };
  }, [enabled]);
}
