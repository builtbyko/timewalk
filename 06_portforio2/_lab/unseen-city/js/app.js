import * as THREE from "../vendor/three.module.js";
import { CONFIG } from "./config.js";
import { detectQuality, pixelRatioFor } from "./quality.js";
import { loadAssets } from "./assets.js";
import { createLocalProjection } from "./geo.js";
import { createCity } from "./city.js";
import { createFixedCamera, frameFixedCamera } from "./camera.js";
import { createUI } from "./ui.js";

function viewportFor(host) {
  const rect = host.getBoundingClientRect();
  const visualHeight = window.visualViewport?.height || window.innerHeight;
  return {
    width: Math.max(1, Math.round(rect.width || window.innerWidth)),
    height: Math.max(1, Math.round(rect.height || visualHeight)),
  };
}

function createRenderer(host, quality) {
  const renderer = new THREE.WebGLRenderer({
    antialias: quality.antialias,
    alpha: false,
    powerPreference: CONFIG.renderer.powerPreference,
  });
  renderer.setPixelRatio(pixelRatioFor(quality));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = CONFIG.renderer.exposure;
  renderer.shadowMap.enabled = false;
  renderer.domElement.setAttribute("aria-hidden", "true");
  host.appendChild(renderer.domElement);
  return renderer;
}

function createScene() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(CONFIG.scene.background);
  scene.fog = new THREE.FogExp2(CONFIG.scene.fog, CONFIG.scene.fogDensity);

  const hemisphere = new THREE.HemisphereLight(
    CONFIG.palette.skyLight,
    CONFIG.palette.groundLight,
    CONFIG.lights.hemisphereIntensity,
  );
  const key = new THREE.DirectionalLight(CONFIG.palette.keyLight, CONFIG.lights.keyIntensity);
  key.position.set(...CONFIG.lights.keyPosition);
  key.castShadow = false;
  scene.add(hemisphere, key);
  return scene;
}

function debugText({ quality, assets, city, renderer }) {
  const info = renderer.info.render;
  const assetState = Object.entries(assets.status).map(([key, value]) => `${key}: ${value}`).join("\n");
  return [
    `quality: ${quality.tier}${quality.forced ? " (forced)" : ""}`,
    `dpr: ${renderer.getPixelRatio().toFixed(2)}`,
    assetState,
    `roads: ${city.stats.roadFeatures} features / ${city.stats.roadSegments} segments`,
    `rail: ${city.stats.railFeatures} features / ${city.stats.railSegments} segments`,
    `waterways: ${city.stats.waterwayFeatures} features / ${city.stats.waterwaySegments} segments`,
    `buildings: ${city.stats.buildings} / ${city.stats.buildingCandidates}`,
    `draw calls: ${info.calls}`,
    `triangles: ${info.triangles}`,
    assets.warnings.length ? `warnings: ${assets.warnings.join(", ")}` : "warnings: none",
  ].join("\n");
}

async function bootstrap(ui) {
  const quality = detectQuality();
  document.documentElement.dataset.quality = quality.tier;
  let renderer;
  try {
    renderer = createRenderer(ui.root, quality);
  } catch (error) {
    // Keep the WebGL-specific wording; the generic handler below would
    // otherwise replace it in the one case where it is most useful.
    ui.showFallback("WebGL 2に対応した最新のブラウザで、ページを再読み込みしてください。");
    throw error;
  }
  const scene = createScene();
  const camera = createFixedCamera();
  const projection = createLocalProjection(CONFIG.geo);
  let city = null;
  let assets = null;
  let disposed = false;
  let contextLost = false;
  let pendingFrame = 0;

  try {
    ui.setLoading("都市データを読み込んでいます");
    assets = await loadAssets({
      onProgress({ state, completed, total }) {
        if (state === "loading") return;
        ui.setLoading(`都市データを準備しています ${completed}/${total}`);
      },
    });
    city = createCity(assets.data, projection, quality);
    scene.add(city.group);
  } catch (error) {
    renderer.dispose();
    renderer.domElement.remove();
    throw error;
  }

  const resizeAndRender = () => {
    if (disposed || contextLost || document.hidden) return;
    const viewport = viewportFor(ui.root);
    renderer.setPixelRatio(pixelRatioFor(quality));
    renderer.setSize(viewport.width, viewport.height, true);
    frameFixedCamera(camera, city.bounds, viewport);
    renderer.render(scene, camera);
    ui.setDebug(debugText({ quality, assets, city, renderer }));
  };

  const scheduleRender = () => {
    if (pendingFrame || disposed || contextLost) return;
    pendingFrame = window.requestAnimationFrame(() => {
      pendingFrame = 0;
      resizeAndRender();
    });
  };

  const onVisibility = () => {
    if (!document.hidden) scheduleRender();
  };
  const onContextLost = (event) => {
    event.preventDefault();
    contextLost = true;
    ui.showFallback("WebGLコンテキストが失われました。復旧を待っています。");
  };
  const onContextRestored = () => {
    contextLost = false;
    ui.hideFallback();
    ui.showReady();
    scheduleRender();
  };
  const onPageShow = () => scheduleRender();
  const onPageHide = (event) => {
    if (!event.persisted) dispose();
  };

  const resizeObserver = typeof ResizeObserver === "function"
    ? new ResizeObserver(scheduleRender)
    : null;
  resizeObserver?.observe(ui.root);
  window.addEventListener("resize", scheduleRender, { passive: true });
  window.addEventListener("orientationchange", scheduleRender, { passive: true });
  window.visualViewport?.addEventListener("resize", scheduleRender, { passive: true });
  window.addEventListener("pageshow", onPageShow);
  window.addEventListener("pagehide", onPageHide);
  document.addEventListener("visibilitychange", onVisibility);
  renderer.domElement.addEventListener("webglcontextlost", onContextLost, false);
  renderer.domElement.addEventListener("webglcontextrestored", onContextRestored, false);

  function dispose() {
    if (disposed) return;
    disposed = true;
    if (pendingFrame) window.cancelAnimationFrame(pendingFrame);
    resizeObserver?.disconnect();
    window.removeEventListener("resize", scheduleRender);
    window.removeEventListener("orientationchange", scheduleRender);
    window.visualViewport?.removeEventListener("resize", scheduleRender);
    window.removeEventListener("pageshow", onPageShow);
    window.removeEventListener("pagehide", onPageHide);
    document.removeEventListener("visibilitychange", onVisibility);
    renderer.domElement.removeEventListener("webglcontextlost", onContextLost);
    renderer.domElement.removeEventListener("webglcontextrestored", onContextRestored);
    city?.dispose();
    scene.clear();
    renderer.dispose();
    renderer.domElement.remove();
    ui.dispose();
  }

  resizeAndRender();
  const debugEnabled = new URLSearchParams(window.location.search).get(CONFIG.debug.queryParameter) === "1";
  ui.setDebugVisible(debugEnabled);
  ui.showReady();
}

const ui = createUI();
bootstrap(ui).catch((error) => {
  console.error("[unseen-city] Phase 2 initialization failed", error);
  if (!ui.isFallbackVisible()) {
    ui.showFallback("都市模型を初期化できませんでした。WebGLとデータ配信を確認してください。");
  }
});
