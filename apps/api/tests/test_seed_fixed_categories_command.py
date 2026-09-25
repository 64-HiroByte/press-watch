import io
import json
import os
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import Mock, patch

from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session

from press_watch_api.commands import seed_fixed_categories as command
from press_watch_api.services.fixed_category_seed import (
    FixedCategorySeedResult,
    parse_fixed_category_csv,
    seed_fixed_categories as seed_service,
)


class SeedFixedCategoriesCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Mock(spec=Session)
        self.factory = Mock(return_value=self.session)
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.seed = self.enterContext(patch.object(command, "seed_fixed_categories"))
        self.seed.return_value = FixedCategorySeedResult(10, 57)

    def run_command(self, argv: list[str] | None = None) -> int:
        return command.main(
            argv or [], session_factory=self.factory,
            stdout=self.stdout, stderr=self.stderr,
        )

    def test_success_commits_and_reports_added_counts(self) -> None:
        self.assertEqual(self.run_command(), 0)
        self.assertEqual(json.loads(self.stdout.getvalue()), {
            "categories_added": 10, "keywords_added": 57,
        })
        self.assertEqual(self.stderr.getvalue(), "")
        self.session.commit.assert_called_once_with()
        self.session.rollback.assert_not_called()
        self.session.close.assert_called_once_with()
        self.seed.assert_called_once()
        self.assertIs(self.seed.call_args.args[0], self.session)
        self.assertEqual(len(self.seed.call_args.args[1].categories), 10)
        self.assertEqual(len(self.seed.call_args.args[1].keywords), 57)

    def test_identical_database_reports_zero_additions(self) -> None:
        self.seed.return_value = FixedCategorySeedResult(0, 0)
        self.assertEqual(self.run_command(), 0)
        self.assertEqual(json.loads(self.stdout.getvalue()), {
            "categories_added": 0, "keywords_added": 0,
        })

    def test_help_and_invalid_arguments_do_not_read_csv_or_initialize_database(self) -> None:
        for argv, expected in (
            (["--help"], 0), (["-h"], 0),
            (["--from-file", "unused.csv"], 2), (["--help", "--unknown"], 2),
        ):
            with (
                self.subTest(argv=argv),
                patch.object(command, "load_fixed_category_seed") as load,
                patch.object(command, "get_session_factory") as get_factory,
            ):
                self.assertEqual(self.run_command(argv), expected)
                load.assert_not_called()
                get_factory.assert_not_called()
                self.factory.assert_not_called()
                self.seed.assert_not_called()

    def test_invalid_arguments_report_fixed_diagnostic_without_echoing_values(self) -> None:
        with (
            patch.object(command, "load_fixed_category_seed") as load,
            patch.object(command, "get_session_factory") as get_factory,
        ):
            self.assertEqual(self.run_command(["--unknown", "PRIVATE_CSV_VALUE"]), 2)
        diagnostic = self.stderr.getvalue()
        self.assertIn("operation=arguments", diagnostic)
        self.assertIn("commit_succeeded=false", diagnostic)
        self.assertIn("reason=invalid command arguments", diagnostic)
        self.assertNotIn("PRIVATE_CSV_VALUE", diagnostic)
        self.assertEqual(self.stdout.getvalue(), "")
        load.assert_not_called()
        get_factory.assert_not_called()
        self.factory.assert_not_called()

    def test_help_flushes_output_without_reading_csv_or_initializing_database(self) -> None:
        output = Mock(wraps=io.StringIO())
        with (
            patch.object(command, "load_fixed_category_seed") as load,
            patch.object(command, "get_session_factory") as get_factory,
        ):
            self.assertEqual(command.main(["--help"], stdout=output, stderr=self.stderr), 0)
        output.write.assert_called_once()
        output.flush.assert_called_once_with()
        load.assert_not_called()
        get_factory.assert_not_called()

    def test_help_write_and_flush_failures_return_execution_failure(self) -> None:
        for method in ("write", "flush"):
            with (
                self.subTest(method=method),
                patch.object(command, "load_fixed_category_seed") as load,
                patch.object(command, "get_session_factory") as get_factory,
            ):
                output, errors = Mock(), io.StringIO()
                getattr(output, method).side_effect = OSError("PRIVATE_DB_DETAIL")
                self.assertEqual(command.main(["--help"], stdout=output, stderr=errors), 1)
                self.assert_safe_diagnostic(errors.getvalue())
                self.assertIn("operation=help", errors.getvalue())
                self.assertIn("commit_succeeded=false", errors.getvalue())
                load.assert_not_called()
                get_factory.assert_not_called()

    def test_argument_diagnostic_write_and_flush_failures_return_execution_failure(self) -> None:
        for method in ("write", "flush"):
            with self.subTest(method=method):
                errors = Mock()
                getattr(errors, method).side_effect = OSError("PRIVATE_DB_DETAIL")
                self.assertEqual(command.main(["--unknown"], stdout=self.stdout, stderr=errors), 1)

    def assert_safe_diagnostic(self, value: str) -> None:
        self.assertNotEqual(value, "")
        for forbidden in ("PRIVATE_DB_DETAIL", "PRIVATE_SQL", "PRIVATE_CSV_VALUE", "Traceback"):
            self.assertNotIn(forbidden, value)

    def run_safely(self, **kwargs: object) -> int:
        try:
            return command.main([], **kwargs)
        except Exception:
            self.fail("例外がCLIの外へ漏れました")

    def test_invalid_keyword_csv_does_not_initialize_database(self) -> None:
        with (
            patch.object(command, "load_fixed_category_seed") as load,
            patch.object(command, "get_session_factory") as get_factory,
        ):
            load.side_effect = lambda: parse_fixed_category_csv(
                b"slug,name,display_order\nair,Air,1\n",
                b"category_slug,keyword\nair,valid\nair, PRIVATE_CSV_VALUE\n",
            )
            self.assertEqual(self.run_safely(stdout=self.stdout, stderr=self.stderr), 1)
            get_factory.assert_not_called()
        self.seed.assert_not_called()
        self.assertEqual(self.stdout.getvalue(), "")
        diagnostic = self.stderr.getvalue()
        self.assert_safe_diagnostic(diagnostic)
        self.assertIn("file=fixed_category_keywords.csv", diagnostic)
        self.assertIn("line=3", diagnostic)
        self.assertIn("column=keyword", diagnostic)

    def test_load_configuration_and_session_failures_do_not_seed(self) -> None:
        for stage in ("load_csv", "configure", "open_session"):
            with (
                self.subTest(stage=stage),
                patch.object(command, "load_fixed_category_seed") as load,
                patch.object(command, "get_session_factory") as get_factory,
            ):
                factory = Mock()
                get_factory.return_value = factory
                failing = {"load_csv": load, "configure": get_factory, "open_session": factory}[stage]
                failing.side_effect = RuntimeError("PRIVATE_DB_DETAIL")
                stderr = io.StringIO()
                self.assertEqual(self.run_safely(stdout=io.StringIO(), stderr=stderr), 1)
                self.assert_safe_diagnostic(stderr.getvalue())
                self.assertIn(f"operation={stage}", stderr.getvalue())
                self.seed.assert_not_called()
                if stage == "load_csv":
                    get_factory.assert_not_called()
                if stage != "open_session":
                    factory.assert_not_called()

    def test_seed_and_commit_failures_rollback_close_and_hide_details(self) -> None:
        for stage in ("seed", "commit"):
            with self.subTest(stage=stage):
                session = Mock(spec=Session)
                self.seed.side_effect = _database_error() if stage == "seed" else None
                if stage == "commit":
                    session.commit.side_effect = _database_error()
                stdout, stderr = io.StringIO(), io.StringIO()
                self.assertEqual(self.run_safely(
                    session_factory=lambda: session, stdout=stdout, stderr=stderr,
                ), 1)
                self.assertEqual(stdout.getvalue(), "")
                self.assert_safe_diagnostic(stderr.getvalue())
                self.assertIn(f"operation={stage}", stderr.getvalue())
                self.assertIn("commit_succeeded=false", stderr.getvalue())
                self.assertEqual(session.commit.call_count, int(stage == "commit"))
                session.rollback.assert_called_once_with()
                session.close.assert_called_once_with()

    def test_repository_read_and_flush_failures_reach_cli_rollback(self) -> None:
        for stage in ("read_categories", "read_keywords", "flush_categories", "flush_keywords"):
            with self.subTest(stage=stage):
                session = Mock(spec=Session)
                session.scalars.side_effect = {
                    "read_categories": [_database_error()],
                    "read_keywords": [(), _database_error()],
                    "flush_categories": [(), ()],
                    "flush_keywords": [(), ()],
                }[stage]

                def flush() -> None:
                    if session.flush.call_count == 1:
                        if stage == "flush_categories":
                            raise _database_error()
                        for index, category in enumerate(session.add_all.call_args.args[0], start=51):
                            category.id = index
                    elif stage == "flush_keywords":
                        raise _database_error()

                session.flush.side_effect = flush
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(command, "seed_fixed_categories", wraps=seed_service):
                    self.assertEqual(self.run_safely(
                        session_factory=lambda: session, stdout=stdout, stderr=stderr,
                    ), 1)
                self.assertEqual(stdout.getvalue(), "")
                self.assert_safe_diagnostic(stderr.getvalue())
                self.assertIn("operation=seed", stderr.getvalue())
                session.commit.assert_not_called()
                session.rollback.assert_called_once_with()
                session.close.assert_called_once_with()

    def test_cleanup_failures_preserve_primary_failure_and_attempt_close(self) -> None:
        for cleanup in (("rollback",), ("close",), ("rollback", "close")):
            with self.subTest(cleanup=cleanup):
                session = Mock(spec=Session)
                for method in cleanup:
                    getattr(session, method).side_effect = _database_error()
                self.seed.side_effect = _database_error()
                stderr = io.StringIO()
                self.assertEqual(self.run_safely(
                    session_factory=lambda: session, stdout=io.StringIO(), stderr=stderr,
                ), 1)
                self.assert_safe_diagnostic(stderr.getvalue())
                self.assertIn("operation=seed", stderr.getvalue())
                for method in cleanup:
                    self.assertIn(f"operation={method}", stderr.getvalue())
                session.rollback.assert_called_once_with()
                session.close.assert_called_once_with()

    def test_output_write_and_flush_failures_do_not_rollback_committed_data(self) -> None:
        for method in ("write", "flush"):
            with self.subTest(method=method):
                session = Mock(spec=Session)
                stdout, stderr = Mock(), io.StringIO()
                getattr(stdout, method).side_effect = OSError("PRIVATE_DB_DETAIL")
                self.assertEqual(self.run_safely(
                    session_factory=lambda: session, stdout=stdout, stderr=stderr,
                ), 1)
                self.assert_safe_diagnostic(stderr.getvalue())
                self.assertIn("operation=output", stderr.getvalue())
                self.assertIn("commit_succeeded=true", stderr.getvalue())
                session.commit.assert_called_once_with()
                session.rollback.assert_not_called()
                session.close.assert_called_once_with()

    def test_close_failure_after_commit_returns_failure_without_rollback(self) -> None:
        self.session.close.side_effect = _database_error()
        self.assertEqual(self.run_safely(
            session_factory=self.factory, stdout=self.stdout, stderr=self.stderr,
        ), 1)
        self.assert_safe_diagnostic(self.stderr.getvalue())
        self.assertIn("operation=close", self.stderr.getvalue())
        self.assertIn("commit_succeeded=true", self.stderr.getvalue())
        self.session.commit.assert_called_once_with()
        self.session.rollback.assert_not_called()

    def test_stderr_failure_does_not_expose_database_exception_chain(self) -> None:
        self.seed.side_effect = _database_error()
        self.session.rollback.side_effect = _database_error()
        self.session.close.side_effect = _database_error()
        stderr = Mock()
        stderr.write.side_effect = OSError("PRIVATE_DB_DETAIL")
        self.assertEqual(self.run_safely(
            session_factory=self.factory, stdout=self.stdout, stderr=stderr,
        ), 1)
        self.session.rollback.assert_called_once_with()
        self.session.close.assert_called_once_with()

    def test_default_path_uses_existing_shared_session_factory(self) -> None:
        with patch.object(command, "get_session_factory", return_value=self.factory) as get_factory:
            self.assertEqual(command.main([], stdout=self.stdout, stderr=self.stderr), 0)
        get_factory.assert_called_once_with()
        self.factory.assert_called_once_with()

    def test_real_stdout_broken_pipe_disables_exit_time_reflush(self) -> None:
        for method in ("write", "flush"):
            with self.subTest(method=method):
                session = Mock(spec=Session)
                output = Mock()
                output.fileno.return_value = 42
                getattr(output, method).side_effect = BrokenPipeError("PRIVATE_DB_DETAIL")
                stderr = io.StringIO()
                with (
                    patch.object(command.sys, "stdout", output),
                    patch.object(command.os, "open", return_value=99) as open_file,
                    patch.object(command.os, "dup2") as duplicate,
                    patch.object(command.os, "close") as close_file,
                ):
                    self.assertEqual(self.run_safely(
                        session_factory=lambda: session, stderr=stderr,
                    ), 1)
                duplicate.assert_called_once_with(99, 42)
                open_file.assert_called_once_with(command.os.devnull, command.os.O_WRONLY)
                close_file.assert_called_once_with(99)
                self.assert_safe_diagnostic(stderr.getvalue())
                session.rollback.assert_not_called()
                session.close.assert_called_once_with()

    def test_output_and_close_errors_are_both_reported_after_commit(self) -> None:
        output = Mock()
        output.write.side_effect = OSError("PRIVATE_DB_DETAIL")
        self.session.close.side_effect = _database_error()
        self.assertEqual(self.run_safely(
            session_factory=self.factory, stdout=output, stderr=self.stderr,
        ), 1)
        diagnostic = self.stderr.getvalue()
        self.assert_safe_diagnostic(diagnostic)
        self.assertIn("operation=output", diagnostic)
        self.assertIn("operation=close", diagnostic)
        self.session.rollback.assert_not_called()


