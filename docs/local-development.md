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
- `apps/api/pyproject.toml`: API 用の Python 依存関係として `fastapi[standard]` / `sqlalchemy` / `psycopg` を定義します。
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

取得結果をローカルで確認したい場合は、CLI の stdout JSON を一時ファイルへリダイレクトします。現段階の最終保存先は PostgreSQL の予定なので、JSON ファイル保存は本格機能ではなく、DB 保存実装前の確認手段として扱います。

```bash
cd packages/scraper
PYTHONPATH=src uv run python -m press_watch_scraper --from-file tests/fixtures/env_press_index_sample.html > /tmp/env_press_sample.json
python -m json.tool /tmp/env_press_sample.json
cd ../..
```

全件取得は再取得コストが高いため、DB 保存が整うまでは検証用 JSON スナップショットを残せるようにします。`--output PATH` を指定すると、成功時の stdout JSON と同じ内容を指定ファイルにも保存します。

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

`--output` は開発・検証用の補助機能として扱い、差分保存や履歴管理は行いません。取得件数、重複URLの有無、カテゴリ、`stop_reason` などを後から確認するためのスナップショット用途に限定します。親ディレクトリは自動作成しないため、任意の保存先を使う場合は先に `mkdir -p /path/to/dir` でディレクトリを作成してください。存在しないディレクトリを指定した場合は、取得前にエラーとして終了します。取得やJSON生成、ファイル書き込みに失敗した場合、途中結果は保存しません。

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
接続文字列の環境変数名は `DATABASE_URL` のままとし、SQLAlchemy から psycopg を使う場合は次のような形式を想定します。

```text
postgresql+psycopg://presswatch:${POSTGRES_PASSWORD}@db:5432/presswatch
```

`.env` は秘密情報を含みうるため、接続に必要な環境変数は `.env.example` やこのドキュメントに記載された名前だけを参照します。

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

Alembic migration が適用済みであることを確認します。`version_num` が初版 migration の revision ID である `31765401e166` であれば、`press_releases` 作成 migration は適用済みです。

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
- `source_categories` が `text[]` で、NULL 許容であること
- `fetched_at` / `created_at` / `updated_at` が `timestamp with time zone` であること

保存件数を確認します。

```sql
select count(*) as total_count
from press_releases;
```

`total_count` が `0` の場合は、まだ保存済みデータがない状態です。
その場合、以降の集計 SQL はすべて `0` 件を返し、直近保存データの確認 SQL は行を返しません。
データ取得処理の実行単位や初回全件取得の手順は Phase 4 で整理します。

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
