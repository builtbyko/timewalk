#!/usr/bin/env python3
"""Build the small, display-oriented Ginza datasets used by Unseen City.

Only processed GeoJSON and its manifest are written. Overpass responses remain
in memory. The existing TimeWalk rail cache is reused when it is available.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests


BBOX = (35.6645, 139.7590, 35.6755, 139.7720)  # south, west, north, east
CENTER = (35.6700, 139.7655)
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
USER_AGENT = "unseen-city-data-prep/0.1 (open-source urban GIS project)"

SCRIPT_DIR = Path(__file__).resolve().parent
LAB_DIR = SCRIPT_DIR.parent
DATA_DIR = LAB_DIR / "data"
REPO_ROOT = SCRIPT_DIR.parents[3]
TIMEWALK_RAIL_CACHE = (
    REPO_ROOT / "04_timewalk" / "data" / "_overpass_ginza_rail_cache.json"
)

ROAD_CLASSES = (
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
)
RAIL_CLASSES = ("rail", "subway", "light_rail")

# These are hand-traced reference lines copied from TimeWalk. They are not
# official river boundaries, surveyed centerlines, or evidence of depth.
HISTORIC_WATERWAY_REFERENCES = (
    (
        "sanjikkenbori-reference",
        "三十間堀川（参考線）",
        (
            (35.674227, 139.771503),
            (35.6735, 139.7705),
            (35.6710, 139.7684),
            (35.6685, 139.7663),
            (35.6662, 139.7645),
        ),
    ),
    (
        "shiodome-reference",
        "汐留川（参考線）",
        (
            (35.6693, 139.7573),
            (35.668124, 139.759030),
            (35.667144, 139.762024),
            (35.666073, 139.762910),
            (35.6662, 139.7645),
        ),
    ),
    (
        "kyobashi-reference",
        "京橋川（参考線）",
        (
            (35.675773, 139.766432),
            (35.675004, 139.769401),
            (35.674227, 139.771503),
        ),
    ),
    (
        "outer-moat-reference",
        "外濠（参考線）",
        (
            (35.668124, 139.759030),
            (35.672145, 139.760612),
            (35.672499, 139.761126),
            (35.673305, 139.764029),
            (35.675699, 139.765588),
            (35.675773, 139.766432),
        ),
    ),
)


def fetch_overpass(query: str) -> dict[str, Any]:
    last_error: Exception | None = None
    for endpoint in OVERPASS_URLS:
        try:
            response = requests.post(
                endpoint,
                data={"data": query},
                headers={"User-Agent": USER_AGENT},
                timeout=180,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Overpass response is not a JSON object")
            if payload.get("remark"):
                raise RuntimeError(f"Overpass returned a remark: {payload['remark']}")
            elements = payload.get("elements")
            if not isinstance(elements, list) or not elements:
                raise RuntimeError("Overpass returned no elements")
            return payload
        except (requests.RequestException, ValueError, RuntimeError) as error:
            last_error = error
            print(f"Overpass endpoint failed: {endpoint} ({error})")
    assert last_error is not None
    raise last_error


def osm_base_timestamp(data: dict[str, Any]) -> str | None:
    return data.get("osm3s", {}).get("timestamp_osm_base")


def round_coord(coord: tuple[float, float]) -> list[float]:
    return [round(coord[0], 6), round(coord[1], 6)]


def geometry_coords(element: dict[str, Any]) -> list[tuple[float, float]]:
    return [
        (float(point["lon"]), float(point["lat"]))
        for point in element.get("geometry", ())
        if "lon" in point and "lat" in point
    ]


def points_close(
    left: tuple[float, float], right: tuple[float, float], epsilon: float = 1e-12
) -> bool:
    return abs(left[0] - right[0]) <= epsilon and abs(left[1] - right[1]) <= epsilon


def clip_segment_to_bbox(
    start: tuple[float, float], end: tuple[float, float]
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Liang-Barsky clip for a longitude/latitude segment."""
    south, west, north, east = BBOX
    x0, y0 = start
    x1, y1 = end
    dx, dy = x1 - x0, y1 - y0
    lower, upper = 0.0, 1.0
    for denominator, numerator in (
        (-dx, x0 - west),
        (dx, east - x0),
        (-dy, y0 - south),
        (dy, north - y0),
    ):
        if denominator == 0.0:
            if numerator < 0.0:
                return None
            continue
        amount = numerator / denominator
        if denominator < 0.0:
            lower = max(lower, amount)
        else:
            upper = min(upper, amount)
        if lower > upper:
            return None
    return (
        (x0 + lower * dx, y0 + lower * dy),
        (x0 + upper * dx, y0 + upper * dy),
    )


