# Local Development

PressWatch をローカル環境で起動・確認するための手順です。

特に明記がないコマンドは、リポジトリルートで実行します。

## 前提ツール

次のツールが使えることを確認します。

```bash
node -v
pnpm -v
uv --version
docker compose version
```

## 用意するファイル

ローカル起動前に `.env` を作成します。

```bash
cp .env.example .env
```

`.env` には、少なくとも PostgreSQL のパスワードを設定します。

```env
POSTGRES_PASSWORD=your-local-postgres-password
```

`.env` は秘密情報を含みうるため、コミットしません。

## セットアップされている主な構成ファイル

- `package.json`: ルートの pnpm scripts を定義します。
- `pnpm-workspace.yaml`: pnpm workspace の対象として `apps/web` を指定します。
- `apps/web/package.json`: Next.js / React / TypeScript の依存関係と scripts を定義します。
- `apps/api/pyproject.toml`: API 用の Python 依存関係として `fastapi[standard]` / `sqlalchemy` / `psycopg` / `alembic` を定義します。
- `packages/scraper/pyproject.toml`: scraper 用の Python パッケージ設定を定義します。
- `infra/compose.yml`: `web` / `api` / `db` の Docker Compose 構成を定義します。
- `infra/docker/web.Dockerfile`: Web コンテナのビルド手順を定義します。
- `infra/docker/api.Dockerfile`: API コンテナのビルド手順を定義します。
- `Makefile`: Docker Compose の起動・停止コマンドを短く呼べるようにします。

## lockfile について

`pnpm-lock.yaml` は Node.js 依存関係の lockfile です。`pnpm install` で生成・更新されます。

`uv.lock` は Python 依存関係の lockfile です。API と scraper はそれぞれ `apps/api/uv.lock`、`packages/scraper/uv.lock` を持ちます。各 `pyproject.toml` をもとに `uv sync` すると、解決されたパッケージの具体的なバージョンが記録され、その内容に沿って仮想環境が作られます。

Dockerfile では `uv sync --frozen` を使うため、lockfile を更新せず、記録済みの依存関係で再現性のある環境を作ります。

## フロントエンドを単体で起動する

画面だけを確認したい場合は、フロントエンドを単体で起動できます。

```bash
pnpm install
pnpm dev:web
```

ブラウザで次を開きます。

```text
http://127.0.0.1:3000/
```

Docker Compose で全体を起動する場合、この単体起動は必須ではありません。

## API を単体で起動する

API だけを確認したい場合は、API 側のディレクトリで依存関係を同期して起動します。

```bash
cd apps/api
uv sync
DATABASE_URL=postgresql+psycopg://presswatch:your-local-postgres-password@127.0.0.1:5432/presswatch uv run fastapi dev src/press_watch_api/main.py
```

`fastapi` コマンドをグローバルにインストールするのではなく、`uv run` で API 用の仮想環境内のコマンドとして実行します。
API 単体起動で PostgreSQL に接続する処理を確認する場合は、Docker Compose の公開ポートに合わせて host を `127.0.0.1` にした `DATABASE_URL` を指定します。

別ターミナルから API のルートエンドポイントを確認します。

```bash
curl http://127.0.0.1:8000/
```

確認後、リポジトリルートへ戻ります。

```bash
cd ../..
```

Docker Compose で全体を起動する場合、この単体起動は必須ではありません。単体起動したまま Docker Compose を起動すると、ポート `8000` が重複することがあります。

## scraper を単体で起動する

scraper の単体動作を確認します。保存済みHTMLを使うと、実HTTP取得をせずにJSON出力を確認できます。

```bash
cd packages/scraper
uv sync
PYTHONPATH=src uv run python -m press_watch_scraper --from-file tests/fixtures/env_press_index_sample.html
cd ../..
```

取得結果をローカルで確認したい場合は、CLI の stdout JSON を一時ファイルへリダイレクトします。JSON ファイル保存は本格機能ではなく、取得件数やカテゴリ、停止理由を確認するための開発・検証用スナップショットとして扱います。

