# PressWatch - デプロイ構成と運用計画

## 記録の位置付け

2026年11月1日の調査と、11月6日までに合意した本人向けの限定配置方針を記録する。
契約・適用前には料金・制限・セキュリティ情報を再確認する。
Railwayでの設定・配置とSupabaseへの適用は未実施である。

| 区分 | 内容 |
| --- | --- |
| 合意済みの計画条件 | 初期のFastAPIは内部用とし、外部プログラム向けの入口は必要になった時点で検討する |
| 合意済みの計画条件 | Railwayの請求期間内の対象利用量が$10に達したら停止し、翌請求期間の自動再開を許容する |
| ユーザーの希望 | 通常の差分取得は1日2回を希望。正確な時刻は未確定 |
| 決定した配置先 | 初回のNext.jsとFastAPIはRailwayに配置し、DBは採用済みのSupabase PostgreSQLを使う |
| 取得ジョブの配置案 | Railwayへの配置を候補とし、後続タスクで配置と手動検証を行う |
| 選定で重視すること | 管理先の少なさ、既存Python実装の活用、想定外の高額請求を抑えること |
| 将来の希望 | Supabase Authによるユーザー登録とユーザー別ブックマーク。MVP後の別タスクとする |

有料契約、クラウド設定・配置、Supabase接続・適用、依存更新は、対象と影響を示して段階ごとに承認を得る。

## 限定配置の構成

| 配置先 | 責務と接続 |
| --- | --- |
| Railway Web | Next.jsで画面を提供する。外部公開の入口とし、FastAPIを内部ネットワークで呼ぶ |
| Railway API | FastAPIで入力検証・検索・DB読取りを行う。公開ドメインを設けない計画 |
| Railway取得ジョブ | 既存Pythonコマンドで環境省から差分を取得し、分類・保存する。実行時だけ起動する案 |
| Supabase | 記事・固定カテゴリ・分類結果をPostgreSQLで保持する。WebへDB資格情報を渡さない |

