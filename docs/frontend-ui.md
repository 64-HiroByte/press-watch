# フロントエンドのUI基盤と一覧UI

## 目的と採用範囲

Phase 6-2では、後続のデザイン検討用Mockに向けてスタイルと基本部品を整える。
画面全体の配置・情報量・カテゴリ選択方式はMockで確認し、検索・絞り込み・ページ移動・URL・APIの仕様は後続タスクで決める。
Neutralと`base-nova`は基盤の初期設定であり、最終デザインを拘束しない。

| 部品 | 基盤で確認する用途 |
| --- | --- |
| Button | 操作部品の基本・枠線・補助・無効状態 |
| Input / Label | 日本語入力、ラベル関連付け、無効状態 |
| Badge | 短い分類表示や長い日本語の表示 |
| Checkbox | 選択・選択済み・無効状態とキーボード操作 |
| Native Select | ネイティブの選択肢と無効状態 |
| Pagination | 現在ページ・前後・省略の表示 |

CheckboxとNative Selectの取り込みは、カテゴリの単一／複数選択方式の確定を意味しない。
確認画面のPaginationには遷移先を設定せず、検索結果・URL・データを変更しない。

## 依存関係と互換性

既存のNode.js 24.21.0、pnpm 12.8.1、Next.js 16.3.8、React / React DOM 19.3.0、TypeScript 7.0.2を維持する。
追加する直接依存は完全なバージョン番号で固定し、間接依存はlockfileで再現する。

| 依存 | 版 | 区分・用途 | ライセンス |
| --- | --- | --- | --- |
| Tailwind CSS / `@tailwindcss/postcss` | 4.3.3 | 開発依存、CSS生成 | MIT |
| PostCSS | 8.5.28 | 開発依存、CSS処理 | MIT |
| shadcn | 4.21.1 | 開発依存、固定CLIと共有CSS | MIT |
| tw-animate-css | 1.4.0 | 開発依存、共有CSS | MIT |
| `@base-ui/react` | 1.8.0 | 実行時依存、基本部品の操作 | MIT |
| class-variance-authority | 0.7.1 | 実行時依存、表示バリエーション | Apache-2.0 |
| cn | 0.4.0 | 実行時依存、クラス名の結合 | MIT |
| lucide-react | 1.50.0 | 実行時依存、アイコン | ISC、一部MIT |
| next-themes | 0.4.6 | 実行時依存、テーマ切替・保存 | MIT |

2026年10月4日に公式マニフェストと取り込むコードを確認した。
TailwindのPostCSS条件と既存の`postcss: ^8.5.28`、Base UI・Lucide・next-themesのReact 19対応条件は整合する。
Lucideは当初候補の1.51.0が新規Docker環境でpnpmの公開後待機条件に拒否されたため、ユーザー承認のもと1.50.0へ変更した。
Lucideは1.50.0を維持し、必要なアイコンの追加、利用箇所に関係する不具合修正、互換性・セキュリティ対応が必要になった時に、差分と動作を確認して更新する。
待機条件の例外は追加せず、`pmOnFail`・`verifyDepsBeforeRun`・既存のビルド許可設定を維持する。
Base UIのoptional peerである日付関連ライブラリは、この7部品には不要なので追加しない。
TailwindのOxideとLightning CSSはネイティブ依存を持つため、OS・CPUに対応するoptional dependenciesを省略しない。

Kibo UIは導入を保留する。
ComboboxはRadix系の操作部品、TableはTanStack Table・Jotaiなどの追加依存を伴い、Choiceboxは選択操作の設計に関わる。
今回の基本部品では具体的な不足がなく、追加依存と保守対象を増やす必要がない。
Phase 6-3のMockで標準部品だけでは足りない複合UIが必要になった時に、対象部品の現行実装・互換性・ライセンスを再評価する。

## 配置・テーマ・Server／Client境界

- 部品は`apps/web/components/ui/`、ユーティリティは`apps/web/lib/`へ配置する。
  `components.json`は`base-nova`、Neutral、CSS変数、Lucide、`rsc: true`、`tsx: true`とする。