def clip_polyline_to_bbox(
    coordinates: list[tuple[float, float]],
) -> list[list[tuple[float, float]]]:
    parts: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []

    def flush() -> None:
        nonlocal current
        if len(current) >= 2:
            parts.append(current)
        current = []

    for start, end in zip(coordinates, coordinates[1:]):
        clipped = clip_segment_to_bbox(start, end)
        if clipped is None:
            flush()
            continue
        clipped_start, clipped_end = clipped
        if current and points_close(current[-1], clipped_start):
            if not points_close(current[-1], clipped_end):
                current.append(clipped_end)
        else:
            flush()
            current = [clipped_start, clipped_end]
        if not points_close(clipped_end, end):
            flush()
    flush()
    return parts


def clip_ring_to_bbox(
    coordinates: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    if len(coordinates) < 4:
        return []
    ring = coordinates[:-1] if points_close(coordinates[0], coordinates[-1]) else coordinates[:]
    south, west, north, east = BBOX

    def clip_edge(
        points: list[tuple[float, float]],
        inside: Any,
        intersection: Any,
    ) -> list[tuple[float, float]]:
        if not points:
            return []
        output: list[tuple[float, float]] = []
        previous = points[-1]
        previous_inside = inside(previous)
        for current in points:
            current_inside = inside(current)
            if current_inside:
                if not previous_inside:
                    output.append(intersection(previous, current))
                output.append(current)
            elif previous_inside:
                output.append(intersection(previous, current))
            previous = current
            previous_inside = current_inside
        return output

    def at_x(
        start: tuple[float, float], end: tuple[float, float], x: float
    ) -> tuple[float, float]:
        amount = (x - start[0]) / (end[0] - start[0])
        return x, start[1] + amount * (end[1] - start[1])

    def at_y(
        start: tuple[float, float], end: tuple[float, float], y: float
    ) -> tuple[float, float]:
        amount = (y - start[1]) / (end[1] - start[1])
        return start[0] + amount * (end[0] - start[0]), y

    ring = clip_edge(ring, lambda point: point[0] >= west, lambda a, b: at_x(a, b, west))
    ring = clip_edge(ring, lambda point: point[0] <= east, lambda a, b: at_x(a, b, east))
    ring = clip_edge(ring, lambda point: point[1] >= south, lambda a, b: at_y(a, b, south))
    ring = clip_edge(ring, lambda point: point[1] <= north, lambda a, b: at_y(a, b, north))
    if len(ring) < 3:
        return []

    deduplicated = [ring[0]]
    for point in ring[1:]:
        if not points_close(deduplicated[-1], point):
            deduplicated.append(point)
    if len(deduplicated) < 3:
        return []
    if not points_close(deduplicated[0], deduplicated[-1]):
        deduplicated.append(deduplicated[0])
    return deduplicated if len(deduplicated) >= 4 else []


def clip_polygon_geometry(geometry: dict[str, Any]) -> dict[str, Any] | None:
    source_polygons = (
        [geometry["coordinates"]]
        if geometry["type"] == "Polygon"
        else geometry["coordinates"]
    )
    clipped_polygons: list[list[list[list[float]]]] = []
    for source_polygon in source_polygons:
        if not source_polygon:
            continue
        outer = clip_ring_to_bbox([tuple(point) for point in source_polygon[0]])
        if not outer:
            continue
        rings = [[round_coord(point) for point in outer]]
        for source_hole in source_polygon[1:]:
            hole = clip_ring_to_bbox([tuple(point) for point in source_hole])
            if hole and point_in_ring(hole[0], outer):
                rings.append([round_coord(point) for point in hole])
        clipped_polygons.append(rings)
    if not clipped_polygons:
        return None
    if len(clipped_polygons) == 1:
        return {"type": "Polygon", "coordinates": clipped_polygons[0]}
    return {"type": "MultiPolygon", "coordinates": clipped_polygons}


def simplify_line(
    coordinates: list[tuple[float, float]], tolerance_m: float
) -> list[tuple[float, float]]:
    """Small Douglas-Peucker simplifier using a local planar approximation."""
    if len(coordinates) < 3:
        return coordinates

    latitude = coordinates[0][1]
    lon_scale = math.cos(math.radians(latitude))
    ax, ay = coordinates[0][0] * lon_scale, coordinates[0][1]
    bx, by = coordinates[-1][0] * lon_scale, coordinates[-1][1]
    dx, dy = bx - ax, by - ay
    furthest_distance = 0.0
    furthest_index = 0

    for index, (lon, lat) in enumerate(coordinates[1:-1], start=1):
        px, py = lon * lon_scale, lat
        if dx == 0.0 and dy == 0.0:
            distance = math.hypot(px - ax, py - ay)
        else:
            amount = max(
                0.0,
                min(
                    1.0,
                    ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy),
                ),
            )
            distance = math.hypot(px - (ax + amount * dx), py - (ay + amount * dy))
        if distance > furthest_distance:
            furthest_distance = distance
            furthest_index = index

    if furthest_distance * 111_000.0 <= tolerance_m:
        return [coordinates[0], coordinates[-1]]

    left = simplify_line(coordinates[: furthest_index + 1], tolerance_m)
    right = simplify_line(coordinates[furthest_index:], tolerance_m)
    return left[:-1] + right


