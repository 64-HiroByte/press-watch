"""一時PostgreSQL17で監督入口のTLS・排他・保存権限・期限を確認"""

import io
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

import psycopg
from psycopg import sql
from sqlalchemy import create_engine, URL
from sqlalchemy.orm import sessionmaker

import press_watch_api.models  # noqa: F401
from press_watch_api.models.base import Base
from press_watch_api.commands import run_fetch_job as job
from press_watch_api.commands.seed_fixed_categories import main as seed
from press_watch_api.config import DATABASE_URL_ENV

ROOT = Path(__file__).resolve().parents[3]
DOCKER_BINARY = (
    '/Applications/Docker.app/Contents/Resources/bin/docker'
    if sys.platform == 'darwin'
    else '/usr/bin/docker'
)
ORIGINAL_JOB_IMAGE = 'presswatch-original-job-validation:local'
SCHEDULED_JOB_IMAGE = 'presswatch-scheduled-job-validation:local'
JOB_PYTHON = '/app/.venv/bin/python'
TEST_DATABASE = 'presswatch_job_test'
CHECK_DATABASE_ARGS = (
    '--check-db-only',
    '--expected-db-user', 'job_writer',
    '--expected-db-name', TEST_DATABASE,
)


def _verify(
    port: int,
    password: str,
    directory: Path,
    environment: dict[str, str],
    container: str,
) -> None:
    """最初の管理接続から隔離環境を適用して一時DBを検証

    Args:
        port: 一時DBのlocalhostポート
        password: 生成した検証DBのパスワード
        directory: テスト用CA配置先
        environment: 親のDB・libpq設定を除去した環境
        container: この実行で作成したDBコンテナ名
    """
    with patch.dict(os.environ, environment, clear=True):
        _verify_database(port, password, directory, environment, container)


