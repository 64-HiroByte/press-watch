"""定期取得のTLS・DB排他・時間上限とプロセス群の停止監督"""

import argparse
from collections.abc import Mapping, Sequence
import ctypes
import importlib.util
import fcntl
import io
import os
import signal
import shutil
import socket
import subprocess
import sys
import time

from sqlalchemy.engine import make_url

from press_watch_api.config import DATABASE_URL_ENV
from press_watch_api.db_tls import certificate_environment

LOCK_KEY = 0x5052455353574154
HEARTBEAT_SECONDS = 5
RESPONSE_SECONDS = 5
RUN_SECONDS = 1800
GRACE_SECONDS = 15
SUPERVISOR_FAILURE_REASON = 'supervisor_failed_save_state_unknown'


def connection_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """対象URLのTLSを検証し、親のlibpq設定を取り除いた接続環境を生成

    Args:
        environment: 明示された対象URLとCAを含む継承元環境

    Returns:
        対象URL、CA、接続待ち・SQL待ちの上限を設定した子プロセス環境

    Raises:
        ValueError: CAまたはDirect接続用URLの形式・接続情報・TLS指定が不適切な場合
    """
    if not environment.get('PRESSWATCH_DB_CA_CERT', '').strip():
        raise ValueError('job CA is required')

    invalid_url_message = 'job requires a Direct URL with only sslmode=verify-full'
    database_url = environment.get(DATABASE_URL_ENV, '')
    try:
        url = make_url(database_url)
    except Exception:
        url = None
    if url is None:
        raise ValueError(invalid_url_message)

    if url.drivername not in ('postgresql', 'postgresql+psycopg'):
        raise ValueError(invalid_url_message)

    host = url.host
    if not host or host.startswith(('/', '@')) or ',' in host or 'pooler' in host.lower():
        raise ValueError(invalid_url_message)

    if not (url.username and url.password and url.database):
        raise ValueError(invalid_url_message)

    if set(url.query) != {'sslmode'} or url.query['sslmode'] != 'verify-full':
        raise ValueError(invalid_url_message)

    env = {
        key: value
        for key, value in environment.items()
        if not key.startswith('PG')
        and key not in (DATABASE_URL_ENV, 'PRESSWATCH_LOCK_FD')
    }
    url = url.set(drivername='postgresql+psycopg').update_query_dict(
        {
            'connect_timeout': '5',
            'options': '-c statement_timeout=30000 -c lock_timeout=5000',
        }
    )
    env[DATABASE_URL_ENV] = url.render_as_string(hide_password=False)
    return env


