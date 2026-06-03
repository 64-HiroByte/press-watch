# DB マイグレーション方針

PressWatch の DB スキーマ変更は Alembic で管理する。
アプリケーション起動時の `metadata.create_all()` には頼らず、レビュー可能な migration として変更履歴を残す。

## 配置

Alembic は DB モデルを持つ API アプリケーションの管理対象として、`apps/api` 配下に置く。

```text
apps/api/
├── alembic.ini
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
└── src/
    └── press_watch_api/
        └── models/
```

`alembic.ini` の `script_location` は `migrations` とし、通常の操作は `apps/api` ディレクトリで実行する。
API プロジェクトは `package = false` のため、`alembic.ini` では `prepend_sys_path = src` を設定し、`press_watch_api` を import できるようにする。
API 側の `pyproject.toml` / `uv.lock` で Alembic を管理し、root や scraper 側には migration 用の依存を持たせない。

## target_metadata

Alembic の `target_metadata` は `press_watch_api.models.base.Base.metadata` を使う。

Autogenerate でテーブルを認識できるように、`migrations/env.py` では `Base` だけでなく SQLAlchemy model モジュールも import する。
モデルが増えた場合は、`press_watch_api.models.__init__` に model import を集約し、`env.py` はそのパッケージを import する形に寄せる。

```ini
[alembic]
script_location = migrations
prepend_sys_path = src
```

```python
from press_watch_api.models.base import Base
import press_watch_api.models.press_release  # noqa: F401

target_metadata = Base.metadata
```

`DATABASE_URL` は既存の `press_watch_api.config.load_settings()` から読み込み、`.env` の内容を migration ファイルや docs に書き込まない。

## 初版 migration 方針

初版 migration は `press_releases` テーブルだけを作成する。
対象は Phase 3 で決めた原本データ保存に必要なカラムと制約に限定し、独自カテゴリ、ブックマーク、API 表示用の派生項目は含めない。

初版 migration に含めるもの:

- `id`: `BigInteger` 主キー
- `title`: `Text`, `nullable=False`
- `source_url`: `Text`, `nullable=False`
- `published_at`: `Date`, `nullable=False`
- `source_categories`: PostgreSQL `text[]`, `nullable=True`
- `fetched_at`: timezone 付き datetime, `nullable=False`
- `created_at`: timezone 付き datetime, `nullable=False`, DB 側 default `now()`
- `updated_at`: timezone 付き datetime, `nullable=False`, DB 側 default `now()`
- `source_url` の名前付き一意制約 `uq_press_releases_source_url`

初版 migration は `31765401e166_create_press_releases.py` として作成済み。
作成時は autogenerate を下書きとして使い、生成結果を手で確認する。
特に PostgreSQL の `text[]`、`source_categories` の NULL 許容、timezone 付き timestamp、制約名、server default が SQLAlchemy model と一致しているかを見る。

`source_categories` は環境省ページに表示された取得元カテゴリであり、過去ページではカテゴリ表示がない発表が存在する。
カテゴリが取れない発表も原本データとして保存できるよう、初版 migration では NULL を許容する。
scraper の取得結果で `source_categories` が空の tuple / list の場合は、保存用 DTO へ変換する段階で `None` に正規化し、DB には NULL として保存する。
1件以上カテゴリが取得できた場合だけ、文字列配列として保存する。

初回 INSERT 時は `created_at` と `updated_at` に同じ時刻が入る想定とする。
`created_at` は PressWatch に初めて保存した日時、`updated_at` は保存済み行を最後に更新した日時を表す。
`updated_at` はユーザー操作による編集日時ではなく、環境省サイト上の修正などを検知して PressWatch 側の保存データを更新した場合の日時として扱う。
`fetched_at` は環境省ページからデータを取得した日時であり、DB行の作成・更新日時とは分けて扱う。
Phase 3 初期では既存データの自動更新は扱わず、通常の重複データはスキップする。

## updated_at トリガー

初版 migration では `updated_at` 自動更新用の PostgreSQL トリガーは作らない。

理由は、Phase 3 初期の通常更新経路は SQLAlchemy repository / service に閉じる想定であり、DB へ直接 `UPDATE` する運用をアプリケーションの通常経路にしないため。
SQLAlchemy model の `onupdate=func.now()` は SQLAlchemy 経由の更新では有効だが、psql などから DB を直接更新した場合には自動実行されない。

DB 直接更新でも `updated_at` を必ず更新したい要件が出た時点で、別 migration として PostgreSQL トリガーを追加する。
それまでは、repository の更新処理で明示的に `updated_at` を更新するか、SQLAlchemy の `onupdate` による更新に寄せる。

## 実行方針

ローカル PC から直接実行する場合:

```bash
cd apps/api
DATABASE_URL=postgresql+psycopg://presswatch:your-local-postgres-password@127.0.0.1:5432/presswatch uv run alembic upgrade head
cd ../..
```

Docker Compose の API コンテナから実行する場合:

```bash
docker compose --env-file .env -f infra/compose.yml exec api uv run alembic upgrade head
```

初版 migration 作成時は次の形を基本にし、生成後に内容をレビューする。

```bash
cd apps/api
DATABASE_URL=postgresql+psycopg://presswatch:your-local-postgres-password@127.0.0.1:5432/presswatch uv run alembic revision --autogenerate -m "create press_releases"
cd ../..
```

現時点では `apps/api` に Alembic 依存、`alembic.ini`、`migrations/env.py`、初版 migration が追加済み。
今後のスキーマ変更では、同じ `apps/api` 配下で revision を追加し、生成内容を確認してから適用する。