- `@/*`はWebルートに対応させ、TypeScript 7で不要な`baseUrl`は追加しない。
  Tailwind 4では空の`tailwind.config`とPostCSSプラグインを使い、旧版用のTailwind設定ファイルは追加しない。
- CSSはTailwind・tw-animate-css・shadcn/tailwind.cssと公式Neutralトークンを使う。
  既存案内画面の見出し・段落スタイルは`.intro`に限定し、部品へ波及させない。
- ルートlayoutと確認ページはServer Componentとし、ThemeProvider・テーマ選択など必要な部分をClient Componentにする。
  取り込み元のClient指定は維持し、全画面をClient化しない。
- テーマはライト・ダーク・システム追従を用意する。
  初期値はシステム追従で、next-themesの標準localStorage保存を使う。
  Providerは`attribute="class"`・`defaultTheme="system"`・`enableSystem`・`disableTransitionOnChange`を設定する。
  `suppressHydrationWarning`は`html`だけに設定し、マウント待ちはテーマ選択部品だけに限定する。

`/ui-foundation`は7部品の静的な日本語見本を置く開発専用ページである。
development以外ではServerページの先頭で`notFound()`を呼び、productionでは404を返す。
UI部品とテーマ自体の操作を確認するページであり、完成Mockや製品機能の実装ではない。

## 一覧UIの採用方針

Phase 6-3で合意した一覧UIの表示方針を、本実装への引き継ぎとして残す。
検索・絞り込み・URL・APIの製品仕様はPhase 6-4で確定する。

- 検索条件を左のサイドバー、報道発表一覧を右に配置する。
  サイドバーはキーワード、公開日の開始日・終了日、検索ボタン、カテゴリの順とし、カテゴリの前に余白と仕切り線を置く。
  検索ボタンの下に入力欄と適用済みのキーワード・公開日を解除する枠線付きのリセットボタンを置き、カテゴリ見出しの右にピル型の全選択・全解除ボタンを置く。
- PCではサイドバーと一覧ヘッダーを画面内に残し、右側をスクロールする。
  ヘッダーの背面には一覧を薄くぼかして透かす。
  狭い画面ではサイドバーを検索条件ドロワーへ切り替える。
- ヘッダーには一覧見出し、検索条件の有無と折りたためる詳細、件数・並び順をまとめる。
  狭い画面の条件変更ボタンからドロワーを開く。
- 一覧では公開日を左、全文のタイトルと所属カテゴリを右に置く。
  カテゴリはタイトルの近くに塗りつぶしのバッジで表示し、所属がなければ「カテゴリなし」とする。
  選択用カテゴリはチェック印のないピル型ボタンとする。
- ライトは白味を抑えた温かみのあるグレー、ダークは黒に近いグレーを使う。
  グラデーションや装飾的なカードを使わず、罫線と整列で情報を整理する。
- 右上には大小の「あ」による文字サイズ切り替えと、太陽・月によるライト／ダーク切り替えを置く。
  操作部品は一覧見出しより控えめにし、ホバー・フォーカス時の補助説明を共用する。
- 取得失敗・データなし・検索結果なしは案内文を主体とし、薄い単色の線画を背景装飾として添える。

