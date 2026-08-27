import os
from pathlib import Path
import secrets
import subprocess
import sys

from sqlalchemy import URL

from integration_tests.database import (
    TEST_DATABASE_DRIVER,
    TEST_DATABASE_HOST,
    TEST_DATABASE_NAME,
    TEST_DATABASE_PASSWORD_ENV,
    TEST_DATABASE_PORT,
    TEST_DATABASE_URL_ENV,
    TEST_DATABASE_USER,
)
from press_watch_api.config import DATABASE_URL_ENV


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_COMPOSE_FILE = _REPOSITORY_ROOT / "infra" / "compose.test.yml"
_COMPOSE_PROJECT_NAME = "press-watch-postgresql-integration"
_COMPOSE_DISABLE_ENV_FILE_ENV = "COMPOSE_DISABLE_ENV_FILE"
_COMPOSE_ENV_FILES_ENV = "COMPOSE_ENV_FILES"


def main() -> int:
    """テスト専用PostgreSQLの起動から終了までを管理

    Returns:
        DB統合テストの終了コード
    """

    test_environment = os.environ.copy()
    test_environment.pop(DATABASE_URL_ENV, None)
    if test_environment.get(TEST_DATABASE_URL_ENV):
        return _run_integration_tests(test_environment)

    inherited_test_password = test_environment.get(TEST_DATABASE_PASSWORD_ENV)
    if inherited_test_password:
        test_environment[TEST_DATABASE_URL_ENV] = _render_test_database_url(
            inherited_test_password
        )
        return _run_integration_tests(test_environment)

    return _run_with_local_postgresql(
        _local_test_environment(test_environment)
    )


def _run_with_local_postgresql(test_environment: dict[str, str]) -> int:
    """ローカルのテスト専用PostgreSQLを使って統合テストを実行

    Args:
        test_environment: Composeと統合テストへ渡すテスト専用環境変数

    Returns:
        DB統合テストの終了コード
    """

    compose_environment = test_environment.copy()
    compose_environment.pop(_COMPOSE_ENV_FILES_ENV, None)
    compose_environment[_COMPOSE_DISABLE_ENV_FILE_ENV] = "1"

    compose_command = [
        "docker",
        "compose",
        "--project-name",
        _COMPOSE_PROJECT_NAME,
        "--file",
        str(_COMPOSE_FILE),
    ]

    try:
        subprocess.run(
            [*compose_command, "up", "--detach", "--wait", "--force-recreate"],
            check=True,
            env=compose_environment,
        )
        test_returncode = _run_integration_tests(test_environment)
    finally:
        cleanup_completed = subprocess.run(
            [*compose_command, "down", "--remove-orphans"],
            check=False,
            env=compose_environment,
        )

    if test_returncode != 0:
        return test_returncode
    return cleanup_completed.returncode


def _local_test_environment(base_environment: dict[str, str]) -> dict[str, str]:
    test_environment = base_environment.copy()
    password = secrets.token_urlsafe(24)
    test_environment[TEST_DATABASE_PASSWORD_ENV] = password
    test_environment[TEST_DATABASE_URL_ENV] = _render_test_database_url(password)
    return test_environment


def _render_test_database_url(password: str) -> str:
    url = URL.create(
        TEST_DATABASE_DRIVER,
        username=TEST_DATABASE_USER,
        password=password,
        host=TEST_DATABASE_HOST,
        port=TEST_DATABASE_PORT,
        database=TEST_DATABASE_NAME,
    )
    return url.render_as_string(hide_password=False)


def _run_integration_tests(environment: dict[str, str]) -> int:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "integration_tests",
            "-t",
            ".",
        ],
        check=False,
        env=environment,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
