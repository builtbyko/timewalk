import { searchCityNominatim, refineHubInBackground } from "./cityResolve.js";
import { setupOsmData } from "./osmData.js";
import { initCropFrame, setCropFrameVisible, getCropFrameBounds } from "./cropFrame.js";
import { FETCH_CATEGORY_IDS, LENS_SETS, LAYER_TOGGLES, ACCESS_TARGET_IDS } from "./layersConfig.js";
import { readStateFromUrl, writeStateToUrl } from "./state.js";
import { exportFeaturesToExcel, exportMapToPng } from "./export.js";
import { loadCatalogItems } from "./catalog.js";

const HUB_ZOOM = 15;
// 地図の移動は自由(取得範囲の安全弁はMIN_FETCH_ZOOMの取得ゲートが担う)。
const MAP_MIN_ZOOM = 4;

const LENS_MESSAGES = {
  place: "この街に、留まれる場所がどれだけあるか見てみましょう。",
  mobility: "この街は、歩いてまわれるでしょうか。",
  access: "公共交通で暮らせる街でしょうか。駅800m・バス停300mを徒歩圏の目安にしています。",
  car: "この街の土地が、どれだけ車のために使われているか見てみましょう。",
};

const map = new maplibregl.Map({
  container: "map",
  preserveDrawingBuffer: true, // PNG書き出しのため
  minZoom: MAP_MIN_ZOOM,
  attributionControl: false,
  style: {
    version: 8,
    sources: {
      "gsi-std": {
        type: "raster",
        tiles: ["https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "地理院タイル",
      },
      "gsi-photo": {
        type: "raster",
        tiles: ["https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{z}/{x}/{y}.jpg"],
        tileSize: 256,
        attribution: "地理院タイル(写真)",
      },
    },
    layers: [
      // デフォルトは航空写真(オーナー判断: 建物や街の構造が自明に見えるため)。
      { id: "gsi-photo", type: "raster", source: "gsi-photo" },
      { id: "gsi-std", type: "raster", source: "gsi-std", layout: { visibility: "none" } },
    ],
  },
  center: [139.7649, 35.6716], // 銀座四丁目交差点付近(初期表示のサンプル)
  zoom: HUB_ZOOM,
});

map.addControl(new maplibregl.NavigationControl(), "top-right");
map.addControl(
  new maplibregl.AttributionControl({
    compact: true,
    customAttribution:
      '地図データ © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>（ODbL）。参考情報であり法定図書の根拠にはなりません。',
  })
);

const photoNoteEl = document.getElementById("photo-note");
const basemapButtons = document.querySelectorAll(".basemap-btn");
for (const btn of basemapButtons) {
  btn.addEventListener("click", () => {
    const target = btn.dataset.basemap; // "std" | "photo"
    map.setLayoutProperty("gsi-std", "visibility", target === "std" ? "visible" : "none");
    map.setLayoutProperty("gsi-photo", "visibility", target === "photo" ? "visible" : "none");
    for (const b of basemapButtons) b.classList.toggle("active", b === btn);
    photoNoteEl.hidden = target !== "photo";
  });
}

const cityForm = document.getElementById("city-form");
const cityInput = document.getElementById("city-input");
const statusEl = document.getElementById("status-message");
const btnPlace = document.getElementById("btn-place");
const btnMobility = document.getElementById("btn-mobility");
const btnAccess = document.getElementById("btn-access");
const btnCar = document.getElementById("btn-car");
const loadingTextEl = document.getElementById("loading-text");
const lensMessageTextEl = document.getElementById("lens-message-text");
const btnExportExcel = document.getElementById("btn-export-excel");
const btnExportPng = document.getElementById("btn-export-png");
const loadingOverlayEl = document.getElementById("loading-overlay");
const btnFetch = document.getElementById("btn-fetch");
const zoomWarningOverlayEl = document.getElementById("zoom-warning-overlay");
const zoomWarningTextEl = document.getElementById("zoom-warning-text");
const btnReturnToHub = document.getElementById("btn-return-to-hub");
const catalogCheckboxesEl = document.getElementById("catalog-checkboxes");
const legendPanelEl = document.getElementById("legend-panel");
const legendEntriesEl = document.getElementById("legend-entries");
const overlayPanelEl = document.getElementById("overlay-panel");
const mobileMediaQuery = window.matchMedia("(max-width: 640px)");
const searchCardEl = document.getElementById("search-card");
const searchCardBodyEl = document.getElementById("search-card-body");
const searchCardToggleEl = document.getElementById("search-card-toggle");

let currentCity = "";
let suppressUrlSync = false;
let activeLensId = null;
let lastHubCenter = null;
let loadingCount = 0;
let userMovedSinceSearch = false;

map.on("movestart", (e) => {
  if (e.originalEvent) userMovedSinceSearch = true;
});
let osm = null; // setupOsmDataの戻り値
let catalogItemById = {};
const lensButtons = { place: btnPlace, mobility: btnMobility, access: btnAccess, car: btnCar };
const toggleCheckboxes = {}; // key -> checkbox要素

const LOADING_TEXT_SEARCH = "自治体を検索しています…";
const LOADING_TEXT_FETCH =
  "OSMからデータを取得しています…<br><small>範囲やデータ量により数秒〜数十秒かかることがあります</small>";
const LOADING_TEXT_FETCH_RETRY =
  "OSMからデータを取得しています…<br><small>2回目以降は混雑により時間がかかることがあります。しばらく動きがない場合は、タブを閉じて開き直してみてください。</small>";
let isRetryFetch = false;
const mobileUi = {
  controlsEl: null,
  layerToggleBtn: null,
  legendToggleBtn: null,
  overlayOpen: false,
  legendOpen: false,
};
const searchCardUi = {
  collapsed: false,
};

function isMobileLayout() {
  return mobileMediaQuery.matches;
}

function applySearchCardState() {
  const mobile = isMobileLayout();
  const collapsed = mobile && searchCardUi.collapsed;
  searchCardEl.classList.toggle("is-collapsed", collapsed);
  searchCardBodyEl.hidden = collapsed;
  searchCardToggleEl.hidden = !mobile;
  searchCardToggleEl.setAttribute("aria-expanded", collapsed ? "false" : "true");
  searchCardToggleEl.textContent = collapsed ? "ひらく" : "しまう";
}

function setSearchCardCollapsed(collapsed) {
  searchCardUi.collapsed = collapsed;
  applySearchCardState();
}

function ensureMobilePanelUi() {
  if (mobileUi.controlsEl) return;

  const controls = document.createElement("div");
  controls.className = "mobile-panel-toggles";
  controls.hidden = true;
  controls.innerHTML = `
    <button type="button" class="mobile-panel-toggle" data-target="layers">表示切替</button>
    <button type="button" class="mobile-panel-toggle" data-target="legend">凡例</button>
  `;
  overlayPanelEl.parentElement.appendChild(controls);

  const overlayHeader = document.createElement("div");
  overlayHeader.className = "overlay-panel-header";
  overlayHeader.innerHTML = `<h3>表示切替</h3><button type="button" class="panel-close-btn" aria-label="表示切替を閉じる">×</button>`;
  overlayPanelEl.prepend(overlayHeader);

  const legendHeader = document.createElement("div");
  legendHeader.className = "legend-panel-header";
  legendHeader.innerHTML = `<h3>凡例</h3><button type="button" class="panel-close-btn" aria-label="凡例を閉じる">×</button>`;
  legendPanelEl.prepend(legendHeader);

  mobileUi.controlsEl = controls;
  mobileUi.layerToggleBtn = controls.querySelector('[data-target="layers"]');
  mobileUi.legendToggleBtn = controls.querySelector('[data-target="legend"]');

  mobileUi.layerToggleBtn.addEventListener("click", () => {
    mobileUi.overlayOpen = !mobileUi.overlayOpen;
    if (mobileUi.overlayOpen) mobileUi.legendOpen = false;
    applyMobilePanelState();
  });
  mobileUi.legendToggleBtn.addEventListener("click", () => {
    mobileUi.legendOpen = !mobileUi.legendOpen;
    if (mobileUi.legendOpen) mobileUi.overlayOpen = false;
    applyMobilePanelState();
  });
  overlayHeader.querySelector(".panel-close-btn").addEventListener("click", () => {
    mobileUi.overlayOpen = false;
    applyMobilePanelState();
  });
  legendHeader.querySelector(".panel-close-btn").addEventListener("click", () => {
    mobileUi.legendOpen = false;
    applyMobilePanelState();
  });
}

function applyMobilePanelState() {
  ensureMobilePanelUi();

  const hasFetched = !!osm?.getFetchedBounds();
  const showControls = isMobileLayout() && hasFetched;
  mobileUi.controlsEl.hidden = !showControls;

  if (!isMobileLayout()) {
    overlayPanelEl.classList.remove("is-open");
    legendPanelEl.classList.remove("is-open");
    mobileUi.layerToggleBtn.classList.remove("is-active");
    mobileUi.legendToggleBtn.classList.remove("is-active");
    overlayPanelEl.hidden = false;
    if (osm?.hasData()) legendPanelEl.hidden = false;
    return;
  }

  overlayPanelEl.classList.toggle("is-open", showControls && mobileUi.overlayOpen);
  legendPanelEl.classList.toggle("is-open", showControls && mobileUi.legendOpen && !legendPanelEl.hidden);
  mobileUi.layerToggleBtn.classList.toggle("is-active", showControls && mobileUi.overlayOpen);
  mobileUi.legendToggleBtn.classList.toggle("is-active", showControls && mobileUi.legendOpen && !legendPanelEl.hidden);
  overlayPanelEl.hidden = false;
}

searchCardToggleEl.addEventListener("click", () => {
  setSearchCardCollapsed(!searchCardUi.collapsed);
});

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", isError);
}