再利用する一覧・状態表示の部品は`apps/web/components/press-releases/`、固定サンプルは`apps/web/mock/`、Mock専用の操作は`apps/web/components/mock/`に分ける。
一覧と入力欄はServer Componentを維持し、表示状態・検索条件の表示・テーマ・文字サイズ・ドロワーの操作だけをClient側で扱う。
細かな配色・寸法は`apps/web/app/mock/mock.css`を参照し、文書で二重管理しない。
Mockの閲覧と確認方法は[開発手順](local-development.md#一覧mockの確認)を参照する。

## 取得・更新手順と独自変更

CLIはWebの開発依存として固定したshadcn 4.21.1を使用する。
秘密ファイル・既存の`node_modules`・`.next`・`tsbuildinfo`を除いた一時Webコピーでだけ実行し、毎回そのコピーを`--cwd`に明示する。
実行前に秘密ファイルが存在しないことをファイル名だけで確認する。
shadcn addはdry-runでもcwd直下の`.env`等を読み込むため、dry-runを秘密ファイル非読取の保証に使わない。

1. 承認版の依存、パス別名、部品設定を一時コピーへ宣言・導入する。
2. 対象7部品・style index・utilsの公式JSONを一度取得し、依存と全ファイル内容を監査する。
3. `registryDependencies`を監査済みローカルJSONの絶対パスへ置き換え、参照先を含めて同じ内容を使う。
4. 固定CLIの`add --dry-run --cwd <一時Webコピー>`で生成先と変更範囲を確認する。
5. 同じローカルJSONから取り込み、生成コード・マニフェスト・lockfile・CSSの差分を監査する。
6. 必要な変更だけをリポジトリへ反映し、取り込むコードの更新時も同じ手順で出典と独自変更を追記する。

取り込み時のCLI変換で、アイコンのplaceholderをLucideへ、部品間のimportをWeb内のパス別名へ置き換えた。
独自変更はPaginationの標準文言・aria-label・省略の補助文言の日本語化である。
ThemeProvider、テーマ選択、確認画面、案内画面に限定したCSSはPressWatch側の追加実装である。

## 利用条件と表示

採用部品は無料で利用できる公開OSSで、有料サービスの契約を前提にしない。
コピーしたshadcn/uiコード・テーマと依存の著作権表示、ライセンス本文、同梱NOTICE等は[第三者表示](../apps/web/public/third-party-notices.txt)へ保存する。
Webでは`/third-party-notices.txt`から参照できる。
パッケージに本文がない`@next/env`と`client-only`には、同じ上流プロジェクトのライセンス本文を使用した旨を表示する。
開発依存のCLI全体と、実際にWebへ含めるコード・生成CSS・実行時依存は区別する。
Lightning CSS 1.32.0はMPL-2.0のビルド用ライブラリで、生成CSSにそのネイティブライブラリのコードを埋め込まない。
ライブラリ自体を再配布する場合は、同版の[ソース](https://github.com/parcel-bundler/lightningcss/tree/v1.32.0)とMPLの配布条件も確認する。

## 検証方針

導入前後のローカルとWeb単体Dockerを、秘密ファイル・既存依存・生成物を含まない別の一時環境で比較する。
手順はfrozen install、型生成、型チェック、本番ビルド、同じブラウザ・画面サイズでの表示確認とする。
導入後はfrozen installを再実行し、lockfileが変わらないことも確認する。
表示・操作の確認項目とコマンドは[開発手順](local-development.md#ui基盤の確認)を参照する。
UIのテスト基盤はPhase 6-5で整備するため、今回は合意した表示・操作・実行経路の実確認を行い、TDDや自動回帰テストで検証したとは説明しない。

productionの部品描画は、確認ページのガードだけを外した一時検証コピーでbuild/startして確認する。
この検証用変更を納品ソースへ取り込まず、通常ソースのproductionで404になることも別に確認する。
検証した環境・制限は完了記録へ残す。

## Phase 6-2の確認実績

2026年10月4日に、macOS 26.1（arm64）とDockerのDebian 12（Linux arm64）で確認した。
どちらも秘密ファイル・既存依存・生成物を除いた一時環境から依存を再現した。
Node.js 24.21.0、pnpm 12.8.1、TypeScript 7.0.2を使用し、Dockerの既存Corepack経路を維持した。

| 確認 | 結果 |
| --- | --- |
| 導入前後のfrozen install・Next型生成・型チェック・production build | ローカル・Dockerとも成功 |
| 導入後の再インストール | lockfileのSHA-256が不変、既存依存の版を維持 |
| 既存案内画面の比較 | 同じブラウザ・1280×720のCSS viewportで文言・見出しの位置と太さを維持、色をテーマ対応へ変更 |
| 開発画面の7部品 | 日本語表示・入力・ラベル連動・Tabフォーカス・CheckboxのSpace操作・無効状態・Native Selectを確認 |
| テーマ | ライト・ダーク・再読込後の保持、システム選択と現在のOS設定との一致を確認 |
| Pagination | 2ページ目を選択してもURL・現在ページが不変 |
| 一時コピーのproduction表示 | ローカル・Dockerとも7部品・テーマを描画し、hydrationエラーなし |
| 通常ソースのproduction | ローカル・Dockerとも`/ui-foundation`が404 |
| ライセンス・差分 | 第三者表示、出典と独自変更、Markdown参照先、`git diff --check`と全差分を確認 |

Badgeは取り込み元のClient指定を追加せず、Serverページから開発・productionで描画できることを確認した。
Dockerの開発リソースは`127.0.0.1`からのoriginを拒否したため、ホスト側のループバック公開を維持して`localhost`で操作を確認した。
origin設定や依存の公開後待機条件を緩めていない。

ブラウザはCodex In-app Browserを使用した。
ブラウザエンジンの版は取得できておらず、他のブラウザ、Windows、Linux amd64、スマートフォンの表示は未確認である。
OSの外観設定そのものは変更していないため、表示中にOS設定を切り替えた際の追従と、実際のスクリーンリーダー読み上げは未確認である。
今回の検証はアクセシビリティツリー上の名称・関連付けと実操作までであり、アクセシビリティ全般の適合を保証しない。
UIの自動テスト・lint基盤は追加しておらず、CIで実行したとは扱わない。
これらは今回の部品基盤の完成条件を超える確認として、対象画面を作る後続タスクで扱う。

## 公式情報と取得記録

- [Tailwind CSSのNext.js手順](https://tailwindcss.com/docs/installation/framework-guides/nextjs)
- [shadcn/uiの標準構成](https://ui.shadcn.com/docs/installation/manual)、[テーマ](https://ui.shadcn.com/docs/theming)、[CLI](https://ui.shadcn.com/docs/cli)
- [next-themes](https://github.com/pacocoursey/next-themes)、[shadcn/uiのNext.jsテーマ設定](https://ui.shadcn.com/docs/dark-mode/next)
- [Kibo UI](https://www.kibo-ui.com/docs)、[公開ソース](https://github.com/shadcnblocks/kibo)

以下は2026年10月4日（日本時間）に取得した元のJSONのSHA-256であり、CLI用に参照パスを置き換えた後のJSONや生成TSXのハッシュではない。
取り込み後のコードと独自変更はGit差分・履歴で追跡する。

| 取得元JSON | SHA-256 |
| --- | --- |
| [index](https://ui.shadcn.com/r/styles/base-nova/index.json) | `152d703b8094fb5036c34a417be84c8b012c5bff922eb2a3a948070859f89cfa` |
| [utils](https://ui.shadcn.com/r/styles/base-nova/utils.json) | `74f5bc88a74dfc19f7cbfaa0c152a5e9b9d3a62823b32b48677652968b442593` |
| [button](https://ui.shadcn.com/r/styles/base-nova/button.json) | `9ba7e870178813f0552b818a913a2792fb500c779e36395740b4973e3025d427` |
| [input](https://ui.shadcn.com/r/styles/base-nova/input.json) | `bbad1bba130ac9750a61844eeb8f043e8a710846e07689fa85398b80a46c2741` |
| [label](https://ui.shadcn.com/r/styles/base-nova/label.json) | `89b01e14fd39dceece9fa421e71e78ea83286bd43a2ca1c2f55d2e8d3958fff2` |
| [badge](https://ui.shadcn.com/r/styles/base-nova/badge.json) | `ccc20021cdcbf0fb23c0d4d28f1da4adde8e51ba59f4b11dd2722ed97a5ee3a4` |
| [checkbox](https://ui.shadcn.com/r/styles/base-nova/checkbox.json) | `e6df7b595f25a7ee97c3fb94e0ddc35998f74c98b990d3030e485905ec677178` |
| [native-select](https://ui.shadcn.com/r/styles/base-nova/native-select.json) | `743d128b09f67c1921e3c302e778834639e5be92c454205cabfb61eed34b4ff1` |
| [pagination](https://ui.shadcn.com/r/styles/base-nova/pagination.json) | `d2c45af4aaf4a676f420c673f337e8ba89dc7db75bf9fa11143f8a947f3a7f42` |
| [neutral](https://ui.shadcn.com/r/colors/neutral.json) | `58f847c9413f0c0e326f4796702a40c31a6d115e2b73b07edc288e7ef949af7f` |
