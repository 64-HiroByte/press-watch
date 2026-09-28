import importlib
import io
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from integration_tests.database import (
    TEST_DATABASE_PASSWORD_ENV,
    TEST_DATABASE_URL_ENV,
    validate_test_database_url,
)
from press_watch_api.config import DATABASE_URL_ENV


_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "real_snapshot_valid.json"


class RealSnapshotRunnerTest(unittest.TestCase):
    """実データ検証runnerのDB起動前境界のテスト"""

    def test_validation_failure_does_not_start_postgresql(self) -> None:
        """入力検証失敗時はCompose経路へ進まず終了コード1にすること"""

        runner = _import_runner()
        error_output = io.StringIO()
        validation_error = runner.SnapshotValidationError(
            "スナップショットの件数が期待値と一致しません。"
        )
        with (
            patch.object(
                runner,
                "load_validated_snapshot",
                side_effect=validation_error,
            ),
            patch.object(
                runner.integration_runner,
                "_run_with_local_postgresql",
            ) as run_with_local_postgresql,
        ):
            exit_code = runner.main(
                [str(_FIXTURE_PATH)],
                stderr=error_output,
            )

        self.assertEqual(exit_code, 1)
        run_with_local_postgresql.assert_not_called()
        self.assertEqual(
            error_output.getvalue(),
            "入力検証に失敗しました: "
            "スナップショットの件数が期待値と一致しません。\n",
        )

    def test_actual_sha256_failure_does_not_start_postgresql(self) -> None:
        """実loaderのSHA-256不一致でもCompose経路へ進まないこと"""

        runner = _import_runner()
        error_output = io.StringIO()
        with patch.object(
            runner.integration_runner,
            "_run_with_local_postgresql",
        ) as run_with_local_postgresql:
            exit_code = runner.main(
                [str(_FIXTURE_PATH)],
                stderr=error_output,
            )

        self.assertEqual(exit_code, 1)
        run_with_local_postgresql.assert_not_called()
        self.assertEqual(
            error_output.getvalue(),
            "入力検証に失敗しました: "
            "スナップショットのSHA-256が期待値と一致しません。\n",
        )

    def test_valid_snapshot_uses_sanitized_local_postgresql_runner(self) -> None:
        """入力検証後だけ安全化した既存Compose経路へ進むこと"""

        runner = _import_runner()
        environment = {
            DATABASE_URL_ENV: "product-database-value",
            "PGHOST": "external-host",
            TEST_DATABASE_PASSWORD_ENV: "inherited-password",
            TEST_DATABASE_URL_ENV: "inherited-database-url",
            "TEST_VALUE": "preserved-value",
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(
                runner,
                "load_validated_snapshot",
                return_value=Mock(),
            ) as load_validated_snapshot,
            patch.object(
                runner.integration_runner,
                "_run_with_local_postgresql",
                return_value=0,
            ) as run_with_local_postgresql,
        ):
            exit_code = runner.main([str(_FIXTURE_PATH)])

        self.assertEqual(exit_code, 0)
        load_validated_snapshot.assert_called_once_with(
            _FIXTURE_PATH,
            expected_count=runner.EXPECTED_SNAPSHOT_COUNT,
            expected_sha256=runner.EXPECTED_SNAPSHOT_SHA256,
            fetched_at_text=runner.SNAPSHOT_FETCHED_AT_TEXT,
        )
        test_environment = run_with_local_postgresql.call_args.args[0]
        self.assertNotIn(DATABASE_URL_ENV, test_environment)
        self.assertNotIn("PGHOST", test_environment)
        self.assertEqual(test_environment["TEST_VALUE"], "preserved-value")
        self.assertNotEqual(
            test_environment[TEST_DATABASE_PASSWORD_ENV],
            "inherited-password",
        )
        validate_test_database_url(test_environment[TEST_DATABASE_URL_ENV])
        self.assertEqual(
            test_environment[runner.REAL_SNAPSHOT_PATH_ENV],
            str(_FIXTURE_PATH.resolve()),
        )


def _import_runner():
    try:
        return importlib.import_module("integration_tests.run_real_snapshot")
    except ModuleNotFoundError as exc:
        if exc.name != "integration_tests.run_real_snapshot":
            raise
        raise AssertionError(
            "実データスナップショット検証runnerが未実装です"
        ) from None


if __name__ == "__main__":
    unittest.main()
