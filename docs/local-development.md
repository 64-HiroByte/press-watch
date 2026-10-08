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
Next.js 16.3.8のビルドも既定のCLI経路で同じプロジェクト内のTypeScriptを使用し、`experimental.useTypeScriptCli`の追加設定は不要です。
`pnpm --filter @press-watch/web exec tsc --version`でCLIの版を確認できます。
[Next.jsの型生成手順](https://nextjs.org/docs/app/api-reference/cli/next#next-typegen-options)に従い、`next-env.d.ts`は手動で編集しません。
Next.js 16.3では`root-params.d.ts`への参照も生成されます。
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

既存のMock・テーマ初期化・共通Label部品を維持するため、次の6ルールを該当する7ファイルに限定して例外にします。
例外は`.oxlintrc.json`の`overrides`へ置き、その他のファイルでは同じルールを有効にします。

| ルール | 対象（`apps/web/`からの相対パス） | 理由 |
| --- | --- | --- |
| `react/set-state-in-effect` | `components/theme-selector.tsx`、`components/mock/theme-toggle.tsx`、`components/mock/workbench.tsx` | hydration後のテーマ表示と画面幅の初期化で使う状態更新を維持する |
| `jsx-a11y/prefer-tag-over-role` | `components/mock/category-toggles.tsx`、`components/mock/theme-toggle.tsx`、`components/mock/workbench.tsx`、`app/mock/page.tsx` | 現Mockの名前付きgroup・region・searchと、対応するCSSを維持する |
| `jsx-a11y/label-has-associated-control` | `components/ui/label.tsx` | 共通部品の`htmlFor`をprops経由で受け取り、呼び出し側で入力欄と対応させる |
| `jsx-a11y/click-events-have-key-events` | `components/mock/workbench.tsx` | 見本内のリンクから伝播するclickを受けて遷移を止める既存処理を維持する |
| `jsx-a11y/no-noninteractive-tabindex` | `components/mock/workbench.tsx` | 名前付き一覧領域へフォーカスし、キーボードでスクロールできる構成を維持する |
| `jsx-a11y/no-noninteractive-element-interactions` | `components/mock/workbench.tsx`、`components/mock/sidebar-filters.tsx` | 見本内の遷移抑止と、dialogの背景クリック・フォーカス制御を維持する |

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
`production-smoke`はproductionのトップページと`/mock`の404を確認します。
対象ファイルと接続先はprojectごとに指定し、Mockの公開ガードを維持します。

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
Playwrightが開発サーバーを`127.0.0.1:3105`、本番サーバーを`127.0.0.1:3106`で起動し、`/`で準備完了を確認します。
既存サーバーは再利用せず、ポート占有時は失敗させます。
終了後は両ポートに待受プロセスが残っていないことを確認します。

CIでは`test.only`・`test.describe.only`を`forbidOnly`で拒否します。
traceは`retain-on-failure`、スクリーンショットは`only-on-failure`とし、出力先はルートの`tmp/playwright/test-results`です。
現在のMockはAPIを呼ばないため、これらは検索・API取得の製品テストではありません。
後続のAPI応答を制御する画面テストは、Server側の取得にも応答できる検証用HTTPサーバー等を使い、実API・DBとの結合確認と分けます。
ブラウザーのリクエスト差し替えだけでServer側の通信を制御できたとは扱いません。

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
Phase 6-5の実行経路はPR #102とマージ後pushで確認済みで、同構成の省略経路は文書のみの別PRで確認します。
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
実CIでの失敗時アップロードは未確認であり、成功runではこのstepが省略されています。
変更判定や空白検査の失敗、不正な判定出力を成功や省略へ置き換えません。
新しくWebで使う共有設定や別のソース配置を追加した場合は、変更判定の対象も見直します。

新規workflow・ルートOxc設定・CI判定スクリプトの変更は、既存Python CIのAPI・scraper・一時PostgreSQLも実行対象にします。
実CI確認では対象SHA、実行step、実行・省略理由を確認し、ローカルの判定確認だけで実CIも確認済みとは扱いません。
実行経路はPR #102とマージ後pushで確認済みです。
省略経路は、統合済みの`phase-6/frontend`をbaseとする文書のみの別PRで確認します。
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

PRの各jobがcheckoutしたマージ結果は`81dc6b8a0f0c6127df3de212e952bb1787c70f17`です。
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
- 同構成の省略経路は、`phase-6/frontend`をbaseとする文書のみの別PRで確認します。
  Webの変更判定・空白検査と`Skip Web validation`の成功、環境準備・検証stepの省略を確認します。
  Pythonの変更判定・空白検査とAPI・scraperの省略stepの成功、環境準備・テストstepの省略、DB統合job全体の省略も確認します。
  確認済みrunのPR head・base・checkoutしたマージ結果・比較範囲・省略理由・URLを記録し、証拠追記後の最新headのCI確認とは区別します。
  実確認前は[Phase 6-5](tasks.md#6-5-検証基盤の整備)全体を未完了とします。
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
API要求中は種別ごとのSQL回数だけを数え、通常は2 SELECT、0件・超過ページは1 SELECTで書込みがないことを確認します。
要求前後の原本全列・カテゴリとキーワードの定義・分類結果を比較し、更新されないことも確認します。

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

報道発表URLや月別アーカイブURLが安全なHTTP(S) URLとして扱えない場合は、その項目だけを黙って除外せず、実行全体を失敗させます。この場合は成功時のJSONを出力せず、DB保存も行いません。stderr の `reason` には `validation=non_ascii_character` などの固定理由コードと、報道発表では `title` / `href`、月別リンクでは `archive_month` / `href` を含めます。URLに認証情報が含まれていた場合、その部分は `[redacted]` に置き換えます。

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
  URL、ファイルパス、その他の例外理由は、改行などの連続空白を1つにまとめ、端末制御文字を表示可能な文字列へ変換し、URL内の認証情報を `[redacted]` に置き換え、診断値を最大1000文字に制限します。
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
