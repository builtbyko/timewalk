# -*- coding: utf-8 -*-
"""
map_toolkit.py — TimeWalk 共通道具箱
全まちで使い回す定型: ベースマップタイル定義 / Overpass取得(キャッシュ付き) /
歩く網等の抽出 / GeoJSON変換

2026-07-07: v3でアーキテクチャをfolium直接描画からGeoJSON生成に移行。
表示側(Leaflet直書き)は scripts/ginza_template.html が担う。
このファイルはデータ取得・整形のみに専念する。
"""

import os
import json
import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "timewalk-maps/0.1 (personal GIS project)"}

# ---------------------------------------------------------------
# ベースマップタイル定義(地理院タイルは attribution "国土地理院" 必須。
# テンプレート側のJSでこの辞書の値を直接使う)
# ---------------------------------------------------------------
GSI_TILES = {
    "航空写真(現在)":      ("https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{z}/{x}/{y}.jpg", 18),
    "空中写真 1974-78":    ("https://cyberjapandata.gsi.go.jp/xyz/gazo1/{z}/{x}/{y}.jpg", 17),
    "空中写真 1961-69":    ("https://cyberjapandata.gsi.go.jp/xyz/ort_old10/{z}/{x}/{y}.png", 17),
    "空中写真 1945-50":    ("https://cyberjapandata.gsi.go.jp/xyz/ort_USA10/{z}/{x}/{y}.png", 17),
}


# ---------------------------------------------------------------
# Overpass
# ---------------------------------------------------------------
def overpass(query, cache_file, use_cache=True):
    if use_cache and os.path.exists(cache_file):
        print(f"[cache] {os.path.basename(cache_file)}")
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)
    print("[fetch] Overpass API...")
    r = requests.post(OVERPASS_URL, data={"data": query}, headers=HEADERS, timeout=90)
    r.raise_for_status()
    data = r.json()
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def node_index(data):
    """座標は小数点6桁(≒11cm精度)に丸める。徒歩地図には十分な精度で、
    JSONに埋め込まれる文字列長を抑える(HTMLサイズ対策、2026-07-05)。"""
    return {el["id"]: (round(el["lat"], 6), round(el["lon"], 6))
            for el in data["elements"] if el["type"] == "node"}


def walk_net_query(bbox):
    """「歩く空間の網」: 細い歩行者空間全般(雰囲気優先で緩め)"""
    b = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
    return f"""[out:json][timeout:60];
(
  way["highway"="footway"]({b});
  way["highway"="path"]({b});
  way["highway"="pedestrian"]({b});
  way["highway"="living_street"]({b});
  way["highway"="service"]["service"="alley"]({b});
  way["highway"="steps"]({b});
);
out body; >; out skel qt;"""


def rail_query(bbox, pad=0.005):
    """鉄道(路線+駅)。まちのbboxより pad 分(約500m)広めに取る:
    駅・路線は「地図の端の少し外」にあっても位置把握の手がかりになるため。"""
    b = f"{bbox[0]-pad},{bbox[1]-pad},{bbox[2]+pad},{bbox[3]+pad}"
    return f"""[out:json][timeout:60];
(
  way["railway"~"^(rail|subway|light_rail)$"]["service"!~"."]({b});
  node["railway"="station"]({b});
  way["railway"="station"]({b});
);
out body; >; out skel qt;"""


def extract_ways(data, nodes):
    """(tags, [(lat,lon),...]) のリスト"""
    out = []
    for el in data["elements"]:
        if el["type"] == "way" and "tags" in el:
            coords = [nodes[n] for n in el.get("nodes", []) if n in nodes]
            if len(coords) >= 2:
                out.append((el["tags"], coords))
    return out


def extract_points(data, nodes):
    """node直接 + way(ポリゴン)は重心で代表。(tags, lat, lon) のリスト"""
    out = []
    for el in data["elements"]:
        if "tags" not in el:
            continue
        if el["type"] == "node":
            out.append((el["tags"], el["lat"], el["lon"]))
        elif el["type"] == "way":
            cs = [nodes[n] for n in el.get("nodes", []) if n in nodes]
            if cs:
                out.append((el["tags"],
                            sum(c[0] for c in cs) / len(cs),
                            sum(c[1] for c in cs) / len(cs)))
    return out