def fetch_surface_data() -> dict[str, Any]:
    south, west, north, east = BBOX
    bbox_text = f"{south},{west},{north},{east}"
    road_pattern = "^(" + "|".join(ROAD_CLASSES) + ")$"
    roads_query = f"""[out:json][timeout:120];
way[\"highway\"~\"{road_pattern}\"]({bbox_text});
out geom;"""
    buildings_query = f"""[out:json][timeout:180];
(
  way[\"building\"][\"building\"!~\"^(no|construction)$\"]({bbox_text});
  relation[\"building\"][\"building\"!~\"^(no|construction)$\"]({bbox_text});
);
out geom;"""
    roads_data = fetch_overpass(roads_query)
    buildings_data = fetch_overpass(buildings_query)
    timestamps = sorted(
        timestamp
        for timestamp in (
            osm_base_timestamp(roads_data),
            osm_base_timestamp(buildings_data),
        )
        if timestamp
    )
    return {
        "elements": roads_data.get("elements", []) + buildings_data.get("elements", []),
        "osm3s": {"timestamp_osm_base": timestamps[0] if timestamps else None},
    }


def build_roads(data: dict[str, Any]) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for element in data.get("elements", ()):
        tags = element.get("tags", {})
        road_class = tags.get("highway")
        if element.get("type") != "way" or road_class not in ROAD_CLASSES:
            continue
        source = simplify_line(geometry_coords(element), tolerance_m=1.2)
        parts = clip_polyline_to_bbox(source)
        for part_index, coordinates in enumerate(parts):
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "osm_type": "way",
                        "osm_id": element["id"],
                        "part": part_index,
                        "class": road_class,
                        "name": tags.get("name", ""),
                        "bridge": tags.get("bridge", "no"),
                        "tunnel": tags.get("tunnel", "no"),
                        "layer": tags.get("layer", "0"),
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [round_coord(coord) for coord in coordinates],
                    },
                }
            )
    features.sort(
        key=lambda feature: (
            feature["properties"]["osm_id"],
            feature["properties"]["part"],
        )
    )
    return feature_collection("Ginza major roads", features)


def same_point(left: tuple[float, float], right: tuple[float, float]) -> bool:
    return left == right


