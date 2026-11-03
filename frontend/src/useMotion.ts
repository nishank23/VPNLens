import { useEffect } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';

gsap.registerPlugin(ScrollTrigger);

export function useResultFeedback(key: string | undefined) {
  useEffect(() => {
    if (!key || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const context = gsap.context(() => {
      gsap.fromTo(
        '[data-result-content]',
        { y: 5, opacity: 0.75 },
        { y: 0, opacity: 1, duration: 0.24, ease: 'power2.out', clearProps: 'transform,opacity' },
      );
    });
    return () => context.revert();
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
