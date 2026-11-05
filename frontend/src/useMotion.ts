import { useEffect } from 'react';
import gsap from 'gsap';
import { CustomEase } from 'gsap/CustomEase';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';

gsap.registerPlugin(CustomEase, ScrollTrigger);
const uiEase = CustomEase.create('vpnlens-out', '0.22, 1, 0.36, 1');

function animateEntrance(selector: string) {
  const targets = document.querySelectorAll(selector);
  if (!targets.length) return;
  return gsap.context(() => {
    gsap.fromTo(
      targets,
      { y: 12, opacity: 0, filter: 'blur(8px)' },
      {
        y: 0,
        opacity: 1,
        filter: 'blur(0px)',
        stagger: 0.065,
        duration: 0.52,
        ease: uiEase,
        clearProps: 'transform,opacity,filter',
      },
    );
  });
}

export function useLookupIntro(active: boolean) {
  useEffect(() => {
    if (!active) return;
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (preference.matches) return;

    const context = animateEntrance('[data-lookup-intro]');
    const stop = () => {
      if (preference.matches) context?.revert();
    };
    preference.addEventListener('change', stop);
    return () => {
      preference.removeEventListener('change', stop);
      context?.revert();
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
      context = animateEntrance('[data-result-content]');
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
      const lenis = new Lenis({
        smoothWheel: true,
        syncTouch: false,
        duration: 0.65,
        easing: uiEase,
      });
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