```bash
cd packages/scraper
PYTHONPATH=src uv run python -m press_watch_scraper --from-file tests/fixtures/env_press_index_sample.html > /tmp/env_press_sample.json
python -m json.tool /tmp/env_press_sample.json
cd ../..
```

全件取得は再取得コストが高いため、DB 保存処理とつなぐ前の確認や再確認に使える JSON スナップショットを残せるようにします。`--output PATH` を指定すると、成功時の stdout JSON と同じ内容を指定ファイルにも保存します。

```bash
cd packages/scraper
PYTHONPATH=src uv run python -m press_watch_scraper --from-file tests/fixtures/env_press_index_sample.html --output /tmp/env_press_sample.json
python -m json.tool /tmp/env_press_sample.json
cd ../..
```

実HTTPで全月別アーカイブを巡回し、結果をスナップショットとして残す場合は次の形です。

```bash
cd packages/scraper
PYTHONPATH=src uv run python -m press_watch_scraper --all-archive-months --output /tmp/env_press_all.json
python -m json.tool /tmp/env_press_all.json
cd ../..
```

取得中のURLや待機をターミナルで確認したい場合は、`--verbose` を指定します。進捗は stderr に出力し、stdout のJSONとは分けて扱います。JSONをstdoutへ出さず、進捗だけを見ながらスナップショットを保存したい場合は、`--no-stdout-json` と `--output` を併用します。

```bash
cd packages/scraper
PYTHONPATH=src uv run python -m press_watch_scraper --archive-month-limit 2 --verbose --no-stdout-json --output /tmp/env_press_sample.json
python -m json.tool /tmp/env_press_sample.json
cd ../..
```

`--output` は開発・検証用の補助機能として扱い、差分保存や履歴管理は行いません。取得件数、重複URLの有無、カテゴリ、`stop_reason` などを後から確認するためのスナップショット用途に限定します。親ディレクトリは自動作成しないため、任意の保存先を使う場合は先に `mkdir -p /path/to/dir` でディレクトリを作成してください。存在しないディレクトリを指定した場合は、取得前にエラーとして終了します。取得やJSON生成、ファイル書き込みに失敗した場合、途中結果は保存しません。ファイル書き込み後にstdoutへの出力だけが失敗した場合は、完成したスナップショットを残したまま、stderrと終了コード `1` でstdoutの出力失敗を伝えます。

実HTTPで環境省の報道発表一覧を取得する場合は、`--from-file` を外します。月別ページを巡回する場合は、意図しない大量取得を避けるため `--archive-month-limit N` または `--all-archive-months` を明示します。

Docker Compose の通常起動には scraper はまだ含めていません。

## DB セットアップの考え方

PostgreSQL はローカル環境へ直接インストールせず、Docker Compose の `db` サービスとして起動します。

`infra/compose.yml` では PostgreSQL 18 のコンテナを使い、次の DB 設定で初期化します。

- DB 名: `presswatch`
- ユーザー名: `presswatch`
- パスワード: `.env` の `POSTGRES_PASSWORD`

初回起動時に Docker が PostgreSQL イメージを取得し、`postgres_data` ボリュームに DB データを保存します。通常のセットアップでは、`.env` を用意して Docker Compose を起動すれば DB も一緒に作られます。

Phase 3 では、API 側から PostgreSQL に接続するために SQLAlchemy + psycopg の最小土台を導入し、Alembic で `press_releases` の初版 migration を管理しています。
スクレイピング結果を DTO 経由で repository / service へ渡して保存する処理も API 側にあり、Phase 4 では既存 scraper CLI の JSON 結果を API 側の手動取得・保存コマンドから保存 service へ渡せるようにしています。
接続文字列の環境変数名は `DATABASE_URL` のままとし、SQLAlchemy から psycopg を使う場合は次のような形式を想定します。

```text
postgresql+psycopg://presswatch:${POSTGRES_PASSWORD}@db:5432/presswatch
```

`.env` は秘密情報を含みうるため、接続に必要な環境変数は `.env.example` やこのドキュメントに記載された名前だけを参照します。

## 手動で取得してDBへ保存する

