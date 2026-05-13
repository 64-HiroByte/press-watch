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
- `apps/api/pyproject.toml`: API 用の Python 依存関係として `fastapi[standard]` を定義します。
- `packages/scraper/pyproject.toml`: scraper 用の Python パッケージ設定を定義します。
- `infra/compose.yml`: `web` / `api` / `db` の Docker Compose 構成を定義します。
- `infra/docker/web.Dockerfile`: Web コンテナのビルド手順を定義します。
- `infra/docker/api.Dockerfile`: API コンテナのビルド手順を定義します。
- `Makefile`: Docker Compose の起動・停止コマンドを短く呼べるようにします。

## lockfile について

`pnpm-lock.yaml` は Node.js 依存関係の lockfile です。`pnpm install` で生成・更新されます。

`uv.lock` は Python 依存関係の lockfile です。`pyproject.toml` をもとに `uv sync` すると、解決されたパッケージの具体的なバージョンが記録され、その内容に沿って仮想環境が作られます。

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
uv run fastapi dev src/press_watch_api/main.py
```

`fastapi` コマンドをグローバルにインストールするのではなく、`uv run` で API 用の仮想環境内のコマンドとして実行します。

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

PostgreSQL に接続できるか、バージョン確認で疎通を見ます。

```bash
docker compose --env-file .env -f infra/compose.yml exec db psql -U presswatch -d presswatch -c "select version();"
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
