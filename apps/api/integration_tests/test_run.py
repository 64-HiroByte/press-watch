import os
import subprocess
import unittest
from unittest.mock import patch

from integration_tests import run
from integration_tests.database import (
    TEST_DATABASE_PASSWORD_ENV,
    TEST_DATABASE_URL_ENV,
    validate_test_database_url,
)
from press_watch_api.config import DATABASE_URL_ENV


class IntegrationTestRunnerTest(unittest.TestCase):
    """ローカルとCIで共有するDB統合テスト実行支援のテスト"""

    def test_ci_password_builds_test_url_without_product_database_url(
        self,
    ) -> None:
        """CI用パスワードから専用URLを生成し製品用URLを渡さないこと"""

        environment = {
            DATABASE_URL_ENV: "product-database-value",
            TEST_DATABASE_PASSWORD_ENV: "test-only-value",
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            patch(
                "integration_tests.run._run_integration_tests",
                return_value=0,
            ) as run_integration_tests,
            patch("integration_tests.run.subprocess.run") as subprocess_run,
        ):
            exit_code = run.main()

        self.assertEqual(exit_code, 0)
        run_environment = run_integration_tests.call_args.args[0]
        self.assertNotIn(DATABASE_URL_ENV, run_environment)
        validate_test_database_url(run_environment[TEST_DATABASE_URL_ENV])
        subprocess_run.assert_not_called()

    def test_local_postgresql_is_stopped_after_test_failure(self) -> None:
        """統合テスト失敗時にもテスト専用Composeを停止すること"""

        test_environment = {"TEST_VALUE": "test-only-value"}
        with (
            patch("integration_tests.run.subprocess.run") as subprocess_run,
            patch(
                "integration_tests.run._run_integration_tests",
                return_value=1,
            ),
        ):
            subprocess_run.return_value.returncode = 0
            exit_code = run._run_with_local_postgresql(test_environment)

        self.assertEqual(exit_code, 1)
        self.assertEqual(subprocess_run.call_count, 2)
        self.assertEqual(
            subprocess_run.call_args_list[0].args[0][-4:],
            ["up", "--detach", "--wait", "--force-recreate"],
        )
        self.assertEqual(
            subprocess_run.call_args_list[1].args[0][-2:],
            ["down", "--remove-orphans"],
        )
        for compose_call in subprocess_run.call_args_list:
            self.assertEqual(
                compose_call.kwargs["env"]["TEST_VALUE"],
                "test-only-value",
            )

    def test_local_postgresql_disables_compose_environment_files(self) -> None:
        """外部env fileを使わずテスト専用Composeを実行すること"""

        test_environment = {
            "COMPOSE_DISABLE_ENV_FILE": "0",
            "COMPOSE_ENV_FILES": "external-value",
            "TEST_VALUE": "test-only-value",
        }
        with (
            patch("integration_tests.run.subprocess.run") as subprocess_run,
            patch(
                "integration_tests.run._run_integration_tests",
                return_value=0,
            ),
        ):
            subprocess_run.return_value.returncode = 0
            exit_code = run._run_with_local_postgresql(test_environment)

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            test_environment,
            {
                "COMPOSE_DISABLE_ENV_FILE": "0",
                "COMPOSE_ENV_FILES": "external-value",
                "TEST_VALUE": "test-only-value",
            },
        )
        for compose_call in subprocess_run.call_args_list:
            compose_environment = compose_call.kwargs["env"]
            self.assertEqual(
                compose_environment["COMPOSE_DISABLE_ENV_FILE"],
                "1",
            )
            self.assertNotIn("COMPOSE_ENV_FILES", compose_environment)
            self.assertEqual(
                compose_environment["TEST_VALUE"],
                "test-only-value",
            )

    def test_local_postgresql_reports_cleanup_failure(self) -> None:
        """統合テスト成功後のCompose停止失敗を成功扱いにしないこと"""

        with (
            patch(
                "integration_tests.run.subprocess.run",
                side_effect=(
                    subprocess.CompletedProcess(args=[], returncode=0),
                    subprocess.CompletedProcess(args=[], returncode=3),
                ),
            ),
            patch(
                "integration_tests.run._run_integration_tests",
                return_value=0,
            ),
        ):
            exit_code = run._run_with_local_postgresql({})

        self.assertEqual(exit_code, 3)

    def test_local_postgresql_is_stopped_after_startup_failure(self) -> None:
        """Compose起動失敗時にもテスト専用Composeを停止すること"""

        with (
            patch(
                "integration_tests.run.subprocess.run",
                side_effect=(
                    subprocess.CalledProcessError(
                        returncode=1,
                        cmd=["docker", "compose", "up"],
                    ),
                    subprocess.CompletedProcess(args=[], returncode=0),
                ),
            ) as subprocess_run,
            patch(
                "integration_tests.run._run_integration_tests"
            ) as run_integration_tests,
            self.assertRaises(subprocess.CalledProcessError),
        ):
            run._run_with_local_postgresql({})

        self.assertEqual(subprocess_run.call_count, 2)
        run_integration_tests.assert_not_called()


if __name__ == "__main__":
    unittest.main()
