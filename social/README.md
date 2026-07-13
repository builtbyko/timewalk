# TimeWalk social publishing

TimeWalkの投稿ストックを、GitHub ActionsからBufferへ送り、Xへ予約投稿するための仕組みです。日々の手動投稿をなくしつつ、事実確認と画像権利の確認は公開前に人が行います。

## 仕組み

1. `social/posts.json` に投稿を追加する。
2. 出典と画像の利用条件を確認する。
3. `approved` を `true`、`status` を `ready` にする。
4. GitHub Actionsが公開予定時刻の36時間前からBufferへ予約登録する。
5. 登録成功後、`status`、`buffer_post_id`、`queued_at`を自動更新する。

ワークフローは1日2回動き、1回につき最大2件だけ登録します。最初は必ず手動のドライランで確認してください。

## セキュリティ方針

- BufferはTimeWalk専用アカウントを作り、TimeWalk用Xだけを接続する。
- APIキーはGitHubのRepository secretにだけ保存し、ファイル、Issue、チャット、投稿データへ書かない。
- APIキーは実投稿ステップにだけ渡され、ドライランや検証処理には渡されない。
- GitHub公式Actionsは、変更不能なコミットSHAで固定している。
- ワークフローに与えるGitHub権限は、投稿済み状態を記録するための`contents: write`だけ。
- 当面、リポジトリの書き込み権限は自分以外に付与しない。
- APIキーを誤って表示・保存した場合は、Buffer側で直ちに無効化して再発行する。

## 初期設定

### 1. TimeWalk専用Bufferアカウントを作る

普段使いのBufferアカウントとは分けて、新しいアカウントを作ります。そのアカウントにはTimeWalk用Xだけを接続してください。

Bufferの **Settings → API** でAPIキーを1つ作成します。APIキーをスクリーンショット、メモ共有サービス、GitHubファイルへ保存しないでください。

### 2. XチャンネルIDを確認する

ローカルのPowerShellで、次を実行します。

```powershell
$env:BUFFER_API_KEY="ここにBufferのAPIキー"
python scripts/buffer_social.py channels
```

表示された一覧から、`service`がX/Twitterに該当する行の`channel_id`を控えます。確認後、同じPowerShellで必ず環境変数を消します。

```powershell
Remove-Item Env:BUFFER_API_KEY
```

APIキーをコマンド引数として渡す機能は、シェル履歴やプロセス一覧への露出を防ぐため用意していません。

### 3. GitHubへ安全に登録する

リポジトリの **Settings → Secrets and variables → Actions** で、次を登録します。

- **Repository secret**: `BUFFER_API_KEY`
- **Repository variable**: `BUFFER_CHANNEL_ID`

APIキーは必ずSecretへ入れます。`BUFFER_CHANNEL_ID`は認証情報ではないためVariableで構いません。

### 4. 手動テストする

GitHubの **Actions → Publish TimeWalk social posts → Run workflow** を開き、最初は`dry_run: true`で実行します。この実行ではAPIキー自体が処理へ渡されず、BufferやXへの送信も行われません。

内容を確認した後、公開してよいテスト投稿を1件だけ`ready`にし、`dry_run: false`で手動実行します。Xへ投稿されたことを確認するまでは、複数件を`ready`にしないでください。

## 投稿データ

```json
{
  "id": "ginza-example-001",
  "text": "投稿本文",
  "publish_at": "2026-08-01T20:00:00+09:00",
  "source_url": "https://情報確認に使ったページ",
  "image": {
    "url": "https://builtbyko.github.io/timewalk/social/example.jpg",
    "source": "Wikimedia Commonsの作品ページURL、またはself",
    "credit": "撮影者名",
    "license": "CC BY-SA 4.0",
    "rights_confirmed": true
  },
  "approved": true,
  "status": "ready",
  "buffer_post_id": null,
  "queued_at": null
}
```

画像を使わない投稿では、`image`を`null`にします。画像を使う場合、`url`はログイン不要で画像ファイルが直接開く恒久的なHTTPS URLにしてください。GitHub Pagesの`docs/`配下に置いた画像も使えます。

## 状態

- `draft`: 作成中。投稿されない。
- `ready`: 承認済みの投稿候補。`approved: true`が必要。
- `queued`: Bufferへの登録完了。再投稿されない。
- `cancelled`: 投稿対象外。

## ローカル確認

```powershell
python scripts/buffer_social.py validate
python scripts/buffer_social.py queue --dry-run --lookahead-hours 9999
```

`ready`にする前に、本文の事実、`source_url`、画像のライセンスとクレジットを確認してください。Webで見つけた画像を、利用条件の確認なしに登録しないでください。
