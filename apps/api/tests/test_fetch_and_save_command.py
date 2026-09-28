"""取得・保存CLIの引数検証、初期化、取得失敗の診断を検証"""

from contextlib import redirect_stderr
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from press_watch_api.commands import fetch_and_save_env_press
from press_watch_api.services import (
    fixed_category_classification as classification,
)
from press_watch_api.commands.fetch_and_save_env_press import (
    CollectedPressReleases,
    main,
)

from api_test_constants import (
    ENV_PRESS_INDEX_URL as INDEX_URL,
)


class FetchAndSaveCommandTest(unittest.TestCase):
    """取得・保存CLIの引数検証・初期化・エラー診断のテスト"""

    def setUp(self) -> None:
        """分類ルールを固定し、テスト終了時にpatchを自動復元"""

        self.rule_loader = self.enterContext(
            patch.object(
                classification,
                "load_fixed_category_rules",
                return_value=((51, "大気"),),
            ),
        )

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


if __name__ == "__main__":
    unittest.main()
