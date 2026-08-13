import { CONFIG } from "./config.js";

const EMPTY_COLLECTION = Object.freeze({ type: "FeatureCollection", features: Object.freeze([]) });
const REQUIRED_DATASETS = Object.freeze(["roads", "buildings"]);

function normalizeFeatureCollection(value, key) {
  if (value?.type === "FeatureCollection" && Array.isArray(value.features)) return value;
  if (value?.type === "Feature" && value.geometry) {
    return { type: "FeatureCollection", features: [value] };
  }
  throw new Error(`${key} is not a GeoJSON FeatureCollection`);
}

async function fetchGeoJSON(path, key, signal) {
  const url = new URL(path, document.baseURI);
  const response = await fetch(url, {
    signal,
    credentials: "same-origin",
    cache: "no-cache",
  });
  if (!response.ok) throw new Error(`${key} returned HTTP ${response.status}`);
  return normalizeFeatureCollection(await response.json(), key);
}

export async function loadAssets({ onProgress = () => {}, timeoutMs = CONFIG.loading.timeoutMs } = {}) {
  const entries = Object.entries(CONFIG.data);
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  let completed = 0;

  try {
    const settled = await Promise.allSettled(
      entries.map(async ([key, path]) => {
        onProgress({ key, state: "loading", completed, total: entries.length });
        const value = await fetchGeoJSON(path, key, controller.signal);
        completed += 1;
        onProgress({ key, state: "loaded", completed, total: entries.length });
        return { key, value };
      }),
    );

    const data = {};
    const status = {};
    const warnings = [];
    const errors = {};

    settled.forEach((result, index) => {
      const [key] = entries[index];
      if (result.status === "fulfilled") {
        data[key] = result.value.value;
        status[key] = "loaded";
        return;
      }
      completed += 1;
      data[key] = EMPTY_COLLECTION;
      status[key] = "failed";
      errors[key] = result.reason;
      warnings.push(`${key} を読み込めませんでした`);
      onProgress({ key, state: "failed", completed, total: entries.length });
    });

    const missingRequired = REQUIRED_DATASETS.filter((key) => status[key] !== "loaded");
    if (missingRequired.length) {
      throw new AggregateError(
        missingRequired.map((key) => errors[key]),
        `Required city data could not be loaded: ${missingRequired.join(", ")}`,
      );
    }

    return { data, status, warnings, errors };
  } finally {
    window.clearTimeout(timer);
  }
}
