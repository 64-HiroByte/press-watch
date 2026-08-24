from contextlib import redirect_stderr
from datetime import date
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

from sqlalchemy.orm import Session

from press_watch_api.commands import fetch_and_save_env_press
from press_watch_api.commands.fetch_and_save_env_press import (
    CollectedPressReleases,
    ScraperCliRelease,
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


class FetchAndSaveCommandTest(unittest.TestCase):
    """手動取得・保存コマンドのテスト"""

    def test_main_saves_scraper_releases_and_commits(self) -> None:
        """取得結果を保存serviceへ渡し、成功時にcommitすること"""

        session = Mock(spec=Session)
        session.scalar.return_value = None
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = main(
            ["--url", INDEX_URL],
            session_factory=lambda: session,
            collect_releases=(
                lambda _args, _stderr, _known_urls: _collected_releases()
            ),
            stdout=stdout,
            stderr=stderr,
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(payload["source_url"], INDEX_URL)
        self.assertEqual(payload["fetched_count"], 2)
        self.assertEqual(payload["saved_count"], 2)
        self.assertEqual(payload["skipped_count"], 0)
        self.assertEqual(payload["fetched_page_urls"], [INDEX_URL])
        self.assertIsNone(payload["stop_reason"])
        session.commit.assert_called_once_with()
        session.rollback.assert_not_called()
        session.close.assert_called_once_with()
        self.assertEqual(
            [
                press_release.source_url
                for press_release in (
                    session.add.call_args_list[0].args[0],
                    session.add.call_args_list[1].args[0],
                )
            ],
            [SOURCE_URL_1, SOURCE_URL_2],
        )

    def test_main_reports_skipped_count(self) -> None:
        """既存URLをskip件数としてstdout JSONへ出すこと"""

        session = Mock(spec=Session)
        session.scalar.side_effect = [None, 1]
        stdout = io.StringIO()

        exit_code = main(
            [],
            session_factory=lambda: session,
            collect_releases=(
                lambda _args, _stderr, _known_urls: _collected_releases()
            ),
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["fetched_count"], 2)
        self.assertEqual(payload["saved_count"], 1)
        self.assertEqual(payload["skipped_count"], 1)
        session.commit.assert_called_once_with()
        session.rollback.assert_not_called()

    def test_main_passes_latest_three_months_urls_for_archive_crawl(
        self,
    ) -> None:
        """既知URLの読取Sessionを閉じてから月別巡回を始めること"""

        read_session = Mock(spec=Session)
        read_session.scalar.return_value = date(2026, 7, 25)
        read_session.scalars.return_value = [SOURCE_URL_1, SOURCE_URL_2]
        save_session = Mock(spec=Session)
        session_factory = Mock(side_effect=[read_session, save_session])
        stdout = io.StringIO()
        captured_known_urls: list[tuple[str, ...]] = []

        def collect_releases(
            _args: object,
            _stderr: object,
            known_release_urls: object,
        ) -> CollectedPressReleases:
            read_session.close.assert_called_once_with()
            self.assertEqual(session_factory.call_count, 1)
            captured_known_urls.append(tuple(known_release_urls))
            return CollectedPressReleases(
                source_url=INDEX_URL,
                releases=(),
                fetched_page_urls=(INDEX_URL,),
                stop_reason="duplicate_release_detected",
            )

        exit_code = main(
            ["--archive-month-limit", "1"],
            session_factory=session_factory,
            collect_releases=collect_releases,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            captured_known_urls,
            [(SOURCE_URL_1, SOURCE_URL_2)],
        )
        statement = read_session.scalars.call_args.args[0]
        self.assertIn(date(2026, 5, 1), statement.compile().params.values())
        self.assertEqual(payload["fetched_count"], 0)
        self.assertEqual(payload["saved_count"], 0)
        self.assertEqual(payload["skipped_count"], 0)
        self.assertEqual(
            payload["stop_reason"],
            "duplicate_release_detected",
        )
        self.assertEqual(session_factory.call_count, 2)
        save_session.commit.assert_called_once_with()
        save_session.close.assert_called_once_with()

    def test_main_uses_requested_known_release_months(
        self,
    ) -> None:
        """既知URLの取得月数をCLI引数で変更できること"""

        read_session = Mock(spec=Session)
        read_session.scalar.return_value = date(2026, 7, 25)
        read_session.scalars.return_value = [SOURCE_URL_1]
        save_session = Mock(spec=Session)
        session_factory = Mock(side_effect=[read_session, save_session])

        exit_code = main(
            [
                "--archive-month-limit",
                "1",
                "--known-release-months",
                "6",
            ],
            session_factory=session_factory,
            collect_releases=(
                lambda _args, _stderr, _known_urls: CollectedPressReleases(
                    source_url=INDEX_URL,
                    releases=(),
                    fetched_page_urls=(INDEX_URL,),
                    stop_reason="duplicate_release_detected",
                )
            ),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

        self.assertEqual(exit_code, 0)
        statement = read_session.scalars.call_args.args[0]
        self.assertIn(date(2026, 2, 1), statement.compile().params.values())

    def test_main_rejects_non_positive_known_release_months(self) -> None:
        """既知URLの取得月数に0以下を許可しないこと"""

        stderr = io.StringIO()
        session_factory = Mock()
        collect_releases = Mock()

        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main(
                    ["--known-release-months", "0"],
                    session_factory=session_factory,
                    collect_releases=collect_releases,
                )

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            "--known-release-months must be greater than 0",
            stderr.getvalue(),
        )
        session_factory.assert_not_called()
        collect_releases.assert_not_called()

    def test_main_reports_database_configuration_error_before_scraping(
        self,
    ) -> None:
        """DB設定の読込失敗をstderrへ出して取得を始めないこと"""

        stdout = io.StringIO()
        stderr = io.StringIO()
        collect_releases = Mock()

        with patch.object(
            fetch_and_save_env_press,
            "_load_session_factory",
            side_effect=RuntimeError("unsafe configuration detail"),
        ):
            exit_code = main(
                [],
                collect_releases=collect_releases,
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(len(stderr.getvalue().splitlines()), 1)
        self.assertIn(
            f"target={fetch_and_save_env_press.DATABASE_URL_ENV}",
            stderr.getvalue(),
        )
        self.assertIn("exception=RuntimeError", stderr.getvalue())
        self.assertIn(
            "reason=database configuration could not be loaded",
            stderr.getvalue(),
        )
        self.assertNotIn("unsafe configuration detail", stderr.getvalue())
        collect_releases.assert_not_called()

    def test_load_session_factory_initializes_database_resources(self) -> None:
        """CLI用Sessionファクトリ取得時にDBリソースを初期化すること"""

        session_factory = Mock()

        with patch.object(
            fetch_and_save_env_press,
            "get_session_factory",
            return_value=session_factory,
        ) as get_session_factory_mock:
            loaded_factory = (
                fetch_and_save_env_press._load_session_factory()
            )

        get_session_factory_mock.assert_called_once_with()
        self.assertIs(loaded_factory, session_factory)

    def test_main_does_not_open_save_session_when_scraper_fails(self) -> None:
        """scraper失敗時は保存用Sessionを作らずエラーを返すこと"""

        session_factory = Mock()
        stdout = io.StringIO()
        stderr = io.StringIO()

        def collect_releases(
            _args: object,
            _stderr: object,
            _known_urls: object,
        ) -> CollectedPressReleases:
            raise RuntimeError(
                "scraper command failed: exit_code=1 "
                "stderr=error: target=fixture "
                "exception=InvalidPressReleaseUrlError "
                "reason=invalid press release URL: "
                "validation=non_ascii_character "
                "title='URL形式が不正な発表' "
                "href='/press/日本語.html'"
            )

        exit_code = main(
            ["--url", INDEX_URL],
            session_factory=session_factory,
            collect_releases=collect_releases,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(len(stderr.getvalue().splitlines()), 1)
        self.assertIn(f"target={INDEX_URL}", stderr.getvalue())
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

    def test_main_reports_url_rejected_by_actual_scraper_cli(self) -> None:
        """scraper subprocessのURL検証理由を引き継ぎDBを開かないこと"""

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

    def test_main_normalizes_error_target_to_one_line(self) -> None:
        """エラー対象の改行をstderrへ持ち込まないこと"""

        target_url = f"{INDEX_URL}\ninjected=true"
        stderr = io.StringIO()

        exit_code = main(
            ["--url", target_url],
            session_factory=Mock(),
            collect_releases=Mock(side_effect=RuntimeError("failed")),
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(len(stderr.getvalue().splitlines()), 1)
        self.assertIn(
            f"target={INDEX_URL} injected=true",
            stderr.getvalue(),
        )

    def test_main_redacts_url_credentials_from_runtime_error(self) -> None:
        """エラー対象と理由に含まれるURL認証情報を伏せること"""

        credential_url = (
            "https://user:password@example.com/press/index.html"
        )
        stderr = io.StringIO()

        exit_code = main(
            ["--url", credential_url],
            session_factory=Mock(),
            collect_releases=Mock(
                side_effect=RuntimeError(
                    f"invalid source URL: {credential_url}"
                )
            ),
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertNotIn("user:password", stderr.getvalue())
        self.assertEqual(
            stderr.getvalue().count(
                "https://[redacted]@example.com"
            ),
            2,
        )

    def test_main_escapes_terminal_control_characters(self) -> None:
        """エラー対象と理由の端末制御文字を無害な表記へ変換すること"""

        stderr = io.StringIO()

        exit_code = main(
            ["--url", f"{INDEX_URL}\x1b[31m"],
            session_factory=Mock(),
            collect_releases=Mock(
                side_effect=RuntimeError("failed\x1b[0m")
            ),
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertNotIn("\x1b", stderr.getvalue())
        self.assertIn(r"\x1b[31m", stderr.getvalue())
        self.assertIn(r"\x1b[0m", stderr.getvalue())

    def test_main_rolls_back_save_session_on_save_failure(self) -> None:
        """保存失敗時は保存用Sessionをrollbackして閉じること"""

        session = Mock(spec=Session)
        session.scalar.side_effect = RuntimeError("database unavailable")
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = main(
            ["--url", INDEX_URL],
            session_factory=lambda: session,
            collect_releases=(
                lambda _args, _stderr, _known_urls: _collected_releases()
            ),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("reason=database unavailable", stderr.getvalue())
        session.commit.assert_not_called()
        session.rollback.assert_called_once_with()
        session.close.assert_called_once_with()

    def test_main_reports_output_failure_after_commit_without_rollback(
        self,
    ) -> None:
        """commit後の出力失敗を保存失敗と混同しないこと"""

        session = Mock(spec=Session)
        session.scalar.return_value = None
        stdout = Mock()
        stdout.write.side_effect = BrokenPipeError("output closed")
        stderr = io.StringIO()

        exit_code = main(
            ["--url", INDEX_URL],
            session_factory=lambda: session,
            collect_releases=(
                lambda _args, _stderr, _known_urls: _collected_releases()
            ),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertIn(
            (
                "reason=database commit succeeded but result output failed: "
                "output closed"
            ),
            stderr.getvalue(),
        )
        session.commit.assert_called_once_with()
        session.rollback.assert_not_called()
        session.close.assert_called_once_with()

    def test_main_reports_flush_failure_after_commit_without_rollback(
        self,
    ) -> None:
        """commit後のstdout flush失敗を保存失敗と混同しないこと"""

        session = Mock(spec=Session)
        session.scalar.return_value = None
        stdout = Mock()
        # argparseの色表示判定から実際のstdoutと同様に整数のfdを返す。
        stdout.fileno.return_value = 1
        stdout.flush.side_effect = BrokenPipeError("flush failed")
        stderr = io.StringIO()

        with (
            patch.object(fetch_and_save_env_press.sys, "stdout", stdout),
            patch.object(
                fetch_and_save_env_press,
                "_redirect_stdout_after_broken_pipe",
            ) as mock_redirect,
        ):
            exit_code = main(
                ["--url", INDEX_URL],
                session_factory=lambda: session,
                collect_releases=(
                    lambda _args, _stderr, _known_urls: _collected_releases()
                ),
                stderr=stderr,
            )

        self.assertEqual(exit_code, 1)
        self.assertIn(
            (
                "reason=database commit succeeded but result output failed: "
                "flush failed"
            ),
            stderr.getvalue(),
        )
        stdout.write.assert_called_once()
        stdout.flush.assert_called_once_with()
        mock_redirect.assert_called_once_with(stdout)
        session.commit.assert_called_once_with()
        session.rollback.assert_not_called()
        session.close.assert_called_once_with()

    def test_redirect_stdout_after_broken_pipe_replaces_stdout_fd(
        self,
    ) -> None:
        """BrokenPipeError後のstdoutを破棄先へ切り替えること"""

        stdout = Mock()
        stdout.fileno.return_value = 42

        with (
            patch.object(fetch_and_save_env_press.sys, "stdout", stdout),
            patch.object(
                fetch_and_save_env_press.os,
                "open",
                return_value=99,
            ) as mock_open,
            patch.object(
                fetch_and_save_env_press.os,
                "dup2",
            ) as mock_dup2,
            patch.object(
                fetch_and_save_env_press.os,
                "close",
            ) as mock_close,
        ):
            fetch_and_save_env_press._redirect_stdout_after_broken_pipe(stdout)

        stdout.fileno.assert_called_once_with()
        mock_open.assert_called_once_with(
            fetch_and_save_env_press.os.devnull,
            fetch_and_save_env_press.os.O_WRONLY,
        )
        mock_dup2.assert_called_once_with(99, 42)
        mock_close.assert_called_once_with(99)

    def test_redirect_stdout_after_broken_pipe_closes_fd_when_dup2_fails(
        self,
    ) -> None:
        """stdoutの切り替え失敗時も破棄先のfdを閉じること"""

        stdout = Mock()
        stdout.fileno.return_value = 42

        with (
            patch.object(fetch_and_save_env_press.sys, "stdout", stdout),
            patch.object(
                fetch_and_save_env_press.os,
                "open",
                return_value=99,
            ),
            patch.object(
                fetch_and_save_env_press.os,
                "dup2",
                side_effect=OSError("redirect failed"),
            ) as mock_dup2,
            patch.object(
                fetch_and_save_env_press.os,
                "close",
            ) as mock_close,
        ):
            fetch_and_save_env_press._redirect_stdout_after_broken_pipe(stdout)

        mock_dup2.assert_called_once_with(99, 42)
        mock_close.assert_called_once_with(99)

    def test_parse_scraper_snapshot_restores_releases(self) -> None:
        """scraper CLI JSONを保存serviceへ渡せる取得結果へ復元すること"""

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
        """scraper側のlockfileに沿って既存CLIを実行すること"""

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
        """全月別ページ巡回指定をscraper CLIへ渡すこと"""

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
        """scraper子プロセスへDB認証情報を渡さないこと"""

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

    def test_main_rejects_from_file_with_all_archive_months(self) -> None:
        """保存済みHTMLと全月別ページ巡回指定の併用を拒否すること"""

        stderr = io.StringIO()
        session_factory = Mock()
        collect_releases = Mock()

        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "index.html"
            html_path.write_text("", encoding="utf-8")

            with redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    main(
                        [
                            "--from-file",
                            str(html_path),
                            "--all-archive-months",
                        ],
                        session_factory=session_factory,
                        collect_releases=collect_releases,
                    )

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            "--from-file cannot be used with --all-archive-months",
            stderr.getvalue(),
        )
        session_factory.assert_not_called()
        collect_releases.assert_not_called()

    def test_main_rejects_archive_month_limit_with_all_archive_months(
        self,
    ) -> None:
        """月別ページ数指定と全月別ページ巡回指定の併用を拒否すること"""

        stderr = io.StringIO()
        session_factory = Mock()
        collect_releases = Mock()

        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main(
                    ["--archive-month-limit", "1", "--all-archive-months"],
                    session_factory=session_factory,
                    collect_releases=collect_releases,
                )

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            "--archive-month-limit cannot be used with --all-archive-months",
            stderr.getvalue(),
        )
        session_factory.assert_not_called()
        collect_releases.assert_not_called()

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
            fetch_and_save_env_press.subprocess,
            "run",
        ) as mock_run:
            mock_run.return_value = completed
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

    def test_collect_releases_forwards_verbose_stderr_on_success(self) -> None:
        """verbose時はscraper CLIの進捗をstderrへ流すこと"""

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
        stderr = io.StringIO()

        with patch.object(
            fetch_and_save_env_press.subprocess,
            "run",
        ) as mock_run:
            mock_run.return_value = completed

            fetch_and_save_env_press._collect_releases_from_scraper_cli(
                args,
                stderr,
                (),
            )

        self.assertEqual(stderr.getvalue(), completed.stderr)

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
            fetch_and_save_env_press.subprocess,
            "run",
        ) as mock_run:
            mock_run.side_effect = run_subprocess

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


def _collected_releases() -> CollectedPressReleases:
    """手動取得・保存テスト用の取得結果を生成"""

    return CollectedPressReleases(
        source_url=INDEX_URL,
        releases=(
            ScraperCliRelease(
                title="報道発表1",
                published_at=date(2026, 5, 1),
                url=SOURCE_URL_1,
                source_categories=("総合政策",),
            ),
            ScraperCliRelease(
                title="報道発表2",
                published_at=date(2026, 5, 2),
                url=SOURCE_URL_2,
                source_categories=(),
            ),
        ),
        fetched_page_urls=(INDEX_URL,),
        stop_reason=None,
    )


if __name__ == "__main__":
    unittest.main()