class SeedFixedCategoriesProcessTest(unittest.TestCase):
    def test_closed_output_pipes_keep_execution_failure_exit_code(self) -> None:
        for stream, mode, argv in (
            ("stdout", "success", ["--help"]),
            ("stdout", "success", []),
            ("stderr", "failure", []),
            ("stderr", "success", ["--unknown"]),
        ):
            with self.subTest(stream=stream, mode=mode, argv=argv):
                result = self._run_with_unavailable_output(stream, mode, argv)
                self.assertEqual(result.returncode, 1)
                visible_output = (result.stdout or b"") + (result.stderr or b"")
                for forbidden in (b"PRIVATE_DB_DETAIL", b"PRIVATE_SQL", b"Traceback", b"Exception ignored"):
                    self.assertNotIn(forbidden, visible_output)

    def test_closed_standard_descriptors_keep_execution_failure_exit_code(self) -> None:
        for stream, mode, argv in (("stdout", "success", ["--help"]), ("stderr", "failure", [])):
            with self.subTest(stream=stream):
                result = self._run_with_unavailable_output(stream, mode, argv, close_descriptor=True)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn(b"Exception ignored", (result.stdout or b"") + (result.stderr or b""))

    def _run_with_unavailable_output(
        self, stream: str, mode: str, argv: list[str], *, close_descriptor: bool = False,
    ) -> subprocess.CompletedProcess[bytes]:
        # DBはMockへ差し替え、実際のファイル記述子とPython終了時のflushを確認する。
        script = textwrap.dedent("""
            import os
            import sys
            from unittest.mock import Mock, patch
            from sqlalchemy.exc import StatementError
            from sqlalchemy.orm import Session
            from press_watch_api.commands import seed_fixed_categories as command
            from press_watch_api.services.fixed_category_seed import FixedCategorySeedResult

            session = Mock(spec=Session)
            failure = StatementError("PRIVATE_DB_DETAIL", "PRIVATE_SQL", {}, RuntimeError("PRIVATE_DB_DETAIL"))
            with (
                patch.object(command, "get_session_factory", return_value=lambda: session),
                patch.object(command, "seed_fixed_categories", return_value=FixedCategorySeedResult(10, 57)) as seed,
            ):
                if sys.argv[1] == "failure":
                    seed.side_effect = failure
                if sys.argv[2] != "-1":
                    os.close(int(sys.argv[2]))
                raise SystemExit(command.main(sys.argv[3:]))
        """)
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        try:
            closed_fd = (1 if stream == "stdout" else 2) if close_descriptor else -1
            return subprocess.run(
                [sys.executable, "-c", script, mode, str(closed_fd), *argv],
                stdout=write_fd if stream == "stdout" else subprocess.PIPE,
                stderr=write_fd if stream == "stderr" else subprocess.PIPE,
                timeout=10,
            )
        finally:
            os.close(write_fd)


def _database_error() -> StatementError:
    return StatementError("PRIVATE_DB_DETAIL", "PRIVATE_SQL", {"value": "PRIVATE_DB_DETAIL"}, RuntimeError("PRIVATE_DB_DETAIL"))


if __name__ == "__main__":
    unittest.main()
