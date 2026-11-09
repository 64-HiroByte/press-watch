"""定期取得の準備・TLS・停止監督の検証"""

import io
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from unittest.mock import MagicMock, patch

from press_watch_api.commands import run_fetch_job as job


class JobPreparationTest(unittest.TestCase):
    """実接続しない準備起動の契約"""

    def test_prepare_without_credentials_does_not_start_processes(self) -> None:
        """資格情報なしの準備が成功し、子プロセスを起動しないこと"""
        with (
            patch.dict(
                os.environ,
                {'PATH': os.environ.get('PATH', '')},
                clear=True,
            ),
            patch('subprocess.Popen') as spawn,
        ):
            with redirect_stderr(io.StringIO()) as output:
                code = job.main(['--prepare-only', '--archive-month-limit', '6'])
        self.assertEqual(code, 0)
        spawn.assert_not_called()
        self.assertIn('prepared', output.getvalue())


class InvalidPreparationTest(unittest.TestCase):
    """scraperが拒否する引数を準備段階で検出"""

    def test_invalid_crawl_arguments_fail_before_starting(self) -> None:
        """負の巡回上限とファイル入力との併用を子起動前に拒否すること"""
        for arguments in (
            ['--archive-month-limit', '-1'],
            ['--from-file', '/tmp/unused.html', '--archive-month-limit', '6'],
        ):
            with (
                self.subTest(arguments=arguments),
                patch('subprocess.Popen') as spawn,
            ):
                with (
                    redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit) as error,
                ):
                    job.main(['--prepare-only', *arguments])
                self.assertEqual(error.exception.code, 2)
                spawn.assert_not_called()


class JobFailureReportingTest(unittest.TestCase):
    """接続準備と監督実行で異なる失敗理由を返すこと"""

    def test_invalid_configuration_stops_before_supervisor(self) -> None:
        """接続設定が不十分なら監督処理を始めず設定エラーを報告すること"""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(job, 'supervise') as supervise,
            redirect_stderr(io.StringIO()) as output,
        ):
            code = job.main([])

        self.assertEqual(code, 1)
        supervise.assert_not_called()
        self.assertEqual(output.getvalue().strip(), 'job reason=configuration_failed exit_code=1')

    def test_supervisor_failure_reports_runtime_error_and_removes_ca(self) -> None:
        """監督例外の詳細を出さず、一時CAを削除して設定を復元すること"""
        with (
            patch.dict(
                os.environ,
                {
                    'DATABASE_URL': 'postgresql://writer:example@db.invalid/postgres?sslmode=verify-full',
                    'PRESSWATCH_DB_CA_CERT': 'synthetic-ca',
                    'PGSSLROOTCERT': '/previous/ca.crt',
                },
                clear=True,
            ),
            patch.object(job, 'supervise', side_effect=OSError('synthetic detail')) as supervise,
            redirect_stderr(io.StringIO()) as output,
        ):
            code = job.main([])
            self.assertEqual(os.environ['PGSSLROOTCERT'], '/previous/ca.crt')

        self.assertEqual(code, 1)
        self.assertEqual(
            output.getvalue().strip(),
            'job reason=supervisor_failed_save_state_unknown exit_code=1',
        )
        self.assertFalse(Path(supervise.call_args.args[1]['PGSSLROOTCERT']).exists())


