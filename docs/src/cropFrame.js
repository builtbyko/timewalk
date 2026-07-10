// 取得範囲を決める正方形のクロップ枠。カメラのファインダーのように、画面中央に
// 固定表示し、ユーザーは地図側を動かして枠に収める(枠自体は動かない)。

const FRAME_RATIO = 0.9; // 画面の短辺に対する比率

let frameEl;
let map;

export function initCropFrame(mapInstance) {
  map = mapInstance;
  frameEl = document.getElementById("crop-frame");
  const reposition = () => positionFrame();
  window.addEventListener("resize", reposition);
  map.on("resize", reposition);
  reposition();
}

function positionFrame() {
  const container = map.getContainer();
  const w = container.clientWidth;
  const h = container.clientHeight;
  const isMobile = window.matchMedia("(max-width: 640px)").matches;
  const reservedTop = isMobile ? 260 : 0;
  const reservedBottom = isMobile ? 150 : 0;
  const usableHeight = Math.max(180, h - reservedTop - reservedBottom);
  const size = Math.min(w, usableHeight) * FRAME_RATIO;
  const topBase = isMobile ? reservedTop + (usableHeight - size) / 2 : (h - size) / 2;
  frameEl.style.width = `${size}px`;
  frameEl.style.height = `${size}px`;
  frameEl.style.left = `${(w - size) / 2}px`;
  frameEl.style.top = `${topBase}px`;
}

export function setCropFrameVisible(visible) {
  frameEl.hidden = !visible;
}

// フレームの四隅を地理座標に変換し、取得bbox({w,s,e,n})を返す。
export function getCropFrameBounds() {
  const rect = frameEl.getBoundingClientRect();
  const containerRect = map.getContainer().getBoundingClientRect();
  const topLeft = map.unproject([rect.left - containerRect.left, rect.top - containerRect.top]);
  const bottomRight = map.unproject([rect.right - containerRect.left, rect.bottom - containerRect.top]);
  return {
    w: topLeft.lng,
    n: topLeft.lat,
    e: bottomRight.lng,
    s: bottomRight.lat,
  };
}
