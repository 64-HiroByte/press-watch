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
- Python アプリケーションからのDB接続には SQLAlchemy + psycopg を採用する
- ORM には SQLAlchemy を採用する
- マイグレーション管理には Alembic を採用する
- PostgreSQL ドライバには psycopg を採用する
- Phase 3 初期では、報道発表の原本に近いデータを `press_releases` に保存することを優先する
- `press_releases.source_url` には、環境省の報道発表詳細ページURLを保存し、一意制約で重複登録を防ぐ
- `source_categories` は環境省ページから取得した分類情報として保持し、PressWatch 独自カテゴリとは分けて扱う
- ブックマークデータはMVP範囲に含めるが、ユーザー登録や単一ユーザー前提の扱いと関係するため、ブックマークAPI実装に近いフェーズで設計する
- 初期段階では、MVPに必要な最小限のテーブル構成とする
- マイグレーションは Alembic で管理し、アプリケーション起動時の `metadata.create_all()` には頼らない
- DB接続情報は環境変数から読み込む
- `.env` や秘密情報を含みうるファイルは原則読まない。確認が必要な場合も、理由を添えてユーザーの許可を得てから読む

### DB周りの採用理由

- SQLAlchemy は FastAPI と組み合わせた利用例が多く、ORM と Core の両方を使い分けやすいため、MVP 以降の検索・ページネーション・保存処理を段階的に育てやすい
- Alembic は SQLAlchemy のメタデータと連携しやすく、テーブル定義の変更履歴をレビュー可能なマイグレーションとして残せる
- psycopg は PostgreSQL 向けの標準的な Python ドライバであり、SQLAlchemy から利用しやすい

### DB責務分割方針

- API route や scraper から SQLAlchemy model を直接操作しない
- DB操作は repository 層に閉じ込める
- API schema / 入出力DTOは Pydantic で定義し、DB model と分ける
- scraper の `PressRelease` は取得結果を表す型として扱い、DB model と直接同一視しない
- スクレイピング結果を保存する処理では、変換関数または service 層を挟む
- `source_url` の一意制約をDB側に置き、既存URLの確認は repository、skip と保存件数 / skip 件数の集計は service で扱う

### Phase 3 初期の実装方針

- SQLAlchemy は同期版から始める
- Phase 3 初期では保存処理、重複防止、マイグレーションの見通しを優先し、async SQLAlchemy は高並行アクセスや非同期I/Oの必要性が明確になった段階で再検討する
- DB接続設定は `apps/api/src/press_watch_api/config.py` で `DATABASE_URL` を環境変数から読み込む
- SQLAlchemy の engine / sessionmaker は `apps/api/src/press_watch_api/db.py` に置く
- Docker Compose 内の接続URLは `postgresql+psycopg://presswatch:${POSTGRES_PASSWORD}@db:5432/presswatch` を基本形とする
- ローカルPCから直接接続する場合は、Compose の公開ポートに合わせて host を `127.0.0.1` に置き換える
- 通常の保存処理では、`source_url` が既存なら重複登録せずスキップする
- MVP段階では管理者またはシステム実行のスクレイピング処理を前提に、`IntegrityError` の詳細ハンドリングと同時実行時の race condition 対策は後続タスクで扱う
- 既存データの修正検知は、初期保存処理とは分けて Phase 4 の差分取得・実行単位整理で扱う
- 週次フルスキャンや再照合モード、`last_seen_at`、`content_hash`、変更履歴の保存は、必要性を確認してから後続フェーズで検討する
- 初期実装では、既存データを自動上書きするよりも重複登録を避けることを優先する
- `source_categories` は初期実装では PostgreSQL の `text[]` として保存する
- 過去ページではカテゴリ表示がない報道発表が存在するため、`source_categories` は NULL を許容する
- scraper の `source_categories` が空の場合は、保存用 DTO への変換時に `None` へ正規化し、DB には NULL として保存する
- `source_categories` にカテゴリ名以外の属性を持たせる必要が出た場合は、別テーブル化または `jsonb` 化を後続フェーズで検討する
- `fetched_at` / `created_at` / `updated_at` などの時刻は UTC 基準で保存する
- `fetched_at` は環境省ページからデータを取得した日時として扱い、DB行の作成・更新日時とは分ける
- 初回保存時は `created_at` と `updated_at` に同じ時刻が入る想定とする
- `updated_at` はユーザー操作による編集日時ではなく、環境省サイト上の修正などを検知して保存済み行を更新した日時として扱う
- SQLAlchemy model では `DateTime(timezone=True)` を使い、UTC への統一は保存処理で timezone aware な UTC datetime を渡すことで担保する
- 時刻をユーザーに表示する必要が出た場合は、表示層で日本時間などのローカルタイムへ変換する
- MVP の主な表示対象は公開日 `published_at` であり、取得時刻は主に定時実行、差分取得、保存状況確認、調査用のメタデータとして扱う

### マイグレーション方針

- Alembic の設定と migration ファイルは `apps/api` 配下に置く
- `target_metadata` は `press_watch_api.models.base.Base.metadata` を使う
- Autogenerate で SQLAlchemy model を認識できるように、Alembic の `env.py` では model モジュールを import する
- 初版 migration は `press_releases` テーブルと `source_url` の名前付き一意制約に限定する
- 初版 migration では `source_categories` を NULL 許容にする
- 初版 migration では `updated_at` 自動更新用の PostgreSQL トリガーは作らない
- DB 直接更新でも `updated_at` を必ず更新する要件が出た場合は、後続 migration でトリガー追加を検討する

詳細は `docs/db-migrations.md` に整理する。

### API 側の配置方針

```text
apps/api/src/press_watch_api/
├── config.py
├── db.py
├── models/
│   └── press_release.py
├── schemas/
│   └── press_release.py
├── repositories/
│   └── press_release.py
└── services/
    └── press_release_import.py
```

- `models/`: SQLAlchemy model を置く
- `schemas/`: Pydantic schema / DTO を置く
- `repositories/`: DB操作を置く
- `services/`: scraper 取得結果から保存用 schema への変換や repository 呼び出しを置く

### SQLModel の扱い

- SQLModel は今回は採用しない
- 現時点では、SQLAlchemy model と Pydantic schema / DTO を明示的に分け、永続化責務と入出力責務の境界を分かりやすく保つことを優先する
- 将来、SQLModel によって型定義の重複を減らす価値が大きくなった場合は再検討する
- 将来のリプレースに備え、API route、scraper、DB model を直接結合せず、repository 層、service 層、変換関数を境界として扱う

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
