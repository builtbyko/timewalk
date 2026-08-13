export const DATASETS = Object.freeze({
  roads: "./data/roads.geojson",
  rail: "./data/railways.geojson",
  waterways: "./data/historic-waterways-reference.geojson",
  buildings: "./data/buildings.geojson",
});

export const QUALITY_PROFILES = Object.freeze({
  high: Object.freeze({
    tier: "high",
    maxDpr: 1.75,
    antialias: true,
    maxBuildings: 9000,
    maxBuildingVertices: 1800,
  }),
  medium: Object.freeze({
    tier: "medium",
    maxDpr: 1.35,
    antialias: true,
    maxBuildings: 1800,
    maxBuildingVertices: 1200,
  }),
  low: Object.freeze({
    tier: "low",
    maxDpr: 1,
    antialias: false,
    maxBuildings: 1000,
    maxBuildingVertices: 700,
  }),
});

export const CONFIG = Object.freeze({
  data: DATASETS,
  geo: Object.freeze({
    // Local display projection around Ginza. One world unit equals 10 m.
    center: Object.freeze([139.7655, 35.67]),
    metersPerUnit: 10,
  }),
  renderer: Object.freeze({
    exposure: 3.1,
    powerPreference: "high-performance",
  }),
  scene: Object.freeze({
    // Background and fog share one colour so the far edge of the model has no
    // horizon line to give it away.
    background: 0x081220,
    fog: 0x081220,
    fogDensity: 0.0092,
  }),
  palette: Object.freeze({
    ground: 0x0a1524,
    buildings: 0x1e2f42,
    roads: 0x5c6f83,
    rail: 0x9aa3b4,
    // Former waterways read as past time, not as present water. Amber keeps
    // them from being mistaken for an official channel or a live river.
    waterways: 0x6d4f2c,
    // The point field is the city before it has form; cooler and dimmer than
    // the roads it becomes.
    points: 0x8fa6bd,
    skyLight: 0x9aacbf,
    groundLight: 0x050d1a,
    keyLight: 0xc8d8e4,
  }),
  lights: Object.freeze({
    // Ambient stays low and the key stays strong so building faces separate by
    // shading rather than by outline.
    hemisphereIntensity: 0.78,
    keyIntensity: 2.9,
    keyPosition: Object.freeze([90, 150, 70]),
  }),
  model: Object.freeze({
    defaultExtent: 190,
    minGroundExtent: 20,
    // The plane runs well past the data so its rectangular edge never reads as
    // the edge of the city; fog absorbs it long before it becomes visible.
    groundPadding: 1.4,
    groundY: -0.16,
    waterY: -0.02,
    roadY: 0.035,
    railY: 0.08,
    buildingBaseY: 0,
    defaultBuildingHeightMeters: 15,
    floorHeightMeters: 3.2,
    minBuildingHeightMeters: 4,
    maxBuildingHeightMeters: 140,
    roadWidthMeters: Object.freeze({
      motorway: 18,
      trunk: 15,
      primary: 12,
      secondary: 9,
      tertiary: 7,
      default: 6,
    }),
    railWidthMeters: 2.2,
    waterwayWidthMeters: 18,
  }),
  camera: Object.freeze({
    desktopFov: 34,
    mobileFov: 39,
    // A lower vertical component keeps the ground plane oblique so the model
    // reads as a city seen from inside it, not as a table-top plan.
    direction: Object.freeze([0.92, 0.56, 1]),
    // Padding below 1 lets the near blocks run past the frame edge, so the
    // city continues off-screen instead of sitting on a visible slab.
    desktopPadding: 0.82,
    portraitPadding: 0.88,
    // A narrow viewport fits the model's width only by retreating far enough
    // that fog swallows it, so portrait frames a slice instead of the whole.
    portraitCrop: 0.34,
    desktopHorizontalShift: 0.12,
    targetHeightRatio: 0.16,
    // Distance ceiling expressed in fog e-folding lengths; the camera never
    // retreats past `fogVisibilityLimit / fogDensity`. Raise it and near-square
    // viewports fade out, lower it and wide ones crop harder.
    fogVisibilityLimit: 1.24,
    // Act 2 swings towards a low oblique so the ground is read edge-on. Fully
    // level would hide everything that drops below the slab, so it keeps
    // enough lift to see down the stack.
    sideDirection: Object.freeze([0.99, 0.34, 0.62]),
    // Once the layers separate the subject is a tall stack, so the camera
    // looks down it rather than at the surface alone.
    strataTargetDrop: 0.46,
    strataDistanceScale: 1.3,
  }),
  sequence: Object.freeze({
    // Length measured in viewport heights, so the reading pace is the same on
    // a phone and a desktop instead of tracking a pixel count.
    scrollViewports: 5,
    // Stage ends as a fraction of the whole, carried over from the second
    // budget in the experience notes: 2.5 / 2.5 / 3 / 4 / 3.5 / 5.5 of 21.
    stageEnds: Object.freeze({
      darkness: 0.119,
      points: 0.238,
      lines: 0.381,
      buildings: 0.571,
      side: 0.738,
      strata: 1,
    }),
    // Fraction of the building stage a single building spends growing. The
    // rest of that stage is the wave travelling from the centre outwards.
    buildingWave: 0.42,
    // Points hold a low glow through the darkness so the space reads as deep
    // rather than empty before anything is legible.
    darknessPointOpacity: 0.16,
    // The very first frame still has to show something. The experience notes
    // put a few points at the threshold of perception, and a truly black
    // landing state reads as a page that failed to load.
    thresholdPointOpacity: 0.055,
    thresholdPointReveal: 0.035,
    // Lines take over as the subject; the points stay only as a faint trace.
    residualPointOpacity: 0.3,
    pointSizePx: 2.3,
    mobilePointSizePx: 1.7,
    // Camera pulls in over the act. 1 is the Phase 2 framing.
    startDistanceScale: 1.32,
    startHeightScale: 1.14,
    // prefers-reduced-motion snaps here instead of interpolating: darkness,
    // the line network, the finished city, and the separated layers.
    reducedMotionStops: Object.freeze([0, 0.31, 0.571, 1]),
  }),
  strata: Object.freeze({
    // World units, and presentation only. These gaps say "different kind of
    // thing", never "this many metres down"; the credit line on screen has to
    // keep saying so.
    // The slab is around 170 units across, so the gaps have to be tens of
    // units before the stack reads as separate layers rather than a crust.
    railDrop: 30,
    pastDrop: 62,
    // The ground stops being a plane and becomes a slab, so stage 5 has a
    // thickness to discover from the side.
    slabThickness: 2.2,
    // In Act 1 the slab runs far past the data so its edge dies in fog. Act 2
    // needs the opposite: it contracts to roughly the city footprint so the
    // edge can be read, and so the layers below are not hidden under it.
    slabContractTo: 0.3,
  }),
  loading: Object.freeze({ timeoutMs: 15000 }),
  debug: Object.freeze({ queryParameter: "debug" }),
});