def _report(reason: str, code: int) -> None:
    """停止監督を待たせず、秘密値を含まない結果をstderrへ出力

    Args:
        reason: 固定の終了理由
        code: プロセス終了コード
    """
    message = f'job reason={reason} exit_code={code}\n'
    if isinstance(sys.stderr, io.StringIO):
        sys.stderr.write(message)
        return
    try:
        descriptor = sys.stderr.fileno()
        flags = fcntl.fcntl(descriptor, fcntl.F_GETFL)
        try:
            fcntl.fcntl(descriptor, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            os.write(descriptor, message.encode('utf-8'))
        finally:
            fcntl.fcntl(descriptor, fcntl.F_SETFL, flags)
    except (OSError, ValueError):
        pass


def _lock_worker(expected_identity: tuple[str, str] | None = None) -> int:
    """同一物理接続でロック保持と照会を行う隔離プロセス

    Args:
        expected_identity: 診断時に照合するロール名・DB名、取得時はNone

    Returns:
        正常な解放は0、接続主体の不一致・接続・監視エラーは1
    """
    import psycopg

    channel = socket.socket(fileno=int(os.environ['PRESSWATCH_LOCK_FD']))
    channel.settimeout(HEARTBEAT_SECONDS)
    try:
        url = make_url(os.environ[DATABASE_URL_ENV])
        with psycopg.connect(
            host=url.host,
            port=url.port or 5432,
            dbname=url.database,
            user=url.username,
            password=url.password,
            sslmode='verify-full',
            sslrootcert=os.environ['PGSSLROOTCERT'],
            connect_timeout=5,
            options='-c statement_timeout=5000 -c lock_timeout=5000',
            autocommit=True,
        ) as connection:
            if expected_identity is not None:
                actual = connection.execute(
                    'SELECT current_user, current_database()',
                ).fetchone()
                if actual != expected_identity:
                    channel.send(b'failed')
                    return 1
            locked = connection.execute(
                'SELECT pg_try_advisory_lock(%s)',
                (LOCK_KEY,),
            ).fetchone()[0]
            channel.send(b'locked' if locked else b'conflict')
            if not locked:
                return 0
            while True:
                try:
                    message = channel.recv(100)
                    if message == b'stop' or not message:
                        return 0
                except TimeoutError:
                    connection.execute('SELECT 1').fetchone()
                    channel.send(b'alive')
    except Exception:
        try:
            channel.send(b'failed')
        except OSError:
            pass
        return 1
    finally:
        channel.close()


def _signal_group(process: subprocess.Popen, number: int) -> None:
    """取得プロセスと同じセッションのuv・scraperへシグナルを送信

    Args:
        process: 新規セッションで起動した取得プロセス
        number: 送るシグナル
    """
    try:
        os.killpg(process.pid, number)
    except ProcessLookupError:
        pass


def _group_alive(process: subprocess.Popen) -> bool:
    """直接の子とLinuxで引き取った子孫を回収し、残存群を確認

    Args:
        process: 取得プロセス群のリーダー

    Returns:
        回収できていないプロセス群が残っていればTrue
    """
    process.poll()
    if process.returncode is not None:
        try:
            while os.waitpid(-process.pid, os.WNOHANG)[0]:
                pass
        except ChildProcessError:
            pass
    try:
        os.killpg(process.pid, 0)
        return True
    except ProcessLookupError:
        return False


def supervise(
    command: Sequence[str],
    environment: Mapping[str, str],
    *,
    lock_command: Sequence[str] | None = None,
    timeout: float = RUN_SECONDS,
    grace: float = GRACE_SECONDS,
    heartbeat_timeout: float = HEARTBEAT_SECONDS + RESPONSE_SECONDS,
    check_only: bool = False,
    expected_identity: tuple[str, str] | None = None,
) -> int:
    """DB照会・ログ出力から独立して取得の期限と排他保持を監督

    Args:
        command: 新規セッションで実行する既存取得CLI
        environment: CAファイル指定を含む検証済み接続環境
        lock_command: テスト用の合成ロック保持コマンド、通常は内部入口
        timeout: 監督開始からの実行時間上限
        grace: 取得群への停止通知から強制終了までの猶予
        heartbeat_timeout: ロック保持プロセスからの最大無応答時間
        check_only: ロック取得・解放の確認だけを行うか
        expected_identity: 診断時に同じ接続で照合するロール名・DB名

    Returns:
        取得成功0、競合3、期限124、signal130/143、その他の異常1
    """
    started = time.monotonic()
    received_signal = 0

    def on_signal(number, _frame) -> None:
        """追加シグナルでも後片付けの順序を維持するための停止要求記録

        Args:
            number: OSから受けたシグナル
            _frame: Pythonのシグナル実行フレーム
        """
        nonlocal received_signal
        if not received_signal:
            received_signal = number

    previous = {
        number: signal.signal(number, on_signal)
        for number in (signal.SIGTERM, signal.SIGINT)
    }
    if sys.platform == 'linux':
        # PID 1以外の起動でも、uvが先に終了した場合の子孫を回収する。
        if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
            for number, handler in previous.items():
                signal.signal(number, handler)
            _report('subreaper_failed', 1)
            return 1
    parent, child = socket.socketpair(type=socket.SOCK_DGRAM)
    parent.setblocking(False)
    worker = None
    lock_process = None
    code, reason = 1, 'failed'
    env = dict(environment)
    env['PRESSWATCH_LOCK_FD'] = str(child.fileno())
    try:
        lock_process = subprocess.Popen(
            lock_command or [
                sys.executable,
                '-m',
                'press_watch_api.commands.run_fetch_job',
                '--lock-worker',
                *(expected_identity or ()),
            ],
            env=env,
            pass_fds=(child.fileno(),),
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        child.close()
        last_response = started
        while True:
            now = time.monotonic()
            if received_signal:
                code, reason = 128 + received_signal, 'interrupted'
                break
            if now - started >= timeout:
                code, reason = 124, 'timeout'
                break
            if now - last_response >= heartbeat_timeout:
                reason = 'lock_unresponsive'
                break
            try:
                message = parent.recv(100)
            except BlockingIOError:
                message = None
            if message == b'conflict':
                code, reason = 3, 'lock_conflict'
                break
            if message == b'failed':
                reason = 'lock_failed'
                break
            if message in (b'locked', b'alive'):
                last_response = now
            if message == b'locked':
                if check_only:
                    code, reason = 0, 'database_checked'
                    break
                worker_env = dict(environment)
                worker_env.pop('PRESSWATCH_LOCK_FD', None)
                worker = subprocess.Popen(
                    command,
                    env=worker_env,
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                )
            if lock_process.poll() is not None:
                reason = 'lock_lost'
                break
            if worker is not None and worker.poll() is not None:
                code = 0 if worker.returncode == 0 else 1
                reason = (
                    'completed'
                    if code == 0
                    else 'acquisition_failed_save_state_unknown'
                )
                break
            time.sleep(.02)
    except Exception:
        code, reason = 1, SUPERVISOR_FAILURE_REASON
    finally:
        child.close()
        cleanup_deadline = time.monotonic() + grace
        if worker is not None:
            _signal_group(worker, signal.SIGTERM)
            until = cleanup_deadline
            while _group_alive(worker) and time.monotonic() < until:
                time.sleep(.02)
            _signal_group(worker, signal.SIGKILL)
            # 強制終了後は全群の回収を先に行い、ロックを後から解放する。
            while _group_alive(worker):
                time.sleep(.02)
        if lock_process is not None:
            try:
                parent.send(b'stop')
            except OSError:
                pass
            try:
                lock_process.wait(
                    timeout=max(
                        0,
                        min(
                            RESPONSE_SECONDS + .2,
                            cleanup_deadline - time.monotonic(),
                        ),
                    ),
                )
            except subprocess.TimeoutExpired:
                lock_process.kill()
                lock_process.wait()
                if code == 0:
                    code, reason = 1, 'lock_cleanup_forced_save_state_unknown'
            if lock_process.returncode != 0 and code == 0:
                code, reason = 1, 'lock_cleanup_failed_save_state_unknown'
        parent.close()
        for number, handler in previous.items():
            signal.signal(number, handler)
    if received_signal and code == 0:
        code, reason = 128 + received_signal, 'interrupted'
    _report(reason, code)
    return code


def main(argv: Sequence[str] | None = None) -> int:
    """準備・接続確認・実取得を区別して監督入口を実行

    Args:
        argv: プログラム名を除くCLI引数

    Returns:
        準備・接続確認・取得成功0、引数2、競合3、期限124、signal130/143、他1
    """
    started = time.monotonic()
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ['--lock-worker']:
        if len(arguments) not in (1, 3):
            return 2
        expected = (arguments[1], arguments[2]) if len(arguments) == 3 else None
        return _lock_worker(expected)
    from press_watch_api.commands import fetch_and_save_env_press as fetch
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--prepare-only', action='store_true')
    modes.add_argument('--check-db-only', action='store_true')
    parser.add_argument('--expected-db-user')
    parser.add_argument('--expected-db-name')
    options, rest = parser.parse_known_args(arguments)
    expected_identity = None
    if options.check_db_only:
        if not options.expected_db_user or not options.expected_db_name:
            parser.error(
                '--check-db-only requires --expected-db-user and --expected-db-name',
            )
        expected_identity = (options.expected_db_user, options.expected_db_name)
    elif options.expected_db_user is not None or options.expected_db_name is not None:
        parser.error('identity expectations require --check-db-only')
    fetch_parser = fetch._build_parser()
    args = fetch_parser.parse_args(rest)
    fetch._validate_args(fetch_parser, args)
    if args.archive_month_limit is not None and args.archive_month_limit < 0:
        fetch_parser.error('--archive-month-limit must be greater than or equal to 0.')
    if (
        args.from_file is not None
        and args.archive_month_limit is not None
        and args.archive_month_limit > 0
    ):
        fetch_parser.error('--from-file cannot be used with --archive-month-limit.')
    if options.prepare_only:
        if (
            not all(importlib.util.find_spec(name) for name in (
                'psycopg',
                'sqlalchemy',
            ))
            or not shutil.which('uv')
            or not (fetch._scraper_package_dir() / '.venv/bin/python').is_file()
        ):
            _report('dependencies_missing', 1)
            return 1
        _report('prepared acquisition=false', 0)
        return 0
    try:
        env = connection_environment(os.environ)
        # APIと同じCAの寿命を利用し、子だけへ対象の接続設定を渡す。
        with certificate_environment():
            env['PGSSLROOTCERT'] = os.environ['PGSSLROOTCERT']
            try:
                return supervise(
                    [
                        sys.executable,
                        '-m',
                        fetch.__name__,
                        *rest,
                    ],
                    env, check_only=options.check_db_only,
                    expected_identity=expected_identity,
                    timeout=max(0, RUN_SECONDS - (time.monotonic() - started)),
                )
            except Exception:
                reason = SUPERVISOR_FAILURE_REASON
    except Exception:
        reason = 'configuration_failed'
    _report(reason, 1)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