function setLoading(delta, textHtml) {
  loadingCount = Math.max(0, loadingCount + delta);
  if (delta > 0 && textHtml) loadingTextEl.innerHTML = textHtml;
  loadingOverlayEl.hidden = loadingCount === 0;
  updateFetchButton();
}

// ---- 表示カテゴリの決定(レンズ+個別レイヤの合成) ----

function visibleCategories() {
  const set = new Set();
  if (activeLensId) {
    for (const id of LENS_SETS[activeLensId]) set.add(id);
  }
  for (const def of LAYER_TOGGLES) {
    if (toggleCheckboxes[def.key]?.checked) {
      for (const id of def.ids) set.add(id);
    }
  }
  return set;
}

function applyVisibility() {
  if (!osm) return;
  const visible = visibleCategories();
  const accessActive = activeLensId === "access";

  if (accessActive) {
    // アクセス性表示中は、対象要素(お出かけ先)は青/赤の色分けレイヤだけを見せ、
    // 通常色のレイヤは隠す(同じ地物が二重に描画されるのを避ける)。
    const accessOnly = new Set([...visible].filter((id) => ACCESS_TARGET_IDS.includes(id)));
    const normalOnly = new Set([...visible].filter((id) => !ACCESS_TARGET_IDS.includes(id)));
    osm.setVisibleCategories(normalOnly);
    osm.setAccessVisibleCategories(accessOnly);
  } else {
    osm.setVisibleCategories(visible);
    osm.setAccessVisibleCategories(new Set());
  }
  osm.setCirclesVisible(accessActive);
  updateLegend(visible);
  updateExportButtons(visible);
}

