const EARTH_RADIUS_METERS = 6378137;
const DEG_TO_RAD = Math.PI / 180;

export function createLocalProjection({ center, metersPerUnit }) {
  const [centerLon, centerLat] = center;
  const longitudeScale = Math.cos(centerLat * DEG_TO_RAD);

  return Object.freeze({
    center: Object.freeze([centerLon, centerLat]),
    metersPerUnit,
    project(coordinate) {
      const lon = Number(coordinate?.[0]);
      const lat = Number(coordinate?.[1]);
      if (!Number.isFinite(lon) || !Number.isFinite(lat)) return null;
      const x = ((lon - centerLon) * DEG_TO_RAD * EARTH_RADIUS_METERS * longitudeScale) / metersPerUnit;
      const z = -((lat - centerLat) * DEG_TO_RAD * EARTH_RADIUS_METERS) / metersPerUnit;
      return [x, z];
    },
    unproject([x, z]) {
      const lon = centerLon + (x * metersPerUnit) / (DEG_TO_RAD * EARTH_RADIUS_METERS * longitudeScale);
      const lat = centerLat - (z * metersPerUnit) / (DEG_TO_RAD * EARTH_RADIUS_METERS);
      return [lon, lat];
    },
  });
}

export function forEachLineString(collection, callback) {
  for (const feature of collection?.features || []) {
    const geometry = feature?.geometry;
    if (!geometry) continue;
    if (geometry.type === "LineString") {
      callback(geometry.coordinates, feature.properties || {}, feature);
    } else if (geometry.type === "MultiLineString") {
      for (const line of geometry.coordinates || []) {
        callback(line, feature.properties || {}, feature);
      }
    }
  }
}

export function forEachPolygon(collection, callback) {
  for (const feature of collection?.features || []) {
    const geometry = feature?.geometry;
    if (!geometry) continue;
    if (geometry.type === "Polygon") {
      callback(geometry.coordinates, feature.properties || {}, feature);
    } else if (geometry.type === "MultiPolygon") {
      for (const polygon of geometry.coordinates || []) {
        callback(polygon, feature.properties || {}, feature);
      }
    }
  }
}

export function numericMeters(value) {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string") return null;
  const number = Number.parseFloat(value.replace(",", "."));
  return Number.isFinite(number) ? number : null;
}

export function truthyTag(value) {
  if (value === true || value === 1) return true;
  if (typeof value !== "string") return false;
  return ["yes", "true", "1"].includes(value.toLowerCase());
}