def join_segments(
    source_segments: Iterable[list[tuple[float, float]]],
) -> list[list[tuple[float, float]]]:
    segments = [segment[:] for segment in source_segments if len(segment) >= 2]
    rings: list[list[tuple[float, float]]] = []
    while segments:
        ring = segments.pop()
        changed = True
        while changed and not same_point(ring[0], ring[-1]):
            changed = False
            for index, segment in enumerate(segments):
                if same_point(ring[-1], segment[0]):
                    ring.extend(segment[1:])
                elif same_point(ring[-1], segment[-1]):
                    ring.extend(reversed(segment[:-1]))
                elif same_point(ring[0], segment[-1]):
                    ring = segment[:-1] + ring
                elif same_point(ring[0], segment[0]):
                    ring = list(reversed(segment[1:])) + ring
                else:
                    continue
                segments.pop(index)
                changed = True
                break
        if len(ring) >= 4 and same_point(ring[0], ring[-1]):
            rings.append(ring)
    return rings


def point_in_ring(point: tuple[float, float], ring: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    previous_x, previous_y = ring[-1]
    for current_x, current_y in ring:
        crosses = (current_y > y) != (previous_y > y)
        if crosses:
            boundary_x = (
                (previous_x - current_x) * (y - current_y)
                / (previous_y - current_y)
                + current_x
            )
            if x < boundary_x:
                inside = not inside
        previous_x, previous_y = current_x, current_y
    return inside


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", "."))
    return float(match.group()) if match else None


def display_height(tags: dict[str, Any], osm_id: int) -> tuple[float, str, float | None]:
    tagged_height = parse_number(tags.get("height"))
    if tagged_height and tagged_height > 0:
        return round(max(4.0, min(tagged_height, 120.0)), 1), "osm_height", tagged_height

    levels = parse_number(tags.get("building:levels"))
    if levels and levels > 0:
        height = max(4.0, min(levels * 3.2, 120.0))
        return round(height, 1), "osm_levels_x_3.2m", None

    # Stable visual fallback. It is deliberately labelled and is not a factual
    # estimate of the real building height.
    fallback = 14.0 + float(osm_id % 5) * 3.0
    return fallback, "visual_fallback", None


def building_properties(element: dict[str, Any]) -> dict[str, Any]:
    tags = element.get("tags", {})
    osm_id = int(element["id"])
    height, basis, source_height = display_height(tags, osm_id)
    levels = parse_number(tags.get("building:levels"))
    return {
        "osm_type": element["type"],
        "osm_id": osm_id,
        "building": tags.get("building", "yes"),
        "source_height_m": source_height,
        "source_levels": levels,
        "display_height_m": height,
        "height_basis": basis,
    }


def relation_geometry(element: dict[str, Any]) -> dict[str, Any] | None:
    outer_segments: list[list[tuple[float, float]]] = []
    inner_segments: list[list[tuple[float, float]]] = []
    for member in element.get("members", ()):
        if member.get("type") != "way":
            continue
        coordinates = geometry_coords(member)
        if len(coordinates) < 2:
            continue
        if member.get("role") == "inner":
            inner_segments.append(coordinates)
        else:
            outer_segments.append(coordinates)

    outer_rings = join_segments(outer_segments)
    inner_rings = join_segments(inner_segments)
    if not outer_rings:
        return None

    polygons: list[list[list[list[float]]]] = []
    for outer in outer_rings:
        rings = [[round_coord(coord) for coord in outer]]
        for inner in inner_rings:
            if point_in_ring(inner[0], outer):
                rings.append([round_coord(coord) for coord in inner])
        polygons.append(rings)

    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": polygons[0]}
    return {"type": "MultiPolygon", "coordinates": polygons}


def build_buildings(data: dict[str, Any]) -> dict[str, Any]:
    relation_member_ids = {
        int(member["ref"])
        for element in data.get("elements", ())
        if element.get("type") == "relation" and element.get("tags", {}).get("building")
        for member in element.get("members", ())
        if member.get("type") == "way" and "ref" in member
    }
    features: list[dict[str, Any]] = []
    for element in data.get("elements", ()):
        tags = element.get("tags", {})
        if not tags.get("building") or tags.get("building") in ("no", "construction"):
            continue

        geometry: dict[str, Any] | None = None
        if element.get("type") == "way":
            if int(element["id"]) in relation_member_ids:
                continue
            coordinates = geometry_coords(element)
            if len(coordinates) >= 4 and same_point(coordinates[0], coordinates[-1]):
                geometry = {
                    "type": "Polygon",
                    "coordinates": [[round_coord(coord) for coord in coordinates]],
                }
        elif element.get("type") == "relation":
            geometry = relation_geometry(element)

        if geometry is None:
            continue
        geometry = clip_polygon_geometry(geometry)
        if geometry is None:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": building_properties(element),
                "geometry": geometry,
            }
        )

    features.sort(
        key=lambda feature: (
            feature["properties"]["osm_type"],
            feature["properties"]["osm_id"],
        )
    )
    return feature_collection("Ginza simplified building footprints", features)


