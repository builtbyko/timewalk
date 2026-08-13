# UNSEEN CITY Repository Audit

> **Phase 2 canonical copy — 2026-07-20**  
> この文書は、Phase 2開始前にリポジトリrootの `_lab/unseen-city/` で作成した監査スナップショットを、正規ラボ `06_portforio2/_lab/unseen-city/` へ複製したものです。本文中の「未実装」「将来作成」は監査時点の記録であり、Phase 2の現在状態は同階層の `README.md` と実ファイルを正とします。

- 調査日: 2026-07-19
- 対象: リポジトリ全体のうち、公開TimeWalk、既存ラボ、Three.js技術資産、地理データ、前処理、公開構成
- 目的: `_lab/unseen-city/` に独立したVertical Sliceを安全に作るための事前監査
- 今回の変更: 本報告書の追加のみ。コード、データ、依存関係、ビルド設定、公開ページ、Git履歴は変更していない

> **読み方**
>
> - 「確認済み」は、調査時点のファイル内容または読み取り専用の集計で確認できた事実を示す。
> - 「判断」「推奨」は、確認済み事実から導いた設計上の評価を示す。
> - 調査時点で親リポジトリと `05_portforio/` の双方に既存の未コミット変更がある。そのため、ローカルにあるThree.js群を「現在公開中の確定実装」とは扱わず、「調査時点の作業中技術資産」として評価した。

## 1. Executive Summary

### 結論

公開TimeWalkと再利用候補のThree.js実装は、同じ実行系ではない。公開入口 `docs/index.html` はLeafletによる静的地図であり、Three.jsは使用していない。一方、Three.js r185の技術資産は入れ子の `05_portforio/` に存在するが、調査時点の `05_portforio/index.html` からは読み込まれておらず、現行入口から切り離されている。

新ラボは、既存の画面表現や旧パイプラインを丸ごと移植せず、次の資産だけを小さく抽出するのが安全である。

1. `04_timewalk/scripts/map_toolkit.py` のOSM取得、局所簡略化、GeoJSON変換の考え方
2. 銀座周辺のOSM鉄道データと、用途を限定した歩行空間データ
3. `05_portforio/js/geo.js` の座標変換の基本式。ただし銀座中心・メートル基準へ再定義する
4. `05_portforio/js/cosmic-scene.js` のBufferGeometryによるPoints／LineSegments集約パターン
5. `05_portforio/js/quality.js` の軽量な品質tier判定を、DPR・viewport・FPS・端末条件へ拡張する考え方
6. `05_portforio/_lab/scroll-sync.js` の「scrollイベントでは値だけ取得し、描画更新はrequestAnimationFrameで行う」方式。これはPhase 2では使わず、後続フェーズの候補とする
7. 同梱Three.js r185の2ファイル。ただし入れ子リポジトリを横断参照せず、将来の公開配置を決めてからラボ内で完結させる

### Phase 2の主要ブロッカー

Phase 2で必要な銀座向けの建物footprint／高さ、主要道路、現況河川は、既存リポジトリ内に確認できなかった。現行の歩行ネットワークは主に `footway` 等で、主要道路ではない。既存の旧河川4線は推定参考線であり、現況河川、公式流路、地下深度、暗渠断面を表すデータではない。

したがってPhase 2へ進む前に、少なくとも以下を確定する必要がある。

- 対象bboxと銀座模型の局所座標原点
- 「河川」が現況水面を指すのか、推定旧河川を指すのか
- 銀座の建物データ源、利用条件、高さ欠損時の扱い
- OSMから主要道路と建物を新規取得してよいか
- ラボをローカル専用にするか、最終的に `docs/` 配下へ公開するか

### 再利用判断の要約

| 領域 | 評価 | 要点 |
|---|---|---|
| 銀座のOSM鉄道 | 高い | 街区スケールの候補。範囲クリップ、重複整理、線種・地下属性の分離が必要 |
| 銀座の歩行空間 | 中 | 路地・歩行空間には使えるが、主要道路ではない |
| 推定旧河川 | 限定的 | 歴史参考層としてのみ使用可能。公式流路・地下河川としては不可 |
| `map_toolkit.py` | 高い | 取得・変換・簡略化処理を整理して再利用可能 |
| Three.js r185 vendor | 高い | 2ファイル一組。配信パスとライセンス表記を維持する |
| BufferGeometry集約 | 高い | Draw callを抑える設計パターンとして再利用価値が高い |
| 粒子モーフ | 中 | 技術例として有用だが既存演出への依存が強く、シェーダーは新規設計が必要 |
| 既存カメラ／HUD／宇宙背景／粉塵 | 低い | 新デザインの要件と異なり、グローバル状態や既存構図への依存も強い |
| 建物生成／照明／ポストプロセス | 該当なし | 既存Three.js群に必要実装を確認できず、新規設計が必要 |

