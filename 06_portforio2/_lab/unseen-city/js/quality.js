import { QUALITY_PROFILES } from "./config.js";

function safeMediaQuery(query) {
  return typeof window.matchMedia === "function" && window.matchMedia(query).matches;
}

function forcedTier() {
  const value = new URLSearchParams(window.location.search).get("quality");
  return Object.hasOwn(QUALITY_PROFILES, value) ? value : null;
}

export function detectQuality() {
  const override = forcedTier();
  const cores = Number.isFinite(navigator.hardwareConcurrency)
    ? navigator.hardwareConcurrency
    : null;
  const memory = Number.isFinite(navigator.deviceMemory)
    ? navigator.deviceMemory
    : null;
  const limitedCores = cores !== null && cores <= 4;
  const limitedMemory = memory !== null && memory <= 4;
  const coarsePointer = safeMediaQuery("(pointer: coarse)");
  const narrow = Math.min(window.innerWidth, window.innerHeight) <= 520;
  const mobileLayout = window.innerWidth <= 760 || coarsePointer;

  let tier = "high";
  if (narrow || (coarsePointer && (limitedCores || limitedMemory))) {
    tier = "low";
  } else if (mobileLayout || limitedCores || limitedMemory) {
    tier = "medium";
  }
  if (override) tier = override;

  return Object.freeze({
    ...QUALITY_PROFILES[tier],
    forced: Boolean(override),
    coarsePointer,
    mobileLayout,
    reducedMotion: safeMediaQuery("(prefers-reduced-motion: reduce)"),
  });
}

export function pixelRatioFor(quality) {
  return Math.min(window.devicePixelRatio || 1, quality.maxDpr);
}
