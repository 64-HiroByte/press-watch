"""同梱CSVから固定カテゴリ初期データを取り込むCLI"""

import argparse
from collections.abc import Callable, Sequence
import json
import os
import sys
from typing import TextIO

from sqlalchemy.orm import Session

from press_watch_api.db import get_session_factory
from press_watch_api.services.fixed_category_seed import (
    FixedCategoryCsvError,
    FixedCategorySeedConflictError,
    load_fixed_category_seed,
    seed_fixed_categories,
)


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable[[], Session] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """固定カテゴリseedを実行し、終了コードを返す

    Args:
        argv: プログラム名を除くCLI引数
        session_factory: テストで差し替え可能なSession生成関数
        stdout: 追加件数JSONの出力先
        stderr: 値や例外詳細を含まない診断の出力先

    Returns:
        成功・ヘルプ表示は0、実行失敗は1、引数不正は2
    """

    output = stdout if stdout is not None else sys.stdout
    error_output = stderr if stderr is not None else sys.stderr
    parser = argparse.ArgumentParser(
        description="Seed bundled fixed categories.", add_help=False, exit_on_error=False,
    )
    parser.add_argument("-h", "--help", action="store_true", help="show this help message and exit")
    try:
        args = parser.parse_args(argv)
    except argparse.ArgumentError as exc:
        return 2 if _print_error(error_output, "arguments", False, exc) else 1
    if args.help:
        try:
            output.write(parser.format_help())
            output.flush()
        except Exception as exc:
            _redirect_stream_after_output_error(output)
            _print_error(error_output, "help", False, exc)
            return 1
        return 0

    session: Session | None = None
    commit_succeeded = False
    operation = "load_csv"
    exit_code = 0
    try:
        data = load_fixed_category_seed()
        operation = "configure"
        factory = session_factory if session_factory is not None else get_session_factory()
        operation = "open_session"
        session = factory()
        operation = "seed"
        result = seed_fixed_categories(session, data)
        operation = "commit"
        session.commit()
        commit_succeeded = True
        operation = "output"
        output.write(json.dumps({
            "categories_added": result.categories_added,
            "keywords_added": result.keywords_added,
        }) + "\n")
        output.flush()
    except Exception as exc:
        exit_code = 1
        if operation == "output":
            _redirect_stream_after_output_error(output)
        _print_error(error_output, operation, commit_succeeded, exc)
        if session is not None and not commit_succeeded:
            try:
                session.rollback()
            except Exception as cleanup_error:
                _print_error(error_output, "rollback", commit_succeeded, cleanup_error)
    finally:
        if session is not None:
            try:
                session.close()
            except Exception as cleanup_error:
                exit_code = 1
                _print_error(error_output, "close", commit_succeeded, cleanup_error)
    return exit_code


def _redirect_stream_after_output_error(output: TextIO) -> None:
    """実stdout・stderrの終了時再flushを破棄先へ切り替え"""

    if output is not sys.stdout and output is not sys.stderr:
        return
    try:
        stream_fd = output.fileno()
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        # 閉じた標準FDと同じ番号で開けた場合は、出力先としてそのまま保持する。
        if devnull_fd != stream_fd:
            try:
                os.dup2(devnull_fd, stream_fd)
            finally:
                os.close(devnull_fd)
    except (AttributeError, OSError, TypeError, ValueError):
        # 切替失敗で元の出力エラーを置き換えない。
        return


def _print_error(
    output: TextIO,
    operation: str,
    commit_succeeded: bool,
    error: Exception,
) -> bool:
    context = ""
    if operation == "load_csv" and isinstance(error, FixedCategoryCsvError):
        reason = error.reason
        context = f" file={error.file_name}"
        if error.line is not None:
            context += f" line={error.line}"
        if error.column is not None:
            context += f" column={error.column}"
    elif operation == "seed" and isinstance(error, FixedCategorySeedConflictError):
        reason = "database definitions differ from bundled CSV"
    else:
        reason = {
            "arguments": "invalid command arguments",
            "help": "help output failed",
            "load_csv": "bundled CSV could not be loaded",
            "configure": "database configuration could not be loaded",
            "output": "database commit succeeded but result output failed",
        }.get(operation, "database operation failed")
    try:
        print(
            f"error: operation={operation} "
            f"commit_succeeded={str(commit_succeeded).lower()}"
            f"{context} reason={reason}",
            file=output,
            flush=True,
        )
    except Exception:
        # 診断出力の失敗で元のDB例外の詳細を外へ伝えない。
        _redirect_stream_after_output_error(output)
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
