import argparse
from collections.abc import Sequence
import sys
from pathlib import Path
from typing import TextIO

from integration_tests import run as integration_runner
from integration_tests.database import (
    TEST_DATABASE_PASSWORD_ENV,
    TEST_DATABASE_URL_ENV,
)
from integration_tests.real_snapshot_validation import (
    SnapshotValidationError,
    load_validated_snapshot,
)


EXPECTED_SNAPSHOT_COUNT = 34_421
EXPECTED_SNAPSHOT_SHA256 = (
    "742ec50a03c4b69e8fc88fccd8a95856a94a18d895717c9a6834bcae144d3939"
)
SNAPSHOT_FETCHED_AT_TEXT = "2026-08-29T13:45:27.408274Z"
REAL_SNAPSHOT_PATH_ENV = "PRESSWATCH_REAL_SNAPSHOT_PATH"


def main(
    argv: Sequence[str] | None = None,
    *,
    stderr: TextIO | None = None,
) -> int:
    """入力検証後にテスト専用PostgreSQLで実データ検証を実行

    Args:
        argv: プログラム名を除くCLI引数
        stderr: 入力検証エラーの出力先

    Returns:
        実データ検証とCompose停止処理を含む終了コード
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot_path", type=Path)
    args = parser.parse_args(argv)
    error_output = stderr or sys.stderr

    try:
        load_validated_snapshot(
            args.snapshot_path,
            expected_count=EXPECTED_SNAPSHOT_COUNT,
            expected_sha256=EXPECTED_SNAPSHOT_SHA256,
            fetched_at_text=SNAPSHOT_FETCHED_AT_TEXT,
        )
    except SnapshotValidationError as exc:
        print(f"入力検証に失敗しました: {exc}", file=error_output)
        return 1

    test_environment = integration_runner._sanitized_test_environment()
    test_environment.pop(TEST_DATABASE_PASSWORD_ENV, None)
    test_environment.pop(TEST_DATABASE_URL_ENV, None)
    test_environment[REAL_SNAPSHOT_PATH_ENV] = str(args.snapshot_path.resolve())
    return integration_runner._run_with_local_postgresql(
        integration_runner._local_test_environment(test_environment)
    )


if __name__ == "__main__":
    raise SystemExit(main())
