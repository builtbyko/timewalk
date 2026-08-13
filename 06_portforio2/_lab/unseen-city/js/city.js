import * as THREE from "../vendor/three.module.js";
import { CONFIG } from "./config.js";
import { forEachLineString, forEachPolygon, numericMeters } from "./geo.js";

const MAJOR_ROADS = new Set(["motorway", "trunk", "primary", "secondary", "tertiary"]);
// Narrow screens keep only the axes that carry the composition.
const MOBILE_ROADS = new Set(["motorway", "trunk", "primary"]);
const INACTIVE_RAIL = new Set(["abandoned", "disused", "razed", "construction", "proposed"]);

function pushTriangle(target, a, b, c, y) {
  target.push(a[0], y, a[1], b[0], y, b[1], c[0], y, c[1]);
}

function pushRibbonSegment(target, alongs, a, b, width, y, alongA, alongB) {
  const dx = b[0] - a[0];
  const dz = b[1] - a[1];
  const length = Math.hypot(dx, dz);
  if (length < 0.0001) return false;
  const half = width * 0.5;
  const px = (-dz / length) * half;
  const pz = (dx / length) * half;
  const aPlus = [a[0] + px, a[1] + pz];
  const aMinus = [a[0] - px, a[1] - pz];
  const bPlus = [b[0] + px, b[1] + pz];
  const bMinus = [b[0] - px, b[1] - pz];
  pushTriangle(target, aPlus, bPlus, aMinus, y);
  pushTriangle(target, aMinus, bPlus, bMinus, y);
  // Same vertex order as the two triangles above.
  alongs.push(alongA, alongB, alongA, alongA, alongB, alongB);
  return true;
}

// Draws each line from its own start towards its end, so stage 3 reads as the
// points joining up rather than a second layer fading in over them.
function attachRibbonReveal(material, uniforms) {
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uReveal = uniforms.reveal;
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nattribute float aAlong;\nvarying float vAlong;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvAlong = aAlong;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nuniform float uReveal;\nvarying float vAlong;")
      .replace(
        "#include <dithering_fragment>",
        "#include <dithering_fragment>\nfloat edge = smoothstep(uReveal, uReveal - 0.035, vAlong);\nif (edge <= 0.0) discard;\ngl_FragColor.a *= edge;",
      );
  };
  material.needsUpdate = true;
}

function createRibbonLayer(collection, projection, options) {
  const positions = [];
  const alongs = [];
  const features = new Set();
  let segments = 0;
  let skipped = 0;

  forEachLineString(collection, (coordinates, properties, feature) => {
    if (!options.filter(properties)) {
      skipped += 1;
      return;
    }
    const widthMeters = options.widthMeters(properties);
    const width = Math.max(0.04, widthMeters / projection.metersPerUnit);

    const points = [];
    for (const coordinate of coordinates || []) {
      const projected = projection.project(coordinate);
      if (projected) points.push(projected);
    }
    if (points.length < 2) return;

    // Normalised distance along this feature, so every line finishes drawing
    // at the same progress regardless of how long it is.
    const cumulative = [0];
    for (let index = 1; index < points.length; index += 1) {
      const previous = points[index - 1];
      const current = points[index];
      cumulative.push(cumulative[index - 1] + Math.hypot(current[0] - previous[0], current[1] - previous[1]));
    }
    const total = cumulative[cumulative.length - 1] || 1;

    for (let index = 1; index < points.length; index += 1) {
      const drawn = pushRibbonSegment(
        positions,
        alongs,
        points[index - 1],
        points[index],
        width,
        options.y,
        cumulative[index - 1] / total,
        cumulative[index] / total,
      );
      if (drawn) {
        segments += 1;
        features.add(feature);
      }
    }

    if (options.vertexSink) {
      for (const point of points) options.vertexSink.push(point[0], options.y, point[1]);
    }
  });

  if (positions.length === 0) return { object: null, features: 0, segments, skipped };
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("aAlong", new THREE.Float32BufferAttribute(alongs, 1));
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
  const material = new THREE.MeshStandardMaterial({
    color: options.color,
    roughness: options.roughness ?? 0.82,
    metalness: options.metalness ?? 0,
    transparent: true,
    opacity: options.opacity,
    depthWrite: options.opacity >= 1,
  });
  attachRibbonReveal(material, options.uniforms);
  const object = new THREE.Mesh(geometry, material);
  object.name = options.name;
  object.renderOrder = options.renderOrder;
  return { object, features: features.size, segments, skipped };
}

