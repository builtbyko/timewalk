export function createUI() {
  const root = document.getElementById("scene-root");
  const loading = document.getElementById("loading");
  const loadingStatus = document.getElementById("loading-status");
  const fallback = document.getElementById("fallback");
  const fallbackMessage = document.getElementById("fallback-message");
  const scrollCue = document.getElementById("scroll-cue");
  const strataLegend = document.getElementById("strata-legend");
  const debugToggle = document.getElementById("debug-toggle");
  const debugPanel = document.getElementById("debug-panel");
  const debugOutput = document.getElementById("debug-output");

  if (!root) throw new Error("#scene-root is required");

  const onDebugToggle = () => {
    if (!debugPanel) return;
    const visible = debugPanel.hidden;
    debugPanel.hidden = !visible;
    debugToggle?.setAttribute("aria-expanded", String(visible));
    debugToggle?.setAttribute("aria-pressed", String(visible));
  };
  debugToggle?.addEventListener("click", onDebugToggle);

  function leaveLoadingState() {
    if (loading) loading.hidden = true;
    document.body.classList.remove("is-loading");
  }

  return Object.freeze({
    root,
    setLoading(message) {
      if (loadingStatus) loadingStatus.textContent = message;
    },
    showReady() {
      leaveLoadingState();
      if (fallback) fallback.hidden = true;
      root.dataset.ready = "true";
    },
    showFallback(message) {
      leaveLoadingState();
      root.dataset.ready = "false";
      if (fallbackMessage) fallbackMessage.textContent = message;
      if (fallback) fallback.hidden = false;
    },
    hideFallback() {
      if (fallback) fallback.hidden = true;
    },
    isFallbackVisible() {
      return fallback ? fallback.hidden === false : false;
    },
    setScrollStarted(started) {
      if (scrollCue) scrollCue.dataset.started = String(started);
    },
    setStrataLegendVisible(visible) {
      if (!strataLegend) return;
      strataLegend.hidden = false;
      strataLegend.dataset.visible = String(visible);
    },
    setDebug(text) {
      if (debugOutput) debugOutput.textContent = text;
    },
    setDebugVisible(visible) {
      if (debugPanel) debugPanel.hidden = !visible;
      debugToggle?.setAttribute("aria-expanded", String(visible));
      debugToggle?.setAttribute("aria-pressed", String(visible));
    },
    dispose() {
      debugToggle?.removeEventListener("click", onDebugToggle);
    },
  });
}