def _verify_database(
    port: int,
    password: str,
    directory: Path,
    environment: dict[str, str],
    container: str,
) -> None:
    """生成した隔離DBだけで接続・保存・不要権限拒否を検証

    Args:
        port: Dockerがlocalhostへ割り当てた一時ポート
        password: 生成した検証DBのパスワード
        directory: 生成した検証用証明書の配置先
        environment: 親のDB・libpq設定を除去した実行環境
        container: この実行が生成した一時DBコンテナ名
    """
    ca = directory / 'server.crt'
    options = dict(
        host='127.0.0.1',
        port=port,
        dbname=TEST_DATABASE,
        user='postgres',
        password=password,
        sslmode='verify-full',
        sslrootcert=str(ca),
        autocommit=True,
        connect_timeout=2,
    )
    deadline = time.monotonic() + 30
    while True:
        try:
            admin = psycopg.connect(**options)
            break
        except psycopg.OperationalError:
            if time.monotonic() >= deadline:
                raise RuntimeError('local TLS database did not become ready') from None
            time.sleep(.2)
    with admin:
        url = URL.create(
            'postgresql+psycopg',
            username='postgres',
            password=password,
            host='127.0.0.1',
            port=port,
            database=TEST_DATABASE,
            query={'sslmode': 'verify-full', 'sslrootcert': str(ca)},
        )
        engine = create_engine(url)
        try:
            Base.metadata.create_all(engine)
            assert seed(
                [],
                session_factory=sessionmaker(engine),
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            ) == 0
        finally:
            engine.dispose()
        writer_password = secrets.token_urlsafe(24)
        admin.execute(
            sql.SQL(
                'CREATE ROLE job_writer LOGIN PASSWORD {} CONNECTION LIMIT 4'
            ).format(sql.Literal(writer_password))
        )
        admin.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
        admin.execute('GRANT USAGE ON SCHEMA public TO job_writer')
        admin.execute(
            'GRANT SELECT ON press_releases, fixed_categories, '
            'fixed_category_keywords, press_release_fixed_categories TO job_writer'
        )
        admin.execute(
            'GRANT INSERT ON press_releases, '
            'press_release_fixed_categories TO job_writer'
        )
        sequence = admin.execute(
            "SELECT pg_get_serial_sequence('press_releases', 'id')"
        ).fetchone()[0]
        admin.execute(
            sql.SQL('GRANT USAGE ON SEQUENCE {} TO job_writer').format(
                sql.Identifier(*sequence.split('.'))
            )
        )
        target = url.set(
            username='job_writer',
            password=writer_password,
            query={'sslmode': 'verify-full'},
        )
        env = {
            **environment,
            DATABASE_URL_ENV: target.render_as_string(hide_password=False),
            'PRESSWATCH_DB_CA_CERT': ca.read_text(),
        }
        with patch.dict(os.environ, env, clear=True):
            assert job.main(CHECK_DATABASE_ARGS) == 0
            mismatched_identities = (
                ('postgres', TEST_DATABASE),
                ('job_writer', 'other'),
            )
            for expected_user, expected_database in mismatched_identities:
                assert job.main([
                    '--check-db-only',
                    '--expected-db-user', expected_user,
                    '--expected-db-name', expected_database,
                ]) == 1
            rejected_tls_cases = (
                ('localhost', ca),
                ('127.0.0.1', directory / 'wrong.crt'),
            )
            for host, certificate in rejected_tls_cases:
                with patch.dict(
                    os.environ,
                    {
                        DATABASE_URL_ENV: target.set(host=host).render_as_string(
                            hide_password=False,
                        ),
                        'PRESSWATCH_DB_CA_CERT': certificate.read_text(),
                    },
                ):
                    assert job.main(CHECK_DATABASE_ARGS) == 1
            admin.execute('SELECT pg_advisory_lock(%s)', (job.LOCK_KEY,))
            try:
                assert job.main(CHECK_DATABASE_ARGS) == 3
            finally:
                admin.execute('SELECT pg_advisory_unlock(%s)', (job.LOCK_KEY,))
            command = [
                '--from-file',
                str(ROOT / 'infra/fixtures/api-validation-press.html'),
            ]
            assert job.main(command) == 0
            first = admin.execute('SELECT count(*) FROM press_releases').fetchone()[0]
            assert first > 0
            assert job.main(command) == 0
            assert admin.execute('SELECT count(*) FROM press_releases').fetchone()[0] == first
            job_image_cases = (
                (ORIGINAL_JOB_IMAGE, False),
                (SCHEDULED_JOB_IMAGE, True),
            )
            for image, tls in job_image_cases:
                container_url = target.set(
                    port=5432,
                    query={'sslmode': 'verify-full'} if tls else {},
                )
                container_env = {
                    **environment,
                    DATABASE_URL_ENV: container_url.render_as_string(hide_password=False),
                }
                if tls:
                    container_env['PRESSWATCH_DB_CA_CERT'] = ca.read_text()
                arguments = [
                    DOCKER_BINARY,
                    'run',
                    '--rm',
                    '--pull',
                    'never',
                    '--network',
                    f'container:{container}',
                    '-e',
                    DATABASE_URL_ENV,
                    '-v',
                    f'{ROOT / "infra/fixtures/api-validation-press.html"}'
                    ':/fixtures/press.html:ro',
                ]
                if tls:
                    arguments += ['-e', 'PRESSWATCH_DB_CA_CERT']
                subprocess.run(
                    [*arguments, image, '--from-file', '/fixtures/press.html'],
                    check=True,
                    env=container_env,
                    stdout=subprocess.DEVNULL,
                )
                assert admin.execute('SELECT count(*) FROM press_releases').fetchone()[0] == first
            _interrupted_saves(admin, target, environment, container, ca.read_text())
            forbidden_queries = (
                'UPDATE press_releases SET title=title',
                'DELETE FROM press_releases',
                'TRUNCATE press_releases',
                'CREATE TABLE public.forbidden(id int)',
            )
            writer_options = {
                **options,
                'user': 'job_writer',
                'password': writer_password,
            }
            for query in forbidden_queries:
                with psycopg.connect(**writer_options) as writer:
                    try:
                        writer.execute(query)
                    except psycopg.errors.InsufficientPrivilege:
                        pass
                    else:
                        raise AssertionError('unexpected writer privilege')
            admin.execute("ALTER ROLE job_writer VALID UNTIL '2000-01-01 00:00:00+00'")
            assert job.main(CHECK_DATABASE_ARGS) == 1
            admin.execute("ALTER ROLE job_writer VALID UNTIL 'infinity'")
            assert job.main(CHECK_DATABASE_ARGS) == 0