function updateExportButtons(visible = visibleCategories()) {
  const count = osm ? osm.getData().features.filter((f) => visible.has(f.properties._category)).length : 0;
  btnExportExcel.disabled = count === 0;
}

// ---- 凡例 ----

function swatchHtml(item) {
  if (item.render_type === "circle") {
    return `<span class="lg-swatch lg-circle" style="background:${item.style_draft["circle-color"]}"></span>`;
  }
  if (item.render_type === "line") {
    return `<span class="lg-swatch lg-line" style="background:${item.style_draft["line-color"]}"></span>`;
  }
  return `<span class="lg-swatch lg-fill" style="background:${item.style_draft["fill-color"]}"></span>`;
}

function updateLegend(visible = visibleCategories()) {
  const ids = FETCH_CATEGORY_IDS.filter((id) => visible.has(id));
  if (ids.length === 0 || !osm?.hasData()) {
    legendPanelEl.hidden = true;
    mobileUi.legendOpen = false;
    applyMobilePanelState();
    return;
  }
  const accessActive = activeLensId === "access";
  const accessIdsShown = accessActive ? ids.filter((id) => ACCESS_TARGET_IDS.includes(id)) : [];
  const normalIds = accessActive ? ids.filter((id) => !ACCESS_TARGET_IDS.includes(id)) : ids;

  const entries = normalIds.map((id) => {
    const item = catalogItemById[id];
    if (!item) return "";
    return `<div class="legend-entry">${swatchHtml(item)}<span>${item.label_ja}</span></div>`;
  });

  if (accessIdsShown.length > 0) {
    entries.push(
      `<div class="legend-entry"><span class="lg-swatch lg-circle" style="background:#2874a6"></span><span class="lg-swatch lg-circle" style="background:#c0392b"></span><span>お出かけ先(飲食店・カフェ・書店・神社仏閣・美術館等)</span></div>`
    );
  }
  if (accessActive) {
    entries.push(
      `<div class="legend-entry"><span class="lg-swatch lg-line" style="background:#2874a6"></span><span>徒歩圏(駅800m/バス停300m)</span></div>`,
      `<div class="legend-note">青=徒歩圏内 / 赤=圏外</div>`
    );
  }
  legendEntriesEl.innerHTML = entries.join("");
  legendPanelEl.hidden = false;
  applyMobilePanelState();
}