// The point field is the same vertices the ribbons are built from, so stage 3
// joins points that were always the line, rather than swapping one layer for
// another.
function createPointField(vertices, quality, uniforms) {
  if (vertices.length < 3) return { object: null, count: 0 };

  const count = vertices.length / 3;
  let minX = Infinity;
  let maxX = -Infinity;
  let minZ = Infinity;
  let maxZ = -Infinity;
  for (let index = 0; index < count; index += 1) {
    const x = vertices[index * 3];
    const z = vertices[index * 3 + 2];
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (z < minZ) minZ = z;
    if (z > maxZ) maxZ = z;
  }
  const centreX = (minX + maxX) * 0.5;
  const centreZ = (minZ + maxZ) * 0.5;
  const reach = Math.max(1e-4, Math.hypot(maxX - centreX, maxZ - centreZ));

  // Order by distance from the centre so the field resolves outwards from the
  // densest part instead of appearing all at once.
  const order = new Float32Array(count);
  for (let index = 0; index < count; index += 1) {
    const dx = vertices[index * 3] - centreX;
    const dz = vertices[index * 3 + 2] - centreZ;
    order[index] = Math.min(1, Math.hypot(dx, dz) / reach);
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
  geometry.setAttribute("aOrder", new THREE.Float32BufferAttribute(order, 1));
  geometry.computeBoundingSphere();

  const material = new THREE.PointsMaterial({
    color: CONFIG.palette.points,
    size: quality.mobileLayout ? CONFIG.sequence.mobilePointSizePx : CONFIG.sequence.pointSizePx,
    sizeAttenuation: false,
    transparent: true,
    opacity: 0,
    depthWrite: false,
    fog: true,
  });
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uReveal = uniforms.pointReveal;
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nattribute float aOrder;\nuniform float uReveal;\nvarying float vShow;")
      .replace(
        "#include <begin_vertex>",
        "#include <begin_vertex>\nvShow = 1.0 - smoothstep(uReveal - 0.06, uReveal, aOrder);",
      )
      .replace("gl_PointSize = size;", "gl_PointSize = size * vShow;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nvarying float vShow;")
      .replace(
        "#include <dithering_fragment>",
        "#include <dithering_fragment>\nif (vShow <= 0.0) discard;\ngl_FragColor.a *= vShow;",
      );
  };

  const object = new THREE.Points(geometry, material);
  object.name = "point-field";
  object.renderOrder = 5;
  return { object, count };
}

// Buildings grow out of the ground in a wave travelling from the centre. The
// delay is derived from position, never random, so a frame can be reproduced.
function attachBuildingGrowth(material, uniforms) {
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uGrow = uniforms.buildingGrow;
    shader.uniforms.uWave = uniforms.buildingWave;
    shader.vertexShader = shader.vertexShader
      .replace(
        "#include <common>",
        "#include <common>\nattribute float aDelay;\nuniform float uGrow;\nuniform float uWave;\nvarying float vGrow;",
      )
      .replace(
        "#include <begin_vertex>",
        [
          "#include <begin_vertex>",
          "float grow = clamp((uGrow - aDelay) / max(uWave, 0.0001), 0.0, 1.0);",
          "grow = grow * grow * (3.0 - 2.0 * grow);",
          "vGrow = grow;",
          // Base vertices sit at y = 0, so scaling keeps them pinned to the
          // ground while the roof rises to its real height.
          "transformed.y *= grow;",
        ].join("\n"),
      );
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nvarying float vGrow;")
      .replace("#include <dithering_fragment>", "#include <dithering_fragment>\nif (vGrow <= 0.002) discard;");
  };
  material.needsUpdate = true;
}

function parseRoadClass(properties) {
  const highway = String(properties.highway || properties.class || "").toLowerCase();
  return highway.split(";")[0].replace(/_link$/, "");
}

function roadWidth(properties) {
  const explicit = numericMeters(properties.width);
  if (explicit && explicit > 0) return THREE.MathUtils.clamp(explicit, 3, 24);
  const roadClass = parseRoadClass(properties);
  return CONFIG.model.roadWidthMeters[roadClass] || CONFIG.model.roadWidthMeters.default;
}

