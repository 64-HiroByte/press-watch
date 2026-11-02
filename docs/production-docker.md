# 本番用Dockerと隔離検証

## 構成と起動

Webは`infra/docker/web.Dockerfile`、Pythonは`infra/docker/python.Dockerfile`を使い、build contextはリポジトリルートとする。
両Dockerfileは依存導入を共有し、`development`・`production`ターゲットで開発・本番の起動方法を分ける。
Pythonの`job`ターゲットはAPIの本番共通部分にscraperを追加する。
開発用の`infra/compose.yml`と隔離検証用Composeは、それぞれの`build.target`を明示する。
Dockerfileを直接buildする場合も、開発は`--target development`、本番は`--target production`、ジョブは`--target job`を指定する。
PythonのAPI用venvは開発・本番とも`/app/.venv`に置き、本番ソースはジョブの相対参照に合わせて`/workspace/apps/api`に置く。

| 対象 | 起動・設定 |
| --- | --- |
| Web | `node apps/web/server.js`。`HOSTNAME`は既定`0.0.0.0`、`PORT`は既定3000、`PRESSWATCH_API_BASE_URL`を実行時に設定する |
| API | Uvicornを1 worker・reloadなしで起動する。`HOST`は既定`0.0.0.0`、`PORT`は既定8000、`DATABASE_URL`を実行時に設定する |
| ジョブ | 既存の`fetch_and_save_env_press`をentrypointとし、コンテナ引数をCLIへ渡す。`DATABASE_URL`を実行時に設定する |

Webのstandalone出力は本番Dockerのビルド時だけ`PRESSWATCH_STANDALONE=1`で有効にする。
開発Webは`pnpm --filter @press-watch/web exec node --version`で`verifyDepsBeforeRun: error`による依存検証を通し、成功後に`exec`でNext.js CLIへ置き換えて停止要求をCLIの終了処理へ渡す。
依存ボリュームを再利用する場合も検証し、不整合があれば起動を失敗させる。
現在の`dev`スクリプトと同じ`next dev`を実行しており、スクリプトに前処理等を追加する場合はDockerの起動方法も確認する。
APIには現在開発専用依存がないため、開発ターゲットも共通のvenvをそのまま使う。
開発専用依存を追加する場合は、開発ターゲットでの導入も必要になる。
ジョブはAPI・scraperのソースと両venvを既存CLIが参照する配置に収録し、`/etc/uv/uv.toml`で実行時の依存・Python取得を禁止する。
ジョブの停止シグナルは`SIGINT`とし、Dockerの停止要求を既存CLIの中断・子プロセス停止処理へ渡す。
中断時の終了130は正常完了の0と区別し、配置先が`SIGTERM`を明示する場合は別途停止処理への対応が必要になる。

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
HTTPの確認にはWebイメージに含まれるNode.jsを使う。
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
production_validation_cli compose -f infra/compose.production-test.yml run --rm -T api /app/.venv/bin/alembic upgrade head
production_validation_cli compose -f infra/compose.production-test.yml run --rm -T api /app/.venv/bin/python -m press_watch_api.commands.seed_fixed_categories
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
待機する合成scraper子プロセスでジョブを起動し、シグナルを上書きしない`docker stop`で猶予内の中断終了・子プロセスの停止を確認する。
秘密情報を含まないダミー`.env`を一時contextのルート・Web配下へ置き、build contextと実行イメージへの非混入を確認する。

途中で失敗した場合も、終了時は`production_validation_cli compose -f infra/compose.production-test.yml down`を実行する。
今回作成したイメージ・一時領域だけを削除してから`unset PRESSWATCH_PRODUCTION_TEST_PASSWORD`で一時パスワードを破棄する。
共有キャッシュの一括pruneや既存ボリュームの削除は行わない。

## 開発ターゲットの回帰確認

`infra/compose.yml`を一時ソース・専用project・専用ボリュームで使い、検証用overrideで公開ポートを除去し、DBをtmpfs・ネットワークを内部限定にする。
通常の開発環境のボリュームやDBは使わない。
Web・APIの起動と一時ソース変更の反映を確認した後、依存ボリュームを残したままWeb・APIコンテナを再作成する。
コンテナIDが変わり、`api_venv`・`web_root_node_modules`・`web_app_node_modules`内の確認用ファイルが保持され、両サービスが再起動することを確認する。
開発Webの起動方法を変更した際は、一時コピーでマニフェストだけを変更した場合と、lockfileも変更して既存の依存ボリュームを残した場合に、依存検証エラーで停止することを確認する。
整合した状態での初回起動・ボリューム再利用・変更を戻した後の再起動と、通常停止も確認する。
終了時は専用projectのボリュームだけを削除する。

## 検証範囲と公開前の確認

合成62件による検証から、実データ規模での性能・配置先の費用を判断しない。
性能や費用の判断には、現行イメージと想定する負荷での測定が必要になる。
現行構成に対するamd64・実CI・本番Dockerでのブラウザー操作、実HTTP巡回中・DB保存中の中断確認は未完了である。
実サイト・既存DB・Supabase・クラウド配置の確認は、合成データによる検証とは別に行う。
公開前の依存更新・配置・定期実行の条件は[デプロイ構成と運用計画](deployment.md)を参照する。