// ---- 取得ボタン ----

function viewOutsideFetched() {
  const f = osm?.getFetchedBounds();
  if (!f) return false;
  const cur = getCropFrameBounds();
  const w = f.e - f.w;
  const h = f.n - f.s;
  const tol = 0.05;
  return (
    cur.w < f.w - w * tol ||
    cur.e > f.e + w * tol ||
    cur.s < f.s - h * tol ||
    cur.n > f.n + h * tol
  );
}

function updateFetchButton() {
  if (!osm || loadingCount > 0) {
    btnFetch.hidden = true;
    setCropFrameVisible(false);
    applyMobilePanelState();
    return;
  }
  const hasFetched = !!osm.getFetchedBounds();
  // クロップ枠+薄灰色はデータ未取得のときだけ表示する。取得済みの範囲は固定であり、
  // 地図を動かしても再表示しない(別の市町村を検索したときだけキャンセルされる)。
  setCropFrameVisible(!hasFetched);

  if (!hasFetched) {
    btnFetch.textContent = "この範囲のOSMデータを取得";
    btnFetch.hidden = false;
    mobileUi.overlayOpen = false;
    mobileUi.legendOpen = false;
    applyMobilePanelState();
    return;
  }
  btnFetch.textContent = "この範囲でデータを再取得";
  btnFetch.hidden = !viewOutsideFetched();
  applyMobilePanelState();
}

// 2回目以降の取得は、ページ再読み込みでは速くならないと判明した(Overpass側の
// フェアユース制御が原因と推測される)ため、ページ内でそのまま待たせる。
// 代わりにローディング表示へフォールバック案内(LOADING_TEXT_FETCH_RETRY)を出す。
let hasFetchedOnce = false;

async function doFetch() {
  if (!osm) return;

  isRetryFetch = hasFetchedOnce;
  const ok = await osm.fetch();
  if (ok) {
    hasFetchedOnce = true;
    applyVisibility();
    overlayPanelEl.hidden = false;
    setSearchCardCollapsed(true);
    if (isMobileLayout()) {
      mobileUi.overlayOpen = false;
      mobileUi.legendOpen = false;
    }
  }
  updateFetchButton();
}