function railwayIsVisible(properties) {
  const status = String(properties.status || properties.railway || "").toLowerCase();
  return !INACTIVE_RAIL.has(status);
}

function lineWidth(properties, fallback) {
  const explicit = numericMeters(properties.width);
  return explicit && explicit > 0 ? THREE.MathUtils.clamp(explicit, 1, 80) : fallback;
}

function normalizeRing(ring, projection, maxVertices) {
  const projected = [];
  for (const coordinate of ring || []) {
    const point = projection.project(coordinate);
    if (!point) continue;
    const prior = projected[projected.length - 1];
    if (!prior || Math.hypot(prior[0] - point[0], prior[1] - point[1]) > 0.0001) projected.push(point);
  }
  if (projected.length > 1) {
    const first = projected[0];
    const last = projected[projected.length - 1];
    if (Math.hypot(first[0] - last[0], first[1] - last[1]) < 0.0001) projected.pop();
  }
  if (projected.length < 3 || projected.length > maxVertices) return null;
  return projected;
}

function buildingHeight(properties) {
  const displayHeight = numericMeters(properties.display_height_m);
  const explicit = numericMeters(
    properties.source_height_m ?? properties.height ?? properties["building:height"],
  );
  const levels = numericMeters(
    properties.source_levels ?? properties.levels ?? properties["building:levels"],
  );
  const roofLevels = numericMeters(properties["roof:levels"]) || 0;
  const estimate = levels && levels > 0
    ? (levels + roofLevels * 0.65) * CONFIG.model.floorHeightMeters
    : CONFIG.model.defaultBuildingHeightMeters;
  return THREE.MathUtils.clamp(
    displayHeight && displayHeight > 0 ? displayHeight : (explicit && explicit > 0 ? explicit : estimate),
    CONFIG.model.minBuildingHeightMeters,
    CONFIG.model.maxBuildingHeightMeters,
  );
}

