# PressWatch

PressWatch は、環境省の報道発表を収集・整理し、環境計量分野に合わせた独自のカテゴリやキーワードで検索できる個人開発のWebアプリケーションです。

## 開発の背景

以前勤務していた環境計量証明事業所では、水質検査や大気（ばい煙）測定など、環境法令に基づく測定業務や法令対応に関わっていました。

法令を遵守した正しい計量証明書を発行するためには、環境省などが公表する報道発表や行政情報を継続的に確認し、業務への影響を把握する必要がありました。

一方で、分野横断の情報から自分の担当業務に関係するものを見つけ続けるには多くの手間がかかり、情報の見落としや確認の属人化、確認忘れといった課題がありました。

PressWatch は、こうした情報収集の負担や見逃しリスクを減らすために、**「当時あったらよかったもの」** を形にするプロジェクトです。

## 現在の機能と開発状況

### 実装済みの機能

- Webの一覧で、報道発表のタイトル・公開日・所属する固定カテゴリを確認し、元記事を別画面で開けます。
- タイトルのキーワードと公開日範囲で検索し、固定カテゴリの複数選択と組み合わせて絞り込めます。
- 50件ずつのページ送り、検索条件の解除、URLによる条件の共有・復元、ブラウザーの戻る／進むに対応しています。
- 取得中・取得失敗・データなし・検索結果なしを表示し、失敗時には再取得できます。
  文字サイズ・テーマの切り替えと、狭い画面の検索ドロワーも利用できます。
- 手動コマンドで環境省の一覧・月別アーカイブから報道発表を取得し、PostgreSQLへ保存できます。
  初回全件取得、通常の差分取得、詳細ページURLによる重複防止に対応しています。
- 共有の固定カテゴリのseed、新規保存時の自動分類、既存記事の再分類を行うCLIを用意しています。
- ヘルスチェック、検索・絞り込み・ページ送りに対応した一覧取得、固定カテゴリの選択肢取得の読み取りAPIを提供します。
  `GET /health`はDB設定に依存せず、`GET /press-releases`はoffset方式のページネーションに対応しています。

### 取得・保存のしくみと制約

タイトル・公開日・詳細ページURL・取得元カテゴリを収集し、取得時刻などとともにDBへ保存します。
詳細ページURLを重複判定キーとし、通常の差分取得では保存済みレコードのタイトル・公開日・取得元カテゴリを更新しません。
通常の差分取得は、DB内の最新公開月を含む直近3か月の既知URLを使い、既知URLだけの月へ到達すると停止します。
固定カテゴリの初期データは保存前にseedで取り込み、既存記事の分類変更は専用の再分類CLIで行います。

scraper単体のCLIは、DB保存前の解析結果をJSONで確認するための入口です。
`--output`は検証用スナップショット、`--verbose`は進捗表示に使い、成功結果をstdout、進捗・エラーをstderrへ出力します。
初回全件取得では`--crawl-state-dir`で取得済みHTMLとmanifestを一時保存でき、途中失敗後に手動再開できます。
この巡回stateはローカルの初回取得用で、定期実行の履歴・再試行管理には使いません。
最終JSONの確認後に専用のcleanup操作で削除します。