def _interrupted_saves(
    admin,
    target: URL,
    environment: dict[str, str],
    container: str,
    certificate: str,
) -> None:
    """実保存CLIのcommit前後を中断し、新実行見送りと再実行を照合

    Args:
        admin: この一時DBへの管理接続
        target: 保存用ロールの接続URL
        environment: ローカルDockerへ固定した隔離環境
        container: この実行で生成したDBコンテナ名
        certificate: この検証で生成したCA
    """
    baseline = admin.execute('SELECT * FROM press_releases ORDER BY id').fetchall()
    memberships = admin.execute('SELECT * FROM press_release_fixed_categories ORDER BY 1, 2').fetchall()
    env = {
        **environment,
        DATABASE_URL_ENV: target.set(port=5432).render_as_string(hide_password=False),
        'PRESSWATCH_DB_CA_CERT': certificate,
    }
    prefix = [
        DOCKER_BINARY,
        'run',
        '--rm',
        '--pull',
        'never',
        '--network',
        f'container:{container}',
        '-e',
        DATABASE_URL_ENV,
        '-e',
        'PRESSWATCH_DB_CA_CERT',
    ]
    for phase in ('before', 'after'):
        source = f'https://www.env.go.jp/press/synthetic-{phase}.html'
        worker = f"""
            from datetime import date
            from pathlib import Path
            import time

            from sqlalchemy.orm import Session

            from press_watch_api.commands import fetch_and_save_env_press as fetch

            original = Session.commit


            def commit(self):
                if {phase!r} == 'after':
                    original(self)
                Path('/tmp/save-ready').touch()
                time.sleep(60)
                if {phase!r} == 'before':
                    original(self)


            Session.commit = commit
            release = fetch.ScraperCliRelease(
                '大気の合成検証', date(2026, 11, 1), {source!r}, (),
            )
            result = fetch.CollectedPressReleases('synthetic', (release,), (), None)
            raise SystemExit(
                fetch.main(
                    ['--from-file', '/unused'],
                    collect_releases=lambda *args: result,
                )
            )
        """
        driver = f"""
            import os
            import sys

            from press_watch_api.commands.run_fetch_job import (
                connection_environment,
                supervise,
            )
            from press_watch_api.db_tls import certificate_environment

            with certificate_environment():
                env = connection_environment(os.environ)
                env['PGSSLROOTCERT'] = os.environ['PGSSLROOTCERT']
                code = supervise(
                    [sys.executable, '-c', {worker!r}],
                    env,
                    timeout=30,
                    grace=2,
                )
            raise SystemExit(code)
        """
        name = f'presswatch-save-stop-{secrets.token_hex(4)}'
        process = subprocess.Popen(
            [
                *prefix,
                '--name',
                name,
                '--entrypoint',
                JOB_PYTHON,
                SCHEDULED_JOB_IMAGE,
                '-c',
                driver,
            ],
            env=env,
            stdout=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 15
            while True:
                ready = subprocess.run(
                    [DOCKER_BINARY, 'exec', name, 'test', '-f', '/tmp/save-ready'],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if ready.returncode == 0:
                    break
                if process.poll() is not None or time.monotonic() > deadline:
                    raise AssertionError('save barrier was not reached')
                time.sleep(.1)
            # 新配置が競合で見送られた後に、旧配置へSIGTERMが届く順序を再現する。
            new = subprocess.run(
                [
                    *prefix,
                    SCHEDULED_JOB_IMAGE,
                    *CHECK_DATABASE_ARGS,
                ],
                env=env,
                stdout=subprocess.DEVNULL,
            )
            assert new.returncode == 3
            subprocess.run(
                [DOCKER_BINARY, 'kill', '--signal', 'TERM', name],
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            assert process.wait(timeout=10) == 143
            count = admin.execute(
                'SELECT count(*) FROM press_releases WHERE source_url=%s',
                (source,),
            ).fetchone()[0]
            assert count == (1 if phase == 'after' else 0)
            assert admin.execute(
                'SELECT * FROM press_releases ORDER BY id LIMIT %s',
                (len(baseline),),
            ).fetchall() == baseline
            assert admin.execute(
                'SELECT * FROM press_release_fixed_categories ORDER BY 1, 2 LIMIT %s',
                (len(memberships),),
            ).fetchall() == memberships
            replay = worker.replace('Session.commit = commit', '# 通常のcommitで再実行')
            replay_driver = driver.replace(repr(worker), repr(replay))
            replay_command = [
                *prefix,
                '--entrypoint',
                JOB_PYTHON,
                SCHEDULED_JOB_IMAGE,
                '-c',
                replay_driver,
            ]
            for _ in range(2):
                result = subprocess.run(
                    replay_command,
                    env=env,
                    stdout=subprocess.DEVNULL,
                )
                assert result.returncode == 0
                assert admin.execute(
                    'SELECT count(*) FROM press_releases WHERE source_url=%s',
                    (source,),
                ).fetchone()[0] == 1
            baseline = admin.execute('SELECT * FROM press_releases ORDER BY id').fetchall()
            memberships = admin.execute('SELECT * FROM press_release_fixed_categories ORDER BY 1, 2').fetchall()
        finally:
            subprocess.run(
                [DOCKER_BINARY, 'rm', '--force', name],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if process.poll() is None:
                process.kill()
            process.wait()


def main() -> int:
    """既存イメージで一時DBを起動し、検証後にコンテナとテスト鍵を削除

    Returns:
        全検証成功0、失敗時は例外によって非0
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith('PG')
        and key not in (DATABASE_URL_ENV, 'PRESSWATCH_DB_CA_CERT')
    }
    password = secrets.token_urlsafe(24)
    name = f'presswatch-job-tls-{secrets.token_hex(5)}'
    with tempfile.TemporaryDirectory(prefix='presswatch-job-tls-') as temporary:
        directory = Path(temporary)
        config = directory / 'docker-config'
        config.mkdir()
        env = local_environment(env, str(config))
        for prefix in ('server', 'wrong'):
            subprocess.run(
                [
                    'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                    '-keyout', str(directory / f'{prefix}.key'),
                    '-out', str(directory / f'{prefix}.crt'),
                    '-days', '1', '-subj', '/CN=presswatch-local-test',
                    '-addext', 'subjectAltName=IP:127.0.0.1',
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        try:
            subprocess.run(
                [
                    DOCKER_BINARY, 'run', '--detach', '--pull', 'never',
                    '--name', name,
                    '--tmpfs', '/var/lib/postgresql/data',
                    '-p', '127.0.0.1::5432',
                    '-e', 'POSTGRES_PASSWORD',
                    '-e', f'POSTGRES_DB={TEST_DATABASE}',
                    '-v', f'{directory}:/test:ro',
                    '--entrypoint', '/bin/sh', 'postgres:17', '-c',
                    'cp /test/server.key /tmp/server.key; '
                    'cp /test/server.crt /tmp/server.crt; '
                    'chown postgres:postgres /tmp/server.key /tmp/server.crt; '
                    'chmod 600 /tmp/server.key; '
                    'exec docker-entrypoint.sh postgres -c ssl=on '
                    '-c ssl_cert_file=/tmp/server.crt '
                    '-c ssl_key_file=/tmp/server.key',
                ],
                check=True,
                env={**env, 'POSTGRES_PASSWORD': password},
                stdout=subprocess.DEVNULL,
            )
            output = subprocess.check_output(
                [DOCKER_BINARY, 'port', name, '5432/tcp'],
                env=env,
                text=True,
            ).strip()
            assert output.startswith('127.0.0.1:')
            _verify(int(output.rsplit(':', 1)[1]), password, directory, env, name)
            print(
                'Local TLS, advisory lock, writer permissions, '
                'deduplication and password expiry: OK'
            )
        finally:
            subprocess.run(
                [DOCKER_BINARY, 'rm', '--force', name],
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
            )
    return 0


def local_environment(environment: dict[str, str], config: str) -> dict[str, str]:
    """専用Docker設定と既知ローカルsocketを使う検証環境を生成

    Args:
        environment: 継承元環境
        config: この検証用に作成した空のDocker設定ディレクトリ

    Returns:
        親のDB・libpq・Docker接続設定を除去した実行環境

    Raises:
        RuntimeError: 既知ローカルsocketまたは固定CLIが存在しない場合
    """
    endpoint = (
        Path.home() / '.docker/run/docker.sock'
        if sys.platform == 'darwin'
        else Path('/var/run/docker.sock')
    )
    if not endpoint.is_socket() or not Path(DOCKER_BINARY).is_file():
        raise RuntimeError('known local Docker endpoint is unavailable')
    env = {
        key: value
        for key, value in environment.items()
        if not key.startswith(('PG', 'DOCKER_'))
        and key not in (DATABASE_URL_ENV, 'PRESSWATCH_DB_CA_CERT', 'BUILDX_CONFIG')
    }
    env.update(DOCKER_HOST=f'unix://{endpoint}', DOCKER_CONFIG=config)
    return env


if __name__ == '__main__':
    raise SystemExit(main())
