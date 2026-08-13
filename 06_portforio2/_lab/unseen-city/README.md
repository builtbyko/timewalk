# UNSEEN CITY — Phase 2

実在する都市データをもとに、銀座周辺を静止した都市模型として描く独立Three.jsラボです。

## 現在の範囲

- 深い藍黒の背景
- 主要道路、鉄道、建物、旧河川の参考線形
- 最小限の照明と霧
- PC／スマートフォンの品質分岐
- 固定カメラ
- Resize、Visibility、WebGL context loss、Dispose
- 最小デバッグ表示

まだ実装しないもの:

- スクロールと30秒シーケンス
- 都市形成アニメーション、粒子モーフ
- 地層分離、亀裂、地下河川への降下
- TimeWalkへの遷移
- 音、複雑なUI、ポストプロセス
- 本番ページとの統合

## ローカル確認

リポジトリrootで次を実行します。起動時にPC用とスマートフォン用のURLが表示されます。

```powershell
python 06_portforio2/_lab/unseen-city/tools/serve_lab.py
```

`file://` ではES modulesとデータfetchが動作しません。`python -m http.server` でも表示はできますが、キャッシュが効いて `js/config.js` の変更が反映されないことがあります。上のスクリプトは `Cache-Control: no-store` を返すため、リロードするだけで変更が反映されます。

検証時はクエリを追加できます。

- `?debug=1`: 読込状態、品質tier、建物数、draw call、triangle数を表示
- `?quality=high` / `medium` / `low`: 自動判定を一時的に上書き

### スマートフォン実機で開く

1. PCとスマートフォンを同じWi-Fiに接続する
2. 上のコマンドを実行し、表示された `phone:` のURLをスマートフォンで開く
3. 確認が終わったら Ctrl+C でサーバーを止める

同じネットワーク上の端末から見える状態になります。確認が済んだら止めてください。URLが表示されない、またはスマートフォンから開けない場合は、WindowsファイアウォールがPythonの受信接続を許可しているかを確認します。

実機で見る項目は [[05_Phase2_制作計画・判断記録]] の「動作確認」を参照してください。縦横、回転、address bar変化、連続表示の発熱が対象です。

## データ

ブラウザが読むのは `data/` 内の軽量化した派生GeoJSONだけです。rawのOverpass応答は保存しません。再生成方法と出典は `tools/prepare_city_data.py`、`DATA_SOURCES.md`、`data/manifest.json` を参照してください。

旧河川は参考線形であり、公式境界、正確な流路、地下位置、深度を示すものではありません。

## 公開

このラボは現時点でローカル検証用です。`docs/`、公開TimeWalk、package、lock、ビルド設定には接続していません。