class DiagnosticIdentityTest(unittest.TestCase):
    """接続診断で承認したDB・ロールとの一致を確認"""

    def test_worker_rejects_wrong_identity_before_lock(self) -> None:
        """管理ロール・APIロール・別DBではロックを取らず診断に失敗すること"""
        for actual in (
            ('postgres', 'postgres'),
            ('presswatch_api_readonly', 'postgres'),
            ('presswatch_fetch_writer', 'other'),
        ):
            with self.subTest(actual=actual):
                code, connection, channel = self.run_worker(actual)
                self.assertEqual(code, 1)
                self.assertEqual(connection.execute.call_count, 1)
                channel.send.assert_called_once_with(b'failed')
                channel.close.assert_called_once()

    def test_matching_identity_checks_and_releases_lock(self) -> None:
        """承認したDB・ロールなら同じ接続で照合してからロックを取得すること"""
        code, connection, channel = self.run_worker(
            ('presswatch_fetch_writer', 'postgres'),
        )
        self.assertEqual(code, 0)
        self.assertEqual(connection.execute.call_count, 2)
        self.assertEqual(
            connection.execute.call_args_list[0].args,
            ('SELECT current_user, current_database()',),
        )
        self.assertIn(
            'pg_try_advisory_lock', connection.execute.call_args_list[1].args[0],
        )
        channel.send.assert_called_once_with(b'locked')
        connection.__exit__.assert_called_once()

    def run_worker(
        self, actual: tuple[str, str],
    ) -> tuple[int, MagicMock, MagicMock]:
        """実DBとsocketを置換して接続主体の判定結果を取得

        Args:
            actual: 接続先から返すロール名とDB名

        Returns:
            終了コード、接続Mock、通信路Mock
        """
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.return_value.fetchone.side_effect = [actual, (True,)]
        channel = MagicMock()
        channel.recv.return_value = b'stop'
        with (
            patch.dict(os.environ, {
                'DATABASE_URL': 'postgresql://writer:example@db.invalid/postgres',
                'PGSSLROOTCERT': '/unused/ca.crt',
                'PRESSWATCH_LOCK_FD': '10',
            }, clear=True),
            patch('psycopg.connect', return_value=connection),
            patch.object(job.socket, 'socket', return_value=channel),
        ):
            code = job._lock_worker(('presswatch_fetch_writer', 'postgres'))
        return code, connection, channel

    def test_diagnostic_requires_both_expectations_before_starting(self) -> None:
        """診断の期待値不足や診断以外への指定を子起動前に拒否すること"""
        for arguments in (
            ['--check-db-only'],
            ['--check-db-only', '--expected-db-user', 'writer'],
            [
                '--prepare-only', '--expected-db-user', 'writer',
                '--expected-db-name', 'postgres',
            ],
            ['--expected-db-user', 'writer', '--expected-db-name', 'postgres'],
        ):
            with self.subTest(arguments=arguments), patch('subprocess.Popen') as spawn:
                with (
                    redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit) as error,
                ):
                    job.main(arguments)
                self.assertEqual(error.exception.code, 2)
                spawn.assert_not_called()

    def test_explicit_identity_reaches_supervisor_and_internal_worker(self) -> None:
        """診断の期待値を接続URLから採らず監督と内部入口へ渡すこと"""
        expected = ('presswatch_fetch_writer', 'postgres')
        with (
            patch.object(job, 'connection_environment', return_value={}),
            patch.object(job, 'certificate_environment'),
            patch.dict(os.environ, {'PGSSLROOTCERT': '/unused/ca.crt'}),
            patch.object(job, 'supervise', return_value=0) as supervise,
        ):
            code = job.main([
                '--check-db-only',
                '--expected-db-user', expected[0],
                '--expected-db-name', expected[1],
            ])
        self.assertEqual(code, 0)
        self.assertEqual(supervise.call_args.kwargs['expected_identity'], expected)
        self.assertTrue(supervise.call_args.kwargs['check_only'])
        with patch.object(job, '_lock_worker', return_value=1) as worker:
            self.assertEqual(job.main(['--lock-worker', *expected]), 1)
        worker.assert_called_once_with(expected)

    def test_supervisor_sends_expectations_to_child_command(self) -> None:
        """期待値をロック保持子へ渡し、起動失敗時は取得を開始しないこと"""
        expected = ('presswatch_fetch_writer', 'postgres')
        with (
            patch('subprocess.Popen', side_effect=OSError) as spawn,
            redirect_stderr(io.StringIO()),
        ):
            code = job.supervise(
                ['unused-fetch-command'], {},
                check_only=True, expected_identity=expected,
            )
        self.assertEqual(code, 1)
        spawn.assert_called_once()
        self.assertEqual(
            spawn.call_args.args[0][-3:], ['--lock-worker', *expected],
        )


