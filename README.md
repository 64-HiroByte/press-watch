# PressWatch

PressWatch は、環境省の報道発表を収集・整理・検索しやすくする個人開発プロジェクトです。

## 開発の背景

以前勤務していた環境計量証明事業所では、水質検査や大気（ばい煙）測定など、環境法令に基づく測定業務や法令対応に関わっていました。

法令を遵守した正しい計量証明書を発行するためには、環境省などが公表する報道発表や行政情報を継続的に確認し、業務への影響を把握する必要がありました。

一方で、分野横断の情報から自分の担当業務に関係するものを見つけ続けるには多くの手間がかかり、情報の見落としや確認の属人化、確認忘れといった課題がありました。

PressWatch は、こうした情報収集の負担や見逃しリスクを減らすために、**「当時あったらよかったもの」** を形にするプロジェクトです。

## 技術スタック

- フロントエンド: Next.js / React / TypeScript
- バックエンド: FastAPI / Python / SQLAlchemy / Alembic
- スクレイパー: Python / Beautiful Soup / lxml
- データベース: PostgreSQL 17 / psycopg
- 管理 PostgreSQL: Supabase
- 開発環境: Docker / docker compose
- CI: GitHub Actions
- パッケージ管理:
  - フロントエンド: pnpm
  - Python: uv

## リポジトリ構成

```text
press-watch/
├── apps/
│   ├── api/
│   └── web/
├── docs/
├── infra/
└── packages/
    └── scraper/
```

## MVPの範囲

MVPでは、報道発表の収集・保存、一覧・検索、共有の固定カテゴリによる絞り込み、定期取得と失敗確認を目指します。
ユーザー登録、ブックマーク、ユーザー定義カテゴリ、本格的な実行履歴管理はMVPに含めません。

## 利用できる機能

- 環境省の報道発表一覧と月別アーカイブから、タイトル、公開日、詳細ページURL、取得元カテゴリを取得し、CLIでJSONとして確認できます。
- 手動コマンドで初回全件取得・通常の差分取得を行い、詳細ページURLによる重複を除いてPostgreSQLへ保存できます。
- DB設定に依存しないヘルスチェックと、offset方式のページネーション・タイトル検索に対応した報道発表一覧取得APIを利用できます。

Data APIは利用せず、FastAPIからSQLAlchemy + psycopgでPostgreSQLへ直接接続します。

進捗・検証結果・今後の作業は[docs/tasks.md](docs/tasks.md)、製品要件とMVP範囲は[docs/requirements.md](docs/requirements.md)を参照してください。

## スクレイパー（`packages/scraper`）でできること

- テスト用HTML（fixture）または環境省サイトの実HTTP取得から報道発表一覧を解析する
- 月別アーカイブリンクを抽出し、指定した月数または全月を新しい順に巡回する
- 報道発表の詳細ページURLをキーに、巡回中の重複を除外する
- 巡回の停止理由を JSON に含める
- 成功時の JSON を stdout と `--output` の両方、または `--output` のみに出力する
- `--verbose` で要求番号、開始からの経過秒、取得中URL、待機の残り秒数、月別ページ番号を stderr に表示する
- ローカルの初回全件取得では、ページHTMLとJSON manifestを一時保存し、途中失敗後に取得済みページを再利用して手動再開する

実HTTP取得では、対象サイトへの連続アクセスを避けるため、1回のscraper CLI実行内で起点、月別ページ、同一オリジンのredirect先を含むHTTP要求の開始間隔を **3秒以上** にします。

`--output` は取得件数、カテゴリ、URL重複、停止理由を確認するための検証用スナップショットです。差分保存、履歴管理、本格的な永続化は行いません。

巡回stateはローカルの初回全件取得と手動再開だけに使用します。
本番の定期差分取得、実行履歴、再試行管理には使用せず、最終JSONの確認後に専用cleanup操作で削除します。

## スクレイピングの設計方針

- 対象ページの構造、利用条件、robots.txt を確認してから実装する
- 取得対象をタイトル、公開日、詳細ページURL、取得元カテゴリに絞り、DB保存前に検証できる形にする
- 詳細ページURLを重複判定キーとして扱い、DB 保存で `source_url` の一意制約へつなげる
- 月別巡回では停止理由を JSON に含め、取得上限に達した場合、月別リンクを最後まで巡回した場合、重複を検知した場合を区別できるようにする
- 実HTTP取得ではすべての要求開始間に待機を入れ、`--verbose` で対象URL、待機、経過時間、月別ページ進捗をターミナルで確認できるようにする

確認内容と取得時の配慮の詳細は `docs/scraping-env-go-jp.md` に記録しています。

## DB保存でできること

