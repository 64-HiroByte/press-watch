"""固定カテゴリ再分類CLIの終了コード・診断・Session管理のテスト"""

import io
import json
import os
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import Mock, call, patch

from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session

from press_watch_api.commands import reclassify_fixed_categories as command
from press_watch_api.services.fixed_category_classification import (
    FixedCategoryClassificationError,
)
from press_watch_api.services.fixed_category_reclassification import (
    PressReleaseReclassificationResult,
)


class ReclassifyFixedCategoriesCommandTest(unittest.TestCase):
    """DBをMockへ置換し、CLIが管理するトランザクションと診断を確認"""

    def setUp(self) -> None:
        self.session = Mock(spec=Session)
        self.factory = Mock(return_value=self.session)
        self.stdout, self.stderr = io.StringIO(), io.StringIO()
        self.reclassify = self.enterContext(
            patch.object(
                command,
                "reclassify_press_releases",
                return_value=PressReleaseReclassificationResult(3, 2, 3),
            )
        )
        self.get_factory = self.enterContext(
            patch.object(
                command, "get_session_factory", return_value=self.factory
            )
        )

    def run_command(self, argv: list[str] | None = None, **kwargs) -> int:
        """DBを差し替えたCLIの終了コードを取得

        Args:
            argv: CLI引数。Noneの場合は引数なしで実行
            kwargs: mainへ渡すSession生成関数や標準出力・標準エラーの差し替え

        Returns:
            CLIの終了コード。未捕捉例外は型名だけを出してテスト失敗とする
        """

        options = dict(
            session_factory=self.factory,
            stdout=self.stdout,
            stderr=self.stderr,
        )
        options.update(kwargs)
        try:
            return command.main([] if argv is None else argv, **options)
        except BaseException as error:
            self.fail(f"CLIから例外が伝播しました: {type(error).__name__}")

    def assert_safe_diagnostic(self, diagnostic: str) -> None:
        """固定診断があり、架空の機密文字列・例外詳細が混入していないことを確認"""

        self.assertIn("error: operation=", diagnostic)
        for forbidden in (
            "PRIVATE_",
            "Traceback",
            "Exception ignored",
            "StatementError",
        ):
            self.assertNotIn(forbidden, diagnostic)

    def test_success_commits_once_then_outputs_counts_and_closes(self) -> None:
        """再分類・commit・closeの順序と、正常時の件数JSONを確認"""

        operations = Mock()
        for name, method in (
            ("reclassify", self.reclassify),
            ("commit", self.session.commit),
            ("close", self.session.close),
        ):
            operations.attach_mock(method, name)
        self.assertEqual(self.run_command(), 0)
        self.session.commit.assert_called_once_with()
        self.assertEqual(
            json.loads(self.stdout.getvalue()),
            {
                "processed_count": 3,
                "matched_count": 2,
                "classification_count": 3,
            },
        )
        self.assertEqual(self.stderr.getvalue(), "")
        self.assertEqual(
            operations.mock_calls,
            [call.reclassify(self.session), call.commit(), call.close()],
        )
        self.session.rollback.assert_not_called()

    def test_empty_result_is_committed_and_reports_zero_counts(self) -> None:
        """対象0件でもcommitし、改行付きの件数JSONを返すことを確認"""

        self.reclassify.return_value = PressReleaseReclassificationResult(
            0, 0, 0
        )
        self.assertEqual(self.run_command(), 0)
        self.assertEqual(
            self.stdout.getvalue(),
            '{"processed_count": 0, "matched_count": 0, '
            '"classification_count": 0}\n',
        )
        self.session.commit.assert_called_once_with()

    def test_help_and_invalid_arguments_do_not_initialize_database(
        self,
    ) -> None:
        """ヘルプと不正引数はDBへ進まず、引数値を診断へ含めないことを確認"""

        for argv, expected in (
            (["--help"], 0),
            (["-h"], 0),
            (["--help", "--unknown"], 2),
            (["--unknown", "PRIVATE_ARGUMENT"], 2),
            (["--he"], 2),
        ):
            with self.subTest(argv=argv):
                output, errors = io.StringIO(), io.StringIO()
                self.assertEqual(
                    self.run_command(argv, stdout=output, stderr=errors),
                    expected,
                )
                if expected == 0:
                    self.assertIn("usage:", output.getvalue())
                else:
                    self.assert_safe_diagnostic(errors.getvalue())
                    self.assertIn("operation=arguments", errors.getvalue())
                self.factory.assert_not_called()
                self.get_factory.assert_not_called()
                self.reclassify.assert_not_called()

    def test_uses_existing_session_factory_by_default(self) -> None:
        """Session生成関数の指定がない場合に、既存のDB設定を使用"""

        self.assertEqual(self.run_command(session_factory=None), 0)
        self.get_factory.assert_called_once_with()
        self.factory.assert_called_once_with()

    def test_configuration_and_open_failures_do_not_run_service(self) -> None:
        """Session生成前の失敗では、再分類や存在しないSessionの終了を行わない"""

        for operation, method in (
            ("configure", self.get_factory),
            ("open_session", self.factory),
        ):
            with self.subTest(operation=operation):
                method.side_effect = _database_error()
                errors = io.StringIO()
                self.assertEqual(
                    self.run_command(session_factory=None, stderr=errors), 1
                )
                self.assert_safe_diagnostic(errors.getvalue())
                self.assertIn(f"operation={operation}", errors.getvalue())
                self.reclassify.assert_not_called()
                self.session.rollback.assert_not_called()
                self.session.close.assert_not_called()
                method.side_effect = None

    def test_service_and_commit_failures_rollback_close_without_output(
        self,
    ) -> None:
        """処理・commitの失敗や中断で、成功出力をせずrollbackとcloseを試行"""

        for operation, method in (
            ("reclassify", self.reclassify),
            ("commit", self.session.commit),
        ):
            for error in (
                _database_error(),
                FixedCategoryClassificationError("PRIVATE_RULE_DETAIL"),
                RuntimeError("PRIVATE_CLASSIFIER_DETAIL"),
                KeyboardInterrupt(),
            ):
                with self.subTest(
                    operation=operation, error=type(error).__name__
                ):
                    self.session.reset_mock()
                    output, errors = io.StringIO(), io.StringIO()
                    method.side_effect = error
                    self.assertEqual(
                        self.run_command(stdout=output, stderr=errors), 1
                    )
                    self.assertEqual(output.getvalue(), "")
                    self.assert_safe_diagnostic(errors.getvalue())
                    self.assertIn(f"operation={operation}", errors.getvalue())
                    self.assertIn("commit_succeeded=false", errors.getvalue())
                    if isinstance(error, KeyboardInterrupt):
                        self.assertIn(
                            "reason=operation interrupted", errors.getvalue()
                        )
                    self.session.rollback.assert_called_once_with()
                    self.session.close.assert_called_once_with()
                    if operation == "reclassify":
                        self.session.commit.assert_not_called()
                    method.side_effect = None

    def test_cleanup_failures_preserve_primary_failure_and_attempt_close(
        self,
    ) -> None:
        """rollback失敗後もcloseを試み、元の失敗と終了処理の失敗を診断"""

        for error in (_database_error(), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                self.session.reset_mock()
                self.reclassify.side_effect = _database_error()
                self.session.rollback.side_effect = error
                self.session.close.side_effect = error
                errors = io.StringIO()
                self.assertEqual(self.run_command(stderr=errors), 1)
                self.assert_safe_diagnostic(errors.getvalue())
                for operation in ("reclassify", "rollback", "close"):
                    self.assertIn(f"operation={operation}", errors.getvalue())
                self.session.rollback.assert_called_once_with()
                self.session.close.assert_called_once_with()

    def test_output_failure_or_interruption_after_commit_does_not_rollback(
        self,
    ) -> None:
        """commit後の出力失敗・中断は、確定済みの診断を出してrollbackを省略"""

        for method in ("write", "flush"):
            for error in (
                OSError("PRIVATE_OUTPUT_DETAIL"),
                KeyboardInterrupt(),
            ):
                with self.subTest(method=method, error=type(error).__name__):
                    self.session.reset_mock()
                    output, errors = Mock(), io.StringIO()
                    getattr(output, method).side_effect = error
                    self.assertEqual(
                        self.run_command(stdout=output, stderr=errors), 1
                    )
                    self.assert_safe_diagnostic(errors.getvalue())
                    self.assertIn("operation=output", errors.getvalue())
                    self.assertIn("commit_succeeded=true", errors.getvalue())
                    self.session.commit.assert_called_once_with()
                    self.session.rollback.assert_not_called()
                    self.session.close.assert_called_once_with()

    def test_close_failure_after_commit_returns_failure(self) -> None:
        """確定後のclose失敗でも終了コード1を返し、確定済みと診断"""

        self.session.close.side_effect = _database_error()
        self.assertEqual(self.run_command(), 1)
        self.assert_safe_diagnostic(self.stderr.getvalue())
        self.assertIn(
            "operation=close commit_succeeded=true", self.stderr.getvalue()
        )
        self.session.rollback.assert_not_called()

    def test_stderr_failures_do_not_escape_or_prevent_cleanup(self) -> None:
        """診断出力自体が失敗しても例外を外へ漏らさず、終了処理を継続"""

        for method in ("write", "flush"):
            with self.subTest(method=method):
                self.session.reset_mock()
                self.reclassify.side_effect = _database_error()
                self.session.rollback.side_effect = _database_error()
                errors = Mock()
                getattr(errors, method).side_effect = OSError(
                    "PRIVATE_OUTPUT_DETAIL"
                )
                self.assertEqual(self.run_command(stderr=errors), 1)
                self.session.rollback.assert_called_once_with()
                self.session.close.assert_called_once_with()

    def test_help_and_argument_diagnostic_output_failures_return_one(
        self,
    ) -> None:
        """ヘルプ・引数診断の出力障害は、通常の終了コードを1へ変更"""

        for argv in (["--help"], ["--unknown"]):
            for method in ("write", "flush"):
                with self.subTest(argv=argv, method=method):
                    broken = Mock()
                    getattr(broken, method).side_effect = OSError(
                        "PRIVATE_OUTPUT_DETAIL"
                    )
                    output, errors = (
                        (broken, io.StringIO())
                        if argv == ["--help"]
                        else (io.StringIO(), broken)
                    )
                    self.assertEqual(
                        self.run_command(argv, stdout=output, stderr=errors), 1
                    )
                    self.factory.assert_not_called()


class ReclassifyFixedCategoriesProcessTest(unittest.TestCase):
    """DBをMockにした子プロセスで、終了時flushを含む出力障害を確認"""

    def test_closed_output_pipes_keep_failure_exit_code_and_hide_details(
        self,
    ) -> None:
        """読取り側のないパイプで、終了時flushによる診断漏れや終了コード変更を防止"""

        for stream, mode, argv in (
            ("stdout", "success", []),
            ("stdout", "success", ["--help"]),
            ("stderr", "failure", []),
            ("stderr", "success", ["--unknown"]),
        ):
            with self.subTest(stream=stream, mode=mode, argv=argv):
                result = self.run_process(stream, mode, argv)
                self.assertEqual(result.returncode, 1)
                for forbidden in (
                    b"PRIVATE_",
                    b"Traceback",
                    b"Exception ignored",
                ):
                    self.assertNotIn(
                        forbidden,
                        (result.stdout or b"") + (result.stderr or b""),
                    )

    def test_closed_standard_descriptors_keep_failure_exit_code(self) -> None:
        """標準FD自体を閉じた場合も、終了時flushの例外を外へ出さず終了コード1"""

        for stream, mode, argv in (
            ("stdout", "success", ["--help"]),
            ("stderr", "failure", []),
        ):
            with self.subTest(stream=stream):
                result = self.run_process(
                    stream, mode, argv, close_descriptor=True
                )
                self.assertEqual(result.returncode, 1)
                self.assertNotIn(
                    b"Exception ignored",
                    (result.stdout or b"") + (result.stderr or b""),
                )

    def run_process(
        self,
        stream: str,
        mode: str,
        argv: list[str],
        *,
        close_descriptor: bool = False,
    ) -> subprocess.CompletedProcess[bytes]:
        """DBをMockへ置換した子プロセスで、標準ストリームの障害を再現

        Args:
            stream: 障害を起こす標準ストリーム名（stdoutまたはstderr）
            mode: 再分類の成否。failureの場合だけDB例外を発生
            argv: 子プロセスのCLIへ渡す引数
            close_descriptor: Trueなら標準FD自体を閉じる
                Falseならパイプの読取り側だけを閉じる

        Returns:
            終了コードと、障害を起こしていない側の出力を含む子プロセス結果
        """

        script = textwrap.dedent(
            """
            import os
            import sys
            from unittest.mock import Mock, patch
            from sqlalchemy.exc import StatementError
            from sqlalchemy.orm import Session
            from press_watch_api.commands import (
                reclassify_fixed_categories as command,
            )
            from press_watch_api.services import (
                fixed_category_reclassification as service,
            )

            session = Mock(spec=Session)
            failure = StatementError(
                "PRIVATE_DB_DETAIL",
                "PRIVATE_SQL",
                {},
                RuntimeError("PRIVATE_CAUSE"),
            )
            with (
                patch.object(
                    command,
                    "get_session_factory",
                    return_value=lambda: session,
                ),
                patch.object(
                    command,
                    "reclassify_press_releases",
                    return_value=service.PressReleaseReclassificationResult(
                        3,
                        2,
                        3,
                    ),
                ) as reclassify,
            ):
                if sys.argv[1] == "failure":
                    reclassify.side_effect = failure
                if sys.argv[2] != "-1":
                    os.close(int(sys.argv[2]))
                raise SystemExit(command.main(sys.argv[3:]))
        """
        )
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        try:
            closed_fd = (
                (1 if stream == "stdout" else 2) if close_descriptor else -1
            )
            return subprocess.run(
                [sys.executable, "-c", script, mode, str(closed_fd), *argv],
                stdout=write_fd if stream == "stdout" else subprocess.PIPE,
                stderr=write_fd if stream == "stderr" else subprocess.PIPE,
                timeout=10,
            )
        finally:
            os.close(write_fd)


def _database_error() -> StatementError:
    """例外本文・SQL・値の診断漏れを検出するため、架空の識別文字列を含む例外を生成"""

    return StatementError(
        "PRIVATE_DB_DETAIL",
        "PRIVATE_SQL",
        {"value": "PRIVATE_PARAMETER"},
        RuntimeError("PRIVATE_CAUSE"),
    )


if __name__ == "__main__":
    unittest.main()
