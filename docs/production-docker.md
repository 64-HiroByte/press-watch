# 本番用Dockerと隔離検証

## 構成と起動

本番用Dockerfileは`infra/docker/`の`web.production.Dockerfile`・`api.production.Dockerfile`・`job.production.Dockerfile`で、build contextはリポジトリルートとする。
開発環境は従来のDockerfileと`infra/compose.yml`を使う。

| 対象 | 起動・設定 |
| --- | --- |
| Web | `node apps/web/server.js`。`HOSTNAME`は既定`0.0.0.0`、`PORT`は既定3000、`PRESSWATCH_API_BASE_URL`を実行時に設定する |
| API | Uvicornを1 worker・reloadなしで起動する。`HOST`は既定`0.0.0.0`、`PORT`は既定8000、`DATABASE_URL`を実行時に設定する |
| ジョブ | 既存の`fetch_and_save_env_press`をentrypointとし、コンテナ引数をCLIへ渡す。`DATABASE_URL`を実行時に設定する |

Webのstandalone出力は本番Dockerのビルド時だけ`PRESSWATCH_STANDALONE=1`で有効にする。
ジョブはAPI・scraperのソースと両venvを既存CLIが参照する配置に収録し、`/etc/uv/uv.toml`で実行時の依存・Python取得を禁止する。

ベースイメージはdigest、依存はlockfileで固定し、各サービスを非rootで実行する。
秘密ファイル・認証設定・ホストの依存を渡さず、WebへDB接続設定を渡さない。
本番DBへのmigration・seed、クラウド配置、定期実行は別途行う。

## 合成データによる検証手順

`infra/compose.production-test.yml`で専用のPostgreSQL 17と合成データを使う。
projectは`presswatch-production-validation`、DB・ユーザーは`presswatch_production_test`、データ領域はtmpfsで、DB停止時にデータは失われる。

以下はmacOSのDocker Desktop用で、専用のCLI設定と既知のローカルsocketを使う。

```bash
set +x
validation_root="$(mktemp -d "${TMPDIR:-/tmp}/presswatch-production.XXXXXX")" || exit 1
docker_validation_config="$validation_root/docker-cli"
mkdir -p "$docker_validation_config/cli-plugins" || exit 1
test -x /Applications/Docker.app/Contents/Resources/bin/docker || exit 1
for plugin in buildx compose; do
  test -x "/Applications/Docker.app/Contents/Resources/cli-plugins/docker-$plugin" || exit 1
  ln -s "/Applications/Docker.app/Contents/Resources/cli-plugins/docker-$plugin" \
    "$docker_validation_config/cli-plugins/docker-$plugin" || exit 1
done
PRESSWATCH_PRODUCTION_TEST_PASSWORD="$(env -i OPENSSL_CONF=/dev/null /usr/bin/openssl rand -hex 24)" || exit 1
test -n "$PRESSWATCH_PRODUCTION_TEST_PASSWORD" || exit 1

production_validation_cli() {
  set +x
  test -d "${docker_validation_config:?}" || return 1
  test -S "$HOME/.docker/run/docker.sock" || return 1
  test -n "${PRESSWATCH_PRODUCTION_TEST_PASSWORD:-}" || return 1
  if env -i PATH=/usr/bin:/bin /bin/sh -c \
    'command -v docker-credential-osxkeychain >/dev/null 2>&1'; then
    printf '%s\n' '認証helperが見つかったため、Docker検証を中止します。' >&2
    return 1
  fi
  env -i HOME="$HOME" PATH=/usr/bin:/bin TMPDIR="${validation_root:?}" \
    DOCKER_CONFIG="$docker_validation_config" \
    DOCKER_HOST="unix://$HOME/.docker/run/docker.sock" \
    BUILDX_CONFIG="$docker_validation_config/buildx" \
    COMPOSE_DISABLE_ENV_FILE=1 \
    PRESSWATCH_PRODUCTION_TEST_PASSWORD="$PRESSWATCH_PRODUCTION_TEST_PASSWORD" \
    /Applications/Docker.app/Contents/Resources/bin/docker "$@"
}
```

必要なソース・設定・fixtureだけを`validation_root`内へコピーし、そのルートへ移動する。
秘密ファイル・認証設定・既存依存・生成物はコピーしない。
一時パスワードは表示・保存せず、Composeの設定確認には`--quiet`を使う。
以後のDocker操作はすべて`production_validation_cli`で実行し、エラー時は後続処理へ進まない。

4サービスを内部ネットワークだけに接続し、ホストへポートを公開しない。
HTTPの確認にはWebイメージに含まれるNode.jsを使い、検証用の中継サービスは置かない。
このComposeは本番配置には使わない。

同名のproject・イメージ・コンテナ・ネットワークがあれば作業を止めて確認する。
通常の再確認ではビルドキャッシュを使う。
初回の再現性確認やキャッシュの影響を切り分けるためにクリーンビルドが必要な場合だけ、下記の`build`コマンドに`--no-cache`を追加する。