- Docker Compose の `db` サービスとして PostgreSQL 17 を起動する
- API コンテナから `DATABASE_URL` を使って PostgreSQL に接続する
- Alembic で `press_releases` テーブルを作成する
- `press_releases` にタイトル、詳細ページURL、公開日、取得元カテゴリ、取得日時、作成日時、更新日時を保存するための DB モデルと migration を持つ
- scraper の取得結果を API 側 DTO に変換し、repository / service 経由の保存処理へ渡せる
- service 層で既存 `source_url` を確認し、通常の重複データを skip する

DB migration と保存済みデータの確認手順は `docs/db-migrations.md` と `docs/local-development.md` に整理しています。

## 手動取得・保存でできること

- scraper CLI から API 側の保存 service までを接続し、取得した報道発表を手動コマンドで PostgreSQL へ保存する
- 保存済み報道発表がない DB では、`--all-archive-months` を使って初回全件取得を行う
- DB 内の最新公開月を含む直近3か月の既知 `source_url` を scraper へ渡し、既知URLだけの月に到達したら停止する通常の差分取得を行う
- stdout の実行結果 JSON で `fetched_count`、`saved_count`、`skipped_count`、`fetched_page_urls`、`stop_reason` を確認する
- stdout を機械可読な実行結果、stderr を進捗・エラーとして使う
- DB設定を読み込めない場合は、スクレイピングやDB処理を開始せず、stderr と終了コード `1` で CLI エラーを伝える

詳細な実行コマンド、差分取得の停止条件、異常終了時の挙動は `docs/local-development.md` に整理しています。

通常の差分取得では、保存済みレコードのタイトル、公開日、取得元カテゴリを更新しません。
保存済みレコードの内容変更を確認するメンテナンス用フルスキャンは、MVP後の改善候補として扱います。

## スクレイピングの最小確認

リポジトリ内のテスト用HTML `packages/scraper/tests/fixtures/env_press_index_sample.html` を使うことで、環境省サイトへアクセスせずに CLI の JSON 出力を確認できます。

```bash
cd packages/scraper
UV_CACHE_DIR=/private/tmp/press-watch-uv-cache \
PYTHONPATH=src \
uv run python -m press_watch_scraper \
  --from-file tests/fixtures/env_press_index_sample.html \
  --no-stdout-json \
  --output /private/tmp/env_press_sample.json
python -m json.tool /private/tmp/env_press_sample.json
cd ../..
```

出力された JSON では、取得件数、月別リンク候補、停止理由、報道発表の主要項目を確認できます。

```json
{
  "source_url": "tests/fixtures/env_press_index_sample.html",
  "count": 3,
  "archive_month_link_count": 2,
  "stop_reason": null,
  "items": [
    {
      "title": "令和８年度テスト事業の公募について",
      "published_at": "2026-05-01",
      "url": "https://www.env.go.jp/press/press_00001.html",
      "source_categories": ["総合政策"]
    }
  ]
}
```

実HTTPで直近の月別アーカイブを少数だけ確認する場合は、次のように実行します。

```bash
cd packages/scraper
PYTHONPATH=src \
uv run python -m press_watch_scraper \
  --archive-month-limit 2 \
  --verbose \
  --no-stdout-json \
  --output /tmp/env_press_sample.json
cd ../..
```

主な CLI オプションは次のとおりです。

- `--from-file PATH`: 保存済みHTMLを解析する
- `--archive-month-limit N`: 月別アーカイブを新しい順に N 件巡回する
- `--all-archive-months`: 抽出できた月別アーカイブをすべて巡回する
- `--crawl-state-dir PATH`: ローカル全件取得の一時HTMLとmanifestを保存する
- `--resume`: 既存の巡回stateから手動再開する
- `--refetch-invalid-pages`: 欠損やハッシュ不一致などで再利用できないページを明示的に再取得する
- `--cleanup-crawl-state PATH`: 検証済みの完了stateを削除する
- `--output PATH`: 成功時の JSON スナップショットをファイルにも保存する
- `--verbose`: 取得中URLや待機状況を stderr に出力する
- `--no-stdout-json`: JSON を stdout に出さず、`--output` のみに保存する

詳細なローカル起動手順は `docs/local-development.md`、環境省サイト構造やスクレイピング方針は `docs/scraping-env-go-jp.md` を参照してください。

## ドキュメント

- `docs/project-overview.md`: 背景、目的、想定ユーザー
- `docs/requirements.md`: MVP 要件
- `docs/tasks.md`: 進捗・検証結果・今後の作業
- `docs/tech-stack.md`: 技術選定とバージョン方針
- `docs/local-development.md`: ローカル開発・確認手順
- `docs/scraping-env-go-jp.md`: 環境省報道発表ページの構造とスクレイピング方針
- `docs/db-migrations.md`: DB マイグレーション方針
- `docs/fixed-categories.md`: 固定カテゴリの初期データと分類設計
