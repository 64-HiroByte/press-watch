# 定期取得ジョブの運用

`fetch-job`は環境省の報道発表を取得し、新しい原本と分類所属を追加する専用サービスである。
一覧表示用APIとは資格情報を分け、既存記事の更新・削除や再分類は行わない。

## 現在の構成

| 項目 | 設定 |
| --- | --- |
| 対象 | Railway brilliant-compassion / production / fetch-job、Supabase PressWatch / postgres |
| ビルド | `infra/docker/python.Dockerfile`、`PRESSWATCH_PYTHON_TARGET=scheduled-job` |
| 実行基盤 | iad 1 replica、既存Trial枠2 vCPU・1 GB、restart NEVER、draining 30秒 |
| Cron | `30 1,7 * * *` UTC、毎日10:30・16:30 JST |
| 接続 | Direct connection・外向きIPv6・`verify-full`、専用保存用ロール |

両方の予定枠でCronの起動と正常終了を確認し、新着の保存とWeb表示、保存件数とDBの一致も確認した。
Cronの開始時刻には遅延があり、前回実行が残ると次回はスキップされる。
HTTP healthcheck・公開ドメイン・TCP Proxy・GitHub自動配置は設定しない。

## 起動コマンドと取得範囲

RailwayのSettings → Deploy → Custom Start Commandには、ENTRYPOINTの置換を考慮して完全なコマンドを指定する。

```text
/app/.venv/bin/python -m press_watch_api.commands.run_fetch_job --url https://www.env.go.jp/press/index.html --archive-month-limit 6 --known-release-months 3 --verbose
```

月別ページを新しい順に最大6ページ巡回し、全件既知の月で停止する。
既知URLは保存済み最新月を含む3か月から読み、時計の日付だけでは基準月は進まない。
ページ上限は厳密な日付境界ではなく、長期停止後に不足期間へ届かない場合は個別に対応を判断する。
robots.txtを毎回確認し、要求開始間隔3秒・HTTP timeout 20秒を維持する。
記事詳細やPDFは取得しない。

設定変更はfetch-jobだけを対象とする。
実取得を伴う変更は旧実行の終了とDB保存状態を確認し、次の予定時刻まで45分以上ある時間帯に行う。
Start CommandとCron式は可能なら同じ変更にまとめ、DashboardのDetailsで対象を確認してDeployする。
個別に変更する場合は、取得しないprepare-onlyのままCronを設定してから実取得コマンドへ切り替える。
設定適用でも取得が起動する可能性があるため、追加のRedeployや`cron run`を重ねない。
配置は固定CLIと送信内容を確認した隔離ディレクトリを使い、配置ID・ソースとイメージの識別情報を実施記録へ残す。
既存API・Webへの影響を避けるため、全体の`config apply`は使用しない。

## DB権限と実行保護

`presswatch_fetch_writer`はDB CONNECT、public USAGE、原本・カテゴリ・キーワード・所属のSELECT、原本と所属のINSERT、原本連番のUSAGEを持つ。
接続上限4、接続待ち5秒、保存SQLのstatement timeout 30秒・lock timeout 5秒とする。
所有・ロール所属・管理属性・既存行の更新削除・schema CREATEを許可しない。
既存PUBLIC由来のTEMPORARYは維持しており、DB内の一切の書込みを禁止するロールではない。
APIロールの権限は拡張せず、Data APIオフ・原本のanon/authenticated SELECT不可・API非公開・Web認証を維持する。

DATABASE_URLは`postgresql+psycopg://…/postgres?sslmode=verify-full`形式とし、追加のquery指定は拒否する。
サービス変数PRESSWATCH_DB_CA_CERTから所有者限定の一時CAファイルを作成する。
親のPG設定を除去し、子scraperにはDB資格情報を渡さない。
新規接続や接続先・資格情報の変更時には次の診断で主体・DB名・TLS・ロック取得を確認し、新規経路の誤CA・誤ホスト拒否も検証する。
同じ接続条件の正常なCron実行ごとに別途診断は行わない。

```text
/app/.venv/bin/python -m press_watch_api.commands.run_fetch_job --check-db-only --expected-db-user presswatch_fetch_writer --expected-db-name postgres
```

手動・再配置・Cronを同じ監督入口に通し、外部HTTPの前にsession advisory lockを非待機取得する。
ロック保持接続を5秒ごとに照会し、応答上限5秒・最大無応答10秒で停止へ進む。
接続喪失から停止までの短い重複HTTPを完全に防ぐ保証はない。
実行上限は30分、自動再接続・再試行なし。
時間切れ・シグナル・ロック異常ではCLI・uv・scraperへSIGTERMを送り、15秒後に残存群を強制終了・回収してからロック接続とCAを片付ける。
終了猶予30秒は`RAILWAY_DEPLOYMENT_DRAINING_SECONDS=30`で設定できる。
Outbound IPv6が画面にない場合は固定CLIの`outbound-network ipv6 enable`へproject・environment・serviceを明示して適用する。

