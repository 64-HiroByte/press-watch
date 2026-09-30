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
- Tailwind CSS 4系（Phase 6で導入予定）
- shadcn/ui（Phase 6で導入予定）
- Kibo UI（Phase 6で必要な部品を導入予定）
- Oxlint / Oxfmt（Phase 6のMock確認後、機能実装前に導入予定）

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

### Phase 6開始時のフロントエンド更新候補

以下は2026年9月30日時点の調査に基づく更新候補であり、導入・検証済みのバージョンではない。
更新作業時に公開状況・互換性・セキュリティ情報を再確認し、実際の解決バージョンは各マニフェストと`pnpm-lock.yaml`を正本とする。

| 対象 | 更新候補・方針 |
| --- | --- |
| Node.js | 24系LTSを維持し、24.21.0を候補にする |
| Next.js | 16.3系の最新セキュリティ修正版を確認する |
| React / React DOM | 19.3.0へ揃える |
| `@types/react` / `@types/react-dom` | 19.3.0へ揃える |
| `@types/node` | Node.jsのメジャーに合わせ、24.19.0を候補にする |
| TypeScript | 7.0.2への更新を独立して検証する |
| pnpm | 12.8.1への移行を独立して検証する |
| PostCSS | 8.5.28を候補にし、既存の上書き設定も確認する |

