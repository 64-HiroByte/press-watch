# PressWatch - デプロイ構成と運用計画

本人向け限定配置の構成、設定と検証の手順をまとめる。
進捗と未完了の条件は[Phase 7のタスク](tasks.md#phase-7-定期実行と運用準備)で管理する。
一般公開、実データ投入、取得ジョブの配置・定期実行は、それぞれ別の完了条件として扱う。

## 限定配置の構成と選定理由

```text
本人のブラウザ
  → HTTPS・Basic認証 → Railway Web（Next.js）
  → Railway内部通信 → Railway API（FastAPI）
  → 証明書・ホスト名を検証するTLS接続 → Supabase PostgreSQL
```

| 配置先 | 責務と接続 |
| --- | --- |
| Railway Web | 画面を生成する。外部からの入口とし、APIを内部ネットワークで呼ぶ |
| Railway API | 入力検証・検索・DB読取りを行う。公開ドメイン・TCP Proxyを設けない |
| Supabase | 記事・固定カテゴリ・分類結果をPostgreSQLで保持する。WebへDB資格情報を渡さない |
| 取得ジョブ（未配置） | 既存Pythonコマンドで取得・分類・保存する。APIとは別の書込み用資格情報を使う |

Web・APIの配置先には、既存のNext.jsとPython APIをコンテナで動かせ、管理先をまとめられるRailwayを選んだ。
DBは採用済みのSupabase PostgreSQLを継続利用する。
WebサーバーがAPIを呼ぶ既存構成を維持できるため、ブラウザからAPIへ直接接続する公開入口は必要ない。
同じRailway環境の内部通信を使い、APIへの直接の外部アクセスを避ける。
[Railway Private Networking](https://docs.railway.com/networking/private-networking)を参照する。

Web・APIは各1レプリカ、APIは1 workerを起点とする。
自動増台、PR環境、永続ディスク、追加サービスは必要性を確認してから導入する。

## 費用の見込みと停止条件

契約・プラン変更前に、料金、利用枠、期限、通知と停止の条件を公式情報で確認する。
Trialのクレジットを継続運用の無料枠とみなさず、有料移行は別に判断する。
リソース上限は利用量を制限する設定であり、固定の月額料金を意味しない。

限定配置で約1週間のCPU・メモリ・通信の使用量を観測し、月額見込みを見直す。
取得ジョブの費用は、その実行時間・頻度・通信量を別に測定して加える。
起動直後の利用額やローカルの瞬間的なメモリ使用量だけで月額を確定しない。

費用上限を使う場合は、通知と停止を区別し、対象料金、他サービスへの影響、停止精度、再開条件を確認する。
停止を解約や請求総額の保証とは扱わず、最低料金・対象外料金・Supabaseの費用も確認する。
Supabaseの休止条件と、再開時のDB接続確認は[後続のDB運用準備](#db運用と後続の取得ジョブ)に含める。

[Railway料金](https://docs.railway.com/pricing/plans)、[Trial](https://docs.railway.com/pricing/free-trial)、[費用管理](https://docs.railway.com/pricing/cost-control)、[見積もり方法](https://docs.railway.com/pricing/faqs)、[Supabase料金](https://supabase.com/pricing)を参照する。

## 公開時の保護とSupabase接続

### 本人向け限定配置の閲覧制限

Web入口をBasic認証で保護し、本番モードではページ・RSC・prefetch・静的ファイルを同じ条件で判定する。
設定不足は503、未認証・不正な資格情報は認証入力を促すヘッダー付き401で拒否し、拒否時はAPIを呼ばない。
保護する応答には`Cache-Control: private, no-store`を指定する。
URLを知らせないことだけを閲覧制限とは扱わない。

`/health`は認証設定が有効なときに固定の生存応答を返す。
DBの接続確認には、一覧とカテゴリ取得まで通す必要がある。
Basic認証は将来のユーザー登録機能とは別であり、Supabase Authを採用する場合は認証情報の検証と利用者ごとの所有者確認を設計する。

### 限定配置のDB接続

- APIは外向きIPv6を有効にし、SupabaseのDirect connectionを`sslmode=verify-full`で利用する。
  SupabaseのCAを`PRESSWATCH_DB_CA_CERT`へ設定する。
  APIは起動時に所有者のみ読書きできる一時ファイルを作成し、`PGSSLROOTCERT`へ指定する。
- API専用ロールには対象DBの`CONNECT`、`public` schemaの`USAGE`、`press_releases`・`fixed_categories`・`press_release_fixed_categories`の`SELECT`だけを付与する。
  接続上限は4とし、所有・管理・書込み権限がないことをロール所属と`PUBLIC`由来の権限も含めて確認する。
  migration・seedには別の管理接続を使い、WebへDB資格情報を渡さない。
- APIの接続URLは`connect_timeout=5`、専用ロールは`statement_timeout='5s'`とする。
  APIの共有プールは最大2接続・追加接続なし・空き待ち5秒とする。
  各期限は独立しており、Webの10秒以内に要求全体が完了する保証はない。
- Data API・RLS・既存権限は適用前に確認し、追加変更が必要なら対象と影響を別に判断する。
  HTTPS入口追加前に`anon`・`authenticated`が`public.press_releases`のSELECT権限を持たないことを確認する。
  Data API・Authの採用、権限・migration変更、DB再作成時の再確認条件は[DBの利用方針](tech-stack.md#db実装状態と未対応範囲)に従う。

[Railwayの外向きIPv6](https://docs.railway.com/networking/outbound-networking#outbound-ipv6)、[Supabaseの接続・SSL設定](https://supabase.com/docs/guides/database/connecting-to-postgres)を参照する。
準備と適用は[Supabaseへ進む条件](local-development.md#supabaseへ進む条件)に従って分ける。
ローカルの実データ確認をSupabase適用済みの根拠にしない。

### Data API無効時のPostgRESTログ抑制

Data APIを無効にしてもPostgRESTは停止せず、存在しない`pg_pgrst_no_exposed_schemas`を参照してschema不存在ログを繰り返す既知事象がある。
[Issue #136](https://github.com/64-HiroByte/press-watch/issues/136)では、監視を妨げるログを[Supabase公式KBの回避策](https://supabase.com/kb/troubleshooting/schema-pg_pgrst_no_exposed_schemas-does-not-exist)で抑制する。
空の`pgrst_no_exposed_schemas`へPostgRESTの参照先を変更し、Data APIはオフのまま維持する。
ログに出るschema名と、作成するschema名は異なる。
業務schemaの公開、追加GRANT、業務データ・API専用ロールの変更、migration・seedの再実行、再配置は含めない。

本節は実行承認を兼ねない。
実アカウント閲覧と読取り診断は対象・項目・方法を提示して承認後に行い、変更SQL・影響・実行主体・復旧方法・APIとWebの利用を確定してから適用の別承認を得る。
資格情報の入力と認証後の画面確認は本人操作を基本とする。
ターミナルを使う場合は接続元・先、読取りか書込みか、記録先、成功判定を先に説明する。
親の`DATABASE_URL`・`PG*`を除去し、承認された対象の接続情報とCAだけを渡して`sslmode=verify-full`を維持する。
秘密ファイルは明示許可なく読まず、秘密値をコマンド引数・履歴・ログ・Issue・Docsへ残さない。

#### 適用前の本人確認と読取り診断

1. Supabaseで対象プロジェクトを照合し、Data APIの`Enable Data API`がオフであることを確認する。
2. Postgresログの直近の発生時刻・件数・間隔と1件の詳細を確認する。
   エラー文、SQLSTATE `3F000`、約32秒間隔、構造調査SQL、接続情報のPostgREST・`authenticator`との整合を確認する。
   対象や発行元が違う場合は適用しない。
3. 対象プロジェクトのSQL Editorで、次の読取り専用SQLを実行する。
   管理ロールを使い、診断時と適用時の`current_user`を一致させてschema作成者のデフォルト権限を照合する。
   出力は業務データ・パスワード・設定配列全体を含まず、1つのJSONとして取得する。

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SET LOCAL search_path = pg_catalog;
WITH target_schemas AS (
  SELECT oid, nspname, nspowner, nspacl
  FROM pg_namespace
  WHERE nspname IN ('pgrst_no_exposed_schemas', 'pg_pgrst_no_exposed_schemas')
), role_settings AS (
  SELECT r.rolname, s.setdatabase, d.datname,
         substr(v.setting, strpos(v.setting, '=') + 1) AS db_schemas
  FROM pg_db_role_setting s
  JOIN pg_roles r ON r.oid = s.setrole
  LEFT JOIN pg_database d ON d.oid = s.setdatabase
  CROSS JOIN LATERAL unnest(s.setconfig) AS v(setting)
  WHERE r.rolname = 'authenticator'
    AND split_part(v.setting, '=', 1) = 'pgrst.db_schemas'
)
SELECT jsonb_build_object(
  'observed_at', clock_timestamp(),
  'database', current_database(),
  'executor', current_user,
  'server_version', current_setting('server_version'),
  'transaction_read_only', current_setting('transaction_read_only'),
  'authenticator_exists', EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticator'),
  'db_schemas_settings', (SELECT coalesce(jsonb_agg(to_jsonb(s) ORDER BY setdatabase), '[]'::jsonb) FROM role_settings s),
  'schema_inventory', (
    SELECT jsonb_agg(jsonb_build_object(
      'name', nspname, 'owner', pg_get_userbyid(nspowner), 'acl', nspacl
    ) ORDER BY nspname) FROM pg_namespace
  ),
  'target_schema_objects', (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
      'schema', n.nspname, 'object', pg_describe_object(d.classid, d.objid, d.objsubid)
    ) ORDER BY n.nspname, d.classid, d.objid, d.objsubid), '[]'::jsonb)
    FROM target_schemas n
    JOIN pg_depend d ON d.refclassid = 'pg_namespace'::regclass AND d.refobjid = n.oid
  ),
  'creator_default_acl', (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
      'object_type', a.defaclobjtype, 'schema', n.nspname, 'acl', a.defaclacl
    ) ORDER BY a.defaclnamespace, a.defaclobjtype), '[]'::jsonb)
    FROM pg_default_acl a
    LEFT JOIN pg_namespace n ON n.oid = a.defaclnamespace
    WHERE a.defaclrole = (SELECT oid FROM pg_roles WHERE rolname = current_user)
  ),
  'raw_select', (
    SELECT jsonb_agg(jsonb_build_object(
      'role', x.role_name, 'role_exists', r.oid IS NOT NULL,
      'table_exists', c.oid IS NOT NULL,
      'table_select', has_table_privilege(r.oid, c.oid, 'SELECT'),
      'any_column_select', has_any_column_privilege(r.oid, c.oid, 'SELECT'),
      'rls', c.relrowsecurity, 'force_rls', c.relforcerowsecurity
    ) ORDER BY x.role_name)
    FROM (VALUES ('anon'), ('authenticated')) AS x(role_name)
    LEFT JOIN pg_roles r ON r.rolname = x.role_name
    LEFT JOIN pg_class c ON c.oid = to_regclass('public.press_releases')
  )
) AS diagnostic;
COMMIT;
```

`transaction_read_only`は`on`、`authenticator_exists`は`true`を期待する。
`raw_select`は両ロール・原本テーブルが存在し、`table_select`・`any_column_select`とも`false`であることを確認する。
`null`や対象欠落は権限なしの証拠にせず、診断を未完了とする。
列単位のGRANTは`has_table_privilege`だけでは検出できないため、[列権限の確認関数](https://www.postgresql.org/docs/17/functions-info.html#FUNCTIONS-INFO-ACCESS-TABLE)も使用する。
RLSは適用前後で照合し、RLSだけを原本保護の根拠にしない。
ACLの`null`は権限なしではなく標準のデフォルト権限を表すため、所有者とデフォルト権限を含めて判断する。

4. API専用ロール名を本人が既存の設定・記録と照合し、次の`<API専用ロール名>`だけを置き換えて別に実行する。
   接続URLやパスワードは貼り付けない。
   対象ロールの欠落、想定外の所属・所有・権限・設定があれば適用せず調査へ戻る。

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SET LOCAL search_path = pg_catalog;
WITH api AS (
  SELECT oid, rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb,
         rolcanlogin, rolreplication, rolbypassrls, rolconnlimit
  FROM pg_roles WHERE rolname = '<API専用ロール名>'
), objects AS (
  SELECT c.oid, c.relname, c.relkind
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
)
SELECT jsonb_build_object(
  'observed_at', clock_timestamp(),
  'database_identity', (
    SELECT jsonb_build_object('oid', oid, 'name', datname, 'acl', datacl)
    FROM pg_database WHERE datname = current_database()
  ),
  'role_found', EXISTS (SELECT 1 FROM api),
  'attributes', (SELECT to_jsonb(a) FROM api a),
  'memberships', (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
      'role', r.rolname, 'can_inherit', pg_has_role(a.oid, r.oid, 'USAGE'),
      'can_set_role', pg_has_role(a.oid, r.oid, 'SET')
    ) ORDER BY r.rolname), '[]'::jsonb)
    FROM api a CROSS JOIN pg_roles r
    WHERE r.oid <> a.oid AND pg_has_role(a.oid, r.oid, 'MEMBER')
  ),
  'settings', (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
      'database_oid', s.setdatabase, 'key', split_part(v.setting, '=', 1),
      'value', substr(v.setting, strpos(v.setting, '=') + 1)
    ) ORDER BY s.setdatabase, v.setting), '[]'::jsonb)
    FROM api a JOIN pg_db_role_setting s ON s.setrole = a.oid
    CROSS JOIN LATERAL unnest(s.setconfig) AS v(setting)
    WHERE split_part(v.setting, '=', 1) IN (
      'statement_timeout', 'lock_timeout', 'default_transaction_read_only', 'search_path'
    )
  ),
  'owned_objects', (
    SELECT coalesce(jsonb_agg(pg_describe_object(d.classid, d.objid, d.objsubid)
      ORDER BY d.classid, d.objid, d.objsubid), '[]'::jsonb)
    FROM api a JOIN pg_shdepend d ON d.refobjid = a.oid
    WHERE d.refclassid = 'pg_authid'::regclass AND d.deptype = 'o'
      AND d.dbid IN (0, (SELECT oid FROM pg_database WHERE datname = current_database()))
  ),
  'database_privileges', (
    SELECT jsonb_build_object(
      'connect', has_database_privilege(a.oid, current_database(), 'CONNECT'),
      'create', has_database_privilege(a.oid, current_database(), 'CREATE'),
      'temporary', has_database_privilege(a.oid, current_database(), 'TEMPORARY')
    ) FROM api a
  ),
  'schema_privileges', (
    SELECT jsonb_agg(jsonb_build_object(
      'schema', n.nspname, 'usage', has_schema_privilege(a.oid, n.oid, 'USAGE'),
      'create', has_schema_privilege(a.oid, n.oid, 'CREATE')
    ) ORDER BY n.nspname) FROM api a CROSS JOIN pg_namespace n
    WHERE n.nspname IN ('public', 'pgrst_no_exposed_schemas', 'pg_pgrst_no_exposed_schemas')
  ),
  'object_privileges', (
    SELECT jsonb_agg(jsonb_build_object(
      'object', c.relname, 'kind', c.relkind,
      'select', CASE WHEN c.relkind = 'S' THEN has_sequence_privilege(a.oid, c.oid, 'SELECT')
        ELSE has_table_privilege(a.oid, c.oid, 'SELECT') END,
      'any_column_select', CASE WHEN c.relkind <> 'S' THEN has_any_column_privilege(a.oid, c.oid, 'SELECT') END,
      'write_or_definition_privilege', CASE WHEN c.relkind = 'S'
        THEN has_sequence_privilege(a.oid, c.oid, 'USAGE, UPDATE')
        ELSE has_table_privilege(a.oid, c.oid, 'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN')
          OR has_any_column_privilege(a.oid, c.oid, 'INSERT, UPDATE, REFERENCES') END
    ) ORDER BY c.relname) FROM api a CROSS JOIN objects c
  )
) AS api_diagnostic;
COMMIT;
```

`role_found`が`true`であることを確認し、属性・所属・所有・設定・権限を[限定配置の基準](#限定配置のdb接続)と照合する。
`database_identity`でDB別設定のOIDと現在のDBを照合する。
DBの`TEMPORARY`権限がある場合はDBのACLから付与元を確認し、専用ロールへの直接付与と`PUBLIC`由来の実効権限を区別して記録する。
`TEMPORARY`は一時テーブルの作成権限であり、業務テーブルへの書込み権限とは別に扱う。
想定外なら適用を止め、APIロールや`PUBLIC`の権限変更を今回の対応へ自動追加しない。
権限確認関数は`PUBLIC`・継承由来も含む実効権限を返す。
直接ログイン時の権限と、所属先へ`SET ROLE`できる権限は区別して確認する。
このSQLは`public`のテーブル・列・連番と対象schemaを調べるもので、全schemaや全関数の権限監査ではない。
想定外の所属があれば所属先の権限も確認するまで適用しない。

5. Railwayで本人向け限定配置のプロジェクト・環境、Web・APIの配置SHA、APIに公開ドメイン・TCP Proxyがないことを照合する。
6. 適用前後で比較する内部APIとWebの代表条件・期待結果を固定する。
   環境利用の承認後、既存のRailway Console等から一覧・検索・カテゴリ絞り込み・ページ切替の基準を取得する。
   `/fixed-categories`と`/press-releases`を使い、検索語・カテゴリslug・ページ番号・件数・応答の表示項目を記録する。
   公開APIや新しいサービスは作成しない。

今回の代表ケースは、カテゴリ一覧、無条件の一覧1ページ目・2ページ目、タイトル検索`q=土壌`、カテゴリ絞り込み`fixed_category=air`の5件とする。
既存APIサービスのConsoleから`127.0.0.1`の既存待受けポートへGETだけを送り、HTTP 200、件数・ページ情報、応答JSON全体のSHA-256を記録する。
応答はJSONのキーをソートし、`ensure_ascii=False`、`separators=(",", ":")`で直列化して比較する。
同じ条件での適用後確認と区別し、過去のハッシュだけを現在の基準にせず、適用前に基準を取得する。

同名schemaがあれば内容・所有者・ACLと用途を調べ、無条件に作成・再利用・削除しない。
`authenticator`の独自設定、想定外の権限、公式手順の変更があれば、変更範囲と復旧方法を見直して別承認を得る。
診断時と適用直前の対象・設定・schema・権限が変わっていないことも照合する。

#### 別承認後の適用と解除

事前確認でschemaが存在せず、既存設定との衝突もないことを確認した場合の適用SQLを示す。
変更用SQLを準備する前に、読取り診断で直前の対象・設定・権限を記録と再照合する。
結果を報告して適用の承認を得てから、適用SQL用の新しいクエリを作成する。
読取り診断と変更用SQLは別タブに分け、その段階で実行するSQLを明示する。
本人が対象プロジェクトのSQL Editorで管理ロールを使い、選択実行せず全体を実行する。
途中で失敗した場合はコミット成功と扱わず、残ったトランザクションがあれば`ROLLBACK`し、状態を読み取りで確認する。

```sql
BEGIN;
CREATE SCHEMA pgrst_no_exposed_schemas;
ALTER ROLE authenticator SET pgrst.db_schemas = 'pgrst_no_exposed_schemas';
NOTIFY pgrst;
COMMIT;
```

公式の3文をトランザクションにまとめ、変更のコミット後に再読込み通知を配送する。
`NOTIFY pgrst;`は設定とschemaキャッシュの両方の再読込みを通知するが、通知成功だけで反映済みとは判断しない。
[PostgreSQLの通知とトランザクション](https://www.postgresql.org/docs/17/sql-notify.html)、[PostgRESTのListener](https://docs.postgrest.org/en/v13/references/listener.html)を参照する。

事前に対象のロール共通設定が未設定だった場合の解除SQLは次のとおりとする。
既存値があった場合はRESETだけでは復元できないため、元の値と設定スコープへ戻すSQLを適用前に確定する。
解除も事前承認された復旧範囲だけで行う。

```sql
BEGIN;
ALTER ROLE authenticator RESET pgrst.db_schemas;
NOTIFY pgrst;
COMMIT;
```

Data APIがオフのまま解除すると、元のログ連発が再発し得る。
空schemaの削除やData APIの再有効化は通常の解除に含めず、必要なら依存・権限・公開範囲を調べて別承認を得る。

#### 適用後の判定と記録

1. 読取り診断を再実行し、空schemaの所有者・ACL・オブジェクトなし、`authenticator`の保存設定を確認する。
   Data APIオフ、原本のテーブル・列SELECT不可、RLS、API専用ロールの既存権限・設定も前後で照合する。
2. コミット時刻以後の新規ログを最低5分観測する。
   約32秒間隔の同一エラーが停止し、別のschema・権限・接続エラーへ置き換わっていないことを確認する。
   過去ログの残存・表示遅延と新規発生を区別し、区別できない場合は停止確認を未完了とする。
3. 承認された既存内部APIと認証後Webで、基準と同じ一覧・検索・カテゴリ絞り込み・ページ切替を確認する。
4. 本人が未認証の別ブラウザ環境で認証要求、誤認証で拒否、正しい認証で表示されることを確認する。
   Railway APIに公開ドメイン・TCP Proxyがないことも再確認する。

SQL Editor自身の`current_setting()`や`SET ROLE`後の値を、PostgRESTの設定反映の証拠にしない。
保存設定とPostgRESTの新規ログ・既存機能を合わせて判定する。
`SET ROLE`ではログイン時の設定は読み直されないことを[PostgreSQL公式](https://www.postgresql.org/docs/17/sql-alterrole.html)でも説明している。
Webのブラウザ操作、HTTP応答・ヘッダー、設定閲覧は別の確認として記録し、未実施のRSC等の全経路まで確認済みと報告しない。
新たなエラー・公開範囲の変化・APIやWebの不具合があれば後続変更を止め、事前記録と照合して報告する。
復旧は事前承認された設定復元の範囲を守る。

必要な実行記録は秘密値を含めずGit管理外へ保存する。
共有する結果には実施主体、対象の一致、公式手順の確認日、適用・観測開始・終了の時刻とタイムゾーン、前後の設定とログ、API・Webの条件と結果、保証範囲・未確認事項、解除条件を残す。
確認後に本節へ結果を反映し、完了条件を満たした項目だけ[Phase 7の進捗](tasks.md#phase-7-定期実行と運用準備)へ反映する。

#### 限定配置での確認状況

2026年11月8日、本人がPressWatchのSupabaseのSQL Editorで公式回避策を適用し、`Success. No rows returned`と正常終了した。
同日に公式KBの手順を照合し、適用前に対象schema・設定・原本権限を再確認した。
実環境の操作主体は本人であり、確認結果はSQL Editor・Railway Consoleの出力、本人の画面操作の報告と提供画像に基づく。
PostgreSQLは17.6、ログの発行元はPostgREST 14.5・`authenticator`で、適用前はSQLSTATE `3F000`の同一エラーが約32秒間隔で発生していた。

| 対象 | 適用・確認結果 |
| --- | --- |
| schema・保存設定 | 適用前は対象2schemaなし、`pgrst.db_schemas`はロール共通・DB別とも未設定。適用後は空の`pgrst_no_exposed_schemas`、所有者`postgres`、標準のデフォルトACL、オブジェクト0件。`authenticator`のロール共通設定はこのschemaだけを指定 |
| 原本の保護 | 前後とも`anon`・`authenticated`は原本のテーブル・列SELECT不可。原本のRLSとFORCE RLSはオフのまま維持 |
| API専用ロール | `presswatch_api_readonly`の既存属性・所属・所有・権限・設定は前後一致。指定3テーブルのSELECTのみ、確認対象のテーブル・連番の書込み等権限、所有、所属、管理属性なし。接続上限4、対象DBの`statement_timeout=5s`。新しい空schemaへのUSAGE・CREATEなし |
| DB権限の区別 | DBのACLは前後一致。専用ロールへの直接付与はCONNECTのみ。既存の`PUBLIC`由来のCONNECT・TEMPORARYを維持し、一時テーブル作成権限もあることを区別して記録 |
| Data API・API非公開 | 本人の適用後の設定閲覧でもData APIオフ、Railway APIの公開ドメイン・TCP Proxyなしを再確認 |
| 既存内部API | 前後の代表5件すべてHTTP 200。応答全体のSHA-256・件数・ページ情報・API配置SHAが一致。カテゴリ10件、原本34,421件、検索「土壌」823件、カテゴリ`air`1,004件 |
| Web・認証拒否 | 本人のブラウザ操作で代表4操作の件数・ページ切替が前後一致。適用後も未認証・誤認証で一覧を見られないことを確認 |
| 配置コード | 作業中のWeb・APIの稼働SHAを`1c43cd80f87ca0023bce2bf6d9ddea9c86757eba`と照合。再配置は行わず、適用後のAPI確認でも同じSHA |

DBの適用後確認は06:41:52 UTC、APIロールの権限照合は06:44:39 UTCに行った。
内部APIの比較基準は06:19:51 UTC、適用後の確認は06:46:17 UTCの本人のConsole出力を使用した。
本人提供のPostgresログ画像では、表示時刻15:39:08を最後に同一エラーが止まり、15:39:24に適用SQLの記録、15:42:40・15:42:41に正常なcheckpointログがある。
15:51頃までの表示範囲で、適用後5分以上の同一エラー停止と別のschema・権限・接続エラーへの置換がないことを確認し、保存設定と合わせてPostgRESTへの反映を判断した。
画像内ではタイムゾーンが明示されていないため、これらは画面表示時刻として記録し、SQL結果のUTC時刻と区別する。

保証範囲は当日の診断・ログ画像・代表操作であり、将来の無期限の無発生や全schema・全関数の権限監査は含まない。
WebのHTTPステータス・ヘッダーやRSC等の全経路を今回実測したとは扱わず、ブラウザ上で確認した範囲と区別する。
解除SQLによる復旧試験は行っていない。
今回の適用前設定は未設定だったため、解除には本節のRESETと再読込み通知を使う。
上流修正の採用や将来のData API再有効化で解除が必要になった場合は、その時点の公式手順・保存設定・公開範囲と承認を再確認する。

## Railwayでの限定配置手順

1. 利用プランと費用・停止条件を確認する。
   外部環境への操作は、対象と影響を示して段階ごとに承認を得る。
2. Supabaseのrevision・記事件数・権限を読み取りで確認し、書込みを止めてバックアップを取得・検査する。
   変更内容と復旧方法を確認してから必要なmigration・seed・専用ロールの設定を行う。
   記事0件で疎通を検証する場合、実データ投入を同時に行わない。
3. CIと本番イメージの検証を通過したコミットSHAを特定する。
   GitHub連携では初回配置を保留し、Web・APIを同じ配置元へ接続して自動デプロイを無効にする。
   次の設定が完了するまで、ビルド・配置を開始しない。
4. 下表の設定をWeb・APIへ登録し、同じRailway環境へ手動配置する。
   build contextはリポジトリルートとし、各Dockerfileの最終`production`ステージと既存の起動コマンドを使う。
   初回検証ではServerlessを無効、Restart PolicyをNeverにする。
   配置直前と直後にSHAを照合し、不一致ならHTTPS入口の追加へ進まない。
   停止や失敗があれば原因を確認してから再配置する。
5. 内部疎通・DB接続・読取り権限・Webの認証拒否と認証済み表示を確認する。
   セキュリティ情報と検証結果を確認し、未対応事項があれば影響と対応時期を示して判断・承認を得る。
6. WebだけにHTTPSドメインを付け、外部からの未認証・不正認証の拒否と、APIに公開経路がないことを再確認する。
   本人のブラウザでログイン、一覧・カテゴリ表示、検索条件の操作を確認する。
   配置後の継続した利用量評価は、起動確認とは別に行う。

| サービス | 配置用の設定 | アプリ用の実行時設定 |
| --- | --- | --- |
| Web | `RAILWAY_DOCKERFILE_PATH=infra/docker/web.Dockerfile` | `PRESSWATCH_API_BASE_URL`に内部APIのHTTP URL、`PRESSWATCH_BASIC_AUTH_USER`と`PRESSWATCH_BASIC_AUTH_PASSWORD` |
| API | `RAILWAY_DOCKERFILE_PATH=infra/docker/python.Dockerfile`、`PORT=8000`、`HOST=0.0.0.0`、外向きIPv6有効、公開ドメイン・TCP Proxyなし | 読取り専用ロールの`DATABASE_URL`、`PRESSWATCH_DB_CA_CERT` |

内部IPv4に対応するRailway環境では、APIの待受は`0.0.0.0`を使う。
APIの待受アドレスと、Supabaseへ接続するための外向きIPv6は別の設定である。
Webの`PORT`はRailwayが渡す値を使い、公開ドメインの転送先ポートと一致させる。
環境変数の値を入力する際は、Markdownのバッククォート等を含めない。

Basic認証のパスワードは十分に長いランダム値とし、ユーザー名にはコロンを含めない。
資格情報は必要なサービスだけへ渡し、ビルド・ログ・クライアントコード・テスト成果物に含めない。
[内部ネットワーク](https://docs.railway.com/networking/private-networking/how-it-works)、[Uvicornの待受設定](https://docs.railway.com/networking/troubleshooting/application-failed-to-respond)、[Dockerfileの指定](https://docs.railway.com/builds/dockerfiles)、[GitHubの配置設定](https://docs.railway.com/deployments/github-autodeploys)を参照する。

### 検証と停止・復旧

| 確認する経路 | 合格条件 |
| --- | --- |
| Web・APIの`/health` | 各プロセスが応答する。これだけでDB疎通の合格とはしない |
| API → Supabase | 一覧・カテゴリ取得が成功し、TLS・証明書とホスト名の検証・専用ロールの権限と期限が設定どおりである |
| Web → 内部API | 内部URLで取得でき、認証済み画面へ反映される |
| Webの閲覧制限 | HTML・RSC・prefetch・実在する静的ファイル・告知ファイルを未認証で取得できず、不正な資格情報も拒否される |
| Webの外部HTTPS入口 | 未認証・不正認証をチャレンジ付き401で拒否し、保護する応答に`private, no-store`が付く |
| 本人のブラウザ | 認証後に一覧・カテゴリを表示し、条件操作でURLと結果表示が更新される |
| APIの公開経路 | 公開ドメイン・TCP Proxyがない |

ヘルスチェック、内部HTTP、外部HTTPS、ブラウザ操作の結果は区別し、実施していない検証を合格と扱わない。
認証迂回や情報露出時はWebの公開ドメインを外して配置を停止し、保護が確認できるまで公開を再開しない。
DB障害時は追加の書込みを止め、現況・バックアップ・ロールと権限の記録から復旧方法を決めて別承認を得る。
アーカイブを読み取れたことと、実際のDBへ復元できたことを区別し、全体復元やdowngradeを自動実行しない。
本番イメージの構成と合成データによる検証手順は[本番用Docker](production-docker.md)を参照する。

## Railway設定のファイル管理

IaCは既存のWeb・API設定を取り込み、理解・再利用できる形にするために使う。
設定本体は`.railway/railway.ts`で管理し、既存のWeb・APIの設定を取り込んでいる。
環境変数は秘密値・通常値ともに`preserve()`で既存値を保持し、値そのものはファイルへ保存していない。
適用・再配置・CIからの自動適用は、この段階の対象外とする。

### ローカルの準備

Node.jsとpnpmはルートの指定版を使い、`pnpm install --frozen-lockfile`でIaC用の開発依存も導入する。
SDKは`railway` 3.16.0、CLIは5.71.0に固定する。
CLIは[公式リリース](https://github.com/railwayapp/cli/releases/tag/v5.71.0)からOS・CPUに合う配布物を取得し、公式のSHA-256 digestと照合した後、Git管理外の`tmp/tools/railway/5.71.0/railway`へ配置する。
macOS arm64の配布物は`railway-v5.71.0-aarch64-apple-darwin.tar.gz`である。
インストーラーやCLIの自動更新を使わず、別の版への変更は互換性を確認してから判断する。

```bash
pnpm railway:cli --version
```

`railway:cli`は固定バイナリの絶対パスと`RAILWAY_NO_AUTO_UPDATE=1`を使い、毎回版を確認する。
SDKの版確認にも同じ実行ファイルを渡し、旧TypeScript runnerへの環境変数による切替は継承しない。
認証・接続先選択・pull・planもこの入口を使う。
CLI認証と接続先保存ではローカルのCLI設定が読み書きされるため、実環境の読み取り承認にはこの操作も含める。

### 承認後の取り込みと照合

対象プロジェクト・環境を示し、設定閲覧、CLI認証・接続先保存、pull・planの承認を得てから実行する。
DBへの接続や書込みは含めない。

```bash
pnpm railway:cli login
pnpm railway:cli link
pnpm railway:cli config pull --variables=managed
```

接続先は本人向け限定配置の環境と照合し、予期しないサービスやリソースがあれば取り込み結果を省略せず作業を止める。
秘密値を展開・復号するオプション、変数を省略するオプション、値を表示するオプションを使わない。
初回取り込み後、または既存ファイルを退避・比較したうえで再取り込みする場合は、CLIが生成するproject直下の`variables: { managed: true }`だけを除き、SDK 3.16.0の型に合わせる。
サービスごとの`env`と`preserve()`は保持し、型キャストで検査を回避しない。
CLI 5.71.0ではprojectの指定省略時もmanaged・除外なしが既定値であり、planの表示で`variables: managed (default)`を確認する。

```bash
pnpm typecheck:railway
pnpm plan:railway
```

設定ファイルが未取り込みの場合、両コマンドは失敗する。
型検査の成功と実環境での照合は区別し、既存のWeb CI成功をIaC型検査の成功とは扱わない。
planの終了0と追加・変更・削除ゼロを合格とし、終了2は未解消の差分、その他の非0は実行エラーとして扱う。
差分が残る場合は内容を報告し、実環境を書き換えてゼロに合わせない。

`preserve()`は実環境に同名変数が存在することを保証しない。
値を表示せず、Webの`PRESSWATCH_API_BASE_URL`・`PRESSWATCH_BASIC_AUTH_USER`・`PRESSWATCH_BASIC_AUTH_PASSWORD`、APIの`DATABASE_URL`・`PRESSWATCH_DB_CA_CERT`のキーが存在することを別に確認する。
欠落があれば未完了とし、この段階で追加・変更しない。
変更ゼロは秘密値の正しさやサービスの正常動作の保証ではない。

### 管理する範囲と新環境で必要な操作

配置元、Dockerfile、起動・ヘルスチェック、地域・レプリカ、再起動、Serverless、外向きIPv6、設定済みリソース上限と通常の環境変数を現況と対応付ける。
設定値の意味は本書の限定配置手順に従い、明示値とRailway提供値を区別する。
自動デプロイ無効・初回配置保留、生成HTTPSドメインと転送先ポート、APIに公開経路がないこと、費用上限・通知は手動の設定・確認事項として残す。
Supabaseのmigration・seed・ロール・バックアップも既存のDB手順で管理する。
新環境では`preserve()`だけでは通常値も秘密値も用意できないため、上記の配置設定表に従って対象サービスへ必要な値を安全に登録し、接続先と手動管理項目を確認してから配置承認へ進む。
取り込み時の`build.builder`は`RAILPACK`だが、Dockerfileの選択には既存の`RAILWAY_DOCKERFILE_PATH`が必要であり、この変数も`preserve()`で保持している。
キーの存在とplanの変更ゼロだけでは、Dockerfileのパスなどの通常値まで新環境へ再現したことにはならない。

[公式IaC手順](https://docs.railway.com/infrastructure-as-code)、[CLI仕様](https://docs.railway.com/cli/config)を参照する。

## 一般公開前の過剰要求対策

本人向けの閲覧制限と、過剰要求対策は別の条件である。
APIが内部専用でもWeb経由の検索は可能なので、[要件NFR-006](requirements.md#nfr-006-公開apiへの過剰なリクエストを抑制できること)の対策を省かない。
一般公開前にWeb・APIそれぞれの制限方式と値を決め、正常操作、HTTP 429、DB非照会、接続元偽装、workerや再起動時の扱いを確認する。
Railwayの基盤上限をアプリのリクエスト数制限とは扱わない。
Under Attack Modeは非ブラウザ通信への影響も確認してから使う。
[公開ネットワークの仕様](https://docs.railway.com/networking/public-networking/specs-and-limits)、[Railway WAF](https://docs.railway.com/networking/waf)を参照する。

## DB運用と後続の取得ジョブ

保存済み原本のSupabaseへの投入・再分類と内部API・本人向けWebの確認は完了し、確認範囲は[限定配置での適用・確認状況](supabase-data-import.md#限定配置の適用と確認状況)に記録する。

Supabaseのプラン・容量・通信量・休止条件を確認し、休止後は状態確認・必要な再開操作・DB接続確認を行う。
Railway側の再開だけで復旧すると仮定しない。
運用中のバックアップ頻度・保管先・復元確認を、適用前バックアップとは別に決める。
[Supabaseの休止条件](https://supabase.com/docs/guides/platform/free-project-pausing)、[バックアップ](https://supabase.com/docs/guides/platform/backups)、[費用管理](https://supabase.com/docs/guides/platform/cost-control)を参照する。

取得ジョブの配置先候補はRailwayとし、既存の`press_watch_api.commands.fetch_and_save_env_press`を実行入口とする。
APIとは別の保存用ロールを用意し、本番用Dockerの`job`ターゲットで取得・保存・終了を手動検証してから定期実行へ進む。
実行コマンドとrobots.txtの確認条件は[取得・保存の手順](local-development.md#手動で取得してdbへ保存する)と[scraper単体の手順](local-development.md#scraper-を単体で起動する)に従う。
正確な実行時刻、実行上限、再試行、重複防止、親子プロセス終了と失敗・欠落の確認方法は配置前に確定する。

Cronは厳密な開始時刻を保証せず、前回実行が残る場合のスキップも考慮する。
終了コードだけで未保存とは判断せず、失敗時の診断を確認してから再実行する。
既存の終了コード・stdout・stderrとサービスの実行結果を使い、独自の実行履歴DBや長期ログ基盤は必要性を確認してから追加する。
[Railway Cron](https://docs.railway.com/cron-jobs)、[再起動方針](https://docs.railway.com/deployments/restart-policy)、[ログ](https://docs.railway.com/observability/logs)を参照する。

## セキュリティ更新と後続タスク

配置直前と一般公開前に、使用するNode.js・Next.js・React・Python依存のセキュリティ情報を確認する。
更新した場合は本番イメージを再ビルドし、依存再現性・回帰確認・配置SHAの照合まで行う。
固定・解決版は各マニフェストとlockfile、残作業は[Phase 7のタスク](tasks.md#phase-7-定期実行と運用準備)で管理する。

後続作業は、限定配置の利用量評価、取得ジョブの配置と手動検証、定期実行、一般公開の順で条件を確認する。
一般公開前には過剰要求対策、最新のセキュリティ情報、実測費用、DBの復旧とバックアップ方針を再確認する。
