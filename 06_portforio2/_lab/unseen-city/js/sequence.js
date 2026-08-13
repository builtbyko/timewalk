import { CONFIG } from "./config.js";

const STAGE_ORDER = ["darkness", "points", "lines", "buildings", "side", "strata"];

function clamp01(value) {
  return value < 0 ? 0 : value > 1 ? 1 : value;
}

// Ease that starts and ends still. Linear reveals read as a machine playing
// back, which the visual rules warn against.
function smooth(value) {
  const t = clamp01(value);
  return t * t * (3 - 2 * t);
}

function stageProgress(progress, stage) {
  const ends = CONFIG.sequence.stageEnds;
  const index = STAGE_ORDER.indexOf(stage);
  const start = index === 0 ? 0 : ends[STAGE_ORDER[index - 1]];
  const end = ends[stage];
  if (end <= start) return progress >= end ? 1 : 0;
  return clamp01((progress - start) / (end - start));
}

export function currentStage(progress) {
  for (const stage of STAGE_ORDER) {
    if (progress < CONFIG.sequence.stageEnds[stage]) return stage;
  }
  return STAGE_ORDER[STAGE_ORDER.length - 1];
}

/**
 * Maps Act 1 scroll progress to the reveal state of every layer.
 * Returns plain numbers so the renderer stays free of sequencing rules.
 */
export function evaluateSequence(progress) {
  const p = clamp01(progress);
  const seq = CONFIG.sequence;

  const darkness = stageProgress(p, "darkness");
  const points = stageProgress(p, "points");
  const lines = stageProgress(p, "lines");
  const buildings = stageProgress(p, "buildings");
  const side = stageProgress(p, "side");
  const strata = stageProgress(p, "strata");

  // Points exist from the first frame but only as a threshold glow, then take
  // the screen, then step back once the lines carry the reading.
  const pointOpacity = p < CONFIG.sequence.stageEnds.darkness
    ? seq.thresholdPointOpacity + smooth(darkness) * (seq.darknessPointOpacity - seq.thresholdPointOpacity)
    : p < CONFIG.sequence.stageEnds.points
      ? seq.darknessPointOpacity + smooth(points) * (1 - seq.darknessPointOpacity)
      : 1 - smooth(lines) * (1 - seq.residualPointOpacity);

  // How much of the point field has arrived, centre first.
  const pointReveal = p < CONFIG.sequence.stageEnds.darkness
    ? seq.thresholdPointReveal + smooth(darkness) * (0.12 - seq.thresholdPointReveal)
    : 0.12 + smooth(points) * 0.88;

  return {
    progress: p,
    stage: currentStage(p),
    pointReveal: clamp01(pointReveal),
    pointOpacity: clamp01(pointOpacity) * (buildings > 0 ? 1 - smooth(buildings) : 1),
    lineReveal: smooth(lines),
    buildingGrow: smooth(buildings),
    // How far the camera has swung round to read the ground edge-on.
    sideT: smooth(side),
    // How far the layers have pulled apart.
    strataT: smooth(strata),
    // Camera closes in over the forming stages only. Act 2 moves the camera
    // through sideT and strataT instead, so this stops advancing at the point
    // the city is finished.
    cameraT: smooth(Math.min(1, p / CONFIG.sequence.stageEnds.buildings)),
  };
}

export function snapProgressForReducedMotion(progress) {
  const stops = CONFIG.sequence.reducedMotionStops;
  let nearest = stops[0];
  let best = Infinity;
  for (const stop of stops) {
    const distance = Math.abs(stop - progress);
    if (distance < best) {
      best = distance;
      nearest = stop;
    }
  }
  return nearest;
}