```bash
(
set -e
production_validation_cli compose -f infra/compose.production-test.yml --profile job config --quiet
production_validation_cli compose -f infra/compose.production-test.yml --profile job build
production_validation_cli compose -f infra/compose.production-test.yml up -d --wait db
production_validation_cli compose -f infra/compose.production-test.yml run --rm -T api .venv/bin/alembic upgrade head
production_validation_cli compose -f infra/compose.production-test.yml run --rm -T api .venv/bin/python -m press_watch_api.commands.seed_fixed_categories
production_validation_cli compose -f infra/compose.production-test.yml run --rm -T job
production_validation_cli compose -f infra/compose.production-test.yml run --rm -T job
production_validation_cli compose -f infra/compose.production-test.yml up -d web api
production_validation_cli compose -f infra/compose.production-test.yml exec -T web node --input-type=module <<'JS'
for (const url of ["http://api:8000/health", "http://api:8000/press-releases", "http://127.0.0.1:3000/"]) {
  let response;
  for (let attempt = 0; attempt < 30; attempt++) {
    response = await fetch(url, { signal: AbortSignal.timeout(1000) }).catch(() => null);
    if (response?.ok) break;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  if (!response?.ok) throw new Error(`起動・HTTP応答の確認失敗: ${url}`);
  console.log(url, response.status);
}
JS
)
```

初回62件保存・再実行62件skipと分類結果を確認し、HTML fixtureだけを使う。
DB初期化・保存・画面テストは順次実行する。
HTTP応答の確認はブラウザー操作の検証とは区別し、画面の振る舞いには既存のWeb画面テストを使う。

不正fixtureと接続不能な専用DB設定で非ゼロ終了、productionの`/mock`・`/ui-foundation`の404、静的ファイルの200を確認する。
空のuvキャッシュでジョブを実行し、非rootと通信遮断を確認する。
秘密情報を含まないダミー`.env`を一時contextのルート・Web配下へ置き、build contextと実行イメージへの非混入を確認する。

途中で失敗した場合も、終了時は`production_validation_cli compose -f infra/compose.production-test.yml down`を実行する。
今回作成したイメージ・一時領域だけを削除してから`unset PRESSWATCH_PRODUCTION_TEST_PASSWORD`で一時パスワードを破棄する。
共有キャッシュの一括pruneや既存ボリュームの削除は行わない。

## 確認結果と未確認事項

2026年11月2日にNode.js 24.22.2・pnpm 12.8.1・Next.js 16.4.1・React 19.3.1、Python 3.14.10・uv 0.11.2・PostgreSQL 17.11で確認した。

| 確認 | 結果 |
| --- | --- |
| 本番イメージ | Linux arm64のクリーンビルド、Web・APIの起動・停止、ジョブの正常・失敗終了を確認。amd64もエミュレーションでビルド・起動確認 |
| Web | 型・lint・format・build成功、既存画面176件と本番Docker＋専用DBの画面3件が成功 |
| Python | Linux arm64・ネットワークなしでAPI 286件、scraper 150件が成功 |
| 保存 | 合成62件の保存・分類、再実行で62件skip、不正fixture・DB接続失敗で終了1 |
| 安全性 | ダミーenvのcontext・runtime非混入、非root、APIから固定外部IPへの通信遮断、空uvキャッシュでのジョブ実行を確認 |
| 検証手順・CI判定 | 専用CLIの変数伝達・不要変数の除外・未設定時停止・Compose設定検証、CI判定6ケースが成功 |

構成整理後はrelay・入口用ネットワーク・公開ポートを削除し、4サービス構成で3イメージを再ビルドした。
保存・重複skip、API検索5条件とWebのHTML応答、静的ファイル、不正fixture・DB停止時の失敗終了、Web・APIの停止を再確認した。
実コンテナの内部ネットワーク・ポート非公開・DBのtmpfs、Webの非rootと固定外部IPへの通信遮断、APIの非rootも確認した。
これはHTTPの確認であり、ブラウザー操作のテストは再実行していない。

測定はDocker DesktopのLinux arm64、8 CPU・メモリ約7.65 GiB、サービス別の資源制限なしで実施した。
以下は整理前のrelayを含む構成での測定であり、整理後の構成では再測定していない。
Web・APIは60秒のアイドル後、一覧・検索・カテゴリ等の合成要求を同時数1と5で各100回実行した。
以下のWeb・APIメモリは軽量サンプラーを含む65回・1秒間隔の観測範囲、CPUは観測全体の累積で、ジョブのメモリは処理終了前のcgroupピークである。

| 対象 | メモリ | CPU累積 |
| --- | --- | --- |
| Web | 50.3〜189.7 MiB | 1.616秒 |
| API | 77.6〜86.1 MiB | 1.291秒 |
| ジョブ（初回62件保存） | ピーク108.3 MiB | 1.50秒 |
| ジョブ（62件skip） | ピーク108.5 MiB | 1.25秒 |

実DB検索・保存は合成62件だけであり、この測定を実データ規模・Railway性能・請求額へ外挿しない。
今回作成したDocker資源・一時領域は削除済みである。

実CIと既存PostgreSQL統合テスト一式、実サイト、既存DB・Supabase、クラウド配置は未実施である。
Next.js修正版の採用後に再ビルド・回帰確認・再測定を行い、公開・定期実行へ進む。