function pushTopFace(positions, a, b, c, height) {
  const cross = (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
  if (cross > 0) {
    pushTriangle(positions, [a.x, a.y], [c.x, c.y], [b.x, b.y], height);
  } else {
    pushTriangle(positions, [a.x, a.y], [b.x, b.y], [c.x, c.y], height);
  }
}

function appendBuilding(positions, polygon, properties, projection, quality) {
  const rings = [];
  for (const ring of polygon || []) {
    const normalized = normalizeRing(ring, projection, quality.maxBuildingVertices);
    if (normalized) rings.push(normalized);
  }
  if (!rings.length) return false;

  const contour = rings[0].map(([x, z]) => new THREE.Vector2(x, z));
  const holes = rings.slice(1).map((ring) => ring.map(([x, z]) => new THREE.Vector2(x, z)));
  const flattened = [...contour, ...holes.flat()];
  let faces;
  try {
    faces = THREE.ShapeUtils.triangulateShape(contour, holes);
  } catch {
    return false;
  }
  if (!faces.length) return false;

  const height = buildingHeight(properties) / projection.metersPerUnit;
  const base = CONFIG.model.buildingBaseY;
  for (const [ia, ib, ic] of faces) {
    pushTopFace(positions, flattened[ia], flattened[ib], flattened[ic], height);
  }

  for (const ring of rings) {
    for (let index = 0; index < ring.length; index += 1) {
      const a = ring[index];
      const b = ring[(index + 1) % ring.length];
      positions.push(
        a[0], base, a[1], b[0], base, b[1], b[0], height, b[1],
        a[0], base, a[1], b[0], height, b[1], a[0], height, a[1],
      );
    }
  }
  return true;
}

function createBuildings(collection, projection, quality, uniforms) {
  const candidates = [];
  forEachPolygon(collection, (polygon, properties) => candidates.push({ polygon, properties }));
  const limit = Math.min(candidates.length, quality.maxBuildings);
  const positions = [];
  const spans = [];
  let built = 0;
  let invalid = 0;

  for (let selected = 0; selected < limit; selected += 1) {
    const index = candidates.length <= limit
      ? selected
      : Math.min(candidates.length - 1, Math.floor((selected * candidates.length) / limit));
    const start = positions.length;
    if (appendBuilding(positions, candidates[index].polygon, candidates[index].properties, projection, quality)) {
      built += 1;
      spans.push({ start, end: positions.length });
    } else {
      invalid += 1;
    }
  }

  if (!positions.length) {
    return { object: null, candidates: candidates.length, built, invalid, thinned: candidates.length - limit };
  }

  // One delay per building, shared by all of its vertices, measured from the
  // centre of the whole model outwards.
  const vertexCount = positions.length / 3;
  const delays = new Float32Array(vertexCount);
  const centres = spans.map((span) => {
    let sumX = 0;
    let sumZ = 0;
    const points = (span.end - span.start) / 3;
    for (let offset = span.start; offset < span.end; offset += 3) {
      sumX += positions[offset];
      sumZ += positions[offset + 2];
    }
    return { span, x: sumX / points, z: sumZ / points };
  });
  let minX = Infinity;
  let maxX = -Infinity;
  let minZ = Infinity;
  let maxZ = -Infinity;
  for (const centre of centres) {
    if (centre.x < minX) minX = centre.x;
    if (centre.x > maxX) maxX = centre.x;
    if (centre.z < minZ) minZ = centre.z;
    if (centre.z > maxZ) maxZ = centre.z;
  }
  const originX = (minX + maxX) * 0.5;
  const originZ = (minZ + maxZ) * 0.5;
  const reach = Math.max(1e-4, Math.hypot(maxX - originX, maxZ - originZ));
  // Leave room for the growth itself so the outermost building still finishes.
  const spread = Math.max(0, 1 - CONFIG.sequence.buildingWave);
  for (const centre of centres) {
    const normalized = Math.min(1, Math.hypot(centre.x - originX, centre.z - originZ) / reach);
    const delay = normalized * spread;
    for (let offset = centre.span.start; offset < centre.span.end; offset += 3) {
      delays[offset / 3] = delay;
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("aDelay", new THREE.Float32BufferAttribute(delays, 1));
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  const material = new THREE.MeshStandardMaterial({
    color: CONFIG.palette.buildings,
    roughness: 0.78,
    metalness: 0.08,
    flatShading: true,
    side: THREE.DoubleSide,
  });
  attachBuildingGrowth(material, uniforms);
  const object = new THREE.Mesh(geometry, material);
  object.name = "buildings";
  object.renderOrder = 4;
  return { object, candidates: candidates.length, built, invalid, thinned: candidates.length - limit };
}

function modelBounds(group) {
  const bounds = new THREE.Box3().setFromObject(group);
  if (!bounds.isEmpty()) return bounds;
  const half = CONFIG.model.defaultExtent * 0.5;
  return new THREE.Box3(new THREE.Vector3(-half, 0, -half), new THREE.Vector3(half, 12, half));
}

function createGround(bounds) {
  const size = bounds.getSize(new THREE.Vector3());
  const center = bounds.getCenter(new THREE.Vector3());
  const width = Math.max(
    CONFIG.model.minGroundExtent,
    size.x * (1 + CONFIG.model.groundPadding * 2),
  );
  const depth = Math.max(
    CONFIG.model.minGroundExtent,
    size.z * (1 + CONFIG.model.groundPadding * 2),
  );
  // A slab rather than a plane: stage 5 turns to the side to discover that the
  // ground has a thickness, which a flat plane cannot show.
  const thickness = CONFIG.strata.slabThickness;
  const geometry = new THREE.BoxGeometry(width, thickness, depth);
  const material = new THREE.MeshStandardMaterial({
    color: CONFIG.palette.ground,
    roughness: 0.96,
    metalness: 0.02,
  });
  const ground = new THREE.Mesh(geometry, material);
  ground.name = "city-ground";
  // Top face sits where the plane used to, so nothing above it moves.
  ground.position.set(center.x, CONFIG.model.groundY - thickness * 0.5, center.z);
  ground.renderOrder = 0;
  return ground;
}

export function createCity(data, projection, quality) {
  const group = new THREE.Group();
  group.name = "phase-2-city";

  // Shared by every layer so one sequence state drives the whole model.
  // Defaults are the finished city, which keeps the still frame unchanged for
  // anything that never applies a sequence.
  const uniforms = {
    reveal: { value: 1 },
    pointReveal: { value: 1 },
    buildingGrow: { value: 1 },
    buildingWave: { value: CONFIG.sequence.buildingWave },
  };
  const vertexSink = [];

  // A narrow screen keeps the main axes and drops the smaller classes, rather
  // than thinning the point field that stage 2 depends on.
  const roadClasses = quality.mobileLayout ? MOBILE_ROADS : MAJOR_ROADS;

  const roads = createRibbonLayer(data.roads, projection, {
    name: "major-roads",
    color: CONFIG.palette.roads,
    opacity: 0.72,
    roughness: 0.88,
    y: CONFIG.model.roadY,
    renderOrder: 2,
    filter: (properties) => {
      const roadClass = parseRoadClass(properties);
      return roadClass ? roadClasses.has(roadClass) : true;
    },
    widthMeters: roadWidth,
    uniforms,
    vertexSink,
  });
  const waterways = createRibbonLayer(data.waterways, projection, {
    name: "waterways",
    color: CONFIG.palette.waterways,
    opacity: 0.94,
    roughness: 0.42,
    metalness: 0.08,
    y: CONFIG.model.waterY,
    renderOrder: 1,
    filter: () => true,
    widthMeters: (properties) => lineWidth(properties, CONFIG.model.waterwayWidthMeters),
    uniforms,
    vertexSink,
  });
  const rail = createRibbonLayer(data.rail, projection, {
    name: "rail-network-reference",
    color: CONFIG.palette.rail,
    opacity: 0.86,
    roughness: 0.6,
    metalness: 0.14,
    y: CONFIG.model.railY,
    renderOrder: 3,
    filter: railwayIsVisible,
    widthMeters: (properties) => lineWidth(properties, CONFIG.model.railWidthMeters),
    uniforms,
    vertexSink,
  });
  const buildings = createBuildings(data.buildings, projection, quality, uniforms);
  const points = createPointField(vertexSink, quality, uniforms);

  // Grouped by what each layer means, because that is the axis stage 6
  // separates along. Present surface stays put; the rest drop away from it.
  const surface = new THREE.Group();
  surface.name = "present-surface";
  const railLayer = new THREE.Group();
  railLayer.name = "rail-layer";
  const past = new THREE.Group();
  past.name = "past-layer";

  for (const layer of [roads.object, buildings.object, points.object]) {
    if (layer) surface.add(layer);
  }
  if (rail.object) railLayer.add(rail.object);
  if (waterways.object) past.add(waterways.object);
  group.add(surface, railLayer, past);

  const contentBounds = modelBounds(group);
  const ground = createGround(contentBounds);
  surface.add(ground);

  return {
    group,
    // Frame the city itself. The ground plane extends far past it so its edge
    // dissolves in fog, and including it here would only push the camera back.
    bounds: contentBounds,
    stats: Object.freeze({
      roadFeatures: roads.features,
      roadSegments: roads.segments,
      skippedRoadLines: roads.skipped,
      railFeatures: rail.features,
      railSegments: rail.segments,
      skippedRailLines: rail.skipped,
      waterwayFeatures: waterways.features,
      waterwaySegments: waterways.segments,
      buildingCandidates: buildings.candidates,
      buildings: buildings.built,
      invalidBuildings: buildings.invalid,
      thinnedBuildings: buildings.thinned,
      points: points.count,
    }),
    applySequence(state) {
      uniforms.reveal.value = state.lineReveal;
      uniforms.pointReveal.value = state.pointReveal;
      uniforms.buildingGrow.value = state.buildingGrow;
      if (points.object) points.object.material.opacity = state.pointOpacity;
      // Separation is presentation, not depth. See the note on screen.
      const separation = state.strataT ?? 0;
      railLayer.position.y = -CONFIG.strata.railDrop * separation;
      past.position.y = -CONFIG.strata.pastDrop * separation;
      // Turning to the side also cuts the ground down to a finite specimen:
      // an endless slab has no readable edge and would roof over everything
      // that drops below it.
      const contracted = THREE.MathUtils.lerp(1, CONFIG.strata.slabContractTo, state.sideT ?? 0);
      ground.scale.set(contracted, 1, contracted);
    },
    dispose() {
      disposeObject3D(group);
    },
  };
}

export function disposeObject3D(root) {
  const geometries = new Set();
  const materials = new Set();
  root.traverse((object) => {
    if (object.geometry) geometries.add(object.geometry);
    const list = Array.isArray(object.material) ? object.material : [object.material];
    for (const material of list) if (material) materials.add(material);
  });
  for (const geometry of geometries) geometry.dispose();
  for (const material of materials) material.dispose();
}