参考事例については、[The Monolith Project](https://themonolithproject.net/) と[制作解説](https://tympanus.net/codrops/2025/11/29/building-the-monolith-composable-rendering-systems-for-a-13-scene-webgl-epic/)から、静止画として成立する構図、連続する場面転換、2Dと3Dの責務分離、再利用可能なシステム単位という考え方だけを参照する。13シーン用の独自レンダリング基盤や表面的な意匠は再現しない。

## 2. 現在の技術構成

### 2.1 使用言語と実行方式

| 項目 | 確認結果 | 根拠 |
|---|---|---|
| 公開TimeWalk | フレームワークなしの静的HTML／CSS／JavaScript | `docs/index.html:7-10,335-580` |
| 地図ライブラリ | Leaflet 1.9.4、Leaflet LocateControl 0.79.0をCDN読込 | `docs/index.html:7-10` |
| Three.js | r185をローカル同梱 | `05_portforio/vendor/three.core.min.js:6`、`05_portforio/vendor/three.module.js:6` |
| Three.js側のモジュール | ブラウザnative ES modules | `05_portforio/js/cover.js:9-12` 等 |
| データ前処理 | Python | `04_timewalk/scripts/*.py`、`05_portforio/tools/*.py` |
| データ形式 | GeoJSON、JSON、Float32／Uint32／Uint16バイナリ、HTML内埋込JSON | `docs/index.html:335-344`、`05_portforio/data/rail-*` |
| npm／Vite／Webpack | 該当なし | `package.json`、lock、Vite／Webpack設定はリポジトリ内で確認できず |

公開TimeWalkは `L.map()` を生成するLeafletアプリである（`docs/index.html:372-376`）。Three.jsで描かれるTimeWalkが公開入口に存在するわけではない。この区別は、再利用対象を誤認しないために重要である。

OSS公開の基礎ファイルである `README.md`、`.gitignore`、`LICENSE`、`data/README.md`、`requirements.txt` と、Pages入口 `docs/index.html` はいずれも存在する。新ラボの公開判断時にも、これらとデータ出典を同時に更新対象としてレビューする必要がある。

### 2.2 ライブラリと依存関係

- ルート `requirements.txt:1-6` は `folium`、`geopandas`、`matplotlib`、`numpy`、`pandas`、`requests` を列挙する。
- `04_timewalk/scripts/map_toolkit.py:12-17,30-41` のOverpass取得は主に `requests` を使用する。
- `05_portforio/tools/prepare_rail.py`、`prepare_population.py` は `geopandas`、`pandas`、`numpy` 等を使う。
- `05_portforio/tools/generate_shatter.py:24-25` はSciPyを使用するが、ルート `requirements.txt` にはSciPyがない。旧演出を再生成する場合の再現性ギャップだが、新ラボでは旧shatterを使わないため、Phase 2で依存を追加する理由にはならない。
- `EffectComposer`、`RenderPass`、`UnrealBloomPass`、`OrbitControls`、`GLTFLoader` 等のThree.js examples追加モジュールは確認できなかった。

### 2.3 開発サーバーとビルド

- `05_portforio/README_SETUP.md:9-13` は、`05_portforio/` をdocument rootにして `python -m http.server 8000` を起動する手順を示す。`file://` ではES modulesとfetchが成立しない。
- 公開TimeWalk側には、リポジトリ全体を起動する統一コマンドは確認できなかった。
- `04_timewalk/scripts/ginza_build.py:379-490` はOverpass取得、GeoJSON変換、テンプレート注入を行い、`04_timewalk/ginza/index.html` を生成する。
- 別系統の `scripts/timewalk_ginza_build.py:21-23,288-324` は `docs/ginza/index.html` を直接生成する。両者の入力・出力・データ制限は同一ではない。

### 2.4 GitHub Pages公開

- `README.md:88-113` は `04_timewalk/` を編集元、`docs/` をGitHub Pages公開コピーとして説明する。
- 公開入口は `docs/index.html`、銀座別入口は `docs/ginza/index.html`。
- `docs/.nojekyll` が存在する。
- `.github/` とデプロイworkflowは確認できず、`04_timewalk/ginza/index.html`、`docs/index.html`、`docs/ginza/index.html` の同期処理も確認できなかった。調査時点で3ファイルは同じ内容だったが、手動同期か別手順かは未確認である。
- 実際のGitHub Pages source設定はリポジトリ外の設定であり、未確認。

## 3. 本番TimeWalkとラボの構造

### 3.1 公開TimeWalk

| 責務 | 主なファイル | 内容 |
|---|---|---|
| 公開入口 | `docs/index.html` | Leaflet、CSS、埋込GeoJSON、描画・UIロジックを含む単一HTML |
| 銀座入口 | `docs/ginza/index.html` | 調査時点では公開入口と同内容 |
| 編集側生成物 | `04_timewalk/ginza/index.html` | `ginza_build.py` の出力先 |
| テンプレート | `04_timewalk/scripts/ginza_template.html` | Leaflet、レイヤー、スライダー、出典表示の雛形 |
| 主ビルダー | `04_timewalk/scripts/ginza_build.py` | OSM取得、手動データ結合、HTML生成 |
| 地理処理 | `04_timewalk/scripts/map_toolkit.py` | Overpass、簡略化、GeoJSON変換 |
| 代替ビルダー | `scripts/timewalk_ginza_build.py` | `docs/ginza/index.html` を別方式で生成 |

`docs/app.js`、`docs/styles.css`、`docs/src/*.js` は調査時点の `docs/index.html` から参照されていないため、公開TimeWalkの共有ランタイムとは見なさない。

### 3.2 既存ラボとThree.js側

- ルート直下に `_lab/` は存在しなかった。本報告書の保存先として `_lab/unseen-city/` だけを新設した。
- 既存ラボは `05_portforio/_lab/` にあり、`shatter`、`scroll-sync`、cosmic styleframe等を含む。
- `05_portforio/` は独自の `.git` を持つ入れ子リポジトリである。親側ではgitlinkとして扱われる一方、`.gitmodules` は確認できない。親リポジトリをcloneしたときに内容が再現される保証がない。
- 調査時点の `05_portforio/index.html:63-75` はインラインの静的ページ用スクリプトのみで、`js/cover.js` やThree.js用DOMを読み込まない。
- 旧3Dパイプラインの意図された流れは `cover.js` → `unfold.js` → `convergence.js` → `journey.js` だが、現在の入口とは未接続である（`05_portforio/js/cover.js:9-12,101-135`）。

### 3.3 共有モジュールの実態

公開TimeWalkと `05_portforio/_lab/` が共有するランタイムモジュールは**該当なし**である。

一方、旧3Dパイプラインと `05_portforio/_lab/` は次を共有する。

- Three.js本体: `05_portforio/vendor/three.module.js` と `three.core.min.js`
- 座標変換: `05_portforio/js/geo.js`
- 人口・鉄道ローダー: `05_portforio/js/act3-data.js`
- 粒子・線・背景の生成: `05_portforio/js/cosmic-scene.js`
- 品質判定: `05_portforio/js/quality.js`

### 3.4 本番へ影響しない独立ラボの条件

**確認済み:** ルート `_lab/unseen-city/` は `docs/index.html` から参照されず、現在のPages公開範囲にも自動では入らない。この場所でローカル検証する限り、本番TimeWalkへ影響しない。

**推奨:** 新ラボは次の原則で隔離する。

1. 既存productionファイルを編集せず、必要な処理だけを新ラボ用に抽出する。
2. `05_portforio/` のファイルへ実行時に直接依存しない。gitlink、Pages配信範囲、URL階層の3点で不安定だからである。
3. アセットURLは文書ルートではなく、モジュール自身または明示したasset baseを基準にする。
4. 公開が必要になった段階で、`docs/_lab/unseen-city/` へのレビュー済み配置方法を別途決める。今回は行わない。
5. `docs/index.html` からのリンク追加は、Vertical Slice完成後の別フェーズとする。

### 3.5 URLと相対パスの注意

- GitHub project Pagesはドメイン直下ではなくプロジェクトのサブパスで配信される。`/assets/...`、`/_lab/...`、`<base href="/">` はドメインrootを参照し、破損し得る。
- 既存cosmicラボは `<base href="/">` と `src="/_lab/..."` を使用するため、`05_portforio/` をローカルdocument rootにした場合に限定された構成である。
- `05_portforio/js/act3-data.js:9-18` の `fetch("./data/...")` はモジュール位置ではなくHTML文書URLを基準にする。別階層からimportすると誤ったdata URLになる。
- Three.js r185は `three.module.js` が同階層の `three.core.min.js` を読むため、片方だけの移動・配信では動作しない。

## 4. Three.jsの主要処理

### 4.1 全体フロー

| 項目 | 主な実装 | 監査結果 |
|---|---|---|
| WebGL／motion gate | `05_portforio/js/cover.js:18-36` | WebGL存在と `prefers-reduced-motion` を確認 |
| Scene／Renderer | `unfold.js:431-447` | `WebGLRenderer({ antialias:true, alpha:true })`、DPR上限2、OrthographicCamera |
| 本編Camera | `convergence.js:407-420` | PerspectiveCameraと固定composition |
| 構図計算 | `cosmic-scene.js:45-66` | `compositionPosition()`、`applyComposition()` |
| Controls | `journey.js:188-233` | OrbitControlsではなくPointer Eventsによる独自オービット |
| Scroll同期 | `journey.js:43-80,91-125,155-180,355-442` | native scroll値を読み、カメラと表示を更新 |
| Animation loop | `cover.js:72-98`、`unfold.js:504-523,549-567`、`convergence.js:486-545`、`journey.js:355-442` | フェーズごとに複数rAF。最終journeyは停止条件なし |
| Resize | `unfold.js:449-458`、`convergence.js:423-429`、`journey.js:169-180` | 複数箇所に重複。単一ライフサイクルではない |
| Scene切替 | `cover.js:101-135` | 同じRenderer／Sceneを段階的に引き渡す設計 |

### 4.2 ShaderMaterial、BufferGeometry、Points

- `cosmic-scene.js:151-213` にPoints／LineSegments用vertex・fragment shaderがある。
- `makeRevealPoints()` と `makeRevealLines()`（`cosmic-scene.js:293-321`）は、1レイヤーを1つのBufferGeometryへ集約する。Draw call抑制の基本パターンは再利用価値が高い。
- `convergence.js:70-155,219-342` は `startPos` と `targetPos` をGPUで補間する粒子モーフを実装する。地域遅延、エッジ発光、ポインタ反応が同じshaderへ密結合している。
- `convergence.js:161-214,378-405` は鉄道パルスを生成する。
- `unfold.js:89-163,180-300` は旧粉塵演出であり、新デザインでは流用対象外。
- `shatter.js:59-104,135-170` はDOM画面を90破片へ分ける表現で、地理的な地表亀裂ではない。
- `InstancedMesh` はリポジトリ内で確認できなかった。

### 4.3 Post-processing、照明、モデル

以下はリポジトリ検索で該当なし。

- `EffectComposer`、`RenderPass`、`UnrealBloomPass`
- `WebGLRenderTarget`
- `TextureLoader`、`GLTFLoader`
- `InstancedMesh`、`ExtrudeGeometry`
- Three.jsのLight、Fog、Shadow
- PBRマテリアルや明示的なtone mapping

既存の発光は主に `AdditiveBlending` とソフトなPoint spriteで作られ、Bloomではない。`convergence.js:11-13` にもpost-processingを使わない旨がある。Phase 2で必要な建物生成、道路・河川の帯形状、最小照明は新規設計が必要である。

### 4.4 Texture／Model／データ読み込み

- `act3-data.js:8-27` は人口JSON、鉄道meta JSON、3本のtyped-arrayバイナリを `Promise.all()` で読む。
- `cover.js:106-123` はユーザー操作後にデータ先読みと演出を並行開始する。
- `unfold.js:533-590` は標準暗転時間の後、最大1.5秒だけデータを追加待機し、静的フォールバックへ進む。
- `timewalk-scene.js:120-136` は `Image()` で背景を読み、失敗時にCSS fallbackを使用する。
- Three.js textureの実例は `shatter.js:208-213` の `CanvasTexture` が中心で、3D model loaderはない。
- fetchのHTTP status確認、AbortController、進捗通知、再試行は確認できない。

### 4.5 Disposeとライフサイクル

部分的なdisposeは存在する。

- Dust／fragment／ember: `unfold.js:524-531,568-575`
- 一時Ignition: `convergence.js:536-541`
- TimeWalk Canvas側のDOM／listener: `timewalk-scene.js:512-517`
- ReadMyCity Canvas側: `readmycity-scene.js:418-423`

ただし、`initJourney()` はdispose関数を返さず、永続Scene、Renderer、主要Geometry／Material、最終rAF、グローバルevent listenerを終了する経路がない。`unfold.js` と `convergence.js` の一部resize listenerは無名関数で削除できない。`shatter.js:260-261` はGroupを外すだけで、90個のGeometry／MaterialとCanvasTextureをdisposeしない。

## 5. 再利用可能な地理データ

### 5.1 データ一覧

量は調査時点の読み取り専用集計である。「CRS記載なし」は、座標値から用途を推測して採用してよいという意味ではなく、元メタデータの確認が必要であることを示す。

現行TimeWalkの取得bboxは `(south=35.6645, west=139.7590, north=35.6755, east=139.7720)` である（`04_timewalk/scripts/ginza_build.py:40-41`）。ただし、Overpassで交差したway全体を取り込む処理があるため、特に鉄道はこのbbox外まで伸びる。新ラボでは表示bboxとデータclip範囲を別々に明示する。

| データ | パス／識別子 | 形式・量 | 対象地域・座標系 | 現用途 | 新ラボでの評価 |
|---|---|---|---|---|---|
| 銀座歩行空間 | `04_timewalk/data/_overpass_ginza_walk_cache.json`、公開埋込 `DATA_WALKNET` (`docs/index.html:336`) | GeoJSON相当。2,076 LineString、5,388頂点、公開payload約373KB | 銀座周辺、OSM経緯度。GeoJSON出力は `[lon,lat]` | Leafletの歩行空間・路地 | **抽出・整理すれば流用可能**。主にfootwayで主要道路ではない。範囲クリップ、線種別集約、ODbL表記が必要 |
| 銀座鉄道・駅 | 同rail cache、`DATA_RAIL_LINES`／`DATA_RAIL_STATIONS` | 313 LineString、1,158頂点、約73KB。駅15点 | 銀座周辺、OSM経緯度 | Leafletの鉄道・駅 | **抽出・整理すれば流用可能。高価値。** `rail`／`subway`／`light_rail`／`tunnel`別に整理し、新bboxへクリップする。`tunnel=yes` は深度ではない |
| 推定旧河川・堀 | `04_timewalk/scripts/ginza_build.py:47` の `LOST_WATERWAYS`、`DATA_RIVERS` | 4 LineString、19頂点、約1KB | 銀座周辺、手動経緯度、CRS記載なし | Leafletの参考破線 | **歴史参考層に限定して抽出・整理すれば流用可能**。公式流路、現況河川、地下河川、深度としては不可 |
| 旧ビルダー主要線 | `scripts/timewalk_ginza_build.py:37` の `SKELETON_LINES` | 手動3線 | 銀座、参考座標 | 旧ビルダーの編集線 | **新規に作り直すべき**。現行主ビルダーでは未使用で、主要道路の実形状には不足 |
| POI／アンカー | `DATA_GALLERY`、`DATA_ANCHORS`、`DATA_VIEWPOINTS`、`DATA_FOOD`、`DATA_NIGHT` | 画廊35点、アンカー19点、視点7点、飲食7点、推定範囲1面 | 銀座、OSM点と手動点の混在 | 解説・POI | **強く依存しており流用困難**。建物アンカーは5点のみでfootprint、高さ、階数がない |
| 年代別空中写真 | `ginza_template.html:206-216` のGSI tile定義 | ローカルファイルなし。4系統のリモートtile | 1945–50、1961–69、1974–78、現在 | Leafletタイムスライダー | **後続フェーズで条件付き**。古地図ではなく空中写真。texture化、キャッシュ、再配布前に利用条件確認が必要 |
| 全国鉄道 | `05_portforio/data/raw/N02-23/...`、`05_portforio/data/rail-*.bin` | 原GeoJSON約14.2MB、21,949線／405,083頂点。加工後約494KB、45,288点 | 全国、元メタデータはJGD2011経緯度 | 全国鉄道の粒子・線 | **加工方式のみ流用可能**。0.006度、約500mで簡略化済みのため銀座街区には不適切 |
| 全国人口 | `05_portforio/data/population-points.json` | JSON 93,313B、1,893市区町村点 | 全国。2020国勢調査人口を市区町村役場位置に配置 | 全国人口の点群 | **銀座には流用不可**。1kmメッシュでも人口重心でもない |
| 全国海岸線 | `portforio/tools/data/output/coastline.json` | JSON 57,859B、主要4島3,081頂点 | 全国、Natural Earth由来 | 旧Canvas日本列島 | **銀座・東京湾には流用不可**。処理パターンのみ参考。4島選別・0.003度簡略化済み |
| 粒子用地理点 | `portforio/tools/data/output/particles.json` | JSON 52,530B、2,800点 | 岡山市中心部、OSM駐車場境界由来 | 旧収束粒子 | **データは流用不可**。地域も意味も異なる |
| 岡山人流 | `01_okayama/data/flow/` | 基礎GeoJSON 172,529B／190 Polygon、ほか概略範囲・代表点 | 岡山市、基礎データはEPSG:4612 | 昼夜・都市条件分析 | **流用不可**。銀座ではなく、代表点・概略範囲を公式ジオメトリとして扱えない。再配布条件も未確認 |
| 岡山PLATEAU建物 | `01_okayama/data/plateau/_plateau_building_age.geojson` | 11,622,851B、22,595 Polygon | 岡山市、出力CRS記載なし | 建物年代分析 | **銀座には流用不可**。大きく、変換元とCRSの再現手順も要確認 |
| 岡山PLATEAU土地利用 | `01_okayama/data/plateau/_plateau_luse_core.geojson` | 480,384B、1,305 Polygon | 岡山市、出力CRS記載なし | 土地利用分析 | **銀座には流用不可** |

### 5.2 該当なし／未確認のデータ

| 必要データ | 結果 |
|---|---|
| 銀座の建物footprint／高さ | **該当なし**。建物アンカーはPointであり、建物生成には使えない |
| 銀座の主要道路 | **該当なし**。現行walk queryは主要道路を取得しない |
| 銀座の現況河川・水面 | **該当なし** |
| 東京湾の詳細海岸線 | **該当なし**。全国4島輪郭は街区・湾岸用途には粗い |
| 銀座・中央区の行政区域 | **該当なし** |
| 銀座の古地図ローカルファイル | **該当なし**。年代別空中写真のremote tile定義のみ |
| 地下河川／暗渠の深度・断面 | **該当なし** |
| 銀座の人流／人口メッシュ | **該当なし** |

### 5.3 精度とライセンス

- `ginza_build.py:345-347` は、旧河川を正確な流路トレースではないと明記する。外堀・汐留川・京橋川はKK線現況を代理線形とし、三十間堀川は年代別空中写真と照合して調整した参考線である。
- 人流の点は代表表示点、概略範囲は参考範囲であり、公式座標、公式境界、厳密メッシュとして扱わない。
- OSM派生データはattributionとODbL上の条件を維持する。raw cacheを公開せず、対象範囲へ絞った派生データと出典manifestを置く方針が適切である。
- GSI tile、国土数値情報、e-Stat、PLATEAUは、加工・配信方法ごとに利用条件とクレジット文を再確認する。
- 元データの再配布条件が未確認の人流rawデータは、新ラボへ含めない。

## 6. 再利用可能なコード

判定はユーザー指定の4分類へ統一した。「そのまま流用可能」でも、ファイル配置、ライセンス、URL、データ出典の確認は別途必要である。

| 資産・処理 | 根拠 | 判定 | 理由・条件 |
|---|---|---|---|
| Three.js r185の2 vendorファイル | `vendor/three.module.js:6`、`three.core.min.js:6` | **そのまま流用可能** | 2ファイル一組。入れ子repoを横断参照せず、将来のラボ公開単位内に置く |
| 決定的乱数 `makeRng()` | `cosmic-scene.js:30-38` | **そのまま流用可能** | 描画デザインへの依存が小さい |
| OSM way抽出 `extract_ways()` | `map_toolkit.py:78-86` | **そのまま流用可能** | 単純なnode参照解決。ただし出力manifestは別途必要 |
| `node_index()` | `map_toolkit.py:44-47` | **そのまま流用可能** | 小地域のOSM変換に利用可能。丸め精度はPhase 2で確認する |
| Overpass取得・cache | `map_toolkit.py:30-41` `overpass()` | **抽出・整理すれば流用可能** | query／bbox／取得日時／OSM timestampをcacheと結び付ける仕組みが不足 |
| 銀座鉄道query | `map_toolkit.py:65-75` `rail_query()` | **抽出・整理すれば流用可能** | 取得way全体が返るため、生成時にbboxへclipする |
| 歩行空間query | `map_toolkit.py:50-62` `walk_net_query()` | **強く依存しており流用困難** | 路地には有用だが主要道路要件を満たさない。道路queryは新設する |
| 局所簡略化 | `map_toolkit.py:106-132` `simplify_ways()` | **抽出・整理すれば流用可能** | 小地域向け。全国や緯度差の大きいデータへそのまま使わない |
| 鉄道処理 | `map_toolkit.py:135-166` `process_railways()` | **抽出・整理すれば流用可能** | 3m簡略化と駅統合が有用。駅平均点は公式中心点ではない |
| GeoJSON変換群 | `map_toolkit.py:172-238` | **抽出・整理すれば流用可能** | `[lon,lat]` 変換は使える。source、license、bbox、CRS、推定状態をproperties／manifestへ追加する |
| 全国鉄道binary化 | `prepare_rail.py:31-59` | **抽出・整理すれば流用可能** | flat typed array方式は有効だが、既存0.006度許容値は銀座には不可 |
| typed-array loader | `act3-data.js:8-27` | **抽出・整理すれば流用可能** | document相対URLをやめ、HTTP error、abort、進捗を扱う |
| 緯度経度投影 | `geo.js:11-22` `project()`／`unproject()` | **抽出・整理すれば流用可能** | 全国用の原点・縮尺を銀座中心・局所メートルへ再定義する |
| Points／LineSegments集約 | `cosmic-scene.js:293-321` | **抽出・整理すれば流用可能** | バッチ化パターンは有効。既存色、AdditiveBlending、属性、shaderは外す |
| 粒子モーフ | `convergence.js:70-155,219-342` | **強く依存しており流用困難** | 地域遅延、既存色、エッジ、ポインタが一体化。将来必要部分だけ再設計する |
| 鉄道layer builder | `cosmic-scene.js:603-663` `buildRailLayerData()` | **強く依存しており流用困難** | 非export、全国投影、dust、色、遅延、パルスへ密結合 |
| Camera球面配置 | `cosmic-scene.js:45-66` | **抽出・整理すれば流用可能** | 数式だけ参考にできるが、既存 `COMP` 値と構図は使わない |
| Scroll magnetism | `_lab/scroll-sync.js:31-69`、`journey.js:43-80` | **抽出・整理すれば流用可能** | native scrollとrAFの分離は有用。Phase 2では未使用 |
| 既存Camera path | `journey.js:91-125` `PATH_KEYS` | **新規に作り直すべき** | 旧作品紹介と既存カメラ構図専用 |
| 品質tier | `quality.js:4-12` | **抽出・整理すれば流用可能** | GPU、viewport、DPR、実測FPS、回転後の再評価が不足 |
| Loading待機・fallback | `unfold.js:533-590` | **抽出・整理すれば流用可能** | bounded waitの考え方は有用。旧暗転演出とDOM依存は外す |
| シーン引継ぎ | `cover.js:101-135` | **強く依存しており流用困難** | 複数演出、既存DOM、グローバルlistenerへ密結合 |
| 建物生成 | 該当なし | **新規に作り直すべき** | footprint、高さ、InstancedMesh／batched geometryの設計が必要 |
| 道路・河川の帯形状 | 該当なし | **新規に作り直すべき** | 既存LineSegmentsは実質細線で、側面カメラの都市模型に不足 |
| Post-processing | 該当なし | **新規に作り直すべき** | Phase 2では導入せず、必要性を静止画評価後に判断する |
| Dispose／pause／resume | 部分実装のみ | **新規に作り直すべき** | App単位の明示的ライフサイクルが必要 |

## 7. 再利用しない方がよい実装

ここでの評価は既存作品の否定ではない。目的、画角、データ密度、公開単位が異なる新Vertical Sliceへ持ち込んだ場合のリスクを示す。

### 7.1 宇宙背景と既存発光地図

`cosmic-scene.js:215-288,324-339` の全画面shaderは宇宙背景と星雲を作り、4-octave FBMを1ピクセルにつき複数回評価する。新しい都市テーマで除外予定の表現であり、DPR 2ではfill-rate負荷も高い。ファイル全体をimportせず、必要ならGeometry集約の関数形だけ抽出する。

### 7.2 既存Camera path、HUD、UI

`journey.js` は旧作品の章立て、`PATH_KEYS`、DOM、HUD、Pointer orbit、TimeWalk／ReadMyCity Canvasを一つの永続rAFで更新する。毎frameの `innerHTML` 更新や自治体全件走査も含む。新しい30秒シーケンス、タイポグラフィ、固定画角とは責務が異なり、流用するとデザインと状態管理が再び密結合する。

### 7.3 粉塵と旧Unfold

`unfold.js:40-86` は画面サイズCanvasを `getImageData()` し、全pixelを走査する。Full HD／DPR 2ではRGBA bufferだけで概算32MiBになる。`buildNetworkFragments()` (`:247-276`) は候補同士の二乗探索を含む。粉塵は新デザインで明示的に除外されており、技術面でも持ち込まない。

### 7.4 旧Shatter

`shatter.js:59-104` は90 fragmentごとにGeometry、Material、Meshを作るため約90 draw callとなり、終了時disposeも不足する。これは画面破砕であり、銀座地表の地理的な亀裂ではない。後続フェーズの亀裂は、地表geometryとデータ層の意味に合わせて新規設計する。

### 7.5 Canvas版TimeWalk／ReadMyCity

`timewalk-scene.js:1-23` は、背景都市、道路状の光、水路glow、動的route等が実データではなく構図用のartistic gestureだと明記する。地理データや建物生成処理として流用しない。画像preload、fallback、arc-length補間等の一般的な考え方だけを参考にできる。

### 7.6 旧3Dパイプライン全体

複数のresize listener、段階ごとのrAF、dispose不在、現在のHTMLとの未接続、未追跡／未コミット資産が重なっている。新ラボは、Renderer、Scene、Camera、resize、visibility、context loss、disposeを一つのAppライフサイクルに集約する方が安全である。

## 8. モバイル・パフォーマンスの現状

### 8.1 モバイル対応

| 項目 | 現状 | 根拠・注意 |
|---|---|---|
| Device Pixel Ratio | あり | 多くのThree.js／Canvas実装で `Math.min(devicePixelRatio, 2)`。動的調整はない |
| 画面・端末別品質 | あり | `quality.js:4-12` がCPU core、deviceMemory、coarse pointerを使用 |
| 粒子数削減 | あり | `convergence.js:34-38` はhigh 72／medium 44／low 24 per municipality。幅640px以下はlow (`:435-441`) |
| 建物数削減 | 該当なし | 建物生成自体がない |
| タッチ操作 | 部分対応 | `journey.js:188-233` のPointer Events。pinch、二本指、pointer captureはない |
| Resize | あり | 複数moduleで実装され、重複呼び出しになる |
| `visualViewport` | 部分対応 | `journey.js:176-180`、`_lab/scroll-sync.js:143-147` |
| `orientationchange` | 該当なし | resize任せ。品質再生成もない |
| iPhone向け高さ | 実験例あり | `_lab/scroll-sync.html:17-25` の `100svh`。現行入口への適用は未確認 |
| `prefers-reduced-motion` | あり | `cover.js:30-36` は3D体験を開始しない。設定変更の監視はない |
| 非表示・復帰 | 該当なし | `visibilitychange`、`pagehide`、`pageshow`、pause／resumeなし |
| WebGL context lost | 該当なし | `webglcontextlost`／`webglcontextrestored` のアプリ対応なし |
| 動的品質低下 | 該当なし | FPS計測や熱・frame budgetに応じたdowngradeなし |

WebGL capability gateにも注意が必要である。`cover.js:18-24` はWebGL1 contextの存在を確認する一方、同梱r185のRendererはWebGL2を前提とする。WebGL1だけの端末では、gate通過後にRenderer生成で失敗し得る。

### 8.2 既存Three.js資産の負荷

読み取り専用で現行データと生成式を集計した概算は次の通り。

| tier | 日本列島の主Points | 全Points概算 |
|---|---:|---:|
| high | 163,098 | 228,085 |
| medium | 100,529 | 165,314 |
| low | 55,790 | 120,799 |

lowでもrail dust約23,052点、artistic continent約41,800点等が削減されない。Draw callはBufferGeometry集約により完成Sceneで概算11と少ないが、AdditiveBlendingの重なりによるoverdrawとfill-rateが大きい。高品質の収束粒子は属性だけで最低約10.6MiB、生成中はJS Arrayと複数copyが併存する。

### 8.3 CPU、DOM、ロードのリスク

- `cosmic-scene.js:354-370` の `computeEdgeness()` は自治体数の二重loop。
- `buildLatticeData()` (`:551-595`) も二重loopと各点sortを含む。
- `journey.js:299-313` は毎frame 1,893自治体をprojectし、pointer active時はさらに全件hit test (`:256-289`)。
- 選択変更時に45,288鉄道点を全探索する (`journey.js:244-253`)。
- HUDの `innerHTML` を毎frame更新する (`journey.js:291-313`)。
- `journey.js:439-441` は停止条件のないrAFで、非表示時はブラウザのthrottleに依存する。
- `act3-data.js` はHTTP errorやabortを扱わず、相対URLも文書基準である。
- 公開TimeWalkは約505KBの単一HTMLで、埋込地理データが約469KBを占める。新ラボでは必要レイヤーだけを個別・最小化して読み込むべきである。

### 8.4 画像・動画・不要アセット

`05_portforio/_lab/` には比較用PNGと複数のWebMがあり、数MB単位のファイルを含むが、runtime参照されていない。新ラボへ既存ラボ一式をコピーしない。Phase 2は地理データとコードだけで成立させ、画像・動画を背景として使わない。

## 9. 技術的リスク

| 優先度 | リスク | 確認済み事実 | Phase 2前の対応 |
|---|---|---|---|
| Blocker | 建物データ欠落 | 銀座footprint／高さなし | データ源、利用条件、bbox、高さ欠損規則を決める |
| Blocker | 河川の意味が未確定 | 現況河川なし。旧河川は4本の推定参考線のみ | 現況水面か歴史参考線かを明文化する |
| High | 主要道路データ欠落 | 現行queryはfootway等のみ | OSM highway classを定義し、新規抽出・clipする |
| High | 地理的意味の混同 | `tunnel=yes` は深度でなく、旧河川も地下実形状でない | 各featureにsource、status、年代、推定／実測区分を持たせる |
| High | ライセンス／再配布 | OSM、GSI、国土数値情報、e-Stat、PLATEAU、人流で条件が異なる | `data/manifest.json` とクレジット方針を先に作る。未確認rawは含めない |
| High | 入れ子repo依存 | `05_portforio/` はgitlinkかつ `.gitmodules` なし | ラボから直接importせず、承認済み最小資産だけをラボ内へ置く |
| High | Pages相対パス | project Pagesはサブパス。既存ラボにroot absolute URLあり | 公開先を確定し、root absolute URLと `<base href="/">` を避ける |
| High | ライフサイクル不足 | rAF停止、visibility、context loss、完全disposeがない | Appに `start/pause/resume/dispose` と単一resizeを持たせる |
| High | モバイルoverdraw／メモリ | 低品質でも12万点超、加算合成、重い全画面shader | 旧cosmic sceneをimportせず、Phase 2は静的geometryと最小materialから始める |
| Medium | ビルド系統の分岐 | TimeWalk生成scriptが2系統、公開3HTMLの自動同期なし | 新ラボは既存ビルダーを変更しない。公開工程は完成後に別途一本化を検討 |
| Medium | 現行3D入口が不明 | 3D modulesは現在の `05_portforio/index.html` から未接続 | 動作確認済みproductionコードとみなさず、処理単位で検証する |
| Medium | WebGL2／端末互換 | gateとRenderer要件が一致しない | 明示的なWebGL2検査と静的fallbackをPhase 2の土台に含める |
| Medium | ロード失敗時の可観測性 | status、timeout、abort、進捗が限定的 | asset loaderに明示的な結果とfallbackを持たせる |
| Medium | 実機基準なし | PC／スマートフォンの対象端末、frame budget未確認 | Phase 2で代表端末と品質別上限を決め、静止画状態で計測する |

## 10. 推奨ディレクトリ構成

以下は**将来の提案**であり、今回作成したのは `REPOSITORY_AUDIT.md` だけである。30秒のVertical Sliceに必要な責務へ絞り、一般化しすぎない。

```text
_lab/unseen-city/
├─ index.html                  # ラボだけの入口
├─ styles.css                 # 2D UIとfallback
├─ REPOSITORY_AUDIT.md        # 本報告書
├─ DATA_SOURCES.md            # 人が読む出典・精度・利用条件
├─ vendor/
│  ├─ three.module.js         # 既存r185の承認済みコピー
│  └─ three.core.min.js       # 必ず上と一組
├─ data/
│  ├─ manifest.json           # bbox、元CRS、出力単位、取得日、簡略化、ライセンス
│  ├─ roads.geojson           # 主要道路と必要なら歩行空間
│  ├─ rail.geojson            # 銀座範囲へclipした鉄道
│  ├─ waterways.geojson       # 意味を確定後。推定状態をpropertiesへ保持
│  └─ buildings.geojson       # 承認済みデータ源から生成
├─ js/
│  ├─ app.js                  # Scene/Renderer lifecycle、resize、visibility、dispose
│  ├─ config.js               # bbox、色以外の数値、品質別上限、camera preset
│  ├─ quality.js              # PC/mobile判定とDPR・負荷上限
│  ├─ assets.js               # fetch、進捗、error、abort、fallback
│  ├─ geo.js                  # 銀座局所メートル座標への統一変換
│  ├─ city.js                 # 道路・鉄道・河川・建物の生成とdispose
│  ├─ camera.js               # 固定構図と後続camera pathの境界
│  ├─ sequence.js             # Phase 3以降の30秒シーケンス
│  ├─ scroll.js               # Phase 3以降のscroll正規化
│  ├─ layers.js               # Phase 3以降の地層分離
│  ├─ underground.js          # Phase 3以降の地下河川表現
│  ├─ ui.js                   # Loading、入口、fallback。3D状態から分離
│  └─ shaders/
│     ├─ city.vert.js         # 必要になった時だけ追加
│     └─ city.frag.js
└─ tools/
   └─ prepare_city_data.py    # 必要なら1本だけ。取得・clip・簡略化・manifest生成
```

### 構成上の判断

- `city.js` はPhase 2では道路・鉄道・河川・建物をまとめ、レイヤーごとに細かいファイルへ分けすぎない。規模が増えたときだけ分割する。
- `sequence.js`、`scroll.js`、`layers.js`、`underground.js` は責務の置き場所を予約する考え方であり、Phase 2では作成しない。
- shaderはbuilt-in materialで静止画が成立するならPhase 2では作成しない。
- `tools/prepare_city_data.py` は新規取得が必要になった場合だけ作る。rawデータはラボへ置かず、派生した最小データとmanifestだけを版管理する。
- vendorをラボ内へ置く案は、入れ子repoへの実行時依存を避けるためである。新しいライブラリを追加する案ではなく、既存r185を同じライセンスのまま再配置する案である。実施前に公開配置を確定する。
- vendor再配置時は、既存のライセンスヘッダーと著作権表示を保持する。

## 11. Phase 2の最小実装計画

### 11.1 対象と非対象

Phase 2は、次を静止画として成立させる。

- 深い藍黒の背景
- 河川または合意済みの水系参考線
- 鉄道
- 主要道路
- 簡略化した建物
- 最小限の照明
- 映画的な固定カメラ
- PC／スマートフォン品質分岐の土台

スクロール、都市形成、地層分離、亀裂、地下降下、TIMEWALK接続、本番ページ変更は行わない。

### 11.2 Phase 2前に必須の決定

1. **地理範囲:** bbox、模型中心、地表の高さ基準、1 world unitの実距離を決める。
2. **水系の意味:** 現況河川か、推定旧河川か。旧河川なら「参考線」であることをデータとUIの両方に保持する。
3. **建物データ:** OSM footprintか、許諾済みPLATEAU等か。高さの実値、欠損補完、演出値を区別する。
4. **道路class:** `primary`、`secondary` 等、何を「主要道路」とするかを決める。既存walk dataで代用しない。
5. **配信先:** 当面root `_lab/` のローカル検証に限定するか、後に `docs/_lab/` へ複製するか。
6. **品質基準:** 代表PC／iPhone／Android、DPR、建物上限、目標frame timeを決める。

### 11.3 Phase 2で新規作成するファイル

既存ファイルの変更は不要とする。次の最小セットを将来、新ラボ内だけに作る。

| ファイル | Phase 2の責務 |
|---|---|
| `index.html` | Canvas host、loading、fallback。外部作品紹介UIは置かない |
| `styles.css` | 全画面layout、深い藍黒背景、最小loading／fallback |
| `DATA_SOURCES.md` | 出典、利用条件、精度、推定／公式の区別 |
| `vendor/three.module.js`、`three.core.min.js` | 既存r185のラボ内完結配置 |
| `data/manifest.json` | bbox、CRS、局所単位、取得日、簡略化、license、feature count |
| `data/roads.geojson` | 新規取得した主要道路。必要なら歩行空間を別classで含める |
| `data/rail.geojson` | 既存銀座OSM鉄道をclip・整理した派生データ |
| `data/waterways.geojson` | 意味確定後の現況水系または推定旧河川 |
| `data/buildings.geojson` | 承認済み銀座building footprintと高さ状態 |
| `js/app.js` | Scene、Renderer、単一resize、visibility、context loss、dispose |
| `js/config.js` | bbox、品質別DPR、building上限、camera preset |
| `js/quality.js` | PC/mobile初期判定。低品質ではDPR、antialias、建物数を生成前に決定 |
| `js/assets.js` | 並列load、HTTP error、abort、結果通知、fallback |
| `js/geo.js` | 全レイヤー共通の銀座局所メートル変換 |
| `js/city.js` | レイヤーごとのBufferGeometry、建物InstancedMesh候補、resource追跡 |
| `js/camera.js` | PC／mobileの固定カメラとlook target |
| `js/ui.js` | loading完了と静的fallbackのみ |

`sequence.js`、`scroll.js`、`layers.js`、`underground.js`、亀裂用shaderはPhase 2では作らない。

### 11.4 再利用する既存資産

| 既存資産 | Phase 2での使い方 |
|---|---|
| Three.js r185 vendor pair | 同一revisionをラボ内に置き、npmや新規libraryを導入しない |
| `map_toolkit.py` | OSM取得、way抽出、局所簡略化、GeoJSON化の処理を参考・抽出する |
| 銀座OSM鉄道 | bboxへclipし、線種・tunnel別に集約した派生データを作る |
| `geo.js` | 数式だけ参考にし、銀座中心・メートル基準で書き直す |
| `cosmic-scene.js` | `makeRevealPoints()`／`makeRevealLines()` のバッチ化パターンだけ抽出する |
| `quality.js` | tier判定の土台だけ抽出し、viewport、DPR、antialias、建物上限へ拡張する |
| `act3-data.js` | typed-arrayが必要になった場合の並列load方式だけ参考にする。Phase 2の小規模GeoJSONならbinary化を先行させない |

### 11.5 実装順と検証ゲート

1. **データ契約:** 4レイヤーのsource、bbox、CRS、status、licenseをmanifestで確定する。
2. **静的Scene:** Renderer、Camera、背景、最小照明だけでPC／mobile表示を確認する。
3. **地表線:** 河川、鉄道、主要道路をレイヤーごと1〜数個のBufferGeometryへ集約する。
4. **建物:** footprintから簡略化し、InstancedMeshまたは少数のbatched geometryへまとめる。個別Mesh大量生成を避ける。
5. **構図:** PC／mobile各1つの固定presetで、都市模型の側面・奥行きが静止画として成立するか確認する。
6. **品質:** draw call、GPU memory、初期化時間、DPR、低品質のbuilding数を実機で計測する。
7. **ライフサイクル:** resize、page visibility、context loss、dispose、load失敗のfallbackを確認する。
8. **停止:** 静止画が成立した時点でPhase 2を完了し、scrollや演出を追加しない。

Phase 2ではpost-processingを導入しない。固定カメラ、geometry、material、最小照明だけで画面が成立するかを先に判断する。Bloom等が必要かは、負荷計測と静止画レビュー後の別判断とする。

## 12. 調査した主要ファイル一覧

| パス | 調査した内容 |
|---|---|
| `AGENTS.md` | 公開、個人情報、データ精度、代表点、Pagesに関するリポジトリ規約 |
| `README.md` | 公開入口、編集元と `docs/` の関係、地理情報の注意書き |
| `.gitignore` | raw、cache、ローカル設定の除外範囲 |
| `data/README.md` | 再配布、出典、参考ジオメトリの方針 |
| `requirements.txt` | Python依存 |
| `docs/index.html` | 公開TimeWalk入口、Leaflet、埋込データ、レイヤー、UI |
| `docs/ginza/index.html` | 銀座公開コピー |
| `04_timewalk/ginza/index.html` | 編集側生成物 |
| `04_timewalk/scripts/ginza_template.html` | Leaflet template、GSI tile、クレジット |
| `04_timewalk/scripts/ginza_build.py` | bbox、旧河川、OSM取得、GeoJSON生成、HTML注入 |
| `04_timewalk/scripts/map_toolkit.py` | Overpass、簡略化、鉄道処理、GeoJSON変換 |
| `scripts/timewalk_ginza_build.py` | 代替ビルダーと別出力系統 |
| `05_portforio/index.html` | 調査時点の入口がThree.js未接続であること |
| `05_portforio/README_SETUP.md` | ローカルserver手順 |
| `05_portforio/vendor/three.module.js` | Three moduleの同梱関係 |
| `05_portforio/vendor/three.core.min.js` | Three.js revision r185 |
| `05_portforio/js/cover.js` | capability gate、reduced motion、旧フェーズ制御 |
| `05_portforio/js/unfold.js` | Renderer、OrthographicCamera、dust、loading、部分dispose |
| `05_portforio/js/convergence.js` | PerspectiveCamera、粒子モーフ、鉄道、品質、animation loop |
| `05_portforio/js/cosmic-scene.js` | ShaderMaterial、BufferGeometry、Points／LineSegments、背景shader |
| `05_portforio/js/journey.js` | Scroll、camera path、Pointer orbit、HUD、永続rAF |
| `05_portforio/js/geo.js` | 全国用の単純投影・逆投影 |
| `05_portforio/js/quality.js` | 端末品質tier |
| `05_portforio/js/act3-data.js` | JSON／typed-array load |
| `05_portforio/js/shatter.js` | 90 fragment、CanvasTexture、dispose不足 |
| `05_portforio/js/timewalk-scene.js` | Canvas2D、pre-rendered art、非地理的gesture、fallback |
| `05_portforio/js/readmycity-scene.js` | Canvas2D作品紹介とdispose |
| `05_portforio/_lab/scroll-sync.js` | native scroll同期、visualViewport、固定path実験 |
| `05_portforio/_lab/cosmic-styleframe-japan*.js` | 旧3D modulesの共有実績とstyleframe |
| `05_portforio/data/population-points.json` | 市区町村人口点の量と意味 |
| `05_portforio/data/rail-*` | 全国鉄道binaryの量と構造 |
| `05_portforio/tools/prepare_population.py` | e-Stat人口と役所点の結合、1km meshではないこと |
| `05_portforio/tools/prepare_rail.py` | N02鉄道の0.006度簡略化とbinary化 |
| `portforio/tools/prepare_coastline.py` | Natural Earth由来、4島選別、簡略化 |
| `portforio/tools/prepare_particles.py` | 岡山OSM駐車場境界からの粒子生成 |
| `01_okayama/data/flow/` | 岡山人流の代表点、概略範囲、基礎Polygon |
| `01_okayama/data/plateau/` | 岡山建物年代・土地利用GeoJSON |

## 13. 仮定と未確認事項

### 13.1 公開・リポジトリ状態

- 実際に現在配信されているWebページと、調査時点のローカル `docs/` が一致するかは未確認。ローカル公開ファイルに既存変更があるため、厳密な本番revisionは断定しない。
- GitHub Pagesのsource設定、deploy操作、cache更新方法は未確認。
- `04_timewalk/ginza/index.html`、`docs/index.html`、`docs/ginza/index.html` の正規同期手順は未確認。
- `05_portforio/` を正式submodule、通常directory、別repoのどれとして扱う意図かは未確認。
- `05_portforio/js/` のThree.js群が、どのrevisionで動作確認済みかは未確認。現行 `index.html` からは実行できない。

### 13.2 地理データ

- Phase 2の正確なbbox、中心点、地表基準、world unitは未確定。
- 「河川」が現況河川、旧河川、暗渠、都市記憶の比喩のどれを指すか未確定。
- 銀座の建物footprint／高さデータ源は未確認。
- 高さ欠損時に、実値、推定値、演出値をどう表示・記録するか未確定。
- 主要道路とみなすOSM highway classは未確定。
- 旧河川4線の位置は参考であり、地下河川降下の実形状へ接続できる根拠は未確認。
- 銀座の現況河川、詳細海岸線、行政区域、人口、人流、地下深度は該当データなし。
- GeoJSONにCRSが書かれていない岡山派生データは、元処理とメタデータの再確認なしにCRSを断定しない。

### 13.3 ライセンスと公開

- OSM、GSI、N02、P34、e-Stat、PLATEAUは出典を確認できるものがあるが、新ラボでの加工・配信・静止画利用に必要な最新条件とクレジット文は実装前に再確認する。
- 人流rawデータの再配布権と公開範囲は未確認であり、新ラボへ含めない。
- 年代別空中写真は古地図ではない。Three.js textureへの利用や焼き込みの可否は未確認。

### 13.4 端末・体験

- 代表PC、iPhone、Android、最低GPU、目標frame time、許容初期load時間は未確定。
- Three.js r185を使うWebGL2端末範囲と静的fallback要件は未確定。
- 30秒相当のscroll距離、各場面の秒数、reduced-motion時の代替構成はPhase 2対象外で未確定。
- The Monolith Projectは構成原則の参考であり、独自renderer、13 scene構造、素材、色、世界観を技術要件とは仮定しない。

---

本監査の推奨は、Phase 2を「新ラボ内だけで完結する、実データに根差した静止都市模型」として開始し、地理データの意味・出典・縮尺と、PC／mobileの描画予算を先に固定することである。既存TimeWalkから持ち込むのはデータ変換、局所データ、座標処理、BufferGeometry集約等の技術要素に限定し、色、UI、HUD、宇宙背景、粉塵、既存Camera path、画面遷移、作品紹介レイアウトは新規設計とする。
