import { CONFIG } from "./config.js";

/**
 * Turns document scroll into Act 1 progress. Kept separate from rendering so
 * the renderer never reads layout, and so the track length has one owner.
 */
export function createScrollDriver({ onProgress }) {
  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)");
  let frame = 0;
  let disposed = false;
  let lastProgress = -1;

  function actLength() {
    const viewport = window.visualViewport?.height || window.innerHeight;
    return Math.max(1, viewport * CONFIG.sequence.scrollViewports);
  }

  function readProgress() {
    const scrolled = window.scrollY || window.pageYOffset || 0;
    return Math.min(1, Math.max(0, scrolled / actLength()));
  }

  function emit() {
    frame = 0;
    if (disposed) return;
    const progress = readProgress();
    if (progress === lastProgress) return;
    lastProgress = progress;
    onProgress(progress, { reducedMotion: reducedMotion?.matches === true });
  }

  const schedule = () => {
    if (frame || disposed) return;
    frame = window.requestAnimationFrame(emit);
  };

  // Force the next emit even when the progress value is unchanged, which is
  // what a resize needs: same scroll fraction, different framing.
  const invalidate = () => {
    lastProgress = -1;
    schedule();
  };

  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", invalidate, { passive: true });
  window.addEventListener("orientationchange", invalidate, { passive: true });
  window.visualViewport?.addEventListener("resize", invalidate, { passive: true });
  reducedMotion?.addEventListener?.("change", invalidate);

  return Object.freeze({
    start() {
      // Emit synchronously rather than waiting for a frame. A reload can
      // restore a scroll position part way through the act, and requestAnimation
      // Frame does not run while the page is hidden, so the first state would
      // otherwise be wrong until the reader moved.
      lastProgress = -1;
      emit();
    },
    invalidate,
    trackHeightCss() {
      return `calc(${CONFIG.sequence.scrollViewports * 100}vh + 100vh)`;
    },
    dispose() {
      disposed = true;
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", invalidate);
      window.removeEventListener("orientationchange", invalidate);
      window.visualViewport?.removeEventListener("resize", invalidate);
      reducedMotion?.removeEventListener?.("change", invalidate);
    },
  });
}