def clip_existing_lines(dataset: dict[str, Any]) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for feature in dataset.get("features", ()):
        geometry = feature.get("geometry", {})
        if geometry.get("type") != "LineString":
            continue
        source = [tuple(point) for point in geometry.get("coordinates", ())]
        for part_index, coordinates in enumerate(clip_polyline_to_bbox(source)):
            properties = dict(feature.get("properties", {}))
            properties["part"] = part_index
            features.append(
                {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [round_coord(coord) for coord in coordinates],
                    },
                }
            )
    return feature_collection(dataset.get("name", "Clipped lines"), features)


def clip_existing_buildings(dataset: dict[str, Any]) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for feature in dataset.get("features", ()):
        geometry = feature.get("geometry", {})
        if geometry.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        clipped = clip_polygon_geometry(geometry)
        if clipped is None:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": dict(feature.get("properties", {})),
                "geometry": clipped,
            }
        )
    return feature_collection(dataset.get("name", "Clipped buildings"), features)


def load_rail_data(refresh: bool) -> tuple[dict[str, Any], str]:
    if TIMEWALK_RAIL_CACHE.exists() and not refresh:
        with TIMEWALK_RAIL_CACHE.open(encoding="utf-8") as source:
            return json.load(source), "04_timewalk rail cache"

    south, west, north, east = BBOX
    padding = 0.005
    bbox_text = (
        f"{south - padding},{west - padding},{north + padding},{east + padding}"
    )
    query = f"""[out:json][timeout:120];
(
  way[\"railway\"~\"^(rail|subway|light_rail)$\"][\"service\"!~\".\"]({bbox_text});
);
out body;
>;
out skel qt;"""
    return fetch_overpass(query), "Overpass API"


def build_railways(data: dict[str, Any]) -> dict[str, Any]:
    nodes = {
        int(element["id"]): (float(element["lon"]), float(element["lat"]))
        for element in data.get("elements", ())
        if element.get("type") == "node" and "lon" in element and "lat" in element
    }
    features: list[dict[str, Any]] = []
    for element in data.get("elements", ()):
        tags = element.get("tags", {})
        rail_class = tags.get("railway")
        if element.get("type") != "way" or rail_class not in RAIL_CLASSES:
            continue
        source = [
            nodes[int(node_id)] for node_id in element.get("nodes", ()) if int(node_id) in nodes
        ]
        source = simplify_line(source, tolerance_m=3.0)
        parts = clip_polyline_to_bbox(source)
        for part_index, coordinates in enumerate(parts):
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "osm_type": "way",
                        "osm_id": element["id"],
                        "part": part_index,
                        "railway": rail_class,
                        "name": tags.get("name", ""),
                        "tunnel": tags.get("tunnel", "no"),
                        "bridge": tags.get("bridge", "no"),
                        "layer": tags.get("layer", "0"),
                        "depth_status": "not_provided",
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [round_coord(coord) for coord in coordinates],
                    },
                }
            )
    features.sort(
        key=lambda feature: (
            feature["properties"]["osm_id"],
            feature["properties"]["part"],
        )
    )
    return feature_collection("Ginza railways", features)


def build_historic_waterways() -> dict[str, Any]:
    features = []
    for identifier, name, lat_lon_coordinates in HISTORIC_WATERWAY_REFERENCES:
        source = [(lon, lat) for lat, lon in lat_lon_coordinates]
        parts = clip_polyline_to_bbox(source)
        for part_index, coordinates in enumerate(parts):
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "id": identifier,
                        "part": part_index,
                        "name": name,
                        "reference_only": True,
                        "geometry_status": "hand_traced_approximation",
                        "depth_status": "not_provided",
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [round_coord(coord) for coord in coordinates],
                    },
                }
            )
    return feature_collection("Historic waterways: reference lines", features)


