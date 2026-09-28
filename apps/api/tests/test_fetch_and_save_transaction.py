"""SessionのMockを使い、取得・保存CLIのトランザクションと結果出力を検証"""

from datetime import date
import io
import json
import unittest
from unittest.mock import Mock, patch

from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session

from press_watch_api.commands import fetch_and_save_env_press
from press_watch_api.services import (
    fixed_category_classification as classification,
)
from press_watch_api.commands.fetch_and_save_env_press import (
    CollectedPressReleases,
    ScraperCliRelease,
    main,
)

from api_test_constants import (
    ENV_PRESS_INDEX_URL as INDEX_URL,
    ENV_PRESS_RELEASE_URL_1 as SOURCE_URL_1,
    ENV_PRESS_RELEASE_URL_2 as SOURCE_URL_2,
)


class FetchAndSaveTransactionTest(unittest.TestCase):
    """取得・保存CLIのSession管理と結果出力のテスト"""

    def setUp(self) -> None:
        """分類ルールを固定し、テスト終了時にpatchを自動復元"""

        self.rule_loader = self.enterContext(
            patch.object(
                classification,
                "load_fixed_category_rules",
                return_value=((51, "大気"),),
            ),
        )

    def test_main_saves_scraper_releases_and_commits(self) -> None:
        """取得結果を保存serviceへ渡し、成功時にcommitすること"""

        session = Mock(spec=Session)
        session.scalars.return_value = (
            Mock(id=1009, title="報道発表1", source_url=SOURCE_URL_1),
            Mock(id=2017, title="報道発表2", source_url=SOURCE_URL_2),
        )
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
        session.scalars.assert_called_once()
        session.scalar.assert_not_called()
        session.add.assert_not_called()
        session.flush.assert_not_called()

    def test_main_rolls_back_when_classification_rules_are_not_ready(
        self,
    ) -> None:
        """分類ルールの未整備を報告し、rollbackしてSessionを閉じること"""

        session = Mock(spec=Session)
        session.scalars.return_value = (
            Mock(id=1009, title="大気", source_url=SOURCE_URL_1),
        )
        self.rule_loader.side_effect = (
            classification.FixedCategoryClassificationError(
                "fixed category definitions are not ready",
            )
        )
        stdout, stderr = io.StringIO(), io.StringIO()
        code = _run_main_without_exposing_exception_chain(
            session, stdout, stderr,
        )
        self.assertEqual((code, stdout.getvalue()), (1, ""))
        self.assertEqual(stderr.getvalue(), (
            f"error: target={INDEX_URL} "
            "exception=FixedCategoryClassificationError "
            "reason=fixed category definitions are not ready\n"
        ))
        session.commit.assert_not_called()
        session.rollback.assert_called_once_with()
        session.close.assert_called_once_with()

    def test_main_rolls_back_classification_insert_failure_with_safe_diagnostic(
        self,
    ) -> None:
        """分類の保存失敗時はDB詳細を伏せ、rollbackしてSessionを閉じること"""

        session = Mock(spec=Session)
        session.scalars.return_value = (
            Mock(id=1009, title="大気", source_url=SOURCE_URL_1),
        )
        session.execute.side_effect = _database_statement_error()
        stdout, stderr = io.StringIO(), io.StringIO()
        code = _run_main_without_exposing_exception_chain(
            session, stdout, stderr,
        )
        self.assertEqual((code, stdout.getvalue()), (1, ""))
        session.execute.assert_called_once()
        _assert_database_error_is_sanitized(stderr.getvalue())
        session.commit.assert_not_called()
        session.rollback.assert_called_once_with()
        session.close.assert_called_once_with()

    def test_main_reports_skipped_count(self) -> None:
        """既存URLをskip件数としてstdout JSONへ出すこと"""

        session = Mock(spec=Session)
        session.scalars.return_value = (
            Mock(id=1009, title="報道発表1", source_url=SOURCE_URL_1),
        )
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

    def test_main_rolls_back_save_session_on_save_failure(self) -> None:
        """保存失敗時は保存用Sessionをrollbackして閉じること"""

        session = Mock(spec=Session)
        session.scalars.side_effect = RuntimeError("database unavailable")
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

    def test_main_does_not_expose_database_details_from_save_error(
        self,
    ) -> None:
        """保存時のSQLAlchemyエラーの診断に入力値やSQLを含めないこと"""

        session = Mock(spec=Session)
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch.object(
            fetch_and_save_env_press,
            "save_press_releases",
            side_effect=_database_statement_error(),
        ):
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
        _assert_database_error_is_sanitized(stderr.getvalue())
        session.commit.assert_not_called()
        session.rollback.assert_called_once_with()
        session.close.assert_called_once_with()

    def test_main_does_not_expose_database_details_from_commit_error(
        self,
    ) -> None:
        """commit時のSQLAlchemyエラーの診断に入力値やSQLを含めないこと"""

        session = Mock(spec=Session)
        session.commit.side_effect = _database_statement_error()
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch.object(
            fetch_and_save_env_press,
            "save_press_releases",
            return_value=Mock(saved_count=2, skipped_count=0),
        ):
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
        _assert_database_error_is_sanitized(stderr.getvalue())
        session.commit.assert_called_once_with()
        session.rollback.assert_called_once_with()
        session.close.assert_called_once_with()

    def test_main_does_not_expose_database_details_from_known_url_error(
        self,
    ) -> None:
        """既知URL取得時のSQLAlchemyエラーの診断にDB詳細を含めないこと"""

        session = Mock(spec=Session)
        session.scalar.side_effect = _database_statement_error()
        collect_releases = Mock()
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = main(
            ["--url", INDEX_URL, "--archive-month-limit", "1"],
            session_factory=lambda: session,
            collect_releases=collect_releases,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        _assert_database_error_is_sanitized(stderr.getvalue())
        collect_releases.assert_not_called()
        session.commit.assert_not_called()
        session.rollback.assert_not_called()
        session.close.assert_called_once_with()

    def test_main_reports_output_failure_after_commit_without_rollback(
        self,
    ) -> None:
        """commit済みの出力失敗と報告し、rollbackしないこと"""

        session = Mock(spec=Session)
        session.scalars.return_value = (
            Mock(id=1009, title="報道発表1", source_url=SOURCE_URL_1),
            Mock(id=2017, title="報道発表2", source_url=SOURCE_URL_2),
        )
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

    def test_main_contains_cleanup_errors_after_database_failure(self) -> None:
        """保存・commit失敗に終了処理の失敗が重なっても詳細を漏らさないこと"""

        for failed_operation in ("save", "commit"):
            for failed_cleanup in (
                ("rollback",), ("close",), ("rollback", "close"),
            ):
                with self.subTest(
                    failed_operation=failed_operation,
                    failed_cleanup=failed_cleanup,
                ):
                    session = Mock(spec=Session)
                    session.scalars.return_value = ()
                    failing_method = (
                        session.scalars
                        if failed_operation == "save"
                        else session.commit
                    )
                    failing_method.side_effect = _database_statement_error()
                    for operation in failed_cleanup:
                        getattr(session, operation).side_effect = (
                            _database_statement_error()
                        )
                    stdout = io.StringIO()
                    stderr = io.StringIO()

                    exit_code = _run_main_without_exposing_exception_chain(
                        session, stdout, stderr,
                    )

                    self.assertEqual(exit_code, 1)
                    self.assertEqual(stdout.getvalue(), "")
                    lines = stderr.getvalue().splitlines(keepends=True)
                    self.assertEqual(len(lines), 1 + len(failed_cleanup))
                    _assert_database_error_is_sanitized(lines[0])
                    for line, operation in zip(
                        lines[1:], failed_cleanup, strict=True,
                    ):
                        _assert_cleanup_error_is_sanitized(
                            line, operation=operation, committed=False,
                        )
                    self.assertEqual(
                        session.commit.call_count,
                        int(failed_operation == "commit"),
                    )
                    session.rollback.assert_called_once_with()
                    session.close.assert_called_once_with()

    def test_main_reports_close_failure_after_commit_without_rollback(
        self,
    ) -> None:
        """commit後のclose失敗はDB詳細を伏せて報告し、rollbackしないこと"""

        session = Mock(spec=Session)
        session.scalars.return_value = ()
        session.close.side_effect = _database_statement_error()
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = _run_main_without_exposing_exception_chain(
            session, stdout, stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(stdout.getvalue())["saved_count"], 0)
        _assert_cleanup_error_is_sanitized(
            stderr.getvalue(), operation="close", committed=True,
        )
        session.commit.assert_called_once_with()
        session.rollback.assert_not_called()
        session.close.assert_called_once_with()

    def test_main_preserves_output_error_when_close_also_fails(self) -> None:
        """stdoutとcloseが両方失敗しても出力エラーを残しrollbackしないこと"""

        session = Mock(spec=Session)
        session.scalars.return_value = ()
        session.close.side_effect = _database_statement_error()
        stdout = Mock()
        stdout.write.side_effect = BrokenPipeError("output closed")
        stderr = io.StringIO()

        exit_code = _run_main_without_exposing_exception_chain(
            session, stdout, stderr,
        )

        self.assertEqual(exit_code, 1)
        lines = stderr.getvalue().splitlines(keepends=True)
        self.assertEqual(len(lines), 2)
        expected = (
            f"error: target={INDEX_URL} exception=BrokenPipeError "
            "reason=database commit succeeded but result output failed: "
            "output closed\n"
        )
        if lines[0] != expected:
            self.fail("stdoutエラーの既存診断が維持されていません。")
        _assert_cleanup_error_is_sanitized(
            lines[1], operation="close", committed=True,
        )
        session.commit.assert_called_once_with()
        session.rollback.assert_not_called()
        session.close.assert_called_once_with()

    def test_main_preserves_non_database_error_when_rollback_fails(
        self,
    ) -> None:
        """rollback失敗時もSQLAlchemy以外の元のエラー理由を維持すること"""

        session = Mock(spec=Session)
        session.scalars.side_effect = ValueError("invalid release input")
        session.rollback.side_effect = _database_statement_error()
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = _run_main_without_exposing_exception_chain(
            session, stdout, stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        lines = stderr.getvalue().splitlines(keepends=True)
        self.assertEqual(len(lines), 2)
        expected = (
            f"error: target={INDEX_URL} exception=ValueError "
            "reason=invalid release input\n"
        )
        if lines[0] != expected:
            self.fail("SQLAlchemy以外の既存エラー理由が維持されていません。")
        _assert_cleanup_error_is_sanitized(
            lines[1], operation="rollback", committed=False,
        )
        session.commit.assert_not_called()
        session.rollback.assert_called_once_with()
        session.close.assert_called_once_with()

    def test_main_contains_errors_when_stderr_write_fails(self) -> None:
        """診断を書けない場合も例外を外へ漏らさず終了処理を続けること"""

        for failure in ("save", "commit", "output", "close"):
            with self.subTest(failure=failure):
                session = Mock(spec=Session)
                session.scalars.return_value = ()
                stdout = io.StringIO()
                stderr = Mock()
                stderr.write.side_effect = OSError(
                    "fixed stderr write failure",
                )
                if failure == "save":
                    session.scalars.side_effect = _database_statement_error()
                    session.rollback.side_effect = _database_statement_error()
                elif failure == "commit":
                    session.commit.side_effect = _database_statement_error()
                elif failure == "output":
                    stdout = Mock()
                    stdout.write.side_effect = BrokenPipeError("output closed")
                session.close.side_effect = _database_statement_error()

                exit_code = _run_main_without_exposing_exception_chain(
                    session, stdout, stderr,
                )

                self.assertEqual(exit_code, 1)
                self.assertEqual(
                    session.commit.call_count, int(failure != "save"),
                )
                self.assertEqual(
                    session.rollback.call_count,
                    int(failure in ("save", "commit")),
                )
                session.close.assert_called_once_with()
                self.assertTrue(stderr.write.called)

    def test_main_contains_known_url_error_when_stderr_write_fails(
        self,
    ) -> None:
        """既知URLの読取失敗も、stderrへの出力失敗で外へ漏らさないこと"""

        session = Mock(spec=Session)
        session.scalar.side_effect = _database_statement_error()
        collect_releases = Mock()
        stderr = Mock()
        stderr.write.side_effect = OSError("fixed stderr write failure")
        stdout = io.StringIO()

        try:
            exit_code = main(
                ["--url", INDEX_URL, "--archive-month-limit", "1"],
                session_factory=lambda: session,
                collect_releases=collect_releases,
                stdout=stdout,
                stderr=stderr,
            )
        except Exception:
            raise AssertionError("既知URLの取得例外がCLIの外へ漏れました。") from None

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        collect_releases.assert_not_called()
        session.commit.assert_not_called()
        session.rollback.assert_not_called()
        session.close.assert_called_once_with()
        self.assertTrue(stderr.write.called)

    def test_main_reports_flush_failure_after_commit_without_rollback(
        self,
    ) -> None:
        """commit後のstdout flush失敗を出力エラーと報告し、rollbackしないこと"""

        session = Mock(spec=Session)
        session.scalars.return_value = (
            Mock(id=1009, title="報道発表1", source_url=SOURCE_URL_1),
            Mock(id=2017, title="報道発表2", source_url=SOURCE_URL_2),
        )
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


def _run_main_without_exposing_exception_chain(
    session: Session,
    stdout: object,
    stderr: object,
) -> int:
    """固定の取得結果でCLIを実行し、漏れた例外の詳細をテスト出力から除外

    Args:
        session: 保存処理や終了処理の成功・失敗を設定したSessionのMock
        stdout: 結果の記録、または出力失敗の再現に使う出力先
        stderr: 診断の記録、または出力失敗の再現に使う出力先

    Returns:
        CLIが返した終了コード

    Raises:
        AssertionError: CLIからExceptionが漏れた場合。元の例外チェーンは非表示
    """

    try:
        return main(
            ["--url", INDEX_URL],
            session_factory=lambda: session,
            collect_releases=(
                lambda _args, _stderr, _known_urls: _collected_releases()
            ),
            stdout=stdout,
            stderr=stderr,
        )
    except Exception:
        # REDのtracebackにも、元のDB例外とその入力値を残さない。
        raise AssertionError("終了処理の例外がCLIの外へ漏れました。") from None


def _assert_cleanup_error_is_sanitized(
    diagnostic: str,
    *,
    operation: str,
    committed: bool,
) -> None:
    """終了処理の診断を固定形式と照合し、不一致でも診断本文を非表示

    Args:
        diagnostic: stderrから取得した終了処理エラーの診断1行
        operation: 失敗した終了処理名（rollbackまたはclose）
        committed: エラー発生前にcommitが成功していたかどうか

    Raises:
        AssertionError: 診断が固定形式と異なる場合。実際の診断本文は非表示
    """

    expected = (
        f"error: target={INDEX_URL} operation={operation} "
        f"committed={str(committed).lower()} "
        "exception=StatementError reason=database operation failed\n"
    )
    if diagnostic != expected:
        raise AssertionError("終了処理エラーの診断が固定形式と一致しません。")


def _database_statement_error() -> StatementError:
    """診断への情報漏れを検出するため、架空のDB詳細を含む例外を生成

    Returns:
        架空の入力値・接続情報・SQL・ドライバー詳細を含むSQLAlchemy例外
    """

    return StatementError(
        (
            "sentinel press release title; "
            "sentinel connection postgresql://user:password@database.test/db"
        ),
        (
            "INSERT INTO press_releases (title, source_url) "
            "VALUES (%(title)s, %(source_url)s)"
        ),
        {
            "title": "sentinel press release title",
            "source_url": "https://example.test/press/sentinel-detail",
        },
        RuntimeError("sentinel driver detail"),
    )


def _assert_database_error_is_sanitized(diagnostic: str) -> None:
    """DBエラーの診断を固定形式と照合し、不一致でも診断本文を非表示

    Args:
        diagnostic: stderrから取得したDBエラーの診断1行

    Raises:
        AssertionError: 診断が固定形式と異なる場合。実際の診断本文は非表示
    """

    expected = (
        f"error: target={INDEX_URL} "
        "exception=StatementError reason=database operation failed\n"
    )
    if diagnostic != expected:
        raise AssertionError(
            "SQLAlchemyエラーの診断が固定形式と一致しません。"
        )


def _collected_releases() -> CollectedPressReleases:
    """HTTP取得を行わず、保存処理のテスト用に固定の取得結果を生成

    Returns:
        報道発表2件と起点ページURLを含み、巡回停止理由のない取得結果
    """

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