手動取得・保存は API 側のコマンドとして実行します。scraper CLI は DB 保存前の取得確認と JSON スナップショット出力の入口として維持し、手動取得・保存コマンドはその JSON 結果を API 側の保存 service へ渡します。

事前に Docker Compose の `db` が起動しており、Alembic migration が適用済みであることを確認します。ローカルホストから DB に接続するため、`DATABASE_URL` の host は `127.0.0.1` を指定します。

保存済みHTMLを使って、実HTTP取得なしで取得・保存経路を確認する場合は次の形です。

```bash
cd apps/api
DATABASE_URL=postgresql+psycopg://presswatch:your-local-postgres-password@127.0.0.1:5432/presswatch \
PYTHONPATH=src \
uv run --locked python -m press_watch_api.commands.fetch_and_save_env_press \
  --from-file ../../packages/scraper/tests/fixtures/env_press_index_sample.html
cd ../..
```

成功時は stdout に実行結果の JSON を出力します。

```json
{
  "source_url": "/absolute/path/to/env_press_index_sample.html",
  "fetched_count": 3,
  "saved_count": 3,
  "skipped_count": 0,
  "fetched_page_urls": [],
  "stop_reason": null
}
```

同じデータを再実行した場合、既存の `source_url` は保存せず `skipped_count` に数えます。取得に失敗した場合は保存用DB Sessionを作成せず、保存処理の開始後に失敗した場合は rollback します。いずれも stderr に `error: target=... exception=... reason=...` の形式で出力し、終了コード `1` を返します。DBへのcommit後に結果JSONの出力だけが失敗した場合は rollback できないため、DB保存済みであることをstderrに明示します。

報道発表URLや月別アーカイブURLが安全なHTTP(S) URLとして扱えない場合は、その項目だけを黙って除外せず、実行全体を失敗させます。この場合は成功時のJSONを出力せず、DB保存も行いません。stderr の `reason` には `validation=non_ascii_character` などの固定理由コードと、報道発表では `title` / `href`、月別リンクでは `archive_month` / `href` を含めます。URLに認証情報が含まれていた場合、その部分は `[redacted]` に置き換えます。

主なURL検証理由は次のとおりです。

- `unsupported_scheme`: HTTPまたはHTTPS以外
- `credentials_not_allowed`: 認証情報を含むURL
- `non_ascii_character`: percent encodeされていない日本語などの非ASCII文字
- `unsafe_character`: 空白、制御文字、URLへ直接置けない記号
- `invalid_percent_escape`: `%ZZ` などの不正なpercent escape
- `invalid_host_or_port`: hostまたはportとして解釈できない形式
- `cross_origin`: 月別アーカイブが起点ページと異なるオリジン

実HTTPで直近の月別アーカイブを少数だけ取得して保存する場合は、意図しない大量取得を避けるため `--archive-month-limit N` を指定します。

```bash
cd apps/api
DATABASE_URL=postgresql+psycopg://presswatch:your-local-postgres-password@127.0.0.1:5432/presswatch \
PYTHONPATH=src \
uv run --locked python -m press_watch_api.commands.fetch_and_save_env_press \
  --archive-month-limit 2 \
  --verbose
cd ../..
```

保存済み報道発表がないDBへの初回全件取得として、環境省の一覧ページから見つかるすべての月別アーカイブを取得して保存する場合は `--all-archive-months` を指定します。実HTTPで多数のページを取得し、DBへ保存するため、事前にDB接続先と migration 適用状態を確認してから実行します。

```bash
cd apps/api
DATABASE_URL=postgresql+psycopg://presswatch:your-local-postgres-password@127.0.0.1:5432/presswatch \
PYTHONPATH=src \
uv run --locked python -m press_watch_api.commands.fetch_and_save_env_press \
  --all-archive-months \
  --verbose
cd ../..
```

`--all-archive-months` は月別アーカイブを巡回する実HTTP取得用の指定です。保存済みHTMLの単一ページ解析で使う `--from-file` や、取得する月別ページ数を制限する `--archive-month-limit` とは併用しません。保存済み報道発表がある場合は、後述する既知URLだけの月に到達すると全月を取得する前に停止します。

