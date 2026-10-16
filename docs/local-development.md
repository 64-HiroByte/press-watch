# Local Development

PressWatch をローカル環境で起動・確認するための手順です。

特に明記がないコマンドは、リポジトリルートで実行します。

## 前提ツール

次のツールが使えることを確認します。

```bash
volta --version
uv --version
docker compose version
```

## Web用のNode.jsとpnpm

WebはNode.js 24.21.0とpnpm 12.8.1を使用します。
ルートの`package.json`が両者の版数を指定し、`apps/web/package.json`の`volta.extends`がNode.jsの指定を継承します。
ローカルのNode.jsは既存のVoltaで選択し、pnpmはグローバルに導入した指定版を使用します。
プロジェクト専用のmise設定、Corepackのshim・キャッシュ、セットアップ補助は使用しません。

### 初回準備と版確認

[Voltaの導入手順](https://docs.volta.sh/guide/getting-started)に従い、`node`がVolta経由で実行される状態にします。
プロジェクト内では`volta.node`の指定が優先され、必要なNode.jsが取得されます。
このPCの既定Node.jsも、[volta install](https://docs.volta.sh/reference/install)で24.21.0へ更新済みです。

pnpmは[公式の導入手順](https://pnpm.io/installation)に従い、12.8.1を用意します。
既存のpnpmを更新する場合は、PressWatchなどpnpmを固定したプロジェクトの外で、[self-update](https://pnpm.io/cli/self-update)を実行します。
プロジェクト内の`self-update`はグローバル更新ではなく`package.json`の指定を書き換えるため、実行場所を分けます。

```bash
pnpm self-update 12.8.1
```

複数のpnpmがインストールされている場合は、更新したものが通常の`pnpm`で選ばれていることも確認します。
このPCはHomebrew版と`PNPM_HOME`側を両方12.8.1へ揃え、CursorではHomebrew版を選ぶことを確認しています。
`self-update`で更新する`PNPM_HOME`側と、Homebrew等が管理するインストールは別であり、一方の更新だけで全ての導入済みpnpmが更新されるわけではありません。

新しいCursorターミナルを作成し、ルートと`apps/web`で次を確認します。

```bash
command -v node
node -v
command -v pnpm
pnpm -v
```

Node.jsは24.21.0、pnpmは12.8.1と表示される必要があります。
この構成ではpnpmの版をプロジェクトごとに自動切り替えしないため、`packageManager`の指定を更新した際は、実際に選ばれるグローバルpnpmも合わせて更新します。
グローバル版の更新は他プロジェクトにも適用されるため、利用中のプロジェクトの起動・ビルドを確認します。
`pmOnFail: error`・`verifyDepsBeforeRun: error`は維持し、版や依存関係の検証を緩和しません。

このPCのCodexの非対話環境では、未登録のVolta pnpm shimが先に選ばれると、子プロセスで`node`が見つからないことを確認しました。
Cursorの通常ターミナルはHomebrew版を選び、そのまま型チェック・ビルドを実行できます。
Codexで同じ問題が出る場合は、次のように実行するプロセスだけHomebrew版を先に選びます。

```bash
PATH="/opt/homebrew/bin:$PATH" pnpm typecheck:web
```

これはこのPCのHomebrew導入先に合わせた実行方法であり、シェル起動ファイルやプロジェクト専用設定の追加は不要です。

2026年10月3日に、このPCのmacOS arm64で既定Node.jsを24.21.0、Homebrew版と`PNPM_HOME`側のpnpmを12.8.1へ更新しました。
その後、プロジェクト専用の自動選択設定・スクリプト・生成物とmiseの信頼登録を撤去しました。
更新・撤去後の新規Cursorターミナルと通常の開発コマンドを確認しています。
別PC・Linuxホストでの初回導入は未確認です。

## 用意するファイル

Docker ComposeでAPI・DBを起動する前に `.env` を作成します。

```bash
cp .env.example .env
```

`.env` には、少なくとも PostgreSQL のパスワードを設定します。

```env
POSTGRES_PASSWORD=your-local-postgres-password
```

`.env` は秘密情報を含みうるため、コミットしません。
Web単体の起動には、このファイルは必要ありません。

## セットアップされている主な構成ファイル

- `package.json`: ルートの pnpm scripts を定義します。
- `pnpm-workspace.yaml`: pnpm workspace の対象として `apps/web` を指定します。
- `apps/web/package.json`: Next.js / React / TypeScript の依存関係と scripts を定義します。
- `apps/api/pyproject.toml`: API 用の Python 依存関係として `fastapi[standard]` / `sqlalchemy` / `psycopg` / `alembic` を定義します。
- `packages/scraper/pyproject.toml`: scraper 用の Python パッケージ設定を定義します。
- `infra/compose.yml`: `web` / `api` / `db` の Docker Compose 構成を定義します。
- `infra/compose.test.yml`: PostgreSQL 17を使うDB統合テスト専用の一時DBを定義します。
- `infra/docker/web.Dockerfile`: Web コンテナのビルド手順を定義します。
- `infra/docker/api.Dockerfile`: API コンテナのビルド手順を定義します。
- `Makefile`: Docker Compose の起動・停止コマンドを短く呼べるようにします。

## Markdownの書式とエディター設定

既存Markdownの段落、一文一行、末尾2スペースによる強制改行を維持します。
Gitの空白検査は`.gitattributes`、EditorConfig対応エディターの保存時の空白削除は`.editorconfig`で設定します。
`.editorconfig`では`[*.md]`の`trim_trailing_whitespace = false`でMarkdownの末尾空白を残し、他のファイルの末尾空白削除は維持します。
設定の意味は[EditorConfigの公式仕様](https://editorconfig.org/#supported-properties)を参照してください。

Cursorでは、既存の`.vscode/settings.json`へ次の言語別設定を追加します。
既存のキーは残し、`[markdown]`がある場合はその中へ統合します。

```json
{
  "[markdown]": {
    "files.trimTrailingWhitespace": false,
    "editor.formatOnSave": false
  }
}
```

`.vscode/`はGit管理外のため、この設定は各開発環境で追加してください。
この設定はMarkdownの保存時整形と末尾空白削除を無効にし、明示的な手動整形の禁止は行いません。
末尾2スペースを含む検証用Markdownを保存し、スペースが残ることとプレビューの強制改行を確認します。

Oxlint 1.87.0・Oxfmt 0.72.0をルートの開発依存へ置き、CLI・CIはルートの`.oxlintrc.json`・`.oxfmtrc.json`を明示して参照します。
Phase 6ではフロントエンドを対象とし、Oxfmtの共有設定の`ignorePatterns`に`**/*.md`を指定してMarkdownを除外します。
CLI・CIの対象パスもフロントエンドに限定し、CursorでOxcを既定のフォーマッターに指定する場合はJavaScript・JSX・TypeScript・TSXの言語別設定にします。
導入時は、エディター・CLI・CIで同じ除外設定が参照され、Markdownが整形・チェック対象に含まれないことを確認します。
除外設定はOxfmtの設定ファイルごとの範囲に適用されるため、設定を階層ごとに分ける場合は各設定でMarkdownの除外を維持します。
リポジトリルートと`apps/web`からの実行、Markdownファイルの明示指定でも除外が効くことを確認します。
除外対象だけを指定した検証では、「対象ファイルなし」による終了と整形失敗を区別し、元の内容が変更されていないことを確認します。
`.gitattributes`と`.editorconfig`だけではOxfmtの整形対象を制御できません。
詳細は[Oxfmtの除外設定](https://oxc.rs/docs/guide/usage/formatter/ignore-files)と[エディター設定](https://oxc.rs/docs/guide/usage/formatter/editors)を参照してください。

導入前の一時環境のOxfmt 0.71.0で、ルート・`apps/web`・明示ファイル指定・階層別設定のCLIでの除外を確認しました。
LSP経由でもルートと`apps/web`のMarkdownに整形結果が返らず、TypeScriptには整形結果が返ることを確認しました。
除外を外すとMarkdownが書き換わり、除外を戻すと内容が維持されることも確認しています。
これは除外方針の検証であり、プロジェクトへの導入やCursorでの実保存・実CIの確認ではありません。
導入時は採用するバージョンで上記の確認を行います。

採用版Oxfmt 0.72.0の一時環境で、除外なしでは差分が出るMarkdownを使ってCLIの除外と内容保持を確認しました。
ルートと`apps/web`のMarkdownを明示指定した場合、除外後は「対象ファイルなし」の診断と終了コード2になり、書式違反による終了コード1と区別できました。
設定不正も非ゼロで終了するため、「対象ファイルなし」・書式違反・設定不正を診断内容で区別し、元のファイルのバイト列も確認します。
LSP経由では同じMarkdownに整形差分が返らず、書式違反のTypeScriptには整形差分が返ることを確認しました。
このCLI・LSP確認は、Cursorでの実保存・プレビューやGitHub Actions上での実行を代替するものではありません。

採用版CLIの除外確認と[Cursorでの実保存・プレビューの確認](#webのlintformatとcursor連携)に加え、[PR #102とマージ後pushの実CI](#phase-6-5の確認実績)で共通設定を使うformat確認と空白検査の成功を確認しました。
CIの`pnpm format:check:web`はWebの共有コマンドを呼び、ルートの`.oxfmtrc.json`を参照し、対象拡張子にMarkdownを含めません。
OxfmtのMarkdown除外設定とCLIの対象指定は維持されています。
一時ファイルを使ったGitの空白検査で、Markdownの末尾2スペースを許容し、TypeScriptの行末空白を検出することも確認しました。
検証用ファイルは確認後に削除しました。

## lockfile について

`pnpm-lock.yaml` は Node.js 依存関係の lockfile です。
pnpm 12では、先頭の文書にpnpm本体の管理情報、最後の文書にWebの依存関係を記録します。
通常の再インストールでは`pnpm install --frozen-lockfile`を使い、lockfileの書き換えが必要な場合は差分を確認します。

`uv.lock` は Python 依存関係の lockfile です。API と scraper はそれぞれ `apps/api/uv.lock`、`packages/scraper/uv.lock` を持ちます。各 `pyproject.toml` をもとに `uv sync` すると、解決されたパッケージの具体的なバージョンが記録され、その内容に沿って仮想環境が作られます。

Dockerfile では `uv sync --frozen` を使うため、lockfile を更新せず、記録済みの依存関係で再現性のある環境を作ります。

## フロントエンドを単体で起動する

画面だけを確認したい場合は、フロントエンドを単体で起動できます。

```bash
pnpm install --frozen-lockfile
pnpm dev:web --hostname 127.0.0.1
```

ブラウザで次を開きます。

```text
http://127.0.0.1:3000/
```

Docker Compose で全体を起動する場合、この単体起動は必須ではありません。
WebのDockerfileもルートの`packageManager`を読み、Node.js 24.21.0とpnpm 12.8.1を使用します。
ComposeのWebは`node_modules`を名前付きボリュームに保持するため、既存ボリュームを使うと以前の依存関係が残る場合があります。
新しい依存関係を確認するときは、秘密ファイルと既存の`node_modules`・`.next`を含めない一時build contextでWeb単体をビルドし、既存ボリュームを使わずに起動します。
ホストの公開ポートは`127.0.0.1`に限定し、確認後は今回作成したコンテナ・イメージだけを削除します。
Dockerの画面確認には`http://localhost:<ホスト側の公開ポート>/`を使い、開発サーバーが表示するホスト名に合わせます。

### Webの型チェックとビルド

新規インストール後は、開発サーバーや古い生成物に依存せず型情報を生成してから確認します。

```bash
pnpm install --frozen-lockfile
pnpm typegen:web
pnpm typecheck:web
pnpm build:web
```

`next typegen`は型情報を生成し、`typecheck:web`はTypeScriptの型チェック、`build:web`は本番ビルドを実行します。
TypeScriptは`^7.0.2`、lockfileの解決版は7.0.2で、`tsc`はインストール先のOS・CPUに対応するネイティブバイナリーを使用します。
optional dependencyに含まれるプラットフォーム用パッケージも必要なため、インストール時にoptional dependencyを一括で省略しません。
Next.js 16.4.1のビルドも既定のCLI経路で同じプロジェクト内のTypeScriptを使用し、`experimental.useTypeScriptCli`の追加設定は不要です。
`pnpm --filter @press-watch/web exec tsc --version`でCLIの版を確認できます。
[Next.jsの型生成手順](https://nextjs.org/docs/app/api-reference/cli/next#next-typegen-options)に従い、`next-env.d.ts`は手動で編集しません。
Next.js 16.4.1では`root-params.d.ts`への参照も生成されます。
型生成・ビルドでは`.next/types/`、開発起動では`.next/dev/types/`を参照するため、`next-env.d.ts`の自動差分と`tsconfig.json`への必要な変更を確認します。
型エラーやビルドエラーを無視する設定は追加しません。

依存更新の比較では、必要なマニフェスト・lockfile・設定・Webソースだけを一時環境へコピーし、秘密ファイル・既存の`node_modules`・`.next`・`tsbuildinfo`を含めません。
更新前後で上記の手順を実行し、同じ画面サイズで文言・レイアウト・タイトル・日本語設定とブラウザ・サーバーのエラーを確認します。
更新後は`pnpm install --frozen-lockfile`を再実行し、lockfileが変わらないことも確認します。
Web単体Dockerでも、表示だけでなく、コンテナ内の`/workspace`から型生成・`pnpm typecheck:web`・`pnpm build:web`を実行し、Linux用コンパイラーの版と起動を確認します。
ループバック限定で起動した開発サーバーは、確認後に終了します。

### Webのlint・formatとCursor連携

lintはWebのJavaScript・JSX・TypeScript・TSXを対象とし、既定のTypeScript・Unicorn・OxcにReact・Next.js・JSXアクセシビリティのプラグインを加えます。
correctnessカテゴリの警告を有効にし、`--deny-warnings`で警告もCLI・CIの失敗として扱います。
formatはWebの対応ソース・CSS・JSONを対象とし、2スペース、ダブルクォート、セミコロン、行幅100を共有します。
import・package.jsonキー・Tailwindクラスの並べ替えは無効です。
Markdown、Next.jsの生成ファイル、依存とビルド・テスト生成物は共有設定で除外します。

Mock・テーマ初期化・共通Label部品と一覧のスクロール・ドロワー操作を維持するため、次の6ルールを該当する8ファイルに限定して例外にします。
例外は`.oxlintrc.json`の`overrides`へ置き、その他のファイルでは同じルールを有効にします。

| ルール | 対象（`apps/web/`からの相対パス） | 理由 |
| --- | --- | --- |
| `react/set-state-in-effect` | `components/theme-selector.tsx`、`components/press-releases/theme-toggle.tsx`、`components/mock/workbench.tsx` | hydration後のテーマ表示と画面幅の初期化で使う状態更新を維持する |
| `jsx-a11y/prefer-tag-over-role` | `components/mock/category-toggles.tsx`、`components/press-releases/theme-toggle.tsx`、`components/mock/workbench.tsx`、`app/mock/page.tsx`、`components/press-releases/scroll-region.tsx` | テーマ・Mockの名前付きgroup・searchと、製品・Mockで共用する一覧のregion、対応するCSSを維持する |
| `jsx-a11y/label-has-associated-control` | `components/ui/label.tsx` | 共通部品の`htmlFor`をprops経由で受け取り、呼び出し側で入力欄と対応させる |
| `jsx-a11y/click-events-have-key-events` | `components/mock/workbench.tsx` | 見本内のリンクから伝播するclickを受けて遷移を止める既存処理を維持する |
| `jsx-a11y/no-noninteractive-tabindex` | `components/press-releases/scroll-region.tsx` | 名前付き一覧領域へフォーカスし、キーボードでスクロールできる構成を維持する |
| `jsx-a11y/no-noninteractive-element-interactions` | `components/mock/workbench.tsx`、`components/press-releases/sidebar-filters.tsx` | 見本内の遷移抑止と、dialogの背景クリック・フォーカス制御を維持する |

ファイル単位の例外なので、そのファイルへ今後追加するコードにも適用されます。
後続の製品実装で対象部品を変更する際は、必要性を見直し、入力ラベル・キーボード操作・フォーカスを画面テストと実操作で確認します。

```bash
pnpm lint:web
pnpm format:check:web
# 書式を変更するときだけ実行します。
pnpm format:web
```

`apps/web`からは`pnpm lint`・`pnpm format:check`・`pnpm format`を使えます。
いずれもルートの共有設定を参照し、チェック用のコマンドはファイルを書き換えません。

Cursorでは公式拡張`oxc.oxc-vscode`を使い、プロジェクトをリポジトリルートで開きます。
既存の`.vscode/settings.json`のキーとMarkdown用設定を残し、次の設定を追加します。
`.vscode/`はGit管理外のため各環境で設定し、全体設定へ追加しません。

```json
{
  "oxc.lint.run": "onType",
  "oxc.configPath": ".oxlintrc.json",
  "oxc.fmt.configPath": ".oxfmtrc.json",
  "[javascript][javascriptreact][typescript][typescriptreact]": {
    "editor.defaultFormatter": "oxc.oxc-vscode",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll.oxc": "never"
    }
  }
}
```

lintは診断表示だけを行い、保存時のlint自動修正は無効にします。
TypeScript・TSXの検証用ファイルに書式違反を入れて実際に保存し、Oxfmtの書式へ変わることを確認します。
別に未使用変数などを入れ、Oxlintの診断が表示され、保存しても自動修正されないことを確認します。
OxcのOutputでプロジェクト内の実行ファイル、Oxlint 1.87.0・Oxfmt 0.72.0と設定を確認し、必要なら`Oxc: Restart oxlint Server`・`Oxc: Restart oxfmt Server`を実行します。
Markdownでは前述の実保存・強制改行と、採用版LSPによる除外を別々に確認します。

リポジトリルートを開いたCursorで公式Oxc拡張1.63.0とプロジェクト内のOxlint 1.87.0・Oxfmt 0.72.0の検出を確認しました。
TypeScript・TSXのそれぞれで、保存時の整形と未使用変数のlint警告表示を確認しました。
保存後も未使用変数と警告が残り、lintによる自動修正が行われないことを確認しました。
末尾2スペースを含むMarkdownは保存前後のバイト列が一致し、プレビューでも強制改行を確認しました。
検証専用ファイルは確認後に削除しています。

### Webの画面テスト

Playwright 1.63.0をWebの開発依存へ置き、Chromium、1280×720、1 worker、リトライ0で実行します。
`dev-mock`はdevelopmentの通常一覧と既存の取得失敗表示への切替を確認します。
`production-smoke`はproductionの実API取得を応答制御サーバーへ接続し、一覧・取得状態・入力境界・復旧・要求数と`/mock`・`/ui-foundation`のHTTP 404を確認します。
対象ファイルと接続先はprojectごとに指定し、Mockの公開ガードを維持します。
通常カテゴリ操作の画面テストは`tests/e2e/category.spec.ts`を`production-smoke`の明示的な`testMatch`へ登録しています。

秘密ファイルを自動読込みさせずに検証するときは、必要なファイルだけを一時環境へコピーします。
許可するものはルートのマニフェスト・lockfile・workspace・Oxc設定・空白設定と、Webのマニフェスト・Next.js／TypeScript／PostCSS／部品設定・製品ソース・テスト・公開アセットです。
今回の確認ではコピーするファイルを個別に選び、`.env`・`.env.*`、認証設定、既存の`node_modules`・`.next`・`next-env.d.ts`・`tsbuildinfo`を含めていません。
起動用の環境変数にも外部API用の値を渡さず、一時環境で依存を再現します。

検証環境のルートから次の順序で実行します。

```bash
pnpm install --frozen-lockfile
pnpm typegen:web
pnpm typecheck:web
pnpm lint:web
pnpm format:check:web
pnpm build:web
PLAYWRIGHT_BROWSERS_PATH="$PWD/tmp/playwright/browsers" PLAYWRIGHT_SKIP_BROWSER_GC=1 pnpm --filter @press-watch/web exec playwright install chromium
pnpm test:web
```

`test:web`は現在のソースで本番ビルド済みであることを前提とします。
Web側の`pnpm test`も同じ専用ブラウザー保存先を使い、取得時は共有キャッシュの旧版を削除する処理を無効にします。
Playwrightが応答制御サーバーを`127.0.0.1:3107`、開発サーバーを`127.0.0.1:3105`、本番サーバーを`127.0.0.1:3106`で起動します。
Webの準備完了はAPI取得を発生させない`/third-party-notices.txt`、応答制御サーバーは`/__ready`で確認します。
既存サーバーは再利用せず、ポート占有時は失敗させます。
終了後は3105・3106・3107番に待受プロセスが残っていないことを確認します。

CIでは`test.only`・`test.describe.only`を`forbidOnly`で拒否します。
traceは`retain-on-failure`、スクリーンショットは`only-on-failure`とし、出力先はルートの`tmp/playwright/test-results`です。
MockはAPIを呼びません。
製品テストでは`tests/support/api-server.mjs`がNext.jsサーバーからの通信を記録し、片側失敗・0件・不正応答・ヘッダー／本文停止・遅延応答・応答前の接続切断を制御します。
本番テストサーバーには`tests/support/server-clock.cjs`を読み込み、日跨ぎの履歴復元テスト中だけNext.jsとブラウザーの日時を合わせて変更します。
Next.jsの時刻は`tmp/playwright/server-clock.json`が存在する間だけ変更し、通信期限に使う時間は進め続け、テスト終了時にファイルを削除します。
`pnpm test:web`は専用DBや資格情報を使用せず、実API・DBとの結合確認とは別の検証です。
ブラウザーのリクエスト差し替えだけでServer側の通信を制御できたとは扱いません。

### 製品一覧の接続先と実API画面テスト

一覧はNext.jsサーバー専用の`PRESSWATCH_API_BASE_URL`を起動時に設定します。
未設定・不正な値は取得失敗になり、Mockへ置き換えません。
`NEXT_PUBLIC_`の設定は作らず、DB資格情報もWebへ渡しません。
API接続先のクエリ・fragment・userinfoとリダイレクトは許可しません。
ビルドはAPIへ接続せず、正常な条件の1回の取得で一覧と選択肢を最大2要求、`cache: "no-store"`、本文読み取りまで各10秒で取得します。

通常の検証は上記の秘密ファイルを含まない一時Webコピーで実行します。
起動環境も`env -i`等で必要なPATH・HOME・TMPDIR・localeとプロセス固有の設定だけに限定し、npmのユーザー／global設定を`/dev/null`にします。
この環境でVoltaのpnpm shimが起動できない場合は、承認版のpnpm 12.8.1本体とNode.js 24.21.0をそのプロセスのPATHへ指定します。
プロジェクト・グローバルのツール設定は変更しません。

実APIの画面確認は[専用PostgreSQL 17の手順](#phase-6の接続検証用postgresql-17)で保存済みDBを再利用します。
専用DB・APIの起動と読取り専用利用の承認、`.env.api-validation`だけを非表示で読む別承認を受け、metadataを照合してから起動します。
既存コンソールの`compose('up', '--detach', '--wait', '--wait-timeout', '60', 'db')`を用い、identity・revision・schema・CSV定義・fixture原本と全所属を読取り専用で照合した後、`start_api()`を実行します。
保存済みデータの再利用だけを承認した場合、初回準備・migration・seed・保存・再分類を再実行しません。
不整合があれば停止し、復旧の書込みは別途確認します。

秘密ファイルを含まない検証環境で本番ビルド後、専用APIが`127.0.0.1:8001`で起動している間だけ次を手動実行します。
ブラウザー保存先は上記の導入手順と揃えます。

```bash
PLAYWRIGHT_BROWSERS_PATH="$PWD/tmp/playwright/browsers" pnpm --filter @press-watch/web exec playwright test --config playwright.real.config.ts
```

このconfigはWebだけを`127.0.0.1:3108`で起動・終了し、API接続先を8001番に固定します。
一覧の画面上で1→2→1ページを移動し、50／12／50件の各表示をAPIの順序・タイトル・リンク・日付・全所属と照合します。
通常の検索ボタンから日本語検索・公開日指定・リセットを行い、カテゴリ付き検索とページ送りの結果も実APIと照合します。
カテゴリボタンから個別選択・解除・全選択・全解除を操作し、ORの件数・検索と日付とのAND・全所属・未分類・未定義slugとページ位置を照合します。
通常の`pnpm test:web`やCIから実APIテストを自動実行しません。
検証前後に業務4テーブルの全列・所属が不変であることを非表示で比較し、利用後は`stop()`・`db.dispose()`と3108・8001・55433番の待受け解放を確認します。
資格情報・永続ボリュームを保持し、fixtureのリンク先へHTTP要求を行いません。

### 専用実APIで本人の画面操作を確認する

自動画面テストと本人による操作性の確認は別々に記録します。
専用DB・API・手動確認用Webの起動と読取り利用、専用秘密ファイルの非表示読取りは、今回の作業範囲に対する承認を受けます。
上記の秘密ファイルを含まない一時Webコピーで本番ビルドし、専用DBの照合後に業務4テーブルの全列・全所属を非表示で保持します。
専用APIを8001番で起動したPythonコンソールは、本人の確認が終わるまで維持します。

実APIテスト終了後、3108番のテスト用Webが終了し、待受けがないことを確認します。
一時Webコピーのルートで、別のターミナルから次を実行します。
Node.js・pnpmの実行パスは[一時環境の実行方法](#製品一覧の接続先と実api画面テスト)に従い、既存の秘密情報を継承しません。

```bash
env -i PATH="$PATH" HOME="$HOME" TMPDIR="${TMPDIR:-/tmp}" LANG="${LANG:-en_US.UTF-8}" \
  NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 \
  npm_config_userconfig=/dev/null npm_config_globalconfig=/dev/null \
  PRESSWATCH_API_BASE_URL=http://127.0.0.1:8001 \
  pnpm --filter @press-watch/web exec next start --hostname 127.0.0.1 --port 3108
```

実行環境のプロセス管理機能を使う場合も、同じ環境と引数で起動し、今回のWeb・APIのPID・プロセスグループ、専用Compose projectを記録します。
3108番を自動テストと同時に使わず、既存プロセスを停止したり別ポートへ自動で切り替えたりしません。
Webの起動と専用API由来の合成一覧を確認してから、`http://127.0.0.1:3108`を案内します。
一覧内の検索・公開日・カテゴリ・ページ送り・下書き・履歴・各解除、文字サイズ・テーマ・狭い画面・キーボードを確認し、記事の外部リンクは開きません。

案内後は「手動確認待ち」とし、本人の終了・中断・省略の指示までサービスを維持します。
終了・中断後は、利用前後の全列・全所属を比較し、今回のWebを終了してから`stop()`・`db.dispose()`でAPI・専用DBを終了します。
Webをターミナルで起動した場合はその前面の処理を終了し、プロセス管理機能を使った場合は記録した所有プロセスグループだけを回収します。
前後比較が失敗した場合も、終了処理で今回のWeb・API・専用DBの停止を試み、不一致は未解決として報告します。
3108・8001・55433番の解放を確認し、資格情報と永続ボリュームは保持します。
例外・中断時の回収は[専用環境の停止手順](#停止再起動と確認実績)に従い、終了を確認できない場合は完了扱いにしません。

### Phase 6-7のローカル確認実績

秘密ファイルを含まない検証コピーでfrozen install、`pnpm typegen:web`・`pnpm typecheck:web`・`pnpm lint:web`・`pnpm format:check:web`・`pnpm build:web`・`pnpm test:web`を実行し、画面テスト85件が成功しました。
正常表示・取得失敗・片側失敗・不正応答・空状態・復旧の観測可能な単位で、実装前のassertion失敗と実装後の成功を確認しています。
実装後に追加した安全性・履歴・要求数の回帰確認と、実API検証はこのRED／GREENの記録とは区別します。

- 応答制御サーバーに到着したNext.jsからの要求を数え、記事0・1・50件とも初回は一覧1＋選択肢1、手動再取得後の累計は4要求でした。
  正規化待ちのURLでは0要求、不正条件では選択肢1要求だけ、正規化後の1取得単位は2要求であり、記事ごとの要求や自動再試行はありません。
- 各APIのヘッダー無応答・本文停止の4ケースは、到着から中断まで9.5〜12秒のassertionを満たしました。
  テストのcleanupより前に接続が中断され、成功側を保持し、手動再取得の2要求で復旧しました。
- 同じURLの再取得、件数差からの再取得、履歴の戻る／進む、遅延した旧応答の完了を確認しました。
  旧一覧・件数・ページ情報を取得中に隠し、再取得では下書き・URL・履歴を維持します。
  日付422の修正では個別解除後のカテゴリ条件（指定なしを含む）を維持し、不正URLのカテゴリ入力は修正値がURLとAPI要求へ反映されることを確認しました。
- 有効なAPI接続先を設定したビルドでも、応答制御サーバーへの要求は0でした。
  未設定・不正接続先の5ケースも要求0で両取得失敗になり、有効な接続先の実行時だけ2要求になりました。
- Mockの通常・失敗表示、文字サイズ・テーマ・ドロワーと、productionの開発専用ページのHTTP 404を確認しました。
  共用CSSの抽出は採用済み555宣言を照合し、製品の失敗・空状態にも採用済みの装飾を引き継ぎました。

専用PostgreSQL 17・実FastAPI・Webの手動画面テストでは、総件数62、1ページ目50件・2ページ目12件、API順序・全文タイトル・リンク・公開日・10選択肢・全所属を照合しました。
所属なし1記事と、土壌検索／大気絞り込みでもair・soilの両所属を表示する記事、条件付き0件を確認しています。
schema・revision・CSV定義・fixture原本と所属を読取り専用で照合し、業務4テーブルの全列・所属が検証前後で不変であることを確認しました。
専用API・DBと所有するWeb・応答制御サーバーは停止し、資格情報・永続ボリュームは保持しています。
障害・正常0選択肢・件数差は応答制御で確認したもので、実DBを変更して再現していません。
通常検索・カテゴリ変更・ページ送り本体は後続タスク、Supabase・開発DB・実データと今回の変更の実CIは未確認です。

### Phase 6-8のローカル確認実績

秘密ファイル・既存依存・生成物を含まない一時コピーでfrozen install、`pnpm typegen:web`・`pnpm typecheck:web`・`pnpm lint:web`・`pnpm format:check:web`・`pnpm build:web`・`pnpm test:web`を実行し、画面テスト107件が成功しました。
その後、幅別の4ケースを長い有効条件によるヘッダー内スクロールの確認へ補強し、4件の再検証と型チェック・lint・format確認が成功しました。
ページ送りの未表示と、遷移後に見出しへフォーカスが移らないassertionのREDを実装前に確認し、実装後のGREENを確認しました。
実装後に補強した失敗・履歴・ドロワー・表示幅などの回帰確認と、実API検証を、このRED／GREENの記録と区別します。

- 応答制御で先頭・中間・最終の123件を50／50／23件として確認しました。
  1ページのみ、5／6ページの表示境界、多数ページの省略、10,000ページ上限、正常0件・範囲外・範囲内の件数差を確認しています。
- 適用済みキーワード・日付・既知／未定義カテゴリを保持してページだけを変更し、下書きを混入しません。
  下書きはページ変更で保持し、戻る／進むではURLの値へ復元することを確認しました。
  現在ページの選択・hover・フォーカスで要求数と履歴は増えず、3ページの取得は一覧・選択肢を合わせて6要求でした。
- 取得中の旧ページ情報の非表示、連打の停止、一覧失敗時のページ情報なし、選択肢失敗・正常0件でのリンク先とTab順の無効化、手動再取得での復旧を確認しました。
  履歴で中断したページ送りの古い応答は、一覧・下書き・フォーカスを上書きしません。
- 幅1280・390・767・768pxで遷移後の見出しフォーカスと一覧先頭の表示を確認しました。
  キーワード100文字・カテゴリ20個の有効条件で、PCのヘッダー内を末尾までスクロールしても先頭へ戻ります。
  完了時の幅変更、待機中の入力編集、ドロワー開閉と再取得による取消済みフォーカス移動の非復活、失敗時の復旧見出し、大きい文字・5桁番号の横はみ出しとEnter操作を確認しています。
- 既存の通信期限・片側失敗・入力境界・復旧・XSS防止、Mockのテーマ・文字サイズ・ドロワー、productionでの開発専用ページのHTTP 404も全体テストで成功しました。

フォーカスの追加修正後は、検索欄・条件トリガーから非フォーカス要素へ移動してから幅を変更する操作と、幅変更そのもので操作部品が隠れる場合の復元を確認しました。
上記の一時Web環境で型生成・型チェック・lint・format確認・本番buildが成功し、画面テスト111件が成功しました。

PR #112の[初回Web CI](https://github.com/64-HiroByte/press-watch/actions/runs/38200939844)では、幅768pxのヘッダースクロール確認だけが失敗しました。
traceでは、読み込み表示中にNext.jsのストリーミング用の非表示領域にあるヘッダーを取得し、表示前に高さを測っていました。
`locator.evaluate()`はDOMへの追加を待つだけで表示を待たないため、スクロールを測定する前に`toBeVisible()`で表示を確認するようにしました。
移動前の`scrollTop > 0`、移動後の`scrollTop = 0`、見出しのフォーカスと見出し・一覧先頭の画面内表示のassertionは維持し、固定時間の待機やretryは追加していません。
一時コピーだけで描画のコールバックを遅らせ、修正前の同じ失敗と修正後の幅1280・390・767・768pxの4件成功を確認しました。
同じ一時コピーでヘッダーのスクロール復元を無効化すると、修正後も幅768pxの見出しの画面内表示のassertionが失敗し、復元不具合を検出できました。
調査用の遅延・無効化を除去し、修正後の現行Webソース・設定・マニフェスト58ファイルとの一致を確認した一時環境で、型生成・型チェック・lint・format確認・本番buildと通常画面テスト111件が成功しました。

以下の実API検証では、Web実装`f960ae1`を使用しました。
専用資格情報の非表示読取りを承認後、Docker endpoint・project・Compose file・コンテナ・マウント・ポート・既存ボリュームを照合し、保存済みの専用PostgreSQL 17を再利用しました。
identity・head`a51eab6808f3`・schemaの列／制約／索引・CSV定義・fixture原本・全所属が一致し、10カテゴリ・57キーワード・62記事・62所属を読取り専用で確認しました。
migration・seed・保存・再分類は実行せず、API接続にも読取り専用の設定を渡し、DB資格情報をWebへ渡していません。

専用実FastAPI・一時Webの手動画面テスト1件が成功しました。
画面の前／次で1→2→1ページを移動し、総件数62・50／12／50件の表示、APIの順序・全文タイトル・リンク・公開日・10選択肢・全所属と未分類、現在ページ・正規URL・見出しフォーカスを照合しました。
APIの新着順はDBの実ID順と一致し、土壌検索／大気絞り込みでair・soilの両所属を表示する記事と条件付き0件も確認しました。
外部の記事詳細URLへアクセスしていません。
業務4テーブルの全列・全所属は、非表示スナップショットの前後比較で不変でした。
所有するWeb・APIと専用DBを停止し、コンテナの`exited`と3105〜3108・8001・55433番の待受け解放、永続ボリュームと資格情報の保持を確認しました。
中間ページ・障害・選択肢0件・件数差は応答制御で確認した結果であり、専用DBのデータを増やしたり変更したりして再現していません。
この実API確認では、通常検索・カテゴリ選択・全操作の結合確認、Supabase・開発DB・実データは対象外または未確認です。

### Phase 6-9のローカル確認実績

Web実装は`ae183fb`であり、以下はこの実装に対するローカル検証の実績です。
検証時の`4dec68e`からコミットメッセージだけを変更したもので、Gitのtreeが一致することを確認しました。
秘密ファイル・既存依存・生成物を含まない一時コピーでfrozen installし、`pnpm typegen:web`・`pnpm typecheck:web`・`pnpm lint:web`・`pnpm format:check:web`・`pnpm build:web`を実行しました。
修正後の現行ソースでこれらの必須チェックと`pnpm test:web`が成功し、既存111件と検索21件の通常画面テスト132件が成功しました。
通常検索・リセットの無効状態、期間選択欄の未実装、IME変換確定Enterによる余分な取得、入力エラーの欄への関連付け不足をassertionのREDで確認し、実装後のGREENを確認しました。
実装後に補強した境界・履歴・失敗時の回帰確認と実API検証は、このRED／GREENの記録と区別します。

- 日本語検索、空白だけの検索解除、Unicodeコードポイント100文字の許可と空白除去前101文字の拒否、NUL拒否、特殊文字の保持とHTML文字列の非実行を確認しました。
  入力エラーでは適用条件・URL・直前の一覧とドロワーを保持し、該当欄にエラーを関連付けてフォーカスを移します。
- 公開日の逆順・開始日だけ・終了日だけ・未指定、不正日付・未来の開始日だけの拒否を確認しました。
  期間選択は取得せず、今日を含む7日間と暦の1・3・6ヶ月／1年、月末・うるう年の期待値を固定した日付で照合しました。
  手動修正、任意の期間への切替、選択翌日の検索・再読み込み・履歴復元でも具体的な日付を保持します。
- 同じURLの検索は履歴を増やさず再取得し、条件変更はカテゴリを保持して1ページ目へ戻ります。
  1取得単位は一覧・選択肢の2要求であり、入力編集・期間選択と適用条件が変わらないリセットでは要求を増やしません。
  取得中の操作停止・下書き編集、検索成功時のドロワー閉鎖とトリガーへのフォーカス復元、選択肢失敗・0件と一覧失敗・結果0件・日付422の操作可否を確認しました。
- セルフレビューで、未完成の日付が状態値の空文字とは別に入力欄へ残ることをREDで再現しました。
  リセット・全条件解除・履歴復元で残留入力を消す修正後のGREENを確認しました。
  既存の履歴復元テストは、エラーを表示する領域を指定し、同じ文言がフォームにも表示される場合の曖昧な対象選択を避けました。

専用PostgreSQL 17と実FastAPIでは、metadata・identity・revision・schemaの列／制約／索引・CSV定義・fixture原本・全所属を照合し、10カテゴリ・57キーワード・62記事・62所属の既存データを読取り専用で再利用しました。
画面テスト2件が成功し、従来の1→2→1ページの全表示照合に加え、通常の日本語検索・逆順日付・公開日両端の包含と範囲外の0件・リセット・カテゴリ保持・51件の検索結果のページ送りをAPI結果と照合しました。
`%_`は検索用のワイルドカードとして解釈されず、通常検索から0件になることも確認しました。
資格情報は専用DB・APIだけへ渡し、migration・seed・保存・再分類や外部の記事詳細URLへのアクセスは行っていません。
業務4テーブルの全列・全所属は非表示の前後比較で不変でした。
今回起動したWeb・API・専用DBを停止し、3105〜3108・8001・55433番の待受け解放、永続ボリュームと資格情報の保持を確認しました。
障害・選択肢0件・入力境界・IMEは応答制御とChromiumでの確認であり、実DBを変更して再現していません。
通常カテゴリ選択は6-10、全操作の最終結合確認とPhase全体の文書点検は6-11へ残します。
Supabase・開発DB・実データ・OS固有の日本語IME操作と今回の変更の実CIは未確認です。

独立レビューでは、`/?q=alpha%0Abeta`または`/?q=alpha%0Dbeta`を直接開くと、検索欄には`alphabeta`と表示される一方、通常検索ではLFまたはCRを含む元の値が送信されることを再現しました。
通常の入力・貼り付けでは発生せず、親ブランチにも存在する既知の軽微な制約です。
キーワード内部の空白を保持する契約に沿って解消するには、改行を表示・編集する入力UIとEnter・IME操作の設計が必要なため、後続Issueの候補として残しています。

### Phase 6-10のローカル確認実績

Web実装は`8bc0778`であり、以下はこの実装に対するローカル検証の実績です。
秘密ファイル・既存`node_modules`・生成物を含まない一時コピーでfrozen installし、型生成・型チェック・lint・format確認・本番buildと通常画面テスト146件が成功しました。
個別カテゴリボタンの無効状態、一括操作ボタンの未実装、20指定時の追加と21選択肢の全選択が操作可能であることをassertionのREDとして確認し、最小実装後のGREENを確認しました。
追加の異常系・履歴・取得中の回帰確認と実API検証は、実装前のRED／GREENとは区別します。

- 個別選択・解除・全選択・全解除、未定義slugの保持・明示解除、20指定の上限と解除後の再開を確認しました。
  選択肢全体が20件なら全選択でき、21件なら全選択だけを停止します。
- 最後に適用したキーワード・公開日へカテゴリだけを変更し、検索下書き・期間選択・送信前の入力エラーを保持することを確認しました。
  カテゴリ変更は1ページ目へ戻してドロワーを維持し、新しい検索では現在のカテゴリを維持します。
- 選択集合が変わらない操作では、2ページ目でもページ・取得・履歴を変更しません。
  ページ送り・戻る／進む・再読み込みで選択と適用条件を復元し、履歴移動では下書きを破棄します。
- 選択肢の失敗・0件、不正URL・日付422ではカテゴリ操作を停止し、再取得または条件修正で復旧することを確認しました。
  一覧だけの500・正常0件ではカテゴリ変更を維持し、検索・リセット・修正・全条件解除の既存回帰も成功しました。
- 取得中の連打・Enterを停止し、下書きの編集、操作元のDOM・フォーカス、利用者が移したフォーカスを維持しました。
  古い応答、範囲外復帰、取得期限と要求数の既存回帰も成功しました。
- セルフレビューで、実APIテストの件数セレクタがページ番号と重なる不備を修正しました。
  期待するURLは製品の選択・URL生成処理から作らず固定条件とし、件数・一覧との一致も確認します。
  無変更操作では取得中の終了を確認してから要求数を調べ、固定待機を追加していません。

専用PostgreSQL 17と実FastAPIでは、metadata・identity・revision・schemaの列／制約／索引・CSV定義・fixture原本・全所属を照合し、10カテゴリ・57キーワード・62記事・62所属を読取り専用で再利用しました。
画面テスト3件が成功し、air単独52件、air／soilのORで53件、全選択61件、全解除62件を実際の操作とAPI結果で照合しました。
カテゴリORとキーワード・公開日のAND、複数所属の全所属表示、未分類、未定義slug、条件変更時のページ位置と必要なページ送りも確認しました。
APIの起動準備で`uv`が見つからなかったため、その検証プロセスのPATHだけへ実体の所在を加えて再実行し、グローバル設定は変更していません。
資格情報は専用DB・APIだけへ渡し、migration・seed・保存・再分類や外部の記事詳細URLへのアクセスは行っていません。
画面テストの失敗時と成功時の業務4テーブルの全列・全所属は非表示の前後比較で不変でした。
今回起動したWeb・API・専用DBを停止し、3105〜3108・8001・55433番の待受け解放、永続ボリュームと資格情報の保持を確認しました。

20指定上限・選択肢の失敗と0件・日付422・送信前の入力エラーは応答制御で確認し、実DBを変更して再現していません。
全操作の最終結合確認とPhase全体の文書点検は6-11へ残します。
Supabase・開発DB・実データ・OS固有の日本語IME操作と今回の変更の実CIは未確認です。
Issue #114のCR／LF入り直接URLと、PR #112で受け入れた拒否URL診断の軽微な過剰伏字は今回の変更対象外です。

その後、カテゴリ指定数・カテゴリslug長・キーワード長の上限を意味ごとに共有定数へ集約し、判定と表示文言の更新漏れを防ぐ構成にしました。
共通化後も型生成・型チェック・lint・format確認・本番buildと通常画面テスト146件が成功し、20／21指定・100／101文字・Unicode文字数と空白除去前の検証を維持しています。
動作を変えない内部整理のため新しい形式的なテストは追加せず、期待値は製品の共有定数から生成していません。
FastAPI・DBと上限値自体は変更しておらず、入力上限だけを共通化した段階では専用DB・実APIの検証を再実行していません。

全差分の追加点検では、表示件数50・最大ページ番号10,000・JavaScriptの狭い画面判定式と、カテゴリ操作の停止条件の重複も整理しました。
一覧の表示範囲は検証済みAPIの`page_size`から計算し、通信期限10秒は最大ページ番号と別の定義にしています。
実APIテストの照合処理を共有し、URL・件数・順序・全文タイトル・リンク・日付・全所属・未分類のassertionを維持しました。
独立した期待値を製品定数から生成せず、型生成・型チェック・lint・format確認・本番build・通常画面テスト146件と実API画面テスト3件が成功しました。
専用DBを再照合して読取り専用で再利用し、業務4テーブルの全列・全所属の不変、所有サービスの停止、対象ポートの解放も再確認しました。

PR #116の最終作業HEAD `296415da4e045108b3217c4bb5cd9e06f78f8b61`に対する[Web CI](https://github.com/64-HiroByte/press-watch/actions/runs/38661672437)では、型生成・型チェック・lint・format確認・本番build・通常画面テスト146件の成功をその後確認しました。
[Python CI](https://github.com/64-HiroByte/press-watch/actions/runs/38661672446)は空白検査・変更判定が成功し、API・scraperの製品テストstepとPostgreSQL統合jobは変更範囲によるskipでした。
上記の「実CIは未確認」はローカル検証時点の記述であり、この実CIの結果と区別します。

### Phase 6-11の結合確認と文書点検

最初の結合確認では、親ブランチ`b4f8c5b`のWeb製品コードを維持し、不足する保証のテストと文書を追加しました。
秘密ファイル・既存依存・生成物を含まない一時Webコピーでfrozen installし、型生成・型チェック・lint・format確認・本番buildと通常画面テスト149件が成功しました。
既存の146件へ、開始日だけの検索後の日跨ぎ1件と、一覧・選択肢それぞれの応答前接続切断2件を追加しました。
この段階で製品不具合は再現しておらず、これらは既存動作の回帰確認でありTDDのRED／GREEN実績とは扱いません。

- 開始日だけの検索で確定した終了日が、翌日の再読込・戻る／進むで変わらず、入力欄・URL・実際の要求に同じ具体的な日付を維持することを確認しました。
  日跨ぎはNext.jsとブラウザーの時計を合わせて再現し、履歴移動で下書きを破棄することも確認しました。
- 応答前に接続を切ったAPIだけを取得失敗とし、成功側を保持することを確認しました。
  自動再試行を加えず、最初の取得は2要求、明示的な再取得後は合計4要求で復旧しました。
- 不正URL・正規化・未定義slug・0件・範囲外、422・500・503・非JSON、ヘッダー／本文の10秒停止、古い応答・同じURLの再取得・無変更操作は既存テストで確認しました。
  入力エラーの関連付け、IMEのEnter抑止、フォーカス・ドロワー・スクロールも通常画面テストの保証範囲です。

専用PostgreSQL 17のmetadata・identity・revision・列／制約／索引・CSV・fixture原本・全所属を照合し、10カテゴリ・57キーワード・62記事・62所属を読取り専用で再利用しました。
実FastAPIの画面テスト3件が成功し、各段階のURL・件数・記事順・タイトル・リンク・公開日・全所属を実API応答と照合しました。
既存のOR／AND・全選択・全解除・未分類・未定義slugに加え、下書きを入力した状態でのカテゴリ追加・ページ送り、戻る／進むでの入力復元を確認しました。
検索リセットでは大気／土壌の53件、カテゴリ全解除では62件を確認し、再び検索・公開日・大気を適用した51件の2ページ目から全条件解除しました。
全条件解除後は下書きも消え、URL `/`・62件・1ページ目になりました。
自動検証後の業務4テーブル全列・全所属は、利用前の非表示スナップショットと一致しました。

README・要件・技術構成・一覧UI・固定カテゴリ設計・開発手順を点検し、実装済みのWeb機能、安全な本人確認の手順、前タスクの実CI結果と今回の保証範囲を反映しています。
最初の本人確認ではカテゴリの補助説明・一括操作ボタン・「条件の詳細」について変更の要望を受けました。
この確認終了後も業務4テーブルの全列・全所属は利用前と一致し、その時点のWeb・API・専用DBを停止しました。
3105〜3108・8001・55433番の解放、所有Web・APIプロセスの終了、永続ボリュームと資格情報の保持を確認しました。

#### 本人確認後のUI調整

カテゴリの補助説明2行は、本人の希望に従って各ボタンのツールチップへ移しました。
全選択では分類済みの全カテゴリ、全解除では未分類も対象になる違いを残し、ホバー・フォーカスと説明の関連付けで確認できます。
取得した全カテゴリが選択済みなら全選択を、未定義slugを含めて選択が一つもなければ全解除を無効にしました。
無効なボタンでもホバーで説明を読めます。
「条件の詳細」は画面幅を問わず閉じて開始し、利用者による開閉は条件変更・画面幅変更で維持し、再読み込みでは閉じます。

これらの変更は、修正前に対象5件のassertion失敗を確認し、最小実装後に成功しました。
型生成・型チェック・lint・format確認・本番buildも成功しました。
通常画面テスト153件の全体実行では151件が成功し、詳細が開いている前提だったスクロールテスト2件が失敗しました。
詳細を明示的に開いてからスクロールする前提へ修正し、関連する画面幅4件すべての成功と型・lint・formatを再確認しました。
既存の未定義slugの解除テストも詳細を開いてから操作し、解除・復旧の保証を維持しています。
修正後の実API画面テスト3件も成功し、再照合した専用DBの全列・全所属は利用前と一致しました。

修正後の本番Web・専用API・専用DBで本人が再確認し、カテゴリの選択・解除で一瞬スケルトンが表示されるちらつきについて指摘を受けました。
再確認の終了後も業務4テーブルの全列・全所属は利用前と一致し、今回のWeb・API・専用DBを停止しました。
所有プロセスグループの終了、3105〜3108・8001・55433番の解放、永続ボリュームの保持を再確認しました。
本人の合意に従い、カテゴリ変更の間は直前の一覧を薄く残し、更新前の結果であることを明示する方式へ調整しました。
旧一覧を操作・フォーカス・読み上げから外し、旧件数・ページ情報は高さを保って隠します。
表示の切り替え以外の取得方式は維持し、成功・失敗が確定したら旧一覧を新しい結果へ置き換えます。
対象4件のassertion失敗を確認した後、修正後の対象6件と実API画面テスト3件が成功しました。
型生成・型チェック・lint・format確認・本番buildと、通常画面テスト全155件も成功しました。
旧記事の位置・薄い表示・操作停止、成功時の差し替え、500での旧記事除去、既存のフォーカス・下書き保持を確認しています。
実API検証後も業務4テーブルの全列・全所属は利用前と一致しました。
再確認用の本番Web・API・専用DBで本人が再確認を終え、記事リンクの別画面化と、記事から戻った際の適用済み検索・カテゴリ・ページ条件のリセットについて指摘を受けました。
この再確認後も業務4テーブルの全列・全所属は利用前と一致し、今回のWeb・API・専用DBを停止しました。
所有プロセスグループの終了、3105〜3108・8001・55433番の解放、永続ボリュームの保持を確認しました。

記事タイトルのリンクへ別画面指定と`noopener noreferrer`を追加し、一覧を離れずに記事を開くようにしました。
新しいタブまたはウィンドウで開くことは、リンクの補助説明にも付けています。
別画面指定のassertion失敗を製品修正前に確認し、修正後は別画面表示、`opener`の遮断、参照元の非送信、一覧のURL・履歴・入力中の値・選択・ページの保持を確認しました。
合成記事はローカルの別オリジンへの要求をテスト内で応答し、実サイトやfixtureの記事URLへは接続していません。
「戻る」での適用済み条件のリセットは、修正前の直接URLからの往復と、実際の検索・カテゴリ追加・ページ送り後の往復の両方で再現しませんでした。
この戻る操作のテストは既存動作の回帰確認とし、別画面化のRED／GREENとは区別します。
保存処理・URL復元の実装は変更していません。
型生成・型チェック・lint・format確認・本番buildと、通常画面テスト全157件・専用実API画面テスト3件が成功しました。
実API検証後も業務4テーブルの全列・全所属は利用前と一致しました。
修正後の本番Web・API・専用DBで本人が最終再確認し、記事の別画面表示と元の一覧の適用済み条件・ページ保持について「問題なし」の回答を得ました。
確認終了後も業務4テーブルの全列・全所属は利用前と一致し、今回のWeb・API・専用DBを停止しました。
所有プロセスグループの終了、3105〜3108・8001・55433番の解放、資格情報と永続ボリュームの保持を確認しました。

全変更ファイルを要件・操作仕様・テスト・本人確認の結果と照合してセルフレビューし、必要な修正と関連検証・再レビューを終えました。
Markdownの構造・追加したローカル参照と`git diff --check`を確認し、Phase 6-11のローカル検証・本人確認・文書点検を完了しました。

Issue #114のCR／LF入り直接URLと、PR #112の拒否URL診断の軽微な過剰伏字は既知Lowとして対象外です。
今回の変更の実CI、Supabase・開発DB・実データ・実サイトとOS固有の日本語IME操作は未確認です。
migration・seed・保存・再分類・依存・lockfile・CI基盤・グローバル設定は変更していません。

#### 敵対的レビュー後の修正

カテゴリのツールチップを検索条件パネル内へ描画し、狭い画面でドロワーの背面に隠れる問題を修正しました。
全選択・全解除は完了後の無効状態でもフォーカスを維持し、Enter・Space・クリックによる再実行を停止します。
対象3件のassertion失敗を修正前に確認し、修正後の対象3件と通常画面テスト全160件が成功しました。
型生成・型チェック・lint・format確認・本番build、変更全ファイルのセルフレビューと空白検査も成功しました。
通常検索の公開日入力補助を後続タスクとしていた現行手順も、実装済みの説明へ修正しました。
今回の追加修正では専用実API・DB・本人による再確認とCIは実行せず、応答を制御した画面テストでUIの回帰を確認しました。
テスト用Web・応答サーバーは終了し、手動確認用Web・API・専用DBも停止した状態を維持しています。

続く再レビューで、無効な一括ボタンにフォーカスが残るとEscでドロワーを閉じられない回帰を確認しました。
選択状態による停止を`aria-disabled`と既存の操作ガードで行い、フォーカス維持と重複操作防止を保ちながらEscの標準動作を妨げないよう修正しました。
全選択・全解除それぞれの完了後にEscで閉じて条件トリガーへフォーカスを戻す追加2件は、修正前の閉鎖assertion失敗と修正後の成功を確認しました。
通常画面テスト全162件、型生成・型チェック・lint・format確認・本番build、変更全ファイルのセルフレビューと空白検査も成功しました。
このEsc修正でも専用実API・DB・本人による再確認とCIは実行せず、検証用サーバーの終了と手動確認用サービスの停止状態を確認しています。

#### PRレビュー後の記事リンク説明の調整

記事リンクの`title`属性を削除し、既存の右上矢印と`aria-describedby`で関連付けた「別の画面で開く」の説明で動作を伝えるようにしました。
説明は一覧ごとに用意し、複数の一覧を表示するMockでもIDが重複しないようにしています。
既存の記事リンクテストで`title`不在のassertionが修正前に失敗し、修正後は説明の関連付け・矢印の表示・別画面表示・`opener`遮断・参照元非送信・一覧の条件と下書きの保持が成功しました。
通常画面テスト全162件、型生成・型チェック・lint・format確認・本番build、変更全ファイルのセルフレビューと空白検査も成功しました。
この追加修正では専用実API・DB・本人による再確認と実スクリーンリーダーの実操作は行っていません。
CIの結果は[PR #117](https://github.com/64-HiroByte/press-watch/pull/117)の対象HEADに対するチェックで確認します。

### Next.jsのセキュリティ更新

Next.jsを16.3.8から16.4.1、React / React DOMを19.3.0から19.3.1へ更新しました。
指定はそれぞれ`^16.4.1`・`^19.3.1`とし、lockfileも同じ版へ揃えました。
公式修正条件と採用範囲は[技術構成](tech-stack.md#2026年10月のセキュリティ更新)を参照します。
16.4.2の追加公開も確認しましたが、今回のセキュリティ修正版16.4.1を先行し、公開後待機の例外は追加していません。

秘密ファイル・認証設定・既存依存・生成物を含まない一時Webコピーを使い、外部API・DB資格情報を継承しない環境で更新前後を比較しました。
Node.js 24.21.0・pnpm 12.8.1でfrozen install、型生成・型チェック・lint・format確認・本番buildが成功し、通常画面テストは更新前後とも162件が成功しました。
初回の隔離実行では子プロセスからNode.jsを見つけられなかったため、既存手順どおり、その検証プロセスのPATHへ採用版のNode.js・pnpm本体を指定して再実行しました。
プロジェクト・グローバルのツール設定は変更していません。
この比較検証では、リポジトリ内の既存`node_modules`は再インストールしませんでした。
更新後のマニフェストとlockfileから既存依存を含まない別コピーでもfrozen installが成功し、lockfileが変わらないことを確認しました。
Next.jsに必須でないブラウザー互換データの再解決を避け、PostCSSの上書き、sharp 0.35.5、型定義・UI依存と待機・依存検証の設定を維持しました。

合成データを返す既存の応答制御サーバーを使い、PC 1280×720の一覧、モバイル390×844の一覧とドロワーを比較しました。
文言・配置・タイトル・日本語設定は一致し、画像の差は入力欄・テーマアイコン周辺の微小な画素差に留まりました。
ブラウザーのconsole警告・エラーとpageerrorは発生していません。
通常画面テストでも、検索・カテゴリ・ページ送り・履歴・下書き保持・失敗復旧・フォーカス・記事リンクの既存動作を確認しました。

Web単体Dockerでも、秘密ファイル・既存依存・生成物を含まないbuild contextと既存Dockerfileを使いました。
Linux arm64で依存再現・型生成・型チェック・本番buildが成功し、同じコンテナ内の応答制御サーバーに接続した本番Webを、ループバック限定で公開してPC・モバイルの表示を確認しました。
macOS arm64・Linux arm64の両方でNext.jsが使うsharp 0.35.5の読み込みとPNG生成が成功しました。
Next.jsの同梱RSC実装の更新、更新パッケージの版・出典・ライセンス表示を照合し、第三者表示の該当箇所を更新しました。

続いて通常の作業フォルダでもfrozen installを行い、実際のNext.js 16.4.1・React / React DOM 19.3.1とsharp 0.35.5の読み込みを確認しました。
以前のページ配置を参照する生成型が残って初回の型チェックが失敗したため、`.next`と`tsconfig.tsbuildinfo`を退避して生成し直しました。
型生成・型チェック・lint・format確認・本番buildと通常画面テスト162件が成功し、画面テスト後の型チェックも成功しました。
lockfileは変わらず、`next-env.d.ts`・`tsconfig.json`にも最終差分はありません。

検証用Web・応答制御サーバーを終了し、今回作成したDockerコンテナ・イメージを削除して3105〜3108番の解放を確認しました。
実API・DB・外部記事への接続、本人による手動確認、実CI・本番反映は行っていません。
commit・push・ドラフトPR作成は承認Bの対象であり、その後のCIは最新HEADのjob・step・skip・ログとrun URLを確認します。

### UI基盤の確認

開発サーバーをループバックに限定して起動し、`http://127.0.0.1:3000/ui-foundation`を開く。
このページはdevelopment限定で、productionの通常ソースでは404になる。
基本部品・テーマの採用版、出典と更新手順は[UI基盤](frontend-ui.md)を参照する。

- 日本語の文言・入力とラベルの関連付け、Button・Input・Checkbox・Native Selectの無効状態を確認する。
- Tabの移動とフォーカス表示、CheckboxのSpace操作、Native Selectの選択を確認する。
- ライト・ダーク・システム追従を切り替え、再読込後も選択が保持されることを確認する。
  システム追従時は現在のOS設定と表示を照合する。
- Paginationは表示だけの見本で、クリックしてもURLや現在ページが変わらないことを確認する。
- ブラウザ・サーバーのエラーとhydration警告、`/third-party-notices.txt`の表示を確認する。

通常ソースのproduction確認は、型生成・型チェック・ビルドの後に次を実行する。

```bash
pnpm --filter @press-watch/web start --hostname 127.0.0.1
```

productionで7部品を確認する時は、秘密ファイル・既存依存・生成物を含まない一時コピーを作る。
そのコピーだけで確認ページのdevelopment判定と`notFound()`呼び出しを外し、frozen install・型生成・型チェック・build/startを行う。
納品ソースにはこの変更を取り込まず、通常ソースのproductionで404になることも別に確認する。
Dockerでは既存のWeb DockerfileとCorepack経路を使い、新規コンテナ内で検証した後、同じコンテナ内の本番ビルドを`start --hostname 0.0.0.0`で起動する。
ホスト側は`127.0.0.1`へ限定して公開し、確認後に今回作成したリソースだけを片付ける。
Dockerの開発画面は`http://localhost:<公開ポート>/ui-foundation`で開く。
コンテナ内を`0.0.0.0`で起動した場合、閲覧先の`127.0.0.1`はNext.jsの開発リソースのorigin制限に拒否されるため、ループバック公開を維持して`localhost`を使う。

### 一覧Mockの確認

[Web単体の起動手順](#フロントエンドを単体で起動する)でループバック限定の開発サーバーを起動し、`http://127.0.0.1:3000/mock`を開く。
別ポートを指定した場合は、そのポートへ読み替える。
Mockはdevelopment限定で、productionでは404になる。
Phase 6-3の検証は、秘密ファイル・既存依存・生成物を含まない一時コピーで行う。
採用した画面構成は[一覧UIの採用方針](frontend-ui.md#一覧uiの採用方針)を参照する。

- 「表示状態」で通常・ローディング・取得失敗・データなし・検索結果なしを切り替える。
- ライト／ダーク、標準／大きめ文字、長いタイトル・カテゴリ名、カテゴリなしの表示を確認する。
- キーワード・公開日は検索ボタン、カテゴリは選択時にヘッダーの条件表示が更新される。
  カテゴリ変更では未検索の入力値を反映しない。
  検索リセットは入力欄と適用済みのキーワード・公開日だけをクリアし、カテゴリ全選択・全解除はカテゴリだけを変更する。
  ドロワー内で解除しても閉じず、それぞれ他方の条件を維持することを確認する。
  一覧・件数・ページ位置・URLは固定のままで、実際の絞り込みは行わない。
- PCの固定サイドバー・ヘッダーと一覧スクロール、狭い画面のドロワー、検索条件詳細の開閉を確認する。
  幅767／768px、低い画面高さ、拡大表示でも内容に届くことを確認する。
- Tab・Space・Enter・Escape、フォーカス表示、ツールチップ、ブラウザ・サーバーのエラーを確認する。

テーマは再読み込み後も保持し、文字サイズは標準へ戻る。

### CursorでのTypeScript 7の型支援

Cursor 3.23.12（VS Code基盤1.128.0）で、Microsoft公式の[TypeScript 7拡張](https://marketplace.visualstudio.com/items?itemName=TypeScriptTeam.native-preview)1.0.1を確認しました。
拡張機能IDは`TypeScriptTeam.native-preview`で、必要なVS Code基盤は1.126.0以上です。
通常の型支援には拡張機能と言語サーバーが必要であり、CLIの更新だけでは切り替わりません。

PressWatchをルートとして開き、拡張の導入前に既存の`.vscode/settings.json`へ次を追加します。
既存のcSpell・Markdown設定は維持し、ユーザー全体の設定へ追加しません。
`.vscode/`はGit管理外のため、他の開発環境ではこの手順を実施します。

```json
{
  "js/ts.experimental.useTsgo": true,
  "js/ts.tsdk.path": "./apps/web/node_modules/typescript"
}
```

拡張を初めて導入する際は、ほかのCursorウィンドウをすべて閉じ、設定済みのPressWatchで導入・初回起動を完了してから開き直します。
設定のない別のワークスペースで先に初回起動すると、ユーザー全体の`js/ts.experimental.useTsgo`が自動で有効になる場合があります。
信頼済みのPressWatchワークスペースでTS・TSXを開き、プロジェクト版を使用する通知が出たら`Allow`を選択します。
通知が出ない場合や選択し直す場合は、コマンド`TypeScript: Select TypeScript Version...`で`Use Workspace Version`からPressWatchのプロジェクト版を選択します。
言語の状態から7.0.2と`apps/web/tsconfig.json`を確認し、Outputの`TypeScript 7`で`Resolved to`がプロジェクト内の`node_modules/.pnpm/@typescript+typescript-<platform>@7.0.2/`配下を指すことも確認します。
拡張同梱版も7.0.2のため、表示された版だけではプロジェクト版を使用している証拠になりません。

2026年10月2日に、macOS arm64のプロジェクト版を使い、TypeScript・TSXで文字列メソッドの補完、型の不一致の診断（TS2322）、定義への移動を確認しました。
一時的な検証ファイルは削除し、診断が解消したことと、ユーザー全体のTypeScript設定を変更していないことも確認しました。
拡張1.0.1とコンパイラー7.0.2の組み合わせでは、Outputに`custom/setContentMapperContributions`の`InvalidRequest`警告が出ましたが、上記の型支援は動作しました。
この警告だけを理由にコンパイラーや拡張の版を変更せず、将来の拡張更新時に連携機能を再確認します。

TypeScript 7では従来の言語サービスプラグインが動作せず、`tsconfig.json`のNext.jsプラグインによる固有の診断・補完は利用できません。
Next.jsビルドのCLI経路でも、Next.js独自の診断表示は利用できません。
通常のTypeScript・Reactの型チェックは維持し、型エラーを無視する設定は追加しません。

## API を単体で起動する

API だけを確認したい場合は、API 側のディレクトリで依存関係を同期して起動します。

```bash
cd apps/api
uv sync
DATABASE_URL=postgresql+psycopg://presswatch:your-local-postgres-password@127.0.0.1:5432/presswatch uv run fastapi dev src/press_watch_api/main.py
```

`fastapi` コマンドをグローバルにインストールするのではなく、`uv run` で API 用の仮想環境内のコマンドとして実行します。
API 単体起動で PostgreSQL に接続する処理を確認する場合は、Docker Compose の公開ポートに合わせて host を `127.0.0.1` にした `DATABASE_URL` を指定します。

別ターミナルから API のルートエンドポイントを確認します。

```bash
curl http://127.0.0.1:8000/
```

確認後、リポジトリルートへ戻ります。

```bash
cd ../..
```

Docker Compose で全体を起動する場合、この単体起動は必須ではありません。単体起動したまま Docker Compose を起動すると、ポート `8000` が重複することがあります。

## 一覧APIで固定カテゴリを絞り込む

APIが起動し、対象DBに既存の固定カテゴリmigrationが適用されていることを前提とします。
絞り込み結果を得るにはカテゴリ定義と分類結果が必要です。
カテゴリ未指定でも記事の所属を返すため、固定カテゴリの関連テーブルが必要です。
API要求は自動でmigration・seed・再分類を実行しません。
開発DB・Supabaseへの適用と実データの再分類は、この機能の実装検証には含めていません。

次の例は、大気または土壌に分類され、タイトルに「調査」を含む報道発表の1ページ目を取得します。

```bash
curl --get 'http://127.0.0.1:8000/press-releases' \
  --data-urlencode 'fixed_category=air' \
  --data-urlencode 'fixed_category=soil' \
  --data-urlencode 'q=調査' \
  --data-urlencode 'page=1' \
  --data-urlencode 'page_size=10'
```

`fixed_category`はslugで指定し、複数の場合は同名クエリを繰り返します。
カンマ区切りは受け付けません。
20指定まで、各値は100文字までで、上限は前後空白・空要素・重複の除去前に適用します。
前後空白を除去した空要素と重複は除外し、全要素が空ならカテゴリ絞り込みを行いません。
不正形式や上限超過は422、形式が正しい未定義slugは一致なしとして扱います。
詳しい入力契約は[REQ-013](requirements.md#req-013-検索絞り込みに対応したapiを提供すること)を参照してください。

カテゴリ未指定なら未分類も対象になります。
複数カテゴリに一致する報道発表も1件として数え、`pagination`は絞り込み後の総件数と総ページ数を返します。
カテゴリ定義が未投入なら指定ありの結果は0件ですが、テーブル未適用などのDB障害は既存の500・503応答になります。

各記事の`fixed_categories`は、保存済みの全所属を`display_order`昇順で返します。
検索で指定したカテゴリ以外の所属も含み、所属なしは`[]`です。
要素は`slug`・`name`だけで、数値ID・`display_order`・分類キーワードは公開しません。
既存の`title`・`source_url`・`published_at`・`source_categories`を維持し、取得元カテゴリが`null`の場合もそのまま返します。

```json
{"title":"調査結果の公表","source_url":"https://example.test/press/1","published_at":"2026-01-01","source_categories":null,"fixed_categories":[{"slug":"soil","name":"土壌"},{"slug":"air","name":"大気"}]}
```

定義・所属が未登録でも、カテゴリ未指定の一覧とタイトル検索は利用でき、記事の所属は`[]`になります。
DB障害を空配列へ置き換えず、所属取得にも既存の500・503、Session終了・例外優先順位・秘匿診断を適用します。
API要求はCSV読込み・タイトル分類・DB更新を行いません。
この所属情報とN+1防止の確認は、合成データを使う[テスト専用PostgreSQL 17](#postgresql-17-db統合テストを実行する)で行っています。

## 一覧APIで公開日を絞り込む

APIが起動し、対象DBに既存migrationが適用されていることを前提とします。
次の例は、公開日が2026年1月2日から4日までの報道発表を、タイトルと固定カテゴリの条件と組み合わせて取得します。

```bash
curl --get 'http://127.0.0.1:8000/press-releases' \
  --data-urlencode 'published_from=2026-01-02' \
  --data-urlencode 'published_to=2026-01-04' \
  --data-urlencode 'q=調査' \
  --data-urlencode 'fixed_category=air' \
  --data-urlencode 'fixed_category=soil' \
  --data-urlencode 'page_size=10'
```

`published_from`・`published_to`は任意のクエリで、ASCIIの`YYYY-MM-DD`に完全一致する実在日を指定します。
保存済み原本の`published_at`へ照合し、両端の当日を含みます。
同じ日を両側へ指定するとその当日だけを対象にします。
下限だけならその日以降、上限だけならその日以前、両方未指定なら公開日を制限しません。
空文字列・前後空白・時刻付き・桁不足・実在しない日付は422です。
下限が上限より新しい場合も422となり、エラー位置は`["query", "published_to"]`です。
APIでは日付の入れ替えや今日・最古日の補完を行いません。
Webでは通常検索・URL復元・不正条件の修正時に日付を正規化します。
実装済みの期間選択と日付入力の仕様は[公開日の入力補助](frontend-ui.md#公開日の入力補助)を参照してください。

日付・タイトル・カテゴリの条件はANDで組み合わせ、カテゴリ間はORです。
件数と一覧へ同じ条件を適用し、絞り込み後に公開日・IDの降順でページを分割します。
0件・超過ページは200と空の`items`を返し、要求ページを保持します。
各記事の公開項目・全所属・表示順、照会上限とDB非更新、既存のエラー処理・Session管理を維持します。
詳しい契約は[公開日範囲検索](requirements.md#phase-6の公開日範囲検索)を参照してください。
日付境界の実DB確認は、合成データを使う[テスト専用PostgreSQL 17](#postgresql-17-db統合テストを実行する)で行っています。
開発DB・Supabase・実データ・常設の接続検証DBは、この検証には含めていません。

## 固定カテゴリの選択肢を取得する

APIが起動し、対象DBに既存の固定カテゴリmigrationが適用されていることを前提とします。
`GET /fixed-categories`は保存済み定義だけを取得し、分類キーワードや記事・分類結果は不要です。
API要求はCSV読込み・migration・seed・再分類・データ更新を行いません。

```bash
curl 'http://127.0.0.1:8000/fixed-categories'
```

応答は次の形式で、`items`を保存済みの`display_order`昇順で返します。
数値IDや分類キーワードは公開しません。

```json
{"items":[{"slug":"air","name":"大気","display_order":1}]}
```

定義が未登録ならHTTP 200と`{"items":[]}`を返し、CSVで補完しません。
テーブル未適用・権限不足・接続障害は正常0件へ置き換えず、既存の500・503応答を返します。
共通処理によるSession終了・例外優先順位・固定アプリ診断を使用し、想定外例外やDTO検証失敗は既定の500と`text/plain`を維持します。
詳しい契約は[REQ-014](requirements.md#req-014-固定カテゴリの選択肢を取得できること)と[共通エラー方針](requirements.md#一覧検索apiのエラー応答)を参照してください。

表示順・正常0件・1 SELECT・DB非更新の実DB確認は、合成データを使う[テスト専用PostgreSQL 17](#postgresql-17-db統合テストを実行する)で行っています。
開発DB・Supabaseへの固定カテゴリmigration・seedの適用と実データの再分類は[未確認](db-migrations.md#実行方針)です。
定義0件でも既存APIの未絞り込み一覧・タイトル検索は利用できます。
Webは成功した一覧と条件を保持して「カテゴリ選択肢が未登録」と表示し、条件変更を止めて再取得を可能にします。

## API unittestを実行する

API unittestは実際のPostgreSQLを起動せずに実行できます。

```bash
cd apps/api
PYTHONPATH=src uv run --locked python -m unittest discover -s tests
cd ../..
```

`apps/api/tests/`の取得・保存コマンドのテストは、次の責務ごとに分けています。

| テストファイル | 確認する内容 |
| --- | --- |
| `test_fetch_and_save_command.py` | 引数検証、DB設定、取得失敗の診断 |
| `test_fetch_and_save_transaction.py` | Sessionの管理、commit・rollback・close、commit後の出力 |
| `test_fetch_and_save_scraper.py` | scraperの子プロセス、JSON復元、stdout・stderr、一時ファイル |

特定のファイルだけ実行する場合も、`discover`にファイル名を指定します。

```bash
cd apps/api
PYTHONPATH=src uv run --locked python -m unittest discover -s tests -p 'test_fetch_and_save_transaction.py'
cd ../..
```

## scraper unittestを実行する

scraperのテストはAPIと別のディレクトリで実行します。

```bash
cd packages/scraper
PYTHONPATH=src uv run --locked python -m unittest discover -s tests
cd ../..
```

`packages/scraper/tests/`のCLIテストは、次の責務ごとに分けています。

| テストファイル | 確認する内容 |
| --- | --- |
| `test_cli.py` | 基本実行、引数検証 |
| `test_cli_archive.py` | 月別巡回、停止条件、rate limiterの共有 |
| `test_cli_output.py` | 出力保存、進捗、stdout抑制、エラー時の診断と出力ファイルの保持 |
| `test_cli_crawl_state.py` | 巡回stateの保存、再開、検証、削除 |

共通helperは`cli_test_support.py`に置き、各責務だけで使うhelperはそのテストファイルに残しています。
個別実行では、巡回stateのテストも含めて`discover`にファイル名を指定します。

```bash
cd packages/scraper
PYTHONPATH=src uv run --locked python -m unittest discover -s tests -p 'test_cli_archive.py'
cd ../..
```

## CIの実行範囲と必須チェック

`.github/workflows/api-tests.yml`は、PRと`main`・Phaseブランチへのpushで動きます。
すべての変更で`git diff --check`を実行し、変更ファイルに応じてPythonテストを実行または省略します。

空白検査は、PRではbaseとの差分、既存ブランチへのpushではpush前との差分、新規ブランチの初回pushでは空ツリーとの差分を比較します。
空ツリーとの比較では既存ファイルの全行が追加扱いになるため、普段の差分に含まれない既存行も検査対象になります。
2026年9月30日の新規Phaseブランチ公開では、この比較により以前から存在するMarkdownの末尾2スペース5行が検出されました。
既存文書の強制改行を変更せずに検査との不整合を解消するため、Markdown用のパス別ルールを採用します。

空白検査のパス別ルールは、ルートの`.gitattributes`でローカルとCIに共有します。
Markdown（`*.md`）は、末尾2スペースによる強制改行を維持するため、`whitespace=-blank-at-eol`で行末空白を許容します。
この設定は2スペースだけに限定せず、1スペース・タブ・コードブロック内を含むMarkdownの行末空白全般に適用されます。
Markdownでも、末尾に追加された空行、インデント内のスペース直後のタブ、競合マーカーは引き続き検出します。
Markdown以外のファイルでは、行末空白の検査も維持します。
詳細は[Gitのwhitespace属性](https://git-scm.com/docs/gitattributes#_checking_whitespace_errors)を参照してください。

| 変更内容 | API unittest・Scraper unittest・PostgreSQL integration |
| --- | --- |
| Markdown（`*.md`）のみ | 3種類とも省略 |
| `apps/web/**`、ルートの`package.json`・`pnpm-lock.yaml`・`pnpm-workspace.yaml`、`infra/docker/web.Dockerfile`のみ | 3種類とも省略 |
| 上記のファイルだけを組み合わせた変更、または差分なし | 3種類とも省略 |
| 上記以外を一つでも含む変更 | 3種類とも実行 |

API・scraperのコード、テスト、Python依存、migration、固定カテゴリCSV、workflow、共有設定は実行対象です。
`.gitattributes`や`.editorconfig`の変更も共有設定として、Pythonテスト3種類の実行対象です。
改名では移動元の削除も判定するため、Pythonファイルを省略対象のパスへ移してもテストを実行します。
API unittestには実際のscraper子プロセスを使う確認があるため、Python内の実行範囲は分割していません。
省略対象の設定をPythonでも使うようにした場合は、変更判定も見直してください。

省略時、API・scraperジョブは理由を表示して成功し、Python環境の構築とテストstepを省きます。
DB統合ジョブはジョブ全体を省略するため、PostgreSQLサービスも起動しません。
変更判定や空白確認が失敗した場合、または判定結果が`true`・`false`以外の場合は、API・scraperジョブを失敗させます。
必須チェックが未報告になることを避けるため、workflow全体を`paths`などで省略する構成にはしません。

実行時のコマンドは、この文書のAPI unittest・scraper unittest・PostgreSQL 17 DB統合テストの手順と同じです。
CIのDB統合テストはGitHub Actions内の一時的なPostgreSQL 17を使い、開発DBやSupabaseには接続しません。
通常CIでは実データスナップショット検証1件をskipします。
確認結果は成功とskipを分けて記録し、CI全体の成功だけで製品テストを実行済みとは判断しません。

PRでは最新コミットだけでなく、baseからのPR全体の差分を判定します。
workflow変更を含むPRに文書だけのコミットを追加しても、Pythonテスト3種類は実行対象のままです。
workflow変更を含むPRでは3種類の実行経路を確認し、省略経路は変更を取り込んだPhaseブランチをbaseにした別のPRで確認します。
Phase 6-5の実行経路はPR #102とマージ後push、省略経路は文書のみのPR #103で確認済みです。
タスクブランチへのpush自体はworkflowの起動対象ではないため、pushだけで省略経路を確認することはできません。

### Web CIの実行範囲

`.github/workflows/web-checks.yml`はPRと`main`・Phaseブランチへのpushで起動します。
workflow全体にパス条件を付けず、変更判定と空白検査を実行してからWeb検証の実行・省略を決めます。
比較範囲は既存Python CIと同じくPR全体、push前後、新規ブランチは空ツリーとの差分です。
`.github/scripts/web-checks-required.sh`はNUL区切りと`--no-renames`で削除・改名元も判定します。

| 変更内容 | Web検証 |
| --- | --- |
| Markdown（`*.md`）のみ | 理由を表示して省略 |
| `apps/web/**`のMarkdown以外 | 実行 |
| ルートのマニフェスト・lockfile・workspace、Oxc設定、`.editorconfig`・`.gitattributes` | 実行 |
| workflow・CI判定スクリプト・Web Dockerfile | 実行 |
| Python専用変更、その他上記の実行対象を含まない変更、差分なし | 理由を表示して省略 |

実行対象を一つでも含むと、Ubuntu 24.04、Node.js 24.21.0、pnpm 12.8.1でfrozen install、型生成、型チェック、lint、format確認、ビルド、Chromium画面テストを順に実行します。
ChromiumのLinux依存はActions内で取得し、ブラウザーとテスト生成物はルートの`tmp/playwright/`へ保存します。
画面テスト失敗時のtrace・スクリーンショットは`playwright-diagnostics` artifactで7日間保持する設定です。
[PR #112の初回Web CI](https://github.com/64-HiroByte/press-watch/actions/runs/38200939844)で、失敗時の保存stepの成功と`playwright-diagnostics` artifactの生成を確認済みです。
成功runではこのstepが省略されます。
変更判定や空白検査の失敗、不正な判定出力を成功や省略へ置き換えません。
新しくWebで使う共有設定や別のソース配置を追加した場合は、変更判定の対象も見直します。

新規workflow・ルートOxc設定・CI判定スクリプトの変更は、既存Python CIのAPI・scraper・一時PostgreSQLも実行対象にします。
実CI確認では対象SHA、実行step、実行・省略理由を確認し、ローカルの判定確認だけで実CIも確認済みとは扱いません。
実行経路はPR #102とマージ後pushで確認済みです。
省略経路は、統合済みの`phase-6/frontend`をbaseとする文書のみのPR #103で確認済みです。
commit・push・PR作成・マージ、GitHubの必須チェック・ruleset変更には、それぞれ定めた承認が必要です。

### 必須チェックの段階適用

テストの実行と、失敗時にマージを止めるGitHub rulesetの設定は別に管理します。
集約ジョブは追加せず、既存のジョブ名を個別に必須チェックへ指定しています。

| 対象・適用時期 | 必須チェック | 適用状況 |
| --- | --- | --- |
| `main` | `API unittest`・`Scraper unittest`・`PostgreSQL integration` | [protect-main](https://github.com/64-HiroByte/press-watch/rules/17208440)で適用済み |
| `phase-5/api` | `API unittest`・`Scraper unittest`・`PostgreSQL integration` | [protect-phase-5-api](https://github.com/64-HiroByte/press-watch/rules/24108046)で適用済み |

2026年9月28日にmainのscraper必須化とPhaseの3チェック必須化を適用しました。
2026年9月29日に[統合PR #91](https://github.com/64-HiroByte/press-watch/pull/91)でDBテストの報告・実行・成功と、他にmain向けのopen PRがないことを確認し、mainへDB統合の必須チェックを追加しました。
変更直前のrulesetを保存し、変更後にrulesetと各ブランチの適用ルールを再取得して、対象条件・必須チェック・提供元・例外設定を確認しました。
`protect-main`の対象はデフォルトブランチ（`~DEFAULT_BRANCH`、現在は`main`）で、DBチェック追加以外の既存設定は維持しています。
`protect-phase-5-api`は`refs/heads/phase-5/api`だけを対象とし、PR経由と3チェックを要求します。
削除禁止とforce push禁止は`main`の既存設定を維持し、Phase専用rulesetには追加していません。
将来のPhaseブランチへの適用は、各Phaseの開始時に確認します。

両rulesetは`active`で、対象の除外とbypass actorは空です。
すべての必須チェックの提供元はGitHub Actions（`integration_id: 15368`）です。
PRの必須レビュー数は0で、CODEOWNER承認・最終pushの承認・会話解決の要求と、古い承認の取り消しは無効です。
指定レビュアーは空で、マージ方式は`merge`・`squash`・`rebase`を許可しています。
最新baseへの追従義務（`strict_required_status_checks_policy`）とブランチ作成時のチェック免除（`do_not_enforce_on_create`）は、ともに`false`です。
最新化を必須にしていないため、baseが更新された後の組み合わせまで常に検証する保証はありません。
Phase 5のmain統合前には、PRのhead SHAに加え、CIがcheckoutしたマージ結果のSHAとその親コミットを確認し、最新のmain・Phaseの組み合わせを検証できていることを確かめます。
一致しない場合は統合を止め、現在の組み合わせを検証する方法と必要な追加承認を確認します。
[既存runの再実行](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)は元のSHAとrefを使用するため、base更新後の組み合わせを確認した証拠にはなりません。

2026年9月29日の設定確認時点では、mainへのDB統合workflowの取り込みは統合PR #91のマージ待ちでした。
DB統合ジョブを含まないmain向けPRは必須チェックが未報告になるため、設定変更前に既存PRへの影響を確認しています。
文書反映後の最新先端に対する製品テストと検証対象の照合は、main統合前の最終確認として行います。
設定結果と統合待ちの状態は[タスク一覧](tasks.md#読み取りapi)に記録しています。
CI見直しの完了とPhase 5全体の完了・main統合は区別します。

### 実行経路と省略経路の確認状況

#### Phase 6-5の確認実績

PR #102とマージ後のPhaseへのpushについて、各jobのstepとログを確認しました。
job全体の成功だけでなく、検証stepが実行されて成功し、Web・API・scraperの省略通知stepは実行されなかったことを確認しています。

| 対象 | head SHA | 実CI |
| --- | --- | --- |
| PR #102 | `71772f2ae12ab80618ff5e3b1490c9aa44df1308` | [Web checks](https://github.com/64-HiroByte/press-watch/actions/runs/37645292645)・[Python tests](https://github.com/64-HiroByte/press-watch/actions/runs/37645292413) |
| マージ後の`phase-6/frontend`へのpush | `af34c0d875741b0d12aef098a796de40285b8b76` | [Web checks](https://github.com/64-HiroByte/press-watch/actions/runs/37649495029)・[Python tests](https://github.com/64-HiroByte/press-watch/actions/runs/37649495024) |
| PR #103（文書のみ・検証省略） | `703b3fce4f26ce0725a3d86d31bb316091e6a647` | [Web checks](https://github.com/64-HiroByte/press-watch/actions/runs/37734517894)・[Python tests](https://github.com/64-HiroByte/press-watch/actions/runs/37734517872) |

PR #102の各jobがcheckoutしたマージ結果は`81dc6b8a0f0c6127df3de212e952bb1787c70f17`です。
その親は当時のbase `2ef556f82fc59f74d5519ad5ba940d243944f7f6`と上記のPR headに一致し、変更判定・空白検査はbaseからこのマージ結果までを比較しました。
マージ後pushの各jobは実際のマージコミット`af34c0d875741b0d12aef098a796de40285b8b76`をcheckoutし、push前の`2ef556f82fc59f74d5519ad5ba940d243944f7f6`から比較しました。
両比較範囲にはworkflow・CI判定スクリプト・Webソース・依存の変更が含まれるため、WebとPythonの両方が実行対象です。

- Webでは変更判定・空白検査、frozen install、型生成・型チェック、lint、format確認、本番ビルド、ChromiumとLinux依存の導入、画面テストの各stepが成功しました。
  両runのログでlintの警告・エラー0件、format適合、Playwrightの3テスト成功を確認しました。
  CLIと同じ共通scripts・Oxc設定を参照し、format確認の対象にMarkdownを含めていません。
- PythonではAPI・scraper・PostgreSQL統合のテストstepが省略されずに実行され、成功しました。
  両runのログでAPI 256件成功、scraper 138件成功、DB統合64件中63件成功・1件skipを確認しました。
  DBのskipは専用runnerでだけ実行する実データスナップショット検証であり、通常CIの対象外です。
- 画面テストの保証範囲はMock表示と本番`/mock`の404であり、API接続・検索の製品動作は確認していません。
  失敗時artifactアップロードは実CIでは未確認で、上記の成功runでは該当stepが省略されました。
- 同構成の省略経路は、`phase-6/frontend`をbaseとする文書のみの[PR #103](https://github.com/64-HiroByte/press-watch/pull/103)で確認しました。
  変更判定jobがcheckoutしたマージ結果は`8de12e7006bee5c81caeed4e555ad81598b30558`で、その親はbase `af34c0d875741b0d12aef098a796de40285b8b76`と上記のPR headに一致しました。
  両workflowの空白検査・変更判定はこのbaseからマージ結果までを比較し、差分が3つのMarkdownのみのためWeb・Pythonとも検証不要と判定しました。
  Webの`Detect Web changes`と空白検査、`Skip Web validation`は成功し、Web validationのcheckout・環境準備・依存取得・型生成・型チェック・lint・format確認・ビルド・Chromium導入・画面テストは省略されました。
  Pythonの`Detect changes`と空白検査、`Skip API unit tests`・`Skip scraper unit tests`は成功し、API・scraper検証jobのcheckout・Python／uvの環境準備・テストstepは省略されました。
  PostgreSQL integrationはjob全体が省略され、runner未割当・stepなしで、PostgreSQLサービスも起動していません。
  Web validation・API unittest・Scraper unittestの成功は省略通知の正常終了であり、製品テストを実行して成功した結果ではありません。
  上記の証拠runはDocs追記前のheadを対象とし、追記後の最新headのCI確認はPRと最終報告で別に示します。
- 文書のみのPRを省略経路の代表例とし、すべての変更組合せを実CIで確認したとは扱いません。
  既存のローカル変更判定16ケースの確認は、実CIの証拠と分けて再利用します。

ローカルでは、秘密ファイルを含めない一時環境でfrozen install・型生成・型チェック・lint・format確認・ビルド・画面テスト3件の成功を確認しています。
型・lint・format・画面テストの負例と、lint例外の対象外で6ルールすべてが違反を検出することも確認済みです。
検証用ファイルを削除した後の成功も確認しています。

#### Phase 5の確認実績

- main向け[統合PR #91のCI](https://github.com/64-HiroByte/press-watch/actions/runs/36440452446)を2026年9月29日に確認しました。
  対象のPhase先端は`780937b1f9dcb5123ebecf01f5dd8f8ad4a15fa1`で、API 256件成功、scraper 138件成功、DB統合64件中63件成功・1件skipを実ログから確認しました。
  各テストstepは実行されて成功し、DBのskipは通常CIの対象外である実データスナップショット検証です。
  全ジョブがcheckoutしたマージ結果は`23833c1fc4ed8e26bd7604adb87e21de59a61a34`で、親コミットはmainの`b9ed483b17b9c496d36090d8693cd14303a0be4f`と上記のPhase先端に一致しました。
  設定変更後に`gh pr checks 91 --required`で3種類が必須として認識され、この統合PRのCIが3種類とも成功していることを確認しました。
- 実行経路は[PR #87のCI](https://github.com/64-HiroByte/press-watch/actions/runs/36388456975)で、API・scraper・DB統合のテストstepの実行と成功を確認済みです。
  前タスクで確認した件数は、API 256件成功、scraper 138件成功、DB統合64件中63件成功・1件skipです。
  DB統合のskipは通常CIで意図した実データスナップショット検証です。
- 文書専用変更の省略経路は[PR #88のCI](https://github.com/64-HiroByte/press-watch/actions/runs/36410395503)（先端`eb5225d`）で確認済みです。
  空白確認・変更判定は成功し、API・scraperは省略stepが成功、Python・uvのセットアップとテストstepはskipでした。
  DB統合はジョブ全体がskipし、runner未割当・stepなしのためPostgreSQLサービスも起動していません。
  `gh pr checks 88 --required`で3ジョブが必須として認識され、API・scraperの成功とDB統合のskipでチェック条件を満たすことを確認しました。
  下書き状態によるマージ制約と、必須チェックの成否を分けて確認しました。
  以後の追記コミットでも、push後に最終的なPR先端に対応するチェックを確認します。
- フロントエンド専用変更の判定は、前タスクのローカル検証を再利用します。
  今回実CIで直接確認する範囲は文書専用変更です。

## 固定カテゴリの初期データを取り込む

固定カテゴリ用migration `a51eab6808f3`が適用済みで、対象DBの`DATABASE_URL`を環境変数へ設定済みであることを前提とします。
seed CLIはmigrationや`.env`の読込を行いません。
開発DBとSupabaseへの固定カテゴリmigration適用・seed実行は、この実装の検証には含めていません。

```bash
cd apps/api
PYTHONPATH=src uv run --locked python -m press_watch_api.commands.seed_fixed_categories
cd ../..
```

APIパッケージに同梱したカテゴリ定義CSVとキーワードCSVだけを使い、入力ファイルを指定する引数はありません。
`--help`はDBへ接続せずに表示できます。
CSV検証規約は`docs/fixed-categories.md`を参照してください。

初回投入では、stdoutへ次のJSONを出力します。

```json
{"categories_added": 10, "keywords_added": 57}
```

同一状態の再実行は両件数が0で成功し、同一定義の不足がある場合は不足分だけを追加します。
CSVにないカテゴリ・キーワードや、同一slugの表示名・表示順の相違がある場合は失敗し、既存データを上書き・削除しません。
報道発表の原本データと分類結果も変更しません。

終了コードは成功・ヘルプ表示が0、CSV・DB・入出力の実行失敗が1、引数不正が2です。
失敗時はstderrへ`operation`、`commit_succeeded`、固定の理由を出し、CSVの規約違反では固定ファイル名・行番号・列名も補足します。
引数不正も`operation=arguments`の固定形式で診断し、引数の値、CSVの入力値、DB例外の詳細、SQL、接続文字列は診断に含めません。
ヘルプの出力や引数エラーの診断で入出力に失敗した場合も、終了コード1を返します。

`commit_succeeded=true`で出力やSession終了処理が失敗した場合、DBへのcommitは済んでいます。
`commit_succeeded=false`はcommit成功を確認できていないという意味であり、commit中の通信失敗などでDBが未変更と断定するものではありません。
出力先や接続障害を解消した後に再実行して、同一状態または不足分の追加として確認できます。

不整合の診断が出た場合は、対象DBと同梱CSVの組合せを確認してください。
意図した分類ルールの変更はseedの再実行で上書きせず、CSV変更・DB更新・再分類を扱う別の保守作業とします。
seedは単独で実行し、同時実行による制約エラーでは先行処理の完了後に再実行してください。

## 既存報道発表を固定カテゴリで再分類する

固定カテゴリ用migrationが適用済みで、対象DBのカテゴリ・キーワードが同梱CSVと完全に一致することを前提とします。
対象DBの`DATABASE_URL`を環境変数へ設定し、新規保存・別の再分類・原本や定義を変更する処理を停止してから実行します。
同時実行の停止は運用側の責任であり、CLIによる検出や排他ロックはありません。
開発DB・Supabaseへの適用と実データへの実行は、この実装の検証には含めていません。

```bash
cd apps/api
PYTHONPATH=src uv run --locked python -m press_watch_api.commands.reclassify_fixed_categories
cd ../..
```

引数なしで、未分類を含む保存済み報道発表の全件を再分類します。
対象を限定する引数はなく、`-h`・`--help`だけを提供します。
ヘルプ・引数不正ではCSV読込やDB初期化を行いません。
CLIは`.env`読込、migration適用、自動seed、原本の再取得を行いません。

既存のタイトル分類を再利用し、原本を保持したまま分類結果だけを削除・再作成します。
対象0件でもルール検証を行い、定義が正しければすべての件数が0で成功します。
処理全体を一つのトランザクションに含め、1,000件ずつ処理してもcommitは最後の1回だけです。
新規保存時の重複skipは再分類を行わず、従来どおり既存行を保持します。

成功時はcommit後にstdoutへJSONを出力します。
次の例は、3件を判定し、2件が1カテゴリ以上に一致して、合計3組の分類結果になった場合です。

```json
{"processed_count": 3, "matched_count": 2, "classification_count": 3}
```

`processed_count`は判定した報道発表数、`matched_count`は1カテゴリ以上に一致した報道発表数、`classification_count`は置換後の報道発表・カテゴリの組数です。
いずれも変更前との比較件数ではなく、未一致の報道発表数は`processed_count - matched_count`です。

終了コードは成功・ヘルプが0、実行失敗・捕捉した中断が1、引数不正が2です。
ヘルプや引数診断の出力失敗も1になります。
stderrには`operation`、`commit_succeeded`、固定の理由を出し、引数値・原本・例外本文・SQL・パラメーター・接続文字列は含めません。

| 主な診断 | 対応 |
| --- | --- |
| `operation=arguments` | 引数を確認する。対象指定は提供しない |
| `operation=configure` | 対象DBの環境変数設定を確認する |
| `fixed category rules could not be loaded or verified` | 同梱CSVと対象DBの定義・seed状況を確認する。CLIは不足や相違を修正しない |
| `operation=reclassify` | DB接続・利用可能なスキーマなどを確認し、原因解消後に再実行する |
| `reason=operation interrupted` | 中断された処理段階とcommit成功の確認状況を確認する |
| `operation=output`・`operation=close` | 出力先・接続の問題を確認する。`commit_succeeded=true`なら変更は確定済み |

commit前の取得・判定・削除・INSERT失敗では、先行バッチも含めて全体のrollbackを試みます。
通常実行中の`KeyboardInterrupt`も捕捉し、固定診断を出して、commit成功を確認できていなければrollbackを試みます。
Sessionが生成済みならcloseを試みます。
rollback自体が失敗してもcloseを試み、終了処理の失敗は元の失敗に加えて固定診断へ出します。
OSによる強制終了など、捕捉できない終了についてrollback呼出しまで保証するものではありません。

`commit_succeeded=true`はcommitの正常終了を確認したことを示し、出力・close失敗時もrollbackしません。
`commit_succeeded=false`は成功を確認できていないという意味であり、commit中の通信失敗・中断でDB未変更と断定するものではありません。
原因を解消して再実行すると、途中位置から再開せず、全件を最初から処理します。
同じ原本・ルールなら結果の集合と件数は同じになりますが、DELETE・INSERTは毎回行います。

## PostgreSQL 17 DB統合テストを実行する

DB統合テストは既存のAPI unittestと別ディレクトリ、別コマンドで実行します。

先に、Docker接続用環境変数を除外した状態のcontextとendpointを読み取り専用で確認します。

```bash
env -u DOCKER_HOST -u DOCKER_CONTEXT docker context show
env -u DOCKER_HOST -u DOCKER_CONTEXT docker context inspect --format '{{json .Endpoints.docker.Host}}'
```

endpointが判別可能なローカルUnix socketを指す場合だけ、次の統合テストを実行します。
remote endpoint、`unix://`以外、空出力などでローカルと確認できない場合は停止します。
このpreflightは確認結果を表示するだけであり、統合テストrunnerがDocker contextを自動判定するものではありません。

```bash
cd apps/api
env -u DATABASE_URL \
  -u PRESSWATCH_TEST_DATABASE_URL \
  -u PRESSWATCH_TEST_POSTGRES_PASSWORD \
  -u PRESSWATCH_REAL_SNAPSHOT_PATH \
  -u DOCKER_HOST \
  -u DOCKER_CONTEXT \
  PYTHONPATH=src uv run --locked python -m integration_tests.run
cd ../..
```

このコマンドは`infra/compose.test.yml`を使い、テスト専用PostgreSQL 17を`127.0.0.1:55432`で起動します。
実行ごとに一時的なテスト専用パスワードを生成するため、`.env`や製品用`DATABASE_URL`は使用しません。
製品DB、外部のテストDB、実データスナップショット、別のDocker接続設定を親shellから引き継がず、ローカルCompose経路へ固定します。
親shellのlibpq用`PG*`環境変数は子プロセスへ引き継がず、SQLAlchemyとAlembicの接続先IPを`127.0.0.1`、`search_path`を`public`へ固定します。

テストはDBを変更する前に、接続URLのdriver、host、port、DB名、ユーザー名を検証します。
実接続後もDB名、ユーザー名、PostgreSQLのメジャーバージョン、`current_schema()`が`public`を返すこと、migration管理外テーブルがないことを確認します。
安全条件を満たさない場合は、Alembic migrationやデータ操作を開始せずに失敗します。

安全確認後、テスト専用DBだけを`downgrade base`で初期化し、既存migrationを`upgrade head`まで適用します。
実スキーマ、PostgreSQL固有の配列型、ILIKE、固定カテゴリの制約と削除規則を確認します。
通常のDBテストでは、外部transactionを終了時にrollbackしてテストデータを分離します。
既存のmigration再適用テストでは、一度commitしたデータが`downgrade base`と`upgrade head`によるDB再構築で消えることを確認します。
固定カテゴリmigrationの部分downgradeテストでは、報道発表1行をcommitし、旧head`9f2c7a4e1d63`で新3テーブルだけが消えてその行が残ることと、現在head`a51eab6808f3`への再upgrade後も同じ行が残ることを確認します。

固定カテゴリseedのテストは外側のtransactionに包まず、CLI自身のcommit・rollbackを実際のDBへ反映します。
初回投入、書込みのない再実行、不足補完、不整合拒否、途中失敗の取消、既存ID・原本・分類結果の保持を別Sessionから確認します。
確認後は、成功・失敗にかかわらずテストデータを外部キーに沿った順序で削除します。

新規保存時の分類テストでも、CLI自身のcommit・rollbackを実際のDBへ反映します。
原本と分類結果の同時保存、重複skipによる既存行の保持、未投入・不整合の拒否、分類結果の1,000組分割と途中失敗時の全体rollbackを別接続から確認します。
ルール取得は新規行がある保存呼出しで2 SELECT、全件skipでは0回であることも確認します。

再分類テストでは、CLIの全件置換・再実行、原本全列と定義の保持、0件でも行うルール検証を別接続から確認します。
実際の外部キー違反と、後半バッチの取得・判定・削除失敗や中断で、削除済みの旧分類も含めて全体がrollbackされることを確認します。
repositoryへ一部IDを渡すテストでは指定外IDの結果保持を確認し、全件対象のCLIテストとは区別します。
再分類区間のSELECT・INSERT・DELETE・UPDATEを専用listenerで数え、SQL本文やパラメーターは保存しません。

カテゴリ絞り込みテストでは、合成データを用意してHTTPから実際のrepositoryを通します。
単一・複数OR、タイトル検索とのAND、文字としての`%`・`_`、未分類・未定義・定義未投入、ページ境界と重複防止を確認します。
保存済みの全所属を検索カテゴリ以外も含めて返し、挿入順・数値ID・slug順と異なる表示順、所属なしの空配列も確認します。
API要求中は種別ごとのSQL回数だけを数え、記事のあるページは件数・記事・所属の3 SELECT、件数取得で判定できる0件・超過ページは1 SELECTで書込みがないことを確認します。
同じ取得経路でページ内の記事数を1・10・50・100件に変えても3 SELECTであることを確認し、fixture準備や検証用照会は要求区間の計測に含めません。
件数取得後の同時更新で一覧が空になる応答はunittestで確認し、所属取得を省略して取得済みの件数と要求ページを保持します。
要求前後の原本全列・カテゴリとキーワードの定義・分類結果を比較し、更新されないことも確認します。

公開日範囲検索のテストも、同じ合成データとHTTP・実repositoryの経路を使います。
両端の当日を含み前後を除くこと、片側・未指定・同日・正常0件、タイトルとカテゴリORとのANDを確認します。
ページ送り用には範囲内の21件と、タイトル・所属は一致する範囲外の行を用意します。
日付で絞り込んでから件数・一覧・ページを求めること、同日のID降順・重複防止・全所属・超過ページの要求ページ保持を確認します。
要求中だけを計測して記事ありは3 SELECT、件数で判定できる空ページは1 SELECTと書込みの不在を確認し、原本・カテゴリ・キーワード・所属の4テーブル全列を要求前後で比較します。
同時更新で記事取得結果が空になる場合は日付条件付きのunittestで確認し、実DBの合成データでは同時更新を起こしません。
日付の形式・実在日・逆順の422と、Session終了失敗時の元の422の保持・初期化失敗の優先順位は、実dependencyを使うunittestで確認します。
この検証は専用DB上の合成データを対象とし、常設DBの準備や開発DB・Supabase・実データの検証を完了したものではありません。

固定カテゴリ選択肢のテストもHTTPから実際のrepositoryを通します。
挿入順・数値ID・slug順と異なる表示順、正常0件、分類キーワードや記事がなくても定義を取得できることを確認します。
要求区間のSQLは定義あり・0件とも1 SELECTで書込みがなく、要求前後の原本・カテゴリ・キーワード・分類結果の全列が保持されることを確認します。
SQL本文やパラメーターは記録せず、操作種別と回数だけを数えます。

テストデータはtmpfsに置かれ、成功時と失敗時のどちらでもテスト専用Compose projectを停止します。
通常の開発DBが使う`127.0.0.1:5432`、`postgres17_data`、旧`postgres_data`、Supabaseには接続しません。
`55432`が別のプロセスに使われている場合は、別ポートへ自動で切り替えずに起動を失敗させます。

### 完成済み実データスナップショットを検証する

Issue #70で確定した環境省報道発表34,421件のJSONスナップショットは、専用runnerから同じテスト専用PostgreSQL 17へ投入できます。
スナップショットはGit管理外のローカルファイルとして用意し、リポジトリへ追加しません。

```bash
cd apps/api
PYTHONPATH=src uv run --locked python -m integration_tests.run_real_snapshot /absolute/path/to/env_press_all.json
cd ../..
```

runnerはComposeを起動する前に、ファイル、JSON構造、件数、各項目の型、保存DTO、詳細ページURLの重複、SHA-256、取得完了時刻を検証します。
入力検証後は、空DBへの初回保存、全行の取得時刻、一覧APIの先頭・最終・超過ページ、タイトル検索、同じスナップショットの再投入を確認し、件数と所要時間だけを出力します。
入力検証、DB操作、API取得の失敗時も、スナップショット本文、接続文字列、認証情報をエラーへ出力しません。

接続先、schema、許可テーブルは通常のDB統合テストと同じ安全条件で検証します。
成功時と失敗時のどちらでもテスト専用Compose projectを停止し、tmpfs上のテストデータ、専用コンテナ、networkを削除します。

## scraper を単体で起動する

scraper の単体動作を確認します。保存済みHTMLを使うと、実HTTP取得をせずにJSON出力を確認できます。

```bash
cd packages/scraper
uv sync
PYTHONPATH=src uv run python -m press_watch_scraper --from-file tests/fixtures/env_press_index_sample.html
cd ../..
```

取得結果をローカルで確認したい場合は、CLI の stdout JSON を一時ファイルへリダイレクトします。JSON ファイル保存は本格機能ではなく、取得件数やカテゴリ、停止理由を確認するための開発・検証用スナップショットとして扱います。

```bash
cd packages/scraper
PYTHONPATH=src uv run python -m press_watch_scraper --from-file tests/fixtures/env_press_index_sample.html > /tmp/env_press_sample.json
python -m json.tool /tmp/env_press_sample.json
cd ../..
```

全件取得は再取得コストが高いため、DB 保存処理とつなぐ前の確認や再確認に使える JSON スナップショットを残せます。
`--output PATH` を指定すると、成功時の stdout JSON と同じ内容を指定ファイルにも保存します。

```bash
cd packages/scraper
PYTHONPATH=src uv run python -m press_watch_scraper --from-file tests/fixtures/env_press_index_sample.html --output /tmp/env_press_sample.json
python -m json.tool /tmp/env_press_sample.json
cd ../..
```

実HTTPで全月別アーカイブを巡回し、結果をスナップショットとして残す場合は次の形です。
全月取得を実行する前に、現在のrobots.txtと利用条件を再確認します。
`--crawl-state-dir` はローカルで行う初回全件取得の途中保存と手動再開専用です。
本番環境へ配置せず、定期差分取得、実行履歴、再試行管理には使用しません。
stateと最終JSONが同じcleanupで消えないよう、`--output` はstateディレクトリ外へ指定します。

```bash
cd packages/scraper
PYTHONPATH=src \
uv run --locked python -m press_watch_scraper \
  --all-archive-months \
  --crawl-state-dir /private/tmp/press-watch-env-crawl-state \
  --verbose \
  --no-stdout-json \
  --output /private/tmp/env_press_all.json
python -m json.tool /private/tmp/env_press_all.json
cd ../..
```

途中で取得または解析に失敗した場合は、同じ巡回条件とstateディレクトリを指定して再開します。
取得失敗ページは再取得し、解析失敗ページは保存済みHTMLから再解析します。

```bash
cd packages/scraper
PYTHONPATH=src \
uv run --locked python -m press_watch_scraper \
  --all-archive-months \
  --crawl-state-dir /private/tmp/press-watch-env-crawl-state \
  --resume \
  --verbose \
  --no-stdout-json \
  --output /private/tmp/env_press_all.json
cd ../..
```

保存HTMLの欠損、サイズ不一致、SHA-256不一致、保存途中の状態は、通常の再開では拒否します。
対象ページを実HTTPで取得し直すことを確認した場合だけ、`--refetch-invalid-pages`を`--resume`と併用します。

```bash
cd packages/scraper
PYTHONPATH=src \
uv run --locked python -m press_watch_scraper \
  --all-archive-months \
  --crawl-state-dir /private/tmp/press-watch-env-crawl-state \
  --resume \
  --refetch-invalid-pages \
  --verbose \
  --no-stdout-json \
  --output /private/tmp/env_press_all.json
cd ../..
```

最終JSONの内容を確認し、後続検証でHTMLを再利用しないことを確認してから、完了stateを削除します。
cleanupは、有効な`complete` manifestと管理対象ファイルだけを持つstateに限定し、未完了、破損、symlink、管理外ファイルを検出した場合は何も削除しません。

```bash
cd packages/scraper
PYTHONPATH=src \
uv run --locked python -m press_watch_scraper \
  --cleanup-crawl-state /private/tmp/press-watch-env-crawl-state
cd ../..
```

巡回中は解析成功ページを含むHTMLを`pages/`に保持し、manifestへ月別対象の確定状態、取得、保存、解析の状態とUTC日時を記録します。
HTMLとmanifestは原子的に置換し、stateディレクトリを`0700`、ファイルを`0600`で作成します。
stateには取得した公開ページ本文とURLが含まれるため、Git管理外のローカル一時データとして扱います。
SHA-256は偶発的な破損検出に使い、改ざんを証明する電子署名としては扱いません。

取得中の要求番号、開始からの経過秒、URL、待機の残り秒数、月別ページ番号と対象件数をターミナルで確認したい場合は、`--verbose` を指定します。
進捗は実行中に stderr へ出力し、stdout のJSONとは分けて扱います。
JSONをstdoutへ出さず、進捗だけを見ながらスナップショットを保存したい場合は、`--no-stdout-json` と `--output` を併用します。

```bash
cd packages/scraper
PYTHONPATH=src uv run python -m press_watch_scraper --archive-month-limit 2 --verbose --no-stdout-json --output /tmp/env_press_sample.json
python -m json.tool /tmp/env_press_sample.json
cd ../..
```

`--output` は開発・検証用の補助機能として扱い、差分保存や履歴管理は行いません。
取得件数、重複URLの有無、カテゴリ、`stop_reason` などを後から確認するためのスナップショット用途に限定します。
親ディレクトリは自動作成しないため、任意の保存先を使う場合は先に `mkdir -p /path/to/dir` でディレクトリを作成してください。
存在しないディレクトリを指定した場合は、取得前にエラーとして終了します。
取得またはJSON生成に失敗した場合はファイルを書き出さず、既存ファイルも変更しません。
ファイルは出力先へ直接書き込むため、ファイル書き込み中の失敗に対する原子的な更新は保証しません。
ファイル書き込み後にstdoutへの出力だけが失敗した場合は、完成したスナップショットを残したまま、stderrと終了コード `1` でstdoutの出力失敗を伝えます。

実HTTPで環境省の報道発表一覧を取得する場合は、`--from-file` を外します。月別ページを巡回する場合は、意図しない大量取得を避けるため `--archive-month-limit N` または `--all-archive-months` を明示します。

Docker Compose の通常起動には scraper はまだ含めていません。

## DB セットアップの考え方

PostgreSQL はローカル環境へ直接インストールせず、Docker Compose の `db` サービスとして起動します。

`infra/compose.yml` では PostgreSQL 17 のコンテナを使い、次の DB 設定で初期化します。

- DB 名: `presswatch`
- ユーザー名: `presswatch`
- パスワード: `.env` の `POSTGRES_PASSWORD`
- ローカルPCからの接続先: `127.0.0.1:5432`

`db` サービスは、コンテナの5432番ポートをローカルPCの `127.0.0.1:5432` に公開します。
このポートは、ローカルPCで単体起動する API、Alembic、手動取得・保存コマンドから接続するために使用します。
接続先を `127.0.0.1` に限定しているため、同じネットワーク上の別端末には公開しません。
Docker Compose 内の API コンテナから接続する場合は、サービス名を使って `db:5432` を指定します。

初回起動時に Docker が PostgreSQL イメージを取得し、`postgres17_data` ボリュームをコンテナ内の `/var/lib/postgresql/data` へマウントして DB データを保存します。
通常のセットアップでは、`.env` を用意して Docker Compose を起動すれば DB も一緒に作られます。

PostgreSQL 18 で使用していた `postgres_data` ボリュームは、PostgreSQL 17 では再利用しません。
既存データを保護するため、PostgreSQL 17 への切り替え作業では `postgres_data` ボリュームを削除せず、そのまま残します。

Phase 3 では、API 側から PostgreSQL に接続するために SQLAlchemy + psycopg の最小土台を導入し、Alembic で `press_releases` の初版 migration を管理しています。
スクレイピング結果を DTO 経由で repository / service へ渡して保存する処理も API 側にあり、Phase 4 では既存 scraper CLI の JSON 結果を API 側の手動取得・保存コマンドから保存 service へ渡せるようにしています。
接続文字列の環境変数名は `DATABASE_URL` のままとし、SQLAlchemy から psycopg を使う場合は次のような形式を想定します。

```text
postgresql+psycopg://presswatch:${POSTGRES_PASSWORD}@db:5432/presswatch
```

`.env` は秘密情報を含みうるため、接続に必要な環境変数は `.env.example` やこのドキュメントに記載された名前だけを参照します。

## Phase 6の接続検証用PostgreSQL 17

Webの実API確認では、開発DBと分離した`infra/compose.validation.yml`のDBを再利用します。
このDBは合成データ専用であり、一時的なDB統合テストのrunnerを向けません。
以下のDB準備手順はAPIの製品コード、migration、同梱CSVを変更しません。

| 対象 | 設定 |
| --- | --- |
| Docker context・endpoint | `desktop-linux`・`unix:///Users/hiro/.docker/run/docker.sock` |
| Compose project | `press-watch-api-validation` |
| PostgreSQL | `postgres:17`、ホストの`127.0.0.1:55433` |
| DB名・ユーザー | `presswatch_api_validation` |
| 永続ボリューム | `press-watch-api-validation_postgres17_data` |
| ホストAPI | `127.0.0.1:8001` |
| 資格情報 | Git管理外の`.env.api-validation`、所有者本人・権限600 |

以下の例ではリポジトリを`/Users/hiro/my-projects/press-watch`へ配置していることを前提とします。
別の配置では、Pythonコード中の`repo`を実際のリポジトリの絶対パスへ合わせます。
コンソール起動コマンドの`cd`先もその配下の`apps/api`へ変更し、`PYTHONPATH`には`apps/api/src`の絶対パスを指定します。
Docker endpoint、DB名、ユーザー、ポートは承認済みの対象として固定し、自動で別の接続先へ切り替えません。
DB操作・ファイル変更と、専用秘密ファイルの非表示読取り、commit・push・PRの承認は`AGENTS.md`と今回の`task.md`に従います。
既存の`.env`、Supabase、開発DBの資格情報は使用しません。

### 初回の専用資格情報

専用project・ボリューム・ポートが未使用であることを、ローカルDockerのmetadataと`lsof`で確認します。
既存開発DBの`press-watch_postgres17_data`と旧`press-watch_postgres_data`は保持します。
資格情報を新規作成する場合だけ、次のコードを実行します。
既存ファイルは上書きせず、既存ボリュームがあるのにファイルがない場合も停止します。

```bash
python3 - <<'PY'
from pathlib import Path
import os
import secrets
import subprocess

repo = Path('/Users/hiro/my-projects/press-watch')
env = {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR') if k in os.environ}
docker = ['docker', '--context', 'desktop-linux']
endpoint = subprocess.run([*docker, 'context', 'inspect', 'desktop-linux', '--format', '{{.Endpoints.docker.Host}}'], env=env, check=True, capture_output=True, text=True).stdout.strip()
if endpoint != 'unix:///Users/hiro/.docker/run/docker.sock':
    raise SystemExit('Docker endpointが対象と一致しません')
volume = subprocess.run([*docker, 'volume', 'ls', '--filter', 'name=^press-watch-api-validation_postgres17_data$', '--format', '{{.Name}}'], env=env, check=True, capture_output=True, text=True).stdout.strip()
if volume:
    raise SystemExit('既存ボリュームの資格情報を再生成しません')
fd = os.open(repo / '.env.api-validation', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
with os.fdopen(fd, 'w', encoding='ascii') as output:
    output.write('PRESSWATCH_VALIDATION_POSTGRES_PASSWORD=' + secrets.token_urlsafe(32) + '\n')
print('専用資格情報を権限600で作成しました。値は表示しません。')
PY
```

`.gitignore`と`.dockerignore`の`.env.*`によって除外されます。
`git check-ignore -v .env.api-validation`で確認し、ステージ・コミット・Docker build contextへ含めません。
パスワードや接続URLをシェルへ貼り付けたり、`source`・`eval`で秘密ファイルを実行したりしません。

### 専用環境で既存コマンドを実行する

APIとscraperの既存セットアップを済ませ、APIの`.venv`が存在することを前提とします。
次のコマンドで、親の`DATABASE_URL`・`PG*`・Docker／Compose／uv設定・`PYTHONPATH`を引き継がないPythonコンソールを開きます。

```bash
cd /Users/hiro/my-projects/press-watch/apps/api
env -i PATH="$PATH" HOME="$HOME" TMPDIR="${TMPDIR:-/tmp}" LANG="${LANG:-en_US.UTF-8}" PYTHONPATH="/Users/hiro/my-projects/press-watch/apps/api/src" .venv/bin/python
```

以下をコンソールへ読み込みます。
接続URLはメモリ内で構成し、子プロセスの環境へ渡します。
実行結果は固定の診断・revision・件数だけを表示し、例外全文・SQL parameters・展開済みCompose設定は表示しません。
コンソールの通常終了とSIGTERM・SIGHUPによる終了では、今回起動したAPIと専用DBの停止を試みます。

```python
import atexit
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, build_opener
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL

repo = Path('/Users/hiro/my-projects/press-watch')
api_dir = repo / 'apps/api'
base_env = {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'XDG_CACHE_HOME') if k in os.environ}
base_env['COMPOSE_DISABLE_ENV_FILE'] = '1'
docker = ['docker', '--context', 'desktop-linux']
compose_args = [*docker, 'compose', '--project-name', 'press-watch-api-validation', '--file', str(repo / 'infra/compose.validation.yml'), '--env-file', str(repo / '.env.api-validation')]
api_process = None
db_started = False
cleanup_depth = 0
pending_exit = None

@contextmanager
def defer_exit(*, raise_exit=True):
    """停止処理中の終了要求を保持し、最外の処理完了後に終了

    Args:
        raise_exit: Python終了処理内ではFalseとし、重ねて終了例外を発生させない
    """
    global cleanup_depth
    cleanup_depth += 1
    try:
        yield
    finally:
        cleanup_depth -= 1
        if cleanup_depth == 0 and pending_exit is not None and raise_exit:
            raise SystemExit(pending_exit)

def raw_run(args, cwd=repo, env=base_env):
    """固定環境で実行し、出力を表示せずメモリへ保持する。"""
    process = subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        output, _ = process.communicate(timeout=120)
    except BaseException as error:
        terminate_owned(process)
        if isinstance(error, SystemExit):
            raise
        raise RuntimeError('コマンド中断。詳細は非表示。DB変更状態を照合してください。') from None
    if process.returncode:
        raise RuntimeError('コマンド失敗。詳細は非表示。DB変更状態を照合してください。')
    return output

def terminate_owned(process):
    """今回作成したプロセスグループを終了し、親プロセスを回収する。"""
    with defer_exit():
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)

def check_context():
    """操作前にローカルDocker endpointを照合する。"""
    value = raw_run([*docker, 'context', 'inspect', 'desktop-linux', '--format', '{{.Endpoints.docker.Host}}']).strip()
    if value != 'unix:///Users/hiro/.docker/run/docker.sock':
        raise RuntimeError('Docker endpointが対象と一致しません')

def compose(*args):
    """専用projectだけを操作し、起動を記録する。"""
    global db_started
    check_context()
    if args[0] == 'up':
        db_started = True
    raw_run([*compose_args, *args])
    print('Compose:', args[0], '成功')

def stop():
    """今回のAPIグループを終了し、専用DBを停止する。ボリュームは保持する。"""
    global api_process, db_started
    with defer_exit():
        try:
            if api_process is not None:
                terminate_owned(api_process)
            api_process = None
        finally:
            if db_started:
                check_context()
                raw_run([*compose_args, 'stop', '--timeout', '10', 'db'])
                db_started = False

def cleanup(*, exiting=False):
    """停止と接続終了を試み、失敗の詳細を表示せず未確認状態を通知

    Args:
        exiting: atexitからの呼出しではTrueとし、終了例外を重ねず処理を完了する
    """
    with defer_exit(raise_exit=not exiting):
        try:
            stop()
        except BaseException:
            print('APIまたは専用DBの停止を確認できません。対象の状態を確認してください。')
        try:
            if 'db' in globals():
                db.dispose()
        except BaseException:
            print('DB接続の終了を確認できません。')

def safe_exception(error_type, error, traceback):
    """例外詳細を表示せず、停止を試みて未確認状態を明示する。"""
    print('処理を中断しました。詳細は非表示です。DB変更状態を照合してください。')
    cleanup()

def handle_signal(signum, frame):
    """停止中の終了要求を保持し、停止中以外は通常の中断へ接続"""
    global pending_exit
    if signum == signal.SIGINT and cleanup_depth == 0 and pending_exit is None:
        raise KeyboardInterrupt
    if pending_exit is None:
        pending_exit = 128 + signum
    if cleanup_depth == 0:
        raise SystemExit(pending_exit)

sys.excepthook = safe_exception
atexit.register(cleanup, exiting=True)
for value in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(value, handle_signal)
fd = os.open(repo / '.env.api-validation', os.O_RDONLY | os.O_NOFOLLOW)
with os.fdopen(fd, 'r', encoding='ascii') as source:
    info = os.fstat(source.fileno())
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise RuntimeError('専用資格情報の所有者・形式・権限が不正です')
    match = re.fullmatch(r'PRESSWATCH_VALIDATION_POSTGRES_PASSWORD=([A-Za-z0-9_-]{43})\n', source.read(200))
    if match is None:
        raise RuntimeError('専用資格情報の形式が不正です')
    password = match.group(1)

db_url = URL.create('postgresql+psycopg', username='presswatch_api_validation', password=password, host='127.0.0.1', port=55433, database='presswatch_api_validation', query={'hostaddr': '127.0.0.1', 'options': '-c search_path=public', 'connect_timeout': '5'})
api_env = {**base_env, 'DATABASE_URL': db_url.render_as_string(hide_password=False), 'PYTHONPATH': str(api_dir / 'src')}
db = create_engine(db_url, pool_pre_ping=True, hide_parameters=True)

def cli(*args):
    """既存APIコマンドを実行し、既知の件数項目だけを表示する。"""
    output = raw_run(['uv', 'run', '--locked', *args], cwd=api_dir, env=api_env)
    if args[0] == 'alembic':
        print('Alembic:', 'a51eab6808f3 (head)' if 'a51eab6808f3 (head)' in output else '実行成功')
    else:
        payload = json.loads(output)
        print({k: payload[k] for k in ('categories_added', 'keywords_added', 'fetched_count', 'saved_count', 'skipped_count') if k in payload})

def get(path, params=()):
    """ローカルAPIの応答をメモリへ取得する。呼出し結果は変数へ保存する。"""
    url = 'http://127.0.0.1:8001' + path
    if params:
        url += '?' + urlencode(params, doseq=True)
    try:
        with build_opener(ProxyHandler({})).open(url, timeout=5) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)

def start_api():
    """専用設定でAPIを起動し、所有するプロセスと取得期限を管理する。"""
    global api_process
    if api_process is not None:
        raise RuntimeError('今回のAPIは既に起動しています')
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(('127.0.0.1', 8001))
        probe.listen(1)
    api_process = subprocess.Popen(['uv', 'run', '--locked', 'python', '-m', 'uvicorn', 'press_watch_api.main:app', '--host', '127.0.0.1', '--port', '8001'], cwd=api_dir, env=api_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if api_process.poll() is not None:
            raise RuntimeError('API起動失敗。詳細は非表示です。')
        try:
            status, response = get('/health')
            if status == 200:
                return
        except (OSError, URLError):
            pass
        time.sleep(0.2)
    raise RuntimeError('API起動確認が期限を超過しました')
```

資格情報、`db_url`、`api_env`、`raw_run`の戻り値をコンソールへ直接表示しません。
例外や中断が発生したら追加投入を止め、`stop()`と`db.dispose()`を実行してコンソールを終了します。
停止に失敗した場合は対象の状態を確認し、完了として扱いません。

### 初回準備・実API確認・再利用

起動前に、専用projectのコンテナ・マウント・ポートとボリュームをDocker metadataで照合します。
`8001`や`55433`が別の処理に使われている場合は、その処理を終了させず停止します。
Composeのproject・file・env-fileは上の固定指定を全操作へ使用します。

```python
compose('config', '--quiet')
compose('up', '--detach', '--wait', '--wait-timeout', '60', 'db')
```

書込み前に、DB名・ユーザー・PostgreSQL 17・public schemaを確認します。
照会時の例外詳細を表示しないよう、次の形で確認します。

```python
try:
    with db.connect() as connection:
        identity = connection.execute(text("SELECT current_database(), current_user, current_schema(), current_setting('server_version_num')::integer")).one()
    assert identity[:3] == ('presswatch_api_validation', 'presswatch_api_validation', 'public')
    assert 170000 <= identity[3] < 180000
    tables = set(inspect(db).get_table_names(schema='public'))
    assert tables in (set(), {'alembic_version', 'press_releases', 'fixed_categories', 'fixed_category_keywords', 'press_release_fixed_categories'})
    print('専用DBのidentityと許可テーブルを確認しました')
except Exception:
    stop()
    raise RuntimeError('DB状態の照合失敗。詳細は非表示です。') from None
```

既存テーブルがある場合はrevision・制約・索引・保存内容も照合し、想定外の状態ならmigration・投入を行いません。
初回の空DBは次の順に進めます。

```python
cli('alembic', 'upgrade', 'head')
cli('alembic', 'current')
start_api()
status, categories = get('/fixed-categories')
assert status == 200 and categories == {'items': []}
status, releases = get('/press-releases')
assert status == 200 and releases == {'items': [], 'pagination': {'page': 1, 'page_size': 50, 'total_items': 0, 'total_pages': 0}}
cli('python', '-m', 'press_watch_api.commands.seed_fixed_categories')
cli('python', '-m', 'press_watch_api.commands.fetch_and_save_env_press', '--from-file', str(repo / 'infra/fixtures/api-validation-press.html'))
```

migration後はhead`a51eab6808f3`、業務4テーブル・`alembic_version`、各列・主キー・一意制約・外部キー削除規則・索引を確認します。
初回seedは10カテゴリ・57キーワード、初回記事投入は保存62件・skip 0件です。
同じAPIで投入後の応答を確認し、`/health`の200だけではDB準備完了としません。

各処理は順次実行し、別の保存・seed・再分類を同時に実行しません。
再利用時は空DB確認を省略し、保存済み定義と同梱CSV、原本のURL・タイトル・公開日・取得元カテゴリ、所属とfixtureの一致を先に確認します。
既存保存処理は同一URLをskipし、欠損・誤分類を修復しません。
不整合があれば停止し、全件再分類や初期化で合わせません。
整合済みなら同じseed・保存コマンドを実行し、追加0カテゴリ・0キーワード、保存0件・skip62件と原本・所属の不変を確認します。
seed済みで記事未投入の中断状態なら、定義一致と記事0件を確認したうえで、seed追加0件、記事保存62件・skip0件として再開できます。
終了コード1でもcommit後の出力・close失敗なら保存済みの場合があります。
commit未確認も未変更とは断定せず、DB状態を照合してから再実行します。

### 合成データと期待値

fixtureは実在の記事を移送せず、すべて`[接続検証]`で始まる62タイトルと`https://example.test/press/api-validation-v1/`配下の絶対URLを含みます。
環境省や詳細URLへのHTTP要求、月別巡回は行いません。
日付別の内容は次のとおりです。

| 公開日 | 内容 | 件数 |
| --- | --- | ---: |
| 2026-01-01 | 案内（取得元カテゴリは大気、固定カテゴリは所属なし） | 1 |
| 2026-01-02 | 土壌、水道水 | 2 |
| 2026-01-03 | 大気ページ001〜051、公共用水域、排水基準、大気と土壌 | 54 |
| 2026-01-04 | 臭気、騒音、振動 | 3 |
| 2026-01-05 | 環境測定、温泉成分 | 2 |

取得元カテゴリを持つのは「案内」だけで、その他はDB・APIとも`null`です。
所属なし1記事・複数所属1記事を含み、所属は合計62組です。
選択肢APIは同梱CSVと一致する10件を表示順で返し、記事APIは保存済み全所属を表示順で返します。
絞り込み条件に一致しない所属も省略しません。

| `/press-releases`の条件 | 総件数 |
| --- | ---: |
| 未指定 | 62 |
| 1月2日〜4日 | 59 |
| 1月2日以降／1月4日以前 | 61／60 |
| 1月3日だけ | 54 |
| `fixed_category=air&fixed_category=soil` | 53 |
| `q=土壌&fixed_category=air` | 1（全所属はair・soil） |
| `q=土壌`、airまたはsoil、1月2日〜4日 | 2 |
| `q=ページ&fixed_category=air` | 51 |

応答を変数へ保存してから、件数・ページなど必要な項目だけを表示します。
例として次のように確認できます。

```python
status, result = get('/press-releases', [('q', '土壌'), ('fixed_category', 'air')])
assert status == 200 and result['pagination']['total_items'] == 1
assert [item['slug'] for item in result['items'][0]['fixed_categories']] == ['air', 'soil']
print(result['pagination'])
```

ページ用51記事は既定50件で50／1／0件、`page_size=10`では10件ずつ5ページ・1件・範囲外0件となります。
ページ間のURL重複・欠落がなく、`published_at DESC, id DESC`と一致することをDBの実IDで照合します。
固定の連番IDは前提にしません。
検索0件、未定義カテゴリ、日付範囲外は200・空結果で、要求ページを保持します。
不正日付・逆順は422です。

### 停止・再起動と確認実績

通常終了・例外・コマンド実行中のCtrl+C・SIGTERM・SIGHUPによる中断では、今回のコマンドとAPIを終了してから専用DBの停止を試みます。
プロセス回収・DB停止・接続終了の途中に届いたCtrl+C・SIGTERM・SIGHUPは終了要求として保持し、停止処理を終えてから終了します。
繰り返しの終了要求も停止処理へ割り込ませず、Pythonが既に終了中の場合はatexitの処理を完了して終了します。
Ctrl+C後にコンソールが継続している場合も、終了時は`stop()`・`db.dispose()`を実行してからコンソールを閉じます。
SIGKILL・OSやDockerの強制停止など、Pythonが終了処理を実行できない場合は自動停止を保証できません。
この場合は、次回の操作前に専用project・コンテナ・今回起動したプロセス・ポートを照合し、残留した専用処理を停止してから保存状態を確認します。
停止を確認できない状態を完了として扱わず、ボリューム削除や初期化で解消しません。

```python
stop()
db.dispose()
```

再起動確認は同じコンソールの`compose('up', '--detach', '--wait', '--wait-timeout', '60', 'db')`と`start_api()`で行います。
revision・定義・業務4テーブルの全列・API応答が停止前と一致することを確認してから、再度`stop()`・`db.dispose()`を実行します。
後続Web作業でAPIを利用する場合もこの専用設定で起動し、利用後は停止します。

停止後は`lsof -nP -iTCP:55433 -iTCP:8001 -sTCP:LISTEN`で待受けがなく、専用コンテナが`exited`であることをmetadataで確認します。
専用資格情報・永続ボリュームは保持します。
`stop`はデータ削除ではありません。
`down -v`・`docker volume rm`・DROP・TRUNCATE・復元・置換は別承認の破壊操作であり、この手順には含めません。

この構成で、head`a51eab6808f3`・4テーブルのschema、初回空API、10カテゴリ・57キーワード・62記事・62所属、検索・全所属・ページ・422を実際のホストAPIと専用PostgreSQL 17で確認しました。
seed再実行の追加0件・記事再投入の保存0件／skip62件、DBとAPIの停止・再起動後の業務4テーブル全列と応答の保持も確認しています。
SIGTERM・SIGHUPによる手順用Pythonの終了でも、専用API・DBの停止と55433・8001番の解放を実環境で確認しました。
専用DB・APIは停止し、55433・8001番を解放済みです。
既存開発DBコンテナと既存・旧ボリュームは変更していません。
開発DB・Supabaseへの固定カテゴリ適用、実データ再分類、Webからの接続はこの確認に含めません。
既存の一時統合テストの実績と、今回の永続DBの確認実績は別の保証範囲です。

## Supabase PostgreSQL へ接続する

Supabase では、継続稼働する FastAPI と Alembic migration に使用できる Direct connection を採用します。
Direct connection は IPv6 を使用するため、接続元の環境が IPv6 で通信できることを事前に確認します。
接続方式の詳細は、[Supabase 公式の接続方法](https://supabase.com/docs/guides/database/connecting-to-postgres)を参照してください。

接続には Supabase ダッシュボードの Direct connection URI と DB パスワードを使用します。
実際の URI、パスワード、プロジェクト識別子は、この文書、コマンド履歴、ログへ記録しません。
URI とパスワードは非表示入力で現在のシェルだけへ読み込み、既存の `DATABASE_URL` へ変換します。

```bash
cd apps/api
read -r -s "SUPABASE_DIRECT_URI?Direct connection URIを貼り付けてEnter: "
echo
read -r -s "SUPABASE_DB_PASSWORD?DBパスワードを貼り付けてEnter: "
echo

DATABASE_URL="$(
    SUPABASE_DIRECT_URI="$SUPABASE_DIRECT_URI" \
    SUPABASE_DB_PASSWORD="$SUPABASE_DB_PASSWORD" \
    uv run python - <<'PY'
import os
from sqlalchemy.engine import make_url

direct_url = make_url(os.environ["SUPABASE_DIRECT_URI"].strip())

is_direct_connection = (
    direct_url.drivername in {"postgres", "postgresql"}
    and direct_url.username == "postgres"
    and direct_url.host is not None
    and direct_url.host.startswith("db.")
    and direct_url.host.endswith(".supabase.co")
    and direct_url.port == 5432
    and direct_url.database == "postgres"
)
if not is_direct_connection:
    raise SystemExit("DIRECT_URI_FORMAT_OK=false")

database_url = direct_url.set(
    drivername="postgresql+psycopg",
    password=os.environ["SUPABASE_DB_PASSWORD"],
).update_query_dict({"sslmode": "require"})

print(database_url.render_as_string(hide_password=False))
PY
)"
url_build_status=$?

unset SUPABASE_DIRECT_URI
unset SUPABASE_DB_PASSWORD

if [ "$url_build_status" -eq 0 ] && [ -n "$DATABASE_URL" ]; then
    export DATABASE_URL
    echo "DATABASE_URL_READY=true"
else
    unset DATABASE_URL
    echo "DATABASE_URL_READY=false"
fi
unset url_build_status
```

`DATABASE_URL_READY=true` を確認してから、SQLAlchemy + psycopg で読み取り専用の接続確認を行います。
`DIRECT_URI_FORMAT_OK=false` または `DATABASE_URL_READY=false` が表示された場合は、接続を試さず、Supabase ダッシュボードで Direct connection の URI をコピーし直します。

```bash
uv run python - <<'PY'
import os

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

engine = create_engine(os.environ["DATABASE_URL"])

try:
    with engine.connect() as connection:
        result = connection.execute(text("select 1")).scalar_one()
    print("DATABASE_CONNECTION_OK=" + str(result == 1).lower())
except OperationalError:
    print("DATABASE_CONNECTION_OK=false")
finally:
    engine.dispose()
PY
```

`DATABASE_CONNECTION_OK=true` を確認できれば、既存のSQLAlchemy + psycopg構成からSupabase PostgreSQLへ接続できています。
エラー時は接続を繰り返さず、URIの形式、パスワード、IPv6到達性を秘密情報なしで一つずつ切り分けます。
Supabase への migration 適用手順は `docs/db-migrations.md` に整理しています。

## 手動で取得してDBへ保存する

手動取得・保存は API 側のコマンドとして実行します。scraper CLI は DB 保存前の取得確認と JSON スナップショット出力の入口として維持し、手動取得・保存コマンドはその JSON 結果を API 側の保存 service へ渡します。

事前に Docker Compose の `db` が起動しており、Alembic migration が適用済みであることを確認します。ローカルホストから DB に接続するため、`DATABASE_URL` の host は `127.0.0.1` を指定します。
新規保存時に固定カテゴリを分類するため、同じ対象DBへ「固定カテゴリの初期データを取り込む」のseed CLIを先に実行してください。
保存コマンドはseedを自動実行せず、DBのカテゴリ定義・キーワードが同梱CSVと完全に一致することを確認します。

保存済みHTMLを使って、実HTTP取得なしで取得・保存経路を確認する場合は次の形です。

```bash
cd apps/api
DATABASE_URL=postgresql+psycopg://presswatch:your-local-postgres-password@127.0.0.1:5432/presswatch \
PYTHONPATH=src \
uv run --locked python -m press_watch_api.commands.fetch_and_save_env_press \
  --from-file ../../packages/scraper/tests/fixtures/env_press_index_sample.html
cd ../..
```

成功時は stdout に実行結果の JSON を出力します。

```json
{
  "source_url": "/absolute/path/to/env_press_index_sample.html",
  "fetched_count": 3,
  "saved_count": 3,
  "skipped_count": 0,
  "fetched_page_urls": [],
  "stop_reason": null
}
```

同じデータを再実行した場合、既存の `source_url` は保存せず `skipped_count` に数えます。
新規行だけをタイトルで分類し、原本と分類結果を同じトランザクションで保存します。
重複skipした既存行と分類結果は変更しません。
キーワードに一致しない新規行は固定カテゴリなしで保存します。
空入力・全件skipでは分類ルールを読み込まないため、ルールが未投入・不整合でも従来どおり成功します。

新規行がある場合のルール検証失敗は`exception=FixedCategoryClassificationError`で診断し、原本も含めてrollbackします。
`reason`の固定文言と対応は次のとおりです。

| reason | 確認する内容 |
| --- | --- |
| `fixed category definitions are not ready` | カテゴリまたはキーワードが未投入。対象DBのseed実行を確認する |
| `fixed category definitions do not match bundled CSV` | 定義の不足・余分・相違・参照不整合。DBと同梱CSVの組合せを確認する |
| `fixed category CSV could not be loaded` | 同梱CSVの読込・検証失敗。配布ファイルの配置と内容を確認する |

分類結果のINSERT失敗は、既存のDBエラー診断と同じ`reason=database operation failed`で出力します。
CSVの入力値・読込パス・元例外の詳細・SQL・接続文字列をこれらの診断に含めません。

DB設定を読み込めない場合は、scraperやDB Sessionを開始せず、`target=DATABASE_URL`、`exception=RuntimeError`、`reason=database configuration could not be loaded` としてstderrへ出力します。
元の設定エラーの詳細はstderrへ出力しません。
取得に失敗した場合は保存用DB Sessionを作成せず、保存処理の開始後に失敗した場合は rollback します。
いずれも stderr に `error: target=... exception=... reason=...` の形式で出力し、終了コード `1` を返します。
DBへのcommit後に結果JSONの出力だけが失敗した場合は rollback できないため、DB保存済みであることをstderrに明示します。

報道発表URLや月別アーカイブURLが安全なHTTP(S) URLとして扱えない場合は、その項目だけを黙って除外せず、実行全体を失敗させます。
この場合は成功時のJSONを出力せず、DB保存も行いません。
stderr の `reason` には `validation=non_ascii_character` などの固定理由コードと、報道発表では `title` / `href`、月別リンクでは `archive_month` / `href` を含めます。
認証情報を含む絶対URLと、`//`で始まるスキーム相対URLは、認証部分を `[redacted]` に置き換えます。
パスワードに `@` が含まれる場合も認証部分全体を伏せます。
空白・TAB・改行・端末制御文字を含む認証部分も、拒否したURLの診断へ残しません。
HTTP(S)のスキーム・コロン・二重スラッシュの間や、スキーム相対URLの二重スラッシュの間にTAB・CR・LFがある場合も、診断のURL候補として認識して認証部分を伏せます。
この判定では元の接頭辞を保持し、診断文字列全体から制御文字を削除して別URL同士を連結しません。
parserが作るURL拒否診断の引用付き項目では、TAB・CR・LFを空白へ変換せず、`\t`・`\r`・`\n`のエスケープ表記で保持します。
CLI・manifest・APIが同じ診断を再処理するときも、引用付き項目からこれらの文字を読み、パス内の`//tag@item`を別の認証付きURLと誤認しないようにします。
HTML解析でCR・CRLFがLFへ正規化された場合は、解析後の値を記録します。
引用付き項目に整形していない一般の例外理由や対象値は、伏字後に従来どおり連続空白をまとめます。
入力検証は引き続きこれらのURLを`unsafe_character`で拒否し、取得・保存に使える正常URLへ修復しません。
伏字ではURL候補のauthorityをパス・クエリ・fragment・次のURLから区切り、認証区切りの最後の `@` までを置き換えます。
パスなしのURLに続く `href='//…'` など、空白・項目名・引用符を挟んで始まるスキーム相対URLも個別に伏せます。
項目名に数字・添字・日本語が含まれる場合や、引用符がエスケープされている場合も、後続URLを先行URLのパスへ取り込みません。
丸括弧・角括弧・波括弧やコロンに続くスキーム相対URLも、先行URLのパスへ取り込まず個別に伏せます。
`href:'//…'`、`参照:(//…)`、`{"href":"//…"}`のようなコロン付き項目名・引用付き項目名も同様に扱います。
項目名を特定の書式に限定せず、空白に続く値の中で、URL開始と同じ条件を満たす`//`を後続URLの境界として認識します。
JSON・配列・タプルでは、引用付きの値やキーを先に分離し、その内部のURL認証部分を個別に伏せます。
`{"url":"https://safe.test","href":"//user:password@host/path"}`や`['https://safe.test','//user:password@host/path']`のように空白がない場合や、項目・配列が入れ子の場合も、後続URLを先行URLのパスへ取り込みません。
先行値が`"failed https://safe.test"`のように説明文を含む場合も、後続の引用付きURLを先行URLへ取り込みません。
`{"msg":"failed https://safe.test","href":"//user:password@host/path"}`や`('failed https://safe.test','//user:password@host/path')`でも、説明文・正常URL・診断項目を保持して認証部分だけを伏せます。
引用付きの値やキーの後ろのカンマ・閉じ括弧・コロン・文字列の終端で境界を認識し、引用符・項目名・区切りの表記を保持します。
引用付き文字列の内部にJSONなどの構造がある場合も、一段ずつ値を読み、内側のURLを個別に伏せます。
引用符・バックスラッシュ・TAB・CR・LFのエスケープを読む際は、各文字と元の診断文字列の位置を対応付け、元の認証部分だけを置き換えます。
外側の引用符、正常URL、診断項目、認証部分以外のエスケープは再整形せず保持します。
処理は反復で進め、引用付き値の入れ子によるPythonの再帰呼び出しを使いません。
対象は文字列中のHTTP(S)・スキーム相対URLと引用符・バックスラッシュ・TAB・CR・LFのエスケープであり、percent encodingやUnicode escapeなどでURLを符号化した値の一般的な復号は行いません。
パス内の `//` を別のスキーム相対URLと誤認せず、パス・クエリ・fragmentの `@` をそのURLの認証情報として扱いません。
URLのパス・クエリ・fragment内の引用符でも解析を打ち切らず、`https://example.com/press/a'//tag@item` のような非認証URLを保持します。
URL拒否診断は、引用付きの `page_url`・`title`・`href` を項目ごとに処理します。
パスなしの取得元URLに続くタイトルのメールアドレスなどを認証情報と誤認せず、取得元や別の診断項目を伏字へ巻き込みません。
項目値の引用符とエスケープを保持し、不正な認証部分に含まれる引用符も伏せます。
scraperの解析例外、CLIのエラー・進捗、巡回manifestの失敗理由は共通の伏字処理を使用し、API側の取得・保存CLIにも同じ伏字方針を適用します。

診断項目の保持と複数URL・引用符・括弧・コロン付き項目名・空白なしJSON／配列の境界を修正した後のローカル確認では、scraper unittest全145件とAPI unittest全283件が成功しました。
空白なしJSON・配列とURLキーの追加ケースは、修正前に伏字のassertionが失敗し、修正後に成功しました。
説明文付き先行URLの追加ケースは、CLI診断・manifestの固定期待値・実scraper子プロセスの各経路で修正前の失敗と修正後の成功を確認しました。
タプルの追加ケースも、CLI診断とmanifestへの保存で修正前の失敗と修正後の成功を確認しました。
引用付き文字列内のJSONでは、APIの取得失敗診断とmanifestの固定期待値で修正前の認証情報漏れを確認しました。
セルフレビューで見つかった、文字列単体で終わる引用付きJSONも、API診断・scraper CLI・manifest・実子プロセスの回帰テストで失敗と修正後の成功を確認しました。
エスケープされたJSONの追加ケースでは、scraper CLIと実scraper子プロセスを経由したAPI診断にも修正前の漏れが再現し、修正後はこれらの回帰テストが成功しました。
この修正後にscraper unittest全146件とAPI unittest全284件が成功しました。
引用・エスケープの入れ子、認証部分内の空白・制御文字・複数の`@`、正常URLと診断項目の保持、処理を繰り返しても結果が変わらないことは、既存の境界2,049通りと追加の入れ子・保持7,327通りの組み合わせでも両実装を照合しました。
組み合わせ確認はローカルの一時スクリプトによる補助検証であり、再実行可能な回帰確認はリポジトリ内のunittestに残しています。
取得HTMLのMock、保存済みHTML、子プロセスの応答制御で拒否・診断・Session未作成を確認した結果であり、実HTTP・実DBを使った検証ではありません。

URL接頭辞内のTAB・CR・LFによる伏字漏れの修正では、発表・月別URLの拒否例外、scraper CLIの診断と進捗、manifestの失敗理由、API CLIの診断で、製品修正前に追加ケースのassertionが失敗することを確認しました。
保存済みの合成HTMLを実scraper子プロセスで解析する経路でも、修正前の漏れと修正後の伏字・診断項目の保持・成功用JSON未出力・Session未作成を確認しました。
修正後にscraper unittest全148件とAPI unittest全285件が成功しました。
既存の正常URL・引用付き診断項目の保持に加え、認証なしの分断URLのパス・クエリ・fragmentと、改行で分かれた別URLの保持を回帰テストで確認しました。
これらは合成HTML・ダミーの認証情報による検証であり、実HTTP・実DB・実際の資格情報は使用していません。

拒否診断の一行化後にパスまで伏せられる問題は、発表・月別URLをparserからCLI・manifestへ渡す回帰テストで、修正前の失敗と修正後の成功を確認しました。
認証情報の有無と制御文字入り接頭辞を変え、パス・クエリ・fragment・診断項目の保持、`unsafe_character`での拒否、成功用JSON未出力を確認しています。
実scraper子プロセスからAPI診断へ渡すテストでも、同じ保持とSession未作成を確認しました。
引用・JSON・入れ子のエスケープも含む修正後のscraper unittest全150件・API unittest全286件が成功し、補助検証800ケースではparser診断へCLI・API・manifestの整形を繰り返しても結果が保たれました。
これらも合成HTMLによるローカル検証であり、実HTTP・実DBは使用していません。

既知の軽微な制約として、取得開始URLの拒否診断には、再処理でパスが余計に伏字になるケースがあります。
実際の改行を含む`https:/\n/host/path=//tag@item`を`--url`へ渡すと、`InvalidFetchUrlError`の`url`項目で`path=//tag@item`が`path=//[redacted]@item`になります。
APIから実scraper子プロセスを起動する経路では、先に一行化された子プロセスの`target`でも同じ変化が起きます。
認証情報の漏えいはなく、URLはHTTP実行前に拒否され、成功用JSONの出力とDB保存も開始されません。
正常なページ送りには影響せず、Phase 6-8の完了を妨げない診断表示の制約として受け入れ、PR #112では追加修正を行わない方針です。

主なURL検証理由は次のとおりです。

- `unsupported_scheme`: HTTPまたはHTTPS以外
- `credentials_not_allowed`: 認証情報を含むURL
- `non_ascii_character`: percent encodeされていない日本語などの非ASCII文字
- `unsafe_character`: 空白、制御文字、URLへ直接置けない記号
- `invalid_percent_escape`: `%ZZ` などの不正なpercent escape
- `invalid_host_or_port`: hostまたはportとして解釈できない形式
- `cross_origin`: 月別アーカイブが起点ページと異なるオリジン

実HTTPで直近の月別アーカイブを少数だけ取得して保存する場合は、意図しない大量取得を避けるため `--archive-month-limit N` を指定します。
実行前に現在のrobots.txtと利用条件を確認します。
1回のscraper CLI実行内では、起点、月別ページ、同一オリジンのredirect先を含むHTTP要求開始の間隔を3秒以上に制御します。

```bash
cd apps/api
DATABASE_URL=postgresql+psycopg://presswatch:your-local-postgres-password@127.0.0.1:5432/presswatch \
PYTHONPATH=src \
uv run --locked python -m press_watch_api.commands.fetch_and_save_env_press \
  --archive-month-limit 2 \
  --verbose
cd ../..
```

保存済み報道発表がないDBへの初回全件取得として、環境省の一覧ページから見つかるすべての月別アーカイブを取得して保存する場合は `--all-archive-months` を指定します。
実HTTPで多数のページを取得し、DBへ保存するため、事前に現在のrobots.txtと利用条件、DB接続先、migration適用状態を確認します。
API側の取得・保存コマンドは、scraper CLIのローカル巡回stateを使用せず、途中保存や再開には対応しません。
途中保存が必要な実データ早期検証では、先にscraper CLIの`--crawl-state-dir`を使用して最終JSONを作成し、このコマンドを直接実行しません。

```bash
cd apps/api
DATABASE_URL=postgresql+psycopg://presswatch:your-local-postgres-password@127.0.0.1:5432/presswatch \
PYTHONPATH=src \
uv run --locked python -m press_watch_api.commands.fetch_and_save_env_press \
  --all-archive-months \
  --verbose
cd ../..
```

`--all-archive-months` は月別アーカイブを巡回する実HTTP取得用の指定です。保存済みHTMLの単一ページ解析で使う `--from-file` や、取得する月別ページ数を制限する `--archive-month-limit` とは併用しません。保存済み報道発表がある場合は、後述する既知URLだけの月に到達すると全月を取得する前に停止します。

初回全件取得後も stdout の実行結果 JSON で、取得件数は `fetched_count`、新規保存件数は `saved_count`、重複などで保存しなかった件数は `skipped_count` として確認できます。巡回した月別ページは `fetched_page_urls`、正常停止理由は `stop_reason` に出力されます。再実行時は、同じ `source_url` の報道発表が新規保存されず `skipped_count` に数えられることを確認します。

差分取得を想定して、保存済みデータがあるDBに対して月別アーカイブを少数だけ取得して保存する場合も、同じ手動取得・保存コマンドを使います。API 側のコマンドは、月別アーカイブ巡回時に、DB内の最新公開月を含む直近3か月の既存 `source_url` を取得済みURLとして scraper 側へ渡します。基準はコマンド実行日ではなく、DBに保存された最新の `published_at` です。

```bash
cd apps/api
DATABASE_URL=postgresql+psycopg://presswatch:your-local-postgres-password@127.0.0.1:5432/presswatch \
PYTHONPATH=src \
uv run --locked python -m press_watch_api.commands.fetch_and_save_env_press \
  --archive-month-limit 6 \
  --verbose
cd ../..
```

既知URLとして取得する月数を変更する場合は、`--known-release-months` に1以上の整数を指定します。例えば、DB内の最新公開月を含む直近6か月を対象にする場合は次のように実行します。

```bash
cd apps/api
DATABASE_URL=postgresql+psycopg://presswatch:your-local-postgres-password@127.0.0.1:5432/presswatch \
PYTHONPATH=src \
uv run --locked python -m press_watch_api.commands.fetch_and_save_env_press \
  --archive-month-limit 12 \
  --known-release-months 6 \
  --verbose
cd ../..
```

月別ページ内の報道発表がすべて保存済み `source_url` と一致した場合、scraper 側はそれより古い月へ進まず停止します。この場合、stdout の実行結果 JSON では `stop_reason` が `duplicate_release_detected` になります。

```json
{
  "source_url": "https://www.env.go.jp/press/index.html",
  "fetched_count": 0,
  "saved_count": 0,
  "skipped_count": 0,
  "fetched_page_urls": [
    "https://www.env.go.jp/press/202605.html"
  ],
  "stop_reason": "duplicate_release_detected"
}
```

確認観点:

- `fetched_count`: scraper から API 側へ渡された新規候補の件数
- `saved_count`: DB に新規保存した件数
- `skipped_count`: API 側保存 service で既存 `source_url` と重複して保存しなかった件数
- `fetched_page_urls`: 実際に巡回した月別ページURL。既知URLだけの月で止まった場合、その月のURLも含まれます
- `stop_reason`: `duplicate_release_detected` の場合は、直近の既知URLだけで構成された月に到達して停止したことを示します

通常の差分取得では `source_url` の重複だけを確認し、保存済みレコードのタイトル、公開日、取得元カテゴリは更新しません。
過去データの内容変更を確認するメンテナンス用フルスキャンは、このコマンドの通常取得とは分け、MVP後の改善候補として扱います。

`duplicate_release_detected` で停止した月の報道発表は scraper から保存 service へ渡されないため、その停止自体は `skipped_count` には加算されません。`skipped_count` は、scraper が返した報道発表を保存しようとした際の重複 skip 件数として確認します。

### 実行結果・進捗・永続ログの扱い

Phase 4 では、取得・保存コマンドの出力を次の3種類に分けて扱います。

- 実行結果: scraper CLI は、`--no-stdout-json` を指定しない限り、成功時の取得結果を機械可読なJSONとしてstdoutへ出力します。
  このJSONは取得結果のスナップショットであると同時に、API 側の取得・保存コマンドへ結果を渡すプロセス間インターフェースでもあるため、進捗やエラーメッセージを混ぜません。
  API 側の取得・保存コマンドは、DBへのcommit後に実行結果JSONをstdoutへ出力します。
- 進捗・エラー: 進捗は `--verbose` 指定時だけ、エラーは失敗時に stderr へ出力します。
  API側の取得・保存コマンドも、scraperの進捗を子プロセス終了後ではなく実行中に転送します。
  stdoutのJSONは子プロセスの完了まで捕捉し、API側が解析する機械可読なインターフェースとして維持します。
  診断対象として `DATABASE_URL`、実行対象のURL、ファイルパス、または `stdout` を示します。
  DB設定を読み込めない場合は固定理由を出力し、元の例外詳細を表示しません。
  URL、ファイルパス、その他の例外理由は、改行などの連続空白を1つにまとめ、端末制御文字を表示可能な文字列へ変換し、絶対URL・スキーム相対URL内の認証情報を `[redacted]` に置き換え、診断値を最大1000文字に制限します。
- 永続的な実行ログ: Phase 4 では実装しません。
  Phase 7 では既存の `stdout`・`stderr` とデプロイ先のジョブ結果・ログを使って成功と失敗を確認します。
  実行ログテーブル、実行ごとの自動ログファイル、本格的な logging 設定はMVP後に必要性を判断します。

scraper CLI の `--output` は、成功時の取得結果を後から確認するための検証用JSONスナップショットです。追記、実行履歴、失敗記録を行わないため、永続的な実行ログとしては扱いません。

API 側の取得・保存コマンドは、処理の終了状態を次のように区別します。

- DBへのcommit、stdoutへの結果JSON出力、保存用Sessionのcloseがすべて成功した場合は、終了コード `0` を返します。
- DB設定の読み込み、取得、保存、またはcommitに失敗した場合は、成功時のJSONをstdoutへ出さず、stderrと終了コード `1` で失敗を伝えます。
  保存用Sessionを作成済みで、commitが完了していない場合は rollback を試みます。
- DBへのcommit後にstdoutへの結果JSON出力が失敗した場合は、DBへ保存済みであることを `database commit succeeded but result output failed` としてstderrへ出し、終了コード `1` を返します。
  この場合は rollback できず、再実行すると保存済みデータが重複としてskipされる可能性があります。
- rollbackまたはcloseに失敗した場合は、元のエラーがあればその診断を残し、終了処理の失敗とcommit呼び出しの完了有無をstderrへ出して、終了コード `1` を返します。
  commitとJSON出力の成功後にcloseだけが失敗した場合も、DBへ保存済みでJSONは出力されていますが、終了コードは `1` です。
- 引数の組み合わせや値が不正な場合は、取得処理やDB処理を開始せず、argparseがstderrへ理由を出して終了コード `2` で終了します。

保存用Sessionを作成した場合は、処理の成否やrollbackの失敗にかかわらずcloseを試みます。

実行ID、開始・終了時刻、所要時間、成功・失敗状態、失敗段階、履歴検索、保持期間は、MVP後に永続的な実行ログを検討する際に必要性を判断します。

定期実行、Docker Compose 全体での取得・保存方法、実HTTPでの差分件数保証は Phase 7 で整理します。

## DB migration の考え方

DB スキーマ変更は Alembic で管理し、API アプリケーション側の責務として `apps/api` 配下に設定と migration ファイルを置きます。
アプリケーション起動時の `metadata.create_all()` には頼りません。

詳細な配置、`target_metadata`、初版 migration、`updated_at` トリガー要否は `docs/db-migrations.md` に整理しています。
Docker Compose の API コンテナから次の形で適用できます。

```bash
docker compose --env-file .env -f infra/compose.yml exec api uv run alembic upgrade head
```

## 保存済みデータを確認する

`press_releases` に保存された報道発表データは、Docker Compose の `db` サービスへ `psql` で接続して確認します。
事前に Docker Compose で `db` が起動しており、Alembic migration が適用済みであることを確認します。
この手順は保存済みデータの確認専用であり、データの追加・更新・削除は行いません。

```bash
docker compose --env-file .env -f infra/compose.yml exec db psql -U presswatch -d presswatch
```

Alembic migrationが適用済みであることを確認します。
リポジトリの現在headは、固定カテゴリ3テーブルを追加する`a51eab6808f3`です。
今回追加したmigrationは開発DBとSupabaseへ未適用であり、両環境で適用確認済みのheadは、`published_at`のインデックスを追加する`9f2c7a4e1d63`までです。
`version_num`が`9f2c7a4e1d63`の場合は固定カテゴリ3テーブルが未適用で、初版migrationの`31765401e166`の場合は公開日インデックスも未適用です。

```sql
select version_num
from alembic_version;
```

psql のメタコマンドで、テーブル定義、NULL 許容、制約を確認します。

```sql
\d+ press_releases
```

確認観点:

- `source_url` に `uq_press_releases_source_url` の一意制約があること
- `published_at` に `ix_press_releases_published_at` のインデックスがあること
- `source_categories` が `text[]` で、NULL 許容であること
- `fetched_at` / `created_at` / `updated_at` が `timestamp with time zone` であること

保存件数を確認します。

```sql
select count(*) as total_count
from press_releases;
```

`total_count` が `0` の場合は、まだ保存済みデータがない状態です。
その場合、以降の集計 SQL はすべて `0` 件を返し、直近保存データの確認 SQL は行を返しません。
手動取得・保存、初回全件取得、差分取得の基本手順は上記のコマンド例で確認できます。
定期実行と Docker Compose 全体での取得・保存方法は Phase 7 で整理します。

`source_url` の重複がないことを確認します。`duplicated_source_url_count` が `0` であれば、保存済みデータ上の URL 重複はありません。

```sql
select count(*) as duplicated_source_url_count
from (
    select source_url
    from press_releases
    group by source_url
    having count(*) > 1
) duplicated;
```

`source_categories` の保存状況を確認します。過去ページではカテゴリが欠損する場合があるため、NULL 件数があること自体は異常ではありません。

```sql
select
    count(*) filter (where source_categories is null) as null_source_categories_count,
    count(*) filter (where source_categories is not null) as non_null_source_categories_count,
    count(*) filter (where source_categories = array[]::text[]) as empty_source_categories_count
from press_releases;
```

確認観点:

- `null_source_categories_count`: カテゴリ欠損として NULL 保存された件数
- `non_null_source_categories_count`: 取得元カテゴリが保存された件数
- `empty_source_categories_count`: 通常は `0` を期待する件数

保存時刻の入っていない行がないことと、保存・取得時刻の範囲を確認します。

```sql
select
    count(*) filter (where fetched_at is null) as null_fetched_at_count,
    count(*) filter (where created_at is null) as null_created_at_count,
    count(*) filter (where updated_at is null) as null_updated_at_count,
    min(fetched_at) as oldest_fetched_at,
    max(fetched_at) as newest_fetched_at,
    min(created_at) as oldest_created_at,
    max(created_at) as newest_created_at,
    min(updated_at) as oldest_updated_at,
    max(updated_at) as newest_updated_at
from press_releases;
```

確認観点:

- `null_fetched_at_count` / `null_created_at_count` / `null_updated_at_count` がすべて `0` であること
- `fetched_at` は環境省ページから取得した日時として入っていること
- `created_at` / `updated_at` は PressWatch 側で保存した日時として入っていること
- Phase 3 初期では既存行の自動更新を扱わないため、通常の初回保存行では `created_at` と `updated_at` が近い値になること

直近で保存されたデータのタイトル、公開日、URL、カテゴリ、時刻を確認します。

```sql
select
    id,
    title,
    published_at,
    source_url,
    source_categories,
    fetched_at,
    created_at,
    updated_at
from press_releases
order by created_at desc, id desc
limit 10;
```

確認観点:

- `title` が空ではなく、環境省の報道発表タイトルとして読めること
- `published_at` が報道発表の公開日として妥当であること
- `source_url` が環境省の詳細ページ URL であること
- `source_categories` は取得できた場合に配列、取得できなかった場合に NULL であること
- `fetched_at` / `created_at` / `updated_at` の時刻が保存タイミングと大きく矛盾しないこと

確認を終えたら `psql` を終了します。

```sql
\q
```

## Docker Compose で全体を起動する

Web、API、DB をまとめて起動します。
ComposeのWebには、サーバー専用の `PRESSWATCH_API_BASE_URL=http://api:8000` を渡します。
`api` はCompose内のサービス名で、WebコンテナからAPIへ接続するために使用します。
ホストでWebを単体起動する場合は、このサービス名ではなく、利用するAPIのアドレスを起動時に設定します。

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

PostgreSQL コンテナに接続できるか、バージョン確認で疎通を見ます。

```bash
docker compose --env-file .env -f infra/compose.yml exec db psql -U presswatch -d presswatch -c "select version();"
```

API コンテナから SQLAlchemy 経由で PostgreSQL に接続できるか確認します。

```bash
docker compose --env-file .env -f infra/compose.yml exec api uv run python -c "from sqlalchemy import text; from press_watch_api.db import get_engine; engine = get_engine(); conn = engine.connect(); print(conn.execute(text('select 1')).scalar_one()); conn.close(); engine.dispose()"
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

## DBボリュームに関する注意

通常の停止手順で使う `docker compose down` は、`postgres17_data` と PostgreSQL 18 で使用していた `postgres_data` を削除しません。
DBボリュームの削除は保存済みデータを失う操作であるため、PostgreSQL 17 への切り替えや通常の開発手順には含めません。
