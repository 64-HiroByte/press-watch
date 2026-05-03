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

scraper の最小起動を確認します。現時点では実際の取得処理はなく、起動ログを確認するためのコマンドです。

```bash
cd packages/scraper
uv sync
uv run python src/press_watch_scraper
cd ../..
```

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
