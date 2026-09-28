"""scraper子プロセスの起動条件、JSON復元、入出力、一時ファイルを検証"""

from datetime import date
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, Mock, patch

from press_watch_api.commands import fetch_and_save_env_press
from press_watch_api.services import (
    fixed_category_classification as classification,
)
from press_watch_api.commands.fetch_and_save_env_press import (
    _parse_scraper_snapshot,
    _scraper_command,
    _scraper_env,
    main,
)

from api_test_constants import (
    ENV_PRESS_INDEX_URL as INDEX_URL,
    ENV_PRESS_RELEASE_URL_1 as SOURCE_URL_1,
    ENV_PRESS_RELEASE_URL_2 as SOURCE_URL_2,
)


class FetchAndSaveScraperTest(unittest.TestCase):
    """取得・保存CLIとscraper子プロセスの境界のテスト"""

    def setUp(self) -> None:
        """分類ルールを固定し、テスト終了時にpatchを自動復元"""

        self.rule_loader = self.enterContext(
            patch.object(
                classification,
                "load_fixed_category_rules",
                return_value=((51, "大気"),),
            ),
        )

    def test_main_reports_url_rejected_by_actual_scraper_cli(self) -> None:
        """scraper子プロセスのURL検証理由を報告し、Sessionを作らないこと"""

        html = """
        <details class="p-press-release-list__block">
          <span class="p-press-release-list__heading">
            2026年05月01日発表
          </span>
          <a href="/press/日本語.html" class="c-news-link__link">
            URL形式が不正な発表
          </a>
        </details>
        """
        session_factory = Mock()
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "invalid-release-url.html"
            html_path.write_text(html, encoding="utf-8")

            exit_code = main(
                ["--from-file", str(html_path)],
                session_factory=session_factory,
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn(
            "exception=InvalidPressReleaseUrlError",
            stderr.getvalue(),
        )
        self.assertIn(
            "validation=non_ascii_character",
            stderr.getvalue(),
        )
        self.assertIn("URL形式が不正な発表", stderr.getvalue())
        self.assertIn("href='/press/日本語.html'", stderr.getvalue())
        session_factory.assert_not_called()

    def test_parse_scraper_snapshot_restores_releases(self) -> None:
        """scraperのJSONから日付・カテゴリを含む取得結果を復元すること"""

        snapshot_json = json.dumps(
            {
                "source_url": INDEX_URL,
                "items": [
                    {
                        "title": "報道発表1",
                        "published_at": "2026-05-01",
                        "url": SOURCE_URL_1,
                        "source_categories": ["総合政策"],
                    },
                    {
                        "title": "報道発表2",
                        "published_at": "2026-05-02",
                        "url": SOURCE_URL_2,
                        "source_categories": [],
                    },
                ],
                "fetched_page_urls": [INDEX_URL],
                "stop_reason": None,
            },
            ensure_ascii=False,
        )

        collected = _parse_scraper_snapshot(snapshot_json)

        self.assertEqual(collected.source_url, INDEX_URL)
        self.assertEqual(collected.fetched_count, 2)
        self.assertEqual(collected.fetched_page_urls, (INDEX_URL,))
        self.assertIsNone(collected.stop_reason)
        self.assertEqual(collected.releases[0].published_at, date(2026, 5, 1))
        self.assertEqual(collected.releases[0].source_categories, ("総合政策",))
        self.assertEqual(collected.releases[1].source_categories, ())

    def test_scraper_command_uses_locked_scraper_cli(self) -> None:
        """scraperの起動コマンドにuv run --lockedとCLI引数を含めること"""

        args = Mock(
            url=INDEX_URL,
            from_file=None,
            archive_month_limit=2,
            all_archive_months=False,
            verbose=True,
        )

        command = _scraper_command(args)

        self.assertEqual(
            command,
            [
                "uv",
                "run",
                "--locked",
                "python",
                "-m",
                "press_watch_scraper",
                "--url",
                INDEX_URL,
                "--archive-month-limit",
                "2",
                "--verbose",
            ],
        )

    def test_scraper_command_forwards_all_archive_months(self) -> None:
        """scraperの起動コマンドに全月別ページ巡回の指定を含めること"""

        args = Mock(
            url=INDEX_URL,
            from_file=None,
            archive_month_limit=None,
            all_archive_months=True,
            verbose=False,
        )

        command = _scraper_command(args)

        self.assertEqual(
            command,
            [
                "uv",
                "run",
                "--locked",
                "python",
                "-m",
                "press_watch_scraper",
                "--url",
                INDEX_URL,
                "--all-archive-months",
            ],
        )

    def test_scraper_env_does_not_forward_database_credentials(self) -> None:
        """生成する子プロセス用の環境変数からDB認証情報とトークンを除くこと"""

        with patch.dict(
            "os.environ",
            {
                "PATH": "/usr/bin",
                "HOME": "/tmp/test-home",
                "DATABASE_URL": "postgresql://user:password@example/db",
                "API_TOKEN": "secret-token",
                "PYTHONPATH": "/untrusted/pythonpath",
            },
            clear=True,
        ):
            env = _scraper_env(Path("/repo/packages/scraper"))

        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertEqual(env["HOME"], "/tmp/test-home")
        self.assertEqual(
            env["PYTHONPATH"],
            "/repo/packages/scraper/src",
        )
        self.assertEqual(env["PYTHONUTF8"], "1")
        self.assertNotIn("DATABASE_URL", env)
        self.assertNotIn("API_TOKEN", env)

    def test_collect_releases_from_scraper_cli_reports_subprocess_error(
        self,
    ) -> None:
        """scraper CLI失敗時の理由を上位のstderrへ渡せること"""

        from press_watch_api.commands import fetch_and_save_env_press

        completed = Mock(
            returncode=1,
            stdout="",
            stderr=(
                "error: target=fixture "
                "exception=InvalidPressReleaseUrlError "
                "reason=invalid press release URL: "
                "validation=non_ascii_character "
                "title='URL形式が不正な発表' "
                "href='/press/日本語.html'\n"
            ),
        )
        args = Mock(
            url=INDEX_URL,
            from_file=None,
            archive_month_limit=None,
            all_archive_months=False,
            verbose=False,
        )

        with patch.object(
            fetch_and_save_env_press,
            "_run_scraper_process",
            return_value=completed,
        ):
            with self.assertRaises(RuntimeError) as raised:
                fetch_and_save_env_press._collect_releases_from_scraper_cli(
                    args,
                    io.StringIO(),
                    (),
                )

        message = str(raised.exception)
        self.assertIn("scraper command failed: exit_code=1", message)
        self.assertIn("InvalidPressReleaseUrlError", message)
        self.assertIn("validation=non_ascii_character", message)
        self.assertIn("URL形式が不正な発表", message)
        self.assertIn("href='/press/日本語.html'", message)

    def test_collect_releases_keeps_final_error_after_long_progress(
        self,
    ) -> None:
        """長い進捗の末尾にある子プロセス失敗理由を保持すること"""

        final_reason = "final fetch failure"
        completed = Mock(
            returncode=1,
            stdout="",
            stderr=("progress line\n" * 200) + f"error: {final_reason}\n",
        )
        args = Mock(
            url=INDEX_URL,
            from_file=None,
            archive_month_limit=None,
            all_archive_months=False,
            verbose=True,
        )

        with patch.object(
            fetch_and_save_env_press,
            "_run_scraper_process",
            return_value=completed,
        ):
            with self.assertRaises(RuntimeError) as raised:
                fetch_and_save_env_press._collect_releases_from_scraper_cli(
                    args,
                    io.StringIO(),
                    (),
                )

        self.assertIn(final_reason, str(raised.exception))

    def test_collect_releases_forwards_verbose_stderr_on_success(self) -> None:
        """verbose時は子プロセス終了前にscraper進捗を転送すること"""

        from press_watch_api.commands import fetch_and_save_env_press

        completed = Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "source_url": INDEX_URL,
                    "items": [],
                    "fetched_page_urls": [],
                    "stop_reason": None,
                }
            ),
            stderr=f"fetching page: {INDEX_URL}\n",
        )
        args = Mock(
            url=INDEX_URL,
            from_file=None,
            archive_month_limit=None,
            all_archive_months=False,
            verbose=True,
        )
        progress_forwarded = threading.Event()

        class ProgressOutput(io.StringIO):
            """進捗書き込みを偽子プロセスへ通知する出力先"""

            def write(self, value: str) -> int:
                written = super().write(value)
                progress_forwarded.set()
                return written

        class FakeProcess:
            """進捗転送後にだけ終了する偽子プロセス"""

            def __init__(self) -> None:
                self.stdout = io.StringIO(completed.stdout)
                self.stderr = io.StringIO(completed.stderr)
                self.returncode: int | None = None
                self.waited_after_forward = False

            def poll(self) -> int | None:
                if progress_forwarded.is_set():
                    self.returncode = 0
                return self.returncode

            def wait(self, timeout: float | None = None) -> int:
                if not progress_forwarded.wait(timeout):
                    raise fetch_and_save_env_press.subprocess.TimeoutExpired(
                        "scraper",
                        timeout,
                    )
                self.waited_after_forward = True
                self.returncode = 0
                return 0

            def terminate(self) -> None:
                self.returncode = 1

            def kill(self) -> None:
                self.returncode = 1

        stderr = ProgressOutput()
        process = FakeProcess()

        with (
            patch.object(
                fetch_and_save_env_press.subprocess,
                "Popen",
                return_value=process,
            ) as mock_popen,
            patch.object(
                fetch_and_save_env_press.subprocess,
                "run",
                return_value=completed,
            ) as mock_run,
        ):

            fetch_and_save_env_press._collect_releases_from_scraper_cli(
                args,
                stderr,
                (),
            )

        mock_popen.assert_called_once()
        mock_run.assert_not_called()
        self.assertTrue(process.waited_after_forward)
        self.assertEqual(stderr.getvalue(), completed.stderr)

    def test_run_scraper_process_stops_child_when_progress_output_fails(
        self,
    ) -> None:
        """進捗転送失敗時は子プロセスをkillして回収すること"""

        progress_failed = threading.Event()

        class FailingOutput:
            """write時に失敗する進捗出力先"""

            def write(self, _value: str) -> int:
                progress_failed.set()
                raise OSError("output unavailable")

            def flush(self) -> None:
                return None

        class WaitingStdout(io.StringIO):
            """進捗転送失敗後に読込を終える偽stdout"""

            def read(self, *args: object, **kwargs: object) -> str:
                progress_failed.wait(timeout=1.0)
                return super().read(*args, **kwargs)

        class FakeProcess:
            """kill後にだけ終了する偽子プロセス"""

            def __init__(self) -> None:
                self.stdout = WaitingStdout("{}")
                self.stderr = io.StringIO("progress\n")
                self.returncode: int | None = None
                self.terminate_calls = 0
                self.kill_calls = 0

            def wait(self, timeout: float | None = None) -> int:
                if self.kill_calls == 0:
                    raise fetch_and_save_env_press.subprocess.TimeoutExpired(
                        "scraper",
                        timeout,
                    )
                self.returncode = 1
                return 1

            def terminate(self) -> None:
                self.terminate_calls += 1

            def kill(self) -> None:
                self.kill_calls += 1

        process = FakeProcess()
        with patch.object(
            fetch_and_save_env_press.subprocess,
            "Popen",
            return_value=process,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "scraper progress output failed",
            ):
                fetch_and_save_env_press._run_scraper_process(
                    ["scraper"],
                    cwd=Path("."),
                    env={},
                    stderr=FailingOutput(),
                    forward_stderr=True,
                )

        self.assertGreaterEqual(process.terminate_calls, 1)
        self.assertEqual(process.kill_calls, 1)

    def test_progress_failure_does_not_wait_for_stdout_eof(self) -> None:
        """進捗転送失敗時はstdout EOFを待たずに子を停止すること"""

        progress_failed = threading.Event()
        release_stdout = threading.Event()
        child_killed = threading.Event()

        class FailingOutput:
            """進捗の書き込み失敗をイベントで通知する出力先"""

            def write(self, _value: str) -> int:
                progress_failed.set()
                raise OSError("output unavailable")

        class BlockingStdout(io.StringIO):
            """解放イベントが届くまで読み取りを終えない偽stdout"""

            def read(self, *args: object, **kwargs: object) -> str:
                release_stdout.wait()
                return super().read(*args, **kwargs)

        class FakeProcess:
            """terminateでは終了せず、killでstdoutの読み取りも解放する偽子プロセス"""

            def __init__(self) -> None:
                self.stdout = BlockingStdout("{}")
                self.stderr = io.StringIO("progress\n")
                self.returncode: int | None = None

            def wait(self, timeout: float | None = None) -> int:
                if not child_killed.is_set():
                    raise fetch_and_save_env_press.subprocess.TimeoutExpired(
                        "scraper",
                        timeout,
                    )
                self.returncode = 1
                return 1

            def terminate(self) -> None:
                return None

            def kill(self) -> None:
                child_killed.set()
                release_stdout.set()

        process = FakeProcess()
        raised_errors: list[BaseException] = []

        def run_process() -> None:
            """ワーカースレッドの例外を呼び出し元の検証用リストへ収集"""

            try:
                fetch_and_save_env_press._run_scraper_process(
                    ["scraper"],
                    cwd=Path("."),
                    env={},
                    stderr=FailingOutput(),
                    forward_stderr=True,
                )
            except BaseException as exc:
                raised_errors.append(exc)

        with patch.object(
            fetch_and_save_env_press.subprocess,
            "Popen",
            return_value=process,
        ):
            worker = threading.Thread(target=run_process)
            worker.start()
            try:
                killed_before_stdout_eof = child_killed.wait(timeout=0.2)
            finally:
                release_stdout.set()
                worker.join(timeout=1.0)

        self.assertTrue(killed_before_stdout_eof)
        self.assertFalse(worker.is_alive())
        self.assertIsInstance(raised_errors[0], RuntimeError)

    def test_run_scraper_process_drains_large_stdout_and_stderr(self) -> None:
        """大量のstdoutとstderrを同時に読み取りデッドロックしないこと"""

        output_size = 200_000
        completed = fetch_and_save_env_press._run_scraper_process(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    f"sys.stderr.write('e' * {output_size}); "
                    "sys.stderr.flush(); "
                    f"sys.stdout.write('o' * {output_size}); "
                    "sys.stdout.flush()"
                ),
            ],
            cwd=Path("."),
            env={"PYTHONUTF8": "1"},
            stderr=io.StringIO(),
            forward_stderr=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(len(completed.stdout), output_size)
        self.assertLessEqual(
            len(completed.stderr),
            fetch_and_save_env_press.MAX_DIAGNOSTIC_VALUE_LENGTH + 1,
        )

    def test_run_scraper_process_keeps_only_recent_stderr_lines(self) -> None:
        """stderrを50行以内に収め、古い進捗を除いて末尾の診断を残すこと"""

        completed = fetch_and_save_env_press._run_scraper_process(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "[print(f'progress {index}', file=sys.stderr) "
                    "for index in range(100)]; "
                    "print('final error', file=sys.stderr)"
                ),
            ],
            cwd=Path("."),
            env={"PYTHONUTF8": "1"},
            stderr=io.StringIO(),
            forward_stderr=False,
        )

        stderr_lines = completed.stderr.splitlines()
        self.assertLessEqual(len(stderr_lines), 50)
        self.assertNotIn("progress 0", stderr_lines)
        self.assertEqual(stderr_lines[-1], "final error")

    def test_run_scraper_process_stops_child_when_interrupted(self) -> None:
        """親プロセス中断時は子プロセスを停止して再送出すること"""

        class FakeProcess:
            """最初のwaitでCtrl+C相当を再現する偽子プロセス"""

            def __init__(self) -> None:
                self.stdout = io.StringIO("{}")
                self.stderr = io.StringIO("")
                self.returncode: int | None = None
                self.terminate_calls = 0

            def wait(self, timeout: float | None = None) -> int:
                if self.terminate_calls == 0:
                    raise KeyboardInterrupt
                self.returncode = 1
                return 1

            def terminate(self) -> None:
                self.terminate_calls += 1

            def kill(self) -> None:
                self.returncode = 1

        process = FakeProcess()
        with patch.object(
            fetch_and_save_env_press.subprocess,
            "Popen",
            return_value=process,
        ):
            with self.assertRaises(KeyboardInterrupt):
                fetch_and_save_env_press._run_scraper_process(
                    ["scraper"],
                    cwd=Path("."),
                    env={},
                    stderr=io.StringIO(),
                    forward_stderr=False,
                )

        self.assertEqual(process.terminate_calls, 1)

    def test_collect_releases_forwards_known_release_urls_file(self) -> None:
        """既知URLを改行区切りファイルとしてscraper CLIへ渡すこと"""

        from press_watch_api.commands import fetch_and_save_env_press

        completed = Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "source_url": INDEX_URL,
                    "items": [],
                    "fetched_page_urls": [INDEX_URL],
                    "stop_reason": "duplicate_release_detected",
                }
            ),
            stderr="",
        )
        args = Mock(
            url=INDEX_URL,
            from_file=None,
            archive_month_limit=1,
            all_archive_months=False,
            verbose=False,
        )
        captured_file_contents: list[str] = []
        captured_file_paths: list[Path] = []

        def run_subprocess(command: list[str], **_kwargs: object) -> object:
            option_index = command.index("--known-release-urls-file")
            file_path = Path(command[option_index + 1])
            captured_file_paths.append(file_path)
            captured_file_contents.append(
                file_path.read_text(encoding="utf-8")
            )
            return completed

        with patch.object(
            fetch_and_save_env_press,
            "_run_scraper_process",
            side_effect=run_subprocess,
        ):

            collected = (
                fetch_and_save_env_press._collect_releases_from_scraper_cli(
                    args,
                    io.StringIO(),
                    (SOURCE_URL_2, SOURCE_URL_1, SOURCE_URL_1),
                )
            )

        self.assertEqual(collected.stop_reason, "duplicate_release_detected")
        self.assertEqual(
            captured_file_contents,
            [f"{SOURCE_URL_1}\n{SOURCE_URL_2}\n"],
        )
        self.assertFalse(captured_file_paths[0].exists())

    def test_write_known_release_urls_file_removes_partial_file_on_error(
        self,
    ) -> None:
        """既知URLファイルの書き込み失敗時に途中ファイルを削除すること"""

        from press_watch_api.commands import fetch_and_save_env_press

        with tempfile.TemporaryDirectory() as temp_dir:
            partial_path = Path(temp_dir) / "known-release-urls.txt"
            partial_path.touch()
            temporary_file = MagicMock()
            temporary_file.name = str(partial_path)
            temporary_file.write.side_effect = OSError("disk unavailable")
            manager = MagicMock()
            manager.__enter__.return_value = temporary_file

            with patch.object(
                fetch_and_save_env_press.tempfile,
                "NamedTemporaryFile",
                return_value=manager,
            ):
                with self.assertRaisesRegex(OSError, "disk unavailable"):
                    fetch_and_save_env_press._write_known_release_urls_file(
                        (SOURCE_URL_1,),
                    )

            self.assertFalse(partial_path.exists())


if __name__ == "__main__":
    unittest.main()
