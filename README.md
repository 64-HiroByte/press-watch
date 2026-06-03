# PressWatch

PressWatch は、環境省の報道発表を収集・整理・検索しやすくする個人開発プロジェクトです。

## 開発の背景

以前勤務していた環境計量証明事業所では、水質検査や大気（ばい煙）測定など、環境法令に基づく測定業務や法令対応に関わっていました。

法令を遵守した正しい計量証明書を発行するためには、環境省などが公表する報道発表や行政情報を継続的に確認し、業務への影響を把握する必要がありました。

一方で、分野横断の情報から自分の担当業務に関係するものを見つけ続けるには多くの手間がかかり、情報の見落としや確認の属人化、確認忘れといった課題がありました。

PressWatch は、こうした情報収集の負担や見逃しリスクを減らすために、**「当時あったらよかったもの」** を形にするプロジェクトです。

## 技術スタック

- フロントエンド: Next.js / React / TypeScript
- バックエンド: FastAPI / Python
- スクレイパー: Python / Beautiful Soup
- データベース: PostgreSQL
- 開発環境: Docker / docker compose
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

## 現在の開発状況

現在は **Phase 3: DB設計と保存処理** として、PostgreSQL へ保存するための API 側の土台を実装した段階です。

Phase 2では、DB保存前に取得結果を検証できるスクレイピング基盤を実装しました。

- 環境省の報道発表一覧と月別アーカイブから、タイトル、公開日、詳細ページURL、取得元カテゴリを取得し、CLI で JSON として確認できます。
- 月別巡回、停止理由、詳細ページURLによる重複除外、DB保存前の検証用 JSON スナップショット出力、実HTTP取得時のページ取得間隔、CLI の進捗表示まで実装済みです。

Phase 3では、次の DB 保存土台を追加しました。

- SQLAlchemy + psycopg で PostgreSQL に接続します。
- Alembic で `press_releases` の初版 migration を管理します。
- `source_url` の一意制約で重複登録を防ぐ前提にし、service 層では既存 `source_url` を skip して保存件数 / skip 件数を返します。
- `source_categories` は環境省ページから取得した分類情報として保持し、欠損時は NULL を許容します。

scraper CLI から DB 保存までを接続する実行単位、初回全件取得、差分取得、ログ方針は Phase 4 で整理します。
一覧取得・検索・カテゴリ絞り込み・ブックマーク API、フロントエンド画面、定期実行は今後のフェーズで実装します。

## スクレイパー（`packages/scraper`）でできること

- テスト用HTML（fixture）または環境省サイトの実HTTP取得から報道発表一覧を解析する
- 月別アーカイブリンクを抽出し、指定した月数または全月を新しい順に巡回する
- 報道発表の詳細ページURLをキーに、巡回中の重複を除外する
- 巡回の停止理由を JSON に含める
- 成功時の JSON を stdout と `--output` の両方、または `--output` のみに出力する
- `--verbose` で取得中URLや待機状況を stderr に表示する

実HTTPで月別ページを巡回する場合、対象サイトへの連続アクセスを避けるため、ページ取得の間に **3秒** 待機します。

`--output` は取得件数、カテゴリ、URL重複、停止理由を確認するための検証用スナップショットです。差分保存、履歴管理、本格的な永続化は行いません。

## Phase 2 実装で考慮した点

- 対象ページの構造、利用条件、robots.txt を確認してから実装する
- 取得対象をタイトル、公開日、詳細ページURL、取得元カテゴリに絞り、DB保存前に検証できる形にする
- 詳細ページURLを重複判定キーとして扱い、Phase 3 の DB 保存で `source_url` の一意制約へつなげる
- 月別巡回では停止理由を JSON に含め、取得上限に達した場合、月別リンクを最後まで巡回した場合、重複を検知した場合を区別できるようにする
- 実HTTP取得ではページ間に待機を入れ、`--verbose` で取得中URLと待機状況をターミナルで確認できるようにする

確認内容と取得時の配慮の詳細は `docs/scraping-env-go-jp.md` に記録しています。

## Phase 3 DB 保存土台でできること

- Docker Compose の `db` サービスとして PostgreSQL 18 を起動する
- API コンテナから `DATABASE_URL` を使って PostgreSQL に接続する
- Alembic で `press_releases` テーブルを作成する
- `press_releases` にタイトル、詳細ページURL、公開日、取得元カテゴリ、取得日時、作成日時、更新日時を保存するための DB モデルと migration を持つ
- scraper の取得結果を API 側 DTO に変換し、repository / service 経由の保存処理へ渡せる
- service 層で既存 `source_url` を確認し、通常の重複データを skip する

DB migration と保存済みデータの確認手順は `docs/db-migrations.md` と `docs/local-development.md` に整理しています。

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
- `--output PATH`: 成功時の JSON スナップショットをファイルにも保存する
- `--verbose`: 取得中URLや待機状況を stderr に出力する
- `--no-stdout-json`: JSON を stdout に出さず、`--output` のみに保存する

詳細なローカル起動手順は `docs/local-development.md`、環境省サイト構造やスクレイピング方針は `docs/scraping-env-go-jp.md` を参照してください。

## ドキュメント

- `docs/project-overview.md`: 背景、目的、想定ユーザー
- `docs/requirements.md`: MVP 要件
- `docs/tasks.md`: フェーズ別タスク
- `docs/tech-stack.md`: 技術選定とバージョン方針
- `docs/local-development.md`: ローカル開発・確認手順
- `docs/scraping-env-go-jp.md`: 環境省報道発表ページの構造とスクレイピング方針
- `docs/db-migrations.md`: DB マイグレーション方針

## 今後の予定

次は Phase 4 以降として、保存処理を実際の取得フローにつなぐための実行単位を整理します。

1. Phase 4: データ取得処理の実行単位、手動実行、初回全件取得、差分取得、ログ方針の整理
2. Phase 5: 一覧取得、検索、カテゴリ絞り込み、ブックマーク操作 API の実装
3. Phase 6: 一覧、検索、カテゴリ絞り込み、ブックマーク画面の実装
4. Phase 7: 定期実行と運用準備

この README は、実装 Phase の進捗に合わせて更新します。
