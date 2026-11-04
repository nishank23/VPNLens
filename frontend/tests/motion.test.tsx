// @vitest-environment jsdom
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const motion = vi.hoisted(() => ({
  fromTo: vi.fn(),
  revert: vi.fn(),
  add: vi.fn(),
  remove: vi.fn(),
  refresh: vi.fn(),
  update: vi.fn(),
  construct: vi.fn(),
  on: vi.fn(),
  off: vi.fn(),
  destroy: vi.fn(),
  stop: vi.fn(),
  start: vi.fn(),
  raf: vi.fn(),
}));
vi.mock('gsap', () => ({
  default: {
    registerPlugin: vi.fn(),
    fromTo: motion.fromTo,
    context: (callback: () => void) => {
      callback();
      return { revert: motion.revert };
    },
    ticker: { add: motion.add, remove: motion.remove },
  },
}));
vi.mock('gsap/ScrollTrigger', () => ({
  ScrollTrigger: { refresh: motion.refresh, update: motion.update },
}));
vi.mock('lenis', () => ({
  default: class {
    constructor() {
      motion.construct();
    }
    on = motion.on;
    off = motion.off;
    destroy = motion.destroy;
    stop = motion.stop;
    start = motion.start;
    raf = motion.raf;
  },
}));
import { useResultFeedback, useSourceScroll } from '../src/useMotion';

let media: {
  matches: boolean;
  addEventListener: ReturnType<typeof vi.fn>;
  removeEventListener: ReturnType<typeof vi.fn>;
};
beforeEach(() => {
  vi.clearAllMocks();
  media = { matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() };
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => media),
  );
  Object.defineProperty(document, 'fonts', {
    configurable: true,
    value: { ready: Promise.resolve() },
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('motion is optional and cleaned up', () => {
  it('bypasses result animation and smooth scrolling under reduced motion', () => {
    media.matches = true;
    renderHook(() => {
      useResultFeedback('8.8.8.8');
      useSourceScroll(true);
    });
    expect(motion.fromTo).not.toHaveBeenCalled();
    expect(motion.construct).not.toHaveBeenCalled();
    expect(motion.add).not.toHaveBeenCalled();
  });
  it('never initializes smooth scrolling in the lookup view', () => {
    renderHook(() => useSourceScroll(false));
    expect(motion.construct).not.toHaveBeenCalled();
  });
  it('converts ticker time to milliseconds and removes all scrolling resources', () => {
    const { unmount } = renderHook(() => useSourceScroll(true));
    expect(motion.construct).toHaveBeenCalledTimes(1);
    const tick = motion.add.mock.calls[0][0];
    tick(1.2);
    expect(motion.raf).toHaveBeenCalledWith(1200);
    unmount();
    expect(motion.remove).toHaveBeenCalledWith(tick);
    expect(motion.off).toHaveBeenCalled();
    expect(motion.destroy).toHaveBeenCalledTimes(1);
    expect(media.removeEventListener).toHaveBeenCalledWith('change', expect.any(Function));
  });
  it('destroys smooth scrolling when reduced motion changes during the session', () => {
    renderHook(() => useSourceScroll(true));
    const change = media.addEventListener.mock.calls[0][1];
    act(() => {
      media.matches = true;
      change();
    });
    expect(motion.destroy).toHaveBeenCalledTimes(1);
    expect(motion.construct).toHaveBeenCalledTimes(1);
  });
  it('reverts result feedback when its component is removed', () => {
    const { unmount } = renderHook(() => useResultFeedback('8.8.8.8'));
    expect(motion.fromTo).toHaveBeenCalledTimes(1);
    unmount();
    expect(motion.revert).toHaveBeenCalledTimes(1);
  });
  it('clears result feedback immediately when reduced motion is enabled', () => {
    renderHook(() => useResultFeedback('8.8.8.8'));
    const change = media.addEventListener.mock.calls[0][1];
    act(() => {
      media.matches = true;
      change();
    });
    expect(motion.revert).toHaveBeenCalledTimes(1);
    expect(motion.fromTo).toHaveBeenCalledTimes(1);
  });
});
