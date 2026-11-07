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

後続作業は、限定配置の利用量評価、Supabaseへの実データ適用、取得ジョブの配置と手動検証、定期実行、一般公開の順で条件を確認する。
一般公開前には過剰要求対策、最新のセキュリティ情報、実測費用、DBの復旧とバックアップ方針を再確認する。