btnFetch.addEventListener("click", doFetch);

btnReturnToHub.addEventListener("click", () => {
  if (lastHubCenter) {
    map.jumpTo({ center: lastHubCenter, zoom: HUB_ZOOM });
  }
  zoomWarningOverlayEl.hidden = true;
});

// ---- レンズ(主張ボタン) ----

async function setLens(id) {
  if (activeLensId === id) {
    activeLensId = null;
    lensButtons[id].classList.remove("active");
    lensMessageTextEl.textContent = "";
  } else {
    if (activeLensId) lensButtons[activeLensId].classList.remove("active");
    activeLensId = id;
    lensButtons[id].classList.add("active");
    lensMessageTextEl.textContent = LENS_MESSAGES[id] || "";
  }
  applyVisibility();
  syncUrl();
  // データ未取得でボタンが押されたら、その場で取得を開始する(60秒動線)。
  if (activeLensId && osm && !osm.getFetchedBounds()) {
    await doFetch();
  }
}

// ---- 個別レイヤ(要素カタログ) ----

function buildCatalogCheckboxes() {
  for (const def of LAYER_TOGGLES) {
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    toggleCheckboxes[def.key] = checkbox;
    checkbox.addEventListener("change", async () => {
      applyVisibility();
      syncUrl();
      if (checkbox.checked && osm && !osm.getFetchedBounds()) {
        await doFetch();
      }
    });
    const swatchSpan = document.createElement("span");
    const item = catalogItemById[def.ids[0]];
    if (item) swatchSpan.innerHTML = swatchHtml(item);
    label.appendChild(checkbox);
    label.appendChild(swatchSpan.firstChild || swatchSpan);
    label.appendChild(document.createTextNode(def.label));
    catalogCheckboxesEl.appendChild(label);
  }
}

// ---- 初期化 ----

map.on("load", async () => {
  initCropFrame(map);
  ensureMobilePanelUi();
  applySearchCardState();

  const catalogItems = await loadCatalogItems();
  catalogItemById = Object.fromEntries(catalogItems.map((item) => [item.id, item]));

  osm = await setupOsmData(
    map,
    FETCH_CATEGORY_IDS,
    {
    onData: (fc) => {
      zoomWarningOverlayEl.hidden = true;
      const total = fc.features.length;
      lensMessageTextEl.textContent =
        total > 0
          ? `この範囲の候補データ${total}件を取得しました。ボタンやレイヤの切り替えは通信なしで即時です。`
          : "この範囲にはデータが見つかりませんでした。場所を変えて再取得してみてください。";
    },
    onError: (err) => {
      setStatus(`データ取得エラー: ${err.message}`, true);
    },
    onLoadingChange: (loading) => {
      setLoading(loading ? 1 : -1, isRetryFetch ? LOADING_TEXT_FETCH_RETRY : LOADING_TEXT_FETCH);
    },
    onZoomTooLow: (minZoom) => {
      zoomWarningTextEl.textContent = `表示範囲が広すぎます。もう少し拡大してから取得してください(目安: ズームレベル${minZoom}以上)。`;
      zoomWarningOverlayEl.hidden = false;
    },
    },
    getCropFrameBounds,
    ACCESS_TARGET_IDS
  );

  buildCatalogCheckboxes();

  btnPlace.addEventListener("click", () => setLens("place"));
  btnMobility.addEventListener("click", () => setLens("mobility"));
  btnAccess.addEventListener("click", () => setLens("access"));
  btnCar.addEventListener("click", () => setLens("car"));

  const initial = readStateFromUrl();
  suppressUrlSync = true;
  if (initial.bbox) {
    map.fitBounds(
      [
        [initial.bbox[0], initial.bbox[1]],
        [initial.bbox[2], initial.bbox[3]],
      ],
      { animate: false }
    );
  }
  if (initial.city) {
    cityInput.value = initial.city;
    currentCity = initial.city;
  }
  if (initial.lens && LENS_SETS[initial.lens]) {
    activeLensId = initial.lens;
    lensButtons[initial.lens].classList.add("active");
    lensMessageTextEl.textContent = LENS_MESSAGES[initial.lens] || "";
  }
  for (const key of initial.layers) {
    if (toggleCheckboxes[key]) toggleCheckboxes[key].checked = true;
  }
  applyVisibility();
  updateFetchButton();
  suppressUrlSync = false;
});