LOCK_READY = """
import os
import socket
import time

s = socket.socket(fileno=int(os.environ['PRESSWATCH_LOCK_FD']))
s.send(b'locked')
while True:
    if s.recv(100) == b'stop':
        break
"""


@unittest.skipUnless(sys.platform == 'linux', 'プロセス群とsubreaperは本番と同じLinuxで検証')
class SupervisorTest(unittest.TestCase):
    """実DBの代わりに合成ロックプロセスを使う停止監督"""

    def test_normal_completion_and_lock_conflict(self) -> None:
        """取得成功を返し、競合時は取得プロセスを起動しないこと"""
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'started'
            command = [
                sys.executable,
                '-c',
                f"""
from pathlib import Path

Path({str(marker)!r}).touch()
""",
            ]
            with redirect_stderr(io.StringIO()):
                code = job.supervise(
                    command,
                    dict(os.environ),
                    lock_command=[sys.executable, '-c', LOCK_READY],
                    grace=.1,
                )
            self.assertEqual(code, 0)
            self.assertTrue(marker.exists())
            marker.unlink()
            conflict = LOCK_READY.replace("b'locked'", "b'conflict'")
            with redirect_stderr(io.StringIO()):
                code = job.supervise(
                    command,
                    dict(os.environ),
                    lock_command=[sys.executable, '-c', conflict],
                    grace=.1,
                )
            self.assertEqual(code, 3)
            self.assertFalse(marker.exists())

    def test_timeout_and_unresponsive_lock_are_bounded(self) -> None:
        """取得の時間切れとロック保持プロセスの応答停止を有限時間で止めること"""
        for timeout, heartbeat, expected in ((.4, 10, 124), (10, .4, 1)):
            with self.subTest(expected=expected), redirect_stderr(io.StringIO()):
                started = time.monotonic()
                code = job.supervise(
                    [sys.executable, '-c', 'import time\ntime.sleep(60)'],
                    dict(os.environ),
                    lock_command=[sys.executable, '-c', LOCK_READY],
                    timeout=timeout,
                    heartbeat_timeout=heartbeat,
                    grace=.1,
                )
                self.assertEqual(code, expected)
                self.assertLess(time.monotonic() - started, 3)

    def test_sigterm_stops_the_worker_before_releasing_lock(self) -> None:
        """SIGTERM時に取得プロセスの終了を待ってからロックを解放すること"""
        with tempfile.TemporaryDirectory() as directory:
            started = Path(directory) / 'started'
            stopped = Path(directory) / 'stopped'
            released = Path(directory) / 'released'
            worker = f"""
import signal
import time
from pathlib import Path


def stop(*args):
    Path({str(stopped)!r}).touch()
    raise SystemExit(0)


signal.signal(signal.SIGTERM, stop)
Path({str(started)!r}).touch()
while True:
    time.sleep(0.01)
"""
            lock = LOCK_READY + f"""
from pathlib import Path

Path({str(released)!r}).write_text(
    str(Path({str(stopped)!r}).exists())
)
"""
            driver = f"""
import os
import sys

from press_watch_api.commands.run_fetch_job import supervise

raise SystemExit(
    supervise(
        [sys.executable, '-c', {worker!r}],
        dict(os.environ),
        lock_command=[sys.executable, '-c', {lock!r}],
        grace=0.5,
    )
)
"""
            process = subprocess.Popen(
                [sys.executable, '-c', driver],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                deadline = time.monotonic() + 5
                while not started.exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(started.exists())
                process.send_signal(signal.SIGTERM)
                self.assertEqual(process.wait(timeout=5), 143)
                self.assertEqual(released.read_text(), 'True')
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    def test_output_blocking_does_not_prevent_timeout(self) -> None:
        """取得プロセスの出力が詰まっても監督が時間切れで停止すること"""
        blocked = '''
import os

r, w = os.pipe()
while True:
    os.write(w, b"x" * 65536)
'''
        with redirect_stderr(io.StringIO()):
            started = time.monotonic()
            code = job.supervise(
                [sys.executable, '-c', blocked],
                dict(os.environ),
                lock_command=[sys.executable, '-c', LOCK_READY],
                timeout=.4,
                grace=.1,
            )
        self.assertEqual(code, 124)
        self.assertLess(time.monotonic() - started, 3)

    def test_supervisor_diagnostic_with_full_stderr_does_not_block_exit(self) -> None:
        """監督自身のstderrが満杯でも終了時のフラッシュ待ちを起こさないこと"""
        driver = '''
import os
import fcntl

from press_watch_api.commands.run_fetch_job import _report

flags = fcntl.fcntl(2, fcntl.F_GETFL)
fcntl.fcntl(2, fcntl.F_SETFL, flags | os.O_NONBLOCK)
try:
    while True:
        os.write(2, b'x' * 4096)
except BlockingIOError:
    pass
fcntl.fcntl(2, fcntl.F_SETFL, flags)
_report('timeout', 124)
'''
        process = subprocess.Popen(
            [sys.executable, '-c', driver],
            stderr=subprocess.PIPE,
        )
        try:
            self.assertEqual(process.wait(timeout=1), 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stderr.close()

    def test_forced_lock_cleanup_is_not_reported_as_success(self) -> None:
        """ロック接続の終了が詰まる場合は強制終了し、通常成功に数えないこと"""
        stalled = LOCK_READY.replace(
            "if s.recv(100) == b'stop':\n        break",
            "if s.recv(100) == b'stop':\n        time.sleep(60)",
        )
        with redirect_stderr(io.StringIO()):
            code = job.supervise(
                [sys.executable, '-c', 'pass'],
                dict(os.environ),
                lock_command=[sys.executable, '-c', stalled],
                grace=.1,
            )
        self.assertEqual(code, 1)

    def test_timeout_reaps_child_and_grandchild_ignoring_sigterm(self) -> None:
        """SIGTERMを無視する取得・孫プロセスを強制終了し、双方を回収すること"""
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'grandchild'
            worker = f'''
import os
import signal
import time
from pathlib import Path

signal.signal(signal.SIGTERM, signal.SIG_IGN)
pid = os.fork()
if pid:
    Path({str(marker)!r}).write_text(str(pid))
while True:
    time.sleep(0.1)
'''
            with redirect_stderr(io.StringIO()):
                code = job.supervise(
                    [sys.executable, '-c', worker],
                    dict(os.environ),
                    lock_command=[sys.executable, '-c', LOCK_READY],
                    timeout=.5,
                    grace=.1,
                )
            self.assertEqual(code, 124)
            descendant = int(marker.read_text())
            with self.assertRaises(ProcessLookupError):
                os.kill(descendant, 0)

    def test_signal_during_lock_cleanup_is_not_reported_as_success(self) -> None:
        """取得完了後のロック解放中に受けたSIGTERMも中断として返すこと"""
        lock = LOCK_READY.replace(
            "if s.recv(100) == b'stop':\n        break",
            """if s.recv(100) == b'stop':
        import signal
        os.kill(os.getppid(), signal.SIGTERM)
        time.sleep(0.05)
        break""",
        )
        with redirect_stderr(io.StringIO()):
            code = job.supervise(
                [sys.executable, '-c', 'pass'],
                dict(os.environ),
                lock_command=[sys.executable, '-c', lock],
            )
        self.assertEqual(code, 143)

    def test_normal_heartbeat_finishes_before_lock_release(self) -> None:
        """応答期限内の監視照会中に取得が完了しても通常終了を維持すること"""
        lock = """
import os
import socket
import time

s = socket.socket(fileno=int(os.environ['PRESSWATCH_LOCK_FD']))
s.send(b'locked')
time.sleep(0.6)
s.send(b'alive')
s.recv(100)
"""
        with redirect_stderr(io.StringIO()):
            code = job.supervise(
                [sys.executable, '-c', 'import time\ntime.sleep(0.25)'],
                dict(os.environ),
                lock_command=[sys.executable, '-c', lock],
                grace=1.5,
            )
        self.assertEqual(code, 0)
