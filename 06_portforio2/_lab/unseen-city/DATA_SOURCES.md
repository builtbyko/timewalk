# UNSEEN CITY — Phase 2 data sources

このフォルダのデータは、銀座周辺の静止都市模型を作るために軽量化した表示用データです。測量成果、公式境界、建物高さの公的台帳、地下構造の実測値ではありません。ファイル単位の件数、取得時点、容量、制約は `data/manifest.json` を正とします。

## 対象範囲と座標

- 対象範囲: 銀座とその近傍
- 作業範囲: 西経ではなく東経 `139.7590–139.7720`、北緯 `35.6645–35.6755`
- GeoJSON座標: RFC 7946／OGC:CRS84のWGS 84経度・緯度順 `[longitude, latitude]`
- Three.js内の座標: このGeoJSONを原点近傍へ変換した表示座標。測量座標として扱わない

すべての形状は上記の作業範囲で実クリップされています。各GeoJSONの `bbox` は、クリップ後に収録された実形状の外接範囲です。元のOSM wayや旧河川参考線が範囲外へ続いていても、その座標は成果物へ残しません。

## OpenStreetMap由来データ

`roads.geojson`、`buildings.geojson`、`railways.geojson` は OpenStreetMap 由来です。

- Attribution: `© OpenStreetMap contributors`
- License: Open Data Commons Open Database License 1.0（ODbL 1.0）
- 公式案内: <https://www.openstreetmap.org/copyright>
- ライセンス本文: <https://opendatacommons.org/licenses/odbl/1-0/>

公開時は、上記の帰属表示とODbLで提供されるデータであることを、WebGL画面から確認できる位置に表示してください。派生データベースを配布する場合の条件は、公開形態を確定した段階で改めて確認します。

### `data/roads.geojson`

- Overpass APIから取得したOSM way
- motorway、trunk、primary、secondary、tertiaryと各linkだけを収録
- 現スナップショット: 273フィーチャー
- 1.2 m相当のDouglas–Peucker簡略化を適用
- 作業範囲を横断するLineStringは境界でクリップ
- 生活道路、歩行者通路、路地を含む完全な道路網ではない
- OSMの道路分類と線形であり、道路管理者が提供する公式道路形状ではない

### `data/buildings.geojson`

- Overpass APIから取得したOSM way／multipolygon relation
- `building=no` と `building=construction` は除外
- 現スナップショット: 2,524フィーチャー
- 作業範囲を横断するPolygon／MultiPolygonは境界でクリップ
- 実高さはOSM `height`、次に `building:levels × 3.2 m` を使用
- どちらもない建物は、模型の凹凸を作るための決定的な表示補完値を `display_height_m` に設定
- 現スナップショットでは2,325件が `visual_fallback`。これは実際の建物高さの推定値ではない
- 結合できないmultipolygonは安全のため除外
- OSMに未収録の建物は含まれず、完全な建物台帳ではない

高さの根拠は各フィーチャーの `height_basis` で必ず判別できます。画面上で事実データとして高さを比較する用途には使用しません。

### `data/railways.geojson`

- 既存TimeWalkの `04_timewalk/data/_overpass_ginza_rail_cache.json` を再処理
- rail、subway、light_railを収録
- 現スナップショット: 103フィーチャー
- 3 m相当のDouglas–Peucker簡略化を適用
- 既存cacheの313フィーチャーから、作業範囲と交差する部分だけを境界でクリップ
- OSMのway単位を維持しているため、並行線や重複に見える線があり得る
- `tunnel=yes` は「OSM上でトンネル分類」という属性だけを示す
- トンネル属性を深度、地下階、河川との上下関係へ変換しない

## 旧河川の参考線

### `data/historic-waterways-reference.geojson`

既存TimeWalkの `04_timewalk/scripts/ginza_build.py` にある手動トレース線を、表示用の4本のLineStringとして移植しています。

- 三十間堀川（参考線）
- 汐留川（参考線）
- 京橋川（参考線）
- 外濠（参考線）

すべて `reference_only: true`、`geometry_status: hand_traced_approximation` としています。これは公式境界、公式中心線、正確な河道幅、現在の地下河川、実測深度を示しません。歴史的事実として公開する前に、各線の根拠資料と解釈を別途確認してください。

4本とも作業範囲で実クリップされ、範囲外へ続く座標は成果物へ残していません。

## 再生成

ラボのルートから次を実行します。

```powershell
python tools/prepare_city_data.py
```

既存TimeWalkの鉄道cacheがある場合はそれを読み、主要道路と建物だけをOverpass APIから更新します。鉄道も更新する場合は次を使います。

```powershell
python tools/prepare_city_data.py --refresh-rail
```

Overpassが一時的に利用できず、既存の処理済み道路・建物・鉄道を同じ範囲で再クリップするだけの場合は次を使えます。これはネットワークへ接続せず、OSMスナップショットも更新しません。

```powershell
python tools/prepare_city_data.py --reuse-existing-surface
```

スクリプトはOverpassのrawレスポンスを保存せず、処理済みGeoJSONと `data/manifest.json` だけを書き出します。公開前には差分、件数、帰属表示、データ更新による構図変化を確認してください。

Overpassがエラー注記、空レスポンス、または既定の最低件数を下回る結果を返した場合は、既存成果物を上書きせず停止します。

## Phase 2での利用範囲

Phase 2では、これらを都市模型の形状と静的な素材差にだけ使用します。旧河川の地下化、鉄道トンネルの深度化、正確な建物高さ比較、地層の史実表現は行いません。