def iter_positions(value: Any) -> Iterable[tuple[float, float]]:
    if not isinstance(value, list):
        return
    if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
        yield float(value[0]), float(value[1])
        return
    for item in value:
        yield from iter_positions(item)


def feature_collection(name: str, features: list[dict[str, Any]]) -> dict[str, Any]:
    positions = [
        position
        for feature in features
        for position in iter_positions(feature["geometry"]["coordinates"])
    ]
    bounds = (
        [
            min(position[0] for position in positions),
            min(position[1] for position in positions),
            max(position[0] for position in positions),
            max(position[1] for position in positions),
        ]
        if positions
        else [BBOX[1], BBOX[0], BBOX[3], BBOX[2]]
    )
    return {
        "type": "FeatureCollection",
        "name": name,
        "bbox": bounds,
        "features": features,
    }


def coordinate_count(value: Any) -> int:
    if not isinstance(value, list):
        return 0
    if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
        return 1
    return sum(coordinate_count(item) for item in value)


def write_json(path: Path, data: dict[str, Any], pretty: bool = False) -> None:
    if pretty:
        payload = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    path.write_text(payload + "\n", encoding="utf-8")


def dataset_record(
    filename: str,
    dataset: dict[str, Any],
    source: str,
    source_snapshot: str | None,
    limitations: list[str],
) -> dict[str, Any]:
    path = DATA_DIR / filename
    return {
        "path": f"data/{filename}",
        "format": "GeoJSON FeatureCollection",
        "feature_count": len(dataset["features"]),
        "coordinate_count": sum(
            coordinate_count(feature["geometry"]["coordinates"])
            for feature in dataset["features"]
        ),
        "size_bytes": path.stat().st_size,
        "source": source,
        "source_snapshot": source_snapshot,
        "limitations": limitations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh-rail",
        action="store_true",
        help="Fetch railways instead of reusing the existing TimeWalk cache.",
    )
    parser.add_argument(
        "--reuse-existing-surface",
        action="store_true",
        help="Re-clip existing roads/buildings/railways without contacting Overpass.",
    )
    arguments = parser.parse_args()

    if arguments.reuse_existing_surface and arguments.refresh_rail:
        parser.error("--reuse-existing-surface and --refresh-rail cannot be combined")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing_manifest_path = DATA_DIR / "manifest.json"
    existing_manifest = (
        json.loads(existing_manifest_path.read_text(encoding="utf-8"))
        if existing_manifest_path.exists()
        else {}
    )

    if arguments.reuse_existing_surface:
        roads_path = DATA_DIR / "roads.geojson"
        buildings_path = DATA_DIR / "buildings.geojson"
        railways_path = DATA_DIR / "railways.geojson"
        if not all(path.exists() for path in (roads_path, buildings_path, railways_path)):
            parser.error(
                "--reuse-existing-surface requires existing roads.geojson, "
                "buildings.geojson, and railways.geojson"
            )
        roads = clip_existing_lines(json.loads(roads_path.read_text(encoding="utf-8")))
        buildings = clip_existing_buildings(
            json.loads(buildings_path.read_text(encoding="utf-8"))
        )
        railways = clip_existing_lines(
            json.loads(railways_path.read_text(encoding="utf-8"))
        )
        existing_rail_record = existing_manifest.get("datasets", {}).get(
            "railways", {}
        )
        existing_rail_source = existing_rail_record.get("source", "")
        source_prefix = "OpenStreetMap via "
        rail_input = (
            existing_rail_source[len(source_prefix) :]
            if existing_rail_source.startswith(source_prefix)
            else "existing processed railways"
        )
        surface_snapshot = (
            existing_manifest.get("datasets", {})
            .get("roads", {})
            .get("source_snapshot")
        )
        rail_snapshot = existing_rail_record.get("source_snapshot")
    else:
        surface_data = fetch_surface_data()
        roads = build_roads(surface_data)
        buildings = build_buildings(surface_data)
        surface_snapshot = osm_base_timestamp(surface_data)
        rail_data, rail_input = load_rail_data(arguments.refresh_rail)
        railways = build_railways(rail_data)
        rail_snapshot = osm_base_timestamp(rail_data)
    historic_waterways = build_historic_waterways()

    datasets = {
        "roads.geojson": roads,
        "buildings.geojson": buildings,
        "railways.geojson": railways,
        "historic-waterways-reference.geojson": historic_waterways,
    }
    minimum_feature_counts = {
        "roads.geojson": 50,
        "buildings.geojson": 500,
        "railways.geojson": 10,
        "historic-waterways-reference.geojson": 4,
    }
    for filename, dataset in datasets.items():
        feature_count = len(dataset.get("features", ()))
        minimum = minimum_feature_counts[filename]
        if feature_count < minimum:
            raise RuntimeError(
                f"Refusing to overwrite {filename}: expected at least "
                f"{minimum} features, received {feature_count}"
            )
    for filename, dataset in datasets.items():
        write_json(DATA_DIR / filename, dataset)

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "project": "BUILT BY KO — UNSEEN CITY / Phase 2",
        "area": {
            "label": "Ginza and immediate surroundings",
            "bbox_wgs84": [BBOX[1], BBOX[0], BBOX[3], BBOX[2]],
            "center_wgs84": [CENTER[1], CENTER[0]],
        },
        "coordinate_reference_system": {
            "identifier": "OGC:CRS84 / RFC 7946",
            "geodetic_basis": "WGS 84 (EPSG:4326)",
            "axis_order_in_files": "longitude, latitude",
            "note": "Runtime Three.js coordinates are a display projection, not an official survey CRS.",
        },
        "processing": {
            "clip_bbox_wgs84": [BBOX[1], BBOX[0], BBOX[3], BBOX[2]],
            "geometry_outside_clip_bbox_retained": False,
            "raw_overpass_responses_stored": False,
        },
        "datasets": {
            "roads": dataset_record(
                "roads.geojson",
                roads,
                "OpenStreetMap via Overpass API",
                surface_snapshot,
                [
                    "Only motorway through tertiary classes and their link roads are retained.",
                    "Every output LineString is clipped to the project bbox.",
                    "Line locations and classifications reflect the OSM snapshot and are not official road geometry.",
                ],
            ),
            "buildings": dataset_record(
                "buildings.geojson",
                buildings,
                "OpenStreetMap via Overpass API",
                surface_snapshot,
                [
                    "Footprints are incomplete wherever OSM lacks building geometry.",
                    "Every output footprint is clipped to the project bbox.",
                    "display_height_m may be derived from OSM levels or a clearly labelled visual fallback; it is not authoritative height data.",
                    "Invalid or unjoinable multipolygon members are omitted.",
                ],
            ),
            "railways": dataset_record(
                "railways.geojson",
                railways,
                f"OpenStreetMap via {rail_input}",
                rail_snapshot,
                [
                    "Every output LineString is clipped to the project bbox.",
                    "The tunnel tag is a category only; it must not be converted into measured depth.",
                    "Track ways may be parallel or duplicated because each OSM way is retained.",
                ],
            ),
            "historic_waterways_reference": dataset_record(
                "historic-waterways-reference.geojson",
                historic_waterways,
                "Hand-traced reference lines reused from 04_timewalk/scripts/ginza_build.py",
                None,
                [
                    "Every output reference line is clipped to the project bbox.",
                    "Approximate reference lines, not official boundaries or surveyed centerlines.",
                    "No underground status or depth is encoded.",
                    "Historical interpretation requires separate source verification before factual publication.",
                ],
            ),
        },
        "license_and_attribution": {
            "openstreetmap": "© OpenStreetMap contributors; data available under ODbL 1.0.",
            "historic_waterways_reference": "Project-authored reference geometry; underlying historical interpretation requires source verification.",
        },
    }
    write_json(DATA_DIR / "manifest.json", manifest, pretty=True)

    for key, record in manifest["datasets"].items():
        print(
            f"{key}: {record['feature_count']} features, "
            f"{record['coordinate_count']} coordinates, {record['size_bytes']} bytes"
        )


if __name__ == "__main__":
    main()
