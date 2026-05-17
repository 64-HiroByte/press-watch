# PressWatch - Tech Stack

## 1. 目的

本ドキュメントは、PressWatch の初期技術前提を整理するためのものである。  
実装開始前に使用技術とバージョン方針を明確にし、開発時の判断ぶれを防ぐことを目的とする。

---

## 2. 技術選定

### フロントエンド

- Next.js
- React
- TypeScript

### バックエンド

- FastAPI
- Python

### データ取得

- Python によるスクレイピング処理

### データベース

- PostgreSQL
- SQLAlchemy
- Alembic
- psycopg

### 開発環境

- Docker
- docker compose

### リポジトリ構成

- モノレポ

### パッケージ管理

- フロントエンド: pnpm
- Python: uv

---

## 3. バージョン方針

### Node.js

- Node.js 24系 LTS を採用する

### Next.js

- Next.js 16系の最新を採用する
- セキュリティ修正を含む更新は適宜取り込む

### Python

- Python 3.14 を採用する

### PostgreSQL

- PostgreSQL 18 を採用する

---

## 4. Docker 方針

- Docker を用いてローカル開発環境を再現可能にする
- Docker ベースイメージは Alpine ではなく slim 系を採用する
- 初期段階では軽量化よりも安定性と再現性を優先する
- フロントエンド、バックエンド、データベースを docker compose で起動できる構成を目指す

---

## 5. Python 開発方針

- Python のパッケージ管理には uv を採用する
- FastAPI ベースで API を構築する
- スクレイピング処理は Python で実装する
- 実装時は Python 3.14 対応ライブラリを前提に選定する
- Pydantic は v2 系を前提とする

---

## 6. フロントエンド開発方針

- Next.js は App Router 構成とする
- TypeScript を使用する
- パッケージマネージャーは pnpm を使用する
- 一覧表示、検索、カテゴリ絞り込み、ブックマークを MVP の中心機能とする

---

## 7. データベース方針

- PostgreSQL 18 を使用する
- Python アプリケーションからのDB接続には SQLAlchemy + psycopg を第一候補とする
- マイグレーション管理には Alembic を第一候補とする
- Phase 3 初期では、報道発表の原本に近いデータを `press_releases` に保存することを優先する
- `press_releases.source_url` には、環境省の報道発表詳細ページURLを保存し、一意制約で重複登録を防ぐ
- `source_categories` は環境省ページから取得した分類情報として保持し、PressWatch 独自カテゴリとは分けて扱う
- ブックマークデータはMVP範囲に含めるが、ユーザー登録や単一ユーザー前提の扱いと関係するため、ブックマークAPI実装に近いフェーズで設計する
- 初期段階では、MVPに必要な最小限のテーブル構成とする
- 将来の拡張に備え、マイグレーション管理を導入する

---

## 8. 初期ディレクトリ構成方針

以下のようなモノレポ構成を想定する。

```txt
press-watch/
├── README.md
├── docs/
│   ├── project-overview.md
│   ├── requirements.md
│   ├── tasks.md
│   └── tech-stack.md
├── infra/
│   ├── docker/
│   └── compose.yml
├── apps/
│   ├── web/
│   └── api/
├── packages/
│   └── scraper/
└── .gitignore
```

- `docs`: プロジェクトドキュメント
- `infra`: Docker 関連設定やインフラ補助ファイル
- `apps/web`: Next.js アプリケーション
- `apps/api`: FastAPI アプリケーション
- `packages/scraper`: スクレイピング処理

---

## 9. 今後の見直し対象

以下は初期方針として採用するが、必要に応じて見直す可能性がある。

- 定期実行方式（Cron を含む）
- デプロイ先
- CI/CD 構成
- 本番向け Docker 最適化
- スクレイピング対象の拡張
- AI 要約機能の追加

---

## 10. 開発上の前提

- 実装は AI を活用して進める
- 要件定義、設計判断、レビュー、修正指示は開発者本人が担う
- 一度に大きく実装せず、小さな単位で差分確認しながら進める
- まずは PressWatch の MVP 完成を優先する