初回全件取得後も stdout の実行結果 JSON で、取得件数は `fetched_count`、新規保存件数は `saved_count`、重複などで保存しなかった件数は `skipped_count` として確認できます。巡回した月別ページは `fetched_page_urls`、正常停止理由は `stop_reason` に出力されます。再実行時は、同じ `source_url` の報道発表が新規保存されず `skipped_count` に数えられることを確認します。

差分取得を想定して、保存済みデータがあるDBに対して月別アーカイブを少数だけ取得して保存する場合も、同じ手動取得・保存コマンドを使います。API 側のコマンドは、月別アーカイブ巡回時に、DB内の最新公開月を含む直近3か月の既存 `source_url` を取得済みURLとして scraper 側へ渡します。基準はコマンド実行日ではなく、DBに保存された最新の `published_at` です。

```bash
cd apps/api
DATABASE_URL=postgresql+psycopg://presswatch:your-local-postgres-password@127.0.0.1:5432/presswatch \
PYTHONPATH=src \
uv run --locked python -m press_watch_api.commands.fetch_and_save_env_press \
  --archive-month-limit 6 \
  --verbose
cd ../..
```

既知URLとして取得する月数を変更する場合は、`--known-release-months` に1以上の整数を指定します。例えば、DB内の最新公開月を含む直近6か月を対象にする場合は次のように実行します。

```bash
cd apps/api
DATABASE_URL=postgresql+psycopg://presswatch:your-local-postgres-password@127.0.0.1:5432/presswatch \
PYTHONPATH=src \
uv run --locked python -m press_watch_api.commands.fetch_and_save_env_press \
  --archive-month-limit 12 \
  --known-release-months 6 \
  --verbose
cd ../..
```

月別ページ内の報道発表がすべて保存済み `source_url` と一致した場合、scraper 側はそれより古い月へ進まず停止します。この場合、stdout の実行結果 JSON では `stop_reason` が `duplicate_release_detected` になります。

```json
{
  "source_url": "https://www.env.go.jp/press/index.html",
  "fetched_count": 0,
  "saved_count": 0,
  "skipped_count": 0,
  "fetched_page_urls": [
    "https://www.env.go.jp/press/202605.html"
  ],
  "stop_reason": "duplicate_release_detected"
}
```

確認観点:

- `fetched_count`: scraper から API 側へ渡された新規候補の件数
- `saved_count`: DB に新規保存した件数
- `skipped_count`: API 側保存 service で既存 `source_url` と重複して保存しなかった件数
- `fetched_page_urls`: 実際に巡回した月別ページURL。既知URLだけの月で止まった場合、その月のURLも含まれます
- `stop_reason`: `duplicate_release_detected` の場合は、直近の既知URLだけで構成された月に到達して停止したことを示します

通常の差分取得では `source_url` の重複だけを確認し、保存済みレコードのタイトル、公開日、取得元カテゴリは更新しません。過去データの内容変更を確認するメンテナンス用フルスキャンは、このコマンドの通常取得とは別の後続タスクとして扱います。

`duplicate_release_detected` で停止した月の報道発表は scraper から保存 service へ渡されないため、その停止自体は `skipped_count` には加算されません。`skipped_count` は、scraper が返した報道発表を保存しようとした際の重複 skip 件数として確認します。

### 実行結果・進捗・永続ログの扱い

Phase 4 では、取得・保存コマンドの出力を次の3種類に分けて扱います。

- 実行結果: stdout 出力を有効にしている場合は、成功時だけ機械可読なJSONを出力します。scraper CLI の stdout JSON は取得結果のスナップショットであると同時に、API 側の取得・保存コマンドへ結果を渡すプロセス間インターフェースでもあるため、進捗やエラーメッセージを混ぜません。
- 進捗・エラー: 進捗は `--verbose` 指定時だけ、エラーは失敗時に stderr へ出力します。診断対象として実行対象のURL、ファイルパス、または `stdout` を示します。URL、ファイルパス、例外理由は、改行などの連続空白を1つにまとめ、端末制御文字を表示可能な文字列へ変換し、URL内の認証情報を `[redacted]` に置き換え、診断値を最大1000文字に制限します。
- 永続的な実行ログ: Phase 4 では実装しません。実行ログテーブル、実行ごとの自動ログファイル、本格的な logging 設定は、定期実行、監視、検索、保持期間の要件が決まった後続タスクで設計します。