// ---- 市名検索 ----

cityForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = cityInput.value.trim();
  if (!name) return;
  setStatus(`「${name}」を検索中...`);
  setLoading(1, LOADING_TEXT_SEARCH);
  try {
    const { center, bounds, displayName } = await searchCityNominatim(name);
    currentCity = name;
    osm.clear(); // 前の街のデータは持ち越さない(取得はユーザーのボタン操作で)
    overlayPanelEl.hidden = true; // 取得前はボタン類を出さない(取得後に現れる)
    mobileUi.overlayOpen = false;
    mobileUi.legendOpen = false;
    setSearchCardCollapsed(true);
    userMovedSinceSearch = false;
    lastHubCenter = center;
    map.jumpTo({ center, zoom: HUB_ZOOM });
    setStatus(`「${displayName}」に移動しました。範囲を調整して「この範囲のOSMデータを取得」を押してください。`);
    applyVisibility();
    updateFetchButton();
    syncUrl();

    // 主要駅の推定は重いOverpass処理のため裏で行い、ユーザーがまだ地図を
    // 操作していなければ静かに寄せる(操作済みなら意図を尊重して何もしない)。
    refineHubInBackground(bounds)
      .then((refined) => {
        if (refined?.center && !userMovedSinceSearch) {
          lastHubCenter = refined.center;
          map.jumpTo({ center: refined.center, zoom: HUB_ZOOM });
          if (refined.stationName) {
            setStatus(
              `「${refined.stationName}」を中心に表示しています(駅周辺の商業集積から主要駅を推定)。範囲を調整して「この範囲のOSMデータを取得」を押してください。`
            );
          }
        }
      })
      .catch(() => {
        // 背景推定の失敗は致命的ではない(初期ジャンプは既に完了しているため)
      });
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    setLoading(-1);
  }
});

// ---- 書き出し(表示中のカテゴリのみ) ----

function visibleFeatures() {
  const visible = visibleCategories();
  const features = osm ? osm.getData().features.filter((f) => visible.has(f.properties._category)) : [];
  return { type: "FeatureCollection", features };
}

btnExportExcel.addEventListener("click", () => {
  exportFeaturesToExcel(visibleFeatures(), `${currentCity || "read-my-city"}_${activeLensId || "layers"}.xlsx`).catch((err) => {
    setStatus(`Excel書き出しに失敗しました: ${err.message}`, true);
  });
});

btnExportPng.addEventListener("click", () => {
  exportMapToPng(map, `${currentCity || "read-my-city"}_${activeLensId || "map"}.png`);
});

// ---- 状態付きURL ----

function syncUrl() {
  if (suppressUrlSync) return;
  const b = map.getBounds();
  const activeLayerKeys = LAYER_TOGGLES.filter((def) => toggleCheckboxes[def.key]?.checked).map((def) => def.key);
  writeStateToUrl({
    city: currentCity,
    lens: activeLensId || "",
    layers: activeLayerKeys,
    bbox: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()],
    zoom: map.getZoom(),
  });
}

map.on("moveend", () => {
  if (currentCity) syncUrl();
  updateFetchButton();
});

mobileMediaQuery.addEventListener("change", () => {
  if (!isMobileLayout()) {
    mobileUi.overlayOpen = false;
    mobileUi.legendOpen = false;
    searchCardUi.collapsed = false;
  }
  updateFetchButton();
  applySearchCardState();
});