## バックアップ・費用・期限

| 項目 | 現在の運転条件 |
| --- | --- |
| 運転期限 | 2026-11-16 09:00 JST / 00:00 UTCまでに手動で停止。自動失効なし |
| ローカルバックアップ | 初回投入やDB移行など、変更前の復元地点が必要なときに取得 |
| 保存と検査 | 本人Macの新規ディレクトリへpublic export。表・連番・ACL、全体読取り、サイズ・SHA-256を検査 |
| 保持 | 取得済みのdumpを運転期間と終了後7日間保持 |
| 費用 | 準備からの追加消費を累計USD 1以内。初期残高USD 4.93を基準にUSD 4.03で停止判断し、USD 3.93到達・超過予測まで継続しない |
| 容量 | DB 400 MB・ディスク1.6 GB・今期Egress 4 GBへの到達・超過予測で停止 |
| 保存用ロール期限 | 2026-12-08 13:24:24.276826 UTC / 22:24:24.276826 JST。延長して運転する場合は7日前までに継続・更新を判断 |

バックアップは下記の[実行・検査手順](#バックアップの実行と検査)に従い、既存PostgreSQL 17.11のpg_dump/pg_restoreを絶対パスで使用する。
対象のDirect Hostと既存公開CAを指定し、public schemaをcustom形式で新規取得する。
管理パスワードはpg_dumpの非表示プロンプトへ入力し、親のDATABASE_URL・PG設定・認証ファイルは使用しない。

保存先は`tmp/supabase-scheduled-fetch/<UTC日時>-<乱数>/`で、ディレクトリ700・ファイル600、毎回新規作成する。
取得・収録検査・全体読取りの成功とサイズ・SHA-256を記録し、同じ形式・schema・17.11の隔離復元実績は再利用する。
既存の補助スクリプトを使う場合は`backup-result.json`の`backup_verified=true`・`archive_read_check=true`がこの検査の成功を表す。
形式・schema・クライアント変更時は必要な復元検証を行う。
public限定のため、ロール定義・期限等のSQLと診断記録も併せて保持する。
Supabase全体・ロールのパスワード・StorageファイルやMac故障に対する二重化は保護範囲に含まない。
継続的なバックアップの方式と頻度は、許容できるデータ損失と復旧時間を基に別途決める。

費用・容量は09:30・17:15にRailway Usage残高、Supabase ProjectsのDB/Egress、InfrastructureのDiskで確認する。
費用・容量や実行結果の確認を担当できない日は事前に停止する。
課金・容量には集計遅延・丸めがあり、残高にはAPI・Webの消費も含まれる。
通知額・Hard limitは表示未確認のため、費用上限への接近は使用量を確認して手動で停止を判断する。
Trial残り1日以下・運転期限到来でも停止し、期間延長・課金移行・資格情報更新は対象と影響を確認して判断する。
パスワード期限切れやNOLOGINは既存接続を切断しないため、ジョブ停止の代用にしない。

### バックアップの実行と検査

本人Macの対話ターミナルでリポジトリルートから実行する。
入力は確認済み17.11のbinディレクトリ、PressWatchのConnect → Direct connectionのHost、既存の公開CAの絶対パスで、パスは引用符を付けず入力する。
パスワードはpg_dumpが求める非表示プロンプトへ入力する。
接続はpostgres / postgres、5432、verify-fullに固定し、読取り専用でpublicだけを取得する。

```bash
(
set -eu
umask 077
printf '既存PostgreSQL 17.11のbin絶対パス: '; read -r backup_client
printf 'PressWatchのDirect Host: '; read -r backup_host
backup_host_pattern='^db\.[a-z0-9-]+\.supabase\.co$'
if ! [[ "$backup_host" =~ $backup_host_pattern ]]; then
  printf 'Direct Hostの形式が不正です。\n' >&2
  exit 1
fi
printf '公開CAの絶対パス: '; read -r backup_ca
test -x "$backup_client/pg_dump"
test -x "$backup_client/pg_restore"
test -f "$backup_ca"
mkdir -p tmp/supabase-scheduled-fetch
backup_dir=$(mktemp -d "${PWD}/tmp/supabase-scheduled-fetch/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
env -i PATH=/usr/bin:/bin PGHOST="$backup_host" PGPORT=5432 \
  PGDATABASE=postgres PGUSER=postgres PGSSLMODE=verify-full \
  PGSSLROOTCERT="$backup_ca" PGSSLCERTMODE=disable PGGSSENCMODE=disable \
  PGPASSFILE=/dev/null PGSERVICEFILE=/dev/null PGCONNECT_TIMEOUT=5 \
  PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=60000 -c lock_timeout=5000' \
  PGCLIENTENCODING=UTF8 \
  "$backup_client/pg_dump" -Fc --schema=public --strict-names \
  --lock-wait-timeout=5000 -W > "$backup_dir/before-fetch.dump"
test -s "$backup_dir/before-fetch.dump"
env -i PATH=/usr/bin:/bin "$backup_client/pg_restore" --list \
  "$backup_dir/before-fetch.dump" > "$backup_dir/archive-list.txt"
env -i PATH=/usr/bin:/bin "$backup_client/pg_restore" --schema-only --file=- \
  "$backup_dir/before-fetch.dump" > "$backup_dir/archive-schema.sql"
env -i PATH=/usr/bin:/bin "$backup_client/pg_restore" --exit-on-error --file=/dev/null \
  "$backup_dir/before-fetch.dump"
wc -c < "$backup_dir/before-fetch.dump" > "$backup_dir/bytes.txt"
shasum -a 256 "$backup_dir/before-fetch.dump" > "$backup_dir/sha256.txt"
printf '収録検査の対象: %s\n' "$backup_dir"
)
```

終了0に加え、archive-list.txtでpress_releases・fixed_categories・fixed_category_keywords・press_release_fixed_categoriesとalembic_versionのTABLE・TABLE DATA、fixed_categories_id_seqとpress_releases_id_seqのSEQUENCE・SEQUENCE SET、業務4表のACLを確認する。
archive-schema.sqlではpresswatch_fetch_writerへのGRANTが収録されていることを確認する。
全項目を満たした場合だけ取得UTC日時・収録検査と全体読取りの成功を同ディレクトリの実施記録へ残し、bytes.txt・sha256.txtと併せて成功バックアップとする。
途中失敗・収録不足があれば、バックアップを前提とするDB変更へ進む前に解消する。
この例はexportとローカル読取り検査だけを行い、本番復元は行わない。

## 結果・失敗の確認

11:15・17:15 JSTを目安にCron Runs / Deploy Logsで予定枠の起動由来・開始終了・結果を確認する。
設定適用・手動起動と予定時刻の自動起動を区別し、由来不明・記録なしを成功にしない。

| 結果 | 判定 |
| --- | --- |
| completed / 0 | 月別ページ1以上、取得・保存・スキップ件数の整合と終了を確認。正常な新着0件は許容 |
| prepared / database_checked / 0 | 取得していないため取得成功に含めない |
| 3 | 排他競合による見送り |
| 124 | 30分の時間上限 |
| 130 / 143 | SIGINT / SIGTERMによる中断 |
| 1 / 2 | 接続・取得・保存・後片付け等の異常、または引数の誤り |
| 記録なし・前回Active | 欠落・前回残存によるスキップを調査 |

45分後は調査・停止判断の目安であり、Railwayの起動保証ではない。
失敗時は後続を停止し、当該runの配置ID・image digest・時刻とタイムゾーン・理由・件数・巡回URL・停止理由を実施記録へ保存する。
ジョブが正常終了していても、API・Webの不具合、保護設定や対象環境の不一致、DBの休止・read-onlyが判明した場合は後続を停止する。
標準通知は補助とし、メールやスキップ通知の到着を前提にしない。
Trialのログ保持は7日なので、最初の両時刻と異常結果は観測時に保存する。
最初の両時刻の成功後は、照合時点までの全runを把握してDB件数を実行前基準とsaved_count合計に1回照合する。
原本全列ハッシュ・分類定義・API・Web全操作を各runで繰り返さない。

## 停止・再開

1. 実行中の取得を止める必要がある場合は対象runの配置をRemove、ビルド中ならAbortする。
2. Custom Start Commandを次のprepare-onlyへ戻し、Cron Scheduleを削除してまとめて適用する。
   分割する場合はprepare-onlyを先に適用し、実取得コマンドのままCron削除だけをDeployしない。
3. `prepared acquisition=false exit_code=0`を確認し、ローカルIaCもCronを除去してprepare-onlyへ合わせる。
   実環境の停止をDB照合・ログ全体保存・ローカル編集の完了まで待たせない。

```text
/app/.venv/bin/python -m press_watch_api.commands.run_fetch_job --prepare-only --archive-month-limit 6
```

Cron解除だけでは既存プロセスは止まらない。
終了・停止確認と元配置ID記録後にprepare-onlyへ復帰し、元runの保存状態は後から照合する。
commit後の結果出力・接続終了の失敗もあるため、非0終了だけで未保存と判断しない。
DB照合不能なら保存成否を未確定とし、再実行しない。
再開は原因解消・保存状態確定・予算容量と期限内を条件に、再実行範囲を確認して行う。
DB休止時はSupabaseの状態と必要なResume操作を確認し、Railwayの再開だけで復旧すると仮定しない。
本番復元・既存行削除・全件再分類・強制DBセッション切断は本手順の対象外とし、影響と復旧先を決めて別の手順で扱う。

[Railway Cron](https://docs.railway.com/cron-jobs)、[ログ](https://docs.railway.com/observability/logs)、[Supabaseバックアップ](https://supabase.com/docs/guides/platform/backups)、[休止条件](https://supabase.com/docs/guides/platform/free-project-pausing)を参照する。