scraper CLI の `--output` は、成功時の取得結果を後から確認するための検証用JSONスナップショットです。追記、実行履歴、失敗記録を行わないため、永続的な実行ログとしては扱いません。

API 側の取得・保存コマンドは、処理の終了状態を次のように区別します。

- DBへのcommitとstdoutへの結果JSON出力が両方成功した場合は、終了コード `0` を返します。
- 取得、保存、またはcommitに失敗した場合は、成功時のJSONをstdoutへ出さず、stderrと終了コード `1` で失敗を伝えます。保存用Sessionを作成済みで、commitが完了していない場合は rollback します。
- DBへのcommit後にstdoutへの結果JSON出力だけが失敗した場合は、DBへ保存済みであることを `database commit succeeded but result output failed` としてstderrへ出し、終了コード `1` を返します。この場合は rollback できず、再実行すると保存済みデータが重複としてskipされる可能性があります。
- 引数の組み合わせや値が不正な場合は、取得処理やDB処理を開始せず、argparseがstderrへ理由を出して終了コード `2` で終了します。

実行ID、開始・終了時刻、所要時間、成功・失敗状態、失敗段階、履歴検索、保持期間は、永続的な実行ログを設計する後続タスクで必要性を判断します。

定期実行、Docker Compose 全体での取得・保存方法、実HTTPでの差分件数保証は後続タスクで整理します。

## DB migration の考え方

DB スキーマ変更は Alembic で管理し、API アプリケーション側の責務として `apps/api` 配下に設定と migration ファイルを置きます。
アプリケーション起動時の `metadata.create_all()` には頼りません。

詳細な配置、`target_metadata`、初版 migration、`updated_at` トリガー要否は `docs/db-migrations.md` に整理しています。
Docker Compose の API コンテナから次の形で適用できます。

```bash
docker compose --env-file .env -f infra/compose.yml exec api uv run alembic upgrade head
```

## 保存済みデータを確認する

`press_releases` に保存された報道発表データは、Docker Compose の `db` サービスへ `psql` で接続して確認します。
事前に Docker Compose で `db` が起動しており、Alembic migration が適用済みであることを確認します。
この手順は保存済みデータの確認専用であり、データの追加・更新・削除は行いません。

```bash
docker compose --env-file .env -f infra/compose.yml exec db psql -U presswatch -d presswatch
```

Alembic migration が適用済みであることを確認します。現在のheadは、`published_at` のインデックスを追加する `9f2c7a4e1d63` です。`version_num` が初版 migration の `31765401e166` の場合は、`press_releases` テーブルは作成済みですが、公開日インデックスのmigrationは未適用です。

```sql
select version_num
from alembic_version;
```

psql のメタコマンドで、テーブル定義、NULL 許容、制約を確認します。

```sql
\d+ press_releases
```

確認観点:

- `source_url` に `uq_press_releases_source_url` の一意制約があること
- `published_at` に `ix_press_releases_published_at` のインデックスがあること
- `source_categories` が `text[]` で、NULL 許容であること
- `fetched_at` / `created_at` / `updated_at` が `timestamp with time zone` であること

保存件数を確認します。

```sql
select count(*) as total_count
from press_releases;
```

`total_count` が `0` の場合は、まだ保存済みデータがない状態です。
その場合、以降の集計 SQL はすべて `0` 件を返し、直近保存データの確認 SQL は行を返しません。
手動取得・保存、初回全件取得、差分取得の基本手順は上記のコマンド例で確認できます。定期実行と Docker Compose 全体での取得・保存方法は後続タスクで整理します。

`source_url` の重複がないことを確認します。`duplicated_source_url_count` が `0` であれば、保存済みデータ上の URL 重複はありません。

```sql
select count(*) as duplicated_source_url_count
from (
    select source_url
    from press_releases
    group by source_url
    having count(*) > 1
) duplicated;
```