Web・APIは各1レプリカで継続稼働する案を費用試算の起点とする。
Railway内の同じ環境に置いたサービス間は、公開インターネットを経由せず通信できる。
この内部通信を使い、APIへの直接の外部アクセスとサービス間の外向き通信料金を減らす。
[Railway Private Networking](https://docs.railway.com/networking/private-networking)、[費用管理](https://docs.railway.com/pricing/cost-control)を参照する。

Next.jsサーバーからAPIを呼ぶ現在の構成を維持できるため、初期公開にブラウザからFastAPIへ直接接続する入口は必要ない。
本人向けの限定配置ではWebをBasic認証で保護し、過剰要求対策は一般公開前に実施する。
将来Authを使う場合は、認証情報の検証とブックマークの所有者確認を設計する。
内部ネットワークやDB接続資格情報だけで、利用者ごとの認可が完了するとは扱わない。

### 比較した候補と判断理由

- VercelのWeb・APIとGitHub Actionsの取得ジョブは、各無料枠内なら低コストにできる。
  Vercel Hobbyは個人・非商用利用に限られるため、無料枠と用途条件の両方を満たす必要がある。
  ただし、DB接続管理の調整と、定期実行の遅延・欠落、公開リポジトリで60日間活動がない場合の自動停止を考慮する必要がある。
  管理先をまとめ、既存のPython APIを活用するため、Web・APIの配置先にはRailwayを選んだ。
  [Vercel Hobby](https://vercel.com/docs/plans/hobby)、[GitHub Actionsの定期実行](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)を参照する。
- Render Freeは15分の無通信で休止し、再起動に約1分かかる。
  現行WebのAPI通信期限10秒とは相性が悪いため、選定から外した。
  [Render Freeの制限](https://render.com/docs/free)を参照する。

## 費用の見込みと停止条件

### 算定条件

通常のコンテナサービスの料金を使い、RailwayのSandboxes・VMやAgentの料金とは分ける。
Hobbyは月$5の最低料金に$5分の利用料を含む。
対象利用料が$3なら月$5、$7なら月$7であり、$5へ利用料全額を加算する計算ではない。

| 対象 | 調査時点の単価 |
| --- | --- |
| メモリ | 月平均1GBを継続使用すると約$10 |
| CPU | 月平均1 vCPU相当を継続使用すると約$20 |
| 外向き通信 | $0.05/GB |
| サービスのビルド | CPU・メモリ等のビルド料金なし |

単価と含まれる利用料は[Railway Pricing Plans](https://docs.railway.com/pricing/plans)を参照する。
以下は30日間、Web・API各1レプリカ、永続ディスクなしの概算であり、税・為替・カード手数料・Supabase料金は含めない。

| 仮定したWeb・APIの月平均 | 通信量/月 | 取得ジョブを含む利用料 | 最低料金を反映した月額・停止の扱い |
| --- | --- | --- | --- |
| メモリ0.3GB、CPU 0.02 vCPU相当 | 1GB | 約$3.52 | $5 |
| メモリ0.5GB、CPU 0.05 vCPU相当 | 5GB | 約$6.32 | 約$6.32 |
| メモリ1GB、CPU 0.2 vCPU相当 | 20GB | 約$15.07 | 上限なしの計算。$10停止案では月途中に停止する想定 |

取得ジョブは、1回5分、メモリ0.5GB、CPU 0.25 vCPU相当、月60回と仮定した約$0.07を各行へ加えた。
実測ではなく、ジョブの外向き通信は表の通信量に含まれる前提である。
月$5〜7程度のケースを予算検討に使えるが、この範囲に収まることを保証しない。
承認後の限定配置で約1週間の使用量を確認し、[Railway公式の見積もり方法](https://docs.railway.com/pricing/faqs)に従って見直す。

### ローカルメモリ測定の参考値

次はユーザーが別チャットで実施を承認した測定の報告であり、この文書を記録したチャットで再実行・独立検証した値ではない。
隔離した一時コピーを本番モードで使い、元のソース・依存・既存ビルドは変更していないとの報告である。

| 測定時点 | WebとAPIの合計 |
| --- | --- |
| 起動後の待機 | 約195MiB |
| 合成記事50件の画面を50回生成後 | 約301MiB |
| 合計75回生成し、少し待った後 | 約275MiB |

APIはDB未接続で、待機とヘルスチェックのみである。
スクレイピング、実DB検索、Linuxでの使用量、CPU・通信料金は未測定である。
測定プロセスは停止済み、一時ファイルも削除済みとの報告であり、元の測定成果物を再検査することはできない。
各時点の値を月平均やRailwayの課金対象メモリへ直接置き換えず、依存更新後のLinux測定と実環境のメトリクスで費用判断を更新する。

### 限定配置の費用設定

合意済みなのは利用量$10で停止する計画基準であり、以下の設定を実施したわけではない。

- Hobbyを基準とし、Compute UsageのHard limitを請求期間ごとに$10、追加メール通知を$5に設定する。
  停止はワークスペース全体に及ぶため、対象と他のサービスへの影響を設定前に確認する。
- Web・APIは各1レプリカ、APIは1 workerとする。
  CPU上限は各1 vCPU、メモリ上限はWeb 512MiB・API 256MiBを暫定値とし、Linuxで不足すれば配置を保留して見直す。
  初回はServerlessを無効にし、再起動ポリシーをNeverに設定する。
  自動増台、PR環境、永続ディスク、追加サービスは作らない。
- Railway Agentは使わない案とし、Compute UsageとAgent Usageの上限は別であることを確認する。
- 翌請求期間の自動再開を許容する。
  手動の上限引上げ・解除・期間途中の再開は別承認とする。
  上限到達から停止までの精度、対象外料金、再開条件は契約・設定前に確認する。

Railway公式ではHard limitの最小額は$10であり、$5で自動停止する設定ではない。
Hard limitはワークスペースの対象利用量に対する制御で、Supabaseや税・為替手数料を含む請求総額の保証ではない。
停止は解約ではなく、契約中の最低料金がなくなるとは扱わない。
[費用上限の仕様](https://docs.railway.com/pricing/cost-control)、[最小額の公式案内](https://railway.com/guides/right-size-cpu-memory)を参照する。

Supabaseは契約プラン・DB容量・通信量を別に確認する。
FreeならDB容量500MB・外向き通信5GB等の枠があり、Free利用中は料金が請求されないが、今回の契約状態や枠内に収まることは未確認である。
有料化する場合は、Spend CapにCompute等の対象外項目があることも含めて別途判断する。
[Supabase料金](https://supabase.com/pricing)、[Supabase費用管理](https://supabase.com/docs/guides/platform/cost-control)を参照する。

Freeでは7日間のDB活動が少ない場合にプロジェクトが休止対象になるため、Railwayの費用上限による停止が長引いた場合は、DBも休止する可能性がある。
Railwayの再開だけで復旧すると仮定せず、Supabaseの状態確認・必要な再開操作・DB接続確認を復旧手順に含める。
Freeの定期的なデータ書き出しと外部保管は公式の推奨であり、適用前のバックアップとは別に、運用中の取得頻度・保管先・復元確認と費用を後続で決める。
休止への対応・バックアップ方式・有料化は未確定であり、[Supabaseの休止条件](https://supabase.com/docs/guides/platform/free-project-pausing)と[バックアップの案内](https://supabase.com/docs/guides/platform/backups)を基に、運用開始前に判断する。

## 公開時の保護とSupabase接続

### 本人向け限定配置の閲覧制限

閲覧者は本人とし、HTTPSのWeb入口で検証用Basic認証を使う。
本番モードではページ・RSC・prefetch・静的ファイルを保護し、設定不足は503、未認証・不正な資格情報はチャレンジ付き401で拒否する。
保護する応答には`private, no-store`を指定し、拒否時はAPIを呼ばない。
`/health`は認証設定が有効なときに固定の生存応答を返し、DBの接続確認は一覧とカテゴリ取得で行う。

### 一般公開前の過剰要求対策

次の値は一般公開前に評価する案である。

| 対象 | 初期案と検証条件 |
| --- | --- |
| Webの動的な画面要求 | 接続元ごとに毎分60回。接続元の偽装、通常の画面操作、静的ファイルとの区別を確認する |
| APIの検索・一覧要求 | 全体で毎分120回。超過時はHTTP 429とし、DB照会へ進めないことを確認する |
| 配置と実行単位 | 各1レプリカを起点に、worker数・制限の共有範囲・再起動時の扱いを設計する |

Railwayの基盤上限を、そのままPressWatchのリクエスト数制限とは扱わない。
アプリケーション側の制限を起点に設計し、攻撃時の追加手段としてRailwayのUnder Attack Modeも確認する。
Under Attack Modeは非ブラウザ通信を拒否するため、サーバー間通信へ無条件に適用しない。
[公開ネットワークの仕様](https://docs.railway.com/networking/public-networking/specs-and-limits)、[Railway WAF](https://docs.railway.com/networking/waf)を参照する。
内部API化は[要件NFR-006](requirements.md#nfr-006-公開apiへの過剰なリクエストを抑制できること)の過剰要求対策を省く理由にせず、既存APIの入力上限・検索・応答契約を維持する。

### 限定配置のDB接続

- APIは外向きIPv6を有効にし、SupabaseのDirect connectionを`sslmode=verify-full`で利用する。
  Supabaseから取得したCAをAPIの`PRESSWATCH_DB_CA_CERT`へ設定する。
  APIは起動時に所有者のみ読書きできる一時ファイルを作成し、`PGSSLROOTCERT`に指定する。
  診断・バックアップ・Alembicには管理手順でCAを明示し、検証に失敗した場合は接続を中止する。
- API専用ロールは対象DBの`CONNECT`、`public` schemaの`USAGE`、`press_releases`・`fixed_categories`・`press_release_fixed_categories`の`SELECT`だけを付与し、接続上限を4にする。
  所有・管理・書込み権限を持たないことを、既存ロール所属と`PUBLIC`由来の権限を含めて確認する。
  migration・seedには別の管理接続を使う。
- APIの接続URLは`connect_timeout=5`、専用ロールは`statement_timeout='5s'`とする。
  APIの共有プールは最大2接続・追加接続なし・空き待ち5秒とする。
  それぞれ別の期限であり、Webの10秒以内に要求全体が完了する保証はない。
- 記事0件と想定したrevision・権限を確認してから、既存migrationとカテゴリseedだけを適用する。
  Data API・RLS・既存権限の現況を確認し、追加の変更が必要な場合は作業を保留して別途判断する。

[Railwayの外向きIPv6](https://docs.railway.com/networking/outbound-networking#outbound-ipv6)、[Supabaseの接続・SSL設定](https://supabase.com/docs/guides/database/connecting-to-postgres)を参照する。
過去のSupabase診断値を現況と断定せず、[Supabaseへ進む条件](local-development.md#supabaseへ進む条件)に従って準備と適用を別承認にする。
ローカルの実データ確認をSupabase適用済みの根拠にしない。

将来のAuthでは、FastAPIでSupabaseの認証情報を検証し、確認したユーザーIDに基づいてブックマークを扱う設計を検討する。
DB所有者等はRLSを回避できるため、RLSを有効にするだけで所有者確認が済むとは扱わない。
[Supabase JWTの検証](https://supabase.com/docs/guides/auth/jwts)を参照し、Auth・ブックマークの実装やData APIの有効化は今回行わない。

## Railwayでの限定配置手順

1. 本人がRailwayへ登録する。
   プラン・支払い条件・停止対象を確認し、別承認後に費用上限・通知・サービス上限を設定する。
2. Supabaseの読取り診断・バックアップを準備し、報告後の別承認で書込みを行う。
   書込み停止と直前のバックアップ検査を経て`a51eab6808f3`まで適用し、既存カテゴリseedを実行する。
   想定と異なるrevision・権限・記事件数の場合は中止する。
3. 準備変更と承認済みのセキュリティ更新を`phase-7/operations`へ統合し、CIと本番イメージの検証を通過したSHAを記録する。
   GitHub連携では両サービスを`phase-7/operations`へ接続し、初回配置を保留して自動配置を無効にする。
   手動配置の直前と直後に配置元SHAを照合し、不一致なら公開へ進まない。
4. 次の設定でWeb・APIを同じRailway環境へ配置する。
   build contextはリポジトリルートとし、各Dockerfileの最終`production`ステージと既存の起動コマンドを使う。
5. Webに公開ドメインを付ける前に、内部疎通・拒否応答・DBの証明書検証・記事0件の一覧とカテゴリ表示を確認する。
   セキュリティ更新・再ビルド・回帰確認が完了した後、WebだけにHTTPSドメインを付け、非許可者の拒否とAPIへの公開経路がないことを再確認する。
   本人の画面操作と約1週間の利用量を確認する。

| サービス | 配置用の設定 | アプリ用の実行時設定 |
| --- | --- | --- |
| Web | `RAILWAY_DOCKERFILE_PATH=infra/docker/web.Dockerfile` | `PRESSWATCH_API_BASE_URL`に内部APIのHTTP URL（例 `http://api.railway.internal:8000`）、`PRESSWATCH_BASIC_AUTH_USER`と`PRESSWATCH_BASIC_AUTH_PASSWORD` |
| API | `RAILWAY_DOCKERFILE_PATH=infra/docker/python.Dockerfile`、`PORT=8000`、`HOST=::`、外向きIPv6有効、公開ドメイン・TCP Proxyなし | 読取り専用ロールの`DATABASE_URL`、`PRESSWATCH_DB_CA_CERT` |

Basic認証のパスワードは十分に長いランダム値とし、DB資格情報とともに設定先のサービスだけへ渡す。
Basic認証のユーザー名にはコロンを含めない。
値をビルド・ログ・クライアントコード・テスト成果物に含めない。
[Dockerfileの指定](https://docs.railway.com/builds/dockerfiles)と[GitHubの配置設定](https://docs.railway.com/deployments/github-autodeploys)を参照する。

認証迂回や情報露出時はWebの公開ドメインを外して配置を停止し、保護が確認できるまで公開を再開しない。
DB障害時は追加の書込みを止め、現況・バックアップ・ロールと権限の記録から復旧方法を決めて別承認を得る。
全体復元やdowngradeを自動実行しない。

## 定期取得と失敗確認

1日2回という希望を前提にRailway Cronを検討する。
10:30・17:30等は比較に使った例であり、実行時刻の決定ではない。
環境省が10時に更新するという仮説も未確認である。
設定前に日本時間の時刻を確定し、UTCへ変換する。
Railwayは分単位の厳密な開始時刻を保証しないため、許容する遅延と確認手順も決める。
[Railway Cron](https://docs.railway.com/cron-jobs)を参照する。

実行入口は、既存の`press_watch_api.commands.fetch_and_save_env_press`を使う案である。
通常の差分取得は`--archive-month-limit 6`、既知URLの範囲は既定の直近3か月を起点に、巡回上限到達時の確認とともに確定する。
空DBへの初回全件取得やメンテナンス用フルスキャンを定期ジョブに含めない。
コマンドとstdout・stderr・終了コードは[開発手順](local-development.md#手動で取得してdbへ保存する)を参照する。

Python Dockerfileは開発API・本番API・取得ジョブをターゲットで分け、APIの依存と本番共通部分を再利用する。
既存コマンドはscraper子プロセスを起動するため、APIとscraperの両方の依存・ソース、分類CSV、リポジトリ相対配置を満たす環境をビルド時に用意する。
実行時の依存取得に頼らず、一時ファイルとstdout・stderrを使う案とし、永続ディスクの必要性は未確認のまま追加しない。

実HTTP取得前に、そのoriginのrobots.txtを確認する。
robots.txtも通常要求・redirect先と同じrate limiterを通し、同一実行中は解析結果を再利用して、各取得対象URLの禁止を確認する。
禁止・取得失敗・解析不能時は報道発表ページへ進まず、CLIのstderrと終了コード1で失敗を確認できる。
初期対応は単一の`User-agent: *`グループと通常の`Disallow`によるパス前方一致に限り、`Allow`・複数グループ・ワイルドカード・終端記号などの未対応形式は確認不能として停止する。
応答条件と保存済みHTMLの扱いは[開発手順](local-development.md#scraper-を単体で起動する)を参照する。

実行上限10分、自動再試行なしを初期案とし、実測後に値を確定する。
Railwayは前回実行が残っていると次回をスキップし、自動では終了させない。
ジョブの再起動方針を明示し、手動実行も含めた重複防止、親子プロセスの終了、DB保存前後の失敗を検証する。
失敗でもcommit済みの場合があるため、終了コードだけで未保存とは判断せず、診断を確認してから再実行する。
[Railway再起動方針](https://docs.railway.com/deployments/restart-policy)を参照する。

独自の実行履歴DBや長期ログ保存は追加せず、既存の終了コード・stdout・stderrとRailwayの実行結果を使う。
Hobbyのログ保持は7日である。
運用者が各日の実行結果を確認する案を起点に、失敗・時間切れ・次回スキップ・予定実行の欠落を確認する手順を決める。
ジョブ失敗通知が必ず届くとは仮定せず、標準通知を使う場合は適用範囲と到達を検証する。
[Railwayログ](https://docs.railway.com/observability/logs)を参照する。

## セキュリティ更新と後続タスク

2026年11月1日に、設定・lockfileと公式資料を照合した主要Web実行系は次のとおりである。
依存全体の監査や、ローカルにインストールされた全実行ファイルの版確認は未実施である。

| 対象 | 現行の固定・解決版 | 更新候補と位置付け |
| --- | --- | --- |
| Node.js | 24.22.2 | PR #129で更新・ローカル・Docker・実CIの確認を完了 |
| Next.js | 16.4.1 | 11月のセキュリティ修正版16.4.5を別タスクの更新候補とする |
| React / React DOM | 19.3.1 | 確認時点の最新安定版。維持する案 |

[Node.jsのセキュリティ告知](https://nodejs.org/en/blog/vulnerability/october-2026-security-releases)、[Node.js 24.22.2](https://nodejs.org/en/blog/release/v24.22.2)、[Next.jsの10月のセキュリティ告知](https://nextjs.org/blog/nextjs-security-update-october-14-2026)、[React 19.3.1](https://github.com/react/react/releases/tag/v19.3.1)を参照する。
Node.jsは承認済みのPhase 7更新で、Volta・Web Dockerfile・Web CIの指定を24.22.2へ揃えた。
検証結果と未確認範囲は[Node.js更新の検証記録](local-development.md#phase-7のnodejsセキュリティ更新)を参照する。
Next.js・Reactの更新は今回に含めず、lockfileも維持する。

[Next.js 16.4.5の公式リリース](https://github.com/vercel/next.js/releases/tag/v16.4.5)で11月のセキュリティ修正を確認した。
別タスクで影響・採用版・検証範囲を確認し、対象パッケージのnpm公開から24時間経過後に承認された更新を行う。
Webを外部から利用可能にする前に、更新後の本番イメージを再ビルドし、回帰検証を完了する。

後続タスクは、次の責務・依存関係で分けて提案する。
個々の実装・環境利用・外部操作は、対象と影響を示して別途承認を得る。

| 順序 | 対象 | 完了条件と承認境界 |
| --- | --- | --- |
| 1 | デプロイ準備 | 費用・停止方針、本人向け閲覧制限、DB接続とスキーマの条件を整え、合成データで検証する |
| 2 | Web・APIの限定配置 | 契約・設定、DB準備と適用、配置を段階ごとに承認する。更新済みのWebから内部APIとSupabaseへ接続し、記事0件とカテゴリ表示、非許可者の拒否、約1週間の使用量を確認する |
| 3 | Supabaseへの実データ適用 | 限定配置後のrevision・カテゴリ定義・権限・記事集合・連番を確認し、その状態に合わせて適用・検証・復旧手順を計画する。バックアップ後の別承認で適用する |
| 4 | 取得ジョブの配置と手動検証 | 取得・保存・終了を確認し、実行上限・再試行・重複防止を整える |
| 5 | 定期実行 | 時刻を確定し、別承認後に自動起動・差分保存・失敗と欠落の確認を検証する |
| 6 | 一般公開 | 過剰要求対策、最新のセキュリティ情報、実測費用と復旧手順を確認し、別承認後に公開する |

進捗は[Phase 7のタスク](tasks.md#phase-7-定期実行と運用準備)で管理する。
構成・方式の最終決定と、実装・設定・実運用の完了を区別する。

本番用イメージの構成と合成データ検証の手順は[本番用Docker](production-docker.md)を参照する。