調査時点のNext.js公開済み最新版16.3.7には、9月30日予定のセキュリティ修正が含まれていない。
[公式告知](https://nextjs.org/blog/upcoming-nextjs-security-release-september-2026)では16.3.8で提供予定とされており、未公開版を導入済み・修正済みとして扱わない。

更新は「Node.js・pnpmと実行環境」「Next.js・React・型定義・PostCSS」「TypeScript」に分け、各段階で再インストール・型チェック・ビルド・既存画面の表示を確認する。
[pnpm 11](https://pnpm.io/blog/releases/11.0)・[pnpm 12](https://github.com/pnpm/pnpm/releases/tag/v12.0.0)の変更点に従い、設定の配置、Docker・開発手順とのバージョン統一、PostCSSの上書き設定を確認する。
TypeScript 7は[Next.jsの公式手順](https://nextjs.org/docs/app/api-reference/config/typescript)を基に、ビルドとエディターの型支援を確認する。
互換性に問題があれば、エラーを無視する設定で通さず、原因と代替案を整理する。

### Python

- Python 3.14 を採用する

### PostgreSQL

- PostgreSQL 17 を採用する
- Phase 0 では PostgreSQL 18 を初期採用したが、Phase 5 開始前に Supabase を管理 PostgreSQL として採用したため、17 へ変更する

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
- Python 3.14 および利用ライブラリで非推奨の言語機能・APIは使用せず、サポートされる代替手段を採用する
- 型注釈は Python 3.14 標準の遅延評価を使用し、非推奨の `from __future__ import annotations` は使用しない
- Pydantic は v2 系を前提とする

---

## 6. フロントエンド開発方針

- Next.js は App Router 構成とする
- TypeScript を使用する
- パッケージマネージャーは pnpm を使用する
- 一覧表示、検索、共有の固定カテゴリによる絞り込みを MVP の中心機能とする

### UI部品と選定理由

| 技術 | 役割と選定理由 |
| --- | --- |
| Tailwind CSS | 慣れた方法でスタイルを調整し、画面の作り込みに時間をかけすぎないために採用する |
| shadcn/ui | 基本部品と見た目を揃え、取り込んだコードを理解・調整して保守するために採用する |
| Kibo UI | 必要な複合部品を補い、画面固有の処理に集中するために採用する |
| Oxlint / Oxfmt | lintとformatの実行方法を揃え、機能実装時の確認を再現できるようにするために採用する |

- UI部品は使用するものだけ取り込み、基本部品との整合、追加依存、選定理由と保守範囲を確認する。
- UI部品は無料で利用できる公開OSS部品を選び、採用時にライセンスと利用条件を確認する。
  有料AI生成サービスの契約を導入の前提にしない。
- 採用部品の出典URL、取り込み日または参照バージョン、独自変更の要点を、docsの設計文書とGit履歴で追えるようにする。
- 画面固有の処理、UI部品、Mock用データを分け、Mockの表示部品を本実装へ引き継げる構成にする。
- 画面には保存済みの固定カテゴリを使用し、取得元カテゴリの`source_categories`は表示・絞り込みに使わない。
- カテゴリの選択肢と記事の所属はAPIから取得し、フロントエンドで定義の二重管理やタイトルの再分類を行わない。
- API側はページ内の記事の所属カテゴリをまとめて取得し、記事ごとのSQL照会によるN+1を防ぐ。
  記事件数を増やしても照会回数が増えないことを実DB統合テストで確認する。
- フロントエンドは一覧レスポンスに含まれる固定カテゴリを使用し、記事ごとの追加API呼び出しを行わない。
  1回の一覧表示について、カテゴリ選択肢の取得も含め、Next.jsサーバーまたはブラウザからAPIへの要求数がページ内の記事数に比例して増えないことを確認する。

### 開発・検証の順序

- 依存関係の更新とUI基盤の導入後に、固定データのMockでPC上の見た目を確認する。
  スマートフォン専用の作り込みはPhase 6の完成条件に含めない。
- Mock確認後に操作・API設計を記録・合意し、Oxlint・Oxfmtと検証基盤を整えてから機能を実装する。
- Phase 6のlint・formatはフロントエンドを対象とし、既存Markdownの書式を変更しない。
  Oxfmt導入時は共有設定の`ignorePatterns`に`**/*.md`を指定し、CLI・CIの対象パスもフロントエンドに限定する。
  Markdownの行末空白を許容する`.gitattributes`はGitの検査用であり、Oxfmtの除外設定や保存時設定とは別に維持する。
- Cursorでは公式Oxc拡張からプロジェクト内のOxlint・Oxfmtを利用し、lintとformatのルールをエディター・CLI・CIで共通に参照する。
  診断表示、保存時の整形、任意のlint自動修正を区別して設定・確認し、他言語の既存設定を維持する。
  Oxcを既定のフォーマッターに指定する場合はJavaScript・JSX・TypeScript・TSXの言語別設定とし、全言語へ一括適用しない。
  Markdownの保存時整形と末尾空白の削除を無効にし、Oxfmt導入後も末尾2スペースによる強制改行が残ることを確認する。
  [Oxlint](https://oxc.rs/docs/guide/usage/linter/editors)・[Oxfmt](https://oxc.rs/docs/guide/usage/formatter/editors)の公式手順を基に連携を確認し、導入後の設定・実行手順を[ローカル開発手順](local-development.md)へ記録する。
- 画面テストはPlaywrightのChromiumを導入する案とし、依存関係と実行方法を確認する。
  [Next.jsの公式手順](https://nextjs.org/docs/app/guides/testing/playwright)を基に、API応答を制御した画面テストと実API・DBとの結合確認を分ける。
- 型チェック・lint・format確認・ビルド・画面テストをCIへ追加し、既存Python CIとの実行範囲と省略経路を確認する。
  必須チェック設定の変更は、workflowの実装・動作確認と分けて扱う。

具体的な作業順序と完成条件は[Phase 6のタスク](tasks.md#phase-6-フロントエンド実装)に整理する。
検索やカテゴリ選択の操作、URL状態、API接続方式、キャッシュ方針、追加APIの詳細はMock確認後に確定する。

---

## 7. データベース方針

- 管理 PostgreSQL には Supabase を採用する
- Supabase とローカル開発環境では PostgreSQL 17 を使用する
- Python アプリケーションからのDB接続には SQLAlchemy + psycopg を採用する
- ORM には SQLAlchemy を採用する
- マイグレーション管理には Alembic を採用する
- PostgreSQL ドライバには psycopg を採用する
- FastAPI から `DATABASE_URL` を使って PostgreSQL へ接続する既存の構成を維持する
- Supabase への接続には、継続稼働する FastAPI と Alembic migration に適した Direct connection を使用する
- Supabase の接続確認では `sslmode=require` を指定し、実際の接続が SSL を使用していることを確認する
- Phase 5 の最初の読み取り API では Supabase SDK、Data API、Auth を利用しない
- Phase 3 初期では、報道発表の原本に近いデータを `press_releases` に保存することを優先する
- `press_releases.source_url` には、環境省の報道発表詳細ページURLを保存し、一意制約で重複登録を防ぐ
- `source_categories` は環境省ページから取得した分類情報として保持し、PressWatch 独自カテゴリとは分けて扱う
- PressWatch 独自カテゴリは、旧 Topics Checker で使用していたCSVを初期データとする共有の固定カテゴリとして扱う
- 旧CSVの水質カテゴリは、2024年以降の報道発表を確認した結果に基づき、水道、環境水、排水へ分ける
- 固定カテゴリは、カテゴリ定義、分類キーワード、報道発表との多対多分類結果を別テーブルで管理する
- 初期データは責務を分けた2つのCSVで管理し、専用seed CLIから取り込む
- 分類は正規化したタイトルへの部分一致で行い、結果をDBへ保存する
- 固定カテゴリの初期データと分類設計の詳細は `docs/fixed-categories.md` を参照する
- ブックマーク、ユーザー登録、ユーザー定義カテゴリはMVP後に設計する
- 初期段階では、MVPに必要な最小限のテーブル構成とする
- マイグレーションは Alembic で管理し、アプリケーション起動時の `metadata.create_all()` には頼らない
- DB接続情報は環境変数から読み込む
- `.env` や秘密情報を含みうるファイルは原則読まない。確認が必要な場合も、理由を添えてユーザーの許可を得てから読む

### DB周りの採用理由

- Supabase は PostgreSQL と将来の認証基盤を一つのサービスで扱え、インフラの学習範囲を抑えながら段階的に導入しやすい
- SQLAlchemy は FastAPI と組み合わせた利用例が多く、ORM と Core の両方を使い分けやすいため、MVP 以降の検索・ページネーション・保存処理を段階的に育てやすい
- Alembic は SQLAlchemy のメタデータと連携しやすく、テーブル定義の変更履歴をレビュー可能なマイグレーションとして残せる
- psycopg は PostgreSQL 向けの標準的な Python ドライバであり、SQLAlchemy から利用しやすい

### DB責務分割方針

- API route や scraper から SQLAlchemy model を直接操作しない
- DB操作は repository 層に閉じ込める
- API schema / 入出力DTOは Pydantic で定義し、DB model と分ける
- scraper の `PressRelease` は取得結果を表す型として扱い、DB model と直接同一視しない
- スクレイピング結果を保存する処理では、変換関数または service 層を挟む
- `source_url` の一意制約をDB側に置き、repositoryで`ON CONFLICT (source_url) DO NOTHING`による一括INSERTを行う
- serviceは入力内の同一URLをまとめ、最大1,000件ずつrepositoryへ渡し、保存件数とskip件数を集計する

### DB実装状態と未対応範囲

- Supabase プロジェクトを作成し、Direct connection で同期版 SQLAlchemy + psycopg から PostgreSQL 17.6 へ接続できることを確認済みである
- Supabase へ既存 Alembic migration を head `9f2c7a4e1d63` まで適用し、`press_releases`、`uq_press_releases_source_url`、`ix_press_releases_published_at` が存在することを確認済みである
- ローカルの Docker Compose は PostgreSQL 17 へ変更済みであり、新しい空 DB への既存 Alembic migration 適用と、コンテナ再作成後も migration 適用状態が保持されることを確認済みである
- 固定カテゴリ3テーブルを追加するmigration `a51eab6808f3`はリポジトリへ追加済みであり、テスト専用PostgreSQL 17で適用、旧headへのdowngrade、再upgradeを確認済みである
  開発DBとSupabaseへの適用状況は、この検証では確認していない
- Data API は利用せず、Supabase の `anon`・`authenticated` ロールが `public.press_releases` の `SELECT` 権限を持たないことを2026年8月20日に確認済みである
- `postgres` のデフォルト権限に両ロール向けの `SELECT` が設定され、既存の `public.press_releases` に対する権限の付与元も `postgres` であることを確認したうえで、両方の `SELECT` 権限を取り消して再確認した
- この結果は現時点の確認であり、Data API や Supabase Auth の採用時、権限や migration の変更時、Supabase プロジェクトや DB の再作成時、本番公開前には再確認する
- SQLAlchemy は同期版から始める
- Phase 3 初期では保存処理、重複防止、マイグレーションの見通しを優先し、async SQLAlchemy は高並行アクセスや非同期I/Oの必要性が明確になった段階で再検討する
- DB接続設定は `apps/api/src/press_watch_api/config.py` で `DATABASE_URL` を環境変数から読み込む
- SQLAlchemy の Engine / sessionmaker は `apps/api/src/press_watch_api/db.py` でDB利用時に遅延初期化し、プロセス内で再利用する
- Docker Compose 内の接続URLは `postgresql+psycopg://presswatch:${POSTGRES_PASSWORD}@db:5432/presswatch` を基本形とする
- ローカルPCから直接接続する場合は `127.0.0.1:5432` を使い、Compose の `db` サービスはこのポートをローカルPCに限定して公開する
- 通常の保存処理では、`source_url` が既存なら重複登録せずスキップする
- `source_url` の競合以外の制約違反は失敗として扱い、呼び出し元でトランザクション全体のrollbackを試みる
- 取得・保存、seed、再分類などの同時実行を制御する排他ロックや自動再試行は実装していない
- 通常の差分取得では `source_url` の一致だけを確認し、保存済みレコードの内容は更新しない
- 既存データの修正検知は、通常の差分取得とは分け、メンテナンス用フルスキャンとして MVP後に再検討する
- 週次フルスキャンや再照合モード、`last_seen_at`、`content_hash`、変更履歴の保存は、実運用で過去データ修正の検知が必要になった時点で検討する
- 初期実装では、既存データを自動上書きするよりも重複登録を避けることを優先する
- `source_categories` は初期実装では PostgreSQL の `text[]` として保存する
- 過去ページではカテゴリ表示がない報道発表が存在するため、`source_categories` は NULL を許容する
- scraper の `source_categories` が空の場合は、保存用 DTO への変換時に `None` へ正規化し、DB には NULL として保存する
- `source_categories` にカテゴリ名以外の属性を持たせる必要が出た場合は、別テーブル化または `jsonb` 化を後続フェーズで検討する
- PressWatch独自の固定カテゴリは`press_releases`へ列を追加せず、固定カテゴリ用のマスター、キーワード、分類結果テーブルへ分ける
- 固定カテゴリのAlembic migrationはスキーマ変更だけを扱い、初期データ取込は専用seed CLIへ分ける
- 新規報道発表は保存処理と同じトランザクション内で分類し、既存報道発表は専用CLIで再分類する
- `fetched_at` / `created_at` / `updated_at` などの時刻は UTC 基準で保存する
- `fetched_at` は環境省ページからデータを取得した日時として扱い、DB行の作成・更新日時とは分ける
- 初回保存時は `created_at` と `updated_at` に同じ時刻が入る想定とする
- `updated_at` はユーザー操作による編集日時ではなく、環境省サイト上の修正などを検知して保存済み行を更新した日時として扱う
- SQLAlchemy model では `DateTime(timezone=True)` を使い、UTC への統一は保存処理で timezone aware な UTC datetime を渡すことで担保する
- 時刻をユーザーに表示する必要が出た場合は、表示層で日本時間などのローカルタイムへ変換する
- MVP の主な表示対象は公開日 `published_at` であり、取得時刻は主に定時実行、差分取得、保存状況確認、調査用のメタデータとして扱う
- scraper 取得結果から API 側 DTO へ変換し、repository / service 経由で保存する処理は Phase 3 で用意済み
- Phase 4 では、scraper CLI からDB保存までをつなぐ手動取得・保存コマンド、初回全件取得、通常の差分取得を実装済み
- メンテナンス用フルスキャンは MVP後の改善候補とする
- 定期実行と、運用者が失敗を確認するためのジョブ結果、ログ、またはサービス標準の失敗通知は Phase 7 で扱う
- 実行履歴の検索、長期保存、再試行管理などの本格的な運用機能はMVP後に検討する

### マイグレーション方針

- Alembic の設定と migration ファイルは `apps/api` 配下に置く
- `target_metadata` は `press_watch_api.models.base.Base.metadata` を使う
- Autogenerate でSQLAlchemy modelを認識できるように、Alembicの`env.py`では`press_watch_api.models`パッケージをimportする
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
├── dependencies.py
├── http_errors.py
├── models/
│   ├── fixed_category.py
│   └── press_release.py
├── routers/
│   └── press_releases.py
├── schemas/
│   ├── error.py
│   └── press_release.py
├── repositories/
│   └── press_release.py
└── services/
    └── press_release_save.py
```

- `models/`: SQLAlchemy model を置く
- `dependencies.py`: HTTPリクエストごとのDB Sessionの生成と終了を扱う
- `http_errors.py`: DB関連例外のHTTP応答への変換と固定診断の出力を扱う
- `routers/`: FastAPIのpath operationとAPIレスポンスの組み立てを置く
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

以下は、今後のタスクで決定する項目、または必要に応じて見直す項目である。

- 定期実行方式（Cron を含む）
- デプロイ先
- 公開APIのリクエスト数を制限する方式
- CI/CD 構成
- 本番向け Docker 最適化
- スクレイピング対象の拡張
- AI 要約機能の追加
- Supabase Auth と RLS を利用する範囲

---

## 10. 開発上の前提

- 実装は AI を活用して進める
- 要件定義、設計判断、レビュー、修正指示は開発者本人が担う
- 一度に大きく実装せず、小さな単位で差分確認しながら進める
- まずは PressWatch の MVP 完成を優先する