`source_categories` の保存状況を確認します。過去ページではカテゴリが欠損する場合があるため、NULL 件数があること自体は異常ではありません。

```sql
select
    count(*) filter (where source_categories is null) as null_source_categories_count,
    count(*) filter (where source_categories is not null) as non_null_source_categories_count,
    count(*) filter (where source_categories = array[]::text[]) as empty_source_categories_count
from press_releases;
```

確認観点:

- `null_source_categories_count`: カテゴリ欠損として NULL 保存された件数
- `non_null_source_categories_count`: 取得元カテゴリが保存された件数
- `empty_source_categories_count`: 通常は `0` を期待する件数

保存時刻の入っていない行がないことと、保存・取得時刻の範囲を確認します。

```sql
select
    count(*) filter (where fetched_at is null) as null_fetched_at_count,
    count(*) filter (where created_at is null) as null_created_at_count,
    count(*) filter (where updated_at is null) as null_updated_at_count,
    min(fetched_at) as oldest_fetched_at,
    max(fetched_at) as newest_fetched_at,
    min(created_at) as oldest_created_at,
    max(created_at) as newest_created_at,
    min(updated_at) as oldest_updated_at,
    max(updated_at) as newest_updated_at
from press_releases;
```

確認観点:

- `null_fetched_at_count` / `null_created_at_count` / `null_updated_at_count` がすべて `0` であること
- `fetched_at` は環境省ページから取得した日時として入っていること
- `created_at` / `updated_at` は PressWatch 側で保存した日時として入っていること
- Phase 3 初期では既存行の自動更新を扱わないため、通常の初回保存行では `created_at` と `updated_at` が近い値になること

直近で保存されたデータのタイトル、公開日、URL、カテゴリ、時刻を確認します。

```sql
select
    id,
    title,
    published_at,
    source_url,
    source_categories,
    fetched_at,
    created_at,
    updated_at
from press_releases
order by created_at desc, id desc
limit 10;
```

確認観点:

- `title` が空ではなく、環境省の報道発表タイトルとして読めること
- `published_at` が報道発表の公開日として妥当であること
- `source_url` が環境省の詳細ページ URL であること
- `source_categories` は取得できた場合に配列、取得できなかった場合に NULL であること
- `fetched_at` / `created_at` / `updated_at` の時刻が保存タイミングと大きく矛盾しないこと

確認を終えたら `psql` を終了します。

```sql
\q
```

## Docker Compose で全体を起動する

Web、API、DB をまとめて起動します。

```bash
make compose-up-build
```

ビルド済みで、再ビルドせずに起動するだけなら次を使います。

```bash
make compose-up
```

## 起動状態と疎通を確認する

サービスの状態を確認します。

```bash
docker compose --env-file .env -f infra/compose.yml ps
```

Web が表示されるか確認します。

```text
http://127.0.0.1:3000/
```

API が応答するか確認します。

```bash
curl http://127.0.0.1:8000/
```

PostgreSQL コンテナに接続できるか、バージョン確認で疎通を見ます。

```bash
docker compose --env-file .env -f infra/compose.yml exec db psql -U presswatch -d presswatch -c "select version();"
```

API コンテナから SQLAlchemy 経由で PostgreSQL に接続できるか確認します。

```bash
docker compose --env-file .env -f infra/compose.yml exec api uv run python -c "from sqlalchemy import text; from press_watch_api.db import engine; conn = engine.connect(); print(conn.execute(text('select 1')).scalar_one()); conn.close()"
```

API コンテナのログを確認したい場合は次を使います。

```bash
docker compose --env-file .env -f infra/compose.yml logs api --tail=50
```

## 停止する

通常の停止は Makefile 経由で行います。

```bash
make compose-down
```

Makefile を使わずに直接実行する場合は次の形です。

```bash
docker compose --env-file .env -f infra/compose.yml down
```

## 注意して使うコマンド

PostgreSQL の永続化データを削除し、DB を初期状態から作り直したいときだけ使います。

データが入った後に実行すると DB の中身が消えるため、通常の開発作業では使いません。

```bash
docker volume rm press-watch_postgres_data
```