def simplify_ways(ways, tol_m=1.2):
    """Douglas-Peuckerで各wayの頂点を間引く(§4②のHTMLサイズ対策、2026-07-06)。
    tol_m≈1m なら徒歩地図の見た目はほぼ不変。依存ライブラリなしの平面近似
    (lngをcos(lat)補正)で十分な精度。"""
    import math

    def _dp(pts, tol):
        if len(pts) < 3:
            return pts
        cosl = math.cos(math.radians(pts[0][0]))
        ax, ay = pts[0][1] * cosl, pts[0][0]
        bx, by = pts[-1][1] * cosl, pts[-1][0]
        dx, dy = bx - ax, by - ay
        dmax, idx = 0.0, 0
        for i in range(1, len(pts) - 1):
            px, py = pts[i][1] * cosl, pts[i][0]
            if dx == 0 and dy == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
                d = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
            if d > dmax:
                dmax, idx = d, i
        if dmax * 111000 > tol:
            return _dp(pts[:idx + 1], tol)[:-1] + _dp(pts[idx:], tol)
        return [pts[0], pts[-1]]

    return [(tags, _dp(coords, tol_m)) for tags, coords in ways]


def process_railways(data):
    """Overpassの生データから (rail_ways, stations) を抽出・整形する。
    rail_ways: [(tags, coords), ...] 頂点間引き済み(tol=3m)
    stations: [(tags, lat, lon), ...] 同名駅ノードは平均座標に統合"""
    nodes = node_index(data)
    stations_raw = {}
    rail_ways = []
    for el in data["elements"]:
        t = el.get("tags", {})
        if not t:
            continue
        if t.get("railway") == "station":
            if el["type"] == "node":
                lat, lon = round(el["lat"], 6), round(el["lon"], 6)
            else:
                cs = [nodes[n] for n in el.get("nodes", []) if n in nodes]
                if not cs:
                    continue
                lat = sum(c[0] for c in cs) / len(cs)
                lon = sum(c[1] for c in cs) / len(cs)
            stations_raw.setdefault(t.get("name", ""), []).append((lat, lon))
        elif el["type"] == "way" and t.get("railway") in ("rail", "subway", "light_rail"):
            coords = [nodes[n] for n in el.get("nodes", []) if n in nodes]
            if len(coords) >= 2:
                rail_ways.append((t, coords))
    rail_ways = simplify_ways(rail_ways, tol_m=3.0)
    stations = []
    for nm, pts in stations_raw.items():
        lat = sum(p[0] for p in pts) / len(pts)
        lon = sum(p[1] for p in pts) / len(pts)
        stations.append(({"name": nm}, lat, lon))
    print(f"[report] 鉄道: {len(rail_ways)} 路線way、駅 {len(stations)}")
    return rail_ways, stations


# ---------------------------------------------------------------
# GeoJSON変換(表示はテンプレート側のLeaflet/JSが担当)
# ---------------------------------------------------------------
def ways_to_geojson(ways, keep=("name", "highway", "service")):
    """[(tags, [(lat,lon),...]), ...] -> GeoJSON FeatureCollection (LineString)
    keep: propertiesに残すタグキー(鉄道はrailway/tunnelも必要なため呼び出し側で指定可)"""
    features = []
    for tags, coords in ways:
        features.append({
            "type": "Feature",
            "properties": {k: v for k, v in tags.items() if k in keep},
            "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in coords]},
        })
    return {"type": "FeatureCollection", "features": features}


def points_to_geojson(pts, kind=None):
    """[(tags, lat, lon), ...] -> GeoJSON FeatureCollection (Point)。OSM由来点用。
    kind: properties.kind に固定値を付与したい場合(例: "shrine")"""
    features = []
    for tags, lat, lon in pts:
        props = {"name": tags.get("name", tags.get("name:en", ""))}
        if kind:
            props["kind"] = kind
        features.append({
            "type": "Feature", "properties": props,
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
        })
    return {"type": "FeatureCollection", "features": features}


def manual_points_to_geojson(items, kind=None):
    """items: [(name, lat, lon, desc), ...] -> GeoJSON FeatureCollection。
    視点場・時のアンカー(建築)・いまも食える歴史など手動データ用。
    desc はタップ時の解説シートに表示する本文。"""
    features = []
    for name, lat, lon, desc in items:
        props = {"name": name, "desc": desc}
        if kind:
            props["kind"] = kind
        features.append({
            "type": "Feature", "properties": props,
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
        })
    return {"type": "FeatureCollection", "features": features}


def lines_named_to_geojson(lines):
    """[(label, [(lat,lon),...]), ...] -> GeoJSON(消えた川など、ラベル付き推定線)"""
    features = []
    for label, coords in lines:
        features.append({
            "type": "Feature", "properties": {"name": label},
            "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in coords]},
        })
    return {"type": "FeatureCollection", "features": features}


def polygon_to_geojson(coords, name):
    """[(lat,lon),...](閉じてなくてOK) -> GeoJSON Polygon Feature"""
    ring = [[lon, lat] for lat, lon in coords]
    ring.append(ring[0])
    return {"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {"name": name},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }]}


def merge_feature_collections(*fcs):
    features = []
    for fc in fcs:
        features.extend(fc["features"])
    return {"type": "FeatureCollection", "features": features}