実HTTP取得前には現在のrobots.txtと利用条件を確認します。
1回のscraper CLI実行内では、起点・月別ページ・同一オリジンのredirect先を含むHTTP要求の開始間隔を3秒以上にします。
取得・停止・再開の仕様は[スクレイピング仕様](docs/scraping-env-go-jp.md)、保存・seed・再分類の操作と失敗時の扱いは[開発手順](docs/local-development.md#手動で取得してdbへ保存する)を参照してください。

### 公開・運用に向けた残作業

アプリは未公開・未デプロイです。
定期取得、定期実行の失敗確認、公開APIのリクエスト数制限は未実装で、デプロイ先と合わせて今後整えます。
開発DB・Supabaseへの固定カテゴリmigration・seed適用と実データの再分類は未確認です。
テスト専用DB・合成データでの検証と、公開運用の準備は区別しています。

MVPは定期取得と失敗確認までを含みます。
ユーザー登録・認証、ブックマーク、ユーザー定義カテゴリ、本格的な実行履歴管理はMVP後に扱います。
進捗と残作業は[タスク一覧](docs/tasks.md)、詳しい製品要件とMVP範囲は[要件定義](docs/requirements.md)を参照してください。

## 全体構成

手動の取得・保存コマンドがスクレイパーで環境省の報道発表を取得し、FastAPI側の保存処理を通してPostgreSQLへ保存します。
FastAPIは保存済みデータの検索・絞り込みと一覧・カテゴリ選択肢の取得を担当します。
Next.jsサーバーがFastAPIへ問い合わせ、ブラウザーには一覧と検索・カテゴリ・ページ送りの操作を表示します。

DBにはSQLAlchemyとpsycopgで直接接続し、SupabaseのData APIは使用しません。
WebのAPI接続先はサーバー専用の`PRESSWATCH_API_BASE_URL`で指定し、DB資格情報をWebへ渡しません。
取得・描画と画面操作の責務は[Server／Client境界](docs/tech-stack.md#一覧の取得とserverclient境界)にまとめています。

## 技術スタック

| 区分 | 採用技術 |
| --- | --- |
| Web | Next.js / React / TypeScript / Tailwind CSS / shadcn/ui |
| API・DB操作 | FastAPI / Python / SQLAlchemy / Alembic / psycopg |
| スクレイパー | Python / Beautiful Soup / lxml |
| データベース | PostgreSQL 17（管理PostgreSQLにSupabaseを採用） |
| 開発・依存管理 | Docker / Docker Compose / pnpm / uv |
| 検証 | GitHub Actions / unittest / Playwright / Oxlint / Oxfmt |

採用版と選定方針は[技術構成](docs/tech-stack.md)、UI部品の出典・ライセンスは[一覧UI](docs/frontend-ui.md#利用条件と表示)を参照してください。

## リポジトリ構成

```text
press-watch/
├── apps/
│   ├── api/          # FastAPI・DB操作・取得保存コマンド
│   └── web/          # Next.jsの一覧画面
├── docs/             # 要件・設計・開発手順
├── infra/            # Docker構成・検証用fixture
└── packages/
    └── scraper/      # 環境省報道発表の取得・解析
```

## ローカルで動かすには

1. [前提ツール](docs/local-development.md#前提ツール)と[Node.js・pnpmの準備](docs/local-development.md#web用のnodejsとpnpm)を確認します。
2. API・DBを含めて起動する場合は、[設定ファイルの準備](docs/local-development.md#用意するファイル)と[Docker Composeの起動手順](docs/local-development.md#docker-compose-で全体を起動する)に従います。
   一覧の利用には、接続先DBへのmigrationとカテゴリ初期データの準備が必要です。
   [DB migration](docs/db-migrations.md#実行方針)と[固定カテゴリのseed手順](docs/local-development.md#固定カテゴリの初期データを取り込む)で、対象DB・適用状況・操作の影響を確認してください。
3. Webをホスト上で単体起動する場合は、[起動手順](docs/local-development.md#フロントエンドを単体で起動する)と[製品一覧のAPI接続設定](docs/local-development.md#製品一覧の接続先と実api画面テスト)を確認します。
   保存済みの専用検証DBを使う場合も、同手順の再利用条件を確認してください。

実HTTP取得、DBへの保存・migration・seed・再分類は、それぞれの手順と対象を確認してから実行してください。

### 実サイト・DBを使わずに取得・解析を確認する

リポジトリルートから次を実行すると、テスト用HTMLを解析してJSONを表示します。
このコマンドは環境省サイトへのアクセスやDB保存を行いません。

```bash
cd packages/scraper
uv sync
PYTHONPATH=src uv run python -m press_watch_scraper --from-file tests/fixtures/env_press_index_sample.html
cd ../..
```

JSONでは取得件数、月別リンク候補、停止理由、各記事のタイトル・公開日・URL・取得元カテゴリを確認できます。
ファイル出力・実HTTP取得・手動再開・完了stateの削除など、詳しいCLI操作は[開発手順](docs/local-development.md#scraper-を単体で起動する)を参照してください。

## 詳しいドキュメント

| 文書 | 内容 |
| --- | --- |
| [プロジェクト概要](docs/project-overview.md) | 背景・目的・想定ユーザー |
| [要件定義](docs/requirements.md) | 製品要件とMVP範囲 |
| [タスク一覧](docs/tasks.md) | 進捗・完了状態・残作業 |
| [技術構成](docs/tech-stack.md) | 技術選定・採用版・責務分担 |
| [一覧UI](docs/frontend-ui.md) | 操作・URL・表示状態とUI部品の出典 |
| [ローカル開発手順](docs/local-development.md) | 起動・コマンド・検証方法と確認実績 |
| [スクレイピング仕様](docs/scraping-env-go-jp.md) | 取得対象・巡回・待機・停止条件 |
| [DB migration](docs/db-migrations.md) | スキーマ変更と環境別の適用状況 |
| [固定カテゴリ](docs/fixed-categories.md) | 初期データ・分類・絞り込みの仕様 |
