import * as THREE from "../vendor/three.module.js";
import { CONFIG } from "./config.js";
import { forEachLineString, forEachPolygon, numericMeters } from "./geo.js";

const MAJOR_ROADS = new Set(["motorway", "trunk", "primary", "secondary", "tertiary"]);
const INACTIVE_RAIL = new Set(["abandoned", "disused", "razed", "construction", "proposed"]);

function pushTriangle(target, a, b, c, y) {
  target.push(a[0], y, a[1], b[0], y, b[1], c[0], y, c[1]);
}

function pushRibbonSegment(target, a, b, width, y) {
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
  return true;
}

function createRibbonLayer(collection, projection, options) {
  const positions = [];
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
    let previous = null;
    for (const coordinate of coordinates || []) {
      const current = projection.project(coordinate);
      if (current && previous && pushRibbonSegment(positions, previous, current, width, options.y)) {
        segments += 1;
        features.add(feature);
      }
      previous = current;
    }
  });

  if (positions.length === 0) return { object: null, features: 0, segments, skipped };
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
  const material = new THREE.MeshStandardMaterial({
    color: options.color,
    roughness: options.roughness ?? 0.82,
    metalness: options.metalness ?? 0,
    transparent: options.opacity < 1,
    opacity: options.opacity,
    depthWrite: options.opacity >= 1,
  });
  const object = new THREE.Mesh(geometry, material);
  object.name = options.name;
  object.renderOrder = options.renderOrder;
  return { object, features: features.size, segments, skipped };
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

function createBuildings(collection, projection, quality) {
  const candidates = [];
  forEachPolygon(collection, (polygon, properties) => candidates.push({ polygon, properties }));
  const limit = Math.min(candidates.length, quality.maxBuildings);
  const positions = [];
  let built = 0;
  let invalid = 0;

  for (let selected = 0; selected < limit; selected += 1) {
    const index = candidates.length <= limit
      ? selected
      : Math.min(candidates.length - 1, Math.floor((selected * candidates.length) / limit));
    if (appendBuilding(positions, candidates[index].polygon, candidates[index].properties, projection, quality)) {
      built += 1;
    } else {
      invalid += 1;
    }
  }

  if (!positions.length) {
    return { object: null, candidates: candidates.length, built, invalid, thinned: candidates.length - limit };
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
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
  const geometry = new THREE.PlaneGeometry(width, depth, 1, 1);
  const material = new THREE.MeshStandardMaterial({
    color: CONFIG.palette.ground,
    roughness: 0.96,
    metalness: 0.02,
  });
  const ground = new THREE.Mesh(geometry, material);
  ground.name = "city-ground";
  ground.rotation.x = -Math.PI / 2;
  ground.position.set(center.x, CONFIG.model.groundY, center.z);
  ground.renderOrder = 0;
  return ground;
}

export function createCity(data, projection, quality) {
  const group = new THREE.Group();
  group.name = "phase-2-city";

  const roads = createRibbonLayer(data.roads, projection, {
    name: "major-roads",
    color: CONFIG.palette.roads,
    opacity: 0.72,
    roughness: 0.88,
    y: CONFIG.model.roadY,
    renderOrder: 2,
    filter: (properties) => {
      const roadClass = parseRoadClass(properties);
      return roadClass ? MAJOR_ROADS.has(roadClass) : true;
    },
    widthMeters: roadWidth,
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
  });
  const buildings = createBuildings(data.buildings, projection, quality);

  for (const layer of [waterways.object, roads.object, rail.object, buildings.object]) {
    if (layer) group.add(layer);
  }
  const contentBounds = modelBounds(group);
  group.add(createGround(contentBounds));

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
    }),
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
